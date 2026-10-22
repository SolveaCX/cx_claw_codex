---
name: runtime-inspector
description: Solvea Kit 运行时自检套件。覆盖沙箱机制、模型行为和 CXClaw 前端消息渲染。仅 canary/dev channel 启用。
---

# Runtime Inspector

执行命令时，将 `<PLUGIN_ROOT>` 替换为当前 CXClaw 插件根目录，并统一通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 调用与插件同版本的 CLI；禁止直接调用 npm `latest`。

执行前必须先调用 `cxclaw.capabilities`。只有返回 `runtime-inspector: true` 时才继续；stable channel 或生产环境必须拒绝执行。

按 **domain × scenario** 路由到具体测试入口。本 SKILL.md 只做路由，不写测试细节。

## 反问机制

用户说"测试运行时"/"自检"/"测沙箱"等模糊指令时，先反问让用户选 domain：

> 想测哪类？
> - **sandbox**：环境变量、目录挂载、虚拟路径、bash 执行链路、依赖库、跨轮持久化
> - **model**：LLM 输出截断（max_tokens）、Claude proxy 连通性
> - **frontend**：Markdown、消息气泡、连续工具过程、运行/完成/失败状态、Subagent 嵌套
>
> 或具体说"测目录持久化"、"测 max_tokens 截断"、"测依赖库"等具体场景，我直接执行对应 scenario。

如果用户已经说出具体场景关键词（"测挂载"、"测截断"、"测依赖"、"测 Markdown"、"测工具块"、"测 Subagent"、"全量测沙箱"、"全量测前端渲染"），直接走对应 scenario，不再反问。

frontend 请求同时命中 `markdown`、`process`、`subagent` 中两个及以上场景，或明确要求“完整/全量”时，统一路由到 `frontend × all`。

## 场景路由表

| domain | scenario | 触发关键词 | 入口 | 详细文档 |
|---|---|---|---|---|
| sandbox | env | 环境变量、注入、安全 | `runtime sandbox --scenario env` | `references/sandbox.md` |
| sandbox | fs | 目录、读写权限、挂载 | `runtime sandbox --scenario fs` | `references/sandbox.md` |
| sandbox | execute | bash 执行、CWD、相对路径 | `runtime sandbox --scenario execute` | `references/sandbox.md` |
| sandbox | paths | 虚拟路径、目录互通 | `runtime sandbox --scenario paths` | `references/sandbox.md` |
| sandbox | deps | 运行时依赖可用性 | `runtime sandbox --scenario deps` | `references/sandbox.md` |
| sandbox | persistence | 跨轮持久化（两轮测试） | `runtime prepare` + `runtime process` + `runtime verify` | `references/sandbox.md` |
| sandbox | claude_proxy | 沙箱内 Claude proxy 连通 | `runtime sandbox --scenario claude_proxy` | `references/sandbox.md` |
| sandbox | all | 沙箱全量（env+fs+execute+paths+deps） | `runtime sandbox` | `references/sandbox.md` |
| model | truncation | LLM 输出 max_tokens 截断诊断 | `runtime model --scenario truncation` | `references/model.md` |
| frontend | markdown | Markdown、标题、列表、表格、引用、代码块、链接 | Agent 按 reference 直接输出格式矩阵 | `references/frontend-rendering.md` |
| frontend | process | 工具块、连续工具、分组、运行、完成、失败、计时、折叠 | Agent 按 reference 调用真实工具 | `references/frontend-rendering.md` |
| frontend | subagent | Subagent、task、嵌套执行过程、内部消息 | Agent 按 reference 调用 `task` | `references/frontend-rendering.md` |
| frontend | all | 前端渲染、全量消息格式、完整验收 | 依次执行 markdown + process + subagent | `references/frontend-rendering.md` |

所有场景均通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs" runtime <action> [args]` 调用，不再依赖 Python 脚本。

## 详细执行步骤

- **沙箱场景**（输出判定标准 / 跨轮持久化分两轮的执行流）：`/skills/runtime-inspector/references/sandbox.md`
- **模型场景**（如何触发 max_tokens 截断、查日志判定结果）：`/skills/runtime-inspector/references/model.md`
- **前端渲染场景**（Markdown 矩阵 / 工具分组 / Subagent / 实时与历史一致性）：`/skills/runtime-inspector/references/frontend-rendering.md`
