import asyncio
import logging
from typing import Literal
from uuid import UUID

import httpx
from pydantic import ValidationError

from app.schemas.review_evaluation import ModerationCallbackResponse

logger = logging.getLogger(__name__)


class ModerationCallbackError(RuntimeError):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code


class ModerationApiClient:
    """Only the moderation workflow uses this client; it is never a chat tool."""

    def __init__(self, client: httpx.AsyncClient, service_key: str | None) -> None:
        self._client = client
        self._service_key = service_key

    def require_configured(self) -> None:
        if not self._service_key or len(self._service_key.strip()) < 32:
            raise ModerationCallbackError(
                503, "moderation_not_configured", "AI_MODERATION_SERVICE_KEY is not configured."
            )

    async def record_decision(
        self,
        *,
        review_id: UUID,
        review_updated_at: str,
        decision: Literal["APPROVED", "FLAGGED", "REJECTED"],
        reason: str,
    ) -> ModerationCallbackResponse:
        self.require_configured()
        path = f"/api/v1/automation/customer-reviews/{review_id}/moderation"
        for attempt in range(3):
            try:
                response = await self._client.patch(
                    path,
                    headers={"X-Service-Key": self._service_key, "Accept": "application/json"},
                    json={
                        "decision": decision,
                        "reason": reason,
                        "reviewUpdatedAt": review_updated_at,
                    },
                )
            except httpx.TransportError:
                response = None

            if response is not None:
                if response.status_code in {404, 409}:
                    raise ModerationCallbackError(
                        response.status_code,
                        "review_missing" if response.status_code == 404 else "review_conflict",
                        "The review is missing, changed, or already moderated. "
                        "Do not apply this decision again.",
                    )
                if response.status_code == 200:
                    try:
                        result = ModerationCallbackResponse.model_validate(response.json())
                        expected_publication = "HIDDEN" if decision == "REJECTED" else "PUBLISHED"
                        if (
                            result.reviewId != review_id
                            or result.moderationStatus != decision
                            or result.moderation.decision != decision
                            or result.publicationStatus != expected_publication
                        ):
                            raise ValueError("Callback result does not match the decision")
                        return result
                    except (ValidationError, ValueError) as exc:
                        raise ModerationCallbackError(
                            502, "invalid_callback_response", "Backend confirmation was invalid."
                        ) from exc
                if response.status_code < 500:
                    raise ModerationCallbackError(
                        502,
                        "callback_rejected",
                        "Backend rejected the moderation callback. "
                        "Check its service key and contract.",
                    )

            if attempt < 2:
                logger.warning(
                    "Retrying moderation callback",
                    extra={"review_id": str(review_id), "attempt": attempt + 1},
                )
                await asyncio.sleep(0.25 * (2**attempt))

        raise ModerationCallbackError(
            502, "callback_unavailable", "Could not confirm that Backend saved the decision."
        )
