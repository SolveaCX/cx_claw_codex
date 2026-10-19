#!/usr/bin/env python3
"""按意图配额从历史会话抽样 → 标准 cases.json（喂给 batch_test.py）。

CLI：
  --total 100              整批配额（按意图分配，floor + 余数 +1）
  --intents A --intents B  指定意图（可重复）；不传则 list_intents() 全量
  --mode single|multi      single=只取首条 USER；multi=取所有 USER（默认 single）
  --with-metadata          抽样时把会话首轮 metadata 带进 case；默认不带
  --max-conversations 50   每个意图 limit
  --output cases.json      输出 cases.json 路径

stdout：完成 `Wrote {N} cases → {output}`；意图列表为空 → exit 2。
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403
from client import SolveaClient


def allocate_quota(total: int, intents: list[str]) -> dict[str, int]:
    """按意图均匀分配总配额：floor 分配 + 余数从前往后各 +1。"""
    n = len(intents)
    if n == 0 or total <= 0:
        return {it: 0 for it in intents}
    base = total // n
    extra = total - base * n
    quota = {}
    for i, it in enumerate(intents):
        quota[it] = base + (1 if i < extra else 0)
    return quota


def _slim_messages(messages: list[str], mode: str) -> list[str]:
    if mode == "single":
        return messages[:1]
    return messages


def main():
    parser = argparse.ArgumentParser(description="按意图配额抽历史会话 → cases.json")
    parser.add_argument("--total", type=int, default=100, help="整批配额")
    parser.add_argument("--intents", action="append", default=None,
                        help="指定意图名（可重复传）；不传则 list_intents 全量")
    parser.add_argument("--mode", choices=["single", "multi"], default="single",
                        help="single=只取首条 USER；multi=取所有 USER")
    parser.add_argument("--with-metadata", action="store_true",
                        help="把会话首轮 metadata 带进 case")
    parser.add_argument("--max-conversations", type=int, default=50,
                        help="每个意图最多拉多少 chat（API limit）")
    parser.add_argument("--output", required=True, help="输出 cases.json 路径")
    args = parser.parse_args()

    client = SolveaClient()

    intents = args.intents
    if not intents:
        all_resp = client.list_intents(category=None)
        all_list = all_resp if isinstance(all_resp, list) else \
            all_resp.get("data", all_resp.get("list", []))
        intents = [it.get("name") for it in all_list
                   if isinstance(it, dict) and it.get("name")]

    if not intents:
        print("意图列表为空：list-intents 返回空，且 --intents 也未指定", file=sys.stderr)
        sys.exit(2)

    quota = allocate_quota(args.total, intents)

    cases = []
    for intent in intents:
        want = quota.get(intent, 0)
        if want <= 0:
            continue
        try:
            convs = client.get_conversations_by_intent(intent, limit=args.max_conversations)
        except Exception as e:
            print(f"  WARN: get_conversations_by_intent({intent}) failed: {e}",
                  file=sys.stderr)
            convs = []
        print(f"  Loaded {len(convs)} conversations for intent '{intent}'",
              file=sys.stderr)
        # 取前 want 条（API 已经做了排序，这里不再重排）
        for c in convs[:want]:
            messages = _slim_messages(c.get("messages") or [], args.mode)
            if not messages:
                continue
            case = {
                "name": c.get("source_chat_id") or "",
                "messages": messages,
                "intent": intent,
                "source_chat_id": c.get("source_chat_id", ""),
            }
            if args.with_metadata and c.get("metadata"):
                case["metadata"] = c["metadata"]
            cases.append(case)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(cases)} cases → {args.output}")


if __name__ == "__main__":
    main()
