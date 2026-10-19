#!/usr/bin/env python3
"""KB website crawl pipeline entry.

Phase 4 implementation:
- 固定 `--mode auto|crawl|legacy` 与 `--provider auto|crawl4ai|tavily` CLI。
- `legacy` 明确输出兼容旧 reference 路径的结果，不执行抓取。
- `crawl/provider=auto` 使用内置轻量 HTTP BFS crawler，输出稳定 crawl_result。
- `crawl4ai` provider 使用 sandbox 内 Python 依赖抓取 JS/动态站点，失败时给出显式错误。

本脚本只负责 KB builder 内部网页抓取能力，不暴露给 POC / Delivery 业务细节。
"""
from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403


USER_AGENT = "SolveaKit-KB-Crawler/1.0"


def resolve_workspace_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute() and str(p).startswith("/workspace"):
        return WORKSPACE / p.relative_to("/workspace")
    return p


def virtual_workspace_path(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(WORKSPACE.resolve())
        return str(Path("/workspace") / rel)
    except Exception:
        return str(path)


def slugify(value: str, fallback: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-")
    return text[:80] or fallback


def normalize_url(url: str) -> str:
    clean, _frag = urldefrag(url.strip())
    return clean.rstrip("/")


def same_domain(url: str, base_netloc: str) -> bool:
    netloc = urlparse(url).netloc.lower()
    return netloc == base_netloc.lower()


def fetch_html(url: str, timeout: int) -> tuple[int, str, str]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200)
        final_url = resp.geturl()
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
    return status, final_url, text


def extract_title(html_text: str, url: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.I | re.S)
    if not m:
        return urlparse(url).path.strip("/") or url
    title = re.sub(r"\s+", " ", html.unescape(m.group(1))).strip()
    return title or url


def strip_noise(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|canvas).*?</\1>", " ", html_text)
    text = re.sub(r"(?is)<(nav|footer|header)[^>]*>.*?</\1>", " ", text)
    return text


def html_to_markdown(html_text: str) -> str:
    cleaned = strip_noise(html_text)
    try:
        from markdownify import markdownify as md  # type: ignore

        markdown = md(cleaned, heading_style="ATX")
    except Exception:
        markdown = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
        markdown = re.sub(r"(?i)</(p|div|section|article|li|h[1-6])>", "\n", markdown)
        markdown = re.sub(r"<[^>]+>", " ", markdown)
        markdown = html.unescape(markdown)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in markdown.splitlines()]
    compact: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                compact.append("")
            blank = True
            continue
        compact.append(line)
        blank = False
    return "\n".join(compact).strip()


def extract_links(html_text: str, page_url: str, base_netloc: str) -> list[str]:
    links: list[str] = []
    for href in re.findall(r'''(?is)<a[^>]+href=["']([^"']+)["']''', html_text):
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = normalize_url(urljoin(page_url, html.unescape(href)))
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if not same_domain(absolute, base_netloc):
            continue
        if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|rar|7z|mp4|mov|avi)$", parsed.path, re.I):
            continue
        links.append(absolute)
    return sorted(set(links))


def classify_page(url: str, title: str, markdown: str) -> str:
    path = urlparse(url).path.lower()
    if path.startswith("/products/") or path.startswith("/collections/"):
        return "product"
    if path.startswith("/policies/") or re.search(r"/(warranty|return|refund|shipping|privacy|terms|policy)", path):
        return "policy"
    if re.search(r"/(help|support|docs|documentation|faq|knowledge-base|troubleshoot)", path):
        return "help_center"

    hay = f"{url}\n{title}\n{markdown[:3000]}".lower()
    if re.search(r"\b(help|support|docs|documentation|faq|knowledge-base|troubleshoot)\b", hay):
        return "help_center"
    if re.search(r"\b(product|products|collection|collections|sku|model|add to cart|buy now|shop)\b", hay):
        return "product"
    if re.search(r"\b(warranty|return|refund|shipping|privacy|terms|policy|guarantee)\b", hay):
        return "policy"
    return "other"


def write_page_markdown(pages_dir: Path, index: int, url: str, title: str, markdown: str) -> Path:
    pages_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title or urlparse(url).path, f"page-{index:03d}")
    out = pages_dir / f"{index:03d}_{slug}.md"
    out.write_text(f"# {title}\n\nURL: {url}\n\n{markdown}\n", encoding="utf-8")
    return out


def crawl_builtin(base_url: str, *, max_depth: int, max_pages: int, timeout: int, output_path: Path) -> dict[str, Any]:
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"invalid URL: {base_url}")

    base_url = normalize_url(base_url)
    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    pages_dir = output_path.parent / f"{output_path.stem}_pages"

    while queue and len(pages) < max_pages:
        url, depth = queue.popleft()
        url = normalize_url(url)
        if url in seen:
            continue
        seen.add(url)
        try:
            status, final_url, html_text = fetch_html(url, timeout=timeout)
            title = extract_title(html_text, final_url)
            markdown = html_to_markdown(html_text)
            links = extract_links(html_text, final_url, parsed.netloc)
            page_type = classify_page(final_url, title, markdown)
            md_path = write_page_markdown(pages_dir, len(pages) + 1, final_url, title, markdown)
            pages.append({
                "url": final_url,
                "title": title,
                "type": page_type,
                "depth": depth,
                "status": status,
                "markdown_path": virtual_workspace_path(md_path),
                "fit_markdown_path": virtual_workspace_path(md_path),
                "links": links[:100],
                "images": [],
            })
            if depth < max_depth:
                for link in links:
                    if link not in seen:
                        queue.append((link, depth + 1))
        except Exception as exc:
            errors.append({"url": url, "depth": depth, "error": str(exc)})

    return {
        "base_url": base_url,
        "provider": "builtin",
        "mode": "crawl",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "max_depth": max_depth,
        "max_pages": max_pages,
        "pages": pages,
        "errors": errors,
    }


def result_value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def markdown_value(result: Any) -> tuple[str, str]:
    markdown_obj = result_value(result, "markdown")
    fit_markdown = result_value(markdown_obj, "fit_markdown") or result_value(result, "fit_markdown") or ""
    markdown = (
        result_value(markdown_obj, "raw_markdown")
        or result_value(markdown_obj, "markdown_with_citations")
        or result_value(result, "markdown")
        or ""
    )
    if not isinstance(markdown, str):
        markdown = str(markdown or "")
    if not isinstance(fit_markdown, str):
        fit_markdown = str(fit_markdown or "")
    return markdown.strip(), fit_markdown.strip()


def links_from_crawl4ai(result: Any, page_url: str, base_netloc: str) -> list[str]:
    raw_links = result_value(result, "links", {}) or {}
    candidates: list[Any] = []
    if isinstance(raw_links, dict):
        for key in ("internal", "external"):
            value = raw_links.get(key) or []
            if isinstance(value, list):
                candidates.extend(value)
    elif isinstance(raw_links, list):
        candidates.extend(raw_links)

    links: list[str] = []
    for item in candidates:
        href = item.get("href") if isinstance(item, dict) else str(item or "")
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absolute = normalize_url(urljoin(page_url, html.unescape(href)))
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        if not same_domain(absolute, base_netloc):
            continue
        if re.search(r"\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|rar|7z|mp4|mov|avi)$", parsed.path, re.I):
            continue
        links.append(absolute)
    return sorted(set(links))


async def crawl4ai_page(crawler: Any, url: str, timeout: int) -> Any:
    try:
        from crawl4ai import CacheMode, CrawlerRunConfig  # type: ignore

        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            page_timeout=timeout * 1000,
            remove_overlay_elements=True,
            word_count_threshold=10,
        )
        return await crawler.arun(url=url, config=config)
    except TypeError:
        return await crawler.arun(url=url)


async def crawl4ai_async(base_url: str, *, max_depth: int, max_pages: int, timeout: int, output_path: Path) -> dict[str, Any]:
    try:
        from crawl4ai import AsyncWebCrawler, BrowserConfig  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "crawl4ai is not installed in the current runtime; run this script inside the sandbox dependency group"
        ) from exc

    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"invalid URL: {base_url}")

    base_url = normalize_url(base_url)
    queue: deque[tuple[str, int]] = deque([(base_url, 0)])
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    pages_dir = output_path.parent / f"{output_path.stem}_pages"

    browser_config = BrowserConfig(headless=True, verbose=False)
    async with AsyncWebCrawler(config=browser_config) as crawler:
        while queue and len(pages) < max_pages:
            url, depth = queue.popleft()
            url = normalize_url(url)
            if url in seen:
                continue
            seen.add(url)
            try:
                result = await crawl4ai_page(crawler, url, timeout)
                success = result_value(result, "success", True)
                if success is False:
                    error = result_value(result, "error_message", "crawl4ai returned success=false")
                    errors.append({"url": url, "depth": depth, "error": str(error)})
                    continue

                final_url = normalize_url(result_value(result, "url", url) or url)
                title = result_value(result, "metadata", {}) or {}
                title_text = title.get("title") if isinstance(title, dict) else ""
                markdown, fit_markdown = markdown_value(result)
                body = fit_markdown or markdown
                links = links_from_crawl4ai(result, final_url, parsed.netloc)
                page_type = classify_page(final_url, title_text or final_url, body)
                md_path = write_page_markdown(pages_dir, len(pages) + 1, final_url, title_text or final_url, body)
                pages.append({
                    "url": final_url,
                    "title": title_text or final_url,
                    "type": page_type,
                    "depth": depth,
                    "status": result_value(result, "status_code", 200),
                    "markdown_path": virtual_workspace_path(md_path),
                    "fit_markdown_path": virtual_workspace_path(md_path),
                    "links": links[:100],
                    "images": [],
                })
                if depth < max_depth:
                    for link in links:
                        if link not in seen:
                            queue.append((link, depth + 1))
            except Exception as exc:
                errors.append({"url": url, "depth": depth, "error": str(exc)})

    return {
        "base_url": base_url,
        "provider": "crawl4ai",
        "mode": "crawl",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "max_depth": max_depth,
        "max_pages": max_pages,
        "pages": pages,
        "errors": errors,
    }


def crawl4ai_provider(base_url: str, *, max_depth: int, max_pages: int, timeout: int, output_path: Path) -> dict[str, Any]:
    return asyncio.run(crawl4ai_async(
        base_url,
        max_depth=max_depth,
        max_pages=max_pages,
        timeout=timeout,
        output_path=output_path,
    ))


def legacy_result(url: str, reason: str) -> dict[str, Any]:
    return {
        "base_url": url,
        "provider": "legacy",
        "mode": "legacy",
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "pages": [],
        "errors": [{"url": url, "error": reason}],
        "next_step": "Use kb-builder legacy references and agent web_crawl/web_fetch tools.",
    }


def error_result(url: str, provider: str, mode: str, error: Exception) -> dict[str, Any]:
    return {
        "base_url": url,
        "provider": provider,
        "mode": mode,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "pages": [],
        "errors": [{"url": url, "error": str(error), "error_type": error.__class__.__name__}],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl website pages for kb-builder")
    parser.add_argument("--url", required=True, help="Website / product / help center URL")
    parser.add_argument("--mode", choices=["auto", "crawl", "legacy"], default="auto")
    parser.add_argument("--provider", choices=["auto", "crawl4ai", "tavily"], default="auto")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--output", default="", help="Output crawl_result JSON path")
    args = parser.parse_args()

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output = resolve_workspace_path(args.output) if args.output else OUTPUTS_DIR / f"crawl_result_{timestamp()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    started = time.time()
    try:
        if args.mode == "legacy" or args.provider == "tavily":
            result = legacy_result(args.url, "legacy/Tavily path is intentionally preserved; script provider not used.")
        elif args.provider == "crawl4ai":
            result = crawl4ai_provider(
                args.url,
                max_depth=max(0, args.max_depth),
                max_pages=max(1, args.max_pages),
                timeout=max(1, args.timeout),
                output_path=output,
            )
        else:
            result = crawl_builtin(
                args.url,
                max_depth=max(0, args.max_depth),
                max_pages=max(1, args.max_pages),
                timeout=max(1, args.timeout),
                output_path=output,
            )
    except Exception as exc:
        result = error_result(args.url, args.provider, "legacy" if args.mode == "legacy" else "crawl", exc)

    result["elapsed_seconds"] = round(time.time() - started, 3)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[crawl_site] output={virtual_workspace_path(output)} pages={len(result.get('pages') or [])} errors={len(result.get('errors') or [])}")


if __name__ == "__main__":
    main()
