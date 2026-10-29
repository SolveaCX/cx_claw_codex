---
name: setup
description: 安装 CXClaw 后完成钉钉登录、租户选择和本地环境自检。
---

# CXClaw Setup

1. 后续命令统一使用 `node "<PLUGIN_ROOT>/plugin-cli.mjs"`。运行
   `node "<PLUGIN_ROOT>/plugin-cli.mjs" auth login`。CLI 固定连接生产授权服务，用户不需要提供服务地址或登录环境。
   这是一个持续运行到授权成功、失败或过期的长命令。若执行工具返回 `session_id`，必须用同一个 `session_id` 持续读取，直到命令退出；不要另跑 `auth status`，不要让用户回复“已授权”，也不要再次启动登录命令。
2. 不要代替用户授权、展示或记录 token。
3. 登录成功后执行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" context init`，保留返回的 `contextId`。只复用当前对话工具输出中的 `contextId`，不得借用其他对话或回退到全局最近租户；无法恢复时重新初始化 context。
4. 登录 token 同时用于生产和测试环境。默认访问生产环境，运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" tenant search <租户名称>`；用户明确要求测试环境时才追加 `--env test`（或 `--env staging`）。
5. 用户确认目标租户后，运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" tenant use <accountId> --profile <profileId> --context <contextId> --purpose <用途>`；`profileId` 使用可识别的租户与环境名称。选择测试环境时追加 `--env test`，生产环境可追加 `--env prod` 但不强制。后续所有租户业务命令自动追加同一 `--context <contextId>`。
6. 运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" doctor` 和
   `node "<PLUGIN_ROOT>/plugin-cli.mjs" update --install-scheduler`。只有两步都成功才报告安装完成。

业务命令返回 `error.reason=not_authenticated` 时，按上述方式执行一次 `auth login`；登录命令成功退出后，只重试原业务命令一次。普通业务命令不会自动打开授权页面。

写操作必须先调用同一业务命令的 `--phase preview` 并展示结果；等待用户明确确认后，使用 `--phase commit --confirmation-token-stdin --idempotency-key <key>` 提交。不得把确认凭证写入命令参数、文件或日志。
