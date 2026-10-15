from fastapi import APIRouter

from app.api.dependencies import ReviewModeratorDep
from app.schemas.moderation import ReviewModerationRequest, ReviewModerationResponse

router = APIRouter()


@router.post("/reviews", response_model=ReviewModerationResponse)
async def moderate_review(
    payload: ReviewModerationRequest,
    moderator: ReviewModeratorDep,
) -> ReviewModerationResponse:
    return await moderator.moderate(payload)
