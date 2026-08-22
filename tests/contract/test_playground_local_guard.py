from umbral.application.playground.service import playground_enabled


def test_playground_is_local_only() -> None:
    assert playground_enabled("local") is True
    assert playground_enabled("preview") is False
    assert playground_enabled("production") is False
