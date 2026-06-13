# 自动交接中文说明

`auto-handoff` 的目标是让下一个 AI 不用读聊天历史，也能在一分钟内知道项目现在是什么状态、刚做了什么、下一步应该做什么。

它维护两类文件：

- 当前快照：`PROJECT_HANDOFF.md`
- 追加式工作日志：`Document/AI_Agent_Migration_2026-06-11/conversation_records/WORK_LOG.md`

## 工作流程

1. 开始工作前读共享根目录的 `PROJECT_HANDOFF.md`。
2. 判断这次工作是否显著。显著工作包括：改文件、调查问题、做决策、发现或解决 blocker、改变下一步行动。
3. 准备一个 UTF-8 JSON，包含：

   - `session_id`: 稳定唯一 ID，用来避免重复写入。
   - `actor`: 完成工作的人或 AI。
   - `objective`: 本次交接的直接目标。
   - `state`: 当前状态。
   - `completed`: 已完成事项。
   - `decisions`: 做出的决策。
   - `blockers`: 仍然存在的阻塞。
   - `next_actions`: 下一步行动。
   - `files_to_read`: 下个 AI 应该先读的文件。
   - `changed_files`: 本次改动文件。
   - `notes`: 其他简短说明。

4. 运行：

```bash
python3 /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/auto-handoff/scripts/update_handoff.py --input <json-file>
```

也可以用标准输入：

```bash
python3 /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/auto-handoff/scripts/update_handoff.py --input -
```

5. updater 会写两份当前快照：英文 `PROJECT_HANDOFF.md`，以及私有中文人类版 `Document/Human_Docs_ZH/PROJECT_HANDOFF_zh.md`。
6. 默认让 updater 自动调用 GitHub 同步脚本。只有明确要本地更新时，才用 `--no-github-sync`。
7. 交接和 GitHub 同步后，刷新大师兄自我认知：

```bash
python3 /Volumes/ZZLab_AI/AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py
```

8. 最后确认：

- `PROJECT_HANDOFF.md` 已更新。
- `Document/Human_Docs_ZH/PROJECT_HANDOFF_zh.md` 已更新。
- `WORK_LOG.md` 有最新条目。
- 大师兄自我说明书已刷新。
- GitHub push 成功，或明确说明只完成本地 commit。

## 内容规则

- `PROJECT_HANDOFF.md` 要短小清晰，让新 AI 一分钟内能决定下一步。
- 记录结果和原因，不记录完整聊天或隐藏推理。
- 每条内容要能独立看懂，相关文件使用明确路径。
- `blockers` 只写还没解决的问题。
- `next_actions` 按优先级排序，第一条应该能直接执行。
- 永远不要记录密码、token、cookie、私钥或不必要个人信息。
- 需要长期可检索的实验室事实，应另建结构化 memory entry。
- GitHub 是公开仓库；依赖 `.gitignore` 和同步脚本安全检查，不要强行提交私有实验室材料。

## JSON 示例

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
