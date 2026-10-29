---
name: agent-tester
description: Use when directly testing, regression-testing, batch-testing, or checking Download Center progress for one Shulex Agent. Supports live_test single cases and system-native batch tests; CHAT_FLOW Agents use the canvas multi-turn batch-test path and other Agents use the menu batch-test path.
requires:
  libs: [solvea-api]
---

# Agent Tester

执行命令时，将 `<PLUGIN_ROOT>` 替换为当前 CXClaw 插件根目录，并统一通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 调用与插件同版本的 CLI；禁止直接调用 npm `latest`。
当前对话首次访问租户前，执行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" context init` 并保留返回的 `contextId`。随后执行租户业务命令（包括 reference 中的命令）时，必须自动追加 `--context <contextId>`；切换租户时执行带同一 `--context` 和命名 `--profile` 的 `tenant use`。只复用当前对话工具输出中的 `contextId`，不得借用其他对话或回退到全局最近租户；无法恢复时重新初始化 context。
本文件是完整文档目录。先根据请求定位到唯一工作流，然后**直接读取该工作流指定的最终文档**；不要逐层读取无关文档。

## 文档目录

| 用户场景 | 直接读取 | 说明 |
|---|---|---|
| 指定 Agent、单个问题、“随便测一下”、继续探索 | `single-test/direct-test.md` | 使用 `live_test` 运行固定 case 或探索式单轮 |
| 历史 ChatId、badcase 复测、验证修复或比较变化 | `single-test/badcase-retest.md` | 读取原会话，重放 USER 消息并比较 AgentAction |
| 多个 case、测试集、Excel、批测、下载中心进度 | `batch-test/overview.md` | 系统 xlsx 批测：Chatflow 多轮或普通 Agent 菜单批测 |

## 目录层级

```text
agent-tester/
├── SKILL.md
├── single-test/
│   ├── overview.md              # 单测公共 live_test 契约（仅 direct/badcase 文档需要时读取）
│   ├── direct-test.md           # 单问题与探索式测试
│   └── badcase-retest.md        # 历史 ChatId 复测
├── batch-test/
│   └── overview.md              # 系统批测工作流
└── CLI commands: `agent-tester create-sheet`, `agent-tester submit`, `agent-tester get-tasks`
    └── agent-tester      # 生成 xlsx、上传、提交、查询下载中心
```

批测必须提交系统下载中心任务，不要调用或复用 POC / Delivery 的本地并发脚本、状态、cases 协议或报告模板。
