from typing import Literal
from uuid import uuid4

from pydantic import Field, SecretStr, field_validator, model_validator

from app.schemas.common import StrictModel


class ConversationMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=5_000)


AssistantCapability = Literal["send_business_message"]


class AssistantPrincipal(StrictModel):
    """Trusted caller context supplied by Express, never by the browser directly."""

    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    capabilities: set[AssistantCapability] = Field(default_factory=set)
    delegation_token: SecretStr | None = None

    @model_validator(mode="after")
    def validate_write_context(self) -> "AssistantPrincipal":
        if self.capabilities and (self.user_id is None or self.delegation_token is None):
            raise ValueError(
                "write capabilities require an authenticated user and delegation token"
            )
        return self


class AssistantBusinessContext(StrictModel):
    business_id: str | None = Field(default=None, min_length=1, max_length=128)
    business_slug: str | None = Field(default=None, min_length=1, max_length=200)


class SendBusinessMessageAction(StrictModel):
    type: Literal["send_business_message"] = "send_business_message"
    business_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2_000)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class ProposedBusinessMessageAction(StrictModel):
    type: Literal["send_business_message"] = "send_business_message"
    business_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=2_000)
    requires_confirmation: Literal[True] = True


class AssistantAgentOutput(StrictModel):
    answer: str = Field(min_length=1, max_length=10_000)
    proposed_action: ProposedBusinessMessageAction | None = None


class AssistantRequest(StrictModel):
    conversation_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=128)
    principal: AssistantPrincipal = Field(default_factory=AssistantPrincipal)
    message: str = Field(min_length=1, max_length=5_000)
    business_context: AssistantBusinessContext | None = None
    history: list[ConversationMessage] = Field(default_factory=list, max_length=20)
    confirmed_action: SendBusinessMessageAction | None = None

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value

    @model_validator(mode="after")
    def validate_confirmed_action(self) -> "AssistantRequest":
        if self.confirmed_action is not None and (
            "send_business_message" not in self.principal.capabilities
        ):
            raise ValueError("confirmed action is not permitted by the trusted principal context")
        return self


class AssistantResponse(StrictModel):
    conversation_id: str
    answer: str
    proposed_action: ProposedBusinessMessageAction | None = None
