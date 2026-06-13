from __future__ import annotations

import base64
import json
import mimetypes
import re
import subprocess
import time
from pathlib import Path
from typing import Any


ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
QWEN_KEY = ZZLAB_ROOT / "Key/Qwen Key.txt"
DEEPSEEK_KEY = ZZLAB_ROOT / "Key/Deepseek Key.txt"
QWEN_MODEL = "qwen3.7-plus"
QWEN_BASE_URLS = (
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
QWEN_EMBEDDING_URLS = (
    "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/embeddings",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
)
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"


def read_api_key(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    parts = raw.replace("：", ":").replace("=", " ").replace(":", " ").split()
    for part in parts:
        if part.startswith("sk-") or part.startswith("dashscope-"):
            return part
    return raw


def infer_provider(model: str, key_file: Path | None = None) -> str:
    if model.startswith("qwen"):
        return "qwen"
    if key_file and "qwen" in key_file.name.casefold():
        return "qwen"
    return "deepseek"


def endpoint_candidates(provider: str, base_url: str = "") -> list[str]:
    if base_url:
        if base_url.endswith("/chat/completions"):
            return [base_url]
        return [base_url.rstrip("/") + "/chat/completions"]
    if provider == "qwen":
        return list(QWEN_BASE_URLS)
    return [DEEPSEEK_URL]


def embedding_endpoint_candidates(provider: str, base_url: str = "") -> list[str]:
    if base_url:
        if base_url.endswith("/embeddings"):
            return [base_url]
        return [base_url.rstrip("/") + "/embeddings"]
    if provider == "qwen":
        return list(QWEN_EMBEDDING_URLS)
    return []


def strip_json_fences(value: str) -> str:
    value = value.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    return value.strip()


def parse_json_content(value: str) -> dict[str, Any]:
    value = strip_json_fences(value)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


def post_chat(
    *,
    key: str,
    model: str,
    messages: list[dict[str, Any]],
    timeout: int,
    provider: str = "qwen",
    response_format: dict[str, Any] | None = None,
    temperature: float = 0.1,
    retries: int = 2,
    base_url: str = "",
) -> tuple[dict[str, Any], dict[str, Any], str]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if response_format:
        payload["response_format"] = response_format
    last_error = ""
    for attempt in range(1, retries + 1):
        for endpoint in endpoint_candidates(provider, base_url):
            result = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "--fail-with-body",
                    "--connect-timeout",
                    "20",
                    "--max-time",
                    str(max(30, timeout)),
                    endpoint,
                    "-H",
                    f"Authorization: Bearer {key}",
                    "-H",
                    "Content-Type: application/json",
                    "-d",
                    json.dumps(payload, ensure_ascii=False),
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout + 5,
            )
            if result.returncode:
                last_error = result.stdout.strip() or result.stderr.strip() or f"curl exited {result.returncode}"
                continue
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                last_error = result.stdout[:1000]
                continue
            if data.get("error"):
                last_error = json.dumps(data["error"], ensure_ascii=False)
                code = str(data.get("error", {}).get("code", ""))
                if code != "invalid_api_key":
                    raise RuntimeError(last_error)
                continue
            return data, data.get("usage", {}), data.get("model", model)
        if attempt < retries:
            time.sleep(2 * attempt)
    raise RuntimeError(last_error or f"{provider} request failed")


def call_json(
    *,
    key: str,
    model: str = QWEN_MODEL,
    messages: list[dict[str, Any]],
    timeout: int = 120,
    retries: int = 2,
    provider: str | None = None,
    base_url: str = "",
) -> tuple[dict[str, Any], dict[str, Any], str]:
    provider = provider or infer_provider(model)
    data, usage, actual_model = post_chat(
        key=key,
        model=model,
        messages=messages,
        timeout=timeout,
        provider=provider,
        response_format={"type": "json_object"},
        retries=retries,
        base_url=base_url,
    )
    content = data["choices"][0]["message"]["content"]
    return parse_json_content(content), usage, actual_model


def call_text(
    *,
    key: str,
    model: str = QWEN_MODEL,
    messages: list[dict[str, Any]],
    timeout: int = 120,
    retries: int = 2,
    provider: str | None = None,
    base_url: str = "",
) -> tuple[str, dict[str, Any], str]:
    provider = provider or infer_provider(model)
    data, usage, actual_model = post_chat(
        key=key,
        model=model,
        messages=messages,
        timeout=timeout,
        provider=provider,
        retries=retries,
        base_url=base_url,
    )
    return data["choices"][0]["message"]["content"], usage, actual_model


def call_embeddings(
    *,
    key: str,
    texts: list[str],
    model: str = "text-embedding-v4",
    dimensions: int | None = 512,
    timeout: int = 120,
    retries: int = 2,
    provider: str = "qwen",
    base_url: str = "",
) -> tuple[list[list[float]], dict[str, Any], str]:
    if not texts:
        return [], {}, model
    endpoints = embedding_endpoint_candidates(provider, base_url)
    if not endpoints:
        raise RuntimeError(f"No embedding endpoint configured for provider: {provider}")
    payload: dict[str, Any] = {"model": model, "input": texts}
    if dimensions:
        payload["dimensions"] = dimensions
    last_error = ""
    for attempt in range(1, retries + 1):
        for endpoint in endpoints:
            result = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "--fail-with-body",
                    "--connect-timeout",
                    "20",
                    "--max-time",
                    str(max(30, timeout)),
                    endpoint,
                    "-H",
                    f"Authorization: Bearer {key}",
                    "-H",
                    "Content-Type: application/json",
                    "-d",
                    json.dumps(payload, ensure_ascii=False),
                ],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout + 5,
            )
            if result.returncode:
                last_error = result.stdout.strip() or result.stderr.strip() or f"curl exited {result.returncode}"
                continue
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                last_error = result.stdout[:1000]
                continue
            if data.get("error"):
                last_error = json.dumps(data["error"], ensure_ascii=False)
                continue
            vectors_by_index = {
                int(item.get("index", index)): item["embedding"]
                for index, item in enumerate(data.get("data", []))
                if item.get("embedding") is not None
            }
            vectors = [vectors_by_index[index] for index in range(len(texts))]
            return vectors, data.get("usage", {}), data.get("model", model)
        if attempt < retries:
            time.sleep(2 * attempt)
    raise RuntimeError(last_error or f"{provider} embedding request failed")


def call_embeddings_batched(
    *,
    key: str,
    texts: list[str],
    model: str = "text-embedding-v4",
    dimensions: int | None = 512,
    batch_size: int = 10,
    timeout: int = 120,
    retries: int = 2,
    provider: str = "qwen",
    base_url: str = "",
) -> tuple[list[list[float]], list[dict[str, Any]], str]:
    vectors: list[list[float]] = []
    usage_records: list[dict[str, Any]] = []
    actual_model = model
    for start in range(0, len(texts), max(1, batch_size)):
        batch = texts[start : start + max(1, batch_size)]
        batch_vectors, usage, actual_model = call_embeddings(
            key=key,
            texts=batch,
            model=model,
            dimensions=dimensions,
            timeout=timeout,
            retries=retries,
            provider=provider,
            base_url=base_url,
        )
        vectors.extend(batch_vectors)
        usage_records.append({"batch_start": start, "batch_size": len(batch), "usage": usage})
    return vectors, usage_records, actual_model


def image_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def describe_image_json(
    *,
    key: str,
    image_path: Path,
    prompt: str,
    model: str = QWEN_MODEL,
    timeout: int = 180,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url(image_path)}},
            ],
        }
    ]
    return call_json(key=key, model=model, messages=messages, timeout=timeout, retries=2, provider="qwen")
