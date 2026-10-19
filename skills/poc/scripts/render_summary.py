#!/usr/bin/env python3
"""Render a concise POC progress / deliverables summary."""
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403

import json


STATE_FILE = STATE_DIR / "progress.json"


def main() -> None:
    if not STATE_FILE.exists():
        print("POC progress not found. Run `python3 /skills/poc/scripts/plan.py --init` first.")
        return
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    print("# POC Progress Summary")
    print(f"- status: `{state.get('status', 'empty')}`")
    print(f"- tenant: `{state.get('tenant') or '-'}`")
    print(f"- brand: `{state.get('brand_name') or '-'}`")
    intent = state.get("intent") or {}
    fallback = state.get("fallback_agent") or {}
    kb = state.get("kb") or {}
    test = state.get("test") or {}
    if intent.get("classification_report_path"):
        print(f"- classification report: `{intent['classification_report_path']}`")
    if intent.get("created_log_path"):
        print(f"- created log: `{intent['created_log_path']}`")
    if fallback.get("agent_id"):
        print(f"- fallback agent: `{fallback.get('agent_name') or '-'} ({fallback['agent_id']})`")
    if kb.get("enabled"):
        print(f"- kb qa plan: `{kb.get('qa_plan_path') or '-'}`")
    if test.get("manual_path"):
        print(f"- POC manual: `{test['manual_path']}`")
    if test.get("results_path"):
        print(f"- test results: `{test['results_path']}`")


if __name__ == "__main__":
    main()
