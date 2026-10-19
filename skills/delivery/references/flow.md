# Delivery 流程

## 阶段一：意图分类与正式 agent 创建

1. 通过 `delivery/interfaces/classify.md` 完成分类。
2. 展示分类结果，等用户确认。
3. 通过 `delivery/interfaces/create-agents.md` 执行 Delivery 创建：
   - 创建或复用 7 个标准意图 + 新发现 L1。
   - 优先按固定 binding 克隆广场 agent。
   - 如果固定广场 agent 找不到，询问用户从零新建还是使用其他现有 agent 替代，不要直接中断等待研发修复。
   - 预置可用时自动绑定策略。
   - 用户确认替代方案后，通过 `--custom-agent-map` 将自定义/替代 agent 按意图写入策略。
   - 默认更新订单工具 X-Token。
4. 展示 intent / agent / strategy 表，等用户确认。

## 阶段二：知识库搭建

Delivery 默认需要知识库；如果用户说明已完成，先通过 `list-directories` / `list-knowledge` 验证，不依赖本地 `kb_progress.json`。

1. 网页、官网、帮助中心：通过 `kb-builder/interfaces/web-kb.md`。
2. 现成 `qa_plan.json` 或 QA parts：通过 `kb-builder/interfaces/qa-upload.md`。
3. PDF / xlsx / 模板 / 导出等非网页能力仍归 `kb-builder` 自己判断，Delivery 不维护这些内部细节。

## 阶段三：批量回归测试

通过 `delivery/interfaces/delivery-test.md` 执行：

- 历史抽样出 cases。
- 或客户上传 xlsx/csv/json。
- `LIVE_CHAT` 默认，`EMAIL` 可选。
- 支持 partial 续跑。
- 输出 KPI HTML + MD。

## 交付物

- 意图分类报告（HTML / Excel）。
- 7 个标准意图 + agent + strategy。
- X-Token 已更新的订单工具。
- 完整知识库。
- KPI 回归报告（HTML + MD）。
