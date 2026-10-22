# 从产品说明书 PDF 提取 QA

→ 通用质量规则见 `/skills/kb-builder/references/qa-quality.md`（必读）

## 读 PDF：直接用 `read_file`

**直接 `read_file` 读 PDF**，不要 inline `python3 -c "import pymupdf4llm..."`。read_file 工具内部已经把 PDF 解析链路封装好：

- 对 `.pdf` 后缀自动走 MinerU API（OCR + 结构识别）→ 失败或未配置 token 时 fallback 到 `pymupdf4llm`
- 解析结果按 markdown 返回，保留标题 / 段落 / 表格 / 列表 / 图片占位，已是 KB 期望的格式
- 同轮内缓存到 `workspace/tmp/parsed/{file_name}.md`，重复读不会重新解析
- 返回带行号 `lines X-Y of N`，长说明书用 `offset` / `limit` 分段读

```
read_file(file_path="/mounted/chat-files/user/manual.pdf")
# 长 PDF 分段：
read_file(file_path="/mounted/chat-files/user/manual.pdf", offset=0, limit=200)
read_file(file_path="/mounted/chat-files/user/manual.pdf", offset=200, limit=200)
```

⚠️ **单次返回上限 ~32K chars**。超出时 read_file 会直接报 "Requested range is too large" 并给建议 `limit`，按提示调小再读，不要试图绕过。

确认内容结构后，按下面规则拆 QA。

## 目录前置自查

提取前先 `list-directories` 看 Product Introduction 下是否已有本说明书产品的品类 / 型号目录。
缺品类（如新出的"Diagnostic Scanners"）或型号目录 → 用 `create-folder` CLI 补建（详见 directory.md §5）。
**不要回头跑全流程目录搭建**——补建单个目录就够了。

## 拆 QA 规则

对每份说明书，生成**两类** QA：

### 第一类：说明书全文 QA（每份说明书 1 条）

- Q：`[型号] — User Manual / Product Manual`
- A：完整解读说明书全部内容，**保留 PDF 中的图片、表格、排版结构**，格式规范清晰

```json
{
  "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
  "question": "Kasa EP25 Smart Plug — User Manual",
  "answer": "## Package Contents\n- 1x EP25 Smart Plug\n- 1x Quick Start Guide\n\n## Setup\n1. Plug into wall outlet\n2. Download Kasa app\n3. Follow in-app setup wizard\n\n## Specifications\n| Spec | Value |\n|------|-------|\n| Voltage | 120V AC |\n| Max Load | 15A / 1800W |\n| Dimensions | 2.1\" x 1.4\" x 1.4\" |"
}
```

### 第二类：说明书潜在问题（按内容密度拆，**不设条数上限**）

按说明书的独立子主题逐一拆 QA——每个独立功能 / 设置项 / 配件 / 故障排查问题都各成一条。覆盖参考维度：

- 产品概述（What is X / Key features）
- 包装清单 / 配件
- 技术规格 / 兼容性 / 适配范围
- 安装 / 连接 / 首次设置
- 各独立功能的使用步骤（按章节拆，每个功能 1 条）
- 设置项（语言 / 单位 / WiFi / 自检 / 恢复出厂等）
- 软件更新流程
- 故障排查（每个独立问题 1 条）
- 安全 / 警告事项（如有）

> 一份功能丰富的说明书（多功能诊断仪、多模式智能设备等）拆出 15~30 条 QA 是常见的；**不要为了控制条数把多个独立功能塞进同一条 answer**。同一功能的多个步骤可合并；不同功能必须拆开。

```json
[
  {
    "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
    "question": "Kasa EP25 Smart Plug — What accessories are included in the box?",
    "answer": "- 1x Kasa EP25 Smart Plug\n- 1x Quick Start Guide"
  },
  {
    "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
    "question": "Kasa EP25 Smart Plug — How do I install and set up the EP25?",
    "answer": "1. Plug the EP25 into any standard 120V wall outlet\n2. Download the Kasa Smart app\n3. Tap '+' to add a new device\n4. Follow the in-app setup wizard to connect to Wi-Fi"
  }
]
```

## 产出文件（每批写到 tmp）

提取的 QA **不要**自己合并成 qa_plan，**也不要**一次 write_file 写完整数组。
每批 ≤ 4 KB 写到 `/workspace/tmp/kb-builder/qa_parts/qa_pdf_<model>_<part>.json`，
最后由 `kb-builder import-qa --from-dir /workspace/tmp/kb-builder/qa_parts/` 自动合并 + 上传。

详见 `/skills/kb-builder/references/upload.md`。

## 常见错误

| 错误 | 正确做法 |
|------|----------|
| inline `python3 -c "import pymupdf4llm..."` | 直接 `read_file(file_path="...pdf")` |
| 说明书只按段落切 QA | 必须生成两类：全文 1 条 + 按内容密度拆潜在问题 |
| 说明书潜在问题被压到 5 条以内、多个独立功能塞进同一条 answer | 无 ≤5 上限，每个独立功能 / 设置项 / 故障排查 / 配件主题独立成条 |
| 缺品类目录就归到 Pending Assignment | 优先 `create-folder` 补建对应品类 / 型号目录 |
