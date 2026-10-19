#!/usr/bin/env python3
"""Fetch authorized report data into a local XLSX snapshot.

The script calls exactly one ticket-system data-source endpoint. That endpoint is
responsible for account isolation and for deciding which datasets to return.
"""

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
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
import pandas as pd


SOURCE_CONTRACT = "single_time_range_paginated_api"
SOURCE_TYPE = "ticket_report_snapshot"
DEFAULT_TIME_RANGE_TYPE = "report_activity_date"
CREATED_AT = "created_at"
RAW_REPORT_SOURCE_PATH = "/api_v2/tars/api/ticket/report/raw/page"
DEFAULT_DESK_STAGING_URL = "https://desk-staging.shulex.com"
DEFAULT_DESK_PROD_URL = "https://desk.shulex.com"
DEFAULT_PAGE_SIZE = 200
MAX_PAGE_SIZE = 200
DEFAULT_MAX_PAGES = 200
DEFAULT_MAX_ROWS = 200000
DEFAULT_USER_TIMEZONE = "Asia/Shanghai"
RESERVED_DATA_KEYS = {
    "hasMore",
    "has_more",
    "nextPage",
    "next_page",
    "nextCursor",
    "next_cursor",
    "pageNo",
    "page_no",
    "pageSize",
    "page_size",
    "schema",
    "total",
}


@dataclass(frozen=True)
class SourceConfig:
    endpoint: str
    token: str
    cookie_name: str


@dataclass(frozen=True)
class TimeWindow:
    requested: dict[str, str]
    fetch_window: dict[str, str]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _base_origin(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def resolve_source_config() -> SourceConfig:
    """Resolve the Desk/Tars raw report source endpoint for the current environment."""
    env = os.environ.get("SOLVEA_ENV", SOLVEA_ENV) or "prod"
    # 鉴权沿用 SLG runtime 注入的 Solvea token；这里不新增 solvea-desk 专属长期 token。
    if env == "prod":
        token = os.environ.get("SOLVEA_PROD_TOKEN", "") or os.environ.get("SOLVEA_TOKEN", "")
        base_url = os.environ.get("DESK_REPORT_PROD_BASE_URL", DEFAULT_DESK_PROD_URL)
        cookie_name = "_token"
    else:
        token = os.environ.get("SOLVEA_TOKEN", "")
        base_url = os.environ.get("DESK_REPORT_STAGING_BASE_URL", DEFAULT_DESK_STAGING_URL)
        cookie_name = "_token_staging"

    explicit_endpoint = os.environ.get("DESK_REPORT_SOURCE_URL", "").strip()
    endpoint = explicit_endpoint or f"{base_url.rstrip('/')}{RAW_REPORT_SOURCE_PATH}"
    return SourceConfig(endpoint=endpoint, token=token, cookie_name=cookie_name)


def _parse_time(value: str, timezone_name: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("time value cannot be empty")
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo(timezone_name))
    return dt


def normalize_time_window(start: str, end: str, *, timezone_name: str = DEFAULT_USER_TIMEZONE) -> TimeWindow:
    """Normalize a full-calendar-day business window for the date-based Tars API."""
    if timezone_name != DEFAULT_USER_TIMEZONE:
        raise ValueError(f"solvea-desk only supports timezone {DEFAULT_USER_TIMEZONE}")
    business_timezone = ZoneInfo(timezone_name)
    start_dt = _parse_time(start, timezone_name).astimezone(business_timezone)
    end_dt = _parse_time(end, timezone_name).astimezone(business_timezone)
    if end_dt < start_dt:
        raise ValueError("end time must be greater than or equal to start time")
    if start_dt.time() != time.min or end_dt.time() != time.min:
        raise ValueError(
            "solvea-desk only supports full calendar days: start and end must both be 00:00:00"
        )

    return TimeWindow(
        requested={
            "start": start,
            "end": end,
            "timezone": timezone_name,
        },
        fetch_window={
            "start": start_dt.replace(tzinfo=None).isoformat(timespec="seconds"),
            "end": end_dt.replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=None).isoformat(
                timespec="seconds"
            ),
        },
    )


def validate_page_size(page_size: str | int) -> int:
    try:
        value = int(page_size)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("page-size must be an integer") from exc
    if value < 1 or value > MAX_PAGE_SIZE:
        raise argparse.ArgumentTypeError(f"page-size must be between 1 and {MAX_PAGE_SIZE}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixed_files() -> dict[str, dict[str, str]]:
    return {
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
    }


def _write_latest_state(
    state_task_dir: Path,
    status: str,
    *,
    requested_window: dict[str, str],
    fetch_window: dict[str, str],
    time_range_type: str = DEFAULT_TIME_RANGE_TYPE,
    tmp_task_dir: Path | None = None,
) -> None:
    output_task_dir = OUTPUTS_DIR / state_task_dir.name
    latest = {
        "skill": "solvea-desk",
        "source_type": SOURCE_TYPE,
        "status": status,
        "task_id": state_task_dir.name,
        "task_dir": str(state_task_dir),
        "state_task_dir": str(state_task_dir),
        "output_task_dir": str(output_task_dir),
        "tmp_task_dir": str(tmp_task_dir or (TMP_DIR / state_task_dir.name)),
        "requested_window": requested_window,
        "fetch_window": fetch_window,
        "time_range_type": time_range_type,
        "updated_at": _now_iso(),
    }
    _write_json(STATE_DIR / "latest_task.json", latest)


def write_pending_snapshot(
    state_task_dir: Path,
    *,
    start: str,
    end: str,
    reason: str,
    requested_window: dict[str, str] | None = None,
    time_range_type: str = DEFAULT_TIME_RANGE_TYPE,
) -> dict[str, Any]:
    state_task_dir.mkdir(parents=True, exist_ok=True)
    output_task_dir = OUTPUTS_DIR / state_task_dir.name
    tmp_task_dir = TMP_DIR / state_task_dir.name
    fetch_window = {"start": start, "end": end}
    requested = requested_window or {"start": start, "end": end, "timezone": DEFAULT_USER_TIMEZONE}
    manifest = {
        "status": "pending_runtime_config",
        "source_type": SOURCE_TYPE,
        "source_contract": SOURCE_CONTRACT,
        "task_id": state_task_dir.name,
        "env": SOLVEA_ENV,
        "tenant_id": SOLVEA_TENANT_ID,
        "project_id": SOLVEA_PROJECT_ID,
        "requested_window": requested,
        "fetch_window": fetch_window,
        "analysis_window": requested,
        "time_range_type": time_range_type,
        "row_counts": {},
        "truncated": False,
        "files": _fixed_files(),
        "message": "Shulex Desk runtime is not configured yet.",
        "reason": reason,
        "generated_at": _now_iso(),
    }
    _write_json(state_task_dir / "manifest.json", manifest)
    _write_latest_state(
        state_task_dir,
        "pending_runtime_config",
        requested_window=requested,
        fetch_window=fetch_window,
        time_range_type=time_range_type,
        tmp_task_dir=tmp_task_dir,
    )
    return {
        "ok": False,
        "source_type": SOURCE_TYPE,
        "task_id": state_task_dir.name,
        "task_dir": str(state_task_dir),
        "state_task_dir": str(state_task_dir),
        "output_task_dir": str(output_task_dir),
        "tmp_task_dir": str(tmp_task_dir),
        "manifest": str(state_task_dir / "manifest.json"),
        "error": "desk_report_runtime_not_configured",
        "message": "Check SOLVEA_ENV and the corresponding SOLVEA token environment variable.",
    }


def _unwrap_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        for key in ("data", "result"):
            value = payload.get(key)
            if isinstance(value, (dict, list)):
                return value
    return payload


def _records_from_value(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    records = []
    for item in value:
        if isinstance(item, dict):
            records.append(item)
        else:
            records.append({"value": item})
    return records


def extract_datasets(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Extract generic dataset sheets from one endpoint page payload."""
    # 不假设 Tars 背后有几张表；接口返回几个 list dataset，就落几个 XLSX sheet。
    body = _unwrap_payload(payload)
    datasets: dict[str, list[dict[str, Any]]] = {}

    if isinstance(body, list):
        return {"data": _records_from_value(body)}

    if not isinstance(body, dict):
        return {"data": [{"value": body}]}

    for key in ("records", "list", "items", "rows"):
        if key in body:
            records = _records_from_value(body.get(key))
            if records:
                return {"data": records}

    for key, value in body.items():
        if key in RESERVED_DATA_KEYS:
            continue
        records = _records_from_value(value)
        if records:
            datasets[key] = records

    if datasets:
        return datasets
    return {"data": []}


def _has_more(payload: Any, page_no: int) -> bool:
    body = _unwrap_payload(payload)
    candidates = [payload, body] if isinstance(payload, dict) else [body]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for key in ("hasMore", "has_more"):
            if key in item:
                return bool(item[key])
        total = item.get("total")
        page_size = item.get("pageSize") or item.get("page_size")
        if isinstance(total, int) and isinstance(page_size, int):
            return page_no * page_size < total
    return False


def _normalize_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return value


def _sheet_name(raw: str, used: set[str]) -> str:
    name = "".join(ch if ch not in r'[]:*?/\\' else "_" for ch in raw).strip() or "data"
    name = name[:31]
    candidate = name
    idx = 2
    while candidate in used:
        suffix = f"_{idx}"
        candidate = f"{name[:31 - len(suffix)]}{suffix}"
        idx += 1
    used.add(candidate)
    return candidate


def _write_xlsx(path: Path, datasets: dict[str, list[dict[str, Any]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    used_sheet_names: set[str] = set()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for dataset_name in sorted(datasets):
            records = datasets[dataset_name]
            rows = [{key: _normalize_cell(value) for key, value in row.items()} for row in records]
            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame([{"_empty": ""}])
            df.to_excel(writer, sheet_name=_sheet_name(dataset_name, used_sheet_names), index=False)


def write_snapshot_from_pages(
    state_task_dir: Path,
    tmp_task_dir: Path,
    pages: list[dict[str, Any]],
    *,
    start: str,
    end: str,
    endpoint: str,
    page_size: int,
    truncated: bool,
    requested_window: dict[str, str] | None = None,
    time_range_type: str = DEFAULT_TIME_RANGE_TYPE,
) -> dict[str, Any]:
    state_task_dir.mkdir(parents=True, exist_ok=True)
    tmp_task_dir.mkdir(parents=True, exist_ok=True)
    output_task_dir = OUTPUTS_DIR / state_task_dir.name

    datasets: dict[str, list[dict[str, Any]]] = {}
    for idx, page in enumerate(pages, start=1):
        _write_json(tmp_task_dir / f"raw_page_{idx:03d}.json", page)
        page_datasets = extract_datasets(page)
        for name, records in page_datasets.items():
            datasets.setdefault(name, []).extend(records)

    if not datasets:
        datasets = {"data": []}

    row_counts = {name: len(records) for name, records in sorted(datasets.items())}
    fetch_window = {"start": start, "end": end}
    requested = requested_window or {"start": start, "end": end, "timezone": DEFAULT_USER_TIMEZONE}
    _write_xlsx(state_task_dir / "datasource.xlsx", datasets)
    manifest = {
        "status": "ready",
        "source_type": SOURCE_TYPE,
        "source_contract": SOURCE_CONTRACT,
        "task_id": state_task_dir.name,
        "env": SOLVEA_ENV,
        "tenant_id": SOLVEA_TENANT_ID,
        "project_id": SOLVEA_PROJECT_ID,
        "requested_window": requested,
        "fetch_window": fetch_window,
        "analysis_window": requested,
        "time_range_type": time_range_type,
        "endpoint": endpoint,
        "page_size": page_size,
        "page_count": len(pages),
        "row_counts": row_counts,
        "truncated": truncated,
        "files": _fixed_files(),
        "tmp_raw_pages": str(tmp_task_dir),
        "generated_at": _now_iso(),
    }
    _write_json(state_task_dir / "manifest.json", manifest)
    _write_latest_state(
        state_task_dir,
        "ready",
        requested_window=requested,
        fetch_window=fetch_window,
        time_range_type=time_range_type,
        tmp_task_dir=tmp_task_dir,
    )
    return {
        "ok": True,
        "source_type": SOURCE_TYPE,
        "task_id": state_task_dir.name,
        "task_dir": str(state_task_dir),
        "state_task_dir": str(state_task_dir),
        "output_task_dir": str(output_task_dir),
        "tmp_task_dir": str(tmp_task_dir),
        "datasource": str(state_task_dir / "datasource.xlsx"),
        "manifest": str(state_task_dir / "manifest.json"),
        "row_counts": row_counts,
        "truncated": truncated,
    }


def _request_page(
    client: httpx.Client,
    endpoint: str,
    token: str,
    cookie_name: str,
    start: str,
    end: str,
    page: int,
    page_size: int,
    time_range_type: str = "",
) -> dict[str, Any]:
    origin = _base_origin(endpoint)
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": origin,
        "Referer": f"{origin}/botdesk",
    }
    if token:
        headers["Cookie"] = f"{cookie_name}={token}"
    request_payload = {
        "startTime": start,
        "endTime": end,
        "page": page,
        "pageSize": page_size,
    }
    if time_range_type:
        request_payload["timeRangeType"] = time_range_type
    response = client.post(endpoint, json=request_payload, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Shulex Desk source endpoint must return a JSON object")
    return payload


def fetch_pages(
    config: SourceConfig,
    *,
    start: str,
    end: str,
    page_size: int,
    max_pages: int,
    max_rows: int,
    time_range_type: str = "",
) -> tuple[list[dict[str, Any]], bool]:
    page_size = validate_page_size(page_size)
    pages: list[dict[str, Any]] = []
    total_rows = 0
    truncated = False
    with httpx.Client(timeout=60.0) as client:
        for page_no in range(1, max_pages + 1):
            payload = _request_page(
                client,
                config.endpoint,
                config.token,
                config.cookie_name,
                start,
                end,
                page_no,
                page_size,
                time_range_type,
            )
            pages.append(payload)
            page_datasets = extract_datasets(payload)
            total_rows += sum(len(records) for records in page_datasets.values())
            if total_rows >= max_rows:
                truncated = True
                break
            if not _has_more(payload, page_no):
                break
        else:
            truncated = True
    return pages, truncated


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch solvea-desk data sources into datasource.xlsx")
    parser.add_argument("--start", required=True, help="Inclusive start time, ISO-8601 preferred")
    parser.add_argument("--end", required=True, help="Inclusive end date at 00:00:00, ISO-8601 preferred")
    parser.add_argument(
        "--timezone",
        default=DEFAULT_USER_TIMEZONE,
        choices=[DEFAULT_USER_TIMEZONE],
        help="Business timezone; solvea-desk currently only supports Asia/Shanghai",
    )
    parser.add_argument(
        "--time-range-type",
        default="",
        choices=[CREATED_AT],
        help="Only set to created_at when the user explicitly requests ticket creation-date filtering",
    )
    parser.add_argument("--task-id", default="", help="Optional task id; defaults to timestamp")
    parser.add_argument(
        "--page-size",
        type=validate_page_size,
        default=DEFAULT_PAGE_SIZE,
        help=f"Rows per page, between 1 and {MAX_PAGE_SIZE}",
    )
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    args = parser.parse_args()

    task_id = args.task_id.strip() or timestamp()
    state_task_dir = STATE_DIR / task_id
    tmp_task_dir = TMP_DIR / task_id

    config = resolve_source_config()
    time_window = normalize_time_window(args.start, args.end, timezone_name=args.timezone)
    effective_time_range_type = args.time_range_type or DEFAULT_TIME_RANGE_TYPE
    if not config.token:
        result = write_pending_snapshot(
            state_task_dir,
            start=time_window.fetch_window["start"],
            end=time_window.fetch_window["end"],
            reason="missing Solvea token for solvea-desk source",
            requested_window=time_window.requested,
            time_range_type=effective_time_range_type,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    pages, truncated = fetch_pages(
        config,
        start=time_window.fetch_window["start"],
        end=time_window.fetch_window["end"],
        page_size=args.page_size,
        max_pages=args.max_pages,
        max_rows=args.max_rows,
        time_range_type=args.time_range_type,
    )
    result = write_snapshot_from_pages(
        state_task_dir,
        tmp_task_dir,
        pages,
        start=time_window.fetch_window["start"],
        end=time_window.fetch_window["end"],
        endpoint=config.endpoint,
        page_size=args.page_size,
        truncated=truncated,
        requested_window=time_window.requested,
        time_range_type=effective_time_range_type,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not truncated else 3


if __name__ == "__main__":
    raise SystemExit(main())
