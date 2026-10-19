#!/usr/bin/env python3
"""Delivery 批量测试主管道。

读 cases.json / .xlsx / .csv（按后缀路由），按 touch-point 走 LIVE_CHAT/EMAIL，
10 并发 + ≥300 分批，输出 results+summary，可选触发 HTML/MD 报告。

cases 兼容并集 schema（POC + Delivery + 历史抽样三种来源）：
  [{name|case_name, messages, agent_name, agent_id, scenario, source_chat_id,
    intent, metadata, expected:{...}}, ...]

stdout 协议（与老 batch_test_job 一致）：
  =启动:  === batch_test_job start: {N} cases, touch_point={TP} ===
  每 10:  PROGRESS:{"done":..., "total":..., "currentAgent":"..."}
  完成:  JOB_DONE:{"done":..., "total":..., "outputFile":"...", "htmlFile":"...", "mdFile":"..."}
  异常:  JOB_ERROR:{"error":"...","traceback":"..."} (退出码 1)

用法：
  python3 batch_test.py --input cases.json --output results.json --report
  python3 batch_test.py --input cases.xlsx --touch-point EMAIL --workers 10
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403
from client import SolveaClient


# noReplyReason codes + multi-language "No content" variants.
# If content equals any of these, the reply is treated as a failure regardless of other fields.
SYSTEM_ERROR_PROMPTS = {
    # ── Human-readable system messages returned by API ──
    "No content has been generated",
    # ── Backend noReplyReason enum values ──
    "INTERNAL_ERROR",
    "STRATEGY_NOT_FOUND",
    "LACK_OF_KNOWLEDGE",
    "KNOWLEDGE_NOT_RELEVANT",
    "INTELLIGENT_CONTROL",
    "TRANSFER_TO_AGENT",
    "DO_NOTHING",
    "STOPPED",
    "SOP_STRATEGY_TO_AGENT",
    "TOOL_TO_AGENT",
    "STRATEGY_TO_AGENT",
    "POST_STRATEGY_TO_AGENT",
    "INTENT_TO_AGENT",
    "MANUAL_TO_AGENT",
    "STRATEGY_DO_NOTHING",
    "TOOL_DO_NOTHING",
    "SYSTEM_ERROR",
    "RED_LINE",
    "DUPLICATE_REPLY",
    "POST_CHECK",
    "COLLECT_EXCEED_MAX_TIMES",
    "URL_NOT_ACCESSIBLE",
    "AGENT_HAS_FINISHED",
    "TEXT_CONTENT_EMPTY",
    "QUALITY_CHECK",
    "HANDOFF_NO_REPLY",
    "MAX_TURN_EXCEED",
    "MAX_AGENT_INVOKE_COUNT_EXCEED",
    "LABEL_ATTACK",
    "LABEL_ENTICE",
    "LABEL_AMAZON_RED_LINE",
    "LABEL_CONTROL",
    "ROLE_CONFUSION",
    "REQUESTED_PROVIDED_INFO",
    "COMPETITIVE_BRAND_REC",
    "PROHIBITED_WORD",
    "UNCERTAINTY_EXPRESSION",
    "WITH_ATTACHMENT",
    "ACTIVE_TRANSFER_TO_HUMAN",
    "BUY_OTHER_BELITTLE_ONESELF",
    "LLM_CONTENT_FILTER",
    "LLM_TOKENS_EXCEED",
    "TEMPLATE_NOT_FOUND",
    "TEMPLATE_NOT_ENABLED",
    "SOP_NOT_FOUND",
    "SOP_NOT_ENABLED",
    "SOP_CALL_LOOP",
    "SOP_CALL_DEPTH_EXCEED",
    "SOP_EXIT",
    "FLOW_NOT_FOUND",
    "FLOW_CALL_FAILED",
    "TOOL_NOT_WORK",
    "TOOL_OCCUR_ERROR",
    "TOOL_CALL_LOOP",
    "TOOL_CALL_DEPTH_EXCEED",
    "TOOL_CALL_TIMES_EXCEED",
    "TEMPLATE_ENGINE_ERROR",
    "HANDOFF_CANCELLED",
    "QUERY_ORDER_FAIL",
    "CALL_AGENT_TRANSFER_TO_HUMAN",
    "CALL_TOOL_STATUS_TO_HUMAN",
    "CALL_MULTI_AGENT_UNKNOWN_ERROR",
    "INVOKE_LLM_ERROR",
    "REQUEST_TIMEOUT",
    "REQUEST_ILLEGAL",
    "CALL_TOOL_ERROR",
    "AGENT_NOT_FOUND",
    "HANDOFF_TOOL_STATUS",
    "AI_CONTENT_ILLEGAL",
    "REVIEW_MANIPULATION",
    "COLLECT_PRIVACY",
    "EXTERNAL_LINK",
    "REDIRECT_THIRD_PARTY",
    "DISPARAGE_COMPETITORS",
    "UNRELATED_REPLY",
    "REPEATED_EXPRESSION",
    "NEGATIVE_ATTITUDE",
    "WRONG_LANGUAGE",
    "MANUAL_PROCESSING_TRANSFER",
    "LACK_OF_KNOWLEDGE_OR_PROCESS",
    "CONTACT_TO_CUSTOMER_SERVICE",
    "FAKE_INFORMATION",
    "COMPLAINT",
    "MENTION_PRIVACY",
    "LEGAL_ISSUE",
    "MENTION_ACCIDENT",
    "NEGATIVE_REVIEW_ALERT",
    "ATTACK_AI",
    "MENTION_THEFT",
    "AGENT_TIMEOUT",
    "NO_CONTENT_GENERATED",
}

BATCH_SIZE = 150
BATCH_TRIGGER = 300
WORKERS = 10

# 用户上传文件的兼容列名 fallback（老版批测的进料习惯）
_FALLBACK_MSG_COLS = ["messages", "message", "content", "问题", "Message"]


# ── 入参加载 ────────────────────────────────────────────────────────────────

def _split_multi_turn(raw):
    """老版兜底单列：单格内 \\n 或 | 拆多轮。"""
    if raw is None:
        return []
    s = str(raw)
    if not s.strip():
        return []
    # 优先按换行分；没有换行再按 | 分；都没有则当作单轮
    if "\n" in s:
        parts = [p.strip() for p in s.split("\n") if p.strip()]
    elif "|" in s:
        parts = [p.strip() for p in s.split("|") if p.strip()]
    else:
        parts = [s.strip()]
    return parts


def _row_to_case(row: dict, idx: int) -> dict | None:
    """把 xlsx/csv 的一行（dict）按规则转成标准 case，命中失败返回 None。"""
    # Step 1: 新版严格列 message_1 / message_2 / message_3
    msgs = []
    for n in (1, 2, 3):
        v = row.get(f"message_{n}")
        if v is not None and str(v).strip():
            msgs.append(str(v).strip())

    # Step 2: 老版兜底列 messages / message / content / 问题 / Message
    if not msgs:
        for col in _FALLBACK_MSG_COLS:
            v = row.get(col)
            if v is not None and str(v).strip():
                msgs = _split_multi_turn(v)
                if msgs:
                    break

    if not msgs:
        return None

    expected = {}
    if row.get("expected_intent"):
        expected["intent"] = str(row["expected_intent"]).strip()
    if row.get("expected_handoff") not in (None, ""):
        v = row["expected_handoff"]
        if isinstance(v, bool):
            expected["handoff"] = v
        else:
            expected["handoff"] = str(v).strip().lower() in ("true", "1", "yes")
    if row.get("content_contains"):
        expected["content_contains"] = [s.strip() for s in
                                        str(row["content_contains"]).split(",") if s.strip()]
    if row.get("content_not_contains"):
        expected["content_not_contains"] = [s.strip() for s in
                                            str(row["content_not_contains"]).split(",") if s.strip()]
    if row.get("nodes_executed"):
        expected["nodes_executed"] = [s.strip() for s in
                                      str(row["nodes_executed"]).split(",") if s.strip()]
    if row.get("flow_status"):
        expected["flow_status"] = str(row["flow_status"]).strip()

    metadata_raw = row.get("metadata")
    metadata = {}
    if metadata_raw not in (None, ""):
        if isinstance(metadata_raw, dict):
            metadata = metadata_raw
        else:
            try:
                metadata = json.loads(str(metadata_raw))
            except Exception:
                metadata = {}

    case = {
        "name": row.get("case_name") or row.get("name") or f"row_{idx}",
        "agent_name": row.get("agent_name") or "",
        "agent_id": int(row["agent_id"]) if row.get("agent_id") not in (None, "") else None,
        "scenario": row.get("scenario") or "",
        "source_chat_id": row.get("source_chat_id") or "",
        "intent": row.get("intent") or "",
        "messages": msgs,
        "metadata": metadata,
        "expected": expected,
    }
    return case


def _load_cases_from_xlsx(path: str) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [(h or "").strip() if isinstance(h, str) else "" for h in rows[0]]
    cases = []
    for idx, raw in enumerate(rows[1:], start=2):
        if not any(c not in (None, "") for c in raw):
            continue
        row = {headers[i]: raw[i] if i < len(raw) else None for i in range(len(headers)) if headers[i]}
        case = _row_to_case(row, idx)
        if case is None:
            print(f"  WARN: row {idx} 无法解析 messages，已跳过", file=sys.stderr)
            continue
        cases.append(case)
    return cases


def _load_cases_from_csv(path: str) -> list[dict]:
    cases = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            if not any((v not in (None, "")) for v in row.values()):
                continue
            case = _row_to_case(row, idx)
            if case is None:
                print(f"  WARN: row {idx} 无法解析 messages，已跳过", file=sys.stderr)
                continue
            cases.append(case)
    return cases


def _load_cases_from_json(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} 顶层必须是 JSON list")
    out = []
    for idx, c in enumerate(data, start=1):
        if not isinstance(c, dict):
            continue
        if not c.get("messages") and c.get("message"):
            c["messages"] = [c["message"]]
        if not c.get("messages"):
            print(f"  WARN: case {idx} 缺 messages，已跳过", file=sys.stderr)
            continue
        c.setdefault("name", f"row_{idx}")
        out.append(c)
    return out


def _detect_and_load(path: str) -> list[dict]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        return _load_cases_from_xlsx(path)
    if ext == ".csv":
        return _load_cases_from_csv(path)
    if ext in (".json", ".jsonl"):
        return _load_cases_from_json(path)
    raise ValueError(f"不支持的文件类型：{ext}（支持 .json/.jsonl/.xlsx/.csv）")


# ── 协议输出 ────────────────────────────────────────────────────────────────

def emit(data: dict):
    prefix = "PROGRESS" if data.get("status") != "error" else "JOB_ERROR"
    print(f"{prefix}:{json.dumps(data, ensure_ascii=False)}", flush=True)


# ── chat 路由 ──────────────────────────────────────────────────────────────

def _build_metadata(case_metadata, specified_agent_id):
    """合并 case.metadata + (--agent-id → specified_agent_id)。"""
    md = dict(case_metadata or {})
    if specified_agent_id:
        md["specified_agent_id"] = int(specified_agent_id)
    return md


def _call_chat(client, msg, chat_id, touch_point, metadata,
               poll_interval=2.0, poll_timeout=300.0):
    """LIVE_CHAT → chat_stream；EMAIL → chat_async + 轮询 get_async_result。"""
    if touch_point == "LIVE_CHAT":
        return client.chat_stream(
            message=msg, chat_id=chat_id,
            touch_point="LIVE_CHAT", metadata=metadata or None)

    # EMAIL: chat_async → poll
    receipt_resp = client.chat_async(
        message=msg, chat_id=chat_id,
        touch_point="EMAIL", metadata=metadata or None)
    receipt = receipt_resp.get("receipt") if isinstance(receipt_resp, dict) else None
    if not receipt:
        # 客户端层无 receipt → 当作错误抛回
        err = receipt_resp.get("errorMessage") if isinstance(receipt_resp, dict) else "no receipt"
        raise RuntimeError(f"chat_async no receipt: {err}")

    deadline = time.time() + poll_timeout
    while time.time() < deadline:
        time.sleep(poll_interval)
        result = client.get_async_result(receipt)
        if isinstance(result, dict) and result.get("completed"):
            data = result.get("data") or {}
            if isinstance(data, dict):
                return data
            return result
    return {"_error": "poll timeout", "content": "", "reason": "REQUEST_TIMEOUT"}


# ── 单 case / 批量 ─────────────────────────────────────────────────────────

def run_case(client, case: dict, touch_point: str, specified_agent_id=None,
             poll_interval=2.0, poll_timeout=300.0) -> list[dict]:
    """跑一个 case（可多轮），返回 detail 行 list。

    多轮规则（与老版一致）：metadata 只在首轮带，后续轮次清空。
    """
    messages = case.get("messages", [])
    case_metadata = _build_metadata(case.get("metadata"), specified_agent_id)
    source_chat_id = case.get("source_chat_id", "")
    intent = case.get("intent", "")
    rows = []
    chat_id = None

    for i, msg in enumerate(messages):
        msg = msg.get("content", str(msg)) if isinstance(msg, dict) else msg
        round_num = i + 1
        try:
            metadata = case_metadata if i == 0 else {}
            resp = _call_chat(
                client, msg, chat_id, touch_point, metadata,
                poll_interval=poll_interval, poll_timeout=poll_timeout,
            )
            if chat_id is None:
                chat_id = (resp.get("chatId") or resp.get("chat_id")
                           or (resp.get("data") or {}).get("chatId", ""))
            content = resp.get("content") or ""
            no_reply_reason = resp.get("reason") or ""
            ctx = resp.get("context") or {}
            agent = (ctx.get("agent", "")
                     or resp.get("agentName", "")
                     or (ctx.get("ext") or {}).get("invoke_agent_name", ""))
            strategy = resp.get("strategyName", "") or ""
            action = agent or strategy
            handoff = bool(resp.get("handoff"))
            rows.append({
                "source_chat_id": source_chat_id, "new_chat_id": chat_id or "",
                "intent": intent, "action": action,
                "round": round_num, "question": msg,
                "answer": content, "handoff": handoff,
                "no_reply_reason": no_reply_reason,
                "_replied": no_reply_reason not in SYSTEM_ERROR_PROMPTS, "_error": "",
            })
        except Exception as e:
            rows.append({
                "source_chat_id": source_chat_id, "new_chat_id": chat_id or "",
                "intent": intent, "action": "",
                "round": round_num, "question": msg,
                "answer": "", "handoff": False,
                "no_reply_reason": "",
                "_replied": False, "_error": str(e)[:80],
            })
    return rows


def _dump_partial(path: str, rows: list[dict], done_keys: set[str]):
    """把内部 rows + done_keys 落盘到 partial 文件（覆盖式）。"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"rows": rows, "done_keys": sorted(done_keys)}, f,
                      ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  WARN: partial save failed: {e}", file=sys.stderr)


def run_cases(client, cases, touch_point, specified_agent_id,
              workers=WORKERS, batch_size=BATCH_SIZE, batch_trigger=BATCH_TRIGGER,
              poll_interval=2.0, poll_timeout=300.0,
              partial_path: str | None = None,
              prev_rows: list[dict] | None = None,
              prev_done_keys: set[str] | None = None):
    """≥batch_trigger 切片 → 每片 ThreadPoolExecutor 并发；每 10 case emit PROGRESS。

    若传入 partial_path，每完成一批后把全量内部 rows+done_keys 落盘，供续跑读取。

    与老版差异（spec 风险 #2）：分批统一应用到 concurrent，老版 _run_cases_concurrent 漏。
    """
    total = len(cases)
    batches = ([cases[i:i + batch_size] for i in range(0, total, batch_size)]
               if total >= batch_trigger else [cases])

    new_rows: list[dict] = []
    base_rows = list(prev_rows or [])
    done_keys: set[str] = set(prev_done_keys or set())
    counter = {"done": 0}
    lock = threading.Lock()

    def run_one(case):
        case_key = _case_key(case)
        try:
            rows = run_case(client, case, touch_point, specified_agent_id,
                            poll_interval=poll_interval, poll_timeout=poll_timeout)
        except Exception as e:
            rows = [{
                "source_chat_id": case.get("source_chat_id", ""),
                "new_chat_id": "", "intent": case.get("intent", ""),
                "action": "", "round": 1,
                "question": (case.get("messages") or [""])[0] if case.get("messages") else "",
                "answer": "", "handoff": False,
                "no_reply_reason": "",
                "_replied": False, "_error": str(e)[:80],
            }]
        with lock:
            counter["done"] += 1
            done = counter["done"]
            current_agent = rows[-1].get("action", "") if rows else ""
        if done % 10 == 0 or done == total:
            emit({"done": done, "total": total, "currentAgent": current_agent})
        return case_key, rows

    for batch in batches:
        batch_results: list[tuple[str, list[dict]] | None] = [None] * len(batch)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(run_one, c): idx for idx, c in enumerate(batch)}
            for f in as_completed(futures):
                idx = futures[f]
                batch_results[idx] = f.result()
        for item in batch_results:
            if not item:
                continue
            case_key, rows = item
            if rows:
                new_rows.extend(rows)
            if case_key:
                done_keys.add(case_key)
        if partial_path:
            _dump_partial(partial_path, base_rows + new_rows, done_keys)

    return new_rows, done_keys


# ── summary ────────────────────────────────────────────────────────────────

def build_summary(all_rows: list) -> dict:
    total_messages = len(all_rows)
    total_replied = sum(1 for r in all_rows if r["_replied"])
    chat_ids = set(r["new_chat_id"] for r in all_rows if r["new_chat_id"])
    total_conversations = len(chat_ids)
    reply_rate = round(total_replied / total_messages, 4) if total_messages else 0

    agent_rows = defaultdict(list)
    for r in all_rows:
        agent_rows[r["action"] or "Unknown"].append(r)

    agents = []
    for agent_name, rows in agent_rows.items():
        by_round = defaultdict(list)
        for r in rows:
            by_round[r["round"]].append(r)
        replied = sum(1 for r in rows if r["_replied"])

        def rr(n, by_round=by_round):
            rws = by_round.get(n, [])
            return round(sum(1 for r in rws if r["_replied"]) / len(rws), 4) if rws else None

        agents.append({
            "name": agent_name,
            "total_conversations": len(set(r["new_chat_id"] for r in rows if r["new_chat_id"])),
            "total_messages": len(rows),
            "replied_messages": replied,
            "reply_rate": round(replied / len(rows), 4) if rows else 0,
            "r1_reply_rate": rr(1),
            "r2_reply_rate": rr(2),
            "r3_reply_rate": rr(3),
            "rs_reply_rate": round(replied / len(rows), 4) if rows else 0,
        })

    handoff_counts = defaultdict(int)
    for r in all_rows:
        if r["handoff"]:
            handoff_counts["直接转人工"] += 1
    total_handoff = sum(handoff_counts.values())
    handoff = [{"type": t, "count": c,
                "rate": round(c / total_handoff, 4) if total_handoff else 0}
               for t, c in handoff_counts.items()]

    error_counts = defaultdict(int)
    for r in all_rows:
        if r["_error"]:
            error_counts[r["_error"][:40]] += 1
    total_errors = sum(error_counts.values())
    errors = [{"type": t, "count": c,
               "rate": round(c / total_errors, 4) if total_errors else 0}
              for t, c in error_counts.items()]

    no_reply_counts = defaultdict(int)
    for r in all_rows:
        if r.get("no_reply_reason"):
            no_reply_counts[r["no_reply_reason"]] += 1
    total_no_reply = sum(no_reply_counts.values())
    no_reply_reasons = [{"reason": rsn, "count": c,
                         "rate": round(c / total_no_reply, 4) if total_no_reply else 0}
                        for rsn, c in sorted(no_reply_counts.items(), key=lambda x: -x[1])]

    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_replied": total_replied,
        "reply_rate": reply_rate,
        "agents": agents,
        "handoff": handoff,
        "errors": errors,
        "no_reply_reasons": no_reply_reasons,
    }


# ── partial 续跑 ───────────────────────────────────────────────────────────

def _load_partial(path: str) -> tuple[list[dict], set[str]]:
    """读 partial JSON，返回 (已完成内部 rows, 已完成的 case 标识集合)。

    partial schema：{"rows": [<内部 row dict 含 _replied/_error/handoff>...],
                    "done_keys": [<key>...]}。
    case 标识用 source_chat_id（历史抽样）或 question 首轮值兜底。
    """
    if not path or not os.path.exists(path):
        return [], set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return [], set()
    if not isinstance(data, dict):
        return [], set()
    rows = data.get("rows")
    if not isinstance(rows, list):
        return [], set()
    done_keys_raw = data.get("done_keys")
    if isinstance(done_keys_raw, list) and done_keys_raw:
        done = {str(k) for k in done_keys_raw if k}
    else:
        # 兜底：从 rows 反推 done_keys
        done = set()
        for r in rows:
            key = r.get("source_chat_id") or r.get("question")
            if key:
                done.add(str(key))
    return rows, done


def _case_key(case: dict) -> str:
    sid = case.get("source_chat_id") or ""
    if sid:
        return str(sid)
    msgs = case.get("messages") or []
    return str(msgs[0]) if msgs else ""


# ── main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Solvea Delivery Batch Tester")
    parser.add_argument("--input", required=True,
                        help="cases.json / .xlsx / .csv（按后缀路由）")
    parser.add_argument("--output", required=True, help="results JSON 输出路径")
    parser.add_argument("--touch-point", default="LIVE_CHAT",
                        choices=["LIVE_CHAT", "EMAIL"],
                        help="LIVE_CHAT→chat_stream；EMAIL→chat_async+轮询")
    parser.add_argument("--agent-id", type=int,
                        help="全局强制路由（脚本组装 metadata.specified_agent_id）")
    parser.add_argument("--workers", type=int, default=WORKERS, help="并发 worker 数")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="单批大小")
    parser.add_argument("--batch-trigger", type=int, default=BATCH_TRIGGER,
                        help="触发分批的最小 case 数")
    parser.add_argument("--poll-interval", type=float, default=2.0,
                        help="EMAIL 轮询间隔（秒）")
    parser.add_argument("--poll-timeout", type=float, default=300.0,
                        help="EMAIL 单 case 最长等待（秒）")
    parser.add_argument("--partial", help="断点续传 partial JSON 路径")
    parser.add_argument("--report", action="store_true",
                        help="同步触发 gen_delivery_report.py 渲染 HTML+MD")
    args = parser.parse_args()

    cases = _detect_and_load(args.input)
    total_cases = len(cases)

    # partial 续跑：跳过已完成的 case
    partial_rows, done_keys = _load_partial(args.partial) if args.partial else ([], set())
    if done_keys:
        cases = [c for c in cases if _case_key(c) not in done_keys]
        print(f"  partial 续跑：跳过 {total_cases - len(cases)} 条已完成", file=sys.stderr)

    total = len(cases)
    print(f"=== batch_test_job start: {total} cases, touch_point={args.touch_point} ===",
          flush=True)

    client = SolveaClient()

    new_rows, done_keys = run_cases(
        client, cases, args.touch_point, args.agent_id,
        workers=args.workers, batch_size=args.batch_size,
        batch_trigger=args.batch_trigger,
        poll_interval=args.poll_interval, poll_timeout=args.poll_timeout,
        partial_path=args.partial,
        prev_rows=partial_rows, prev_done_keys=done_keys,
    )

    all_rows = list(partial_rows) + new_rows

    summary = build_summary(all_rows)
    details = [{
        "source_chat_id": r.get("source_chat_id", ""),
        "new_chat_id": r.get("new_chat_id", ""),
        "intent": r.get("intent", ""),
        "action": r.get("action", ""),
        "round": r.get("round", ""),
        "question": r.get("question", ""),
        "answer": r.get("answer", ""),
        "no_reply_reason": r.get("no_reply_reason", ""),
        "judge": "", "correct": "",
    } for r in all_rows]

    base = os.path.splitext(os.path.abspath(args.output))[0]
    html_file = base + ".html"
    md_file = base + ".md"

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": details}, f,
                  ensure_ascii=False, indent=2)

    # partial 完成后再补一次最终落盘（保证 done_keys 与 all_rows 一致）
    if args.partial:
        _dump_partial(args.partial, all_rows, done_keys)

    if args.report:
        report_script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "gen_delivery_report.py")
        try:
            subprocess.run(
                [sys.executable, report_script,
                 "--results", args.output,
                 "--html", html_file, "--md", md_file],
                check=True,
            )
        except Exception as e:
            print(f"  WARN: report render failed: {e}", file=sys.stderr)

    done_rows = len(all_rows)
    done_cases = len(done_keys) if done_keys else total_cases
    print("JOB_DONE:" + json.dumps({
        "done": done_rows, "total": done_rows,
        "done_cases": done_cases, "total_cases": total_cases,
        "outputFile": args.output,
        "htmlFile": html_file if args.report else "",
        "mdFile": md_file if args.report else "",
    }), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("JOB_ERROR:" + json.dumps({
            "error": str(e), "traceback": traceback.format_exc(),
        }), flush=True)
        sys.exit(1)
