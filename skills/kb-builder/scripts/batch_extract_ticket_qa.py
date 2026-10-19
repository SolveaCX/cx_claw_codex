#!/usr/bin/env python3
"""
Batch wrapper for extract_ticket_qa.py.

Reads one xlsx, processes it page by page, stores page artifacts in state, then
merges and de-duplicates into a single output JSON. It never uploads knowledge.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *

from openai import OpenAI
import pandas as pd

from extract_ticket_qa import (
    MAX_BATCH_SIZE,
    MAX_PAGE_SIZE,
    MAX_WORKERS,
    build_thread,
    chunked,
    extract_batch,
    resolve_columns,
    select_rows,
)


STATE_ROOT = STATE_DIR / "ticket_extract"
PAGES_DIR = STATE_ROOT / "pages"
PROGRESS_FILE = STATE_ROOT / "progress.json"

PRE_FILTER_PATTERNS = [
    r"\btracking\b",
    r"\bdelivery\b",
    r"\bshipping\b",
    r"\border status\b",
    r"\brefund\b",
    r"\breturn\b",
    r"\bexchange\b",
    r"\bpayment\b",
    r"\binvoice\b",
    r"\baccount\b",
    r"\bplease send (a )?(photo|picture|image|receipt|order number)",
    r"\bcontact (customer )?(support|service)\b",
    r"\bsubmit (a )?(ticket|case)\b",
    r"\bbroken on arrival\b",
    r"\bdamaged on arrival\b",
]

POST_FILTER_PATTERNS = [
    r"contact (customer )?(support|service)",
    r"submit (a )?(ticket|case)",
    r"send (a )?(photo|picture|image|receipt|order number)",
    r"we will (issue|send|process)",
]


def normalize_question(question: str) -> str:
    text = question.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def should_pre_filter(thread: str) -> bool:
    lowered = thread.lower()
    return any(re.search(pattern, lowered) for pattern in PRE_FILTER_PATTERNS)


def should_post_filter(item: dict) -> bool:
    answer = str(item.get("answer", "")).lower()
    return any(re.search(pattern, answer) for pattern in POST_FILTER_PATTERNS)


def merge_and_dedupe(page_files: list[Path]) -> tuple[list[dict], dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    stats = {"input": 0, "post_filtered": 0, "deduped": 0}

    for page_file in page_files:
        data = json.loads(page_file.read_text(encoding="utf-8"))
        for item in data.get("qa_pairs", []):
            stats["input"] += 1
            if should_post_filter(item):
                stats["post_filtered"] += 1
                continue
            key = normalize_question(str(item.get("question", "")))
            if not key:
                continue
            if key in seen:
                stats["deduped"] += 1
                continue
            seen.add(key)
            merged.append(item)

    merged.sort(key=lambda item: (item.get("source_page") or 0, item.get("source_row") or 0))
    stats["output"] = len(merged)
    return merged, stats


def _page_file(page: int) -> Path:
    return PAGES_DIR / f"page_{page:03d}.json"


def _write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def process_page(
    *,
    df: pd.DataFrame,
    page: int,
    page_size: int,
    brand: str,
    messages_col: str | None,
    title_col: str | None,
    reply_col: str | None,
    batch_size: int,
    workers: int,
    client,
) -> dict:
    page_df, window = select_rows(df, page=page, page_size=page_size)
    columns = resolve_columns(page_df, messages_col=messages_col, title_col=title_col, reply_col=reply_col)

    items: list[dict] = []
    pre_filtered = 0
    empty = 0
    for source_row, (_, row) in enumerate(page_df.iterrows(), start=window.start_row):
        thread = build_thread(row, columns)
        if not thread:
            empty += 1
            continue
        if should_pre_filter(thread):
            pre_filtered += 1
            continue
        items.append({"source_row": source_row, "thread": thread})

    qa_pairs: list[dict] = []
    skipped = 0
    failed = 0
    batches = list(chunked(items, batch_size))

    # Keep dependency local so tests can import this module without invoking model code.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_batch, client, batch, brand): len(batch) for batch in batches}
        for future in as_completed(futures):
            results = future.result()
            if not results:
                failed += futures[future]
                continue
            for result in results:
                if result.get("skip_reason"):
                    skipped += 1
                    continue
                question = str(result.get("question", "")).strip()
                answer = str(result.get("answer", "")).strip()
                if not question or not answer or len(answer) <= 20:
                    failed += 1
                    continue
                qa_pairs.append({
                    "source_page": page,
                    "source_row": result.get("source_row"),
                    "topic": result.get("topic", "troubleshooting"),
                    "question": question,
                    "answer": answer,
                    "dir_path": [],
                })

    qa_pairs.sort(key=lambda item: item.get("source_row") or 0)
    return {
        "page": page,
        "rows": {"start": window.start_row, "end": window.end_row, "total": window.total_rows},
        "columns": {
            "mode": columns.mode,
            "messages_col": columns.messages_col,
            "title_col": columns.title_col,
            "reply_col": columns.reply_col,
            "fallback_col": columns.fallback_col,
        },
        "stats": {
            "page_rows": len(page_df),
            "valid_threads": len(items),
            "pre_filtered": pre_filtered,
            "empty": empty,
            "model_calls": len(batches),
            "extracted": len(qa_pairs),
            "skipped": skipped,
            "failed": failed,
        },
        "qa_pairs": qa_pairs,
    }


def run(args) -> None:
    if args.page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page-size {args.page_size} exceeds maximum {MAX_PAGE_SIZE}")
    if args.batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch-size {args.batch_size} exceeds maximum {MAX_BATCH_SIZE}")
    if args.workers < 1 or args.workers > MAX_WORKERS:
        raise ValueError(f"workers must be 1-{MAX_WORKERS}, got {args.workers}")

    print(f"[batch_extract] Reading {args.xlsx}")
    df = pd.read_excel(args.xlsx)
    total_rows = len(df)
    total_pages = math.ceil(total_rows / args.page_size) if total_rows else 0
    print(f"[batch_extract] rows={total_rows} pages={total_pages} page-size={args.page_size}")

    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Sandbox injects OPENAI_BASE_URL + dummy OPENAI_API_KEY for the internal proxy.
    client = OpenAI()
    done_pages: list[int] = []
    failed_pages: list[int] = []

    for page in range(1, total_pages + 1):
        out_file = _page_file(page)
        if args.resume and out_file.exists():
            print(f"[batch_extract] page {page}/{total_pages} exists, skip")
            done_pages.append(page)
            continue
        try:
            result = process_page(
                df=df,
                page=page,
                page_size=args.page_size,
                brand=args.brand,
                messages_col=args.messages_col,
                title_col=args.title_col,
                reply_col=args.reply_col,
                batch_size=args.batch_size,
                workers=args.workers,
                client=client,
            )
            _write_json(out_file, result)
            done_pages.append(page)
            print(f"[batch_extract] page {page}/{total_pages} done -> {out_file}")
        except Exception as exc:
            failed_pages.append(page)
            print(f"[batch_extract] page {page}/{total_pages} failed: {exc}", file=sys.stderr)

        _write_json(PROGRESS_FILE, {
            "status": "running" if failed_pages else "extracting",
            "xlsx": args.xlsx,
            "brand": args.brand,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "page_size": args.page_size,
            "batch_size": args.batch_size,
            "workers": args.workers,
            "messages_col": args.messages_col,
            "title_col": args.title_col,
            "reply_col": args.reply_col,
            "done_pages": done_pages,
            "failed_pages": failed_pages,
        })

    if failed_pages:
        _write_json(PROGRESS_FILE, {
            "status": "failed",
            "xlsx": args.xlsx,
            "brand": args.brand,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "done_pages": done_pages,
            "failed_pages": failed_pages,
        })
        raise RuntimeError(f"QA extraction failed pages={failed_pages}; no merged output was generated")

    page_files = [_page_file(page) for page in range(1, total_pages + 1) if _page_file(page).exists()]
    merged, merge_stats = merge_and_dedupe(page_files)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUTS_DIR / f"ticket_qa_merged_{timestamp()}.json"
    _write_json(out_path, merged)

    final_progress = {
        "status": "completed_with_errors" if failed_pages else "completed",
        "xlsx": args.xlsx,
        "brand": args.brand,
        "total_rows": total_rows,
        "total_pages": total_pages,
        "done_pages": done_pages,
        "failed_pages": failed_pages,
        "page_files": [str(path) for path in page_files],
        "merged_output": str(out_path),
        "merge_stats": merge_stats,
    }
    _write_json(PROGRESS_FILE, final_progress)

    print(f"[batch_extract] merged -> {out_path}")
    print(
        "[batch_extract] stats "
        f"input={merge_stats['input']} post_filtered={merge_stats['post_filtered']} "
        f"deduped={merge_stats['deduped']} output={merge_stats['output']}"
    )
    print("[batch_extract] Not uploaded. Review merged output, then run import_qa.py dry-run after user confirmation.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--brand", required=True)
    parser.add_argument("--messages-col", default=None)
    parser.add_argument("--title-col", default=None)
    parser.add_argument("--reply-col", default=None)
    parser.add_argument("--page-size", type=int, default=100, dest="page_size")
    parser.add_argument("--batch-size", type=int, default=5, dest="batch_size")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    try:
        run(args)
    except ValueError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(2)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
