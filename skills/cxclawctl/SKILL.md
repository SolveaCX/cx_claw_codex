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

不要改用旧的 marketplace CLI、全局 `cxclawctl`、远程 MCP、Python 代理脚本或用户自行拼接的服务地址。

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
- 用户要求切换租户时，使用 `context use <profileId> --context <contextId>`；不要修改其他会话的 context。
- 需要一次性覆盖租户时，可显式追加 `--profile <profileId>`。解析优先级是命令级 `--profile`，再到 `--context` 的 active profile；无法确定时直接失败。
- 业务操作前可执行 `context current --context <contextId>`，确认并向用户展示 `contextId`、`profileId`、`accountId`、`environment` 和 `purpose`。
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
