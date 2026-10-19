#!/usr/bin/env python3
"""验证跨轮 state 持久化机制：上一轮写入的 state 是否被正确还原到 workspace/state/。"""
import os, sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *
import json

print("=" * 60)
print("CROSS-ROUND STATE VERIFICATION")
print("=" * 60)

state_file = STATE_DIR / "inspect.json"

print(f"\n{'✅' if state_file.exists() else '❌'} workspace/state ({state_file})")
if state_file.exists():
    try:
        data = json.loads(state_file.read_text())
        print(f"   content: {json.dumps(data, indent=4, ensure_ascii=False)}")
    except Exception as e:
        print(f"   [error reading] {e}")
else:
    print("   (not found — 可能是第一轮，或上一轮未写入 state)")

print("\n" + "=" * 60)
if state_file.exists():
    data = json.loads(state_file.read_text())
    count = data.get("write_count", 0)
    print(f"✅ 跨轮持久化验证通过！累计写入 {count} 次")
    print(f"   上一轮 run_id: {data.get('last_run_id', 'N/A')}")
else:
    print("ℹ️  state 不存在，这是第一轮或 state 尚未上传")
print("=" * 60)
