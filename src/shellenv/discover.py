"""Startup-file discovery for shells.

Uses shell-level tracing (see ``trace``) to record which files under ``$HOME``
are actually sourced for each invocation mode. Results are cached with a
timestamp; stale entries are recomputed automatically based on
``discover.cache_ttl_secs`` (or ``SHELLENV_DISCOVER_CACHE_TTL_SECS``).

The ``discover`` and ``trace`` CLI commands always refresh traced data and
update the cache. Other callers (for example ``backup``) reuse the cache when
it is still fresh, unless ``force_refresh=True`` or CLI ``--refresh-cache``.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

CACHE_DIR = Path(os.environ.get("SHELLENV_CACHE_DIR") or Path.home() / ".cache" / "shellenv")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(family: str, mode: str | None = None) -> Path:
    suffix = f"_{mode}" if mode else ""
    return CACHE_DIR / f"discovered_{family}{suffix}.json"


def clear_cache(family: str | None = None, mode: str | None = None) -> None:
    """Clear cached discovery results.

    If *family* is ``None``, clear all discovery caches. If *mode* is set,
    clear only that family's mode cache.
    """
    if family is None:
        for p in CACHE_DIR.glob("discovered_*.json"):
            try:
                p.unlink()
            except OSError:
                pass
        return

    p = _cache_path(family, mode)
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass


def get_discovery_cache_ttl_secs() -> float:
    """Maximum cache age in seconds before discovery is recomputed.

    Override with environment variable ``SHELLENV_DISCOVER_CACHE_TTL_SECS``.
    Default from config ``discover.cache_ttl_secs`` is one week (604800).
    """
    raw = os.environ.get("SHELLENV_DISCOVER_CACHE_TTL_SECS")
    if raw is not None and raw.strip() != "":
        try:
            return float(raw)
        except ValueError:
            pass
    try:
        from .config import config_get

        v = config_get("discover.cache_ttl_secs")
        if v is None:
            return 604800.0
        return float(v)
    except Exception:
        return 604800.0


def _save_cache_payload(family: str, mode: str | None, files: Iterable[str]) -> None:
    p = _cache_path(family, mode)
    payload = {"updated": time.time(), "files": sorted(set(files))}
    p.write_text(json.dumps(payload), encoding="utf8")


def _load_cache_payload(family: str, mode: str | None) -> tuple[list[str], float | None]:
    """Return (files, updated_unix_time_or_None). Legacy list-only JSON is treated as stale."""
    p = _cache_path(family, mode)
    if not p.exists():
        return [], None
    try:
        data = json.loads(p.read_text(encoding="utf8"))
    except Exception:
        return [], None
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict) and "files" in data:
        fl = data["files"]
        if not isinstance(fl, list):
            return [], None
        ts = data.get("updated")
        try:
            updated = float(ts) if ts is not None else None
        except (TypeError, ValueError):
            updated = None
        return [str(x) for x in fl], updated
    return [], None


def _cache_entry_fresh(updated_ts: float | None, ttl_secs: float) -> bool:
    if updated_ts is None or ttl_secs <= 0:
        return False
    return (time.time() - updated_ts) < ttl_secs


# Valid startup file prefixes per family (basename must match or start with one of these).
# Used to filter out wrong-shell files when tracer misreports (e.g. running zsh instead of tcsh).
_FAMILY_FILE_PREFIXES: dict[str, tuple[str, ...]] = {
    "bash": (
        ".bashrc",
        ".bash_profile",
        ".bash_login",
        ".profile",
        ".bash_logout",
        ".bash_env",
        ".bash_history",
        ".inputrc",
    ),
    "zsh": (".zshenv", ".zshrc", ".zprofile", ".zlogin", ".zlogout", ".zsh_history"),
    "tcsh": (".tcshrc", ".cshrc", ".login", ".tcshenv", ".logout", ".history"),
}

# Glob patterns under $HOME for files startup tracing never sees (logout-only scripts,
# history, readline) or that are optional ecosystem files. Matched paths must still pass
# :func:`_is_valid_for_family`.
_FAMILY_SUPPLEMENTAL_GLOBS: dict[str, tuple[str, ...]] = {
    "bash": (
        ".bash_logout",
        ".bash_logout-*",
        ".bash_history",
        ".inputrc",
    ),
    "zsh": (
        ".zlogout",
        ".zlogout-*",
        ".zsh_history",
    ),
    "tcsh": (
        ".logout",
        ".logout-*",
        ".history",
    ),
}


def _is_valid_for_family(path_or_name: str, family: str) -> bool:
    """Return True if basename is a valid startup file for the given family."""
    family = family.lower()
    if family == "zsh":
        rel = path_or_name.lstrip("/")
        if rel.startswith(".zshlib/"):
            return True
    prefixes = _FAMILY_FILE_PREFIXES.get(family, ())
    base = os.path.basename(path_or_name.lstrip("/"))
    return any(base == p or base.startswith(p + "-") for p in prefixes)


def _supplemental_home_relative_paths(family: str, home: Path) -> list[str]:
    """Return existing home-relative paths not covered by startup tracing."""
    fam = family.lower()
    patterns = _FAMILY_SUPPLEMENTAL_GLOBS.get(fam, ())
    if not patterns:
        return []
    found: set[str] = set()
    try:
        home_resolved = home.resolve()
    except OSError:
        home_resolved = home
    for pattern in patterns:
        for p in home.glob(pattern):
            try:
                if not p.exists():
                    continue
            except OSError:
                continue
            if p.is_dir():
                continue
            try:
                rel = p.relative_to(home_resolved)
            except ValueError:
                try:
                    rel = p.relative_to(home)
                except ValueError:
                    continue
            rel_s = rel.as_posix()
            if rel_s in found:
                continue
            if not _is_valid_for_family(rel_s, fam):
                continue
            found.add(rel_s)
    return sorted(found)


def traces_to_home_rel_paths(family: str, traces: Sequence[Any]) -> list[str]:
    """Map tracer output to unique home-relative paths valid for *family*."""
    home = str(Path.home())
    out: list[str] = []
    seen: set[str] = set()
    for ft in traces:
        path = getattr(ft, "path", None)
        if path is None:
            continue
        abs_path = os.path.normpath(os.path.abspath(os.path.expanduser(str(path))))
        if home and not abs_path.startswith(home):
            continue
        rel = os.path.relpath(abs_path, home)
        if not rel or rel in seen:
            continue
        if not _is_valid_for_family(rel, family):
            continue
        seen.add(rel)
        out.append(rel)
    return out


def write_discovery_cache_for_mode(family: str, mode: str, traces: Sequence[Any]) -> None:
    """Persist discovery for one mode from ``collect_startup_file_traces`` output."""
    rels = traces_to_home_rel_paths(family, traces)
    _save_cache_payload(family, mode, rels)


def _run_tracer(family: str, shell_path: str, args: list[str]) -> set[str]:
    """Run shell trace collection and return startup files under ``$HOME``."""
    try:
        from .trace import collect_startup_file_traces

        traces = collect_startup_file_traces(
            family,
            shell_path=shell_path,
            args=args,
            dry_run=False,
        )
        if isinstance(traces, str):
            return set()
        return set(traces_to_home_rel_paths(family, traces))
    except Exception:
        return set()


def discover_startup_files_modes(
    family: str,
    shell_path: str | None = None,
    *,
    force_refresh: bool = False,
    cache_ttl_secs: float | None = None,
    existing_only: bool = False,
    full_paths: bool = False,
    modes: list[str] | None = None,
) -> dict:
    """Discover startup files for each invocation mode (login/interactive combos).

    Parameters
    ----------
    force_refresh
        If True, ignore the on-disk cache and always run the tracer, then save.
    cache_ttl_secs
        Override TTL for this call; default from config / env.
    """
    from .modes import INVOCATION_MODES, mode_to_args

    family = family.lower()
    mode_list = modes if modes is not None else list(INVOCATION_MODES)
    results: dict[str, list[str]] = {}
    ttl = get_discovery_cache_ttl_secs() if cache_ttl_secs is None else float(cache_ttl_secs)

    if family == "bash":
        from .trace import get_bash_for_tracing

        if shell_path and os.path.basename(shell_path).lower() == "bash":
            tracer_shell = get_bash_for_tracing(shell_path)
        else:
            tracer_shell = get_bash_for_tracing(None)
        tracer_shell = tracer_shell or shutil.which("bash")
    elif family in ("tcsh", "csh"):
        from .trace import get_tcsh_for_tracing

        if shell_path and os.path.basename(shell_path).lower() in ("tcsh", "csh"):
            tracer_shell = get_tcsh_for_tracing(shell_path)
        else:
            tracer_shell = get_tcsh_for_tracing(None)
        tracer_shell = tracer_shell or shutil.which("tcsh")
    else:
        tracer_shell = shell_path or shutil.which(family) or shutil.which(f"/bin/{family}")

    for mode in mode_list:
        if mode not in INVOCATION_MODES:
            continue
        used_cache = False
        traced: set[str] = set()

        if not force_refresh:
            cached_files, updated_ts = _load_cache_payload(family, mode)
            if _cache_entry_fresh(updated_ts, ttl):
                traced = set(cached_files)
                used_cache = True

        if not used_cache:
            args = mode_to_args(family, mode)
            if tracer_shell:
                traced = _run_tracer(family, tracer_shell, args)
            else:
                traced = set()
            filtered = sorted(traced)
            try:
                _save_cache_payload(family, mode, filtered)
            except OSError:
                pass

        result = sorted(traced)

        processed: list[str] = []
        for name in result:
            if full_paths:
                cand = os.path.join(str(Path.home()), name)
            else:
                cand = name
            if existing_only:
                check_path = cand if os.path.isabs(cand) else os.path.join(str(Path.home()), name)
                if not os.path.exists(check_path):
                    continue
            processed.append(cand)

        results[mode] = processed

    return results


def discover_startup_files(
    family: str,
    shell_path: str | None = None,
    *,
    force_refresh: bool = False,
    cache_ttl_secs: float | None = None,
    existing_only: bool = False,
    full_paths: bool = False,
    modes: list[str] | None = None,
) -> list[str]:
    """Return union of all mode lists (deduped)."""
    from .modes import INVOCATION_MODES

    mode_results = discover_startup_files_modes(
        family,
        shell_path=shell_path,
        force_refresh=force_refresh,
        cache_ttl_secs=cache_ttl_secs,
        existing_only=existing_only,
        full_paths=full_paths,
        modes=modes,
    )
    seen: set[str] = set()
    out: list[str] = []
    for mode in INVOCATION_MODES:
        for f in mode_results.get(mode, []):
            if f not in seen:
                out.append(f)
                seen.add(f)

    home = Path.home()
    for rel in _supplemental_home_relative_paths(family, home):
        check_path = str(home / rel)
        if not os.path.exists(check_path):
            continue
        cand = check_path if full_paths else rel
        if cand in seen:
            continue
        out.append(cand)
        seen.add(cand)
    return out
