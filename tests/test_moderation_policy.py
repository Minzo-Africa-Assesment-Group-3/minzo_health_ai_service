from app.review_moderation.service import enforce_moderation_policy
from app.schemas.moderation import ReviewModerationDecision


def _decision(**overrides):
    values = {
        "is_abusive": False,
        "action": "allow",
        "categories": ["none"],
        "severity": "none",
        "confidence": 0.99,
        "explanation": "Ordinary negative feedback",
        "requires_human_review": False,
    }
    values.update(overrides)
    return ReviewModerationDecision.model_validate(values)


def _enforce(decision: ReviewModerationDecision) -> ReviewModerationDecision:
    return enforce_moderation_policy(
        decision,
        flag_confidence_threshold=0.85,
        block_confidence_threshold=0.95,
    )


def test_low_confidence_decision_is_escalated() -> None:
    result = _enforce(_decision(confidence=0.7))
    assert result.action == "flag"
    assert result.requires_human_review is True


def test_harassment_is_rejected_without_human_review() -> None:
    result = _enforce(
        _decision(
            is_abusive=True,
            action="block",
            categories=["harassment"],
            severity="medium",
            confidence=0.99,
        )
    )
    assert result.action == "block"
    assert result.requires_human_review is False


def test_profanity_is_rejected_without_human_review() -> None:
    result = _enforce(
        _decision(
            is_abusive=True,
            action="flag",
            categories=["profanity"],
            severity="low",
            confidence=0.7,
        )
    )

    assert result.action == "block"
    assert result.requires_human_review is False


def test_high_confidence_severe_block_is_preserved() -> None:
    result = _enforce(
        _decision(
            is_abusive=True,
            action="block",
            categories=["threat"],
            severity="high",
            confidence=0.99,
        )
    )
    assert result.action == "block"
    assert result.requires_human_review is False


def test_model_cannot_allow_hate_content() -> None:
    result = _enforce(
        _decision(
            action="allow",
            categories=["hate"],
            severity="high",
            confidence=0.99,
        )
    )
    assert result.action == "block"
    assert result.is_abusive is True
