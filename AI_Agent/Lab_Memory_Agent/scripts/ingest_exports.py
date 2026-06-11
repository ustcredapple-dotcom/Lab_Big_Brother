from __future__ import annotations

import argparse
import email
import hashlib
import html.parser
import re
import shutil
import sys
import textwrap
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "inbox"
SOURCES = ROOT / "sources" / "imported"
ENTRIES = ROOT / "entries"
CHUNK_CHARS = 5000


TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".log",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
}


class TextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        data = data.strip()
        if data:
            self.parts.append(data)

    def get_text(self) -> str:
        return "\n".join(self.parts)


def slugify(value: str, limit: int = 60) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    if not value:
        value = "imported-note"
    return value[:limit].strip("-")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 10000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not find unique path for {path}")


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def extract_html(path: Path) -> str:
    parser = TextExtractor()
    parser.feed(read_text_file(path))
    return parser.get_text()


def extract_mhtml(path: Path) -> str:
    message = email.message_from_bytes(path.read_bytes())
    candidates: list[str] = []
    for part in message.walk():
        content_type = part.get_content_type()
        if content_type not in {"text/html", "text/plain"}:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if content_type == "text/html":
            parser = TextExtractor()
            parser.feed(text)
            text = parser.get_text()
        candidates.append(text)
    return "\n\n".join(candidates)


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception as exc:
            raise RuntimeError("PDF extraction requires pypdf or PyPDF2") from exc
    reader = PdfReader(str(path))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[page {index}]\n{text.strip()}")
    return "\n\n".join(pages)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return read_text_file(path)
    if suffix in {".html", ".htm"}:
        return extract_html(path)
    if suffix in {".mht", ".mhtml"}:
        return extract_mhtml(path)
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    raise RuntimeError(f"unsupported file type: {path.suffix}")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []
    chunks = []
    while len(text) > size:
        split_at = text.rfind("\n\n", 0, size)
        if split_at < size // 2:
            split_at = text.rfind("\n", 0, size)
        if split_at < size // 2:
            split_at = size
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


def yaml_list(values: list[str]) -> str:
    if not values:
        return "[]"
    escaped = [value.replace("\\", "/").replace('"', '\\"') for value in values]
    return "[" + ", ".join(f'"{value}"' for value in escaped) + "]"


def write_entry(
    source_path: Path,
    original_name: str,
    source_hash: str,
    chunk: str,
    chunk_index: int,
    chunk_total: int,
) -> Path:
    today = date.today().isoformat()
    base_slug = slugify(Path(original_name).stem)
    entry_id = f"{today}-{base_slug}"
    if chunk_total > 1:
        entry_id = f"{entry_id}-part-{chunk_index:03d}"
    entry_path = unique_path(ENTRIES / f"{entry_id}.md")
    final_id = entry_path.stem
    preview = re.sub(r"\s+", " ", chunk).strip()[:180]
    source_ref = source_path.relative_to(ROOT).as_posix()
    title = Path(original_name).stem
    if chunk_total > 1:
        title = f"{title} part {chunk_index}/{chunk_total}"
    body = f"""---
id: {final_id}
title: "{title.replace('"', '\\"')}"
type: notebook_page
status: draft
date: {today}
projects: []
people: []
tags: ["onenote-export", "needs-review"]
source_refs: {yaml_list([source_ref])}
confidence: medium
source_hash: {source_hash}
chunk_index: {chunk_index}
chunk_total: {chunk_total}
summary: "{preview.replace('"', '\\"')}"
---

## Imported Source

- Original file: `{original_name}`
- Archived source: `{source_ref}`
- Chunk: {chunk_index} of {chunk_total}

## Extracted Text

{chunk}

## Review Notes

- This draft was generated from exported notebook material.
- Review and split it into stronger experiment, protocol, result, decision, or hypothesis entries when needed.
"""
    entry_path.write_text(body, encoding="utf-8", newline="\n")
    return entry_path


def ingest_file(path: Path, dry_run: bool = False) -> list[Path]:
    text = extract_text(path)
    chunks = chunk_text(text)
    if not chunks:
        raise RuntimeError("no text extracted")
    file_hash = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    source_name = f"{date.today().isoformat()}-{slugify(path.stem)}-{file_hash}{path.suffix.lower()}"
    archived_source = unique_path(SOURCES / source_name)
    if dry_run:
        print(f"would archive {path} -> {archived_source.relative_to(ROOT)}")
        print(f"would create {len(chunks)} entries")
        return []
    SOURCES.mkdir(parents=True, exist_ok=True)
    ENTRIES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, archived_source)
    written = []
    for index, chunk in enumerate(chunks, start=1):
        written.append(write_entry(archived_source, path.name, file_hash, chunk, index, len(chunks)))
    return written


def iter_inputs(paths: list[str]) -> list[Path]:
    if paths:
        items = [Path(item) for item in paths]
    else:
        items = [path for path in INBOX.iterdir() if path.is_file() and path.name != "README.md"]
    return sorted(items)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest exported OneNote materials into the memory pack.")
    parser.add_argument("paths", nargs="*", help="Files to ingest. Defaults to files in inbox/.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without writing files.")
    args = parser.parse_args()

    inputs = iter_inputs(args.paths)
    if not inputs:
        print("No files found. Put exports in inbox/ or pass file paths.")
        return

    failures = 0
    for path in inputs:
        try:
            written = ingest_file(path, dry_run=args.dry_run)
            if not args.dry_run:
                print(f"ingested {path.name}: {len(written)} entries")
        except Exception as exc:
            failures += 1
            print(f"failed {path}: {exc}", file=sys.stderr)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
