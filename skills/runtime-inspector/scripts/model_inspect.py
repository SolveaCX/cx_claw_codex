#!/usr/bin/env python3
"""
model_inspect.py — runtime-inspector 的 model 域入口。

scenarios:
  truncation     — 引导 agent 触发 max_tokens 截断；脚本本身不真的调 LLM，
                   只输出一个引导任务，由 agent 在沙箱外用 write_file 工具执行。

Usage:
    python3 /skills/runtime-inspector/scripts/model_inspect.py --scenario truncation
"""
from __future__ import annotations
import argparse, os, sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *


def scenario_truncation() -> None:
    """打印一段引导文本，告诉 agent 主动构造一个会消耗大量输出 token 的 write_file。

    脚本本身不调 LLM、不写文件——agent 看到本脚本输出后，按引导执行 write_file 工具调用。
    实际是否触发 max_tokens 取决于当前 endpoint 的 max_tokens 配置。
    """
    target = TMP_DIR / "truncation_test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"[truncation] target_path={target}")
    print()
    print("=" * 72)
    print("AGENT INSTRUCTION")
    print("=" * 72)
    print()
    print(f"Use the write_file tool to write a long markdown document to:")
    print(f"  {target}")
    print()
    print("Content requirements (designed to push past max_tokens):")
    print("  - 60+ paragraphs of English lorem ipsum style technical text")
    print("  - Each paragraph 8-12 sentences")
    print("  - Topic: 'Best practices for distributed systems observability'")
    print("  - Target output length: ~6000 words (~8000 tokens)")
    print()
    print("After invoking write_file, regardless of whether it succeeds or fails:")
    print("  1. Tell the user to grep service logs for 'SLG model_response'")
    print("  2. Report the stop_reason and output_tokens shown in that log line")
    print()
    print("Expected outcomes:")
    print("  - stop_reason=end_turn / tool_use → max_tokens is sufficient")
    print("  - stop_reason=max_tokens / length → truncation triggered, see references/model.md")
    print()
    print("Do NOT analyse the resulting file content — this test is about the LLM")
    print("response metadata, not about the document being well-formed.")
    print("=" * 72)


SCENARIOS = {
    "truncation": scenario_truncation,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, choices=sorted(SCENARIOS.keys()))
    args = ap.parse_args()
    SCENARIOS[args.scenario]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
