# env-config

env-config is a lightweight toolkit to discover, trace, and analyze shell
startup files (bash, zsh, tcsh) so you can find slow or surprising startup
hooks. The project includes safe mock traces and a simple TUI for exploration.

## Quickstart

Install into your environment (editable for development):

```bash
python -m pip install -e .
```

Run the CLI (example):

```bash
env-config detect
env-config discover --family bash --modes
env-config trace --family bash --mode ln --dry-run
env-config trace --family bash --mode login_noninteractive --tui
```

Force the safer shell-level tracer (useful on macOS/CI):

```bash
env-config discover --use-shell-trace --modes
```

Clear discovery cache:

```bash
env-config discover --refresh-cache
```

## Logging

Use `--log-level` to control verbosity (applies to all commands):

```bash
env-config --log-level DEBUG compose list
```

Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL (default: WARNING).

## Environment variables

- `ENVCONFIG_MOCK_TRACE_DIR`: directory of fixture traces used by tests and
  to run the shell-level tracer in mock mode. Point this to
  `tests/fixtures/traces` to reproduce CI/test behavior.
- `ENVCONFIG_USE_SHELL_TRACE`: set to `1`, `true`, or `yes` to force the
  shell-level tracer instead of system tracers like `strace`.
- `ENVCONFIG_CACHE_DIR`: overrides the cache directory used by discovery.
- `ENVCONFIG_BACKUP_DIR`: overrides the backup archive directory
  (default `~/.cache/env-config/backups`).

## CLI highlights

- `detect` — detect current and intended shell and family. See
  [src/env_config/detect_shell.py](src/env_config/detect_shell.py)
- `discover` — discover candidate startup files (per-mode or union). Flags:
  `--family`, `--shell-path`, `--use-shell-trace`, `--refresh-cache`,
  `--modes`, `--mode` (li/ln/ni/nn or full names, repeatable). See [src/env_config/discover.py](src/env_config/discover.py).
- `trace` — run a shell-level trace and summarize per-file timing. Flags:
  `--family`, `--shell-path`, `--mode` (li/ln/ni/nn), `--dry-run`, `--output-file`,
  `--threshold-secs`, `--threshold-percent`, `--tui`. Core tracing/parsing is in
  [src/env_config/trace.py](src/env_config/trace.py).
- `backup` — back up discovered startup files to a tar.gz archive. Flags:
  `--family`, `--include`, `--exclude`, `--tui`.
- `archive` — back up startup files and remove originals. Flags:
  `--family`, `--include`, `--exclude`, `--yes`, `--tui`.
- `restore` — restore files from a backup archive. Flags:
  `--archive`, `--include`, `--exclude`, `--force`, `--yes`, `--tui`.
- `list-backups` — list available backup archives with timestamps and
  file contents.
- `compose` — pick and install optional shell init files from compose paths.
  Subcommands: `list`, `pick` (with `--tui` for interactive selection).

## Testing

Run the test suite with the correct PYTHONPATH (the Makefile target wraps
this for convenience):

```bash
make test
# or
PYTHONPATH=src pytest -q
```

The tests use mock trace fixtures under `tests/fixtures/traces`; to run the
discovery/trace code paths using these fixtures set `ENVCONFIG_MOCK_TRACE_DIR`.

## Development notes

- Parsers: `src/env_config/trace.py` contains parsers for bash, zsh, tcsh and
  a generic fallback. Improve path normalization and timestamp extraction
  there when adding new fixtures.
- Discovery: `src/env_config/discover.py` prefers system tracers where
  available but falls back to the safer shell-level tracer which honors the
  mock fixtures. The cache directory defaults to `~/.cache/env-config` but
  can be overridden with `ENVCONFIG_CACHE_DIR`.
- TUI: a simple curses UI lives in `src/env_config/tui.py`.

# env-config

env-config is a tool to manage shell
startup files (login/profile/rc files), back them up, and include compose startup files from directories given in the config.

Current implemented features (prototype)

- `detect`: determine current/login shell and intended shell using:
  - login shell from the passwd entry
  - `$SHELL` environment variable
  - parent process name
  - optional CLI override `--shell`

- `discover`: best-effort discovery of startup files used by shell
  families. Provides a fallback curated list and a tracer-backed
  discovery mode (if `strace` present). Use `--modes` to list files
  for four invocation modes: `login_interactive`, `login_noninteractive`,
  `nonlogin_interactive`, `nonlogin_noninteractive`.

- `trace`: run a non-privileged shell-level trace to capture which
  startup files are sourced and approximate time spent in each file.
  - Supports `bash`, `zsh`, and `tcsh` families.
  - Uses `BASH_XTRACEFD` + `PS4` for `bash` to capture timestamps.
  - Uses `-x` capture of stderr for `zsh`/`tcsh` and best-effort parsing.
  - Analyze results to compute per-file duration and percent of total.
  - Thresholds: `--threshold-secs` and `--threshold-percent` to flag slow files.
  - `--dry-run` prints the command without executing.
  - `--output-file` saves raw trace output for inspection.
  - `--tui` opens a minimal curses UI to inspect flagged files.

## Configuration

Global config: `/etc/env-config.toml` (optional)
User config: `~/.env-config.toml` (optional)

Config keys of interest (example):

```toml
[trace]
threshold_secs = 0.5
threshold_percent = 10.0

[tui]
page_size = 20
```

User level config overrides global ones.

### CLI config commands

View all config keys and their current (merged) values:

```bash
env-config config show
env-config config show compose.paths   # show just one key's value
```

Get a single key:

```bash
env-config config get tui.page_size
# 20

env-config config get trace.threshold_secs
# None
```

Set a value in the user config (`~/.env-config.toml`):

```bash
# integer
env-config config set tui.page_size 50

# float
env-config config set trace.threshold_secs 0.05

# string
env-config config set repo.url https://example.com/dotfiles.git

# clear a nullable key back to null
env-config config set trace.threshold_secs null

# list of strings (space-separated)
env-config config set compose.paths /opt/shell-extras /usr/local/etc/env

# append to an existing list instead of replacing it
env-config config set compose.paths /another/path --append
```

Reset a key (removes it from the user config, reverting to the
global or default value):

```bash
env-config config reset tui.page_size
```

Open the user config in `$EDITOR` with live validation (invalid
edits are reverted automatically):

```bash
env-config config --tui
```

## Backup, archive, and restore

Back up discovered startup files to a tar.gz archive:

```bash
env-config backup
env-config backup --family zsh
env-config backup --include ".zshrc" --include ".zprofile"
env-config backup --exclude ".bash*"
```

Archive (backup + delete originals) — prompts for confirmation unless
`--yes` is passed:

```bash
env-config archive --family bash
env-config archive --family bash --yes
```

List available backup archives:

```bash
env-config list-backups
```

Restore from the most recent archive (skips existing files by default):

```bash
env-config restore
env-config restore --force          # overwrite existing files
env-config restore --archive 20260215   # match archive by substring
env-config restore --include ".zshrc" --exclude ".zprofile"
env-config restore --yes --force    # no confirmation, overwrite
```

Use `--tui` for interactive file selection (shows all shell families,
active family highlighted and pre-checked):

```bash
env-config backup --tui
env-config archive --tui
env-config restore --tui
```

Archives are stored in `~/.cache/env-config/backups/` by default.
Override with the `ENVCONFIG_BACKUP_DIR` environment variable.

Safety and notes

- The tracer runs the user's shell and will execute startup files. By
  default the invocation uses `-c true` to exit after startup, but the
  startup files are still executed — run on a safe/test account if you
  are worried about side-effects.
- The syscall-level tracing (strace/eBPF/DTrace) is not used by default
  because it can require privileges. The shell-level approach is
  portable and non-privileged and typically identifies slow shell
  plugins and initialization commands which are the primary operator
  complaints.

Development / usage

Install test deps and run tests:

```bash
python -m pip install -U pytest
make test
```

Basic CLI examples

```bash
# detect
PYTHONPATH=src python -m env_config.cli detect

# discover (per-mode)
PYTHONPATH=src python -m env_config.cli discover --family bash --modes

# run a trace and print a summary
PYTHONPATH=src python -m env_config.cli trace --family bash --mode login_noninteractive --threshold-secs 0.05

# run trace and open curses TUI
PYTHONPATH=src python -m env_config.cli trace --family bash --mode login_noninteractive --threshold-secs 0.05 --tui

# dry-run to view command
PYTHONPATH=src python -m env_config.cli trace --family zsh --mode login_noninteractive --dry-run
```

Next features to implement

- Repo init/install for compose startup files.
- Additional shell-family improvements and safer tracer mocks for CI.
