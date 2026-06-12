# Lab Big Brother

Portable, auditable AI memory infrastructure for laboratory work.

The project separates evidence, structured memory, search indices, and AI operating skills so the same knowledge base can move between computers and AI agents without depending on chat history.

## Core Layout

```text
AI_Agent/Lab_Memory_Agent/
  config/       example integration configuration
  entries/      structured, source-linked memory entries
  inbox/        staging area for exported documents
  indices/      rebuildable search indices
  schemas/      memory entry schema
  scripts/      ingestion, indexing, search, and OneNote sync
  skills/       AI operating workflows
  sources/      original evidence
```

## 实验室大师兄

`AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/` is the GPT-facing lab notebook query interface.

Use it when asking whether the lab has done something before and how it was done. The skill queries the Qwen-distilled notebook index first, then points back to the source HTML evidence.

Example:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/query_lab_notebook.py \
  "我们之前做过 DDS 验收吗？怎么做的？" \
  --include-source-snippets
```

Local web UI retired by default:

The browser UI script still exists for one-off local debugging, but the routine web entrypoint is stopped/disabled. Use Codex, Telegram, or Gmail forwarding for normal interaction. Do not expose the web UI through ngrok unless the user explicitly asks to re-enable it.

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py
```

Then open `http://127.0.0.1:8765/`. The browser talks to a local Python server; the Qwen API key is read only by the server and is not embedded in the HTML page.

The UI includes a `中文 / English` toggle for the final answer language.

Public sharing can be re-enabled only by explicit request, by running the same local server behind an ngrok tunnel. Keep the tunnel protected with Basic Auth and store runtime credentials only in local private configuration, never in Git:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/serve_lab_senior_brother.py \
  --access-user "$LAB_SENIOR_BROTHER_USER" \
  --access-password "$LAB_SENIOR_BROTHER_PASSWORD"
ngrok http 8765
```

The public URL may change when ngrok is restarted unless a reserved domain is configured. Anyone with the URL and Basic Auth credentials can query the notebook interface and may consume Qwen API quota.

Self-knowledge refresh:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py
```

After significant updates and handoff refreshes, run this script so 大师兄 re-distills its current code, docs, handoff, and service configuration into the private lab documentation and the `Lab Big Brother System` section of the notebook index.

Nightly notebook maintenance:

```bash
python3 AI_Agent/Lab_Memory_Agent/scripts/notebook_pipeline/daily_notebook_update.py
```

This can first merge a fresh incoming HTML export into the active HTML tree, skipping duplicate pages and copying only added or changed pages plus their referenced attachments. It then builds a fresh HTML manifest, compares it with the previous snapshot, writes timestamped JSON/Markdown change logs, and sends only added or modified pages to Qwen before merging those page records back into the distilled index. A macOS LaunchAgent can run the script every day at `00:00`; keep any cloud-sync command in private local configuration, not in Git.

Telegram entrypoint:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/telegram_lab_senior_brother.py
```

Store the BotFather token privately at `/Volumes/ZZLab_AI/Key/telegram_bot_token.txt`. The bot supports `/id`, `/ask`, `/note`, `/allow`, `/status`, and `/help`; lab access is gated by chat ID allow-list in the private Telegram bot config.

Telegram now uses a small local agent backend. Explicit commands still run directly, while other normal messages go through a Qwen router that selects only from a safe local tool registry: chat, notebook query, note capture, archived-file lookup, allow-list admin, help, and status. It does not expose arbitrary shell or filesystem access. Greetings and light social messages get a natural “大师兄已就位” style reply; lab questions query the notebook; `记` or `/note` writes a note; `开始记` switches that chat into record mode; and `停止记` switches back to query mode. Only durable records are kept long term by default: notes, uploaded files, mode changes, and admin actions. Ordinary queries, greetings, file requests, and unsupported requests are not persisted into the daily records; query-detail HTML is generated temporarily for sending and then discarded. Query replies use Qwen at runtime to inspect the distilled notebook directory, select evidence pages, and write the short answer; if Qwen finds no direct evidence, the bot should say it does not know instead of forcing an unrelated result. Any actual uploaded file, including Telegram photos/images, is archived automatically by date and sender, using the caption/current chat as context; text-like files, Markdown, HTML, CSV/JSON, and PDF files get text/HTML previews, while images get Qwen vision previews, and binary engineering files such as STEP or EXE are stored as metadata-only attachments.

Telegram, Lark, and email daily digests keep their raw archives by source, but Qwen memory indexing is topic-first. The nightly digest first filters out obvious verification codes, account-login/security noise, newsletters, advertisements, and promotional messages; when the rule-based filter is unsure, Qwen decides conservatively and keeps anything that may be lab-relevant. Kept records are classified against existing notebook sections such as equipment purchasing, ARTIQ, and the Yb experiment, then written as supplemental pages under those topics. Only records that cannot be confidently matched go to `Unsorted Communication Records`; `Telegram Records`, `Lark Records`, and `Email Records` are provenance channels, not long-term topic buckets.

Lark entrypoint:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_lab_senior_brother.py
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/lark_daily_digest.py
```

The Lark account uses the international Lark platform, so the default OpenAPI domain is `https://open.larksuite.com`. Store App ID/App Secret and event encryption settings privately under `/Volumes/ZZLab_AI/Key/`; the runtime config lives at `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/lark_bot_config.json`, and the public example is `AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/references/lark_bot.example.json`.

Lark uses a WebSocket event connection, so it does not need ngrok. Once the bot is added to a group, it records delivered group messages by default under `/Volumes/ZZLab_AI/YYYY-MM-DD/lark文档和消息记录/`. To receive every message in a group instead of only direct mentions, the Lark app must be granted the official scope `Read all messages in associated group chat` and subscribe to the `Receive message` event. In group chats the bot stays quiet unless mentioned with `@大师兄` or called with commands such as `/ask`, `/note`, `/help`, `/status`, or `/id`. In private chat it can reply directly. Uploaded files and images are archived like Telegram files: text-like files and PDFs get extracts, images get Qwen vision previews, and binary engineering files are stored as metadata-only attachments. The nightly Lark digest is topic-first and should supplement existing notebook sections instead of creating a durable `Lark Records` topic.

Install runtime dependencies with:

```bash
python3 -m pip install -r AI_Agent/Lab_Memory_Agent/requirements.txt
```

Gmail forwarding entrypoint:

```bash
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_ingest.py
python3 AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/email_daily_digest.py
```

The Gmail address is `ultracoldhku@gmail.com`. Store a Gmail app password privately at `/Volumes/ZZLab_AI/Key/gmail_app_password.txt`; never store a normal Google password or app password in Git. The ingester reads new unread mail through IMAP, skips known Google account-notification senders by default, archives each message under `/Volumes/ZZLab_AI/YYYY-MM-DD/email文件和邮件记录/<sender>/`, saves raw `.eml`, readable HTML, extracted text, and attachments, then the nightly digest adds that day's email records into the topic-based Qwen distillation. Text-like attachments and PDFs get text extracts; binary files are kept as metadata-only attachments.

To obtain the Gmail credential, sign in to the Google account, enable 2-Step Verification, then open Google Account Security -> App passwords. Create an app password for Mail, copy the 16-character password, and put that single line in `/Volumes/ZZLab_AI/Key/gmail_app_password.txt`. IMAP must be enabled in Gmail settings. If Google does not show App passwords for this account, use OAuth instead; do not disable account security to make IMAP work.

## Quick Start

```bash
cd AI_Agent/Lab_Memory_Agent
python3 scripts/rebuild_index.py
python3 scripts/search_memory.py "memory framework"
```

Place exported TXT, Markdown, HTML, MHTML, DOCX, or PDF files in `inbox/`, then run:

```bash
python3 scripts/ingest_exports.py
python3 scripts/rebuild_index.py
```

## Automatic Handoff

The `auto-handoff` skill maintains a concise current snapshot and an append-only local work log. After significant AI work, it can also commit and push public project changes to this repository.

The GitHub repository is public. Raw notebook exports, real memory entries, generated indices, local configuration, detailed work logs, and credentials are excluded by default. The complete operational record remains on the private shared volume.

## Repository

[ustcredapple-dotcom/Lab_Big_Brother](https://github.com/ustcredapple-dotcom/Lab_Big_Brother)
