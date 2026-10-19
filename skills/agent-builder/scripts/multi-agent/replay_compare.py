#!/usr/bin/env python3
"""Replay one synthetic or historical case against old/new agents and compare behavior.

Default mode is dry-run. Pass --execute to send chat-stream requests.
Use --synthetic for a quick smoke test, or fetch one real transcript by
--source-chat-id, --source-agent-id, or --intent. --cases-file is a replay
cache / override. Use --save-cases-file to persist generated/fetched cases.

Cases file schema:

{
  "cases": [
    {
      "id": "order_not_found",
      "messages": ["Where is order 123?"],
      "metadata": {"customer_email": "x@example.com"},
      "expected": {
        "handoff": true,
        "contains": ["order"],
        "not_contains": ["{{Template_Reply}}"]
      }
    }
  ]
}
"""

from __future__ import annotations

import argparse
import difflib
import html
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

_solvea_lib_dir = os.environ.get("SOLVEA_LIB_DIR")
if not _solvea_lib_dir:
    cur = os.path.abspath(os.path.dirname(__file__))
    while True:
        candidate = os.path.join(cur, "__lib__")
        if os.path.isdir(candidate):
            _solvea_lib_dir = candidate
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            raise RuntimeError("Cannot locate skills __lib__")
        cur = parent
sys.path.insert(0, os.path.join(_solvea_lib_dir, "skill-runtime"))
from bootstrap import *  # noqa: F401,F403
from client import SolveaClient


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _coerce_list_payload(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return []
    for key in ("list", "records", "rows", "data", "items"):
        nested = value.get(key)
        if isinstance(nested, list):
            return nested
        if isinstance(nested, dict):
            for nested_key in ("list", "records", "rows", "items"):
                nested_list = nested.get(nested_key)
                if isinstance(nested_list, list):
                    return nested_list
    return []


def _safe_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for key, item in value.items():
        if key in {
            "displayData",
            "displayPrompt",
            "chatflow_run_info",
            "createdAt",
            "updatedAt",
            "createdBy",
            "updatedBy",
        }:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            out[str(key)] = item
        elif isinstance(item, list) and len(item) <= 20 and all(isinstance(v, (str, int, float, bool)) or v is None for v in item):
            out[str(key)] = item
        elif isinstance(item, dict) and len(item) <= 20:
            nested = _safe_metadata(item)
            if nested:
                out[str(key)] = nested
    return out


def _content_from_message(item: dict[str, Any]) -> str:
    for key in ("content", "message", "text", "question", "query"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            for nested_key in ("text", "content", "message"):
                nested = value.get(nested_key)
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()
    return ""


def _is_user_message(item: dict[str, Any]) -> bool:
    role_values = [
        item.get("role"),
        item.get("type"),
        item.get("sender"),
        item.get("senderRole"),
        item.get("messageType"),
        item.get("from"),
    ]
    role_text = " ".join(str(value).upper() for value in role_values if value is not None)
    if any(token in role_text for token in ("USER", "CUSTOMER", "VISITOR", "BUYER")):
        return True
    if any(token in role_text for token in ("ASSISTANT", "AGENT", "BOT", "SYSTEM", "AI")):
        return False
    return bool(_content_from_message(item)) and not any(key in item for key in ("answer", "reply", "response"))


def _extract_transcript_messages(detail: Any) -> tuple[list[str], dict[str, Any]]:
    if not isinstance(detail, dict):
        return [], {}

    metadata: dict[str, Any] = {}
    for key in ("metadata", "meta", "variables"):
        metadata = _safe_metadata(detail.get(key))
        if metadata:
            break
    if not metadata and isinstance(detail.get("context"), dict):
        context = detail["context"]
        metadata = _safe_metadata(context.get("metadata") or context.get("meta") or context.get("ext"))

    candidates: list[Any] = []
    for key in ("turns", "messages", "messageList", "records", "conversation", "history"):
        if isinstance(detail.get(key), list):
            candidates = detail[key]
            break
    if not candidates and isinstance(detail.get("data"), dict):
        data = detail["data"]
        for key in ("turns", "messages", "messageList", "records", "conversation", "history"):
            if isinstance(data.get(key), list):
                candidates = data[key]
                break
        if not metadata:
            metadata = _safe_metadata(data.get("metadata") or data.get("meta"))
    if not candidates:
        candidates = _coerce_list_payload(detail)

    messages: list[str] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        if not metadata:
            metadata = _safe_metadata(item.get("metadata") or item.get("meta"))
        content = _content_from_message(item)
        if content and _is_user_message(item):
            messages.append(content)
    return messages, metadata


def _case_from_transcript(client: SolveaClient, chat_id: str, *, source_type: str, source_label: str | None = None) -> dict[str, Any]:
    detail = client.get_transcript(chat_id)
    messages, metadata = _extract_transcript_messages(detail)
    if not messages:
        raise ValueError(f"no USER messages found in transcript chatId={chat_id}")
    return {
        "id": f"{source_type}_{chat_id}",
        "source": {
            "type": source_type,
            "chatId": chat_id,
            "label": source_label,
        },
        "messages": messages,
        "metadata": metadata,
        "expected": {
            "not_contains": ["{{Template_Reply}}", "<span"],
        },
    }


def _case_from_synthetic_args(args: argparse.Namespace) -> dict[str, Any]:
    messages = args.synthetic_message or ["Where is my order 123456?"]
    metadata: dict[str, Any] = {}
    if args.synthetic_metadata:
        parsed = json.loads(args.synthetic_metadata)
        if not isinstance(parsed, dict):
            raise ValueError("--synthetic-metadata must be a JSON object")
        metadata = _safe_metadata(parsed)
    return {
        "id": args.synthetic_case_id or "synthetic_order_status_smoke",
        "source": {
            "type": "synthetic",
            "label": "smoke_test",
        },
        "messages": [str(message) for message in messages if str(message).strip()],
        "metadata": metadata,
        "expected": {
            "not_contains": ["{{Template_Reply}}", "<span"],
        },
    }


def _fetch_cases_from_source(client: SolveaClient, args: argparse.Namespace) -> list[dict[str, Any]]:
    source_count = sum(bool(value) for value in (args.synthetic, args.source_chat_id, args.source_agent_id, args.intent))
    if source_count != 1:
        raise ValueError("provide exactly one source: --synthetic, --source-chat-id, --source-agent-id, or --intent")

    if args.synthetic:
        return [_case_from_synthetic_args(args)]

    if args.source_chat_id:
        return [_case_from_transcript(client, args.source_chat_id, source_type="chat_id")]

    if args.intent:
        rows = client.get_conversations_by_intent(args.intent, limit=args.limit)
        cases = []
        for row in rows[: args.limit]:
            if not isinstance(row, dict):
                continue
            chat_id = row.get("source_chat_id") or row.get("chatId") or row.get("id")
            messages = row.get("messages") if isinstance(row.get("messages"), list) else []
            if chat_id and messages:
                cases.append(
                    {
                        "id": f"intent_{args.intent}_{chat_id}",
                        "source": {"type": "intent", "chatId": chat_id, "label": args.intent},
                        "messages": [str(message) for message in messages if str(message).strip()],
                        "metadata": _safe_metadata(row.get("metadata")),
                        "expected": {"not_contains": ["{{Template_Reply}}", "<span"]},
                    }
                )
        if not cases:
            raise ValueError(f"no historical conversations found for intent={args.intent}")
        return cases

    filters: dict[str, Any] = {"agentId": int(args.source_agent_id)}
    if args.source_touch_point:
        filters["touchpoint"] = args.source_touch_point
    rows_resp = client.list_transcripts(
        page_size=args.limit,
        page_index=1,
        debug=True,
        begin_ts=args.begin_ts,
        end_ts=args.end_ts,
        **filters,
    )
    rows = _coerce_list_payload(rows_resp)
    cases = []
    for row in rows[: args.limit]:
        if not isinstance(row, dict):
            continue
        chat_id = row.get("chatId") or row.get("id")
        if chat_id:
            cases.append(_case_from_transcript(client, str(chat_id), source_type="agent_id", source_label=str(args.source_agent_id)))
    if not cases:
        raise ValueError(f"no transcript found for source agentId={args.source_agent_id}")
    return cases


def _content_similarity(left: str, right: str) -> float:
    left = _norm_text(left)
    right = _norm_text(right)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return round(difflib.SequenceMatcher(None, left, right).ratio(), 4)


def _extract_route(result: dict[str, Any]) -> dict[str, Any]:
    context = result.get("context") if isinstance(result.get("context"), dict) else {}
    ext = context.get("ext") if isinstance(context.get("ext"), dict) else {}
    agent = context.get("agent") if isinstance(context.get("agent"), dict) else {}
    run_info = ext.get("chatflow_run_info")
    final_node = {}
    if isinstance(run_info, list):
        for event in reversed(run_info):
            if not isinstance(event, dict):
                continue
            event_data = event.get("eventData") if isinstance(event.get("eventData"), dict) else {}
            if event.get("event") == "node_finished" or event_data.get("node_id"):
                final_node = event_data
                break
    elif isinstance(run_info, dict):
        final_node = run_info
    return {
        "agentId": agent.get("id") or agent.get("agentId"),
        "agentName": agent.get("name") or ext.get("invoke_agent_name"),
        "strategyName": result.get("strategyName"),
        "nodeId": final_node.get("node_id") or final_node.get("nodeId"),
        "nodeName": final_node.get("title") or final_node.get("node_name") or final_node.get("nodeName"),
        "nodeType": final_node.get("category") or final_node.get("node_type") or final_node.get("nodeType"),
    }


def _extract_node_runs(result: dict[str, Any]) -> dict[str, Any]:
    context = result.get("context") if isinstance(result.get("context"), dict) else {}
    ext = context.get("ext") if isinstance(context.get("ext"), dict) else {}
    run_info = ext.get("chatflow_run_info", [])
    node_runs = []
    errors = []
    status = None
    if isinstance(run_info, list):
        for event in run_info:
            if not isinstance(event, dict):
                continue
            event_data = event.get("eventData") if isinstance(event.get("eventData"), dict) else {}
            if event.get("event") == "chat_finished":
                status = event_data.get("status", "")
            if isinstance(event_data.get("error"), dict):
                errors.append(
                    {
                        "nodeId": event_data.get("node_id") or event_data.get("nodeId"),
                        "name": event_data["error"].get("name", ""),
                        "detail": str(event_data["error"].get("detail", ""))[:300],
                    }
                )
            if event.get("event") == "node_finished":
                node_runs.append(
                    {
                        "nodeId": event_data.get("node_id", ""),
                        "nodeName": event_data.get("title", ""),
                        "nodeType": event_data.get("category", ""),
                        "status": event_data.get("status", ""),
                        "outHandle": event_data.get("out_handle") or event_data.get("outHandle"),
                    }
                )
    return {
        "status": status,
        "nodeRuns": node_runs,
        "nodePath": [
            {
                "nodeId": item.get("nodeId"),
                "nodeName": item.get("nodeName"),
                "nodeType": item.get("nodeType"),
                "status": item.get("status"),
                "outHandle": item.get("outHandle"),
            }
            for item in node_runs
        ],
        "nodePathUnavailable": not bool(node_runs),
        "errors": errors,
    }


def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    execution = _extract_node_runs(result)
    return {
        "chatId": result.get("chatId"),
        "content": result.get("content") or "",
        "reason": result.get("reason") or result.get("noReplyReason"),
        "handoff": result.get("handoff"),
        "type": result.get("type"),
        "isEnd": result.get("isEnd"),
        "route": _extract_route(result),
        "execution": execution,
        "nodePath": execution["nodePath"],
        "nodePathUnavailable": execution["nodePathUnavailable"],
    }


def _expected_checks(expected: dict[str, Any], new_result: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    content = new_result.get("content") or ""
    if "handoff" in expected:
        checks.append(
            {
                "name": "expected_handoff",
                "pass": new_result.get("handoff") == expected["handoff"],
                "expected": expected["handoff"],
                "actual": new_result.get("handoff"),
            }
        )
    for item in expected.get("contains", []) or []:
        checks.append({"name": f"contains:{item}", "pass": str(item) in content})
    for item in expected.get("not_contains", []) or []:
        checks.append({"name": f"not_contains:{item}", "pass": str(item) not in content})
    route = new_result.get("route") or {}
    for key in ("agentName", "nodeName", "nodeType"):
        expected_key = f"route_{key}"
        if expected_key in expected:
            checks.append(
                {
                    "name": expected_key,
                    "pass": route.get(key) == expected[expected_key],
                    "expected": expected[expected_key],
                    "actual": route.get(key),
                }
            )
    return checks


def _side_metadata(base_metadata: dict[str, Any], agent_id: str | None) -> dict[str, Any]:
    metadata = dict(base_metadata or {})
    if agent_id:
        metadata["specified_agent_id"] = int(agent_id)
    return metadata


def _run_side(
    client: SolveaClient,
    *,
    bot_id: str | None,
    agent_id: str | None,
    touch_point: str,
    case: dict[str, Any],
    side: str,
) -> dict[str, Any]:
    chat_id = f"replay-{case.get('id') or uuid.uuid4().hex}-{side}-{uuid.uuid4().hex[:8]}"
    final = {}
    metadata = _side_metadata(case.get("metadata") or {}, agent_id)
    for message in case.get("messages", []) or []:
        final = client.chat_stream(
            message=message,
            bot_id=bot_id,
            chat_id=chat_id,
            touch_point=touch_point,
            metadata=metadata,
            option={"debug": True, "migrationReplay": True},
        )
    return _summarize_result(final if isinstance(final, dict) else {})


def _compare_case(old_result: dict[str, Any], new_result: dict[str, Any], expected: dict[str, Any], threshold: float) -> dict[str, Any]:
    similarity = _content_similarity(old_result.get("content", ""), new_result.get("content", ""))
    checks = _expected_checks(expected or {}, new_result)
    route_old = old_result.get("route") or {}
    route_new = new_result.get("route") or {}
    issues = []
    if similarity < threshold:
        issues.append("content_similarity_low")
    if old_result.get("handoff") != new_result.get("handoff"):
        issues.append("handoff_changed")
    if old_result.get("type") != new_result.get("type"):
        issues.append("type_changed")
    if route_old.get("agentName") and route_new.get("agentName") and route_old.get("agentName") != route_new.get("agentName"):
        issues.append("agent_route_changed")
    if any(not check["pass"] for check in checks):
        issues.append("expected_check_failed")
    return {
        "contentSimilarity": similarity,
        "handoffEqual": old_result.get("handoff") == new_result.get("handoff"),
        "typeEqual": old_result.get("type") == new_result.get("type"),
        "routeOld": route_old,
        "routeNew": route_new,
        "expectedChecks": checks,
        "issues": issues,
        "pass": not issues,
    }


def _render_html(report: dict[str, Any]) -> str:
    rows = []
    for case in report.get("cases", []):
        status = "PASS" if case.get("compare", {}).get("pass") else "REVIEW"
        issues = ", ".join(case.get("compare", {}).get("issues", []))
        node_path = case.get("new", {}).get("nodePath") or []
        node_path_text = "\n".join(
            f"{idx + 1}. {item.get('nodeType') or ''} {item.get('nodeName') or item.get('nodeId') or ''} [{item.get('status') or ''}]"
            for idx, item in enumerate(node_path)
        )
        if not node_path_text and case.get("new", {}).get("nodePathUnavailable"):
            node_path_text = "node_path_unavailable"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(case.get('id')))}</td>"
            f"<td>{status}</td>"
            f"<td>{case.get('compare', {}).get('contentSimilarity')}</td>"
            f"<td>{html.escape(issues)}</td>"
            f"<td><pre>{html.escape(node_path_text)}</pre></td>"
            f"<td><pre>{html.escape(_norm_text(case.get('old', {}).get('content')))}</pre></td>"
            f"<td><pre>{html.escape(_norm_text(case.get('new', {}).get('content')))}</pre></td>"
            "</tr>"
        )
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Multi-agent Replay Compare</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #172033; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d0d5dd; padding: 8px; vertical-align: top; }}
    th {{ background: #f2f4f7; }}
    pre {{ white-space: pre-wrap; max-width: 520px; }}
  </style>
</head>
<body>
  <h1>Multi-agent Replay Compare</h1>
  <p>Mode: {mode}</p>
  <p>Total: {total}, Pass: {passed}, Review: {review}</p>
  <table>
    <thead><tr><th>Case</th><th>Status</th><th>Similarity</th><th>Issues</th><th>New Node Path</th><th>Old</th><th>New</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
""".format(
        mode=html.escape(report.get("mode", "")),
        total=report.get("summary", {}).get("total", 0),
        passed=report.get("summary", {}).get("pass", 0),
        review=report.get("summary", {}).get("review", 0),
        rows="\n".join(rows),
    )


def _select_cases(cases: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.case_id:
        selected = [case for case in cases if str(case.get("id")) == str(args.case_id)]
        if not selected:
            raise ValueError(f"case_id not found: {args.case_id}")
        return selected[:1]
    return cases[: args.limit]


def run(args: argparse.Namespace) -> dict[str, Any]:
    source_client = None
    if args.cases_file:
        payload = _read_json(Path(args.cases_file))
        cases = payload.get("cases", payload if isinstance(payload, list) else [])
    else:
        source_client = None if args.synthetic else SolveaClient(env=args.env, project_id=args.project_id)
        cases = _fetch_cases_from_source(source_client, args)
    if not isinstance(cases, list):
        raise ValueError("cases file must be a JSON array or an object with cases[]")
    cases = _select_cases(cases, args)
    if args.save_cases_file:
        _write_json(Path(args.save_cases_file), {"cases": cases})

    report_cases = []
    client = source_client if args.execute and source_client is not None else SolveaClient(env=args.env, project_id=args.project_id) if args.execute else None
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("id") or f"case_{len(report_cases):03d}"
        if args.execute:
            old_result = _run_side(
                client,
                bot_id=args.old_bot_id,
                agent_id=args.old_agent_id,
                touch_point=args.touch_point,
                case={**case, "id": case_id},
                side="old",
            )
            new_result = _run_side(
                client,
                bot_id=args.new_bot_id or args.old_bot_id,
                agent_id=args.new_agent_id,
                touch_point=args.touch_point,
                case={**case, "id": case_id},
                side="new",
            )
        else:
            old_result = _summarize_result({})
            new_result = _summarize_result({})
        compare = _compare_case(old_result, new_result, case.get("expected") or {}, args.similarity_threshold)
        report_cases.append(
            {
                "id": case_id,
                "source": case.get("source"),
                "messages": case.get("messages", []),
                "metadataKeys": sorted((case.get("metadata") or {}).keys()),
                "old": old_result,
                "new": new_result,
                "compare": compare,
            }
        )

    passed = sum(1 for case in report_cases if case.get("compare", {}).get("pass"))
    report = {
        "mode": "execute" if args.execute else "dry-run",
        "env": args.env,
        "caseSource": "cases_file" if args.cases_file else "synthetic" if args.synthetic else "transcript_api",
        "savedCasesFile": args.save_cases_file,
        "old": {"botId": args.old_bot_id, "agentId": args.old_agent_id},
        "new": {"botId": args.new_bot_id or args.old_bot_id, "agentId": args.new_agent_id},
        "summary": {"total": len(report_cases), "pass": passed, "review": len(report_cases) - passed},
        "cases": report_cases,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-file", help="Optional replay cache. If omitted, generate/fetch one case from the selected source.")
    parser.add_argument("--save-cases-file", help="Persist generated/fetched cases so the same case can be replayed later.")
    parser.add_argument("--synthetic", action="store_true", help="Generate one synthetic smoke-test case instead of fetching transcript APIs.")
    parser.add_argument("--synthetic-case-id", help="Case id for --synthetic. Default: synthetic_order_status_smoke.")
    parser.add_argument(
        "--synthetic-message",
        action="append",
        help="User message for --synthetic. Can be repeated for multi-turn. Default: order status smoke message.",
    )
    parser.add_argument("--synthetic-metadata", help="JSON object metadata for --synthetic.")
    parser.add_argument("--source-chat-id", help="Fetch exactly this historical chatId and build one replay case.")
    parser.add_argument("--source-agent-id", help="Fetch one historical transcript that matched the old MULTI_AGENT agentId.")
    parser.add_argument("--intent", help="Fetch one historical transcript by intent name.")
    parser.add_argument("--old-bot-id")
    parser.add_argument("--new-bot-id")
    parser.add_argument("--old-agent-id")
    parser.add_argument("--new-agent-id")
    parser.add_argument("--env", choices=["staging", "prod"], default=os.environ.get("SOLVEA_ENV", "staging"))
    parser.add_argument("--project-id")
    parser.add_argument("--touch-point", default="LIVE_CHAT")
    parser.add_argument("--source-touch-point", help="Optional touchpoint filter when using --source-agent-id.")
    parser.add_argument("--begin-ts", type=int, help="Optional begin timestamp in ms when using --source-agent-id.")
    parser.add_argument("--end-ts", type=int, help="Optional end timestamp in ms when using --source-agent-id.")
    parser.add_argument("--similarity-threshold", type=float, default=0.55)
    parser.add_argument("--case-id", help="Run exactly one case by id.")
    parser.add_argument("--limit", type=int, default=1, help="Number of cases to run when --case-id is not set. Default: 1.")
    parser.add_argument("--execute", action="store_true", help="Actually call chat-stream. Default is dry-run.")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-html")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.cases_file and not (args.synthetic or args.source_chat_id or args.source_agent_id or args.intent):
        raise ValueError("provide --cases-file or one source: --synthetic, --source-chat-id, --source-agent-id, or --intent")
    if args.execute and not (args.old_bot_id or args.old_agent_id or args.new_agent_id):
        raise ValueError("--execute requires routing info such as --old-bot-id and/or --old-agent-id/--new-agent-id")
    report = run(args)
    _write_json(Path(args.out_json), report)
    if args.out_html:
        out_html = Path(args.out_html)
        out_html.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(_render_html(report), encoding="utf-8")
    first_case = report["cases"][0] if report.get("cases") else {}
    print(
        json.dumps(
            {
                "out_json": args.out_json,
                "out_html": args.out_html,
                "summary": report["summary"],
                "case": first_case.get("id"),
                "case_source": first_case.get("source"),
                "saved_cases_file": report.get("savedCasesFile"),
                "new_final_result": {
                    "content": first_case.get("new", {}).get("content"),
                    "handoff": first_case.get("new", {}).get("handoff"),
                    "type": first_case.get("new", {}).get("type"),
                    "route": first_case.get("new", {}).get("route"),
                    "nodePath": first_case.get("new", {}).get("nodePath"),
                    "nodePathUnavailable": first_case.get("new", {}).get("nodePathUnavailable"),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
