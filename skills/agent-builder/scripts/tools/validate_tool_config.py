#!/usr/bin/env python3
"""Validate a local Agent Builder HTTP tool JSON payload."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


PARAMETER_TYPES = {"string", "integer", "number", "date", "boolean", "array", "object"}
API_TYPES_BY_PARAMETER_TYPE = {
    "string": {"TEXT"},
    "integer": {"NUMBER"},
    "number": {"NUMBER"},
    "date": {"DATE_TO_NOW", "NOW_TO_DATE"},
    "boolean": {"BOOLEAN"},
    "array": {"ARRAY_SIZE"},
    "object": set(),
}
RELATIONS_BY_API_TYPE = {
    "TEXT": {"CONTAIN", "NOT_CONTAIN", "IS_EMPTY", "NOT_EMPTY", "EQUAL", "NOT_EQUAL"},
    "NUMBER": {
        "GREATER_THAN", "GREATER_THAN_OR_EQUAL", "LESS_THAN", "LESS_THAN_OR_EQUAL",
        "BETWEEN", "EQUAL", "NOT_EQUAL", "IS_EMPTY", "NOT_EMPTY",
    },
    "DATE_TO_NOW": {
        "GREATER_THAN", "GREATER_THAN_OR_EQUAL", "LESS_THAN", "LESS_THAN_OR_EQUAL",
        "BETWEEN", "EQUAL", "NOT_EQUAL", "IS_EMPTY", "NOT_EMPTY",
    },
    "NOW_TO_DATE": {
        "GREATER_THAN", "GREATER_THAN_OR_EQUAL", "LESS_THAN", "LESS_THAN_OR_EQUAL",
        "BETWEEN", "EQUAL", "NOT_EQUAL", "IS_EMPTY", "NOT_EMPTY",
    },
    "ARRAY_SIZE": {
        "GREATER_THAN", "GREATER_THAN_OR_EQUAL", "LESS_THAN", "LESS_THAN_OR_EQUAL",
        "BETWEEN", "EQUAL", "NOT_EQUAL", "IS_EMPTY", "NOT_EMPTY",
    },
    "BOOLEAN": {"EQUAL", "NOT_EQUAL", "IS_EMPTY", "NOT_EMPTY"},
}


def reject_non_finite_json_number(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value} is not allowed")


def parse_finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        reject_non_finite_json_number(value)
    return parsed


def is_finite_number_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, str) and value.strip():
        try:
            return math.isfinite(float(value.strip()))
        except ValueError:
            return False
    return False


def validate_tool_config(data: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    def add_error(path: str, code: str, message: str) -> None:
        errors.append({"path": path, "code": code, "message": message})

    if not isinstance(data, dict):
        add_error("$", "invalid_tool_config", "tool config must be a JSON object")
        return {"valid": False, "errors": errors}

    if data.get("type") != "EXTERNAL_HTTP_CALL":
        add_error("type", "invalid_tool_type", "type must be EXTERNAL_HTTP_CALL")

    meta = data.get("meta")
    if not isinstance(meta, dict):
        add_error("meta", "missing_meta", "meta must be an object")
        meta = {}
    external = meta.get("externalHttpCallConfig")
    if not isinstance(external, dict):
        add_error(
            "meta.externalHttpCallConfig",
            "missing_external_http_call_config",
            "externalHttpCallConfig must be an object",
        )
        external = {}

    category = meta.get("category")
    is_manual = category == "MANUAL" or (category is None and data.get("source") == "MANUAL")
    if is_manual and not str(external.get("url") or "").strip():
        add_error(
            "meta.externalHttpCallConfig.url",
            "missing_manual_url",
            "MANUAL tools require a non-empty URL",
        )
    if meta.get("category") == "EXCEL" and not str(meta.get("fileName") or "").strip():
        add_error("meta.fileName", "missing_excel_file_name", "EXCEL tools require fileName")

    headers = external.get("headerParams", [])
    if not isinstance(headers, list):
        add_error(
            "meta.externalHttpCallConfig.headerParams",
            "invalid_headers",
            "headerParams must be an array",
        )
    else:
        for index, header in enumerate(headers):
            header_path = f"meta.externalHttpCallConfig.headerParams[{index}]"
            if not isinstance(header, dict):
                add_error(header_path, "invalid_header", "header must be an object")
                continue
            name = header.get("name")
            if not isinstance(name, str) or not name.strip():
                add_error(
                    f"{header_path}.name",
                    "invalid_header_name",
                    "header name must not be empty",
                )

    parameter_count = {"request": 0, "response": 0}
    response_paths: dict[str, str] = {}

    def validate_items(
        items: Any,
        schema_path: str,
        kind: str,
        api_parent: tuple[str, ...] = (),
        include_api_name: bool = True,
    ) -> None:
        if not isinstance(items, list):
            add_error(schema_path, "invalid_parameter_items", "items must be an array")
            return

        names: set[str] = set()
        for index, item in enumerate(items):
            item_path = f"{schema_path}[{index}]"
            if not isinstance(item, dict):
                add_error(item_path, "invalid_parameter", "parameter must be an object")
                continue
            parameter_count[kind] += 1
            name = item.get("name")
            clean_name = name.strip() if isinstance(name, str) else ""
            if not clean_name:
                add_error(f"{item_path}.name", "invalid_parameter_name", "parameter name must not be empty")
            elif "." in clean_name:
                add_error(f"{item_path}.name", "invalid_parameter_name", "parameter name must not contain dots")
            if clean_name in names:
                add_error(
                    f"{item_path}.name",
                    "duplicate_parameter_name",
                    f"duplicate parameter name {clean_name!r} in the same scope",
                )
            elif clean_name:
                names.add(clean_name)

            parameter_type = item.get("type")
            valid_parameter_type = isinstance(parameter_type, str) and parameter_type in PARAMETER_TYPES
            if not valid_parameter_type:
                add_error(
                    f"{item_path}.type",
                    "invalid_parameter_type",
                    f"type must be one of {sorted(PARAMETER_TYPES)}",
                )

            api_path = api_parent + ((clean_name,) if clean_name and include_api_name else ())
            if kind == "response" and clean_name and include_api_name and valid_parameter_type:
                response_paths[".".join(api_path)] = parameter_type

            if parameter_type == "array":
                child = item.get("listSubItem")
                if not isinstance(child, dict):
                    add_error(f"{item_path}.listSubItem", "missing_list_sub_item", "array requires listSubItem")
                else:
                    validate_items([child], f"{item_path}.listSubItem", kind, api_path, False)
            elif parameter_type == "object":
                children = item.get("objectItems")
                if not isinstance(children, list) or not children:
                    add_error(f"{item_path}.objectItems", "missing_object_items", "object requires non-empty objectItems")
                else:
                    validate_items(children, f"{item_path}.objectItems", kind, api_path)

    for kind, key in (("request", "requestParam"), ("response", "responseParam")):
        container_path = f"meta.externalHttpCallConfig.{key}"
        container = external.get(key, {})
        if not isinstance(container, dict):
            add_error(container_path, "invalid_parameter_config", f"{key} must be an object")
            continue
        validate_items(container.get("items", []), f"{container_path}.items", kind)

    statuses = external.get("actionStatuses", [])
    if not isinstance(statuses, list):
        add_error(
            "meta.externalHttpCallConfig.actionStatuses",
            "invalid_action_statuses",
            "actionStatuses must be an array",
        )
        statuses = []

    status_names: set[str] = set()
    for status_index, status in enumerate(statuses):
        status_path = f"meta.externalHttpCallConfig.actionStatuses[{status_index}]"
        if not isinstance(status, dict):
            add_error(status_path, "invalid_action_status", "action status must be an object")
            continue
        name = status.get("name")
        clean_name = name.strip() if isinstance(name, str) else ""
        if not clean_name:
            add_error(f"{status_path}.name", "invalid_status_name", "action status name must not be empty")
        elif clean_name in status_names:
            add_error(f"{status_path}.name", "duplicate_status_name", "action status names must be unique")
        else:
            status_names.add(clean_name)

        condition = status.get("condition")
        is_default = condition == {} or condition == {"or": []}
        if status_index == len(statuses) - 1:
            if not is_default:
                add_error(
                    f"{status_path}.condition",
                    "invalid_default_status",
                    "the last action status must have condition: {}",
                )
        elif is_default:
            add_error(
                f"{status_path}.condition",
                "invalid_default_status",
                "only the last action status may be the default",
            )

        if is_default:
            continue
        groups = condition.get("or") if isinstance(condition, dict) else None
        all_rules: list[tuple[dict[str, Any], str]] = []
        if isinstance(groups, list):
            for group_index, group in enumerate(groups):
                group_path = f"{status_path}.condition.or[{group_index}]"
                if not isinstance(group, dict):
                    add_error(group_path, "invalid_condition_group", "condition group must be an object")
                    continue
                rules = group.get("rules")
                if not isinstance(rules, list) or not rules:
                    add_error(
                        f"{group_path}.rules",
                        "missing_group_rules",
                        "each condition group requires a non-empty rules array",
                    )
                    continue
                for rule_index, rule in enumerate(rules):
                    rule_path = f"{group_path}.rules[{rule_index}]"
                    if isinstance(rule, dict):
                        all_rules.append((rule, rule_path))
                    else:
                        add_error(rule_path, "invalid_status_rule", "rule must be an object")
        if not all_rules:
            add_error(
                f"{status_path}.condition",
                "missing_status_rules",
                "non-default action statuses require at least one rule",
            )
            continue

        for rule, rule_path in all_rules:
            if rule.get("type") != "GENERIC":
                add_error(f"{rule_path}.type", "invalid_rule_type", "rule type must be GENERIC")
            api_name = rule.get("apiName")
            if not isinstance(api_name, str) or not api_name.strip():
                add_error(f"{rule_path}.apiName", "missing_api_name", "apiName must not be empty")
                response_type = None
            else:
                response_type = response_paths.get(api_name)
                if response_type is None:
                    add_error(
                        f"{rule_path}.apiName",
                        "unknown_response_path",
                        f"apiName {api_name!r} is not an exact response parameter path",
                    )
                elif response_type == "object":
                    add_error(
                        f"{rule_path}.apiName",
                        "object_status_not_supported",
                        "object response parameters cannot be used in action status rules",
                    )

            api_type = rule.get("apiType")
            if api_type is None or api_type == "":
                add_error(f"{rule_path}.apiType", "missing_api_type", "apiType is required")
                valid_api_type = None
            elif not isinstance(api_type, str) or api_type not in RELATIONS_BY_API_TYPE:
                add_error(
                    f"{rule_path}.apiType",
                    "invalid_api_type",
                    f"apiType must be one of {sorted(RELATIONS_BY_API_TYPE)}",
                )
                valid_api_type = None
            else:
                valid_api_type = api_type
            if (
                response_type
                and valid_api_type is not None
                and valid_api_type not in API_TYPES_BY_PARAMETER_TYPE.get(response_type, set())
            ):
                add_error(
                    f"{rule_path}.apiType",
                    "api_type_mismatch",
                    f"apiType {api_type!r} is incompatible with response type {response_type!r}",
                )

            relation = rule.get("relation")
            valid_relation = relation if isinstance(relation, str) else None
            if valid_relation not in RELATIONS_BY_API_TYPE.get(valid_api_type, set()):
                add_error(
                    f"{rule_path}.relation",
                    "invalid_relation",
                    f"relation {relation!r} is not supported for apiType {api_type!r}",
                )

            values = rule.get("values")
            values_valid = isinstance(values, list)
            if values_valid and valid_relation in {"IS_EMPTY", "NOT_EMPTY"}:
                values_valid = values == []
            elif values_valid and valid_relation == "BETWEEN":
                values_valid = len(values) == 2
            elif values_valid and valid_api_type == "TEXT" and valid_relation in {"CONTAIN", "NOT_CONTAIN"}:
                values_valid = len(values) >= 1
            elif values_valid:
                values_valid = len(values) == 1
            if values_valid and valid_api_type == "BOOLEAN" and valid_relation in {"EQUAL", "NOT_EQUAL"}:
                boolean_value = values[0]
                values_valid = isinstance(boolean_value, bool) or (
                    isinstance(boolean_value, str)
                    and boolean_value.strip().lower() in {"true", "false"}
                )
            if values_valid and valid_api_type == "TEXT" and values:
                values_valid = all(isinstance(value, str) for value in values)
            if values_valid and valid_api_type in {"NUMBER", "DATE_TO_NOW", "NOW_TO_DATE", "ARRAY_SIZE"} and values:
                values_valid = all(is_finite_number_value(value) for value in values)
            if not values_valid:
                add_error(
                    f"{rule_path}.values",
                    "invalid_rule_values",
                    "values has an invalid count or value type for the selected relation and apiType",
                )

    if errors:
        return {"valid": False, "errors": errors}
    return {
        "valid": True,
        "request_parameter_count": parameter_count["request"],
        "response_parameter_count": parameter_count["response"],
        "action_status_count": len(statuses),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an Agent Builder tool JSON payload")
    parser.add_argument("--data-file", required=True, help="Path to a local JSON file")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    try:
        with Path(args.data_file).open(encoding="utf-8") as file:
            data = json.load(
                file,
                parse_constant=reject_non_finite_json_number,
                parse_float=parse_finite_json_float,
            )
        output = validate_tool_config(data)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        output = {
            "valid": False,
            "errors": [{"path": "$", "code": "invalid_data_file", "message": str(exc)}],
        }
    print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if output["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
