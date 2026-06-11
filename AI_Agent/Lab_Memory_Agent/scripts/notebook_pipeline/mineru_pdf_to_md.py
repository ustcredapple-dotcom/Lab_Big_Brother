from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


DEFAULT_TOKEN_CANDIDATES = (
    "MinerU Key.txt",
    "MinerU Token.txt",
    "mineru_token.txt",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_token(key_dir: Path, explicit: Path | None) -> str:
    candidates = [explicit] if explicit else [key_dir / name for name in DEFAULT_TOKEN_CANDIDATES]
    for path in candidates:
        if path and path.is_file():
            token = path.read_text(encoding="utf-8").strip()
            if token:
                return token
    names = ", ".join(DEFAULT_TOKEN_CANDIDATES)
    raise SystemExit(f"MinerU token not found. Add one of these files under {key_dir}: {names}")


def request_json(method: str, url: str, token: str, payload: dict | None = None, timeout: int = 60) -> dict:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc
    if not data:
        return {}
    return json.loads(data.decode("utf-8"))


def put_file(upload_url: str, path: Path, timeout: int = 600) -> None:
    headers = {"Content-Type": "application/pdf"}
    request = urllib.request.Request(
        upload_url,
        data=path.read_bytes(),
        headers=headers,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"PUT upload failed for {path.name}: HTTP {exc.code}: {detail}") from exc


def download(url: str, output: Path, timeout: int = 600) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, output.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"download failed: HTTP {exc.code}: {detail}") from exc


def find_markdown(extract_dir: Path) -> Path | None:
    names = ("full.md", "result.md", "output.md")
    for name in names:
        matches = sorted(extract_dir.rglob(name))
        if matches:
            return matches[0]
    matches = sorted(extract_dir.rglob("*.md"))
    return matches[0] if matches else None


def extract_result(zip_path: Path, raw_dir: Path, markdown_dir: Path, section_name: str) -> Path | None:
    extract_dir = raw_dir / section_name
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extract_dir)
    source_md = find_markdown(extract_dir)
    if not source_md:
        return None
    markdown_dir.mkdir(parents=True, exist_ok=True)
    target = markdown_dir / f"{section_name}.md"
    target.write_text(source_md.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
    return target


def normalize_upload_item(item: dict) -> tuple[str, str | None]:
    name = str(item.get("file_name") or item.get("filename") or item.get("name") or "")
    url = item.get("upload_url") or item.get("url") or item.get("presigned_url")
    return name, url


def parse_batch_response(response: dict) -> tuple[str, list[dict]]:
    data = response.get("data", response)
    batch_id = data.get("batch_id") or data.get("batchId")
    urls = data.get("file_urls") or data.get("fileUrls") or data.get("urls") or []
    if not batch_id:
        raise RuntimeError(f"MinerU response did not include batch_id: {json.dumps(response)[:1000]}")
    if not isinstance(urls, list) or not urls:
        raise RuntimeError(f"MinerU response did not include upload URLs: {json.dumps(response)[:1000]}")
    return str(batch_id), urls


def iter_result_items(response: dict) -> list[dict]:
    data = response.get("data", response)
    if isinstance(data, dict):
        for key in ("extract_result", "extract_results", "results", "files"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def item_status(item: dict) -> str:
    return str(item.get("state") or item.get("status") or item.get("extract_state") or "").lower()


def item_name(item: dict) -> str:
    return str(item.get("file_name") or item.get("filename") or item.get("name") or item.get("fileName") or "")


def item_zip_url(item: dict) -> str | None:
    for key in ("full_zip_url", "zip_url", "download_url", "result_url", "fullZipUrl"):
        value = item.get(key)
        if value:
            return str(value)
    return None


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit lab notebook PDFs to MinerU and collect Markdown outputs.")
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--markdown-dir", type=Path, required=True)
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--key-dir", type=Path, default=Path("/Volumes/ZZLab_AI/Key"))
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--base-url", default="https://mineru.net")
    parser.add_argument("--upload-path", default="/api/v4/file-urls/batch")
    parser.add_argument("--result-path", default="/api/v4/extract-results/batch")
    parser.add_argument("--model-version", default="vlm")
    parser.add_argument("--language", default="ch")
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--timeout-minutes", type=int, default=90)
    parser.add_argument("--resume-batch-id")
    args = parser.parse_args()

    token = read_token(args.key_dir, args.token_file)
    pdfs = sorted(args.pdf_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in {args.pdf_dir}")

    state = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pdf_dir": str(args.pdf_dir),
        "raw_dir": str(args.raw_dir),
        "markdown_dir": str(args.markdown_dir),
        "mineru_base_url": args.base_url,
        "pdfs": [
            {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in pdfs
        ],
    }

    if args.resume_batch_id:
        batch_id = args.resume_batch_id
    else:
        payload = {
            "files": [{"name": path.name, "is_ocr": True, "data_id": path.stem} for path in pdfs],
            "model_version": args.model_version,
            "language": args.language,
        }
        upload_url = urllib.parse.urljoin(args.base_url, args.upload_path)
        response = request_json("POST", upload_url, token, payload)
        batch_id, upload_items = parse_batch_response(response)
        by_name = {path.name: path for path in pdfs}
        for item in upload_items:
            name, url = normalize_upload_item(item)
            if name not in by_name or not url:
                raise RuntimeError(f"Unmatched MinerU upload item: {json.dumps(item, ensure_ascii=False)}")
            put_file(url, by_name[name])
        state["upload_response"] = response

    state["batch_id"] = batch_id
    save_state(args.state_file, state)

    deadline = time.time() + args.timeout_minutes * 60
    result_url = urllib.parse.urljoin(args.base_url, args.result_path)
    final_response = None
    while time.time() < deadline:
        response = request_json("GET", f"{result_url}?batch_id={urllib.parse.quote(batch_id)}", token)
        final_response = response
        items = iter_result_items(response)
        statuses = [item_status(item) for item in items]
        done = items and all(status in {"done", "success", "finished", "completed"} for status in statuses)
        failed = [item for item in items if item_status(item) in {"failed", "error"}]
        state.update(
            {
                "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "last_result_response": response,
            }
        )
        save_state(args.state_file, state)
        if failed:
            raise RuntimeError(f"MinerU failed for: {[item_name(item) for item in failed]}")
        if done:
            break
        print(f"waiting for MinerU batch {batch_id}: {statuses or 'no result items yet'}")
        time.sleep(args.poll_seconds)
    else:
        raise TimeoutError(f"Timed out waiting for MinerU batch {batch_id}")

    written = []
    assert final_response is not None
    for item in iter_result_items(final_response):
        name = item_name(item)
        section = Path(name).stem if name else str(item.get("data_id") or item.get("dataId") or "unknown")
        zip_url = item_zip_url(item)
        if not zip_url:
            raise RuntimeError(f"No zip URL in MinerU result item: {json.dumps(item, ensure_ascii=False)[:1000]}")
        zip_path = args.raw_dir / f"{section}.zip"
        download(zip_url, zip_path)
        markdown = extract_result(zip_path, args.raw_dir, args.markdown_dir, section)
        written.append({"section": section, "zip": str(zip_path), "markdown": str(markdown) if markdown else None})

    state.update(
        {
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "written": written,
        }
    )
    save_state(args.state_file, state)
    print(json.dumps({"batch_id": batch_id, "written": written}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
