from pathlib import Path

from env_config.config import _load_cfg_safe, default_config_dict

# def test_validate_load_config():
#     p = Path("config/env-config.global.defaults.toml")
#     p.write_text("-")
#     assert load_config(p) == {}


def test_load_config_safe():
    """This calls load_config so should cover that as well."""
    p = Path("config/env-config.global.defaults.toml")
    p.write_text("-")
    assert _load_cfg_safe(p) == {}


def test_default_config_dict():
    assert default_config_dict() == {
        "trace": {"threshold_secs": None, "threshold_percent": None},
        "repo": {"url": None, "destination": None},
        "compose": {"paths": [], "shell_rc_files": [], "allow_non_repo": "false"},
    }
