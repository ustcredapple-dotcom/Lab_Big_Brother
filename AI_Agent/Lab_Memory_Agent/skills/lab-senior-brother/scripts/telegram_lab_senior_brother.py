from __future__ import annotations

import argparse
import html
import json
import re
import shutil
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
DEFAULT_STATE = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/telegram_bot_state.json"
DEFAULT_INBOX = ZZLAB_ROOT / "AI_Agent/Lab_Memory_Agent/inbox/telegram"
DEFAULT_DAILY_ROOT = ZZLAB_ROOT
QUERY_SCRIPT = ZZLAB_ROOT / "AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py"


HELP_TEXT = """实验室大师兄 Telegram 入口

命令：
/id - 显示当前 chat_id，用于加入白名单
/ask 问题 - 查询 lab notebook，默认不写入记忆
/note 内容 - 写入一条待整理实验记录
/开始记 - 进入连续记录模式
/停止记 - 退出连续记录模式，恢复默认查询
/status - 查看 bot 状态
/help - 显示帮助

中文快捷写法：
查 DDS 验收怎么做的？
记 今天 556 laser 测试发现功率漂移，需要明天复查。
开始记
停止记
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
        "daily_root": str(DEFAULT_DAILY_ROOT),
        "telegram_folder_name": "telegram文件和聊天记录",
        "query_timeout_seconds": 60,
        "allow_registration_mode": True,
        "send_html_details": True,
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


def send_document(token: str, chat_id: int, path: Path, caption: str = "") -> None:
    command = [
        "curl",
        "-sS",
        "--fail-with-body",
        f"https://api.telegram.org/bot{token}/sendDocument",
        "-F",
        f"chat_id={chat_id}",
        "-F",
        f"document=@{path}",
    ]
    if caption:
        command.extend(["-F", f"caption={caption[:900]}"])
    completed = subprocess.run(command, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if completed.returncode:
        detail = completed.stdout.strip() or completed.stderr.strip() or f"curl exited {completed.returncode}"
        raise RuntimeError(f"Telegram sendDocument failed: {detail}")


def allowed(chat_id: int, config: dict[str, Any]) -> bool:
    ids = [int(item) for item in config.get("allowed_chat_ids", [])]
    return chat_id in ids


def safe_name(value: str, fallback: str = "unknown") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff._-]+", "_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:80] or fallback


def person_label(chat_id: int, user: dict[str, Any]) -> str:
    username = user.get("username")
    if username:
        return safe_name(str(username), f"chat_{chat_id}")
    name = " ".join(str(user.get(key, "")).strip() for key in ("first_name", "last_name")).strip()
    return safe_name(name, f"chat_{chat_id}")


def daily_person_dir(chat_id: int, user: dict[str, Any], config: dict[str, Any], when: datetime | None = None) -> Path:
    when = when or datetime.now().astimezone()
    root = Path(config.get("daily_root") or str(DEFAULT_DAILY_ROOT))
    folder_name = config.get("telegram_folder_name") or "telegram文件和聊天记录"
    path = root / when.date().isoformat() / folder_name / f"{person_label(chat_id, user)}_{chat_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_chat_record(chat_id: int, user: dict[str, Any], message: dict[str, Any], config: dict[str, Any], kind: str, text: str = "", files: list[dict[str, Any]] | None = None) -> None:
    now = datetime.now().astimezone()
    folder = daily_person_dir(chat_id, user, config, now)
    record = {
        "created_at": now.isoformat(timespec="seconds"),
        "chat_id": chat_id,
        "user": {
            "id": user.get("id"),
            "username": user.get("username"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
        },
        "message_id": message.get("message_id"),
        "kind": kind,
        "text": text,
        "files": files or [],
    }
    with (folder / "chat_records.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    md = folder / "chat_records.md"
    with md.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {record['created_at']} | {kind}\n\n")
        if text:
            handle.write(text.strip() + "\n\n")
        for file_record in files or []:
            handle.write(f"- File: `{file_record.get('path', '')}` ({file_record.get('mime_type', '')})\n")


def state_for_chat(state: dict[str, Any], chat_id: int) -> dict[str, Any]:
    return state.setdefault("chats", {}).setdefault(str(chat_id), {"mode": "ask"})


def set_chat_mode(state_path: Path, chat_id: int, mode: str) -> None:
    state = read_json(state_path, {"chats": {}})
    state_for_chat(state, chat_id)["mode"] = mode
    write_json(state_path, state)


def get_chat_mode(state: dict[str, Any], chat_id: int) -> str:
    return str(state.get("chats", {}).get(str(chat_id), {}).get("mode", "ask"))


def query_notebook(question: str, config: dict[str, Any]) -> dict[str, Any]:
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
        return {"error": f"查询失败：{result.stderr.strip() or result.stdout.strip() or result.returncode}"}
    return json.loads(result.stdout)


def render_query_html(question: str, result: dict[str, Any], output: Path) -> None:
    evidence = result.get("evidence", [])
    rows = []
    for item in evidence:
        facts = "".join(f"<li>{html.escape(str(fact))}</li>" for fact in (item.get("important_facts") or []))
        decisions = "".join(f"<li>{html.escape(str(decision))}</li>" for decision in (item.get("decisions_or_conclusions") or []))
        rows.append(
            "<section>"
            f"<h2>{html.escape(item.get('section', ''))} / {html.escape(item.get('title', ''))}</h2>"
            f"<p><b>Score:</b> {html.escape(str(item.get('score', '')))}</p>"
            f"<p>{html.escape(item.get('summary', ''))}</p>"
            f"<h3>Important facts</h3><ul>{facts}</ul>"
            f"<h3>Decisions / conclusions</h3><ul>{decisions}</ul>"
            f"<h3>Source snippet</h3><pre>{html.escape(item.get('source_snippet', ''))}</pre>"
            f"<p><b>Source:</b> {html.escape(item.get('html', ''))}</p>"
            "</section>"
        )
    body = f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8">
  <title>实验室大师兄查询详情</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 28px; line-height: 1.55; }}
    section {{ border-top: 1px solid #ddd; padding-top: 1rem; margin-top: 1rem; }}
    pre {{ white-space: pre-wrap; background: #f7f7f7; padding: 12px; border: 1px solid #ddd; }}
  </style>
</head>
<body>
  <h1>实验室大师兄查询详情</h1>
  <p><b>Question:</b> {html.escape(question)}</p>
  <p><b>Likely:</b> {html.escape(str(result.get('likely_done_before', 'unknown')))} | <b>Confidence:</b> {html.escape(str(result.get('confidence', 'unknown')))}</p>
  {''.join(rows) if rows else '<p>没有找到明确证据。</p>'}
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")


def short_query_reply(question: str, result: dict[str, Any]) -> str:
    if result.get("error"):
        return str(result["error"])
    evidence = result.get("evidence", [])
    if not evidence:
        return f"我没在现有 notebook 里找到明确记录。详情我放在 HTML 里了。"
    top = evidence[0]
    facts = top.get("important_facts") or []
    happened = top.get("what_happened") or []
    decisions = top.get("decisions_or_conclusions") or []
    bullets = []
    candidates = [*happened, *decisions, *facts]
    priority_words = ("解决", "正常", "成功", "结论", "滤波", "功放", "避免", "参数", "温度", "时间")
    priority = [item for item in candidates if any(word in str(item) for word in priority_words)]
    for item in [*happened[:2], *priority, *candidates]:
        text = str(item).strip()
        if text and text not in bullets:
            bullets.append(text)
        if len(bullets) >= 4:
            break
    if not bullets:
        summary = top.get("summary") or "我找到了相关记录，但摘要比较短。"
        return f"{summary}\n\n详情我放在 HTML 里了。"
    lines = ["之前的记录里是这样做的："]
    lines.extend(f"- {item}" for item in bullets)
    lines.append("\n更完整的原文和来源我放在 HTML 里。")
    return "\n".join(lines)


def build_file_index(config: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(config.get("daily_root") or str(DEFAULT_DAILY_ROOT))
    folder_name = config.get("telegram_folder_name") or "telegram文件和聊天记录"
    records: list[dict[str, Any]] = []
    for jsonl in sorted(root.glob(f"20??-??-??/{folder_name}/*/chat_records.jsonl")):
        for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            for file_item in item.get("files", []):
                path = file_item.get("path", "")
                if not path or not Path(path).is_file():
                    continue
                haystack = "\n".join(
                    [
                        str(file_item.get("file_name", "")),
                        str(file_item.get("path", "")),
                        str(file_item.get("mime_type", "")),
                        str(file_item.get("classification", "")),
                        str(file_item.get("text_preview", "")),
                        str(item.get("text", "")),
                        str(item.get("_person_folder", "")),
                    ]
                ).casefold()
                records.append(
                    {
                        "path": path,
                        "file_name": file_item.get("file_name") or Path(path).name,
                        "mime_type": file_item.get("mime_type", ""),
                        "created_at": item.get("created_at", ""),
                        "person": item.get("_person_folder", ""),
                        "context": item.get("text", ""),
                        "haystack": haystack,
                    }
                )
    return records


def file_request_terms(text: str) -> list[str]:
    cleaned = text
    for phrase in ["请给我", "给我", "发给我", "发送", "找一下", "找", "说明书", "pdf", "文件", "manual", "datasheet"]:
        cleaned = cleaned.replace(phrase, " ")
    terms = [term.casefold() for term in re.findall(r"[A-Za-z0-9\u4e00-\u9fff_.+-]{2,}", cleaned)]
    return [term for term in terms if term not in {"一下", "这个", "那个"}]


def looks_like_file_request(text: str) -> bool:
    lowered = text.casefold()
    return any(key in lowered for key in ["给我", "发", "发送", "说明书", "pdf", "manual", "datasheet", "文件"])


def find_files_for_request(text: str, config: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    terms = file_request_terms(text)
    if not terms:
        return []
    scored = []
    for item in build_file_index(config):
        score = sum(1 for term in terms if term in item["haystack"])
        suffix = Path(item["path"]).suffix.casefold()
        if "说明书" in text or "manual" in text.casefold() or "pdf" in text.casefold():
            if suffix == ".pdf":
                score += 2
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], pair[1].get("created_at", "")), reverse=True)
    return [item for _score, item in scored[:limit]]


def save_note(text: str, chat_id: int, user: dict[str, Any], config: dict[str, Any]) -> Path:
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    username = user.get("username") or "unknown"
    folder = daily_person_dir(chat_id, user, config, now) / "notes"
    folder.mkdir(parents=True, exist_ok=True)
    inbox = Path(config.get("notes_inbox") or str(DEFAULT_INBOX))
    inbox.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stamp}_note.md"
    legacy_path = inbox / f"{stamp}_{chat_id}.md"
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
    legacy_path.write_text(content, encoding="utf-8")
    return path


def message_file_items(message: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if message.get("document"):
        doc = message["document"]
        items.append(
            {
                "kind": "document",
                "file_id": doc.get("file_id"),
                "file_name": doc.get("file_name") or "document",
                "mime_type": doc.get("mime_type", ""),
                "file_size": doc.get("file_size"),
            }
        )
    for kind in ("audio", "video", "voice", "animation", "video_note", "sticker"):
        if message.get(kind):
            item = message[kind]
            items.append(
                {
                    "kind": kind,
                    "file_id": item.get("file_id"),
                    "file_name": item.get("file_name") or kind,
                    "mime_type": item.get("mime_type", ""),
                    "file_size": item.get("file_size"),
                }
            )
    if message.get("photo"):
        photo = sorted(message["photo"], key=lambda item: item.get("file_size", 0))[-1]
        items.append(
            {
                "kind": "photo",
                "file_id": photo.get("file_id"),
                "file_name": f"photo_{message.get('message_id', 'unknown')}.jpg",
                "mime_type": "image/jpeg",
                "file_size": photo.get("file_size"),
            }
        )
    return [item for item in items if item.get("file_id")]


def download_telegram_file(token: str, file_id: str, destination: Path) -> None:
    info = telegram_request(token, "getFile", {"file_id": file_id}, timeout=30)["result"]
    file_path = info.get("file_path")
    if not file_path:
        raise RuntimeError("Telegram getFile did not return file_path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            "curl",
            "-sS",
            "--fail-with-body",
            "-o",
            str(destination),
            f"https://api.telegram.org/file/bot{token}/{file_path}",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    if completed.returncode:
        detail = completed.stdout.strip() or completed.stderr.strip() or f"curl exited {completed.returncode}"
        raise RuntimeError(f"Telegram file download failed: {detail}")


def text_like(path: Path, mime_type: str = "") -> bool:
    suffix = path.suffix.casefold()
    if mime_type.startswith("text/"):
        return True
    return suffix in {".txt", ".md", ".markdown", ".html", ".htm", ".csv", ".tsv", ".json", ".yaml", ".yml", ".log", ".py", ".m", ".tex", ".xml"}


def pdf_like(path: Path, mime_type: str = "") -> bool:
    return path.suffix.casefold() == ".pdf" or mime_type == "application/pdf"


def ignored_binary_like(path: Path, mime_type: str = "") -> bool:
    suffix = path.suffix.casefold()
    return suffix in {".step", ".stp", ".exe", ".dll", ".dylib", ".app", ".zip", ".7z", ".rar", ".tar", ".gz", ".dmg"}


def extract_pdf_text(path: Path, limit_pages: int = 80) -> str:
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages[:limit_pages]:
            parts.append(page.extract_text() or "")
        return "\n\n".join(part for part in parts if part.strip()).strip()
    except Exception as exc:
        return f"[PDF text extraction failed: {type(exc).__name__}: {exc}]"


def write_text_preview_html(source: Path, text: str, output: Path, title: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 28px; line-height: 1.55; }}
    pre {{ white-space: pre-wrap; background: #f8f8f8; padding: 12px; border: 1px solid #ddd; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <p><b>Source:</b> {html.escape(str(source))}</p>
  <pre>{html.escape(text[:120000])}</pre>
</body>
</html>
""",
        encoding="utf-8",
    )


def save_message_files(token: str, message: dict[str, Any], chat_id: int, user: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    folder = daily_person_dir(chat_id, user, config) / "files"
    saved: list[dict[str, Any]] = []
    for item in message_file_items(message):
        base = safe_name(str(item.get("file_name") or item["kind"]), item["kind"])
        stamp = datetime.now().astimezone().strftime("%H%M%S")
        destination = folder / f"{stamp}_{message.get('message_id', 'msg')}_{base}"
        download_telegram_file(token, str(item["file_id"]), destination)
        record = {
            "kind": item.get("kind"),
            "path": str(destination),
            "file_name": item.get("file_name"),
            "mime_type": item.get("mime_type", ""),
            "file_size": item.get("file_size"),
        }
        mime_type = str(item.get("mime_type", ""))
        preview_dir = daily_person_dir(chat_id, user, config) / "file_html"
        if pdf_like(destination, mime_type):
            text = extract_pdf_text(destination)
            text_path = destination.with_suffix(destination.suffix + ".txt")
            text_path.write_text(text, encoding="utf-8")
            html_path = preview_dir / f"{destination.name}.html"
            write_text_preview_html(destination, text, html_path, f"PDF text preview - {destination.name}")
            record["classification"] = "pdf_text"
            record["text_extract"] = str(text_path)
            record["html_preview"] = str(html_path)
            record["text_preview"] = " ".join(text.split())[:1000]
        elif text_like(destination, mime_type):
            try:
                text = destination.read_text(encoding="utf-8", errors="replace")
                text_path = destination.with_suffix(destination.suffix + ".txt")
                text_path.write_text(text, encoding="utf-8")
                html_path = preview_dir / f"{destination.name}.html"
                write_text_preview_html(destination, text, html_path, f"Text preview - {destination.name}")
                record["classification"] = "text"
                record["text_extract"] = str(text_path)
                record["html_preview"] = str(html_path)
                record["text_preview"] = " ".join(text.split())[:1000]
            except Exception as exc:
                record["text_extract_error"] = f"{type(exc).__name__}: {exc}"
        elif ignored_binary_like(destination, mime_type):
            record["classification"] = "binary_metadata_only"
        else:
            record["classification"] = "file_metadata_only"
        saved.append(record)
    return saved


def parse_command(text: str) -> tuple[str, str]:
    stripped = text.strip()
    lowered = stripped.casefold()
    help_phrases = (
        "有哪些指令",
        "有什么指令",
        "怎么用",
        "使用说明",
        "帮助",
        "命令",
        "指令",
        "help",
        "commands",
    )
    if any(phrase in lowered for phrase in help_phrases):
        return "help", ""
    if lowered in {"/开始记", "开始记", "开始记录", "/record_on"}:
        return "record_on", ""
    if lowered in {"/停止记", "停止记", "停止记录", "/record_off"}:
        return "record_off", ""
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


def handle_message(token: str, message: dict[str, Any], config: dict[str, Any], state_path: Path) -> None:
    chat = message.get("chat") or {}
    chat_id = int(chat.get("id"))
    user = message.get("from") or {}
    text = str(message.get("text") or "").strip()
    caption = str(message.get("caption") or "").strip()
    display_text = text or caption
    command, body = parse_command(text)
    state = read_json(state_path, {"chats": {}})
    mode = get_chat_mode(state, chat_id)

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

    saved_files = save_message_files(token, message, chat_id, user, config)
    if saved_files:
        context = caption or text
        append_chat_record(chat_id, user, message, config, "file", context, saved_files)
        extracted = sum(1 for item in saved_files if item.get("text_extract"))
        metadata_only = sum(1 for item in saved_files if not item.get("text_extract"))
        detail = []
        if extracted:
            detail.append(f"{extracted} 个已抽文本")
        if metadata_only:
            detail.append(f"{metadata_only} 个仅存元数据")
        suffix = f"（{'，'.join(detail)}）" if detail else ""
        send_message(token, chat_id, f"收到文件，已按当前上下文自动归档 {len(saved_files)} 个{suffix}。")
        return

    if command == "help":
        send_message(token, chat_id, HELP_TEXT)
    elif command == "status":
        send_message(token, chat_id, f"大师兄 Telegram bot 正在运行。\n当前模式：{mode}\n默认：查询；开始记后默认写入。")
    elif command == "record_on":
        set_chat_mode(state_path, chat_id, "record")
        append_chat_record(chat_id, user, message, config, "mode", "开始记")
        send_message(token, chat_id, "已进入记录模式。接下来默认记；发“停止记”恢复默认查询。")
    elif command == "record_off":
        set_chat_mode(state_path, chat_id, "ask")
        append_chat_record(chat_id, user, message, config, "mode", "停止记")
        send_message(token, chat_id, "已停止记录模式。现在默认查询。")
    elif command == "note":
        if not body:
            send_message(token, chat_id, "请在 /note 后面写入内容。")
            return
        path = save_note(body, chat_id, user, config)
        append_chat_record(chat_id, user, message, config, "note", body, saved_files)
        send_message(token, chat_id, f"已记：{path.name}")
    elif command == "ask":
        if mode == "record" and text and not text.startswith(("/ask", "查")):
            path = save_note(display_text, chat_id, user, config)
            append_chat_record(chat_id, user, message, config, "note", display_text, saved_files)
            send_message(token, chat_id, f"已记：{path.name}")
            return
        if not body:
            send_message(token, chat_id, "请在 /ask 后面写问题。")
            return
        if looks_like_file_request(body):
            matches = find_files_for_request(body, config)
            if matches:
                send_message(token, chat_id, f"找到 {len(matches)} 个相关文件，先发最相关的。")
                for item in matches:
                    send_document(token, chat_id, Path(item["path"]), f"{item.get('file_name', '')}\n{item.get('context', '')[:500]}")
                append_chat_record(chat_id, user, message, config, "file_request", body)
                return
        append_chat_record(chat_id, user, message, config, "query", body, saved_files)
        result = query_notebook(body, config)
        detail_path = daily_person_dir(chat_id, user, config) / "query_html" / f"{datetime.now().astimezone().strftime('%H%M%S')}_{safe_name(body, 'query')}.html"
        render_query_html(body, result, detail_path)
        send_message(token, chat_id, short_query_reply(body, result))
        if config.get("send_html_details", True):
            send_document(token, chat_id, detail_path, "查询详情 HTML")


def poll(token: str, config_path: Path, offset_path: Path, state_path: Path, once: bool = False) -> None:
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
                        handle_message(token, update["message"], config, state_path)
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
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
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
    poll(token, args.config, args.offset, args.state, once=args.once)


if __name__ == "__main__":
    main()
