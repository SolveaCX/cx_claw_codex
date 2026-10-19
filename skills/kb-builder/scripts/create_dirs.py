#!/usr/bin/env python3
"""
create_dirs.py — Recursively create Solvea KB folders from confirmed_tree.json.

Reads `STATE_DIR/confirmed_tree.json`, deep-first creates folders via SolveaClient.
Idempotent: if a folder with same (name, parentId) already exists, reuse its id
instead of creating a duplicate.

Tree schema (each node):
    {"name": "...", "children": [ ... ]}    # children optional

Usage:
    python3 /skills/kb-builder/scripts/create_dirs.py
    python3 /skills/kb-builder/scripts/create_dirs.py --tree-file <path>
    python3 /skills/kb-builder/scripts/create_dirs.py --dry-run
"""
from __future__ import annotations
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *
from pathlib import Path


def flatten_folders(nodes, result=None):
    if result is None:
        result = []
    for node in nodes:
        result.append(node)
        children = node.get("children", [])
        if children:
            flatten_folders(children, result)
    return result


def fetch_existing_index(client: SolveaClient) -> dict:
    """Return {(parent_id, name): folder_id} for all existing folders."""
    folders = client.list_directories()
    if isinstance(folders, list):
        flat = flatten_folders(folders)
    else:
        raw = folders.get("list") or folders.get("records") or folders.get("data") or []
        flat = flatten_folders(raw)
    return {
        ((f.get("parentId") or 0), f.get("name", "")): f["id"]
        for f in flat if f.get("id") is not None
    }


def walk(nodes, parent_id, depth, *, client, existing, dry_run, stats, max_depth=3):
    """Depth-first create folders. Mutates existing index as new folders are created.

    In dry_run mode, only existing folders have a real id for child placement;
    not-yet-created folders use parent_id=None for their children (children counted
    but not nested under a real parent).
    """
    for node in nodes:
        if depth >= max_depth:
            raise ValueError(
                f"directory tree exceeds the default {max_depth}-level limit; "
                f"cannot create '{node.get('name', '')}' at level {depth + 1}. "
                "Pass an explicitly approved --max-depth to override."
            )
        name = node.get("name", "").strip()
        if not name:
            print(f"  {'  ' * depth}[skip] empty name at depth {depth}", file=sys.stderr)
            continue

        key = (parent_id, name)
        fid = None
        if key in existing:
            fid = existing[key]
            stats["existing"] += 1
            print(f"  {'  ' * depth}[exist] {name} (id={fid})")
        elif dry_run:
            stats["to_create"] += 1
            print(f"  {'  ' * depth}[dry]   {name}")
        else:
            result = client.create_folder(name, parent_id=parent_id)
            fid = _extract_folder_id(result)
            if fid is None:
                stats["failed"] += 1
                print(f"  {'  ' * depth}[FAIL]  {name} parent={parent_id} resp={result}", file=sys.stderr)
                continue
            existing[key] = fid
            stats["created"] += 1
            print(f"  {'  ' * depth}[ok]    {name} (id={fid})")

        children = node.get("children", [])
        if children:
            walk(children, fid, depth + 1, client=client, existing=existing,
                 dry_run=dry_run, stats=stats, max_depth=max_depth)


def _extract_folder_id(result):
    """Pull folder id from create_folder response. Returns None on failure."""
    if not isinstance(result, dict):
        return None
    if "id" in result:
        return result["id"]
    data = result.get("data")
    if isinstance(data, dict) and "id" in data:
        return data["id"]
    return None


def run(tree_file: str, dry_run: bool, max_depth: int = 3) -> None:
    from client import SolveaClient

    tree_path = STATE_DIR / "confirmed_tree.json" if tree_file == "" else Path(tree_file)
    if not tree_path.exists():
        print(f"[error] tree file not found: {tree_path}", file=sys.stderr)
        sys.exit(1)

    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    if not isinstance(tree, list):
        print(f"[error] tree must be a list of root nodes, got {type(tree).__name__}", file=sys.stderr)
        sys.exit(1)

    print(f"[create_dirs] tree={tree_path} root_nodes={len(tree)} dry_run={dry_run}")
    client = SolveaClient()
    existing = fetch_existing_index(client)
    print(f"[create_dirs] existing folders: {len(existing)}")

    stats = {"created": 0, "existing": 0, "to_create": 0, "failed": 0}
    walk(tree, parent_id=0, depth=0, client=client, existing=existing,
         dry_run=dry_run, stats=stats, max_depth=max_depth)

    print(f"\n[create_dirs] Done: created={stats['created']} existing={stats['existing']} "
          f"to_create={stats['to_create']} failed={stats['failed']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree-file", default="", dest="tree_file",
                    help="Path to confirmed_tree.json (default: STATE_DIR/confirmed_tree.json)")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--max-depth", type=int, default=3,
                    help="Maximum folder depth (default: 3; override only when explicitly requested)")
    args = ap.parse_args()
    if args.max_depth < 1:
        ap.error("--max-depth must be positive")
    run(args.tree_file, args.dry_run, args.max_depth)


if __name__ == "__main__":
    main()
