# shellenv

shellenv is a tool for operators to control shell environment startup files (bash, zsh, tcsh): discover what runs, trace cost, back up and restore, optionally pull init files from a repo, and **compose** extra snippets from configured directories.

This document is the product spec. For day-to-day CLI usage and developer commands, see `README.md`.

## Configuration

| Layer | Path | Notes |
| --- | --- | --- |
| Site / global | `/etc/shellenv.toml` | Optional. |
| User | `~/.shellenv.toml` | Overrides global; list keys such as `compose.paths` append to global when merged. |

- **Site template**: `config/shellenv.global.defaults.toml` in the repo is a full commented template (regenerate with `shellenv config init-global --path …`).
- **Override global path (installs, CI, pytest)**: set **`SHELLENV_GLOBAL_CONFIG_PATH`** to another file instead of `/etc/shellenv.toml`.

Relevant schema keys include `trace.*`, `repo.*`, `compose.*`, and **`shellenv.tool_repo_path`** (clone location for this tool’s own repo, default `~/.shellenv`). See `src/shellenv/config.py` (`CONFIG_SCHEMA`).

## Compose (feature summary)

Composable init fragments use filenames `{rc_base}-{tag}` (e.g. `zshrc-fzf`); the first comment line is a one-line description. The operator selects fragments in interactive/TUI or CLI; **enabled** fragments appear in the home directory and are tracked in a registry under the cache dir.

### Target design (in progress)

- **`compose.paths`** entries are **git repository URLs** (not raw host paths). Each URL is **cloned** under the user’s home inside a layout managed by shellenv (exact subdirectory rules TBD), then scanned for matching fragment files.
- **Enablement** uses **symlinks** from the clone into `~` (e.g. `~/.zshrc-fzf` → file inside the clone), so updates can be refreshed from the remote without copying.
- The **shellenv tool repository** is also cloned/updated for the operator. Config key **`shellenv.tool_repo_path`** (default **`~/.shellenv`**) is the destination under home for that checkout.

### Current implementation

`compose.paths` now accepts **git URLs** and **filesystem git repos**. Both are treated as clone sources: shellenv clones/updates each source under `shellenv.tool_repo_path/compose-sources` and scans the **clone** for compose fragments (not the original source directory). Tests use fixtures under `repos/compose/teamA/env` and `repos/compose/teamB/env`.

Remaining product work: parent-rc **warnings** when `~/.zprofile` (etc.) does not source `~/.{rc}-*` fragments; **`update`** to refresh clones and symlink targets.

## Features

1. **Preferred shell** — If the operator’s preferred shell differs from `loginShell` (via `getpwent`), guide them to change it. Preference can come from: CLI shell/family name, `SHELL`, or running the tool from a non-login shell.

2. **Discover startup files** — Find startup files in the home directory that are sourced for bash, tcsh, and zsh in all combinations of login vs non-login and interactive vs non-interactive. Do not assume files exist; only report what the shell actually sources (including indirect sources).
   - Bash does not print filenames with `-x`; ship or document a patched bash for filename tracing.
   - Tcsh does not allow `-l` with other options and does not print filenames with `-x`; ship or document a patched tcsh.
   - Zsh already supports useful tracing; keep links/instructions to rebuild patched shells where needed.
   - When listing, show which modes source which files.

3. **Configuration** — Global and user TOML config (see above); CLI and TUI to edit user-level settings.

4. **Invocation modes** — Non-interactive (full task, no prompts), interactive (partial/no commands), TUI (same CLI parameters, curses UI).

5. **Default listing** — Show startup files for the current shell, then the intended shell, then other families. In TUI, expose actions for other commands.

6. **Backup and archive** — Select files to include; configurable backup location; archive removes originals after backup; prune old backups (configurable retention).

7. **Restore** — List backups; select in interactive/TUI; restore safely. If restore would overwrite differing files, prompt to archive the current files first; skip the prompt when there is nothing to conflict.

8. **TUI backup detail** — When a backup is selected in TUI, show files that would be restored/overwritten in the same file-browser style as the discovery view.

9. **Init repo** — URL in config clones/updates a project with initial startup files; error if the path is not that clone; warn if wrong branch or not up to date and offer to fix.

10. **`init` command** — Archive files that would be overwritten if not already archived, then copy family-appropriate files from the repo into the home directory.

11. **`compose`** — Pick optional init files discovered from **cloned** repos listed as URLs in `compose.paths` (file picker in interactive/TUI; CLI match in non-interactive). First line is a short description comment; longer comments follow. Show the short line next to the filename in lists.
    1. Each `compose.paths` entry is a **git URL**; shellenv **clones** it under the user’s home (layout TBD), scans for fragments, and **symlinks** chosen files into `~` as `~/.{name}` (leading dot). Optional org-specific URL allow/deny rules can be added later.
    2. Filenames `{shell}{part}-{tag}` with `{shell}{part}` matching a known startup basename; `-{tag}` is unique.
    3. Registry of user selections (persisted with compose state).
    4. **`shellenv.tool_repo_path`** — default `~/.shellenv` — where the shellenv tool repo itself is cloned/updated alongside compose sources.
    5. Warn if the parent rc (e.g. `~/.zprofile`) does not source the `-*` fragments (repos should include the stanza), e.g.:
    ```sh
    for _rc in $HOME/.zshenv-*; do
        source $_rc
    done
    ```

12. **`update` command** — Compare everything from `init` or `compose` to its source and refresh when out of date.

## Testing and quality

- Each feature should have tests before it is wired into operator scripts and the TUI.
- **Pytest / hermetic config**: point **`SHELLENV_GLOBAL_CONFIG_PATH`** at a temp site TOML; patch or redirect **`user_config_path`** in tests that must not read the developer’s real `~/.shellenv.toml`.
- **Compose**: today’s tests use **`compose.allow_non_repo`** or `allow_non_repo=True` for paths that are not git repos; **`SHELLENV_COMPOSE_ALLOW_DIRTY`** when a real repo on `main` is intentionally dirty; fixtures **`repos/compose/teamA`** / **`teamB`**. After **URL + clone** compose lands, add coverage for clone layout, symlinks, and **`shellenv.tool_repo_path`**.

## Issue tracker

**Standard stack (this repo and future projects): [Vikunja](https://vikunja.io)** — open-source task manager with kanban (buckets), lists, comments, CalDAV, and a REST API.

### Run Vikunja locally (Docker on this Mac)

Files live under **`infra/vikunja/`** (compose + `.env.example`). **`infra/vikunja/.env`** is gitignored.

1. `cd infra/vikunja`
2. `cp .env.example .env` and set **`VIKUNJA_SERVICE_JWTSECRET`** (e.g. `openssl rand -hex 32`) and a strong **`POSTGRES_PASSWORD`**.
3. **`VIKUNJA_SERVICE_PUBLICURL`** must match how you open the app (default `http://localhost:3456` if **`VIKUNJA_PORT`** is `3456`). If you change the host port, update both the URL and `VIKUNJA_PORT`.
4. Prepare the attachments volume (Vikunja runs as UID **1000** in the container):

   ```bash
   mkdir -p files
   sudo chown 1000 files
   ```

   On Docker Desktop for Mac, if uploads fail with permission errors, try `sudo chown -R 1000 files` or see [Vikunja: full Docker example](https://vikunja.io/docs/full-docker-example) (rootless / `user:` notes).

5. `docker compose up -d`
6. Open **`VIKUNJA_SERVICE_PUBLICURL`** in a browser, register the first user (no default account). API sanity check: `http://localhost:3456/api/v1/info` (adjust host/port if you changed them).

Stop: `docker compose down`. Data: `./db` (Postgres) and `./files` (attachments) under `infra/vikunja/`.

Official reference: [Docker walkthrough](https://vikunja.io/docs/docker-walkthrough/).

### Kanban columns

Map Vikunja **kanban buckets** to `.cursor/rules/issue-tracker-kanban.mdc`:

| Column  | Vikunja practice           |
| ------- | -------------------------- |
| To Do   | Bucket named **To Do**     |
| Ready   | Bucket named **Ready**     |
| Doing   | Bucket named **Doing**     |
| Done    | Bucket named **Done**      |

### API access (agents, scripts, integrations)

Vikunja’s [API documentation](https://vikunja.io/docs/api-documentation/) lives at **`/api/v1/docs`** on your instance (for example `http://localhost:3456/api/v1/docs`).

**Recommended auth: API tokens** (long-lived; they are **not** affected by Vikunja 2.x short-lived login JWTs — see [API login session migration](https://vikunja.io/docs/api-login-session-migration/)):

1. Log in to the web UI.
2. Open **Settings** → **API Tokens** (wording may be **User settings** / avatar menu → **Settings** depending on version).
3. Create a new token, copy it once (it is shown only at creation). Tokens often start with **`tk_`**.
4. Call the API with:

   ```http
   Authorization: Bearer <your-token>
   ```

For Cursor or other automation, keep the token in a **secret** the agent can read (for example an environment variable such as `VIKUNJA_API_TOKEN` in your shell profile, or Cursor’s secrets / env injection). **Do not** commit tokens or paste them into the repo. The server’s `infra/vikunja/.env` is for **deployment** secrets (DB, JWT signing), not per-user API tokens.

### Access and secrets

- **URL**: `VIKUNJA_SERVICE_PUBLICURL` in `infra/vikunja/.env`.
- **Credentials**: Vikunja accounts are self-registration (configure auth in Vikunja settings for stricter setups). Keep **`.env`** (DB password, JWT secret) out of git; store copies in your vault if needed.
