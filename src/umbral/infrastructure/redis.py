"""Shared Redis client construction for long-lived runtime processes."""

from __future__ import annotations

from redis import Redis

_REDIS_HEALTH_CHECK_INTERVAL_SECONDS = 30


def build_redis_connection(url: str) -> Redis[bytes]:
    """Build a client that refreshes connections before proxy idle expiry."""

    return Redis.from_url(
        url,
        health_check_interval=_REDIS_HEALTH_CHECK_INTERVAL_SECONDS,
    )
