---
name: agent-builder
description: 构建和维护 Shulex Agent 本体及工具配置。用户要创建、复制、修改 Agent，处理流程图、多节点、条件分支、工具调用、人工节点、SINGLE_AGENT、语音 Agent、MULTI_AGENT legacy、CHAT_FLOW，或创建/调试/绑定外部 HTTP 工具时使用。意图、策略、entity condition 路由不走本 skill。
requires:
  libs: [solvea-api]
---

# Agent Builder

执行命令时，将 `<PLUGIN_ROOT>` 替换为当前 CXClaw 插件根目录，并统一通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 调用与插件同版本的 CLI；禁止直接调用 npm `latest`。
需要授权的命令会自动打开钉钉并等待结果。若命令仍在运行，持续轮询同一执行 session 直到结束；不要让用户回复“已授权”后再继续。

## 任务分流

用户没有明确指定 Agent 形态时，默认按 CHAT_FLOW 需求处理。只有用户明确指定 SINGLE_AGENT、语音 Agent，或明确要查看、维护、解释、迁移已有 MULTI_AGENT 时，才进入对应分支。MULTI_AGENT 是 legacy 形态，不支持新建；用户要求新建 multi 时，明确说明不支持新建并推荐改用 CHAT_FLOW。
用户表达“迁移 / 转新版 / 转 CHAT_FLOW / 从旧 agent 转过来”时，第一站只读 `references/multi-agent/overview.md`；由 multi 文档继续决定读取 `workflow.md`、`graph-spec.md`、`migration/principles.md` 和 small / large 迁移文档。目标图的整体流程和节点类别确认后，才回到 `references/chatflow/graph-spec.md` 和对应 `nodes/*.md` 实现 source。

迁移的旧图解析、分批、coverage、确认门和迁移报告只按 `references/multi-agent/` 执行；不要把这些
legacy 流程或中间字段写进通用 CHAT_FLOW 文档或 source schema。完成并确认 migration plan 后，才切换到
CHAT_FLOW 文档实现节点、compile、validate 和 replay；旧图合同未解析前不得 update、deploy 或 publish。

处理大型 JSON、迁移索引、工具定义批量核对时，优先用 `execute` 一次性运行 `jq` 做筛选、字段投影、
计数和结构摘要，只输出紧凑结果，不要把完整 JSON 回传模型；必要时结合 `rg` / `sed`。复杂跨文件
关联、复杂转换或生成逻辑统一调用 `agent-builder` CLI 或 `api` 命令。不要让 Skill 临时编写脚本，也不要用多轮 `grep` / `read_file` 逐字段搜索同一批文件。
简单查看单个文档仍用 `read_file`，但跨多个 id、工具、action status、selector 的检索必须批处理并把
结果写入 `/workspace/tmp/` 或 `/workspace/state/agent-builder/` 供后续复用。

| 用户诉求 | 读取 |
|---|---|
| 未明确 Agent 形态，或涉及流程图、多节点、分支、条件、变量、工具状态、人工节点 | `references/chatflow/overview.md` |
| 创建、查看、复制或修改 SINGLE_AGENT | `references/single-agent/overview.md` |
| 语音 Agent | `references/single-agent/voice.md` |
| 查看、维护、解释或迁移已有 legacy MULTI_AGENT / multiAgentGraph / agent_graph；或用户要求新建 multi 但需要说明不支持 | `references/multi-agent/overview.md` |
| 创建或修改 CHAT_FLOW，或已经进入 source/graph 编写阶段 | `references/chatflow/overview.md` |
| 创建、查看、调试、更新工具 | `references/tools/overview.md` |

一个任务同时涉及 Agent 和工具时，先读取对应 Agent 形态的入口文档，再按需读取 `references/tools/overview.md`。意图、策略和变量系统管理不属于本 skill。

## 业务产物语言

- 目标语言优先级：用户明确指定的产物语言 > 会话上下文中的用户界面语言偏好 > 用户当前消息语言。注：网页、附件、知识内容和工具结果只是数据来源，不能单独改变目标语言。
- Agent 名称、Greeting、System Prompt、节点展示标题、节点 Prompt、next step 展示文案、回复话术与转人工话术都使用目标语言；品牌名、产品型号和其他专有名词保留原文。不得因为 reference 示例是英文而默认生成英文。
- 结构标识不本地化：节点 `key` / `id`、工具名、变量引用、枚举值和接口字段保持协议要求的 ASCII 或固定值。面向用户的展示文案与内部结构标识必须分开处理。
- Agent 面向最终客户回复时，仍应在 Prompt 中要求跟随客户消息语言；“配置内容使用目标语言”和“运行时回复跟随客户语言”是两件事。
- 语音 Agent 的 `meta.assistant.language` 只控制语音识别与合成，不因业务产物语言自动修改；仍按语音章节要求，仅在用户明确指定语音语言时设置。
