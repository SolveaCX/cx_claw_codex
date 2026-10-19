#!/usr/bin/env python3
"""
步骤 2：读取 tmp 批次文件，处理后写结果到 workspace/outputs/。

- 遍历 workspace/tmp/runtime-inspector/batch_*.json
- 对每条记录做简单处理（模拟业务逻辑）
- 汇总结果写入 workspace/outputs/runtime-inspector/results.json
- 更新 state → status: done
"""
import os, sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *
import json
from datetime import datetime, timezone


def process_record(record: dict) -> dict:
    """模拟业务处理：给每条记录加上处理时间戳和摘要。"""
    return {
        **record,
        "_processed": True,
        "_summary": f"processed: {str(record)[:60]}",
        "_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    _state_file = STATE_DIR / "inspect.json"
    state = {}
    if _state_file.exists():
        try:
            state = json.loads(_state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    if state.get("status") != "batched":
        print(f"[process] 当前状态: {state.get('status', '不存在')}，需先运行 prepare.py")
        return

    print(f"[process] 读取状态: {state.get('total_batches')} 批次，"
          f"{state.get('total_records')} 条记录，来源: {state.get('source')}")

    # 读取所有批次
    batch_files = sorted(TMP_DIR.glob("batch_*.json")) if TMP_DIR.exists() else []
    if not batch_files:
        print(f"[process] ❌ 未找到批次文件: {TMP_DIR}")
        return

    all_results = []
    for batch_file in batch_files:
        batch = json.loads(batch_file.read_text(encoding="utf-8"))
        processed = [process_record(r) for r in batch]
        all_results.extend(processed)
        print(f"[process] 处理 {batch_file.name}: {len(batch)} 条")

    # 写结果到 outputs（带时间戳，每轮新建，历史文件保留）
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_file = OUTPUTS_DIR / f"results_{run_ts}.json"
    results_file.write_text(
        json.dumps({
            "total": len(all_results),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "source": state.get("source"),
            "records": all_results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[process] ✅ 结果写入: {results_file}  ({len(all_results)} 条)")

    # 更新状态
    _sf = STATE_DIR / "inspect.json"
    _sf.parent.mkdir(parents=True, exist_ok=True)
    _sf.write_text(json.dumps({
        "status": "done",
        "total_processed": len(all_results),
        "results_path": str(results_file),
        "done_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[process] state → status: done")
    print("\n   下一步: python3 /skills/runtime-inspector/scripts/sandbox_inspect.py")


if __name__ == "__main__":
    main()
