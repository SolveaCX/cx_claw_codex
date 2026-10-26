---
name: setup
description: 安装 CXClaw 后完成钉钉登录、租户选择和本地环境自检。
---

# CXClaw Setup

1. 后续命令统一使用 `node "<PLUGIN_ROOT>/plugin-cli.mjs"`。运行
   `node "<PLUGIN_ROOT>/plugin-cli.mjs" auth ensure`。CLI 固定连接生产授权服务；未登录时会自动打开钉钉授权页并持续监听授权结果，用户不需要提供服务地址或登录环境。
2. 授权期间保持当前命令运行；若执行工具返回 running session，持续轮询该 session，直到命令成功或明确失败。不要要求用户回复“已授权”，也不要代替用户授权、展示或记录 token。
3. 登录 token 同时用于生产和测试环境。用户要求测试环境时运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" tenant search <租户名称> --env test`；生产环境必须明确使用 `--env prod`，不能自行推断。
4. 用户确认目标租户后，运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" tenant use <accountId> --env <test|prod> --purpose <用途>`。
5. 运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" doctor` 和
   `node "<PLUGIN_ROOT>/plugin-cli.mjs" update --install-scheduler`。只有两步都成功才报告安装完成。

写操作必须先调用同一业务命令的 `--phase preview` 并展示结果；等待用户明确确认后，使用 `--phase commit --confirmation-token-stdin --idempotency-key <key>` 提交。不得把确认凭证写入命令参数、文件或日志。
