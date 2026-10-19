#!/usr/bin/env python3
"""Solvea POC 测试执行器：跑 cases.json → 解析 chatflow_run_info → 输出 results JSON。

POC 路径：agent 设计完 cases.json → 跑测试 → results 给 gen_poc_manual.py 渲染手册。

入参格式（test-file）：
  [
    {
      "case_name": "P1_Shipping_Inquiry",   // 必填；老字段 "name" 仍兼容兜底
      "agent_name": "Return and exchange",
      "agent_id": 38050,
      "messages": ["I want to return my order", "My order number is 204-..."],
      "expected": { "intent": "...", "content_contains": [...], "flow_status": "success", ... }
    }
  ]

CHAT_FLOW Agent 默认走策略路由；SINGLE_AGENT 通过 --agent-id 触发
metadata.specified_agent_id 强制路由（服务端 Entities.specifiedAgentId 直接读 ID 查库）。

用法：
  python3 poc_test.py --test-file cases.json --output results.json --report
  python3 poc_test.py --test-file cases.json --agent-id 2274 --report   # 强制 SINGLE_AGENT
"""

import argparse
import json
import os
import sys
import time

_solvea_lib_dir = os.environ.get("SOLVEA_LIB_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "__lib__")
)
sys.path.insert(0, os.path.join(_solvea_lib_dir, "skill-runtime"))
from bootstrap import *  # noqa: F401,F403
from client import SolveaClient


# ── Response Parsing ──

def _extract_intent(resp):
    """Extract intent name from response."""
    ctx = resp.get("context")
    if not ctx or isinstance(ctx, str):
        return ""
    intent = ctx.get("intent", "")
    if isinstance(intent, str):
        return intent
    if isinstance(intent, dict):
        return intent.get("name", "")
    return ""


def _extract_chatflow_info(resp):
    """Extract chatflow execution info from response.

    Pulls chatflow_run_info events out of context.ext, structuring node runs,
    final status, errors, and the executed-node sequence.
    """
    ctx = resp.get("context", {})
    if not isinstance(ctx, dict):
        return {}
    ext = ctx.get("ext", {})
    if not isinstance(ext, dict):
        return {}

    run_info = ext.get("chatflow_run_info", [])
    node_runs = []
    errors = []
    status = None

    for event in run_info:
        ed = event.get("eventData", {})
        if event.get("event") == "chat_finished":
            status = ed.get("status", "")
        if "error" in ed:
            errors.append({
                "name": ed["error"].get("name", ""),
                "detail": ed["error"].get("detail", "")[:200]
            })
        if event.get("event") == "node_finished":
            node_runs.append({
                "node_id": ed.get("node_id", ""),
                "category": ed.get("category", ""),
                "status": ed.get("status", ""),
                "title": ed.get("title", ""),
                "output": ed.get("output", ""),
            })

    return {
        "agent_id": ext.get("invoke_agent_id"),
        "agent_name": ext.get("invoke_agent_name", ""),
        "status": status,
        "node_runs": node_runs,
        "errors": errors,
        "nodes_executed": [nr.get("category", "") for nr in node_runs if nr.get("status") == "success"],
    }


def _extract_reply_text(resp, flow_info):
    """Pick the user-visible reply text.

    Priority:
      1. top-level `content` if it's not the placeholder "No content has been generated"
         (this is filled for SINGLE_AGENT and some CHAT_FLOW completions)
      2. last successful REPLY/AGENT/RAG_REPLY/KNOWLEDGE_REPLY node output
    """
    top = resp.get("content", "")
    if top and top != "No content has been generated":
        return top

    reply_categories = {"REPLY", "AGENT", "RAG_REPLY", "KNOWLEDGE_REPLY"}
    for nr in reversed(flow_info.get("node_runs", [])):
        if nr.get("status") == "success" and nr.get("category") in reply_categories:
            out = nr.get("output", "")
            if out:
                return out
    return top  # fall back to the placeholder so the report still shows something


# ── Test Execution ──

def _is_handoff(resp, flow_info):
    """检测是否触发了转人工：top-level handoff=True 或 chatflow 节点出现 TRANSFER_TO_HUMANS。"""
    if resp.get("handoff") is True:
        return True
    for nr in flow_info.get("node_runs", []):
        if nr.get("status") == "success" and "TRANSFER_TO_HUMANS" in (nr.get("category", "") or ""):
            return True
    return False


def run_single_test(client, test_case, bot_id=None, force_metadata=None, max_turns=3):
    """Run a single test case (may be multi-turn).

    终止条件（任一满足即停）：
      - case.messages 已跑完
      - 已达到 max_turns（默认 3，POC 模式硬上限）
      - 任意一轮触发了转人工（resp.handoff=True 或 TRANSFER_TO_HUMANS 节点 success）

    force_metadata：CLI --agent-id 组装的 {"specified_agent_id": int} 等强制 metadata；
    与 case.metadata 合并，CLI 优先级最高。
    """
    messages = test_case.get("messages", [])
    if not messages and test_case.get("message"):
        messages = [test_case["message"]]

    base_metadata = dict(test_case.get("metadata") or {})
    if force_metadata:
        base_metadata.update(force_metadata)

    expected = test_case.get("expected", {})
    results = []
    chat_id = None
    stopped_reason = "messages_exhausted"

    for i, msg in enumerate(messages):
        if i >= max_turns:
            stopped_reason = f"max_turns({max_turns})"
            break
        try:
            # 多轮规则：metadata 仅首轮带，后续轮次清空（与老版一致）
            metadata = base_metadata if i == 0 else None
            resp = client.chat(
                message=msg,
                bot_id=bot_id,
                chat_id=chat_id,
                touch_point=test_case.get("touchPoint", "LIVE_CHAT"),
                metadata=metadata,
            )
            chat_id = resp.get("chatId", chat_id)
            flow_info = _extract_chatflow_info(resp)
            reply_text = _extract_reply_text(resp, flow_info)
            handoff = _is_handoff(resp, flow_info)
            results.append({
                "turn": i + 1,
                "input": msg,
                "content": reply_text,
                "raw_content": resp.get("content", ""),
                "handoff": handoff,
                "reasonDesc": resp.get("reasonDesc", ""),
                "chatId": chat_id,
                "type": resp.get("type", ""),
                "intent": _extract_intent(resp),
                "chatflow": flow_info,
            })
            if handoff:
                stopped_reason = f"handoff(turn {i+1})"
                break
            if i < len(messages) - 1 and i + 1 < max_turns:
                time.sleep(1)
        except Exception as e:
            results.append({
                "turn": i + 1,
                "input": msg,
                "error": str(e)
            })
            stopped_reason = f"error(turn {i+1})"
            break

    evaluation = evaluate_test(test_case, results, expected)
    return {
        "name": test_case.get("case_name") or test_case.get("name") or "unnamed",
        "agent_name": test_case.get("agent_name", ""),
        "agent_id": test_case.get("agent_id"),
        "scenario": test_case.get("scenario", ""),
        "category": test_case.get("category", ""),
        "stopped_reason": stopped_reason,
        "results": results,
        "expected": expected,
        "evaluation": evaluation,
    }


def evaluate_test(test_case, results, expected):
    """Evaluate test results against expected outcomes."""
    if not results:
        return {"pass": False, "reason": "No results", "checks": []}

    last_result = results[-1]
    checks = []
    all_pass = True

    # Auto-check: INTERNAL_ERROR is always a failure
    for r in results:
        if r.get("content") == "INTERNAL_ERROR" or r.get("raw_content") == "INTERNAL_ERROR":
            flow_errors = r.get("chatflow", {}).get("errors", [])
            error_detail = flow_errors[0]["name"] if flow_errors else "unknown"
            checks.append({
                "check": f"no_internal_error (turn {r['turn']})",
                "pass": False,
                "actual": f"INTERNAL_ERROR: {error_detail}"
            })
            all_pass = False

    # Auto-check: response type STOPPED/CONFUSED is failure
    for r in results:
        if r.get("type") in ("STOPPED", "CONFUSED"):
            checks.append({
                "check": f"response_type (turn {r['turn']})",
                "pass": False,
                "expected": "MESSAGE",
                "actual": r.get("type")
            })
            all_pass = False

    # Intent recognition
    if expected.get("intent"):
        first_intent = results[0].get("intent", "")
        intent_match = expected["intent"].lower() in first_intent.lower() if first_intent else False
        checks.append({
            "check": "intent_match",
            "expected": expected["intent"],
            "actual": first_intent,
            "pass": intent_match
        })
        if not intent_match:
            all_pass = False

    # Handoff check
    if "handoff" in expected:
        handoff_match = last_result.get("handoff") == expected["handoff"]
        checks.append({
            "check": "handoff",
            "expected": expected["handoff"],
            "actual": last_result.get("handoff"),
            "pass": handoff_match
        })
        if not handoff_match:
            all_pass = False

    # Content contains
    if expected.get("content_contains"):
        content = last_result.get("content", "")
        for keyword in expected["content_contains"]:
            found = keyword.lower() in content.lower()
            checks.append({"check": f"content_contains '{keyword}'", "pass": found})
            if not found:
                all_pass = False

    # Content NOT contains
    if expected.get("content_not_contains"):
        content = last_result.get("content", "")
        for keyword in expected["content_not_contains"]:
            found = keyword.lower() in content.lower()
            checks.append({"check": f"content_not_contains '{keyword}'", "pass": not found})
            if found:
                all_pass = False

    # CHAT_FLOW node execution check
    if expected.get("nodes_executed"):
        actual_nodes = last_result.get("chatflow", {}).get("nodes_executed", [])
        for expected_cat in expected["nodes_executed"]:
            found = expected_cat in actual_nodes
            checks.append({
                "check": f"node_executed '{expected_cat}'",
                "expected": expected_cat,
                "actual": actual_nodes,
                "pass": found
            })
            if not found:
                all_pass = False

    # CHAT_FLOW status check
    if expected.get("flow_status"):
        actual_status = last_result.get("chatflow", {}).get("status", "")
        status_match = actual_status == expected["flow_status"]
        checks.append({
            "check": "flow_status",
            "expected": expected["flow_status"],
            "actual": actual_status,
            "pass": status_match
        })
        if not status_match:
            all_pass = False

    # Error check
    if last_result.get("error"):
        checks.append({"check": "no_error", "pass": False, "actual": last_result["error"]})
        all_pass = False

    # Fallback: at least got a response
    if not expected and not any(c["check"].startswith("no_internal_error") for c in checks):
        has_content = bool(last_result.get("content"))
        checks.append({"check": "has_response", "pass": has_content})
        if not has_content:
            all_pass = False

    return {"pass": all_pass, "checks": checks}


# ── Batch Runner ──

def run_batch_test(client, test_cases, bot_id=None, force_metadata=None, delay=2,
                   max_turns=3):
    """Run all test cases and return summary."""
    results = []
    total = len(test_cases)

    for i, tc in enumerate(test_cases):
        case_label = tc.get("case_name") or tc.get("name") or "unnamed"
        print(f"  [{i+1}/{total}] Testing: {case_label}...", file=sys.stderr)
        result = run_single_test(client, tc, bot_id=bot_id,
                                 force_metadata=force_metadata,
                                 max_turns=max_turns)
        print(f"      → stopped: {result.get('stopped_reason', '?')}", file=sys.stderr)
        results.append(result)
        if i < total - 1:
            time.sleep(delay)

    return _summarize(results)


def _summarize(results):
    total = len(results)
    passed = sum(1 for r in results if r["evaluation"]["pass"])
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": f"{(passed / total * 100) if total > 0 else 0:.1f}%",
        "results": results,
    }


# ── Report ──

def print_report(summary):
    """Print a human-readable test report."""
    print("\n" + "=" * 70)
    print("  SOLVEA BATCH TEST REPORT")
    print("=" * 70)
    print(f"  Total: {summary['total']}  |  Passed: {summary['passed']}  |  "
          f"Failed: {summary['failed']}  |  Rate: {summary['pass_rate']}")
    print("=" * 70)

    for r in summary["results"]:
        status = "PASS" if r["evaluation"]["pass"] else "FAIL"
        icon = "✅" if r["evaluation"]["pass"] else "❌"
        print(f"\n{icon} [{status}] {r['name']}")
        if r.get("agent_name"):
            print(f"   Agent: {r['agent_name']} (id={r.get('agent_id')})")
        if r.get("category"):
            print(f"   Category: {r['category']}")

        for turn in r["results"]:
            print(f"   Turn {turn['turn']}: \"{turn['input'][:80]}\"")
            if turn.get("error"):
                print(f"     ⚠️  Error: {turn['error']}")
            else:
                content_preview = (turn.get("content", ""))[:120]
                ellipsis = "..." if len(turn.get("content", "")) > 120 else ""
                print(f"     → {content_preview}{ellipsis}")
                if turn.get("intent"):
                    print(f"     Intent: {turn['intent']}")
                if turn.get("handoff"):
                    print("     Handoff: True")
                flow = turn.get("chatflow", {})
                if flow.get("nodes_executed"):
                    print(f"     Nodes: {' → '.join(flow['nodes_executed'])}")
                if flow.get("errors"):
                    for fe in flow["errors"]:
                        print(f'     FlowError: {fe["name"]}: {fe["detail"][:100]}')

        if not r["evaluation"]["pass"]:
            print("   --- Failed checks ---")
            for chk in r["evaluation"].get("checks", []):
                if not chk["pass"]:
                    msg = f"   ❌ {chk['check']}"
                    if "expected" in chk:
                        msg += f" (expected: {chk['expected']}, actual: {chk.get('actual', 'N/A')})"
                    elif "actual" in chk:
                        msg += f" ({chk['actual']})"
                    print(msg)

    print("\n" + "=" * 70)
    print(f"  SUMMARY: {summary['pass_rate']} pass rate ({summary['passed']}/{summary['total']})")
    print("=" * 70 + "\n")


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="Solvea POC Test Runner")
    parser.add_argument("--test-file", required=True,
                        help="JSON file with test cases (POC 模式：agent 设计的 cases.json)")
    parser.add_argument("--max-turns", type=int, default=3,
                        help="单 case 最大对话轮数（默认 3，POC 硬上限；触发 handoff 也提前终止）")
    parser.add_argument("--agent-id", type=int,
                        help="强制 SINGLE_AGENT 路由（组装 metadata.specified_agent_id；"
                             "CHAT_FLOW 默认走策略路由，不需要）")
    parser.add_argument("--bot-id", help="Bot ID override")
    parser.add_argument("--delay", type=float, default=2, help="Delay between cases (seconds)")
    parser.add_argument("--report", action="store_true", help="Print human-readable report")
    parser.add_argument("--output", help="Save results JSON to this path")
    parser.add_argument("--pretty", action="store_true", help="Pretty print compact JSON to stdout")
    args = parser.parse_args()

    client = SolveaClient()

    with open(args.test_file, encoding="utf-8") as f:
        test_cases = json.load(f)

    force_metadata = None
    if args.agent_id:
        force_metadata = {"specified_agent_id": int(args.agent_id)}
        print(f"  Forcing SINGLE_AGENT route via metadata.specified_agent_id={args.agent_id}",
              file=sys.stderr)

    print(f"  Running {len(test_cases)} test cases (max_turns={args.max_turns})...",
          file=sys.stderr)
    summary = run_batch_test(
        client,
        test_cases,
        bot_id=args.bot_id,
        force_metadata=force_metadata,
        delay=args.delay,
        max_turns=args.max_turns,
    )

    if args.report:
        print_report(summary)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"  Results saved to {args.output}", file=sys.stderr)

    if args.pretty:
        compact = {
            "total": summary["total"],
            "passed": summary["passed"],
            "failed": summary["failed"],
            "pass_rate": summary["pass_rate"],
            "details": [
                {
                    "name": r["name"],
                    "agent_name": r.get("agent_name", ""),
                    "pass": r["evaluation"]["pass"],
                    "last_content": r["results"][-1].get("content", "")[:200] if r["results"] else "",
                    "intent_detected": r["results"][0].get("intent", "") if r["results"] else "",
                    "nodes_executed": r["results"][-1].get("chatflow", {}).get("nodes_executed", []) if r["results"] else [],
                    "failed_checks": [c for c in r["evaluation"].get("checks", []) if not c["pass"]],
                }
                for r in summary["results"]
            ]
        }
        print(json.dumps(compact, indent=2, ensure_ascii=False))

    if summary["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
