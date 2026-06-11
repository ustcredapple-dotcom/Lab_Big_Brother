from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ROOT / "entries"
INDEX = ROOT / "indices" / "memory_index.jsonl"


def parse_scalar(value: str):
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("\"'") for item in inner.split(",")]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value.strip("\"'")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    meta = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = parse_scalar(value)
    return meta, body


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_record(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    body_text = normalize_text(re.sub(r"#+\s*", "", body))
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "id": meta.get("id", path.stem),
        "title": meta.get("title", path.stem),
        "type": meta.get("type", ""),
        "status": meta.get("status", ""),
        "date": meta.get("date", ""),
        "projects": meta.get("projects", []),
        "people": meta.get("people", []),
        "tags": meta.get("tags", []),
        "source_refs": meta.get("source_refs", []),
        "confidence": meta.get("confidence", ""),
        "summary": meta.get("summary", ""),
        "body_text": body_text,
    }


def main() -> None:
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    records = [build_record(path) for path in sorted(ENTRIES.glob("*.md"))]
    with INDEX.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"wrote {len(records)} records to {INDEX.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
