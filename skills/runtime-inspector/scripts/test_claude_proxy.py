#!/usr/bin/env python3
"""验证沙箱内 internal Claude proxy 是否可用。独立运行，不依赖 sandbox_inspect。"""
import os, sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *

import time

def main():
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    api_key  = os.environ.get("ANTHROPIC_API_KEY", "")
    print(f"ANTHROPIC_BASE_URL = {base_url or '(not set)'}")
    print(f"ANTHROPIC_API_KEY  = {api_key  or '(not set)'}")

    if not base_url:
        print("FAIL: ANTHROPIC_BASE_URL 未设置")
        sys.exit(1)
    if "api.anthropic.com" in base_url:
        print("WARN: ANTHROPIC_BASE_URL 直接指向真实端点，非 internal proxy")

    import anthropic
    client = anthropic.Anthropic(timeout=30.0)

    model = "claude-haiku-4-5-20251001"
    prompt = "reply with the single word: ok"
    print(f"\n>>> model : {model}")
    print(f">>> prompt: {prompt}")
    print(f"calling {base_url} ...")
    t0 = time.time()
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=16,
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.time() - t0
        reply = resp.content[0].text.strip() if resp.content else ""
        print(f"<<< reply : {reply!r}")
        print(f"PASS  model={resp.model}"
              f" in={resp.usage.input_tokens} out={resp.usage.output_tokens}"
              f" elapsed={elapsed:.2f}s")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"<<< reply : (none)")
        print(f"FAIL  elapsed={elapsed:.2f}s error={e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
