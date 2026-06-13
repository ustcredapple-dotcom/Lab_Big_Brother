---
name: auto-handoff
description: Maintain the ZZLab_AI project's portable work handoff. Use after any significant project session, file change, investigation, decision, blocker change, or status change; before ending work or transferring the project to another AI; and whenever the user asks to record, summarize, or hand off work.
---

# Auto Handoff

Chinese human-readable companion: `SKILL_zh.md`.

Keep one concise current snapshot and one append-only work log so a new AI can resume without reading chat history.

## Workflow

1. Read the shared-root `PROJECT_HANDOFF.md` before working.
2. Treat work as significant when it changes files, decisions, current state, blockers, or next actions. Skip casual conversation and unchanged informational answers.
3. Prepare a UTF-8 JSON object containing:
   - `session_id`: stable unique ID for idempotency.
   - `actor`: AI or person completing the work.
   - `objective`: the immediate objective now handed off.
   - `state`, `completed`, `decisions`, `blockers`, `next_actions`, `files_to_read`, `changed_files`, `notes`: arrays of concise strings.
4. Run `scripts/update_handoff.py --input <json-file>`. The script finds the shared root from its installed location; use `--root <path>` only when testing or using a copied script.
5. The updater writes the English current snapshot at `PROJECT_HANDOFF.md` and a private Chinese human-readable snapshot at `Document/Human_Docs_ZH/PROJECT_HANDOFF_zh.md`.
6. Let the updater call `scripts/sync_github.py` after writing. Use `--no-github-sync` only for an explicit local-only operation.
7. Refresh 大师兄 self-knowledge after the handoff and GitHub sync, so it sees the final current snapshot:

```bash
python /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py
```

8. Verify `PROJECT_HANDOFF.md`, `Document/Human_Docs_ZH/PROJECT_HANDOFF_zh.md`, the newest work-log section, the self-knowledge page, and the Git push result before claiming the handoff is current.

## Content Rules

- Make `PROJECT_HANDOFF.md` sufficient for a new AI to choose the next action in under one minute.
- Record outcomes and reasons, not a transcript or hidden chain of thought.
- Keep each item independently understandable and name exact relative paths when relevant.
- Put only unresolved constraints in `blockers`; remove resolved blockers from the current snapshot.
- Order `next_actions` by priority and make the first action directly executable.
- Never record passwords, tokens, cookies, private keys, or unnecessary personal data.
- Create or update structured memory entries separately when a fact should be searchable as durable lab knowledge.
- Treat GitHub as public: rely on `.gitignore` and the sync script's deny rules, and never force-add private laboratory material.

## Example Input

```json
{
  "session_id": "2026-06-11-auto-handoff-v1",
  "actor": "Codex",
  "objective": "Import the first real ZZLab Notebook export",
  "state": ["Automatic handoff is installed and the memory index is operational."],
  "completed": ["Added the portable handoff workflow."],
  "decisions": ["Use a replaceable current snapshot plus an append-only work log."],
  "blockers": ["OneNote Graph access still requires delegated HKU login."],
  "next_actions": ["Test Graph PowerShell login on the Windows machine."],
  "files_to_read": ["PROJECT_HANDOFF.md"],
  "changed_files": ["AGENTS.md", "PROJECT_HANDOFF.md"],
  "notes": []
}
```
