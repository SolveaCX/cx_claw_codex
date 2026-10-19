#!/usr/bin/env python3
"""验证沙箱内 internal OpenAI proxy 是否可用。独立运行。"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *

from openai import OpenAI


def main():
    base_url = os.environ.get("OPENAI_BASE_URL", "")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    print(f"OPENAI_BASE_URL = {base_url or '(not set)'}")
    print(f"OPENAI_API_KEY  = {api_key or '(not set)'}")
    if not base_url:
        print("FAIL: OPENAI_BASE_URL 未设置")
        sys.exit(1)
    if "api.openai.com" in base_url:
        print("WARN: OPENAI_BASE_URL 直接指向真实端点，非 internal proxy")

    client = OpenAI(timeout=30.0)
    t0 = time.time()
    try:
        response = client.chat.completions.create(
            model="server-managed",
            max_tokens=16,
            temperature=0,
            messages=[{"role": "user", "content": "reply with the single word: ok"}],
        )
        reply = response.choices[0].message.content or ""
        print(f"PASS model={response.model} reply={reply!r} elapsed={time.time() - t0:.2f}s")
    except Exception as exc:
        print(f"FAIL elapsed={time.time() - t0:.2f}s error={exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
