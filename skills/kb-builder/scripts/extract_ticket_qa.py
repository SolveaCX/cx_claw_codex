#!/usr/bin/env python3
"""
extract_ticket_qa.py — Extract clean QA knowledge from historical ticket xlsx.

Supports two xlsx formats:
  1. Solvea inbox export: 'conversations' column with numbered dialog
  2. Custom system export: auto-detects conversation columns by header name/content

Output: workspace/outputs/kb-builder/ticket_qa_{ts}.json
        each item: {topic, question, answer, dir_path:[]}
        (agent assigns dir_path based on directory tree + topic)

Usage:
    python3 extract_ticket_qa.py --xlsx mounted/chat-files/user/tickets.xlsx --brand "Anker" --page 1 --page-size 100 --batch-size 5
    python3 extract_ticket_qa.py --xlsx mounted/chat-files/user/tickets.xlsx --brand "Anker" --messages-col conversations --title-col subject
    python3 extract_ticket_qa.py --xlsx mounted/chat-files/user/tickets.xlsx --brand "Anker" --dry-run
"""
from __future__ import annotations
import argparse, json, os, sys, time
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *

import pandas as pd
from openai import OpenAI

MAX_PAGE_SIZE = 100
MAX_BATCH_SIZE = 10
MAX_WORKERS = 4
SERVICE_MANAGED_MODEL = "server-managed"


@dataclass(frozen=True)
class PageWindow:
    page: int
    page_size: int
    start_row: int
    end_row: int
    total_rows: int


@dataclass(frozen=True)
class ColumnSelection:
    mode: str
    messages_col: str | None = None
    title_col: str | None = None
    reply_col: str | None = None
    fallback_col: str | None = None


def select_rows(df: pd.DataFrame, page: int, page_size: int) -> tuple[pd.DataFrame, PageWindow]:
    if page < 1:
        raise ValueError(f"page must be >= 1, got {page}")
    if page_size < 1:
        raise ValueError(f"page-size must be >= 1, got {page_size}")
    if page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page-size {page_size} exceeds maximum {MAX_PAGE_SIZE}")

    total_rows = len(df)
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)
    selected = df.iloc[start_idx:end_idx].copy()
    start_row = start_idx + 1 if start_idx < total_rows else total_rows + 1
    window = PageWindow(
        page=page,
        page_size=page_size,
        start_row=start_row,
        end_row=end_idx,
        total_rows=total_rows,
    )
    return selected, window

EXTRACT_BATCH_PROMPT = """\
You are a knowledge base engineer extracting reusable product knowledge from a customer support conversation for {brand}.

CONVERSATIONS:
{items_json}

For EACH conversation, extract zero or one clean Q&A pair following these strict rules.

QUESTION rules:
- Rewrite the customer's core issue as a generic, searchable question
- Remove ALL personal info (names, order numbers, addresses, phone numbers, dates)
- Make it product-centric and reusable (e.g. "Anker 737 PowerBank — Why does it stop charging at 80%?")
- Format: "[Brand Product Name] — [question]"

ANSWER rules:
- Output as **markdown** (Solvea KB renders markdown end-to-end):
  * Bullet lists: `- item`
  * Ordered steps: `1. ... 2. ... 3. ...` for step-by-step procedures
  * Bold key terms: `**term**` for product names, settings, key parameters
  * Tables `| col | col |` for spec/comparison data when applicable
  * Code/values: `` `value` `` for short code-like tokens (model numbers, paths)
- Extract ONLY reusable product knowledge: steps, specs, solutions, tips
- REMOVE: order-specific details, "contact support" instructions, apologies, case-specific info, customer names
- REMOVE: any instruction that requires agent action (e.g. "we will issue a refund")
- Keep: troubleshooting steps, how-to instructions, compatibility info, product specs

TOPIC: classify into exactly one of:
  product_info | setup_installation | usage_guide | troubleshooting | compatibility | warranty_maintenance

SKIP_REASON: If this conversation is ENTIRELY about one of these — set skip_reason:
  logistics | shipping | delivery | tracking | order_status | order_cancel | order_modify |
  return | refund | exchange | account | payment | billing
  Otherwise set to null.

Respond with JSON only, no markdown wrapper. Return an array with one object per input item:
[
  {{"source_row": 1, "question": "...", "answer": "...", "topic": "...", "skip_reason": null}},
  {{"source_row": 2, "question": "", "answer": "", "topic": "", "skip_reason": "logistics"}}
]

If conversation should be skipped:
{{"source_row": <same source_row>, "question": "", "answer": "", "topic": "", "skip_reason": "logistics"}}"""


def _require_column(df: pd.DataFrame, col: str | None, arg_name: str) -> str | None:
    if not col:
        return None
    if col not in df.columns:
        raise ValueError(f"{arg_name} '{col}' not found. Available columns: {list(df.columns)}")
    return col


def _score_conversation_column(df: pd.DataFrame, col: str) -> int:
    name = col.strip().lower()
    score = 0
    strong_names = [
        "conversations", "conversation", "messages", "comments_json", "comments",
        "chat_history", "message_history", "聊天记录", "对话", "对话内容", "工单内容",
    ]
    weak_names = ["message", "content", "body", "description", "text", "问题", "客户"]
    noise_names = ["status", "state", "order", "email", "phone", "tag", "time", "date", "url", "id"]
    if any(h in name for h in strong_names):
        score += 80
    if any(h in name for h in weak_names):
        score += 35
    if any(h in name for h in noise_names):
        score -= 30

    sample = "\n".join(df[col].dropna().astype(str).head(8).tolist())
    avg_len = df[col].dropna().astype(str).head(20).str.len().mean()
    if avg_len and avg_len > 120:
        score += 25
    if avg_len and avg_len > 500:
        score += 20
    markers = ["user:", "customer:", "agent:", "assistant:", "ai_", "(1)", "body", "author", "客服", "客户"]
    lowered = sample.lower()
    score += sum(8 for marker in markers if marker in lowered)
    if sample.strip().startswith("[") and ("body" in lowered or "content" in lowered):
        score += 30
    return score


def detect_message_reply_columns(df: pd.DataFrame) -> tuple[str | None, str | None]:
    """For split-column exports: find user-message column and agent-reply column by name hints."""
    msg_hints = ["message", "question", "customer", "user", "inquiry", "content", "body",
                 "问题", "用户", "客户", "来信", "first_message"]
    rep_hints = ["reply", "answer", "response", "agent", "support", "resolution",
                 "客服", "回复", "答案"]
    cols = list(df.columns)
    cols_lower = [c.lower() for c in cols]
    msg_col, rep_col = None, None
    for i, cl in enumerate(cols_lower):
        if msg_col is None and any(h in cl for h in msg_hints):
            msg_col = cols[i]
        if rep_col is None and any(h in cl for h in rep_hints):
            rep_col = cols[i]
    return msg_col, rep_col


def detect_best_conversation_column(df: pd.DataFrame) -> str | None:
    scored = [(_score_conversation_column(df, col), col) for col in df.columns]
    scored.sort(reverse=True)
    if scored and scored[0][0] >= 50:
        return scored[0][1]
    return None


def detect_longest_text_column(df: pd.DataFrame) -> str | None:
    """Fallback: find the column with the longest average text content."""
    best_col, best_avg = None, 0
    for col in df.columns:
        sample = df[col].dropna().astype(str).head(20)
        avg_len = sample.str.len().mean()
        if avg_len > best_avg:
            best_avg = avg_len
            best_col = col
    return best_col if best_avg > 80 else None


def resolve_columns(
    df: pd.DataFrame,
    messages_col: str | None,
    title_col: str | None,
    reply_col: str | None,
) -> ColumnSelection:
    messages_col = _require_column(df, messages_col, "--messages-col")
    title_col = _require_column(df, title_col, "--title-col")
    reply_col = _require_column(df, reply_col, "--reply-col")

    if messages_col:
        return ColumnSelection(mode="split" if reply_col else "single", messages_col=messages_col, title_col=title_col, reply_col=reply_col)

    detected = detect_best_conversation_column(df)
    if detected:
        return ColumnSelection(mode="single", messages_col=detected, title_col=title_col)

    msg_col, rep_col = detect_message_reply_columns(df)
    if msg_col and rep_col:
        return ColumnSelection(mode="split", messages_col=msg_col, title_col=title_col, reply_col=rep_col)

    fallback_col = detect_longest_text_column(df)
    if fallback_col:
        return ColumnSelection(mode="fallback", fallback_col=fallback_col, title_col=title_col)

    raise ValueError("Cannot detect conversation column. Use --messages-col or --messages-col + --reply-col.")


def _clean_cell(value) -> str:
    text = str(value).strip() if pd.notna(value) else ""
    return "" if text.lower() == "nan" else text


def build_thread(row: pd.Series, columns: ColumnSelection) -> str | None:
    """Convert a dataframe row into a conversation thread string."""
    title = _clean_cell(row.get(columns.title_col)) if columns.title_col else ""

    if columns.mode == "single" and columns.messages_col:
        text = _clean_cell(row.get(columns.messages_col))
        if not text:
            return None
        return f"Title: {title}\n\n{text}" if title else text

    if columns.mode == "split" and columns.messages_col and columns.reply_col:
        q = _clean_cell(row.get(columns.messages_col))
        a = _clean_cell(row.get(columns.reply_col))
        if q or a:
            thread = f"Customer: {q}\n\nAgent: {a}"
            return f"Title: {title}\n\n{thread}" if title else thread
        return None

    if columns.mode == "fallback" and columns.fallback_col:
        text = _clean_cell(row.get(columns.fallback_col))
        if not text:
            return None
        return f"Title: {title}\n\n{text}" if title else text

    return None


def _loads_json_response(text: str):
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def extract_batch(client: OpenAI, items: list[dict], brand: str) -> list[dict]:
    payload = [
        {"source_row": item["source_row"], "conversation": item["thread"][:2500]}
        for item in items
    ]
    prompt = EXTRACT_BATCH_PROMPT.format(
        brand=brand,
        items_json=json.dumps(payload, ensure_ascii=False, indent=2),
    )
    try:
        resp = client.chat.completions.create(
            # /internal/openai/v1 overwrites this sentinel with the service-managed model.
            model=SERVICE_MANAGED_MODEL,
            max_tokens=max(800, 500 * len(items)),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        result = _loads_json_response(text)
        if isinstance(result, dict):
            result = [result]
        return result if isinstance(result, list) else []
    except Exception as e:
        rows = [item["source_row"] for item in items]
        raise RuntimeError(f"batch extraction failed rows={rows}: {e}") from e


def chunked(items: list, size: int):
    if size < 1:
        raise ValueError(f"batch-size must be >= 1, got {size}")
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _normalize_result(result: dict) -> dict | None:
    if result.get("skip_reason"):
        return {"skip_reason": result.get("skip_reason"), "source_row": result.get("source_row")}
    q = str(result.get("question", "")).strip()
    a = str(result.get("answer", "")).strip()
    topic = result.get("topic", "troubleshooting")
    if q and a and len(a) > 20:
        return {
            "source_row": result.get("source_row"),
            "topic": topic,
            "question": q,
            "answer": a,
            "dir_path": [],
        }
    return None


def run(
    xlsx_path: str,
    brand: str,
    page: int,
    page_size: int,
    dry_run: bool,
    messages_col: str | None,
    title_col: str | None,
    reply_col: str | None,
    batch_size: int,
    workers: int,
) -> None:
    if batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch-size {batch_size} exceeds maximum {MAX_BATCH_SIZE}")
    if workers < 1 or workers > MAX_WORKERS:
        raise ValueError(f"workers must be 1-{MAX_WORKERS}, got {workers}")

    print(f"[extract] Reading {xlsx_path}")
    df = pd.read_excel(xlsx_path)
    df, window = select_rows(df, page=page, page_size=page_size)

    print(
        f"[extract] Processing page {window.page} pageSize {window.page_size} "
        f"| rows {window.start_row}-{window.end_row} of {window.total_rows}"
    )
    print(f"[extract] {len(df)} rows in this page | Columns: {list(df.columns)}")

    columns = resolve_columns(df, messages_col=messages_col, title_col=title_col, reply_col=reply_col)
    print(
        "[detect] "
        f"mode={columns.mode} messages_col={columns.messages_col} "
        f"reply_col={columns.reply_col} title_col={columns.title_col} fallback_col={columns.fallback_col}"
    )

    items: list[dict] = []
    for offset, (_, row) in enumerate(df.iterrows(), start=window.start_row):
        thread = build_thread(row, columns)
        if thread:
            items.append({"source_row": offset, "thread": thread})

    if dry_run:
        sample = None
        if items:
            sample = items[0]["thread"]
        print(f"\n[dry-run] Sample thread preview:\n{'-'*60}")
        print((sample or "(no content found)")[:600])
        print(f"{'-'*60}")
        calls = (len(items) + batch_size - 1) // batch_size if items else 0
        print(f"\n[dry-run] {len(items)}/{len(df)} rows have conversation content")
        print(f"[dry-run] Would call the service-managed model {calls} times with batch-size={batch_size}, workers={workers}")
        print("[dry-run] Output -> workspace/outputs/kb-builder/ticket_qa_<ts>.json")
        return

    # Sandbox injects OPENAI_BASE_URL + dummy OPENAI_API_KEY for the internal proxy.
    client = OpenAI()

    qa_pairs: list[dict] = []
    skipped = 0
    failed = 0

    batches = list(chunked(items, batch_size))
    print(f"[extract] {len(items)} valid rows -> {len(batches)} model calls | batch-size={batch_size} workers={workers}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_batch, client, batch, brand): len(batch) for batch in batches}
        for done, future in enumerate(as_completed(futures), start=1):
            results = future.result()
            if not results:
                failed += futures[future]
            for result in results:
                normalized = _normalize_result(result)
                if not normalized:
                    failed += 1
                elif normalized.get("skip_reason"):
                    skipped += 1
                else:
                    qa_pairs.append(normalized)
            print(f"  [batch {done}/{len(batches)}] extracted={len(qa_pairs)} skipped={skipped} failed={failed}")

    qa_pairs.sort(key=lambda item: item.get("source_row") or 0)

    ts = timestamp()
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / f"ticket_qa_{ts}.json"
    out_path.write_text(json.dumps(qa_pairs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[extract_ticket_qa] Output -> {out_path}")

    print(f"\n[extract] Done: {len(qa_pairs)} QA extracted | {skipped} skipped (non-product) | {failed} failed/empty")
    print(f"[extract] Output: {out_path}")
    print(f"\nNext step: assign dir_path for each item, merge into qa_plan, then run import_qa.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx",     required=True, help="Path to ticket xlsx (e.g. mounted/chat-files/user/tickets.xlsx)")
    ap.add_argument("--brand",    required=True, help="Brand name prefix for questions")
    ap.add_argument("--page", type=int, default=1, help="1-based page number to process")
    ap.add_argument("--page-size", type=int, default=100, dest="page_size", help=f"Rows per page, max {MAX_PAGE_SIZE}")
    ap.add_argument("--messages-col", default=None, help="Column containing full conversation or customer message")
    ap.add_argument("--title-col", default=None, help="Optional ticket title/subject column")
    ap.add_argument("--reply-col", default=None, help="Optional agent reply column when customer/reply are split")
    ap.add_argument("--batch-size", type=int, default=5, dest="batch_size", help=f"Conversations per model call, max {MAX_BATCH_SIZE}")
    ap.add_argument("--workers", type=int, default=3, help=f"Parallel model calls, max {MAX_WORKERS}")
    ap.add_argument("--dry-run",  action="store_true", dest="dry_run")
    args = ap.parse_args()
    try:
        run(
            args.xlsx,
            args.brand,
            args.page,
            args.page_size,
            args.dry_run,
            args.messages_col,
            args.title_col,
            args.reply_col,
            args.batch_size,
            args.workers,
        )
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
