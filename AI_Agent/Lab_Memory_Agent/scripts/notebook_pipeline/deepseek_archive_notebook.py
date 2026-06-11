from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


FOLDERS = {
    "01_Experimental_Protocols": "Experimental procedures, apparatus tests, measurements, and operating records",
    "02_Equipment_and_Purchasing": "Equipment selection, quotations, purchasing, vendors, and budgets",
    "03_Software_and_Control": "Software, ARTIQ, control systems, code, and computing infrastructure",
    "04_Lab_Operations": "Accounts, renovation, safety, facilities, and routine lab administration",
    "05_Theory_and_Analysis": "Theory, calculations, design analysis, and scientific references",
    "06_Meetings_and_Records": "Meeting notes, journal clubs, decisions, and chronological records",
    "99_Uncategorized": "Material that cannot be classified confidently",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_key(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"DeepSeek key file not found: {path}")
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit(f"DeepSeek key file is empty: {path}")
    return key


def request_chat(base_url: str, key: str, model: str, messages: list[dict], timeout: int = 300) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API failed: HTTP {exc.code}: {detail}") from exc
    content = data["choices"][0]["message"]["content"]
    return {"result": json.loads(content), "usage": data.get("usage", {}), "model": data.get("model", model)}


def chunks(text: str, size: int) -> list[str]:
    if len(text) <= size:
        return [text]
    parts = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            split = text.rfind("\n", start, end)
            if split > start + size // 2:
                end = split
        parts.append(text[start:end])
        start = end
    return parts


def note_chunks(base_url: str, key: str, model: str, source_name: str, parts: list[str]) -> tuple[list[dict], list[dict]]:
    notes = []
    usage = []
    system = (
        "Extract grounded notes from laboratory Markdown. Return a JSON object. "
        "Do not invent facts. Preserve names, quantities, dates, decisions, problems, and source page markers."
    )
    for index, part in enumerate(parts, start=1):
        prompt = f"""
Return JSON with keys summary, topics, important_facts, dates_and_decisions,
people_organizations_equipment, source_markers, and uncertainties.

Source file: {source_name}
Chunk: {index}/{len(parts)}

MARKDOWN:
{part}
"""
        response = request_chat(
            base_url,
            key,
            model,
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        notes.append(response["result"])
        usage.append(response["usage"])
    return notes, usage


def classify(base_url: str, key: str, model: str, source_name: str, notes: list[dict]) -> dict:
    taxonomy = "\n".join(f"- {name}: {description}" for name, description in FOLDERS.items())
    prompt = f"""
Classify a laboratory notebook document using only the extraction notes below.
Return one JSON object with keys document_title, primary_folder, secondary_topics,
summary, tags, important_facts, open_questions, and archive_note.

Rules:
1. primary_folder must be one exact folder name from the taxonomy.
2. important_facts must be objects with statement, source_marker, and confidence.
3. confidence must be high, medium, or low.
4. Do not invent missing facts or source markers.
5. Use 99_Uncategorized when evidence is insufficient.

Taxonomy:
{taxonomy}

Source file: {source_name}
Extraction notes:
{json.dumps(notes, ensure_ascii=False)}
"""
    response = request_chat(
        base_url,
        key,
        model,
        [{"role": "system", "content": "You are a careful laboratory knowledge archivist. Return valid JSON only."}, {"role": "user", "content": prompt}],
    )
    result = response["result"]
    folder = result.get("primary_folder")
    if folder not in FOLDERS:
        result["primary_folder"] = "99_Uncategorized"
        result["archive_note"] = f"Unsupported folder returned by model: {folder!r}. " + str(result.get("archive_note", ""))
    result["_usage"] = response["usage"]
    result["_model"] = response["model"]
    return result


def one_line(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", name).strip(" .")
    return cleaned or "untitled"


def render_archive(source_path: Path, source_text: str, result: dict, model: str) -> str:
    tags = [one_line(item) for item in result.get("tags", []) if one_line(item)]
    topics = [one_line(item) for item in result.get("secondary_topics", []) if one_line(item)]
    facts = result.get("important_facts", [])
    questions = [one_line(item) for item in result.get("open_questions", []) if one_line(item)]
    lines = [
        "---",
        f"title: {json.dumps(one_line(result.get('document_title') or source_path.stem), ensure_ascii=False)}",
        f"source_file: {json.dumps(source_path.name, ensure_ascii=False)}",
        f"source_sha256: {sha256(source_path)}",
        f"primary_folder: {result['primary_folder']}",
        f"deepseek_model: {model}",
        f"archived_at: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
        "---",
        "",
        "# AI Archive Summary",
        "",
        one_line(result.get("summary")) or "No summary returned.",
        "",
        "## Classification",
        "",
        f"- Primary folder: {result['primary_folder']}",
        f"- Secondary topics: {', '.join(topics) if topics else 'None recorded'}",
        f"- Rationale: {one_line(result.get('archive_note')) or 'None recorded'}",
        "",
        "## Important Facts",
        "",
    ]
    if facts:
        for fact in facts:
            if isinstance(fact, dict):
                statement = one_line(fact.get("statement"))
                marker = one_line(fact.get("source_marker")) or "not recorded"
                confidence = one_line(fact.get("confidence")) or "not recorded"
                lines.append(f"- {statement} (source: {marker}; confidence: {confidence})")
            else:
                lines.append(f"- {one_line(fact)}")
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Open Questions", ""])
    lines.extend(f"- {question}" for question in questions)
    if not questions:
        lines.append("- None recorded.")
    lines.extend(["", "## Source Markdown", "", source_text.rstrip(), ""])
    return "\n".join(lines)


def render_index(records: list[dict]) -> str:
    lines = [
        "# Lab Notebook Knowledge Archive",
        "",
        f"Last updated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        "",
        "This index points to DeepSeek-classified Markdown derivatives. Original OneNote files and readable PDFs remain preserved separately.",
        "",
        "## Folder Guide",
        "",
    ]
    for folder, description in FOLDERS.items():
        lines.append(f"- {folder}: {description}")
    lines.extend(["", "## Documents", "", "| Title | Folder | Source | Summary |", "| --- | --- | --- | --- |"])
    for record in sorted(records, key=lambda item: (item["folder"], item["title"].casefold())):
        title = one_line(record["title"]).replace("|", "\\|")
        summary = one_line(record["summary"]).replace("|", "\\|")
        source = one_line(record["source"]).replace("|", "\\|")
        relative = record["relative_path"].replace(" ", "%20")
        lines.append(f"| [{title}]({relative}) | {record['folder']} | {source} | {summary} |")
    lines.extend(["", "## Provenance", "", "- MinerU raw results: ../mineru_raw/", "- Clean Markdown inputs: ../markdown/", "- PDF derivatives and manifests: ../pdf/ and ../manifests/", "- Original immutable archive: ../../Lab_Notebook_Original_2026-06-11/", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify MinerU Markdown with DeepSeek and build a lab archive.")
    parser.add_argument("--markdown-dir", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--manifest-dir", type=Path, required=True)
    parser.add_argument("--key-file", type=Path, default=Path("/Volumes/ZZLab_AI/Key/Deepseek Key.txt"))
    parser.add_argument("--base-url", default="https://api.deepseek.com")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--chunk-chars", type=int, default=50000)
    args = parser.parse_args()

    key = read_key(args.key_file)
    markdown_files = sorted(path for path in args.markdown_dir.glob("*.md") if path.name != "INDEX.md")
    if not markdown_files:
        raise SystemExit(f"No Markdown files found in {args.markdown_dir}")
    args.archive_dir.mkdir(parents=True, exist_ok=True)
    args.manifest_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for source_path in markdown_files:
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        notes, note_usage = note_chunks(args.base_url, key, args.model, source_path.name, chunks(source_text, args.chunk_chars))
        result = classify(args.base_url, key, args.model, source_path.name, notes)
        target_dir = args.archive_dir / result["primary_folder"]
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{safe_filename(source_path.stem)}.md"
        target.write_text(render_archive(source_path, source_text, result, args.model), encoding="utf-8")
        manifest = {
            "source": str(source_path),
            "source_sha256": sha256(source_path),
            "archive": str(target),
            "classified_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "model": args.model,
            "chunk_usage": note_usage,
            "classification": result,
        }
        (args.manifest_dir / f"{safe_filename(source_path.stem)}.deepseek.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(
            {
                "title": one_line(result.get("document_title")) or source_path.stem,
                "folder": result["primary_folder"],
                "source": source_path.name,
                "summary": result.get("summary", ""),
                "relative_path": target.relative_to(args.archive_dir).as_posix(),
                "source_sha256": manifest["source_sha256"],
            }
        )

    (args.archive_dir / "INDEX.md").write_text(render_index(records), encoding="utf-8")
    (args.archive_dir / "INDEX.json").write_text(json.dumps({"updated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "documents": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"documents": len(records), "index": str(args.archive_dir / "INDEX.md")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
