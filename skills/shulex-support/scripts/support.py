#!/usr/bin/env python3
"""CLI for Shulex product docs lookup and support ticket APIs.

Usage:
  python3 /skills/shulex-support/scripts/support.py search-docs --query "how to connect" --pretty
  python3 /skills/shulex-support/scripts/support.py query-docs-filesystem --command 'rg -il "变量" / | head -10' --pretty
  python3 /skills/shulex-support/scripts/support.py create-ticket --content "help me" --pretty
  python3 /skills/shulex-support/scripts/support.py list-tickets --page 1 --page-size 20 --pretty
  python3 /skills/shulex-support/scripts/support.py get-ticket --ticket-number CX-1 --pretty
  python3 /skills/shulex-support/scripts/support.py append-message --ticket-number CX-1 --content "more details" --pretty
"""
from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
import re
import sys
import uuid
from typing import Any
from urllib import error, parse, request

sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import *  # noqa: F401,F403


def _base_url() -> str:
    env = os.environ.get("SOLVEA_ENV", "prod")
    if env == "prod":
        base_url = os.environ.get("SOLVEA_PROD_URL", "https://apps.voc.ai").strip()
    else:
        base_url = os.environ.get("SOLVEA_BASE_URL", "https://apps-staging.voc.ai").strip()
    return f"{base_url.rstrip('/')}/api_v2/gpt"


def _support_ticket_origin() -> str:
    env = os.environ.get("SOLVEA_ENV", "prod")
    if env == "prod":
        return os.environ.get("SOLVEA_SUPPORT_PORTAL_URL", "https://ai.solvea.cx").rstrip("/")
    return os.environ.get("SOLVEA_SUPPORT_PORTAL_URL_STAGING", "https://ai-staging.solvea.cx").rstrip("/")


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    env = os.environ.get("SOLVEA_ENV", "prod")
    if env == "prod":
        token = os.environ.get("SOLVEA_PROD_TOKEN", "").strip() or os.environ.get("SOLVEA_TOKEN", "").strip()
        cookie_name = "_token"
    else:
        token = os.environ.get("SOLVEA_TOKEN", "").strip()
        cookie_name = "_token_staging"
    if token:
        headers["Cookie"] = f"{cookie_name}={token}"
    # 透传当前请求的 trace，让 gpt/ARMS 续上同一条链路（SLS 可按一个 trace 串到底）；env 没有就不带，不影响独立运行
    traceparent = os.environ.get("TRACEPARENT", "").strip()
    if traceparent:
        headers["traceparent"] = traceparent
    return headers


def _request(
    method: str,
    path: str,
    payload: dict[str, Any] | bytes | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    if payload is None:
        data = None
    elif isinstance(payload, bytes):
        data = payload
    else:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, method=method.upper(), headers=headers or _headers())
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {method.upper()} {url}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"HTTP request failed {method.upper()} {url}: {exc.reason}") from exc
    return json.loads(body) if body else {}


def _unwrap_result(payload: dict[str, Any]) -> Any:
    if payload.get("code") != 200:
        raise RuntimeError(payload.get("message") or "support ticket API failed")
    return payload.get("data")


_DOCS_SERVICE_URL = "https://solvea-39f11a36.mintlify.app/mcp"
_DOCS_PREVIEW_URL_PREFIX = "https://solvea-39f11a36.mintlify.app/"
_PUBLIC_DOCS_URL_PREFIX = "https://www.voc.ai/cn/docs/"


def _tool_text_blocks(result: Any) -> list[str]:
    blocks = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            blocks.append(text)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            blocks.append(item["text"])
    return blocks


def _call_docs_tool(tool_name: str, arguments: dict[str, Any]) -> list[str]:
    """Call the product docs service and return text content blocks."""

    timeout = float(os.environ.get("SOLVEA_DOCS_MCP_TIMEOUT_SECONDS", "30"))

    async def _call() -> list[str]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(_DOCS_SERVICE_URL, timeout=timeout, sse_read_timeout=timeout) as (
            read,
            write,
            _get_session_id,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)

        if getattr(result, "isError", False):
            text = "\n".join(_tool_text_blocks(result)).strip()
            raise RuntimeError(text or f"Product docs query failed: {tool_name}")
        return _tool_text_blocks(result)

    return asyncio.run(asyncio.wait_for(_call(), timeout=timeout + 5))


def _parse_search_result_block(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    result: dict[str, Any] = {}
    content_lines: list[str] = []
    in_content = False
    for line in lines:
        if in_content:
            content_lines.append(line)
            continue
        if line.startswith("Title: "):
            result["title"] = line[len("Title: "):].strip()
        elif line.startswith("Link: "):
            result["url"] = line[len("Link: "):].strip()
        elif line.startswith("Page: "):
            result["page"] = line[len("Page: "):].strip()
        elif line.startswith("Content:"):
            first_line = line[len("Content:"):].lstrip()
            if first_line:
                content_lines.append(first_line)
            in_content = True
    content = "\n".join(content_lines).strip()
    if content:
        result["content"] = content
    if not result:
        result["content"] = text
    return result


def _public_docs_url(url: str) -> str:
    if not url.startswith(_DOCS_PREVIEW_URL_PREFIX):
        return url
    path = url[len(_DOCS_PREVIEW_URL_PREFIX):]
    fragment = ""
    if "#" in path:
        path, fragment = path.split("#", 1)
        fragment = f"#{fragment}"
    if path.startswith("solvea/bot_cn/"):
        return _PUBLIC_DOCS_URL_PREFIX + "bot/" + path.rsplit("/", 1)[-1] + fragment
    if path.startswith("updates/log_cn/log/"):
        version = path.rsplit("/", 1)[-1]
        version = re.sub(r"^(V|v)(\d+)-(\d+)-(\d+)$", r"\1\2.\3.\4", version)
        version = re.sub(r"^(version\d+)-(\d+)-(\d+)$", r"\1.\2.\3", version)
        return _PUBLIC_DOCS_URL_PREFIX + "log/" + version + fragment
    return _PUBLIC_DOCS_URL_PREFIX + path + fragment


def _cmd_search_docs(args: argparse.Namespace) -> Any:
    blocks = _call_docs_tool("search_solvea", {"query": args.query})
    results = [_parse_search_result_block(block) for block in blocks]
    for result in results:
        url = result.get("url")
        if isinstance(url, str):
            result["url"] = _public_docs_url(url)
    return {
        "query": args.query,
        "results": results,
    }


def _cmd_query_docs_filesystem(args: argparse.Namespace) -> Any:
    blocks = _call_docs_tool("query_docs_filesystem_solvea", {"command": args.command})
    return {
        "command": args.command,
        "output": blocks,
    }


def _normalize_create_ticket_result(ticket: Any) -> Any:
    if not isinstance(ticket, dict):
        return ticket
    # 只返回客户相关字段；内部字段（sourceType/sourceId、tars/shulex 工单号、同步时间戳等）一律不透出
    ticket_number = ticket.get("ticketNumber")
    result = {
        "ticketNumber": ticket_number,
        "ticketDetailUrl": (
            f"{_support_ticket_origin()}/chatbot#/support/tickets/{ticket_number}"
            if ticket_number
            else None
        ),
        "status": ticket.get("status"),
        "subject": ticket.get("subject"),
        "issueType": ticket.get("issueType"),
        "createdAt": ticket.get("createdAt"),
    }
    return {k: v for k, v in result.items() if v is not None}


def _upload_attachment(path: str) -> dict[str, Any]:
    """上传本地文件到附件端点，返回 {name, url, mimeType}。

    用 stdlib urllib 手工构造 multipart/form-data body，字段名 file。
    保留 token cookie，Content-Type 换成 multipart/form-data; boundary=...。
    """
    filename = os.path.basename(path)
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    with open(path, "rb") as f:
        file_bytes = f.read()

    boundary = uuid.uuid4().hex

    def _field_bytes(name: str, data: bytes, fname: str, content_type: str) -> bytes:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{fname}"\r\n'
            f"Content-Type: {content_type}\r\n"
            f"\r\n"
        ).encode("utf-8")
        return header + data + b"\r\n"

    body = _field_bytes("file", file_bytes, filename, mime_type)
    body += f"--{boundary}--\r\n".encode("utf-8")

    hdrs = _headers()
    hdrs["Content-Type"] = f"multipart/form-data; boundary={boundary}"

    return _unwrap_result(_request("POST", "/support/tickets/attachments/upload", body, hdrs))


def _report_ticket_created(result: Any, source_id: str) -> None:
    """非阻塞上报“创建了工单”到 support_skill_metrics；失败只打日志，绝不影响建单。

    带当前请求 token，tenantId 由 gpt 从 token 解析。
    """
    ticket_number = result.get("ticketNumber") if isinstance(result, dict) else None
    try:
        _request(
            "POST",
            "/support/skill-metrics",
            {
                "chatId": source_id,
                "ticketNumber": ticket_number,
            },
            _headers(),
        )
    except Exception as exc:  # noqa: BLE001 上报失败不影响建单
        print(
            f"support_skill_metrics ticket report failed chatId={source_id} error={exc}",
            file=sys.stderr,
        )


def _cmd_create_ticket(args: argparse.Namespace) -> Any:
    source_id = os.environ.get("CHAT_ID", "").strip()
    if not source_id:
        raise RuntimeError("CHAT_ID is not configured")

    # 先上传附件，收集 attachments 列表
    attachments = []
    for att_path in getattr(args, "attachment", None) or []:
        att = _upload_attachment(att_path)
        attachments.append(att)

    # 工单类型：--issue-type 优先，没有时回退到 --category（兼容别名）
    issue_type = getattr(args, "issue_type", None) or getattr(args, "category", None)

    # 扩展字段
    ext_fields: dict[str, Any] | None = None
    ext_str = getattr(args, "ext", None)
    if ext_str:
        ext_fields = json.loads(ext_str)

    payload: dict[str, Any] = {
        "content": args.content,
        "sourceType": "cxclaw",
        "sourceId": source_id,
        "brand": args.brand,
        "issueType": issue_type,
        "subject": args.subject,
        "contactEmail": args.contact_email,
    }
    if ext_fields is not None:
        payload["extFields"] = ext_fields
    if attachments:
        payload["attachments"] = attachments

    result = _unwrap_result(
        _request(
            "POST",
            "/support/tickets/create",
            payload,
            _headers(),
        )
    )
    _report_ticket_created(result, source_id)
    return _normalize_create_ticket_result(result)


def _cmd_list_tickets(args: argparse.Namespace) -> Any:
    return _unwrap_result(
        _request(
            "POST",
            "/support/tickets",
            {"page": args.page, "pageSize": args.page_size},
            _headers(),
        )
    )


def _cmd_get_ticket(args: argparse.Namespace) -> Any:
    ticket_number = parse.quote(args.ticket_number, safe="")
    return _unwrap_result(
        _request(
            "GET",
            f"/support/tickets/{ticket_number}",
            None,
            _headers(),
        )
    )


def _cmd_append_message(args: argparse.Namespace) -> Any:
    ticket_number = parse.quote(args.ticket_number, safe="")
    return _unwrap_result(
        _request(
            "POST",
            f"/support/tickets/{ticket_number}/messages",
            {"content": args.content},
            _headers(),
        )
    )


def _add_pretty_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call Shulex docs lookup and support ticket APIs.")
    _add_pretty_arg(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search-docs", help="Search Shulex product docs.")
    _add_pretty_arg(search)
    search.add_argument("--query", required=True)
    search.set_defaults(func=_cmd_search_docs)

    docs_fs = sub.add_parser("query-docs-filesystem", help="Run a read-only query against product docs files.")
    _add_pretty_arg(docs_fs)
    docs_fs.add_argument("--command", required=True)
    docs_fs.set_defaults(func=_cmd_query_docs_filesystem)

    create = sub.add_parser("create-ticket", help="Create a support ticket.")
    _add_pretty_arg(create)
    create.add_argument("--content", required=True)
    create.add_argument("--brand", default=None)
    create.add_argument("--issue-type", default=None,
                        help="Issue type code: agent_badcase / consult / agent_feature / "
                             "integration_feature / ticket_feature / ticket_bug / other")
    create.add_argument("--category", default=None, help="Deprecated alias for --issue-type.")
    create.add_argument("--ext", default=None,
                        help="JSON string of extra fields, e.g. '{\"chatId\":\"c1\"}'")
    create.add_argument("--attachment", action="append", default=None,
                        help="Path to a local file to attach (may be repeated).")
    create.add_argument("--subject", default=None)
    create.add_argument("--contact-email", default=None)
    create.set_defaults(func=_cmd_create_ticket)

    list_tickets = sub.add_parser("list-tickets", help="List current tenant support tickets.")
    _add_pretty_arg(list_tickets)
    list_tickets.add_argument("--page", type=int, default=1)
    list_tickets.add_argument("--page-size", type=int, default=20)
    list_tickets.set_defaults(func=_cmd_list_tickets)

    get = sub.add_parser("get-ticket", help="Get support ticket detail and messages.")
    _add_pretty_arg(get)
    get.add_argument("--ticket-number", required=True)
    get.set_defaults(func=_cmd_get_ticket)

    append = sub.add_parser("append-message", help="Append a customer message to a support ticket.")
    _add_pretty_arg(append)
    append.add_argument("--ticket-number", required=True)
    append.add_argument("--content", required=True)
    append.set_defaults(func=_cmd_append_message)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    result = args.func(args)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
