# Sandbox 场景详细说明

端到端验证沙箱的环境变量、目录结构、bash 执行链路、依赖库、跨轮持久化。

---

## 单轮检查

`sandbox_inspect.py` 支持全量或单项 scenario：

```bash
# 全量（默认，等价于 --scenario all）
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/sandbox_inspect.py

# 仅环境变量注入与安全校验
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/sandbox_inspect.py --scenario env

# 仅目录结构与读写权限
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/sandbox_inspect.py --scenario fs

# 仅 bash 执行路径行为（CWD、$WORKSPACE_DIR、相对路径写文件）
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/sandbox_inspect.py --scenario execute

# 仅虚拟路径行为（bash/Python 路径映射对齐）
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/sandbox_inspect.py --scenario paths

# 仅依赖库可用性
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/sandbox_inspect.py --scenario deps
```

### 各 scenario 检查内容

| scenario | 主要校验项 |
|----------|-----------|
| `env` | WORKSPACE_DIR 路径可写、SOLVEA_LIB_DIR 路径存在、Anthropic / OpenAI proxy 地址非真实端点、敏感变量安全 |
| `fs` | workspace/outputs/state/tmp 可写；mounted 目录逻辑只读（OS 可写属正常）；skills 文件只读 |
| `execute` | CWD 为沙箱根、bash 能读 $WORKSPACE_DIR/$SOLVEA_LIB_DIR、相对路径写文件 Python 可读、python3 来自 venv |
| `paths` | WORKSPACE/MOUNTED_USER/MOUNTED_TENANT 路径存在；OUTPUTS_DIR/STATE_DIR/TMP_DIR 父目录存在；bash/Python 路径写读互通 |
| `deps` | anthropic/httpx/pandas/openpyxl 等库是否可 import（不可用记录为 ⬜，非错误） |

---

## Internal Claude Proxy 测试

单独验证沙箱内能否通过 internal proxy 调用 Claude，不依赖 sandbox_inspect 全量：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/test_claude_proxy.py
```

打印 `ANTHROPIC_BASE_URL`、实际发一条 haiku 请求，输出 `PASS model=... in=... out=... elapsed=...s` 或 `FAIL error=...`。

## Internal OpenAI Proxy 测试

验证沙箱内能否通过 internal proxy 调用 OpenAI-compatible 模型：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/test_openai_proxy.py
```

模型由主服务的 Nacos 配置统一决定。输出 `PASS model=...` 表示代理与模型权限均正常。

---

## 持久化两轮测试

验证前一次对话写入的 outputs/state 在新对话中是否可用。**仅在用户明确要求时才执行，不要在单轮检查后自动继续。**

### 第一次对话：写入数据

#### 步骤 1 — 准备数据

```bash
# 有用户文件
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/prepare.py --source /mounted/chat-files/user/{文件名}

# 无用户文件（自动生成测试数据）
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/prepare.py
```

#### 步骤 2 — 处理并写入

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/process.py
```

#### 步骤 3 — 确认写入正常

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/sandbox_inspect.py --scenario fs
```

确认 `workspace/outputs/` 和 `workspace/state/` 均 ✅ 可写且有文件。

---

### 第二次对话：验证可用性

#### 步骤 A — 跑断言脚本（直接验证 eager 还原）

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/verify_persistence.py
```

脚本直接用 `Path.read_text()` 读 `OUTPUTS_DIR.glob("results_*.json")` 和 `STATE_DIR / "inspect.json"`，**全程不调用 `read_file` 工具**。

eager 模型保障：上一轮写入 `workspace/outputs/` 和 `workspace/state/` 的文件，本轮启动时已自动还原到同一路径，脚本直接 `open()` 就能读到。

- 全部 ✅ → eager 还原工作正常，跨轮路径稳定
- 出现 `FileNotFoundError —— eager 还原可能未生效` ❌ → 检查 `_build_file_manifest._restore` 流程 / Java 回调 / S3 上传

#### 步骤 B — 全量检查（可选）

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" script skills/runtime-inspector/scripts/sandbox_inspect.py --scenario fs
```

`fs` scenario 中"上一轮 agent outputs"项会显示 `workspace/outputs/runtime-inspector/` 下文件数量，可肉眼对照第一轮的 process.py 输出。

---

## 判断标准

| 检查项 | PASS 条件 |
|--------|-----------|
| `--scenario env` | RESULT: ✅ PASS，无 ❌ |
| `--scenario fs` | workspace 目录均 ✅ 可写，mounted 目录存在 |
| `--scenario execute` | CWD 对齐、bash 变量可读、写文件 Python 可读、python3 来自 venv |
| `--scenario deps` | 核心库（anthropic/httpx）✅，sandbox 组库不可用属正常 |
| 步骤 A read_file results | 返回内容包含 records 数组 |
| 步骤 B verify_persistence | 全部断言输出 ✅ PASS |
