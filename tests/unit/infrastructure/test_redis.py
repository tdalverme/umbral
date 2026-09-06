from redis import Redis

from umbral.infrastructure.redis import build_redis_connection


def test_build_redis_connection_enables_periodic_health_checks() -> None:
    connection = build_redis_connection("redis://127.0.0.1:6379/0")

    assert isinstance(connection, Redis)
    assert connection.connection_pool.connection_kwargs["health_check_interval"] == 30

    connection.close()
