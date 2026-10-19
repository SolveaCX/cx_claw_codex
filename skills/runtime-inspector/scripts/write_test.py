#!/usr/bin/env python3
"""向 workspace/outputs 和 workspace/state 写入测试文件，验证写入机制和 S3 上传路径。"""
import os, sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *
import json
from datetime import datetime, timezone

now = datetime.now(timezone.utc).isoformat()

# 1. outputs — 每轮不同文件名（模拟 run_id 命名）
run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_dir = OUTPUTS_DIR
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / f"{run_id}_test.json"
out_file.write_text(json.dumps({
    "run_id": run_id,
    "written_at": now,
    "note": "此文件每轮新建，S3 上累积保留",
}, indent=2))
print(f"[outputs] Written: {out_file}")

# 2. state — 固定文件名（模拟跨轮状态覆盖）
state_file = STATE_DIR / "inspect.json"
existing = {}
if state_file.exists():
    try:
        existing = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        pass
existing.update({
    "last_run_id": run_id,
    "last_written_at": now,
    "write_count": existing.get("write_count", 0) + 1,
    "note": "固定文件名，S3 上传时覆盖旧版本",
})
state_file.parent.mkdir(parents=True, exist_ok=True)
state_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[state] Written: {state_file}  (write_count={existing['write_count']})")

print("\n✅ 写入完成。下一轮运行 read_state.py 验证跨轮持久化。")
