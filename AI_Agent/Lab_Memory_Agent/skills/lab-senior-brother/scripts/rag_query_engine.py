from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
PROCESSING = ZZLAB_ROOT / "Document/Lab_Notebook_Processing"
DEFAULT_DISTILLATION = PROCESSING / "html_deepseek_distilled/DEEPSEEK_DISTILLATION.json"
DEFAULT_HTML_ROOT = PROCESSING / "html/active/Lab_Notebook_Original_2026-06-11"
DEFAULT_INDEX_DIR = PROCESSING / "rag_chunk_index"
DEFAULT_LLM_KEY = ZZLAB_ROOT / "Key/Qwen Key.txt"
ANYTHINGLLM_KEY_CANDIDATES = (
    ZZLAB_ROOT / "Key/AnythingLLM API Key.txt",
    ZZLAB_ROOT / "Key/AnythingLLM Key.txt",
    ZZLAB_ROOT / "Key/anythingllm_api_key.txt",
)
DEFAULT_LLM_MODEL = "qwen3.7-plus"
DEFAULT_EMBEDDING_MODEL = "text-embedding-v4"
DEFAULT_EMBEDDING_DIMENSIONS = 512
PIPELINE_DIR = ZZLAB_ROOT / "AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline"
if str(PIPELINE_DIR) not in sys.path:
    sys.path.insert(0, str(PIPELINE_DIR))

import llm_provider  # noqa: E402


NOTEBOOK_UNKNOWN = "师兄我也不知道，notebook 里没找到明确记录。"
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".csv", ".tsv", ".json", ".yaml", ".yml", ".log", ".tex", ".xml"}
COMMUNICATION_FOLDERS = {
    "telegram": "telegram文件和聊天记录",
    "lark": "lark文档和消息记录",
    "email": "email文件和邮件记录",
}
TELEGRAM_MEMORY_KINDS = {"note", "file", "mode", "admin"}
LARK_MEMORY_KINDS = {"chat", "note", "file"}
SECRET_PATTERNS = (
    (re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b"), "<telegram-token-redacted>"),
    (re.compile(r"sk-[A-Za-z0-9_-]+"), "sk-<redacted>"),
    (re.compile(r"dashscope-[A-Za-z0-9_-]+"), "dashscope-<redacted>"),
    (re.compile(r"(?i)(password|passwd|api[_ -]?key|secret|token)\s*[:=]\s*\S+"), r"\1=<redacted>"),
    (re.compile(r"(?i)(password|passwd|api[_ -]?key|secret|token)\s+\S+"), r"\1 <redacted>"),
    (re.compile(r"(密码|口令|密钥|令牌|验证码|校验码)\s*[：:=]?\s*\S+"), r"\1<redacted>"),
)
LAB_HINTS = {
    "lab",
    "实验",
    "采购",
    "报价",
    "invoice",
    "quotation",
    "quote",
    "order",
    "shipment",
    "delivery",
    "laser",
    "cavity",
    "finesse",
    "finess",
    "vacuum",
    "dds",
    "artiq",
    "yb",
    "ion",
    "atom",
    "optical",
    "moku",
    "liquid instruments",
    "hku",
}
NOISE_HINTS = {
    "verification code",
    "login code",
    "security code",
    "one-time code",
    "验证码",
    "登录码",
    "安全码",
    "unsubscribe",
    "newsletter",
    "promotion",
    "广告",
    "营销",
}
CJK_STOP_CHARS = set("我们你您他她它这那哪的了是有在和与及或吗呢啊吧呀几多少什么怎么如何请问大师兄实验室")


@dataclass
class SourceDoc:
    source_id: str
    source_type: str
    section: str
    title: str
    path: str
    text: str
    date: str = ""
    author: str = ""
    metadata: dict[str, Any] | None = None


class PlainTextHTMLParser(html.parser.HTMLParser):
    block_tags = {"p", "div", "br", "tr", "table", "li", "h1", "h2", "h3", "h4", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "head", "noscript"}:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in self.block_tags:
            self.parts.append("\n")
        attributes = dict(attrs)
        if tag == "img" and (attributes.get("alt") or "").strip():
            self.parts.append(f"\n[image] {attributes.get('alt', '').strip()}\n")
        if tag in {"a", "embed"} and (attributes.get("href") or attributes.get("src") or "").strip():
            label = attributes.get("href") or attributes.get("src") or ""
            if tag == "embed":
                self.parts.append(f"\n[attachment] {label.strip()}\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "head", "noscript"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts).replace("\xa0", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def now_stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def redact_secrets(text: str) -> str:
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return value


def flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten(item) for item in value if item is not None)
    if isinstance(value, dict):
        return "\n".join(f"{key}: {flatten(item)}" for key, item in value.items() if item is not None)
    return str(value)


def compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def html_to_text(path: Path) -> str:
    parser = PlainTextHTMLParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.text()


def resolve_page_html(page: dict[str, Any], html_root: Path) -> Path:
    value = str(page.get("html", ""))
    path = Path(value)
    if path.is_absolute():
        return path
    return html_root / value


def distilled_text(page: dict[str, Any]) -> str:
    distilled = page.get("distilled", {})
    fields = [
        f"Section: {page.get('section', '')}",
        f"Title: {page.get('title', '')}",
        f"Summary: {distilled.get('one_sentence_summary', '')}",
        f"What happened:\n{flatten(distilled.get('what_happened', []))}",
        f"Important facts:\n{flatten(distilled.get('important_facts', []))}",
        f"Decisions or conclusions:\n{flatten(distilled.get('decisions_or_conclusions', []))}",
        f"Open questions or next steps:\n{flatten(distilled.get('open_questions_or_next_steps', []))}",
        f"People, organizations, equipment:\n{flatten(distilled.get('people_organizations_equipment', []))}",
        f"Tags: {flatten(distilled.get('tags', []))}",
        f"Attachments: {flatten(page.get('attachments', []))}",
    ]
    return redact_secrets("\n\n".join(field for field in fields if field.strip()))


def iter_distillation_sources(distillation_path: Path, html_root: Path) -> Iterable[SourceDoc]:
    data = read_json(distillation_path, {"sections": []})
    for section in data.get("sections", []):
        section_name = str(section.get("section", ""))
        for page in section.get("pages", []):
            page = dict(page)
            page.setdefault("section", section_name)
            title = str(page.get("title", "") or "Untitled")
            html_path = resolve_page_html(page, html_root)
            base_id = f"{section_name}/{title}/{page.get('source_sha256') or page.get('html')}"
            yield SourceDoc(
                source_id=f"distilled:{sha256_text(base_id)[:16]}",
                source_type="distilled_page",
                section=section_name,
                title=title,
                path=str(html_path),
                date=str(page.get("updated") or page.get("created") or ""),
                metadata={
                    "source_sha256": page.get("source_sha256", ""),
                    "attachments": page.get("attachments", []),
                    "distilled": page.get("distilled", {}),
                },
                text=distilled_text(page),
            )
            if html_path.is_file():
                try:
                    text = html_to_text(html_path)
                except Exception as exc:
                    text = f"[HTML text extraction failed: {type(exc).__name__}: {exc}]"
                if text.strip():
                    yield SourceDoc(
                        source_id=f"html:{sha256_text(str(html_path))[:16]}",
                        source_type="source_html",
                        section=section_name,
                        title=title,
                        path=str(html_path),
                        date=str(page.get("updated") or page.get("created") or ""),
                        metadata={"source_sha256": page.get("source_sha256", ""), "attachments": page.get("attachments", [])},
                        text=redact_secrets(text),
                    )


def text_file_extract(path_value: str, limit: int = 80000) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file():
        return ""
    if path.suffix.casefold() not in TEXT_EXTENSIONS and not path.name.endswith(".qwen_vision.json"):
        return ""
    return redact_secrets(path.read_text(encoding="utf-8", errors="replace")[:limit])


def record_file_summary(files: list[dict[str, Any]]) -> str:
    lines = []
    for item in files:
        fields = [
            f"file_name={item.get('file_name') or item.get('filename') or Path(str(item.get('path', ''))).name}",
            f"mime_type={item.get('mime_type', '')}",
            f"classification={item.get('classification', '')}",
            f"path={item.get('path', '')}",
            f"text_preview={item.get('text_preview', '')}",
        ]
        lines.append("; ".join(field for field in fields if not field.endswith("=")))
    return "\n".join(lines)


def has_lab_hint(text: str) -> bool:
    lowered = text.casefold()
    return any(hint in lowered for hint in LAB_HINTS)


def is_noise_record(text: str) -> bool:
    lowered = text.casefold()
    if has_lab_hint(lowered):
        return False
    return any(hint in lowered for hint in NOISE_HINTS)


def iter_chat_sources(root: Path) -> Iterable[SourceDoc]:
    for day_dir in sorted(root.glob("20??-??-??")):
        if not day_dir.is_dir():
            continue
        day = day_dir.name
        for source_type, folder_name in (("telegram", COMMUNICATION_FOLDERS["telegram"]), ("lark", COMMUNICATION_FOLDERS["lark"])):
            folder = day_dir / folder_name
            if not folder.exists():
                continue
            for jsonl_path in sorted(folder.glob("*/chat_records.jsonl")):
                person = jsonl_path.parent.name
                for index, record in enumerate(read_jsonl(jsonl_path), start=1):
                    kind = str(record.get("kind", ""))
                    if source_type == "telegram" and kind not in TELEGRAM_MEMORY_KINDS:
                        continue
                    if source_type == "lark" and kind not in LARK_MEMORY_KINDS:
                        continue
                    files = record.get("files") or []
                    text = "\n".join(
                        [
                            f"Source: {source_type}",
                            f"Date: {record.get('created_at') or day}",
                            f"Person: {person}",
                            f"Kind: {kind}",
                            f"Text:\n{record.get('text', '')}",
                            f"Files:\n{record_file_summary(files)}",
                        ]
                    )
                    if is_noise_record(text):
                        continue
                    source_id = f"{source_type}:{sha256_text(str(jsonl_path) + str(record.get('message_id')) + str(index))[:18]}"
                    yield SourceDoc(
                        source_id=source_id,
                        source_type=source_type,
                        section="Communication Records",
                        title=f"{source_type.title()} {day} {person}",
                        path=str(jsonl_path),
                        date=str(record.get("created_at") or day),
                        author=person,
                        metadata={"kind": kind, "message_id": record.get("message_id"), "files": files},
                        text=redact_secrets(text),
                    )
                    for file_index, item in enumerate(files):
                        extract = text_file_extract(str(item.get("text_extract", "")))
                        if not extract.strip():
                            continue
                        file_path = str(item.get("path", "") or item.get("text_extract", ""))
                        yield SourceDoc(
                            source_id=f"{source_type}-file:{sha256_text(file_path + str(file_index))[:18]}",
                            source_type=f"{source_type}_file_text",
                            section="Communication Attachments",
                            title=str(item.get("file_name") or Path(file_path).name),
                            path=file_path,
                            date=str(record.get("created_at") or day),
                            author=person,
                            metadata={"parent_record": str(jsonl_path), "mime_type": item.get("mime_type", "")},
                            text=extract,
                        )


def iter_email_sources(root: Path) -> Iterable[SourceDoc]:
    for day_dir in sorted(root.glob("20??-??-??")):
        folder = day_dir / COMMUNICATION_FOLDERS["email"]
        if not folder.exists():
            continue
        day = day_dir.name
        for jsonl_path in sorted(folder.glob("*/email_records.jsonl")):
            sender = jsonl_path.parent.name
            for index, record in enumerate(read_jsonl(jsonl_path), start=1):
                attachments = record.get("attachments") or []
                body_text = text_file_extract(str(record.get("body_text", "")), limit=60000)
                text = "\n".join(
                    [
                        "Source: email",
                        f"Date: {record.get('date') or day}",
                        f"From: {record.get('from') or sender}",
                        f"Subject: {record.get('subject') or '(no subject)'}",
                        f"Preview:\n{record.get('text_preview', '')}",
                        f"Body:\n{body_text}",
                        f"Attachments:\n{record_file_summary(attachments)}",
                    ]
                )
                if is_noise_record(text):
                    continue
                yield SourceDoc(
                    source_id=f"email:{sha256_text(str(jsonl_path) + str(record.get('message_id')) + str(index))[:18]}",
                    source_type="email",
                    section="Communication Records",
                    title=str(record.get("subject") or f"Email {day} {sender}"),
                    path=str(jsonl_path),
                    date=str(record.get("date") or day),
                    author=str(record.get("from") or sender),
                    metadata={"attachments": attachments, "html_preview": record.get("html_preview", "")},
                    text=redact_secrets(text),
                )
                for file_index, item in enumerate(attachments):
                    extract = text_file_extract(str(item.get("text_extract", "")))
                    if not extract.strip():
                        continue
                    file_path = str(item.get("path", "") or item.get("text_extract", ""))
                    yield SourceDoc(
                        source_id=f"email-file:{sha256_text(file_path + str(file_index))[:18]}",
                        source_type="email_file_text",
                        section="Communication Attachments",
                        title=str(item.get("filename") or Path(file_path).name),
                        path=file_path,
                        date=str(record.get("date") or day),
                        author=str(record.get("from") or sender),
                        metadata={"parent_record": str(jsonl_path), "mime_type": item.get("mime_type", "")},
                        text=extract,
                    )


def collect_sources(distillation_path: Path, html_root: Path, root: Path = ZZLAB_ROOT) -> list[SourceDoc]:
    sources = list(iter_distillation_sources(distillation_path, html_root))
    sources.extend(iter_chat_sources(root))
    sources.extend(iter_email_sources(root))
    return [source for source in sources if compact_whitespace(source.text)]


def paragraph_chunks(text: str, max_chars: int = 1800, overlap_chars: int = 220) -> list[str]:
    clean = re.sub(r"\r\n?", "\n", text)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", clean) if part.strip()]
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > max_chars:
            head = paragraph[:max_chars].strip()
            pieces.append(head)
            paragraph = paragraph[max_chars - overlap_chars :].strip()
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
        tail = current[-overlap_chars:] if current and overlap_chars else ""
        current = f"{tail}\n\n{paragraph}".strip() if tail else paragraph
    if current:
        pieces.append(current)
    return pieces


def chunk_sources(sources: list[SourceDoc]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for source in sources:
        source_hash = sha256_text(source.text)
        for index, text in enumerate(paragraph_chunks(source.text), start=1):
            text = redact_secrets(text.strip())
            if len(compact_whitespace(text)) < 30:
                continue
            text_hash = sha256_text(text)
            chunk_id = f"chunk-{sha256_text(f'{source.source_id}:{index}:{text_hash}')[:20]}"
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "chunk_index": index,
                    "source_id": source.source_id,
                    "source_type": source.source_type,
                    "section": source.section,
                    "title": source.title,
                    "path": source.path,
                    "date": source.date,
                    "author": source.author,
                    "source_hash": source_hash,
                    "text_hash": text_hash,
                    "text": text,
                    "metadata": redact_value(source.metadata or {}),
                }
            )
    return chunks


def index_paths(index_dir: Path) -> tuple[Path, Path]:
    return index_dir / "chunks.jsonl", index_dir / "manifest.json"


def load_existing_vectors(index_dir: Path, embedding_model: str, dimensions: int | None) -> dict[str, list[float]]:
    chunks_path, manifest_path = index_paths(index_dir)
    if not chunks_path.exists() or not manifest_path.exists():
        return {}
    manifest = read_json(manifest_path, {})
    if manifest.get("embedding_model") != embedding_model:
        return {}
    if manifest.get("embedding_dimensions") != dimensions:
        return {}
    vectors: dict[str, list[float]] = {}
    for chunk in read_jsonl(chunks_path):
        vector = chunk.get("vector")
        text_hash = chunk.get("text_hash")
        if text_hash and isinstance(vector, list):
            vectors[text_hash] = vector
    return vectors


def embedding_input(chunk: dict[str, Any]) -> str:
    header = "\n".join(
        [
            f"Section: {chunk.get('section', '')}",
            f"Title: {chunk.get('title', '')}",
            f"Source type: {chunk.get('source_type', '')}",
            f"Date: {chunk.get('date', '')}",
        ]
    )
    return f"{header}\n\n{chunk.get('text', '')}"[:6000]


def build_index(
    *,
    index_dir: Path = DEFAULT_INDEX_DIR,
    distillation_path: Path = DEFAULT_DISTILLATION,
    html_root: Path = DEFAULT_HTML_ROOT,
    root: Path = ZZLAB_ROOT,
    key_file: Path = DEFAULT_LLM_KEY,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dimensions: int | None = DEFAULT_EMBEDDING_DIMENSIONS,
    no_embeddings: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    started = time.time()
    sources = collect_sources(distillation_path, html_root, root)
    chunks = chunk_sources(sources)
    old_vectors = {} if force else load_existing_vectors(index_dir, embedding_model, embedding_dimensions)
    reused_vectors = 0
    for chunk in chunks:
        vector = old_vectors.get(chunk["text_hash"])
        if vector:
            chunk["vector"] = vector
            reused_vectors += 1

    embedded_chunks = 0
    embedding_error = ""
    usage_records: list[dict[str, Any]] = []
    actual_embedding_model = embedding_model
    missing = [chunk for chunk in chunks if not chunk.get("vector")]
    if missing and not no_embeddings:
        try:
            key = llm_provider.read_api_key(key_file)
            vectors, usage_records, actual_embedding_model = llm_provider.call_embeddings_batched(
                key=key,
                texts=[embedding_input(chunk) for chunk in missing],
                model=embedding_model,
                dimensions=embedding_dimensions,
                batch_size=10,
                timeout=120,
                retries=2,
                provider="qwen",
            )
            for chunk, vector in zip(missing, vectors):
                chunk["vector"] = [round(float(value), 6) for value in vector]
                embedded_chunks += 1
        except Exception as exc:
            embedding_error = f"{type(exc).__name__}: {exc}"

    chunks_path, manifest_path = index_paths(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    temporary_chunks = chunks_path.with_name(f".{chunks_path.name}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    try:
        with temporary_chunks.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")) + "\n")
        temporary_chunks.replace(chunks_path)
    finally:
        if temporary_chunks.exists():
            temporary_chunks.unlink()
    manifest = {
        "generated_at": now_stamp(),
        "engine": "chunk_hybrid_qwen_rag",
        "source_root": str(root),
        "distillation": str(distillation_path),
        "html_root": str(html_root),
        "source_count": len(sources),
        "chunk_count": len(chunks),
        "chunks_with_vectors": sum(1 for chunk in chunks if chunk.get("vector")),
        "reused_vectors": reused_vectors,
        "embedded_chunks": embedded_chunks,
        "embedding_model": actual_embedding_model,
        "embedding_dimensions": embedding_dimensions,
        "embedding_error": embedding_error,
        "embedding_usage": usage_records,
        "duration_seconds": round(time.time() - started, 2),
    }
    write_json(manifest_path, manifest)
    return manifest


def load_index(index_dir: Path = DEFAULT_INDEX_DIR) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    chunks_path, manifest_path = index_paths(index_dir)
    if not chunks_path.exists() or not manifest_path.exists():
        manifest = build_index(index_dir=index_dir)
    else:
        manifest = read_json(manifest_path, {})
    chunks = list(read_jsonl(chunks_path))
    return chunks, manifest


def ensure_index(index_dir: Path = DEFAULT_INDEX_DIR) -> dict[str, Any]:
    chunks_path, manifest_path = index_paths(index_dir)
    if chunks_path.exists() and manifest_path.exists():
        return read_json(manifest_path, {})
    return build_index(index_dir=index_dir)


def refresh_index_quietly(**kwargs: Any) -> dict[str, Any]:
    try:
        return build_index(**kwargs)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def cjk_ngrams(text: str) -> list[str]:
    chars = [char for char in re.findall(r"[\u3400-\u9fff]", text) if char not in CJK_STOP_CHARS]
    grams: list[str] = []
    for size in (2, 3, 4):
        grams.extend("".join(chars[index : index + size]) for index in range(max(0, len(chars) - size + 1)))
    return grams


def query_aliases(question: str) -> list[str]:
    lowered = question.casefold()
    aliases = []
    if "finess" in lowered or "finesse" in lowered or "精细" in question or "细度" in question:
        aliases.append("finesse finess 精细度 optical cavity cavity mirror FSR linewidth free spectral range")
    if "cavity" in lowered or "腔" in question:
        aliases.append("optical cavity in-vacuum cavity out-of-vacuum cavity 稳频腔 腔镜")
    if "真空" in question and ("烤" in question or "bake" in lowered):
        aliases.append("真空烘烤 真空烤 bakeout baking heating tape 加热带")
    if "dds" in lowered:
        aliases.append("DDS ARTIQ Urukul 测试 验收 频率 功率 RF")
    if "电脑" in question or "计算机" in question or "computer" in lowered:
        aliases.append("computer lab computers workstation mini PC 电脑 计算机")
    if "邮件" in question or "email" in lowered:
        aliases.append("email Gmail forwarded mail attachment")
    if "lark" in lowered or "飞书" in question:
        aliases.append("Lark 飞书 group chat message")
    return aliases


def query_terms(question: str) -> list[str]:
    expanded = " ".join([question, *query_aliases(question)])
    terms = [term.casefold() for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.+-]{1,}", expanded)]
    terms.extend(cjk_ngrams(expanded))
    unique = []
    seen = set()
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            unique.append(term)
    return unique


def lexical_score(question: str, terms: list[str], chunk: dict[str, Any]) -> float:
    text = "\n".join(
        [
            str(chunk.get("section", "")),
            str(chunk.get("title", "")),
            str(chunk.get("source_type", "")),
            str(chunk.get("date", "")),
            str(chunk.get("author", "")),
            str(chunk.get("text", "")),
            flatten(chunk.get("metadata", {})),
        ]
    )
    lowered = text.casefold()
    score = 0.0
    phrase = question.casefold().strip()
    if len(phrase) >= 3 and phrase in lowered:
        score += 12.0
    for alias in query_aliases(question):
        alias_lower = alias.casefold()
        if alias_lower in lowered:
            score += 6.0
    title_lower = str(chunk.get("title", "")).casefold()
    section_lower = str(chunk.get("section", "")).casefold()
    for term in terms:
        count = lowered.count(term)
        if not count:
            continue
        if re.fullmatch(r"[\u3400-\u9fff]+", term):
            weight = 0.45 + 0.25 * min(len(term), 4)
        else:
            weight = 1.6 if len(term) <= 3 else 2.2
        score += weight * min(4, count)
        if term in title_lower:
            score += 4.0
        if term in section_lower:
            score += 2.0
    return score


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_query(question: str, manifest: dict[str, Any], key_file: Path = DEFAULT_LLM_KEY) -> list[float]:
    key = llm_provider.read_api_key(key_file)
    model = str(manifest.get("embedding_model") or DEFAULT_EMBEDDING_MODEL)
    dimensions = manifest.get("embedding_dimensions", DEFAULT_EMBEDDING_DIMENSIONS)
    text = "\n".join([question, *query_aliases(question)])
    vectors, _usage, _model = llm_provider.call_embeddings(
        key=key,
        texts=[text[:6000]],
        model=model,
        dimensions=int(dimensions) if dimensions else None,
        timeout=90,
        retries=2,
        provider="qwen",
    )
    return vectors[0] if vectors else []


def retrieve_candidates(
    question: str,
    chunks: list[dict[str, Any]],
    manifest: dict[str, Any],
    top_k: int = 40,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    terms = query_terms(question)
    query_vector: list[float] = []
    semantic_error = ""
    if manifest.get("chunks_with_vectors", 0):
        try:
            query_vector = embed_query(question, manifest)
        except Exception as exc:
            semantic_error = f"{type(exc).__name__}: {exc}"
    scored = []
    for chunk in chunks:
        lex = lexical_score(question, terms, chunk)
        sem = cosine_similarity(query_vector, chunk.get("vector", [])) if query_vector and chunk.get("vector") else 0.0
        lex_norm = lex / (lex + 10.0) if lex > 0 else 0.0
        sem_norm = max(0.0, sem)
        final = 0.68 * sem_norm + 0.32 * lex_norm if query_vector else lex_norm
        if final <= 0 and lex <= 0:
            continue
        item = dict(chunk)
        item["_lexical_score"] = round(lex, 4)
        item["_semantic_score"] = round(sem, 6)
        item["_score"] = round(final, 6)
        scored.append(item)
    scored.sort(key=lambda item: (item["_score"], item["_lexical_score"], item.get("date", "")), reverse=True)
    return scored[:top_k], {"semantic_error": semantic_error, "terms": terms[:80], "query_has_vector": bool(query_vector)}


def snippet(text: str, terms: list[str], length: int = 900) -> str:
    compact = compact_whitespace(text)
    lowered = compact.casefold()
    positions = [lowered.find(term.casefold()) for term in terms if term and lowered.find(term.casefold()) >= 0]
    if not positions:
        return compact[:length]
    center = min(positions)
    start = max(0, center - length // 3)
    end = min(len(compact), start + length)
    return compact[start:end]


def compact_candidate(chunk: dict[str, Any], terms: list[str]) -> dict[str, Any]:
    return {
        "chunk_id": chunk.get("chunk_id"),
        "score": chunk.get("_score"),
        "semantic_score": chunk.get("_semantic_score"),
        "lexical_score": chunk.get("_lexical_score"),
        "source_type": chunk.get("source_type"),
        "section": chunk.get("section"),
        "title": chunk.get("title"),
        "date": chunk.get("date"),
        "author": chunk.get("author"),
        "path": chunk.get("path"),
        "snippet": snippet(str(chunk.get("text", "")), terms, 1000),
    }


def llm_json(messages: list[dict[str, Any]], config: dict[str, Any], timeout_extra: int = 60) -> tuple[dict[str, Any], dict[str, Any]]:
    model = str(config.get("llm_model") or DEFAULT_LLM_MODEL)
    timeout = int(config.get("query_timeout_seconds", 60)) + timeout_extra
    data, usage, _actual_model = llm_provider.call_json(
        key=llm_provider.read_api_key(DEFAULT_LLM_KEY),
        model=model,
        messages=messages,
        timeout=timeout,
        retries=2,
        provider=llm_provider.infer_provider(model, DEFAULT_LLM_KEY),
    )
    return data, usage


def rerank_with_qwen(question: str, candidates: list[dict[str, Any]], terms: list[str], config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    compact = [compact_candidate(item, terms) for item in candidates[:24]]
    messages = [
        {
            "role": "system",
            "content": (
                "你是 ZZLab 实验室记忆的 RAG reranker。"
                "只根据候选证据块判断是否能直接回答用户问题。"
                "注意同义词、拼写误差和中英混用，例如 finess 应理解为 finesse，烤真空应理解为真空烘烤。"
                "不要因为泛词相似就强行选证据；电脑、电气、温控、光学平台不是同一件事。"
                "如果没有直接证据，has_answer=false 且 selected_chunk_ids 为空。"
                "不要输出密钥、密码、token 或验证码。只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "max_selected": max(1, min(int(config.get("default_top_k", 5)), 8)),
                    "output_schema": {
                        "has_answer": "boolean",
                        "selected_chunk_ids": ["chunk id strings"],
                        "reason": "brief Chinese reason",
                    },
                    "candidate_chunks": compact,
                },
                ensure_ascii=False,
            ),
        },
    ]
    return llm_json(messages, config, timeout_extra=80)


def answer_with_qwen(question: str, evidence: list[dict[str, Any]], config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    compact = []
    for item in evidence[:8]:
        compact.append(
            {
                "chunk_id": item.get("chunk_id"),
                "source_type": item.get("source_type"),
                "section": item.get("section"),
                "title": item.get("title"),
                "date": item.get("date"),
                "author": item.get("author"),
                "path": item.get("path"),
                "text": str(item.get("text", ""))[:2200],
            }
        )
    messages = [
        {
            "role": "system",
            "content": (
                "你是“实验室大师兄”。用 Telegram/Lark 适合的短回复回答，中文，自然，别写“结论/置信度/score”。"
                "必须忠于证据；证据无法直接回答时，reply 必须是：师兄我也不知道，notebook 里没找到明确记录。"
                "有证据时给够信息，不要只回一句；通常 4 到 8 行，先直接回答，再给关键做法/数量/参数。"
                "如果用户问怎么做、怎么测、为什么、证据在哪，要按步骤或要点说清楚。"
                "可以说“我看到的记录里...”，但不要机械列标签。"
                "不要输出密码、token、密钥、验证码、个人登录信息。只输出 JSON。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "output_schema": {
                        "has_answer": "boolean",
                        "reply": "short natural Chinese reply",
                        "used_chunk_ids": ["chunk id strings"],
                    },
                    "evidence_chunks": compact,
                },
                ensure_ascii=False,
            ),
        },
    ]
    return llm_json(messages, config, timeout_extra=100)


def evidence_record(chunk: dict[str, Any]) -> dict[str, Any]:
    text = redact_secrets(str(chunk.get("text", "")))
    metadata = chunk.get("metadata") or {}
    distilled = metadata.get("distilled") if isinstance(metadata, dict) else {}
    if not isinstance(distilled, dict):
        distilled = {}
    facts = redact_value(distilled.get("important_facts") or [compact_whitespace(text)[:1200]])
    return {
        "id": chunk.get("chunk_id"),
        "score": float(chunk.get("_score") or 0),
        "semantic_score": float(chunk.get("_semantic_score") or 0),
        "lexical_score": float(chunk.get("_lexical_score") or 0),
        "source_type": chunk.get("source_type", ""),
        "section": chunk.get("section", ""),
        "title": chunk.get("title", ""),
        "html": chunk.get("path", ""),
        "source_sha256": metadata.get("source_sha256", "") if isinstance(metadata, dict) else "",
        "summary": redact_secrets(str(distilled.get("one_sentence_summary", ""))) if distilled else compact_whitespace(text)[:260],
        "what_happened": redact_value(distilled.get("what_happened", [])) if distilled else [],
        "important_facts": facts if isinstance(facts, list) else [facts],
        "decisions_or_conclusions": redact_value(distilled.get("decisions_or_conclusions", [])) if distilled else [],
        "open_questions_or_next_steps": redact_value(distilled.get("open_questions_or_next_steps", [])) if distilled else [],
        "people_organizations_equipment": redact_value(distilled.get("people_organizations_equipment", [])) if distilled else [],
        "tags": redact_value(distilled.get("tags", [])) if distilled else [chunk.get("source_type", "")],
        "attachments": metadata.get("attachments", []) if isinstance(metadata, dict) else [],
        "source_snippet": compact_whitespace(text)[:1400],
        "date": chunk.get("date", ""),
        "author": chunk.get("author", ""),
    }


def read_secret_value(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def anythingllm_api_key(config: dict[str, Any]) -> str:
    key = str(config.get("anythingllm_api_key") or os.environ.get("ANYTHINGLLM_API_KEY") or "").strip()
    if key:
        return key
    path_value = str(config.get("anythingllm_api_key_path") or "").strip()
    if path_value:
        key = read_secret_value(Path(path_value).expanduser())
        if key:
            return key
    for candidate in ANYTHINGLLM_KEY_CANDIDATES:
        key = read_secret_value(candidate)
        if key:
            return key
    return ""


def anythingllm_base_url(config: dict[str, Any]) -> str:
    raw = str(config.get("anythingllm_base_url") or os.environ.get("ANYTHINGLLM_BASE_URL") or "http://127.0.0.1:3001/api")
    return raw.rstrip("/")


def anythingllm_evidence(source: dict[str, Any], index: int) -> dict[str, Any]:
    title = str(source.get("title") or source.get("name") or source.get("chunkSource") or f"AnythingLLM source {index}")
    snippet = compact_whitespace(str(source.get("chunk") or source.get("text") or source.get("pageContent") or source.get("content") or ""))
    source_url = str(source.get("url") or source.get("docpath") or source.get("location") or source.get("source") or "")
    return {
        "chunk_id": str(source.get("id") or source.get("uuid") or index),
        "score": float(source.get("score") or source.get("similarity") or 0),
        "source_type": "anythingllm",
        "section": title,
        "title": title,
        "html": source_url,
        "source_sha256": "",
        "summary": snippet[:260],
        "what_happened": [],
        "important_facts": [],
        "decisions_or_conclusions": [],
        "open_questions_or_next_steps": [],
        "people_organizations_equipment": [],
        "tags": ["anythingllm"],
        "attachments": [],
        "source_snippet": snippet[:1400],
        "date": "",
        "author": "",
    }


def query_anythingllm(question: str, config: dict[str, Any]) -> dict[str, Any]:
    slug = str(config.get("anythingllm_workspace_slug") or os.environ.get("ANYTHINGLLM_WORKSPACE_SLUG") or "").strip()
    if not slug:
        return {"error": "AnythingLLM 未配置 workspace slug：请设置 anythingllm_workspace_slug 或 ANYTHINGLLM_WORKSPACE_SLUG。"}
    key = anythingllm_api_key(config)
    if not key:
        return {"error": "AnythingLLM 未配置 API key：请设置 anythingllm_api_key、ANYTHINGLLM_API_KEY 或 Key/AnythingLLM API Key.txt。"}
    mode = str(config.get("anythingllm_mode") or "query").strip() or "query"
    payload = {
        "message": question,
        "mode": mode,
        "sessionId": str(config.get("anythingllm_session_id") or "zzlab-big-brother"),
    }
    url = f"{anythingllm_base_url(config)}/v1/workspace/{urllib.parse.quote(slug)}/chat"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=int(config.get("query_timeout_seconds", 60)) + 15) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        return {"error": f"AnythingLLM 查询失败：HTTP {exc.code}: {body}"}
    except Exception as exc:
        return {"error": f"AnythingLLM 查询失败：{type(exc).__name__}: {exc}"}
    answer = str(data.get("textResponse") or data.get("text") or data.get("response") or data.get("message") or "").strip()
    sources = data.get("sources") if isinstance(data.get("sources"), list) else []
    evidence = [anythingllm_evidence(source, index) for index, source in enumerate(sources, start=1) if isinstance(source, dict)]
    if not answer or (mode == "query" and not evidence):
        answer = NOTEBOOK_UNKNOWN
        evidence = []
    return {
        "query": question,
        "engine": "anythingllm_api",
        "likely_done_before": "yes" if evidence else "unknown",
        "confidence": "anythingllm" if evidence else "low",
        "top_score": evidence[0]["score"] if evidence else 0,
        "evidence_count": len(evidence),
        "evidence": evidence,
        "answer": answer,
        "anythingllm": {
            "base_url": anythingllm_base_url(config),
            "workspace_slug": slug,
            "mode": mode,
            "type": data.get("type", ""),
        },
    }


def query_notebook(question: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    if str(config.get("rag_engine", "chunk")).casefold() == "anythingllm":
        return query_anythingllm(question, config)
    try:
        index_dir = Path(config.get("rag_index_dir") or DEFAULT_INDEX_DIR)
        chunks, manifest = load_index(index_dir)
        top_k = max(10, int(config.get("rag_candidate_k", 40)))
        candidates, retrieval_meta = retrieve_candidates(question, chunks, manifest, top_k=top_k)
        if not candidates:
            return {
                "query": question,
                "engine": "chunk_hybrid_qwen_rag",
                "likely_done_before": "unknown",
                "confidence": "low",
                "top_score": 0,
                "evidence_count": 0,
                "evidence": [],
                "answer": NOTEBOOK_UNKNOWN,
                "retrieval": retrieval_meta,
                "index_manifest": manifest,
            }
        rerank, rerank_usage = rerank_with_qwen(question, candidates, retrieval_meta.get("terms", []), config)
        selected_ids = [str(item) for item in rerank.get("selected_chunk_ids") or []]
        selected = [item for item in candidates if str(item.get("chunk_id")) in selected_ids]
        if not rerank.get("has_answer") or not selected:
            return {
                "query": question,
                "engine": "chunk_hybrid_qwen_rag",
                "likely_done_before": "unknown",
                "confidence": "low",
                "top_score": candidates[0].get("_score", 0),
                "evidence_count": 0,
                "evidence": [],
                "answer": NOTEBOOK_UNKNOWN,
                "llm_selection": rerank,
                "retrieval": retrieval_meta,
                "usage": {"rerank": rerank_usage},
                "index_manifest": manifest,
            }
        answer_data, answer_usage = answer_with_qwen(question, selected, config)
        has_answer = bool(answer_data.get("has_answer"))
        reply = str(answer_data.get("reply") or "").strip()
        if not has_answer or not reply:
            reply = NOTEBOOK_UNKNOWN
            selected = []
        evidence = [evidence_record(item) for item in selected]
        return {
            "query": question,
            "engine": "chunk_hybrid_qwen_rag",
            "likely_done_before": "yes" if selected else "unknown",
            "confidence": "llm" if selected else "low",
            "top_score": evidence[0]["score"] if evidence else 0,
            "evidence_count": len(evidence),
            "evidence": evidence,
            "answer": reply,
            "llm_selection": rerank,
            "retrieval": retrieval_meta,
            "usage": {"rerank": rerank_usage, "answer": answer_usage},
            "index_manifest": manifest,
        }
    except Exception as exc:
        return {"error": f"Chunk RAG 查询失败：{type(exc).__name__}: {exc}"}


def render_text(result: dict[str, Any]) -> str:
    lines = [
        f"Query: {result.get('query', '')}",
        f"Engine: {result.get('engine', 'unknown')}",
        f"Likely done before: {result.get('likely_done_before', 'unknown')}",
    ]
    if result.get("answer"):
        lines.extend(["", "Answer:", str(result["answer"])])
    lines.extend(["", "Evidence:"])
    for index, item in enumerate(result.get("evidence", []), start=1):
        lines.extend(
            [
                f"{index}. {item.get('section', '')} / {item.get('title', '')} (score {float(item.get('score', 0)):.3f})",
                f"   Source: {item.get('html', '')}",
                f"   Snippet: {item.get('source_snippet', '')[:500]}",
                "",
            ]
        )
    if result.get("error"):
        lines.extend(["", str(result["error"])])
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and query the ZZLab chunk-level hybrid RAG index.")
    parser.add_argument("query", nargs="*", help="Question to ask. Omit when using --build-index.")
    parser.add_argument("--build-index", action="store_true")
    parser.add_argument("--force", action="store_true", help="Do not reuse existing vectors.")
    parser.add_argument("--no-embeddings", action="store_true")
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    parser.add_argument("--distillation", type=Path, default=DEFAULT_DISTILLATION)
    parser.add_argument("--html-root", type=Path, default=DEFAULT_HTML_ROOT)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    if args.build_index:
        result = build_index(
            index_dir=args.index_dir,
            distillation_path=args.distillation,
            html_root=args.html_root,
            no_embeddings=args.no_embeddings,
            force=args.force,
        )
    else:
        question = " ".join(args.query).strip()
        if not question:
            raise SystemExit("Provide a query or use --build-index.")
        result = query_notebook(question, {"rag_index_dir": str(args.index_dir)})
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result), end="")


if __name__ == "__main__":
    main()
