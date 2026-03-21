"""Tests for compose file selection and installation."""
from __future__ import annotations

from env_config.compose import (
    ComposeFile,
    _extract_summary,
    _registry_path,
    _shell_rc_files_for_family,
    get_registry,
    install_compose_files,
    list_compose_files,
)


class TestExtractSummary:
    """Tests for summary extraction from shell init files."""

    def test_comment_hash(self, tmp_path):
        f = tmp_path / "zshrc-foo"
        f.write_text("# Load fzf key bindings\nbindkey ...")
        assert _extract_summary(f) == "Load fzf key bindings"

    def test_comment_double_hash(self, tmp_path):
        f = tmp_path / "zshrc-bar"
        f.write_text("## NVM initialization\nsource ...")
        assert _extract_summary(f) == "NVM initialization"

    def test_first_non_comment_line(self, tmp_path):
        f = tmp_path / "zshrc-baz"
        f.write_text("\n\nsource /opt/thing/init.sh\n")
        assert _extract_summary(f) == "source /opt/thing/init.sh"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty"
        f.write_text("")
        assert _extract_summary(f) == ""

    def test_no_description_fallback(self, tmp_path):
        f = tmp_path / "zshrc-qux"
        f.write_text("  \n  \n")
        assert _extract_summary(f) == ""


class TestShellRcFilesForFamily:
    """Tests for shell RC file resolution."""

    def test_uses_config_when_non_empty(self):
        assert _shell_rc_files_for_family("zsh", ["zshrc", "zshenv"]) == [
            "zshrc",
            "zshenv",
        ]

    def test_uses_default_for_zsh(self):
        assert _shell_rc_files_for_family("zsh", []) == [
            "zshrc",
            "zshenv",
            "zprofile",
            "zlogin",
            "zlogout",
        ]

    def test_uses_default_for_bash(self):
        assert _shell_rc_files_for_family("bash", []) == [
            "bashrc",
            "bash_profile",
            "bash_login",
            "profile",
            "bash_logout",
        ]

    def test_uses_default_for_tcsh(self):
        assert _shell_rc_files_for_family("tcsh", []) == [
            "tcshrc",
            "cshrc",
            "login",
        ]


class TestListComposeFiles:
    """Tests for listing compose files."""

    def test_empty_paths(self):
        files = list_compose_files("zsh", paths=[], allow_non_repo=True)
        assert files == []

    def test_nonexistent_path_skipped(self):
        files = list_compose_files(
            "zsh",
            paths=["/nonexistent/path/12345"],
            allow_non_repo=True,
        )
        assert files == []

    def test_finds_matching_files(self, tmp_path):
        (tmp_path / "zshrc-fzf").write_text("# FZF key bindings\nbindkey")
        (tmp_path / "zshrc-nvm").write_text("## NVM\nsource")
        (tmp_path / "zshenv-path").write_text("# PATH additions")
        (tmp_path / "other.txt").write_text("ignore")
        (tmp_path / "zshrc-invalid-suffix").write_text("x")

        files = list_compose_files(
            "zsh",
            paths=[str(tmp_path)],
            shell_rc_files=["zshrc", "zshenv"],
            allow_non_repo=True,
        )

        by_name = {cf.name: cf for cf in files}
        assert "fzf" in by_name
        assert "nvm" in by_name
        assert "path" in by_name
        assert by_name["fzf"].dest_basename == ".zshrc-fzf"
        assert by_name["fzf"].summary == "FZF key bindings"
        assert by_name["nvm"].summary == "NVM"

    def test_deduplicates_same_name_from_different_paths(self, tmp_path):
        d1 = tmp_path / "dir1"
        d1.mkdir()
        (d1 / "zshrc-foo").write_text("# First")
        d2 = tmp_path / "dir2"
        d2.mkdir()
        (d2 / "zshrc-foo").write_text("# Second")

        files = list_compose_files(
            "zsh",
            paths=[str(d1), str(d2)],
            shell_rc_files=["zshrc"],
            allow_non_repo=True,
        )
        # First occurrence wins
        assert len([f for f in files if f.name == "foo"]) == 1


class TestInstallComposeFiles:
    """Tests for installing compose files to home."""

    def test_installs_to_home(self, tmp_path):
        src = tmp_path / "compose"
        src.mkdir()
        (src / "zshrc-fzf").write_text("# FZF\nbindkey")
        cf = ComposeFile(
            source_path=str(src / "zshrc-fzf"),
            rc_base="zshrc",
            name="fzf",
            dest_basename=".zshrc-fzf",
            summary="FZF",
        )

        home = tmp_path / "home"
        home.mkdir()
        installed = install_compose_files([cf], home_dir=home)

        assert len(installed) == 1
        dest = home / ".zshrc-fzf"
        assert dest.exists()
        assert dest.read_text() == "# FZF\nbindkey"
        assert str(dest) in installed

    def test_updates_registry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENVCONFIG_CACHE_DIR", str(tmp_path / "cache"))
        src = tmp_path / "compose"
        src.mkdir()
        (src / "zshrc-fzf").write_text("# FZF")
        cf = ComposeFile(
            source_path=str(src / "zshrc-fzf"),
            rc_base="zshrc",
            name="fzf",
            dest_basename=".zshrc-fzf",
            summary="FZF",
        )

        home = tmp_path / "home"
        home.mkdir()
        install_compose_files([cf], home_dir=home)

        reg = get_registry()
        assert len(reg) == 1
        assert reg[0]["source_path"] == str(src / "zshrc-fzf")
        assert reg[0]["dest_basename"] == ".zshrc-fzf"


class TestRegistry:
    """Tests for the compose registry."""

    def test_empty_registry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENVCONFIG_CACHE_DIR", str(tmp_path))
        assert get_registry() == []

    def test_registry_path_respects_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ENVCONFIG_CACHE_DIR", str(tmp_path))
        p = _registry_path()
        assert str(tmp_path) in str(p)
        assert p.name == "compose_registry.json"
