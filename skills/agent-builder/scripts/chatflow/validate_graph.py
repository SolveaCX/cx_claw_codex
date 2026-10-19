#!/usr/bin/env python3
"""chatFlowGraph 结构校验工具。

提供 validate_graph(graph) 函数与 CLI（用于在提交 chatflow 前自检）：

  python3 /skills/agent-builder/scripts/chatflow/validate_graph.py --data-file graph.json
"""

import argparse
import ast
import builtins
import json
import keyword
import os
import re
import sys

_solvea_lib_dir = os.environ.get("SOLVEA_LIB_DIR")
if not _solvea_lib_dir:
    cur = os.path.abspath(os.path.dirname(__file__))
    while True:
        candidate = os.path.join(cur, "__lib__")
        if os.path.isdir(candidate):
            _solvea_lib_dir = candidate
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            raise RuntimeError("Cannot locate skills __lib__")
        cur = parent
sys.path.insert(0, os.path.join(_solvea_lib_dir, "skill-runtime"))
from bootstrap import *  # noqa: E402,F401,F403

PARAM_NAME_REG = re.compile(r"^(?!\d)[A-Za-z0-9_-]{1,64}$")
NEXT_STEP_TITLE_REG = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
CODE_FIELD_NAME_REG = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CODE_RESERVED_NAMES = set(keyword.kwlist) | set(dir(builtins))
CODE_ALLOWED_IMPORTS = {"math", "json", "datetime", "re"}
CODE_DANGEROUS_CALLS = {
    "eval", "exec", "compile", "__import__", "input", "globals", "locals",
    "vars", "dir", "getattr", "setattr", "delattr", "open", "breakpoint", "type",
}
CODE_DANGEROUS_ATTRS = {"sys", "_sys", "codecs", "builtins", "bltns", "_os"}
CODE_DANGEROUS_STRING_PATTERNS = {
    "__class__", "__mro__", "__bases__", "__subclasses__", "__globals__",
    "__dict__", "__builtins__", "__import__",
}
LIBRARY_BLOCK_REG = re.compile(r"\{#LibraryBlock\s+(.+?)\s*#\}")
LIBRARY_BLOCK_ATTR_REG = re.compile(r"(?:^|\s+)([A-Za-z_]\w*)=")


def _parse_library_block_fields(raw_fields):
    matches = list(LIBRARY_BLOCK_ATTR_REG.finditer(raw_fields))
    if not matches or raw_fields[:matches[0].start()].strip():
        raise ValueError("invalid attributes; expected key=value")
    fields = {}
    for index, match in enumerate(matches):
        key = match.group(1)
        if not key or key in fields:
            raise ValueError(f"invalid or duplicate attribute '{key}'")
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_fields)
        value = raw_fields[match.end():value_end].strip()
        if value.startswith('"') or value.endswith('"'):
            if len(value) < 2 or not (value.startswith('"') and value.endswith('"')):
                raise ValueError(f"invalid quoted attribute '{key}'")
            value = value[1:-1]
        fields[key] = value
    return fields


def _parse_library_blocks(text):
    if not text:
        return []
    if not isinstance(text, str):
        raise ValueError("prompt must be a string")
    matches = list(LIBRARY_BLOCK_REG.finditer(text))
    if text.count("{#LibraryBlock") != len(matches):
        raise ValueError("incomplete LibraryBlock")
    blocks = []
    for match in matches:
        fields = _parse_library_block_fields(match.group(1))
        block_type = fields.get("type")
        if block_type == "variable":
            if not {"id", "type", "name"}.issubset(fields):
                raise ValueError("variable block requires id/type/name")
            if not fields["id"].isdigit() or int(fields["id"]) <= 0 or not fields["name"]:
                raise ValueError("variable block requires a positive id and non-empty name")
        elif block_type == "tool":
            if not {"id", "type", "name", "tool"}.issubset(fields):
                raise ValueError("tool block requires id/type/name/tool")
            if not fields["id"].isdigit() or int(fields["id"]) <= 0:
                raise ValueError("tool block requires a positive id")
            if not fields["name"] or not fields["tool"]:
                raise ValueError("tool block requires non-empty name and tool")
        elif block_type == "transferHuman":
            if not {"tool_id", "type", "name"}.issubset(fields):
                raise ValueError("transferHuman block requires tool_id/type/name")
            if not fields["tool_id"].isdigit() or int(fields["tool_id"]) <= 0:
                raise ValueError("transferHuman block requires a positive numeric tool_id")
            if not fields["name"]:
                raise ValueError("transferHuman block requires a non-empty name")
            if fields.get("action") and fields["action"] not in {
                "NOT_REPLY", "CUSTOM_REPLY", "TEMPLATE_REPLY",
            }:
                raise ValueError("transferHuman block has an unsupported action")
            if fields.get("templateId") and (
                not fields["templateId"].isdigit() or int(fields["templateId"]) <= 0
            ):
                raise ValueError("transferHuman block templateId must be a positive integer")
        else:
            raise ValueError(f"unsupported block type '{block_type}'")
        blocks.append({"type": block_type, "fields": fields, "raw": match.group(0)})
    return blocks


def _format_library_blocks(text, blocks):
    by_raw = {block["raw"]: block for block in blocks}

    def replace(match):
        block = by_raw[match.group(0)]
        fields = block["fields"]
        if block["type"] == "variable":
            return f" {fields['name']} "
        if block["type"] == "tool":
            if fields["tool"] == "template_reply":
                return f" template_reply tool (template id: {fields['id']})"
            return f"{fields['name']} tool "
        return f" Transfer_To_Agent (reason: {fields['name']}) "

    return LIBRARY_BLOCK_REG.sub(replace, text)


def _collapse_prompt_whitespace(value):
    if not isinstance(value, str):
        return value
    return re.sub(r"\s+", " ", value).strip()


def _normalize_template_items(value):
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("list", "records", "items", "data"):
            child = value.get(key)
            if isinstance(child, (list, dict)):
                return _normalize_template_items(child)
    return []


def _is_note_node(node):
    data = node.get("data", {}) or {}
    return node.get("type") == "CUSTOM_NOTE" or data.get("category") == "NOTE"


def _detect_cycle(nodes, edges):
    """DFS 三色法检测有向图中的环。返回找到的环路径（节点 id 列表），无环返回 None。"""
    adj = {}
    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src and tgt:
            adj.setdefault(src, []).append(tgt)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n["id"]: WHITE for n in nodes}
    parent = {}
    found = []

    def dfs(u):
        color[u] = GRAY
        for v in adj.get(u, []):
            if v not in color:
                continue  # 边指向不存在节点的情况由其他规则报错
            if color[v] == GRAY:
                # 反向边 → 环。从 u 沿 parent 回溯到 v 还原路径。
                path = [v]
                cur = u
                while cur != v:
                    path.append(cur)
                    if cur not in parent:
                        break
                    cur = parent[cur]
                path.append(v)
                path.reverse()
                found.append(path)
                return True
            if color[v] == WHITE:
                parent[v] = u
                if dfs(v):
                    return True
        color[u] = BLACK
        return False

    for nid in list(color):
        if color[nid] == WHITE:
            if dfs(nid):
                return found[0]
    return None


def _code_all_paths_return(stmts):
    for node in stmts:
        if isinstance(node, ast.Return):
            return True
        if isinstance(node, ast.If):
            if node.orelse and _code_all_paths_return(node.body) and _code_all_paths_return(node.orelse):
                return True
        elif isinstance(node, ast.Try) or (hasattr(ast, "TryStar") and isinstance(node, ast.TryStar)):
            if node.finalbody and _code_all_paths_return(node.finalbody):
                return True
            if node.handlers and _code_all_paths_return(node.body) and all(_code_all_paths_return(h.body) for h in node.handlers):
                return True
        elif isinstance(node, ast.With):
            if _code_all_paths_return(node.body):
                return True
        elif hasattr(ast, "Match") and isinstance(node, ast.Match):
            has_wildcard = any(isinstance(c.pattern, ast.MatchAs) and c.pattern.pattern is None for c in node.cases)
            if has_wildcard and all(_code_all_paths_return(c.body) for c in node.cases):
                return True
    return False


def _validate_code_source(code, title):
    errors = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"CODE '{title}' syntax error at line {e.lineno}: {e.msg}"]

    if not _code_all_paths_return(tree.body):
        errors.append(f"CODE '{title}' must return a value on all execution paths")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_root = alias.name.split(".")[0]
                if module_root not in CODE_ALLOWED_IMPORTS:
                    errors.append(f"CODE '{title}' import of '{alias.name}' is not allowed")
        elif isinstance(node, ast.ImportFrom):
            if not node.module:
                errors.append(f"CODE '{title}' relative imports are not allowed")
            else:
                module_root = node.module.split(".")[0]
                if module_root not in CODE_ALLOWED_IMPORTS:
                    errors.append(f"CODE '{title}' import from '{node.module}' is not allowed")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                errors.append(f"CODE '{title}' access to dunder attribute '{node.attr}' is not allowed")
            elif node.attr in CODE_DANGEROUS_ATTRS:
                errors.append(f"CODE '{title}' access to attribute '{node.attr}' is not allowed")
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") and node.id.endswith("__"):
                errors.append(f"CODE '{title}' use of dunder name '{node.id}' is not allowed")
            elif node.id == "type":
                errors.append(f"CODE '{title}' use of 'type' is not allowed")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for pattern in CODE_DANGEROUS_STRING_PATTERNS:
                if pattern in node.value:
                    errors.append(f"CODE '{title}' string pattern '{pattern}' is not allowed")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in CODE_DANGEROUS_CALLS:
                errors.append(f"CODE '{title}' call to '{node.func.id}()' is not allowed")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in {"eval", "exec"}:
                errors.append(f"CODE '{title}' call to method '{node.func.attr}()' is not allowed")
        elif isinstance(node, (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith)):
            errors.append(f"CODE '{title}' async constructs are not allowed")
        elif isinstance(node, (ast.Yield, ast.YieldFrom)):
            errors.append(f"CODE '{title}' yield/generator constructs are not allowed")
        elif isinstance(node, ast.ClassDef):
            errors.append(f"CODE '{title}' class definitions are not allowed")
    return errors


def validate_graph(graph, ai_fields=None, plugins=None, agent_ai_fields=None, templates=None):
    """Validate a chatFlowGraph structure before submitting.

    Returns: {"valid": bool, "errors": [...], "warnings": [...], "stats": {...}}
    """
    errors = []
    warnings = []

    valid_system_selectors = None
    valid_ai_field_ids = None
    templates_by_id = None
    if templates is not None:
        templates_by_id = {
            str(item.get("id") or item.get("templateId")): item
            for item in _normalize_template_items(templates)
            if item.get("id") is not None or item.get("templateId") is not None
        }
    if isinstance(ai_fields, list):
        valid_system_selectors = set()
        valid_ai_field_ids = set()

        def add_ai_field(field, category, parent_path=None):
            if not isinstance(field, dict) or field.get("id") is None:
                return
            path = [*(parent_path or []), field["id"]]
            valid_system_selectors.add(tuple(["SYSTEM", category, *path]))
            valid_ai_field_ids.add(field["id"])
            for child in field.get("children") or []:
                add_ai_field(child, category, path)

        for field in ai_fields:
            if isinstance(field, dict):
                add_ai_field(field, field.get("bizType", "Custom"))

    valid_agent_ai_field_ids = valid_ai_field_ids
    if isinstance(agent_ai_fields, list):
        valid_agent_ai_field_ids = set()

        def add_agent_ai_field(field):
            if not isinstance(field, dict) or field.get("id") is None:
                return
            valid_agent_ai_field_ids.add(field["id"])
            for child in field.get("children") or []:
                add_agent_ai_field(child)

        for field in agent_ai_fields:
            add_agent_ai_field(field)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    edge_ids = set()
    required_edge_fields = ("id", "source", "sourceHandle", "target", "targetHandle", "type")
    for edge_idx, edge_item in enumerate(edges):
        if not isinstance(edge_item, dict):
            errors.append(f"edge[{edge_idx}] must be an object")
            continue
        for field in required_edge_fields:
            field_value = edge_item.get(field)
            if field_value is None or (isinstance(field_value, str) and not field_value.strip()):
                errors.append(f"edge[{edge_idx}] missing {field}")
        edge_id = edge_item.get("id")
        if edge_id is not None and (not isinstance(edge_id, str) or edge_id.strip()):
            if edge_id in edge_ids:
                errors.append(f"duplicate edge id '{edge_id}'")
            edge_ids.add(edge_id)
        edge_type = edge_item.get("type")
        if edge_type is not None and (not isinstance(edge_type, str) or edge_type.strip()) and edge_type != "default":
            errors.append(f"edge[{edge_idx}] unsupported type '{edge_type}'; expected 'default'")

    node_ids = {n["id"] for n in nodes}
    note_node_ids = {n["id"] for n in nodes if _is_note_node(n)}
    runtime_nodes = [n for n in nodes if n["id"] not in note_node_ids]
    runtime_edges = [
        e for e in edges
        if isinstance(e, dict)
        and e.get("source")
        and e.get("target")
        and e.get("source") not in note_node_ids
        and e.get("target") not in note_node_ids
    ]
    runtime_node_ids = {n["id"] for n in runtime_nodes}
    runtime_node_map = {n["id"]: n for n in runtime_nodes}

    plugin_metadata_available = plugins is not None
    plugins_by_id = {}
    for plugin in plugins or []:
        if isinstance(plugin, dict) and plugin.get("id") is not None:
            plugins_by_id[str(plugin["id"])] = plugin

    tool_output_paths_by_node = {}
    for node in runtime_nodes:
        if node.get("data", {}).get("category") != "TOOL":
            continue
        tool = node.get("data", {}).get("config", {}).get("tool") or {}
        plugin = plugins_by_id.get(str(tool.get("id")))
        if not plugin:
            continue
        response_items = []
        for plugin_config in (plugin.get("meta") or {}).values():
            if isinstance(plugin_config, dict):
                items = (plugin_config.get("responseParam") or {}).get("items")
                if isinstance(items, list):
                    response_items = items
                    break

        valid_paths = set()

        def add_tool_paths(items, parent_path=()):
            for item in items or []:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                path = (*parent_path, item["name"])
                valid_paths.add(path)
                # Keep arrays as leaves to match aiFlowV2 processToolParamItems.
                if item.get("type") == "object":
                    add_tool_paths(item.get("objectItems") or [], path)

        add_tool_paths(response_items)
        tool_output_paths_by_node[node["id"]] = valid_paths

    def is_blank(value):
        return value is None or (isinstance(value, str) and not value.strip())

    # 1. Must have nodes
    if not nodes:
        errors.append("Graph has no nodes")
        return {"valid": False, "errors": errors, "warnings": warnings}

    # 2. Must have exactly one START node
    start_nodes = [n for n in runtime_nodes if n.get("data", {}).get("category") == "START"]
    if len(start_nodes) == 0:
        errors.append("Missing START node")
    elif len(start_nodes) > 1:
        errors.append(f"Multiple START nodes found: {[n['id'] for n in start_nodes]}")

    # 3. All edge source/target must reference existing nodes
    for edge_idx, e in enumerate(edges):
        if not isinstance(e, dict):
            continue
        edge_label = e.get("id") or f"edge[{edge_idx}]"
        if e.get("source") not in node_ids:
            errors.append(f"Edge {edge_label}: source '{e.get('source')}' not in nodes")
        if e.get("target") not in node_ids:
            errors.append(f"Edge {edge_label}: target '{e.get('target')}' not in nodes")

    # 4. START must have outgoing edge
    if start_nodes:
        start_id = start_nodes[0]["id"]
        start_out = [e for e in runtime_edges if e.get("source") == start_id]
        if not start_out:
            errors.append(f"START node '{start_id}' has no outgoing edge")

    # 5. Check for orphan nodes (not reachable from START)
    if start_nodes and runtime_edges:
        reachable = set()
        queue = [start_nodes[0]["id"]]
        while queue:
            nid = queue.pop(0)
            if nid in reachable:
                continue
            reachable.add(nid)
            for e in runtime_edges:
                if e.get("source") == nid and e.get("target") not in reachable:
                    queue.append(e["target"])
        orphans = runtime_node_ids - reachable
        if orphans:
            orphan_info = [f"{oid}({runtime_node_map[oid].get('data', {}).get('category', '')})"
                           for oid in orphans]
            errors.append(f"Orphan nodes not reachable from START: {orphan_info}")

    # 6. Non-START/FINISH nodes should have incoming edges
    for n in runtime_nodes:
        cat = n.get("data", {}).get("category", "")
        if cat == "START":
            continue
        incoming = [e for e in runtime_edges if e.get("target") == n["id"]]
        if not incoming:
            warnings.append(f"Node '{n['id']}' ({cat}) has no incoming edge")

    # 7. AGENT nodes must keep both UI displayPrompt and runtime prompt.
    for n in runtime_nodes:
        cat = n.get("data", {}).get("category", "")
        if cat == "AGENT":
            config = n.get("data", {}).get("config", {})
            agent_data = config.get("agentData", {})
            if not agent_data.get("prompt"):
                errors.append(f"AGENT node '{n['id']}' has empty prompt")
            if not agent_data.get("displayPrompt"):
                errors.append(f"AGENT node '{n['id']}' has empty displayPrompt")

    # 8. Node titles must not be empty (except START)
    for n in runtime_nodes:
        cat = n.get("data", {}).get("category", "")
        if cat in ("START",):
            continue
        title = n.get("data", {}).get("title", "")
        if is_blank(title):
            errors.append(f"Node '{n['id']}' ({cat}) has empty title")

    # 9. Check duplicate titles
    titles = [n.get("data", {}).get("title", "") for n in runtime_nodes
              if n.get("data", {}).get("category") not in ("START",) and n.get("data", {}).get("title")]
    seen = set()
    for t in titles:
        if t in seen:
            errors.append(f"Duplicate node title: '{t}'")
        seen.add(t)

    # 10. Frontend connection-completeness rules (align with aiFlowV2 useCheckFlow).
    # Some handles are implicit UI handles and are not present in node config as normal branches.
    # If they are not connected, the frontend shows "当前节点未连接完全" and runtime fallback routes dead-end.
    def title_of(node):
        return node.get("data", {}).get("title") or node["id"]

    def validate_template_reference(template_id, owner):
        if not template_id or templates_by_id is None:
            return
        template = templates_by_id.get(str(template_id))
        if template is None:
            errors.append(f"{owner} references unknown template id {template_id}")
            return
        status = str(template.get("status") or "").upper()
        if status != "ENABLED":
            errors.append(
                f"{owner} references template id {template_id} with status "
                f"{status or 'UNKNOWN'}; expected ENABLED"
            )

    incoming_by_node = {}
    outgoing_by_node = {}
    handles_by_node = {}
    for e in runtime_edges:
        incoming_by_node.setdefault(e.get("target"), []).append(e)
        outgoing_by_node.setdefault(e.get("source"), []).append(e)
        if e.get("source"):
            handles_by_node.setdefault(e.get("source"), set()).add(e.get("sourceHandle"))

    def has_incoming(node):
        return bool(incoming_by_node.get(node["id"]))

    def has_outgoing(node):
        return bool(outgoing_by_node.get(node["id"]))

    def require_incoming(node):
        if not has_incoming(node):
            errors.append(f"{node.get('data', {}).get('category')} '{title_of(node)}' has no incoming edge")

    def require_outgoing(node):
        if not has_outgoing(node):
            errors.append(f"{node.get('data', {}).get('category')} '{title_of(node)}' has no outgoing edge")

    def require_handles(node, handles):
        actual = handles_by_node.get(node["id"], set())
        cat = node.get("data", {}).get("category")
        title = title_of(node)
        for handle in handles:
            if handle and handle not in actual:
                errors.append(f"{cat} '{title}' missing {handle} edge")

    extract_ids_by_node = {}
    code_outputs_by_node = {}
    agent_params_by_node = {}
    agent_params_by_step_by_node = {}
    human_review_fields_by_node = {}
    for n in runtime_nodes:
        cat = n.get("data", {}).get("category")
        cfg = n.get("data", {}).get("config", {}) or {}
        if cat == "VARIABLE_PROCESS":
            extracts = (cfg.get("variableProcess") or {}).get("extracts") or []
            extract_ids_by_node[n["id"]] = {item.get("id") for item in extracts if item.get("id")}
        elif cat == "VARIABLE_EXTRACT":
            extracts = (cfg.get("variableExtract") or {}).get("extracts") or []
            extract_ids_by_node[n["id"]] = {item.get("id") for item in extracts if item.get("id")}
        elif cat == "CODE":
            outputs = (cfg.get("code") or {}).get("outputs") or []
            code_outputs_by_node[n["id"]] = {item.get("fieldName") for item in outputs if item.get("fieldName")}
        elif cat == "AGENT":
            params = set()
            params_by_step = {}
            for step in cfg.get("nextStep") or []:
                step_params = set()
                for param in step.get("params") or []:
                    if param.get("name"):
                        params.add(param["name"])
                        step_params.add(param["name"])
                if step.get("id"):
                    params_by_step[step["id"]] = step_params
            agent_params_by_node[n["id"]] = params
            agent_params_by_step_by_node[n["id"]] = params_by_step
        elif cat == "HUMAN_REVIEW":
            human_review = cfg.get("humanReview") or cfg.get("humanInLoop") or {}
            fields = human_review.get("fields") or []
            human_review_fields_by_node[n["id"]] = {item.get("id") for item in fields if item.get("id")}

    llm_structured_output_by_node = {}
    for n in runtime_nodes:
        if n.get("data", {}).get("category") != "LLM":
            continue
        llm_cfg = (n.get("data", {}).get("config", {}) or {}).get("llm") or {}
        structured_output = llm_cfg.get("structuredOutput") or {}
        llm_structured_output_by_node[n["id"]] = structured_output

    def is_predecessor(source_id, current_id):
        if not source_id or not current_id or source_id == current_id:
            return False
        queue = [source_id]
        seen = set()
        while queue:
            nid = queue.pop(0)
            if nid == current_id:
                return True
            if nid in seen:
                continue
            seen.add(nid)
            for edge_item in outgoing_by_node.get(nid, []):
                target = edge_item.get("target")
                if target and target not in seen:
                    queue.append(target)
        return False

    def connected_agent_step_ids(agent_node_id, current_node_id):
        connected = set()
        visited = set()

        def dfs(node_id):
            if node_id in visited:
                return
            visited.add(node_id)
            for edge_item in incoming_by_node.get(node_id, []):
                source = edge_item.get("source")
                if source == agent_node_id and edge_item.get("sourceHandle"):
                    connected.add(edge_item.get("sourceHandle"))
                elif source:
                    dfs(source)

        if current_node_id:
            dfs(current_node_id)
        return connected

    def validate_selector(selector, owner, field, current_node_id=None,
                          allow_self=False, self_extract_ids=None,
                          allow_node=False, system_only=False,
                          allow_tool_status=False):
        if not selector:
            return []
        if not isinstance(selector, list):
            return [f"{owner} {field} must be a variable selector array"]
        first = selector[0] if selector else None
        if system_only and first != "SYSTEM":
            return [f"{owner} {field} must target SYSTEM variable"]

        def check_source_node(node_id, expected_categories, label):
            ref = runtime_node_map.get(node_id)
            if not ref:
                return [f"{owner} {field} references missing {label} node '{node_id}'"]
            ref_cat = ref.get("data", {}).get("category")
            if expected_categories is not None:
                expected = {expected_categories} if isinstance(expected_categories, str) else set(expected_categories)
            else:
                expected = None
            if expected is not None and ref_cat not in expected:
                return [f"{owner} {field} references {label} node '{node_id}' with category '{ref_cat}'"]
            if current_node_id and not is_predecessor(node_id, current_node_id):
                return [f"{owner} {field} references non-predecessor {label} node '{node_id}'"]
            return []

        if first == "SYSTEM":
            if len(selector) < 3:
                return [f"{owner} {field} SYSTEM selector must include category and field path"]
            if valid_system_selectors is not None and tuple(selector) not in valid_system_selectors:
                return [f"{owner} {field} references invalid SYSTEM field path {selector}"]
            return []

        if first == "TOOL":
            if len(selector) < 3:
                return [f"{owner} {field} TOOL selector must include node id and output path"]
            if "ACTION_STATUS_NAME" in selector and not allow_tool_status:
                return [f"{owner} {field} does not allow TOOL action status selector"]
            source_errors = check_source_node(selector[1], "TOOL", "TOOL")
            if source_errors:
                return source_errors
            if selector[2:] == ["ACTION_STATUS_NAME"]:
                return []
            if any(isinstance(segment, str) and "." in segment for segment in selector[2:]):
                return [
                    f"{owner} {field} references invalid TOOL output path {selector[2:]}; "
                    "nested fields must use separate path segments"
                ]
            valid_paths = tool_output_paths_by_node.get(selector[1])
            if valid_paths is not None and tuple(selector[2:]) not in valid_paths:
                return [f"{owner} {field} references invalid TOOL output path {selector[2:]}"]
            return []

        if first == "NODE":
            if not allow_node:
                return [f"{owner} {field} does not allow NODE output selector"]
            if len(selector) != 2:
                return [f"{owner} {field} NODE selector must have 2 elements"]
            return check_source_node(selector[1], None, "NODE")

        if first == "EXTRACT":
            if len(selector) != 3:
                return [f"{owner} {field} EXTRACT selector must have 3 elements"]
            node_id = selector[1]
            selector_errors = check_source_node(node_id, {"VARIABLE_EXTRACT", "VARIABLE_PROCESS"}, "EXTRACT")
            if selector_errors:
                return selector_errors
            extract_id = selector[2]
            if extract_id not in extract_ids_by_node.get(node_id, set()):
                return [f"{owner} {field} references unknown EXTRACT id '{extract_id}' on node '{node_id}'"]
            return []

        if first == "CODE":
            if len(selector) not in (2, 3):
                return [f"{owner} {field} CODE selector must have 2 or 3 elements"]
            node_id = selector[1]
            selector_errors = check_source_node(node_id, "CODE", "CODE")
            if selector_errors:
                return selector_errors
            if len(selector) == 3 and selector[2] not in code_outputs_by_node.get(node_id, set()):
                return [f"{owner} {field} references unknown CODE output '{selector[2]}' on node '{node_id}'"]
            return []

        if first == "AGENT":
            if len(selector) != 3:
                return [f"{owner} {field} AGENT selector must have 3 elements"]
            node_id = selector[1]
            selector_errors = check_source_node(node_id, "AGENT", "AGENT")
            if selector_errors:
                return selector_errors
            if selector[2] not in agent_params_by_node.get(node_id, set()):
                return [f"{owner} {field} references unknown AGENT param '{selector[2]}' on node '{node_id}'"]
            if current_node_id and agent_params_by_step_by_node.get(node_id):
                connected_steps = connected_agent_step_ids(node_id, current_node_id)
                params_on_connected_steps = set()
                for step_id in connected_steps:
                    params_on_connected_steps.update(agent_params_by_step_by_node.get(node_id, {}).get(step_id, set()))
                if selector[2] not in params_on_connected_steps:
                    return [
                        f"{owner} {field} references AGENT param '{selector[2]}' that is not available on the connected nextStep path"
                    ]
            return []

        if first == "LLM":
            if len(selector) < 3:
                return [f"{owner} {field} LLM selector must have at least 3 elements"]
            node_id = selector[1]
            selector_errors = check_source_node(node_id, "LLM", "LLM")
            if selector_errors:
                return selector_errors
            output_field = selector[2]
            if output_field == "text":
                if len(selector) != 3:
                    return [f"{owner} {field} LLM text selector must have exactly 3 elements"]
                return []
            if output_field != "structured_output":
                return [
                    f"{owner} {field} LLM selector must use 'text' or 'structured_output', got {output_field!r}"
                ]
            structured_output = llm_structured_output_by_node.get(node_id) or {}
            if not structured_output.get("enabled"):
                return [
                    f"{owner} {field} references LLM structured_output on node '{node_id}' but structuredOutput is disabled"
                ]
            schema = structured_output.get("schema") or {}
            nested_path = selector[3:]
            if nested_path:
                if not isinstance(nested_path[0], str):
                    return [f"{owner} {field} LLM structured_output root path must be a string"]
                if any(isinstance(segment, bool) or not isinstance(segment, (str, int)) for segment in nested_path):
                    return [f"{owner} {field} LLM structured_output path segments must be strings or integers"]
                properties = schema.get("properties") if isinstance(schema, dict) else None
                if isinstance(properties, dict) and nested_path[0] not in properties:
                    return [
                        f"{owner} {field} references unknown LLM structured_output field '{nested_path[0]}' on node '{node_id}'"
                    ]
            return []

        if first == "HUMAN_REVIEW":
            if len(selector) not in (2, 3):
                return [f"{owner} {field} HUMAN_REVIEW selector must have 2 or 3 elements"]
            node_id = selector[1]
            selector_errors = check_source_node(node_id, "HUMAN_REVIEW", "HUMAN_REVIEW")
            if selector_errors:
                return selector_errors
            if len(selector) == 3 and selector[2] not in human_review_fields_by_node.get(node_id, set()):
                return [f"{owner} {field} references unknown HUMAN_REVIEW field '{selector[2]}' on node '{node_id}'"]
            return []

        if first == "SELF":
            if not allow_self:
                return [f"{owner} {field} does not allow SELF selector"]
            if len(selector) != 2:
                return [f"{owner} {field} SELF selector must have 2 elements"]
            if selector[1] not in (self_extract_ids or set()):
                return [f"{owner} {field} references unknown SELF extract id '{selector[1]}'"]
            return []

        return [f"{owner} {field} has unknown selector type '{first}'"]

    def validate_selector_templates(text, owner, field, current_node_id=None,
                                    allow_tool_status=False, allow_node=False):
        if not text:
            return []
        if not isinstance(text, str):
            return [f"{owner} {field} must be a string"]

        selector_errors = []
        prefix = "[[var:"
        suffix = "]]"
        decoder = json.JSONDecoder()
        cursor = 0
        while True:
            start = text.find(prefix, cursor)
            if start < 0:
                break
            json_start = start + len(prefix)
            try:
                selector, json_end = decoder.raw_decode(text, json_start)
            except json.JSONDecodeError:
                selector_errors.append(f"{owner} {field} has invalid variable template JSON")
                break
            if not text.startswith(suffix, json_end):
                selector_errors.append(f"{owner} {field} has a variable template without closing ']]'")
                break
            selector_errors.extend(
                validate_selector(
                    selector,
                    owner,
                    field,
                    current_node_id=current_node_id,
                    allow_tool_status=allow_tool_status,
                    allow_node=allow_node,
                )
            )
            cursor = json_end + len(suffix)
        return selector_errors

    def reject_selector_templates(text, owner, field):
        if not text or not re.search(r"\[\[var:\[[\s\S]*?\]\]\]", text):
            return []
        return [
            f"{owner} {field} does not support [[var:...]] templates; "
            "use aiFieldIds for variable-system prompt fields"
        ]

    def validate_tool_input_params(input_params, owner, current_node_id):
        selector_errors = []
        for idx, param in enumerate(input_params or []):
            field_name = f"inputParams[{idx}].variableSelector"
            if param.get("variableSelector"):
                selector_errors.extend(
                    validate_selector(param.get("variableSelector"), owner, field_name, current_node_id=current_node_id)
                )
            selector_errors.extend(validate_tool_input_params(param.get("children") or [], owner, current_node_id))
        return selector_errors

    def find_missing_tool_params(request_items, input_params, parent_path=""):
        missing = []
        for request_item in request_items or []:
            if request_item.get("required") is False:
                continue
            name = request_item.get("name")
            if not name:
                continue
            path = f"{parent_path}.{name}" if parent_path else name
            matched = next(
                (param for param in input_params or [] if param.get("name") == name),
                None,
            )
            if not matched:
                missing.append(path)
                continue
            is_object = (
                matched.get("varType") == "object"
                or request_item.get("type") == "object"
                or request_item.get("typeEnum") == "ObjectType"
            )
            if is_object:
                request_children = request_item.get("objectItems") or []
                input_children = matched.get("children") or matched.get("objectItems") or []
                missing.extend(find_missing_tool_params(request_children, input_children, path))
            elif not (matched.get("text") or matched.get("variableSelector")):
                missing.append(path)
        return missing

    for n in runtime_nodes:
        cat = n.get("data", {}).get("category", "")
        cfg = n.get("data", {}).get("config", {})

        if cat == "FINISH":
            require_incoming(n)

        if cat in {"REPLY", "TRANSFER_TO_HUMAN", "CODE", "SUB_GRAPH"}:
            require_incoming(n)

        if cat in {
            "BUSINESS_TRACK", "COLLECT_ORDER", "TOOL", "VARIABLE_ASSIGNMENT",
            "VARIABLE_EXTRACT", "VARIABLE_PROCESS", "LLM",
        }:
            require_incoming(n)
            require_outgoing(n)

        if cat == "REPLY":
            reply_content = cfg.get("replyContent") or {}
            reply_type = reply_content.get("type") or "PROMPT"
            if reply_type == "TEMPLATE":
                if not reply_content.get("templateId"):
                    errors.append(f"REPLY '{title_of(n)}' missing templateId")
                else:
                    validate_template_reference(
                        reply_content.get("templateId"), f"REPLY '{title_of(n)}'"
                    )
                if reply_content.get("aiFieldIds"):
                    errors.append(f"REPLY '{title_of(n)}' TEMPLATE does not use aiFieldIds")
            elif reply_type == "PROMPT":
                if is_blank(reply_content.get("prompt")):
                    errors.append(f"REPLY '{title_of(n)}' missing prompt")
                for idx, field_id in enumerate(reply_content.get("aiFieldIds") or []):
                    if isinstance(field_id, bool) or not isinstance(field_id, int):
                        errors.append(
                            f"REPLY '{title_of(n)}' aiFieldIds[{idx}] must be an integer field id"
                        )
                errors.extend(
                    reject_selector_templates(
                        reply_content.get("prompt"),
                        f"REPLY '{title_of(n)}'",
                        "replyContent.prompt",
                    )
                )
            elif reply_type == "DYNAMIC_TEMPLATE":
                template_content = reply_content.get("templateContent")
                if is_blank(template_content):
                    errors.append(f"REPLY '{title_of(n)}' missing templateContent")
                else:
                    errors.extend(
                        validate_selector_templates(
                            template_content,
                            f"REPLY '{title_of(n)}'",
                            "replyContent.templateContent",
                            current_node_id=n["id"],
                            allow_tool_status=True,
                            allow_node=True,
                        )
                    )
                if reply_content.get("aiFieldIds"):
                    errors.append(
                        f"REPLY '{title_of(n)}' DYNAMIC_TEMPLATE does not use aiFieldIds"
                    )
            else:
                errors.append(f"REPLY '{title_of(n)}' has unsupported type '{reply_type}'")

        if cat == "TRANSFER_TO_HUMAN":
            transfer_to_human = cfg.get("transferToHuman") or {}
            transfer_type = transfer_to_human.get("type") or "PROMPT"
            if transfer_type == "TEMPLATE":
                if not transfer_to_human.get("templateId"):
                    errors.append(f"TRANSFER_TO_HUMAN '{title_of(n)}' missing templateId")
                else:
                    validate_template_reference(
                        transfer_to_human.get("templateId"),
                        f"TRANSFER_TO_HUMAN '{title_of(n)}'",
                    )
            elif transfer_type == "PROMPT":
                if is_blank(transfer_to_human.get("prompt")):
                    errors.append(f"TRANSFER_TO_HUMAN '{title_of(n)}' missing prompt")
                for idx, field_id in enumerate(transfer_to_human.get("aiFieldIds") or []):
                    if isinstance(field_id, bool) or not isinstance(field_id, int):
                        errors.append(
                            f"TRANSFER_TO_HUMAN '{title_of(n)}' aiFieldIds[{idx}] must be an integer field id"
                        )
                    elif valid_ai_field_ids is not None and field_id not in valid_ai_field_ids:
                        errors.append(
                            f"TRANSFER_TO_HUMAN '{title_of(n)}' aiFieldIds[{idx}] references unknown field id {field_id}"
                        )
            elif transfer_type != "NO_REPLY":
                errors.append(f"TRANSFER_TO_HUMAN '{title_of(n)}' has unsupported type '{transfer_type}'")
            if transfer_type != "PROMPT" and transfer_to_human.get("aiFieldIds"):
                errors.append(
                    f"TRANSFER_TO_HUMAN '{title_of(n)}' type {transfer_type} does not use aiFieldIds"
                )

        if cat == "COLLECT_ORDER":
            for idx, item in enumerate(cfg.get("collectOrderException") or []):
                item_type = item.get("type") or "REPLY"
                if item_type == "TEMPLATE":
                    if not item.get("templateId"):
                        errors.append(f"COLLECT_ORDER '{title_of(n)}' exception[{idx}] missing templateId")
                    else:
                        validate_template_reference(
                            item.get("templateId"),
                            f"COLLECT_ORDER '{title_of(n)}' exception[{idx}]",
                        )
                elif item_type != "REPLY":
                    errors.append(
                        f"COLLECT_ORDER '{title_of(n)}' exception[{idx}] has unsupported type '{item_type}'"
                    )
                elif is_blank(item.get("reply")):
                    errors.append(f"COLLECT_ORDER '{title_of(n)}' exception[{idx}] missing reply")

        if cat == "TOOL":
            tool = cfg.get("tool") or {}
            if tool.get("id") is None:
                errors.append(f"TOOL '{title_of(n)}' missing tool id")
            # Tool.type defaults to EXTERNAL_HTTP_CALL in the ChatFlow schema.
            # Existing graphs therefore legitimately omit it; reject only an
            # explicitly supplied invalid value.
            if "type" in tool and (
                not isinstance(tool.get("type"), str) or not tool.get("type").strip()
            ):
                errors.append(f"TOOL '{title_of(n)}' missing tool type")
            errors.extend(validate_tool_input_params(tool.get("inputParams") or [], f"TOOL '{title_of(n)}'", n["id"]))
            plugin = plugins_by_id.get(str(tool.get("id")))
            if plugin:
                request_items = []
                for plugin_config in (plugin.get("meta") or {}).values():
                    if isinstance(plugin_config, dict):
                        items = (plugin_config.get("requestParam") or {}).get("items")
                        if isinstance(items, list):
                            request_items = items
                            break
                for path in find_missing_tool_params(request_items, tool.get("inputParams") or []):
                    errors.append(f"TOOL '{title_of(n)}' required tool param '{path}' is not configured")

        if cat == "QUESTION":
            require_incoming(n)
            require_outgoing(n)
            collect_info = cfg.get("collectInfo", {})
            question_type = collect_info.get("questionType") or "PROMPT"
            collect_type = collect_info.get("type") or "VARIABLE"
            if question_type not in {"PROMPT", "TEMPLATE"}:
                errors.append(f"QUESTION '{title_of(n)}' has unsupported questionType '{question_type}'")
            elif question_type == "TEMPLATE":
                if not collect_info.get("questionTemplateId"):
                    errors.append(f"QUESTION '{title_of(n)}' missing questionTemplateId")
                else:
                    validate_template_reference(
                        collect_info.get("questionTemplateId"),
                        f"QUESTION '{title_of(n)}'",
                    )
            elif is_blank(collect_info.get("question")):
                errors.append(f"QUESTION '{title_of(n)}' missing question")
            variables = collect_info.get("variables") or []
            replies = collect_info.get("replies") or []
            if not variables and not replies:
                errors.append(f"QUESTION '{title_of(n)}' missing variables or replies")
            condition = collect_info.get("condition") or "AND"
            if condition not in {"AND", "OR"}:
                errors.append(f"QUESTION '{title_of(n)}' has unsupported condition '{condition}'")
            if collect_type not in {"VARIABLE", "USER_REPLY"}:
                errors.append(f"QUESTION '{title_of(n)}' has unsupported type '{collect_type}'")
            elif collect_type == "VARIABLE" and not variables:
                errors.append(f"QUESTION '{title_of(n)}' VARIABLE mode missing variables")
            if collect_type == "USER_REPLY":
                reply_names = []
                for idx, reply in enumerate(replies):
                    if not reply.get("id"):
                        errors.append(f"QUESTION '{title_of(n)}' reply[{idx}] missing id")
                    if is_blank(reply.get("name")):
                        errors.append(f"QUESTION '{title_of(n)}' reply[{idx}] missing name")
                    elif reply.get("name") in reply_names:
                        errors.append(f"QUESTION '{title_of(n)}' duplicate reply name '{reply.get('name')}'")
                    reply_names.append(reply.get("name"))
            if collect_type == "USER_REPLY":
                reply_handles = [r.get("id") for r in replies]
                require_handles(n, [*reply_handles, "OTHER"])

        if cat == "INTENT":
            require_incoming(n)
            require_outgoing(n)
            intent_handles = [i.get("id") for i in cfg.get("intents", [])]
            intent_names = []
            for idx, intent in enumerate(cfg.get("intents", []) or []):
                if not intent.get("id"):
                    errors.append(f"INTENT '{title_of(n)}' intent[{idx}] missing id")
                if not intent.get("intentId"):
                    if is_blank(intent.get("name")):
                        errors.append(f"INTENT '{title_of(n)}' intent[{idx}] missing name")
                    if is_blank(intent.get("desc")):
                        errors.append(f"INTENT '{title_of(n)}' intent[{idx}] missing desc")
                if not is_blank(intent.get("name")):
                    if intent.get("name") in intent_names:
                        errors.append(f"INTENT '{title_of(n)}' duplicate intent name '{intent.get('name')}'")
                    intent_names.append(intent.get("name"))
            require_handles(n, [*intent_handles, "OTHER"])

        if cat == "IF_ELSE":
            require_incoming(n)
            require_outgoing(n)
            cases = cfg.get("cases", []) or []
            if not cases:
                errors.append(f"IF_ELSE '{title_of(n)}' missing cases")
            case_handles = [case.get("id") for case in cases]
            for case_idx, case in enumerate(cases):
                if not case.get("id"):
                    errors.append(f"IF_ELSE '{title_of(n)}' case[{case_idx}] missing id")
                conditions = case.get("conditions") or []
                if not conditions:
                    errors.append(f"IF_ELSE '{title_of(n)}' case[{case_idx}] missing conditions")
                for cond_idx, cond in enumerate(conditions):
                    if not cond.get("variableSelector"):
                        errors.append(f"IF_ELSE '{title_of(n)}' case[{case_idx}].conditions[{cond_idx}] missing variableSelector")
                    else:
                        errors.extend(
                            validate_selector(
                                cond.get("variableSelector"),
                                f"IF_ELSE '{title_of(n)}'",
                                f"case[{case_idx}].conditions[{cond_idx}].variableSelector",
                                current_node_id=n["id"],
                                allow_tool_status=True,
                            )
                        )
                    if not cond.get("comparisonOperator"):
                        errors.append(f"IF_ELSE '{title_of(n)}' case[{case_idx}].conditions[{cond_idx}] missing comparisonOperator")
                    if cond.get("comparisonOperator") not in {"EMPTY", "NOT_EMPTY"}:
                        value = cond.get("value")
                        if value is None or value == "" or value == []:
                            errors.append(f"IF_ELSE '{title_of(n)}' case[{case_idx}].conditions[{cond_idx}] missing value")
                        elif (
                            str(cond.get("varType") or "").lower() == "boolean"
                            and (not isinstance(value, str) or value not in ("true", "false"))
                        ):
                            errors.append(
                                f"IF_ELSE '{title_of(n)}' case[{case_idx}].conditions[{cond_idx}] "
                                "boolean value must be string 'true' or 'false'"
                            )
            require_handles(n, [*case_handles, "FALSE"])

        if cat == "KNOWLEDGE_REPLY":
            require_incoming(n)
            require_handles(n, ["RESOLVED", "UNRESOLVED"])

        if cat == "RAG_REPLY":
            require_incoming(n)
            require_handles(n, ["TRUE", "LACK_KNOWLEDGE"])
            rag_reply = cfg.get("ragReply") or {}
            keyword_ids = rag_reply.get("knowledgeKeywordIds")
            if keyword_ids is not None and (
                not isinstance(keyword_ids, list)
                or any(not isinstance(item, int) or isinstance(item, bool) for item in keyword_ids)
            ):
                errors.append(
                    f"RAG_REPLY '{title_of(n)}' knowledgeKeywordIds must be an integer id array"
                )
            keyword_selector = rag_reply.get("knowledgeKeywordSelector")
            if keyword_ids is not None and keyword_selector is not None:
                errors.append(
                    f"RAG_REPLY '{title_of(n)}' must not set both knowledgeKeywordIds and knowledgeKeywordSelector"
                )
            if keyword_selector is not None:
                errors.extend(
                    validate_selector(
                        keyword_selector,
                        f"RAG_REPLY '{title_of(n)}'",
                        "knowledgeKeywordSelector",
                        current_node_id=n["id"],
                    )
                )
            if rag_reply.get("customizeQuery"):
                if not rag_reply.get("querySelector"):
                    errors.append(f"RAG_REPLY '{title_of(n)}' missing querySelector")
                else:
                    errors.extend(
                        validate_selector(
                            rag_reply.get("querySelector"),
                            f"RAG_REPLY '{title_of(n)}'",
                            "querySelector",
                            current_node_id=n["id"],
                        )
                    )

        if cat == "HUMAN_REVIEW":
            require_incoming(n)
            human_review = cfg.get("humanReview") or cfg.get("humanInLoop") or {}
            method = human_review.get("method") or "approval"
            if method not in {"approval", "fill"}:
                errors.append(f"HUMAN_REVIEW '{title_of(n)}' has unsupported method '{method}'")
            midway_message_strategy = human_review.get("midwayMessageStrategy") or "ignore"
            if midway_message_strategy not in {"ignore", "handle"}:
                errors.append(
                    f"HUMAN_REVIEW '{title_of(n)}' has unsupported midwayMessageStrategy '{midway_message_strategy}'"
                )
            if is_blank(human_review.get("description")):
                errors.append(f"HUMAN_REVIEW '{title_of(n)}' missing description")
            else:
                errors.extend(
                    validate_selector_templates(
                        human_review.get("description"),
                        f"HUMAN_REVIEW '{title_of(n)}'",
                        "description",
                        current_node_id=n["id"],
                        allow_tool_status=True,
                        allow_node=True,
                    )
                )
            if method == "fill":
                for idx, field in enumerate(human_review.get("fields") or []):
                    if is_blank(field.get("fieldName")):
                        errors.append(f"HUMAN_REVIEW '{title_of(n)}' field[{idx}] missing fieldName")
                    if field.get("fieldType") == "options":
                        options = field.get("options") or []
                        if not options or any(is_blank(option) for option in options):
                            errors.append(f"HUMAN_REVIEW '{title_of(n)}' field[{idx}] has empty options")
                        elif len(set(options)) != len(options):
                            errors.append(f"HUMAN_REVIEW '{title_of(n)}' field[{idx}] has duplicate options")
            if method == "fill":
                require_handles(n, ["SOURCE"])
            else:
                require_handles(n, ["AGREE", "REJECT"])

        if cat == "BUSINESS_TRACK":
            business_track = cfg.get("businessTrack") or {}
            trace_events = business_track.get("traceEvents")
            if not isinstance(trace_events, list) or not trace_events:
                errors.append(f"BUSINESS_TRACK '{title_of(n)}' missing traceEvents")
            elif any(not isinstance(event, str) or not event.strip() for event in trace_events):
                errors.append(
                    f"BUSINESS_TRACK '{title_of(n)}' traceEvents must be non-empty strings"
                )

        if cat == "CODE":
            code = cfg.get("code") or {}
            if not code.get("sourceCode"):
                errors.append(f"CODE '{title_of(n)}' has empty sourceCode")
            else:
                errors.extend(_validate_code_source(code.get("sourceCode"), title_of(n)))
            input_names = []
            for idx, item in enumerate(code.get("inputs") or []):
                field_name = item.get("fieldName")
                if not field_name:
                    errors.append(f"CODE '{title_of(n)}' input[{idx}] missing fieldName")
                else:
                    input_names.append(field_name)
                if not item.get("variableSelector"):
                    errors.append(f"CODE '{title_of(n)}' input[{idx}] missing variableSelector")
                else:
                    errors.extend(
                        validate_selector(
                            item.get("variableSelector"),
                            f"CODE '{title_of(n)}'",
                            f"input[{idx}].variableSelector",
                            current_node_id=n["id"],
                            allow_tool_status=True,
                        )
                    )
            if not code.get("outputs"):
                errors.append(f"CODE '{title_of(n)}' missing outputs")
            output_names = []
            for idx, item in enumerate(code.get("outputs") or []):
                field_name = item.get("fieldName")
                if not field_name:
                    errors.append(f"CODE '{title_of(n)}' output[{idx}] missing fieldName")
                else:
                    output_names.append(field_name)
                if not item.get("fieldType"):
                    errors.append(f"CODE '{title_of(n)}' output[{idx}] missing fieldType")
            for group_name, names in (("input", input_names), ("output", output_names)):
                duplicates = {name for name in names if names.count(name) > 1}
                for name in sorted(duplicates):
                    errors.append(f"CODE '{title_of(n)}' duplicate {group_name} fieldName '{name}'")
            for name in [*input_names, *output_names]:
                if not CODE_FIELD_NAME_REG.match(name):
                    errors.append(f"CODE '{title_of(n)}' fieldName '{name}' is not a valid Python identifier")
                if name in CODE_RESERVED_NAMES:
                    errors.append(f"CODE '{title_of(n)}' fieldName '{name}' is a reserved Python name")

        if cat == "SUB_GRAPH":
            if has_outgoing(n):
                errors.append(f"SUB_GRAPH '{title_of(n)}' must not have outgoing edges")
            sub_graph = cfg.get("subGraph") or {}
            if not sub_graph.get("targetAgentId"):
                errors.append(f"SUB_GRAPH '{title_of(n)}' missing targetAgentId")
            context_turn_limit = sub_graph.get("contextTurnLimit", 5)
            if context_turn_limit < 1 or context_turn_limit > 10:
                errors.append(f"SUB_GRAPH '{title_of(n)}' contextTurnLimit must be between 1 and 10")

        if cat == "VARIABLE_PROCESS":
            variable_process = cfg.get("variableProcess") or {}
            extracts = variable_process.get("extracts") or []
            assignments = variable_process.get("assignments") or []
            self_extract_ids = {item.get("id") for item in extracts if item.get("id")}
            if not extracts and not assignments:
                errors.append(f"VARIABLE_PROCESS '{title_of(n)}' has neither extracts nor assignments")
            for data_idx, selector in enumerate(variable_process.get("additionalData") or []):
                errors.extend(
                    validate_selector(
                        selector,
                        f"VARIABLE_PROCESS '{title_of(n)}'",
                        f"additionalData[{data_idx}]",
                        current_node_id=n["id"],
                        allow_node=True,
                    )
                )
            for idx, item in enumerate(extracts):
                if not item.get("id") or not item.get("name") or not item.get("describe") or not item.get("type"):
                    errors.append(f"VARIABLE_PROCESS '{title_of(n)}' extract[{idx}] missing id/name/describe/type")
                if item.get("name") and not PARAM_NAME_REG.match(item.get("name")):
                    errors.append(f"VARIABLE_PROCESS '{title_of(n)}' extract[{idx}] has invalid name '{item.get('name')}'")
            for idx, item in enumerate(assignments):
                if not item.get("id") or not item.get("operation") or not item.get("target"):
                    errors.append(f"VARIABLE_PROCESS '{title_of(n)}' assignment[{idx}] missing id/operation/target")
                if item.get("operation") == "CONSTANT" and is_blank(item.get("source")):
                    errors.append(f"VARIABLE_PROCESS '{title_of(n)}' assignment[{idx}] CONSTANT missing source")
                for target_idx, selector in enumerate(item.get("target") or []):
                    errors.extend(
                        validate_selector(
                            selector,
                            f"VARIABLE_PROCESS '{title_of(n)}'",
                            f"assignment[{idx}].target[{target_idx}]",
                            current_node_id=n["id"],
                            system_only=True,
                        )
                    )
                if item.get("operation") == "OVER_WRITE" and isinstance(item.get("source"), list):
                    errors.extend(
                        validate_selector(
                            item.get("source"),
                            f"VARIABLE_PROCESS '{title_of(n)}'",
                            f"assignment[{idx}].source",
                            current_node_id=n["id"],
                            allow_self=True,
                            self_extract_ids=self_extract_ids,
                        )
                    )

        if cat == "VARIABLE_EXTRACT":
            variable_extract = cfg.get("variableExtract") or {}
            extracts = variable_extract.get("extracts") or []
            if not extracts:
                errors.append(f"VARIABLE_EXTRACT '{title_of(n)}' missing extracts")
            for data_idx, selector in enumerate(variable_extract.get("additionalData") or []):
                errors.extend(
                    validate_selector(
                        selector,
                        f"VARIABLE_EXTRACT '{title_of(n)}'",
                        f"additionalData[{data_idx}]",
                        current_node_id=n["id"],
                        allow_node=True,
                    )
                )
            for idx, item in enumerate(extracts):
                if not item.get("id") or not item.get("name") or not item.get("describe") or not item.get("type"):
                    errors.append(f"VARIABLE_EXTRACT '{title_of(n)}' extract[{idx}] missing id/name/describe/type")
                if item.get("name") and not PARAM_NAME_REG.match(item.get("name")):
                    errors.append(f"VARIABLE_EXTRACT '{title_of(n)}' extract[{idx}] has invalid name '{item.get('name')}'")

        if cat == "VARIABLE_ASSIGNMENT":
            assignments = cfg.get("variableAssignment") or []
            for idx, item in enumerate(assignments):
                if not item.get("id") or not item.get("operation") or not item.get("target"):
                    errors.append(f"VARIABLE_ASSIGNMENT '{title_of(n)}' assignment[{idx}] missing id/operation/target")
                if item.get("operation") == "CONSTANT" and is_blank(item.get("source")):
                    errors.append(f"VARIABLE_ASSIGNMENT '{title_of(n)}' assignment[{idx}] CONSTANT missing source")
                for target_idx, selector in enumerate(item.get("target") or []):
                    errors.extend(
                        validate_selector(
                            selector,
                            f"VARIABLE_ASSIGNMENT '{title_of(n)}'",
                            f"assignment[{idx}].target[{target_idx}]",
                            current_node_id=n["id"],
                            system_only=True,
                        )
                    )
                if item.get("operation") == "OVER_WRITE" and isinstance(item.get("source"), list):
                    errors.extend(
                        validate_selector(
                            item.get("source"),
                            f"VARIABLE_ASSIGNMENT '{title_of(n)}'",
                            f"assignment[{idx}].source",
                            current_node_id=n["id"],
                        )
                    )

        if cat == "AGENT":
            require_incoming(n)
            agent_data = cfg.get("agentData") or {}
            transfer_to_humans = agent_data.get("transferToHumans")
            if transfer_to_humans not in (None, []):
                errors.append(
                    f"AGENT '{title_of(n)}' transferToHumans is not supported by the current runtime; use a TRANSFER_TO_HUMAN node"
                )
            max_rounds_exceeded_action = cfg.get("maxRoundsExceededAction") or {}
            if not isinstance(max_rounds_exceeded_action, dict):
                errors.append(
                    f"AGENT '{title_of(n)}' maxRoundsExceededAction must be an object"
                )
            else:
                exceeded_action_type = max_rounds_exceeded_action.get("type") or "TRANSFER_TO_HUMAN"
                if exceeded_action_type not in {"FORCE_NEXT_STEP", "TRANSFER_TO_HUMAN"}:
                    errors.append(
                        f"AGENT '{title_of(n)}' has unsupported maxRoundsExceededAction '{exceeded_action_type}'"
                    )
            errors.extend(
                reject_selector_templates(
                    agent_data.get("prompt"),
                    f"AGENT '{title_of(n)}'",
                    "agentData.prompt",
                )
            )
            errors.extend(
                reject_selector_templates(
                    agent_data.get("displayPrompt"),
                    f"AGENT '{title_of(n)}'",
                    "agentData.displayPrompt",
                )
            )
            library_blocks = []
            try:
                library_blocks = _parse_library_blocks(agent_data.get("displayPrompt"))
            except ValueError as exc:
                errors.append(f"AGENT '{title_of(n)}' has invalid LibraryBlock: {exc}")
            else:
                if library_blocks:
                    expected_runtime_prompt = _format_library_blocks(
                        agent_data.get("displayPrompt"), library_blocks
                    )
                    runtime_prompt = agent_data.get("prompt")
                    if runtime_prompt != expected_runtime_prompt:
                        legacy_runtime_prompt = expected_runtime_prompt.replace(
                            "Transfer_To_Agent", "Transfer_to_agent"
                        )
                        if (
                            any(block["type"] == "transferHuman" for block in library_blocks)
                            and _collapse_prompt_whitespace(runtime_prompt)
                            == _collapse_prompt_whitespace(legacy_runtime_prompt)
                        ):
                            warnings.append(
                                f"AGENT '{title_of(n)}' runtime prompt uses legacy "
                                "Transfer_to_agent casing; resave it as Transfer_To_Agent"
                            )
                        elif (
                            _collapse_prompt_whitespace(runtime_prompt)
                            == _collapse_prompt_whitespace(expected_runtime_prompt)
                        ):
                            warnings.append(
                                f"AGENT '{title_of(n)}' runtime prompt differs from "
                                "displayPrompt only in whitespace; resave it to synchronize formatting"
                            )
                        else:
                            errors.append(
                                f"AGENT '{title_of(n)}' runtime prompt is not synchronized "
                                "with displayPrompt LibraryBlocks"
                            )
            used_plugins = agent_data.get("usedPlugins") or []
            seen_plugin_ids = set()
            duplicate_plugin_ids = set()
            for plugin_id in used_plugins:
                if isinstance(plugin_id, bool) or not isinstance(plugin_id, int):
                    continue
                if plugin_id in seen_plugin_ids:
                    duplicate_plugin_ids.add(plugin_id)
                seen_plugin_ids.add(plugin_id)
            for plugin_id in sorted(duplicate_plugin_ids, key=str):
                warnings.append(
                    f"AGENT '{title_of(n)}' usedPlugins contains duplicate id {plugin_id}"
                )
            required_system_plugin_types = set()
            transfer_tool_ids = []
            for block in library_blocks:
                fields = block["fields"]
                if block["type"] == "variable":
                    field_id = int(fields["id"])
                    if field_id not in (agent_data.get("aiFieldIds") or []):
                        errors.append(
                            f"AGENT '{title_of(n)}' variable LibraryBlock id {field_id} "
                            "is missing from aiFieldIds"
                        )
                elif block["type"] == "tool" and fields["tool"] == "template_reply":
                    template_id = int(fields["id"])
                    required_system_plugin_types.add("TEMPLATE_REPLY")
                    validate_template_reference(
                        template_id, f"AGENT '{title_of(n)}' template_reply LibraryBlock"
                    )
                elif block["type"] == "tool":
                    plugin_id = int(fields["id"])
                    if plugin_id not in used_plugins:
                        errors.append(
                            f"AGENT '{title_of(n)}' tool LibraryBlock id {plugin_id} "
                            "is missing from usedPlugins"
                        )
                    plugin = plugins_by_id.get(str(plugin_id))
                    if plugin_metadata_available and plugin is None:
                        errors.append(
                            f"AGENT '{title_of(n)}' tool LibraryBlock references "
                            f"unknown plugin id {plugin_id}"
                        )
                    elif plugin is not None:
                        plugin_name = next(
                            (
                                str(plugin.get(field)).strip()
                                for field in ("name", "pluginName", "title", "toolName")
                                if str(plugin.get(field) or "").strip()
                            ),
                            "",
                        )
                        if plugin_name:
                            for field in ("name", "tool"):
                                if fields[field] != plugin_name:
                                    errors.append(
                                        f"AGENT '{title_of(n)}' tool LibraryBlock {field} "
                                        f"{fields[field]!r} does not match plugin id "
                                        f"{plugin_id} name {plugin_name!r}"
                                    )
                elif block["type"] == "transferHuman":
                    required_system_plugin_types.add("TRANSFER_TO_HUMAN")
                    transfer_tool_ids.append(block["fields"]["tool_id"])
            if len(transfer_tool_ids) != len(set(transfer_tool_ids)):
                warnings.append(
                    f"AGENT '{title_of(n)}' has duplicate transferHuman tool_id values; "
                    "resave those PE blocks with unique instance IDs"
                )
            bound_plugin_types = set()
            for idx, plugin_id in enumerate(agent_data.get("usedPlugins") or []):
                if isinstance(plugin_id, bool) or not isinstance(plugin_id, int):
                    errors.append(
                        f"AGENT '{title_of(n)}' usedPlugins[{idx}] must be an integer tool id"
                    )
                    continue
                plugin = plugins_by_id.get(str(plugin_id))
                if plugin:
                    plugin_type = str(
                        plugin.get("type") or plugin.get("pluginType") or ""
                    ).upper()
                    if plugin_type:
                        bound_plugin_types.add(plugin_type)
            if plugin_metadata_available:
                for plugin_type in sorted(required_system_plugin_types - bound_plugin_types):
                    errors.append(
                        f"AGENT '{title_of(n)}' {plugin_type} LibraryBlock requires a "
                        f"usedPlugins entry whose plugin type is {plugin_type}"
                    )
            for idx, field_id in enumerate(agent_data.get("aiFieldIds") or []):
                if isinstance(field_id, bool) or not isinstance(field_id, int):
                    errors.append(
                        f"AGENT '{title_of(n)}' aiFieldIds[{idx}] must be an integer field id"
                    )
                elif valid_agent_ai_field_ids is not None and field_id not in valid_agent_ai_field_ids:
                    errors.append(
                        f"AGENT '{title_of(n)}' aiFieldIds[{idx}] references unknown field id {field_id}"
                    )
            keyword_ids = agent_data.get("knowledgeKeywordIds")
            if keyword_ids is not None and (
                not isinstance(keyword_ids, list)
                or any(not isinstance(item, int) or isinstance(item, bool) for item in keyword_ids)
            ):
                errors.append(
                    f"AGENT '{title_of(n)}' knowledgeKeywordIds must be an integer id array"
                )
            keyword_selector = agent_data.get("knowledgeKeywordSelector")
            if keyword_ids is not None and keyword_selector is not None:
                errors.append(
                    f"AGENT '{title_of(n)}' must not set both knowledgeKeywordIds and knowledgeKeywordSelector"
                )
            if keyword_selector is not None:
                errors.extend(
                    validate_selector(
                        keyword_selector,
                        f"AGENT '{title_of(n)}'",
                        "knowledgeKeywordSelector",
                        current_node_id=n["id"],
                    )
                )
            next_step = cfg.get("nextStep") or []
            if next_step:
                param_names = []
                for idx, step in enumerate(next_step):
                    if not step.get("id"):
                        errors.append(f"AGENT '{title_of(n)}' nextStep[{idx}] missing id")
                    if not step.get("title"):
                        errors.append(f"AGENT '{title_of(n)}' nextStep[{idx}] missing title")
                    elif not NEXT_STEP_TITLE_REG.fullmatch(str(step.get("title"))):
                        warnings.append(
                            f"AGENT '{title_of(n)}' nextStep[{idx}].title is not lowercase snake_case; "
                            "lowercase snake_case is recommended for generated transfer tool names"
                        )
                    if not step.get("prompt"):
                        errors.append(f"AGENT '{title_of(n)}' nextStep[{idx}] missing prompt")
                    for param_idx, param in enumerate(step.get("params") or []):
                        param_name = param.get("name")
                        if not param_name or not param.get("type") or not param.get("describe"):
                            errors.append(
                                f"AGENT '{title_of(n)}' nextStep[{idx}].params[{param_idx}] missing name/type/describe"
                            )
                        if param_name:
                            param_names.append(param_name)
                            if not PARAM_NAME_REG.match(param_name):
                                errors.append(
                                    f"AGENT '{title_of(n)}' nextStep[{idx}].params[{param_idx}] has invalid name '{param_name}'"
                                )
                duplicate_param_names = {name for name in param_names if param_names.count(name) > 1}
                for name in sorted(duplicate_param_names):
                    errors.append(f"AGENT '{title_of(n)}' has duplicate nextStep param name '{name}'")
                require_handles(n, [ns.get("id") for ns in next_step])
            else:
                if (
                    isinstance(max_rounds_exceeded_action, dict)
                    and max_rounds_exceeded_action.get("type") == "FORCE_NEXT_STEP"
                ):
                    warnings.append(
                        f"AGENT '{title_of(n)}' uses FORCE_NEXT_STEP without nextStep; runtime will hand off instead"
                    )
                # AGENT without nextStep: SOURCE edge required unless this is a terminal AGENT
                # (terminal AGENTs are rare — warn rather than error)
                handles = handles_by_node.get(n["id"], set())
                if "SOURCE" not in handles:
                    warnings.append(f"AGENT '{title_of(n)}' has no SOURCE outbound edge — confirm it's a terminal node")

        if cat == "LLM":
            require_handles(n, ["SOURCE"])
            llm_cfg = cfg.get("llm") or {}
            prompt = llm_cfg.get("promptTemplate")
            if is_blank(prompt):
                errors.append(f"LLM '{title_of(n)}' missing promptTemplate")
            history_round_limit = cfg.get("historyRoundLimit", 0)
            if (
                not isinstance(history_round_limit, int)
                or isinstance(history_round_limit, bool)
                or history_round_limit < -1
            ):
                errors.append(
                    f"LLM '{title_of(n)}' historyRoundLimit must be -1, 0, or a positive integer"
                )
            for legacy_field in ("aiFieldIds", "modelId", "outputs", "outputVariables"):
                if legacy_field in llm_cfg:
                    warnings.append(
                        f"LLM '{title_of(n)}' {legacy_field} is ignored by the current runtime; use variable templates or structuredOutput"
                    )

            vision = llm_cfg.get("vision") or {}
            if not isinstance(vision, dict):
                errors.append(f"LLM '{title_of(n)}' vision must be an object")
            else:
                vision_enabled = vision.get("enabled", False)
                vision_detail = vision.get("detail", "auto")
                media_selectors = vision.get("mediaSelectors", [])
                if not isinstance(vision_enabled, bool):
                    errors.append(f"LLM '{title_of(n)}' vision.enabled must be boolean")
                if vision_detail not in {"auto", "low", "high"}:
                    errors.append(f"LLM '{title_of(n)}' vision.detail must be auto, low, or high")
                if not isinstance(media_selectors, list):
                    errors.append(f"LLM '{title_of(n)}' vision.mediaSelectors must be a list")
                elif vision_enabled and not media_selectors:
                    errors.append(f"LLM '{title_of(n)}' vision.enabled requires mediaSelectors")
                else:
                    for idx, selector in enumerate(media_selectors):
                        errors.extend(
                            validate_selector(
                                selector,
                                f"LLM '{title_of(n)}'",
                                f"vision.mediaSelectors[{idx}]",
                                current_node_id=n["id"],
                                allow_node=True,
                            )
                        )

            structured_output = llm_cfg.get("structuredOutput") or {}
            if not isinstance(structured_output, dict):
                errors.append(f"LLM '{title_of(n)}' structuredOutput must be an object")
            else:
                structured_enabled = structured_output.get("enabled", False)
                schema = structured_output.get("schema", {})
                if not isinstance(structured_enabled, bool):
                    errors.append(f"LLM '{title_of(n)}' structuredOutput.enabled must be boolean")
                if not isinstance(schema, dict):
                    errors.append(f"LLM '{title_of(n)}' structuredOutput.schema must be an object")
                elif structured_enabled:
                    if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
                        errors.append(
                            f"LLM '{title_of(n)}' structuredOutput.schema must be object-rooted with properties"
                        )
                    if "required" in schema and not isinstance(schema.get("required"), list):
                        errors.append(
                            f"LLM '{title_of(n)}' structuredOutput.schema.required must be a list"
                        )

            errors.extend(
                validate_selector_templates(
                    prompt,
                    f"LLM '{title_of(n)}'",
                    "llm.promptTemplate",
                    current_node_id=n["id"],
                    allow_tool_status=True,
                    allow_node=True,
                )
            )

    # 11. Cycle detection (对齐前端 useCheckFlow.detectCycle)
    # 多轮追问交给节点自带的 maxRounds 字段（KNOWLEDGE_REPLY / QUESTION），
    # 不要在图层面回连——QUESTION "Need_More_Help" 应该接 TRANSFER_TO_HUMAN
    # 或 FINISH，不要回连上游 KB。
    cycle_path = _detect_cycle(runtime_nodes, runtime_edges)
    if cycle_path:
        labels = []
        for nid in cycle_path:
            n = runtime_node_map.get(nid)
            title = n.get("data", {}).get("title") if n else None
            labels.append(title or nid)
        errors.append(f"Graph has a cycle: {' → '.join(labels)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "categories": [n.get("data", {}).get("category", "") for n in nodes],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="chatFlowGraph 结构校验")
    parser.add_argument("--data-file", required=True, help="JSON file with chatFlowGraph")
    args = parser.parse_args()

    with open(args.data_file, encoding="utf-8") as f:
        graph = json.load(f)
    result = validate_graph(graph)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
