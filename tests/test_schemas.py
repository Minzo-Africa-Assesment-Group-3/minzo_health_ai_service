import pytest
from pydantic import ValidationError

from app.schemas.assistant import (
    AssistantPrincipal,
    AssistantRequest,
    SendBusinessMessageAction,
)
from app.schemas.moderation import ReviewModerationDecision, ReviewModerationRequest


def test_assistant_message_is_trimmed() -> None:
    request = AssistantRequest(message="  Find a clinic  ")
    assert request.message == "Find a clinic"


def test_confirmed_action_requires_trusted_capability() -> None:
    with pytest.raises(ValidationError):
        AssistantRequest(
            message="Send it",
            confirmed_action=SendBusinessMessageAction(
                business_id="business-1",
                message="Hello",
                idempotency_key="message-12345",
            ),
        )


def test_write_capability_requires_delegation_context() -> None:
    with pytest.raises(ValidationError):
        AssistantPrincipal(
            user_id="user-1",
            capabilities={"send_business_message"},
        )


def test_blank_review_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ReviewModerationRequest(review_id="review-1", text="   ")


def test_moderation_confidence_must_be_bounded() -> None:
    with pytest.raises(ValidationError):
        ReviewModerationDecision(
            is_abusive=True,
            action="flag",
            categories=["harassment"],
            severity="medium",
            confidence=1.5,
            explanation="Targeted insult",
            requires_human_review=True,
        )


def test_none_category_cannot_be_combined_with_abuse_category() -> None:
    with pytest.raises(ValidationError):
        ReviewModerationDecision(
            is_abusive=False,
            action="allow",
            categories=["none", "spam"],
            severity="none",
            confidence=0.99,
            explanation="Invalid mixed categories",
            requires_human_review=False,
        )
