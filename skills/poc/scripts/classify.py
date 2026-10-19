#!/usr/bin/env python3
"""POC wrapper for the shared Solvea Kit intent classifier."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    script = Path(__file__).resolve().parents[2] / "solvea-kit" / "scripts" / "intent_classify.py"
    env = os.environ.copy()
    env.setdefault(
        "SOLVEA_LIB_DIR",
        str(Path(__file__).resolve().parents[2] / "__lib__"),
    )
    return subprocess.call([sys.executable, str(script), "--owner", "poc", *sys.argv[1:]], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
