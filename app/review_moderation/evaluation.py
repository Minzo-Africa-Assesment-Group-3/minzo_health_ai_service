from typing import Literal

from app.clients.moderation_api import ModerationApiClient
from app.review_moderation.service import ReviewModerator
from app.schemas.moderation import ReviewModerationRequest
from app.schemas.review_evaluation import ReviewEvaluationRequest, ReviewEvaluationResponse

DECISIONS: dict[str, Literal["APPROVED", "FLAGGED", "REJECTED"]] = {
    "allow": "APPROVED",
    "flag": "FLAGGED",
    "block": "REJECTED",
}


class ReviewEvaluationService:
    def __init__(self, moderator: ReviewModerator, callback: ModerationApiClient) -> None:
        self._moderator = moderator
        self._callback = callback

    async def evaluate(self, request: ReviewEvaluationRequest) -> ReviewEvaluationResponse:
        self._callback.require_configured()
        analysis = await self._moderator.moderate(
            ReviewModerationRequest(
                review_id=str(request.reviewId),
                review_version=request.reviewUpdatedAt,
                text=request.text,
                stars=request.stars,
            ),
            business_context=request.business.model_dump(mode="json"),
        )
        decision = DECISIONS[analysis.decision.action]
        reason = analysis.decision.explanation.strip()[:1000]
        if len(reason) < 3:
            # Missing explanations require human assessment, never an unexplained rejection.
            decision = "FLAGGED"
            reason = "The model did not provide a usable explanation. Requires admin review."
        saved = await self._callback.record_decision(
            review_id=request.reviewId,
            review_updated_at=request.reviewUpdatedAt,
            decision=decision,
            reason=reason,
        )
        return ReviewEvaluationResponse(
            reviewId=request.reviewId,
            reviewUpdatedAt=request.reviewUpdatedAt,
            decision=decision,
            reason=reason,
            confidence=analysis.decision.confidence,
            categories=analysis.decision.categories,
            moderationId=saved.moderation.id,
        )
