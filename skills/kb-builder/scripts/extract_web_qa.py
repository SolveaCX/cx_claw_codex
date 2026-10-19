#!/usr/bin/env python3
"""Extract basic web QA parts from crawl_result JSON.

Phase 4 provides deterministic starter QA so the upload pipeline can be tested.
Future phases may replace the extraction internals with Crawl4AI fit_markdown and LLM
summarization while keeping this CLI / output contract stable.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403


def resolve_workspace_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute() and str(p).startswith("/workspace"):
        return WORKSPACE / p.relative_to("/workspace")
    return p


def slugify(value: str, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return text[:80] or fallback


def compact_markdown(text: str, limit: int) -> str:
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("URL:"):
            continue
        if len(s) < 3:
            continue
        lines.append(s)
        if sum(len(x) for x in lines) >= limit:
            break
    body = "\n".join(lines).strip()
    return body[:limit].strip()


def dir_path_for(page: dict) -> list[str]:
    title = page.get("title") or "Knowledge"
    if page.get("type") == "policy":
        lower = f"{page.get('url', '')} {title}".lower()
        if "warranty" in lower or "guarantee" in lower:
            return ["Brand Policy", "Warranty Policy"]
        if "return" in lower or "refund" in lower:
            return ["Brand Policy", "Return Policy"]
        if "shipping" in lower or "delivery" in lower:
            return ["Brand Policy", "Shipping Policy"]
        if "privacy" in lower:
            return ["Brand Policy", "Privacy Policy"]
        return ["Brand Policy", "Brand Policy"]
    if page.get("type") == "help_center":
        return ["Help Center", "Help Articles"]
    if page.get("type") == "product":
        return ["Product Introduction", "Products", title[:80]]
    return ["Pending Assignment"]


def question_for(page: dict) -> str:
    title = page.get("title") or "this page"
    if page.get("type") == "policy":
        return f"{title} — What should customers know?"
    if page.get("type") == "help_center":
        return f"{title} — How can customers use this help article?"
    if page.get("type") == "product":
        return f"{title} — What is the product overview?"
    return f"{title} — What information is available?"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract web QA parts from crawl_result JSON")
    parser.add_argument("--crawl-result", required=True)
    parser.add_argument("--output-dir", default="/workspace/tmp/kb-builder/qa_parts")
    parser.add_argument("--max-pages", type=int, default=80)
    parser.add_argument("--answer-limit", type=int, default=3500)
    args = parser.parse_args()

    crawl_path = resolve_workspace_path(args.crawl_result)
    crawl = json.loads(crawl_path.read_text(encoding="utf-8"))
    out_dir = resolve_workspace_path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for idx, page in enumerate((crawl.get("pages") or [])[: max(1, args.max_pages)], 1):
        md_path_raw = page.get("fit_markdown_path") or page.get("markdown_path")
        if not md_path_raw:
            continue
        md_path = resolve_workspace_path(md_path_raw)
        if not md_path.exists():
            continue
        answer = compact_markdown(md_path.read_text(encoding="utf-8"), max(500, args.answer_limit))
        if not answer:
            continue
        item = {
            "dir_path": dir_path_for(page),
            "question": question_for(page),
            "answer": answer,
            "source_url": page.get("url", ""),
        }
        slug = slugify(page.get("title") or page.get("url") or f"page-{idx}", f"page-{idx:03d}")
        part = out_dir / f"qa_web_{idx:03d}_{slug}.json"
        part.write_text(json.dumps([item], ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1

    print(f"[extract_web_qa] output_dir={args.output_dir} parts={written}")


if __name__ == "__main__":
    main()
