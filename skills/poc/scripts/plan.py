#!/usr/bin/env python3
"""POC 顶层状态规划器。

只维护 `/workspace/state/poc/progress.json`，不执行 intent / agent / KB / batch
等底层能力。其他 skill 的状态只通过路径引用记录在本文件中，避免职责泄漏。
"""
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403

import argparse
import json
from datetime import datetime, timezone
from typing import Any


STATE_FILE = STATE_DIR / "progress.json"

STATUS_ORDER = [
    "empty",
    "classified",
    "business_agents_created",
    "fallback_agent_created",
    "fallback_strategy_linked",
    "kb_done",
    "cases_ready",
    "test_done",
    "done",
]


def default_state() -> dict[str, Any]:
    return {
        "status": "empty",
        "tenant": SOLVEA_TENANT_ID or "",
        "brand_name": "",
        "brand_website": "",
        "intent": {
            "progress_path": "/workspace/state/poc/progress.json",
            "created_log_path": "",
            "classification_report_path": "",
            "classification_excel_path": "",
        },
        "fallback_agent": {
            "agent_id": "",
            "agent_name": "",
            "created": False,
        },
        "kb": {
            "enabled": False,
            "source_url": "",
            "directory_plan_path": "",
            "qa_plan_path": "",
            "upload_result_path": "",
        },
        "test": {
            "agents": [],
            "cases_json_path": "",
            "results_path": "",
            "manual_path": "",
        },
        "updated_at": "",
    }


def read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return default_state()
    try:
        loaded = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return default_state()
    state = default_state()
    merge_dict(state, loaded)
    return state


def merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge_dict(base[key], value)
        else:
            base[key] = value


def write_state(state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def set_path(state: dict[str, Any], dotted_key: str, raw_value: str) -> None:
    parts = [p for p in dotted_key.split(".") if p]
    if not parts:
        raise ValueError("empty key")
    cur = state
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    value: Any = raw_value
    if raw_value.lower() == "true":
        value = True
    elif raw_value.lower() == "false":
        value = False
    elif raw_value.startswith("[") or raw_value.startswith("{"):
        value = json.loads(raw_value)
    cur[parts[-1]] = value


def recommendation(status: str) -> str:
    return {
        "empty": "下一步：读取 poc/interfaces/classify.md 和 poc/interfaces/create-agents.md，确认从 xlsx 分类还是固定 7 意图开始。",
        "classified": "下一步：展示分类结果并等待用户确认；确认后调用 /skills/poc/scripts/create_agents.py --mode poc。",
        "business_agents_created": "下一步：通过 agent-builder/interfaces/fallback-chatflow.md 创建兜底 CHAT_FLOW agent。",
        "fallback_agent_created": "下一步：调用 /skills/poc/scripts/create_agents.py --mode poc --poc-fallback-agent-id <agent_id> 绑定兜底策略。",
        "fallback_strategy_linked": "下一步：询问是否进入可选 KB 阶段；跳过则进入 POC 批测。",
        "kb_done": "下一步：读取 poc/interfaces/poc-test.md，设计并确认测试 cases。",
        "cases_ready": "下一步：执行 poc_test.py，然后生成 POC 测试手册。",
        "test_done": "下一步：汇总 POC 测试手册和原始结果，确认交付完成。",
        "done": "当前 POC 已完成；如需重跑，请明确要重跑的阶段。",
    }.get(status, "状态未知：请检查 progress.json。")


def main() -> None:
    parser = argparse.ArgumentParser(description="POC top-level progress planner")
    parser.add_argument("--init", action="store_true", help="Create progress.json if missing")
    parser.add_argument("--status", choices=STATUS_ORDER, help="Update top-level status")
    parser.add_argument("--tenant", default=None)
    parser.add_argument("--brand-name", default=None)
    parser.add_argument("--brand-website", default=None)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                        help="Set a dotted state path, e.g. intent.created_log_path=/workspace/...")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    existed = STATE_FILE.exists()
    state = read_state()
    changed = False

    if args.init and not existed:
        changed = True
    if args.status:
        state["status"] = args.status
        changed = True
    if args.tenant is not None:
        state["tenant"] = args.tenant
        changed = True
    if args.brand_name is not None:
        state["brand_name"] = args.brand_name
        changed = True
    if args.brand_website is not None:
        state["brand_website"] = args.brand_website
        changed = True
    for item in args.set:
        if "=" not in item:
            raise SystemExit(f"--set expects KEY=VALUE, got: {item}")
        key, value = item.split("=", 1)
        set_path(state, key, value)
        changed = True

    if changed:
        write_state(state)

    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return

    print(f"POC progress: {STATE_FILE}")
    print(f"status={state.get('status')} tenant={state.get('tenant') or '-'} brand={state.get('brand_name') or '-'}")
    print(recommendation(str(state.get("status") or "")))
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
