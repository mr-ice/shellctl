"""Startup-file discovery for shells.

This module provides a safe discovery strategy:
- Try to use system tracers (`strace` on Linux, `dtruss` on macOS) to see
  which files are opened when the shell starts.
- If tracers are unavailable or fail, fall back to a curated list of
  candidate startup files for common shells (bash, zsh, tcsh).
- Cache simple results under the user's cache directory.

The tracer approach is best-effort; use with care. For now discovery
exposes a simple API suitable for unit testing and CLI display.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

CACHE_DIR = Path(os.environ.get("ENVCONFIG_CACHE_DIR") or Path.home() / ".cache" / "env-config")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(family: str, mode: str | None = None) -> Path:
    suffix = f"_{mode}" if mode else ""
    return CACHE_DIR / f"discovered_{family}{suffix}.json"


def clear_cache(family: str | None = None, mode: str | None = None) -> None:
    """Clear cached discovery results.

    If `family` is None, clear all discovery caches. If `mode` is
    provided, clear only that family's mode cache.
    """
    if family is None:
        # remove any discovered_*.json files
        for p in CACHE_DIR.glob("discovered_*.json"):
            try:
                p.unlink()
            except Exception:
                pass
        return

    p = _cache_path(family, mode)
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def _save_cache(family: str, files: Iterable[str], mode: str | None = None) -> None:
    p = _cache_path(family, mode)
    p.write_text(json.dumps(sorted(set(files))), encoding="utf8")


def _load_cache(family: str, mode: str | None = None) -> list[str]:
    p = _cache_path(family, mode)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf8"))
    except Exception:
        return []


def _run_tracer(family: str, shell_path: str, args: list[str]) -> set[str]:
    """Run a system tracer to capture opened files under $HOME.

    Returns a set of file basenames (relative to home) discovered.
    If tracer not available or errors, returns an empty set.
    """
    home = str(Path.home())
    files: set[str] = set()

    # Allow forcing the shell-level tracer via env var for CI/tests.
    use_shell_trace = os.environ.get("ENVCONFIG_USE_SHELL_TRACE")
    if use_shell_trace and use_shell_trace.lower() in ("1", "true", "yes"):
        use_system_tracer = False
    else:
        use_system_tracer = True

    # Prefer system tracers where available (strace). If not available or
    # explicitly disabled, fall back to the shell-level tracer implemented
    # in `trace.py`, which is safer for tests/CI and supports mock
    # fixtures via `ENVCONFIG_MOCK_TRACE_DIR`.
    if use_system_tracer and shutil.which("strace"):
        cmd = ["strace", "-e", "open,openat", shell_path] + args
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out = proc.stderr + "\n" + proc.stdout
        except Exception:
            out = ""

        # Parse lines looking for file paths quoted in syscalls, e.g.
        # openat(AT_FDCWD, "/home/user/.bashrc", O_RDONLY) = 3
        # open("/home/user/.bash_profile", O_RDONLY) = -1 ENOENT (No such file)
        # We search for patterns like ".../path..." and keep those under $HOME
        path_pat = re.compile(r'"(/[^"\s]+)"')
        for line in out.splitlines():
            for m in path_pat.finditer(line):
                pth = m.group(1)
                if home and pth.startswith(home):
                    # record basename relative to home
                    rel = os.path.relpath(pth, home)
                    files.add(rel)
        return files

    # Fall back to shell-level tracer
    try:
        # import here to avoid top-level dependency cycles
        from .trace import parse_trace, run_shell_trace

        # run_shell_trace accepts family and will honor ENVCONFIG_MOCK_TRACE_DIR
        trace_txt = run_shell_trace(family, shell_path, args=args, dry_run=False)
        if not trace_txt:
            return set()
        ftraces = parse_trace(trace_txt, family=family)
        home = str(Path.home())
        for ft in ftraces:
            # Only include files under $HOME (user's startup files)
            abs_path = os.path.normpath(os.path.abspath(os.path.expanduser(ft.path)))
            if home and not abs_path.startswith(home):
                continue
            name = os.path.basename(ft.path)
            if name:
                files.add(name)
        return files
    except Exception:
        return set()


def discover_startup_files_modes(
    family: str,
    shell_path: str | None = None,
    use_cache: bool = True,
    *,
    existing_only: bool = False,
    full_paths: bool = False,
    modes: list[str] | None = None,
) -> dict:
    """Discover startup files for each invocation mode (login/interactive combos).

    Parameters
    ----------
    modes : list[str] or None
        Modes to discover. If None, use all INVOCATION_MODES.

    Returns
    -------
    dict
        Mapping mode -> list of file basenames.
    """
    from .modes import INVOCATION_MODES, mode_to_args

    family = family.lower()
    mode_list = modes if modes is not None else list(INVOCATION_MODES)
    results: dict[str, list[str]] = {}

    # Resolve shell path for tracing; required to actually trace sourced files.
    # For tcsh, prefer patched tcsh with TCSH_XTRACEFD (see patches/README.md).
    if family == "tcsh" or family == "csh":
        from .trace import get_tcsh_for_tracing

        tracer_shell = get_tcsh_for_tracing(shell_path) or shutil.which("tcsh")
    else:
        tracer_shell = shell_path or shutil.which(family) or shutil.which(f"/bin/{family}")

    for mode in mode_list:
        if mode not in INVOCATION_MODES:
            continue
        traced: set[str] = set()
        args = mode_to_args(family, mode)
        if tracer_shell:
            traced = _run_tracer(family, tracer_shell, args)

        if not traced and use_cache:
            traced = set(_load_cache(family, mode))

        result: list[str] = []
        seen: set[str] = set()

        # Prioritize traced: when we have traced files, use them as authoritative
        for f in sorted(traced):
            name = os.path.basename(f)
            if name and name not in seen:
                result.append(name)
                seen.add(name)

        # Always include canonical entry points for the shell
        extra = [f".{family}rc", f".{family}env"]
        for e in extra:
            if e not in seen:
                result.append(e)
                seen.add(e)

        # optionally filter to existing files and/or return full paths
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

        try:
            _save_cache(family, result, mode)
        except Exception:
            pass

        results[mode] = processed

    return results


def discover_startup_files(
    family: str,
    shell_path: str | None = None,
    use_cache: bool = True,
    *,
    existing_only: bool = False,
    full_paths: bool = False,
    modes: list[str] | None = None,
) -> list[str]:
    """Backward-compatible wrapper: returns union of all mode lists (deduped)."""
    from .modes import INVOCATION_MODES

    mode_results = discover_startup_files_modes(
        family,
        shell_path=shell_path,
        use_cache=use_cache,
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
    return out
