from pathlib import Path


def test_playground_launcher_invokes_hoisted_next_directly() -> None:
    repo_root = Path(__file__).parents[2]
    launcher = (repo_root / "scripts" / "playground.ps1").read_text(encoding="utf-8")

    assert '$env:UMBRAL_ACCESS_MODE = "product_session"' in launcher
    assert '[string]$SnapshotPath = ""' in launcher
    assert '$env:PLAYGROUND_SNAPSHOT_PATH' in launcher
    assert "real-snapshot.json" in launcher
    assert '$apiProbe = "http://127.0.0.1:$ApiPort/api/v1/playground/fixtures"' in launcher
    assert 'Invoke-WebRequest -Uri $apiProbe' in launcher
    assert '$expectRealSnapshot' in launcher
    assert 'respondió demo-only' in launcher
    assert 'El API del playground no respondió 200' in launcher
    assert '$nextExitCode = $LASTEXITCODE' in launcher
    assert 'No se pudo iniciar Next' in launcher
    assert '$next = Join-Path $repoRoot "node_modules\\.bin\\next.cmd"' in launcher
    assert "& $next dev --port $WebPort" in launcher
    assert "npm run dev -- --port" not in launcher
