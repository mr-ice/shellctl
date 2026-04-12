"""Tests for the discover modes functionality."""

import os

from shellenv.discover import discover_startup_files_modes


def test_discover_modes_keys_and_contents(monkeypatch, tmp_path):
    """Per-mode keys exist; mock traces supply at least one bash startup file."""
    fixtures = os.path.join(os.getcwd(), "tests", "fixtures", "traces")
    monkeypatch.setenv("SHELLENV_MOCK_TRACE_DIR", fixtures)
    monkeypatch.setenv("SHELLENV_USE_SHELL_TRACE", "1")
    monkeypatch.setenv("HOME", "/home/testuser")
    monkeypatch.setenv("SHELLENV_CACHE_DIR", str(tmp_path / "cache"))

    modes = discover_startup_files_modes(
        "bash",
        shell_path="/bin/bash",
        force_refresh=True,
    )
    expected_modes = [
        "login_interactive",
        "login_noninteractive",
        "nonlogin_interactive",
        "nonlogin_noninteractive",
    ]
    for m in expected_modes:
        assert m in modes
        assert isinstance(modes[m], list)

    assert any(
        any(name in (".bashrc", ".profile", ".bash_profile") for name in modes[m]) for m in modes
    )
