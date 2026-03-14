"""Tests for the CLI ``config`` subcommand (show/get/set/reset)."""
import tomllib

import pytest
from env_config.cli import main


@pytest.fixture()
def _isolate(tmp_path, monkeypatch):
    """Redirect config paths to tmp_path so tests are hermetic."""
    user_cfg = tmp_path / ".env-config.toml"
    global_cfg = tmp_path / "global.toml"
    monkeypatch.setattr("env_config.config.user_config_path", lambda: user_cfg)
    monkeypatch.setattr("env_config.config.GLOBAL_CONFIG_PATH", global_cfg)
    return user_cfg, global_cfg


# -- config show ------------------------------------------------------------


class TestConfigShow:
    """Tests for ``env-config config show``."""

    def test_show_prints_all_keys(self, _isolate, capsys):
        rc = main(["config", "show"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "trace.threshold_secs" in out
        assert "tui.page_size" in out
        assert "repo.url" in out
        assert "compose.paths" in out

    def test_show_single_key(self, _isolate, capsys):
        main(["config", "set", "compose.paths", "/a", "/b"])
        rc = main(["config", "show", "compose.paths"])
        assert rc == 0
        assert capsys.readouterr().out.strip() == "['/a', '/b']"

    def test_show_unknown_key(self, _isolate, capsys):
        rc = main(["config", "show", "no.such.key"])
        assert rc == 1
        assert "unknown config key" in capsys.readouterr().err


# -- config get -------------------------------------------------------------


class TestConfigGet:
    """Tests for ``env-config config get``."""

    def test_get_known_key(self, _isolate, capsys):
        rc = main(["config", "get", "tui.page_size"])
        assert rc == 0
        assert "20" in capsys.readouterr().out

    def test_get_unknown_key(self, _isolate, capsys):
        rc = main(["config", "get", "no.such.key"])
        assert rc == 1
        assert "unknown config key" in capsys.readouterr().err

    def test_get_reflects_set(self, _isolate, capsys):
        main(["config", "set", "tui.page_size", "50"])
        rc = main(["config", "get", "tui.page_size"])
        assert rc == 0
        assert "50" in capsys.readouterr().out


# -- config set -------------------------------------------------------------


class TestConfigSet:
    """Tests for ``env-config config set``."""

    def test_set_valid_int(self, _isolate, capsys):
        rc = main(["config", "set", "tui.page_size", "30"])
        assert rc == 0
        user_cfg, _ = _isolate
        with open(user_cfg, "rb") as f:
            data = tomllib.load(f)
        assert data["tui"]["page_size"] == 30

    def test_set_invalid_type(self, _isolate, capsys):
        rc = main(["config", "set", "tui.page_size", "abc"])
        assert rc == 1
        assert "error" in capsys.readouterr().err.lower()

    def test_set_unknown_key(self, _isolate, capsys):
        rc = main(["config", "set", "bogus.key", "1"])
        assert rc == 1
        assert "unknown config key" in capsys.readouterr().err

    def test_set_float_or_null(self, _isolate, capsys):
        rc = main(["config", "set", "trace.threshold_secs", "0.05"])
        assert rc == 0
        user_cfg, _ = _isolate
        with open(user_cfg, "rb") as f:
            data = tomllib.load(f)
        assert data["trace"]["threshold_secs"] == pytest.approx(0.05)

    def test_set_null(self, _isolate, capsys):
        main(["config", "set", "trace.threshold_secs", "0.05"])
        rc = main(["config", "set", "trace.threshold_secs", "null"])
        assert rc == 0
        user_cfg, _ = _isolate
        with open(user_cfg, "rb") as f:
            data = tomllib.load(f)
        # None values are omitted in TOML; key should be absent
        assert "threshold_secs" not in data.get("trace", {})

    def test_set_list(self, _isolate, capsys):
        rc = main(["config", "set", "compose.paths", "/a", "/b"])
        assert rc == 0
        user_cfg, _ = _isolate
        with open(user_cfg, "rb") as f:
            data = tomllib.load(f)
        assert data["compose"]["paths"] == ["/a", "/b"]

    def test_set_list_append(self, _isolate, capsys):
        main(["config", "set", "compose.paths", "/a"])
        rc = main(["config", "set", "compose.paths", "/b", "/c", "--append"])
        assert rc == 0
        user_cfg, _ = _isolate
        with open(user_cfg, "rb") as f:
            data = tomllib.load(f)
        assert data["compose"]["paths"] == ["/a", "/b", "/c"]

    def test_set_string_or_null(self, _isolate, capsys):
        rc = main(["config", "set", "repo.url", "https://example.com/repo.git"])
        assert rc == 0
        user_cfg, _ = _isolate
        with open(user_cfg, "rb") as f:
            data = tomllib.load(f)
        assert data["repo"]["url"] == "https://example.com/repo.git"


# -- config reset -----------------------------------------------------------


class TestConfigReset:
    """Tests for ``env-config config reset``."""

    def test_reset_reverts_to_default(self, _isolate, capsys):
        main(["config", "set", "tui.page_size", "99"])
        rc = main(["config", "reset", "tui.page_size"])
        assert rc == 0
        # get should now show default
        main(["config", "get", "tui.page_size"])
        assert "20" in capsys.readouterr().out

    def test_reset_unknown_key(self, _isolate, capsys):
        rc = main(["config", "reset", "bogus.key"])
        assert rc == 1
        assert "unknown config key" in capsys.readouterr().err


# -- config (no subcommand) -------------------------------------------------


class TestConfigNoSubcmd:
    """Tests for ``env-config config`` with no sub-subcommand."""

    def test_prints_usage(self, _isolate, capsys):
        rc = main(["config"])
        assert rc == 1
        assert "usage" in capsys.readouterr().err.lower()
