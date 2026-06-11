from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "indices" / "memory_index.jsonl"


def tokenize(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", text.lower()) if t]


def load_records() -> list[dict]:
    if not INDEX.exists():
        raise SystemExit("Index not found. Run scripts/rebuild_index.py first.")
    records = []
    for line in INDEX.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def score(record: dict, terms: list[str]) -> int:
    fields = [
        record.get("id", ""),
        record.get("title", ""),
        record.get("type", ""),
        record.get("status", ""),
        record.get("date", ""),
        " ".join(record.get("projects", [])),
        " ".join(record.get("people", [])),
        " ".join(record.get("tags", [])),
        record.get("summary", ""),
        record.get("body_text", ""),
    ]
    haystack = "\n".join(fields).lower()
    total = 0
    for term in terms:
        total += haystack.count(term)
        if term in str(record.get("tags", [])).lower():
            total += 3
        if term in record.get("title", "").lower():
            total += 5
    return total


def snippet(record: dict, max_len: int = 220) -> str:
    text = record.get("summary") or record.get("body_text", "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def main() -> None:
    query = " ".join(sys.argv[1:]).strip()
    if not query:
        raise SystemExit("Usage: python scripts/search_memory.py <query>")
    terms = tokenize(query)
    matches = []
    for record in load_records():
        points = score(record, terms)
        if points > 0:
            matches.append((points, record))
    matches.sort(key=lambda item: item[0], reverse=True)
    for points, record in matches[:10]:
        print(f"[{points}] {record.get('id')} | {record.get('title')} | {record.get('path')}")
        print(f"    {snippet(record)}")
        print(f"    sources: {', '.join(record.get('source_refs', []))}")


if __name__ == "__main__":
    main()
