#!/usr/bin/env python3
"""Delivery 顶层状态规划器。

只维护 `/workspace/state/delivery/progress.json`，不执行 intent / KB / batch
等底层能力。其他 skill 的状态只通过路径引用记录在本文件中。
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
    "agents_created",
    "kb_done",
    "regression_done",
    "done",
]


def default_state() -> dict[str, Any]:
    return {
        "status": "empty",
        "tenant": SOLVEA_TENANT_ID or "",
        "brand_name": "",
        "intent": {
            "progress_path": "/workspace/state/delivery/progress.json",
            "classification_report_path": "",
            "classification_excel_path": "",
            "created_log_path": "",
        },
        "kb": {
            "required": True,
            "source_url": "",
            "directory_plan_path": "",
            "qa_plan_path": "",
            "upload_result_path": "",
        },
        "regression": {
            "input_path": "",
            "touch_point": "LIVE_CHAT",
            "results_path": "",
            "report_html": "",
            "report_md": "",
        },
        "updated_at": "",
    }


def merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge_dict(base[key], value)
        else:
            base[key] = value


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
        "empty": "下一步：读取 delivery/interfaces/classify.md，确认从 xlsx 分类还是固定 7 意图开始。",
        "classified": "下一步：展示分类结果并等待用户确认；确认后调用 /skills/delivery/scripts/create_agents.py --mode delivery。",
        "agents_created": "下一步：进入 KB 阶段；如用户声称已有 KB，先 list-directories / list-knowledge 验证。",
        "kb_done": "下一步：读取 delivery/interfaces/delivery-test.md，确认回归数据来源和 touch-point。",
        "regression_done": "下一步：汇总 KPI 报告和失败明细，确认交付完成。",
        "done": "当前 Delivery 已完成；如需重跑，请明确要重跑的阶段。",
    }.get(status, "状态未知：请检查 progress.json。")


def main() -> None:
    parser = argparse.ArgumentParser(description="Delivery top-level progress planner")
    parser.add_argument("--init", action="store_true", help="Create progress.json if missing")
    parser.add_argument("--status", choices=STATUS_ORDER, help="Update top-level status")
    parser.add_argument("--tenant", default=None)
    parser.add_argument("--brand-name", default=None)
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

    print(f"Delivery progress: {STATE_FILE}")
    print(f"status={state.get('status')} tenant={state.get('tenant') or '-'} brand={state.get('brand_name') or '-'}")
    print(recommendation(str(state.get("status") or "")))
    print(json.dumps(state, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
