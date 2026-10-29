---
name: setup
description: 安装 CXClaw 后完成钉钉登录、租户选择和本地环境自检。
---

# CXClaw Setup

执行本 Skill 前先遵循 `cxclawctl` Skill，统一处理 CLI 入口、自动登录、`contextId` 生命周期和租户隔离。本 Skill 只补充安装后的自检步骤：

1. 登录成功并选择目标租户后，运行 `node "<PLUGIN_ROOT>/plugin-cli.mjs" doctor` 和
   `node "<PLUGIN_ROOT>/plugin-cli.mjs" update --install-scheduler`。只有两步都成功才报告安装完成。
