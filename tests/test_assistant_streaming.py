from app.assistant.service import _AnswerFieldStreamDecoder


def test_answer_decoder_streams_only_human_readable_text() -> None:
    decoder = _AnswerFieldStreamDecoder()
    chunks = [
        '{"answer":"Hello',
        "\\nMinzo ",
        "user",
        '","proposed_action":null}',
    ]

    result = "".join(text for chunk in chunks for text in decoder.feed(chunk))

    assert result == "Hello\nMinzo user"


def test_answer_decoder_handles_unicode_surrogate_pairs() -> None:
    decoder = _AnswerFieldStreamDecoder()

    result = "".join(decoder.feed('{"answer":"Hello \\uD83D\\uDC4B"}'))

    assert result == "Hello 👋"
