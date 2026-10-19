#!/usr/bin/env python3
"""Render a concise Delivery progress / deliverables summary."""
import os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403

import json


STATE_FILE = STATE_DIR / "progress.json"


def main() -> None:
    if not STATE_FILE.exists():
        print("Delivery progress not found. Run `python3 /skills/delivery/scripts/plan.py --init` first.")
        return
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    print("# Delivery Progress Summary")
    print(f"- status: `{state.get('status', 'empty')}`")
    print(f"- tenant: `{state.get('tenant') or '-'}`")
    print(f"- brand: `{state.get('brand_name') or '-'}`")
    intent = state.get("intent") or {}
    kb = state.get("kb") or {}
    regression = state.get("regression") or {}
    if intent.get("classification_report_path"):
        print(f"- classification report: `{intent['classification_report_path']}`")
    if intent.get("created_log_path"):
        print(f"- created log: `{intent['created_log_path']}`")
    if kb.get("qa_plan_path"):
        print(f"- kb qa plan: `{kb['qa_plan_path']}`")
    if regression.get("report_html"):
        print(f"- regression HTML: `{regression['report_html']}`")
    if regression.get("report_md"):
        print(f"- regression MD: `{regression['report_md']}`")


if __name__ == "__main__":
    main()
