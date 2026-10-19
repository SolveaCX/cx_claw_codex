#!/usr/bin/env python3
"""Patch headers on tools attached to one or more agents.

Usage:
  python3 /skills/agent-builder/scripts/patch_agent_tools.py \
    --agent-id 123 --tool-name new_Order_information_ship --patch-x-token --dry-run --pretty
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", ""), "skill-runtime"))
try:
    from bootstrap import *  # noqa: F401,F403
except Exception:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "__lib__", "skill-runtime"))
    from bootstrap import *  # noqa: F401,F403

from client import SolveaClient


def _token_value(raw) -> str:
    if isinstance(raw, dict):
        return str(raw.get("apiKey") or raw.get("key") or raw.get("value") or raw.get("data") or "")
    return str(raw or "")


def _tool_items(response):
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        for key in ("list", "data", "records"):
            if isinstance(response.get(key), list):
                return response[key]
    return []


def _patch_headers(config: dict, headers: dict[str, str]) -> dict:
    updated = dict(config or {})
    existing = dict(updated.get("headers") or {})
    existing.update(headers)
    updated["headers"] = existing

    external = updated.get("externalHttpCallConfig")
    if isinstance(external, dict) and isinstance(external.get("headerParams"), list):
        by_name = {h.get("name"): h for h in external["headerParams"] if isinstance(h, dict)}
        for name, value in headers.items():
            if name in by_name:
                by_name[name]["value"] = value
            else:
                external["headerParams"].append({"name": name, "value": value, "description": ""})
    return updated


def patch_agent_tools(
    client: SolveaClient,
    agent_id: int,
    tool_names: set[str],
    headers: dict[str, str],
    dry_run: bool = False,
) -> list[dict]:
    response = client._curl("GET", f"/api_v2/gpt/ap/agent/{agent_id}/tools", {})
    results = []
    for tool in _tool_items(response):
        name = tool.get("name")
        if tool_names and name not in tool_names:
            continue
        tool_id = tool.get("id")
        if not tool_id:
            continue
        config = _patch_headers(tool.get("config") or {}, headers)
        item = {"agent_id": agent_id, "tool_id": tool_id, "tool_name": name, "dry_run": dry_run}
        if not dry_run:
            client._curl("PUT", f"/api_v2/gpt/ap/tools/{tool_id}", {"config": config})
            item["updated"] = True
        results.append(item)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch headers for tools attached to agents")
    parser.add_argument("--agent-id", type=int, action="append", required=True,
                        help="Agent id. Can be repeated.")
    parser.add_argument("--tool-name", action="append", default=[],
                        help="Only patch matching tool name. Can be repeated. Omit to patch all tools.")
    parser.add_argument("--header", action="append", default=[],
                        help="Header assignment, e.g. X-Token=abc. Can be repeated.")
    parser.add_argument("--patch-x-token", action="store_true",
                        help="Fetch current project API key and patch X-Token.")
    parser.add_argument("--env", choices=["staging", "prod"], default=os.environ.get("SOLVEA_ENV", "prod"))
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    headers = {}
    for item in args.header:
        if "=" not in item:
            raise ValueError(f"--header must be NAME=VALUE, got {item!r}")
        name, value = item.split("=", 1)
        headers[name] = value

    client = SolveaClient(env=args.env, project_id=args.project_id)
    if args.patch_x_token:
        x_token = _token_value(client.get_api_key())
        if not x_token:
            raise RuntimeError("get_api_key returned no token value")
        headers["X-Token"] = x_token
    if not headers:
        raise ValueError("provide --header NAME=VALUE or --patch-x-token")

    patched = []
    for agent_id in args.agent_id:
        patched.extend(
            patch_agent_tools(
                client,
                agent_id,
                set(args.tool_name),
                headers,
                dry_run=args.dry_run,
            )
        )
    output = {
        "patched": patched,
        "matched_count": len(patched),
        "headers": sorted(headers),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
