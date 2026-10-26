---
name: solvea-kit
description: Shulex 路由与运营配置工具包。用于意图、策略、变量系统、AI 质检和标签树的查询与管理；也负责将 Agent/工具/CHAT_FLOW/知识库/测试/数据分析等需求分流到对应 skill。
---

# Solvea Kit

执行命令时，将 `<PLUGIN_ROOT>` 替换为当前 CXClaw 插件根目录，并统一通过 `node "<PLUGIN_ROOT>/plugin-cli.mjs"` 调用与插件同版本的 CLI；禁止直接调用 npm `latest`。
Solvea Kit 保留路由与运营相关配置：意图、策略、变量系统、AI 质检和标签树。Agent、工具、CHAT_FLOW、测试、知识库和分析类需求按下方分流。

## CXClaw CLI

已迁移的查询与写入操作统一使用“资源 + 动作”两层命令；只有尚未迁移的兼容命令才使用 `api <command>`：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" agent list --pretty
node "<PLUGIN_ROOT>/plugin-cli.mjs" intent create --data-file intent.json --pretty
# 临时兼容入口，Skill 不应为已迁移能力新增这种调用：
node "<PLUGIN_ROOT>/plugin-cli.mjs" api <legacy-command> --pretty
```

## 能力分流

| 用户诉求 | 去哪里 |
|---|---|
| 通用意图分类实现（供 POC / Delivery 调用） | `poc classify` / `delivery classify` |
| 意图创建、查询、更新、启停 | 本 skill：`references/intent.md` |
| 策略创建、查询、更新、启停、entity condition | 本 skill：`references/strategy.md` |
| 变量系统字段查询、初始化、创建、更新、删除、启停 | 本 skill：`references/variables.md` |
| AI 质检开关、规则、自定义规则、预警 | 本 skill：`references/quality-inspection.md` |
| 标签树 / 标签组 / 标签节点 / 批量导入 | 本 skill：`references/tagging.md` |
| SINGLE_AGENT / 语音 Agent / MULTI_AGENT / CHAT_FLOW / 工具配置 | `agent-builder` |
| CHAT_FLOW 图构建、校验、迁移 | `agent-builder` |
| 售前 POC 流程、POC 测试手册 | `poc` |
| 正式交付流程、交付回归 | `delivery` |
| 知识库内容、目录、QA、隔离关键词、回复模板库 | `kb-builder` |
| badcase、异常回复、失败节点，或按 ChatId / External ID 定位会话 | `shulex-support`（优先级高于所有数据分析入口，进入 Agent 会话诊断场景） |
| Agent 运营数据、指标、趋势、原始会话列表下钻（不要求解释异常根因） | `agent-analytics` |
| Shulex Desk 工单查询、报表和标签操作 | `solvea-desk` |
| 售后咨询、创建/查询/追加售后工单 | `shulex-support` |

## 核心约束（必须遵守，不用查文档也要记住）

1. **统一走 CLI** — 所有查询与写入都通过文档指定的 CLI；鉴权和调用目标由工程逻辑处理，agent 不读取、不切换、不解释底层配置。
2. **先查后改** — 更新任何资源前必须先 get 或 list 确认现状
3. **写入配置落 state** — 大 JSON 或待用户确认的配置写 `/workspace/state/solvea-kit/`，不要写 `/workspace/tmp/`
4. **写入操作需确认** — 修改线上数据前必须与用户确认

## 模块文档（按需读取）

遇到具体问题时，用 `read_file` 读取对应模块文档：

| 文档                                                    | 内容 | 何时读 |
|-------------------------------------------------------|------|--------|
| `/skills/solvea-kit/references/intent.md` | 意图管理 | 创建、更新、启用、禁用意图 |
| `/skills/solvea-kit/references/strategy.md` | 策略管理 | 创建、更新、启用、禁用策略；查看 entity condition |
| `/skills/solvea-kit/references/variables.md` | 变量系统管理 | 查询、初始化、创建、更新、删除、启停及使用边界 |
| `/skills/solvea-kit/references/quality-inspection.md` | AI 质检管理 | 查看质检、管理规则/自定义规则/预警 |
| `/skills/solvea-kit/references/tagging.md` | 标签树管理 | 标签组、标签节点、模板下载、批量导入 |

## 目录结构

```text
solvea-kit/
├── SKILL.md
├── references/
│   └──（标签导入和意图分类已迁移到 `workflow` CLI）
└── references/
    ├── intent.md
    ├── strategy.md
    ├── variables.md                 # 变量系统管理
    ├── quality-inspection.md        # AI 质检管理
    ├── tagging.md                   # 标签树管理
    ├── agent.md                     # 历史兼容，不作新入口
    ├── plugin.md                    # 历史兼容，不作新入口
    └── chat.md                      # 历史兼容，不作新入口
```

## 过时文档

以下文档暂时保留用于历史兼容，不作为新任务入口：

- `/skills/solvea-kit/references/agent.md`：已迁入 `agent-builder`
- `/skills/solvea-kit/references/plugin.md`：工具能力已迁入 `agent-builder`
- `/skills/solvea-kit/references/chat.md`：测试和会话分析已拆到 `poc` / `delivery` / `agent-analytics` / `shulex-support`
