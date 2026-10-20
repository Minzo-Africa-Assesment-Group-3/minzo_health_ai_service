from fastapi import APIRouter

from app.api.dependencies import ReviewEvaluationDep, ReviewModeratorDep
from app.schemas.moderation import ReviewModerationRequest, ReviewModerationResponse
from app.schemas.review_evaluation import ReviewEvaluationRequest, ReviewEvaluationResponse

router = APIRouter()


@router.post("/reviews", response_model=ReviewModerationResponse)
async def moderate_review(
    payload: ReviewModerationRequest,
    moderator: ReviewModeratorDep,
) -> ReviewModerationResponse:
    return await moderator.moderate(payload)


@router.post(
    "/customer-reviews/evaluate",
    response_model=ReviewEvaluationResponse,
    summary="Analyse a published review and save the moderation decision",
    description=(
        "Use an existing review ID and its exact updatedAt value from Backend. "
        "Returns RECORDED only after Backend confirms the decision. "
        "APPROVED remains visible, FLAGGED awaits an admin, REJECTED becomes hidden."
    ),
    responses={
        401: {"description": "Invalid AI service key"},
        404: {"description": "Backend review no longer exists"},
        409: {"description": "Review changed or has already been moderated"},
        502: {"description": "Backend callback could not be confirmed"},
        503: {"description": "Required service configuration is missing"},
    },
)
async def evaluate_customer_review(
    payload: ReviewEvaluationRequest,
    evaluator: ReviewEvaluationDep,
) -> ReviewEvaluationResponse:
    return await evaluator.evaluate(payload)
