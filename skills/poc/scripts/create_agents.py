"""
POC intent / agent / strategy creation pipeline.

Creates all intents, tries to clone 3 fixed marketplace agents, creates 3
business strategies when those presets are available, and marks the remaining
intents as fallback_pending. If a preset agent is unavailable, the script writes
a recoverable state instead of raising, so the operator can ask whether to build
new agents from scratch or use substitute agents.

Usage:
  # poc business setup: create all intents + 3 cloned agents + 3 strategies
  python3 scripts/create_agents.py --mode poc

  # poc fallback link: bind a previously-built fallback agent to remaining intents
  python3 scripts/create_agents.py --mode poc --poc-fallback-agent-id 99999

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

STANDARD_INTENT_NAMES = [
    "Pre-Sales Inquiry",
    "Invoices",
    "Order Issues",
    "Logistics Issues",
    "Package issues",
    "Product issues",
    "Return and exchange",
]


# POC 固定绑定：每个 binding 把若干 L1 意图绑到同一个广场 agent（按 squareAgent_id）。
# 不在任何 binding 中的意图，全部走兜底策略（由 --poc-fallback-agent-id 阶段绑定）。
POC_AGENT_BINDINGS = [
    {
        "name": "Package_Logistics",
        "intents": ["Package issues", "Logistics Issues"],
        "square_agent_id": 38433,
    },
    {
        "name": "PreSales",
        "intents": ["Pre-Sales Inquiry"],
        "square_agent_id": 38429,
    },
    {
        "name": "Product",
        "intents": ["Product issues"],
        "square_agent_id": 38428,
    },
]

POC_BUSINESS_INTENT_NAMES = {n for b in POC_AGENT_BINDINGS for n in b["intents"]}

# 兜底策略的优先级（数值越大越后匹配）。业务策略默认 0，兜底设大避免抢匹配。
POC_FALLBACK_STRATEGY_PRIORITY = 999


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

    POC 按固定 squareAgent_id 复制广场 agent，取代"查广场→按名字匹配"。
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
    """N 个意图 → 1 个 agent 的策略（rules.values 多值）。POC 模式专用。"""
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


# ── POC handlers ──────────────────────────────────────────────────────────────

def _run_poc_business(
    solvea: SolveaClient,
    all_intents: list,
    run_id: str,
    dry_run: bool = False,
) -> None:
    """POC 业务阶段：建全部意图 + 克隆 3 个固定广场 agent + 建 3 条业务策略。

    其余意图标 fallback_pending，等 agent-builder 的 chatflow 能力建好兜底 agent 后回调
    `_run_poc_fallback_link` 绑定兜底策略。
    """
    creation_log = []
    intent_name_to_id: dict = {}
    existing_by_name = {}
    if not dry_run:
        existing_by_name = {
            item.get("name"): item
            for item in _intent_items(solvea.list_intents())
            if isinstance(item, dict) and item.get("name") and (item.get("id") or item.get("intentId"))
        }

    print(f"\n[poc.business] Step 1/3 — create {len(all_intents)} intents")
    for intent in all_intents:
        name = intent["name"]
        intent_result = create_l1_intent(
            solvea,
            intent,
            dry_run=dry_run,
            existing_by_name=existing_by_name,
        )
        intent_id = str(intent_result.get("id")) if intent_result else f"dry_{name}"
        intent_name_to_id[name] = intent_id
        creation_log.append({
            "intent_name": name,
            "intent_id": intent_id,
            "agent_id": None,
            "strategy_id": None,
            "binding": None,
            "fallback_pending": True,
        })

    print(f"\n[poc.business] Step 2/3 — clone {len(POC_AGENT_BINDINGS)} marketplace agents + create business strategies")
    preset_agent_errors = []
    for binding in POC_AGENT_BINDINGS:
        bname = binding["name"]
        target_intent_names = binding["intents"]
        square_id = binding["square_agent_id"]
        bound_intent_ids = [intent_name_to_id[n] for n in target_intent_names if n in intent_name_to_id]
        missing = [n for n in target_intent_names if n not in intent_name_to_id]
        if missing:
            print(f"[poc.business] WARNING binding '{bname}': intents not created: {missing}; skipping binding")
            continue
        if not bound_intent_ids:
            print(f"[poc.business] WARNING binding '{bname}': no intents to bind; skipping")
            continue

        if dry_run:
            print(f"[dry-run] copyAgent(square_id={square_id}) for binding '{bname}'")
            agent_id = f"dry_agent_{bname}"
        else:
            try:
                agent_id = copy_marketplace_agent_by_id(solvea, square_id)
            except Exception as exc:
                preset_agent_errors.append({
                    "binding": bname,
                    "square_agent_id": square_id,
                    "intent_names": target_intent_names,
                    "intent_ids": bound_intent_ids,
                    "error": str(exc),
                })
                print(
                    f"[poc.business] PRESET_AGENT_MISSING binding={bname} "
                    f"square_agent_id={square_id}: {exc}"
                )
                break

        if preset_agent_errors:
            break

        strategy_result = create_strategy_for_intents(
            solvea, bound_intent_ids, agent_id, bname, priority=0, dry_run=dry_run
        )
        strategy_id = str(strategy_result.get("id")) if strategy_result else f"dry_strategy_{bname}"

        for item in creation_log:
            if item["intent_name"] in target_intent_names:
                item["agent_id"] = agent_id
                item["strategy_id"] = strategy_id
                item["binding"] = bname
                item["fallback_pending"] = False

    if preset_agent_errors:
        fallback_pending = [item for item in creation_log if item["fallback_pending"]]
        fallback_pending_intent_ids = [item["intent_id"] for item in fallback_pending]
        print(
            f"\n[poc.business] Step 3/3 — preset agent unavailable; "
            f"{len(fallback_pending)} intent(s) remain pending"
        )

        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = str(OUTPUTS_DIR / f"created_{timestamp()}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "intents": creation_log,
                "mode": "poc",
                "run_id": run_id,
                "fallback_pending_intent_ids": fallback_pending_intent_ids,
                "fallback_strategy": None,
                "preset_agent_errors": preset_agent_errors,
                "next_action": (
                    "Ask the user whether to build new CHAT_FLOW business agents "
                    "from scratch or use substitute existing agents, then continue "
                    "with agent-builder or an explicit agent mapping."
                ),
            }, f, ensure_ascii=False, indent=2)

        state = _read_state()
        state.update({
            "status": "preset_agent_missing",
            "mode": "poc",
            "created_log_path": log_path,
            "preset_agent_errors": preset_agent_errors,
            "updated_at": timestamp(),
        })
        _write_state(state)

        print(f"\n[poc.business] Recoverable stop. Log → {log_path}")
        print("[poc.business] Do not report this as a hard system blocker.")
        print("[poc.business] Ask the user to choose one option:")
        print("  1. Build new CHAT_FLOW business agents from scratch for the missing preset binding(s).")
        print("  2. Use existing substitute agent id(s) for the affected business binding(s).")
        print(f"[poc.business] Pending intent IDs ({len(fallback_pending_intent_ids)}): {fallback_pending_intent_ids}")
        return

    fallback_pending = [item for item in creation_log if item["fallback_pending"]]
    fallback_pending_intent_ids = [item["intent_id"] for item in fallback_pending]
    print(f"\n[poc.business] Step 3/3 — write log; {len(fallback_pending)} intent(s) pending fallback binding")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = str(OUTPUTS_DIR / f"created_{timestamp()}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "intents": creation_log,
            "mode": "poc",
            "run_id": run_id,
            "fallback_pending_intent_ids": fallback_pending_intent_ids,
            "fallback_strategy": None,
        }, f, ensure_ascii=False, indent=2)

    state = _read_state()
    state.update({
        "status": "created",
        "mode": "poc",
        "created_log_path": log_path,
        "updated_at": timestamp(),
    })
    _write_state(state)

    # Report SYSTEM intents that could be disabled.
    if not dry_run:
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

    print(f"\n[poc.business] Done. Log → {log_path}")
    print(f"[poc.business] Summary:")
    for item in creation_log:
        if item["fallback_pending"]:
            print(f"  {item['intent_name']}: intent={item['intent_id']} (fallback-pending)")
        else:
            print(f"  {item['intent_name']}: intent={item['intent_id']} "
                  f"agent={item['agent_id']} strategy={item['strategy_id']} binding={item['binding']}")
    print(f"\n[poc.business] Next step: build a fallback chatflow agent with agent-builder, then re-invoke:")
    print(f"  python3 /skills/poc/scripts/create_agents.py --mode poc --poc-fallback-agent-id <new_agent_id>")
    print(f"[poc.business] Pending intent IDs ({len(fallback_pending_intent_ids)}): {fallback_pending_intent_ids}")


def _run_poc_fallback_link(
    solvea: SolveaClient,
    log_path: str,
    fallback_agent_id: str,
    dry_run: bool = False,
) -> None:
    """POC 兜底阶段：把 fallback_pending 的意图绑定到 chatflow 兜底 agent。"""
    if not log_path or not os.path.exists(log_path):
        raise FileNotFoundError(
            f"created_log not found (state.created_log_path={log_path}). "
            "Run `--mode poc` business stage first."
        )
    with open(log_path) as f:
        log_data = json.load(f)

    if log_data.get("mode") != "poc":
        raise RuntimeError(f"created_log mode is {log_data.get('mode')!r}, expected 'poc'.")
    if log_data.get("fallback_strategy"):
        existing = log_data["fallback_strategy"]
        print(f"[poc.fallback] WARNING fallback strategy already linked: "
              f"agent={existing.get('agent_id')} strategy={existing.get('strategy_id')}")
        print(f"[poc.fallback] Re-binding (will create another strategy). Disable the old one manually if needed.")

    pending_ids = log_data.get("fallback_pending_intent_ids") or []
    if not pending_ids:
        print("[poc.fallback] No fallback_pending_intent_ids in log — nothing to bind.")
        return

    print(f"[poc.fallback] Binding {len(pending_ids)} intent(s) → agent {fallback_agent_id} "
          f"(priority={POC_FALLBACK_STRATEGY_PRIORITY})")
    strategy_result = create_strategy_for_intents(
        solvea, pending_ids, str(fallback_agent_id), name="Fallback",
        priority=POC_FALLBACK_STRATEGY_PRIORITY, dry_run=dry_run,
    )
    strategy_id = str(strategy_result.get("id")) if strategy_result else "dry_strategy_Fallback"

    log_data["fallback_strategy"] = {
        "agent_id": str(fallback_agent_id),
        "strategy_id": strategy_id,
        "intent_ids": pending_ids,
        "name": "Route_Fallback",
        "priority": POC_FALLBACK_STRATEGY_PRIORITY,
    }
    for item in log_data.get("intents", []):
        if item.get("intent_id") in pending_ids:
            item["strategy_id"] = strategy_id
            item["agent_id"] = str(fallback_agent_id)
            item["binding"] = "Fallback"
            item["fallback_pending"] = False

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    state = _read_state()
    state.update({
        "status": "created",
        "mode": "poc",
        "created_log_path": log_path,
        "updated_at": timestamp(),
    })
    _write_state(state)

    print(f"\n[poc.fallback] Done. Strategy id={strategy_id}; log updated → {log_path}")


def _load_agent_map(path: str) -> dict:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"custom agent map not found: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and isinstance(data.get("bindings"), dict):
        data = data["bindings"]
    if not isinstance(data, dict):
        raise ValueError("custom agent map must be a JSON object or {'bindings': {...}}")
    return {str(k): str(v) for k, v in data.items() if v not in (None, "")}


def _run_poc_custom_agent_link(
    solvea: SolveaClient,
    log_path: str,
    map_path: str,
    dry_run: bool = False,
) -> None:
    """把用户确认的新建/替代业务 Agent 按 POC binding 写入策略。"""
    if not log_path or not os.path.exists(log_path):
        raise FileNotFoundError(
            f"created_log not found (state.created_log_path={log_path}). "
            "Run `--mode poc` business stage first."
        )
    with open(log_path, encoding="utf-8") as f:
        log_data = json.load(f)
    if log_data.get("mode") != "poc":
        raise RuntimeError(f"created_log mode is {log_data.get('mode')!r}, expected 'poc'.")

    agent_map = _load_agent_map(map_path)
    intents_by_name = {
        item.get("intent_name"): item
        for item in log_data.get("intents", [])
        if item.get("intent_name") and item.get("intent_id")
    }
    linked = []
    for binding in POC_AGENT_BINDINGS:
        bname = binding["name"]
        agent_id = agent_map.get(bname)
        if not agent_id:
            continue
        target_items = [intents_by_name[name] for name in binding["intents"] if name in intents_by_name]
        intent_ids = [item["intent_id"] for item in target_items]
        if not intent_ids:
            print(f"[poc.custom] WARNING binding '{bname}' has no matching created intents; skipped")
            continue
        print(f"[poc.custom] Binding {bname}: intents={intent_ids} → agent {agent_id}")
        strategy_result = create_strategy_for_intents(
            solvea,
            intent_ids,
            str(agent_id),
            name=bname,
            priority=0,
            dry_run=dry_run,
        )
        strategy_id = str(strategy_result.get("id")) if strategy_result else f"dry_strategy_{bname}"
        for item in target_items:
            item["agent_id"] = str(agent_id)
            item["strategy_id"] = strategy_id
            item["binding"] = bname
            item["fallback_pending"] = False
            item["custom_agent"] = True
        linked.append({"binding": bname, "agent_id": str(agent_id), "intent_ids": intent_ids, "strategy_id": strategy_id})

    if not linked:
        raise ValueError(
            "custom agent map did not match any POC binding. "
            f"Expected keys: {[b['name'] for b in POC_AGENT_BINDINGS]}"
        )

    fallback_pending = [item for item in log_data.get("intents", []) if item.get("fallback_pending")]
    log_data["fallback_pending_intent_ids"] = [item["intent_id"] for item in fallback_pending]
    log_data["custom_agent_strategies"] = [*(log_data.get("custom_agent_strategies") or []), *linked]
    log_data["next_action"] = "Build/link fallback agent for remaining fallback_pending_intent_ids, then continue KB/test."

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

    state = _read_state()
    state.update({
        "status": "created",
        "mode": "poc",
        "created_log_path": log_path,
        "updated_at": timestamp(),
    })
    _write_state(state)
    print(f"\n[poc.custom] Done. Linked {len(linked)} business binding(s); log updated → {log_path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Create intents + copy marketplace agents + strategy routing"
    )
    parser.add_argument("--mode", choices=["poc"], default="poc",
                        help="POC only: create all intents, clone 3 fixed marketplace agents, "
                             "build 3 business strategies, expose fallback_pending_intent_ids "
                             "for agent-builder chatflow handoff.")
    parser.add_argument("--select", default=None,
                        help="DEPRECATED — ignored in all modes (all intents are now created).")
    parser.add_argument("--poc-fallback-agent-id", dest="poc_fallback_agent_id", default=None,
                        help="POC fallback-link stage: bind a previously-built chatflow agent "
                             "to all fallback_pending intents. Must run after `--mode poc` "
                             "business stage. Requires --mode poc.")
    parser.add_argument("--custom-agent-map", default=None,
                        help="POC recovery stage: JSON map of POC binding name to custom/existing agent id, "
                             "for example {'Package_Logistics': 2641, 'PreSales': 2642, 'Product': 2643}.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--disable-system", action="store_true",
                        help="Disable active SYSTEM intents not matching created intent names")
    args = parser.parse_args()

    # ── Early args sanity ──────────────────────────────────────────────────────
    if args.poc_fallback_agent_id and args.mode != "poc":
        print(f"[main] ERROR: --poc-fallback-agent-id requires --mode poc (got {args.mode!r}).")
        sys.exit(2)
    if args.custom_agent_map and args.poc_fallback_agent_id:
        print("[main] ERROR: --custom-agent-map and --poc-fallback-agent-id are separate stages.")
        sys.exit(2)
    if args.select:
        print(f"[main] WARNING: --select is deprecated and ignored (mode={args.mode}). "
              "All intents will be created.")

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

    if args.mode == "poc" and args.poc_fallback_agent_id:
        solvea = SolveaClient()
        if not args.dry_run:
            print(f"[main] project_id={solvea.project_id}")
        _run_poc_fallback_link(
            solvea,
            log_path=state.get("created_log_path"),
            fallback_agent_id=args.poc_fallback_agent_id,
            dry_run=args.dry_run,
        )
        return

    if args.mode == "poc" and args.custom_agent_map:
        solvea = SolveaClient()
        if not args.dry_run:
            print(f"[main] project_id={solvea.project_id}")
        _run_poc_custom_agent_link(
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

    # ── 兜底补全固定 7 个意图 ─────────────────────────────────────────────────
    # 客户数据里如果没有某个固定意图的样本，classify.py 不会产生它；
    # POC 要建全部 7 个标准意图，这里强制补入缺失的（fallback-link 阶段跳过）。
    found_names = {i["name"] for i in all_intents}
    for fixed_name in STANDARD_INTENT_NAMES:
        if fixed_name not in found_names:
            print(f"[main] '{fixed_name}' missing from classification results → added from fixed taxonomy")
            all_intents.append({"name": fixed_name, "definition": ""})

    # ── Feature pre-flight ────────────────────────────────────────────────────
    if not args.dry_run:
        check_and_enable_intent_feature(solvea)    # 建意图前
        check_and_enable_variable_feature(solvea)  # copyAgent 前

    # ── POC business stage ─────────────────────────────────────────────────────
    if args.mode == "poc":
        _run_poc_business(
            solvea,
            all_intents=all_intents,
            run_id=run_id,
            dry_run=args.dry_run,
        )
        return


if __name__ == "__main__":
    main()
