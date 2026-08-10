"""Message content contract: optional bounded context (UM-H4-025, T057)."""

from __future__ import annotations

from umbral.application.chat.contracts import validate_message_content


def test_context_is_accepted_on_user_text() -> None:
    errors = validate_message_content(
        {"kind": "text", "text": "contame de este listing", "context": {"entity": "listing", "id": "l1"}},
        max_text_length=4000,
    )
    assert errors == ()


def test_comparison_context_is_accepted() -> None:
    errors = validate_message_content(
        {"kind": "text", "text": "comparalos", "context": {"entity": "comparison", "id": "a,b"}},
        max_text_length=4000,
    )
    assert errors == ()


def test_malformed_context_is_rejected() -> None:
    for bad in (
        {"entity": "listing"},
        {"id": "x"},
        {"entity": "alien", "id": "x"},
        {"entity": "listing", "id": ""},
        "listing",
    ):
        errors = validate_message_content(
            {"kind": "text", "text": "hola", "context": bad},
            max_text_length=4000,
        )
        assert "chat.content_bad_context" in errors
