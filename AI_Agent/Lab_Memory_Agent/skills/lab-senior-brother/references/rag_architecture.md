# Lab Big Brother RAG Architecture

## What RAG Means Here

RAG means retrieval-augmented generation:

1. Retrieve relevant evidence from the lab memory store.
2. Let an LLM reason over that evidence.
3. Answer with traceable citations and explicit uncertainty.

For Lab Big Brother, RAG is not a keyword search box. It is an evidence pipeline for answering questions such as "之前做过吗", "怎么做的", "参数是多少", "谁负责", and "证据在哪".

## Current State

The system now has a shared chunk-level local RAG loop:

- Source material is preserved as HTML notebook pages and daily Telegram/Lark/email archives.
- Qwen distills pages into a compact JSON/HTML directory.
- `rag_query_engine.py` builds a private local chunk index under `/Volumes/ZZLab_AI/Document/Lab_Notebook_Processing/rag_chunk_index/`.
- Notebook pages, source HTML, Telegram/Lark records, Gmail records, PDFs, text files, Markdown/HTML/CSV/JSON, and Qwen vision image previews are split into small evidence chunks.
- Qwen `text-embedding-v4` embeddings plus weighted lexical recall provide hybrid retrieval; Qwen then reranks candidate chunks for direct answerability and writes the short answer.
- Telegram, Lark, and the CLI use the same shared chunk RAG engine. The older page-level Qwen evidence selector remains only as a fallback if chunk RAG fails.
- Daily notebook, Telegram, Lark, and email digest scripts refresh the chunk index after new memory is distilled.
- Evidence is redacted before indexing and before query-detail rendering to avoid exposing passwords, tokens, API keys, and verification codes.

The old weighted keyword search is still available only for debugging with `query_lab_notebook.py --engine lexical`.

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

## RAGFlow Option

RAGFlow is a good candidate for a future heavy backend because it provides a UI, document parsing, template chunking, multiple recall, reranking, grounded citations, and APIs. It should be treated as an optional backend rather than an immediate replacement for the lightweight local RAG, because the current Mac has no Docker runtime installed and is ARM64 while RAGFlow's public prebuilt Docker images are x86-focused. Official self-hosting prerequisites include Docker/Compose, at least 16 GB RAM, and at least 50 GB disk.

Recommended integration path:

1. Keep the local chunk RAG as the default production path for Telegram/Lark/email.
2. Deploy RAGFlow only after Docker Desktop, OrbStack, or Colima is installed and verified.
3. Use RAGFlow as an experimental backend fed by the same normalized HTML/text exports.
4. Add a backend switch in `query_notebook`: `local_chunk` by default, `ragflow` when the RAGFlow API is configured and healthy.
5. Compare answers on regression questions before switching any live interface.

## AnythingLLM Option

AnythingLLM is a lighter candidate than RAGFlow for a ready-made RAG backend. It provides a desktop app, Docker/self-hosting paths, a developer API, built-in document pipelines, default LanceDB vector storage, many LLM/embedder integrations, source citations, agents, and optional telemetry controls. It is a better near-term candidate if the lab wants an off-the-shelf RAG UI without the full RAGFlow stack.

Implemented adapter:

- `rag_query_engine.py` supports `rag_engine=anythingllm`.
- It calls AnythingLLM's workspace chat API at `/api/v1/workspace/{slug}/chat` with `mode=query` by default, which keeps answers grounded in workspace sources.
- Secrets are read from `anythingllm_api_key`, `ANYTHINGLLM_API_KEY`, `anythingllm_api_key_path`, or `Key/AnythingLLM API Key.txt`.
- Required runtime config: `anythingllm_base_url`, `anythingllm_workspace_slug`, and an API key. The default base URL is `http://127.0.0.1:3001/api`.

Recommended integration path:

1. Keep the local chunk RAG as the production path until AnythingLLM is installed and regression-tested.
2. Prefer AnythingLLM Docker/API or bare-metal server mode for Telegram/Lark/email integration. The desktop app is useful for human browsing but is less ideal as a service backend.
3. Disable telemetry if running it on private lab material.
4. Feed it normalized HTML/text exports generated by the existing pipeline instead of raw secrets or private config.
5. Switch live config to `rag_engine=anythingllm` only after AnythingLLM health checks, ingestion, retrieval, citations, and latency are verified.

## Regression Questions

Use these after retrieval changes:

- `cavity 的 finesse 是多少`
- `我们烤过真空吗`
- `DDS 怎么验收`
- `实验室有几台电脑`
