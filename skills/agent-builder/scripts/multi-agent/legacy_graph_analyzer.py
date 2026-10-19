#!/usr/bin/env python3
"""Analyze and trim legacy MULTI_AGENT graphs before CHAT_FLOW migration.

Usage:
  python3 /skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py inspect \
    --input /workspace/state/agent-builder/multi-agent/read_123_raw.json \
    --out-dir /workspace/state/agent-builder/multi-agent

  python3 /skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py prepare-batch \
    --index-file /workspace/state/agent-builder/multi-agent/migrate_123_agent/index.ai.json \
    --chunks-file /workspace/state/agent-builder/multi-agent/migrate_123_agent/chunks.json \
    --progress-file /workspace/state/agent-builder/multi-agent/migrate_123_agent/progress.json \
    --out-file /workspace/state/agent-builder/multi-agent/migrate_123_agent/batches/batch_context.json

  python3 /skills/agent-builder/scripts/multi-agent/legacy_graph_analyzer.py prepare-batches \
    --index-file /workspace/state/agent-builder/multi-agent/migrate_123_agent/index.ai.json \
    --chunks-file /workspace/state/agent-builder/multi-agent/migrate_123_agent/chunks.json \
    --progress-file /workspace/state/agent-builder/multi-agent/migrate_123_agent/progress.json \
    --out-dir /workspace/state/agent-builder/multi-agent/migrate_123_agent/batches \
    --parallelism 4
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from collections import deque
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", ""), "skill-runtime"))
try:
    from bootstrap import *  # noqa: F401,F403
except Exception:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "__lib__", "skill-runtime"))
    from bootstrap import *  # noqa: F401,F403


DROP_KEYS = {
    "createdAt", "updatedAt", "createdBy", "updatedBy", "createAtLong", "updateAtLong",
    "gmtCreate", "gmtModified", "creator", "modifier", "displayData", "position",
    "positions", "viewport", "selected", "dragging", "style", "className",
}
HTML_TAG_RE = re.compile(r"<[^>]+>")
PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
LIBRARY_BLOCK_RE = re.compile(r"\{#LibraryBlock\s+(.+?)\s*#\}")
EXPLICIT_TEMPLATE_REPLY_RE = re.compile(
    r"(?<![A-Za-z0-9_])template_reply\s+tool\s*[（(]\s*template\s+id\s*:\s*(\d+)\s*[)）]",
    re.IGNORECASE,
)
EXPLICIT_TRANSFER_TO_HUMAN_RE = re.compile(
    r"(?<![A-Za-z0-9_])transfer_to_agent(?:\s+tool)?\s*[（(]\s*reason\s*:\s*([^\n()（）]+?)\s*[)）]",
    re.IGNORECASE,
)
ORPHAN_STYLE_RE = re.compile(r"\(?\s*style\s*=\s*(['\"]).*?\1\s*>\)?", re.IGNORECASE)
ORPHAN_ATTR_RE = re.compile(r"\(?\s*(?:class|data-[\w-]+)\s*=\s*(['\"]).*?\1\s*>\)?", re.IGNORECASE)
LEGACY_COMMAND_RE = re.compile(
    r"\b(?:template_reply|transfer_to_agent|finish_agent|call\s+[^\n]{0,120}?\s+agent)\b",
    re.IGNORECASE,
)
MOJIBAKE_RE = re.compile(
    r"(?:�|(?:Ã|Â|â|ð|ï)[\x80-\xBF\xD7-\xFF]|[åæçèéêëìíîïðñòóôõöøùúûüýþÿ][\x80-\xFF])"
)
SYSTEM_REFERENCE_KIND = {
    "transfertoagent": ("SYSTEM_ACTION", "TRANSFER_TO_HUMAN"),
    "transfertohuman": ("SYSTEM_ACTION", "TRANSFER_TO_HUMAN"),
    "kbreply": ("SYSTEM_ACTION", "KNOWLEDGE_AI_REPLY"),
    "knowledgeaireply": ("SYSTEM_ACTION", "KNOWLEDGE_AI_REPLY"),
    "templatereply": ("SYSTEM_ACTION", "TEMPLATE_REPLY"),
    "finishagent": ("SYSTEM_ACTION", "FINISH_AGENT"),
}
SYSTEM_REFERENCE_TYPE_KIND = {
    "knowledge_ai_reply": ("SYSTEM_ACTION", "KNOWLEDGE_AI_REPLY"),
    "transfer_to_human": ("SYSTEM_ACTION", "TRANSFER_TO_HUMAN"),
    "template_reply": ("SYSTEM_ACTION", "TEMPLATE_REPLY"),
    "finish_agent": ("SYSTEM_ACTION", "FINISH_AGENT"),
}
WORD_RE = re.compile(r"[A-Za-z0-9_:-]{3,}")
SNAKE_RE = re.compile(r"[^A-Za-z0-9]+")
PROMPT_REVIEW_BLOCK_TARGETS = {
    "TEMPLATE_REPLY": ["AGENT_LIBRARY_BLOCK", "REPLY_TEMPLATE"],
    "TRANSFER_TO_HUMAN": ["AGENT_LIBRARY_BLOCK", "TRANSFER_NODE"],
    "BUSINESS_TOOL": ["AGENT_LIBRARY_BLOCK", "TOOL_NODE"],
    "FIXED_WORDING": ["NODE_PROMPT_FIELD"],
    # Kept only for migration plans created before semantic prompt reviews.
    "INLINE_FIXED_REPLY": [
        "AGENT_INLINE_WORDING", "REPLY_PROMPT", "REPLY_DYNAMIC_TEMPLATE",
    ],
    "WAIT_FOR_USER": ["AGENT_WAIT", "REPLY_WAIT", "QUESTION_WAIT"],
}
PROMPT_REVIEW_DISCOVERY_KINDS = [
    "TEMPLATE_REPLY",
    "TRANSFER_TO_HUMAN",
    "BUSINESS_TOOL",
    "FIXED_WORDING",
    "WAIT_FOR_USER",
]
MIGRATION_SOURCE_TYPE_ALIASES = {
    "model": "LLM",
    "ifelse": "IF_ELSE",
    "collectorder": "COLLECT_ORDER",
    "transfer": "TRANSFER_TO_HUMAN",
    "humanreview": "HUMAN_REVIEW",
    "knowledge": "RAG_REPLY",
    "rag": "RAG_REPLY",
    "variableextract": "VARIABLE_EXTRACT",
    "variableassignment": "VARIABLE_ASSIGNMENT",
    "variableprocess": "VARIABLE_PROCESS",
    "subgraph": "SUB_GRAPH",
    "businesstrack": "BUSINESS_TRACK",
}
GENERIC_AGENT_NEXT_STEP_NAMES = {
    "complete",
    "completed",
    "continue",
    "done",
    "finish",
    "next",
    "proceed",
    "success",
}
MIGRATION_HANDOFF_KIND = "MULTI_AGENT_TO_CHAT_FLOW"
MIGRATION_HANDOFF_SCHEMA_VERSION = 1
MIGRATION_DROP_DECISIONS = {"dropped", "dropped_with_reason"}
COVERAGE_STABLE_ID_FIELDS = {
    "agents": "old_id",
    "tools": "old_tool_key",
    "actions": "action_id",
    "explicit_edges": "edge_id",
    "resources": "resource_id",
    "classifiers": "contract_id",
    "templates": "contract_id",
    "interactions": "contract_id",
    "branches": "contract_id",
    "prompt_reviews": "contract_id",
    "prompt_blocks": "contract_id",
}


def _migration_decision_is_resolved(item: dict) -> bool:
    return item.get("resolved") is True and bool(
        str(item.get("resolution") or "").strip()
    )


def _migration_decision_is_drop(item: dict) -> bool:
    return item.get("decision") in MIGRATION_DROP_DECISIONS


def _read_json(path: str) -> object:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_name(value: object, default: str = "agent") -> str:
    text = str(value or default).strip() or default
    text = SNAKE_RE.sub("_", text).strip("_").lower()
    return text[:80] or default


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _clean_text(value: object, *, keep_placeholders: bool = True) -> str:
    if value is None:
        return ""
    text = str(value)
    text = html.unescape(text)
    text = LIBRARY_BLOCK_RE.sub(" ", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = ORPHAN_STYLE_RE.sub(" ", text)
    text = ORPHAN_ATTR_RE.sub(" ", text)
    if not keep_placeholders:
        text = PLACEHOLDER_RE.sub(" ", text)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_prompt(value: object) -> str:
    """Keep business PE only; structural actions come from graph fields."""
    text = _clean_text(_repair_mojibake(value), keep_placeholders=False).replace("�", " ")
    text = re.sub(r"\b(?:template_reply|transfer_to_agent|finish_agent)\s+tool\b", " ", text, flags=re.IGNORECASE)
    text = LEGACY_COMMAND_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def _repair_mojibake(value: object) -> str:
    """Repair common UTF-8 decoded as Latin-1/CP1252 without changing clean text."""
    text = str(value or "")
    if not MOJIBAKE_RE.search(text) or "�" in text:
        return text
    try:
        encoded = bytes(
            ord(char) if ord(char) <= 0xFF else char.encode("cp1252")[0]
            for char in text
        )
        candidate = encoded.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if len(MOJIBAKE_RE.findall(candidate)) < len(MOJIBAKE_RE.findall(text)):
        return candidate
    return text


def _encoding_quality(value: object) -> dict:
    """Report raw encoding quality; prompt cleaning is handled separately."""
    text = str(value or "")
    replacement_count = text.count("�")
    markers = MOJIBAKE_RE.findall(text)
    if replacement_count:
        quality = "replacement_character"
    elif markers:
        quality = "mojibake_suspected"
    else:
        quality = "clean"
    return {
        "quality": quality,
        "needs_human_review": False,
        "marker_count": len(markers),
        "replacement_character_count": replacement_count,
        "evidence": sorted(set(markers))[:20],
    }


def _tool_references(prompt: object, display_prompt: object) -> list[dict]:
    """Extract rendered tool chips without treating their HTML as prompt text."""
    refs = []
    seen = set()

    def add(
        name: object,
        source: str,
        *,
        actionable: bool = True,
        audit_reason: str | None = None,
    ) -> None:
        normalized = str(name or "").strip()
        if not normalized:
            return
        key = normalized.lower()
        if key in seen:
            return
        seen.add(key)
        item = {"name": normalized, "source": source, "actionable": actionable}
        if audit_reason:
            item["audit_reason"] = audit_reason
        refs.append(item)

    for name in PLACEHOLDER_RE.findall(str(display_prompt or "")):
        add(name, "displayPrompt_tool_chip")
    for name in PLACEHOLDER_RE.findall(str(prompt or "")):
        add(name, "prompt_placeholder")
    return refs


def _structured_system_references(value: object) -> list[dict]:
    """Find structured SYSTEM chips that may not be serialized in displayPrompt."""
    refs = []

    def walk(item: object) -> None:
        if isinstance(item, dict):
            source = str(item.get("source") or "").upper()
            ref_type = str(item.get("type") or "")
            name = item.get("name")
            if source == "SYSTEM" and name and ref_type:
                refs.append({
                    "name": str(name),
                    "source": "structured_system_metadata",
                    "resource_source": "SYSTEM",
                    "resource_type": ref_type,
                })
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    return refs


def _normalize_directory_ids(value: object) -> list[object]:
    """Accept the legacy list/string shapes without inventing directory ids."""
    if isinstance(value, (list, tuple, set)):
        values = list(value)
    elif isinstance(value, str):
        values = value.split(",")
    elif value is None:
        values = []
    else:
        values = [value]
    result = []
    seen = set()
    for item in values:
        if item is None or (isinstance(item, str) and not item.strip()):
            continue
        key = str(item).strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(item.strip() if isinstance(item, str) else item)
    return result


def _coerce_optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "enabled", "enable"}:
            return True
        if normalized in {"false", "0", "no", "off", "disabled", "disable"}:
            return False
    return None


def _knowledge_config_state(value: object) -> dict:
    """Normalize direct and nested KB settings for migration decisions.

    Old exports put the settings directly on ``knowledgeAiReplyPlugin`` while
    newer exports place the effective settings in ``knowledgeAiReplyConfig``.
    The nested config takes precedence for the enabled flag, but ids from both
    forms are retained because they are references to the same legacy KB.
    """
    if not isinstance(value, dict):
        return {
            "configured": False,
            "enabled": None,
            "directory_ids": [],
            "config_sources": [],
        }

    configs: list[tuple[str, dict]] = []

    def add_config(name: str, candidate: object) -> None:
        if not isinstance(candidate, dict):
            return
        if any(candidate is existing for _, existing in configs):
            return
        configs.append((name, candidate))

    add_config("knowledgeAiReplyConfig", value.get("knowledgeAiReplyConfig"))
    meta = value.get("meta") if isinstance(value.get("meta"), dict) else {}
    add_config("meta.knowledgeAiReplyConfig", meta.get("knowledgeAiReplyConfig"))
    config = value.get("config") if isinstance(value.get("config"), dict) else {}
    add_config("config.knowledgeAiReplyConfig", config.get("knowledgeAiReplyConfig"))
    add_config("plugin", value)

    enabled = None
    for _, candidate in configs:
        for field in ("enable", "enabled", "isEnable", "isEnabled"):
            if field not in candidate:
                continue
            enabled = _coerce_optional_bool(candidate.get(field))
            if enabled is not None:
                break
        if enabled is not None:
            break

    directory_ids = []
    seen = set()
    for _, candidate in configs:
        for field in ("directoryIds", "knowledgeDirectoryIds"):
            for directory_id in _normalize_directory_ids(candidate.get(field)):
                key = str(directory_id)
                if key in seen:
                    continue
                seen.add(key)
                directory_ids.append(directory_id)

    return {
        "configured": True,
        "enabled": enabled,
        "directory_ids": directory_ids,
        "config_sources": [name for name, _ in configs],
    }


def _reference_requires_binding(ref: dict) -> bool:
    """Only explicit executable prompt commands become user-decision blockers."""
    if not ref.get("actionable", True):
        return False
    sources = set(ref.get("evidence_sources") or [ref.get("source")])
    return "prompt_tool_command" in sources


def _bind_tool_references(agent: dict, refs: list[dict]) -> list[dict]:
    """Reconcile rendered names with external and system plugin evidence."""
    candidates = {}
    for plugin in agent.get("usedPlugins") or []:
        if isinstance(plugin, dict):
            for value in (plugin.get("name"), plugin.get("pluginName"), plugin.get("id"), plugin.get("pluginId")):
                if value:
                    candidates[re.sub(r"[^a-z0-9]", "", str(value).lower())] = "used_plugin"
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    for value in meta.values():
        if isinstance(value, dict) and value.get("type"):
            for field in ("name", "pluginName", "id", "pluginId"):
                if value.get(field):
                    candidates[re.sub(r"[^a-z0-9]", "", str(value[field]).lower())] = "system_plugin"
    bound = []
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    raw_knowledge_config = meta.get("knowledgeAiReplyPlugin")
    knowledge_config_present = isinstance(raw_knowledge_config, dict)
    knowledge_state = _knowledge_config_state(raw_knowledge_config)
    for ref in refs:
        key = re.sub(r"[^a-z0-9]", "", ref["name"].lower())
        item = dict(ref)
        system_key = re.sub(r"[^a-z0-9]", "", ref["name"].lower())
        system_kind, system_type = SYSTEM_REFERENCE_KIND.get(system_key, (None, None))
        explicit_type = re.sub(r"[^a-z0-9]", "", str(ref.get("resource_type") or "").lower())
        if not system_type:
            system_kind, system_type = SYSTEM_REFERENCE_TYPE_KIND.get(explicit_type, (None, None))
        if system_kind:
            item["reference_kind"] = system_kind
            item.setdefault("resource_source", "SYSTEM")
            item["system_type"] = system_type
            item["resource_type"] = system_type
        if not item.get("actionable", True):
            item["binding"] = "non_actionable"
        elif system_type == "TRANSFER_TO_HUMAN" or system_type == "TEMPLATE_REPLY" or system_type == "FINISH_AGENT":
            item["binding"] = "system_action"
        elif system_type == "KNOWLEDGE_AI_REPLY":
            item["binding"] = "system_plugin" if knowledge_config_present else "unresolved"
            if knowledge_config_present:
                item["knowledge_enabled"] = knowledge_state["enabled"]
                item["knowledge_directory_ids"] = knowledge_state["directory_ids"]
        else:
            item["binding"] = candidates.get(key, "unresolved")
        bound.append(item)
    return bound


def _drop_frontend_noise(value: object) -> object:
    if isinstance(value, dict):
        cleaned = {}
        for key, child in value.items():
            if key in DROP_KEYS:
                continue
            if key == "displayPrompt":
                cleaned["displayPromptText"] = _clean_text(child, keep_placeholders=False)
                cleaned["displayPromptPlaceholders"] = PLACEHOLDER_RE.findall(str(child or ""))
                continue
            if key == "prompt":
                cleaned["prompt"] = _clean_prompt(child)
                continue
            cleaned[key] = _drop_frontend_noise(child)
        return cleaned
    if isinstance(value, list):
        return [_drop_frontend_noise(item) for item in value]
    if isinstance(value, str):
        return _clean_text(value)
    return value


def _find_multi_agent_payload(raw: object) -> tuple[dict, dict]:
    if isinstance(raw, list):
        for item in raw:
            try:
                return _find_multi_agent_payload(item)
            except ValueError:
                continue
    if not isinstance(raw, dict):
        raise ValueError("input does not contain a JSON object")

    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    graph = meta.get("multiAgentGraph")
    if isinstance(graph, dict):
        return raw, graph

    direct_graph = raw.get("multiAgentGraph")
    if isinstance(direct_graph, dict):
        return raw, direct_graph

    if isinstance(raw.get("agents"), list) and (
        isinstance(raw.get("agentEdges"), list) or raw.get("entryAgentId") is not None
    ):
        return {"meta": {"multiAgentGraph": raw}}, raw

    data = raw.get("data")
    if isinstance(data, dict):
        return _find_multi_agent_payload(data)

    raise ValueError("input does not look like a legacy multiAgentGraph")


def _plugin_id(plugin: dict) -> str:
    return str(plugin.get("id") or plugin.get("pluginId") or plugin.get("toolId") or "")


def _plugin_name(plugin: dict) -> str:
    return str(plugin.get("name") or plugin.get("pluginName") or plugin.get("title") or _plugin_id(plugin) or "tool")


def _protected_prompt_references(agent: dict, prompt: str) -> list[dict]:
    """Seed exact executable references that the semantic worker may not omit."""
    agent_id = str(agent.get("id") or agent.get("agentId") or "")
    protected = []

    def append_reference(match: re.Match, kind: str, **fields: object) -> None:
        start, end = match.span()
        protected.append({
            "protected_ref_id": _stable_id(
                "protected_prompt_ref",
                agent_id,
                kind,
                start,
                end,
                *fields.values(),
            ),
            "kind": kind,
            "source_span": {"start": start, "end": end},
            "source_quote": prompt[start:end],
            "source": "explicit_runtime_tool_syntax",
            **fields,
        })

    for match in EXPLICIT_TEMPLATE_REPLY_RE.finditer(prompt):
        append_reference(match, "TEMPLATE_REPLY", template_id=int(match.group(1)))

    for match in EXPLICIT_TRANSFER_TO_HUMAN_RE.finditer(prompt):
        append_reference(
            match,
            "TRANSFER_TO_HUMAN",
            transfer_reason=match.group(1).strip(),
        )

    business_tools_by_name: dict[str, list[tuple[int, str]]] = {}
    for plugin in agent.get("usedPlugins") or []:
        if not isinstance(plugin, dict):
            continue
        plugin_id = plugin.get("id") or plugin.get("pluginId") or plugin.get("toolId")
        if isinstance(plugin_id, str) and plugin_id.isdigit():
            plugin_id = int(plugin_id)
        if isinstance(plugin_id, bool) or not isinstance(plugin_id, int) or plugin_id <= 0:
            continue
        plugin_name = _plugin_name(plugin).strip()
        normalized_name = re.sub(r"[^a-z0-9]", "", plugin_name.lower())
        plugin_type = str(plugin.get("type") or "").upper()
        if (
            not plugin_name
            or normalized_name in SYSTEM_REFERENCE_KIND
            or plugin_type in {
                "TRANSFER_TO_HUMAN",
                "TEMPLATE_REPLY",
                "KNOWLEDGE_AI_REPLY",
                "FINISH_AGENT",
                "SWITCH_AGENT",
                "CLASSIFIER",
            }
        ):
            continue
        business_tools_by_name.setdefault(plugin_name.casefold(), []).append(
            (plugin_id, plugin_name)
        )

    occupied_spans = {
        (item["source_span"]["start"], item["source_span"]["end"])
        for item in protected
    }
    for bindings in business_tools_by_name.values():
        unique_bindings = list(dict.fromkeys(bindings))
        if len(unique_bindings) != 1:
            continue
        plugin_id, plugin_name = unique_bindings[0]
        tool_pattern = re.compile(
            rf"(?<![A-Za-z0-9_]){re.escape(plugin_name)}\s+tool\b",
            re.IGNORECASE,
        )
        for match in tool_pattern.finditer(prompt):
            if any(
                match.start() < occupied_end and occupied_start < match.end()
                for occupied_start, occupied_end in occupied_spans
            ):
                continue
            append_reference(
                match,
                "BUSINESS_TOOL",
                tool_id=plugin_id,
                tool_name=plugin_name,
            )
            occupied_spans.add(match.span())

    protected.sort(key=lambda item: (
        item["source_span"]["start"],
        item["source_span"]["end"],
        item["kind"],
    ))
    for source_sequence, item in enumerate(protected):
        item["source_sequence"] = source_sequence
    return protected


def _library_block_attr(
    value: object,
    label: str = "LibraryBlock attribute",
) -> str:
    text = str(value or "")
    unsupported = []
    if "#}" in text:
        unsupported.append("the block terminator '#}'")
    if '"' in text:
        unsupported.append("double quotes")
    if "\\" in text:
        unsupported.append("backslashes")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        unsupported.append("line breaks or control characters")
    if re.search(r"(?:^|\s)[A-Za-z_]\w*=", text):
        unsupported.append("an attribute-like key=value token")
    if unsupported:
        raise ValueError(
            f"{label} cannot be represented losslessly in a PE LibraryBlock; "
            "use a separate node or adjust the value (unsupported: "
            f"{', '.join(unsupported)})"
        )
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _prompt_review_contract(agent: dict) -> dict | None:
    """Preserve a complete PE for semantic review by a migration worker."""
    prompt = _repair_mojibake(agent.get("prompt") or "")
    if not prompt.strip():
        return None
    agent_id = str(agent.get("id") or agent.get("agentId") or "")
    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    protected_refs = _protected_prompt_references(agent, prompt)
    return {
        "contract_id": _stable_id("prompt_review", agent_id, prompt_sha256),
        "agent_id": agent_id,
        "agent_name": agent.get("name") or agent.get("title") or agent_id,
        "prompt": prompt,
        "prompt_sha256": prompt_sha256,
        "prompt_char_count": len(prompt),
        "review_mode": "full_semantic_review",
        "required_block_kinds": PROMPT_REVIEW_DISCOVERY_KINDS,
        "protected_refs": protected_refs,
        "requirements": [
            "Read the complete prompt and infer executable semantics from context, not phrases.",
            "Return every template, human transfer, business tool, fixed wording, and wait point in source order.",
            "Every protected_refs entry is an exact executable reference and must appear in discovered_blocks with the same source span and binding.",
            "Keep flow-internal jumps, finish actions, and tool-status branches as control_semantics, not human transfers.",
            "Preserve fixed wording or output instructions verbatim with their SHA-256.",
        ],
    }


def _transfer_library_block_tool_id(block: dict) -> int:
    """Derive a stable, PE-safe instance id without reusing a plugin id."""
    identity = {
        "block_id": block.get("block_id"),
        "sequence": block.get("sequence"),
        "source_span": block.get("source_span"),
        "transfer_reason": block.get("transfer_reason"),
    }
    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16], 16)
    return 1_000_000_000_000 + digest % 8_000_000_000_000


def _render_discovered_library_block(block: dict) -> tuple[str | None, list[int]]:
    """Render protocol blocks from worker-understood semantics, independent of PE wording."""
    kind = str(block.get("kind") or "")
    if kind == "TEMPLATE_REPLY":
        template_id = block.get("template_id")
        if isinstance(template_id, bool) or not isinstance(template_id, int) or template_id <= 0:
            raise ValueError("TEMPLATE_REPLY requires a positive integer template_id")
        return (
            f"{{#LibraryBlock id={template_id} type=tool "
            "name=template_reply tool=template_reply #}",
            [],
        )
    if kind == "TRANSFER_TO_HUMAN":
        reason = str(block.get("transfer_reason") or "").strip()
        if not reason:
            raise ValueError("TRANSFER_TO_HUMAN requires transfer_reason")
        tool_id = _transfer_library_block_tool_id(block)
        reason_attr = _library_block_attr(
            reason,
            "TRANSFER_TO_HUMAN transfer_reason",
        )
        return (
            f"{{#LibraryBlock tool_id={tool_id} type=transferHuman "
            f"name={reason_attr} transferType=INSTRUCTION "
            'action=NOT_REPLY templateContent="" templateId= #}',
            [],
        )
    if kind == "BUSINESS_TOOL":
        tool_id = block.get("tool_id")
        tool_name = str(block.get("tool_name") or "").strip()
        if isinstance(tool_id, bool) or not isinstance(tool_id, int) or tool_id <= 0:
            raise ValueError("BUSINESS_TOOL requires a positive integer tool_id")
        if not tool_name:
            raise ValueError("BUSINESS_TOOL requires tool_name")
        attr = _library_block_attr(tool_name, "BUSINESS_TOOL tool_name")
        return (
            f"{{#LibraryBlock id={tool_id} type=tool name={attr} tool={attr} #}}",
            [tool_id],
        )
    if kind in {"FIXED_WORDING", "INLINE_FIXED_REPLY", "WAIT_FOR_USER"}:
        return None, []
    raise ValueError(f"unsupported discovered prompt block kind '{kind}'")


def _enrich_discovered_prompt_block(block: dict) -> dict:
    enriched = deepcopy(block)
    kind = str(enriched.get("kind") or "")
    if kind not in PROMPT_REVIEW_BLOCK_TARGETS:
        raise ValueError(f"unsupported discovered prompt block kind '{kind}'")
    unresolved = enriched.get("decision") == "open_question" or (
        _migration_decision_is_drop(enriched)
        and _migration_decision_is_resolved(enriched)
    )
    try:
        library_block, required_plugins = _render_discovered_library_block(enriched)
    except ValueError:
        if not unresolved:
            raise
        library_block, required_plugins = None, []
    enriched["target_options"] = deepcopy(PROMPT_REVIEW_BLOCK_TARGETS[kind])
    enriched["library_block"] = library_block
    enriched["required_used_plugins"] = required_plugins
    if kind in {"TEMPLATE_REPLY", "TRANSFER_TO_HUMAN"}:
        enriched["required_plugin_types"] = [kind]
    if kind == "TRANSFER_TO_HUMAN":
        enriched["transfer_to_humans"] = []
    if kind in {"FIXED_WORDING", "INLINE_FIXED_REPLY"}:
        content = enriched.get("content")
        if not isinstance(content, str) or not content:
            if not unresolved:
                raise ValueError(f"{kind} requires complete non-empty content")
        else:
            enriched["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
            enriched["must_preserve_verbatim"] = True
    return enriched


def _iter_action_statuses(plugin: dict) -> list[dict]:
    meta = plugin.get("meta") if isinstance(plugin.get("meta"), dict) else {}
    config = meta.get("externalHttpCallConfig") if isinstance(meta.get("externalHttpCallConfig"), dict) else {}
    statuses = config.get("actionStatuses") or meta.get("actionStatuses") or plugin.get("actionStatuses") or []
    return [item for item in statuses if isinstance(item, dict)]


def _iter_tool_actions(container: dict) -> list[dict]:
    meta = container.get("meta") if isinstance(container.get("meta"), dict) else {}
    actions = meta.get("toolAfterExecuteActions") or container.get("toolAfterExecuteActions") or []
    return [item for item in actions if isinstance(item, dict)]


def _action_targets(action_group: dict) -> list[dict]:
    actions = action_group.get("actions") or action_group.get("action") or []
    if isinstance(actions, dict):
        actions = [actions]
    return [item for item in actions if isinstance(item, dict)]


def _action_summary(action: dict) -> dict:
    action_type = action.get("type") or action.get("actionType")
    action_value = action.get("value") or action.get("targetAgentId") or action.get("agentId")
    template_id = action.get("templateId") or action.get("user_input_template_id")
    # Legacy uses -1 (and sometimes 0) as the no-fixed-template sentinel.
    if template_id in {-1, 0, "-1", "0", ""}:
        template_id = None
    template_content = _clean_text(
        action.get("templateContent") or action.get("user_input_template_content")
    )
    transfer_reason = action.get("reason") or action.get("transferReason")
    if not transfer_reason and action_type == "TRANSFER_TO_HUMAN" and action_value:
        transfer_reason = action_value
    return {
        "type": action_type,
        "value": action_value,
        "reason": str(transfer_reason).strip() if transfer_reason else None,
        "template_id": template_id,
        "template_status": "BOUND" if template_id is not None else ("INLINE" if template_content else "NONE"),
        "template_content": template_content,
        "user_input_template_enabled": bool(action.get("user_input_template_enable")),
        "raw": _drop_frontend_noise(action),
    }


def _classifier_categories(classifier: dict) -> list[dict]:
    """Keep the configured classifier vocabulary as a closed migration contract.

    Old agents use several editor payload shapes, so only accept list items that
    actually look like categories.  Action matchStatus is kept separately and
    is not invented as a new customer intent.
    """
    candidates = []
    for container in (classifier, classifier.get("meta") if isinstance(classifier.get("meta"), dict) else {}):
        for key in ("categories", "intents", "classifications", "classifyConfigs"):
            value = container.get(key) if isinstance(container, dict) else None
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))
    result = []
    seen = set()
    for item in candidates:
        name = item.get("name") or item.get("category") or item.get("label")
        category_id = item.get("id") or item.get("categoryId") or name
        if not category_id or str(category_id) in seen:
            continue
        seen.add(str(category_id))
        result.append({
            "id": str(category_id),
            "name": str(name or category_id),
            "desc": item.get("desc") or item.get("description") or "",
            "examples": item.get("examples") or [],
        })
    return result


def _collect_prompt_terms(agent: dict) -> set[str]:
    terms = set()
    for plugin in agent.get("usedPlugins") or []:
        if not isinstance(plugin, dict):
            continue
        terms.update(WORD_RE.findall(_plugin_name(plugin)))
        terms.update(WORD_RE.findall(str(plugin.get("type") or "")))
        for status in _iter_action_statuses(plugin):
            terms.update(WORD_RE.findall(str(status.get("name") or "")))
        for group in _iter_tool_actions(plugin):
            terms.update(WORD_RE.findall(str(group.get("matchStatus") or "")))
            for action in _action_targets(group):
                terms.update(WORD_RE.findall(json.dumps(_action_summary(action), ensure_ascii=False)))
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    terms.update(WORD_RE.findall(json.dumps(_drop_frontend_noise(meta), ensure_ascii=False)))
    return {term.lower() for term in terms if len(term) >= 3}


def _prompt_evidence(prompt: str, terms: set[str], extra_terms: list[str], max_chars: int) -> dict:
    raw_clean_prompt = _clean_text(prompt)
    clean_prompt = _clean_prompt(prompt)
    encoding = _encoding_quality(prompt)
    all_terms = {term.lower() for term in terms}
    all_terms.update(term.lower() for term in extra_terms)
    snippets = []
    for line in re.split(r"[\n。；;]+", raw_clean_prompt):
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        term_hit = any(term in lower for term in all_terms)
        if term_hit:
            cleaned_line = _clean_prompt(line)
            if cleaned_line:
                snippets.append(cleaned_line[:600])
    if not snippets and clean_prompt:
        snippets = [clean_prompt[: min(max_chars, 1200)]]
    joined = "\n".join(snippets)
    if len(joined) > max_chars:
        joined = joined[:max_chars] + "\n...[truncated]"
    return {
        "length": len(clean_prompt),
        "placeholders": PLACEHOLDER_RE.findall(raw_clean_prompt),
        "evidence": joined,
        "encoding_quality": encoding["quality"],
        "cleaned_encoding_quality": _encoding_quality(clean_prompt)["quality"],
        "encoding_evidence": encoding["evidence"],
        "needs_human_review": False,
    }


def _explicit_edges(graph: dict) -> list[dict]:
    edges = []
    for index, edge in enumerate(graph.get("agentEdges") or []):
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("fromAgentId") or edge.get("source") or edge.get("from") or "")
        target = str(edge.get("toAgentId") or edge.get("target") or edge.get("to") or "")
        edges.append({
            "edge_id": _stable_id("agent_edge", source, target, index),
            "type": "explicit_agent_edge",
            "routing_semantics": "model_selectable",
            "target_mapping_policy": "model_decides",
            "from": source,
            "to": target,
            "raw": _drop_frontend_noise(edge),
        })
    return edges


def _extract_tools_and_actions(agent: dict) -> tuple[list[dict], list[dict]]:
    tools = []
    action_edges = []
    agent_id = str(agent.get("id") or agent.get("agentId") or "")
    for plugin_index, plugin in enumerate(agent.get("usedPlugins") or []):
        if not isinstance(plugin, dict):
            continue
        tool = {
            "agent_id": agent_id,
            "tool_key": _stable_id("tool", agent_id, _plugin_id(plugin), plugin_index),
            "id": _plugin_id(plugin),
            "name": _plugin_name(plugin),
            "type": plugin.get("type"),
            "request_param": _drop_frontend_noise(
                ((plugin.get("meta") or {}).get("externalHttpCallConfig") or {}).get("requestParam")
            ),
            "response_param": _drop_frontend_noise(
                ((plugin.get("meta") or {}).get("externalHttpCallConfig") or {}).get("responseParam")
            ),
            "action_statuses": [
                {"name": item.get("name"), "condition": _drop_frontend_noise(item.get("condition"))}
                for item in _iter_action_statuses(plugin)
            ],
        }
        tools.append(tool)
        for group_index, group in enumerate(_iter_tool_actions(plugin)):
            for action_index, action in enumerate(_action_targets(group)):
                action_summary = _action_summary(action)
                action_edges.append({
                    "action_id": _stable_id(
                        "action", agent_id, tool["tool_key"], group.get("matchStatus"),
                        group_index, action_index, action_summary.get("type"), action_summary.get("value"),
                    ),
                    "source": "used_plugin",
                    "from_agent": agent_id,
                    "tool_id": tool["id"],
                    "tool_name": tool["name"],
                    "match_status": group.get("matchStatus"),
                    "action_group_id": _stable_id("action_group", agent_id, tool["tool_key"], group.get("matchStatus"), group_index),
                    "sequence": action_index,
                    "action": action_summary,
                })

    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    classifier = meta.get("classifierPlugin") if isinstance(meta.get("classifierPlugin"), dict) else {}
    for group_index, group in enumerate(_iter_tool_actions(classifier)):
        for action_index, action in enumerate(_action_targets(group)):
            action_summary = _action_summary(action)
            action_edges.append({
                "action_id": _stable_id(
                    "action", agent_id, "classifier", group.get("matchStatus"),
                    group_index, action_index, action_summary.get("type"), action_summary.get("value"),
                ),
                "source": "classifier_plugin",
                "from_agent": agent_id,
                "tool_id": _plugin_id(classifier),
                "tool_name": _plugin_name(classifier),
                "match_status": group.get("matchStatus"),
                "action_group_id": _stable_id("action_group", agent_id, "classifier", group.get("matchStatus"), group_index),
                "sequence": action_index,
                "action": action_summary,
            })
    return tools, action_edges


def _migration_contracts(agents: list[dict], action_edges: list[dict]) -> dict:
    """Extract protected executable semantics before an LLM selects nodes."""
    classifiers = []
    templates = []
    interactions = []
    branches = []
    prompt_reviews = []
    for agent in agents:
        if isinstance(agent.get("prompt_review"), dict):
            prompt_reviews.append(deepcopy(agent["prompt_review"]))
        classifier = agent.get("classifier")
        if isinstance(classifier, dict) and classifier:
            categories = _classifier_categories(classifier)
            classifiers.append({
                "contract_id": _stable_id("classifier", agent["id"], _plugin_id(classifier)),
                "agent_id": agent["id"],
                "plugin_id": _plugin_id(classifier),
                "categories": categories,
                "action_statuses": sorted({str(edge.get("match_status")) for edge in action_edges
                                           if edge.get("from_agent") == agent["id"] and edge.get("source") == "classifier_plugin"
                                           and edge.get("match_status") is not None}),
            })
    grouped = {}
    for edge in action_edges:
        grouped.setdefault(edge.get("action_group_id") or edge.get("action_id"), []).append(edge)
    for group_id, edges in grouped.items():
        ordered = sorted(edges, key=lambda item: item.get("sequence", 0))
        first = ordered[0]
        branches.append({
            "contract_id": str(group_id),
            "from_agent": first.get("from_agent"),
            "source": first.get("source"),
            "tool_id": first.get("tool_id"),
            "match_status": first.get("match_status"),
            "actions": [{"action_id": edge.get("action_id"), **(edge.get("action") or {})} for edge in ordered],
        })
        for edge in ordered:
            action = edge.get("action") or {}
            if action.get("template_status") in {"BOUND", "INLINE"}:
                template = {
                    "contract_id": _stable_id("template", edge.get("action_id")),
                    "action_id": edge.get("action_id"),
                    "template_id": action.get("template_id"),
                    "template_content": action.get("template_content"),
                    "template_status": action.get("template_status"),
                    "required_target": "TEMPLATE",
                }
                templates.append(template)
                interactions.append({
                    "contract_id": _stable_id("interaction", edge.get("action_id")),
                    "action_id": edge.get("action_id"),
                    "kind": "template_reply",
                    "waits_for_user": action.get("user_input_template_enabled", False),
                    "must_precede_action_group": str(group_id),
                })
    return {
        "classifiers": classifiers,
        "templates": templates,
        "interactions": interactions,
        "branches": branches,
        "prompt_reviews": prompt_reviews,
    }


def _meta_tools(agent: dict) -> dict:
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    raw_kb = meta.get("knowledgeAiReplyPlugin")
    kb = raw_kb if isinstance(raw_kb, dict) else None
    template = meta.get("templateReplyPlugin") if isinstance(meta.get("templateReplyPlugin"), dict) else {}
    transfers = meta.get("transferToHumans") or meta.get("transferToHumanPlugin") or []
    finish = meta.get("finishAgentPlugin") or {}
    return {
        "knowledge": _drop_frontend_noise(kb) if kb is not None else None,
        "template_reply": _drop_frontend_noise(template),
        "transfer_to_humans": _drop_frontend_noise(transfers),
        "finish": _drop_frontend_noise(finish),
    }


def _migration_hints(agent: dict, tools: list[dict], actions: list[dict]) -> list[str]:
    hints = []
    prompt = _clean_text(agent.get("prompt") or "")
    meta = agent.get("meta") if isinstance(agent.get("meta"), dict) else {}
    if tools:
        hints.append("has_real_tools")
    if any(tool.get("action_statuses") for tool in tools):
        hints.append("has_tool_action_statuses")
    if actions:
        hints.append("has_structural_actions")
    if meta.get("classifierPlugin"):
        hints.append("classifier")
    kb = meta.get("knowledgeAiReplyPlugin")
    if isinstance(kb, dict):
        hints.append("knowledge_config")
    if re.search(r"\b(summary|summari[sz]e|rewrite|extract|normalize)\b", prompt, re.I):
        hints.append("candidate_llm")
    if not tools and not actions:
        hints.append("candidate_merge_or_reply")
    return hints


def _entry_agent_id(graph: dict, agents: list[dict], explicit_edges: list[dict], action_edges: list[dict]) -> str:
    entry = graph.get("entryAgentId") or graph.get("entry_agent_id") or graph.get("entry")
    if entry:
        return str(entry)
    all_ids = [str(agent.get("id") or agent.get("agentId")) for agent in agents]
    # agentEdges are model-callable transfer tools, not deterministic graph
    # edges.  They cannot establish a unique entry on their own.
    incoming = set()
    for edge in action_edges:
        action = edge.get("action") or {}
        if action.get("type") in {"SWITCH_AGENT", "SWITCH_TO_AGENT"} and action.get("value"):
            incoming.add(str(action["value"]))
    candidates = [agent_id for agent_id in all_ids if agent_id and agent_id not in incoming]
    return candidates[0] if candidates else (all_ids[0] if all_ids else "")


def _graph_topology(
    entry_id: str,
    agents: list[dict],
    explicit_edges: list[dict],
    action_edges: list[dict],
) -> dict:
    """Separate deterministic control edges from model-selectable agent jumps."""
    agent_ids = {str(agent.get("id")) for agent in agents}
    outgoing = {agent_id: [] for agent_id in agent_ids}
    incoming = {agent_id: [] for agent_id in agent_ids}
    selectable_outgoing = {agent_id: [] for agent_id in agent_ids}
    selectable_incoming = {agent_id: [] for agent_id in agent_ids}
    control_edges = []
    model_selectable_edges = []

    for edge in explicit_edges:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source not in agent_ids or target not in agent_ids:
            continue
        item = {
            "edge_id": edge.get("edge_id"),
            "kind": "model_selectable_agent_edge",
            "from_agent": source,
            "to_agent": target,
            "label": "agent can choose",
            "routing_semantics": "model_selectable",
        }
        model_selectable_edges.append(item)
        selectable_outgoing[source].append(item)
        selectable_incoming[target].append(item)

    for edge in action_edges:
        action = edge.get("action") or {}
        action_type = action.get("type")
        target = str(action.get("value") or "")
        if action_type not in {"SWITCH_AGENT", "SWITCH_TO_AGENT"} or target not in agent_ids:
            continue
        item = {
            "edge_id": edge.get("action_id"),
            "kind": "action_switch_agent",
            "from_agent": str(edge.get("from_agent") or ""),
            "to_agent": target,
            "label": edge.get("match_status") or action_type,
            "action_type": action_type,
        }
        if item["from_agent"] not in agent_ids:
            continue
        control_edges.append(item)
        outgoing[item["from_agent"]].append(item)
        incoming[target].append(item)

    deterministic_reachable = set()
    queue = deque([entry_id] if entry_id in agent_ids else [])
    while queue:
        current = queue.popleft()
        if current in deterministic_reachable:
            continue
        deterministic_reachable.add(current)
        queue.extend(edge["to_agent"] for edge in outgoing.get(current, []))

    # A legacy agentEdge can make its target executable at runtime, but only
    # when the upstream model chooses its transfer tool.  Keep that potential
    # reachability for coverage/risk analysis without turning it into a target
    # deterministic edge in the migrated graph.
    reachable = set()
    queue = deque([entry_id] if entry_id in agent_ids else [])
    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        queue.extend(edge["to_agent"] for edge in outgoing.get(current, []))
        queue.extend(edge["to_agent"] for edge in selectable_outgoing.get(current, []))

    node_summary = []
    for agent in agents:
        agent_id = str(agent.get("id"))
        node_summary.append({
            "id": agent_id,
            "name": agent.get("name"),
            "reachable": agent_id in reachable,
            "deterministically_reachable": agent_id in deterministic_reachable,
            "in_degree": len(incoming.get(agent_id, [])),
            "out_degree": len(outgoing.get(agent_id, [])),
            "incoming_edge_ids": [edge.get("edge_id") for edge in incoming.get(agent_id, [])],
            "outgoing_edge_ids": [edge.get("edge_id") for edge in outgoing.get(agent_id, [])],
            "model_selectable_in_degree": len(selectable_incoming.get(agent_id, [])),
            "model_selectable_out_degree": len(selectable_outgoing.get(agent_id, [])),
            "model_selectable_incoming_edge_ids": [
                edge.get("edge_id") for edge in selectable_incoming.get(agent_id, [])
            ],
            "model_selectable_outgoing_edge_ids": [
                edge.get("edge_id") for edge in selectable_outgoing.get(agent_id, [])
            ],
        })

    return {
        "entry_agent_id": entry_id,
        "reachable_agent_ids": sorted(reachable),
        "deterministically_reachable_agent_ids": sorted(deterministic_reachable),
        "unreachable_agent_ids": sorted(agent_ids - reachable),
        "control_edges": control_edges,
        "model_selectable_edges": model_selectable_edges,
        "nodes": node_summary,
    }


def _build_chunks(entry_id: str, agents: list[dict], explicit_edges: list[dict], action_edges: list[dict]) -> list[dict]:
    by_id = {agent["id"]: agent for agent in agents}
    deterministic_adj = {agent_id: [] for agent_id in by_id}
    selectable_adj = {agent_id: [] for agent_id in by_id}
    for edge in explicit_edges:
        if edge.get("from") in selectable_adj and edge.get("to") in by_id:
            selectable_adj[edge["from"]].append(edge["to"])
    for edge in action_edges:
        action = edge.get("action") or {}
        if action.get("type") in {"SWITCH_AGENT", "SWITCH_TO_AGENT"} and str(action.get("value")) in by_id:
            deterministic_adj.setdefault(edge["from_agent"], []).append(str(action["value"]))

    ordered = []
    seen = set()
    queue = deque([entry_id] if entry_id else [])
    while queue:
        agent_id = queue.popleft()
        if agent_id in seen or agent_id not in by_id:
            continue
        seen.add(agent_id)
        ordered.append(agent_id)
        queue.extend(deterministic_adj.get(agent_id, []))
        queue.extend(selectable_adj.get(agent_id, []))
    ordered.extend(agent["id"] for agent in agents if agent["id"] not in seen)

    chunks = []
    for idx, agent_id in enumerate(ordered):
        agent = by_id[agent_id]
        suffix = "entry" if agent_id == entry_id else _safe_name(agent.get("name"), "agent")
        chunk_id = f"chunk_{idx:02d}_{suffix}"
        local_out = sorted(set(deterministic_adj.get(agent_id, [])))
        selectable_out = sorted(set(selectable_adj.get(agent_id, [])))
        action_out = [
            edge for edge in action_edges
            if edge.get("from_agent") == agent_id
        ]
        explicit_out = [
            edge for edge in explicit_edges
            if edge.get("from") == agent_id
        ]
        raw_agent = agent.get("raw_trimmed") if isinstance(agent.get("raw_trimmed"), dict) else {}
        meta = raw_agent.get("meta") if isinstance(raw_agent.get("meta"), dict) else {}
        if agent.get("tools"):
            role_hint = "tool_controller"
        elif meta.get("classifierPlugin"):
            role_hint = "classifier"
        elif action_out:
            role_hint = "transition_or_terminal_controller"
        elif agent.get("unresolved_tool_references"):
            role_hint = "prompt_tool_reference_review"
        else:
            role_hint = "conversation_logic_candidate"
        external_anchors = []
        for edge in action_out:
            action = edge.get("action") or {}
            action_type = action.get("type")
            if action_type in {"TRANSFER_TO_HUMAN"}:
                external_anchors.append("$transfer")
            elif action_type in {"FINISH_AGENT"}:
                external_anchors.append("$finish")
            elif action.get("value"):
                external_anchors.append(str(action["value"]))
        chunks.append({
            "id": chunk_id,
            "agent_ids": [agent_id],
            "agent_names": [agent.get("name")],
            "entry": agent_id == entry_id,
            "reachable": agent_id in seen,
            "outgoing_agent_ids": local_out,
            "model_selectable_agent_ids": selectable_out,
            "explicit_edge_ids": [edge.get("edge_id") for edge in explicit_out],
            "action_ids": [edge.get("action_id") for edge in action_out],
            "external_anchors": sorted(set(external_anchors)),
            "action_edges": len(action_out),
            "hint": agent.get("migration_hints", []),
            "role_hint": role_hint,
            "merge_candidate": role_hint == "conversation_logic_candidate",
            "merge_requires_contract_match": True,
        })
    return chunks


def _mermaid(index: dict) -> str:
    lines = ["flowchart TD"]
    for agent in index["agents"]:
        node_id = "A_" + _safe_name(agent["id"], "agent")
        label = f'{agent.get("name") or agent["id"]}<br/>tools:{len(agent.get("tools", []))} actions:{len(agent.get("action_edges", []))}'
        lines.append(f'  {node_id}["{label.replace(chr(34), chr(39))}"]')
    id_to_node = {agent["id"]: "A_" + _safe_name(agent["id"], "agent") for agent in index["agents"]}
    for edge in index["explicit_edges"]:
        if edge.get("from") in id_to_node and edge.get("to") in id_to_node:
            lines.append(
                f'  {id_to_node[edge["from"]]} -. agent can choose .-> {id_to_node[edge["to"]]}'
            )
    for edge in index["action_edges"]:
        src = id_to_node.get(edge.get("from_agent"))
        if not src:
            continue
        action = edge.get("action") or {}
        label = str(edge.get("match_status") or action.get("type") or "action").replace('"', "'")
        value = str(action.get("value") or action.get("type") or "terminal")
        if value in id_to_node:
            lines.append(f"  {src} -->|{label}| {id_to_node[value]}")
        elif action.get("type") == "TRANSFER_TO_HUMAN":
            lines.append(f"  {src} -->|{label}| TRANSFER[Transfer]")
        elif action.get("type") == "FINISH_AGENT":
            lines.append(f"  {src} -->|{label}| FINISH[Finish]")
        elif action.get("type") == "TEMPLATE_REPLY":
            lines.append(f"  {src} -->|{label}| TEMPLATE[Template Reply]")
    return "\n".join(lines) + "\n"


def _sop_mapping_mermaid(plan: object) -> str:
    """Render a user-reviewable SOP-to-node-category draft from a migration plan.

    This deliberately renders business blocks and node *categories*, never
    target-node fields or final graph edges. Large migrations call this only
    after all batch fragments and blocking questions have been consolidated.
    """
    if not isinstance(plan, dict):
        raise ValueError("migration plan must be a JSON object")
    mapping = plan.get("sop_mapping")
    if not isinstance(mapping, dict):
        raise ValueError("migration plan missing sop_mapping object")
    blocks = mapping.get("blocks")
    relations = mapping.get("relations")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("sop_mapping.blocks must be a non-empty list")
    if not isinstance(relations, list):
        raise ValueError("sop_mapping.relations must be a list")

    def text(value: object) -> str:
        return re.sub(r"[\[\]\"|\n\r]", " ", str(value or "")).strip()

    def categories(value: object) -> list[str]:
        values = value if isinstance(value, list) else [value]
        result = []
        for item in values:
            if isinstance(item, dict):
                item = item.get("type") or item.get("category") or item.get("name")
            name = text(item)
            if name and name not in result:
                result.append(name)
        return result

    by_id = {}
    node_ids = {}
    lines = ["flowchart TD"]
    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            raise ValueError(f"sop_mapping.blocks[{index}] must be an object")
        block_id = str(block.get("id") or block.get("key") or block.get("block_id") or "").strip()
        if not block_id:
            raise ValueError(f"sop_mapping.blocks[{index}] missing id")
        if block_id in by_id:
            raise ValueError(f"duplicate SOP mapping block id: {block_id}")
        node_id = "S_" + _safe_name(block_id, "block")
        if node_id in node_ids:
            raise ValueError(f"SOP mapping ids collide after Mermaid normalization: {block_id}")
        title = text(block.get("title") or block.get("name") or block.get("responsibility") or block_id)
        selected = categories(block.get("selected_nodes") or block.get("node_categories"))
        candidates = categories(block.get("candidate_nodes"))
        node_text = " + ".join(selected or candidates) or "待选择"
        prefix = "节点" if selected else "候选"
        lines.append(f'  {node_id}["{title}<br/>{prefix}: {node_text}"]')
        by_id[block_id] = node_id
        node_ids[node_id] = block_id

    for index, relation in enumerate(relations):
        if not isinstance(relation, dict):
            raise ValueError(f"sop_mapping.relations[{index}] must be an object")
        source = str(
            relation.get("from")
            or relation.get("from_block")
            or relation.get("source")
            or ""
        ).strip()
        target = str(
            relation.get("to")
            or relation.get("to_block")
            or relation.get("target")
            or ""
        ).strip()
        if source not in by_id or target not in by_id:
            raise ValueError(
                f"sop_mapping.relations[{index}] references an unknown block: {source!r} -> {target!r}"
            )
        label = text(
            relation.get("label")
            or relation.get("condition")
            or relation.get("on")
            or relation.get("match_status")
            or "下一步"
        )
        lines.append(f"  {by_id[source]} -->|{label}| {by_id[target]}")
    return "\n".join(lines) + "\n"


def analyze(raw: object, *, prompt_max_chars: int, prompt_terms: list[str]) -> dict:
    root, graph = _find_multi_agent_payload(raw)
    raw_agents = [agent for agent in graph.get("agents") or [] if isinstance(agent, dict)]
    explicit = _explicit_edges(graph)
    agents = []
    all_tools = []
    all_actions = []
    for agent in raw_agents:
        agent_id = str(agent.get("id") or agent.get("agentId") or "")
        tools, actions = _extract_tools_and_actions(agent)
        prompt_review = _prompt_review_contract(agent)
        terms = _collect_prompt_terms(agent)
        prompt_info = _prompt_evidence(agent.get("prompt") or "", terms, prompt_terms, prompt_max_chars)
        display_text = _clean_text(agent.get("displayPrompt") or "", keep_placeholders=False)
        raw_refs = _tool_references(
            agent.get("prompt") or "", agent.get("displayPrompt") or ""
        ) + _structured_system_references(agent)
        # Keep one reference per semantic source/name/type.  A rendered chip
        # and its structured metadata are two evidence sources for one item.
        unique_refs = []
        seen_refs = set()
        for ref in raw_refs:
            normalized_name = str(ref.get("name") or "").lower()
            normalized_key = re.sub(r"[^a-z0-9]", "", normalized_name)
            inferred_type = ref.get("resource_type") or SYSTEM_REFERENCE_KIND.get(normalized_key, (None, None))[1]
            key = (
                normalized_name,
                str(inferred_type or "").lower(),
            )
            if key in seen_refs:
                for existing in unique_refs:
                    if (
                        str(existing.get("name") or "").lower(),
                        str(existing.get("resource_type") or SYSTEM_REFERENCE_KIND.get(
                            re.sub(r"[^a-z0-9]", "", str(existing.get("name") or "").lower()),
                            (None, None),
                        )[1] or "").lower(),
                    ) == key:
                        existing["evidence_sources"] = sorted(set(
                            (existing.get("evidence_sources") or [existing.get("source")])
                            + [ref.get("source")]
                        ) - {None})
                        existing["actionable"] = bool(
                            existing.get("actionable", True) or ref.get("actionable", True)
                        )
                        if existing["actionable"]:
                            existing.pop("audit_reason", None)
                        if ref.get("resource_source"):
                            existing["resource_source"] = ref["resource_source"]
                        if ref.get("resource_type"):
                            existing["resource_type"] = ref["resource_type"]
                        break
                continue
            seen_refs.add(key)
            ref["evidence_sources"] = [ref.get("source")]
            unique_refs.append(ref)
        tool_refs = _bind_tool_references(agent, unique_refs)
        raw_classifier = (
            (agent.get("meta") or {}).get("classifierPlugin")
            if isinstance(agent.get("meta"), dict)
            else None
        )
        item = {
            "id": agent_id,
            "name": agent.get("name") or agent.get("title") or agent_id,
            "type": agent.get("type"),
            "prompt": _clean_prompt(agent.get("prompt") or ""),
            "tool_references": tool_refs,
            "unresolved_tool_references": [
                ref for ref in tool_refs
                if ref["binding"] == "unresolved" and _reference_requires_binding(ref)
            ],
            "tool_reference_audit_warnings": [
                ref for ref in tool_refs
                if ref["binding"] in {"unresolved", "non_actionable"}
                and not _reference_requires_binding(ref)
            ],
            "prompt_evidence": prompt_info,
            "prompt_review": prompt_review,
            "display_prompt": {
                "length": len(display_text),
                "text_excerpt": display_text[: min(1200, prompt_max_chars)],
                "placeholders": PLACEHOLDER_RE.findall(str(agent.get("displayPrompt") or "")),
                "html_removed": bool(
                    HTML_TAG_RE.search(str(agent.get("displayPrompt") or ""))
                    or ORPHAN_STYLE_RE.search(str(agent.get("displayPrompt") or ""))
                    or ORPHAN_ATTR_RE.search(str(agent.get("displayPrompt") or ""))
                ),
            },
            "tools": tools,
            "action_edges": actions,
            "meta_tools": _meta_tools(agent),
            "classifier": (
                _drop_frontend_noise(raw_classifier)
                if isinstance(raw_classifier, dict) and raw_classifier
                else None
            ),
            "migration_hints": _migration_hints(agent, tools, actions),
            "raw_trimmed": _drop_frontend_noise(agent),
        }
        display_encoding = _encoding_quality(agent.get("displayPrompt") or "")
        item["prompt_quality"] = {
            "prompt": prompt_info["encoding_quality"],
            "display_prompt": display_encoding["quality"],
            "cleaned_prompt": prompt_info["cleaned_encoding_quality"],
            "needs_human_review": False,
            "evidence": sorted(set(prompt_info["encoding_evidence"] + display_encoding["evidence"]))[:20],
        }
        agents.append(item)
        all_tools.extend(tools)
        all_actions.extend(actions)

    entry_id = _entry_agent_id(graph, raw_agents, explicit, all_actions)
    topology = _graph_topology(entry_id, agents, explicit, all_actions)
    topology_by_id = {item["id"]: item for item in topology["nodes"]}
    for agent in agents:
        agent["incoming"] = [
            edge for edge in topology["control_edges"] if edge.get("to_agent") == agent["id"]
        ]
        agent["outgoing"] = [
            edge for edge in topology["control_edges"] if edge.get("from_agent") == agent["id"]
        ]
        agent["model_selectable_incoming"] = [
            edge for edge in explicit if edge.get("to") == agent["id"]
        ]
        agent["model_selectable_outgoing"] = [
            edge for edge in explicit if edge.get("from") == agent["id"]
        ]
        agent["graph_position"] = topology_by_id.get(agent["id"], {
            "id": agent["id"],
            "name": agent.get("name"),
            "reachable": False,
            "deterministically_reachable": False,
            "in_degree": 0,
            "out_degree": 0,
            "incoming_edge_ids": [],
            "outgoing_edge_ids": [],
            "model_selectable_in_degree": 0,
            "model_selectable_out_degree": 0,
            "model_selectable_incoming_edge_ids": [],
            "model_selectable_outgoing_edge_ids": [],
        })

    source_id = root.get("id") or root.get("agentId") or graph.get("id") or entry_id or "unknown"
    source_name = root.get("name") or root.get("title") or graph.get("name") or "multi_agent"
    index = {
        "source": {
            "id": str(source_id),
            "name": source_name,
            "type": root.get("type") or "MULTI_AGENT",
        },
        "graph": {
            "entry_agent_id": entry_id,
            "agents_count": len(agents),
            "explicit_edges_count": len(explicit),
            "action_edges_count": len(all_actions),
            "prompt_reviews_count": sum(
                1 for agent in agents if isinstance(agent.get("prompt_review"), dict)
            ),
            "tools_count": len(all_tools),
            "reachable_agents_count": len(topology["reachable_agent_ids"]),
            "unreachable_agents_count": len(topology["unreachable_agent_ids"]),
        },
        "agents": agents,
        "tools": all_tools,
        "explicit_edges": explicit,
        "action_edges": all_actions,
        "risk_items": _risk_items(agents, explicit, all_actions),
        "topology": topology,
    }
    for agent_id in topology["unreachable_agent_ids"]:
        agent = next((item for item in agents if item["id"] == agent_id), None)
        index["risk_items"].append({
            "type": "unreachable_agent",
            "severity": "blocking",
            "blocking": True,
            "requires_user_decision": True,
            "agent_id": agent_id,
            "agent_name": agent.get("name") if agent else agent_id,
            "resolution": "recover an incoming structural edge or explicitly confirm dropping the node",
        })
    index["resources"] = _resource_inventory(agents, all_tools)
    index["migration_contracts"] = _migration_contracts(agents, all_actions)
    index["coverage_manifest"] = _coverage_manifest(
        agents, all_tools, explicit, all_actions, index["resources"]
    )
    index["coverage_manifest"].update({
        key: [item["contract_id"] for item in index["migration_contracts"][key]]
        for key in ("classifiers", "templates", "interactions", "branches", "prompt_reviews")
    })
    index["coverage_manifest"]["counts"]["prompt_reviews"] = len(
        index["migration_contracts"]["prompt_reviews"]
    )
    index["chunks"] = _build_chunks(entry_id, agents, explicit, all_actions)
    return index


def _risk_items(agents: list[dict], explicit_edges: list[dict], action_edges: list[dict]) -> list[dict]:
    agent_ids = {agent["id"] for agent in agents}
    risks = []

    def add_risk(
        risk_type: str,
        *,
        severity: str,
        requires_user_decision: bool,
        **fields: object,
    ) -> None:
        risks.append({
            "type": risk_type,
            "severity": severity,
            "blocking": severity == "blocking",
            "requires_user_decision": requires_user_decision,
            **fields,
        })

    for edge in explicit_edges:
        if edge.get("from") not in agent_ids or edge.get("to") not in agent_ids:
            add_risk(
                "dangling_agent_edge",
                severity="blocking",
                requires_user_decision=True,
                edge=edge,
                resolution="recover the selectable target or explicitly approve dropping this legacy transfer capability",
            )
    for edge in action_edges:
        action = edge.get("action") or {}
        action_type = action.get("type")
        value = str(action.get("value") or "")
        if action_type in {"SWITCH_AGENT", "SWITCH_TO_AGENT"} and value not in agent_ids:
            add_risk(
                "dangling_switch_agent_action",
                severity="blocking",
                requires_user_decision=True,
                edge=edge,
                resolution="recover the target agent or explicitly approve dropping this branch",
            )
        if action_type == "TEMPLATE_REPLY" and not (action.get("template_id") or action.get("template_content")):
            add_risk(
                "template_action_without_template",
                severity="blocking",
                requires_user_decision=True,
                edge=edge,
                resolution="provide the original template or explicitly approve a replacement reply contract",
            )
    for agent in agents:
        for ref in agent.get("tool_references") or []:
            if ref.get("binding") == "non_actionable":
                add_risk(
                    "non_actionable_tool_reference",
                    severity="warning",
                    requires_user_decision=False,
                    agent_id=agent["id"],
                    agent_name=agent["name"],
                    reference=ref,
                    resolution="retain as prompt audit evidence; it does not identify a concrete tool",
                )
                continue
            if ref.get("binding") != "unresolved":
                continue

            executable = _reference_requires_binding(ref)
            evidence_sources = set(ref.get("evidence_sources") or [ref.get("source")])
            is_kb = ref.get("system_type") == "KNOWLEDGE_AI_REPLY"
            # Structured SYSTEM metadata is direct evidence that a capability
            # exists, unlike an unbound editor chip that may be stale display data.
            capability_required = executable or "structured_system_metadata" in evidence_sources
            if is_kb:
                risk_type = "knowledge_reference_without_config"
            elif executable:
                risk_type = "unresolved_tool_reference"
            else:
                risk_type = "unbound_display_tool_reference"
            add_risk(
                risk_type,
                severity="blocking" if capability_required else "warning",
                requires_user_decision=capability_required,
                agent_id=agent["id"],
                agent_name=agent["name"],
                reference=ref,
                resolution=(
                    "bind the executable reference to a real capability or explicitly remove it"
                    if capability_required
                    else "retain as audit evidence; do not create a user question from display-only data"
                ),
            )
        if agent["display_prompt"]["html_removed"] and not agent["prompt"]:
            add_risk(
                "display_prompt_html_without_prompt",
                severity="warning",
                requires_user_decision=False,
                agent_id=agent["id"],
                agent_name=agent["name"],
                resolution="display HTML is audit-only when no prompt business text remains",
            )
        kb = agent["meta_tools"].get("knowledge")
        kb_state = _knowledge_config_state(kb)
        if (
            kb_state["configured"]
            and kb_state["enabled"] is not False
            and not kb_state["directory_ids"]
        ):
            add_risk(
                "knowledge_config_without_directory",
                severity="blocking",
                requires_user_decision=True,
                agent_id=agent["id"],
                agent_name=agent["name"],
                knowledge_enabled=kb_state["enabled"],
                knowledge_config_sources=kb_state["config_sources"],
                resolution="provide a target KB directory or explicitly approve removing the enabled KB capability",
            )
    return risks


def _resource_inventory(agents: list[dict], tools: list[dict]) -> list[dict]:
    """Normalize external tools and system references into one audit list."""
    resources = []
    seen = set()

    def add_owner(
        resource: dict,
        agent_id: object,
        *,
        ref: dict | None = None,
    ) -> None:
        if agent_id is not None:
            resource["owner_agents"] = sorted(set(
                (resource.get("owner_agents") or []) + [agent_id]
            ))
        if ref is None:
            return
        resource["evidence_sources"] = sorted(set(
            (resource.get("evidence_sources") or [])
            + (ref.get("evidence_sources") or [ref.get("source")])
        ) - {None})

    for tool in tools:
        resource_id = str(tool.get("id") or tool.get("name") or "")
        key = ("EXTERNAL_TOOL", resource_id)
        if key in seen:
            continue
        seen.add(key)
        owner_agents = sorted({
            item.get("agent_id")
            for item in tools
            if str(item.get("id") or item.get("name") or "") == resource_id
        } - {None})
        resources.append({
            "id": tool.get("id"),
            "name": tool.get("name"),
            "resource_kind": "EXTERNAL_TOOL",
            "execution_kind": "HTTP_CALL" if tool.get("request_param") or tool.get("response_param") else "PLUGIN",
            "binding": "used_plugin",
            "owner_agents": owner_agents,
        })
    for agent in agents:
        for ref in agent.get("tool_references") or []:
            system_type = ref.get("system_type")
            if ref.get("binding") == "used_plugin":
                kind, execution, target = "EXTERNAL_TOOL", "HTTP_CALL", "TOOL"
            elif system_type == "KNOWLEDGE_AI_REPLY":
                kind, execution, target = "SYSTEM_KNOWLEDGE", "KNOWLEDGE_AI_REPLY", "KNOWLEDGE_RESPONSE_CAPABILITY"
            elif system_type == "TRANSFER_TO_HUMAN":
                kind, execution, target = "SYSTEM_ACTION", "TRANSFER_TO_HUMAN", "TRANSFER_TO_HUMAN"
            elif system_type == "TEMPLATE_REPLY":
                kind, execution, target = "SYSTEM_ACTION", "TEMPLATE_REPLY", "REPLY_OR_TRANSFER"
            elif system_type == "FINISH_AGENT":
                kind, execution, target = "SYSTEM_ACTION", "FINISH_AGENT", "FINISH"
            else:
                kind, execution, target = "UNKNOWN_REFERENCE", "UNKNOWN", None
            resource_id = str(ref.get("name") or "")
            if kind == "EXTERNAL_TOOL":
                existing = next(
                    (item for item in resources
                     if item.get("resource_kind") == "EXTERNAL_TOOL"
                     and str(item.get("name") or "").lower() == resource_id.lower()),
                    None,
                )
                if existing:
                    add_owner(
                        existing,
                        agent.get("id"),
                        ref=ref,
                    )
                    continue
            key = (kind, resource_id.lower())
            if key in seen:
                existing = next(
                    (
                        item for item in resources
                        if item.get("resource_kind") == kind
                        and str(item.get("name") or "").lower() == resource_id.lower()
                    ),
                    None,
                )
                if existing:
                    add_owner(
                        existing,
                        agent.get("id"),
                        ref=ref,
                    )
                continue
            seen.add(key)
            resource = {
                "id": None,
                "name": ref.get("name"),
                "resource_kind": kind,
                "execution_kind": execution,
                "target": target,
                "binding": ref.get("binding"),
                "resource_source": ref.get("resource_source"),
                "resource_type": ref.get("resource_type"),
                "evidence_sources": [],
                "owner_agents": [],
            }
            add_owner(
                resource,
                agent.get("id"),
                ref=ref,
            )
            resources.append(resource)
    return resources


def _coverage_manifest(
    agents: list[dict],
    tools: list[dict],
    explicit_edges: list[dict],
    action_edges: list[dict],
    resources: list[dict],
) -> dict:
    return {
        "agents": [str(agent.get("id")) for agent in agents],
        "tools": [str(tool.get("tool_key")) for tool in tools],
        "explicit_edges": [str(edge.get("edge_id")) for edge in explicit_edges],
        "actions": [str(edge.get("action_id")) for edge in action_edges],
        "resources": [
            _stable_id("resource", item.get("resource_kind"), item.get("id"), item.get("name"))
            for item in resources
        ],
        "counts": {
            "agents": len(agents),
            "tools": len(tools),
            "explicit_edges": len(explicit_edges),
            "actions": len(action_edges),
            "resources": len(resources),
        },
    }


def _ai_index(full: dict) -> dict:
    def compact_action_edge(edge: dict) -> dict:
        action = edge.get("action") if isinstance(edge.get("action"), dict) else {}
        compact = {
            key: action.get(key)
            for key in ("type", "value", "reason", "template_id", "template_status", "template_content")
            if action.get(key) not in (None, "")
        }
        if isinstance(compact.get("template_content"), str):
            compact["template_content"] = compact["template_content"][:800]
        return {
            "action_id": edge.get("action_id"),
            "source": edge.get("source"),
            "from_agent": edge.get("from_agent"),
            "tool_id": edge.get("tool_id"),
            "tool_name": edge.get("tool_name"),
            "match_status": edge.get("match_status"),
            "action": compact,
        }

    def compact_param(value: object) -> object:
        if not isinstance(value, dict):
            return value if isinstance(value, (str, int, float, bool)) or value is None else None
        items = value.get("items")
        if isinstance(items, list):
            return {
                "items": [
                    {
                        key: item.get(key)
                        for key in ("name", "type", "required", "source", "effect", "apiName")
                        if isinstance(item, dict) and item.get(key) is not None
                    }
                    for item in items
                    if isinstance(item, dict)
                ]
            }
        return {
            key: value.get(key)
            for key in ("name", "type", "required", "source", "effect", "apiName")
            if value.get(key) is not None
        }

    def compact_meta(meta_tools: dict) -> dict:
        result = {}
        for key, value in meta_tools.items():
            if not isinstance(value, dict):
                if value is not None:
                    result[key] = value
                continue
            item = {
                field: value.get(field)
                for field in ("id", "name", "type", "enable", "visible", "directoryIds", "knowledgeDirectoryIds")
                if value.get(field) is not None
            }
            if key == "knowledge":
                kb_state = _knowledge_config_state(value)
                item["effective_enabled"] = kb_state["enabled"]
                item["effective_directory_ids"] = kb_state["directory_ids"]
            meta = value.get("meta") if isinstance(value.get("meta"), dict) else {}
            for config_name in ("externalHttpCallConfig", "templateReplyConfig", "transferToHumanConfig", "knowledgeAiReplyConfig"):
                config = meta.get(config_name)
                if not isinstance(config, dict):
                    continue
                compact = {field: config.get(field) for field in ("enable", "directoryIds", "kuLabelValueIds", "responseTemplate", "enableResponseTemplate") if config.get(field) is not None}
                if config.get("requestParam") is not None:
                    compact["requestParam"] = compact_param(config["requestParam"])
                if compact:
                    item[config_name] = compact
            if item:
                result[key] = item
        return result

    def compact_tool(tool: dict) -> dict:
        return {
            "agent_id": tool.get("agent_id"),
            "tool_key": tool.get("tool_key"),
            "id": tool.get("id"),
            "name": tool.get("name"),
            "type": tool.get("type"),
            "request_fields": compact_param(tool.get("request_param")),
            "response_fields": compact_param(tool.get("response_param")),
            "action_statuses": tool.get("action_statuses", []),
        }

    def compact_prompt_evidence(agent: dict) -> dict:
        evidence = agent.get("prompt_evidence") or {}
        compact = {
            "length": evidence.get("length", 0),
            "evidence": evidence.get("evidence") or "",
        }
        if evidence.get("encoding_quality") not in (None, "clean"):
            compact["encoding_quality"] = evidence.get("encoding_quality")
        if evidence.get("cleaned_encoding_quality") not in (None, "clean"):
            compact["cleaned_encoding_quality"] = evidence.get("cleaned_encoding_quality")
        return compact

    def compact_prompt_quality(agent: dict) -> dict | None:
        quality = agent.get("prompt_quality") or {}
        compact = {}
        for key in ("prompt", "display_prompt", "cleaned_prompt"):
            value = quality.get(key)
            if value and value != "clean":
                compact[key] = value
        if quality.get("needs_human_review"):
            compact["needs_human_review"] = True
        evidence = quality.get("evidence") or []
        if evidence:
            compact["evidence"] = evidence
        return compact or None

    agents = []
    for agent in full["agents"]:
        item = {
            "id": agent["id"],
            "name": agent["name"],
            "type": agent["type"],
            "tool_references": agent["tool_references"],
            "prompt_evidence": compact_prompt_evidence(agent),
            "prompt_review": {
                key: deepcopy(value)
                for key, value in (agent.get("prompt_review") or {}).items()
                if key != "prompt"
            },
            "tool_ids": [tool.get("id") for tool in agent["tools"] if tool.get("id")],
            "meta_tools": compact_meta(agent["meta_tools"]),
            "incoming": agent["incoming"],
            "outgoing": agent["outgoing"],
            "model_selectable_incoming": agent["model_selectable_incoming"],
            "model_selectable_outgoing": agent["model_selectable_outgoing"],
            "graph_position": agent["graph_position"],
            "action_edges": [compact_action_edge(edge) for edge in agent.get("action_edges") or []],
            "migration_hints": agent["migration_hints"],
        }
        prompt_quality = compact_prompt_quality(agent)
        if prompt_quality:
            item["prompt_quality"] = prompt_quality
        agents.append(item)
    return {
        "source": full["source"],
        "graph": full["graph"],
        "agents": agents,
        "tools": [compact_tool(tool) for tool in full["tools"]],
        "resources": full.get("resources", []),
        "coverage_manifest": full.get("coverage_manifest", {}),
        "migration_contracts": full.get("migration_contracts", {}),
        "explicit_edges": full["explicit_edges"],
        "action_edges": [compact_action_edge(edge) for edge in full["action_edges"]],
        "handoff_groups": _handoff_groups(full),
        "chunks": full["chunks"],
        "risk_items": full["risk_items"],
        "topology": {
            "entry_agent_id": full["topology"]["entry_agent_id"],
            "reachable_agent_ids": full["topology"]["reachable_agent_ids"],
            "deterministically_reachable_agent_ids": full["topology"].get(
                "deterministically_reachable_agent_ids", []
            ),
            "unreachable_agent_ids": full["topology"]["unreachable_agent_ids"],
            "control_edges": full["topology"]["control_edges"],
            "model_selectable_edges": full["topology"].get("model_selectable_edges", []),
        },
        "migration_contract": {
            "required_phases": [
                "flow_understanding",
                "mapping_decisions",
                "coverage_review",
                "source_generation",
            ],
            "node_types_are_open_choice": True,
            "mermaid_is_visual_evidence_only": True,
            "preserve_raw_and_clean_prompt_evidence": True,
        },
    }


def _candidate_nodes(agent: dict) -> list[str]:
    """Offer semantic candidates without deciding the target node for AI."""
    hints = set(agent.get("migration_hints") or [])
    candidates = ["AGENT"]
    if "classifier" in hints:
        candidates.append("INTENT")
    if "has_real_tools" in hints:
        candidates.append("TOOL")
    if "has_tool_action_statuses" in hints or "has_structural_actions" in hints:
        candidates.append("IF_ELSE")
    if "candidate_merge_or_reply" in hints:
        candidates.extend(["QUESTION", "REPLY"])
    action_types = {
        (edge.get("action") or {}).get("type")
        for edge in agent.get("action_edges") or []
    }
    if "TRANSFER_TO_HUMAN" in action_types:
        candidates.append("TRANSFER_TO_HUMAN")
    if "FINISH_AGENT" in action_types:
        candidates.append("FINISH")
    return list(dict.fromkeys(candidates))


def _handoff_groups(full: dict) -> list[dict]:
    """Partition handoffs by responsibility and terminal reply contract."""
    agents_by_id = {str(agent.get("id")): agent for agent in full.get("agents") or []}
    groups = {}
    for edge in full.get("action_edges") or []:
        action = edge.get("action") if isinstance(edge.get("action"), dict) else {}
        if action.get("type") != "TRANSFER_TO_HUMAN":
            continue
        source_id = str(edge.get("from_agent") or "")
        agent = agents_by_id.get(source_id, {})
        contract = {
            "transfer_type": "TEMPLATE" if action.get("template_id") else ("PROMPT" if action.get("template_content") else "NO_REPLY"),
            "reason": action.get("reason"),
            "template_id": action.get("template_id"),
            "template_status": action.get("template_status"),
            "template_content": action.get("template_content"),
        }
        # The source agent is part of the default scope. AI may merge groups only
        # after confirming the business responsibility and terminal contract match.
        group_key = _stable_id(
            "handoff_group",
            source_id,
            agent.get("name"),
            contract.get("transfer_type"),
            contract.get("reason"),
            contract.get("template_id"),
            contract.get("template_content"),
        )
        group = groups.setdefault(group_key, {
            "group_key": group_key,
            "responsibility_hint": agent.get("name") or source_id,
            "source_agent_ids": [],
            "source_agent_names": [],
            "action_ids": [],
            "branch_labels": [],
            "terminal_contract": contract,
            "recommended_node_key": f"handoff_{_safe_name(agent.get('name'), 'agent')}",
            "reuse_policy": "merge only when responsibility, user turn, branch reason, and terminal contract match",
        })
        if source_id not in group["source_agent_ids"]:
            group["source_agent_ids"].append(source_id)
            group["source_agent_names"].append(agent.get("name") or source_id)
        if edge.get("action_id") not in group["action_ids"]:
            group["action_ids"].append(edge.get("action_id"))
        if edge.get("match_status") and edge.get("match_status") not in group["branch_labels"]:
            group["branch_labels"].append(edge.get("match_status"))
    return list(groups.values())


def _terminal_action_groups(full: dict) -> list[dict]:
    """Partition legacy terminal/reply actions so shared target collapse is visible."""
    agents_by_id = {str(agent.get("id")): agent for agent in full.get("agents") or []}
    groups = []
    for edge in full.get("action_edges") or []:
        action = edge.get("action") if isinstance(edge.get("action"), dict) else {}
        action_type = action.get("type")
        if action_type not in {"TRANSFER_TO_HUMAN", "TEMPLATE_REPLY", "FINISH_AGENT"}:
            continue
        source_id = str(edge.get("from_agent") or "")
        agent = agents_by_id.get(source_id, {})
        template_id = action.get("template_id")
        template_content = action.get("template_content") or ""
        reply_type = "TEMPLATE" if template_id else ("PROMPT" if template_content else "NO_REPLY")
        contract = {
            "action_type": action_type,
            "reply_type": reply_type,
            "reason": action.get("reason"),
            "template_id": template_id,
            "template_status": action.get("template_status"),
            "template_content": template_content,
            "match_status": edge.get("match_status"),
        }
        group_key = _stable_id(
            "terminal_group",
            action_type,
            source_id,
            agent.get("name"),
            edge.get("match_status"),
            action.get("reason"),
            reply_type,
            template_id,
            template_content,
        )
        if action_type == "TRANSFER_TO_HUMAN":
            recommended_target = f"handoff_{_safe_name(agent.get('name'), 'agent')}"
            reuse_policy = "merge only when responsibility, branch reason, user turn, and transfer reply contract match"
        elif action_type == "TEMPLATE_REPLY":
            recommended_target = f"reply_{_safe_name(edge.get('match_status') or agent.get('name'), 'template')}"
            reuse_policy = "merge only when template id/content and downstream terminal semantics match"
        else:
            recommended_target = "$finish" if reply_type == "NO_REPLY" else f"reply_{_safe_name(edge.get('match_status') or agent.get('name'), 'finish')}"
            reuse_policy = "bare no-reply finish may share $finish; finish with reply needs its own reply contract"
        groups.append({
            "group_key": group_key,
            "action_id": edge.get("action_id"),
            "source_agent_id": source_id,
            "source_agent_name": agent.get("name") or source_id,
            "branch_label": edge.get("match_status"),
            "terminal_contract": contract,
            "recommended_target": recommended_target,
            "reuse_policy": reuse_policy,
        })
    return groups


def _flow_understanding_seed(full: dict) -> dict:
    """Build deterministic evidence for the AI's semantic understanding phase."""
    agents_by_id = {str(agent.get("id")): agent for agent in full.get("agents") or []}
    chunks = []
    for chunk in full.get("chunks") or []:
        agent_id = str((chunk.get("agent_ids") or [""])[0])
        agent = agents_by_id.get(agent_id, {})
        chunks.append({
            "chunk_id": chunk.get("id"),
            "old_agent_ids": chunk.get("agent_ids", []),
            "old_agent_names": chunk.get("agent_names", []),
            "entry": chunk.get("entry", False),
            "reachable": chunk.get("reachable", False),
            "role_hint": chunk.get("role_hint"),
            "candidate_nodes": _candidate_nodes(agent),
            "incoming_control_edges": agent.get("incoming", []),
            "outgoing_control_edges": agent.get("outgoing", []),
            "model_selectable_incoming": agent.get("model_selectable_incoming", []),
            "model_selectable_outgoing": agent.get("model_selectable_outgoing", []),
            "explicit_edge_ids": chunk.get("explicit_edge_ids", []),
            "action_ids": chunk.get("action_ids", []),
            "external_anchors": chunk.get("external_anchors", []),
            "tool_names": [tool.get("name") for tool in agent.get("tools", [])],
            "waits_for_user": None,
            "phase": None,
            "branch_contract": [],
            "merge_candidates": [],
        })
    return {
        "version": "1",
        "status": "seed_only",
        "instruction": "AI must complete phase and branch semantics before selecting target nodes.",
        "entry_agent_id": full.get("topology", {}).get("entry_agent_id"),
        "stages": [],
        "user_turns": [],
        "terminals": [],
        "handoff_groups": _handoff_groups(full),
        "terminal_action_groups": _terminal_action_groups(full),
        "merge_points": [],
        "chunks": chunks,
        "control_edges": full.get("topology", {}).get("control_edges", []),
        "explicit_edges": full.get("explicit_edges", []),
        "action_edges": full.get("action_edges", []),
        "open_questions": [],
    }


def _migration_plan_template(full: dict) -> dict:
    """Create an auditable, intentionally undecided plan for the AI."""
    flow_understanding = _flow_understanding_seed(full)
    return {
        "version": "1",
        "status": "mapping_required",
        "flow_understanding": flow_understanding,
        "flow_skeleton": {
            "status": "draft_required",
            "source": "flow_understanding.seed",
            "entry_agent_id": flow_understanding.get("entry_agent_id"),
            "stages": [],
            "protected_branches": [],
            "merge_points": [],
            "open_questions": [],
        },
        "sop_mapping": {
            "status": "draft_required",
            "blocks": [],
            "relations": [],
        },
        "merge_groups": [],
        "handoff_groups": [
            {
                **group,
                "target_node_key": "",
                "decision": "pending",
                "reason": "",
                "evidence": [],
                "merged_group_keys": [],
            }
            for group in _handoff_groups(full)
        ],
        "terminal_action_groups": [
            {
                **group,
                "target_node_key": "",
                "decision": "pending",
                "reason": "",
                "evidence": [],
                "merged_group_keys": [],
            }
            for group in _terminal_action_groups(full)
        ],
        "node_decision": [
            {
                "old_id": agent.get("id"),
                "old_name": agent.get("name"),
                "candidate_nodes": _candidate_nodes(agent),
                "selected_nodes": [],
                "reason": "",
                "evidence": [],
                "merged_from": [],
                "split_into": [],
                "open_questions": [],
            }
            for agent in full.get("agents") or []
        ],
        "coverage": {
            "agents": [
                {"old_id": agent.get("id"), "decision": "pending", "mapped_to": [], "reason": "", "evidence": []}
                for agent in full.get("agents") or []
            ],
            "tools": [
                {"old_tool_key": tool.get("tool_key"), "old_tool_id": tool.get("id"), "decision": "pending", "mapped_to": [], "reason": "", "evidence": []}
                for tool in full.get("tools") or []
            ],
            "actions": [
                {"action_id": edge.get("action_id"), "decision": "pending", "mapped_to": [], "reason": "", "evidence": []}
                for edge in full.get("action_edges") or []
            ],
            "explicit_edges": [
                {
                    "edge_id": edge.get("edge_id"),
                    "routing_semantics": edge.get("routing_semantics", "model_selectable"),
                    "decision": "pending",
                    "mapped_to": [],
                    "reason": "",
                    "evidence": [],
                }
                for edge in full.get("explicit_edges") or []
            ],
            "resources": [
                {"resource_id": _stable_id("resource", item.get("resource_kind"), item.get("id"), item.get("name")), "decision": "pending", "mapped_to": [], "reason": "", "evidence": []}
                for item in full.get("resources") or []
            ],
            **{
                section: [
                    {"contract_id": item.get("contract_id"), "decision": "pending", "mapped_to": [], "reason": "", "evidence": []}
                    for item in (full.get("migration_contracts") or {}).get(section, [])
                ]
                for section in (
                    "classifiers",
                    "templates",
                    "interactions",
                    "branches",
                    "prompt_blocks",
                )
            },
            "prompt_reviews": [
                {
                    "contract_id": item.get("contract_id"),
                    "agent_id": item.get("agent_id"),
                    "source_prompt_sha256": item.get("prompt_sha256"),
                    "reviewed_full_prompt": None,
                    "decision": "pending",
                    "mapped_to": [],
                    "reason": "",
                    "evidence": [],
                    "discovered_blocks": [],
                    "control_semantics": [],
                }
                for item in (full.get("migration_contracts") or {}).get("prompt_reviews", [])
            ],
        },
        "open_questions": [],
    }


def _migration_progress_template(full: dict, migrate_dir: Path) -> dict:
    chunks = []
    for chunk in full.get("chunks") or []:
        chunks.append({
            "id": chunk.get("id"),
            "status": "pending",
            "agent_ids": chunk.get("agent_ids") or [],
            "updated_at_ms": None,
            "outputs": {},
            "notes": [],
        })
    now = _now_ms()
    return {
        "schema_version": 3,
        "phase": "inspect_complete",
        "source": full.get("source"),
        "current_chunk_id": None,
        "active_batch_ids": [],
        "current_batch_id": None,
        "created_at_ms": now,
        "updated_at_ms": now,
        "summary": {
            "total_chunks": len(chunks),
            "pending": len(chunks),
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
        },
        "chunks": chunks,
        "batches": [],
        "batch_summary": {
            "total_batches": 0,
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "failed": 0,
        },
        "artifacts": {
            "dir": str(migrate_dir),
            "index_full": str(migrate_dir / "index.full.json"),
            "index_ai": str(migrate_dir / "index.ai.json"),
            "chunks": str(migrate_dir / "chunks.json"),
            "migration_plan": str(migrate_dir / "migration_plan.json"),
            "validation_report": str(migrate_dir / "validation_report.json"),
            "batches_dir": str(migrate_dir / "batches"),
            "worker_manifest": str(migrate_dir / "batches" / "worker_manifest.json"),
            "open_questions": str(migrate_dir / "open_questions.json"),
            "sop_mapping_mermaid": str(migrate_dir / "sop_mapping.mmd"),
        },
    }


def _ensure_batch_progress_state(progress: dict) -> None:
    """Upgrade legacy progress documents in memory without losing chunk history."""
    if not isinstance(progress, dict):
        raise ValueError("progress must be a JSON object")
    if not isinstance(progress.get("chunks"), list):
        raise ValueError("progress chunks must be a list")
    if not isinstance(progress.get("batches"), list):
        progress["batches"] = []
    progress.setdefault("current_batch_id", None)
    if not isinstance(progress.get("active_batch_ids"), list):
        progress["active_batch_ids"] = [
            str(item.get("id"))
            for item in progress["batches"]
            if isinstance(item, dict)
            and item.get("id")
            and item.get("status") == "in_progress"
        ]
    if not isinstance(progress.get("batch_summary"), dict):
        progress["batch_summary"] = {}
    if not isinstance(progress.get("schema_version"), int) or progress["schema_version"] < 3:
        progress["schema_version"] = 3


def _recalculate_progress(progress: dict) -> None:
    chunks = progress.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("progress chunks must be a list")
    counts = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
    for item in chunks:
        if not isinstance(item, dict):
            continue
        item_status = item.get("status")
        if item_status in counts:
            counts[item_status] += 1
    progress["summary"] = {"total_chunks": len(chunks), **counts}

    batches = progress.get("batches") if isinstance(progress.get("batches"), list) else []
    batch_counts = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        status = batch.get("status")
        if status in batch_counts:
            batch_counts[status] += 1
    progress["batch_summary"] = {"total_batches": len(batches), **batch_counts}
    active_batch_ids = [
        str(batch.get("id"))
        for batch in batches
        if isinstance(batch, dict)
        and batch.get("id")
        and batch.get("status") == "in_progress"
    ]
    progress["active_batch_ids"] = active_batch_ids
    # Retained for old migration directories. It is intentionally unset when
    # more than one worker batch is active.
    progress["current_batch_id"] = active_batch_ids[0] if len(active_batch_ids) == 1 else None

    if counts["failed"]:
        progress["phase"] = "blocked"
    elif chunks and counts["completed"] == len(chunks):
        progress["phase"] = "chunks_complete"
    elif active_batch_ids:
        progress["phase"] = "batch_migration"
    elif counts["in_progress"]:
        progress["phase"] = "chunk_migration"
    elif progress.get("phase") in {"blocked", "batch_migration", "chunk_migration", "chunks_complete"}:
        progress["phase"] = "inspect_complete"


def _progress_chunk(progress: dict, chunk_id: str) -> dict:
    chunks = progress.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("progress chunks must be a list")
    target = next(
        (item for item in chunks if isinstance(item, dict) and item.get("id") == chunk_id),
        None,
    )
    if target is None:
        raise ValueError(f"chunk not found in progress: {chunk_id}")
    return target


def _update_progress(
    progress: dict,
    *,
    chunk_id: str,
    status: str,
    note: str | None = None,
    artifacts: dict[str, str] | None = None,
) -> dict:
    _ensure_batch_progress_state(progress)
    chunks = progress["chunks"]
    target = _progress_chunk(progress, chunk_id)

    active_batch = next(
        (
            item
            for item in progress["batches"]
            if isinstance(item, dict)
            and item.get("status") == "in_progress"
            and chunk_id in {str(owned) for owned in item.get("chunk_ids") or []}
        ),
        None,
    )
    if active_batch:
        raise ValueError(
            f"chunk '{chunk_id}' is owned by active batch '{active_batch.get('id')}'; "
            "use update-batch-progress instead"
        )

    if status == "in_progress":
        active_chunk_ids = [
            str(item.get("id"))
            for item in chunks
            if isinstance(item, dict)
            and item.get("id") != chunk_id
            and item.get("status") == "in_progress"
        ]
        if active_chunk_ids:
            raise ValueError(
                f"cannot start chunk '{chunk_id}': "
                f"chunk(s) already in progress: {', '.join(active_chunk_ids)}"
            )

    target["status"] = status
    target["updated_at_ms"] = _now_ms()
    if note:
        notes = target.setdefault("notes", [])
        if isinstance(notes, list):
            notes.append(note)
    if artifacts:
        outputs = target.setdefault("outputs", {})
        if isinstance(outputs, dict):
            outputs.update(artifacts)

    if status == "in_progress":
        progress["current_chunk_id"] = chunk_id
        progress["phase"] = "chunk_migration"
    elif progress.get("current_chunk_id") == chunk_id:
        progress["current_chunk_id"] = None

    _recalculate_progress(progress)
    progress["updated_at_ms"] = _now_ms()
    return progress


def _chunk_control_adjacency(index: dict, chunks: list[dict]) -> dict[str, set[str]]:
    """Map deterministic legacy control edges to chunks for batch grouping."""
    chunk_ids = [str(chunk.get("id")) for chunk in chunks if isinstance(chunk, dict) and chunk.get("id")]
    adjacency = {chunk_id: set() for chunk_id in chunk_ids}
    chunk_by_agent = {}
    for chunk in chunks:
        if not isinstance(chunk, dict) or not chunk.get("id"):
            continue
        chunk_id = str(chunk["id"])
        for agent_id in chunk.get("agent_ids") or []:
            chunk_by_agent.setdefault(str(agent_id), chunk_id)

    def add_edge(source_agent: object, target_agent: object) -> None:
        source_chunk = chunk_by_agent.get(str(source_agent or ""))
        target_chunk = chunk_by_agent.get(str(target_agent or ""))
        if source_chunk and target_chunk:
            adjacency[source_chunk].add(target_chunk)

    topology = index.get("topology") if isinstance(index.get("topology"), dict) else {}
    for edge in topology.get("control_edges") or []:
        if isinstance(edge, dict):
            add_edge(edge.get("from_agent"), edge.get("to_agent"))
    for edge in index.get("action_edges") or []:
        if not isinstance(edge, dict):
            continue
        action = edge.get("action") if isinstance(edge.get("action"), dict) else {}
        if action.get("type") in {"SWITCH_AGENT", "SWITCH_TO_AGENT"}:
            add_edge(edge.get("from_agent"), action.get("value"))
    return adjacency


def _chunk_scc_groups(index: dict, chunks: list[dict]) -> list[dict]:
    """Return SCC-safe chunk groups in deterministic topology order.

    A large legacy graph can contain retry/handoff cycles.  An iterative
    Kosaraju walk avoids Python's recursion limit and keeps all chunks in the
    same cycle in one migration batch.
    """
    ordered_chunks = [chunk for chunk in chunks if isinstance(chunk, dict) and chunk.get("id")]
    chunk_ids = [str(chunk["id"]) for chunk in ordered_chunks]
    position = {chunk_id: index for index, chunk_id in enumerate(chunk_ids)}
    adjacency = _chunk_control_adjacency(index, ordered_chunks)
    reverse_adjacency = {chunk_id: set() for chunk_id in chunk_ids}
    for source, targets in adjacency.items():
        for target in targets:
            reverse_adjacency[target].add(source)

    finished = []
    seen = set()
    for start in chunk_ids:
        if start in seen:
            continue
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                finished.append(node)
                continue
            if node in seen:
                continue
            seen.add(node)
            stack.append((node, True))
            for target in sorted(adjacency.get(node, set()), key=lambda value: position[value], reverse=True):
                if target not in seen:
                    stack.append((target, False))

    components = []
    assigned = set()
    for start in reversed(finished):
        if start in assigned:
            continue
        component = []
        stack = [start]
        assigned.add(start)
        while stack:
            node = stack.pop()
            component.append(node)
            for source in sorted(reverse_adjacency.get(node, set()), key=lambda value: position[value], reverse=True):
                if source not in assigned:
                    assigned.add(source)
                    stack.append(source)
        components.append(sorted(component, key=lambda value: position[value]))

    component_by_chunk = {
        chunk_id: component_index
        for component_index, component in enumerate(components)
        for chunk_id in component
    }
    component_edges = {index: set() for index in range(len(components))}
    indegree = {index: 0 for index in range(len(components))}
    for source, targets in adjacency.items():
        source_component = component_by_chunk[source]
        for target in targets:
            target_component = component_by_chunk[target]
            if source_component == target_component or target_component in component_edges[source_component]:
                continue
            component_edges[source_component].add(target_component)
            indegree[target_component] += 1

    entry_chunk_ids = {
        str(chunk.get("id"))
        for chunk in ordered_chunks
        if chunk.get("entry") is True
    }

    def component_key(component_index: int) -> tuple[int, int]:
        component = components[component_index]
        return (
            0 if entry_chunk_ids.intersection(component) else 1,
            min(position[chunk_id] for chunk_id in component),
        )

    ready = sorted(
        [component_index for component_index, value in indegree.items() if value == 0],
        key=component_key,
    )
    ordered_components = []
    while ready:
        component_index = ready.pop(0)
        ordered_components.append(component_index)
        for target_component in sorted(component_edges[component_index], key=component_key):
            indegree[target_component] -= 1
            if indegree[target_component] == 0:
                ready.append(target_component)
                ready.sort(key=component_key)

    for component_index in sorted(set(range(len(components))) - set(ordered_components), key=component_key):
        ordered_components.append(component_index)

    return [
        {
            "id": f"scc_{position_index:02d}",
            "chunk_ids": components[component_index],
            "cyclic": len(components[component_index]) > 1 or any(
                chunk_id in adjacency.get(chunk_id, set())
                for chunk_id in components[component_index]
            ),
        }
        for position_index, component_index in enumerate(ordered_components)
    ]


def _chunk_action_edge_count(chunk: dict, index: dict) -> int:
    value = chunk.get("action_edges")
    if isinstance(value, int) and not isinstance(value, bool):
        return max(value, 0)
    agent_ids = {str(item) for item in chunk.get("agent_ids") or []}
    return sum(
        1
        for edge in index.get("action_edges") or []
        if isinstance(edge, dict) and str(edge.get("from_agent") or "") in agent_ids
    )


def _batch_metrics(index: dict, chunks: list[dict]) -> dict:
    agent_ids = {
        str(agent_id)
        for chunk in chunks
        if isinstance(chunk, dict)
        for agent_id in chunk.get("agent_ids") or []
    }
    evidence_chars = 0
    full_prompt_chars = 0
    for agent in index.get("agents") or []:
        if not isinstance(agent, dict) or str(agent.get("id") or "") not in agent_ids:
            continue
        evidence = agent.get("prompt_evidence") if isinstance(agent.get("prompt_evidence"), dict) else {}
        evidence_chars += len(str(evidence.get("evidence") or ""))
        review = agent.get("prompt_review") if isinstance(agent.get("prompt_review"), dict) else {}
        full_prompt_chars += int(review.get("prompt_char_count") or 0)
    return {
        "chunks": len(chunks),
        "agents": len(agent_ids),
        "action_edges": sum(_chunk_action_edge_count(chunk, index) for chunk in chunks if isinstance(chunk, dict)),
        "evidence_chars": max(evidence_chars, full_prompt_chars),
        "full_prompt_chars": full_prompt_chars,
    }


def _select_pending_batch(
    index: dict,
    chunks: list[dict],
    progress: dict,
    *,
    max_chunks: int,
    max_action_edges: int,
    max_evidence_chars: int,
) -> dict:
    if max_chunks < 1:
        raise ValueError("max_chunks must be at least 1")
    if max_action_edges < 1:
        raise ValueError("max_action_edges must be at least 1")
    if max_evidence_chars < 0:
        raise ValueError("max_evidence_chars must be zero or greater")

    chunk_by_id = {
        str(chunk.get("id")): chunk
        for chunk in chunks
        if isinstance(chunk, dict) and chunk.get("id")
    }
    status_by_id = {
        str(chunk.get("id")): chunk.get("status")
        for chunk in progress.get("chunks") or []
        if isinstance(chunk, dict) and chunk.get("id")
    }
    selected = []
    selected_groups = []
    budget_exceptions = []
    for group in _chunk_scc_groups(index, chunks):
        group_ids = [chunk_id for chunk_id in group["chunk_ids"] if chunk_id in chunk_by_id]
        group_statuses = [status_by_id.get(chunk_id, "pending") for chunk_id in group_ids]
        pending_ids = [
            chunk_id for chunk_id, status in zip(group_ids, group_statuses)
            if status == "pending"
        ]
        if not pending_ids:
            if any(status == "failed" for status in group_statuses):
                break
            continue
        if any(status == "failed" for status in group_statuses):
            break
        if any(status == "in_progress" for status in group_statuses):
            raise ValueError(
                "cannot prepare a new batch while chunks are in progress outside an active batch: "
                + ", ".join(group_ids)
            )

        candidate = [chunk_by_id[chunk_id] for chunk_id in pending_ids]
        projected = _batch_metrics(index, selected + candidate)
        exceeds = (
            projected["chunks"] > max_chunks
            or projected["action_edges"] > max_action_edges
            or projected["evidence_chars"] > max_evidence_chars
        )
        if selected and exceeds:
            break
        if not selected and exceeds:
            budget_exceptions.append({
                "group_id": group["id"],
                "chunk_ids": pending_ids,
                "reason": "an SCC-safe group exceeds the configured batch budget and cannot be split",
                "metrics": projected,
            })
        selected.extend(candidate)
        selected_groups.append({**group, "chunk_ids": pending_ids})
        if projected["chunks"] >= max_chunks or projected["action_edges"] >= max_action_edges or projected["evidence_chars"] >= max_evidence_chars:
            break

    return {
        "chunks": selected,
        "groups": selected_groups,
        "metrics": _batch_metrics(index, selected),
        "budget_exceptions": budget_exceptions,
    }


def _coverage_requirements(index: dict, agent_ids: set[str]) -> dict:
    action_owner_by_id = {
        str(edge.get("action_id")): str(edge.get("from_agent") or "")
        for edge in index.get("action_edges") or []
        if isinstance(edge, dict) and edge.get("action_id")
    }
    entry_agent_id = str((index.get("graph") or {}).get("entry_agent_id") or "")

    def contract_belongs_to_batch(contract: dict) -> bool:
        owner = str(contract.get("agent_id") or contract.get("from_agent") or "")
        if not owner and contract.get("action_id"):
            owner = action_owner_by_id.get(str(contract.get("action_id")), "")
        if owner:
            return owner in agent_ids
        return bool(entry_agent_id and entry_agent_id in agent_ids)

    migration_contracts = (
        index.get("migration_contracts")
        if isinstance(index.get("migration_contracts"), dict)
        else {}
    )
    return {
        "agents": [
            {"old_id": agent.get("id"), "old_name": agent.get("name")}
            for agent in index.get("agents") or []
            if isinstance(agent, dict) and str(agent.get("id") or "") in agent_ids
        ],
        "tools": [
            {
                "old_tool_id": tool.get("id"),
                "old_tool_key": tool.get("tool_key"),
                "old_tool_name": tool.get("name"),
            }
            for tool in index.get("tools") or []
            if isinstance(tool, dict) and str(tool.get("agent_id") or "") in agent_ids
        ],
        "actions": [
            {
                "action_id": edge.get("action_id"),
                "from_old_agent": edge.get("from_agent"),
                "match_status": edge.get("match_status"),
                "action_type": (edge.get("action") or {}).get("type"),
            }
            for edge in index.get("action_edges") or []
            if isinstance(edge, dict) and str(edge.get("from_agent") or "") in agent_ids
        ],
        "explicit_edges": [
            {
                "edge_id": edge.get("edge_id"),
                "from_old_agent": edge.get("from"),
                "to_old_agent": edge.get("to"),
                "routing_semantics": edge.get("routing_semantics", "model_selectable"),
            }
            for edge in index.get("explicit_edges") or []
            if isinstance(edge, dict)
            and (
                str(edge.get("from") or "") in agent_ids
                or str(edge.get("to") or "") in agent_ids
            )
        ],
        "resources": [
            {
                **deepcopy(resource),
                "resource_id": _stable_id(
                    "resource",
                    resource.get("resource_kind"),
                    resource.get("id"),
                    resource.get("name"),
                ),
            }
            for resource in index.get("resources") or []
            if isinstance(resource, dict)
            and (
                {
                    str(owner)
                    for owner in resource.get("owner_agents") or []
                }.intersection(
                    agent_ids
                )
                or (
                    not resource.get("owner_agents")
                    and entry_agent_id in agent_ids
                )
            )
        ],
        **{
            section: [
                deepcopy(contract)
                for contract in migration_contracts.get(section) or []
                if isinstance(contract, dict) and contract_belongs_to_batch(contract)
            ]
            for section in (
                "classifiers",
                "templates",
                "interactions",
                "branches",
                "prompt_blocks",
            )
        },
        "prompt_reviews": [
            deepcopy(review)
            for review in migration_contracts.get("prompt_reviews", [])
            if isinstance(review, dict) and str(review.get("agent_id") or "") in agent_ids
        ],
    }


def _risk_matches_agent_ids(risk: dict, agent_ids: set[str]) -> bool:
    if str(risk.get("agent_id") or "") in agent_ids:
        return True
    edge = risk.get("edge") if isinstance(risk.get("edge"), dict) else {}
    for field in ("from_agent", "to_agent", "from", "to"):
        if str(edge.get(field) or "") in agent_ids:
            return True
    return False


def _batch_cross_anchors(index: dict, agent_ids: set[str]) -> dict:
    incoming = []
    outgoing = []
    terminals = []
    model_selectable = []

    def append_anchor(target: list[dict], *, kind: str, edge_id: object, source: object, destination: object, label: object) -> None:
        target.append({
            "kind": kind,
            "id": edge_id,
            "from_agent": source,
            "to_agent": destination,
            "label": label,
        })

    for edge in index.get("explicit_edges") or []:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("from") or "")
        destination = str(edge.get("to") or "")
        if source in agent_ids and destination not in agent_ids:
            append_anchor(
                model_selectable,
                kind="model_selectable_agent_edge",
                edge_id=edge.get("edge_id"),
                source=source,
                destination=destination,
                label="agent can choose",
            )
        elif source not in agent_ids and destination in agent_ids:
            append_anchor(
                model_selectable,
                kind="model_selectable_agent_edge",
                edge_id=edge.get("edge_id"),
                source=source,
                destination=destination,
                label="agent can choose",
            )
    for edge in index.get("action_edges") or []:
        if not isinstance(edge, dict):
            continue
        action = edge.get("action") if isinstance(edge.get("action"), dict) else {}
        source = str(edge.get("from_agent") or "")
        action_type = action.get("type")
        destination = str(action.get("value") or "")
        if action_type in {"SWITCH_AGENT", "SWITCH_TO_AGENT"}:
            if source in agent_ids and destination not in agent_ids:
                append_anchor(outgoing, kind="action_switch_agent", edge_id=edge.get("action_id"), source=source, destination=destination, label=edge.get("match_status") or action_type)
            elif source not in agent_ids and destination in agent_ids:
                append_anchor(incoming, kind="action_switch_agent", edge_id=edge.get("action_id"), source=source, destination=destination, label=edge.get("match_status") or action_type)
        elif source in agent_ids and action_type in {"TEMPLATE_REPLY", "TRANSFER_TO_HUMAN", "FINISH_AGENT"}:
            terminals.append({
                "action_id": edge.get("action_id"),
                "from_agent": source,
                "match_status": edge.get("match_status"),
                "action_type": action_type,
                "reason": action.get("reason"),
                "template_id": action.get("template_id"),
                "template_status": action.get("template_status"),
            })
    return {
        "incoming": incoming,
        "outgoing": outgoing,
        "terminals": terminals,
        "model_selectable_agent_edges": model_selectable,
    }


def _batch_worker_contract() -> dict:
    return {
        "interaction": "none",
        "mutate_shared_progress": False,
        "emit_mermaid": False,
        "required_output": [
            "batch_id",
            "chunk_ids",
            "old_semantics",
            "sop_mapping.blocks",
            "sop_mapping.relations",
            "coverage_delta",
            "prompt_cleanup",
            "open_questions",
        ],
        "prompt_reviews": (
            "Read every coverage_required.prompt_reviews.prompt in full. Infer executable "
            "semantics from the flow context, return discovered_blocks in source order, and "
            "cover every protected_refs entry with the same source span and concrete binding. "
            "Protected refs do not replace full-text review of fixed wording or wait points. "
            "Preserve concrete ids, exact transfer reasons, full fixed wording, and waits. "
            "Map FIXED_WORDING to NODE_PROMPT_FIELD without assuming a REPLY node; after the "
            "global node choice is confirmed, the coordinator must set the selected node's "
            "actual source render_path. Do not classify natural language with phrase or "
            "regex cases."
        ),
        "coverage": (
            "Return a decision for every record in every coverage_required section. Shared "
            "resources or cross-batch edges may appear in more than one batch; map only the "
            "targets supported by this batch. The deterministic merge unions mapped_to, "
            "rendered_to, and source_nodes while retaining each batch reason. Copy every stable "
            "identifier verbatim: agents.old_id, tools.old_tool_key, actions.action_id, "
            "explicit_edges.edge_id, resources.resource_id, and contract_id for every contract "
            "section. Never identify a tool by old_tool_id alone because one plugin can be "
            "referenced by multiple source agents."
        ),
        "open_questions": "Return only blocking executable-semantics questions; do not ask the user.",
    }


def _build_batch_context(
    index: dict,
    chunks: list[dict],
    batch: dict,
    *,
    max_evidence_chars: int,
) -> dict:
    chunk_by_id = {
        str(chunk.get("id")): chunk
        for chunk in chunks
        if isinstance(chunk, dict) and chunk.get("id")
    }
    selected_chunks = [
        deepcopy(chunk_by_id[chunk_id])
        for chunk_id in batch.get("chunk_ids") or []
        if chunk_id in chunk_by_id
    ]
    agent_ids = {
        str(agent_id)
        for chunk in selected_chunks
        for agent_id in chunk.get("agent_ids") or []
    }
    agents = []
    remaining_evidence_chars = max_evidence_chars
    evidence_truncated = False
    for agent in index.get("agents") or []:
        if not isinstance(agent, dict) or str(agent.get("id") or "") not in agent_ids:
            continue
        item = deepcopy(agent)
        # Context must stay safe even when a caller accidentally supplies the
        # full index instead of index.ai.json.
        item.pop("raw_trimmed", None)
        item.pop("prompt", None)
        evidence = item.get("prompt_evidence") if isinstance(item.get("prompt_evidence"), dict) else None
        if evidence is not None:
            original = str(evidence.get("evidence") or "")
            allowed = max(remaining_evidence_chars, 0)
            if len(original) > allowed:
                evidence["evidence"] = original[:allowed] + ("\n...[batch evidence truncated]" if allowed else "")
                evidence["batch_truncated"] = True
                evidence_truncated = True
            remaining_evidence_chars -= min(len(original), allowed)
        agents.append(item)

    resources = []
    shared_resources = []
    for resource in index.get("resources") or []:
        if not isinstance(resource, dict):
            continue
        owners = {str(item) for item in resource.get("owner_agents") or []}
        if not owners.intersection(agent_ids):
            continue
        item = deepcopy(resource)
        resources.append(item)
        if owners - agent_ids:
            item["shared_with_agent_ids"] = sorted(owners - agent_ids)
            shared_resources.append(item)

    scoped_risks = [
        deepcopy(risk)
        for risk in index.get("risk_items") or []
        if isinstance(risk, dict) and _risk_matches_agent_ids(risk, agent_ids)
    ]
    return {
        "schema_version": 1,
        "batch": deepcopy(batch),
        "source": index.get("source"),
        "graph": index.get("graph"),
        "chunks": selected_chunks,
        "agents": agents,
        "tools": [
            deepcopy(tool)
            for tool in index.get("tools") or []
            if isinstance(tool, dict) and str(tool.get("agent_id") or "") in agent_ids
        ],
        "resources": resources,
        "shared_resources": shared_resources,
        "explicit_edges": [
            deepcopy(edge)
            for edge in index.get("explicit_edges") or []
            if isinstance(edge, dict)
            and (
                str(edge.get("from") or "") in agent_ids
                or str(edge.get("to") or "") in agent_ids
            )
        ],
        "action_edges": [
            deepcopy(edge)
            for edge in index.get("action_edges") or []
            if isinstance(edge, dict) and str(edge.get("from_agent") or "") in agent_ids
        ],
        "handoff_groups": [
            deepcopy(group)
            for group in _handoff_groups(index)
            if isinstance(group, dict) and set(group.get("source_agent_ids") or []).intersection(agent_ids)
        ],
        "cross_batch_anchors": _batch_cross_anchors(index, agent_ids),
        "risk_items": {
            "blocking": [risk for risk in scoped_risks if risk.get("severity", "blocking") == "blocking"],
            "warnings": [risk for risk in scoped_risks if risk.get("severity", "blocking") != "blocking"],
        },
        "coverage_required": _coverage_requirements(index, agent_ids),
        "worker_contract": _batch_worker_contract(),
        "input_budget": {
            "max_evidence_chars": max_evidence_chars,
            "evidence_truncated": evidence_truncated,
            "included_evidence_chars": max_evidence_chars - max(remaining_evidence_chars, 0),
            "full_prompt_chars": sum(
                int(review.get("prompt_char_count") or len(str(review.get("prompt") or "")))
                for review in _coverage_requirements(index, agent_ids)["prompt_reviews"]
            ),
            "full_prompts_truncated": False,
        },
    }


def _batch_by_id(progress: dict, batch_id: str) -> dict:
    batch = next(
        (item for item in progress.get("batches") or [] if isinstance(item, dict) and item.get("id") == batch_id),
        None,
    )
    if batch is None:
        raise ValueError(f"batch not found in progress: {batch_id}")
    return batch


def _next_batch_id(progress: dict) -> str:
    used = {
        str(item.get("id"))
        for item in progress.get("batches") or []
        if isinstance(item, dict) and item.get("id")
    }
    sequence = 1
    while f"batch_{sequence:03d}" in used:
        sequence += 1
    return f"batch_{sequence:03d}"


def _update_batch_progress(
    progress: dict,
    *,
    batch_id: str,
    status: str,
    note: str | None = None,
    artifacts: dict[str, str] | None = None,
) -> dict:
    if status not in {"pending", "in_progress", "completed", "failed"}:
        raise ValueError(f"invalid batch status: {status}")
    _ensure_batch_progress_state(progress)
    batch = _batch_by_id(progress, batch_id)
    chunk_ids = [str(chunk_id) for chunk_id in batch.get("chunk_ids") or []]
    if not chunk_ids:
        raise ValueError(f"batch '{batch_id}' has no chunks")

    if status == "in_progress":
        overlapping_active = [
            str(item.get("id"))
            for item in progress["batches"]
            if isinstance(item, dict)
            and item.get("id") != batch_id
            and item.get("status") == "in_progress"
            and set(chunk_ids).intersection(str(owned) for owned in item.get("chunk_ids") or [])
        ]
        if overlapping_active:
            raise ValueError(
                f"cannot start batch '{batch_id}': chunks overlap active batch(es): "
                + ", ".join(overlapping_active)
            )

    now = _now_ms()
    for chunk_id in chunk_ids:
        chunk = _progress_chunk(progress, chunk_id)
        chunk["status"] = status
        chunk["batch_id"] = batch_id
        chunk["updated_at_ms"] = now
    batch["status"] = status
    batch["updated_at_ms"] = now
    if note:
        notes = batch.setdefault("notes", [])
        if isinstance(notes, list):
            notes.append(note)
    if artifacts:
        outputs = batch.setdefault("outputs", {})
        if isinstance(outputs, dict):
            outputs.update(artifacts)

    progress["current_chunk_id"] = None
    _recalculate_progress(progress)
    progress["updated_at_ms"] = now
    return progress


def _prepare_migration_batch(
    index: dict,
    chunks: list[dict],
    progress: dict,
    *,
    max_chunks: int,
    max_action_edges: int,
    max_evidence_chars: int,
) -> tuple[dict | None, bool]:
    """Claim one bounded, topology-safe batch; return (batch, resumed)."""
    _ensure_batch_progress_state(progress)
    active_batches = [
        item for item in progress["batches"]
        if isinstance(item, dict) and item.get("status") == "in_progress"
    ]
    if active_batches:
        return active_batches[0], True

    return _claim_new_migration_batch(
        index,
        chunks,
        progress,
        max_chunks=max_chunks,
        max_action_edges=max_action_edges,
        max_evidence_chars=max_evidence_chars,
    ), False


def _claim_new_migration_batch(
    index: dict,
    chunks: list[dict],
    progress: dict,
    *,
    max_chunks: int,
    max_action_edges: int,
    max_evidence_chars: int,
) -> dict | None:
    """Claim a new disjoint batch while other worker batches may be active."""
    _ensure_batch_progress_state(progress)

    selection = _select_pending_batch(
        index,
        chunks,
        progress,
        max_chunks=max_chunks,
        max_action_edges=max_action_edges,
        max_evidence_chars=max_evidence_chars,
    )
    if not selection["chunks"]:
        return None
    now = _now_ms()
    batch = {
        "id": _next_batch_id(progress),
        "status": "pending",
        "chunk_ids": [str(chunk.get("id")) for chunk in selection["chunks"]],
        "topology_groups": selection["groups"],
        "budgets": {
            "max_chunks": max_chunks,
            "max_action_edges": max_action_edges,
            "max_evidence_chars": max_evidence_chars,
        },
        "estimated": selection["metrics"],
        "budget_exceptions": selection["budget_exceptions"],
        "created_at_ms": now,
        "updated_at_ms": now,
        "outputs": {},
        "notes": [],
    }
    progress["batches"].append(batch)
    _update_batch_progress(progress, batch_id=batch["id"], status="in_progress")
    return batch


def _prepare_migration_batches(
    index: dict,
    chunks: list[dict],
    progress: dict,
    *,
    parallelism: int,
    max_chunks: int,
    max_action_edges: int,
    max_evidence_chars: int,
) -> list[dict]:
    """Resume or claim independent worker batches in one coordinator update."""
    if parallelism < 1:
        raise ValueError("parallelism must be at least 1")
    _ensure_batch_progress_state(progress)
    active = [
        batch
        for batch in progress["batches"]
        if isinstance(batch, dict) and batch.get("status") == "in_progress"
    ]
    if len(active) > parallelism:
        raise ValueError(
            f"progress has {len(active)} active batches; parallelism must be at least that value"
        )

    prepared = [{"batch": batch, "resumed": True} for batch in active]
    while len(prepared) < parallelism:
        batch = _claim_new_migration_batch(
            index,
            chunks,
            progress,
            max_chunks=max_chunks,
            max_action_edges=max_action_edges,
            max_evidence_chars=max_evidence_chars,
        )
        if batch is None:
            break
        prepared.append({"batch": batch, "resumed": False})
    return prepared


def migration_coverage_report(plan: object, index: dict) -> dict:
    """Summarize mapping completeness without imposing node-type choices."""
    plan_dict = plan if isinstance(plan, dict) else {}
    coverage = plan_dict.get("coverage") if isinstance(plan_dict.get("coverage"), dict) else {}
    sections = {
        "agents": (index.get("agents") or [], coverage.get("agents") or [], lambda item: item.get("id") or item.get("old_id") or item.get("old_agent_id")),
        "tools": (index.get("tools") or [], coverage.get("tools") or [], lambda item: item.get("tool_key") or item.get("old_tool_key") or item.get("id") or item.get("old_tool_id")),
        "actions": (index.get("action_edges") or [], coverage.get("actions") or [], lambda item: item.get("action_id")),
        "explicit_edges": (index.get("explicit_edges") or [], coverage.get("explicit_edges") or [], lambda item: item.get("edge_id")),
        "resources": (index.get("resources") or [], coverage.get("resources") or [], lambda item: item.get("resource_id") or _stable_id("resource", item.get("resource_kind"), item.get("id"), item.get("name"))),
    }
    for contract_section in (
        "classifiers", "templates", "interactions", "branches", "prompt_reviews", "prompt_blocks",
    ):
        sections[contract_section] = (
            (index.get("migration_contracts") or {}).get(contract_section) or [],
            coverage.get(contract_section) or [],
            lambda item: item.get("contract_id"),
        )
    result = {"version": "1", "status": "incomplete", "sections": {}, "unresolved": [], "warnings": []}
    for name, (expected, mapped, identifier) in sections.items():
        expected_ids = {str(identifier(item) or "") for item in expected if isinstance(item, dict)}
        mapped_ids = {str(identifier(item) or "") for item in mapped if isinstance(item, dict)}
        missing = sorted(item for item in expected_ids - mapped_ids if item)
        pending = []
        for item in mapped:
            if not isinstance(item, dict):
                continue
            decision = item.get("decision")
            needs_resolution = (
                decision in {None, "pending", "open_question"}
                or decision in MIGRATION_DROP_DECISIONS
            )
            if needs_resolution and not _migration_decision_is_resolved(item):
                pending.append(str(identifier(item) or ""))
        result["sections"][name] = {
            "expected": len(expected_ids - {""}),
            "mapped": len((expected_ids & mapped_ids) - {""}),
            "missing": missing,
            "pending": sorted(item for item in pending if item),
        }
        result["unresolved"].extend({"section": name, "id": item, "reason": "missing"} for item in missing)
        result["unresolved"].extend({"section": name, "id": item, "reason": "pending"} for item in pending if item)
    expected_handoff_groups = _handoff_groups(index)
    handoff_groups = plan_dict.get("handoff_groups") if isinstance(plan_dict.get("handoff_groups"), list) else []
    expected_group_keys = {group["group_key"] for group in expected_handoff_groups}
    mapped_groups = {
        str(item.get("group_key")): item
        for item in handoff_groups
        if isinstance(item, dict) and item.get("group_key")
    }
    missing_groups = sorted(expected_group_keys - set(mapped_groups))
    targets = {
        str(item.get("target_node_key"))
        for item in handoff_groups
        if isinstance(item, dict) and str(item.get("target_node_key") or "").strip()
    }
    if len(expected_group_keys) > 1 and targets == {"$transfer"}:
        result["warnings"].append({
            "type": "shared_transfer_collapse",
            "message": "Multiple handoff responsibilities collapse into one $transfer target.",
            "group_count": len(expected_group_keys),
        })
    result["sections"]["handoff_groups"] = {
        "expected": len(expected_group_keys),
        "mapped": len(expected_group_keys & set(mapped_groups)),
        "missing": missing_groups,
        "pending": sorted(
            group_key for group_key, item in mapped_groups.items()
            if item.get("decision") in {None, "pending", "open_question"}
            and item.get("resolved") is not True
        ),
    }
    result["unresolved"].extend({"section": "handoff_groups", "id": item, "reason": "missing"} for item in missing_groups)
    terminal_groups = {
        group["group_key"]: group
        for group in _terminal_action_groups(index)
    }
    action_targets = {}
    for item in coverage.get("actions") or []:
        if not isinstance(item, dict):
            continue
        action_id = item.get("action_id")
        if not action_id:
            continue
        group = next((g for g in terminal_groups.values() if g.get("action_id") == action_id), None)
        if not group:
            continue
        mapped_to = item.get("mapped_to")
        targets_for_item = mapped_to if isinstance(mapped_to, list) else [mapped_to]
        for target in targets_for_item:
            target_text = str(target or "").strip()
            if not target_text:
                continue
            action_targets.setdefault(target_text, []).append(group)
    for target, groups in sorted(action_targets.items()):
        unique_groups = {
            group["group_key"]: group
            for group in groups
        }
        if len(unique_groups) <= 1:
            continue
        action_types = sorted({
            str(group.get("terminal_contract", {}).get("action_type"))
            for group in unique_groups.values()
        })
        reply_contracts = {
            (
                group.get("terminal_contract", {}).get("reply_type"),
                group.get("terminal_contract", {}).get("template_id"),
                group.get("terminal_contract", {}).get("template_content"),
            )
            for group in unique_groups.values()
        }
        # Bare no-reply FINISH actions are allowed to share $finish.
        if target == "$finish" and action_types == ["FINISH_AGENT"] and reply_contracts == {("NO_REPLY", None, "")}:
            continue
        result["warnings"].append({
            "type": "shared_terminal_action_collapse",
            "message": "Multiple legacy terminal/reply action contracts map to the same target node.",
            "target": target,
            "group_count": len(unique_groups),
            "action_types": action_types,
            "groups": [
                {
                    "group_key": group.get("group_key"),
                    "action_id": group.get("action_id"),
                    "source_agent_name": group.get("source_agent_name"),
                    "branch_label": group.get("branch_label"),
                    "terminal_contract": group.get("terminal_contract"),
                    "reuse_policy": group.get("reuse_policy"),
                }
                for group in unique_groups.values()
            ],
        })
    approved_merge_targets = {
        str(item.get("target") or item.get("target_node_key") or "").strip()
        for item in (plan_dict.get("merge_groups") if isinstance(plan_dict.get("merge_groups"), list) else [])
        if isinstance(item, dict) and str(item.get("target") or item.get("target_node_key") or "").strip()
    }
    terminal_action_ids = {
        str(group.get("action_id"))
        for group in _terminal_action_groups(index)
        if group.get("action_id")
    }
    shared_targets = {}
    for section_name, id_field in (
        ("agents", "old_id"),
        ("actions", "action_id"),
        ("explicit_edges", "edge_id"),
    ):
        for item in coverage.get(section_name) or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get(id_field) or item.get("old_agent_id") or item.get("id") or "").strip()
            if section_name == "actions" and item_id in terminal_action_ids:
                continue
            mapped_to = item.get("mapped_to")
            targets_for_item = mapped_to if isinstance(mapped_to, list) else [mapped_to]
            for target in targets_for_item:
                target_text = str(target or "").strip()
                if not target_text or target_text in {"$finish", "$transfer"}:
                    continue
                shared_targets.setdefault(target_text, []).append({
                    "section": section_name,
                    "id": item_id,
                    "decision": item.get("decision"),
                    "reason": item.get("reason"),
                    "evidence": item.get("evidence") or [],
                })
    for target, sources in sorted(shared_targets.items()):
        unique_sources = {
            (source["section"], source["id"]): source
            for source in sources
            if source.get("id")
        }
        if len(unique_sources) <= 1 or target in approved_merge_targets:
            continue
        result["warnings"].append({
            "type": "shared_flow_target_without_merge_contract",
            "message": "Multiple legacy flow units map to the same target without a merge_groups contract.",
            "target": target,
            "source_count": len(unique_sources),
            "sources": list(unique_sources.values()),
            "required_action": "Split the target by chunk/branch, or add a merge_groups entry proving same inputs, user turn, resource contract, branch set, and downstream semantics.",
        })
    result["status"] = "complete" if not result["unresolved"] else "incomplete"
    result["blocking"] = bool(result["unresolved"])
    return result


def _canonical_migration_source_type(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    collapsed = normalized.replace("_", "")
    return MIGRATION_SOURCE_TYPE_ALIASES.get(
        normalized,
        MIGRATION_SOURCE_TYPE_ALIASES.get(collapsed, normalized.upper()),
    )


def _migration_mapping_targets(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item or "").strip()]


def _migration_source_fingerprint(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_migration_source(plan: object, index: object, source: object) -> dict:
    """Audit plan-to-source drift without making semantic suggestions blocking."""
    errors: list[dict] = []
    warnings: list[dict] = []
    report = {
        "schema_version": 1,
        "status": "failed",
        "blocking": True,
        "policy": {
            "structural_errors_block": True,
            "semantic_warnings_block": False,
        },
        "summary": {
            "nodes": 0,
            "edges": 0,
            "errors": 0,
            "warnings": 0,
        },
        "fingerprints": {
            "plan_sha256": _migration_source_fingerprint(plan),
            "index_sha256": _migration_source_fingerprint(index),
            "source_sha256": _migration_source_fingerprint(source),
        },
        "errors": errors,
        "warnings": warnings,
    }

    if not isinstance(plan, dict):
        errors.append({
            "code": "invalid_plan_document",
            "message": "migration plan must be a JSON object",
        })
    if not isinstance(index, dict):
        errors.append({
            "code": "invalid_index_document",
            "message": "migration index must be a JSON object",
        })
    if not isinstance(source, dict):
        errors.append({
            "code": "invalid_source_document",
            "message": "CHAT_FLOW source must be a JSON object",
        })
    if errors:
        report["summary"]["errors"] = len(errors)
        return report

    nodes = source.get("nodes")
    edges = source.get("edges", [])
    if not isinstance(nodes, list):
        errors.append({
            "code": "invalid_source_nodes",
            "message": "CHAT_FLOW source nodes must be an array",
        })
        nodes = []
    if not isinstance(edges, list):
        errors.append({
            "code": "invalid_source_edges",
            "message": "CHAT_FLOW source edges must be an array",
        })
        edges = []

    node_by_key: dict[str, dict] = {}
    node_types: dict[str, str] = {}
    for position, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append({
                "code": "invalid_source_node",
                "message": f"source nodes[{position}] must be an object",
                "node_index": position,
            })
            continue
        node_key = str(
            node.get("key") or node.get("name") or node.get("title") or f"node_{position}"
        )
        if node_key in node_by_key:
            errors.append({
                "code": "duplicate_source_node_key",
                "message": f"source node key is duplicated: {node_key}",
                "node_key": node_key,
            })
            continue
        node_by_key[node_key] = node
        node_types[node_key] = _canonical_migration_source_type(
            node.get("type") or node.get("category")
        )
        if not node_types[node_key]:
            errors.append({
                "code": "source_node_type_missing",
                "message": f"source node '{node_key}' has no type/category",
                "node_key": node_key,
            })

    terminal_keys = {"$finish", "$transfer"}
    adjacency: dict[str, set[str]] = {}
    valid_edges = []
    for position, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append({
                "code": "invalid_source_edge",
                "message": f"source edges[{position}] must be an object",
                "edge_index": position,
            })
            continue
        source_key = str(edge.get("from") or edge.get("source") or "").strip()
        target_key = str(edge.get("to") or edge.get("target") or "").strip()
        if source_key not in node_by_key:
            errors.append({
                "code": "source_edge_origin_missing",
                "message": f"source edge origin does not exist: {source_key or '<empty>'}",
                "edge_index": position,
            })
            continue
        if target_key not in node_by_key and target_key not in terminal_keys:
            errors.append({
                "code": "source_edge_target_missing",
                "message": f"source edge target does not exist: {target_key or '<empty>'}",
                "edge_index": position,
            })
            continue
        adjacency.setdefault(source_key, set()).add(target_key)
        valid_edges.append(edge)

    entry = str(source.get("entry") or "").strip()
    if entry and entry not in node_by_key:
        errors.append({
            "code": "source_entry_missing",
            "message": f"source entry node does not exist: {entry}",
            "entry": entry,
        })

    coverage = plan.get("coverage") if isinstance(plan.get("coverage"), dict) else {}
    sop_mapping = plan.get("sop_mapping") if isinstance(plan.get("sop_mapping"), dict) else {}
    blocks = [
        block for block in (sop_mapping.get("blocks") or [])
        if isinstance(block, dict)
    ]
    blocks_by_id = {
        str(block.get("id")): block
        for block in blocks
        if str(block.get("id") or "").strip()
    }
    rendered_targets_by_block: dict[str, list[str]] = {}
    ambiguous_render_mappings = []
    for section, records in coverage.items():
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            rendered_to = _migration_mapping_targets(record.get("rendered_to"))
            if not rendered_to:
                continue
            mapped_to = _migration_mapping_targets(record.get("mapped_to"))
            if len(mapped_to) > 1 and len(rendered_to) > 1:
                ambiguous_render_mappings.append(
                    (section, record, mapped_to, rendered_to)
                )
                continue
            for mapping_target in mapped_to:
                rendered_targets_by_block.setdefault(mapping_target, [])
                for target in rendered_to:
                    if target not in rendered_targets_by_block[mapping_target]:
                        rendered_targets_by_block[mapping_target].append(target)

    for section, record, mapped_to, rendered_to in ambiguous_render_mappings:
        unresolved_blocks = []
        for block_id in mapped_to:
            block = blocks_by_id.get(block_id)
            if block is None:
                continue
            explicit_targets = _migration_mapping_targets(
                block.get("source_nodes") or block.get("rendered_to")
            )
            if not explicit_targets:
                unresolved_blocks.append(block_id)
        if unresolved_blocks:
            warnings.append({
                "code": "coverage_mapping_requires_explicit_source_nodes",
                "message": (
                    f"Coverage section '{section}' maps multiple SOP blocks to multiple source "
                    "nodes; add source_nodes to each affected SOP block instead of inferring a "
                    "many-to-many association."
                ),
                "section": section,
                "coverage_id": _coverage_record_id(section, record),
                "mapped_to": mapped_to,
                "rendered_to": rendered_to,
                "blocks_requiring_source_nodes": unresolved_blocks,
            })

    source_nodes_by_block: dict[str, list[str]] = {}
    for block_id, block in blocks_by_id.items():
        explicit_targets = _migration_mapping_targets(
            block.get("source_nodes") or block.get("rendered_to")
        )
        declared_targets = explicit_targets or rendered_targets_by_block.get(block_id, [])
        block_targets = declared_targets
        if not block_targets and block_id in node_by_key:
            block_targets = [block_id]
        source_nodes_by_block[block_id] = block_targets
        selected_types = {
            _canonical_migration_source_type(item)
            for item in (block.get("selected_nodes") or [])
            if str(item or "").strip()
        }
        if not block_targets:
            warnings.append({
                "code": "sop_block_not_traceable_to_source",
                "message": (
                    f"SOP block '{block_id}' cannot be traced to a source node; "
                    "keep the same key or record source_nodes/rendered_to."
                ),
                "block_id": block_id,
            })
        for target in block_targets:
            if target not in node_by_key:
                finding = {
                    "code": (
                        "sop_declared_source_node_missing"
                        if declared_targets
                        else "sop_source_node_missing"
                    ),
                    "message": f"SOP block '{block_id}' points to missing source node '{target}'.",
                    "block_id": block_id,
                    "node_key": target,
                }
                if declared_targets:
                    errors.append(finding)
                else:
                    warnings.append(finding)
                continue
            actual_type = node_types.get(target, "")
            if selected_types and actual_type not in selected_types:
                warnings.append({
                    "code": "node_type_differs_from_confirmed_mapping",
                    "message": (
                        f"Source node '{target}' is {actual_type or '<missing>'}, while SOP block "
                        f"'{block_id}' selected {sorted(selected_types)}."
                    ),
                    "block_id": block_id,
                    "node_key": target,
                    "actual_type": actual_type,
                    "selected_types": sorted(selected_types),
                })
        if "AGENT" in selected_types and not str(
            block.get("selection_reason") or block.get("reason") or ""
        ).strip():
            warnings.append({
                "code": "agent_selection_reason_missing",
                "message": (
                    f"SOP block '{block_id}' selects AGENT but does not explain why INTENT, "
                    "QUESTION, REPLY, TOOL, IF_ELSE, or LLM cannot express the responsibility."
                ),
                "block_id": block_id,
            })

    coverage_report = migration_coverage_report(plan, index)
    for section, section_report in coverage_report.get("sections", {}).items():
        missing = section_report.get("missing") or []
        pending = section_report.get("pending") or []
        if missing or pending:
            warnings.append({
                "code": "migration_coverage_unresolved",
                "message": f"Migration coverage for '{section}' is not complete.",
                "section": section,
                "missing": missing,
                "pending": pending,
            })
    for finding in coverage_report.get("warnings", []):
        warning = deepcopy(finding)
        warning["code"] = str(warning.pop("type", "migration_coverage_warning"))
        warnings.append(warning)

    for section, records in coverage.items():
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            if (
                _migration_decision_is_drop(record)
                and _migration_decision_is_resolved(record)
            ):
                continue
            rendered_targets = _migration_mapping_targets(record.get("rendered_to"))
            effective_targets = rendered_targets or _migration_mapping_targets(
                record.get("mapped_to")
            )
            for target in effective_targets:
                if target in terminal_keys or (not rendered_targets and target in blocks_by_id):
                    continue
                target_root = target.split(".", 1)[0]
                if target not in node_by_key and target_root not in node_by_key:
                    finding = {
                        "code": (
                            "coverage_rendered_target_missing"
                            if rendered_targets
                            else "coverage_target_not_in_source"
                        ),
                        "message": (
                            f"Coverage section '{section}' maps to '{target}', but no matching "
                            "source node is present."
                        ),
                        "section": section,
                        "target": target,
                    }
                    if rendered_targets:
                        errors.append(finding)
                    else:
                        warnings.append(finding)

    def target_is_reachable(origins: list[str], destinations: list[str]) -> bool:
        wanted = set(destinations)
        queue = deque(origins)
        visited = set(origins)
        while queue:
            current = queue.popleft()
            if current in wanted:
                return True
            for next_key in adjacency.get(current, set()):
                if next_key not in visited and next_key in node_by_key:
                    visited.add(next_key)
                    queue.append(next_key)
        return False

    for relation in sop_mapping.get("relations") or []:
        if not isinstance(relation, dict):
            continue
        from_block = str(relation.get("from") or "").strip()
        to_block = str(relation.get("to") or "").strip()
        origins = source_nodes_by_block.get(from_block, [])
        destinations = source_nodes_by_block.get(to_block, [])
        if origins and destinations and not target_is_reachable(origins, destinations):
            warnings.append({
                "code": "sop_relation_not_reachable_in_source",
                "message": (
                    f"No source path was found from SOP block '{from_block}' to '{to_block}'."
                ),
                "from": from_block,
                "to": to_block,
                "condition": relation.get("condition"),
            })

    for node_key, node in node_by_key.items():
        if node_types.get(node_key) != "AGENT":
            continue
        matching_blocks = [
            block_id for block_id, source_nodes in source_nodes_by_block.items()
            if node_key in source_nodes
        ]
        if not matching_blocks:
            warnings.append({
                "code": "agent_not_supported_by_sop_mapping",
                "message": (
                    f"Source AGENT '{node_key}' is not traceable to a confirmed SOP block."
                ),
                "node_key": node_key,
            })
        next_steps = node.get("next_steps")
        if next_steps is None:
            next_steps = node.get("nextStep")
        if not isinstance(next_steps, list):
            next_steps = []
        step_ids = set()
        generic_steps = []
        for step in next_steps:
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("id") or "").strip()
            step_title = str(step.get("title") or step.get("name") or step_id).strip()
            if step_id:
                step_ids.add(step_id)
            normalized_names = {
                re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
                for value in (step_id, step_title)
                if value
            }
            if normalized_names.intersection(GENERIC_AGENT_NEXT_STEP_NAMES):
                generic_steps.append(step_id or step_title)
        if generic_steps:
            warnings.append({
                "code": "generic_agent_next_step",
                "message": (
                    f"AGENT '{node_key}' uses generic next step names; next_steps must name "
                    "a concrete downstream responsibility."
                ),
                "node_key": node_key,
                "next_steps": generic_steps,
            })
        routed_edges = [
            edge for edge in valid_edges
            if str(edge.get("from") or edge.get("source") or "") == node_key
            and str(edge.get("on") or edge.get("sourceHandle") or "") in step_ids
        ]
        if len(next_steps) == 1 and routed_edges:
            warnings.append({
                "code": "single_agent_next_step_review",
                "message": (
                    f"AGENT '{node_key}' has one next step. Confirm that the model truly decides "
                    "whether and when to hand off; fixed order should use a SOURCE edge."
                ),
                "node_key": node_key,
            })
        for edge in routed_edges:
            target = str(edge.get("to") or edge.get("target") or "")
            if target == "$transfer" or node_types.get(target) == "TRANSFER_TO_HUMAN":
                warnings.append({
                    "code": "agent_next_step_used_for_human_transfer",
                    "message": (
                        f"AGENT '{node_key}' routes next_steps to human transfer. Use the real "
                        "transfer action inside AGENT, or a deterministic transfer node."
                    ),
                    "node_key": node_key,
                    "target": target,
                })

    report["summary"].update({
        "nodes": len(node_by_key),
        "edges": len(valid_edges),
        "errors": len(errors),
        "warnings": len(warnings),
    })
    report["blocking"] = bool(errors)
    report["status"] = "failed" if errors else ("review" if warnings else "passed")
    return report


def _cmd_inspect(args: argparse.Namespace) -> int:
    raw = _read_json(args.input)
    full = analyze(raw, prompt_max_chars=args.prompt_max_chars, prompt_terms=args.prompt_term or [])
    source = full["source"]
    out_base = Path(args.out_dir)
    migrate_dir = out_base / f"migrate_{_safe_name(source['id'], 'unknown')}_{_safe_name(source['name'], 'multi_agent')}"
    chunks_dir = migrate_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    ai = _ai_index(full)
    _write_json(migrate_dir / "index.full.json", full)
    _write_json(migrate_dir / "index.ai.json", ai)
    _write_json(migrate_dir / "chunks.json", {"chunks": full["chunks"]})
    _write_json(migrate_dir / "flow_understanding.seed.json", _flow_understanding_seed(full))
    _write_json(migrate_dir / "migration_plan.template.json", _migration_plan_template(full))
    _write_json(migrate_dir / "coverage.template.json", _migration_plan_template(full)["coverage"])
    _write_json(migrate_dir / "progress.json", _migration_progress_template(full, migrate_dir))
    (migrate_dir / "overview.mmd").write_text(_mermaid(full), encoding="utf-8")

    result = {
        "source": source,
        "entry_agent_id": full["graph"]["entry_agent_id"],
        "agents": full["graph"]["agents_count"],
        "tools": full["graph"]["tools_count"],
        "explicit_edges": full["graph"]["explicit_edges_count"],
        "action_edges": full["graph"]["action_edges_count"],
        "prompt_reviews": full["graph"]["prompt_reviews_count"],
        "chunks": len(full["chunks"]),
        "risk_items": len(full["risk_items"]),
        "artifacts": {
            "dir": str(migrate_dir),
            "index_full": str(migrate_dir / "index.full.json"),
            "index_ai": str(migrate_dir / "index.ai.json"),
            "overview": str(migrate_dir / "overview.mmd"),
            "chunks": str(migrate_dir / "chunks.json"),
            "flow_understanding_seed": str(migrate_dir / "flow_understanding.seed.json"),
            "migration_plan_template": str(migrate_dir / "migration_plan.template.json"),
            "coverage_template": str(migrate_dir / "coverage.template.json"),
            "progress": str(migrate_dir / "progress.json"),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _cmd_emit_chunk_context(args: argparse.Namespace) -> int:
    index = _read_json(args.index_file)
    chunks_doc = _read_json(args.chunks_file)
    chunks = chunks_doc.get("chunks") if isinstance(chunks_doc, dict) else chunks_doc
    chunk = next((item for item in chunks if item.get("id") == args.chunk_id), None)
    if not chunk:
        raise ValueError(f"chunk not found: {args.chunk_id}")
    agent_ids = set(chunk.get("agent_ids") or [])
    agents = [agent for agent in index.get("agents") or [] if agent.get("id") in agent_ids]
    context = {
        "chunk": chunk,
        "source": index.get("source"),
        "graph": index.get("graph"),
        "agents": agents,
        "tools": [tool for tool in index.get("tools") or [] if tool.get("agent_id") in agent_ids],
        "explicit_edges": [
            edge for edge in index.get("explicit_edges") or []
            if edge.get("from") in agent_ids or edge.get("to") in agent_ids
        ],
        "action_edges": [
            edge for edge in index.get("action_edges") or []
            if edge.get("from_agent") in agent_ids
        ],
        "handoff_groups": [
            group for group in _handoff_groups(index)
            if set(group.get("source_agent_ids") or []) & agent_ids
        ],
        "risk_items": [
            item for item in index.get("risk_items") or []
            if item.get("agent_id") in agent_ids or (item.get("edge") or {}).get("from_agent") in agent_ids
        ],
        "coverage_required": {
            "agents": [{"old_id": agent.get("id"), "old_name": agent.get("name")} for agent in agents],
            "tools": [
                {"old_tool_id": tool.get("id"), "old_tool_key": tool.get("tool_key"), "old_tool_name": tool.get("name")}
                for tool in index.get("tools") or []
                if tool.get("agent_id") in agent_ids
            ],
            "actions": [
                {
                    "action_id": edge.get("action_id"),
                    "from_old_agent": edge.get("from_agent"),
                    "match_status": edge.get("match_status"),
                    "action_type": (edge.get("action") or {}).get("type"),
                }
                for edge in index.get("action_edges") or []
                if edge.get("from_agent") in agent_ids
            ],
            "explicit_edges": [
                {"edge_id": edge.get("edge_id"), "from_old_agent": edge.get("from"), "to_old_agent": edge.get("to")}
                for edge in index.get("explicit_edges") or []
                if edge.get("from") in agent_ids
            ],
        },
    }
    _write_json(Path(args.out_file), context)
    print(json.dumps({"chunk_id": args.chunk_id, "out_file": args.out_file}, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _read_chunks_document(path: str) -> list[dict]:
    document = _read_json(path)
    chunks = document.get("chunks") if isinstance(document, dict) else document
    if not isinstance(chunks, list):
        raise ValueError("chunks file must contain a chunks array")
    return [item for item in chunks if isinstance(item, dict)]


def _parse_artifacts(items: list[str]) -> dict[str, str]:
    artifacts = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"--artifact must use key=path format: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError(f"--artifact must use non-empty key=path format: {item}")
        artifacts[key] = value
    return artifacts


def _append_unique(target: list, values: object) -> None:
    items = values if isinstance(values, list) else [values]
    known = {json.dumps(item, ensure_ascii=False, sort_keys=True) for item in target}
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in known:
            target.append(deepcopy(item))
            known.add(key)


def _merge_mapping_record(
    target: dict,
    incoming: dict,
    *,
    label: str,
    source_batch_id: str,
) -> None:
    mergeable_target_fields = {
        "mapped_to",
        "rendered_to",
        "source_nodes",
        "candidate_nodes",
        "selected_nodes",
        "merged_from",
        "split_into",
    }
    for key, raw_value in incoming.items():
        if key in {"source_batch_ids", "evidence", "reason_by_batch"}:
            continue
        value = deepcopy(raw_value)
        if key in mergeable_target_fields and value not in (None, ""):
            value = value if isinstance(value, list) else [value]
        current = target.get(key)
        if current in (None, "", [], "pending"):
            target[key] = value
        elif value in (None, "", [], "pending") or current == value:
            continue
        elif key in mergeable_target_fields:
            if not isinstance(current, list):
                raise ValueError(f"{label} field '{key}' must be a list")
            _append_unique(current, value)
        elif key == "reason" and isinstance(current, str) and isinstance(value, str):
            # Shared resources and cross-batch edges can have distinct local
            # evidence. Keep the first concise reason for compatibility and
            # retain every worker's explanation below for auditability.
            continue
        else:
            raise ValueError(
                f"conflicting {label} field '{key}' from batch '{source_batch_id}'"
            )
    incoming_reason = str(incoming.get("reason") or "").strip()
    if incoming_reason:
        reason_by_batch = target.setdefault("reason_by_batch", {})
        if not isinstance(reason_by_batch, dict):
            raise ValueError(f"{label} reason_by_batch must be an object")
        existing_reason = reason_by_batch.get(source_batch_id)
        if existing_reason not in (None, incoming_reason):
            raise ValueError(
                f"conflicting {label} reason from batch '{source_batch_id}'"
            )
        reason_by_batch[source_batch_id] = incoming_reason
    evidence = target.setdefault("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError(f"{label} evidence must be a list")
    _append_unique(evidence, incoming.get("evidence") or [])
    source_batches = target.setdefault("source_batch_ids", [])
    if not isinstance(source_batches, list):
        raise ValueError(f"{label} source_batch_ids must be a list")
    _append_unique(source_batches, [source_batch_id])


def _coverage_record_id(section: str, item: dict) -> str:
    keys = {
        "agents": ("old_id", "old_agent_id", "id"),
        "tools": ("old_tool_key", "tool_key", "old_tool_id", "tool_id", "id"),
        "actions": ("action_id",),
        "explicit_edges": ("edge_id",),
        "resources": ("resource_id", "id"),
        "classifiers": ("contract_id",),
        "templates": ("contract_id",),
        "interactions": ("contract_id",),
        "branches": ("contract_id",),
        "prompt_reviews": ("contract_id",),
        "prompt_blocks": ("contract_id",),
    }
    for key in keys.get(section, ()):
        if item.get(key) not in (None, ""):
            return str(item[key])
    return ""


def _validate_batch_fragment_coverage(
    fragment: dict,
    context: dict,
    *,
    batch_id: str,
) -> None:
    """Require every batch-local contract before global mappings are merged."""
    required = context.get("coverage_required")
    if not isinstance(required, dict):
        raise ValueError(f"batch '{batch_id}' context has no coverage_required object")
    coverage_delta = fragment.get("coverage_delta")
    if not isinstance(coverage_delta, dict):
        raise ValueError(f"batch '{batch_id}' plan missing coverage_delta")

    for section, required_records in required.items():
        if not isinstance(required_records, list):
            raise ValueError(
                f"batch '{batch_id}' coverage_required.{section} must be an array"
            )
        expected_ids = {
            _coverage_record_id(section, item)
            for item in required_records
            if isinstance(item, dict) and _coverage_record_id(section, item)
        }
        if not expected_ids:
            continue
        delta_records = coverage_delta.get(section)
        if not isinstance(delta_records, list):
            raise ValueError(
                f"batch '{batch_id}' coverage_delta missing required section '{section}'"
            )
        stable_id_field = COVERAGE_STABLE_ID_FIELDS.get(section)
        if stable_id_field:
            for item in delta_records:
                if (
                    isinstance(item, dict)
                    and item.get(stable_id_field) in (None, "")
                ):
                    raise ValueError(
                        f"batch '{batch_id}' coverage_delta.{section} entry must copy "
                        f"stable field '{stable_id_field}' from coverage_required"
                    )
        actual_ids = {
            _coverage_record_id(section, item)
            for item in delta_records
            if isinstance(item, dict) and _coverage_record_id(section, item)
        }
        missing_ids = sorted(expected_ids - actual_ids)
        if missing_ids:
            raise ValueError(
                f"batch '{batch_id}' coverage_delta.{section} is missing required ids: "
                f"{missing_ids}"
            )
        actual_by_id = {
            _coverage_record_id(section, item): item
            for item in delta_records
            if isinstance(item, dict) and _coverage_record_id(section, item)
        }
        has_blocking_question = any(
            isinstance(question, dict)
            and question.get("blocking", True) is True
            and not (
                question.get("resolved") is True
                and str(question.get("resolution") or "").strip()
            )
            for question in fragment.get("open_questions") or []
        )
        for record_id in sorted(expected_ids):
            item = actual_by_id[record_id]
            decision = item.get("decision")
            if decision in (None, "", "pending"):
                raise ValueError(
                    f"batch '{batch_id}' coverage_delta.{section} id '{record_id}' "
                    "has no decision"
                )
            if not str(item.get("reason") or "").strip():
                raise ValueError(
                    f"batch '{batch_id}' coverage_delta.{section} id '{record_id}' "
                    "has no reason"
                )
            if decision == "open_question":
                if not has_blocking_question:
                    raise ValueError(
                        f"batch '{batch_id}' coverage_delta.{section} id '{record_id}' "
                        "is open_question but the fragment has no unresolved blocking question"
                    )
                continue
            if _migration_decision_is_drop(item):
                if not _migration_decision_is_resolved(item):
                    raise ValueError(
                        f"batch '{batch_id}' coverage_delta.{section} id '{record_id}' "
                        "drops source semantics without a resolved user decision"
                    )
                continue
            if not item.get("mapped_to"):
                raise ValueError(
                    f"batch '{batch_id}' coverage_delta.{section} id '{record_id}' "
                    "has no mapped_to target"
                )


def _question_key(question: object) -> str:
    if isinstance(question, dict):
        for key in ("id", "question_id", "question", "problem", "title", "description"):
            if str(question.get(key) or "").strip():
                return re.sub(r"\s+", " ", str(question[key]).strip().lower())
    return re.sub(
        r"\s+",
        " ",
        json.dumps(question, ensure_ascii=False, sort_keys=True).strip().lower(),
    )


def _merge_batch_plan_fragments(base_plan: dict, fragments: list[tuple[str, dict]]) -> dict:
    """Merge isolated worker output and consolidate questions deterministically."""
    plan = deepcopy(base_plan)
    if not isinstance(plan.get("coverage"), dict):
        raise ValueError("base migration plan must contain coverage")
    if not isinstance(plan.get("sop_mapping"), dict):
        raise ValueError("base migration plan must contain sop_mapping")

    coverage_indexes = {}
    for section, records in plan["coverage"].items():
        if not isinstance(records, list):
            continue
        coverage_indexes[section] = {
            _coverage_record_id(section, record): record
            for record in records
            if isinstance(record, dict) and _coverage_record_id(section, record)
        }

    blocks = plan["sop_mapping"].setdefault("blocks", [])
    relations = plan["sop_mapping"].setdefault("relations", [])
    if not isinstance(blocks, list) or not isinstance(relations, list):
        raise ValueError("base migration plan sop_mapping blocks/relations must be arrays")
    block_index = {
        str(block.get("id")): block
        for block in blocks
        if isinstance(block, dict) and block.get("id")
    }
    relation_index = {
        json.dumps(
            {
                key: value
                for key, value in relation.items()
                if key != "source_batch_ids"
            },
            ensure_ascii=False,
            sort_keys=True,
        ): relation
        for relation in relations
        if isinstance(relation, dict)
    }
    node_decisions = plan.setdefault("node_decision", [])
    node_index = {
        str(item.get("old_id")): item
        for item in node_decisions
        if isinstance(item, dict) and item.get("old_id")
    }
    question_index = {}
    consolidated_questions = []
    resolved_questions = plan.setdefault("resolved_questions", [])
    audit_warnings = plan.setdefault("audit_warnings", [])
    batch_results = []

    for batch_id, fragment in fragments:
        if not isinstance(fragment, dict):
            raise ValueError(f"batch '{batch_id}' plan must be a JSON object")
        fragment_batch_id = str(fragment.get("batch_id") or fragment.get("batch") or "")
        if fragment_batch_id != batch_id:
            raise ValueError(
                f"batch plan id mismatch: manifest has '{batch_id}', plan has '{fragment_batch_id}'"
            )
        mapping = fragment.get("sop_mapping")
        coverage_delta = fragment.get("coverage_delta")
        if not isinstance(mapping, dict):
            raise ValueError(f"batch '{batch_id}' plan missing sop_mapping")
        if not isinstance(coverage_delta, dict):
            raise ValueError(f"batch '{batch_id}' plan missing coverage_delta")

        for block in mapping.get("blocks") or []:
            if not isinstance(block, dict) or not str(block.get("id") or "").strip():
                raise ValueError(f"batch '{batch_id}' has SOP block without id")
            block_id = str(block["id"])
            if block_id in block_index:
                _merge_mapping_record(
                    block_index[block_id],
                    block,
                    label=f"SOP block {block_id}",
                    source_batch_id=batch_id,
                )
            else:
                merged = deepcopy(block)
                merged["source_batch_ids"] = [batch_id]
                block_reason = str(merged.get("reason") or "").strip()
                if block_reason:
                    merged["reason_by_batch"] = {batch_id: block_reason}
                blocks.append(merged)
                block_index[block_id] = merged
        for relation in mapping.get("relations") or []:
            if not isinstance(relation, dict):
                raise ValueError(f"batch '{batch_id}' SOP relations must contain objects")
            relation_payload = {
                key: value
                for key, value in relation.items()
                if key != "source_batch_ids"
            }
            relation_key = json.dumps(
                relation_payload,
                ensure_ascii=False,
                sort_keys=True,
            )
            existing_relation = relation_index.get(relation_key)
            if existing_relation is None:
                merged_relation = {
                    **deepcopy(relation_payload),
                    "source_batch_ids": [batch_id],
                }
                relations.append(merged_relation)
                relation_index[relation_key] = merged_relation
            else:
                source_batch_ids = existing_relation.setdefault(
                    "source_batch_ids", []
                )
                if not isinstance(source_batch_ids, list):
                    raise ValueError(
                        f"SOP relation {relation_payload!r} source_batch_ids must be a list"
                    )
                _append_unique(source_batch_ids, [batch_id])

        for section, delta_records in coverage_delta.items():
            if section not in coverage_indexes:
                raise ValueError(f"batch '{batch_id}' has unsupported coverage section '{section}'")
            if not isinstance(delta_records, list):
                raise ValueError(f"batch '{batch_id}' coverage_delta.{section} must be an array")
            seen_ids = set()
            for delta in delta_records:
                if not isinstance(delta, dict):
                    raise ValueError(f"batch '{batch_id}' coverage_delta.{section} entries must be objects")
                stable_id_field = COVERAGE_STABLE_ID_FIELDS.get(section)
                if stable_id_field and delta.get(stable_id_field) in (None, ""):
                    raise ValueError(
                        f"batch '{batch_id}' coverage_delta.{section} entry must copy "
                        f"stable field '{stable_id_field}' from coverage_required"
                    )
                if section == "prompt_reviews":
                    delta = deepcopy(delta)
                    discovered = delta.get("discovered_blocks") or []
                    if not isinstance(discovered, list):
                        raise ValueError(
                            f"batch '{batch_id}' prompt review discovered_blocks must be an array"
                        )
                    enriched_blocks = []
                    block_ids = set()
                    for block in discovered:
                        if not isinstance(block, dict):
                            raise ValueError(
                                f"batch '{batch_id}' prompt review blocks must be objects"
                            )
                        block_id = str(block.get("block_id") or "").strip()
                        if not block_id:
                            raise ValueError(
                                f"batch '{batch_id}' discovered prompt block has no block_id"
                            )
                        if block_id in block_ids:
                            raise ValueError(
                                f"batch '{batch_id}' duplicates discovered prompt block '{block_id}'"
                            )
                        block_ids.add(block_id)
                        enriched_blocks.append(_enrich_discovered_prompt_block(block))
                    delta["discovered_blocks"] = enriched_blocks
                record_id = _coverage_record_id(section, delta)
                if not record_id:
                    raise ValueError(f"batch '{batch_id}' coverage_delta.{section} entry has no stable id")
                if record_id in seen_ids:
                    raise ValueError(
                        f"batch '{batch_id}' duplicates coverage_delta.{section} id '{record_id}'"
                    )
                seen_ids.add(record_id)
                target = coverage_indexes[section].get(record_id)
                if target is None:
                    raise ValueError(
                        f"batch '{batch_id}' references unknown coverage_delta.{section} id '{record_id}'"
                    )
                _merge_mapping_record(
                    target,
                    delta,
                    label=f"coverage {section} {record_id}",
                    source_batch_id=batch_id,
                )

        for delta in fragment.get("node_decision_delta") or []:
            if not isinstance(delta, dict) or not delta.get("old_id"):
                raise ValueError(f"batch '{batch_id}' node_decision_delta entry has no old_id")
            old_id = str(delta["old_id"])
            target = node_index.get(old_id)
            if target is None:
                raise ValueError(f"batch '{batch_id}' references unknown node decision '{old_id}'")
            _merge_mapping_record(
                target,
                delta,
                label=f"node decision {old_id}",
                source_batch_id=batch_id,
            )

        skeleton_delta = fragment.get("flow_skeleton_delta") or {}
        if skeleton_delta:
            if not isinstance(skeleton_delta, dict):
                raise ValueError(f"batch '{batch_id}' flow_skeleton_delta must be an object")
            skeleton = plan.setdefault("flow_skeleton", {})
            for key, value in skeleton_delta.items():
                if not isinstance(value, list):
                    raise ValueError(
                        f"batch '{batch_id}' flow_skeleton_delta.{key} must be an array"
                    )
                target = skeleton.setdefault(key, [])
                if not isinstance(target, list):
                    raise ValueError(f"base flow_skeleton.{key} must be an array")
                _append_unique(target, value)

        _append_unique(plan.setdefault("merge_groups", []), fragment.get("merge_groups") or [])
        for question in fragment.get("open_questions") or []:
            item = deepcopy(question) if isinstance(question, dict) else {"question": str(question)}
            item.setdefault("blocking", True)
            item["source_batch_ids"] = [batch_id]
            if item.get("resolved") is True and str(item.get("resolution") or "").strip():
                _append_unique(resolved_questions, [item])
                continue
            if item["blocking"] is not True:
                _append_unique(audit_warnings, [item])
                continue
            key = _question_key(item)
            existing = question_index.get(key)
            if existing is None:
                consolidated_questions.append(item)
                question_index[key] = item
            else:
                _append_unique(existing.setdefault("source_batch_ids", []), [batch_id])
                for field in ("options", "evidence", "impact"):
                    if isinstance(existing.get(field), list):
                        _append_unique(existing[field], item.get(field) or [])

        batch_results.append({
            "batch_id": batch_id,
            "chunk_ids": deepcopy(fragment.get("chunk_ids") or []),
            "old_semantics": deepcopy(fragment.get("old_semantics") or []),
            "prompt_cleanup": deepcopy(fragment.get("prompt_cleanup") or []),
        })

    plan["batch_results"] = batch_results
    plan["open_questions"] = consolidated_questions
    plan["sop_mapping"]["status"] = "draft_ready"
    plan["status"] = (
        "open_questions_required"
        if consolidated_questions
        else "final_mapping_confirmation_required"
    )
    return plan


def _cmd_prepare_batch(args: argparse.Namespace) -> int:
    index = _read_json(args.index_file)
    if not isinstance(index, dict):
        raise ValueError("index file must contain a JSON object")
    chunks = _read_chunks_document(args.chunks_file)
    progress_file = Path(args.progress_file)
    progress = _read_json(str(progress_file))
    if not isinstance(progress, dict):
        raise ValueError("progress file must contain a JSON object")
    batch, resumed = _prepare_migration_batch(
        index,
        chunks,
        progress,
        max_chunks=args.max_chunks,
        max_action_edges=args.max_action_edges,
        max_evidence_chars=args.max_evidence_chars,
    )
    if batch is None:
        _write_json(progress_file, progress)
        print(json.dumps({
            "status": "no_pending_chunks",
            "progress_file": str(progress_file),
            "summary": progress.get("summary"),
        }, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0

    outputs = batch.setdefault("outputs", {})
    if not isinstance(outputs, dict):
        outputs = {}
        batch["outputs"] = outputs
    context_file = str(outputs.get("context") or args.out_file)
    outputs["context"] = context_file
    budgets = batch.get("budgets") if isinstance(batch.get("budgets"), dict) else {}
    max_evidence_chars = budgets.get("max_evidence_chars", args.max_evidence_chars)
    context = _build_batch_context(
        index,
        chunks,
        batch,
        max_evidence_chars=int(max_evidence_chars),
    )
    _write_json(Path(context_file), context)
    _write_json(progress_file, progress)
    print(json.dumps({
        "status": "resumed" if resumed else "prepared",
        "batch_id": batch["id"],
        "chunk_ids": batch.get("chunk_ids"),
        "context_file": context_file,
        "estimated": batch.get("estimated"),
        "budget_exceptions": batch.get("budget_exceptions"),
        "summary": progress.get("summary"),
    }, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _cmd_prepare_batches(args: argparse.Namespace) -> int:
    index = _read_json(args.index_file)
    if not isinstance(index, dict):
        raise ValueError("index file must contain a JSON object")
    chunks = _read_chunks_document(args.chunks_file)
    progress_file = Path(args.progress_file)
    progress = _read_json(str(progress_file))
    if not isinstance(progress, dict):
        raise ValueError("progress file must contain a JSON object")

    prepared = _prepare_migration_batches(
        index,
        chunks,
        progress,
        parallelism=args.parallelism,
        max_chunks=args.max_chunks,
        max_action_edges=args.max_action_edges,
        max_evidence_chars=args.max_evidence_chars,
    )
    out_dir = Path(args.out_dir)
    workers = []
    for item in prepared:
        batch = item["batch"]
        batch_id = str(batch["id"])
        context_file = out_dir / f"{batch_id}.context.json"
        plan_file = out_dir / f"{batch_id}.plan.json"
        outputs = batch.setdefault("outputs", {})
        if not isinstance(outputs, dict):
            outputs = {}
            batch["outputs"] = outputs
        outputs["context"] = str(context_file)
        outputs["plan"] = str(plan_file)
        budgets = batch.get("budgets") if isinstance(batch.get("budgets"), dict) else {}
        context = _build_batch_context(
            index,
            chunks,
            batch,
            max_evidence_chars=int(
                budgets.get("max_evidence_chars", args.max_evidence_chars)
            ),
        )
        _write_json(context_file, context)
        workers.append({
            "batch_id": batch_id,
            "chunk_ids": deepcopy(batch.get("chunk_ids") or []),
            "context_file": str(context_file),
            "plan_file": str(plan_file),
            "resumed": item["resumed"],
        })

    manifest_file = Path(args.manifest_file) if args.manifest_file else out_dir / "worker_manifest.json"
    manifest = {
        "schema_version": 1,
        "created_at_ms": _now_ms(),
        "parallelism": args.parallelism,
        "execution": {
            "contexts_prepared_only": True,
            "workers_started_by_script": False,
            "required_dispatch": "one task tool call per batch in the same assistant turn",
            "completion_barrier": "all listed plan files must exist before merge-batch-plans",
        },
        "progress_file": str(progress_file),
        "worker_contract": _batch_worker_contract(),
        "batches": workers,
    }
    _write_json(manifest_file, manifest)
    _write_json(progress_file, progress)
    print(json.dumps({
        "status": "prepared" if workers else "no_pending_chunks",
        "manifest_file": str(manifest_file),
        "workers": workers,
        "workers_started": False,
        "dispatch_required": "parallel task tool calls in one assistant turn",
        "active_batch_ids": progress.get("active_batch_ids"),
        "summary": progress.get("summary"),
    }, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _cmd_merge_batch_plans(args: argparse.Namespace) -> int:
    base_plan = _read_json(args.base_plan_file)
    if not isinstance(base_plan, dict):
        raise ValueError("base plan file must contain a JSON object")
    manifest = _read_json(args.manifest_file)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("batches"), list):
        raise ValueError("manifest file must contain a batches array")
    progress_file = Path(args.progress_file)
    progress = _read_json(str(progress_file))
    if not isinstance(progress, dict):
        raise ValueError("progress file must contain a JSON object")
    _ensure_batch_progress_state(progress)

    manifest_entries = {
        str(entry.get("batch_id")): entry
        for entry in manifest["batches"]
        if isinstance(entry, dict) and entry.get("batch_id")
    }
    if not manifest_entries:
        raise ValueError("manifest has no worker batches to merge")

    updated_progress = deepcopy(progress)
    for batch_id, entry in manifest_entries.items():
        plan_file = str(entry.get("plan_file") or "")
        if not plan_file or not Path(plan_file).is_file():
            raise ValueError(f"batch '{batch_id}' plan file is missing: {plan_file or '<empty>'}")
        batch = _batch_by_id(updated_progress, batch_id)
        if batch.get("status") not in {"in_progress", "completed"}:
            raise ValueError(
                f"batch '{batch_id}' must be in_progress or completed before merge"
            )
        _update_batch_progress(
            updated_progress,
            batch_id=batch_id,
            status="completed",
            artifacts={"plan": plan_file},
        )

    fragments = []
    for batch in updated_progress.get("batches") or []:
        if not isinstance(batch, dict) or batch.get("status") != "completed":
            continue
        batch_id = str(batch.get("id") or "")
        outputs = batch.get("outputs") if isinstance(batch.get("outputs"), dict) else {}
        plan_file = str(outputs.get("plan") or "")
        context_file = str(outputs.get("context") or "")
        if not batch_id or not plan_file or not Path(plan_file).is_file():
            raise ValueError(
                f"completed batch '{batch_id or '<unknown>'}' has no readable plan artifact"
            )
        if not context_file or not Path(context_file).is_file():
            raise ValueError(
                f"completed batch '{batch_id or '<unknown>'}' has no readable context artifact"
            )
        fragment = _read_json(plan_file)
        if not isinstance(fragment, dict):
            raise ValueError(f"batch '{batch_id}' plan must contain a JSON object")
        context = _read_json(context_file)
        if not isinstance(context, dict):
            raise ValueError(f"batch '{batch_id}' context must contain a JSON object")
        _validate_batch_fragment_coverage(fragment, context, batch_id=batch_id)
        fragments.append((batch_id, fragment))

    merged = _merge_batch_plan_fragments(base_plan, fragments)
    summary = updated_progress.get("summary") if isinstance(updated_progress.get("summary"), dict) else {}
    all_chunks_complete = bool(summary.get("total_chunks")) and (
        summary.get("completed") == summary.get("total_chunks")
    )
    unresolved_questions = merged.get("open_questions") or []
    confirmation_ready = all_chunks_complete and not unresolved_questions
    if not all_chunks_complete:
        merged["status"] = "batch_processing"

    mermaid = None
    if confirmation_ready:
        mermaid = _sop_mapping_mermaid(merged)

    _write_json(Path(args.out_file), merged)
    if args.open_questions_file:
        _write_json(Path(args.open_questions_file), {
            "count": len(unresolved_questions),
            "open_questions": unresolved_questions,
        })
    if args.mermaid_file:
        mermaid_path = Path(args.mermaid_file)
        if mermaid is None:
            if mermaid_path.exists():
                mermaid_path.unlink()
        else:
            mermaid_path.parent.mkdir(parents=True, exist_ok=True)
            mermaid_path.write_text(mermaid, encoding="utf-8")
    _write_json(progress_file, updated_progress)

    print(json.dumps({
        "status": merged.get("status"),
        "out_file": args.out_file,
        "merged_batches": [batch_id for batch_id, _ in fragments],
        "open_questions": len(unresolved_questions),
        "all_chunks_complete": all_chunks_complete,
        "confirmation_ready": confirmation_ready,
        "mermaid_file": args.mermaid_file if mermaid is not None else None,
        "summary": summary,
    }, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _cmd_emit_batch_context(args: argparse.Namespace) -> int:
    index = _read_json(args.index_file)
    if not isinstance(index, dict):
        raise ValueError("index file must contain a JSON object")
    chunks = _read_chunks_document(args.chunks_file)
    progress_file = Path(args.progress_file)
    progress = _read_json(str(progress_file))
    if not isinstance(progress, dict):
        raise ValueError("progress file must contain a JSON object")
    _ensure_batch_progress_state(progress)
    batch = _batch_by_id(progress, args.batch_id)
    outputs = batch.setdefault("outputs", {})
    if not isinstance(outputs, dict):
        outputs = {}
        batch["outputs"] = outputs
    outputs["context"] = args.out_file
    budgets = batch.get("budgets") if isinstance(batch.get("budgets"), dict) else {}
    max_evidence_chars = budgets.get("max_evidence_chars", args.max_evidence_chars)
    context = _build_batch_context(
        index,
        chunks,
        batch,
        max_evidence_chars=int(max_evidence_chars),
    )
    _write_json(Path(args.out_file), context)
    _write_json(progress_file, progress)
    print(json.dumps({
        "batch_id": args.batch_id,
        "out_file": args.out_file,
        "chunk_ids": batch.get("chunk_ids"),
    }, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _cmd_emit_mapping_mermaid(args: argparse.Namespace) -> int:
    plan = _read_json(args.plan_file)
    if isinstance(plan, dict) and (plan.get("batch_id") or plan.get("batch")):
        raise ValueError(
            "batch plans do not emit Mermaid; merge all batch plans before rendering"
        )
    mermaid = _sop_mapping_mermaid(plan)
    out_file = Path(args.out_file)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(mermaid, encoding="utf-8")
    mapping = plan.get("sop_mapping") if isinstance(plan, dict) else {}
    blocks = mapping.get("blocks") if isinstance(mapping, dict) else []
    relations = mapping.get("relations") if isinstance(mapping, dict) else []
    print(json.dumps({
        "plan_file": args.plan_file,
        "out_file": str(out_file),
        "blocks": len(blocks) if isinstance(blocks, list) else 0,
        "relations": len(relations) if isinstance(relations, list) else 0,
    }, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _cmd_update_batch_progress(args: argparse.Namespace) -> int:
    progress_file = Path(args.progress_file)
    progress = _read_json(str(progress_file))
    if not isinstance(progress, dict):
        raise ValueError("progress file must contain a JSON object")
    updated = _update_batch_progress(
        progress,
        batch_id=args.batch_id,
        status=args.status,
        note=args.note,
        artifacts=_parse_artifacts(args.artifact or []),
    )
    _write_json(progress_file, updated)
    batch = _batch_by_id(updated, args.batch_id)
    print(json.dumps({
        "progress_file": str(progress_file),
        "batch_id": args.batch_id,
        "chunk_ids": batch.get("chunk_ids"),
        "status": args.status,
        "summary": updated.get("summary"),
        "phase": updated.get("phase"),
    }, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _validate_prompt_reviews(
    plan: dict,
    index: dict,
    *,
    require_render_paths: bool = False,
) -> list[str]:
    contracts = {
        str(item.get("contract_id")): item
        for item in (index.get("migration_contracts") or {}).get("prompt_reviews", [])
        if isinstance(item, dict) and item.get("contract_id")
    }
    coverage = plan.get("coverage") if isinstance(plan.get("coverage"), dict) else {}
    reviews = {
        str(item.get("contract_id")): item
        for item in coverage.get("prompt_reviews") or []
        if isinstance(item, dict) and item.get("contract_id")
    }
    errors = []
    missing = sorted(set(contracts) - set(reviews))
    if missing:
        errors.append(f"coverage missing prompt_reviews: {missing}")

    tools_by_agent = {}
    for tool in index.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        tool_id = tool.get("id")
        if isinstance(tool_id, str) and tool_id.isdigit():
            tool_id = int(tool_id)
        if isinstance(tool_id, int) and not isinstance(tool_id, bool):
            agent_tools = tools_by_agent.setdefault(
                str(tool.get("agent_id") or ""), {}
            )
            agent_tools.setdefault(tool_id, set()).add(str(tool.get("name") or ""))

    for contract_id, review in reviews.items():
        contract = contracts.get(contract_id)
        if contract is None:
            errors.append(f"coverage prompt_review {contract_id} has no source contract")
            continue
        review_decision = review.get("decision")
        review_resolved = _migration_decision_is_resolved(review)
        review_dropped = _migration_decision_is_drop(review)
        source_prompt = str(contract.get("prompt") or "")
        expected_hash = hashlib.sha256(source_prompt.encode("utf-8")).hexdigest()
        if expected_hash != contract.get("prompt_sha256"):
            errors.append(f"prompt_review {contract_id} source prompt hash is invalid")
        if review.get("source_prompt_sha256") != expected_hash:
            errors.append(f"prompt_review {contract_id} was not performed against the full source prompt")
        if review.get("reviewed_full_prompt") is not True:
            errors.append(f"prompt_review {contract_id} must set reviewed_full_prompt=true")
        if review_decision in (None, "", "pending") or (
            review_decision == "open_question" and not review_resolved
        ):
            errors.append(f"prompt_review {contract_id} has unresolved decision")
        if review_dropped and not review_resolved:
            errors.append(
                f"prompt_review {contract_id} has unresolved decision "
                f"'{review_decision}'"
            )
        if not review.get("mapped_to") and not (review_dropped and review_resolved):
            errors.append(f"prompt_review {contract_id} has no mapped_to target")
        if not str(review.get("reason") or "").strip():
            errors.append(f"prompt_review {contract_id} missing reason")
        if not isinstance(review.get("control_semantics"), list):
            errors.append(f"prompt_review {contract_id} control_semantics must be an array")

        blocks = review.get("discovered_blocks")
        if not isinstance(blocks, list):
            errors.append(f"prompt_review {contract_id} discovered_blocks must be an array")
            continue
        seen_block_ids = set()
        previous_start = -1
        for position, raw_block in enumerate(blocks):
            label = f"prompt_review {contract_id} block[{position}]"
            if not isinstance(raw_block, dict):
                errors.append(f"{label} must be an object")
                continue
            block_id = str(raw_block.get("block_id") or "").strip()
            if not block_id:
                errors.append(f"{label} missing block_id")
            elif block_id in seen_block_ids:
                errors.append(f"prompt_review {contract_id} duplicates block_id {block_id}")
            seen_block_ids.add(block_id)
            if raw_block.get("sequence") != position:
                errors.append(f"{label} sequence must preserve source order")

            source_span = raw_block.get("source_span")
            source_quote = raw_block.get("source_quote")
            if not isinstance(source_span, dict):
                errors.append(f"{label} missing source_span")
                continue
            start = source_span.get("start")
            end = source_span.get("end")
            if (
                isinstance(start, bool)
                or isinstance(end, bool)
                or not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end <= start
                or end > len(source_prompt)
            ):
                errors.append(f"{label} has invalid source_span")
                continue
            if start < previous_start:
                errors.append(f"{label} is out of source order")
            previous_start = start
            if not isinstance(source_quote, str) or source_prompt[start:end] != source_quote:
                errors.append(f"{label} source_quote does not match the full source prompt")

            try:
                enriched = _enrich_discovered_prompt_block(raw_block)
            except ValueError as exc:
                errors.append(f"{label}: {exc}")
                continue
            block_decision = raw_block.get("decision")
            block_resolved = _migration_decision_is_resolved(raw_block)
            block_dropped = _migration_decision_is_drop(raw_block)
            if block_decision in (None, "", "pending") or (
                block_decision == "open_question" and not block_resolved
            ):
                errors.append(f"{label} has unresolved decision")
            if block_dropped and not block_resolved:
                errors.append(f"{label} has unresolved decision '{block_decision}'")
            for field in (
                "target_options", "library_block", "required_used_plugins", "required_plugin_types",
                "transfer_to_humans",
                "content_sha256", "must_preserve_verbatim",
            ):
                if field in enriched and raw_block.get(field) != enriched.get(field):
                    errors.append(f"{label} has invalid derived field {field}")
            target_type = raw_block.get("target_type")
            if (
                not (block_dropped and block_resolved)
                and target_type not in enriched["target_options"]
            ):
                errors.append(
                    f"{label} target_type {target_type!r} must be one of "
                    f"{enriched['target_options']}"
                )
            if not raw_block.get("mapped_to") and not (block_dropped and block_resolved):
                errors.append(f"{label} has no mapped_to target")
            if not str(raw_block.get("reason") or "").strip():
                errors.append(f"{label} missing mapping reason")
            if (
                require_render_paths
                and raw_block.get("kind") == "FIXED_WORDING"
                and target_type == "NODE_PROMPT_FIELD"
            ):
                render_path = raw_block.get("render_path")
                if (
                    not isinstance(render_path, list)
                    or not render_path
                    or any(not isinstance(part, str) or not part for part in render_path)
                ):
                    errors.append(
                        f"{label} NODE_PROMPT_FIELD requires a non-empty render_path"
                    )

            if not (block_dropped and block_resolved):
                kind = raw_block.get("kind")
                if kind == "TRANSFER_TO_HUMAN":
                    transfer_reason = str(raw_block.get("transfer_reason") or "")
                    if transfer_reason not in str(source_quote or ""):
                        errors.append(f"{label} transfer_reason is not preserved exactly in source_quote")
                elif kind == "BUSINESS_TOOL":
                    source_tools = tools_by_agent.get(
                        str(contract.get("agent_id") or ""), {}
                    )
                    source_tool_names = source_tools.get(raw_block.get("tool_id"))
                    if source_tool_names is None:
                        errors.append(f"{label} tool_id is not bound to the source agent")
                    elif raw_block.get("tool_name") not in source_tool_names:
                        errors.append(
                            f"{label} tool_name does not match source tool id "
                            f"{raw_block.get('tool_id')}"
                        )
                elif kind in {"FIXED_WORDING", "INLINE_FIXED_REPLY"}:
                    content = str(raw_block.get("content") or "")
                    if content not in source_prompt:
                        errors.append(f"{label} fixed wording is not present verbatim in the source prompt")
                elif kind == "WAIT_FOR_USER" and raw_block.get("target_type") == "AGENT_WAIT":
                    if not str(raw_block.get("rendered_instruction") or "").strip():
                        errors.append(f"{label} AGENT_WAIT requires rendered_instruction")

        if review_dropped and review_resolved:
            continue

        protected_refs = contract.get("protected_refs") or []
        if not isinstance(protected_refs, list):
            errors.append(f"prompt_review {contract_id} protected_refs must be an array")
            continue
        for protected_position, protected_ref in enumerate(protected_refs):
            protected_label = (
                f"prompt_review {contract_id} protected_ref[{protected_position}]"
            )
            if not isinstance(protected_ref, dict):
                errors.append(f"{protected_label} must be an object")
                continue
            protected_span = protected_ref.get("source_span")
            if not isinstance(protected_span, dict):
                errors.append(f"{protected_label} missing source_span")
                continue
            protected_start = protected_span.get("start")
            protected_end = protected_span.get("end")
            if (
                isinstance(protected_start, bool)
                or isinstance(protected_end, bool)
                or not isinstance(protected_start, int)
                or not isinstance(protected_end, int)
                or protected_start < 0
                or protected_end <= protected_start
                or protected_end > len(source_prompt)
            ):
                errors.append(f"{protected_label} has invalid source_span")
                continue
            if source_prompt[protected_start:protected_end] != protected_ref.get(
                "source_quote"
            ):
                errors.append(f"{protected_label} source_quote does not match source prompt")
                continue

            span_matches = []
            for raw_block in blocks:
                if not isinstance(raw_block, dict):
                    continue
                block_span = raw_block.get("source_span")
                if not isinstance(block_span, dict):
                    continue
                if (
                    block_span.get("start") == protected_start
                    and block_span.get("end") == protected_end
                ):
                    span_matches.append(raw_block)
            kind = protected_ref.get("kind")
            kind_matches = [
                block for block in span_matches if block.get("kind") == kind
            ]
            if not kind_matches:
                protected_ref_id = protected_ref.get("protected_ref_id")
                if span_matches:
                    errors.append(
                        f"{protected_label} {protected_ref_id} is covered with the wrong kind"
                    )
                else:
                    errors.append(
                        f"{protected_label} {protected_ref_id} is missing from discovered_blocks"
                    )
                continue
            if len(kind_matches) > 1:
                errors.append(
                    f"{protected_label} is covered more than once in discovered_blocks"
                )
                continue
            block = kind_matches[0]
            block_ref_id = block.get("protected_ref_id")
            if block_ref_id not in (None, "", protected_ref.get("protected_ref_id")):
                errors.append(f"{protected_label} has a mismatched protected_ref_id")
            if (
                _migration_decision_is_drop(block)
                and _migration_decision_is_resolved(block)
            ):
                continue
            if kind == "TEMPLATE_REPLY":
                if block.get("template_id") != protected_ref.get("template_id"):
                    errors.append(
                        f"{protected_label} template_id must remain "
                        f"{protected_ref.get('template_id')}"
                    )
            elif kind == "TRANSFER_TO_HUMAN":
                if block.get("transfer_reason") != protected_ref.get("transfer_reason"):
                    errors.append(
                        f"{protected_label} transfer_reason must remain exactly "
                        f"{protected_ref.get('transfer_reason')!r}"
                    )
            elif kind == "BUSINESS_TOOL":
                if block.get("tool_id") != protected_ref.get("tool_id"):
                    errors.append(
                        f"{protected_label} tool_id must remain "
                        f"{protected_ref.get('tool_id')}"
                    )
                if block.get("tool_name") != protected_ref.get("tool_name"):
                    errors.append(
                        f"{protected_label} tool_name must remain exactly "
                        f"{protected_ref.get('tool_name')!r}"
                    )
    return errors


def validate_prompt_block_rendering(plan: object, index: dict, source: object) -> list[str]:
    """Verify that migration prompt-block contracts reached target source nodes."""
    if not isinstance(plan, dict):
        return ["migration plan must be a JSON object"]
    if not isinstance(source, dict) or not isinstance(source.get("nodes"), list):
        return ["target source must be a JSON object with a nodes array"]
    legacy_contracts = {
        str(item.get("contract_id")): item
        for item in (index.get("migration_contracts") or {}).get("prompt_blocks", [])
        if isinstance(item, dict) and item.get("contract_id")
    }
    coverage = plan.get("coverage") if isinstance(plan.get("coverage"), dict) else {}
    legacy_mapped = {
        str(item.get("contract_id")): item
        for item in coverage.get("prompt_blocks") or []
        if isinstance(item, dict) and item.get("contract_id")
    }
    nodes = {
        str(node.get("key")): node
        for node in source["nodes"]
        if isinstance(node, dict) and node.get("key")
    }
    edges = [edge for edge in source.get("edges") or [] if isinstance(edge, dict)]
    errors = _validate_prompt_reviews(plan, index, require_render_paths=True)

    def value_at_path(value: object, path: object) -> object:
        if not isinstance(path, list) or not path:
            return None
        current = value
        for part in path:
            if not isinstance(current, dict) or not isinstance(part, str) or part not in current:
                return None
            current = current[part]
        return current

    render_items = [
        (contract_id, contract, legacy_mapped.get(contract_id))
        for contract_id, contract in legacy_contracts.items()
    ]
    for review in coverage.get("prompt_reviews") or []:
        if not isinstance(review, dict):
            continue
        review_id = str(review.get("contract_id") or "")
        for block in review.get("discovered_blocks") or []:
            if not isinstance(block, dict):
                continue
            block_id = str(block.get("block_id") or "")
            render_items.append((f"{review_id}/{block_id}", block, block))

    for contract_id, contract, decision in render_items:
        if decision is None:
            errors.append(f"prompt block {contract_id} is missing from migration coverage")
            continue
        if (
            _migration_decision_is_drop(decision)
            and _migration_decision_is_resolved(decision)
        ):
            continue
        target_type = str(decision.get("target_type") or "")
        target_keys = decision.get("rendered_to") or decision.get("mapped_to") or []
        if not isinstance(target_keys, list):
            target_keys = [target_keys]
        target_keys = [str(item) for item in target_keys if str(item or "").strip()]
        if not target_keys:
            errors.append(f"prompt block {contract_id} has no rendered target")
            continue
        target_nodes = []
        for key in target_keys:
            node = nodes.get(key)
            if node is None and key == "$transfer" and target_type == "TRANSFER_NODE":
                node = {"key": "$transfer", "type": "transfer"}
            if node is None:
                errors.append(f"prompt block {contract_id} target node '{key}' does not exist")
            else:
                target_nodes.append(node)
        if len(target_nodes) != len(target_keys):
            continue

        if target_type == "AGENT_LIBRARY_BLOCK":
            expected_block = str(contract.get("library_block") or "")
            if not expected_block:
                errors.append(f"prompt block {contract_id} has no source LibraryBlock")
                continue
            for node in target_nodes:
                if str(node.get("type") or "").lower() != "agent":
                    errors.append(
                        f"prompt block {contract_id} target '{node.get('key')}' must be AGENT"
                    )
                elif expected_block not in str(node.get("prompt") or ""):
                    errors.append(
                        f"prompt block {contract_id} LibraryBlock is missing from AGENT "
                        f"'{node.get('key')}' prompt"
                    )
        elif target_type == "REPLY_TEMPLATE":
            for node in target_nodes:
                if (
                    str(node.get("type") or "").lower() != "reply"
                    or str(node.get("reply_type") or "").upper() != "TEMPLATE"
                    or str(node.get("template_id") or "") != str(contract.get("template_id") or "")
                ):
                    errors.append(
                        f"prompt block {contract_id} target '{node.get('key')}' does not preserve "
                        f"template id {contract.get('template_id')}"
                    )
        elif target_type == "TOOL_NODE":
            for node in target_nodes:
                if (
                    str(node.get("type") or "").lower() != "tool"
                    or str(node.get("tool_id") or "") != str(contract.get("tool_id") or "")
                ):
                    errors.append(
                        f"prompt block {contract_id} target '{node.get('key')}' does not preserve "
                        f"tool id {contract.get('tool_id')}"
                    )
        elif target_type == "TRANSFER_NODE":
            for node in target_nodes:
                if str(node.get("type") or "").lower() not in {"transfer", "transfer_to_human"}:
                    errors.append(
                        f"prompt block {contract_id} target '{node.get('key')}' must transfer to human"
                    )
        elif target_type == "NODE_PROMPT_FIELD":
            content = str(contract.get("content") or "")
            render_path = contract.get("render_path")
            if (
                not content
                or hashlib.sha256(content.encode("utf-8")).hexdigest()
                != contract.get("content_sha256")
            ):
                errors.append(f"prompt block {contract_id} source fixed wording is incomplete")
                continue
            if (
                not isinstance(render_path, list)
                or not render_path
                or any(not isinstance(part, str) or not part for part in render_path)
            ):
                errors.append(
                    f"prompt block {contract_id} NODE_PROMPT_FIELD has no valid render_path"
                )
                continue
            for node in target_nodes:
                rendered_value = value_at_path(node, render_path)
                if not isinstance(rendered_value, str):
                    errors.append(
                        f"prompt block {contract_id} target '{node.get('key')}' has no text at "
                        f"render_path {render_path}"
                    )
                elif content not in rendered_value:
                    errors.append(
                        f"prompt block {contract_id} fixed wording is not preserved verbatim in "
                        f"'{node.get('key')}' at render_path {render_path}"
                    )
        elif target_type in {"AGENT_INLINE_WORDING", "REPLY_PROMPT", "REPLY_DYNAMIC_TEMPLATE"}:
            content = str(contract.get("content") or "")
            if not content or hashlib.sha256(content.encode("utf-8")).hexdigest() != contract.get("content_sha256"):
                errors.append(f"prompt block {contract_id} source fixed wording is incomplete")
                continue
            for node in target_nodes:
                node_type = str(node.get("type") or "").lower()
                if target_type == "AGENT_INLINE_WORDING":
                    field = "prompt"
                    valid_type = node_type == "agent"
                elif target_type == "REPLY_DYNAMIC_TEMPLATE":
                    field = "template_content"
                    valid_type = node_type == "reply" and str(node.get("reply_type") or "").upper() == "DYNAMIC_TEMPLATE"
                else:
                    field = "prompt"
                    valid_type = node_type == "reply" and str(node.get("reply_type") or "PROMPT").upper() == "PROMPT"
                if not valid_type:
                    errors.append(
                        f"prompt block {contract_id} target '{node.get('key')}' has wrong node type"
                    )
                elif content not in str(node.get(field) or ""):
                    errors.append(
                        f"prompt block {contract_id} fixed wording is not preserved verbatim in "
                        f"'{node.get('key')}'"
                    )
        elif target_type in {"AGENT_WAIT", "REPLY_WAIT", "QUESTION_WAIT"}:
            expected_node_type = {
                "AGENT_WAIT": "agent",
                "REPLY_WAIT": "reply",
                "QUESTION_WAIT": "question",
            }[target_type]
            for node in target_nodes:
                node_key = str(node.get("key"))
                if str(node.get("type") or "").lower() != expected_node_type:
                    errors.append(
                        f"prompt block {contract_id} wait target '{node_key}' must be {expected_node_type.upper()}"
                    )
                elif target_type == "AGENT_WAIT" and str(
                    contract.get("rendered_instruction") or ""
                ) not in str(node.get("prompt") or ""):
                    errors.append(
                        f"prompt block {contract_id} AGENT wait target '{node_key}' "
                        "has no explicit wait-for-user instruction"
                    )
                elif target_type == "REPLY_WAIT" and not any(
                    str(edge.get("from") or "") == node_key for edge in edges
                ):
                    errors.append(
                        f"prompt block {contract_id} REPLY wait target '{node_key}' needs an outgoing edge"
                    )
        else:
            errors.append(
                f"prompt block {contract_id} has unsupported render target_type {target_type!r}"
            )
    return errors


def _cmd_validate_prompt_block_rendering(args: argparse.Namespace) -> int:
    plan = _read_json(args.plan_file)
    index = _read_json(args.index_file)
    source = _read_json(args.source_file)
    if not isinstance(index, dict):
        raise ValueError("index file must contain a JSON object")
    errors = validate_prompt_block_rendering(plan, index, source)
    result = {"valid": not errors, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if not errors else 1


def _cmd_audit_migration_source(args: argparse.Namespace) -> int:
    plan = _read_json(args.plan_file)
    index = _read_json(args.index_file)
    source = _read_json(args.source_file)
    report = audit_migration_source(plan, index, source)
    if args.out_file:
        _write_json(Path(args.out_file), report)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 1 if report["blocking"] else 0


def validate_migration_plan(plan: object, index: dict) -> list[str]:
    """Validate the evidence gates required before generating full source."""
    errors = []
    if not isinstance(plan, dict):
        return ["migration plan must be a JSON object"]
    skeleton = plan.get("flow_skeleton") or plan.get("flow_understanding")
    if not skeleton:
        errors.append("missing required migration plan section: flow_skeleton")
    if "sop_mapping" not in plan:
        errors.append("missing required migration plan section: sop_mapping")
    else:
        try:
            _sop_mapping_mermaid(plan)
        except ValueError as exc:
            errors.append(f"invalid sop_mapping: {exc}")
        else:
            mapping = plan.get("sop_mapping")
            blocks = mapping.get("blocks") if isinstance(mapping, dict) else []
            for idx, block in enumerate(blocks):
                selected_nodes = block.get("selected_nodes") if isinstance(block, dict) else []
                if not isinstance(selected_nodes, list) or not any(
                    str(item).strip() for item in selected_nodes
                ):
                    errors.append(
                        f"sop_mapping.blocks[{idx}] requires selected_nodes before source generation"
                    )
    for key in ("merge_groups", "node_decision", "coverage"):
        if key not in plan or plan.get(key) is None or (key != "merge_groups" and not plan.get(key)):
            errors.append(f"missing required migration plan section: {key}")
    coverage = plan.get("coverage") if isinstance(plan.get("coverage"), dict) else {}
    agents = coverage.get("agents") if isinstance(coverage.get("agents"), list) else []
    tools = coverage.get("tools") if isinstance(coverage.get("tools"), list) else []
    resources = coverage.get("resources") if isinstance(coverage.get("resources"), list) else []
    actions = coverage.get("actions") if isinstance(coverage.get("actions"), list) else []
    explicit_edges = coverage.get("explicit_edges") if isinstance(coverage.get("explicit_edges"), list) else []
    errors.extend(_validate_prompt_reviews(plan, index))

    def coverage_decision(item: dict, label: str) -> tuple[bool, bool]:
        decision = item.get("decision")
        resolved = _migration_decision_is_resolved(item)
        dropped = _migration_decision_is_drop(item)
        if (decision == "open_question" or dropped) and not resolved:
            errors.append(f"coverage {label} has unresolved decision '{decision}'")
        return resolved, dropped

    def require_mapping(item: dict, label: str, resolved: bool, dropped: bool) -> None:
        if not item.get("mapped_to") and not (resolved and dropped):
            errors.append(f"coverage {label} has no mapped_to target")
    expected_agents = {str(agent.get("id")) for agent in index.get("agents") or []}
    mapped_agents = {
        str(item.get("old_id") or item.get("old_agent_id") or item.get("id"))
        for item in agents
        if isinstance(item, dict)
    }
    missing_agents = sorted(expected_agents - mapped_agents)
    if missing_agents:
        errors.append(f"coverage missing agents: {missing_agents}")
    for item in agents:
        if not isinstance(item, dict):
            errors.append("coverage agents entries must be objects")
            continue
        item_id = item.get("old_id") or item.get("old_agent_id") or item.get("id")
        resolved, dropped = coverage_decision(item, f"agent {item_id}")
        require_mapping(item, f"agent {item_id}", resolved, dropped)
        if not item.get("reason"):
            errors.append(
                f"coverage agent {item_id} "
                "missing reason"
            )
    expected_tools = {
        str(tool.get("tool_key") or tool.get("id"))
        for tool in index.get("tools") or []
        if tool.get("tool_key") or tool.get("id")
    }
    mapped_tools = {
        str(item.get("old_tool_key") or item.get("old_tool_id") or item.get("tool_id") or item.get("id"))
        for item in tools
        if isinstance(item, dict)
    }
    missing_tools = sorted(expected_tools - mapped_tools)
    if missing_tools:
        errors.append(f"coverage missing tools: {missing_tools}")
    for item in tools:
        if not isinstance(item, dict):
            errors.append("coverage tools entries must be objects")
            continue
        item_id = item.get("old_tool_key") or item.get("old_tool_id") or item.get("tool_id") or item.get("id")
        resolved, dropped = coverage_decision(item, f"tool {item_id}")
        require_mapping(item, f"tool {item_id}", resolved, dropped)
        if not item.get("reason"):
            errors.append(
                f"coverage tool {item_id} "
                "missing reason"
            )
    expected_resources = {
        str(resource_id)
        for resource_id in (index.get("coverage_manifest") or {}).get("resources") or []
        if resource_id
    }
    mapped_resources = {
        str(item.get("resource_id") or item.get("id"))
        for item in resources
        if isinstance(item, dict) and (item.get("resource_id") or item.get("id"))
    }
    missing_resources = sorted(expected_resources - mapped_resources)
    if missing_resources:
        errors.append(f"coverage missing resources: {missing_resources}")
    if len(resources) < len(expected_resources):
        errors.append(f"coverage resources incomplete: expected {len(expected_resources)}, got {len(resources)}")
    for item in resources:
        if not isinstance(item, dict):
            errors.append("coverage resources entries must be objects")
            continue
        resource_id = item.get("resource_id") or item.get("id")
        resolved, dropped = coverage_decision(item, f"resource {resource_id}")
        require_mapping(item, f"resource {resource_id}", resolved, dropped)
        if not item.get("reason"):
            errors.append(f"coverage resource {resource_id} missing reason")
    expected_explicit_edges = {
        str(edge.get("edge_id")) for edge in index.get("explicit_edges") or [] if edge.get("edge_id")
    }
    mapped_explicit_edges = {
        str(item.get("edge_id")) for item in explicit_edges
        if isinstance(item, dict) and item.get("edge_id")
    }
    missing_explicit_edges = sorted(expected_explicit_edges - mapped_explicit_edges)
    if missing_explicit_edges:
        errors.append(f"coverage missing explicit edges: {missing_explicit_edges}")
    for item in explicit_edges:
        if not isinstance(item, dict):
            errors.append("coverage explicit_edges entries must be objects")
            continue
        edge_id = item.get("edge_id")
        if item.get("routing_semantics") != "model_selectable":
            errors.append(
                f"coverage explicit edge {edge_id} must keep routing_semantics=model_selectable"
            )
        if item.get("decision") in (None, "", "pending"):
            errors.append(
                f"coverage explicit edge {edge_id} requires a semantic decision; "
                "do not turn an agentEdges entry into a deterministic target edge"
            )
        resolved, dropped = coverage_decision(item, f"explicit edge {edge_id}")
        require_mapping(item, f"explicit edge {edge_id}", resolved, dropped)
        if not item.get("reason"):
            errors.append(f"coverage explicit edge {edge_id} missing reason")
    expected_actions = {
        str(edge.get("action_id")) for edge in index.get("action_edges") or [] if edge.get("action_id")
    }
    mapped_actions = {
        str(item.get("action_id")) for item in actions
        if isinstance(item, dict) and item.get("action_id")
    }
    missing_actions = sorted(expected_actions - mapped_actions)
    if missing_actions:
        errors.append(f"coverage missing actions: {missing_actions}")
    if len(actions) < len(expected_actions):
        errors.append(f"coverage actions incomplete: expected {len(expected_actions)}, got {len(actions)}")
    for item in actions:
        if not isinstance(item, dict):
            errors.append("coverage actions entries must be objects")
            continue
        resolved, dropped = coverage_decision(item, f"action {item.get('action_id')}")
        require_mapping(item, f"action {item.get('action_id')}", resolved, dropped)
        if not item.get("reason"):
            errors.append(f"coverage action {item.get('action_id')} missing reason")

    # These sections are absent on indexes generated by older analyzer versions.
    # When present they are executable contracts, not optional documentation.
    for section in ("classifiers", "templates", "interactions", "branches", "prompt_blocks"):
        expected = {str(item.get("contract_id")) for item in (index.get("migration_contracts") or {}).get(section, [])}
        if not expected:
            continue
        mapped = coverage.get(section) if isinstance(coverage.get(section), list) else []
        by_id = {str(item.get("contract_id")): item for item in mapped if isinstance(item, dict) and item.get("contract_id")}
        missing = sorted(expected - set(by_id))
        if missing:
            errors.append(f"coverage missing {section}: {missing}")
        for contract_id, item in by_id.items():
            resolved, dropped = coverage_decision(item, f"{section} {contract_id}")
            require_mapping(item, f"{section} {contract_id}", resolved, dropped)
            if not item.get("reason"):
                errors.append(f"coverage {section} {contract_id} missing reason")
            if (
                section == "templates"
                and not (resolved and dropped)
                and item.get("target_type")
                not in {"TEMPLATE", "NEW_TEMPLATE", "USER_APPROVED_PROMPT"}
            ):
                errors.append(f"coverage template {contract_id} must declare TEMPLATE, NEW_TEMPLATE, or USER_APPROVED_PROMPT target_type")
            if section == "prompt_blocks" and not (resolved and dropped):
                expected_contract = next(
                    (
                        contract
                        for contract in (index.get("migration_contracts") or {}).get("prompt_blocks", [])
                        if str(contract.get("contract_id")) == contract_id
                    ),
                    {},
                )
                target_type = item.get("target_type")
                allowed_targets = set(expected_contract.get("target_options") or [])
                if not target_type:
                    errors.append(
                        f"coverage prompt_blocks {contract_id} missing target_type"
                    )
                elif target_type not in allowed_targets:
                    errors.append(
                        f"coverage prompt_blocks {contract_id} target_type {target_type!r} "
                        f"must be one of {sorted(allowed_targets)}"
                    )
                if expected_contract.get("kind") == "INLINE_FIXED_REPLY":
                    if item.get("source_content_sha256") != expected_contract.get("content_sha256"):
                        errors.append(
                            f"coverage prompt_blocks {contract_id} lost fixed wording content hash"
                        )
                    if item.get("must_preserve_verbatim") is not True:
                        errors.append(
                            f"coverage prompt_blocks {contract_id} must preserve fixed wording verbatim"
                        )

    for idx, decision in enumerate(
        (plan.get("node_decision") if isinstance(plan.get("node_decision"), list) else [plan.get("node_decision")])
    ):
        if not isinstance(decision, dict):
            errors.append(f"node_decision[{idx}] must be an object")
            continue
        for key in ("candidate_nodes", "selected_nodes", "reason", "evidence"):
            if not decision.get(key):
                errors.append(f"node_decision[{idx}] missing {key}")
    return errors


def build_migration_handoff(
    plan: object,
    index: object,
    source: object,
    *,
    plan_file: str,
    index_file: str,
    source_file: str,
) -> dict:
    """Record migration inputs and validation findings for an optional handoff."""
    if isinstance(index, dict):
        plan_errors = validate_migration_plan(plan, index)
        prompt_rendering_errors = validate_prompt_block_rendering(plan, index, source)
    else:
        plan_errors = ["migration index must be a JSON object"]
        prompt_rendering_errors = ["migration index must be a JSON object"]
    source_audit = audit_migration_source(plan, index, source)
    fingerprints = {
        "index_sha256": _migration_source_fingerprint(index),
        "plan_sha256": _migration_source_fingerprint(plan),
        "source_sha256": _migration_source_fingerprint(source),
    }
    validation_passed = (
        not plan_errors
        and not prompt_rendering_errors
        and not source_audit["blocking"]
    )
    warning_count = int(source_audit.get("summary", {}).get("warnings") or 0)
    return {
        "schema_version": MIGRATION_HANDOFF_SCHEMA_VERSION,
        "kind": MIGRATION_HANDOFF_KIND,
        "created_at_ms": _now_ms(),
        "status": (
            "recorded_with_errors"
            if not validation_passed
            else "recorded_with_warnings"
            if warning_count
            else "recorded"
        ),
        "validation_passed": validation_passed,
        "source": index.get("source") if isinstance(index, dict) else None,
        "fingerprints": fingerprints,
        "artifacts": {
            "index": {"path": index_file, "sha256": fingerprints["index_sha256"]},
            "plan": {"path": plan_file, "sha256": fingerprints["plan_sha256"]},
            "source": {"path": source_file, "sha256": fingerprints["source_sha256"]},
        },
        "validation": {
            "migration_plan": {
                "valid": not plan_errors,
                "errors": plan_errors,
            },
            "prompt_block_rendering": {
                "valid": not prompt_rendering_errors,
                "errors": prompt_rendering_errors,
            },
            "source_audit": {
                "status": source_audit.get("status"),
                "blocking": source_audit.get("blocking"),
                "summary": source_audit.get("summary"),
                "errors": source_audit.get("errors") or [],
                "warning_codes": sorted({
                    str(item.get("code"))
                    for item in source_audit.get("warnings") or []
                    if isinstance(item, dict) and item.get("code")
                }),
            },
        },
        "policy": {
            "semantic_warnings_block": False,
            "verification_required": False,
            "verification_recommended_for": [
                "cross_turn_resume",
                "multi_worker_handoff",
                "manual_artifact_edit",
            ],
        },
    }


def verify_migration_handoff(
    handoff: object,
    plan: object,
    index: object,
    source: object,
) -> dict:
    """Verify that a handoff still describes the current migration inputs."""
    if not isinstance(handoff, dict):
        return {
            "valid": False,
            "code": "INVALID_MIGRATION_HANDOFF",
            "message": "migration handoff must be a JSON object",
            "stale_artifacts": [],
        }
    if (
        handoff.get("schema_version") != MIGRATION_HANDOFF_SCHEMA_VERSION
        or handoff.get("kind") != MIGRATION_HANDOFF_KIND
    ):
        return {
            "valid": False,
            "code": "INVALID_MIGRATION_HANDOFF",
            "message": "migration handoff kind or schema_version is not supported",
            "stale_artifacts": [],
        }
    expected = handoff.get("fingerprints")
    required_hashes = {"index_sha256", "plan_sha256", "source_sha256"}
    if not isinstance(expected, dict) or not required_hashes.issubset(expected):
        return {
            "valid": False,
            "code": "INVALID_MIGRATION_HANDOFF",
            "message": "migration handoff is missing required fingerprints",
            "stale_artifacts": [],
        }
    current = {
        "index_sha256": _migration_source_fingerprint(index),
        "plan_sha256": _migration_source_fingerprint(plan),
        "source_sha256": _migration_source_fingerprint(source),
    }
    artifact_by_hash = {
        "index_sha256": "index",
        "plan_sha256": "plan",
        "source_sha256": "source",
    }
    stale_artifacts = [
        artifact_by_hash[key]
        for key in ("index_sha256", "plan_sha256", "source_sha256")
        if expected.get(key) != current[key]
    ]
    if stale_artifacts:
        return {
            "valid": False,
            "code": "STALE_MIGRATION_PLAN",
            "message": "migration inputs changed after handoff; emit a new handoff",
            "stale_artifacts": stale_artifacts,
            "validation_passed": handoff.get("validation_passed"),
            "expected_fingerprints": expected,
            "current_fingerprints": current,
        }
    return {
        "valid": True,
        "code": None,
        "message": "migration handoff matches the current index, plan, and source",
        "stale_artifacts": [],
        "validation_passed": handoff.get("validation_passed"),
        "fingerprints": current,
    }


def _cmd_emit_handoff(args: argparse.Namespace) -> int:
    plan = _read_json(args.plan_file)
    index = _read_json(args.index_file)
    source = _read_json(args.source_file)
    handoff = build_migration_handoff(
        plan,
        index,
        source,
        plan_file=args.plan_file,
        index_file=args.index_file,
        source_file=args.source_file,
    )
    _write_json(Path(args.out_file), handoff)
    print(json.dumps(handoff, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def _cmd_verify_handoff(args: argparse.Namespace) -> int:
    handoff = _read_json(args.handoff_file)
    plan = _read_json(args.plan_file)
    index = _read_json(args.index_file)
    source = _read_json(args.source_file)
    result = verify_migration_handoff(handoff, plan, index, source)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["valid"] else 1


def _cmd_validate_migration_plan(args: argparse.Namespace) -> int:
    plan = _read_json(args.plan_file)
    index = _read_json(args.index_file)
    errors = validate_migration_plan(plan, index)
    result = {"valid": not errors, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if not errors else 1


def _cmd_coverage_report(args: argparse.Namespace) -> int:
    plan = _read_json(args.plan_file)
    index = _read_json(args.index_file)
    report = migration_coverage_report(plan, index)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if not report["blocking"] else 1


def _cmd_update_progress(args: argparse.Namespace) -> int:
    progress_file = Path(args.progress_file)
    progress = _read_json(str(progress_file))
    updated = _update_progress(
        progress,
        chunk_id=args.chunk_id,
        status=args.status,
        note=args.note,
        artifacts=_parse_artifacts(args.artifact or []),
    )
    _write_json(progress_file, updated)
    print(json.dumps({
        "progress_file": str(progress_file),
        "chunk_id": args.chunk_id,
        "status": args.status,
        "summary": updated.get("summary"),
        "phase": updated.get("phase"),
    }, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze legacy MULTI_AGENT graphs for CHAT_FLOW migration")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("--input", required=True)
    inspect.add_argument("--out-dir", required=True)
    inspect.add_argument("--prompt-max-chars", type=int, default=9000)
    inspect.add_argument("--prompt-term", action="append", default=[])
    inspect.add_argument("--pretty", action="store_true")
    inspect.set_defaults(func=_cmd_inspect)

    emit = sub.add_parser("emit-chunk-context")
    emit.add_argument("--index-file", required=True)
    emit.add_argument("--chunks-file", required=True)
    emit.add_argument("--chunk-id", required=True)
    emit.add_argument("--out-file", required=True)
    emit.add_argument("--pretty", action="store_true")
    emit.set_defaults(func=_cmd_emit_chunk_context)

    prepare_batch = sub.add_parser(
        "prepare-batch",
        help="claim one bounded topology-safe batch and emit its compact context",
    )
    prepare_batch.add_argument("--index-file", required=True)
    prepare_batch.add_argument("--chunks-file", required=True)
    prepare_batch.add_argument("--progress-file", required=True)
    prepare_batch.add_argument("--out-file", required=True)
    prepare_batch.add_argument("--max-chunks", type=int, default=4)
    prepare_batch.add_argument("--max-action-edges", type=int, default=12)
    prepare_batch.add_argument("--max-evidence-chars", type=int, default=20000)
    prepare_batch.add_argument("--pretty", action="store_true")
    prepare_batch.set_defaults(func=_cmd_prepare_batch)

    prepare_batches = sub.add_parser(
        "prepare-batches",
        help="claim multiple disjoint batches and emit isolated worker contexts",
    )
    prepare_batches.add_argument("--index-file", required=True)
    prepare_batches.add_argument("--chunks-file", required=True)
    prepare_batches.add_argument("--progress-file", required=True)
    prepare_batches.add_argument("--out-dir", required=True)
    prepare_batches.add_argument("--manifest-file")
    prepare_batches.add_argument("--parallelism", type=int, default=4)
    prepare_batches.add_argument("--max-chunks", type=int, default=4)
    prepare_batches.add_argument("--max-action-edges", type=int, default=12)
    prepare_batches.add_argument("--max-evidence-chars", type=int, default=20000)
    prepare_batches.add_argument("--pretty", action="store_true")
    prepare_batches.set_defaults(func=_cmd_prepare_batches)

    merge_batches = sub.add_parser(
        "merge-batch-plans",
        help="merge isolated worker plans and emit only a confirmation-ready global Mermaid",
    )
    merge_batches.add_argument("--base-plan-file", required=True)
    merge_batches.add_argument("--manifest-file", required=True)
    merge_batches.add_argument("--progress-file", required=True)
    merge_batches.add_argument("--out-file", required=True)
    merge_batches.add_argument("--open-questions-file")
    merge_batches.add_argument("--mermaid-file")
    merge_batches.add_argument("--pretty", action="store_true")
    merge_batches.set_defaults(func=_cmd_merge_batch_plans)

    emit_batch = sub.add_parser(
        "emit-batch-context",
        help="re-emit context for an existing batch without selecting a new one",
    )
    emit_batch.add_argument("--index-file", required=True)
    emit_batch.add_argument("--chunks-file", required=True)
    emit_batch.add_argument("--progress-file", required=True)
    emit_batch.add_argument("--batch-id", required=True)
    emit_batch.add_argument("--out-file", required=True)
    emit_batch.add_argument("--max-evidence-chars", type=int, default=20000)
    emit_batch.add_argument("--pretty", action="store_true")
    emit_batch.set_defaults(func=_cmd_emit_batch_context)

    mapping_mermaid = sub.add_parser(
        "emit-mapping-mermaid",
        help="render SOP-to-node-category draft Mermaid from a migration plan",
    )
    mapping_mermaid.add_argument("--plan-file", required=True)
    mapping_mermaid.add_argument("--out-file", required=True)
    mapping_mermaid.add_argument("--pretty", action="store_true")
    mapping_mermaid.set_defaults(func=_cmd_emit_mapping_mermaid)

    validate_plan = sub.add_parser("validate-migration-plan")
    validate_plan.add_argument("--plan-file", required=True)
    validate_plan.add_argument("--index-file", required=True)
    validate_plan.add_argument("--pretty", action="store_true")
    validate_plan.set_defaults(func=_cmd_validate_migration_plan)

    validate_rendering = sub.add_parser(
        "validate-prompt-block-rendering",
        help="verify migration prompt-block contracts against CHAT_FLOW source nodes",
    )
    validate_rendering.add_argument("--plan-file", required=True)
    validate_rendering.add_argument("--index-file", required=True)
    validate_rendering.add_argument("--source-file", required=True)
    validate_rendering.add_argument("--pretty", action="store_true")
    validate_rendering.set_defaults(func=_cmd_validate_prompt_block_rendering)

    audit_source = sub.add_parser(
        "audit-migration-source",
        help="report plan-to-source drift; semantic node-selection findings are warnings",
    )
    audit_source.add_argument("--plan-file", required=True)
    audit_source.add_argument("--index-file", required=True)
    audit_source.add_argument("--source-file", required=True)
    audit_source.add_argument("--out-file")
    audit_source.add_argument("--pretty", action="store_true")
    audit_source.set_defaults(func=_cmd_audit_migration_source)

    emit_handoff = sub.add_parser(
        "emit-handoff",
        help="record migration index/plan/source fingerprints for an optional handoff",
    )
    emit_handoff.add_argument("--plan-file", required=True)
    emit_handoff.add_argument("--index-file", required=True)
    emit_handoff.add_argument("--source-file", required=True)
    emit_handoff.add_argument("--out-file", required=True)
    emit_handoff.add_argument("--pretty", action="store_true")
    emit_handoff.set_defaults(func=_cmd_emit_handoff)

    verify_handoff = sub.add_parser(
        "verify-handoff",
        help="compare migration inputs with a previously emitted handoff",
    )
    verify_handoff.add_argument("--handoff-file", required=True)
    verify_handoff.add_argument("--plan-file", required=True)
    verify_handoff.add_argument("--index-file", required=True)
    verify_handoff.add_argument("--source-file", required=True)
    verify_handoff.add_argument("--pretty", action="store_true")
    verify_handoff.set_defaults(func=_cmd_verify_handoff)

    coverage_report = sub.add_parser("coverage-report")
    coverage_report.add_argument("--plan-file", required=True)
    coverage_report.add_argument("--index-file", required=True)
    coverage_report.add_argument("--pretty", action="store_true")
    coverage_report.set_defaults(func=_cmd_coverage_report)

    progress = sub.add_parser("update-progress")
    progress.add_argument("--progress-file", required=True)
    progress.add_argument("--chunk-id", required=True)
    progress.add_argument("--status", required=True, choices=["pending", "in_progress", "completed", "failed"])
    progress.add_argument("--note")
    progress.add_argument("--artifact", action="append", default=[])
    progress.add_argument("--pretty", action="store_true")
    progress.set_defaults(func=_cmd_update_progress)

    batch_progress = sub.add_parser(
        "update-batch-progress",
        help="atomically update every chunk owned by one migration batch",
    )
    batch_progress.add_argument("--progress-file", required=True)
    batch_progress.add_argument("--batch-id", required=True)
    batch_progress.add_argument("--status", required=True, choices=["pending", "in_progress", "completed", "failed"])
    batch_progress.add_argument("--note")
    batch_progress.add_argument("--artifact", action="append", default=[])
    batch_progress.add_argument("--pretty", action="store_true")
    batch_progress.set_defaults(func=_cmd_update_batch_progress)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
