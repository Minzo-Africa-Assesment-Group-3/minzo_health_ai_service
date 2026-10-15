from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import StrictModel

AbuseCategory = Literal[
    "harassment",
    "hate",
    "threat",
    "sexual_content",
    "personal_information",
    "spam",
    "fraud",
    "profanity",
    "none",
]


class ReviewModerationRequest(StrictModel):
    review_id: str = Field(min_length=1, max_length=128)
    review_version: str | None = Field(default=None, min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=10_000)
    stars: int | None = Field(default=None, ge=1, le=5)
    locale: str = Field(default="en-LR", min_length=2, max_length=20)

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


class ReviewModerationDecision(StrictModel):
    is_abusive: bool
    action: Literal["allow", "flag", "block"]
    categories: list[AbuseCategory] = Field(min_length=1)
    severity: Literal["none", "low", "medium", "high"]
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(
        description="Short policy explanation; do not include private reasoning."
    )
    requires_human_review: bool

    @model_validator(mode="after")
    def validate_categories(self) -> "ReviewModerationDecision":
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("categories must not contain duplicates")
        if "none" in self.categories and len(self.categories) != 1:
            raise ValueError("none cannot be combined with another moderation category")
        return self


class ReviewModerationResponse(StrictModel):
    review_id: str
    review_version: str | None
    content_hash: str
    policy_version: str
    model: str
    decision: ReviewModerationDecision
