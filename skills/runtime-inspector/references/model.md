# Model 场景详细说明

测试 LLM 在当前 endpoint 配置下的运行时行为。

---

## scenario `truncation` — max_tokens 截断诊断

### 背景

LLM 一次输出超过 endpoint 配置的 `max_tokens` 时会被强制停止（`stop_reason=max_tokens`）。
若被截断的恰好是 `tool_use` 调用的 input JSON，会出现 tool 入参不完整的错误，例如：

```
Error invoking tool 'write_file' with kwargs {'file_path': '...'} with error:
 content: Field required
```

`file_path` 已生成、`content` 还没生成完就被切断 → schema 校验失败。这种问题用日志才能定性。

### 触发方式

`model_inspect.py --scenario truncation` 让 LLM 主动构造一个**会消耗大量输出 token 的 write_file 调用**：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/model_inspect.py --scenario truncation
```

脚本只是**给 agent 一个引导文本**——告诉 agent 用 write_file 写一个长 markdown 内容到 `/workspace/tmp/runtime-inspector/truncation_test.md`，要求 ≥6000 字英文 lorem ipsum 段落。

是否真触发取决于当前 endpoint 的 `max_tokens` 配置：
- `max_tokens` ≤ 4096 → 几乎必触发
- `max_tokens` ≥ 16384 → 难触发，需要更夸张的 content（agent 可主动加大要求）

### 判定（看日志）

服务进程日志里搜 `SLG model_response`：

```
SLG model_response req=... chat=... stop_reason=end_turn output_tokens=3500 tool_calls=1
```

- `stop_reason=end_turn` / `tool_use`：正常完成，**没截断**
- `stop_reason=max_tokens` / `length`：**触发了截断**，会同时打 ⚠ warning 行：

```
⚠ SLG output truncated by max_tokens req=... output_tokens=4096 — increase endpoint max_tokens or split the work
```

### 修复方向

1. **endpoint 配置层**：`settings.local.yaml` / Nacos 给对应 endpoint 加 `max_tokens` 字段（claude sonnet/haiku 4 系列上限 64000，建议 32000）
2. **skill 流程层**：避免单次 LLM 输出超大 content。例如 kb-builder 的 qa_plan 应分批写到 `qa_plan_part_NN.json`，由脚本合并

---

## scenario `claude_proxy` — Claude Proxy 连通性

不属于 model domain，归在 sandbox（沙箱内通过 internal proxy 调 Claude），见 `references/sandbox.md`。
