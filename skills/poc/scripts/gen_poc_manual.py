#!/usr/bin/env python3
"""POC 测试手册 HTML 生成器。

读取 poc_test.py 输出的 results JSON + 一份模板 + 一份 CSS，
渲染成单文件 HTML（图片 base64 嵌入，无外部依赖、可邮件直发）。

模板路由：
  .html  → Jinja2 渲染（推荐）；py 侧传 by_agent dict，模板自己写循环
  .md    → 传统 markdown 渲染（旧模板，保留供回退）

Jinja2 模板可用变量：
  顶层：title, brand_name, brand_website, generated_at, total_cases,
        console_url, agents_url, account_email, account_password,
        scene_count, by_agent
  by_agent：dict[str, list[case]]，已过滤掉无 AI 回复的 case 和空 agent，
            case 字段：name, agent_name, agent_id, scenario, results, stopped_reason
            results 字段：turn, input, content, chatId, handoff, ...

旧 .md 模板额外占位符（{{var}} 替换）：
  scene_tags_html, agent_sections_html

用法：
  python3 gen_poc_manual.py --results results.json \\
      --output manual.html \\
      [--template assets/poc_test_template.html] \\
      [--css assets/default_manual.css] \\
      [--brand-name WOLTU] [--brand-website https://woltu.de] \\
      [--account-email a@b.com] [--password 123456] [--title "POC 测试手册"]
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403

import markdown  # noqa: E402
from jinja2 import Environment, BaseLoader  # noqa: E402

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
DEFAULT_CONSOLE_URL = "https://apps.voc.ai/chatbot#/setting"
DEFAULT_AGENTS_URL = "https://apps.voc.ai/chatbot#/agents"
DEFAULT_TEMPLATE = str(ASSETS_DIR / "poc_test_template.html")
DEFAULT_CSS = str(ASSETS_DIR / "default_manual.css")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _has_reply(case: dict) -> bool:
    """case 中是否有至少一轮 AI 实际回复了内容（过滤掉全部出错 / 无 content 的 case）。"""
    return any(t.get("content") for t in case.get("results", []))


# ── MD-path rendering (legacy, kept for rollback) ────────────────────────────

def _render_dialogues(turns) -> str:
    rows = []
    for t in turns:
        u = _esc(t.get("input", ""))
        b = _esc(t.get("content", "")).replace("\n", "<br>")
        rows.append(
            f'<div class="msg"><span class="label">👤 User</span>'
            f'<div class="bubble user-bubble">{u}</div></div>'
        )
        rows.append(
            f'<div class="msg"><span class="label">🤖 AI</span>'
            f'<div class="bubble bot-bubble">{b}</div></div>'
        )
    return "\n".join(rows)


def _render_cases(cases) -> str:
    out = []
    for c in cases:
        results = c.get("results", [])
        chat_id = results[-1].get("chatId", "—") if results else "—"
        scenario = c.get("scenario") or c.get("name", "")
        case_id = c.get("name", "")
        out.append(f"""<div class="case-card">
<div class="case-header">
  <span class="case-id">{_esc(case_id)}</span>
  <span class="case-scenario">{_esc(scenario)}</span>
  <span class="chat-id-badge">Chat ID: <code>{_esc(chat_id)}</code></span>
</div>
<div class="dialogue">{_render_dialogues(results)}</div>
</div>""")
    return "\n".join(out)


def _render_agent_sections(by_agent: dict) -> str:
    out = []
    for aname, cases in by_agent.items():
        visible = [c for c in cases if _has_reply(c)]
        if not visible:
            continue
        aid = visible[0].get("agent_id", "")
        out.append(
            f'<section class="agent-section">'
            f'<h2>🤖 {_esc(aname)} <span class="agent-meta">Agent ID: {aid}</span></h2>'
            f'{_render_cases(visible)}</section>'
        )
    return "\n".join(out)


def _render_scene_tags(by_agent: dict) -> str:
    return "".join(f'<span class="scene-tag">{_esc(n)}</span>' for n in by_agent.keys())


def render_template(tpl: str, ctx: dict) -> str:
    """轻量模板替换：仅 {{var}} 占位符（旧 .md 路径使用）。"""
    def _sub(match):
        key = match.group(1).strip()
        val = ctx.get(key, "")
        return str(val) if val is not None else ""
    return re.sub(r"\{\{\s*([\w\.]+)\s*\}\}", _sub, tpl)


# ── Image embedding ───────────────────────────────────────────────────────────

def _embed_images_as_base64(html: str, base_dir: Path) -> str:
    """把 <img src="<rel_path>"> 替换成 data: base64 内嵌。

    跳过远程 URL（http/https/data:）。本地路径找不到时打 warning 但不阻断渲染。
    """
    def _sub(m):
        prefix = m.group(1)
        src = m.group(2)
        suffix = m.group(3)
        if src.startswith(("http://", "https://", "data:")):
            return m.group(0)
        img_path = (base_dir / src).resolve()
        if not img_path.exists():
            print(f"[warn] image not found, kept original src: {img_path}", file=sys.stderr)
            return m.group(0)
        mime, _ = mimetypes.guess_type(str(img_path))
        if not mime:
            mime = "image/png"
        b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
        return f'{prefix}data:{mime};base64,{b64}{suffix}'
    return re.sub(r'(<img[^>]*\ssrc=")([^"]+)(")', _sub, html)


def _wrap_html(body: str, title: str, css: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
{css}
</style>
</head>
<body>
{body}
</body>
</html>
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="POC 测试手册 HTML 生成器")
    parser.add_argument("--results", required=True, help="poc_test.py 输出的 results JSON 路径")
    parser.add_argument("--output", required=True, help="输出 HTML 路径")
    parser.add_argument("--title", default="Solvea POC 测试手册", help="手册标题")
    parser.add_argument("--brand-name", default="", help="客户品牌名")
    parser.add_argument("--brand-website", default="", help="客户品牌官网 URL")
    parser.add_argument("--console-url", default=DEFAULT_CONSOLE_URL)
    parser.add_argument("--agents-url", default=DEFAULT_AGENTS_URL)
    parser.add_argument("--account-email", default=os.environ.get("SOLVEA_ACCOUNT_EMAIL", "请联系实施顾问获取"))
    parser.add_argument("--password", default="123456")
    args = parser.parse_args()

    summary = json.loads(Path(args.results).read_text(encoding="utf-8"))
    results = summary.get("results", [])

    # 按 agent 分组，并过滤掉无 AI 回复的 case 和全空的 agent section
    by_agent_raw: dict = defaultdict(list)
    for r in results:
        by_agent_raw[r.get("agent_name") or "(unknown)"].append(r)

    by_agent = {
        aname: visible
        for aname, cases in by_agent_raw.items()
        if (visible := [c for c in cases if _has_reply(c)])
    }

    tpl_path = Path(DEFAULT_TEMPLATE)
    tpl = tpl_path.read_text(encoding="utf-8")

    ctx = {
        "title": args.title,
        "brand_name": args.brand_name,
        "brand_website": args.brand_website,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_cases": len(results),
        "console_url": args.console_url,
        "agents_url": args.agents_url,
        "account_email": args.account_email,
        "account_password": args.password,
        "scene_count": len(by_agent),
        "by_agent": by_agent,
    }

    if tpl_path.suffix.lower() == ".html":
        # Jinja2 渲染：模板自带 CSS + 循环，直接输出完整 HTML
        env = Environment(loader=BaseLoader(), autoescape=False)
        template = env.from_string(tpl)
        html = template.render(**ctx)
        html = _embed_images_as_base64(html, base_dir=tpl_path.parent)
    else:
        # 旧 .md 路径（保留供回退）
        md_ctx = {
            **ctx,
            "scene_tags_html": _render_scene_tags(by_agent),
            "agent_sections_html": _render_agent_sections(by_agent_raw),
        }
        rendered = render_template(tpl, md_ctx)
        body = markdown.markdown(
            rendered,
            extensions=["tables", "fenced_code", "md_in_html", "sane_lists"],
        )
        body = _embed_images_as_base64(body, base_dir=tpl_path.parent)
        css = Path(args.css).read_text(encoding="utf-8")
        html = _wrap_html(body, title=args.title, css=css)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"  Manual rendered → {out_path}  ({size_kb:.1f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
