#!/usr/bin/env python3
import json
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parents[1]
manifests = [root / "plugin.json", root / ".codex-plugin" / "plugin.json"]
versions = {json.loads(path.read_text())["version"] for path in manifests}
if len(versions) != 1:
    raise SystemExit(f"manifest versions differ: {sorted(versions)}")
version = versions.pop()
if len(sys.argv) > 1 and sys.argv[1].lstrip("v") != version:
    raise SystemExit(f"tag version {sys.argv[1]} does not match manifests {version}")
if not re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:canary|dev)\.\d+)?", version):
    raise SystemExit(f"invalid release version: {version}")
marketplace = json.loads((root / ".agents/plugins/marketplace.json").read_text())
if marketplace.get("name") != "cxclaw" or marketplace.get("plugins", [{}])[0].get("source") != "./":
    raise SystemExit("invalid CXClaw marketplace manifest")
print(version)
