# Lab Big Brother RAG Architecture

## What RAG Means Here

RAG means retrieval-augmented generation:

1. Retrieve relevant evidence from the lab memory store.
2. Let an LLM reason over that evidence.
3. Answer with traceable citations and explicit uncertainty.

For Lab Big Brother, RAG is not a keyword search box. It is an evidence pipeline for answering questions such as "之前做过吗", "怎么做的", "参数是多少", "谁负责", and "证据在哪".

## Current State

The system already has a partial RAG loop:

- Source material is preserved as HTML notebook pages and daily Telegram/Lark/email archives.
- Qwen distills pages into a compact JSON/HTML directory.
- Telegram and Lark use Qwen to select evidence pages from the distilled directory, then Qwen writes a short answer from selected evidence.
- The CLI `query_lab_notebook.py` now defaults to the same Qwen RAG evidence-selection path; the old weighted keyword search is still available with `--engine lexical`.

This is better than plain text lookup, but it is still page-level RAG. The main missing layer is chunk-level semantic retrieval.

## Target Architecture

The desired mature RAG stack is:

1. Ingestion
   - Keep raw source files private and unchanged.
   - Convert readable source material into clean text/HTML.
   - Preserve source path, channel, date, author/sender, page title, attachment path, and content hash.

2. Chunking
   - Split notebook pages, digests, email bodies, Lark/Telegram records, PDFs, and text attachments into evidence chunks.
   - Use stable chunk IDs.
   - Keep enough surrounding context for lab procedures and parameters.

3. Indexing
   - Store a rebuildable chunk index under private generated memory.
   - Each chunk should include text, summary, tags, topic section, timestamp, source path, and source hash.
   - Add semantic vectors when an approved embedding provider is configured.
   - Keep a lexical fallback for exact part numbers, dates, vendor names, and filenames.

4. Retrieval
   - Use hybrid retrieval: semantic vector search plus lexical/BM25-style exact matching.
   - Expand lab aliases, e.g. "烤真空" -> "真空烘烤", "finess" -> "finesse", "腔精细度" -> "cavity finesse".
   - Return candidate chunks, not just pages.

5. Reranking
   - Ask Qwen to rerank candidate chunks for direct answerability.
   - Reject weak matches instead of forcing unrelated answers.

6. Answering
   - Give a concise natural answer.
   - Cite source titles and paths.
   - Say "师兄我也不知道" when evidence is absent or ambiguous.
   - Never expose credentials or unrelated personal data.

7. Feedback
   - Log failed queries and missed aliases without storing casual chat.
   - Use those failures to improve chunking, aliases, and topic classification.

## Operational Rule

All user-facing interfaces should call the same RAG engine:

- Codex skill / CLI
- Telegram bot
- Lark bot
- Local debug web UI if re-enabled

Do not let one interface use a purely mechanical keyword search while another uses Qwen-based evidence selection.

## Near-Term Implementation Plan

1. Consolidate the current duplicated Qwen retrieval code into one shared `rag_query_engine.py`.
2. Build a private chunk index from the distilled notebook plus source HTML.
3. Add chunk-level retrieval and Qwen reranking.
4. Migrate Telegram/Lark/CLI to the shared engine.
5. Add regression questions such as:
   - `cavity 的 finesse 是多少`
   - `我们烤过真空吗`
   - `DDS 怎么验收`
   - `实验室有几台电脑`
6. Add a query-failure log for "should know but did not know" cases.
