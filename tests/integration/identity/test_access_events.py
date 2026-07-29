from __future__ import annotations

import pytest

from umbral.domain.identity.events import EVENT_RESULTS, validate_event


def test_every_closed_event_result_is_validated() -> None:
    for event_type, results in EVENT_RESULTS.items():
        for result in results:
            validate_event(
                event_type=event_type,
                result=result,
                reason="eligible",
                fields={"attempt_id": "internal-reference"},
            )


def test_unknown_event_and_reason_are_rejected() -> None:
    with pytest.raises(ValueError):
        validate_event(
            event_type="identity.unknown.v1",
            result="accepted",
            reason="eligible",
            fields={},
        )
    with pytest.raises(ValueError):
        validate_event(
            event_type="magic_link.issued.v1",
            result="accepted",
            reason="unknown-reason",
            fields={},
        )
