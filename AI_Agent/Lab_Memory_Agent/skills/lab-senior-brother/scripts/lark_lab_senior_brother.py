from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
DEFAULT_APP_SECRET_FILE = ZZLAB_ROOT / "Key/Lark_App ID&Secret.txt"
DEFAULT_ENCRYPT_FILE = ZZLAB_ROOT / "Key/Lark加密策略.txt"
DEFAULT_CONFIG = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/lark_bot_config.json"
DEFAULT_STATE = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/lark_bot_state.json"
DEFAULT_INBOX = ZZLAB_ROOT / "AI_Agent/Lab_Memory_Agent/inbox/lark"
DEFAULT_DAILY_ROOT = ZZLAB_ROOT
DEFAULT_FOLDER_NAME = "lark文档和消息记录"
DEFAULT_LLM_MODEL = "qwen3.7-plus"

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import telegram_lab_senior_brother as core  # noqa: E402

try:
    import certifi  # type: ignore

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except Exception:
    pass

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateFileRequest,
        CreateFileRequestBody,
        CreateImageRequest,
        CreateImageRequestBody,
        GetMessageResourceRequest,
        P2ImMessageReceiveV1,
        ReplyMessageRequest,
        ReplyMessageRequestBody,
    )
except Exception:  # pragma: no cover - validated by runtime check
    lark = None  # type: ignore[assignment]


HELP_TEXT = """实验室大师兄 Lark 入口

群聊默认：默默记录白名单群里的发言；只有 @ 大师兄或使用命令时回复。

命令：
/id - 显示当前 chat_id / open_id，用于加入白名单
/ask 问题 或 查 问题 - 查询 lab notebook
/note 内容 或 记 内容 - 写入一条待整理实验记录
/status - 查看 bot 状态
/help - 显示帮助

群里用法：
@大师兄 cavity 的 finesse 是多少？
@大师兄 查 DDS 怎么验收？
记 今天调了 556 laser，明天复查功率漂移。
"""


def read_json(path: Path, default: Any) -> Any:
    return core.read_json(path, default)


def write_json(path: Path, value: Any) -> None:
    core.write_json(path, value)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    raw = read_json(path, {}) if path.exists() else {}
    config = default_config()
    if isinstance(raw, dict):
        config.update(raw)
    return config


def ensure_config_file(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_config(path)
    raw = read_json(path, {}) if path.exists() else {}
    if raw != config:
        write_json(path, config)
    return config


def default_config() -> dict[str, Any]:
    return {
        "platform": "lark",
        "base_url": "https://open.larksuite.com",
        "allowed_chat_ids": [],
        "allowed_user_ids": [],
        "admin_open_ids": [],
        "allow_registration_mode": True,
        "default_top_k": 5,
        "query_timeout_seconds": 60,
        "send_html_details": True,
        "llm_model": DEFAULT_LLM_MODEL,
        "rag_engine": "chunk",
        "anythingllm_base_url": "http://127.0.0.1:3001/api",
        "anythingllm_workspace_slug": "",
        "anythingllm_mode": "query",
        "daily_root": str(DEFAULT_DAILY_ROOT),
        "lark_folder_name": DEFAULT_FOLDER_NAME,
        "notes_inbox": str(DEFAULT_INBOX),
        "persistent_record_kinds": ["chat", "note", "file", "mode", "admin"],
        "digest_memory_kinds": ["chat", "note", "file"],
        "respond_in_group_only_when_mentioned": True,
        "bot_mention_names": ["大师兄", "实验室大师兄", "ZZLab Big Brother", "Lab Big Brother"],
        "record_all_joined_chats": True,
        "ignore_app_senders": True,
        "log_received_events": True,
        "conversation_context_turns": 6,
        "conversation_context_max_age_seconds": 1800,
        "send_query_progress": True,
    }


def redact_secrets(text: str) -> str:
    text = core.redact_secrets(text)
    text = re.sub(r"\bcli_[A-Za-z0-9]+\b", "cli_<redacted>", text)
    text = re.sub(r"(?i)(app[_ -]?secret[\"'=:\\s]+)[A-Za-z0-9_-]{8,}", r"\1<redacted>", text)
    text = re.sub(r"(?i)(encrypt[_ -]?key[\"'=:\\s]+)[A-Za-z0-9_-]{8,}", r"\1<redacted>", text)
    return text


def online_check(config: dict[str, Any], credentials: dict[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "tenant_access_token_ok": False,
        "bot_enabled": False,
        "bot_check_code": None,
        "bot_check_msg": "",
    }
    try:
        token_url = f"{str(config.get('base_url') or 'https://open.larksuite.com').rstrip('/')}/open-apis/auth/v3/tenant_access_token/internal"
        payload = json.dumps({"app_id": credentials.get("app_id"), "app_secret": credentials.get("app_secret")}).encode("utf-8")
        request = urllib.request.Request(
            token_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            token_data = json.loads(response.read().decode("utf-8", errors="replace"))
        result["tenant_access_token_code"] = token_data.get("code")
        result["tenant_access_token_msg"] = token_data.get("msg")
        token = str(token_data.get("tenant_access_token") or "")
        result["tenant_access_token_ok"] = bool(token) and token_data.get("code") == 0
        if not token:
            return result
        bot_url = f"{str(config.get('base_url') or 'https://open.larksuite.com').rstrip('/')}/open-apis/bot/v3/info"
        bot_request = urllib.request.Request(bot_url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(bot_request, timeout=20) as response:
            bot_data = json.loads(response.read().decode("utf-8", errors="replace"))
        result["bot_check_code"] = bot_data.get("code")
        result["bot_check_msg"] = bot_data.get("msg")
        result["bot_enabled"] = bool(bot_data.get("bot") or bot_data.get("data")) and bot_data.get("code") == 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        result["error"] = f"HTTP {exc.code}: {redact_secrets(body)}"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {redact_secrets(str(exc))}"
    return result


def parse_key_value_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("|")
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
        elif "=" in line:
            key, value = line.split("=", 1)
        elif "\t" in line:
            key, value = line.split("\t", 1)
        else:
            continue
        key = re.sub(r"[\s_-]+", "_", key.strip().casefold())
        value = value.strip().strip("`'\"")
        if value:
            result[key] = value
    return result


def read_lark_credentials(app_file: Path = DEFAULT_APP_SECRET_FILE, encrypt_file: Path = DEFAULT_ENCRYPT_FILE) -> dict[str, str]:
    app_text = app_file.read_text(encoding="utf-8", errors="replace") if app_file.exists() else ""
    enc_text = encrypt_file.read_text(encoding="utf-8", errors="replace") if encrypt_file.exists() else ""
    merged = parse_key_value_text(app_text + "\n" + enc_text)

    def pick(*needles: str) -> str:
        for key, value in merged.items():
            normalized = key.replace("_", "")
            if all(needle in normalized for needle in needles):
                return value
        return ""

    app_id = pick("app", "id") or pick("appid")
    app_secret = pick("app", "secret") or pick("secret")
    verification_token = pick("verification", "token") or pick("verify", "token") or pick("token")
    encrypt_key = pick("encrypt", "key") or pick("encryption", "key")

    if not app_id:
        match = re.search(r"\bcli_[A-Za-z0-9]+\b", app_text)
        app_id = match.group(0) if match else ""
    if not app_secret:
        candidates = [
            part
            for part in re.findall(r"\b[A-Za-z0-9_-]{20,}\b", app_text)
            if part != app_id and not part.startswith("cli_")
        ]
        app_secret = candidates[0] if candidates else ""
    return {
        "app_id": app_id.strip(),
        "app_secret": app_secret.strip(),
        "verification_token": verification_token.strip(),
        "encrypt_key": encrypt_key.strip(),
    }


def lark_client(config: dict[str, Any], credentials: dict[str, str]):
    if lark is None:
        raise RuntimeError("Missing lark_oapi. Install with: python3 -m pip install lark-oapi")
    return (
        lark.Client.builder()
        .app_id(credentials["app_id"])
        .app_secret(credentials["app_secret"])
        .domain(str(config.get("base_url") or lark.LARK_DOMAIN))
        .log_level(lark.LogLevel.ERROR)
        .build()
    )


def safe_name(value: str, fallback: str = "unknown") -> str:
    return core.safe_name(value, fallback)


def sender_ids(sender: Any) -> dict[str, str]:
    sid = getattr(sender, "sender_id", None)
    return {
        "open_id": str(getattr(sid, "open_id", "") or ""),
        "user_id": str(getattr(sid, "user_id", "") or ""),
        "union_id": str(getattr(sid, "union_id", "") or ""),
        "sender_type": str(getattr(sender, "sender_type", "") or ""),
        "tenant_key": str(getattr(sender, "tenant_key", "") or ""),
    }


def audit_event(message: Any, sender: dict[str, str], text: str, config: dict[str, Any], status: str, error: str = "") -> None:
    if not config.get("log_received_events", True):
        return
    payload = {
        "event": "lark_message",
        "status": status,
        "time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "chat_id": str(getattr(message, "chat_id", "") or ""),
        "chat_type": str(getattr(message, "chat_type", "") or ""),
        "message_type": str(getattr(message, "message_type", "") or ""),
        "message_id_present": bool(getattr(message, "message_id", "")),
        "sender_type": sender.get("sender_type", ""),
        "sender_open_id_present": bool(sender.get("open_id")),
        "text_len": len(text or ""),
        "file_item_count": len(message_file_items(message)),
        "should_reply": should_reply(message, text or "", config),
        "record_all_joined_chats": bool(config.get("record_all_joined_chats", True)),
    }
    if error:
        payload["error"] = redact_secrets(error)[:500]
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def allowed(chat_id: str, sender: dict[str, str], config: dict[str, Any]) -> bool:
    allowed_chats = {str(item) for item in config.get("allowed_chat_ids", [])}
    allowed_users = {str(item) for item in config.get("allowed_user_ids", [])}
    return chat_id in allowed_chats or sender.get("open_id") in allowed_users or sender.get("user_id") in allowed_users


def daily_sender_dir(chat_id: str, sender: dict[str, str], config: dict[str, Any], when: datetime | None = None) -> Path:
    when = when or datetime.now().astimezone()
    root = Path(config.get("daily_root") or str(DEFAULT_DAILY_ROOT))
    folder_name = str(config.get("lark_folder_name") or DEFAULT_FOLDER_NAME)
    person = sender.get("open_id") or sender.get("user_id") or "unknown"
    path = root / when.date().isoformat() / folder_name / f"{safe_name(person)}_{safe_name(chat_id, 'chat')}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_chat_record(
    chat_id: str,
    sender: dict[str, str],
    message: Any,
    config: dict[str, Any],
    kind: str,
    text: str = "",
    files: list[dict[str, Any]] | None = None,
    responded: bool = False,
) -> None:
    persistent_kinds = set(config.get("persistent_record_kinds") or default_config()["persistent_record_kinds"])
    if kind not in persistent_kinds:
        return
    now = datetime.now().astimezone()
    folder = daily_sender_dir(chat_id, sender, config, now)
    record = {
        "created_at": now.isoformat(timespec="seconds"),
        "source": "lark",
        "chat_id": chat_id,
        "sender": sender,
        "message_id": getattr(message, "message_id", None),
        "chat_type": getattr(message, "chat_type", None),
        "message_type": getattr(message, "message_type", None),
        "kind": kind,
        "responded": responded,
        "text": text,
        "files": files or [],
    }
    with (folder / "chat_records.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (folder / "chat_records.md").open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {record['created_at']} | {kind}\n\n")
        handle.write(f"- chat_id: `{chat_id}`\n")
        handle.write(f"- sender_open_id: `{sender.get('open_id', '')}`\n")
        if text:
            handle.write(f"\n{text.strip()}\n\n")
        for file_record in files or []:
            handle.write(f"- File: `{file_record.get('path', '')}` ({file_record.get('mime_type', '')})\n")


def parse_content(message: Any) -> dict[str, Any]:
    raw = getattr(message, "content", "") or ""
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def collect_text_from_post(value: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"text", "un_escape_text"} and isinstance(item, str):
                texts.append(item)
            else:
                texts.extend(collect_text_from_post(item))
    elif isinstance(value, list):
        for item in value:
            texts.extend(collect_text_from_post(item))
    return texts


def message_text(message: Any) -> str:
    content = parse_content(message)
    message_type = str(getattr(message, "message_type", "") or "")
    if message_type == "text":
        text = str(content.get("text") or "")
    elif message_type == "post":
        title = str(content.get("title") or "")
        text = "\n".join([title, *collect_text_from_post(content)]).strip()
    else:
        text = str(content.get("text") or content.get("file_name") or content.get("image_key") or "")
    for mention in getattr(message, "mentions", None) or []:
        key = str(getattr(mention, "key", "") or "")
        name = str(getattr(mention, "name", "") or "")
        if key:
            text = text.replace(key, "")
        if name:
            text = text.replace(f"@{name}", "")
    return re.sub(r"[ \t]+", " ", text).strip()


def bot_was_mentioned(message: Any, config: dict[str, Any]) -> bool:
    chat_type = str(getattr(message, "chat_type", "") or "")
    if chat_type == "p2p":
        return True
    names = {str(item).casefold() for item in config.get("bot_mention_names", [])}
    for mention in getattr(message, "mentions", None) or []:
        mentioned_type = str(getattr(mention, "mentioned_type", "") or "").casefold()
        name = str(getattr(mention, "name", "") or "").casefold()
        if mentioned_type in {"app", "bot"}:
            return True
        if name and name in names:
            return True
    return False


def should_reply(message: Any, text: str, config: dict[str, Any]) -> bool:
    stripped = text.strip()
    chat_type = str(getattr(message, "chat_type", "") or "")
    if chat_type == "p2p":
        return True
    if stripped.startswith(("/id", "/help", "/status", "/ask", "/note")):
        return True
    if bot_was_mentioned(message, config):
        return True
    return not bool(config.get("respond_in_group_only_when_mentioned", True))


def parse_command(text: str) -> tuple[str, str]:
    stripped = text.strip()
    lowered = stripped.casefold()
    if lowered.startswith("/ask"):
        return "ask", stripped[4:].strip()
    if lowered.startswith("/note"):
        return "note", stripped[5:].strip()
    if lowered.startswith("/help"):
        return "help", ""
    if lowered.startswith("/id"):
        return "id", ""
    if lowered.startswith("/status"):
        return "status", ""
    if core.is_help_request(stripped):
        return "help", ""
    note_body = core.note_request_body(stripped)
    if note_body:
        return "note", note_body
    if stripped.startswith("查"):
        return "ask", stripped[1:].strip()
    if re.match(r"^记(?:\s|[：:，,])", stripped):
        return "note", re.sub(r"^记[\s：:，,]*", "", stripped).strip()
    if core.is_casual_chat(stripped):
        return "chat", stripped
    return "agent", stripped


def send_text(client: Any, message_id: str, text: str) -> None:
    chunks = [text[index : index + 1800] for index in range(0, len(text), 1800)] or [""]
    for chunk in chunks:
        body = (
            ReplyMessageRequestBody.builder()
            .msg_type("text")
            .content(json.dumps({"text": chunk}, ensure_ascii=False))
            .reply_in_thread(False)
            .uuid(str(uuid.uuid4()))
            .build()
        )
        request = ReplyMessageRequest.builder().message_id(message_id).request_body(body).build()
        response = client.im.v1.message.reply(request)
        if not response.success():
            raise RuntimeError(f"Lark reply failed: code={response.code} msg={response.msg}")


def upload_file(client: Any, path: Path) -> str:
    with path.open("rb") as handle:
        body = (
            CreateFileRequestBody.builder()
            .file_type("stream")
            .file_name(path.name)
            .file(handle)
            .build()
        )
        response = client.im.v1.file.create(CreateFileRequest.builder().request_body(body).build())
    if not response.success():
        raise RuntimeError(f"Lark file upload failed: code={response.code} msg={response.msg}")
    return str(response.data.file_key)


def upload_image(client: Any, path: Path) -> str:
    with path.open("rb") as handle:
        body = CreateImageRequestBody.builder().image_type("message").image(handle).build()
        response = client.im.v1.image.create(CreateImageRequest.builder().request_body(body).build())
    if not response.success():
        raise RuntimeError(f"Lark image upload failed: code={response.code} msg={response.msg}")
    return str(response.data.image_key)


def send_file(client: Any, message_id: str, path: Path, caption: str = "") -> None:
    try:
        if core.image_like(path, ""):
            key = upload_image(client, path)
            msg_type = "image"
            content = {"image_key": key}
        else:
            key = upload_file(client, path)
            msg_type = "file"
            content = {"file_key": key}
        body = (
            ReplyMessageRequestBody.builder()
            .msg_type(msg_type)
            .content(json.dumps(content, ensure_ascii=False))
            .reply_in_thread(False)
            .uuid(str(uuid.uuid4()))
            .build()
        )
        response = client.im.v1.message.reply(ReplyMessageRequest.builder().message_id(message_id).request_body(body).build())
        if not response.success():
            raise RuntimeError(f"Lark file reply failed: code={response.code} msg={response.msg}")
        if caption:
            send_text(client, message_id, caption[:1200])
    except Exception as exc:
        send_text(client, message_id, f"我找到了文件，但 Lark 发送失败：{type(exc).__name__}: {redact_secrets(str(exc))}\n本机路径：{path}")


def render_query_detail_if_needed(client: Any, message_id: str, question: str, result: dict[str, Any], config: dict[str, Any]) -> None:
    if not config.get("send_html_details", True) or not core.has_clear_notebook_evidence(result):
        return
    with tempfile.TemporaryDirectory(prefix="zzlab_lark_query_html_") as temporary:
        detail_path = Path(temporary) / f"{safe_name(question, 'query')}.html"
        core.render_query_html(question, result, detail_path)
        send_file(client, message_id, detail_path, "查询详情 HTML")


def run_query_interaction(client: Any, message_id: str, chat_id: str, question_text: str, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    state_key = f"lark:{chat_id}"
    state = read_json(DEFAULT_STATE, {"chats": {}})
    resolved = core.resolve_query_with_context(question_text, state, state_key, config)
    if config.get("send_query_progress", True):
        send_text(client, message_id, core.query_progress_text(resolved))
    result = core.query_notebook(str(resolved.get("question") or question_text), config)
    send_text(client, message_id, core.short_query_reply(str(resolved.get("question") or question_text), result))
    render_query_detail_if_needed(client, message_id, str(resolved.get("question") or question_text), result, config)
    core.remember_query_context(DEFAULT_STATE, state_key, question_text, resolved, result)
    return resolved, result


def message_file_items(message: Any) -> list[dict[str, Any]]:
    content = parse_content(message)
    message_type = str(getattr(message, "message_type", "") or "")
    items: list[dict[str, Any]] = []
    if message_type == "image" and content.get("image_key"):
        items.append(
            {
                "kind": "image",
                "resource_type": "image",
                "file_key": content.get("image_key"),
                "file_name": f"image_{getattr(message, 'message_id', 'msg')}.jpg",
                "mime_type": "image/jpeg",
            }
        )
    elif message_type == "file" and content.get("file_key"):
        items.append(
            {
                "kind": "file",
                "resource_type": "file",
                "file_key": content.get("file_key"),
                "file_name": content.get("file_name") or "lark_file",
                "mime_type": content.get("mime_type") or "",
                "file_size": content.get("file_size"),
            }
        )
    elif message_type in {"media", "audio"} and content.get("file_key"):
        items.append(
            {
                "kind": message_type,
                "resource_type": "file",
                "file_key": content.get("file_key"),
                "file_name": content.get("file_name") or message_type,
                "mime_type": content.get("mime_type") or "",
                "file_size": content.get("file_size"),
            }
        )
    return items


def download_message_resource(client: Any, message_id: str, file_key: str, resource_type: str, destination: Path) -> None:
    request = (
        GetMessageResourceRequest.builder()
        .message_id(message_id)
        .file_key(file_key)
        .type(resource_type)
        .build()
    )
    response = client.im.v1.message_resource.get(request)
    if not response.success():
        raise RuntimeError(f"Lark resource download failed: code={response.code} msg={response.msg}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_obj = response.file
    destination.write_bytes(file_obj.read())


def save_message_files(client: Any, message: Any, chat_id: str, sender: dict[str, str], config: dict[str, Any], context: str) -> list[dict[str, Any]]:
    folder = daily_sender_dir(chat_id, sender, config) / "files"
    preview_dir = daily_sender_dir(chat_id, sender, config) / "file_html"
    saved: list[dict[str, Any]] = []
    for item in message_file_items(message):
        base = safe_name(str(item.get("file_name") or item["kind"]), item["kind"])
        stamp = datetime.now().astimezone().strftime("%H%M%S")
        destination = folder / f"{stamp}_{safe_name(str(getattr(message, 'message_id', 'msg')), 'msg')}_{base}"
        download_message_resource(client, str(getattr(message, "message_id", "")), str(item["file_key"]), str(item["resource_type"]), destination)
        mime_type = str(item.get("mime_type", ""))
        record = {
            "kind": item.get("kind"),
            "path": str(destination),
            "file_name": item.get("file_name"),
            "mime_type": mime_type,
            "file_size": item.get("file_size"),
        }
        if core.pdf_like(destination, mime_type):
            text = core.extract_pdf_text(destination)
            text_path = destination.with_suffix(destination.suffix + ".txt")
            text_path.write_text(text, encoding="utf-8")
            html_path = preview_dir / f"{destination.name}.html"
            core.write_text_preview_html(destination, text, html_path, f"PDF text preview - {destination.name}")
            record.update({"classification": "pdf_text", "text_extract": str(text_path), "html_preview": str(html_path), "text_preview": " ".join(text.split())[:1000]})
        elif core.text_like(destination, mime_type):
            text = destination.read_text(encoding="utf-8", errors="replace")
            text_path = destination.with_suffix(destination.suffix + ".txt")
            text_path.write_text(text, encoding="utf-8")
            html_path = preview_dir / f"{destination.name}.html"
            core.write_text_preview_html(destination, text, html_path, f"Text preview - {destination.name}")
            record.update({"classification": "text", "text_extract": str(text_path), "html_preview": str(html_path), "text_preview": " ".join(text.split())[:1000]})
        elif core.image_like(destination, mime_type):
            try:
                text = core.describe_image_with_qwen(destination, context)
                text_path = destination.with_suffix(destination.suffix + ".qwen_vision.json")
                text_path.write_text(text, encoding="utf-8")
                html_path = preview_dir / f"{destination.name}.html"
                core.write_text_preview_html(destination, text, html_path, f"Qwen vision preview - {destination.name}")
                record.update({"classification": "image_qwen_vision", "text_extract": str(text_path), "html_preview": str(html_path), "text_preview": " ".join(text.split())[:1000]})
            except Exception as exc:
                record.update({"classification": "image_metadata_only", "text_extract_error": f"{type(exc).__name__}: {exc}"})
        elif core.ignored_binary_like(destination, mime_type):
            record["classification"] = "binary_metadata_only"
        else:
            record["classification"] = "file_metadata_only"
        saved.append(record)
    return saved


def save_note(text: str, chat_id: str, sender: dict[str, str], message: Any, config: dict[str, Any]) -> Path:
    now = datetime.now().astimezone()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    folder = daily_sender_dir(chat_id, sender, config, now) / "notes"
    folder.mkdir(parents=True, exist_ok=True)
    inbox = Path(config.get("notes_inbox") or str(DEFAULT_INBOX))
    inbox.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stamp}_note.md"
    legacy_path = inbox / f"{stamp}_{safe_name(chat_id, 'chat')}.md"
    content = f"""---
source: lark
chat_id: {chat_id}
sender_open_id: "{sender.get('open_id', '')}"
created_at: {now.isoformat(timespec="seconds")}
status: inbox
---

# Lark Note {stamp}

{text.strip()}
"""
    path.write_text(content, encoding="utf-8")
    legacy_path.write_text(content, encoding="utf-8")
    return path


def build_lark_file_index(config: dict[str, Any]) -> list[dict[str, Any]]:
    root = Path(config.get("daily_root") or str(DEFAULT_DAILY_ROOT))
    folder_name = str(config.get("lark_folder_name") or DEFAULT_FOLDER_NAME)
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
                    ]
                ).casefold()
                records.append(
                    {
                        "path": path,
                        "file_name": file_item.get("file_name") or Path(path).name,
                        "mime_type": file_item.get("mime_type", ""),
                        "created_at": item.get("created_at", ""),
                        "context": item.get("text", ""),
                        "haystack": haystack,
                    }
                )
    return records


def find_files_for_request(text: str, config: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    terms = core.file_request_terms(text)
    if not terms:
        return []
    candidates = build_lark_file_index(config) + core.build_file_index(
        {
            **config,
            "telegram_folder_name": "telegram文件和聊天记录",
        }
    )
    scored = []
    for item in candidates:
        score = sum(1 for term in terms if term in item["haystack"])
        if ("说明书" in text or "manual" in text.casefold() or "pdf" in text.casefold()) and Path(item["path"]).suffix.casefold() == ".pdf":
            score += 2
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], pair[1].get("created_at", "")), reverse=True)
    return [item for _score, item in scored[:limit]]


def handle_authorized_message(client: Any, message: Any, chat_id: str, sender: dict[str, str], text: str, config: dict[str, Any]) -> None:
    command, body = parse_command(text)
    message_id = str(getattr(message, "message_id", ""))
    if command == "help":
        send_text(client, message_id, HELP_TEXT)
    elif command == "status":
        send_text(client, message_id, "大师兄 Lark bot 正在运行。\n群里默认记录；被 @ 或命令触发时才回复。\n后端：Qwen router + chunk RAG + 本地安全工具。")
    elif command == "chat":
        send_text(client, message_id, core.casual_chat_reply(text))
    elif command == "note":
        if not body:
            send_text(client, message_id, "要记什么？你可以说：记 今天调好了 556 laser。")
            return
        path = save_note(body, chat_id, sender, message, config)
        append_chat_record(chat_id, sender, message, config, "note", body, responded=True)
        send_text(client, message_id, f"已记：{path.name}")
    elif command == "ask":
        if not body:
            send_text(client, message_id, "你想查什么？直接 @ 我问就行。")
            return
        if core.looks_like_file_request(body):
            matches = find_files_for_request(body, config)
            if matches:
                send_text(client, message_id, f"找到 {len(matches)} 个相关文件，先发最相关的。")
                for item in matches:
                    send_file(client, message_id, Path(item["path"]), f"{item.get('file_name', '')}\n{item.get('context', '')[:500]}")
                return
        run_query_interaction(client, message_id, chat_id, body, config)
    else:
        state = read_json(DEFAULT_STATE, {"chats": {}})
        if core.looks_like_followup(body or text) and core.has_recent_query_context(state, f"lark:{chat_id}", config):
            run_query_interaction(client, message_id, chat_id, body or text, config)
            return
        route = core.deepseek_agent_route(body or text, "ask", config)
        action = str(route.get("action") or "unsupported")
        route_body = str(route.get("body") or body or text).strip()
        if action == "chat":
            send_text(client, message_id, str(route.get("reply") or core.casual_chat_reply(text)))
        elif action == "help":
            send_text(client, message_id, HELP_TEXT)
        elif action == "status":
            send_text(client, message_id, "大师兄 Lark bot 正在运行。\n群里默认记录；被 @ 或命令触发时才回复。\n后端：Qwen router + chunk RAG + 本地安全工具。")
        elif action == "note":
            path = save_note(route_body, chat_id, sender, message, config)
            append_chat_record(chat_id, sender, message, config, "note", route_body, responded=True)
            send_text(client, message_id, f"已记：{path.name}")
        elif action == "find_file":
            matches = find_files_for_request(route_body, config)
            if matches:
                send_text(client, message_id, f"找到 {len(matches)} 个相关文件，先发最相关的。")
                for item in matches:
                    send_file(client, message_id, Path(item["path"]), f"{item.get('file_name', '')}\n{item.get('context', '')[:500]}")
            else:
                send_text(client, message_id, "我没找到这个文件。你可以换个文件名、型号或关键词试试。")
        elif action == "query_notebook":
            run_query_interaction(client, message_id, chat_id, route_body, config)
        else:
            send_text(client, message_id, str(route.get("reply") or "这个动作我还没接到 Lark 工具里。现在我能查 notebook、记笔记、找归档文件。"))


def handle_message(client: Any, event: Any, config_path: Path) -> None:
    config = load_config(config_path)
    message = event.event.message
    sender = sender_ids(event.event.sender)
    chat_id = str(getattr(message, "chat_id", "") or "")
    text = message_text(message)
    message_id = str(getattr(message, "message_id", "") or "")

    if config.get("ignore_app_senders", True) and sender.get("sender_type", "").casefold() == "app":
        audit_event(message, sender, text, config, "ignored_app_sender")
        return

    if parse_command(text)[0] == "id":
        if config.get("allow_registration_mode", True):
            send_text(
                client,
                message_id,
                "Lark 身份信息：\n"
                f"chat_id: {chat_id}\n"
                f"open_id: {sender.get('open_id', '')}\n"
                f"user_id: {sender.get('user_id', '')}\n\n"
                "默认策略：bot 被拉进群后就会记录该群消息；群里 @ 大师兄或发命令时才回复。\n"
                "这些 ID 只用于以后需要限制敏感工具或排查权限。"
            )
        audit_event(message, sender, text, config, "replied_id")
        return

    is_allowed = allowed(chat_id, sender, config)
    if not is_allowed and not config.get("record_all_joined_chats", True):
        audit_event(message, sender, text, config, "ignored_not_allowed")
        return

    files = save_message_files(client, message, chat_id, sender, config, text)
    if files:
        append_chat_record(chat_id, sender, message, config, "file", text, files, responded=False)

    if text:
        append_chat_record(chat_id, sender, message, config, "chat", text, files, responded=False)

    if not is_allowed and not should_reply(message, text, config):
        audit_event(message, sender, text, config, "recorded_silent")
        return

    if files and should_reply(message, text, config):
        extracted = sum(1 for item in files if item.get("text_extract"))
        metadata_only = sum(1 for item in files if not item.get("text_extract"))
        detail = []
        if extracted:
            detail.append(f"{extracted} 个已抽文本")
        if metadata_only:
            detail.append(f"{metadata_only} 个仅存元数据")
        suffix = f"（{'，'.join(detail)}）" if detail else ""
        send_text(client, message_id, f"收到文件，已按当前上下文自动归档 {len(files)} 个{suffix}。")
        audit_event(message, sender, text, config, "recorded_and_replied_file")
        return

    if text and should_reply(message, text, config):
        handle_authorized_message(client, message, chat_id, sender, text, config)
        audit_event(message, sender, text, config, "recorded_and_replied")
        return
    audit_event(message, sender, text, config, "recorded_no_text")


def check_setup(config_path: Path, app_file: Path, encrypt_file: Path) -> dict[str, Any]:
    config = load_config(config_path)
    credentials = read_lark_credentials(app_file, encrypt_file)
    return {
        "sdk": bool(lark is not None),
        "config": str(config_path),
        "base_url": config.get("base_url"),
        "app_id_present": bool(credentials.get("app_id")),
        "app_secret_present": bool(credentials.get("app_secret")),
        "verification_token_present": bool(credentials.get("verification_token")),
        "encrypt_key_present": bool(credentials.get("encrypt_key")),
        "allowed_chat_ids": len(config.get("allowed_chat_ids", [])),
        "allowed_user_ids": len(config.get("allowed_user_ids", [])),
        "record_all_joined_chats": bool(config.get("record_all_joined_chats", True)),
        "respond_in_group_only_when_mentioned": bool(config.get("respond_in_group_only_when_mentioned", True)),
        "ignore_app_senders": bool(config.get("ignore_app_senders", True)),
        "log_received_events": bool(config.get("log_received_events", True)),
    }


def run(config_path: Path, app_file: Path, encrypt_file: Path) -> None:
    if lark is None:
        raise SystemExit("Missing lark_oapi. Install with: python3 -m pip install lark-oapi")
    config = ensure_config_file(config_path)
    credentials = read_lark_credentials(app_file, encrypt_file)
    missing = [key for key in ("app_id", "app_secret") if not credentials.get(key)]
    if missing:
        raise SystemExit(f"Missing Lark credentials: {', '.join(missing)}")
    client = lark_client(config, credentials)

    def on_message(event: P2ImMessageReceiveV1) -> None:
        config_for_error = load_config(config_path)
        message = getattr(getattr(event, "event", None), "message", None)
        text = ""
        sender = {}
        if message is not None:
            text = message_text(message)
            sender = sender_ids(event.event.sender)
        try:
            handle_message(client, event, config_path)
        except Exception as exc:
            try:
                if message is not None:
                    audit_event(message, sender, text, config_for_error, "error", f"{type(exc).__name__}: {exc}")
                message_id = str(getattr(message, "message_id", "") or "") if message is not None else ""
                if message_id and message is not None and should_reply(message, text, config_for_error):
                    send_text(client, message_id, f"处理失败：{type(exc).__name__}: {redact_secrets(str(exc))}")
            finally:
                print(f"lark message handling failed: {type(exc).__name__}: {redact_secrets(str(exc))}", flush=True)

    handler = (
        lark.EventDispatcherHandler.builder(credentials.get("encrypt_key", ""), credentials.get("verification_token", ""))
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    ws_client = lark.ws.Client(
        credentials["app_id"],
        credentials["app_secret"],
        log_level=lark.LogLevel.ERROR,
        event_handler=handler,
        domain=str(config.get("base_url") or lark.LARK_DOMAIN),
        auto_reconnect=True,
        source="zzlab-lab-big-brother",
    )
    print("实验室大师兄 Lark bot WebSocket started.", flush=True)
    ws_client.start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Lark interface for 实验室大师兄.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--app-secret-file", type=Path, default=DEFAULT_APP_SECRET_FILE)
    parser.add_argument("--encrypt-file", type=Path, default=DEFAULT_ENCRYPT_FILE)
    parser.add_argument("--check", action="store_true", help="Validate local config and credential presence without connecting.")
    parser.add_argument("--check-online", action="store_true", help="Validate Lark OpenAPI token and bot capability without starting the WebSocket loop.")
    args = parser.parse_args()

    if args.check:
        print(json.dumps(check_setup(args.config, args.app_secret_file, args.encrypt_file), ensure_ascii=False, indent=2))
        return
    if args.check_online:
        config = ensure_config_file(args.config)
        credentials = read_lark_credentials(args.app_secret_file, args.encrypt_file)
        result = check_setup(args.config, args.app_secret_file, args.encrypt_file)
        result.update(online_check(config, credentials))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    while True:
        try:
            run(args.config, args.app_secret_file, args.encrypt_file)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"Lark bot crashed: {type(exc).__name__}: {redact_secrets(str(exc))}", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
