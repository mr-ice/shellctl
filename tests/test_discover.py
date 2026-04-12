"""Tests for the discover functionality."""

import os

from shellenv.discover import discover_startup_files


def test_discover_uses_mock_traces_for_bash(monkeypatch):
    fixtures = os.path.join(os.getcwd(), "tests", "fixtures", "traces")
    monkeypatch.setenv("SHELLENV_MOCK_TRACE_DIR", fixtures)
    monkeypatch.setenv("SHELLENV_USE_SHELL_TRACE", "1")
    monkeypatch.setenv("HOME", "/home/testuser")

    files = discover_startup_files(
        "bash",
        shell_path="/bin/bash",
        force_refresh=True,
    )
    assert any(name in (".bash_profile", ".bashrc") for name in files)


def test_discover_uses_mock_traces_for_zsh(monkeypatch):
    fixtures = os.path.join(os.getcwd(), "tests", "fixtures", "traces")
    monkeypatch.setenv("SHELLENV_MOCK_TRACE_DIR", fixtures)
    monkeypatch.setenv("SHELLENV_USE_SHELL_TRACE", "1")
    monkeypatch.setenv("HOME", "/home/testuser")

    files = discover_startup_files(
        "zsh",
        shell_path="/bin/zsh",
        force_refresh=True,
    )
    assert any(f.startswith(".zsh") for f in files)


def test_discover_uses_mock_traces_for_tcsh(monkeypatch):
    fixtures = os.path.join(os.getcwd(), "tests", "fixtures", "traces")
    monkeypatch.setenv("SHELLENV_MOCK_TRACE_DIR", fixtures)
    monkeypatch.setenv("SHELLENV_USE_SHELL_TRACE", "1")
    monkeypatch.setenv("HOME", "/home/testuser")

    files = discover_startup_files(
        "tcsh",
        shell_path="/bin/tcsh",
        force_refresh=True,
    )
    assert ".tcshrc" in files or ".cshrc" in files or ".login" in files


def test_discover_without_evidence_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELLENV_CACHE_DIR", str(tmp_path / "cache"))

    files = discover_startup_files("bash", shell_path="/no/such/bash", force_refresh=True)
    assert files == []


def test_discover_supplemental_logout_history_inputrc(tmp_path, monkeypatch):
    """Logout/history/readline files are not startup-sourced; still discover if present."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELLENV_CACHE_DIR", str(tmp_path / "cache"))
    (tmp_path / ".bashrc").write_text("# rc")
    (tmp_path / ".bash_profile").write_text("# prof")
    (tmp_path / ".bash_logout").write_text("# bye")
    (tmp_path / ".bash_history").write_text("ls\n")
    (tmp_path / ".inputrc").write_text("set editing-mode vi\n")

    monkeypatch.setattr("shellenv.discover._run_tracer", lambda *_a, **_k: {".bashrc", ".bash_profile"})

    files = discover_startup_files(
        "bash",
        shell_path="/bin/bash",
        force_refresh=True,
        existing_only=True,
        full_paths=True,
    )
    basenames = {os.path.basename(f) for f in files}
    assert ".bash_logout" in basenames
    assert ".bash_history" in basenames
    assert ".inputrc" in basenames
