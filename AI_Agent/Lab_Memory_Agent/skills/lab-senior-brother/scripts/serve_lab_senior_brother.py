from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
ZZLAB_ROOT = Path("/Volumes/ZZLab_AI")
HTML_ROOT = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11"
DISTILLATION = ZZLAB_ROOT / "Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.json"
KEY_FILE = ZZLAB_ROOT / "Key/Deepseek Key.txt"

sys.path.insert(0, str(SCRIPT_DIR))
from query_lab_notebook import search  # noqa: E402


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>实验室大师兄</title>
  <style>
    :root { color-scheme: light; --bg: #f7f7f8; --card: #fff; --ink: #1f2328; --muted: #687076; --accent: #3451b2; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; background: var(--bg); color: var(--ink); }
    main { max-width: 1120px; margin: 0 auto; padding: 32px 20px 56px; }
    header { margin-bottom: 22px; }
    h1 { font-size: 32px; margin: 0 0 8px; }
    .subtitle { color: var(--muted); margin: 0; }
    .panel, .card { background: var(--card); border: 1px solid #e2e2e5; border-radius: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
    .panel { padding: 18px; margin-bottom: 18px; }
    textarea { width: 100%; min-height: 96px; resize: vertical; box-sizing: border-box; border: 1px solid #d4d4d8; border-radius: 10px; padding: 12px; font-size: 16px; line-height: 1.45; }
    .row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
    button { border: 0; border-radius: 10px; background: var(--accent); color: white; padding: 10px 16px; font-size: 15px; cursor: pointer; }
    button:disabled { opacity: .55; cursor: wait; }
    label { color: var(--muted); font-size: 14px; }
    input[type="number"] { width: 64px; padding: 6px; border-radius: 8px; border: 1px solid #d4d4d8; }
    #status { color: var(--muted); font-size: 14px; }
    .answer { white-space: pre-wrap; line-height: 1.55; }
    .card { padding: 14px 16px; margin-top: 12px; }
    .meta { color: var(--muted); font-size: 13px; }
    .score { display: inline-block; color: #0f766e; font-weight: 600; margin-left: 6px; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    ul { margin: 8px 0 0; padding-left: 22px; }
    details { margin-top: 8px; }
    code { background: #f1f1f3; padding: 1px 4px; border-radius: 4px; }
  </style>
</head>
<body>
<main>
  <header>
    <h1>实验室大师兄</h1>
    <p class="subtitle">先查 DeepSeek 蒸馏索引，再回到原始 HTML 证据。问我“之前做过吗？怎么做的？证据在哪？”</p>
  </header>

  <section class="panel">
    <textarea id="question" placeholder="例如：我们之前做过 DDS 验收吗？怎么做的？证据在哪里？"></textarea>
    <div class="row">
      <button id="ask">查询</button>
      <label><input id="useDeepseek" type="checkbox" checked /> 用 DeepSeek 整理答案</label>
      <label>证据数 <input id="topK" type="number" value="5" min="1" max="10" /></label>
      <span id="status">就绪</span>
    </div>
  </section>

  <section id="result"></section>
</main>

<script>
const question = document.getElementById("question");
const ask = document.getElementById("ask");
const statusEl = document.getElementById("status");
const result = document.getElementById("result");

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function list(items, max=4) {
  if (!items || !items.length) return "";
  return "<ul>" + items.slice(0, max).map(x => `<li>${esc(x)}</li>`).join("") + "</ul>";
}

function render(data) {
  const answer = data.answer || "没有生成 DeepSeek 答案；下面是索引检索结果。";
  const evidence = data.search?.evidence || [];
  result.innerHTML = `
    <div class="panel">
      <h2>回答</h2>
      <div class="answer">${esc(answer)}</div>
      <p class="meta">判断：${esc(data.search?.likely_done_before)}；置信度：${esc(data.search?.confidence)}；最高分：${esc(data.search?.top_score)}</p>
    </div>
    <h2>证据</h2>
    ${evidence.map((item, i) => `
      <article class="card">
        <h3>${i + 1}. ${esc(item.section)} / ${esc(item.title)} <span class="score">${Number(item.score).toFixed(1)}</span></h3>
        <p>${esc(item.summary)}</p>
        <p><a href="${esc(item.source_url)}" target="_blank">打开原始 HTML</a></p>
        ${list(item.important_facts)}
        ${item.source_snippet ? `<details><summary>查看原文片段</summary><p>${esc(item.source_snippet)}</p></details>` : ""}
      </article>
    `).join("")}
  `;
}

async function run() {
  const q = question.value.trim();
  if (!q) { question.focus(); return; }
  ask.disabled = true;
  statusEl.textContent = "查询中...";
  result.innerHTML = "";
  try {
    const resp = await fetch("/api/query", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        question: q,
        use_deepseek: document.getElementById("useDeepseek").checked,
        top_k: Number(document.getElementById("topK").value || 5)
      })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || "request failed");
    render(data);
    statusEl.textContent = "完成";
  } catch (err) {
    statusEl.textContent = "出错";
    result.innerHTML = `<div class="panel"><h2>错误</h2><pre>${esc(err.message || err)}</pre></div>`;
  } finally {
    ask.disabled = false;
  }
}

ask.addEventListener("click", run);
question.addEventListener("keydown", e => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") run();
});
</script>
</body>
</html>
"""


def read_deepseek_key(path: Path = KEY_FILE) -> str:
    raw = path.read_text(encoding="utf-8").strip()
    parts = raw.replace("：", ":").replace("=", " ").replace(":", " ").split()
    for part in parts:
        if part.startswith("sk-"):
            return part
    if raw.startswith("sk-"):
        return raw
    raise RuntimeError(f"No DeepSeek sk-token found in {path}")


def call_deepseek(question: str, search_result: dict, model: str = "deepseek-chat") -> tuple[str, dict]:
    key = read_deepseek_key()
    compact_evidence = []
    for item in search_result.get("evidence", []):
        compact_evidence.append(
            {
                "section": item.get("section"),
                "title": item.get("title"),
                "html": item.get("html"),
                "summary": item.get("summary"),
                "important_facts": item.get("important_facts", [])[:6],
                "decisions_or_conclusions": item.get("decisions_or_conclusions", [])[:4],
                "open_questions_or_next_steps": item.get("open_questions_or_next_steps", [])[:4],
                "source_snippet": item.get("source_snippet", "")[:900],
            }
        )
    prompt = f"""
你是“实验室大师兄”，实验室 notebook 数据库管家。

请根据检索证据回答用户问题。必须忠于证据，不要编造。

回答结构：
1. 结论：之前是否做过，置信度如何。
2. 怎么做的：步骤、参数、设备、结论。
3. 证据：列出页面标题和 HTML 路径。
4. 还不确定/建议下一步：如果证据不足，说明还要查什么。

用户问题：
{question}

检索结果：
{json.dumps({'likely_done_before': search_result.get('likely_done_before'), 'confidence': search_result.get('confidence'), 'evidence': compact_evidence}, ensure_ascii=False)}
"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a careful lab notebook database steward. Answer in Chinese. Do not invent facts."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "stream": False,
    }
    result = subprocess.run(
        [
            "curl",
            "-sS",
            "https://api.deepseek.com/chat/completions",
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
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"curl exited {result.returncode}")
    data = json.loads(result.stdout)
    if data.get("error"):
        raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))
    return data["choices"][0]["message"]["content"], data.get("usage", {})


def source_url_for(html_path: str) -> str:
    try:
        rel = Path(html_path).resolve().relative_to(HTML_ROOT.resolve()).as_posix()
        return "/source/" + quote(rel, safe="/#%")
    except ValueError:
        return ""


def make_handler(model: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "LabSeniorBrother/1.0"

        def log_message(self, format: str, *args) -> None:
            print(f"{self.client_address[0]} - {format % args}")

        def send_json(self, status: int, body: dict) -> None:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                raw = HTML_PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if parsed.path.startswith("/source/"):
                rel = unquote(parsed.path[len("/source/") :])
                target = (HTML_ROOT / rel).resolve()
                try:
                    target.relative_to(HTML_ROOT.resolve())
                except ValueError:
                    self.send_error(403)
                    return
                if not target.is_file():
                    self.send_error(404)
                    return
                raw = target.read_bytes()
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                if target.suffix.lower() == ".html":
                    content_type = "text/html; charset=utf-8"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/query":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                question = str(payload.get("question", "")).strip()
                if not question:
                    self.send_json(400, {"error": "question is required"})
                    return
                top_k = max(1, min(int(payload.get("top_k", 5)), 10))
                search_result = search(question, DISTILLATION, HTML_ROOT, top_k, include_source_snippets=True)
                for item in search_result.get("evidence", []):
                    item["source_url"] = source_url_for(item.get("html", ""))
                answer = ""
                usage = {}
                if payload.get("use_deepseek", True):
                    answer, usage = call_deepseek(question, search_result, model=model)
                self.send_json(200, {"answer": answer, "usage": usage, "search": search_result})
            except Exception as exc:
                self.send_json(500, {"error": f"{type(exc).__name__}: {exc}"})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the 实验室大师兄 local web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.model))
    url = f"http://{args.host}:{args.port}/"
    print(f"实验室大师兄 running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
