"""
Delivery intent / agent / strategy creation pipeline.

Creates all standard delivery intents, copies fixed marketplace agents by
squareAgent_id when available, binds strategy routing, and patches X-Token in
order tools by default. Same-name intents are reused. Missing preset agents are
recorded as recoverable gaps instead of crashing the run.

Override the X-Token behaviour explicitly via --update-x-token / --no-update-x-token.

Usage:
  # delivery: create all 7 intents + update X-Token
  python3 scripts/create_agents.py

  # disable SYSTEM intents after a creation run
  python3 scripts/create_agents.py --disable-system

  # dry-run preview (no API calls beyond marketplace listing in non-disable mode)
  python3 scripts/create_agents.py --dry-run
"""

import os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *

import json, argparse
from pathlib import Path

from client import SolveaClient


def _read_state() -> dict:
    _sf = STATE_DIR / "progress.json"
    if _sf.exists():
        try:
            return json.loads(_sf.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_state(data: dict) -> None:
    _sf = STATE_DIR / "progress.json"
    _sf.parent.mkdir(parents=True, exist_ok=True)
    _sf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Fixed mapping table ────────────────────────────────────────────────────────

# Delivery 固定绑定：每个意图 → 一个广场 agent（按 squareAgent_id 直接克隆，
# 不再走"查广场列表 + 按名字匹配"链路，避免名字漂移。
# 不在此 map 中的意图（数据中新发现的 L1）→ 跳过 agent / 策略，标 SKIPPED。
# 固定 squareAgent_id 是首选来源，不是硬阻塞；复制失败时记录可恢复缺口。
DELIVERY_AGENT_BINDINGS = {
    "Pre-Sales Inquiry":   37625,
    "Invoices":            37627,
    "Order Issues":        37631,
    "Logistics Issues":    37633,
    "Package issues":      37623,
    "Product issues":      38114,
    "Return and exchange": 37626,
}

# ── Data loading ───────────────────────────────────────────────────────────────

def load_results(state: dict) -> dict:
    """Load classification results pointed to by state.results_path.

    eager 模型下 workspace/outputs/ 跨轮路径稳定，state 里存的绝对路径下轮直接可用。
    """
    path = state.get("results_path")
    if not path:
        raise FileNotFoundError("state.results_path missing. Run classify.py first.")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Results file missing: {path}")
    with open(path) as f:
        return json.load(f)


# ── Feature pre-flight checks ─────────────────────────────────────────────────

def check_and_enable_intent_feature(solvea: SolveaClient) -> None:
    """创建意图前确保意图功能已开启（configurationWizard.intent=true）。

    查询：GET /api_v2/gpt/project/{projectId}/config → configurationWizard.intent
    开启：PUT /api_v2/gpt/project/{projectId}        → body: {configurationWizard: {intent: true}}
    """
    resp = solvea._curl("GET", f"/api_v2/gpt/project/{solvea.project_id}/config")
    payload = resp.get("data", resp) or {}
    wizard = payload.get("configurationWizard") or {}
    if wizard.get("intent"):
        return
    solvea._curl("PUT", f"/api_v2/gpt/project/{solvea.project_id}", {
        "configurationWizard": {"intent": True}
    })
    print("[NOTICE] 该租户意图功能（Intent）原本未开启，已自动启用")


def check_and_enable_variable_feature(solvea: SolveaClient) -> None:
    """复制 agent 前确保变量功能已初始化（isInitAiField=true）。

    查询：POST /api_v2/tars/api/field/manage/guide/record → isInitAiField
    开启：GET  /api_v2/tars/api/field/manage/pre/install
    """
    resp = solvea._curl("POST", "/api_v2/tars/api/field/manage/guide/record")
    payload = resp.get("data", resp) or {}
    if payload.get("isInitAiField"):
        return
    solvea._curl("GET", "/api_v2/tars/api/field/manage/pre/install")
    print("[NOTICE] 该租户变量功能（AI Field）原本未开启，已自动初始化预装字段")


# ── Marketplace agent lookup ───────────────────────────────────────────────────

def copy_marketplace_agent_by_id(solvea: SolveaClient, square_agent_id: int) -> str:
    """直接按广场 agent ID 克隆到当前租户，返回新 agent_id。

    Delivery 按固定 squareAgent_id 复制广场 agent，取代"查广场→按名字匹配"。
    链路，避免广场 agent 名字漂移。
    """
    result = solvea._curl("POST", "/api_v2/gpt/ap/copyAgent", {
        "projectId": int(solvea.project_id),
        "agentId": int(square_agent_id),
    })
    new_id = str(
        result.get("id") or
        result.get("agentId") or
        result.get("data", {}).get("id", "")
    )
    if not new_id:
        raise RuntimeError(f"copyAgent(square_agent_id={square_agent_id}) returned no id: {result}")
    print(f"[copy_agent] square_id={square_agent_id} → new id={new_id}")
    return new_id


# ── L1 intent creation ─────────────────────────────────────────────────────────

def _intent_items(result) -> list:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "list", "records"):
            if isinstance(result.get(key), list):
                return result[key]
    return []


def _find_existing_intent_by_name(solvea: SolveaClient, name: str) -> dict | None:
    result = solvea.list_intents()
    for item in _intent_items(result):
        if isinstance(item, dict) and item.get("name") == name:
            intent_id = item.get("id") or item.get("intentId")
            if intent_id:
                return item
    return None


def create_l1_intent(
    solvea: SolveaClient,
    intent: dict,
    dry_run: bool = False,
    existing_by_name: dict | None = None,
) -> dict | None:
    name = intent["name"]
    definition = intent.get("definition") or f"Customer messages related to {name}."
    data = {
        "name": name,
        "description": definition,
        "example": definition,
        "status": "ENABLED",
    }
    if dry_run:
        print(f"[dry-run] create_intent: {name}")
        return None

    existing = (existing_by_name or {}).get(name)
    if existing:
        intent_id = existing.get("id") or existing.get("intentId")
        print(f"[create_intent] existing same-name intent found, reusing id={intent_id} name={name}")
        return {"id": intent_id, **existing}

    print(f"[create_intent] {name} ...")
    try:
        result = solvea.create_intent(data)
    except RuntimeError as exc:
        if "already exists" not in str(exc):
            raise
        existing = _find_existing_intent_by_name(solvea, name)
        if not existing:
            raise
        intent_id = existing.get("id") or existing.get("intentId")
        print(f"[create_intent] already exists, reusing id={intent_id} name={name}")
        return {"id": intent_id, **existing}
    intent_id = result.get("id") or result.get("intentId")
    if not intent_id:
        if "already exists" in str(result.get("errmsg", "")):
            existing = _find_existing_intent_by_name(solvea, name)
            if existing:
                intent_id = existing.get("id") or existing.get("intentId")
                print(f"[create_intent] already exists, reusing id={intent_id} name={name}")
                result["id"] = intent_id
        if not intent_id:
            raise RuntimeError(f"create_intent returned no id for '{name}': {result}")
    else:
        print(f"[create_intent] OK → id={intent_id}")
    return result


# ── Strategy creation ──────────────────────────────────────────────────────────

def create_strategy_for_intent(
    solvea: SolveaClient,
    intent_id: str,
    agent_id: str,
    intent_name: str,
    dry_run: bool = False,
) -> dict | None:
    if dry_run:
        print(f"[dry-run] create_strategy: intent={intent_id} → agent={agent_id}")
        return None
    data = {
        "name": f"Route_{intent_name}",
        "status": "ENABLED",
        "priority": 0,
        "trigger": "MESSAGE",
        "condition": {
            "and": [{
                "rules": [{
                    "apiName": "__intent_ids",
                    "apiType": "TEXT",
                    "relation": "IN",
                    "type": "GENERIC",
                    "values": [int(intent_id)],
                }]
            }]
        },
        "action": {
            "type": "AGENT",
            "agentId": int(agent_id),
        },
    }
    print(f"[create_strategy] Route_{intent_name} ...")
    result = solvea.create_strategy(data)
    strategy_id = result.get("id") or result.get("strategyId")
    if not strategy_id:
        raise RuntimeError(
            f"create_strategy returned no id for '{intent_name}' "
            f"(intent={intent_id}, agent={agent_id}): {result}"
        )
    print(f"[create_strategy] OK → id={strategy_id}")
    return result


def create_strategy_for_intents(
    solvea: SolveaClient,
    intent_ids: list,
    agent_id: str,
    name: str,
    priority: int = 0,
    dry_run: bool = False,
) -> dict | None:
    """N 个意图 → 1 个 agent 的策略（rules.values 多值）。"""
    if not intent_ids:
        raise ValueError(f"create_strategy_for_intents '{name}': intent_ids is empty")
    if dry_run:
        print(f"[dry-run] create_strategy: intents={intent_ids} → agent={agent_id} (priority={priority})")
        return None
    data = {
        "name": f"Route_{name}",
        "status": "ENABLED",
        "priority": priority,
        "trigger": "MESSAGE",
        "condition": {
            "and": [{
                "rules": [{
                    "apiName": "__intent_ids",
                    "apiType": "TEXT",
                    "relation": "IN",
                    "type": "GENERIC",
                    "values": [int(i) for i in intent_ids],
                }]
            }]
        },
        "action": {
            "type": "AGENT",
            "agentId": int(agent_id),
        },
    }
    print(f"[create_strategy] Route_{name} (intents={intent_ids}, priority={priority}) ...")
    result = solvea.create_strategy(data)
    strategy_id = result.get("id") or result.get("strategyId")
    if not strategy_id:
        raise RuntimeError(
            f"create_strategy returned no id for '{name}' "
            f"(intents={intent_ids}, agent={agent_id}): {result}"
        )
    print(f"[create_strategy] OK → id={strategy_id}")
    return result


# ── Update order tool X-Token ────────────────────────────────────────────────

def update_order_tool_x_token(solvea: SolveaClient, creation_log: list, dry_run: bool = False) -> None:
    """After all agent copies, patch X-Token header in any order information tools found."""
    TARGET_TOOLS = {
        "new_Order_information_product",
        "new_Order_information_FBA",
        "new_Order_information_ship",
    }
    copied_agent_ids = [
        item["agent_id"] for item in creation_log
        if not item.get("skipped") and item.get("agent_id")
    ]
    if not copied_agent_ids:
        return

    raw = solvea.get_api_key()
    if isinstance(raw, dict):
        x_token = raw.get("apiKey") or raw.get("key") or raw.get("value") or raw.get("data") or str(raw)
    else:
        x_token = str(raw)

    updated = 0
    for agent_id in copied_agent_ids:
        tools_resp = solvea._curl("GET", f"/api_v2/gpt/ap/agent/{agent_id}/tools", {})
        for tool in (tools_resp if isinstance(tools_resp, list) else []):
            if tool.get("name") not in TARGET_TOOLS:
                continue
            tool_id = tool["id"]
            if dry_run:
                print(f"[dry-run] would update X-Token for tool '{tool['name']}' (id={tool_id})")
                continue
            config  = tool.get("config") or {}
            headers = config.get("headers") or {}
            headers["X-Token"] = x_token
            config["headers"] = headers
            solvea._curl("PUT", f"/api_v2/gpt/ap/tools/{tool_id}", {"config": config})
            print(f"[x_token] updated '{tool['name']}' (tool_id={tool_id})")
            updated += 1

    if updated:
        print(f"[x_token] {updated} tool(s) X-Token updated.")
    elif not dry_run:
        print("[x_token] No order information tools found — skipped.")


# ── Disable SYSTEM intents ────────────────────────────────────────────────────

def disable_system_intents(solvea: SolveaClient, keep_names: set, dry_run: bool = False) -> int:
    """Disable SYSTEM-source intents whose name is not in keep_names."""
    result = solvea.list_intents()
    intents = result if isinstance(result, list) else result.get("data", result.get("list", []))
    to_disable = [
        i for i in intents
        if i.get("source") == "SYSTEM"
        and i.get("name") not in keep_names
        and i.get("status") != "DISABLED"
    ]
    print(f"[disable_system] {len(to_disable)} SYSTEM intents to disable "
          f"(keeping {len(keep_names)} by name match)")
    for i in to_disable:
        if dry_run:
            print(f"[dry-run] disable intent: {i['name']} id={i['id']}")
        else:
            solvea.toggle_intent(i["id"], enabled=False)
            print(f"[disable_system] disabled: {i['name']} id={i['id']}")
    return len(to_disable)


def _load_agent_map(path: str) -> dict:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"custom agent map not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("intents"), dict):
        data = data["intents"]
    if not isinstance(data, dict):
        raise ValueError("custom agent map must be a JSON object or {'intents': {...}}")
    return {str(k): str(v) for k, v in data.items() if v not in (None, "")}


def _run_delivery_custom_agent_link(
    solvea: SolveaClient,
    log_path: str,
    map_path: str,
    dry_run: bool = False,
) -> None:
    """把用户确认的新建/替代 Agent 按 Delivery 意图写入策略。"""
    if not log_path or not os.path.exists(log_path):
        raise FileNotFoundError(
            f"created_log not found (state.created_log_path={log_path}). "
            "Run delivery creation first."
        )
    with open(log_path, encoding="utf-8") as f:
        log_data = json.load(f)
    if log_data.get("mode") != "delivery":
        raise RuntimeError(f"created_log mode is {log_data.get('mode')!r}, expected 'delivery'.")

    agent_map = _load_agent_map(map_path)
    linked = []
    for item in log_data.get("intents", []):
        intent_name = item.get("intent_name")
        if not intent_name or intent_name not in agent_map:
            continue
        intent_id = item.get("intent_id")
        agent_id = agent_map[intent_name]
        if not intent_id:
            print(f"[delivery.custom] WARNING intent '{intent_name}' has no intent_id; skipped")
            continue
        print(f"[delivery.custom] Binding {intent_name}: intent={intent_id} → agent {agent_id}")
        strategy_result = create_strategy_for_intent(
            solvea,
            str(intent_id),
            str(agent_id),
            intent_name,
            dry_run=dry_run,
        )
        strategy_id = str(strategy_result.get("id")) if strategy_result else f"dry_strategy_{intent_name}"
        item["agent_id"] = str(agent_id)
        item["strategy_id"] = strategy_id
        item["skipped"] = False
        item["skip_reason"] = ""
        item["recoverable"] = False
        item["custom_agent"] = True
        linked.append({"intent_name": intent_name, "agent_id": str(agent_id), "intent_id": intent_id, "strategy_id": strategy_id})

    if not linked:
        raise ValueError("custom agent map did not match any created Delivery intent name")

    log_data["custom_agent_strategies"] = [*(log_data.get("custom_agent_strategies") or []), *linked]
    log_data["next_action"] = "Continue knowledge-base setup and delivery regression test."
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    state = _read_state()
    state.update({
        "status": "created",
        "mode": "delivery",
        "created_log_path": log_path,
        "updated_at": timestamp(),
    })
    _write_state(state)
    print(f"\n[delivery.custom] Done. Linked {len(linked)} intent(s); log updated → {log_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create intents + copy marketplace agents + strategy routing"
    )
    parser.add_argument("--mode", choices=["delivery"], default="delivery",
                        help="Delivery only: create all intents + update X-Token.")
    parser.add_argument("--select", default=None,
                        help="DEPRECATED — ignored in all modes (all intents are now created).")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-system", action="store_true",
                        help="Disable active SYSTEM intents not matching created intent names")
    parser.add_argument("--custom-agent-map", default=None,
                        help="Delivery recovery stage: JSON map of intent name to custom/existing agent id, "
                             "for example {'Pre-Sales Inquiry': 2642, 'Product issues': 2643}.")
    x_token_grp = parser.add_mutually_exclusive_group()
    x_token_grp.add_argument("--update-x-token", dest="update_x_token", action="store_true",
                             help="Force X-Token patch after copy (default for --mode delivery)")
    x_token_grp.add_argument("--no-update-x-token", dest="update_x_token", action="store_false",
                             help="Skip X-Token patch")
    parser.set_defaults(update_x_token=None)
    args = parser.parse_args()

    # ── Early args sanity ──────────────────────────────────────────────────────
    if args.select:
        print(f"[main] WARNING: --select is deprecated and ignored (mode={args.mode}). "
              "All intents will be created.")

    # Resolve update_x_token default by mode when caller did not set it explicitly
    if args.update_x_token is None:
        update_x_token = (args.mode == "delivery")
    else:
        update_x_token = args.update_x_token

    state = _read_state()
    if not state:
        raise FileNotFoundError(
            "No state found. Run classify.py first (state should contain run_id and results_path)."
        )

    run_id = state.get("run_id")
    if not run_id:
        raise ValueError("state.run_id missing. Re-run classify.py.")

    # ── Disable-only mode ──────────────────────────────────────────────────────
    if args.disable_system:
        log_path = state.get("created_log_path")
        if not log_path or not os.path.exists(log_path):
            raise FileNotFoundError(
                f"No creation log found (state.created_log_path={log_path}). "
                "Run without --disable-system first."
            )
        with open(log_path) as f:
            existing_log = json.load(f)
        our_names = {item["intent_name"] for item in existing_log.get("intents", [])}
        solvea = SolveaClient()
        print(f"[main] Disable-only mode. project_id={solvea.project_id}")
        disable_system_intents(solvea, keep_names=our_names, dry_run=args.dry_run)
        return

    if args.custom_agent_map:
        solvea = SolveaClient()
        if not args.dry_run:
            print(f"[main] project_id={solvea.project_id}")
        _run_delivery_custom_agent_link(
            solvea,
            log_path=state.get("created_log_path"),
            map_path=args.custom_agent_map,
            dry_run=args.dry_run,
        )
        return

    results = load_results(state)
    all_intents = results.get("intents", []) + results.get("new_intents", [])
    print(f"[main] {len(all_intents)} intents loaded, run_id={run_id} (mode={args.mode})")

    if not all_intents:
        print("[main] No intents found. Run classify.py first.")
        return

    solvea = SolveaClient()
    if not args.dry_run:
        print(f"[main] project_id={solvea.project_id}")

    # ── 补全 Delivery 固定 7 个意图 ─────────────────────────────────────────────
    # 客户数据里如果没有某个固定意图的样本，classify.py 不会产生它；
    # Delivery 要建全部 7 个标准意图，这里强制补入缺失项。
    found_names = {i["name"] for i in all_intents}
    for fixed_name in DELIVERY_AGENT_BINDINGS:
        if fixed_name not in found_names:
            print(f"[main] '{fixed_name}' missing from classification results → added from fixed taxonomy")
            all_intents.append({"name": fixed_name, "definition": ""})

    # ── Feature pre-flight ─────────────────────────────────────────────────────
    if not args.dry_run:
        check_and_enable_intent_feature(solvea)    # 建意图前
        check_and_enable_variable_feature(solvea)  # copyAgent 前

    # ── Delivery ───────────────────────────────────────────────────────────────
    # 走固定 squareAgent_id 直接 copyAgent，不查广场 / 不按名字匹配。
    # 不在 DELIVERY_AGENT_BINDINGS 中的意图（数据中新发现的 L1）→ 跳过 agent/策略。

    creation_log = []
    preset_agent_errors = []
    existing_by_name = {}
    if not args.dry_run:
        existing_by_name = {
            item.get("name"): item
            for item in _intent_items(solvea.list_intents())
            if isinstance(item, dict) and item.get("name") and (item.get("id") or item.get("intentId"))
        }

    for intent in all_intents:
        name = intent["name"]
        print(f"\n{'='*60}")
        print(f"[main] Processing: {name}")

        # 1. Create L1 intent
        intent_result = create_l1_intent(
            solvea,
            intent,
            dry_run=args.dry_run,
            existing_by_name=existing_by_name,
        )
        intent_id = str(intent_result.get("id")) if intent_result else f"dry_{name}"

        # 2. Resolve square_agent_id from fixed binding
        square_id = DELIVERY_AGENT_BINDINGS.get(name)
        if not square_id:
            print(f"[main] No mapping for '{name}' in DELIVERY_AGENT_BINDINGS — skipping")
            creation_log.append({
                "intent_name": name, "intent_id": intent_id,
                "agent_name": None, "agent_id": None, "strategy_id": None,
                "skipped": True, "skip_reason": "no mapping in DELIVERY_AGENT_BINDINGS",
            })
            continue

        # 3. Copy by squareAgent_id
        agent_name = f"{name}【Delivery Version】"
        if args.dry_run:
            print(f"[dry-run] copy square_agent_id={square_id} ('{agent_name}')")
            agent_id = f"dry_agent_{name}"
        else:
            try:
                agent_id = copy_marketplace_agent_by_id(solvea, square_id)
            except Exception as exc:
                preset_agent_errors.append({
                    "intent_name": name,
                    "intent_id": intent_id,
                    "square_agent_id": square_id,
                    "agent_name": agent_name,
                    "error": str(exc),
                })
                print(
                    f"[main] PRESET_AGENT_MISSING intent={name} "
                    f"square_agent_id={square_id}: {exc}"
                )
                creation_log.append({
                    "intent_name": name, "intent_id": intent_id,
                    "agent_name": agent_name, "agent_id": None, "strategy_id": None,
                    "skipped": True, "skip_reason": "preset agent unavailable",
                    "recoverable": True,
                    "square_agent_id": square_id,
                })
                continue

        # 4. Create strategy routing
        strategy_result = create_strategy_for_intent(
            solvea, intent_id, agent_id, name, dry_run=args.dry_run
        )
        strategy_id = str(strategy_result.get("id")) if strategy_result else f"dry_strategy_{name}"

        creation_log.append({
            "intent_name": name, "intent_id": intent_id,
            "agent_name": agent_name, "agent_id": agent_id,
            "strategy_id": strategy_id, "skipped": False,
        })

    # 4. Patch X-Token in order information tools (delivery default; togglable)
    if update_x_token:
        update_order_tool_x_token(solvea, creation_log, dry_run=args.dry_run)
    else:
        print("[x_token] skipped (--no-update-x-token)")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = str(OUTPUTS_DIR / f"created_{timestamp()}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "intents": creation_log,
            "mode": args.mode,
            "run_id": run_id,
            "preset_agent_errors": preset_agent_errors,
            "next_action": (
                "For skipped preset-agent intents, ask the user whether to build new "
                "CHAT_FLOW agents from scratch or use substitute existing agent ids."
                if preset_agent_errors else ""
            ),
        }, f, ensure_ascii=False, indent=2)

    status = "preset_agent_missing" if preset_agent_errors else "created"
    state = _read_state()
    state.update({
        "status": status,
        "mode": args.mode,
        "created_log_path": log_path,
        "preset_agent_errors": preset_agent_errors,
        "updated_at": timestamp(),
    })
    _write_state(state)

    # Report SYSTEM intents that could be disabled (user confirms separately)
    if not args.dry_run:
        our_names = {item["intent_name"] for item in creation_log}
        result2 = solvea.list_intents()
        intents2 = result2 if isinstance(result2, list) else result2.get("data", result2.get("list", []))
        pending_disable = [
            i for i in intents2
            if i.get("source") == "SYSTEM"
            and i.get("name") not in our_names
            and i.get("status") != "DISABLED"
        ]
        if pending_disable:
            print(f"\n[system_intents] {len(pending_disable)} SYSTEM intents can be disabled:")
            for i in pending_disable:
                print(f"  id={i['id']} name={i['name']}")
            print("[system_intents] Run with --disable-system to disable them.")
        else:
            print("\n[system_intents] No active SYSTEM intents to disable.")

    created = [x for x in creation_log if not x.get("skipped")]
    skipped = [x for x in creation_log if x.get("skipped")]
    print(f"\n[main] Done. {len(created)} created, {len(skipped)} skipped.")
    print(f"[main] Log → {log_path}")
    if preset_agent_errors:
        print("[main] Recoverable preset-agent gap detected.")
        print("[main] Ask the user to choose one option for each skipped standard intent:")
        print("  1. Build a new CHAT_FLOW agent from scratch.")
        print("  2. Use an existing substitute agent id.")
    print(f"\n[main] Summary:")
    for item in creation_log:
        if item.get("skipped"):
            print(f"  {item['intent_name']}: SKIPPED ({item.get('skip_reason', '')})")
        else:
            print(f"  {item['intent_name']}: intent={item['intent_id']} "
                  f"agent={item['agent_id']} strategy={item['strategy_id']}")


if __name__ == "__main__":
    main()
