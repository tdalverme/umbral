from pathlib import Path


def test_playground_launcher_invokes_hoisted_next_directly() -> None:
    repo_root = Path(__file__).parents[2]
    launcher = (repo_root / "scripts" / "playground.ps1").read_text(encoding="utf-8")

    assert '$next = Join-Path $repoRoot "node_modules\\.bin\\next.cmd"' in launcher
    assert "& $next dev --port $WebPort" in launcher
    assert "npm run dev -- --port" not in launcher
