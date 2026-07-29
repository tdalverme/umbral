from __future__ import annotations

from umbral.workers.__main__ import main


def test_worker_cli_commands_are_safe_to_parse() -> None:
    assert main(["worker"]) == 0
    assert main(["scheduler"]) == 0
