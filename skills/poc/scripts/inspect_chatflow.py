#!/usr/bin/env python3
"""为 POC 案例设计精简 chatflow 图视图。

把 raw graph（完整 nodes/edges + UUID + 渲染坐标）压成 agent 看一眼就能设计 case 的形态：
- 节点按 category 提取**业务关键字段**（NOTE 的 noteText、AGENT/REPLY 的 prompt、
  INTENT 的 intents 列表、TOOL 的 inputParams 等），不仅是字段名
- edge label 中的 intent uuid / next_step uuid **自动解码**为人类可读的名字
- 去掉 position 坐标、UUID 中段（保留前 8 位）等纯渲染元素

为什么这段不放 solvea-api：solvea-api 是纯封装层（API + CLI 透传），不掺业务视图加工。
这种 POC 设计 case 的特定 view 属于 poc skill 自己的职责。

用法：
    python3 inspect_chatflow.py --agent-id 38099 --pretty
    python3 inspect_chatflow.py --agent-id 38099 --agent-id 38100 --agent-id 38101 --pretty
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403
from client import SolveaClient


# 长 prompt 的截断阈值；prompt / desc 超过这个长度时尾部加 …<truncated>
_PROMPT_TRUNCATE = 1500


def _truncate(text: str, limit: int = _PROMPT_TRUNCATE) -> str:
    if not isinstance(text, str):
        return text
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…<truncated, total {len(text)} chars>"


def _short_id(uuid: str) -> str:
    return (uuid or "")[:8]


def _summarize_node(n: dict) -> dict:
    """按 category 提取关键业务字段。未识别的 category 退回到 raw config。"""
    data = n.get("data") or {}
    config = data.get("config") or {}
    category = data.get("category") or ""
    title = data.get("title") or "(start)"

    out: dict = {
        "id": _short_id(n.get("id")),
        "category": category,
        "title": title,
    }
    desc = data.get("desc")
    if desc:
        out["desc"] = desc

    if category == "START":
        return out

    if category == "NOTE":
        out["note_text"] = config.get("noteText", "")
        return out

    if category in ("AGENT", "KNOWLEDGE_REPLY"):
        agent_data = config.get("agentData") or {}
        prompt = agent_data.get("prompt") or (config.get("knowledgeReply") or {}).get("prompt")
        if prompt:
            out["prompt"] = _truncate(prompt)
        next_steps = config.get("nextStep") or []
        if next_steps:
            out["next_step"] = [
                {k: v for k, v in {"id": ns.get("id"), "title": ns.get("title"), "prompt": _truncate(ns.get("prompt") or "", 300)}.items() if v}
                for ns in next_steps
            ]
        if config.get("maxRounds"):
            out["max_rounds"] = config["maxRounds"]
        return out

    if category == "REPLY":
        rc = config.get("replyContent") or {}
        if rc.get("prompt"):
            out["reply_prompt"] = _truncate(rc["prompt"])
        if rc.get("type") and rc["type"] != "PROMPT":
            out["reply_type"] = rc["type"]
        return out

    if category == "INTENT":
        out["intents"] = [
            {k: v for k, v in {"id": it.get("id"), "name": it.get("name"), "desc": _truncate(it.get("desc") or "", 400)}.items() if v}
            for it in (config.get("intents") or [])
        ]
        return out

    if category == "TOOL":
        tool = config.get("tool") or {}
        out["tool_id"] = tool.get("id")
        out["tool_type"] = tool.get("type")
        params = tool.get("inputParams") or []
        if params:
            out["input_params"] = [
                {"name": p.get("name"), "var_type": p.get("varType"), "from": p.get("variableSelector")}
                for p in params
            ]
        return out

    if category == "VARIABLE_EXTRACT":
        ve = config.get("variableExtract") or {}
        out["extracts"] = [
            {k: v for k, v in {"name": e.get("name"), "describe": e.get("describe"), "type": e.get("type")}.items() if v}
            for e in (ve.get("extracts") or [])
        ]
        return out

    if category == "VARIABLE_ASSIGNMENT":
        out["assignments"] = [
            {"source": a.get("source"), "target": a.get("target"), "operation": a.get("operation")}
            for a in (config.get("variableAssignment") or [])
        ]
        return out

    if category == "TRANSFER_TO_HUMAN":
        h = config.get("transferToHuman") or {}
        if h.get("prompt"):
            out["handoff_prompt"] = _truncate(h["prompt"])
        return out

    # 未知 category：保留原始 config（截断长字符串）便于后续扩展
    if config:
        out["config"] = config
    return out


def _build_handle_index(raw_nodes: list) -> dict:
    """构造 source_handle uuid → 可读 label 的反查表。

    INTENT 节点的 intents[].id 和 AGENT/KNOWLEDGE_REPLY 节点的 nextStep[].id 都是 uuid，
    会出现在 edge.sourceHandle 上。把它们映射成 `[Intent] xxx` / `[NextStep] xxx`，
    edge label 立刻可读，不再是裸 uuid。
    """
    idx: dict[str, str] = {}
    for n in raw_nodes:
        data = n.get("data") or {}
        config = data.get("config") or {}
        category = data.get("category") or ""
        if category == "INTENT":
            for it in (config.get("intents") or []):
                if it.get("id") and it.get("name"):
                    idx[it["id"]] = f"[Intent] {it['name']}"
        elif category in ("AGENT", "KNOWLEDGE_REPLY"):
            for ns in (config.get("nextStep") or []):
                if ns.get("id") and ns.get("title"):
                    idx[ns["id"]] = f"[NextStep] {ns['title']}"
    return idx


def build_summary(client: SolveaClient, agent_id: int) -> dict:
    g = client.get_chatflow_graph(agent_id)
    graph = g.get("graph") or {}
    raw_nodes = graph.get("nodes") or []
    raw_edges = graph.get("edges") or []
    by_id = {n.get("id"): n for n in raw_nodes}
    handle_idx = _build_handle_index(raw_nodes)

    def _title(nid):
        return ((by_id.get(nid) or {}).get("data") or {}).get("title") or "(start)"

    nodes = [_summarize_node(n) for n in raw_nodes]

    edges = []
    for e in raw_edges:
        handle = e.get("sourceHandle") or ""
        # 优先解码 intent / next_step uuid，否则回退到 handle 原值
        label = handle_idx.get(handle) or handle or e.get("label") or ""
        edges.append({
            "from": f"{_short_id(e.get('source'))} ({_title(e.get('source'))})",
            "to": f"{_short_id(e.get('target'))} ({_title(e.get('target'))})",
            "label": label,
        })

    return {
        "agent_id": g.get("agentId"),
        "version": g.get("chatFlowVersion") or g.get("version"),
        "stats": {"nodes": len(raw_nodes), "edges": len(raw_edges)},
        "nodes": nodes,
        "edges": edges,
    }


def main():
    p = argparse.ArgumentParser(description="Inspect chatflow graph for POC case design")
    p.add_argument("--agent-id", type=int, action="append", required=True,
                   help="Agent ID (可重复传多个，例如 --agent-id 38099 --agent-id 38100)")
    p.add_argument("--pretty", action="store_true", help="Pretty print JSON")
    args = p.parse_args()

    client = SolveaClient()
    result = [build_summary(client, aid) for aid in args.agent_id]
    out = result[0] if len(result) == 1 else result

    if args.pretty:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
