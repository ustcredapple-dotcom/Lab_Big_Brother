# ZZLab AI Project Instructions

These instructions apply to the entire `ZZLab_AI` shared volume.

## Start Every Work Session

1. Read `PROJECT_HANDOFF.md` first when it exists on the private shared volume.
2. Read `AI_Agent/Lab_Memory_Agent/manifest.yaml` and only the documents relevant to the immediate objective.
3. Treat files on this shared volume as the cross-device source of truth. Do not rely on chat history as the only record.

## Maintain The Handoff

Before the final response after significant work, load `AI_Agent/Lab_Memory_Agent/skills/auto-handoff/SKILL.md` and update the handoff. Significant work includes file changes, investigations, decisions, new or resolved blockers, and changes to next actions.

- Rewrite `PROJECT_HANDOFF.md` as a concise current snapshot.
- Append one idempotent session entry to `Document/AI_Agent_Migration_2026-06-11/conversation_records/WORK_LOG.md`.
- Refresh 大师兄 self-knowledge with `AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py` so the agent understands its own current architecture and work after each significant update.
- Do not log casual conversation or answers that leave project state unchanged.
- Do not paste full conversations or hidden reasoning. Record outcomes, evidence, decisions, blockers, changed paths, and executable next actions.
- Never record passwords, tokens, cookies, private keys, or unnecessary personal information.
- If the update fails, report that plainly instead of claiming the handoff is current.
- The updater should run the GitHub sync automatically. Confirm the push succeeded, or report that only a local commit was created.

## Public GitHub Boundary

The remote repository is public. Commit reusable framework code and public documentation only. Never force-add ignored files. Raw notebook exports, real memory entries, generated indices, local config, detailed work logs, and the private current handoff stay on the shared volume.

## Preserve Durable Knowledge

Use `AI_Agent/Lab_Memory_Agent/entries/` for durable facts that should be searchable later. Every factual memory entry needs source references. Rebuild `indices/memory_index.jsonl` after changing entries.

## Editing Rules

- Preserve user-created files and unrelated changes.
- Prefer relative paths in shared documentation so Windows and macOS can use the same records.
- Keep the current handoff short enough to understand in under one minute; put history in the work log.
