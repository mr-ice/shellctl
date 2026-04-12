# shellenv — Claude Project Rules

Rules specific to this project. These supplement the global rules in `~/.claude/CLAUDE.md`.

---

## Project Source of Truth

- **Read `PROJECT.md`** for instructions, descriptions, and specifications before working on features.
- **Ask questions** when requirements are inconsistent, unclear, or you cannot proceed confidently.
- **Add or update `PROJECT.md`** when the user gives new instructions that should become permanent project specs.

---

## Python & Ruff (applies to all `*.py` files)

- **Python**: 3.11 or later (matches `pyproject.toml`).
- **Formatting**: Run `ruff format` after any edit.
- **Linting**: Run `ruff check` before committing; fix all reported issues.
- Ruff config is in `pyproject.toml` — do not duplicate or override it.

---

## Config vs Secrets

- **Config files** (`config.yaml`, `settings.toml`, `pyproject.toml`, etc.) hold feature flags, endpoints, timeouts, paths, log levels. These may be committed.
- **`.env` files** hold API keys, tokens, passwords, signing secrets. **Never commit** them; provide `.env.example` with placeholder values.
  - Add `.env` entries to `.gitignore`.

---

## Issue Tracker: Vikunja

Vikunja (self-hosted, Docker) is the **selected** tracker. See `PROJECT.md → Issue tracker` for setup.

### Workflow with git commits (required)

Before or while preparing a commit for tracked work:

1. **Update the relevant Vikunja task(s)**: add a comment (what changed, decisions), adjust percent done, and/or move to the correct bucket (**To Do → Ready → Doing → Done**).
2. **Commit subject line**: first token must be `<project>-<index>` (e.g. `shellenv-14`).
   - `<project>` = project slug (`shellenv` for this repo).
   - `<index>` = the task's human-facing identifier/index in Vikunja (not the internal API `id`).
   - Example: `shellenv-14 Document compose symlink install`

### Referencing tasks

- Use `shellenv-N` (index) in discussion and commit subjects.
- Use the API `id` only for REST calls (`GET /api/v1/tasks/{id}`).
- Before referencing a task in a commit, verify it exists; create one if it doesn't.

### Vikunja CLI tool

`tools/vikunja_cli.py` is a lightweight CLI for task management:

```
VIKUNJA_URL=http://localhost:3456
CURSOR_VIKUNJA_API_TOKEN=tk_…   # or VIKUNJA_API_KEY
VIKUNJA_PROJECT=shellenv
```

These are loaded from `.cursor/rules/.env` (gitignored) automatically. Common commands:

```bash
python tools/vikunja_cli.py list                  # open tasks
python tools/vikunja_cli.py list --all            # including done
python tools/vikunja_cli.py get shellenv-14       # task detail
python tools/vikunja_cli.py move shellenv-14 doing
python tools/vikunja_cli.py comment shellenv-14 "progress note"
python tools/vikunja_cli.py update shellenv-14 --percent 80
```

### Kanban columns

| Column | Vikunja bucket |
|--------|---------------|
| To Do  | **To Do**     |
| Ready  | **Ready**     |
| Doing  | **Doing**     |
| Done   | **Done**      |

---

## FreeCAD Macros (applies to `*.FCMacro` files only)

When creating or editing `.FCMacro` files:

1. **Close and re-open** the active document at the start.
2. **Call methods** to create the objects described.
3. **Reload all Python files** on each run.
4. Target **FreeCAD 1.0.2 or later** — do not use features from earlier versions.
5. Store design measurements in config (`config.py`, `config.yaml`). "Off by" / adjustment measurements are computed inline, not stored.
