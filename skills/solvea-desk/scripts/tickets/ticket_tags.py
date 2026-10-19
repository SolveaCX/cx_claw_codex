#!/usr/bin/env python3
"""Query and safely mutate Tars ticket tags."""

import os
import sys
sys.path.insert(0, os.path.join(os.environ["SOLVEA_LIB_DIR"], "skill-runtime"))
from bootstrap import SOLVEA_ENV  # noqa: E402,F401

import argparse
import json
from pathlib import Path
from typing import Any

import httpx

from desk_api import DeskApiConfig, request_json, resolve_desk_api_config


TAG_LIST_PATH = "/api_v2/tars/api/tags/list"
TICKET_TAGS_PATH = "/api_v2/tars/api/tags/ticket_tags"
BATCH_TICKET_TAGS_PATH = "/api_v2/tars/api/tags/new/getTags"
TAG_SEARCH_PATH = "/api_v2/tars/api/tags/new/find"
BIND_TAGS_PATH = "/api_v2/tars/api/tags/manual/binding"
UNBIND_TAGS_PATH = "/api_v2/tars/api/tags/manual/unbinding"


class TagVerificationError(RuntimeError):
    def __init__(
        self,
        *,
        before: dict[str, Any],
        requested: dict[str, Any],
        after: dict[str, Any],
        operation: str,
    ) -> None:
        super().__init__(f"{operation} tag verification failed")
        self.evidence = {
            "operation": operation,
            "before": before,
            "requested": requested,
            "after": after,
        }


def list_tags(client: httpx.Client, config: DeskApiConfig) -> Any:
    return request_json(client, config, "GET", TAG_LIST_PATH).get("data", [])


def get_ticket_tags(
    client: httpx.Client,
    config: DeskApiConfig,
    ticket_number: str,
) -> dict[str, Any]:
    normalized = ticket_number.strip()
    if not normalized:
        raise ValueError("ticket number cannot be empty")
    data = request_json(
        client,
        config,
        "GET",
        TICKET_TAGS_PATH,
        params={"ticketNum": normalized},
    ).get("data", {})
    if not isinstance(data, dict):
        raise ValueError("ticket tag response data must be an object")
    return data


def batch_get_ticket_tags(
    client: httpx.Client,
    config: DeskApiConfig,
    ticket_ids: list[int],
) -> list[Any]:
    if not ticket_ids or any(
        isinstance(value, bool) or not isinstance(value, int) for value in ticket_ids
    ):
        raise ValueError("ticketIdList must be a non-empty integer list")
    data = request_json(
        client,
        config,
        "POST",
        BATCH_TICKET_TAGS_PATH,
        json_body={"ticketIdList": ticket_ids},
    ).get("data", [])
    if not isinstance(data, list):
        raise ValueError("batch ticket tag response data must be a list")
    return data


def search_tags(
    client: httpx.Client,
    config: DeskApiConfig,
    name: str,
) -> list[Any]:
    normalized = name.strip()
    if not normalized:
        raise ValueError("tag name cannot be empty")
    data = request_json(
        client,
        config,
        "GET",
        TAG_SEARCH_PATH,
        params={"tagName": normalized},
    ).get("data", [])
    if not isinstance(data, list):
        raise ValueError("tag search response data must be a list")
    return data


def load_ticket_ids_file(path: str | Path) -> list[int]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    ticket_ids = payload.get("ticketIdList") if isinstance(payload, dict) else None
    if not isinstance(ticket_ids, list) or not ticket_ids or any(
        isinstance(value, bool) or not isinstance(value, int) for value in ticket_ids
    ):
        raise ValueError("ticketIdList must be a non-empty integer list")
    return ticket_ids


def load_tags_file(path: str | Path) -> list[dict[str, int | str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    tags = payload.get("tags") if isinstance(payload, dict) else None
    return _normalize_tags(tags)


def _normalize_tags(tags: Any) -> list[dict[str, int | str]]:
    if not isinstance(tags, list) or not tags:
        raise ValueError("tags must be a non-empty list")
    normalized = []
    for tag in tags:
        if (
            not isinstance(tag, dict)
            or isinstance(tag.get("id"), bool)
            or not isinstance(tag.get("id"), int)
        ):
            raise ValueError("each tag id must be an integer")
        if not isinstance(tag.get("name"), str) or not tag["name"].strip():
            raise ValueError("each tag name must be non-empty")
        normalized.append({"id": tag["id"], "name": tag["name"].strip()})
    return normalized


def _user_tag_ids(tag_state: dict[str, Any]) -> set[int]:
    values = tag_state.get("userTags", [])
    if not isinstance(values, list):
        return set()
    result = set()
    for tag in values:
        if not isinstance(tag, dict) or isinstance(tag.get("id"), bool):
            continue
        try:
            result.add(int(tag["id"]))
        except (KeyError, TypeError, ValueError):
            continue
    return result


def change_tags(
    client: httpx.Client,
    config: DeskApiConfig,
    *,
    operation: str,
    ticket_number: str,
    tags: list[dict[str, int | str]],
    confirmed: bool,
) -> dict[str, Any]:
    if operation not in {"bind", "unbind"}:
        raise ValueError("operation must be bind or unbind")
    normalized_ticket_number = ticket_number.strip()
    if not normalized_ticket_number:
        raise ValueError("ticket number cannot be empty")
    normalized_tags = _normalize_tags(tags)
    before = get_ticket_tags(client, config, normalized_ticket_number)
    requested = {"ticketNum": normalized_ticket_number, "tags": normalized_tags}
    if not confirmed:
        return {
            "ok": False,
            "status": "confirmation_required",
            "operation": operation,
            "before": before,
            "requested": requested,
        }

    path = BIND_TAGS_PATH if operation == "bind" else UNBIND_TAGS_PATH
    server_payload = request_json(client, config, "POST", path, json_body=requested)
    after = get_ticket_tags(client, config, normalized_ticket_number)
    requested_ids = {int(tag["id"]) for tag in normalized_tags}
    after_user_ids = _user_tag_ids(after)
    verified = (
        requested_ids <= after_user_ids
        if operation == "bind"
        else requested_ids.isdisjoint(after_user_ids)
    )
    if not verified:
        raise TagVerificationError(
            before=before,
            requested=requested,
            after=after,
            operation=operation,
        )
    return {
        "ok": True,
        "operation": operation,
        "verified": True,
        "before": before,
        "requested": requested,
        "after": after,
        "server_result": server_payload.get("data"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query and manage Shulex Desk ticket tags")
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("list-tags", help="Return the complete Tars tag tree")

    get_parser = subparsers.add_parser("get-ticket-tags", help="Get one ticket's tags")
    get_parser.add_argument("--ticket-number", required=True)

    batch_parser = subparsers.add_parser(
        "batch-get-ticket-tags", help="Get tags for internal ticket IDs"
    )
    batch_parser.add_argument("--ticket-ids-file", required=True)

    search_parser = subparsers.add_parser("search-tags", help="Search tag paths by node name")
    search_parser.add_argument("--name", required=True)

    for operation in ("bind-tags", "unbind-tags"):
        write_parser = subparsers.add_parser(
            operation,
            help="Bind tags to a ticket" if operation == "bind-tags" else "Unbind tags from a ticket",
        )
        write_parser.add_argument("--ticket-number", required=True)
        write_parser.add_argument("--tags-file", required=True)
        write_parser.add_argument(
            "--confirm",
            action="store_true",
            help="Send the write request after the user explicitly confirms the preview",
        )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = resolve_desk_api_config()
    if not config.token:
        print(json.dumps({
            "ok": False,
            "operation": args.operation,
            "error": "desk_runtime_not_configured",
            "message": "Check SOLVEA_ENV and the corresponding Solvea token environment variable.",
        }, ensure_ascii=False, indent=2))
        return 2

    try:
        with httpx.Client(timeout=60.0) as client:
            if args.operation == "list-tags":
                data = list_tags(client, config)
            elif args.operation == "get-ticket-tags":
                data = get_ticket_tags(client, config, args.ticket_number)
            elif args.operation == "batch-get-ticket-tags":
                data = batch_get_ticket_tags(
                    client, config, load_ticket_ids_file(args.ticket_ids_file)
                )
            elif args.operation == "search-tags":
                data = search_tags(client, config, args.name)
            else:
                data = change_tags(
                    client,
                    config,
                    operation="bind" if args.operation == "bind-tags" else "unbind",
                    ticket_number=args.ticket_number,
                    tags=load_tags_file(args.tags_file),
                    confirmed=args.confirm,
                )
    except TagVerificationError as exc:
        print(json.dumps({
            "ok": False,
            "operation": args.operation,
            "error": type(exc).__name__,
            "message": str(exc),
            **exc.evidence,
        }, ensure_ascii=False, indent=2))
        return 3
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, httpx.HTTPError) as exc:
        print(json.dumps({
            "ok": False,
            "operation": args.operation,
            "error": type(exc).__name__,
            "message": str(exc),
        }, ensure_ascii=False, indent=2))
        return 1

    result = data if args.operation in {"bind-tags", "unbind-tags"} else {
        "ok": True,
        "operation": args.operation,
        "data": data,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
