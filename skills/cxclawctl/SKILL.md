---
name: cxclawctl
description: CXClaw 插件 CLI 的统一运行规范：自动登录、初始化和携带会话 context，按指定租户安全执行业务命令。用于任何需要调用 CXClaw plugin-cli.mjs 的任务。
---

# cxclawctl 运行规范

这个 Skill 只负责“如何使用 CXClaw CLI”，不承载 Agent、知识库、测试等具体业务流程。业务 Skill 需要调用 CXClaw CLI 时，遵循本规范。

## CLI 入口

所有命令统一使用：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" <command>
```

不要改用旧的 marketplace CLI、全局 `cxclawctl`、远程 MCP、Python 代理脚本或用户自行拼接的服务地址。下述辅助脚本只组合调用此公开入口，不替代 CLI 的鉴权、context 或接口实现。

## 批量查询与辅助脚本

优先复用现有命令。对于批量查询、核验、分析或文件处理任务，可以在本地工作区编写辅助脚本，组合调用当前 skill 文档公开的 CLI 并处理返回数据；每条租户业务命令仍须携带当前会话的 `--context <contextId>`。控制并发、内存占用和执行时长，只向上下文返回必要摘要，不得绕过权限、写入确认或调用未公开接口。

- 查询范围应匹配用户目标，避免无关扫描；明确要求全量核验时，分批执行并报告覆盖情况，不因数据量大就改成抽样或缩短时间范围。遇到实际资源或接口限制时，说明已完成范围和缺口，再与用户协商。
- 大文件、批量原始数据和可重新生成的中间结果放工作区 `tmp/`；仅将需跨轮复用的小脚本、任务参数、进度和必要摘要存入 `state/<skill>/`，最终交付物放 `outputs/`。使用当前本地工作区的实际绝对路径，不假定线上沙箱的 `/workspace/` 存在。
- 临时数据不作为持久保证；续跑先检查依赖数据是否仍在，缺失则重新获取，不能仅凭已保存的进度认定数据可用。不得将凭据写入脚本、进度或数据文件。

## 登录与首次初始化

1. 先执行 `auth status`。如果已经登录，继续使用当前登录态。
2. 如果返回 `error.reason=not_authenticated` 或 `loggedIn=false`，由 AI 自己执行一次：

   ```bash
   node "<PLUGIN_ROOT>/plugin-cli.mjs" auth login
   ```

   这是持续运行到授权成功、失败或过期的长命令。用户只需要在 CLI 打开的 DingTalk 页面完成授权，不需要执行任何终端命令，也不需要回复“已授权”。
3. 如果执行工具返回 `session_id`，必须用同一个 `session_id` 持续读取，直到 `auth login` 退出。不要另起 `auth status`，不要并行启动第二个登录命令。
4. 登录成功后执行 `context init`，保存本次对话得到的 `contextId`。只复用当前对话中的 `contextId`，不得借用其他对话的 context，也不得回退到机器级最近租户。
5. 原业务命令因未登录失败时，登录成功后只自动重试原命令一次；第二次仍失败就报告实际错误。

不得代替用户点击授权，不得输出或记录 access token、refresh token、business token 或完整授权响应。

## context 与租户隔离

- 每个会话维护自己的 `contextId`。后续每条需要租户的命令都追加 `--context <contextId>`。
- 用户给出的租户线索可能是以下任一种结构：
  - `accountId`：纯数字正整数，例如 `488592`。
  - `accountCode`：短标识，通常由字母和数字组成，例如 `V75400`、`R53308`。
  - 公司名：自然语言名称，可能只给出部分名称、简称或中英文名称，不要求与搜索结果完全一致。
- 收到租户线索后，先将用户原文传给 `tenant search`。结合输入结构和候选的 `accountId`、`accountCode`、`accountName` 判断：ID 和 code 优先精确对应；公司名允许按语义、简称和包含关系判断。只选择 `status=1` 的租户。
- 只有一个候选与用户意图明确一致时，才把该候选的 `accountId` 传给 `tenant use`。多个候选都合理时，向用户展示候选的 `accountId`、`accountCode`、`accountName` 并要求选择，不得默认使用第一条。
- 已有目标 `profileId` 时使用 `context use <profileId> --context <contextId>`；用户只给出租户线索时完成上述搜索，再用 `tenant use <accountId>` 创建或刷新 profile 并绑定当前 context。不要修改其他会话的 context。
- 需要一次性覆盖租户时，可显式追加 `--profile <profileId>`。解析优先级是命令级 `--profile`，再到 `--context` 的 active profile；无法确定时直接失败。
- 业务操作前可执行 `context current --context <contextId>`，确认并向用户展示 `contextId`、`profileId`、`accountId`、`environment` 和 `purpose`。
- 未登录时不得调用 `tenant.current`。完成 `context use` 或 `tenant use` 后，先用 `context current --context <contextId>` 确认目标租户，再调用 `tenant.current({ contextId })` 显示当前会话的租户卡片。
- 每次切换租户成功后重新调用 `tenant.current({ contextId })`。不得省略 `contextId`，不得复用其他会话创建的租户卡片。
- 不把 tenant token 写入 `process.env`，不从全局“当前租户”猜测业务归属。

## 安装后自检

首次安装或升级插件后，在登录并选择目标租户前后按需执行：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" doctor
node "<PLUGIN_ROOT>/plugin-cli.mjs" update --install-scheduler
```

只有两个命令都成功，才能报告本地环境安装完成。普通业务请求不需要重复执行这两个命令。

常用命令：

```bash
node "<PLUGIN_ROOT>/plugin-cli.mjs" context init
node "<PLUGIN_ROOT>/plugin-cli.mjs" context current --context <contextId>
node "<PLUGIN_ROOT>/plugin-cli.mjs" context use <profileId> --context <contextId>
node "<PLUGIN_ROOT>/plugin-cli.mjs" profile list
node "<PLUGIN_ROOT>/plugin-cli.mjs" tenant search "关键词" --env prod
node "<PLUGIN_ROOT>/plugin-cli.mjs" tenant use <accountId> --env prod --purpose "用途" --profile <profileId> --context <contextId>
```

## 写操作

- preview 和 commit 必须使用同一个 `contextId`，并在提交前确认 active profile 没有变化。
- 先执行写命令的 `--phase preview`，展示服务端预览并等待用户明确确认。
- 确认后才使用 `--phase commit --confirmation-token-stdin --idempotency-key <key>` 提交。
- 不把确认凭证写入命令参数、文件或日志；不要在 preview 未成功时提交。

## 输出与失败处理

完成业务操作时，在不泄露凭据的前提下说明当前 `contextId` 和租户摘要。遇到 `not_selected`、`expired`、`unavailable` 或 context 缺失时，停止业务请求并先修复 context/profile；不得静默选择其他租户。

- 根据错误信息、skill/reference 或 CLI help 修正参数或调整公开方法，继续完成任务；没有可行路径时如实说明，继续不受影响的部分。
- 不要无依据地反复重试、猜测接口或编写调试脚本绕过失败。调整方法仍须保持用户目标、查询范围和授权边界。
- 不要翻阅插件实现源码或调用私有方法探究业务命令用法；不要为排查业务命令探测环境变量、系统目录或凭证。登录、context 修复和安装自检使用上文的公开命令。
