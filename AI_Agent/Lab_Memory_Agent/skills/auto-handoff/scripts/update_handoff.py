from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


HANDOFF_RELATIVE = Path("PROJECT_HANDOFF.md")
HANDOFF_ZH_RELATIVE = Path("Document/Human_Docs_ZH/PROJECT_HANDOFF_zh.md")
LOG_RELATIVE = Path(
    "Document/AI_Agent_Migration_2026-06-11/conversation_records/WORK_LOG.md"
)
LIST_FIELDS = (
    "state",
    "completed",
    "decisions",
    "blockers",
    "next_actions",
    "files_to_read",
    "changed_files",
    "notes",
)


def default_root() -> Path:
    # scripts/update_handoff.py -> auto-handoff -> skills -> Lab_Memory_Agent
    # -> AI_Agent -> shared ZZLab_AI root
    return Path(__file__).resolve().parents[5]


def read_payload(path: str) -> dict:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("handoff input must be a JSON object")
    return data


def clean_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return " ".join(value.strip().split())


def clean_list(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array of strings")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} must contain only strings")
        cleaned = " ".join(item.strip().split())
        if cleaned:
            result.append(cleaned)
    return result


def normalize(data: dict) -> dict:
    normalized = {
        "session_id": clean_text(data.get("session_id"), "session_id"),
        "actor": clean_text(data.get("actor", "AI agent"), "actor"),
        "objective": clean_text(data.get("objective"), "objective"),
    }
    for field in LIST_FIELDS:
        normalized[field] = clean_list(data.get(field, []), field)
    return normalized


def bullets(items: list[str], empty: str = "None recorded.") -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in items)


def numbered(items: list[str]) -> str:
    if not items:
        return "1. No next action recorded."
    return "\n".join(f"{index}. {item}" for index, item in enumerate(items, start=1))


def render_current(data: dict, timestamp: str) -> str:
    return f"""# ZZLab AI Project Handoff

> Start here. This file is the current project snapshot for humans and AI agents. Detailed history is kept in the work log.

- Last updated: {timestamp}
- Updated by: {data['actor']}
- Session ID: `{data['session_id']}`

## Immediate Objective

{data['objective']}

## Current State

{bullets(data['state'])}

## Completed In Latest Session

{bullets(data['completed'])}

## Decisions

{bullets(data['decisions'])}

## Active Blockers

{bullets(data['blockers'], 'No active blocker recorded.')}

## Next Actions

{numbered(data['next_actions'])}

## Files To Read

{bullets(data['files_to_read'])}

## Changed Files

{bullets(data['changed_files'])}

## Notes

{bullets(data['notes'])}

## Handoff Protocol

- Read `AGENTS.md` and this file before changing the project.
- After significant work, update this snapshot and append to the work log with the `auto-handoff` skill.
- Keep durable, searchable lab facts in `AI_Agent/Lab_Memory_Agent/entries/` with source references.
- Never place passwords, tokens, cookies, or private keys in handoff documents.
"""


def render_current_zh(data: dict, timestamp: str) -> str:
    return f"""# ZZLab AI 当前交接快照

> 这是 `PROJECT_HANDOFF.md` 的中文人类版，保存在私有 `Document/` 目录下，不进入公开 GitHub。详细历史见工作日志。

- 最近更新: {timestamp}
- 更新者: {data['actor']}
- Session ID: `{data['session_id']}`

## 当前目标

{data['objective']}

## 当前状态

{bullets(data['state'])}

## 最新完成

{bullets(data['completed'])}

## 已做决策

{bullets(data['decisions'])}

## 当前 Blocker

{bullets(data['blockers'], 'No active blocker recorded.')}

## 下一步

{numbered(data['next_actions'])}

## 下个 AI 先读

{bullets(data['files_to_read'])}

## 本次改动文件

{bullets(data['changed_files'])}

## 备注

{bullets(data['notes'])}

## 交接规则

- 修改项目前先读 `AGENTS.md` 和 `PROJECT_HANDOFF.md`。
- 显著工作结束后，用 `auto-handoff` 更新当前快照并追加工作日志。
- 需要长期可检索的实验室事实，放进 `AI_Agent/Lab_Memory_Agent/entries/` 并附来源。
- 永远不要把密码、token、cookie 或私钥写进交接文档。
"""


def render_log_entry(data: dict, timestamp: str) -> str:
    return f"""

## {timestamp} | {data['objective']}

<!-- session_id: {data['session_id']} -->

- Actor: {data['actor']}
- Session ID: `{data['session_id']}`

### Completed

{bullets(data['completed'])}

### Decisions

{bullets(data['decisions'])}

### Blockers

{bullets(data['blockers'], 'No active blocker recorded.')}

### Next Actions

{numbered(data['next_actions'])}

### Changed Files

{bullets(data['changed_files'])}

### Notes

{bullets(data['notes'])}
"""


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update the ZZLab current handoff and append an idempotent work-log entry."
    )
    parser.add_argument("--input", required=True, help="UTF-8 JSON file, or - for stdin")
    parser.add_argument("--root", help="Override the shared ZZLab_AI root")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print without writing")
    parser.add_argument(
        "--no-github-sync",
        action="store_true",
        help="Update local handoff files without committing or pushing GitHub",
    )
    args = parser.parse_args()

    data = normalize(read_payload(args.input))
    root = Path(args.root).expanduser().resolve() if args.root else default_root()
    handoff_path = root / HANDOFF_RELATIVE
    handoff_zh_path = root / HANDOFF_ZH_RELATIVE
    log_path = root / LOG_RELATIVE
    timestamp = datetime.now().astimezone().isoformat(timespec="minutes")
    current = render_current(data, timestamp)
    current_zh = render_current_zh(data, timestamp)
    marker = f"<!-- session_id: {data['session_id']} -->"
    if log_path.exists():
        log = log_path.read_text(encoding="utf-8")
    else:
        log = "# ZZLab AI Work Log\n\nThis file is append-only. Read `PROJECT_HANDOFF.md` for the current snapshot.\n"
    appended = marker not in log
    if appended:
        log = log.rstrip() + render_log_entry(data, timestamp) + "\n"

    if args.dry_run:
        print(current)
        print("\n--- PRIVATE CHINESE HANDOFF ---")
        print(current_zh)
        print("\n--- WORK LOG ENTRY ---")
        print(render_log_entry(data, timestamp) if appended else "session already present")
        return

    atomic_write(handoff_path, current)
    atomic_write(handoff_zh_path, current_zh)
    if appended:
        atomic_write(log_path, log)
    print(f"updated {handoff_path}")
    print(f"updated {handoff_zh_path}")
    print(f"{'appended to' if appended else 'already present in'} {log_path}")

    if not args.no_github_sync:
        sync_script = Path(__file__).with_name("sync_github.py")
        if sync_script.exists() and (root / ".git").exists():
            result = subprocess.run(
                [sys.executable, str(sync_script), "--root", str(root)],
                check=False,
            )
            if result.returncode:
                raise SystemExit(result.returncode)
        elif not (root / ".git").exists():
            print("GitHub sync skipped: shared root is not a Git repository")


if __name__ == "__main__":
    main()
