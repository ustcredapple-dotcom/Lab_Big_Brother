from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
DEFAULT_TOKEN_FILE = ZZLAB_ROOT / "Key/telegram_bot_token.txt"
DEFAULT_CONFIG = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/telegram_bot_config.json"
DEFAULT_OFFSET = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/telegram_bot_offset.json"
DEFAULT_INBOX = ZZLAB_ROOT / "AI_Agent/Lab_Memory_Agent/inbox/telegram"
QUERY_SCRIPT = ZZLAB_ROOT / "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py"


HELP_TEXT = """实验室大师兄 Telegram 入口

命令：
/id - 显示当前 chat_id，用于加入白名单
/ask 问题 - 查询 lab notebook
/note 内容 - 写入一条待整理实验记录
/status - 查看 bot 状态
/help - 显示帮助

中文快捷写法：
查 DDS 验收怎么做的？
记 今天 556 laser 测试发现功率漂移，需要明天复查。
"""


def read_token(path: Path) -> str:
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    for part in raw.replace("=", " ").replace(":", " ").split():
        if re.match(r"^\d{6,}:[A-Za-z0-9_-]{20,}$", part):
            return part
    return raw if re.match(r"^\d{6,}:[A-Za-z0-9_-]{20,}$", raw) else ""


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_config() -> dict[str, Any]:
    return {
        "allowed_chat_ids": [],
        "default_top_k": 5,
        "notes_inbox": str(DEFAULT_INBOX),
        "query_timeout_seconds": 60,
        "allow_registration_mode": True,
    }


def telegram_request(token: str, method: str, payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    command = [
        "curl",
        "-sS",
        "--fail-with-body",
        f"https://api.telegram.org/bot{token}/{method}",
    ]
    if payload is not None:
        command.extend(
            [
                "-H",
                "Content-Type: application/json",
                "-d",
                json.dumps(payload, ensure_ascii=False),
            ]
        )
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if completed.returncode:
        detail = completed.stdout.strip() or completed.stderr.strip() or f"curl exited {completed.returncode}"
        raise RuntimeError(f"Telegram API {method} failed: {detail}")
    result = json.loads(completed.stdout)
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API {method} returned not ok: {json.dumps(result, ensure_ascii=False)}")
    return result


def send_message(token: str, chat_id: int, text: str) -> None:
    chunks = [text[index : index + 3800] for index in range(0, len(text), 3800)] or [""]
    for chunk in chunks:
        telegram_request(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )


def allowed(chat_id: int, config: dict[str, Any]) -> bool:
    ids = [int(item) for item in config.get("allowed_chat_ids", [])]
    return chat_id in ids


def query_notebook(question: str, config: dict[str, Any]) -> str:
    top_k = int(config.get("default_top_k", 5))
    result = subprocess.run(
        [
            sys.executable,
            str(QUERY_SCRIPT),
            question,
            "--top-k",
            str(top_k),
            "--include-source-snippets",
            "--format",
            "json",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=int(config.get("query_timeout_seconds", 60)),
    )
    if result.returncode:
        return f"查询失败：{result.stderr.strip() or result.stdout.strip() or result.returncode}"
    data = json.loads(result.stdout)
    evidence = data.get("evidence", [])
    if not evidence:
        return f"没有找到明确证据。\n\nQuery: {question}"
    lines = [
        f"结论：{data.get('likely_done_before', 'unknown')}，置信度 {data.get('confidence', 'unknown')}，证据 {len(evidence)} 条。",
        "",
    ]
    for index, item in enumerate(evidence[:3], start=1):
        lines.extend(
            [
                f"{index}. {item.get('section', '')} / {item.get('title', '')}",
                f"分数：{item.get('score', 0):.1f}",
                f"摘要：{item.get('summary', '')}",
            ]
        )
        facts = item.get("important_facts") or []
        if facts:
            lines.append("关键事实：")
            lines.extend(f"- {fact}" for fact in facts[:4])
        decisions = item.get("decisions_or_conclusions") or []
        if decisions:
            lines.append("结论/决定：")
            lines.extend(f"- {decision}" for decision in decisions[:3])
        snippet = item.get("source_snippet", "")
        if snippet:
            lines.append(f"原文片段：{snippet[:700]}")
        lines.append(f"来源：{item.get('html', '')}")
        lines.append("")
    return "\n".join(lines).strip()


def save_note(text: str, chat_id: int, user: dict[str, Any], config: dict[str, Any]) -> Path:
    inbox = Path(config.get("notes_inbox") or str(DEFAULT_INBOX))
    inbox.mkdir(parents=True, exist_ok=True)
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    username = user.get("username") or "unknown"
    path = inbox / f"{stamp}_{chat_id}.md"
    content = f"""---
source: telegram
chat_id: {chat_id}
username: "{str(username).replace('"', '\\"')}"
created_at: {now.isoformat(timespec="seconds")}
status: inbox
---

# Telegram Note {stamp}

{text.strip()}
"""
    path.write_text(content, encoding="utf-8")
    return path


def parse_command(text: str) -> tuple[str, str]:
    stripped = text.strip()
    lowered = stripped.casefold()
    if lowered.startswith("/ask"):
        return "ask", stripped[4:].strip()
    if lowered.startswith("/note"):
        return "note", stripped[5:].strip()
    if lowered.startswith("/help"):
        return "help", ""
    if lowered.startswith("/start"):
        return "start", ""
    if lowered.startswith("/id"):
        return "id", ""
    if lowered.startswith("/status"):
        return "status", ""
    if stripped.startswith("查"):
        return "ask", stripped[1:].strip()
    if stripped.startswith("记"):
        return "note", stripped[1:].strip()
    return "ask", stripped


def handle_message(token: str, message: dict[str, Any], config: dict[str, Any]) -> None:
    chat = message.get("chat") or {}
    chat_id = int(chat.get("id"))
    user = message.get("from") or {}
    text = str(message.get("text") or "").strip()
    command, body = parse_command(text)

    if command in {"start", "id"}:
        if allowed(chat_id, config):
            send_message(token, chat_id, f"已授权。你的 chat_id 是：{chat_id}\n\n{HELP_TEXT}")
        elif config.get("allow_registration_mode", True):
            send_message(token, chat_id, f"你的 chat_id 是：{chat_id}\n请把它加入 telegram_bot_config.json 的 allowed_chat_ids 后再查询或写入。")
        else:
            send_message(token, chat_id, "未授权。")
        return

    if not allowed(chat_id, config):
        send_message(token, chat_id, "未授权。先发送 /id 获取 chat_id，然后把它加入白名单。")
        return

    if command == "help":
        send_message(token, chat_id, HELP_TEXT)
    elif command == "status":
        send_message(token, chat_id, "大师兄 Telegram bot 正在运行。\n查询索引：DeepSeek distillation + source HTML\n写入入口：telegram inbox")
    elif command == "note":
        if not body:
            send_message(token, chat_id, "请在 /note 后面写入内容。")
            return
        path = save_note(body, chat_id, user, config)
        send_message(token, chat_id, f"已记入 inbox：{path}")
    elif command == "ask":
        if not body:
            send_message(token, chat_id, "请在 /ask 后面写问题。")
            return
        send_message(token, chat_id, "收到，我查一下 lab notebook。")
        send_message(token, chat_id, query_notebook(body, config))


def poll(token: str, config_path: Path, offset_path: Path, once: bool = False) -> None:
    offset = int(read_json(offset_path, {"offset": 0}).get("offset", 0))
    print("实验室大师兄 Telegram bot polling started.", flush=True)
    while True:
        config = read_json(config_path, default_config())
        payload = {"timeout": 30, "offset": offset, "allowed_updates": ["message"]}
        try:
            response = telegram_request(token, "getUpdates", payload, timeout=45)
            for update in response.get("result", []):
                offset = max(offset, int(update["update_id"]) + 1)
                if "message" in update:
                    try:
                        handle_message(token, update["message"], config)
                    except Exception as exc:
                        chat_id = int((update.get("message", {}).get("chat") or {}).get("id", 0))
                        if chat_id:
                            send_message(token, chat_id, f"处理失败：{type(exc).__name__}: {exc}")
                        print(f"message handling failed: {type(exc).__name__}: {exc}", flush=True)
                write_json(offset_path, {"offset": offset})
        except Exception as exc:
            print(f"poll failed: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(5)
        if once:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram interface for 实验室大师兄.")
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--offset", type=Path, default=DEFAULT_OFFSET)
    parser.add_argument("--wait-for-token", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if not args.config.exists():
        write_json(args.config, default_config())
    token = read_token(args.token_file)
    while not token and args.wait_for_token:
        print(f"Telegram bot token not found yet. Waiting for {args.token_file}", flush=True)
        time.sleep(60)
        token = read_token(args.token_file)
    if not token:
        raise SystemExit(f"Telegram bot token not found. Put BotFather token in {args.token_file}")
    poll(token, args.config, args.offset, once=args.once)


if __name__ == "__main__":
    main()
