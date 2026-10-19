#!/usr/bin/env python3
"""Fetch the current Desk ticket list into a local XLSX snapshot."""

import os
import sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import (  # noqa: E402
    OUTPUTS_DIR,
    SOLVEA_ENV,
    SOLVEA_PROJECT_ID,
    SOLVEA_TENANT_ID,
    STATE_DIR,
    TMP_DIR,
    timestamp,
)

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pandas as pd

from desk_api import DeskApiConfig, request_json, resolve_desk_api_config


SOURCE_TYPE = "ticket_list_snapshot"
SOURCE_CONTRACT = "current_user_view_filtered_paginated_api"
TICKET_LIST_PATH = "/api_v2/tars/api/ticket/list"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
DEFAULT_MAX_PAGES = 120
DEFAULT_MAX_ROWS = 200000
BACKEND_FILTER_FIELDS = {
    "ticketNumber",
    "ticketStatusList",
    "channelList",
    "platformList",
    "channelIdList",
    "supportEmailIdList",
    "agentIdList",
    "tagList",
    "replyUserList",
    "customerEmail",
    "customerName",
    "customerEmailFull",
    "customerPhone",
    "createTimeBegin",
    "createTimeEnd",
    "keyword",
    "marketList",
    "sendFailure",
    "orderId",
    "categoryList",
    "brandList",
    "humanHandling",
    "myTicket",
    "snoozed",
    "scheduled",
    "notSpam",
    "notNotification",
    "botIdList",
    "noTag",
    "ticketNumberList",
    "supportPhoneList",
    "unread",
    "personaId",
    "campaignName",
    "lastVoiceAnswerType",
    "lastVoicePhoneType",
}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def resolve_source_config() -> DeskApiConfig:
    """Resolve the Desk ticket-list endpoint for the current environment."""
    config = resolve_desk_api_config()
    explicit_endpoint = os.environ.get("DESK_TICKET_SOURCE_URL", "").strip()
    if not explicit_endpoint:
        return config
    parsed = urlsplit(explicit_endpoint)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("DESK_TICKET_SOURCE_URL must be an absolute URL")
    return DeskApiConfig(
        base_url=f"{parsed.scheme}://{parsed.netloc}",
        token=config.token,
        cookie_name=config.cookie_name,
    )


def _ticket_list_path() -> str:
    explicit_endpoint = os.environ.get("DESK_TICKET_SOURCE_URL", "").strip()
    if not explicit_endpoint:
        return TICKET_LIST_PATH
    parsed = urlsplit(explicit_endpoint)
    return parsed.path or TICKET_LIST_PATH


def validate_page_size(page_size: str | int) -> int:
    try:
        value = int(page_size)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("page-size must be an integer") from exc
    if value < 1 or value > MAX_PAGE_SIZE:
        raise argparse.ArgumentTypeError(f"page-size must be between 1 and {MAX_PAGE_SIZE}")
    return value


def parse_backend_filters(raw_json: str = "", filters_file: str = "") -> dict[str, Any]:
    """Parse the filter-only subset of TicketListPageDTO."""
    if raw_json and filters_file:
        raise ValueError("use only one of --filters-json and --filters-file")
    if filters_file:
        raw_json = Path(filters_file).read_text(encoding="utf-8")
    if not raw_json:
        return {}
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError("ticket filters must be a JSON object")
    unknown = sorted(set(payload) - BACKEND_FILTER_FIELDS)
    if unknown:
        raise ValueError(f"unsupported ticket filter fields: {', '.join(unknown)}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    code = payload.get("code")
    if code is not None and str(code) != "200":
        raise RuntimeError(payload.get("message") or "Desk ticket-list API failed")
    body = payload.get("data", payload)
    if not isinstance(body, dict):
        return []
    values = body.get("list") or body.get("records") or body.get("items") or []
    return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


def _page_body(payload: dict[str, Any]) -> dict[str, Any]:
    body = payload.get("data", payload)
    return body if isinstance(body, dict) else {}


def _has_more(payload: dict[str, Any], page: int, page_size: int, row_count: int) -> bool:
    body = _page_body(payload)
    for key in ("hasMore", "has_more"):
        if key in body:
            return bool(body[key])
    total = body.get("total")
    if isinstance(total, int):
        return page * page_size < total
    return row_count >= page_size


def _request_page(
    client: httpx.Client,
    config: DeskApiConfig,
    *,
    page: int,
    page_size: int,
    view_id: str,
    sort: str,
    order: str,
    backend_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = {
        "page": page,
        "pageSize": page_size,
        "viewId": view_id,
        "sort": sort,
        "order": order,
    }
    request_payload.update(backend_filters or {})
    return request_json(
        client,
        config,
        "POST",
        _ticket_list_path(),
        json_body=request_payload,
    )


def fetch_pages(
    config: DeskApiConfig,
    *,
    page_size: int,
    max_pages: int,
    max_rows: int,
    view_id: str,
    sort: str,
    order: str,
    backend_filters: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool, str]:
    page_size = validate_page_size(page_size)
    pages: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    truncated = False
    completion_reason = "source_exhausted"
    with httpx.Client(timeout=60.0) as client:
        for page_no in range(1, max_pages + 1):
            payload = _request_page(
                client,
                config,
                page=page_no,
                page_size=page_size,
                view_id=view_id,
                sort=sort,
                order=order,
                backend_filters=backend_filters,
            )
            page_records = _records(payload)
            pages.append(payload)
            records.extend(page_records)
            if len(records) >= max_rows:
                exceeded_limit = len(records) > max_rows
                records = records[:max_rows]
                has_more = _has_more(payload, page_no, page_size, len(page_records))
                truncated = exceeded_limit or has_more
                completion_reason = "max_rows" if truncated else "source_exhausted"
                break
            if not _has_more(payload, page_no, page_size, len(page_records)):
                break
        else:
            truncated = True
            completion_reason = "max_pages"
    return pages, records, truncated, completion_reason


def write_snapshot(
    task_id: str,
    pages: list[dict[str, Any]],
    records: list[dict[str, Any]],
    *,
    config: DeskApiConfig,
    page_size: int,
    view_id: str,
    sort: str,
    order: str,
    truncated: bool,
    backend_filters: dict[str, Any] | None = None,
    completion_reason: str = "source_exhausted",
) -> dict[str, Any]:
    state_task_dir = STATE_DIR / task_id
    output_task_dir = OUTPUTS_DIR / task_id
    tmp_task_dir = TMP_DIR / task_id
    state_task_dir.mkdir(parents=True, exist_ok=True)
    tmp_task_dir.mkdir(parents=True, exist_ok=True)

    for index, page in enumerate(pages, start=1):
        _write_json(tmp_task_dir / f"raw_page_{index:03d}.json", page)

    rows = [{key: _normalize_cell(value) for key, value in row.items()} for row in records]
    dataframe = pd.DataFrame(rows) if rows else pd.DataFrame([{"_empty": ""}])
    datasource = state_task_dir / "datasource.xlsx"
    dataframe.to_excel(datasource, sheet_name="data", index=False, engine="openpyxl")

    manifest = {
        "status": "ready",
        "skill": "solvea-desk",
        "source_type": SOURCE_TYPE,
        "source_contract": SOURCE_CONTRACT,
        "task_id": task_id,
        "env": SOLVEA_ENV,
        "tenant_id": SOLVEA_TENANT_ID,
        "project_id": SOLVEA_PROJECT_ID,
        "endpoint": f"{config.base_url}{_ticket_list_path()}",
        "data_scope": "current_user",
        "snapshot_semantics": "current_state",
        "view_id": view_id,
        "sort": sort,
        "order": order,
        "backend_filters": backend_filters or {},
        "completion_reason": completion_reason,
        "page_size": page_size,
        "page_count": len(pages),
        "row_counts": {"data": len(records)},
        "truncated": truncated,
        "files": {
            "state": {
                "datasource": "datasource.xlsx",
                "manifest": "manifest.json",
                "analysis": "analysis.py",
                "report_data": "report_data.json",
                "calculation_notes": "calculation_notes.json",
            },
            "outputs": {
                "report_pattern": "<report_slug>.html",
                "detail_pattern": "<report_slug>_detail.xlsx",
            },
        },
        "datasource": str(datasource),
        "tmp_raw_pages": str(tmp_task_dir),
        "generated_at": _now_iso(),
    }
    _write_json(state_task_dir / "manifest.json", manifest)
    _write_json(
        STATE_DIR / "latest_task.json",
        {
            "skill": "solvea-desk",
            "status": "ready",
            "source_type": SOURCE_TYPE,
            "task_id": task_id,
            "task_dir": str(state_task_dir),
            "state_task_dir": str(state_task_dir),
            "output_task_dir": str(output_task_dir),
            "tmp_task_dir": str(tmp_task_dir),
            "view_id": view_id,
            "backend_filters": backend_filters or {},
            "updated_at": _now_iso(),
        },
    )
    return {
        "ok": True,
        "source_type": SOURCE_TYPE,
        "task_id": task_id,
        "task_dir": str(state_task_dir),
        "state_task_dir": str(state_task_dir),
        "output_task_dir": str(output_task_dir),
        "tmp_task_dir": str(tmp_task_dir),
        "datasource": str(datasource),
        "manifest": str(state_task_dir / "manifest.json"),
        "row_counts": {"data": len(records)},
        "truncated": truncated,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch current Desk ticket details into datasource.xlsx")
    parser.add_argument("--task-id", default="", help="Optional task id; defaults to timestamp")
    parser.add_argument("--view-id", default="1", help="Desk ticket view id")
    parser.add_argument("--page-size", type=validate_page_size, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    parser.add_argument("--sort", default="last_update_time")
    parser.add_argument("--order", choices=["ASC", "DESC"], default="DESC")
    parser.add_argument(
        "--filters-json",
        default="",
        help="JSON object containing supported TicketListPageDTO filter fields",
    )
    parser.add_argument("--filters-file", default="", help="Path to a JSON filter object")
    args = parser.parse_args()

    try:
        backend_filters = parse_backend_filters(args.filters_json, args.filters_file)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        parser.error(str(exc))

    config = resolve_source_config()
    if not config.token:
        print(json.dumps({
            "ok": False,
            "source_type": SOURCE_TYPE,
            "error": "desk_ticket_runtime_not_configured",
            "message": "Check SOLVEA_ENV and the corresponding Solvea token environment variable.",
        }, ensure_ascii=False, indent=2))
        return 2

    task_id = args.task_id.strip() or timestamp()
    pages, records, truncated, completion_reason = fetch_pages(
        config,
        page_size=args.page_size,
        max_pages=args.max_pages,
        max_rows=args.max_rows,
        view_id=args.view_id,
        sort=args.sort,
        order=args.order,
        backend_filters=backend_filters,
    )
    result = write_snapshot(
        task_id,
        pages,
        records,
        config=config,
        page_size=args.page_size,
        view_id=args.view_id,
        sort=args.sort,
        order=args.order,
        truncated=truncated,
        backend_filters=backend_filters,
        completion_reason=completion_reason,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 3 if truncated else 0


if __name__ == "__main__":
    raise SystemExit(main())
