"""
HTML report generator for delivery skill.

Reads classification results (workspace/state/delivery/progress.json -> results_path) and
renders a polished HTML report under workspace/outputs/delivery/.

Usage:
  python3 scripts/gen_report.py [--brand "Acme"]
"""

import os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *

import json, argparse
from uuid import uuid4


def _read_state() -> dict:
    _sf = STATE_DIR / "progress.json"
    if _sf.exists():
        try:
            return json.loads(_sf.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_state(data: dict) -> None:
    _sf = STATE_DIR / "progress.json"
    _sf.parent.mkdir(parents=True, exist_ok=True)
    _sf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

from render import render_html

COLOR_PALETTE = [
    "#ef4444", "#f97316", "#eab308", "#22c55e",
    "#14b8a6", "#3b82f6", "#8b5cf6", "#ec4899",
    "#06b6d4", "#84cc16",
]

CIRCLE_NUMS = "①②③④⑤⑥⑦⑧⑨⑩"


def build_config_from_results(results, brand_name=""):
    def uid():
        return uuid4().hex

    agents = []
    all_intents = results.get("intents", []) + results.get("new_intents", [])
    meta = results.get("meta", {})
    total = meta.get("total", 0)

    for i, intent in enumerate(all_intents):
        sub_intents = intent.get("sub_intents", [])
        is_new = intent.get("is_new", False)
        agent_id = f"intent-{i}"

        l2_nodes = []
        for j, s in enumerate(sub_intents):
            sample_preview = s["samples"][0][:50] + "..." if s.get("samples") else ""
            l2_nodes.append({
                "id": f"n2-{uid()[:8]}",
                "name": s["name"],
                "desc": f"{s['pct']:.1f}% — {sample_preview}" if sample_preview else f"{s['pct']:.1f}%",
                "count": s["count"],
                "definition": s.get("definition", ""),
                "is_shared": False,
                "shared_agents": [],
                "samples": s.get("samples", []),
            })

        nodes_ac = []
        for s in sub_intents[:3]:
            nodes_ac.append({
                "name": f"节点 · {s['name']}",
                "trigger": f"客户投诉：{s['name']}",
                "action": f"<code>LLM</code> 处理 {s['name']}，引导解决",
            })

        agents.append({
            "id": agent_id,
            "name": f"{CIRCLE_NUMS[i % len(CIRCLE_NUMS)]} {intent['name']}",
            "color": COLOR_PALETTE[i % len(COLOR_PALETTE)],
            "l1_intents": [intent["name"]],
            "total_count": intent["count"],
            "total_pct": intent["pct"],
            "is_new": is_new,
            "intent_config": {
                "definition": intent.get("definition", ""),
                "excludes": [],
                "examples": intent.get("samples", [])[:3],
                "covers": [s["name"] for s in sub_intents],
            },
            "agent_config": {
                "type": "chatflow",
                "nodes": nodes_ac,
                "footer": f"<b>结束：</b>解决{intent['name']}问题 / 转人工",
            },
            "l2_nodes": l2_nodes,
        })

    edges = []
    for a in agents:
        ag_html_id = f"ag-{a['id'].replace('_', '-')}"
        color = a.get("color", "#6b7280")
        for node in a["l2_nodes"]:
            count = node.get("count", 0)
            if count > 0:
                edges.append({"from": ag_html_id, "to": node["id"], "count": count, "color": color})

    total_nodes = sum(len(a["l2_nodes"]) for a in agents)
    n_known = meta.get("n_known", len(results.get("intents", [])))
    n_new = meta.get("n_new", len(results.get("new_intents", [])))

    rows = []
    for a in agents:
        n = len(a["l2_nodes"])
        badge = f"{n} 节点 ✓" if n <= 2 else (f"{n} 节点 ⚠️" if n <= 3 else f"{n} 节点 ❌")
        rows.append({
            "agent_name": a["name"],
            "color": a["color"],
            "node_count": n,
            "badge": badge,
        })

    l2_total = sum(s["count"] for intent in all_intents for s in intent.get("sub_intents", []))
    opt_notes = (
        f"✅ 已知意图 {n_known} 个，新发现意图 {n_new} 个，共 {n_known + n_new} 个 L1 意图\n\n"
        f"📊 数据基础：{total:,} 条对话 / L2 分类：{l2_total:,} 条"
    )
    if n_new > 0:
        new_names = [i["name"] for i in results.get("new_intents", [])]
        opt_notes += f"\n\n⚡ 新发现意图：{' · '.join(new_names)}"

    return {
        "agents": agents,
        "filter_block": {"types": ["未分类投诉"], "count": 0},
        "node_summary": {
            "rows": rows,
            "total_nodes": total_nodes,
            "optimization_notes": opt_notes,
        },
        "shared_nodes": [],
        "edges": edges,
    }


def _resolve_results_path(state: dict) -> str:
    path = state.get("results_path")
    if not path:
        raise FileNotFoundError(
            "No results_path in state. Run classify.py first."
        )
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Results file missing: {path}. Run classify.py first."
        )
    return path


def main():
    parser = argparse.ArgumentParser(description="Generate delivery intent classification HTML report")
    parser.add_argument("--brand", default="")
    parser.add_argument("--results", default=None,
                        help="Override results JSON path (default: read from progress.json)")
    args = parser.parse_args()

    if args.results:
        results_path = args.results
        if not os.path.exists(results_path):
            raise FileNotFoundError(f"Results file missing: {results_path}")
    else:
        state = _read_state()
        results_path = _resolve_results_path(state)

    with open(results_path) as f:
        results = json.load(f)

    config = build_config_from_results(results, brand_name=args.brand)

    meta = results.get("meta", {})
    data_compat = {
        "_meta": {"total": meta.get("total", 0), "brand": args.brand},
        "tree": {},
        "turn_distribution": {},
        "fuzzy_samples": {},
    }

    project_id = os.environ.get("SOLVEA_PROJECT_ID", "")
    html = render_html(config, data_compat, brand=args.brand, project_id=project_id)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = str(OUTPUTS_DIR / f"report_{timestamp()}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[gen_report] Report -> {report_path}")

    state = _read_state()
    state["report_path"] = report_path
    state["updated_at"] = timestamp()
    _write_state(state)

    print(f"[gen_report] Done.")


if __name__ == "__main__":
    main()
