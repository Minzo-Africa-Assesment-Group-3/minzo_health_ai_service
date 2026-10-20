from typing import Annotated

from langchain_core.tools import BaseTool, tool
from pydantic import Field

from app.assistant.tools import _read, _validation_message
from app.clients.current_user_api import CurrentUserApiClient


def build_current_user_tools(api: CurrentUserApiClient) -> list[BaseTool]:
    """Only the bound client knows the token. No model-controlled identity arguments."""

    @tool
    async def get_my_profile() -> str:
        """Read the signed-in user's display name, email, phone and account status.

        Use only when the user asks about their own account.
        """
        return await _read(api.get_profile())

    @tool
    async def get_my_reviews(
        page_number: Annotated[int, Field(ge=1)] = 1,
        page_size: Annotated[int, Field(ge=1, le=20)] = 10,
    ) -> str:
        """Read the signed-in user's reviews, newest first, including moderation status.

        Includes the user's anonymous and hidden reviews, excludes deleted reviews.
        Use only when the user asks about their own reviews.
        """
        return await _read(api.get_reviews(page_number=page_number, page_size=page_size))

    tools: list[BaseTool] = [get_my_profile, get_my_reviews]
    for user_tool in tools:
        user_tool.handle_tool_error = True
        user_tool.handle_validation_error = _validation_message
    return tools
