#!/usr/bin/env python3
"""
步骤 1：准备数据，分批写入 /workspace/tmp/runtime-inspector/。

- 有 --source 时：读取用户上传的文件（csv/json/txt），解析内容
- 无 --source 时：自动生成 30 条测试记录
- 读取 state，展示当前任务状态
- 将数据按 10 条一批写入 tmp，更新 state → status: batched
"""
import os, sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *
import argparse, csv, io, json
from datetime import datetime, timezone


def parse_source(path: str) -> list[dict]:
    """解析用户上传的文件，支持 json / csv / txt（每行一条）。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    suffix = p.suffix.lower()
    content = p.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(content)
        if isinstance(data, list):
            return [{"text": str(item)} if not isinstance(item, dict) else item for item in data]
        return [data]
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(content))
        return list(reader)
    # txt / 其他：每行一条
    return [{"text": line.strip()} for line in content.splitlines() if line.strip()]


def generate_test_data(n: int = 30) -> list[dict]:
    return [{"id": i + 1, "text": f"测试记录 #{i + 1}", "value": (i + 1) * 10} for i in range(n)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=None, help="用户上传文件路径（可选）")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    # 读取并展示当前状态
    _state_file = STATE_DIR / "inspect.json"
    state = {}
    if _state_file.exists():
        try:
            state = json.loads(_state_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    if state:
        print(f"[state] 读取到上一轮状态: status={state.get('status')} "
              f"batches={state.get('total_batches')} "
              f"written_at={state.get('written_at', 'N/A')}")
    else:
        print("[state] 首次运行，无历史状态")

    # 解析或生成数据
    if args.source:
        records = parse_source(args.source)
        print(f"[prepare] 解析用户文件 {args.source} → {len(records)} 条记录")
    else:
        records = generate_test_data(30)
        print(f"[prepare] 自动生成 {len(records)} 条测试数据")

    # 清空 tmp 目录
    if TMP_DIR.exists():
        import shutil
        shutil.rmtree(TMP_DIR)
    TMP_DIR.mkdir(parents=True, exist_ok=True)

    # 分批写入 tmp
    batches = [records[i:i + args.batch_size] for i in range(0, len(records), args.batch_size)]
    for idx, batch in enumerate(batches):
        batch_file = TMP_DIR / f"batch_{idx:03d}.json"
        batch_file.write_text(json.dumps(batch, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[prepare] 写入 {batch_file.name}  ({len(batch)} 条)")

    # 更新状态
    _sf = STATE_DIR / "inspect.json"
    _sf.parent.mkdir(parents=True, exist_ok=True)
    _sf.write_text(json.dumps({
        "status": "batched",
        "total_records": len(records),
        "total_batches": len(batches),
        "batch_size": args.batch_size,
        "source": args.source or "auto-generated",
        "written_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 分批完成: {len(batches)} 个批次写入 {TMP_DIR}")
    print("   下一步: python3 /skills/runtime-inspector/scripts/process.py")


if __name__ == "__main__":
    main()
