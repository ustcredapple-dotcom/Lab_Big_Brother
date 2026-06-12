---
name: lab-senior-brother
description: Query and answer from the ZZLab lab notebook knowledge base. Use when the user asks whether the lab has previously done, tested, bought, designed, installed, debugged, measured, or decided something; asks "之前做过吗", "怎么做的", "证据在哪", "谁负责", "买过什么", "参数是多少", or wants a lab-memory/database steward for the HTML notebook and Qwen distillation. Also use for maintaining or refreshing the lab notebook HTML index and distilled lookup interface.
---

# 实验室大师兄

Act as the lab's notebook database steward: first query the distilled index, then inspect source HTML when needed, then answer with evidence.

## Core Workflow

1. Run the query script before answering factual notebook questions:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py \
  "USER QUESTION" \
  --include-source-snippets \
  --format json
```

2. Read the returned evidence. If the top evidence is weak, run 1-2 alternative keyword queries.
3. If the answer depends on a detail not present in the distilled evidence, open the cited HTML file and inspect the source text around the snippet.
4. Answer in this structure:

- Conclusion: whether the lab appears to have done it before (`yes`, `likely`, `unclear`, or `no evidence found`)
- How it was done: concise procedure, parameters, devices, people, or decisions found in the notebook
- Evidence: cite page titles and absolute HTML paths
- Caveats / next checks: mention uncertainty, missing data, or source pages to inspect

## Web Interface

To launch the local browser UI:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py
```

Then open `http://127.0.0.1:8765/`.

The browser never receives the Qwen API key. The local Python server reads the key, queries the notebook index, calls Qwen when enabled, and returns the answer plus source HTML links.

The UI has a `中文 / English` response-language toggle. Use it to force the final DeepSeek answer language regardless of whether the retrieved notebook evidence is Chinese or English.

For public access, run the local server with Basic Auth and expose port `8765` through ngrok:

```bash
LAB_SENIOR_BROTHER_USER="..." \
LAB_SENIOR_BROTHER_PASSWORD="..." \
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py

ngrok http 8765
```

Do not write the real ngrok authtoken, Basic Auth password, Qwen key, or notebook sharing secrets into this skill, GitHub, or handoff files. Public tunnels should be treated as temporary operational state unless a reserved ngrok domain is intentionally configured.

## Data Sources

For current paths and source hierarchy, read `references/data_sources.md` when needed.

Primary lookup index:

`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html_deepseek_distilled/DEEPSEEK_DISTILLATION.json`

Source HTML root:

`/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/html/active/Lab_Notebook_Original_2026-06-11/`

## Answering Rules

- Do not answer from memory when the question is about lab history; query first.
- Treat Qwen distillation as a navigation layer, not the source of truth.
- Prefer source HTML citations for final answers.
- Do not expose keys, passwords, cookies, or notebook sharing secrets.
- If no evidence is found, say so plainly and suggest likely query terms or source areas to inspect.
- Keep the tone practical and senior-labmate-like: direct, helpful, and traceable.

## Maintenance

When new notebook HTML exports are added:

1. Refresh `HTML_INDEX.html` and `HTML_MANIFEST.json` using `build_html_notebook_index.py`.
2. Refresh `DEEPSEEK_DISTILLATION.html/json` using `distill_html_with_deepseek.py` if external API use is approved. The file name is kept for compatibility; current default provider is Qwen.
3. Re-run this skill's query script on representative questions to verify retrieval quality.
4. Update `PROJECT_HANDOFF.md` and `WORK_LOG.md` after significant changes.

For routine maintenance, prefer the daily incremental updater:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/daily_notebook_update.py
```

It can merge a fresh incoming HTML export into the active HTML tree first, skipping duplicate pages so the notebook is not stored twice. It then compares the active HTML notebook against the previous snapshot, writes timestamped change logs, and sends only added or modified pages to Qwen before merging the refreshed page records into the distilled index. Use `--no-deepseek` only for baseline seeding or dry verification.

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

Telegram replies should stay brief and alive. The Telegram entrypoint now has a small local agent backend: explicit commands run directly, while other normal messages go through a Qwen router that may select only from a safe local tool registry (`chat`, `query_notebook`, `note`, `find_file`, `allow_chat_id`, `help`, `status`, or `unsupported`). It must not expose arbitrary shell or unrestricted filesystem access. Greetings, thanks, and simple presence checks should be handled by the Telegram personality layer instead of being sent to notebook search. Safe admin intents, such as adding a chat ID to the allow-list, should route to explicit local tools instead of notebook search. Persist only durable records by default: `note`, `file`, `mode`, and `admin`. Ordinary queries, greetings, file requests, and unsupported requests should not be kept in daily chat records, and query-detail HTML should be generated temporarily for sending rather than saved under the daily folder. Runtime Telegram queries should call Qwen on the distilled notebook directory to select evidence pages, then call Qwen again on the selected page details to write the short answer. Python may load files and assemble prompts, but it should not decide an answer from keyword scores alone. If Qwen finds no direct evidence, answer naturally that the notebook does not contain a clear record. Any actual Telegram file upload, including photos/images, is archived automatically under `/Volumes/ZZLab_AI/YYYY-MM-DD/telegram文件和聊天记录/<person>_<chat_id>/`, using its caption/current chat as context. PDF and text-like files are extracted into text/HTML previews, images get Qwen vision previews, and binary files such as STEP or EXE are stored without content extraction.

Telegram and email are source channels, not long-term memory topics. Their daily digest scripts should keep raw archives in source folders for auditability, then call `topic_distillation.py`. The topic distiller must filter obvious verification codes, login/security noise, newsletters, advertisements, and promotional messages before memory insertion; if the rule-based filter is unsure, call Qwen as the conservative gatekeeper and keep anything that may be lab-relevant. Kept records are classified into an existing notebook topic section when possible. Only records with no confident topic match should go to `Unsorted Communication Records`. Do not create new `Telegram Records` or `Email Records` pages in the distilled index for routine memory.

## Gmail Interface

Forwarded email can be used as another memory intake path for 大师兄:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_ingest.py
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_daily_digest.py
```

The private mailbox is `ultracoldhku@gmail.com`. Store the Gmail app password only at `/Volumes/ZZLab_AI/Key/gmail_app_password.txt`, one line, no spaces. The private runtime config is `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/email_ingest_config.json`; the public example is `AI_Agent/Lab_Memory_Agent/config/gmail_email_ingest.example.json`.

The ingester reads new unread IMAP messages, skips known Google account-notification senders by default, archives raw `.eml`, readable HTML, body text, attachments, and extracted text under `/Volumes/ZZLab_AI/YYYY-MM-DD/email文件和邮件记录/<sender>/`. Text-like files and PDFs are extracted for future distillation; binary files are stored as metadata-only attachments. The daily digest writes a private daily HTML overview and then upserts topic supplement pages into `DEEPSEEK_DISTILLATION.json/html`.

If the app password file is missing, the ingester should exit cleanly with `missing_password_file` instead of failing or blocking other services. Never log or commit the Gmail app password.
