---
name: lab-memory
description: Use this skill when answering questions from a portable lab memory pack made of source documents, structured memory entries, and rebuildable indices.
---

# Lab Memory

Chinese human-readable companion: `SKILL_zh.md`.

This skill is a thin operating guide for a portable AI memory pack. The memory itself lives in `entries/`, with raw evidence in `sources/` and rebuildable indices in `indices/`.

## Workflow

1. Read `manifest.yaml` to understand paths and policies.
2. Search `indices/memory_index.jsonl` first when available.
3. Load only the most relevant `entries/*.md` files.
4. Use `source_refs` to cite evidence or inspect raw material in `sources/` when needed.
5. Answer with uncertainty when records are missing, stale, low confidence, or conflicting.

## Answer Rules

- Give the direct answer first.
- Cite memory entry IDs or source paths for factual claims.
- Treat `hypothesis` and `confidence: low` as uncertain.
- Do not silently ignore `status: superseded`; prefer the newer entry if linked.
- If two entries conflict, report the conflict instead of inventing a synthesis.
- Do not expose sensitive content unless the user is authorized and the memory pack policy allows it.

## Maintenance

When adding new memory:

1. Preserve the raw source in `sources/`.
2. Create a small entry in `entries/`.
3. Include stable `id`, `type`, `status`, `date`, `source_refs`, `confidence`, and `summary`.
4. Rebuild indices with `scripts/rebuild_index.py`.

When updating memory:

- Prefer adding a new entry and marking the old one `superseded`.
- Keep old records available for audit.
- Never remove source references while facts still depend on them.
