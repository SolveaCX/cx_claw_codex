# POC 流程

## 阶段一：意图分类与 POC agent 创建

1. 通过 `poc/interfaces/classify.md` 完成分类：
   - 有 xlsx：分类用户数据。
   - 无 xlsx：使用固定 7 个标准意图。
2. 展示分类结果，等用户确认。
3. 通过 `poc/interfaces/create-agents.md` 执行 POC 业务阶段：
   - 创建全部意图。
   - 优先克隆 3 个固定业务 agent。
   - 如果预置 agent 找不到，询问用户从零新建还是使用其他现有 agent 替代，不要直接中断等待研发修复。
   - 预置可用时自动创建 3 条业务策略。
   - 用户确认替代方案后，通过 `--custom-agent-map` 将自定义/替代 agent 按业务 binding 写入策略。
   - 获取 `fallback_pending_intent_ids`。
4. 展示 intent / agent / strategy 表，等用户确认。

## 阶段一补充：兜底 chatflow agent

1. 通过 `agent-builder/interfaces/fallback-chatflow.md` 创建兜底 CHAT_FLOW agent。
2. 首版允许由 agent-builder reference 创建；POC 不维护 graph 细节。
3. 拿到 `agent_id` 后，通过 `poc/interfaces/create-agents.md` 执行 fallback-link。
4. 展示 fallback strategy 结果，等用户确认。

## 阶段二：知识库，可选

用户希望体验产品/政策问答时才进入。

1. 先读 `poc/references/kb-directory.md`，确定本次 POC 是否使用标准目录模板，还是用户显式目录 schema。
2. 通过 `kb-builder/interfaces/web-kb.md` 处理网页、帮助中心或文档站。
3. 通过 `kb-builder/interfaces/qa-upload.md` 处理现成 `qa_plan.json` 或 QA parts。
4. POC 只维护业务目录规范选择；crawl provider、QA 提取和上传实现仍归 `kb-builder`。

## 阶段三：批量测试 + POC 手册

1. 通过 `poc/interfaces/poc-test.md` 获取业务 agent 列表。
2. 跳过 Fallback agent。
3. 每个业务 agent 设计测试 case，展示给用户确认。
4. 执行 POC 测试。
5. 生成 POC 测试手册。

## 交付物

- 意图分类报告（HTML / Excel）。
- 已创建的 POC 意图、3 个业务 agent、1 个兜底 chatflow agent、4 条策略。
- 可选知识库目录与 QA。
- POC 测试手册 HTML。
