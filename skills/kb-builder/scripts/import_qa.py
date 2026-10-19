#!/usr/bin/env python3
"""
Import qa_plan into Solvea knowledge base as QA entries.

Two input modes:

1. --qa-file <path>   already-merged qa_plan_<ts>.json
2. --from-dir <dir>   merge all *.json files in <dir> (each is a QA list).
                      Useful when the agent wrote multiple small batches into
                      /workspace/tmp/kb-builder/qa_parts/ to avoid the LLM max_tokens
                      truncation that hits any single huge tool_call. The
                      merged plan is written to OUTPUTS_DIR/qa_plan_<ts>.json
                      for traceability before upload.

QA item format (each list entry):
[
  {
    "dir_path": ["Product Introduction", "Smart Plugs", "Kasa EP25"],
    "question": "Kasa EP25 Smart Plug — What is the Kasa EP25 and what does it do?",
    "answer": "The Kasa EP25 is ...\n\n![Product image](https://cdn.example.com/...)"
  }
]

Usage:
  python3 import_qa.py --qa-file /workspace/outputs/kb-builder/qa_plan_<ts>.json
  python3 import_qa.py --qa-file /workspace/outputs/kb-builder/qa_plan_<ts>.json --dry-run
  python3 import_qa.py --from-dir /workspace/tmp/kb-builder/qa_parts/
  python3 import_qa.py --from-dir /workspace/tmp/kb-builder/qa_parts/ --dry-run

SolveaClient() picks token / project_id / env from environment variables
(SOLVEA_TOKEN / SOLVEA_PROD_TOKEN / SOLVEA_PROJECT_ID / SOLVEA_ENV).
"""
from __future__ import annotations
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *
from pathlib import Path

def validate_qa_item(item: object, index: int, max_depth: int = 3) -> tuple[list[str], str, str]:
    """Return normalized QA fields or raise a clear schema error."""
    if not isinstance(item, dict):
        raise ValueError(f"QA item #{index} must be an object, got {type(item).__name__}")

    dir_path = item.get("dir_path")
    question = item.get("question")
    answer = item.get("answer")

    if not isinstance(dir_path, list) or not dir_path:
        raise ValueError(
            f"QA item #{index} dir_path must be a non-empty list of folder names, "
            f'e.g. ["Product Introduction", "Speakers", "B0117-03018-BK"]; '
            f"got {dir_path!r}"
        )
    if not all(isinstance(name, str) and name.strip() for name in dir_path):
        raise ValueError(f"QA item #{index} dir_path entries must be non-empty strings: {dir_path!r}")
    if len(dir_path) > max_depth:
        raise ValueError(f"QA item #{index} dir_path has {len(dir_path)} levels; maximum is {max_depth}")
    if any("/" in name or "\\" in name for name in dir_path):
        raise ValueError(
            f"QA item #{index} dir_path entries must be folder names, not slash paths: {dir_path!r}"
        )
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"QA item #{index} question must be a non-empty string")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(f"QA item #{index} answer must be a non-empty markdown string")

    return [name.strip() for name in dir_path], question.strip(), answer.strip()


def validate_plan(plan: object, max_depth: int = 3) -> list[tuple[list[str], str, str]]:
    if not isinstance(plan, list):
        raise ValueError(f"QA plan must be a list, got {type(plan).__name__}")
    return [validate_qa_item(item, i + 1, max_depth=max_depth) for i, item in enumerate(plan)]


def flatten_folders(nodes: list, result: list | None = None) -> list:
    """Recursively flatten a nested folder tree into a flat list."""
    if result is None:
        result = []
    for node in nodes:
        result.append(node)
        children = node.get("children", [])
        if children:
            flatten_folders(children, result)
    return result


def get_or_create_dir(client: SolveaClient, path: list[str], dir_cache: dict) -> str | int:
    """Walk dir_path, creating missing folders. Returns final directory ID."""
    parent_id = 0
    current_path: list[str] = []
    for name in path:
        current_path.append(name)
        key = "/".join(current_path)
        if key in dir_cache:
            parent_id = dir_cache[key]
            continue
        # Search in existing folders (API returns {"list": [nested tree]})
        folders = client.list_directories()
        if isinstance(folders, list):
            all_folders = flatten_folders(folders)
        else:
            raw = folders.get("list") or folders.get("records") or folders.get("data") or []
            all_folders = flatten_folders(raw)
        match = next(
            (f for f in all_folders
             if f.get("name") == name and (f.get("parentId") or 0) == parent_id),
            None,
        )
        if match:
            fid = match["id"]
        else:
            result = client.create_folder(name, parent_id=parent_id)
            fid = result.get("id") if isinstance(result, dict) else None
            if not fid:
                print(f"  [warn] Could not create folder '{name}' under parentId={parent_id}: {result}", file=sys.stderr)
                fid = parent_id  # fallback: use parent
        dir_cache[key] = fid
        parent_id = fid
    return parent_id


def merge_dir(src_dir: Path) -> tuple[list, Path]:
    """Merge every *.json in src_dir (each must be a QA list) into one list,
    then write the result to OUTPUTS_DIR/qa_plan_{ts}.json for traceability.

    Files are merged in filename-sorted order so the result is deterministic.
    Files whose top-level JSON isn't a list are skipped with a warning.
    """
    if not src_dir.exists() or not src_dir.is_dir():
        raise FileNotFoundError(f"--from-dir not a directory: {src_dir}")

    merged: list = []
    parts = sorted(src_dir.glob("*.json"))
    if not parts:
        raise FileNotFoundError(f"No *.json found under {src_dir}")

    for p in parts:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [warn] skip {p.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            print(f"  [warn] skip {p.name}: top-level is not a list", file=sys.stderr)
            continue
        print(f"  [merge] {p.name}: +{len(data)} QA")
        merged.extend(data)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUTS_DIR / f"qa_plan_{timestamp()}.json"
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[merge] {len(merged)} QA total -> {out}")
    return merged, out


def run(qa_file: str | None, from_dir: str | None, dry_run: bool, max_depth: int = 3) -> None:
    if from_dir:
        plan, qa_file_path = merge_dir(Path(from_dir))
    else:
        qa_file_path = Path(qa_file)
        plan = json.loads(qa_file_path.read_text(encoding="utf-8"))

    normalized_plan = validate_plan(plan, max_depth=max_depth)

    print(f"[import] {len(normalized_plan)} QA entries to import (dry_run={dry_run}) source={qa_file_path}")

    dir_cache: dict[str, str | int] = {}
    ok = 0
    fail = 0
    client = None
    if not dry_run:
        from client import SolveaClient
        client = SolveaClient()

    for i, (dir_path, question, answer) in enumerate(normalized_plan):
        if dry_run:
            print(f"  [{i+1}] DRY dir={dir_path}")
            print(f"         Q: {question[:80]}")
            print(f"         A: {answer[:80]}...")
            continue

        try:
            assert client is not None
            dir_id = get_or_create_dir(client, dir_path, dir_cache) if dir_path else ""
            client.upload_qa([{
                "title": question,
                "content": answer,
                "directoryId": dir_id,
            }])
            ok += 1
            print(f"  [{i+1}/{len(normalized_plan)}] OK  {'/'.join(dir_path)} | {question[:60]}")
        except Exception as e:
            fail += 1
            print(f"  [{i+1}/{len(normalized_plan)}] FAIL {question[:60]}: {e}")

    if not dry_run:
        print(f"\n[import] Done: {ok} OK, {fail} failed")


def main():
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--qa-file", dest="qa_file",
                     help="Path to a pre-merged qa_plan_<ts>.json")
    src.add_argument("--from-dir", dest="from_dir",
                     help="Merge all *.json under this directory (each = QA list); "
                          "merged result is written to OUTPUTS_DIR/qa_plan_<ts>.json")
    ap.add_argument("--dry-run", action="store_true", dest="dry_run")
    ap.add_argument("--max-depth", type=int, default=3,
                    help="Maximum QA directory depth (default: 3; override only when explicitly requested)")
    args = ap.parse_args()
    if args.max_depth < 1:
        ap.error("--max-depth must be positive")
    run(args.qa_file, args.from_dir, args.dry_run, args.max_depth)


if __name__ == "__main__":
    main()
