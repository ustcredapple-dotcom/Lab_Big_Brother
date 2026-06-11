from __future__ import annotations

import argparse
import difflib
import hashlib
import html
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_html_notebook_index as html_index  # noqa: E402
import distill_html_with_deepseek as deepseek_distill  # noqa: E402


DEFAULT_ROOT = Path("/Volumes/ZZLab_AI")
DEFAULT_PROCESSING = DEFAULT_ROOT / "Document/Lab_Notebook_Processing"
DEFAULT_HTML_ROOT = DEFAULT_PROCESSING / "html/active/Lab_Notebook_Original_2026-06-11"
DEFAULT_INDEX = DEFAULT_PROCESSING / "html/active/HTML_INDEX.html"
DEFAULT_MANIFEST = DEFAULT_PROCESSING / "html/active/HTML_MANIFEST.json"
DEFAULT_DISTILLATION_DIR = DEFAULT_PROCESSING / "html_deepseek_distilled"
DEFAULT_STATE_DIR = DEFAULT_PROCESSING / "daily_updates"
DEFAULT_CONFIG = DEFAULT_PROCESSING / "daily_update_config.json"
DEFAULT_INCOMING_HTML_ROOT = DEFAULT_PROCESSING / "html/incoming"


def now_stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def file_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_page_key(page: dict[str, Any]) -> str:
    return page.get("onenote_page_id") or page.get("html") or f"{page.get('section', '')}/{page.get('title', '')}"


def text_snapshot_name(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest() + ".txt"


def flatten_manifest(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    pages: dict[str, dict[str, Any]] = {}
    for section in manifest.get("sections", []):
        for page in section.get("pages", []):
            record = dict(page)
            record["section"] = section.get("section", "")
            pages[stable_page_key(record)] = record
    return pages


def extract_page_text(html_root: Path, page: dict[str, Any]) -> tuple[str, list[str]]:
    return deepseek_distill.extract_html(html_root / page["html"])


def safe_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def copy_if_changed(source: Path, target: Path) -> str:
    if not source.is_file():
        return "missing"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and sha256(source) == sha256(target):
        return "duplicate"
    shutil.copy2(source, target)
    return "copied"


def resolve_attachment(page_path: Path, attachment: str) -> Path | None:
    if not attachment or "://" in attachment or attachment.startswith("#"):
        return None
    clean = attachment.split("#", 1)[0].split("?", 1)[0]
    candidate = (page_path.parent / clean).resolve()
    return candidate if candidate.exists() else None


def prune_empty_dirs(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted([item for item in root.rglob("*") if item.is_dir()], key=lambda item: len(item.parts), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def maybe_remove(path: Path, cleanup: bool, incoming_root: Path) -> bool:
    if not cleanup:
        return False
    if not safe_relative(path, incoming_root):
        return False
    if path.exists() and path.is_file():
        path.unlink()
        return True
    return False


def merge_incoming_html(incoming_root: Path, active_root: Path, cleanup: bool) -> dict[str, Any]:
    incoming_root = incoming_root.expanduser().resolve()
    active_root = active_root.expanduser().resolve()
    empty_result = {
        "enabled": False,
        "incoming_root": str(incoming_root),
        "added_pages": 0,
        "updated_pages": 0,
        "duplicate_pages": 0,
        "copied_files": 0,
        "duplicate_files": 0,
        "removed_incoming_files": 0,
    }
    if not incoming_root.exists():
        return empty_result
    if incoming_root == active_root:
        return {**empty_result, "enabled": False, "note": "incoming_html_root equals active html_root; merge skipped"}
    if not safe_relative(incoming_root, DEFAULT_PROCESSING):
        return {**empty_result, "enabled": False, "note": "incoming_html_root is outside Lab_Notebook_Processing; merge skipped for safety"}

    incoming_manifest = html_index.build_manifest(incoming_root)
    active_manifest = html_index.build_manifest(active_root) if active_root.exists() else {"sections": []}
    incoming_pages = flatten_manifest(incoming_manifest)
    active_pages = flatten_manifest(active_manifest)
    copied_files = 0
    duplicate_files = 0
    removed_files = 0
    added_pages = 0
    updated_pages = 0
    duplicate_pages = 0

    for section in incoming_manifest.get("sections", []):
        index_rel = section.get("index_html", "")
        if index_rel:
            source_index = incoming_root / index_rel
            status = copy_if_changed(source_index, active_root / index_rel)
            if status == "copied":
                copied_files += 1
            elif status == "duplicate":
                duplicate_files += 1
            if status in {"copied", "duplicate"}:
                removed_files += int(maybe_remove(source_index, cleanup, incoming_root))

    for key, page in incoming_pages.items():
        incoming_page_path = incoming_root / page["html"]
        active_page_path = active_root / page["html"]
        previous = active_pages.get(key)
        same_content = bool(previous and previous.get("sha256") == page.get("sha256"))
        if same_content:
            duplicate_pages += 1
        elif previous:
            updated_pages += 1
        else:
            added_pages += 1

        _text, attachments = deepseek_distill.extract_html(incoming_page_path)
        status = copy_if_changed(incoming_page_path, active_page_path)
        if status == "copied":
            copied_files += 1
        elif status == "duplicate":
            duplicate_files += 1
        if status in {"copied", "duplicate"}:
            removed_files += int(maybe_remove(incoming_page_path, cleanup, incoming_root))

        copied_attachment_paths: set[Path] = set()
        for attachment in attachments:
            source = resolve_attachment(incoming_page_path, attachment)
            if not source or source in copied_attachment_paths or not safe_relative(source, incoming_root):
                continue
            copied_attachment_paths.add(source)
            target = active_page_path.parent / source.relative_to(incoming_page_path.parent)
            attachment_status = copy_if_changed(source, target)
            if attachment_status == "copied":
                copied_files += 1
            elif attachment_status == "duplicate":
                duplicate_files += 1
            if attachment_status in {"copied", "duplicate"}:
                removed_files += int(maybe_remove(source, cleanup, incoming_root))

    if cleanup:
        prune_empty_dirs(incoming_root)

    return {
        "enabled": True,
        "incoming_root": str(incoming_root),
        "added_pages": added_pages,
        "updated_pages": updated_pages,
        "duplicate_pages": duplicate_pages,
        "copied_files": copied_files,
        "duplicate_files": duplicate_files,
        "removed_incoming_files": removed_files,
        "cleanup": cleanup,
    }


def run_pre_sync(command: str, log_dir: Path) -> dict[str, Any]:
    if not command.strip():
        return {"enabled": False, "returncode": 0, "duration_seconds": 0}
    log_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = subprocess.run(
        command,
        shell=True,
        check=False,
        cwd=str(DEFAULT_ROOT),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60 * 60,
    )
    duration = round(time.time() - started, 2)
    stamp = file_stamp()
    (log_dir / f"{stamp}-pre-sync.stdout.log").write_text(result.stdout, encoding="utf-8", errors="replace")
    (log_dir / f"{stamp}-pre-sync.stderr.log").write_text(result.stderr, encoding="utf-8", errors="replace")
    return {
        "enabled": True,
        "command": shlex.join(shlex.split(command)) if command.strip() else "",
        "returncode": result.returncode,
        "duration_seconds": duration,
        "stdout_log": str(log_dir / f"{stamp}-pre-sync.stdout.log"),
        "stderr_log": str(log_dir / f"{stamp}-pre-sync.stderr.log"),
    }


def diff_lines(previous: str, current: str, max_lines: int) -> list[str]:
    previous_lines = previous.splitlines()
    current_lines = current.splitlines()
    lines = list(
        difflib.unified_diff(
            previous_lines,
            current_lines,
            fromfile="previous",
            tofile="current",
            lineterm="",
            n=3,
        )
    )
    if len(lines) > max_lines:
        omitted = len(lines) - max_lines
        return lines[:max_lines] + [f"... diff truncated, {omitted} lines omitted ..."]
    return lines


def classify_changes(
    previous_state: dict[str, Any],
    current_pages: dict[str, dict[str, Any]],
    html_root: Path,
    state_dir: Path,
    detected_at: str,
    max_diff_lines: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    previous_pages = previous_state.get("pages", {})
    changes: list[dict[str, Any]] = []
    current_texts: dict[str, str] = {}

    for key, page in sorted(current_pages.items(), key=lambda item: (item[1].get("section", ""), item[1].get("order", 0))):
        current_text, attachments = extract_page_text(html_root, page)
        current_texts[key] = current_text
        previous = previous_pages.get(key)
        change_type = ""
        previous_text = ""
        if previous:
            previous_text_path = previous.get("text_path", "")
            if previous_text_path and Path(previous_text_path).exists():
                previous_text = Path(previous_text_path).read_text(encoding="utf-8", errors="replace")
            if previous.get("sha256") != page.get("sha256"):
                change_type = "modified"
        else:
            change_type = "added"

        if change_type:
            change: dict[str, Any] = {
                "type": change_type,
                "detected_at": detected_at,
                "key": key,
                "section": page.get("section", ""),
                "title": page.get("title", ""),
                "html": page.get("html", ""),
                "previous_sha256": previous.get("sha256", "") if previous else "",
                "current_sha256": page.get("sha256", ""),
                "created": page.get("created", ""),
                "updated": page.get("updated", ""),
                "attachments": attachments,
            }
            if change_type == "added":
                change["text_preview"] = " ".join(current_text.split())[:1000]
                change["diff"] = ["--- previous", "+++ current", "@@ added page @@", *current_text.splitlines()[:max_diff_lines]]
            else:
                change["diff"] = diff_lines(previous_text, current_text, max_diff_lines)
            changes.append(change)

    for key, previous in sorted(previous_pages.items()):
        if key not in current_pages:
            changes.append(
                {
                    "type": "removed",
                    "detected_at": detected_at,
                    "key": key,
                    "section": previous.get("section", ""),
                    "title": previous.get("title", ""),
                    "html": previous.get("html", ""),
                    "previous_sha256": previous.get("sha256", ""),
                    "current_sha256": "",
                    "diff": ["--- previous", "+++ current", "@@ removed page @@"],
                }
            )

    return changes, current_texts


def render_changelog_markdown(detected_at: str, changes: list[dict[str, Any]], pre_sync: dict[str, Any], merge_result: dict[str, Any]) -> str:
    counts = {"added": 0, "modified": 0, "removed": 0}
    for change in changes:
        counts[change["type"]] = counts.get(change["type"], 0) + 1
    lines = [
        f"# Lab Notebook Daily Change Log",
        "",
        f"- Detected at: {detected_at}",
        f"- Added: {counts.get('added', 0)}",
        f"- Modified: {counts.get('modified', 0)}",
        f"- Removed: {counts.get('removed', 0)}",
        f"- Pre-sync enabled: {pre_sync.get('enabled', False)}",
        f"- Pre-sync return code: {pre_sync.get('returncode', 0)}",
        f"- HTML merge enabled: {merge_result.get('enabled', False)}",
        f"- HTML merge added pages: {merge_result.get('added_pages', 0)}",
        f"- HTML merge updated pages: {merge_result.get('updated_pages', 0)}",
        f"- HTML merge duplicate pages: {merge_result.get('duplicate_pages', 0)}",
        f"- Removed incoming duplicate files: {merge_result.get('removed_incoming_files', 0)}",
        "",
    ]
    if not changes:
        lines.extend(["No notebook page changes detected.", ""])
        return "\n".join(lines)

    for change in changes:
        lines.extend(
            [
                f"## {change['type'].upper()} | {change.get('section', '')} / {change.get('title', '')}",
                "",
                f"- HTML: `{change.get('html', '')}`",
                f"- Previous SHA-256: `{change.get('previous_sha256', '')}`",
                f"- Current SHA-256: `{change.get('current_sha256', '')}`",
                f"- Detected at: {change.get('detected_at', detected_at)}",
                "",
                "```diff",
                *change.get("diff", []),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def find_section(distillation: dict[str, Any], section_name: str) -> dict[str, Any]:
    for section in distillation.setdefault("sections", []):
        if section.get("section") == section_name:
            return section
    section = {
        "section": section_name,
        "page_count": 0,
        "distilled": {
            "section_summary": "Section created or first seen during an incremental update. Full section summary has not been regenerated yet.",
            "main_topics": [],
            "key_results": [],
            "important_assets_or_attachments": [],
            "people_and_responsibilities": [],
            "recommended_reading_order": [],
            "follow_up_items": [],
        },
        "pages": [],
    }
    distillation.setdefault("sections", []).append(section)
    return section


def upsert_page(section: dict[str, Any], page_record: dict[str, Any]) -> None:
    pages = section.setdefault("pages", [])
    for index, existing in enumerate(pages):
        if existing.get("html") == page_record.get("html") or existing.get("source_sha256") == page_record.get("source_sha256"):
            pages[index] = page_record
            return
    pages.append(page_record)


def prune_and_sort_distillation(distillation: dict[str, Any], manifest: dict[str, Any]) -> None:
    order: dict[str, tuple[int, int]] = {}
    active_html = set()
    for section_index, section in enumerate(manifest.get("sections", [])):
        for page in section.get("pages", []):
            active_html.add(page.get("html"))
            order[page.get("html", "")] = (section_index, page.get("order", 0))
    for section in distillation.get("sections", []):
        section["pages"] = [page for page in section.get("pages", []) if page.get("html") in active_html]
        section["pages"].sort(key=lambda page: order.get(page.get("html", ""), (9999, 9999)))
        section["page_count"] = len(section["pages"])


def incremental_deepseek_update(
    changes: list[dict[str, Any]],
    manifest_pages: dict[str, dict[str, Any]],
    current_texts: dict[str, str],
    manifest: dict[str, Any],
    manifest_path: Path,
    html_root: Path,
    distillation_dir: Path,
    key_file: Path,
    model: str,
    timeout: int,
    detected_at: str,
    changelog_json: Path,
) -> dict[str, Any]:
    distillation_path = distillation_dir / "DEEPSEEK_DISTILLATION.json"
    distillation = read_json(
        distillation_path,
        {
            "generated_at": detected_at,
            "method": "deepseek_html_distillation_incremental",
            "requested_model": model,
            "source_manifest": str(manifest_path),
            "html_root": str(html_root),
            "notebook": {
                "notebook_summary": "Incremental notebook distillation created before a full notebook summary was available.",
                "top_level_topics": [],
                "high_value_pages": [],
                "operational_state": [],
                "risks_or_open_questions": [],
                "suggested_next_index_improvements": [],
            },
            "sections": [],
            "usage": [],
        },
    )
    key = deepseek_distill.read_deepseek_key(key_file)
    usage_records = distillation.setdefault("usage", [])
    distilled_count = 0
    skipped_removed = 0

    for change in changes:
        if change["type"] == "removed":
            skipped_removed += 1
            continue
        page = manifest_pages[change["key"]]
        text = current_texts[change["key"]]
        attachments = change.get("attachments", [])
        distilled, usage, actual_model = deepseek_distill.distill_page(
            key,
            model,
            page["section"],
            page,
            text,
            attachments,
            timeout,
        )
        distilled["_incremental_update"] = {
            "change_type": change["type"],
            "detected_at": detected_at,
            "previous_sha256": change.get("previous_sha256", ""),
            "current_sha256": change.get("current_sha256", ""),
            "change_log": str(changelog_json),
        }
        page_record = {
            "section": page["section"],
            "title": page["title"],
            "html": page["html"],
            "source_sha256": page["sha256"],
            "created": page.get("created", ""),
            "updated": page.get("updated", ""),
            "attachments": attachments,
            "distilled": distilled,
        }
        section = find_section(distillation, page["section"])
        upsert_page(section, page_record)
        usage_records.append(
            {
                "kind": "incremental_page",
                "section": page["section"],
                "title": page["title"],
                "change_type": change["type"],
                "detected_at": detected_at,
                "usage": usage,
                "model": actual_model,
            }
        )
        distilled_count += 1
        print(json.dumps({"distilled": page["title"], "tokens": usage.get("total_tokens")}, ensure_ascii=False), flush=True)

    prune_and_sort_distillation(distillation, manifest)
    distillation["generated_at"] = detected_at
    distillation["method"] = "deepseek_html_distillation_incrementally_updated"
    distillation["requested_model"] = model
    distillation["source_manifest"] = str(manifest_path)
    distillation["html_root"] = str(html_root)
    distillation.setdefault("incremental_updates", []).append(
        {
            "detected_at": detected_at,
            "change_log": str(changelog_json),
            "distilled_pages": distilled_count,
            "removed_pages": skipped_removed,
        }
    )
    distillation_dir.mkdir(parents=True, exist_ok=True)
    write_json(distillation_path, distillation)
    (distillation_dir / "DEEPSEEK_DISTILLATION.html").write_text(
        deepseek_distill.render_html(distillation),
        encoding="utf-8",
    )
    return {"distilled_pages": distilled_count, "removed_pages": skipped_removed}


def save_state(state_dir: Path, manifest: dict[str, Any], current_pages: dict[str, dict[str, Any]], current_texts: dict[str, str], detected_at: str) -> None:
    texts_dir = state_dir / "page_texts"
    pages: dict[str, Any] = {}
    for key, page in current_pages.items():
        text_path = texts_dir / text_snapshot_name(key)
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(current_texts.get(key, ""), encoding="utf-8")
        pages[key] = {
            "section": page.get("section", ""),
            "title": page.get("title", ""),
            "html": page.get("html", ""),
            "sha256": page.get("sha256", ""),
            "created": page.get("created", ""),
            "updated": page.get("updated", ""),
            "text_path": str(text_path),
            "last_seen_at": detected_at,
        }
    write_json(
        state_dir / "state.json",
        {
            "updated_at": detected_at,
            "manifest_generated_at": manifest.get("generated_at", ""),
            "pages": pages,
        },
    )


def load_config(path: Path) -> dict[str, Any]:
    return read_json(path, {}) if path.exists() else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily incremental update for the ZZLab HTML notebook and DeepSeek distillation.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--html-root", type=Path, default=DEFAULT_HTML_ROOT)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--distillation-dir", type=Path, default=DEFAULT_DISTILLATION_DIR)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--incoming-html-root", type=Path)
    parser.add_argument("--cleanup-incoming", action="store_true")
    parser.add_argument("--key-file", type=Path, default=Path("/Volumes/ZZLab_AI/Key/Deepseek Key.txt"))
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-diff-lines", type=int, default=500)
    parser.add_argument("--no-deepseek", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    pre_sync_command = os.environ.get("ZZLAB_NOTEBOOK_PRE_SYNC_COMMAND", config.get("pre_sync_command", ""))
    incoming_html_root_value = os.environ.get("ZZLAB_NOTEBOOK_INCOMING_HTML_ROOT", config.get("incoming_html_root", ""))
    incoming_html_root = args.incoming_html_root or (Path(incoming_html_root_value) if incoming_html_root_value else DEFAULT_INCOMING_HTML_ROOT)
    cleanup_incoming = args.cleanup_incoming or bool(config.get("cleanup_incoming_html", False))
    detected_at = now_stamp()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    log_dir = args.state_dir / "logs"
    pre_sync = run_pre_sync(pre_sync_command, log_dir)
    merge_result = merge_incoming_html(incoming_html_root, args.html_root, cleanup_incoming)

    manifest = html_index.build_manifest(args.html_root.resolve())
    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(html_index.render_index(manifest, args.index.resolve(), args.html_root.resolve()), encoding="utf-8")
    write_json(args.manifest, manifest)

    previous_state = read_json(args.state_dir / "state.json", {"pages": {}})
    current_pages = flatten_manifest(manifest)
    changes, current_texts = classify_changes(
        previous_state,
        current_pages,
        args.html_root,
        args.state_dir,
        detected_at,
        args.max_diff_lines,
    )

    change_dir = args.state_dir / "changes"
    stamp = file_stamp()
    changelog_json = change_dir / f"{stamp}_change_log.json"
    changelog_md = change_dir / f"{stamp}_change_log.md"
    change_payload = {
        "detected_at": detected_at,
        "pre_sync": pre_sync,
        "html_merge": merge_result,
        "html_root": str(args.html_root),
        "manifest": str(args.manifest),
        "counts": {
            "added": sum(1 for item in changes if item["type"] == "added"),
            "modified": sum(1 for item in changes if item["type"] == "modified"),
            "removed": sum(1 for item in changes if item["type"] == "removed"),
        },
        "changes": changes,
    }
    write_json(changelog_json, change_payload)
    changelog_md.parent.mkdir(parents=True, exist_ok=True)
    changelog_md.write_text(render_changelog_markdown(detected_at, changes, pre_sync, merge_result), encoding="utf-8")

    deepseek_result = {"distilled_pages": 0, "removed_pages": 0, "skipped": args.no_deepseek or not changes}
    if changes and not args.no_deepseek:
        deepseek_result = incremental_deepseek_update(
            changes,
            current_pages,
            current_texts,
            manifest,
            args.manifest,
            args.html_root,
            args.distillation_dir,
            args.key_file,
            args.model,
            args.timeout,
            detected_at,
            changelog_json,
        )

    save_state(args.state_dir, manifest, current_pages, current_texts, detected_at)
    result = {
        "detected_at": detected_at,
        "pages": len(current_pages),
        "changes": change_payload["counts"],
        "changelog_json": str(changelog_json),
        "changelog_md": str(changelog_md),
        "pre_sync": pre_sync,
        "html_merge": merge_result,
        "deepseek": deepseek_result,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
