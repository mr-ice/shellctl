"""Tests for existing-only and full-paths options in discovery."""

from shellenv.discover import discover_startup_files_modes


def test_existing_only_and_full_paths(tmp_path, monkeypatch):
    """Honor existing-only and full-paths using a controlled tracer."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELLENV_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / ".bashrc").write_text("# test bashrc")

    monkeypatch.setattr("shellenv.discover._run_tracer", lambda *_a, **_k: {".bashrc"})

    modes = discover_startup_files_modes(
        "bash",
        shell_path="/bin/bash",
        force_refresh=True,
        existing_only=True,
        full_paths=True,
    )
    found = False
    for files in modes.values():
        for f in files:
            if str(tmp_path / ".bashrc") == f:
                found = True
    assert found
