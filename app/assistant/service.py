import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from app.assistant.prompts import SYSTEM_PROMPT
from app.assistant.tools import build_tools
from app.clients.express_api import ExpressApiClient
from app.schemas.assistant import (
    AssistantAgentOutput,
    AssistantRequest,
    AssistantResponse,
)

logger = logging.getLogger(__name__)


class AssistantService:
    def __init__(self, model: ChatOpenAI, express_api: ExpressApiClient) -> None:
        self._model = model
        self._express_api = express_api

    async def respond(self, request: AssistantRequest) -> AssistantResponse:
        agent, messages = self._create_agent_run(request)

        result: dict[str, Any] = await agent.ainvoke({"messages": messages})
        structured_response = result.get("structured_response")
        if structured_response is not None:
            output = (
                structured_response
                if isinstance(structured_response, AssistantAgentOutput)
                else AssistantAgentOutput.model_validate(structured_response)
            )
            return AssistantResponse(
                conversation_id=request.conversation_id,
                answer=output.answer,
                proposed_action=output.proposed_action,
            )

        final_message = result["messages"][-1]
        if not isinstance(final_message, AIMessage):
            raise RuntimeError("Agent did not return a final assistant message")
        return AssistantResponse(
            conversation_id=request.conversation_id,
            answer=_content_to_text(final_message.content),
        )

    async def stream(self, request: AssistantRequest) -> AsyncIterator[dict[str, Any]]:
        """Stream clean answer tokens and finish with structured action metadata."""

        agent, messages = self._create_agent_run(request)
        decoder = _AnswerFieldStreamDecoder()
        raw_output: list[str] = []

        yield {"type": "start", "conversationId": request.conversation_id}

        try:
            async for token, metadata in agent.astream(
                {"messages": messages},
                stream_mode="messages",
            ):
                if metadata.get("langgraph_node") != "model" or not token.text:
                    continue

                raw_output.append(token.text)
                decoded_text = "".join(decoder.feed(token.text))
                if decoded_text:
                    yield {"type": "token", "text": decoded_text}

            output = AssistantAgentOutput.model_validate_json("".join(raw_output))
            if output.proposed_action is not None:
                yield {
                    "type": "proposed_action",
                    "action": output.proposed_action.model_dump(mode="json"),
                }
            yield {"type": "done", "conversationId": request.conversation_id}
        except Exception:
            logger.exception(
                "Assistant streaming failed",
                extra={"conversation_id": request.conversation_id},
            )
            yield {
                "type": "error",
                "message": "The assistant response could not be completed.",
            }

    def _create_agent_run(self, request: AssistantRequest) -> tuple[Any, list[dict[str, str]]]:
        tools = build_tools(
            self._express_api,
            request.principal,
            request.confirmed_action,
        )
        trusted_context = _trusted_context(request)
        agent = create_agent(
            model=self._model,
            tools=tools,
            system_prompt=f"{SYSTEM_PROMPT}\n\n{trusted_context}",
            response_format=AssistantAgentOutput,
        )

        messages: list[dict[str, str]] = [
            {"role": item.role, "content": item.content} for item in request.history
        ]
        messages.append({"role": "user", "content": request.message})
        return agent, messages


class _AnswerFieldStreamDecoder:
    """Incrementally extract the JSON `answer` string without exposing JSON framing."""

    _answer_start = re.compile(r'"answer"\s*:\s*"')

    def __init__(self) -> None:
        self._prefix = ""
        self._started = False
        self._finished = False
        self._escaped = False
        self._unicode_digits = ""
        self._pending_high_surrogate: int | None = None

    def feed(self, chunk: str) -> list[str]:
        if self._finished or not chunk:
            return []

        if not self._started:
            self._prefix += chunk
            match = self._answer_start.search(self._prefix)
            if match is None:
                return []
            chunk = self._prefix[match.end() :]
            self._prefix = ""
            self._started = True

        output: list[str] = []
        for character in chunk:
            if self._unicode_digits:
                self._unicode_digits += character
                if len(self._unicode_digits) == 5:
                    codepoint = int(self._unicode_digits[1:], 16)
                    self._unicode_digits = ""
                    self._append_codepoint(codepoint, output)
                continue

            if self._escaped:
                self._escaped = False
                if character == "u":
                    self._unicode_digits = "u"
                    continue
                escapes = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                output.append(escapes.get(character, character))
                continue

            if character == "\\":
                self._escaped = True
            elif character == '"':
                if self._pending_high_surrogate is not None:
                    output.append("�")
                    self._pending_high_surrogate = None
                self._finished = True
                break
            else:
                output.append(character)

        return output

    def _append_codepoint(self, codepoint: int, output: list[str]) -> None:
        if 0xD800 <= codepoint <= 0xDBFF:
            self._pending_high_surrogate = codepoint
            return
        if 0xDC00 <= codepoint <= 0xDFFF and self._pending_high_surrogate is not None:
            high = self._pending_high_surrogate
            self._pending_high_surrogate = None
            output.append(chr(0x10000 + ((high - 0xD800) << 10) + (codepoint - 0xDC00)))
            return
        if self._pending_high_surrogate is not None:
            output.append("�")
            self._pending_high_surrogate = None
        output.append(chr(codepoint))


def _trusted_context(request: AssistantRequest) -> str:
    lines = [f"Trusted conversation ID: {request.conversation_id}"]
    if request.business_context is not None:
        if request.business_context.business_id:
            lines.append(f"Trusted current business ID: {request.business_context.business_id}")
        if request.business_context.business_slug:
            lines.append(f"Trusted current business slug: {request.business_context.business_slug}")
    if request.confirmed_action is not None:
        lines.append(
            "A server-verified business-message action has been confirmed. "
            "Invoke send_confirmed_message_to_business exactly once."
        )
    else:
        lines.append("No write action has been confirmed for this request.")
    return "\n".join(lines)


def _content_to_text(content: str | list[str | dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts).strip()
