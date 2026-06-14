---
name: lab-senior-brother
description: Query and answer from the ZZLab lab notebook knowledge base. Use when the user asks whether the lab has previously done, tested, bought, designed, installed, debugged, measured, or decided something; asks "之前做过吗", "怎么做的", "证据在哪", "谁负责", "买过什么", "参数是多少", or wants a lab-memory/database steward for the HTML notebook and Qwen distillation. Also use for maintaining or refreshing the lab notebook HTML index and distilled lookup interface.
---

# 实验室大师兄

Chinese human-readable companion: `SKILL_zh.md`.

Act as the lab's notebook RAG steward: retrieve relevant evidence, let Qwen reason over that evidence, inspect source HTML when needed, then answer with citations and uncertainty.

## Core Workflow

1. Run the RAG query script before answering factual notebook questions:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py \
  "USER QUESTION" \
  --include-source-snippets \
  --format json
```

The default engine is `--engine rag`: the shared chunk-level hybrid RAG engine loads `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/rag_chunk_index/`, retrieves small evidence chunks with Qwen embeddings plus lexical recall, asks Qwen to rerank those chunks for direct answerability, then writes the answer from selected evidence. The old mechanical keyword engine remains available only for debugging with `--engine lexical`.

2. Read the returned answer and evidence. If the evidence is weak, run 1-2 alternative natural-language or alias-expanded queries.
3. If the answer depends on a detail not present in the distilled evidence, open the cited HTML file and inspect the source text around the snippet.
4. Answer in this structure:

- Conclusion: whether the lab appears to have done it before (`yes`, `likely`, `unclear`, or `no evidence found`)
- How it was done: concise procedure, parameters, devices, people, or decisions found in the notebook
- Evidence: cite page titles and absolute HTML paths
- Caveats / next checks: mention uncertainty, missing data, or source pages to inspect

## Web Interface

The web interface is currently retired as a routine entrypoint. The user asked to stop the web version because Telegram/Codex are the useful interfaces. Keep the script available for local debugging only; do not start or expose it unless the user explicitly asks.

For one-off local debugging:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py
```

Then open `http://127.0.0.1:8765/`.

The browser never receives the Qwen API key. The local Python server reads the key, queries the notebook index, calls Qwen when enabled, and returns the answer plus source HTML links.

The UI has a `中文 / English` response-language toggle. Use it to force the final Qwen answer language regardless of whether the retrieved notebook evidence is Chinese or English.

The LaunchAgent `com.zzlab.lab-senior-brother` should stay unloaded/disabled by default. Public ngrok access is also stopped by default. If the user explicitly asks to re-enable the web UI, run the local server with Basic Auth and expose port `8765` through ngrok:

```bash
LAB_SENIOR_BROTHER_USER="..." \
LAB_SENIOR_BROTHER_PASSWORD="..." \
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py

ngrok http 8765
```

Do not write the real ngrok authtoken, Basic Auth password, Qwen key, or notebook sharing secrets into this skill, GitHub, or handoff files. Public tunnels should be treated as temporary operational state unless a reserved ngrok domain is intentionally configured.

## Data Sources

For current paths and source hierarchy, read `references/data_sources.md` when needed.

For the intended RAG architecture and next implementation steps, read `references/rag_architecture.md`.

Primary lookup index:

`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.json`

Primary chunk RAG index:

`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/rag_chunk_index/chunks.jsonl`

Source HTML root:

`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11/`

## Answering Rules

- Do not answer from memory when the question is about lab history; query first.
- Treat Qwen distillation as a navigation layer, not the source of truth.
- Treat RAG as evidence retrieval plus grounded generation, not as keyword lookup.
- Prefer source HTML citations for final answers.
- Do not expose keys, passwords, cookies, or notebook sharing secrets.
- If no evidence is found, say so plainly and suggest likely query terms or source areas to inspect.
- Keep the tone practical and senior-labmate-like: direct, helpful, and traceable.

## Maintenance

When new notebook HTML exports are added:

1. Refresh `HTML_INDEX.html` and `HTML_MANIFEST.json` using `build_html_notebook_index.py`.
2. Refresh `DEEPSEEK_DISTILLATION.html/json` using `distill_html_with_deepseek.py` if external API use is approved. The file name is kept for compatibility; current default provider is Qwen.
3. Rebuild the chunk index when needed:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/rag_query_engine.py --build-index
```

4. Re-run this skill's query script on representative questions to verify retrieval quality.
5. Update `PROJECT_HANDOFF.md` and `WORK_LOG.md` after significant changes.
6. Refresh 大师兄 self-knowledge so the agent can answer questions about its own current architecture and maintenance state:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py
```

For routine maintenance, prefer the daily incremental updater:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/daily_notebook_update.py
```

It can merge a fresh incoming HTML export into the active HTML tree first, skipping duplicate pages so the notebook is not stored twice. It then compares the active HTML notebook against the previous snapshot, writes timestamped change logs, and sends only added or modified pages to Qwen before merging the refreshed page records into the distilled index. Use `--no-deepseek` only for baseline seeding or dry verification.

Daily notebook, Telegram, Lark, and email digest scripts refresh the chunk RAG index after distillation so new notebook pages and communication records become queryable without a separate manual step.

RAGFlow is an optional future backend, not the current default. It is useful if the lab wants a full UI and heavier document-processing platform, but the present Mac has no Docker runtime installed and is ARM64 while RAGFlow's public prebuilt Docker images are x86-focused. Keep the local chunk RAG as the production path unless Docker/ARM64 RAGFlow deployment has been installed, tested, and wired through a backend switch.

AnythingLLM is the lighter off-the-shelf RAG backend candidate. Prefer testing its Docker/API or server mode before RAGFlow if the lab wants a ready-made RAG UI and API. `rag_query_engine.py` already has an optional `rag_engine=anythingllm` adapter for AnythingLLM's workspace chat API, using `anythingllm_base_url`, `anythingllm_workspace_slug`, `anythingllm_mode=query`, and an API key from config/env/`Key/AnythingLLM API Key.txt`. Do not switch live Telegram/Lark/email to it until it has ingested normalized lab exports, telemetry/privacy settings are reviewed, and regression questions match or beat the local chunk RAG.

## Telegram Interface

Telegram can be used as a lightweight query and note-capture entrypoint:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/telegram_lab_senior_brother.py
```

The BotFather token must stay private at `/Volumes/ZZLab_AI/Key/telegram_bot_token.txt`. The private config lives at `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/telegram_bot_config.json`.

Supported commands:

- `/id`: return the current chat ID for allow-list setup
- `/ask QUESTION` or `查 QUESTION`: query the lab notebook; normal messages default to query
- `/note TEXT` or `记 TEXT`: write a Telegram note into the private daily Telegram folder
- `/allow CHAT_ID`: add a Telegram chat ID to the allow-list; natural Chinese such as `把 8004894761 写进白名单` also works for already-authorized users
- `开始记`: switch this chat into record mode; normal messages become notes
- `停止记`: switch this chat back to query mode
- `/status`, `/help`

Multiple Telegram accounts can access the bot by sending `/id` and then being added to `allowed_chat_ids` in the private config. Do not enable notebook query or note write access for unknown chat IDs.

Telegram replies should stay brief and alive. The Telegram entrypoint now has a small local agent backend: explicit commands run directly, while other normal messages go through a Qwen router that may select only from a safe local tool registry (`chat`, `query_notebook`, `note`, `find_file`, `allow_chat_id`, `help`, `status`, or `unsupported`). It must not expose arbitrary shell or unrestricted filesystem access. Greetings, thanks, and simple presence checks should be handled by the Telegram personality layer instead of being sent to notebook search. Safe admin intents, such as adding a chat ID to the allow-list, should route to explicit local tools instead of notebook search. Persist only durable records by default: `note`, `file`, `mode`, and `admin`. Ordinary queries, greetings, file requests, and unsupported requests should not be kept in daily chat records, and query-detail HTML should be generated temporarily for sending rather than saved under the daily folder. Runtime Telegram queries should call the shared chunk RAG engine first; that engine performs Qwen embedding retrieval, lexical recall, Qwen reranking, and Qwen grounded answering from selected chunks. The older page-level Qwen selector remains only as a fallback. Python may load files and assemble prompts, but it should not decide an answer from keyword scores alone. If Qwen finds no direct evidence, answer naturally that the notebook does not contain a clear record. Any actual Telegram file upload, including photos/images, is archived automatically under `/Volumes/ZZLab_AI/YYYY-MM-DD/telegram文件和聊天记录/<person>_<chat_id>/`, using its caption/current chat as context. PDF and text-like files are extracted into text/HTML previews, images get Qwen vision previews, and binary files such as STEP or EXE are stored without content extraction.

Telegram and Lark keep a short-term conversation state in their private state JSON files so follow-up questions can inherit recent context without permanently storing ordinary chats. The bot should emit a brief progress message before long RAG calls, such as "我接着上文查一下...", then send the grounded answer and optional HTML detail.

Telegram, Lark, and email are source channels, not long-term memory topics. Their daily digest scripts should keep raw archives in source folders for auditability, then call `topic_distillation.py`. The topic distiller must filter obvious verification codes, login/security noise, newsletters, advertisements, and promotional messages before memory insertion; if the rule-based filter is unsure, call Qwen as the conservative gatekeeper and keep anything that may be lab-relevant. Kept records are classified into an existing notebook topic section when possible. Only records with no confident topic match should go to `Unsorted Communication Records`. Do not create new `Telegram Records`, `Lark Records`, or `Email Records` pages in the distilled index for routine memory.

## Lark Interface

Lark can be used as a group-memory and Q&A entrypoint:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_lab_senior_brother.py
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_daily_digest.py
```

The Lark account uses the international Lark platform, so the default domain is `https://open.larksuite.com`. Store App ID/App Secret at `/Volumes/ZZLab_AI/Key/Lark_App ID&Secret.txt` and event verification/encryption settings at `/Volumes/ZZLab_AI/Key/Lark加密策略.txt`. The private runtime config is `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/lark_bot_config.json`; the public example is `AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/references/lark_bot.example.json`.

Lark runs through the official `lark-oapi` Python SDK and WebSocket events, with an OpenAPI polling fallback enabled by default, so it does not need a public ngrok callback. Once the bot is added to a group, it records delivered or polled group messages by default under `/Volumes/ZZLab_AI/YYYY-MM-DD/lark文档和消息记录/<sender>_<chat>/`. To receive every message in a group instead of only direct mentions, the Lark app should still be granted the official scope `Read all messages in associated group chat` and subscribe to the `Receive message` event; polling is a resilience path when events are not delivered. In group chats it should remain quiet unless mentioned with `@大师兄` or called with explicit commands such as `/ask`, `/note`, `/help`, `/status`, or `/id`. In private chat it may answer directly when events are delivered or when the p2p chat is visible to polling / listed in `polling_extra_chat_ids`. Files and images are archived automatically; PDFs/text-like files get text/HTML previews, images get Qwen vision previews, and binary engineering files are stored as metadata-only attachments.

Use `lark_lab_senior_brother.py --check-online` for live diagnostics. `tenant_access_token_ok=true` validates the credentials; `bot_enabled=true` is required for chat install, message events, and replies. If Lark reports `app do not have bot`, the app's Bot capability is still missing even if other scopes were approved.

The Lark daily digest runs topic-first, like Telegram/email, and should feed kept records into existing notebook sections through `topic_distillation.py`.

## Gmail Interface

Forwarded email can be used as another memory intake path for 大师兄:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_ingest.py
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_daily_digest.py
```

The private mailbox is `ultracoldhku@gmail.com`. Store the Gmail app password only at `/Volumes/ZZLab_AI/Key/gmail_app_password.txt`, one line, no spaces. The private runtime config is `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/email_ingest_config.json`; the public example is `AI_Agent/Lab_Memory_Agent/config/gmail_email_ingest.example.json`.

The ingester reads new unread IMAP messages, skips known Google account-notification senders by default, archives raw `.eml`, readable HTML, body text, attachments, and extracted text under `/Volumes/ZZLab_AI/YYYY-MM-DD/email文件和邮件记录/<sender>/`. Text-like files and PDFs are extracted for future distillation; binary files are stored as metadata-only attachments. The daily digest writes a private daily HTML overview and then upserts topic supplement pages into `DEEPSEEK_DISTILLATION.json/html`.

If the app password file is missing, the ingester should exit cleanly with `missing_password_file` instead of failing or blocking other services. Never log or commit the Gmail app password.
