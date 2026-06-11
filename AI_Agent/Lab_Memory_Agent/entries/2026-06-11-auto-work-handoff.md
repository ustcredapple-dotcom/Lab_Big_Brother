---
id: auto-work-handoff-v1
title: ZZLab AI 自动工作交接机制
type: decision
status: active
date: 2026-06-11
projects: [ai-memory-framework]
people: []
tags: [handoff, automation, documentation, workflow]
source_refs: [../../PROJECT_HANDOFF.md, ../../AGENTS.md, skills/auto-handoff/SKILL.md]
confidence: high
summary: 重要工作结束前，AI 必须更新当前交接快照并向工作日志追加一条幂等记录。
---

## Decision

ZZLab AI 项目采用两层自动交接：

- `PROJECT_HANDOFF.md` 保存简短、可覆盖更新的当前状态。
- `Document/AI_Agent_Migration_2026-06-11/conversation_records/WORK_LOG.md` 保存只追加的历史记录。

盘根目录的 `AGENTS.md` 要求 AI 在重要工作结束前执行 `skills/auto-handoff`。脚本使用稳定的 `session_id` 避免重复写入。

## Rationale

当前状态与历史记录分离后，新 AI 可以快速了解下一步，同时仍可审计过去完成的工作和决策。项目记录不再依赖某个客户端的聊天历史。

## Boundaries

- 闲聊和未改变项目状态的回答不写入。
- 不保存密码、token、cookie、私钥或隐藏推理。
- 可长期查询的实验知识仍然进入独立 memory entries，并保留来源。
