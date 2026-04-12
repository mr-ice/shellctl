"""Tests for discovery cache TTL and force_refresh."""

import json
import time

from shellenv.discover import (
    _cache_path,
    discover_startup_files_modes,
    get_discovery_cache_ttl_secs,
)


def test_fresh_cache_skips_tracer(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    cdir = tmp_path / "cache"
    monkeypatch.setenv("SHELLENV_CACHE_DIR", str(cdir))
    monkeypatch.setenv("SHELLENV_DISCOVER_CACHE_TTL_SECS", "999999")

    p = _cache_path("bash", "login_noninteractive")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"updated": time.time(), "files": [".profile"]}),
        encoding="utf8",
    )

    calls = {"n": 0}

    def fake_run_tracer(*_a, **_k):
        calls["n"] += 1
        return {".bashrc"}

    monkeypatch.setattr("shellenv.discover._run_tracer", fake_run_tracer)

    modes = discover_startup_files_modes(
        "bash",
        shell_path="/bin/bash",
        force_refresh=False,
        modes=["login_noninteractive"],
    )
    assert calls["n"] == 0
    assert ".profile" in modes["login_noninteractive"]


def test_stale_cache_runs_tracer(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    cdir = tmp_path / "cache"
    monkeypatch.setenv("SHELLENV_CACHE_DIR", str(cdir))
    monkeypatch.setenv("SHELLENV_DISCOVER_CACHE_TTL_SECS", "60")

    p = _cache_path("bash", "login_noninteractive")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"updated": time.time() - 86400, "files": [".profile"]}),
        encoding="utf8",
    )

    calls = {"n": 0}

    def fake_run_tracer(*_a, **_k):
        calls["n"] += 1
        return {".bashrc"}

    monkeypatch.setattr("shellenv.discover._run_tracer", fake_run_tracer)

    modes = discover_startup_files_modes(
        "bash",
        shell_path="/bin/bash",
        force_refresh=False,
        modes=["login_noninteractive"],
    )
    assert calls["n"] == 1
    assert ".bashrc" in modes["login_noninteractive"]


def test_force_refresh_ignores_fresh_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    cdir = tmp_path / "cache"
    monkeypatch.setenv("SHELLENV_CACHE_DIR", str(cdir))
    monkeypatch.setenv("SHELLENV_DISCOVER_CACHE_TTL_SECS", "999999")

    p = _cache_path("bash", "login_noninteractive")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"updated": time.time(), "files": [".profile"]}),
        encoding="utf8",
    )

    calls = {"n": 0}

    def fake_run_tracer(*_a, **_k):
        calls["n"] += 1
        return {".bashrc"}

    monkeypatch.setattr("shellenv.discover._run_tracer", fake_run_tracer)

    modes = discover_startup_files_modes(
        "bash",
        shell_path="/bin/bash",
        force_refresh=True,
        modes=["login_noninteractive"],
    )
    assert calls["n"] == 1
    assert ".bashrc" in modes["login_noninteractive"]


def test_get_ttl_from_env(monkeypatch):
    monkeypatch.setenv("SHELLENV_DISCOVER_CACHE_TTL_SECS", "123")
    assert get_discovery_cache_ttl_secs() == 123.0
