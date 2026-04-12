#!/usr/bin/env python3
"""vikunja_cli.py — Lightweight CLI for the Vikunja task manager.

Loads connection settings from .env files (checked in order:
``.cursor/rules/.env``, then project-root ``.env``, then the
environment).  Supported variables:

- ``VIKUNJA_URL`` — base URL of the running instance (e.g. ``http://localhost:3456``)
- ``VIKUNJA_API_KEY`` or ``CURSOR_VIKUNJA_API_TOKEN`` — API token (``tk_…``)
- ``VIKUNJA_PROJECT`` — project title to default to (e.g. ``shellenv``)

Usage examples
--------------
  python tools/vikunja_cli.py list
  python tools/vikunja_cli.py list --bucket doing
  python tools/vikunja_cli.py list --all
  python tools/vikunja_cli.py get 15
  python tools/vikunja_cli.py get shellenv-15
  python tools/vikunja_cli.py create "New feature" --bucket ready --priority high
  python tools/vikunja_cli.py move 15 done
  python tools/vikunja_cli.py update 15 --percent 50 --priority medium
  python tools/vikunja_cli.py done 15
  python tools/vikunja_cli.py undone 15
  python tools/vikunja_cli.py delete 15
  python tools/vikunja_cli.py comment 15 "Implemented the core logic, ~70% done"
  python tools/vikunja_cli.py buckets
  python tools/vikunja_cli.py projects
  python tools/vikunja_cli.py views
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

import dotenv
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config() -> dict[str, str]:
    """Load Vikunja connection settings from .env files and the environment.

    Searches (in order):
    1. ``.cursor/rules/.env`` relative to the script's project root
    2. Project-root ``.env``
    3. System environment

    Returns
    -------
    dict[str, str]
        Mapping with keys ``url``, ``key``, and ``project``.
    """
    # Walk up from this file to find the project root (.git marker)
    here = Path(__file__).resolve().parent
    project_root = here
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            project_root = parent
            break

    cursor_env = project_root / ".cursor" / "rules" / ".env"
    root_env = project_root / ".env"

    for env_file in [cursor_env, root_env]:
        if env_file.exists():
            dotenv.load_dotenv(env_file, override=False)

    url = os.getenv("VIKUNJA_URL", "").rstrip("/")
    # Accept both naming conventions
    key = os.getenv("VIKUNJA_API_KEY") or os.getenv("CURSOR_VIKUNJA_API_TOKEN", "")
    project = os.getenv("VIKUNJA_PROJECT", "")

    missing = [k for k, v in [("VIKUNJA_URL", url), ("VIKUNJA_API_KEY / CURSOR_VIKUNJA_API_TOKEN", key)] if not v]
    if missing:
        sys.exit(f"Missing required env vars: {', '.join(missing)}")

    return {"url": url, "key": key, "project": project}


# ---------------------------------------------------------------------------
# Vikunja API client
# ---------------------------------------------------------------------------


class VikunjaClient:
    """Thin wrapper around the Vikunja REST API.

    Parameters
    ----------
    url : str
        Base URL of the Vikunja instance (e.g. ``http://localhost:3456``).
    key : str
        API token for ``Authorization: Bearer`` authentication.
    project : str, optional
        Project title to default to.  Falls back to the first non-Inbox project.
    """

    # Priority name → Vikunja integer
    PRIORITY: dict[str, int] = {"none": 0, "low": 1, "medium": 2, "high": 3, "urgent": 4, "now": 5}
    PRIORITY_LABEL: dict[int, str] = {v: k for k, v in PRIORITY.items()}

    def __init__(self, url: str, key: str, project: str = "") -> None:
        self.base = f"{url}/api/v1"
        self.headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        self._project_name = project
        self._project_id: int | None = None
        self._project_slug: str = project.lower()
        self._buckets: dict[str, int] = {}       # name→id
        self._bucket_names: dict[int, str] = {}   # id→name
        self._kanban_view_id: int | None = None
        self._index_to_api_id: dict[int, int] = {}  # task index→api id cache

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> Any:
        r = requests.get(f"{self.base}{path}", headers=self.headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> Any:
        r = requests.post(f"{self.base}{path}", headers=self.headers, json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    def _put(self, path: str, body: dict) -> Any:
        # Vikunja task *updates* use POST (PUT returns 405 on /tasks/{id}).
        r = requests.post(f"{self.base}{path}", headers=self.headers, json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    def _put_real(self, path: str, body: dict) -> Any:
        """Actual HTTP PUT — used for endpoints that require it (e.g. comments)."""
        r = requests.put(f"{self.base}{path}", headers=self.headers, json=body, timeout=15)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> Any:
        r = requests.delete(f"{self.base}{path}", headers=self.headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def _resolve_project(self) -> int:
        if self._project_id is not None:
            return self._project_id
        projects = self._get("/projects")
        if self._project_name:
            for p in projects:
                if p["title"].lower() == self._project_name.lower():
                    self._project_id = p["id"]
                    self._project_slug = p["title"].lower()
                    return self._project_id
        # Fall back to first non-inbox project
        for p in projects:
            if p["title"].lower() != "inbox":
                self._project_id = p["id"]
                self._project_slug = p["title"].lower()
                return self._project_id
        sys.exit("No project found")

    def _resolve_buckets(self) -> None:
        if self._buckets:
            return
        pid = self._resolve_project()
        views = self._get(f"/projects/{pid}/views")
        kanban = next((v for v in views if v["view_kind"] == "kanban"), None)
        if not kanban:
            return
        self._kanban_view_id = kanban["id"]
        raw = self._get(
            f"/projects/{pid}/views/{kanban['id']}/buckets",
            params={"per_page": 50},
        )
        for b in raw:
            name_lower = b["title"].lower()
            self._buckets[name_lower] = b["id"]
            self._bucket_names[b["id"]] = b["title"]

    def _bucket_id(self, name: str) -> int:
        """Resolve bucket name or numeric id to integer id."""
        self._resolve_buckets()
        try:
            bid = int(name)
            if bid in self._bucket_names:
                return bid
            sys.exit(f"Bucket id {bid} not found. Available: {self._fmt_buckets()}")
        except ValueError:
            key = name.lower()
            if key in self._buckets:
                return self._buckets[key]
            sys.exit(f"Unknown bucket '{name}'. Available: {self._fmt_buckets()}")

    def _bucket_name(self, bid: int) -> str:
        self._resolve_buckets()
        return self._bucket_names.get(bid, str(bid) if bid else "none")

    def _load_view_tasks(self, include_done: bool = True) -> list[dict]:
        """Fetch tasks from the Kanban view, augmented with bucket_name."""
        self._resolve_buckets()
        pid = self._resolve_project()
        if not self._kanban_view_id:
            return []
        raw = self._get(
            f"/projects/{pid}/views/{self._kanban_view_id}/tasks",
            params={"per_page": 500},
        )
        result = []
        for bucket_block in raw:
            bid = bucket_block["id"]
            bname = bucket_block.get("title", str(bid))
            for t in bucket_block.get("tasks") or []:
                t["_bucket_id"] = bid
                t["_bucket_name"] = bname
                # Cache index→api_id
                if "index" in t:
                    self._index_to_api_id[t["index"]] = t["id"]
                if include_done or not t.get("done"):
                    result.append(t)
        return result

    def _resolve_task_id(self, identifier: str) -> int:
        """Resolve a task identifier to the Vikunja API id.

        Accepts:
        - Raw API id integer string: ``"42"``
        - Project-prefixed index: ``"shellenv-14"``
        - Bare index number (treated as task index): ``"14"``

        Parameters
        ----------
        identifier : str
            The task reference string.

        Returns
        -------
        int
            Vikunja API task id.
        """
        # Pattern: <slug>-<index>  e.g. shellenv-14
        m = re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*-(\d+)", identifier)
        if m:
            index = int(m.group(1))
            return self._index_to_api_id_lookup(index)

        try:
            return int(identifier)
        except ValueError:
            sys.exit(f"Cannot parse task identifier: '{identifier}'")

    def _index_to_api_id_lookup(self, index: int) -> int:
        """Look up API id for a task index (the human-facing number)."""
        # Try cache first (populated by _load_view_tasks)
        if index in self._index_to_api_id:
            return self._index_to_api_id[index]
        # Load all tasks to populate the cache
        self._load_view_tasks(include_done=True)
        if index in self._index_to_api_id:
            return self._index_to_api_id[index]
        # Also search via project tasks API (includes done tasks not in kanban)
        pid = self._resolve_project()
        tasks = self._get(f"/projects/{pid}/tasks", params={"per_page": 500})
        for t in tasks:
            if t.get("index") == index:
                self._index_to_api_id[index] = t["id"]
                return t["id"]
        sys.exit(f"No task with index {index} found in project")

    def _fmt_buckets(self) -> str:
        self._resolve_buckets()
        return ", ".join(f"{n}({i})" for n, i in self._buckets.items())

    @staticmethod
    def _priority_int(name: str) -> int:
        try:
            v = int(name)
            if 0 <= v <= 5:
                return v
            sys.exit(f"Priority integer must be 0-5, got {v}")
        except ValueError:
            key = name.lower()
            if key not in VikunjaClient.PRIORITY:
                opts = "/".join(VikunjaClient.PRIORITY)
                sys.exit(f"Unknown priority '{name}'. Options: {opts}")
            return VikunjaClient.PRIORITY[key]

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    def _fmt_task(self, t: dict, verbose: bool = False) -> str:
        pid = t.get("priority", 0)
        pname = self.PRIORITY_LABEL.get(pid, str(pid))
        bucket_name = self._bucket_name(t.get("bucket_id", 0))
        pct = t.get("percent_done", 0)
        pct_str = f" {int(pct * 100)}%" if pct and pct > 0 else ""

        # _bucket_name is injected by _load_view_tasks; fall back to lookup
        effective_bucket = t.get("_bucket_name") or bucket_name
        status = "DONE" if t.get("done") else effective_bucket

        index = t.get("index", "")
        slug = self._project_slug or "task"
        ref = f"{slug}-{index}" if index else f"#{t['id']}"

        header = f"{ref:<14}  [{status:<10}]  pri={pname:<6}  {t['title']}{pct_str}"
        if not verbose:
            return header
        lines = [header]
        if t.get("description"):
            lines.append(f"  {t['description']}")
        lines.append(
            f"  api_id={t['id']}  project_id={t.get('project_id', '?')}"
            f"  bucket_id={t.get('bucket_id', 0)}"
            f"  created={t['created'][:10]}  updated={t['updated'][:10]}"
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def list_projects(self) -> None:
        """Print all accessible projects."""
        projects = self._get("/projects")
        for p in projects:
            print(f"  id={p['id']}  {p['title']}")

    def list_views(self) -> None:
        """Print all views for the configured project."""
        pid = self._resolve_project()
        views = self._get(f"/projects/{pid}/views")
        for v in views:
            print(f"  id={v['id']}  {v['title']:<12}  kind={v['view_kind']}")

    def list_buckets(self) -> None:
        """Print Kanban bucket names and ids."""
        self._resolve_buckets()
        if not self._buckets:
            print("  No Kanban view found in this project.")
            return
        for name, bid in self._buckets.items():
            print(f"  id={bid}  {name}")

    def list_tasks(
        self,
        bucket: str | None = None,
        include_done: bool = False,
        verbose: bool = False,
    ) -> None:
        """List tasks, optionally filtered by bucket.

        Parameters
        ----------
        bucket : str or None
            Bucket name or id to filter by.
        include_done : bool
            Include completed tasks when True.
        verbose : bool
            Show descriptions and metadata.
        """
        tasks = self._load_view_tasks(include_done=include_done)
        if not tasks:
            print("No tasks found.")
            return

        if bucket:
            bid = self._bucket_id(bucket)
            tasks = [t for t in tasks if t.get("_bucket_id") == bid]

        if not tasks:
            print("  (no tasks)")
            return
        for t in sorted(tasks, key=lambda x: x.get("index", x["id"])):
            print(self._fmt_task(t, verbose=verbose))

    def get_task(self, identifier: str) -> None:
        """Print details for a single task.

        Parameters
        ----------
        identifier : str
            Task API id, bare index, or ``<project>-<index>`` string.
        """
        # Load view tasks first so index cache is warm
        self._load_view_tasks(include_done=True)
        task_id = self._resolve_task_id(identifier)
        t = self._get(f"/tasks/{task_id}")
        self._resolve_buckets()
        print(self._fmt_task(t, verbose=True))

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        bucket: str | None = None,
        percent_done: float = 0.0,
    ) -> None:
        """Create a new task.

        Parameters
        ----------
        title : str
            Task title.
        description : str, optional
            Task body text.
        priority : str, optional
            Priority name or integer 0-5.
        bucket : str or None, optional
            Bucket name or id to place the task in.
        percent_done : float, optional
            Completion percentage 0-100.
        """
        pid = self._resolve_project()
        body: dict[str, Any] = {
            "title": title,
            "description": description,
            "priority": self._priority_int(priority),
            "percent_done": percent_done / 100.0 if percent_done > 1 else percent_done,
        }
        task = self._put_real(f"/projects/{pid}/tasks", body)
        if bucket:
            bid = self._bucket_id(bucket)
            self._set_task_bucket(task["id"], bid)
            task["_bucket_name"] = self._bucket_name(bid)
        print(f"Created: {self._fmt_task(task)}")

    def update_task(
        self,
        identifier: str,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        percent_done: float | None = None,
        bucket: str | None = None,
        done: bool | None = None,
    ) -> None:
        """Update one or more fields of an existing task.

        Parameters
        ----------
        identifier : str
            Task API id, bare index, or ``<project>-<index>`` string.
        title, description, priority, percent_done, bucket, done
            Fields to update; ``None`` means leave unchanged.
        """
        self._load_view_tasks(include_done=True)
        task_id = self._resolve_task_id(identifier)
        existing = self._get(f"/tasks/{task_id}")
        body: dict[str, Any] = {
            "title": existing["title"],
            "description": existing.get("description", ""),
            "priority": existing.get("priority", 0),
            "percent_done": existing.get("percent_done", 0),
            "done": existing.get("done", False),
        }
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if priority is not None:
            body["priority"] = self._priority_int(priority)
        if percent_done is not None:
            body["percent_done"] = percent_done / 100.0 if percent_done > 1 else percent_done
        if done is not None:
            body["done"] = done
        task = self._put(f"/tasks/{task_id}", body)
        self._resolve_buckets()
        if bucket is not None:
            bid = self._bucket_id(bucket)
            self._set_task_bucket(task_id, bid)
            task["_bucket_name"] = self._bucket_name(bid)
        print(f"Updated: {self._fmt_task(task)}")

    def _set_task_bucket(self, task_id: int, bucket_id: int) -> None:
        """Move a task to a Kanban bucket via the view-bucket-tasks endpoint."""
        self._resolve_buckets()
        pid = self._resolve_project()
        if not self._kanban_view_id:
            return
        self._post(
            f"/projects/{pid}/views/{self._kanban_view_id}/buckets/{bucket_id}/tasks",
            {"task_id": task_id},
        )

    def move_task(self, identifier: str, bucket: str) -> None:
        """Move a task to a different Kanban bucket.

        Parameters
        ----------
        identifier : str
            Task API id, bare index, or ``<project>-<index>`` string.
        bucket : str
            Destination bucket name or id.
        """
        self._load_view_tasks(include_done=True)
        task_id = self._resolve_task_id(identifier)
        self._resolve_buckets()
        bid = self._bucket_id(bucket)
        self._set_task_bucket(task_id, bid)
        # Mark done=True when moving to the done bucket
        done_bid = self._buckets.get("done")
        if done_bid and bid == done_bid:
            existing = self._get(f"/tasks/{task_id}")
            if not existing.get("done"):
                self._put(f"/tasks/{task_id}", {
                    "title": existing["title"],
                    "description": existing.get("description", ""),
                    "priority": existing.get("priority", 0),
                    "percent_done": existing.get("percent_done", 0),
                    "done": True,
                })
        t = self._get(f"/tasks/{task_id}")
        t["_bucket_name"] = self._bucket_name(bid)
        print(f"Moved:   {self._fmt_task(t)}")

    def mark_done(self, identifier: str, done: bool = True) -> None:
        """Mark a task as done or reopen it.

        Parameters
        ----------
        identifier : str
            Task API id, bare index, or ``<project>-<index>`` string.
        done : bool
            ``True`` to complete, ``False`` to reopen.
        """
        self._load_view_tasks(include_done=True)
        task_id = self._resolve_task_id(identifier)
        existing = self._get(f"/tasks/{task_id}")
        body: dict[str, Any] = {
            "title": existing["title"],
            "description": existing.get("description", ""),
            "priority": existing.get("priority", 0),
            "percent_done": 1.0 if done else existing.get("percent_done", 0),
            "done": done,
        }
        task = self._put(f"/tasks/{task_id}", body)
        self._resolve_buckets()
        if done:
            done_bid = self._buckets.get("done")
            if done_bid:
                self._set_task_bucket(task_id, done_bid)
                task["_bucket_name"] = self._bucket_name(done_bid)
        verb = "Done" if done else "Reopened"
        print(f"{verb}:   {self._fmt_task(task)}")

    def add_comment(self, identifier: str, comment: str) -> None:
        """Add a comment to a task.

        Parameters
        ----------
        identifier : str
            Task API id, bare index, or ``<project>-<index>`` string.
        comment : str
            Comment text to post.
        """
        self._load_view_tasks(include_done=True)
        task_id = self._resolve_task_id(identifier)
        result = self._put_real(f"/tasks/{task_id}/comments", {"comment": comment})
        print(f"Comment #{result.get('id', '?')} added to task {task_id}")

    def delete_task(self, identifier: str, force: bool = False) -> None:
        """Delete a task, with optional confirmation prompt.

        Parameters
        ----------
        identifier : str
            Task API id, bare index, or ``<project>-<index>`` string.
        force : bool
            Skip the confirmation prompt when True.
        """
        self._load_view_tasks(include_done=True)
        task_id = self._resolve_task_id(identifier)
        if not force:
            t = self._get(f"/tasks/{task_id}")
            confirm = input(f"Delete task #{task_id} '{t['title']}'? [y/N] ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Aborted.")
                return
        result = self._delete(f"/tasks/{task_id}")
        print(f"Deleted task #{task_id}: {result.get('message', 'ok')}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    p = argparse.ArgumentParser(
        prog="vikunja_cli",
        description="Vikunja task manager CLI (loads settings from .env)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # projects
    sub.add_parser("projects", help="List all projects")

    # views
    sub.add_parser("views", help="List views for the configured project")

    # buckets
    sub.add_parser("buckets", help="List Kanban buckets (columns)")

    # list
    ls = sub.add_parser("list", help="List tasks")
    ls.add_argument("--bucket", "-b", metavar="NAME", help="Filter by bucket name or id")
    ls.add_argument("--all", "-a", dest="include_done", action="store_true",
                    help="Include completed tasks")
    ls.add_argument("--verbose", "-v", action="store_true", help="Show descriptions")

    # get
    g = sub.add_parser("get", help="Get task details")
    g.add_argument("id", metavar="TASK", help="API id, bare index, or <project>-<index>")

    # create
    cr = sub.add_parser("create", help="Create a new task")
    cr.add_argument("title", metavar="TITLE")
    cr.add_argument("--desc", "-d", metavar="DESCRIPTION", default="")
    cr.add_argument("--priority", "-p", metavar="LEVEL", default="medium",
                    help="none/low/medium/high/urgent/now or 0-5")
    cr.add_argument("--bucket", "-b", metavar="NAME", help="Bucket name or id")
    cr.add_argument("--percent", metavar="N", type=float, default=0,
                    help="Percent done 0-100")

    # update
    up = sub.add_parser("update", help="Update a task")
    up.add_argument("id", metavar="TASK", help="API id, bare index, or <project>-<index>")
    up.add_argument("--title", "-t", metavar="TITLE")
    up.add_argument("--desc", "-d", metavar="DESCRIPTION")
    up.add_argument("--priority", "-p", metavar="LEVEL",
                    help="none/low/medium/high/urgent/now or 0-5")
    up.add_argument("--percent", metavar="N", type=float,
                    help="Percent done 0-100")
    up.add_argument("--bucket", "-b", metavar="NAME", help="Move to bucket")

    # move
    mv = sub.add_parser("move", help="Move task to a different bucket/state")
    mv.add_argument("id", metavar="TASK", help="API id, bare index, or <project>-<index>")
    mv.add_argument("bucket", metavar="BUCKET", help="Bucket name or id")

    # done
    dn = sub.add_parser("done", help="Mark task as done")
    dn.add_argument("id", metavar="TASK", help="API id, bare index, or <project>-<index>")

    # undone
    un = sub.add_parser("undone", help="Reopen a completed task")
    un.add_argument("id", metavar="TASK", help="API id, bare index, or <project>-<index>")

    # comment
    cm = sub.add_parser("comment", help="Add a comment to a task")
    cm.add_argument("id", metavar="TASK", help="API id, bare index, or <project>-<index>")
    cm.add_argument("text", metavar="TEXT", help="Comment text")

    # delete
    dl = sub.add_parser("delete", help="Delete a task")
    dl.add_argument("id", metavar="TASK", help="API id, bare index, or <project>-<index>")
    dl.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    return p


def main() -> None:
    """Entry point for the Vikunja CLI."""
    parser = build_parser()
    args = parser.parse_args()

    cfg = load_config()
    client = VikunjaClient(cfg["url"], cfg["key"], cfg["project"])

    try:
        match args.cmd:
            case "projects":
                client.list_projects()
            case "views":
                client.list_views()
            case "buckets":
                client.list_buckets()
            case "list":
                client.list_tasks(
                    bucket=args.bucket,
                    include_done=args.include_done,
                    verbose=args.verbose,
                )
            case "get":
                client.get_task(args.id)
            case "create":
                client.create_task(
                    title=args.title,
                    description=args.desc,
                    priority=args.priority,
                    bucket=args.bucket,
                    percent_done=args.percent,
                )
            case "update":
                client.update_task(
                    identifier=args.id,
                    title=args.title,
                    description=args.desc,
                    priority=args.priority,
                    percent_done=args.percent,
                    bucket=args.bucket,
                )
            case "move":
                client.move_task(args.id, args.bucket)
            case "done":
                client.mark_done(args.id, done=True)
            case "undone":
                client.mark_done(args.id, done=False)
            case "comment":
                client.add_comment(args.id, args.text)
            case "delete":
                client.delete_task(args.id, force=args.force)
    except requests.HTTPError as e:
        body = ""
        try:
            body = e.response.json().get("message", "")
        except Exception:
            pass
        sys.exit(f"HTTP {e.response.status_code}: {body or str(e)}")
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
