from __future__ import annotations

from datetime import datetime

import pytest


@pytest.mark.identity
async def test_async_identity_clock_fixture_is_available(
    identity_now: datetime,
) -> None:
    assert identity_now.isoformat() == "2026-01-01T00:00:00+00:00"
