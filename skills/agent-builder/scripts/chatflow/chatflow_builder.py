"""
CHAT_FLOW graph builder for Solvea agents.

Provides node/edge construction functions with built-in constraint enforcement
(ASCII titles, prompt/displayPrompt split, structural validation). Agents should
normally use the CLI: write source JSON, compile it to a full chatFlowGraph,
validate the graph file, then deploy/update/publish the same graph file.

Direct CLI:
    python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py --help --pretty
    python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py inspect --agent-name My_Agent
    python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py compile --source-file source.json --graph-file graph.json
    python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py validate --graph-file graph.json
    python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py deploy --agent-name My_Agent --graph-file graph.json
    python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py update --agent-id 12345 --graph-file patch.json
    python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py publish --agent-id 12345 --graph-file patch.json
"""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def uid():
    """Generate a random UUID string (public API)."""
    return str(uuid.uuid4())

# Keep _uid as alias for internal/backward compatibility
_uid = uid


# ---------------------------------------------------------------------------
# variableSelector builders
# ---------------------------------------------------------------------------

def var_tool_output(tool_node_or_id, *field_path):
    """
    TOOL output variable selector.

    Format: ["TOOL", node_id, field1, field2, ...]
    Example: var_tool_output(n2, "orderType") -> ["TOOL", "<id>", "orderType"]
             var_tool_output(n2, "consigneeInfo", "country") -> ["TOOL", "<id>", "consigneeInfo", "country"]

    NOTE: Do NOT add an "output" layer — field path starts directly at the 3rd element.
    """
    node_id = tool_node_or_id["id"] if isinstance(tool_node_or_id, dict) else tool_node_or_id
    return ["TOOL", node_id, *field_path]


def var_tool_status(tool_node_or_id):
    """
    TOOL action status variable selector.

    Format: ["TOOL", node_id, "ACTION_STATUS_NAME"]
    """
    node_id = tool_node_or_id["id"] if isinstance(tool_node_or_id, dict) else tool_node_or_id
    return ["TOOL", node_id, "ACTION_STATUS_NAME"]


def var_system(category, field_path):
    """
    System / variable-system field selector.

    Format: ["SYSTEM", category, *field_path]
    Example: var_system("Order", [3248, 3249])
    """
    path = field_path if isinstance(field_path, list) else [field_path]
    return ["SYSTEM", category, *path]


def var_node(node_or_id):
    """
    Node reference variable selector.

    Format: ["NODE", node_id]
    """
    node_id = node_or_id["id"] if isinstance(node_or_id, dict) else node_or_id
    return ["NODE", node_id]


def var_extract(node_or_id, variable_id):
    """
    Variable extract reference selector.

    Format: ["EXTRACT", node_id, variable_id]
    """
    node_id = node_or_id["id"] if isinstance(node_or_id, dict) else node_or_id
    return ["EXTRACT", node_id, variable_id]


def var_code_output(code_node_or_id, field_name):
    """
    CODE output variable selector.

    Format: ["CODE", node_id, field_name]
    """
    node_id = code_node_or_id["id"] if isinstance(code_node_or_id, dict) else code_node_or_id
    return ["CODE", node_id, field_name]


def _normalize_id_list(items, field_name):
    normalized = []
    for idx, item in enumerate(items or []):
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"{field_name}[{idx}] must be an integer id, got {item!r}")
        normalized.append(item)
    return normalized


def _validate_title(title):
    """Allow Chinese/Unicode letters, ASCII alnum, underscore, hyphen."""
    cleaned = re.sub(r'[^\w\u4e00-\u9fff-]', '_', title)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    if not cleaned:
        # All non-ASCII chars (e.g. pure Chinese) → generate a fallback
        cleaned = f"Node_{_uid()[:8]}"
        print(f"  [auto-fix] title '{title}' -> '{cleaned}' (original had no ASCII chars)")
    elif cleaned != title:
        print(f"  [auto-fix] title '{title}' -> '{cleaned}'")
    return cleaned


def _short_id(node_id):
    """Return first 8 chars of a node ID (handles long UUIDs)."""
    return node_id[:8]


# ---------------------------------------------------------------------------
# Prompt builder — layered constraints
# ---------------------------------------------------------------------------

BASE_CONSTRAINTS = [
    "NEVER guide customers to seek human support, contact retailers, "
    "contact our support team, or transfer to a human agent.",

    "NEVER repeat issues the customer has already described or include "
    "content irrelevant to their question — this appears mechanical "
    "rather than empathetic.",

    "NEVER restate the customer's problem as a form of acknowledgment "
    "— it feels robotic, not comforting. Move directly to providing "
    "a solution or next step.",

    "ALWAYS reply in the same language the customer used in their message.",

    "NEVER disclose internal costs, supplier details, profit margins, "
    "or internal processes.",

    "NEVER make decisions on behalf of the customer without their "
    "explicit consent (e.g., canceling orders, changing shipping address).",
]

KNOWLEDGE_BASE_CONSTRAINTS = [
    "If the available knowledge does not appear relevant or sufficient "
    "to resolve the customer's issue, escalate to a human agent "
    "immediately rather than providing a potentially incorrect answer.",
]

AFTER_SALES_CONSTRAINTS = [
    "NEVER guide customers to contact Amazon, eBay, or any third-party "
    "platform to handle returns or exchanges.",

    "NEVER instruct customers to follow warranty terms or return policy "
    "procedures on their own.",
]

COMPENSATION_CONSTRAINTS = [
    "NEVER promise refunds, compensation, replacements, or store credit "
    "unless explicitly authorized in this flow.",
]

SCENARIO_MAP = {
    "knowledge_base": KNOWLEDGE_BASE_CONSTRAINTS,
    "after_sales": AFTER_SALES_CONSTRAINTS,
    "compensation": COMPENSATION_CONSTRAINTS,
}

_AFTER_SALES_KEYWORDS = {
    "return", "refund", "exchange", "warranty", "replacement",
    "damage", "defect", "broken", "missing", "lost",
}

_COMPENSATION_KEYWORDS = {
    "refund", "compensation", "discount", "coupon", "credit",
    "reimburse", "price adjustment",
}


def _infer_scenarios(title, task, key_info, kb_dirs):
    """Infer applicable scenario tags from node content."""
    scenarios = set()
    text = f"{title} {task} {key_info}".lower()

    if kb_dirs:
        scenarios.add("knowledge_base")

    if any(kw in text for kw in _AFTER_SALES_KEYWORDS):
        scenarios.add("after_sales")

    if any(kw in text for kw in _COMPENSATION_KEYWORDS):
        scenarios.add("compensation")

    return scenarios


def build_prompt(role, task, key_info, guidelines, brand_name,
                 scenarios=None, kb_dirs=None, extra_constraints=None):
    """
    Assemble a four-segment prompt with auto-generated layered constraints.

    All output is in English.

    Parameters
    ----------
    role : str
        Role description (e.g. "specialized in logistics and order tracking").
    task : str
        Task description for this specific node.
    key_info : str
        Key information relevant to the node's function.
    guidelines : str
        Behavioral guidelines for the AI agent.
    brand_name : str
        Brand name injected into the Role segment.
    scenarios : list[str] | None
        Manual scenario override.  Replaces auto-inferred scenarios except
        ``knowledge_base`` which is always added when *kb_dirs* is non-empty.
    kb_dirs : list[str] | None
        Knowledge base directory IDs.  Non-empty triggers ``knowledge_base``.
    extra_constraints : list[str] | None
        Additional custom constraints appended after all layers.
    """
    # --- resolve scenarios ---
    if scenarios is not None:
        active = set(scenarios)
    else:
        active = _infer_scenarios("", task, key_info, kb_dirs)

    # knowledge_base is always forced when kb_dirs present
    if kb_dirs:
        active.add("knowledge_base")

    # --- build constraints list ---
    constraints = list(BASE_CONSTRAINTS)
    for tag in sorted(active):
        constraints.extend(SCENARIO_MAP.get(tag, []))
    if extra_constraints:
        constraints.extend(extra_constraints)

    restrictions = "\n".join(f"- {c}" for c in constraints)

    return (
        f"## Role\n"
        f"You are a professional customer service representative "
        f"officially representing {brand_name}. {role}\n\n"
        f"## Task\n{task}\n\n"
        f"## Key Information\n{key_info}\n\n"
        f"## Guidelines\n{guidelines}\n\n"
        f"## Restrictions (NEVER violate)\n{restrictions}"
    )


# ---------------------------------------------------------------------------
# Node builders
# ---------------------------------------------------------------------------

def start_node(position=(0, 0)):
    """START node -- unique entry point of the graph."""
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {"category": "START"},
        "position": {"x": position[0], "y": position[1]},
    }


def finish_node(title="Finish", position=(0, 0)):
    """FINISH node -- shared terminal node; must have at least one inbound edge."""
    title = _validate_title(title)
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "FINISH",
            "title": title,
            "config": {},
        },
        "position": {"x": position[0], "y": position[1]},
    }


def reply_node(title, prompt="", reply_type="PROMPT", template_id=None,
               template_content=None, ai_field_ids=None, use_long_memory=False,
               disable_prev_node_results=False, position=(0, 0)):
    """REPLY node -- prompt, fixed template, or rendered variable template."""
    title = _validate_title(title)
    reply_type = (reply_type or "PROMPT").upper()
    if reply_type not in {"PROMPT", "TEMPLATE", "DYNAMIC_TEMPLATE"}:
        raise ValueError(f"unsupported REPLY type: {reply_type}")
    if reply_type == "TEMPLATE" and not template_id:
        raise ValueError("REPLY type TEMPLATE requires template_id")
    if reply_type == "DYNAMIC_TEMPLATE" and not isinstance(template_content, str):
        raise ValueError("REPLY type DYNAMIC_TEMPLATE requires template_content")
    if reply_type == "DYNAMIC_TEMPLATE" and not template_content.strip():
        raise ValueError("REPLY type DYNAMIC_TEMPLATE requires non-empty template_content")
    if reply_type != "PROMPT" and ai_field_ids:
        raise ValueError(f"REPLY type {reply_type} does not use ai_field_ids")
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "REPLY",
            "title": title,
            "config": {
                "replyContent": {
                    "type": reply_type,
                    "prompt": prompt if reply_type == "PROMPT" else None,
                    "templateId": template_id if reply_type == "TEMPLATE" else None,
                    "templateContent": template_content if reply_type == "DYNAMIC_TEMPLATE" else None,
                    "aiFieldIds": _normalize_id_list(ai_field_ids, "ai_field_ids") if reply_type == "PROMPT" else None,
                },
                "useLongMemory": bool(use_long_memory),
                "disablePrevNodeResult": bool(disable_prev_node_results),
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def agent_node(title, prompt, plugins=None, ai_field_ids=None,
               enable_kb=False, kb_dirs=None,
               knowledge_keyword_ids=None, knowledge_keyword_selector=None,
               max_rounds=10, max_rounds_exceeded_action="TRANSFER_TO_HUMAN",
               next_step=None, use_long_memory=False,
               disable_prev_node_results=False, position=(0, 0)):
    """
    AGENT V2 node -- LLM-powered reply with displayPrompt for UI and normalized runtime prompt.

    next_step example::

        [
            {"id": "uuid-1", "title": "resolved", "prompt": "User issue resolved"},
            {"id": "uuid-2", "title": "not_resolved", "prompt": "User still has issues"},
        ]

    When next_step is provided, sourceHandle for edges = next_step[].id.
    When next_step is None, sourceHandle = "SOURCE".

    NOTE: transferToHumans is always set to [] to avoid GraphDefParseError in
    complex graphs. Flow-internal next_steps are not human handoff branches;
    deterministic handoff should use a separate TRANSFER_TO_HUMAN node.
    """
    title = _validate_title(title)
    if isinstance(max_rounds_exceeded_action, dict):
        max_rounds_exceeded_action = max_rounds_exceeded_action.get("type")
    max_rounds_exceeded_action = str(
        max_rounds_exceeded_action or "TRANSFER_TO_HUMAN"
    ).upper()
    if max_rounds_exceeded_action not in {"FORCE_NEXT_STEP", "TRANSFER_TO_HUMAN"}:
        raise ValueError(
            "AGENT max_rounds_exceeded_action must be FORCE_NEXT_STEP or TRANSFER_TO_HUMAN"
        )
    prompt_blocks = _parse_library_blocks(prompt)
    used_plugins = list(dict.fromkeys(_normalize_id_list(plugins, "plugins")))
    for block in prompt_blocks:
        if block["type"] != "tool" or block["fields"]["tool"] == "template_reply":
            continue
        plugin_id = int(block["fields"]["id"])
        if plugin_id not in used_plugins:
            used_plugins.append(plugin_id)
    config = {
        "maxRounds": max_rounds,
        "maxRoundsExceededAction": {"type": max_rounds_exceeded_action},
        "useLongMemory": bool(use_long_memory),
        "disablePrevNodeResult": bool(disable_prev_node_results),
        "agentData": {
            "prompt": _format_chatflow_agent_prompt(prompt),
            "displayPrompt": prompt,
            "usedPlugins": used_plugins,
            "aiFieldIds": _normalize_id_list(ai_field_ids, "ai_field_ids"),
            "enableKnowledgeBase": enable_kb,
            "knowledgeDirectoryIds": kb_dirs or [],
            # Keep the legacy UI-only transferToHumans collection empty. The
            # executable transfer tool is bound through usedPlugins from the
            # Chatflow plugin catalog when compiling online.
            "transferToHumans": [],
        },
    }
    if knowledge_keyword_ids is not None:
        config["agentData"]["knowledgeKeywordIds"] = knowledge_keyword_ids
    if knowledge_keyword_selector is not None:
        config["agentData"]["knowledgeKeywordSelector"] = knowledge_keyword_selector
    if next_step:
        config["nextStep"] = next_step
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "AGENT",
            "version": 2,
            "title": title,
            "config": config,
        },
        "position": {"x": position[0], "y": position[1]},
    }


def llm_node(title, prompt, history_round_limit=0, use_long_memory=False,
             vision=None, structured_output=None, position=(0, 0)):
    """LLM node -- one-shot text, vision, or JSON-schema processing."""
    title = _validate_title(title)
    if not isinstance(history_round_limit, int) or isinstance(history_round_limit, bool) or history_round_limit < -1:
        raise ValueError("LLM history_round_limit must be -1, 0, or a positive integer")
    if vision is None:
        vision = {}
    if not isinstance(vision, dict):
        raise ValueError("LLM vision must be an object")
    vision_enabled = bool(vision.get("enabled", False))
    vision_detail = vision.get("detail", "auto")
    vision_media_selectors = vision.get("media_selectors", vision.get("mediaSelectors", []))
    if vision_detail not in {"auto", "low", "high"}:
        raise ValueError("LLM vision.detail must be auto, low, or high")
    if not isinstance(vision_media_selectors, list):
        raise ValueError("LLM vision.media_selectors must be a list")
    if vision_enabled and not vision_media_selectors:
        raise ValueError("LLM vision.enabled requires media_selectors")

    if structured_output is None:
        structured_output = {}
    if not isinstance(structured_output, dict):
        raise ValueError("LLM structured_output must be an object")
    structured_output_enabled = bool(structured_output.get("enabled", False))
    structured_output_schema = structured_output.get("schema", {})
    if not isinstance(structured_output_schema, dict):
        raise ValueError("LLM structured_output.schema must be an object")
    if structured_output_enabled:
        if (
            structured_output_schema.get("type") != "object"
            or not isinstance(structured_output_schema.get("properties"), dict)
        ):
            raise ValueError(
                "LLM structured_output.enabled requires an object-rooted JSON Schema with properties"
            )
        if "required" in structured_output_schema and not isinstance(
            structured_output_schema["required"], list
        ):
            raise ValueError("LLM structured_output.schema.required must be a list")
    llm_config = {
        "promptTemplate": prompt,
        "vision": {
            "enabled": vision_enabled,
            "detail": vision_detail,
            "mediaSelectors": vision_media_selectors,
        },
        "structuredOutput": {
            "enabled": structured_output_enabled,
            "schema": structured_output_schema,
        },
    }
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "LLM",
            "title": title,
            "config": {
                "historyRoundLimit": history_round_limit,
                "useLongMemory": bool(use_long_memory),
                "llm": llm_config,
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


_LIBRARY_BLOCK_REG = re.compile(r"\{#LibraryBlock\s+(.+?)\s*#\}")
_LIBRARY_BLOCK_ATTR_REG = re.compile(r"(?:^|\s+)([A-Za-z_]\w*)=")


def _parse_library_block_fields(raw_fields):
    matches = list(_LIBRARY_BLOCK_ATTR_REG.finditer(raw_fields))
    if not matches or raw_fields[:matches[0].start()].strip():
        raise ValueError("invalid LibraryBlock attributes; expected key=value")
    fields = {}
    for index, match in enumerate(matches):
        key = match.group(1)
        if not key or key in fields:
            raise ValueError(f"invalid or duplicate LibraryBlock attribute '{key}'")
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_fields)
        value = raw_fields[match.end():value_end].strip()
        if value.startswith('"') or value.endswith('"'):
            if len(value) < 2 or not (value.startswith('"') and value.endswith('"')):
                raise ValueError(f"invalid quoted LibraryBlock attribute '{key}'")
            value = value[1:-1]
        fields[key] = value
    return fields


def _parse_library_blocks(display_prompt):
    if not display_prompt:
        return []
    if not isinstance(display_prompt, str):
        raise ValueError("AGENT prompt must be a string")
    matches = list(_LIBRARY_BLOCK_REG.finditer(display_prompt))
    if display_prompt.count("{#LibraryBlock") != len(matches):
        raise ValueError("AGENT prompt contains an incomplete LibraryBlock")

    blocks = []
    for match in matches:
        fields = _parse_library_block_fields(match.group(1))
        block_type = fields.get("type")
        if block_type == "variable":
            if not {"id", "type", "name"}.issubset(fields):
                raise ValueError("variable LibraryBlock requires id/type/name")
            if not fields["id"].isdigit() or int(fields["id"]) <= 0 or not fields["name"]:
                raise ValueError("variable LibraryBlock requires a positive field id and non-empty name")
        elif block_type == "tool":
            if not {"id", "type", "name", "tool"}.issubset(fields):
                raise ValueError("tool LibraryBlock requires id/type/name/tool")
            if not fields["id"].isdigit() or int(fields["id"]) <= 0:
                raise ValueError("tool LibraryBlock requires a positive id")
            if not fields["name"] or not fields["tool"]:
                raise ValueError("tool LibraryBlock requires non-empty name and tool")
        elif block_type == "transferHuman":
            if not {"tool_id", "type", "name"}.issubset(fields):
                raise ValueError("transferHuman LibraryBlock requires tool_id/type/name")
            if not fields["tool_id"].isdigit() or int(fields["tool_id"]) <= 0:
                raise ValueError("transferHuman LibraryBlock requires a positive numeric tool_id")
            if not fields["name"]:
                raise ValueError("transferHuman LibraryBlock requires a non-empty name")
            if fields.get("action") and fields["action"] not in {
                "NOT_REPLY", "CUSTOM_REPLY", "TEMPLATE_REPLY",
            }:
                raise ValueError("transferHuman LibraryBlock has an unsupported action")
            if fields.get("templateId") and (
                not fields["templateId"].isdigit() or int(fields["templateId"]) <= 0
            ):
                raise ValueError("transferHuman LibraryBlock templateId must be a positive integer")
        else:
            raise ValueError(f"unsupported LibraryBlock type '{block_type}'")
        blocks.append({
            "raw": match.group(0),
            "type": block_type,
            "fields": fields,
            "start": match.start(),
            "end": match.end(),
        })
    transfer_tool_ids = [
        block["fields"]["tool_id"] for block in blocks if block["type"] == "transferHuman"
    ]
    if len(transfer_tool_ids) != len(set(transfer_tool_ids)):
        raise ValueError("transferHuman LibraryBlock tool_id must be unique within one AGENT prompt")
    return blocks


def _format_chatflow_agent_prompt(display_prompt):
    """Convert frontend LibraryBlock chips into runtime prompt text."""
    if not display_prompt:
        return ""

    blocks = _parse_library_blocks(display_prompt)
    by_raw = {block["raw"]: block for block in blocks}

    def replace_block(match):
        block = by_raw[match.group(0)]
        fields = block["fields"]
        block_type = block["type"]
        if block_type == "variable":
            return f" {fields.get('name', '')} "
        if block_type == "tool":
            if fields.get("tool") == "template_reply":
                return f" template_reply tool (template id: {fields.get('id', '')})"
            return f"{fields.get('name', '')} tool "
        if block_type == "transferHuman":
            return f" Transfer_To_Agent (reason: {fields.get('name', '')}) "
        return ""

    return _LIBRARY_BLOCK_REG.sub(replace_block, display_prompt)


def if_else_node(title, cases, position=(0, 0)):
    """
    IF_ELSE multi-branch condition node.

    cases example::

        [
            {
                "id": "SHIPPED",
                "conditions": [
                    {
                        "variableSelector": [...],
                        "comparisonOperator": "EQUAL",
                        "value": "SHIPPED",
                    }
                ],
            }
        ]

    Each condition gets an auto-generated ``id`` and default ``varType``.
    """
    title = _validate_title(title)
    processed_cases = []
    for case in cases:
        conds = []
        for c in case.get("conditions", []):
            cond = {"varType": c.get("varType", "string")}
            cond.update(c)
            if "id" not in cond:
                cond["id"] = _uid()
            conds.append(cond)
        processed_cases.append({
            "id": case["id"],
            "logicalOperator": case.get("logicalOperator", "AND"),
            "conditions": conds,
        })
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "IF_ELSE",
            "title": title,
            "config": {"cases": processed_cases},
        },
        "position": {"x": position[0], "y": position[1]},
    }


def tool_node(title, tool_id, input_params=None,
              enable_action_status=False, tool_type="EXTERNAL_HTTP_CALL",
              position=(0, 0)):
    """TOOL node -- calls a configured project tool plugin."""
    title = _validate_title(title)
    if not isinstance(tool_type, str) or not tool_type.strip():
        raise ValueError("TOOL tool_type must be a non-empty plugin type")
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "TOOL",
            "title": title,
            "config": {
                "tool": {
                    "id": tool_id,
                    "type": tool_type,
                    "enableActionStatus": enable_action_status,
                    "inputParams": input_params or [],
                }
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def question_node(title, question=None, mode="VARIABLE", variables=None,
                  replies=None, max_rounds=5, question_type="PROMPT",
                  question_template_id=None, condition="AND",
                  use_chat_history=True, position=(0, 0)):
    """
    QUESTION node.

    mode="VARIABLE"    -- collect AI field variables; pass ``variables=[id1, ...]``
    mode="USER_REPLY"  -- classify user reply; pass ``replies=[{"id": "r1", "name": "Option_A"}, ...]``
    """
    title = _validate_title(title)
    mode = (mode or "VARIABLE").upper()
    if mode not in {"VARIABLE", "USER_REPLY"}:
        raise ValueError(f"unsupported QUESTION mode: {mode}")
    question_type = (question_type or "PROMPT").upper()
    if question_type not in {"PROMPT", "TEMPLATE"}:
        raise ValueError(f"unsupported QUESTION question_type: {question_type}")
    if question_type == "TEMPLATE" and not question_template_id:
        raise ValueError(f"QUESTION node '{title}' type TEMPLATE requires question_template_id")
    if question_type == "PROMPT" and not question:
        raise ValueError(f"QUESTION node '{title}' type PROMPT requires question")
    condition = (condition or "AND").upper()
    if condition not in {"AND", "OR"}:
        raise ValueError(f"QUESTION node '{title}' condition must be AND or OR")
    collect_info = {
        "type": mode,
        "questionType": question_type,
        "question": question if question_type == "PROMPT" else None,
        "questionTemplateId": question_template_id if question_type == "TEMPLATE" else None,
        "condition": condition,
    }
    if mode == "VARIABLE":
        collect_info["variables"] = variables or []
        collect_info["replies"] = []
    else:
        collect_info["replies"] = [
            {"id": r["id"], "name": _validate_title(r["name"])}
            for r in (replies or [])
        ]
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "QUESTION",
            "title": title,
            "config": {
                "maxRounds": max_rounds,
                "useChatHistory": bool(use_chat_history),
                "collectInfo": collect_info,
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def collect_order_node(title="Collect_Order", max_rounds=5, exceptions=None,
                       position=(0, 0)):
    """COLLECT_ORDER node -- soon-offline compatibility order collection step."""
    title = _validate_title(title)
    normalized_exceptions = []
    for index, item in enumerate(exceptions or []):
        if not isinstance(item, dict):
            raise ValueError(f"COLLECT_ORDER exception[{index}] must be an object")
        item_type = str(item.get("type") or "REPLY").upper()
        entry = {
            "key": item.get("key") or "ORDER_NUMBER_NOT_PROVIDED",
            "type": item_type,
            "reply": item.get("reply"),
            "templateId": item.get("template_id", item.get("templateId")),
        }
        if item_type == "TEMPLATE" and not entry["templateId"]:
            raise ValueError(f"COLLECT_ORDER exception[{index}] type TEMPLATE requires template_id")
        if item_type != "TEMPLATE" and not isinstance(entry["reply"], str):
            raise ValueError(f"COLLECT_ORDER exception[{index}] type REPLY requires reply")
        normalized_exceptions.append(entry)
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "COLLECT_ORDER",
            "title": title,
            "config": {
                "maxRounds": max_rounds,
                "collectOrderException": normalized_exceptions,
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def transfer_human_node(title="Transfer_To_Human",
                        prompt="", transfer_type="NO_REPLY",
                        template_id=None, ai_field_ids=None,
                        disable_prev_node_results=False, explain=None,
                        position=(0, 0)):
    """
    TRANSFER_TO_HUMAN node.

    transfer_type: "NO_REPLY" (default) / "PROMPT" / "TEMPLATE"
    prompt: used when transfer_type="PROMPT"
    template_id: used when transfer_type="TEMPLATE"
    """
    title = _validate_title(title)
    transfer_type = (transfer_type or "NO_REPLY").upper()
    if transfer_type not in {"NO_REPLY", "PROMPT", "TEMPLATE"}:
        raise ValueError(f"unsupported TRANSFER_TO_HUMAN type: {transfer_type}")
    if transfer_type == "TEMPLATE" and not template_id:
        raise ValueError(f"TRANSFER_TO_HUMAN node '{title}' type TEMPLATE requires template_id")
    if transfer_type == "PROMPT" and not prompt:
        raise ValueError(f"TRANSFER_TO_HUMAN node '{title}' type PROMPT requires prompt")
    if transfer_type != "PROMPT" and ai_field_ids:
        raise ValueError(f"TRANSFER_TO_HUMAN type {transfer_type} does not use ai_field_ids")
    config = {
        "type": transfer_type,
        "prompt": prompt,
        "explain": explain or title,
        "aiFieldIds": _normalize_id_list(ai_field_ids, "ai_field_ids") if transfer_type == "PROMPT" else None,
    }
    if transfer_type == "TEMPLATE" and template_id:
        config["templateId"] = template_id
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "TRANSFER_TO_HUMAN",
            "title": title,
            "config": {
                "transferToHuman": config,
                "disablePrevNodeResult": bool(disable_prev_node_results),
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def human_review_node(title="Human_Review", method="approval", description="", fields=None,
                      midway_message_strategy="ignore", position=(0, 0)):
    """HUMAN_REVIEW node - human-in-the-loop approval or form fill."""
    title = _validate_title(title)
    method = (method or "approval").lower()
    if method not in {"approval", "fill"}:
        raise ValueError("HUMAN_REVIEW method must be approval or fill")
    midway_message_strategy = (midway_message_strategy or "ignore").lower()
    if midway_message_strategy not in {"ignore", "handle"}:
        raise ValueError("HUMAN_REVIEW midway_message_strategy must be ignore or handle")
    config = {
        "humanReview": {
            "method": method,
            "description": description,
            "midwayMessageStrategy": midway_message_strategy,
        }
    }
    if method == "fill" and fields:
        config["humanReview"]["fields"] = fields
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "HUMAN_REVIEW",
            "title": title,
            "desc": "Routes task to a human operator for review, approval, or manual input",
            "config": config,
        },
        "position": {"x": position[0], "y": position[1]},
    }


def intent_node(title, intents, prompt=None, history_round_limit=None,
                use_chat_history=True, position=(0, 0)):
    """
    INTENT node.

    intents example::

        [{"id": "intent-refund", "name": "Refund", "desc": "...", "intentId": 12345}]
    """
    title = _validate_title(title)
    processed = []
    for i in intents:
        processed.append({
            "id": i.get("id", _uid()),
            "name": _validate_title(i["name"]),
            "desc": i.get("desc", ""),
            "intentId": i.get("intentId"),
            "examples": i.get("examples", []),
        })
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "INTENT",
            "title": title,
            "config": {
                "useChatHistory": bool(use_chat_history),
                "historyRoundLimit": history_round_limit,
                "prompt": prompt,
                "intents": processed,
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def knowledge_reply_node(title, prompt, kb_dirs, max_rounds=10,
                         disable_prev_node_results=False, position=(0, 0)):
    """KNOWLEDGE_REPLY node -- must have RESOLVED and UNRESOLVED outbound edges."""
    title = _validate_title(title)
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "KNOWLEDGE_REPLY",
            "title": title,
            "config": {
                "maxRounds": max_rounds,
                "knowledgeReply": {
                    "prompt": prompt,
                    "knowledgeDirectoryIds": kb_dirs,
                },
                "nextStep": [
                    {"id": "RESOLVED", "title": "Resolved", "prompt": None},
                    {"id": "UNRESOLVED", "title": "Unresolved", "prompt": None},
                ],
                "disablePrevNodeResult": bool(disable_prev_node_results),
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def rag_reply_node(
    title,
    prompt,
    kb_dirs=None,
    knowledge_keyword_ids=None,
    knowledge_keyword_selector=None,
    customize_query=False,
    query_selector=None,
    disable_prev_node_results=False,
    position=(0, 0),
):
    """RAG_REPLY node -- must have TRUE and LACK_KNOWLEDGE outbound edges."""
    title = _validate_title(title)
    rag_reply = {
        "prompt": prompt,
    }
    if kb_dirs is not None:
        rag_reply["knowledgeDirectoryIds"] = kb_dirs
    if knowledge_keyword_ids is not None:
        rag_reply["knowledgeKeywordIds"] = knowledge_keyword_ids
    if knowledge_keyword_selector is not None:
        rag_reply["knowledgeKeywordSelector"] = knowledge_keyword_selector
    if customize_query:
        rag_reply["customizeQuery"] = True
        rag_reply["querySelector"] = query_selector
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "RAG_REPLY",
            "title": title,
            "config": {
                "ragReply": rag_reply,
                "disablePrevNodeResult": bool(disable_prev_node_results),
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def variable_extract_node(title, variables, additional_data=None,
                          use_chat_history=False, position=(0, 0)):
    """
    VARIABLE_EXTRACT node -- extract variables from conversation context.

    variables example::

        [
            {
                "name": "order_number",
                "description": "The customer order number",
                "type": "string",
                "required": True,
            }
        ]
    """
    title = _validate_title(title)
    processed = []
    for v in variables:
        processed.append({
            "id": v.get("id", _uid()),
            "name": _validate_title(v["name"]),
            "describe": v.get("describe", v.get("description", "")),
            "type": v.get("type", "string"),
        })
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "VARIABLE_EXTRACT",
            "title": title,
            "config": {
                "useChatHistory": bool(use_chat_history),
                "variableExtract": {
                    "additionalData": additional_data or [],
                    "extracts": processed,
                },
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def _normalize_assignment(assignment):
    return {
        "id": assignment.get("id", _uid()),
        "operation": assignment.get("operation", "OVER_WRITE"),
        "source": assignment.get("source", assignment.get("variableSelector", assignment.get("value"))),
        "target": assignment.get("target") or assignment.get("targets") or [],
        "forceOverride": assignment.get("forceOverride", assignment.get("force_override", False)),
    }


def variable_assignment_node(title, assignments, position=(0, 0)):
    """
    VARIABLE_ASSIGNMENT node -- assign values to conversation variables.

    assignments example::

        [
            {
                "variableSelector": ["TOOL", "<tool_node_id>", "status"],
                "targetVariable": "order_status",
                "value": None,   # None means take from variableSelector
            }
        ]
    """
    title = _validate_title(title)
    processed = [_normalize_assignment(a) for a in assignments]
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "VARIABLE_ASSIGNMENT",
            "title": title,
            "config": {
                "variableAssignment": processed,
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def variable_process_node(title, variables=None, assignments=None,
                          additional_data=None, use_chat_history=False,
                          position=(0, 0)):
    """VARIABLE_PROCESS node -- extract variables and/or assign variable-system fields."""
    title = _validate_title(title)
    extracts = []
    for v in variables or []:
        extracts.append({
            "id": v.get("id", _uid()),
            "name": _validate_title(v["name"]),
            "describe": v.get("describe", v.get("description", "")),
            "type": v.get("type", "string"),
        })
    normalized_assignments = [_normalize_assignment(a) for a in assignments or []]
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "VARIABLE_PROCESS",
            "title": title,
            "config": {
                "useChatHistory": bool(use_chat_history),
                "variableProcess": {
                    "additionalData": additional_data or [],
                    "extracts": extracts,
                    "assignments": normalized_assignments,
                },
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def code_node(title, source_code, inputs=None, outputs=None, position=(0, 0)):
    """CODE node -- trusted Python code block with declared inputs/outputs."""
    title = _validate_title(title)

    def normalize_input(item):
        field_name = item.get("fieldName", item.get("field_name"))
        if not field_name:
            raise ValueError(f"CODE node '{title}' input missing field_name")
        variable_selector = item.get("variableSelector", item.get("variable_selector"))
        if variable_selector is None:
            raise ValueError(f"CODE node '{title}' input '{field_name}' missing variable_selector")
        return {
            "id": item.get("id", _uid()),
            "fieldName": field_name,
            "variableSelector": variable_selector,
        }

    def normalize_output(item):
        field_name = item.get("fieldName", item.get("field_name"))
        if not field_name:
            raise ValueError(f"CODE node '{title}' output missing field_name")
        return {
            "id": item.get("id", _uid()),
            "fieldName": field_name,
            "fieldType": item.get("fieldType", item.get("field_type", "String")),
        }

    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "CODE",
            "title": title,
            "config": {
                "code": {
                    "inputs": [normalize_input(i) for i in inputs or []],
                    "sourceCode": source_code,
                    "outputs": [normalize_output(o) for o in outputs or []],
                },
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def sub_graph_node(title, target_agent_id, context_turn_limit=5, position=(0, 0)):
    """SUB_GRAPH node -- call another CHAT_FLOW graph. It must not have outgoing edges."""
    if not target_agent_id:
        raise ValueError(f"SUB_GRAPH node '{title}' missing target_agent_id")
    title = _validate_title(title)
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "SUB_GRAPH",
            "title": title,
            "config": {
                "subGraph": {
                    "targetAgentId": int(target_agent_id),
                    "contextTurnLimit": int(context_turn_limit),
                },
            },
        },
        "position": {"x": position[0], "y": position[1]},
    }


def business_track_node(title, trace_events, position=(0, 0)):
    """BUSINESS_TRACK node -- emits one or more business trace event codes."""
    title = _validate_title(title)
    if not isinstance(trace_events, list) or not trace_events:
        raise ValueError("BUSINESS_TRACK trace_events must be a non-empty list")
    normalized_events = []
    for index, event in enumerate(trace_events):
        if not isinstance(event, str) or not event.strip():
            raise ValueError(f"BUSINESS_TRACK trace_events[{index}] must be a non-empty string")
        normalized_events.append(event.strip())
    return {
        "id": _uid(),
        "type": "CUSTOM",
        "data": {
            "category": "BUSINESS_TRACK",
            "title": title,
            "config": {"businessTrack": {"traceEvents": normalized_events}},
        },
        "position": {"x": position[0], "y": position[1]},
    }


# ---------------------------------------------------------------------------
# Edge builders
# ---------------------------------------------------------------------------

def edge(source_node, target_node, source_handle="SOURCE"):
    """
    Create a single edge between two nodes.

    source_node / target_node are node dicts returned by builder functions.
    Uses first 8 chars of node IDs to keep edge IDs readable even with UUIDs.
    """
    return {
        "id": f"e-{_short_id(source_node['id'])}-{source_handle}-{_short_id(target_node['id'])}",
        "source": source_node["id"],
        "sourceHandle": source_handle,
        "target": target_node["id"],
        "targetHandle": "TARGET",
        "type": "default",
    }


def edges_from_if_else(if_node, case_targets, false_target=None):
    """
    Create all branch edges from an IF_ELSE node.

    case_targets: {"CASE_ID": target_node, ...}
    false_target:  target node for the FALSE (else) branch (optional)
    """
    result = []
    for case_id, target in case_targets.items():
        result.append(edge(if_node, target, source_handle=case_id))
    if false_target:
        result.append(edge(if_node, false_target, source_handle="FALSE"))
    return result


def edges_from_intent(intent_node_obj, intent_targets, other_target=None):
    """
    Create all intent-branch edges from an INTENT node.

    intent_targets: {"intent-id": target_node, ...}
    other_target:   target node for the OTHER (fallback) branch (optional)
    """
    result = []
    for intent_id, target in intent_targets.items():
        result.append(edge(intent_node_obj, target, source_handle=intent_id))
    if other_target:
        result.append(edge(intent_node_obj, other_target, source_handle="OTHER"))
    return result


def edges_from_question_replies(question_node_obj, reply_targets,
                                other_target=None):
    """
    Create branch edges from a USER_REPLY-mode QUESTION node.

    reply_targets: {"reply_id": target_node, ...}
    """
    result = []
    for reply_id, target in reply_targets.items():
        result.append(edge(question_node_obj, target, source_handle=reply_id))
    if other_target:
        result.append(edge(question_node_obj, other_target, source_handle="OTHER"))
    return result


def edges_from_knowledge_reply(kr_node, resolved_target, unresolved_target):
    """
    Create the two required edges from a KNOWLEDGE_REPLY node.

    KNOWLEDGE_REPLY must always have both RESOLVED and UNRESOLVED outbound edges.
    """
    return [
        edge(kr_node, resolved_target, source_handle="RESOLVED"),
        edge(kr_node, unresolved_target, source_handle="UNRESOLVED"),
    ]


def edges_from_rag_reply(rag_node, true_target, lack_knowledge_target):
    """
    Create the two required edges from a RAG_REPLY node.

    RAG_REPLY must always have both TRUE and LACK_KNOWLEDGE outbound edges.
    """
    return [
        edge(rag_node, true_target, source_handle="TRUE"),
        edge(rag_node, lack_knowledge_target, source_handle="LACK_KNOWLEDGE"),
    ]


def edges_from_human_review(hr_node, agree_target, reject_target=None):
    """Create edges from HUMAN_REVIEW(approval) node."""
    result = [edge(hr_node, agree_target, "AGREE")]
    if reject_target:
        result.append(edge(hr_node, reject_target, "REJECT"))
    return result


def edges_from_agent(agent_node_obj, next_step_targets, default_target=None):
    """
    Create all outbound edges from an AGENT node with nextStep branches.

    next_step_targets: {"next_step_id": target_node, ...}
        Keys MUST match the ``id`` values defined in the agent's nextStep config.
    default_target: target node for AGENT without nextStep (sourceHandle="SOURCE")

    Raises ValueError if any nextStep id has no matching target — prevents the
    common bug where an AGENT branch is silently a dead-end.
    """
    cfg = agent_node_obj.get("data", {}).get("config", {})
    next_step = cfg.get("nextStep") or []
    if not next_step:
        if default_target is None:
            raise ValueError(
                f"agent_node {agent_node_obj['id']} has no nextStep — pass default_target for the SOURCE edge"
            )
        return [edge(agent_node_obj, default_target, source_handle="SOURCE")]

    defined_ids = {ns["id"] for ns in next_step}
    provided_ids = set(next_step_targets.keys())
    missing = defined_ids - provided_ids
    extra = provided_ids - defined_ids
    if missing:
        raise ValueError(
            f"agent_node {agent_node_obj['id']} missing edges for nextStep ids: {sorted(missing)}"
        )
    if extra:
        raise ValueError(
            f"agent_node {agent_node_obj['id']} has unknown nextStep ids in targets: {sorted(extra)}"
        )
    return [edge(agent_node_obj, target, source_handle=ns_id)
            for ns_id, target in next_step_targets.items()]


# ---------------------------------------------------------------------------
# Auto parameter binding
# ---------------------------------------------------------------------------

# Common variable-system field name → field ID mapping (updated per project; these are defaults)
_DEFAULT_FIELD_MAPPING = {
    "ordernumber": "OrderNumber",
    "orderno": "OrderNumber",
    "orderid": "OrderNumber",
    "order_number": "OrderNumber",
    "trackingnumbers": "TrackingNumber",
    "trackingnumber": "TrackingNumber",
    "tracking_number": "TrackingNumber",
    "customeremail": "CustomerEmail",
    "email": "CustomerEmail",
    "customername": "CustomerName",
    "name": "CustomerName",
}


def auto_bind_tool_params(client, nodes, _plugin_cache=None, _field_cache=None):
    """
    For every TOOL node in the graph, check plugin required params and
    auto-bind them to variable-system fields via variableSelector.

    Skips params that already have inputParams configured.
    Prints warnings for unmatched required params.

    Args:
        client: SolveaClient instance (used to query plugins and AI fields)
        nodes: list of node dicts
        _plugin_cache: optional pre-fetched plugin list (avoids duplicate API call)
        _field_cache: optional pre-fetched AI field list (avoids duplicate API call)

    Returns:
        tuple of (plugin_map, field_lookup) for reuse by downstream validators
    """
    # Collect TOOL nodes
    tool_nodes = [n for n in nodes
                  if n.get("data", {}).get("category") == "TOOL"]
    if not tool_nodes:
        return {}, {}

    # Fetch plugins and AI fields once (or reuse cache)
    plugins = _plugin_cache if _plugin_cache is not None else client.list_plugins()
    plugin_map = {}
    for p in plugins:
        pid = p.get("id")
        if pid:
            plugin_map[pid] = p

    ai_fields = _field_cache if _field_cache is not None else client.list_ai_fields()
    # Build name -> (field_path, bizType) lookup. Nested fields must retain
    # their complete cascader path, e.g. OrderInformation -> OrderNumber.
    field_lookup = {}  # lowercase name -> (field_path, bizType)
    if isinstance(ai_fields, list):
        def add_field(field, biz_type, parent_path=None):
            if not isinstance(field, dict) or field.get("id") is None:
                return
            path = [*(parent_path or []), field["id"]]
            if field.get("name"):
                field_lookup[field["name"].lower()] = (path, biz_type)
            for child in field.get("children") or []:
                add_field(child, biz_type, path)

        for f in ai_fields:
            if isinstance(f, dict):
                biz = f.get("bizType", "Custom")
                add_field(f, biz)

    for tool_nd in tool_nodes:
        title = tool_nd["data"].get("title", "?")
        tool_cfg = tool_nd["data"]["config"]["tool"]
        plugin_id = tool_cfg["id"]
        existing_params = tool_cfg.get("inputParams", [])
        existing_names = {p["name"] for p in existing_params}

        plugin = plugin_map.get(plugin_id)
        if not plugin:
            print(f"  ⚠️  WARNING: TOOL '{title}' references plugin {plugin_id} not found in project")
            continue

        config = plugin.get("meta", {}).get("externalHttpCallConfig", {})
        req_items = config.get("requestParam", {}).get("items", [])

        for item in req_items:
            param_name = item["name"]
            required = item.get("required", False)
            source = item.get("source", "LLM")

            # Skip non-required or non-LLM params
            if not required or source != "LLM":
                continue
            # Skip already configured
            if param_name in existing_names:
                continue

            # Try to match to a variable-system field
            lookup_key = param_name.lower()
            matched_field_name = _DEFAULT_FIELD_MAPPING.get(lookup_key)

            field_entry = None  # (field_path, bizType)
            if matched_field_name:
                field_entry = field_lookup.get(matched_field_name.lower())

            if not field_entry:
                # Try direct name match
                field_entry = field_lookup.get(lookup_key)

            if field_entry:
                field_path, biz_type = field_entry
                new_param = {
                    "name": param_name,
                    "variableSelector": ["SYSTEM", biz_type, *field_path],
                    "varType": item.get("type", "string"),
                }
                existing_params.append(new_param)
                existing_names.add(param_name)
                print(f"  [auto-bind] TOOL '{title}': {param_name} → variable-system field {matched_field_name or param_name} (path: {field_path}, bizType: {biz_type})")
            else:
                print(f"  ⚠️  WARNING: TOOL '{title}': required param '{param_name}' has no matching variable-system field — must bind manually")

        tool_cfg["inputParams"] = existing_params

    return plugin_map, field_lookup


def _validate_business_rules(nodes, client=None, _plugin_map=None):
    """
    Business-level validation beyond structural checks.
    Returns list of error strings.
    """
    errors = []

    for n in nodes:
        cat = n.get("data", {}).get("category", "")
        title = n.get("data", {}).get("title", "?")
        cfg = n.get("data", {}).get("config", {})

        # TOOL: check required params are bound
        if cat == "TOOL":
            tool_cfg = cfg.get("tool", {})
            input_params = tool_cfg.get("inputParams", [])
            configured_names = {p["name"] for p in input_params}

            if client or _plugin_map:
                if _plugin_map:
                    plugin = _plugin_map.get(tool_cfg.get("id"))
                else:
                    plugins = client.list_plugins()
                    plugin = next((p for p in plugins if p.get("id") == tool_cfg.get("id")), None)
                if plugin:
                    req_items = plugin.get("meta", {}).get("externalHttpCallConfig", {}).get("requestParam", {}).get("items", [])
                    for item in req_items:
                        if item.get("required") and item.get("source") == "LLM" and item["name"] not in configured_names:
                            errors.append(f"TOOL '{title}': required param '{item['name']}' not bound in inputParams")

        # IF_ELSE: check variableSelector doesn't have stale "output" layer
        if cat == "IF_ELSE":
            cases = cfg.get("cases", [])
            for case in cases:
                for cond in case.get("conditions", []):
                    vs = cond.get("variableSelector", [])
                    if len(vs) >= 3 and vs[0] == "TOOL" and vs[2] == "output":
                        errors.append(
                            f"IF_ELSE '{title}': variableSelector {vs} has invalid 'output' layer. "
                            f"Correct format: ['TOOL', node_id, field_name, ...]"
                        )

        # AGENT: check nextStep items have id
        if cat == "AGENT":
            for ns in cfg.get("nextStep", []):
                if not ns.get("id"):
                    errors.append(f"AGENT '{title}': nextStep item '{ns.get('title', '?')}' missing 'id'")

    return errors


# ---------------------------------------------------------------------------
# Graph assembly + validation
# ---------------------------------------------------------------------------

def build_graph(nodes, edges, client=None, ai_fields=None, agent_ai_fields=None):
    """
    Assemble a chatFlowGraph dict from nodes and edges.

    **Validation is mandatory** — runs validate_graph + business rules and
    raises ValueError on any error. There is no opt-out switch; deploy 前
    必须 validate 通过，避免被后端拒收或运行时炸。

    When client is provided, also runs:
      - auto_bind_tool_params: auto-bind TOOL required params to variable-system fields
      - _validate_business_rules: check TOOL params, IF_ELSE selectors, etc.
    """
    # --- Auto-bind TOOL params if client provided ---
    _plugin_map = {}
    if client:
        if ai_fields is None:
            ai_fields = client.list_ai_fields()
        _plugin_map, _ = auto_bind_tool_params(client, nodes, _field_cache=ai_fields)

    # --- Pre-build warnings ---
    for n in nodes:
        cat = n.get("data", {}).get("category", "")
        title = n.get("data", {}).get("title", "?")
        cfg = n.get("data", {}).get("config", {})
        # Warn: empty knowledgeDirectoryIds
        if cat == "KNOWLEDGE_REPLY":
            kb = cfg.get("knowledgeReply", {}).get("knowledgeDirectoryIds", [])
            if not kb:
                print(f"  ⚠️  WARNING: KNOWLEDGE_REPLY '{title}' has empty knowledgeDirectoryIds — will always go UNRESOLVED")
        if cat == "RAG_REPLY":
            kb = cfg.get("ragReply", {}).get("knowledgeDirectoryIds", [])
            if not kb:
                print(f"  ⚠️  WARNING: RAG_REPLY '{title}' has empty knowledgeDirectoryIds — will always go LACK_KNOWLEDGE")

    # --- Business rule validation (reuse plugin_map from auto_bind) ---
    if client:
        biz_errors = _validate_business_rules(nodes, client, _plugin_map=_plugin_map)
        if biz_errors:
            raise ValueError(
                "Business validation failed:\n"
                + "\n".join(f"  ERROR: {e}" for e in biz_errors)
            )

    graph = {
        "nodes": nodes,
        "edges": edges,
        "viewport": {"x": 0, "y": 0, "zoom": 0.8},
    }

    # Mandatory validation — no opt-out
    # validate_graph 与本文件同目录（chatflow/scripts/validate_graph.py）。
    # 调用方负责把 chatflow/scripts/ 加入 sys.path。
    from validate_graph import validate_graph as _validate_graph

    result = _validate_graph(
        graph,
        ai_fields=ai_fields,
        agent_ai_fields=agent_ai_fields,
    )
    if isinstance(result, list):
        if result:
            raise ValueError(
                "Graph validation failed:\n"
                + "\n".join(f"  ERROR: {e}" for e in result)
            )
        print(f"  Graph OK: {len(nodes)} nodes, {len(edges)} edges")
    elif isinstance(result, dict):
        if not result.get("valid", True):
            raise ValueError(
                "Graph validation failed:\n"
                + "\n".join(f"  ERROR: {e}" for e in result.get("errors", []))
            )
        for w in result.get("warnings", []):
            print(f"  WARNING: {w}")
        stats = result.get("stats", {})
        n_count = stats.get("nodes", len(nodes))
        e_count = stats.get("edges", len(edges))
        print(f"  Graph OK: {n_count} nodes, {e_count} edges")
    else:
        print(f"  Graph OK: {len(nodes)} nodes, {len(edges)} edges")

    return graph


# ---------------------------------------------------------------------------
# One-step deploy
# ---------------------------------------------------------------------------

@contextmanager
def _deploy_lock():
    """Serialize createAgent/updateAgent deploys from parallel tool executions."""
    runtime = _bootstrap_cli_runtime()
    lock_dir = runtime.STATE_DIR if runtime is not None else Path("workspace") / "state" / "chatflow"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "chatflow_deploy.lock"
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        try:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass


def _create_agent_with_retry(client, skeleton):
    try:
        return client.create_agent(skeleton)
    except RuntimeError as exc:
        message = str(exc)
        if "System Error" not in message or "createAgent" not in message:
            raise
        print("  WARNING: createAgent returned System Error; retrying once after deploy lock wait")
        time.sleep(2)
        return client.create_agent(skeleton)


def deploy_chatflow(client, graph, agent_name):
    """
    Create and deploy a new CHAT_FLOW agent end-to-end.

    Do not use this for incremental edits to an existing agent. Existing
    CHAT_FLOW updates should call `client.update_chatflow(agent_id, graph)`,
    which follows the UI behavior and saves a draft by default.

    1. Create agent skeleton (START + FINISH with connecting edge)
    2. Update agent with the full chatFlowGraph

    NOTE: Intents 在 INTENT 节点里定义，不调系统意图接口。
    CHAT_FLOW agent 必须走策略路由测试——本函数 **不做** 烟雾测试，因为
    裸 client.chat() 会被默认 bot 接走，根本打不到刚部署的 chatflow，
    返回的 test_result 是假阳性（来自默认 agent）。部署完后请按具体业务走
    poc / delivery skill，或手动建策略路由验证。

    Returns dict with keys: agent_id.
    """
    result = {}

    # ------------------------------------------------------------------
    # Step 1: Create skeleton with START and FINISH connected by an edge
    # ------------------------------------------------------------------
    skel_start = start_node()
    skel_finish = finish_node()
    skel_edge = edge(skel_start, skel_finish)
    skeleton_graph = {
        "nodes": [skel_start, skel_finish],
        "edges": [skel_edge],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    }
    skeleton = {
        "name": agent_name,
        "type": "CHAT_FLOW",
        "category": "TEXT",
        "source": "MANUAL",
        "projectId": int(client.project_id),
        "meta": {
            # Pass as a Python dict -- NOT json.dumps
            "chatFlowGraph": skeleton_graph,
        },
    }
    with _deploy_lock():
        created = _create_agent_with_retry(client, skeleton)
        agent_id = created.get("id") or created.get("data", {}).get("id")
        result["agent_id"] = agent_id
        print(f"  [1/2] Agent created: {agent_id}")

        # ------------------------------------------------------------------
        # Step 2: Fetch full detail, merge in real graph, update
        # ------------------------------------------------------------------
        agent_detail = client.get_agent(agent_id)
        agent_data = agent_detail[0] if isinstance(agent_detail, list) else agent_detail
        agent_data["agentId"] = agent_id
        agent_data["meta"] = agent_data.get("meta", {})
        # chatFlowGraph as a Python dict (not json.dumps string)
        agent_data["meta"]["chatFlowGraph"] = graph
        client.update_agent(agent_data)
        print(f"  [2/2] Graph written: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")

    return result



# ---------------------------------------------------------------------------
# Source compiler (agent-authored source JSON -> full chatFlowGraph)
# ---------------------------------------------------------------------------

_SOURCE_TYPE_ALIASES = {
    "start": "START",
    "finish": "FINISH",
    "reply": "REPLY",
    "llm": "LLM",
    "model": "LLM",
    "agent": "AGENT",
    "if_else": "IF_ELSE",
    "ifelse": "IF_ELSE",
    "tool": "TOOL",
    "question": "QUESTION",
    "collect_order": "COLLECT_ORDER",
    "collectorder": "COLLECT_ORDER",
    "transfer": "TRANSFER_TO_HUMAN",
    "transfer_to_human": "TRANSFER_TO_HUMAN",
    "human_review": "HUMAN_REVIEW",
    "humanreview": "HUMAN_REVIEW",
    "intent": "INTENT",
    "knowledge_reply": "KNOWLEDGE_REPLY",
    "knowledge": "RAG_REPLY",
    "rag_reply": "RAG_REPLY",
    "rag": "RAG_REPLY",
    "variable_extract": "VARIABLE_EXTRACT",
    "variableextract": "VARIABLE_EXTRACT",
    "variable_assignment": "VARIABLE_ASSIGNMENT",
    "variableassignment": "VARIABLE_ASSIGNMENT",
    "variable_process": "VARIABLE_PROCESS",
    "variableprocess": "VARIABLE_PROCESS",
    "code": "CODE",
    "sub_graph": "SUB_GRAPH",
    "subgraph": "SUB_GRAPH",
    "business_track": "BUSINESS_TRACK",
    "businesstrack": "BUSINESS_TRACK",
}


def _source_node_type(spec):
    raw = spec.get("type") or spec.get("category")
    if not raw:
        raise ValueError(f"source node missing type/category: {spec}")
    key = str(raw).strip().lower().replace("-", "_")
    return _SOURCE_TYPE_ALIASES.get(key, str(raw).strip().upper())


def _source_key(spec, index):
    key = spec.get("key") or spec.get("name") or spec.get("title")
    if key:
        return str(key)
    return f"node_{index}"


def _source_title(spec, key):
    return spec.get("title") or spec.get("name") or key


def _source_get(spec, *names, default=None):
    for name in names:
        if name in spec and spec[name] is not None:
            return spec[name]
    return default


def _source_position(spec, index):
    pos = spec.get("position")
    if isinstance(pos, dict):
        return (pos.get("x", 0), pos.get("y", 0))
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        return (pos[0], pos[1])
    return ((index % 5) * 320, (index // 5) * 180)


def _has_source_position(spec):
    pos = spec.get("position")
    return isinstance(pos, dict) or (isinstance(pos, (list, tuple)) and len(pos) >= 2)


def _source_item_id_name(item, *, default_prefix="item"):
    if isinstance(item, str):
        name = item
        return _validate_title(name), name
    if not isinstance(item, dict):
        raise ValueError(f"branch item must be string or object, got {item!r}")
    name = item.get("name") or item.get("title") or item.get("id") or default_prefix
    item_id = item.get("id") or _validate_title(str(name))
    return str(item_id), str(name)


def _source_branch_lookup(branch_handles, node_key, label, handle):
    labels = {str(label), str(handle), _validate_title(str(label)), _validate_title(str(handle))}
    for candidate in labels:
        branch_handles[(node_key, candidate)] = str(handle)


def _merge_dict(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge_dict(dst[key], value)
        else:
            dst[key] = value
    return dst


def _apply_source_overrides(node, spec):
    if "node_id" in spec:
        node["id"] = str(spec["node_id"])
    if "id" in spec and spec.get("preserve_id"):
        node["id"] = str(spec["id"])
    if isinstance(spec.get("data"), dict):
        _merge_dict(node.setdefault("data", {}), spec["data"])
    if isinstance(spec.get("config"), dict):
        _merge_dict(node.setdefault("data", {}).setdefault("config", {}), spec["config"])
    if isinstance(spec.get("extra"), dict):
        _merge_dict(node, spec["extra"])
    return node


def _normalize_replies(replies, branch_handles, node_key):
    normalized = []
    for item in replies or []:
        item_id, name = _source_item_id_name(item, default_prefix="reply")
        normalized.append({"id": item_id, "name": name})
        _source_branch_lookup(branch_handles, node_key, name, item_id)
    return normalized


def _normalize_intents(intents, branch_handles, node_key):
    normalized = []
    for item in intents or []:
        if isinstance(item, str):
            item_id, name = _source_item_id_name(item, default_prefix="intent")
            entry = {"id": item_id, "name": name, "desc": ""}
        elif isinstance(item, dict):
            item_id, name = _source_item_id_name(item, default_prefix="intent")
            entry = dict(item)
            entry["id"] = item_id
            entry["name"] = name
        else:
            raise ValueError(f"intent item must be string or object, got {item!r}")
        if entry.get("intentId") is None and not str(entry.get("desc") or "").strip():
            raise ValueError(f"intent '{entry.get('name') or entry.get('id')}' in node '{node_key}' missing desc")
        normalized.append(entry)
        _source_branch_lookup(branch_handles, node_key, entry["name"], entry["id"])
    return normalized


def _apply_auto_layout(nodes, edges, locked_node_ids=None):
    """Lay out generated nodes by graph depth while preserving explicit positions."""
    locked_node_ids = set(locked_node_ids or [])
    node_ids = {n.get("id") for n in nodes}
    order = {n.get("id"): idx for idx, n in enumerate(nodes)}
    outgoing = {}
    indegree = {n.get("id"): 0 for n in nodes}
    for edge_obj in edges:
        source = edge_obj.get("source")
        target = edge_obj.get("target")
        if source not in node_ids or target not in node_ids:
            continue
        outgoing.setdefault(source, []).append(target)
        indegree[target] = indegree.get(target, 0) + 1

    start_ids = [
        n.get("id")
        for n in nodes
        if n.get("data", {}).get("category") == "START"
    ]
    roots = start_ids or [node_id for node_id, count in indegree.items() if count == 0]
    depth = {node_id: 0 for node_id in roots}
    queue = list(roots)
    remaining_indegree = dict(indegree)
    for root in roots:
        remaining_indegree[root] = 0

    while queue:
        source = queue.pop(0)
        for target in outgoing.get(source, []):
            depth[target] = max(depth.get(target, 0), depth.get(source, 0) + 1)
            remaining_indegree[target] -= 1
            if remaining_indegree[target] == 0:
                queue.append(target)

    columns = {}
    for node in nodes:
        node_id = node.get("id")
        columns.setdefault(depth.get(node_id, 0), []).append(node)

    for column_nodes in columns.values():
        column_nodes.sort(key=lambda n: order.get(n.get("id"), 0))

    x_gap = 360
    y_gap = 220
    for column, column_nodes in columns.items():
        for row, node in enumerate(column_nodes):
            if node.get("id") in locked_node_ids:
                continue
            node["position"] = {"x": column * x_gap, "y": row * y_gap}
    return nodes


def _normalize_cases(cases, branch_handles, node_key):
    normalized = []
    for item in cases or []:
        if isinstance(item, str):
            case_id, name = _source_item_id_name(item, default_prefix="case")
            entry = {"id": case_id, "name": name, "conditions": []}
        elif isinstance(item, dict):
            case_id, name = _source_item_id_name(item, default_prefix="case")
            entry = dict(item)
            entry["id"] = case_id
        else:
            raise ValueError(f"case item must be string or object, got {item!r}")
        normalized.append(entry)
        _source_branch_lookup(branch_handles, node_key, entry.get("name", entry["id"]), entry["id"])
    return normalized


def _normalize_next_steps(next_steps, branch_handles, node_key):
    normalized = []
    for item in next_steps or []:
        if isinstance(item, str):
            raise ValueError(
                f"AGENT '{node_key}' next_steps item '{item}' must be an object with id/title/prompt; "
                "string shorthand cannot pass frontend validation"
            )
        elif isinstance(item, dict):
            title = item.get("title") or item.get("name") or item.get("id") or "Step"
            step_id = item.get("id") or _validate_title(str(title))
            entry = dict(item)
            entry["id"] = str(step_id)
            entry["title"] = str(title)
        else:
            raise ValueError(f"next step must be string or object, got {item!r}")
        normalized.append(entry)
        _source_branch_lookup(branch_handles, node_key, entry["title"], entry["id"])
    return normalized


def _source_extract_items(items):
    normalized = []
    aliases = {}
    for item in items or []:
        entry = dict(item)
        alias = entry.get("alias") or entry.get("key") or entry.get("id")
        entry["id"] = entry.get("graph_id") or entry.get("graphId") or _uid()
        if alias:
            aliases[str(alias)] = entry["id"]
        normalized.append(entry)
    return normalized, aliases


def _resolve_extract_alias(extract_aliases_by_key, node_key, extract_id):
    if extract_id is None:
        return extract_id
    return (extract_aliases_by_key or {}).get(node_key, {}).get(str(extract_id), extract_id)


def _normalize_variable_selector(selector, key_to_node, extract_aliases_by_key=None):
    if isinstance(selector, list):
        if selector and selector[0] == "TOOL_KEY":
            node = key_to_node[selector[1]]
            return var_tool_output(node, *selector[2:])
        if selector and selector[0] == "NODE_KEY":
            return var_node(key_to_node[selector[1]])
        if selector and selector[0] == "EXTRACT_KEY":
            extract_id = _resolve_extract_alias(extract_aliases_by_key, selector[1], selector[2])
            return var_extract(key_to_node[selector[1]], extract_id)
        return selector
    if not isinstance(selector, dict):
        return selector
    if "tool" in selector:
        path = selector.get("path") or selector.get("field") or []
        if isinstance(path, str):
            if "." in path:
                raise ValueError(
                    f"nested TOOL output '{path}' must use path segments, for example "
                    f"{{'tool': '{selector['tool']}', 'path': {path.split('.')}}}"
                )
            path = [path]
        return var_tool_output(key_to_node[selector["tool"]], *path)
    if "tool_status" in selector:
        return var_tool_status(key_to_node[selector["tool_status"]])
    if "node" in selector:
        return var_node(key_to_node[selector["node"]])
    if "llm" in selector:
        node_key = selector["llm"]
        path = selector.get("path") or selector.get("field") or []
        if isinstance(path, str):
            path = [path]
        if not path:
            path = ["text"]
        node = key_to_node[node_key]
        node_id = node["id"]
        if path[0] in {"text", "structured_output"}:
            return ["LLM", node_id, *path]
        structured_output = (node.get("data", {}).get("config", {}).get("llm", {})
                             .get("structuredOutput", {}))
        if structured_output.get("enabled"):
            return ["LLM", node_id, "structured_output", *path]
        raise ValueError(
            f"LLM selector for '{node_key}' must use field='text', or enable structured_output "
            f"before selecting structured fields"
        )
    if "code" in selector:
        field_name = selector.get("field") or selector.get("field_name") or selector.get("output")
        if not isinstance(field_name, str) or not field_name:
            raise ValueError(f"CODE selector for '{selector['code']}' missing field")
        return var_code_output(key_to_node[selector["code"]], field_name)
    if "extract" in selector:
        node_key = selector["extract"]
        extract_id = (
            selector.get("alias")
            or selector.get("id")
            or selector.get("extract_id")
            or selector.get("variable_id")
            or selector.get("variable")
        )
        return var_extract(
            key_to_node[node_key],
            _resolve_extract_alias(extract_aliases_by_key, node_key, extract_id),
        )
    if "system" in selector:
        system = selector["system"]
        if isinstance(system, dict):
            path = system.get("path")
            if path is None:
                path = system.get("field_id") or system.get("id")
            return var_system(system.get("category", "Custom"), path)
        if isinstance(system, list) and len(system) >= 2:
            path = system[1] if len(system) == 2 and isinstance(system[1], list) else system[1:]
            return var_system(system[0], path)
    return selector


_DYNAMIC_TEMPLATE_PREFIX = "[[var:"
_DYNAMIC_TEMPLATE_SUFFIX = "]]"
_DYNAMIC_TEMPLATE_DECODER = json.JSONDecoder()


def _is_source_selector_shortcut(selector):
    if isinstance(selector, list):
        return (
            bool(selector)
            and isinstance(selector[0], str)
            and selector[0] in {"TOOL_KEY", "NODE_KEY", "EXTRACT_KEY"}
        )
    if not isinstance(selector, dict):
        return False
    return (
        isinstance(selector.get("tool"), str)
        or isinstance(selector.get("tool_status"), str)
        or isinstance(selector.get("node"), str)
        or isinstance(selector.get("llm"), str)
        or isinstance(selector.get("code"), str)
        or isinstance(selector.get("extract"), str)
        or isinstance(selector.get("system"), (dict, list))
    )


def _resolve_dynamic_template_selectors(text, key_to_node, extract_aliases_by_key=None):
    """Replace source selector shortcuts embedded in [[var:...]] templates.

    ChatFlow persists a variable template as ``[[var:<selector-array>]]``. Source
    JSON may use the same selector shortcuts as other fields so generated node IDs
    do not have to be guessed. Invalid templates are deliberately left unchanged:
    the graph validator can report the original text without hiding it.
    """
    if not isinstance(text, str) or _DYNAMIC_TEMPLATE_PREFIX not in text:
        return text

    rendered = []
    cursor = 0
    while True:
        start = text.find(_DYNAMIC_TEMPLATE_PREFIX, cursor)
        if start < 0:
            rendered.append(text[cursor:])
            break
        rendered.append(text[cursor:start])
        json_start = start + len(_DYNAMIC_TEMPLATE_PREFIX)
        try:
            selector, json_end = _DYNAMIC_TEMPLATE_DECODER.raw_decode(text, json_start)
        except json.JSONDecodeError:
            rendered.append(text[start:])
            break
        if not text.startswith(_DYNAMIC_TEMPLATE_SUFFIX, json_end):
            rendered.append(text[start:])
            break
        end = json_end + len(_DYNAMIC_TEMPLATE_SUFFIX)
        if _is_source_selector_shortcut(selector):
            selector = _normalize_variable_selector(selector, key_to_node, extract_aliases_by_key)
            rendered.append(
                f"{_DYNAMIC_TEMPLATE_PREFIX}{json.dumps(selector, ensure_ascii=False, separators=(',', ':'))}{_DYNAMIC_TEMPLATE_SUFFIX}"
            )
        else:
            rendered.append(text[start:end])
        cursor = end
    return "".join(rendered)


def _resolve_source_selectors(value, key_to_node, extract_aliases_by_key=None, current_key=None):
    if isinstance(value, str):
        return _resolve_dynamic_template_selectors(value, key_to_node, extract_aliases_by_key)
    if isinstance(value, dict):
        if "variableSelector" in value:
            value["variableSelector"] = _normalize_variable_selector(value["variableSelector"], key_to_node, extract_aliases_by_key)
        elif _is_source_selector_shortcut(value):
            return _normalize_variable_selector(value, key_to_node, extract_aliases_by_key)
        for child_key, child_value in list(value.items()):
            value[child_key] = _resolve_source_selectors(child_value, key_to_node, extract_aliases_by_key, current_key)
    elif isinstance(value, list):
        if _is_source_selector_shortcut(value):
            return _normalize_variable_selector(value, key_to_node, extract_aliases_by_key)
        if value and value[0] == "SELF" and len(value) == 2 and current_key:
            return ["SELF", _resolve_extract_alias(extract_aliases_by_key, current_key, value[1])]
        for idx, item in enumerate(value):
            value[idx] = _resolve_source_selectors(item, key_to_node, extract_aliases_by_key, current_key)
    return value


def _build_source_node(spec, index, key, branch_handles):
    position = _source_position(spec, index)
    if isinstance(spec.get("node"), dict):
        node = dict(spec["node"])
        node.setdefault("id", _uid())
        node.setdefault("type", "CUSTOM")
        node.setdefault("position", {"x": position[0], "y": position[1]})
        return _apply_source_overrides(node, spec)

    node_type = _source_node_type(spec)
    title = _source_title(spec, key)

    if node_type == "START":
        node = start_node(position=position)
    elif node_type == "FINISH":
        node = finish_node(title=title, position=position)
    elif node_type == "REPLY":
        node = reply_node(
            title,
            _source_get(spec, "prompt", "text", "message", default=""),
            reply_type=_source_get(spec, "reply_type", "replyType", "type_value", default="PROMPT"),
            template_id=_source_get(spec, "template_id", "templateId"),
            template_content=_source_get(spec, "template_content", "templateContent"),
            ai_field_ids=_source_get(spec, "ai_field_ids", "aiFieldIds"),
            use_long_memory=_source_get(spec, "use_long_memory", "useLongMemory", default=False),
            disable_prev_node_results=_source_get(
                spec, "disable_prev_node_results", "disablePrevNodeResult", default=False
            ),
            position=position,
        )
    elif node_type == "AGENT":
        next_steps = _normalize_next_steps(_source_get(spec, "next_steps", "nextStep"), branch_handles, key)
        node = agent_node(
            title,
            spec.get("prompt") or "",
            plugins=_source_get(spec, "plugins", "usedPlugins"),
            ai_field_ids=_source_get(spec, "ai_field_ids", "aiFieldIds"),
            enable_kb=_source_get(spec, "enable_kb", "enableKnowledgeBase", default=False),
            kb_dirs=_source_get(spec, "kb_dirs", "knowledgeDirectoryIds"),
            knowledge_keyword_ids=_source_get(spec, "knowledge_keyword_ids", "knowledgeKeywordIds"),
            knowledge_keyword_selector=_source_get(
                spec, "knowledge_keyword_selector", "knowledgeKeywordSelector"
            ),
            max_rounds=_source_get(spec, "max_rounds", "maxRounds", default=10),
            max_rounds_exceeded_action=_source_get(
                spec, "max_rounds_exceeded_action", "maxRoundsExceededAction",
                default="TRANSFER_TO_HUMAN",
            ),
            next_step=next_steps or None,
            use_long_memory=_source_get(spec, "use_long_memory", "useLongMemory", default=False),
            disable_prev_node_results=_source_get(
                spec, "disable_prev_node_results", "disablePrevNodeResult", default=False
            ),
            position=position,
        )
    elif node_type == "LLM":
        unsupported_fields = [
            field for field in ("ai_field_ids", "aiFieldIds", "model_id", "modelId", "outputs", "output_variables", "outputVariables")
            if field in spec
        ]
        if unsupported_fields:
            raise ValueError(
                "LLM source fields are no longer supported by the current ChatFlow runtime: "
                f"{', '.join(unsupported_fields)}. Use [[var:...]] templates, vision, and structured_output instead."
            )
        node = llm_node(
            title,
            spec.get("prompt") or "",
            history_round_limit=_source_get(spec, "history_round_limit", "historyRoundLimit", default=0),
            use_long_memory=_source_get(spec, "use_long_memory", "useLongMemory", default=False),
            vision=spec.get("vision"),
            structured_output=_source_get(spec, "structured_output", "structuredOutput"),
            position=position,
        )
    elif node_type == "IF_ELSE":
        node = if_else_node(title, _normalize_cases(spec.get("cases"), branch_handles, key), position=position)
    elif node_type == "TOOL":
        tool = spec.get("tool") if isinstance(spec.get("tool"), dict) else {}
        tool_id = _source_get(spec, "tool_id", "toolId", default=tool.get("id"))
        if tool_id is None:
            raise ValueError(f"TOOL node '{key}' missing tool_id")
        node = tool_node(
            title,
            tool_id,
            input_params=_source_get(spec, "input_params", "inputParams"),
            enable_action_status=_source_get(spec, "enable_action_status", "enableActionStatus", default=False),
            tool_type=_source_get(spec, "tool_type", "toolType", default=tool.get("type", "EXTERNAL_HTTP_CALL")),
            position=position,
        )
    elif node_type == "QUESTION":
        replies = spec.get("replies") or []
        mode = _source_get(spec, "mode", "collect_type", default="USER_REPLY" if replies else "VARIABLE")
        node = question_node(
            title,
            _source_get(spec, "question", "prompt", default=""),
            mode=mode,
            variables=spec.get("variables"),
            replies=_normalize_replies(replies, branch_handles, key),
            max_rounds=_source_get(spec, "max_rounds", "maxRounds", default=5),
            question_type=_source_get(spec, "question_type", "questionType", default="PROMPT"),
            question_template_id=_source_get(spec, "question_template_id", "questionTemplateId"),
            condition=_source_get(spec, "condition", default="AND"),
            use_chat_history=_source_get(spec, "use_chat_history", "useChatHistory", default=True),
            position=position,
        )
    elif node_type == "COLLECT_ORDER":
        node = collect_order_node(
            title=title,
            max_rounds=_source_get(spec, "max_rounds", "maxRounds", default=5),
            exceptions=_source_get(spec, "collect_order_exception", "collectOrderException", default=[]),
            position=position,
        )
    elif node_type == "TRANSFER_TO_HUMAN":
        node = transfer_human_node(
            title=title,
            prompt=spec.get("prompt", ""),
            transfer_type=_source_get(spec, "transfer_type", "type_value", "transferType", default="NO_REPLY"),
            template_id=_source_get(spec, "template_id", "templateId"),
            ai_field_ids=_source_get(spec, "ai_field_ids", "aiFieldIds"),
            disable_prev_node_results=_source_get(
                spec, "disable_prev_node_results", "disablePrevNodeResult", default=False
            ),
            explain=spec.get("explain"),
            position=position,
        )
    elif node_type == "HUMAN_REVIEW":
        node = human_review_node(
            title=title,
            method=spec.get("method", "approval"),
            description=spec.get("description", ""),
            fields=spec.get("fields"),
            midway_message_strategy=_source_get(
                spec, "midway_message_strategy", "midwayMessageStrategy", default="ignore"
            ),
            position=position,
        )
        _source_branch_lookup(branch_handles, key, "AGREE", "AGREE")
        _source_branch_lookup(branch_handles, key, "REJECT", "REJECT")
    elif node_type == "INTENT":
        node = intent_node(
            title,
            _normalize_intents(spec.get("intents"), branch_handles, key),
            prompt=spec.get("prompt"),
            history_round_limit=_source_get(
                spec, "history_round_limit", "historyRoundLimit", default=None
            ),
            use_chat_history=_source_get(spec, "use_chat_history", "useChatHistory", default=True),
            position=position,
        )
        _source_branch_lookup(branch_handles, key, "OTHER", "OTHER")
    elif node_type == "KNOWLEDGE_REPLY":
        node = knowledge_reply_node(
            title,
            spec.get("prompt") or "",
            _source_get(spec, "kb_dirs", "knowledgeDirectoryIds", default=None),
            max_rounds=_source_get(spec, "max_rounds", "maxRounds", default=10),
            disable_prev_node_results=_source_get(
                spec, "disable_prev_node_results", "disablePrevNodeResult", default=False
            ),
            position=position,
        )
        _source_branch_lookup(branch_handles, key, "RESOLVED", "RESOLVED")
        _source_branch_lookup(branch_handles, key, "UNRESOLVED", "UNRESOLVED")
    elif node_type == "RAG_REPLY":
        node = rag_reply_node(
            title,
            spec.get("prompt") or "",
            _source_get(spec, "kb_dirs", "knowledgeDirectoryIds", default=[]),
            knowledge_keyword_ids=_source_get(spec, "knowledge_keyword_ids", "knowledgeKeywordIds"),
            knowledge_keyword_selector=_source_get(
                spec, "knowledge_keyword_selector", "knowledgeKeywordSelector"
            ),
            customize_query=_source_get(spec, "customize_query", "customizeQuery", default=False),
            query_selector=_source_get(spec, "query_selector", "querySelector"),
            disable_prev_node_results=_source_get(
                spec, "disable_prev_node_results", "disablePrevNodeResult", default=False
            ),
            position=position,
        )
        _source_branch_lookup(branch_handles, key, "TRUE", "TRUE")
        _source_branch_lookup(branch_handles, key, "LACK_KNOWLEDGE", "LACK_KNOWLEDGE")
    elif node_type == "VARIABLE_EXTRACT":
        variables, extract_aliases = _source_extract_items(spec.get("variables") or spec.get("extracts") or [])
        node = variable_extract_node(
            title,
            variables,
            additional_data=_source_get(spec, "additional_data", "additionalData", default=[]),
            use_chat_history=_source_get(spec, "use_chat_history", "useChatHistory", default=False),
            position=position,
        )
        if extract_aliases:
            node["_sourceExtractAliases"] = extract_aliases
    elif node_type == "VARIABLE_ASSIGNMENT":
        node = variable_assignment_node(title, spec.get("assignments") or [], position=position)
    elif node_type == "VARIABLE_PROCESS":
        variables, extract_aliases = _source_extract_items(spec.get("variables") or spec.get("extracts") or [])
        node = variable_process_node(
            title,
            variables=variables,
            assignments=spec.get("assignments") or [],
            additional_data=_source_get(spec, "additional_data", "additionalData", default=[]),
            use_chat_history=_source_get(spec, "use_chat_history", "useChatHistory", default=False),
            position=position,
        )
        if extract_aliases:
            node["_sourceExtractAliases"] = extract_aliases
    elif node_type == "CODE":
        node = code_node(
            title,
            _source_get(spec, "source_code", "sourceCode", "code", default=""),
            inputs=spec.get("inputs") or [],
            outputs=spec.get("outputs") or [],
            position=position,
        )
    elif node_type == "SUB_GRAPH":
        node = sub_graph_node(
            title,
            _source_get(spec, "target_agent_id", "targetAgentId", "agent_id", "agentId"),
            context_turn_limit=_source_get(spec, "context_turn_limit", "contextTurnLimit", default=5),
            position=position,
        )
    elif node_type == "BUSINESS_TRACK":
        node = business_track_node(
            title,
            _source_get(spec, "trace_events", "traceEvents"),
            position=position,
        )
    else:
        raise ValueError(f"unsupported source node type '{node_type}' for key '{key}'")

    return _apply_source_overrides(node, spec)


def _ensure_special_source_node(special_key, nodes, key_to_node):
    if special_key in key_to_node:
        return key_to_node[special_key]
    position = (len(nodes) % 5 * 320, len(nodes) // 5 * 180)
    if special_key == "$start":
        node = start_node(position=position)
    elif special_key == "$finish":
        node = finish_node(title="Finish", position=position)
    elif special_key == "$transfer":
        node = transfer_human_node(title="Transfer_To_Human", position=position)
    else:
        raise ValueError(f"unknown special node key: {special_key}")
    nodes.append(node)
    key_to_node[special_key] = node
    return node


def _compile_source_to_graph(source, client=None, ai_fields=None, agent_ai_fields=None):
    """Compile agent-authored source JSON into a full chatFlowGraph."""
    if not isinstance(source, dict):
        raise ValueError("source must be a JSON object")
    source_nodes = source.get("nodes") or []
    if not isinstance(source_nodes, list) or not source_nodes:
        raise ValueError("source.nodes must be a non-empty list")

    nodes = []
    edges = []
    key_to_node = {}
    node_id_to_key = {}
    extract_aliases_by_key = {}
    branch_handles = {}
    explicit_position_node_ids = set()

    for index, spec in enumerate(source_nodes):
        if not isinstance(spec, dict):
            raise ValueError(f"source node at index {index} must be an object")
        key = _source_key(spec, index)
        if key in key_to_node:
            raise ValueError(f"duplicate source node key: {key}")
        node = _build_source_node(spec, index, key, branch_handles)
        source_extract_aliases = node.pop("_sourceExtractAliases", None)
        if source_extract_aliases:
            extract_aliases_by_key[key] = source_extract_aliases
        nodes.append(node)
        key_to_node[key] = node
        node_id_to_key[node["id"]] = key
        if _has_source_position(spec):
            explicit_position_node_ids.add(node["id"])

    source_edges = list(source.get("edges") or [])
    if source.get("entry") and not any(n.get("data", {}).get("category") == "START" for n in nodes):
        _ensure_special_source_node("$start", nodes, key_to_node)
        source_edges.insert(0, {"from": "$start", "to": source["entry"]})

    for node in nodes:
        _resolve_source_selectors(
            node,
            key_to_node,
            extract_aliases_by_key=extract_aliases_by_key,
            current_key=node_id_to_key.get(node["id"]),
        )

    for edge_spec in source_edges:
        if not isinstance(edge_spec, dict):
            raise ValueError(f"source edge must be an object, got {edge_spec!r}")
        src_key = _source_get(edge_spec, "from", "source")
        tgt_key = _source_get(edge_spec, "to", "target")
        if src_key in {"$start", "$finish", "$transfer"}:
            _ensure_special_source_node(src_key, nodes, key_to_node)
        if tgt_key in {"$start", "$finish", "$transfer"}:
            _ensure_special_source_node(tgt_key, nodes, key_to_node)
        if src_key not in key_to_node:
            raise ValueError(f"edge source key not found: {src_key}")
        if tgt_key not in key_to_node:
            raise ValueError(f"edge target key not found: {tgt_key}")
        handle = _source_get(edge_spec, "source_handle", "sourceHandle", "handle")
        if handle is None and "on" in edge_spec:
            on = str(edge_spec["on"])
            handle = branch_handles.get((src_key, on)) or branch_handles.get((src_key, _validate_title(on))) or on
        if handle is None:
            handle = "SOURCE"
        edges.append(edge(key_to_node[src_key], key_to_node[tgt_key], source_handle=str(handle)))

    _apply_auto_layout(nodes, edges, locked_node_ids=explicit_position_node_ids)
    return build_graph(
        nodes,
        edges,
        client=client,
        ai_fields=ai_fields,
        agent_ai_fields=agent_ai_fields,
    )


def _merge_source_fragments(fragment_files, integration):
    """Merge keyed source fragments into one source document before compilation.

    Fragments contain only nodes and edges internal to one flow block. The
    integration document owns the final entry and cross-block edges. Merging
    source, rather than compiled graphs, keeps generated node IDs, START and
    layout deterministic in the one final compiler pass.
    """
    if not fragment_files:
        raise ValueError("at least one source fragment is required")
    if not isinstance(integration, dict):
        raise ValueError("integration document must be a JSON object")
    if "nodes" in integration:
        raise ValueError("integration document must not define nodes; put nodes in source fragments")
    entry = integration.get("entry")
    if not isinstance(entry, str) or not entry.strip():
        raise ValueError("integration document requires a non-empty entry node key")
    connector_edges = integration.get("edges") or []
    if not isinstance(connector_edges, list):
        raise ValueError("integration.edges must be a list")

    merged = {"entry": entry.strip(), "nodes": [], "edges": []}
    node_keys = set()
    node_origins = {}
    edge_signatures = set()
    fragment_edges = []

    def add_edge(edge_spec, origin):
        if not isinstance(edge_spec, dict):
            raise ValueError(f"{origin} edge must be an object")
        source_key = _source_get(edge_spec, "from", "source")
        target_key = _source_get(edge_spec, "to", "target")
        if not isinstance(source_key, str) or not source_key.strip():
            raise ValueError(f"{origin} edge missing source key")
        if not isinstance(target_key, str) or not target_key.strip():
            raise ValueError(f"{origin} edge missing target key")
        signature = json.dumps(edge_spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if signature in edge_signatures:
            raise ValueError(f"duplicate source edge while merging: {source_key} -> {target_key}")
        edge_signatures.add(signature)
        merged["edges"].append(dict(edge_spec))
        return source_key.strip(), target_key.strip()

    for fragment_file in fragment_files:
        path = Path(fragment_file)
        fragment = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(fragment, dict):
            raise ValueError(f"source fragment must be a JSON object: {path}")
        if "entry" in fragment:
            raise ValueError(
                f"source fragment must not define entry; integration owns the final entry: {path}"
            )
        nodes = fragment.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise ValueError(f"source fragment requires a non-empty nodes list: {path}")
        edges = fragment.get("edges") or []
        if not isinstance(edges, list):
            raise ValueError(f"source fragment edges must be a list: {path}")
        fragment_node_keys = set()
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                raise ValueError(f"source fragment node must be an object: {path}[{index}]")
            key = node.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"source fragment node requires an explicit key: {path}[{index}]")
            key = key.strip()
            if key in node_keys:
                raise ValueError(f"duplicate source node key while merging: {key}")
            node_keys.add(key)
            fragment_node_keys.add(key)
            node_origins[key] = str(path)
            merged["nodes"].append(dict(node))
        for edge_spec in edges:
            source_key, target_key = add_edge(edge_spec, str(path))
            fragment_edges.append((source_key, target_key, str(path), fragment_node_keys))

    terminal_keys = {"$finish", "$transfer"}
    for source_key, target_key, origin, fragment_node_keys in fragment_edges:
        if source_key not in fragment_node_keys:
            raise ValueError(
                f"source fragment edge must start at a node in the same fragment: {origin}: {source_key}"
            )
        if target_key not in fragment_node_keys and target_key not in terminal_keys:
            raise ValueError(
                "source fragment edge crosses flow blocks; put cross-block edges in integration: "
                f"{origin}: {source_key} -> {target_key}"
            )

    for edge_spec in connector_edges:
        source_key, target_key = add_edge(edge_spec, "integration")
        if source_key not in node_keys:
            raise ValueError(f"integration edge source key not found in fragments: {source_key}")
        if target_key not in node_keys and target_key not in terminal_keys:
            raise ValueError(f"integration edge target key not found in fragments: {target_key}")
        if (
            source_key in node_origins
            and target_key in node_origins
            and node_origins[source_key] == node_origins[target_key]
        ):
            raise ValueError(
                "integration edge stays inside one source fragment; put it in that fragment instead: "
                f"{source_key} -> {target_key}"
            )

    if merged["entry"] not in node_keys:
        raise ValueError(f"integration entry key not found in fragments: {merged['entry']}")
    for edge_spec in merged["edges"]:
        source_key = _source_get(edge_spec, "from", "source")
        target_key = _source_get(edge_spec, "to", "target")
        if source_key not in node_keys:
            raise ValueError(f"merged edge source key not found in fragments: {source_key}")
        if target_key not in node_keys and target_key not in terminal_keys:
            raise ValueError(f"merged edge target key not found in fragments: {target_key}")
    return merged


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _normalize_chatflow_graph_response(response):
    """Return the chatFlowGraph dict from direct or wrapped API responses."""
    if not isinstance(response, dict):
        raise ValueError(f"chatflow graph response must be a dict, got {type(response).__name__}")
    graph = response.get("graph") if isinstance(response.get("graph"), dict) else response
    if (
        not isinstance(graph, dict)
        or not isinstance(graph.get("nodes"), list)
        or not isinstance(graph.get("edges"), list)
    ):
        raise ValueError("chatFlowGraph must be a dict with nodes and edges")
    return graph


def _agent_from_detail(detail):
    if isinstance(detail, list):
        return detail[0] if detail else None
    return detail if isinstance(detail, dict) else None


def _resolve_agent_id(client, *, agent_id=None, agent_name=None):
    if agent_id is not None:
        return int(agent_id), None
    if not agent_name:
        raise ValueError("provide --agent-id or --agent-name")

    agents = client.list_agents(category="text")
    if not isinstance(agents, list):
        raise ValueError("list_agents did not return a list")

    exact = [a for a in agents if a.get("name") == agent_name]
    matches = exact or [a for a in agents if agent_name.lower() in str(a.get("name", "")).lower()]
    if not matches:
        raise ValueError(f"CHAT_FLOW agent not found by name: {agent_name}")
    chatflow_matches = [a for a in matches if a.get("type") == "CHAT_FLOW"]
    if len(chatflow_matches) != 1:
        names = [f"{a.get('id')}:{a.get('name')}:{a.get('type')}" for a in chatflow_matches or matches]
        raise ValueError(f"agent name is ambiguous or not CHAT_FLOW: {names}")
    return int(chatflow_matches[0]["id"]), chatflow_matches[0]


def _summarize_graph(graph, *, agent_id=None, agent_name=None, out_file=None):
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    return {
        "agent_id": agent_id,
        "agent_name": agent_name,
        "out_file": str(out_file) if out_file else None,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": [
            {
                "id": node.get("id"),
                "category": node.get("data", {}).get("category"),
                "title": node.get("data", {}).get("title", ""),
            }
            for node in nodes
        ],
        "edges": [
            {
                "source": edge.get("source"),
                "sourceHandle": edge.get("sourceHandle"),
                "target": edge.get("target"),
                "targetHandle": edge.get("targetHandle"),
            }
            for edge in edges
        ],
    }


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_graph_file(path):
    return _normalize_chatflow_graph_response(json.loads(Path(path).read_text(encoding="utf-8")))


def _bootstrap_cli_runtime():
    """Load runtime paths only for direct CLI execution, not library import."""
    lib_root = os.environ.get("SOLVEA_LIB_DIR")
    if lib_root:
        skill_runtime = os.path.join(lib_root, "skill-runtime")
        if skill_runtime not in sys.path:
            sys.path.insert(0, skill_runtime)
        import bootstrap  # type: ignore
        return bootstrap
    return None


def _get_cli_client(env, project_id):
    _bootstrap_cli_runtime()
    from client import SolveaClient  # type: ignore
    return SolveaClient(env=env, project_id=project_id)


def _safe_list_resource(label, loader):
    try:
        return loader(), None
    except Exception as exc:
        return None, (
            f"{label} unavailable; skipped related remote metadata validation. "
            f"This is a remote resource lookup issue, not necessarily a graph schema error: {exc}"
        )


def _append_resource_warnings(validation, warnings):
    if warnings:
        validation.setdefault("warnings", []).extend(warnings)
    return validation


def _default_output_path(prefix, agent_id):
    runtime = _bootstrap_cli_runtime()
    if runtime is not None:
        out_dir = runtime.STATE_DIR
    else:
        out_dir = Path("workspace") / "state" / "chatflow"
    return out_dir / f"{prefix}_{agent_id}.json"


def _workspace_virtual_path(path):
    runtime = _bootstrap_cli_runtime()
    path = Path(path)
    if runtime is None:
        return path
    try:
        rel = path.resolve().relative_to(runtime.WORKSPACE.resolve())
    except ValueError:
        return path
    return Path("/workspace") / rel


def _validate_graph_file(graph, ai_fields=None, plugins=None, agent_ai_fields=None, templates=None):
    _bootstrap_cli_runtime()
    from validate_graph import validate_graph  # type: ignore
    return validate_graph(
        graph,
        ai_fields=ai_fields,
        plugins=plugins,
        agent_ai_fields=agent_ai_fields,
        templates=templates,
    )


_AGENT_SYSTEM_PLUGIN_TYPES = {"TEMPLATE_REPLY", "TRANSFER_TO_HUMAN"}


def _normalize_chatflow_plugin_items(value):
    """Flatten the grouped Chatflow plugin response used by the PE editor."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []

    if "SYSTEM" in value or "MANUAL" in value:
        items = []
        for group in ("SYSTEM", "MANUAL"):
            items.extend(_normalize_chatflow_plugin_items(value.get(group)))
        return items
    for key in ("data", "list", "records", "items"):
        if key in value:
            return _normalize_chatflow_plugin_items(value.get(key))
    return []


def _plugin_integer_id(plugin):
    value = plugin.get("id") if isinstance(plugin, dict) else None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value)
    return None


def _agent_system_plugin_requirements(graph):
    requirements = []
    for node in graph.get("nodes", []):
        data = node.get("data", {})
        if data.get("category") != "AGENT":
            continue
        display_prompt = ((data.get("config") or {}).get("agentData") or {}).get("displayPrompt") or ""
        try:
            blocks = _parse_library_blocks(display_prompt)
        except ValueError:
            # validate_graph reports the concrete prompt error. Resource lookup
            # should not replace it with a catalog failure first.
            continue
        required_types = set()
        for block in blocks:
            fields = block["fields"]
            if block["type"] == "tool" and fields.get("tool") == "template_reply":
                required_types.add("TEMPLATE_REPLY")
            elif block["type"] == "transferHuman":
                required_types.add("TRANSFER_TO_HUMAN")
        if required_types:
            requirements.append((node, required_types))
    return requirements


def _get_chatflow_plugin_catalog(client):
    response = client.list_chatflow_plugins(for_agent_node=True)
    return _normalize_chatflow_plugin_items(response)


def _bind_agent_system_plugins(graph, plugin_catalog):
    """Bind PE system actions to the project-specific Chatflow plugin IDs."""
    requirements = _agent_system_plugin_requirements(graph)
    if not requirements:
        return graph

    plugins_by_type = {}
    for plugin in _normalize_chatflow_plugin_items(plugin_catalog):
        plugin_type = str(plugin.get("type") or "").upper()
        plugin_id = _plugin_integer_id(plugin)
        if plugin_type in _AGENT_SYSTEM_PLUGIN_TYPES and plugin_id is not None:
            plugins_by_type.setdefault(plugin_type, plugin_id)

    for node, required_types in requirements:
        missing = sorted(required_types - set(plugins_by_type))
        if missing:
            title = node.get("data", {}).get("title") or node.get("id")
            raise ValueError(
                f"AGENT '{title}' requires Chatflow system plugin type(s) {missing}, "
                "but /api_v2/gpt/chatflow/queryPlugin did not return them for forAgentNode=true"
            )
        agent_data = node["data"]["config"]["agentData"]
        used_plugins = agent_data.setdefault("usedPlugins", [])
        for plugin_type in sorted(required_types):
            plugin_id = plugins_by_type[plugin_type]
            if plugin_id not in used_plugins:
                used_plugins.append(plugin_id)
    return graph


def _get_graph_plugin_details(client, graph, plugin_catalog=None):
    # TOOL nodes serialize plugin ids as strings, while AGENT.usedPlugins uses
    # integers. Normalize both before de-duplicating. System action ids come
    # from the Chatflow catalog; the legacy AP endpoint cannot resolve them.
    requirements = _agent_system_plugin_requirements(graph)
    required_system_types = set().union(
        *(required_types for _, required_types in requirements)
    ) if requirements else set()

    tool_ids = set()
    agent_plugin_ids = set()
    for node in graph.get("nodes", []):
        data = node.get("data", {})
        config = data.get("config", {})
        if data.get("category") == "TOOL":
            tool_id = (config.get("tool") or {}).get("id")
            if isinstance(tool_id, str) and tool_id.isdecimal():
                tool_id = int(tool_id)
            if isinstance(tool_id, int) and not isinstance(tool_id, bool) and tool_id > 0:
                tool_ids.add(tool_id)

        if data.get("category") != "AGENT":
            continue
        agent_data = config.get("agentData") or {}
        for plugin_id in agent_data.get("usedPlugins") or []:
            if (
                isinstance(plugin_id, int)
                and not isinstance(plugin_id, bool)
                and plugin_id != 0
            ):
                agent_plugin_ids.add(plugin_id)
                if plugin_id > 0:
                    tool_ids.add(plugin_id)

    if (
        required_system_types
        or any(plugin_id < 0 for plugin_id in agent_plugin_ids)
    ) and plugin_catalog is None:
        plugin_catalog = _get_chatflow_plugin_catalog(client)
    catalog_items = _normalize_chatflow_plugin_items(plugin_catalog)
    catalog_by_id = {
        str(plugin_id): plugin
        for plugin in catalog_items
        if (plugin_id := _plugin_integer_id(plugin)) is not None
    }
    details_by_id = {}
    for plugin in catalog_items:
        plugin_type = str(plugin.get("type") or "").upper()
        plugin_id = _plugin_integer_id(plugin)
        if plugin_id is not None and (
            plugin_type in required_system_types
            or (
                plugin_id in agent_plugin_ids
                and plugin_type in _AGENT_SYSTEM_PLUGIN_TYPES
            )
        ):
            details_by_id[str(plugin_id)] = plugin
    details = []
    for tool_id in sorted(tool_ids):
        catalog_plugin = catalog_by_id.get(str(tool_id))
        if catalog_plugin and str(catalog_plugin.get("type") or "").upper() in _AGENT_SYSTEM_PLUGIN_TYPES:
            details_by_id[str(tool_id)] = catalog_plugin
            continue
        response = client.get_plugin(tool_id)
        if isinstance(response, list):
            details.extend(item for item in response if isinstance(item, dict))
        elif isinstance(response, dict):
            details.append(response)
    for item in details:
        plugin_id = _plugin_integer_id(item)
        if plugin_id is not None:
            details_by_id[str(plugin_id)] = item
    return list(details_by_id.values())


def _safe_get_graph_plugin_details(client, graph, plugin_catalog=None):
    return _safe_list_resource(
        "Plugin metadata",
        lambda: _get_graph_plugin_details(
            client,
            graph,
            plugin_catalog=plugin_catalog,
        ),
    )


def _graph_template_ids(graph):
    template_ids = set()

    def add_template_id(value):
        try:
            template_id = int(value)
        except (TypeError, ValueError):
            return
        if template_id > 0:
            template_ids.add(template_id)

    for node in graph.get("nodes", []):
        data = node.get("data", {})
        config = data.get("config", {})
        category = data.get("category")
        if category == "REPLY":
            reply = config.get("replyContent") or {}
            if reply.get("type") == "TEMPLATE" and reply.get("templateId"):
                add_template_id(reply["templateId"])
        elif category == "TRANSFER_TO_HUMAN":
            transfer = config.get("transferToHuman") or {}
            if transfer.get("type") == "TEMPLATE" and transfer.get("templateId"):
                add_template_id(transfer["templateId"])
        elif category == "QUESTION":
            collect = config.get("collectInfo") or {}
            if collect.get("questionType") == "TEMPLATE" and collect.get("questionTemplateId"):
                add_template_id(collect["questionTemplateId"])
        elif category == "COLLECT_ORDER":
            for item in config.get("collectOrderException") or []:
                if item.get("type") == "TEMPLATE" and item.get("templateId"):
                    add_template_id(item["templateId"])
        elif category == "AGENT":
            display_prompt = (config.get("agentData") or {}).get("displayPrompt") or ""
            try:
                blocks = _parse_library_blocks(display_prompt)
            except ValueError:
                continue
            for block in blocks:
                fields = block["fields"]
                if block["type"] == "tool" and fields.get("tool") == "template_reply":
                    add_template_id(fields["id"])
    return sorted(template_ids)


def _normalize_template_items(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("list", "records", "items", "data"):
            if key in value:
                return _normalize_template_items(value.get(key))
    return []


def _list_graph_templates(client, template_ids, page_size=999):
    wanted_ids = {str(template_id) for template_id in template_ids}
    templates_by_key = {}
    seen_pages = set()
    page_index = 1
    while True:
        response = client.list_templates(
            page_index=page_index,
            page_size=page_size,
        )
        items = _normalize_template_items(response)
        if not items:
            break
        page_signature = tuple(
            json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
            for item in items
        )
        if page_signature in seen_pages:
            raise RuntimeError(
                f"template pagination repeated page {page_index}; "
                "cannot determine whether every referenced template was checked"
            )
        seen_pages.add(page_signature)
        for item in items:
            template_id = item.get("id") or item.get("templateId")
            item_key = (
                f"id:{template_id}"
                if template_id is not None
                else "value:" + json.dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )
            templates_by_key.setdefault(item_key, item)
        found_ids = {
            str(item.get("id") or item.get("templateId"))
            for item in templates_by_key.values()
            if item.get("id") is not None or item.get("templateId") is not None
        }
        if wanted_ids.issubset(found_ids) or len(items) < page_size:
            break
        page_index += 1
        if page_index > 10_000:
            raise RuntimeError("template pagination exceeded 10000 pages")
    return list(templates_by_key.values())


def _get_graph_templates(client, graph):
    template_ids = _graph_template_ids(graph)
    if not template_ids:
        return None, None
    templates, warning = _safe_list_resource(
        "Templates",
        lambda: _list_graph_templates(client, template_ids),
    )
    return templates, warning


_SOURCE_HELP = {
    "usage": [
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py inspect --agent-id 123 --out /workspace/state/agent-builder/chatflow/patch_123_graph.json --pretty",
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py validate --graph-file /workspace/state/agent-builder/chatflow/patch_123_graph.json --pretty",
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py update --agent-id 123 --graph-file /workspace/state/agent-builder/chatflow/patch_123_graph.json --pretty",
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py compile --source-file /workspace/state/agent-builder/chatflow/chatflow_source.json --graph-file /workspace/state/agent-builder/chatflow/chatflow_graph.json --pretty",
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py merge-source --fragment-file /workspace/state/agent-builder/chatflow/blocks/block_001.json --integration-file /workspace/state/agent-builder/chatflow/blocks/integration.json --out-file /workspace/state/agent-builder/chatflow/chatflow_source.json --pretty",
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py validate --graph-file /workspace/state/agent-builder/chatflow/chatflow_graph.json --pretty",
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py deploy --agent-name Example_Chatflow --graph-file /workspace/state/agent-builder/chatflow/chatflow_graph.json --pretty",
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py update --agent-id 123 --graph-file /workspace/state/agent-builder/chatflow/chatflow_graph.json --pretty",
        "python3 /skills/agent-builder/scripts/chatflow/chatflow_builder.py publish --agent-id 123 --graph-file /workspace/state/agent-builder/chatflow/chatflow_graph.json --pretty",
    ],
    "source_shape": {
        "entry": "optional node key; compile auto-creates START and connects it to entry",
        "nodes": "list of {key, type, ...business fields}",
        "edges": "list of {from, to, on?}; use $finish and $transfer for shared terminal nodes",
        "source_fragments": "keyed {nodes, edges} files; integration owns entry and cross-block edges, then merge-source writes the final source",
    },
    "node_types": [
        "start", "finish", "transfer", "reply", "question", "agent", "intent",
        "llm", "if_else", "tool", "rag_reply", "knowledge", "knowledge_reply", "collect_order",
        "human_review", "variable_process", "code", "sub_graph",
        "variable_extract", "variable_assignment", "business_track",
    ],
    "node_fields": {
        "reply": "reply_type=PROMPT with prompt and optional ai_field_ids, TEMPLATE with template_id, or DYNAMIC_TEMPLATE with template_content containing [[var:<selector>]]; optional use_long_memory and disable_prev_node_results",
        "llm": "prompt + optional history_round_limit/use_long_memory, vision{enabled,detail,media_selectors}, and structured_output{enabled,schema}; [[var:<selector>]] templates are rendered before the model call; pure model generation without plugins or next_steps",
        "transfer": "transfer_type=NO_REPLY/PROMPT/TEMPLATE; prompt or template_id only when needed; PROMPT also supports ai_field_ids, disable_prev_node_results, and explain",
        "agent": "prompt may use LibraryBlock chips, plugins/usedPlugins as tool id array, ai_field_ids, optional enable_knowledge_base/knowledge_directory_ids, knowledge_keyword_ids (fixed isolation keyword ids), knowledge_keyword_selector (variable selector yielding keyword name(s)), max_rounds_exceeded_action, use_long_memory, disable_prev_node_results, and next_steps[{id,title,prompt,params?}] for flow-internal branches; online compile binds TEMPLATE_REPLY and TRANSFER_TO_HUMAN system plugins from the Chatflow catalog by type; deterministic handoff uses a separate transfer node or $transfer",
        "intent": "optional prompt for global intent classification guidance (default null/None), history_round_limit (default null/None; -1=all history, positive=recent N rounds); intents[{id,name,desc,intentId?,examples?}]",
        "question": "mode=VARIABLE/USER_REPLY, question_type=PROMPT/TEMPLATE, question or question_template_id, variables or replies, condition=AND/OR, and use_chat_history",
        "knowledge": "alias for RAG_REPLY; supports kb_dirs/knowledgeDirectoryIds, knowledge_keyword_ids/knowledgeKeywordIds, knowledge_keyword_selector/knowledgeKeywordSelector, and optional customize_query/query_selector",
        "rag_reply": "prompt + knowledgeDirectoryIds, optional knowledgeKeywordIds (isolation keyword ids), knowledgeKeywordSelector (variable selector yielding keyword name(s)), and customizeQuery/querySelector",
        "collect_order": "soon-offline compatibility node for existing order-number collection flows; supports max_rounds and collect_order_exception; new graphs should use QUESTION(VARIABLE) plus TOOL/IF_ELSE/AGENT as needed",
        "human_review": "method=approval/fill, description, fill fields, and midway_message_strategy=ignore/handle",
        "business_track": "trace_events non-empty business event-code array; emits observability trace data and then follows SOURCE",
        "variable_process": "extracts + assignments in one node; source extracts use alias/name/describe/type; preferred replacement for variable_extract/variable_assignment",
        "code": "source_code, inputs[{field_name, variable_selector}], outputs[{field_name, field_type}]",
        "sub_graph": "target_agent_id and optional context_turn_limit; SUB_GRAPH must not have outgoing edges",
        "variable_extract": "soon-offline compatibility node; source extracts use alias/name/describe/type; prefer QUESTION(VARIABLE) for collection or AGENT/TOOL outputs for derived values",
        "variable_assignment": "soon-offline compatibility node; prefer passing upstream outputs/variable-system fields directly instead of writing assignment nodes",
    },
    "soon_offline_node_types": [
        "COLLECT_ORDER",
        "KNOWLEDGE_REPLY",
        "VARIABLE_ASSIGNMENT",
        "VARIABLE_EXTRACT",
        "AGENT version 1",
    ],
    "edge_on_values": [
        "QUESTION reply name", "INTENT name or OTHER", "IF_ELSE case name or FALSE",
        "AGENT next_steps title", "RESOLVED", "UNRESOLVED", "TRUE",
        "LACK_KNOWLEDGE", "AGREE", "REJECT",
    ],
    "variable_selector_shortcuts": [
        {"variableSelector": {"tool": "lookup_order", "field": "status"}},
        {"variableSelector": {"tool_status": "lookup_order"}},
        {"variableSelector": {"code": "normalize_items", "field": "has_items"}},
        {"variableSelector": {"llm": "summarize_case", "field": "summary"}},
        {"variableSelector": {"node": "ask_order"}},
        {"variableSelector": {"extract": "extract_info", "alias": "order_no_value"}},
        {"variableSelector": {"system": {"category": "Order", "path": [3248, 3249]}}},
    ],
    "rules": [
        "For an existing CHAT_FLOW, inspect its complete graph, edit that graph, validate it, then update the same graph file.",
        "Use source JSON for a new graph or an explicitly requested full rebuild; use an inspected graph for an existing graph patch.",
        "Write source JSON, not Python scripts.",
        "For a large flow, keep each flow block as a keyed source fragment; merge source fragments before one final compile, never merge compiled graph JSON.",
        "Do not import chatflow_builder.py from a generated script.",
        "Do not read /skill-lib or explore bootstrap.",
        "Compile source JSON to graph JSON, then validate the graph JSON.",
        "After user confirmation, reuse the same graph file for deploy/update/publish.",
    ],
}


def _cmd_help(args):
    topic = getattr(args, "topic", "source")
    if topic in ("source", "compile", "schema"):
        return _SOURCE_HELP
    if topic == "commands":
        return {"commands": _SOURCE_HELP["usage"]}
    return {"topic": topic, "message": "Unknown help topic. Use source, compile, schema, or commands."}


def _cmd_inspect(args):
    client = _get_cli_client(args.env, args.project_id)
    agent_id, listed_agent = _resolve_agent_id(client, agent_id=args.agent_id, agent_name=args.agent_name)
    detail_agent = _agent_from_detail(client.get_agent(agent_id))
    agent_name = (
        args.agent_name
        or (detail_agent or {}).get("name")
        or (listed_agent or {}).get("name")
    )
    graph = _normalize_chatflow_graph_response(client.get_chatflow_graph(agent_id))
    out_file = Path(args.out) if args.out else _default_output_path("current_graph", agent_id)
    _write_json(out_file, graph)
    return _summarize_graph(
        graph,
        agent_id=agent_id,
        agent_name=agent_name,
        out_file=_workspace_virtual_path(out_file),
    )


def _cmd_validate(args):
    graph = _load_graph_file(args.graph_file)
    offline = getattr(args, "offline", False)
    client = None if offline else _get_cli_client(args.env, args.project_id)
    if offline:
        ai_fields, agent_ai_fields, plugins, templates, warnings = None, None, None, None, [
            "offline validation: remote AI fields, plugin metadata, and template status were not checked"
        ]
    else:
        ai_fields, ai_fields_warning = _safe_list_resource("queryAiFields", client.list_ai_fields)
        agent_ai_fields, agent_ai_fields_warning = _safe_list_resource("Agent field range", client.list_agent_ai_fields)
        plugins, plugins_warning = _safe_get_graph_plugin_details(client, graph)
        templates, templates_warning = _get_graph_templates(client, graph)
        warnings = [
            item for item in (
                ai_fields_warning,
                agent_ai_fields_warning,
                plugins_warning,
                templates_warning,
            ) if item
        ]
    result = _validate_graph_file(
        graph,
        ai_fields=ai_fields,
        agent_ai_fields=agent_ai_fields,
        plugins=plugins,
        templates=templates,
    )
    _append_resource_warnings(result, warnings)
    if not result.get("valid"):
        raise SystemExit(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def _cmd_merge_source(args):
    integration = json.loads(Path(args.integration_file).read_text(encoding="utf-8"))
    source = _merge_source_fragments(args.fragment_file or [], integration)
    out_file = _write_json(args.out_file, source)
    return {
        "source_file": str(out_file),
        "fragment_files": list(args.fragment_file or []),
        "integration_file": args.integration_file,
        "node_count": len(source["nodes"]),
        "edge_count": len(source["edges"]),
    }


def _cmd_compile(args):
    source = json.loads(Path(args.source_file).read_text(encoding="utf-8"))
    offline = getattr(args, "offline", False)
    resource_client = None if offline else _get_cli_client(args.env, args.project_id)
    if offline:
        ai_fields, agent_ai_fields, warnings = None, None, [
            "offline compilation: remote AI fields, plugin metadata, and template status were not checked"
        ]
    else:
        ai_fields, ai_fields_warning = _safe_list_resource("queryAiFields", resource_client.list_ai_fields)
        agent_ai_fields, agent_ai_fields_warning = _safe_list_resource("Agent field range", resource_client.list_agent_ai_fields)
        warnings = [item for item in (ai_fields_warning, agent_ai_fields_warning) if item]
    if args.bind_tool_params and ai_fields is None:
        warnings.append("--bind-tool-params skipped because queryAiFields is unavailable")
    client = resource_client if args.bind_tool_params and ai_fields is not None else None
    graph = _compile_source_to_graph(
        source,
        client=client,
        ai_fields=ai_fields,
        agent_ai_fields=agent_ai_fields,
    )
    plugin_catalog = None
    system_plugin_requirements = _agent_system_plugin_requirements(graph)
    if offline:
        plugins = None
        templates = None
        if system_plugin_requirements:
            warnings.append(
                "offline compilation: TEMPLATE_REPLY / TRANSFER_TO_HUMAN system plugin IDs "
                "were not bound; run an online compile before deploy"
            )
    else:
        if system_plugin_requirements:
            plugin_catalog = _get_chatflow_plugin_catalog(resource_client)
            _bind_agent_system_plugins(graph, plugin_catalog)
        templates, templates_warning = _get_graph_templates(resource_client, graph)
        if templates_warning:
            warnings.append(templates_warning)
        plugins, plugins_warning = _safe_get_graph_plugin_details(
            resource_client,
            graph,
            plugin_catalog=plugin_catalog,
        )
        if plugins_warning:
            warnings.append(plugins_warning)
    validation = _validate_graph_file(
        graph,
        ai_fields=ai_fields,
        agent_ai_fields=agent_ai_fields,
        plugins=plugins,
        templates=templates,
    )
    _append_resource_warnings(validation, warnings)
    if not validation.get("valid"):
        raise SystemExit(json.dumps(validation, ensure_ascii=False, indent=2))
    out_file = _write_json(args.graph_file, graph)
    return {
        "source_file": args.source_file,
        "graph_file": str(out_file),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        "validation_warnings": validation.get("warnings", []),
    }


def _cmd_deploy(args):
    graph = _load_graph_file(args.graph_file)
    client = _get_cli_client(args.env, args.project_id)
    ai_fields, ai_fields_warning = _safe_list_resource("queryAiFields", client.list_ai_fields)
    agent_ai_fields, agent_ai_fields_warning = _safe_list_resource("Agent field range", client.list_agent_ai_fields)
    plugins, plugins_warning = _safe_get_graph_plugin_details(client, graph)
    templates, templates_warning = _get_graph_templates(client, graph)
    warnings = [
        item for item in (
            ai_fields_warning,
            agent_ai_fields_warning,
            plugins_warning,
            templates_warning,
        ) if item
    ]
    validation = _validate_graph_file(
        graph,
        ai_fields=ai_fields,
        agent_ai_fields=agent_ai_fields,
        plugins=plugins,
        templates=templates,
    )
    _append_resource_warnings(validation, warnings)
    if not validation.get("valid"):
        raise SystemExit(json.dumps(validation, ensure_ascii=False, indent=2))
    result = deploy_chatflow(client, graph, agent_name=args.agent_name)
    return {
        "agent_name": args.agent_name,
        "graph_file": args.graph_file,
        "validation": validation,
        "result": result,
    }


def _cmd_update_or_publish(args, *, publish):
    graph = _load_graph_file(args.graph_file)
    client = _get_cli_client(args.env, args.project_id)
    ai_fields, ai_fields_warning = _safe_list_resource("queryAiFields", client.list_ai_fields)
    agent_ai_fields, agent_ai_fields_warning = _safe_list_resource("Agent field range", client.list_agent_ai_fields)
    plugins, plugins_warning = _safe_get_graph_plugin_details(client, graph)
    templates, templates_warning = _get_graph_templates(client, graph)
    warnings = [
        item for item in (
            ai_fields_warning,
            agent_ai_fields_warning,
            plugins_warning,
            templates_warning,
        ) if item
    ]
    validation = _validate_graph_file(
        graph,
        ai_fields=ai_fields,
        agent_ai_fields=agent_ai_fields,
        plugins=plugins,
        templates=templates,
    )
    _append_resource_warnings(validation, warnings)
    if not validation.get("valid"):
        raise SystemExit(json.dumps(validation, ensure_ascii=False, indent=2))
    result = client.update_chatflow(args.agent_id, graph, publish=publish)
    return {
        "agent_id": int(args.agent_id),
        "graph_file": args.graph_file,
        "published": publish,
        "validation": validation,
        "result": result,
    }


def _build_arg_parser():
    parser = argparse.ArgumentParser(description="CHAT_FLOW builder utility CLI", add_help=False)
    parser.add_argument("--help", action="store_true", dest="show_help", help="Show source JSON schema and command examples")
    parser.add_argument("--env", default=os.environ.get("SOLVEA_ENV", "prod"), help="Solvea environment, defaults to SOLVEA_ENV")
    parser.add_argument("--project-id", default=os.environ.get("SOLVEA_PROJECT_ID"), help="Solvea project id")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")
    sub = parser.add_subparsers(dest="command")

    inspect_parser = sub.add_parser("inspect", help="Fetch current CHAT_FLOW graph by agent id or name")
    inspect_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    inspect_group = inspect_parser.add_mutually_exclusive_group(required=True)
    inspect_group.add_argument("--agent-id", type=int)
    inspect_group.add_argument("--agent-name")
    inspect_parser.add_argument("--out", help="Output graph JSON path")

    validate_parser = sub.add_parser("validate", help="Validate a chatFlowGraph JSON file")
    validate_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    validate_parser.add_argument("--graph-file", required=True)
    validate_parser.add_argument("--offline", action="store_true", help="Skip remote AI-field and plugin metadata checks")

    compile_parser = sub.add_parser("compile", help="Compile source JSON into a full chatFlowGraph JSON file")
    compile_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    compile_parser.add_argument("--source-file", required=True)
    compile_parser.add_argument("--graph-file", required=True)
    compile_parser.add_argument("--bind-tool-params", action="store_true", help="Use Solvea API to auto-bind TOOL LLM params to variable-system fields")
    compile_parser.add_argument("--offline", action="store_true", help="Skip remote AI-field and plugin metadata checks")

    merge_source_parser = sub.add_parser(
        "merge-source",
        help="Merge keyed flow-block source fragments before one final compilation",
    )
    merge_source_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    merge_source_parser.add_argument("--fragment-file", action="append", required=True)
    merge_source_parser.add_argument("--integration-file", required=True)
    merge_source_parser.add_argument("--out-file", required=True)

    deploy_parser = sub.add_parser("deploy", help="Create a new CHAT_FLOW agent from a graph JSON file")
    deploy_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    deploy_parser.add_argument("--agent-name", required=True)
    deploy_parser.add_argument("--graph-file", required=True)

    update_parser = sub.add_parser("update", help="Save an existing CHAT_FLOW graph as draft")
    update_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    update_parser.add_argument("--agent-id", type=int, required=True)
    update_parser.add_argument("--graph-file", required=True)

    publish_parser = sub.add_parser("publish", help="Publish an existing CHAT_FLOW graph")
    publish_parser.add_argument("--pretty", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    publish_parser.add_argument("--agent-id", type=int, required=True)
    publish_parser.add_argument("--graph-file", required=True)

    return parser


def main(argv=None):
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.show_help:
        result = _cmd_help(args)
    elif args.command == "inspect":
        result = _cmd_inspect(args)
    elif args.command == "validate":
        result = _cmd_validate(args)
    elif args.command == "compile":
        result = _cmd_compile(args)
    elif args.command == "merge-source":
        result = _cmd_merge_source(args)
    elif args.command == "deploy":
        result = _cmd_deploy(args)
    elif args.command == "update":
        result = _cmd_update_or_publish(args, publish=False)
    elif args.command == "publish":
        result = _cmd_update_or_publish(args, publish=True)
    else:
        parser.error("command is required unless --help is provided")

    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))


# ---------------------------------------------------------------------------
# Resource discovery helpers
# ---------------------------------------------------------------------------

def auto_query_plugins(client):
    """
    Query all plugins from the project, return a lookup dict.

    Returns::

        {
            "by_id":   {12345: {"id": 12345, "name": "OrderStandard", ...}},
            "by_name": {"orderstandard": {"id": 12345, ...}},
        }
    """
    plugins = client.list_plugins()
    by_id = {}
    by_name = {}
    for p in plugins:
        pid = p.get("id")
        name = p.get("name", "")
        if pid:
            by_id[pid] = p
            by_name[name.lower()] = p
    print(f"  [plugins] Loaded {len(by_id)} plugins")
    return {"by_id": by_id, "by_name": by_name}


def auto_query_ai_fields(client):
    """
    Query all variable-system fields from the project, return a lookup dict.

    Returns::

        {
            "by_id":   {21545: {"id": 21545, "name": "OrderNumber", ...}},
            "by_name": {"ordernumber": 21545, "customeremail": 21531, ...},
        }
    """
    fields = client.list_ai_fields()
    by_id = {}
    by_name = {}
    if isinstance(fields, list):
        for f in fields:
            if isinstance(f, dict):
                fid = f.get("id")
                fname = f.get("name", "")
                by_id[fid] = f
                by_name[fname.lower()] = fid
                for c in f.get("children", []):
                    cid = c.get("id")
                    cname = c.get("name", "")
                    by_id[cid] = c
                    by_name[cname.lower()] = cid
    print(f"  [ai_fields] Loaded {len(by_name)} fields")
    return {"by_id": by_id, "by_name": by_name}


def resolve_plugin(hint, plugin_map):
    """
    Resolve a plugin by name hint (case-insensitive, partial match).

    Args:
        hint: plugin name or keyword (e.g. "OrderStandard", "shipment")
        plugin_map: result from auto_query_plugins()

    Returns:
        plugin dict or None
    """
    by_name = plugin_map["by_name"]
    key = hint.lower()
    if key in by_name:
        return by_name[key]
    # Partial match
    candidates = [(k, v) for k, v in by_name.items() if key in k or k in key]
    if len(candidates) == 1:
        return candidates[0][1]
    if len(candidates) > 1:
        names = [c[0] for c in candidates]
        raise ValueError(
            f"Multiple plugins match '{hint}': {names}. "
            f"Use the exact plugin name to disambiguate."
        )
    print(f"  ⚠️  No plugin matches '{hint}'")
    return None


def resolve_ai_field(name, field_map):
    """
    Resolve a variable-system field ID by name (case-insensitive).

    Args:
        name: field name (e.g. "OrderNumber", "Attachments")
        field_map: result from auto_query_ai_fields()

    Returns:
        field ID (int) or None
    """
    by_name = field_map["by_name"]
    key = name.lower()
    if key in by_name:
        return by_name[key]
    candidates = [(k, v) for k, v in by_name.items() if key in k]
    if candidates:
        return candidates[0][1]
    print(f"  ⚠️  No variable-system field matches '{name}'")
    return None


def build_and_deploy(client, nodes, edges, agent_name):
    """
    Legacy one-step helper: auto-bind params -> validate -> deploy.

    Kept for programmatic callers. Agent-facing workflows should use the CLI
    compile/validate/deploy commands with source JSON and graph JSON files.

    Args:
        client: SolveaClient instance
        nodes: list of node dicts from builder functions
        edges: list of edge dicts
        agent_name: name for the new CHAT_FLOW agent

    Returns:
        dict with agent_id, node_count, edge_count
    """
    print(f"\n{'='*60}")
    print(f"  Building & deploying: {agent_name}")
    print(f"{'='*60}")

    print("\n[Step 1/2] Building graph...")
    graph = build_graph(nodes, edges, client=client)

    print("\n[Step 2/2] Deploying...")
    result = deploy_chatflow(client, graph, agent_name)
    result["node_count"] = len(nodes)
    result["edge_count"] = len(edges)

    print(f"\n{'='*60}")
    print(f"  Done! Agent ID: {result['agent_id']}")
    print(f"     {len(nodes)} nodes, {len(edges)} edges")
    print(f"{'='*60}")
    return result


if __name__ == "__main__":
    main()
