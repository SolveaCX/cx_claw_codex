#!/usr/bin/env python3
"""Import URL/Word/PDF sources as DOCUMENT knowledge.

Input is a JSON list of records:
  {"source": "https://...", "dir_path": ["一级", "二级", "三级"]}
  {"source": "/mounted/chat-files/manual.docx", "dir_path": ["..."]}

The default is a dry-run.  URL duplicates in the input are reported as
``skipped_duplicate``; the API response is retained because the backend may
also deduplicate URLs already present in the knowledge base.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F403


def validate_record(item, index, max_depth=3):
    if not isinstance(item, dict) or not isinstance(item.get("source"), str) or not item["source"].strip():
        raise ValueError(f"source document #{index} needs a non-empty source")
    path = item.get("dir_path", [])
    if not isinstance(path, list) or any(not isinstance(x, str) or not x.strip() for x in path):
        raise ValueError(f"source document #{index} dir_path must be a list of non-empty names")
    if len(path) > max_depth:
        raise ValueError(f"source document #{index} dir_path has {len(path)} levels; maximum is {max_depth}")
    if any("/" in x or "\\" in x for x in path):
        raise ValueError(f"source document #{index} dir_path entries cannot contain slashes")
    source = item["source"].strip()
    is_url = source.lower().startswith(("http://", "https://"))
    if not is_url and not Path(source).is_file():
        raise ValueError(f"source document #{index} file not found: {source}")
    if not is_url and Path(source).suffix.lower() not in {".doc", ".docx", ".pdf"}:
        raise ValueError(f"source document #{index} supports .doc/.docx/.pdf, got {Path(source).suffix}")
    return {"source": source, "dir_path": [x.strip() for x in path], "is_url": is_url}


def validate_plan(data, max_depth=3):
    if not isinstance(data, list):
        raise ValueError("source document plan must be a JSON list")
    normalized = [validate_record(item, i + 1, max_depth) for i, item in enumerate(data)]
    seen = set()
    for item in normalized:
        if item["is_url"]:
            item["status"] = "skipped_duplicate" if item["source"] in seen else "pending"
            seen.add(item["source"])
        else:
            item["status"] = "pending"
    return normalized


def _flatten(nodes, out=None):
    out = [] if out is None else out
    for node in nodes:
        out.append(node)
        _flatten(node.get("children", []), out)
    return out


def resolve_dir(client, path, cache):
    parent = 0
    prefix = []
    for name in path:
        prefix.append(name)
        key = "/".join(prefix)
        if key in cache:
            parent = cache[key]
            continue
        raw = client.list_directories()
        nodes = raw if isinstance(raw, list) else raw.get("list", raw.get("records", raw.get("data", [])))
        match = next((x for x in _flatten(nodes) if x.get("name") == name and (x.get("parentId") or 0) == parent), None)
        if match:
            parent = match["id"]
        else:
            result = client.create_folder(name, parent_id=parent)
            parent = result.get("id") if isinstance(result, dict) else None
            if not parent:
                raise RuntimeError(f"could not create directory {key!r}: {result}")
        cache[key] = parent
    return parent


def run(plan_file, dry_run=True, max_depth=3):
    data = json.loads(Path(plan_file).read_text(encoding="utf-8"))
    plan = validate_plan(data, max_depth)
    print(f"[source-documents] {len(plan)} records (dry_run={dry_run})")
    for item in plan:
        print(f"  [{item['status']}] {item['source']} -> {'/'.join(item['dir_path']) or '(root)'}")
    if dry_run:
        return plan

    from client import SolveaClient
    client = SolveaClient()
    cache = {}
    results = []
    for item in plan:
        if item["status"] == "skipped_duplicate":
            results.append({**item, "result": None})
            continue
        try:
            directory_id = resolve_dir(client, item["dir_path"], cache)
            if item["is_url"]:
                documents = [{"filePath": item["source"], "docType": "TC", "fileType": "website"}]
                response = client.create_documents(documents, directory_id=directory_id, task_type="WEB")
            else:
                key = client.upload_temp_file(item["source"], for_knowledge=True)
                # The file-document endpoint derives the loader from the uploaded
                # object key; unlike WEBSITE, it does not require fileType.
                documents = [{"filePath": key, "docType": "TC"}]
                response = client.create_documents(documents, directory_id=directory_id, task_type="FILE")
            if not response:
                raise RuntimeError("document API returned no created or refreshed record")
            results.append({**item, "status": "submitted", "directory_id": directory_id, "result": response})
            print(f"  [submitted] {item['source']}")
        except Exception as exc:
            results.append({**item, "status": "failed", "error": str(exc)})
            print(f"  [failed] {item['source']}: {exc}", file=sys.stderr)
    out = OUTPUTS_DIR / f"source_document_import_{timestamp()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[source-documents] result={out}")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan-file", required=True)
    ap.add_argument("--execute", action="store_true", help="Submit documents after explicit user confirmation")
    ap.add_argument("--max-depth", type=int, default=3)
    args = ap.parse_args()
    if args.max_depth < 1:
        ap.error("--max-depth must be positive")
    run(args.plan_file, dry_run=not args.execute, max_depth=args.max_depth)


if __name__ == "__main__":
    main()
