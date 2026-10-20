from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import StrictModel
from app.schemas.moderation import AbuseCategory


class ReviewBusinessContext(StrictModel):
    id: UUID
    name: str = Field(min_length=1, max_length=300)


class ReviewEvaluationRequest(StrictModel):
    reviewId: UUID
    reviewUpdatedAt: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$",
        description="Copy updatedAt from the Backend review unchanged, including the UTC Z suffix.",
    )
    stars: int = Field(ge=1, le=5)
    text: str = Field(min_length=3, max_length=5_000)
    business: ReviewBusinessContext

    @field_validator("reviewUpdatedAt")
    @classmethod
    def valid_timestamp(cls, value: str) -> str:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("text")
    @classmethod
    def nonblank_review(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class ReviewEvaluationResponse(StrictModel):
    reviewId: UUID
    reviewUpdatedAt: str
    decision: Literal["APPROVED", "FLAGGED", "REJECTED"]
    reason: str
    confidence: float = Field(ge=0, le=1)
    categories: list[AbuseCategory]
    callbackStatus: Literal["RECORDED"] = "RECORDED"
    moderationId: UUID
    moderatedBy: Literal["AI"] = "AI"


class RecordedModeration(StrictModel):
    id: UUID
    actorType: Literal["AUTOMATION"]
    decision: Literal["APPROVED", "FLAGGED", "REJECTED"]
    adminUserId: None
    actorReference: str
    reason: str | None
    createdAt: datetime
    moderatedBy: Literal["AI"]


class ModerationCallbackResponse(StrictModel):
    reviewId: UUID
    publicationStatus: Literal["PUBLISHED", "HIDDEN"]
    moderationStatus: Literal["APPROVED", "FLAGGED", "REJECTED"]
    moderation: RecordedModeration
