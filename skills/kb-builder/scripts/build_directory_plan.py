#!/usr/bin/env python3
"""Build a KB directory plan from crawl_result JSON."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403


def resolve_workspace_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute() and str(p).startswith("/workspace"):
        return WORKSPACE / p.relative_to("/workspace")
    return p


def virtual_workspace_path(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(WORKSPACE.resolve())
        return str(Path("/workspace") / rel)
    except Exception:
        return str(path)


def clean_name(value: str, fallback: str) -> str:
    value = re.sub(r"\s+", " ", (value or "")).strip()
    value = re.sub(r"[<>\"{}|\\^`]", "", value).strip()
    return value[:80] or fallback


def policy_name(page: dict) -> str:
    hay = f"{page.get('url', '')} {page.get('title', '')}".lower()
    if "warranty" in hay or "guarantee" in hay:
        return "Warranty Policy"
    if "return" in hay or "refund" in hay:
        return "Return Policy"
    if "shipping" in hay or "delivery" in hay:
        return "Shipping Policy"
    if "privacy" in hay:
        return "Privacy Policy"
    if "terms" in hay:
        return "Terms Policy"
    return "Brand Policy"


def infer_product_group(page: dict) -> str:
    path = urlparse(page.get("url", "")).path.strip("/")
    parts = [p for p in path.split("/") if p]
    for marker in ("collections", "collection", "category", "categories"):
        if marker in parts:
            idx = parts.index(marker)
            if idx + 1 < len(parts):
                return clean_name(parts[idx + 1].replace("-", " ").title(), "Products")
    return "Products"


def build_tree(crawl: dict) -> list[dict]:
    pages = crawl.get("pages") or []
    products = [p for p in pages if p.get("type") == "product"]
    policies = [p for p in pages if p.get("type") == "policy"]
    help_pages = [p for p in pages if p.get("type") == "help_center"]

    product_groups: dict[str, list[dict]] = {}
    for page in products:
        product_groups.setdefault(infer_product_group(page), []).append(page)

    product_children = []
    for group, group_pages in sorted(product_groups.items()):
        product_children.append({
            "name": group,
            "children": [
                {"name": clean_name(p.get("title") or urlparse(p.get("url", "")).path.rsplit("/", 1)[-1], "Product")}
                for p in group_pages[:80]
            ],
        })

    policy_names = sorted({policy_name(p) for p in policies})
    tree = [
        {
            "name": "Product Introduction",
            "children": product_children or [{"name": "Products", "children": []}],
        },
        {
            "name": "Brand Policy",
            "children": [{"name": name} for name in (policy_names or ["Brand Policy"])],
        },
    ]

    if help_pages:
        tree.append({
            "name": "Help Center",
            "children": [{"name": "Help Articles"}],
        })

    tree.append({"name": "Pending Assignment", "children": []})
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(description="Build kb-builder directory plan from crawl result")
    parser.add_argument("--crawl-result", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--write-confirmed-tree", action="store_true",
                        help="Also write /workspace/state/kb-builder/confirmed_tree.json after user confirmation")
    args = parser.parse_args()

    crawl_path = resolve_workspace_path(args.crawl_result)
    crawl = json.loads(crawl_path.read_text(encoding="utf-8"))
    tree = build_tree(crawl)
    plan = {
        "base_url": crawl.get("base_url", ""),
        "source_crawl_result": args.crawl_result,
        "tree": tree,
        "stats": {
            "pages": len(crawl.get("pages") or []),
            "product": sum(1 for p in crawl.get("pages") or [] if p.get("type") == "product"),
            "policy": sum(1 for p in crawl.get("pages") or [] if p.get("type") == "policy"),
            "help_center": sum(1 for p in crawl.get("pages") or [] if p.get("type") == "help_center"),
        },
    }

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out = resolve_workspace_path(args.output) if args.output else OUTPUTS_DIR / f"directory_plan_{timestamp()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.write_confirmed_tree:
        confirmed = STATE_DIR / "confirmed_tree.json"
        confirmed.parent.mkdir(parents=True, exist_ok=True)
        confirmed.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[build_directory_plan] confirmed_tree={virtual_workspace_path(confirmed)}")

    print(f"[build_directory_plan] output={virtual_workspace_path(out)} root_nodes={len(tree)} pages={plan['stats']['pages']}")


if __name__ == "__main__":
    main()
