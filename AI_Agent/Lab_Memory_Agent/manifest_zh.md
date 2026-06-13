# Lab Memory Pack manifest 中文说明

`manifest.yaml` 是这个记忆包的地图。它告诉 AI 和维护者：资料放在哪里、哪些东西可以公开、哪些规则必须遵守。

## 基本信息

- 名称：`lab-memory-pack`
- 版本：`0.1.0`
- 目标：保存实验室工作、文档、决策和实验记录，让它们可以在不同电脑和 AI 之间迁移。

## 主要路径

- `inbox`: 临时放导入资料的入口。
- `sources`: 原始证据。
- `entries`: 结构化记忆条目。
- `indices`: 可重建索引。
- `schemas`: 记忆条目格式。
- `skills/lab-memory/SKILL.md`: 通用记忆包操作说明。

## 交接配置

- 当前快照：`../../PROJECT_HANDOFF.md`
- 工作日志：`../../Document/AI_Agent_Migration_2026-06-11/conversation_records/WORK_LOG.md`
- 交接 skill：`skills/auto-handoff/SKILL.md`
- 规则：显著工作后更新交接。

## GitHub 配置

- 仓库：`https://github.com/ustcredapple-dotcom/Lab_Big_Brother`
- 分支：`main`
- 可见性：公开
- 交接后自动同步公开安全部分。
- 私有数据默认排除。

## 记忆条目规则

- 每条 factual memory 需要来源引用。
- 旧条目被替代时不要删除，标记 `superseded`。
- 默认置信度是 `medium`。
- 回答事实问题时需要引用证据。
- 不允许保存敏感数据。
- 必须维护项目交接。

## 支持的记忆类型

- notebook 页面
- 文档
- 实验
- protocol
- 结果
- 决策
- 会议
- 数据集
- 代码
- 仪器
- 想法
- 假设

## 索引文件

主要索引是：

```text
indices/memory_index.jsonl
```

索引应该可以从 `entries/` 重新生成，不应该把它当成唯一事实来源。
