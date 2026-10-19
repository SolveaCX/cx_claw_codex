#!/usr/bin/env python3
"""
跨轮持久化断言脚本。

eager 模型下 workspace/state/ 与 workspace/outputs/ 都由运行时在 build 时
自动 eager 还原到原路径，脚本直接读即可，无需 read_file 物化。
"""
import os, sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *
import json

_SECTION = "=" * 64
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ✅  {label}")
    else:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"  ❌  {msg}")
        _failures.append(msg)


print(_SECTION)
print("VERIFY PERSISTENCE — 跨轮持久化断言")
print(_SECTION)

# ── 1. 上一轮 state 是否还原到 workspace ─────────────────────────────────────
print("\n[1] 上一轮 state 还原（workspace/state/）")
state_path = STATE_DIR / "inspect.json"
check("state 文件已还原", state_path.exists(), str(state_path))

if state_path.exists():
    try:
        prev_state = json.loads(state_path.read_text(encoding="utf-8"))
        check("status == 'done'", prev_state.get("status") == "done",
              f"actual status={prev_state.get('status')!r}")
        check("total_processed > 0", (prev_state.get("total_processed") or 0) > 0,
              f"total_processed={prev_state.get('total_processed')}")
        check("results_path 字段存在", bool(prev_state.get("results_path")))
    except Exception as e:
        check("state 文件可解析", False, str(e))

# ── 2. 上一轮 outputs 是否还原（workspace/outputs/，eager 模型） ──────────
# 关键断言：脚本直接通过绝对路径 open() 就能读到，**没有任何 read_file 物化操作**。
# 如果还原走的是 lazy（旧模型），这里会失败 —— 这就是 eager 模型的保障验证点。
print("\n[2] 上一轮 outputs eager 还原（workspace/outputs/）")
check("outputs 目录已落盘", OUTPUTS_DIR.exists(), str(OUTPUTS_DIR))

if OUTPUTS_DIR.exists():
    result_files = sorted(OUTPUTS_DIR.glob("results_*.json"))
    check("至少一个 results 文件存在", len(result_files) > 0)

    if result_files:
        latest = result_files[-1]
        # 直接用 open()/read_text，不经任何工具，等价于 bash 脚本里 cat / Path.read_text
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            total = data.get("total", 0)
            check("records 数量 > 0", total > 0, f"total={total}")
            check("records 字段存在", "records" in data)
            check("脚本直接 open() 可读（eager 还原已就位）", True,
                  f"{latest.name} {latest.stat().st_size}B")
        except FileNotFoundError as e:
            check("脚本直接 open() 可读（eager 还原已就位）", False,
                  f"FileNotFoundError —— eager 还原可能未生效: {e}")
        except Exception as e:
            check(f"{latest.name} 可解析", False, str(e))

# ── 3. SKILL_NAME 推断正确 ────────────────────────────────────────────────────
print("\n[3] SKILL_NAME 推断")
check("SKILL_NAME == 'runtime-inspector'", SKILL_NAME == "runtime-inspector",
      f"actual={SKILL_NAME!r}")

# 写一个带 SKILL_NAME 的标记文件，验证 OUTPUTS_DIR 路径包含正确的 skill 名
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
marker = OUTPUTS_DIR / f"skill_name_check_{timestamp()}.txt"
marker.write_text(SKILL_NAME, encoding="utf-8")
check("OUTPUTS_DIR 包含正确 skill 名",
      "runtime-inspector" in str(marker),
      f"actual path={marker}")

# ── 4. lib 可 import ──────────────────────────────────────────────────────────
print("\n[4] lib 可 import")
try:
    import client as _solvea_client  # solvea-api/client.py
    check("solvea-api client 可 import", True)
except ImportError as e:
    check("solvea-api client 可 import", False, str(e))

# ── 结果汇总 ──────────────────────────────────────────────────────────────────
print(f"\n{_SECTION}")
if _failures:
    print(f"RESULT: ❌ FAIL  ({len(_failures)} 项断言失败)")
    for f in _failures:
        print(f"  - {f}")
else:
    print("RESULT: ✅ PASS  所有断言通过")
print(_SECTION)
