#!/usr/bin/env python3
"""Generate and verify the CXClaw skill/command capability lock."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
LOCK = ROOT / "capabilities.lock.json"
CLI = "npx --yes @shulex/cxclawctl@latest"
GROUPS = [
    "agent-analytics",
    "agent-builder",
    "agent-tester",
    "delivery",
    "kb-builder",
    "poc",
    "runtime-inspector",
    "shulex-support",
    "solvea-desk",
    "solvea-kit",
]


def command_inventory() -> list[str]:
    source = (SKILLS / "__lib__/solvea-api/solvea_api.py").read_text()
    block = source.split("Commands:", 1)[1].split("Environment:", 1)[0]
    return sorted(set(re.findall(r"^    ([a-z][a-z0-9*-]+)\s+", block, re.MULTILINE)))


def manifest() -> dict:
    commands = command_inventory()
    version = json.loads((ROOT / "package.json").read_text())["version"]
    return {
        "schemaVersion": 1,
        "plugin": {
            "pluginVersion": version,
            "cliVersion": version,
            "toolSchemaVersion": "1",
            "serverApiVersion": "1",
        },
        "capabilities": [
            {
                "name": group,
                "execution": "local-cli",
                "access": "read-write",
                "confirmation": "cli-preview-confirm-commit",
                "channels": ["dev", "canary"] if group == "runtime-inspector" else ["stable", "canary", "dev"],
                "tests": ["skill-present", "command-mapping"],
            }
            for group in GROUPS
        ],
        "localCommands": [
            f"{CLI} auth status",
            f"{CLI} tenant current",
            f"{CLI} tenant search",
            f"{CLI} tenant use",
            f"{CLI} sls query",
            f"{CLI} api",
            f"{CLI} commands",
            f"{CLI} capabilities",
        ],
        "solveaApiCommands": [
            {
                "name": command,
                "command": f"{CLI} api {command}",
                "execution": "local-cli",
                "writeConfirmation": "cli-policy",
            }
            for command in commands
        ],
    }


def validate() -> None:
    missing = [group for group in GROUPS if not (SKILLS / group / "SKILL.md").is_file()]
    if missing:
        raise SystemExit(f"missing skills: {', '.join(missing)}")
    text = "\n".join(path.read_text(errors="replace") for path in SKILLS.rglob("*") if path.is_file())
    forbidden = [
        "python3 /skill-lib/solvea-api/solvea_api.py",
        "SOLVEA_INTERNAL_PROXY_BASE_URL",
        "$SOLVEA_INTERNAL_PROXY_BASE_URL/sls/query",
        "/internal/proxy/sls/query",
        "cxclawctl mcp serve",
        "solvea-kit` 远程 MCP",
        "solvea-kit /mcp",
    ]
    found = [item for item in forbidden if item in text]
    if found:
        raise SystemExit(f"forbidden legacy entrypoints remain: {', '.join(found)}")
    expected = manifest()
    if not LOCK.is_file() or json.loads(LOCK.read_text()) != expected:
        raise SystemExit("capabilities.lock.json is stale; run scripts/check_capabilities.py --write")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        LOCK.write_text(json.dumps(manifest(), ensure_ascii=False, indent=2) + "\n")
    validate()


if __name__ == "__main__":
    main()
