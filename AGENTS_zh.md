# ZZLab AI 项目协作规则

这些规则适用于整个 `/Volumes/ZZLab_AI` 共享盘。人类和 AI 都应该按这里的边界做事。

## 每次开始工作先读什么

1. 先读 `PROJECT_HANDOFF.md`，了解当前项目状态。
2. 再读 `AI_Agent/Lab_Memory_Agent/manifest.yaml`，以及和本次任务直接相关的文档。
3. 把共享盘里的文件当作跨设备、跨 AI 的事实来源。不要只依赖聊天历史。

## 如何维护交接

显著工作结束前，必须加载 `AI_Agent/Lab_Memory_Agent/skills/auto-handoff/SKILL.md` 并更新交接。显著工作包括：改文件、调查问题、做决策、发现或解决 blocker、改变下一步行动。

需要做到：

- 更新 `PROJECT_HANDOFF.md`，让它保持短小、当前、可快速接手。
- 向 `Document/AI_Agent_Migration_2026-06-11/conversation_records/WORK_LOG.md` 追加一条幂等工作日志。
- 运行 `AI_Agent/Lab_Memory_Agent/skills/lab-senior-brother/scripts/update_self_knowledge.py`，让大师兄理解自己的最新架构和工作状态。
- 不记录闲聊或没有改变项目状态的普通问答。
- 不粘贴完整聊天记录或隐藏推理过程，只记录结果、证据、决策、blocker、改动路径和可执行下一步。
- 永远不要记录密码、token、cookie、私钥或不必要的个人信息。
- 如果交接更新失败，要如实报告，不要声称已经同步。
- 更新脚本默认会同步 GitHub。需要确认 push 成功；如果只创建了本地 commit，也要说明。

## 公开 GitHub 边界

GitHub 仓库是公开的。只能提交可复用框架代码和公共文档。

不要提交：

- 原始 notebook 导出。
- 真实实验室记忆条目。
- 生成索引。
- 本地配置。
- 详细工作日志。
- 任何凭据或私密数据。

## 长期知识怎么保存

需要以后可检索的事实，放进 `AI_Agent/Lab_Memory_Agent/entries/`。每条事实都需要来源引用。

改动 entries 后，重建：

```bash
AI_Agent/Lab_Memory_Agent/indices/memory_index.jsonl
```

## 编辑规则

- 保留用户创建的文件和无关改动，不要随手回滚。
- 共享文档里尽量用相对路径，方便 Windows 和 macOS 共用。
- 当前交接要短到一分钟内能读懂；历史细节放工作日志。
