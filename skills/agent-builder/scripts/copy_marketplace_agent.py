#!/usr/bin/env python3
"""Copy one or more marketplace agents into the current project.

Usage:
  python3 /skills/agent-builder/scripts/copy_marketplace_agent.py --square-id 38433 --pretty
  python3 /skills/agent-builder/scripts/copy_marketplace_agent.py --square-id 38433 --dry-run
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


def copy_marketplace_agent(client: SolveaClient, square_agent_id: int, dry_run: bool = False) -> dict:
    if dry_run:
        return {"square_agent_id": square_agent_id, "dry_run": True, "new_agent_id": None}

    result = client._curl("POST", "/api_v2/gpt/ap/copyAgent", {
        "projectId": int(client.project_id),
        "agentId": int(square_agent_id),
    })
    new_id = (
        result.get("id")
        or result.get("agentId")
        or (result.get("data") or {}).get("id")
        or (result.get("data") or {}).get("agentId")
    )
    if not new_id:
        raise RuntimeError(f"copyAgent square_agent_id={square_agent_id} returned no id: {result}")
    return {"square_agent_id": square_agent_id, "new_agent_id": int(new_id), "raw": result}


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy marketplace agents by square agent id")
    parser.add_argument("--square-id", type=int, action="append", required=True,
                        help="Marketplace square agent id. Can be repeated.")
    parser.add_argument("--env", choices=["staging", "prod"], default=os.environ.get("SOLVEA_ENV", "prod"))
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    client = SolveaClient(env=args.env, project_id=args.project_id)
    copied = [copy_marketplace_agent(client, sid, dry_run=args.dry_run) for sid in args.square_id]
    output = {"copied": copied}
    print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
