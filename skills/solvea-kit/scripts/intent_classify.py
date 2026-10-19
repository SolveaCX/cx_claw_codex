"""
Intent Classification — shared Solvea Kit capability.

Business inputs: TAXONOMY (L1 → predefined L2 names) + DISAMBIGUATION_RULES
System generates: L1/L2 definitions, new L2s (max 3/L1 capped at 5 total), new L1s (max 3)

Modes:
  --xlsx: Full LLM classification of complaint data
  --no-excel: Generate synthetic results from fixed TAXONOMY, no LLM needed

Usage:
  python3 scripts/intent_classify.py --owner poc --xlsx mounted/chat-files/user/complaints.xlsx [--max-rows 2000]
  python3 scripts/intent_classify.py --owner delivery --no-excel
"""

import os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *

import json, re, argparse, html as html_lib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import openpyxl
from bs4 import BeautifulSoup
from openai import OpenAI


# ── Business inputs ───────────────────────────────────────────────────────────

TAXONOMY: dict[str, list[str]] = {
    "Pre-Sales Inquiry":   ["Product Recommendation", "Discount Inquiry", "Price Inquiry", "Stock Availability", "Payment Issues"],
    "Invoices":            ["Request Invoice", "Modify Invoice Information"],
    "Order Issues":        ["Modify Order", "Check Order Status", "Cancel Order"],
    "Logistics Issues":    ["Track Shipment", "Shipping Exception"],
    "Package issues":      ["Missing Items", "Wrong Items Received", "Damaged Package"],
    "Product issues":      ["Product Usage", "Physical Damage", "Non-Physical Issues"],
    "Return and exchange": [],
}

FIXED_DESCRIPTIONS: dict[str, str] = {
    "Pre-Sales Inquiry":   "Covers all pre-purchase consultations and issues, including product recommendations, discount inquiries, price inquiries, stock availability checks, payment method questions, payment process troubleshooting, and other related pre-sales needs before placing an order.",
    "Invoices":            "Includes requests for invoice issuance, inquiries about invoice status, modifications to invoice information (such as recipient name, tax ID, billing address), and other consultation or problems related to invoices.",
    "Order Issues":        "Covers order modification requests (e.g., changing shipping address, adjusting product quantity), inquiries about order details (order status, order confirmation, order history), order cancellation requests, and other consultation or problems related to orders.",
    "Logistics Issues":    "Includes tracking inquiries (requesting logistics tracking number, checking shipping progress), reports of logistics abnormalities (delayed delivery, stuck in transit, incorrect shipping route), and other logistics-related problems.",
    "Package issues":      "Covers issues such as missing items, missing manual, incomplete packages, lost packages, wrong items delivered (mismatched with order), package damage (external or internal damage to the package), and other package-related consultations or problems.",
    "Product issues":      "Includes product usage questions (operation guidance, function inquiries, usage precautions), physical damage to products (non-packaging-related product damage), non-physical product quality issues (performance failures, functional defects, quality inconsistencies with descriptions), and other product-related consultations or problems.",
    "Return and exchange": "Covers customer requests for returns, refunds, or exchanges. Note: if the customer explicitly mentions product quality issues as the reason, classify under Product issues instead. This intent applies to return/refund/exchange requests for non-quality reasons (e.g., wrong size, change of mind, incompatible needs).",
}

DISAMBIGUATION_RULES: list[str] = [
    "If a message involves both order status checking AND logistics tracking → classify as Logistics Issues (not Order Issues)",
    "If a message involves both Physical Damage (Product issues) AND Damaged Package (Package issues) → classify as Package issues / Damaged Package",
    "If a message involves both Product issues AND Return and exchange → classify as Product issues",
    "Return and exchange has the lowest priority: if ANY other L1 intent is present, classify as that other intent instead of Return and exchange",
]


# ── Constants ─────────────────────────────────────────────────────────────────

BATCH_SIZE = 40
MAX_WORKERS = 5
MAX_NEW_L1 = 3
MAX_NEW_L2_PER_L1 = 3
MAX_L2_TOTAL = 5          # predefined + new L2s capped at 5 per L1
OTHER_THRESHOLD = 0.10
MAX_RESEARCH_ROUNDS = 5
_checkpoint_lock = threading.Lock()
SERVICE_MANAGED_MODEL = "server-managed"


# ── Token tracking ────────────────────────────────────────────────────────────

class TokenTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._usage: dict = {}

    def record(self, model: str, input_tokens: int, output_tokens: int):
        with self._lock:
            if model not in self._usage:
                self._usage[model] = {"input": 0, "output": 0, "calls": 0}
            self._usage[model]["input"] += input_tokens
            self._usage[model]["output"] += output_tokens
            self._usage[model]["calls"] += 1

    def summary(self) -> dict:
        result = {}
        for model, usage in self._usage.items():
            result[model] = {
                "calls": usage["calls"],
                "input_tokens": usage["input"],
                "output_tokens": usage["output"],
                "total_tokens": usage["input"] + usage["output"],
            }
        return result

    def print_summary(self):
        pass  # token 用量不打印到 stdout（写入 results JSON meta 里）


_tracker = TokenTracker()


class _MessageResponse:
    def __init__(self, text: str):
        self.content = [type("Content", (), {"text": text})()]


def _api_call(client: OpenAI, model: str, **kwargs):
    messages = []
    if kwargs.get("system"):
        messages.append({"role": "system", "content": kwargs["system"]})
    messages.extend(kwargs.get("messages") or [])
    resp = client.chat.completions.create(
        # /internal/openai/v1 overwrites this sentinel with the service-managed model.
        model=SERVICE_MANAGED_MODEL,
        max_tokens=kwargs.get("max_tokens"),
        messages=messages,
        temperature=0,
    )
    if getattr(resp, "usage", None):
        _tracker.record(SERVICE_MANAGED_MODEL, resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0)
    return _MessageResponse((resp.choices[0].message.content or "").strip())


# ── HTML helpers ──────────────────────────────────────────────────────────────

_FOOTER_MARKERS = [
    "copyright 20", "© 20",
    "was this e-mail helpful", "was this email helpful",
    "all rights reserved",
    "to unsubscribe", "opt-out here", "opt out here",
    "if you'd rather not receive", "if you would rather not receive",
    "you are receiving this",
]

def has_html(text: str) -> bool:
    return bool(re.search(r'<[a-zA-Z][^>]{0,100}>', text))

def _strip_email_footer(text: str) -> str:
    if len(text) < 400:
        return text
    low = text.lower()
    cut = len(text)
    for marker in _FOOTER_MARKERS:
        pos = low.find(marker)
        if 0 < pos < cut:
            cut = pos
    return text[:cut].strip()

def clean_message(text: str) -> str:
    text = str(text or "").strip()
    text = html_lib.unescape(text)
    if has_html(text):
        soup = BeautifulSoup(text, 'html.parser')
        for tag in soup(["style", "script", "head", "meta", "link"]):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
    text = re.sub(r'\s+', ' ', text).strip()
    return _strip_email_footer(text)




# ── Excel loader ──────────────────────────────────────────────────────────────

def load_xlsx(path: str, max_rows: int = 0,
              messages_col: str | None = None,
              title_col: str | None = None) -> list:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Excel file is empty")
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]

    def _find_col(name: str | None, required: bool = False) -> int | None:
        if name is None:
            return None
        if name in headers:
            return headers.index(name)
        available = ", ".join(h for h in headers if h)
        raise ValueError(f"Column '{name}' not found. Available: {available}")

    if not messages_col:
        available = ", ".join(h for h in headers if h)
        raise ValueError(f"--messages-col is required. Available columns: {available}")

    idx_messages = _find_col(messages_col, required=True)
    idx_title = _find_col(title_col)
    items = []
    for i, row in enumerate(rows[1:], start=1):
        if max_rows and i > max_rows:
            break
        messages_raw = str(row[idx_messages]) if row[idx_messages] is not None else ""
        text_clean = clean_message(messages_raw)
        if not text_clean:
            continue
        title_val = str(row[idx_title]).strip() if idx_title is not None and row[idx_title] else ""
        items.append({
            "id": str(i),
            "title": title_val,
            "text": text_clean,
            "messages": messages_raw,
        })
    return items


# ── Prompt builders ───────────────────────────────────────────────────────────

def _taxonomy_text() -> str:
    lines = []
    for l1, l2s in TAXONOMY.items():
        if l2s:
            lines.append(f"- {l1}: {', '.join(l2s)}")
        else:
            lines.append(f"- {l1}: (no predefined L2 — coin a specific 2-5 word name from the message content)")
    return "\n".join(lines)

def _rules_text() -> str:
    return "\n".join(f"{i+1}. {r}" for i, r in enumerate(DISAMBIGUATION_RULES))

def _valid_l1_list() -> str:
    return ", ".join(f'"{k}"' for k in TAXONOMY) + ', "Other"'

CLASSIFY_SYSTEM = f"""You are an e-commerce customer support intent classifier.
Output ONLY a JSON array. No markdown, no explanation, no code fences.

## Intent Taxonomy
{_taxonomy_text()}

## Disambiguation Rules (apply when a message matches multiple intents)
{_rules_text()}

## Output format for each item:
{{"id": "<id>", "l1": "<MUST be one of the allowed values below>", "l2": "<REQUIRED: exact predefined L2 name, or 2-5 word descriptive name — NEVER empty>", "new_l2_hint": "<only when l2 is newly coined>", "new_l1_hint": "<only when l1='Other' — topic in 2-5 words>"}}

## Allowed l1 values (copy EXACTLY, no variations):
{_valid_l1_list()}

## Rules:
- l1 MUST be copied verbatim from the allowed list — do NOT paraphrase or invent new names
- Use "Other" only when the message falls completely outside all taxonomy categories
- l2 MUST be non-empty for EVERY item — use predefined L2 names when they fit; otherwise coin a 2-5 word name
- new_l2_hint: include ONLY for newly coined l2 names
- new_l1_hint: include ONLY when l1="Other"; describe a genuine customer need, not data characteristics
- Apply disambiguation rules before assigning l1
"""

DEFINITION_PROMPT = """You are writing intent definitions for an e-commerce AI customer support routing system.
These definitions determine how incoming messages are routed — they must precisely reflect the actual customer requests in the samples.

## L1 Intent: {l1_name}
## Standard base description (use as starting point, refine based on data):
{base_description}

## Predefined L2 sub-intents: {predefined_l2_json}
## Newly discovered L2 sub-intents (from data): {new_l2_json}

## Sample messages classified under this intent:
{samples_text}

Your task: refine the base description into a precise L1 definition that reflects the actual patterns in the samples above.
Keep the core scope of the base description, but adjust wording to match the specific scenarios visible in the data.

Output ONLY JSON (no markdown):
{{
  "l1_def": "One sentence (≤30 words) — start from the base description, adjust to reflect actual customer patterns in the samples",
  "l2_defs": {{
    "<l2_name>": "One sentence (≤20 words) based on actual sample patterns — describe the specific customer request, not a generic category label"
  }},
  "new_l2_normalized": {{
    "<newly_coined_l2>": "<closest predefined L2 name>"
  }}
}}

Rules:
- l1_def must preserve the intent scope from the base description; only adjust emphasis or wording based on data
- l2_defs must include ALL l2 names listed above (predefined + newly discovered)
- new_l2_normalized: for each newly coined L2, map to its closest predefined L2 if semantically similar; omit if genuinely distinct
- Definitions MUST reference specific scenarios from the samples where possible
- Avoid generic filler like "issues with", "problems related to", "requests about"
"""

CLUSTER_SYSTEM = """You are an e-commerce customer support intent design expert.
Given complaint groups (each with a topic hint, count, and samples), merge them into coherent L1 intent categories.
Output ONLY a JSON array, no markdown:
[{"merged_hints": ["hint1", "hint2"], "name": "Intent Name", "desc": "One sentence description"}]

## Quality bar for new intents:
- Prefer intents with a clear, actionable customer need that a support agent can resolve differently from existing intents
- Merge hints that describe the same underlying customer problem
- If a group's samples are entirely auto-generated system messages with zero customer question, merge it into "Other"

Rules:
- Every input hint must appear in exactly one group's "merged_hints"
- Names: 2-5 words, title case, English, concise and professional
- Merge hints describing the same customer problem type
- Do NOT create intents that overlap with the known intents listed
- Use "Other" group for noise, ambiguous items, and anything that fails the valid intent criteria above
"""

SPLIT_SYSTEM = """You are an e-commerce customer support expert.
Analyze these complaint texts and group them into distinct intent categories.
Output ONLY JSON (no markdown):
[{"name": "Intent Name", "desc": "One sentence description", "indices": [0, 2, 5]}]

Rules:
- name: 2-5 words, title case, English
- Every index 0..N-1 must appear in exactly ONE group
- Each group needs at least 2 complaints
- Use "Other" for items that don't fit any clear pattern
- Target: 2-8 distinct groups
"""



# ── Stage 2: Cluster "Other" items into new L1s ───────────────────────────────

def _split_into_groups(items: list, known_names: list, client) -> tuple:
    sample = items[:80]
    lines = "\n".join(f"[{i}] {it.get('text', '')[:200]}" for i, it in enumerate(sample))
    user_msg = f"Known intents (do NOT duplicate): {', '.join(known_names)}\n\nComplaints:\n{lines}"
    try:
        resp = _api_call(client,
            SERVICE_MANAGED_MODEL,
            max_tokens=2000,
            system=SPLIT_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        groups = _parse_json_response(resp.content[0].text)
        idx_to_name = {idx: g["name"]
                       for g in groups for idx in g.get("indices", [])
                       if 0 <= idx < len(sample)}
        cluster_items: dict = defaultdict(list)
        for i, item in enumerate(sample):
            cluster_items[idx_to_name.get(i, "Other")].append(item)
        for item in items[len(sample):]:
            cluster_items["Other"].append(item)
        clusters, seen = [], set()
        for g in groups:
            n = g["name"]
            if n not in seen and cluster_items.get(n):
                clusters.append({"merged_hints": [n], "name": n, "desc": g.get("desc", "")})
                seen.add(n)
        if cluster_items.get("Other") and "Other" not in seen:
            clusters.append({"merged_hints": ["Other"], "name": "Other", "desc": "Uncategorized complaints"})
        return clusters, dict(cluster_items)
    except Exception as e:
        print(f"  [split] failed: {e}")
        return ([{"merged_hints": ["Other"], "name": "Other", "desc": "Uncategorized"}],
                {"Other": items})


def cluster_new_intents(other_items: list, known_names: list, client, max_new: int = 0) -> tuple:
    if not other_items:
        return [], {}
    hint_groups: dict = defaultdict(list)
    for it in other_items:
        hint = (it.get("new_l1_hint") or "").strip() or "Other"
        hint_groups[hint].append(it)
    if len(hint_groups) == 1:
        print("  [cluster] single-hint group, switching to split-by-content mode")
        return _split_into_groups(other_items, known_names, client)
    groups_data = [
        {"hint": hint, "count": len(its),
         "samples": [i.get("text", "")[:200] for i in its[:3]]}
        for hint, its in sorted(hint_groups.items(), key=lambda x: -len(x[1]))
    ]
    user_msg = (
        f"Known L1 intents (do NOT overlap): {', '.join(known_names)}\n\n"
        f"Complaint groups to merge:\n{json.dumps(groups_data, ensure_ascii=False, indent=2)}\n\n"
        f"Output merged L1 intents as JSON array."
        + (f"\n\nIMPORTANT: Produce at most {max_new} clusters total." if max_new > 0 else "")
    )
    for attempt in range(2):
        try:
            resp = _api_call(client,
                SERVICE_MANAGED_MODEL,
                max_tokens=2000,
                system=CLUSTER_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            clusters = _parse_json_response(resp.content[0].text)
            if isinstance(clusters, list) and clusters:
                covered = {h for c in clusters for h in c.get("merged_hints", [])}
                missing = set(hint_groups.keys()) - covered
                if missing:
                    clusters.append({"merged_hints": list(missing), "name": "Other", "desc": "Uncategorized"})
                hint_to_name = {h: c["name"] for c in clusters for h in c.get("merged_hints", [])}
                cluster_items: dict = defaultdict(list)
                for it in other_items:
                    hint = (it.get("new_l1_hint") or "").strip() or "Other"
                    cluster_items[hint_to_name.get(hint, hint)].append(it)
                return clusters, dict(cluster_items)
        except Exception as e:
            print(f"  [cluster] attempt {attempt+1} error: {e}")
    print("  [cluster] fallback: everything as Other")
    return ([{"merged_hints": list(hint_groups.keys()), "name": "Other", "desc": "Uncategorized"}],
            {"Other": other_items})

# ── JSON response parser ──────────────────────────────────────────────────────

def _parse_json_response(raw: str):
    text = raw.strip()
    m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if m:
        text = m.group(1).strip()
    else:
        m = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
        if m:
            text = m.group(1)
    return json.loads(text)


# ── Stage 1: Classification ───────────────────────────────────────────────────

def validate_classify_response(raw: str) -> list | None:
    valid_l1s = set(TAXONOMY.keys()) | {"Other"}
    try:
        items = _parse_json_response(raw)
    except Exception:
        return None
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            return None
        if not {"id", "l1", "l2"}.issubset(item.keys()):
            return None
        if item["l1"] not in valid_l1s:
            item["l1"] = "Other"
    return items


def classify_batch(items: list, client) -> list:
    def _item_payload(it):
        payload = {"id": it["id"], "text": it["text"][:1500]}
        if it.get("title"):
            payload["title"] = it["title"]
        return payload

    user_msg = "Classify these customer messages:\n" + json.dumps(
        [_item_payload(it) for it in items],
        ensure_ascii=False,
    )
    for attempt in range(2):
        try:
            resp = _api_call(client,
                SERVICE_MANAGED_MODEL,
                max_tokens=2048,
                system=CLASSIFY_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            result = validate_classify_response(resp.content[0].text)
            if result is not None:
                return result
            print(f"  [classify] attempt {attempt+1} parse failed, retrying...")
        except Exception as e:
            print(f"  [classify] attempt {attempt+1} API error: {e}")
    print(f"  [classify] double failure, marking as Other")
    return [{"id": it["id"], "l1": "Other", "l2": "General", "new_l1_hint": "unknown"} for it in items]


# ── Checkpoint ────────────────────────────────────────────────────────────────

def load_checkpoint(results_path: str) -> dict:
    if not os.path.exists(results_path):
        return {"meta": {}, "raw_items": {}}
    with open(results_path) as f:
        return json.load(f)

def save_item(results_path: str, checkpoint: dict, item_id: str, classified: dict):
    with _checkpoint_lock:
        checkpoint.setdefault("raw_items", {})[item_id] = classified
        tmp = results_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(checkpoint, f, ensure_ascii=False, indent=2)
        os.replace(tmp, results_path)


# ── Stage 2: Definition generation (one call per L1) ─────────────────────────

def _generate_l1_defs(l1_name: str, predefined_l2s: list, new_l2s: list,
                      samples: list, client) -> dict:
    prompt = DEFINITION_PROMPT.format(
        l1_name=l1_name,
        base_description=FIXED_DESCRIPTIONS.get(l1_name, f"Customer messages related to {l1_name}."),
        predefined_l2_json=json.dumps(predefined_l2s),
        new_l2_json=json.dumps(new_l2s),
        samples_text="\n".join(f"- {s[:200]}" for s in samples[:15]),
    )
    try:
        resp = _api_call(client,
            SERVICE_MANAGED_MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_response(resp.content[0].text)
    except Exception as e:
        print(f"  [defs] failed for '{l1_name}': {e}")
        return {
            "l1_def": FIXED_DESCRIPTIONS.get(l1_name, f"Customer messages related to {l1_name}."),
            "l2_defs": {l2: f"Issues related to {l2}." for l2 in predefined_l2s + new_l2s},
            "new_l2_normalized": {},
        }


# ── Stage 3: Assemble results ─────────────────────────────────────────────────

def _build_intent_entry(name: str, items: list, l1_def: str, l2_defs: dict,
                        is_new: bool, grand_total: int) -> dict:
    predefined = set(TAXONOMY.get(name, []))
    max_sub = min(len(predefined) + MAX_NEW_L2_PER_L1, MAX_L2_TOTAL)
    sub_groups: dict = defaultdict(list)
    for it in items:
        l2 = it.get("l2") or ""
        if l2:
            sub_groups[l2].append(it.get("text", ""))
    total = len(items)
    sorted_subs = sorted(sub_groups.items(), key=lambda x: -len(x[1]))
    top_subs = sorted_subs[:max_sub]
    overflow_subs = sorted_subs[max_sub:]
    sub_intents = []
    for sub_name, sub_samps in top_subs:
        sub_count = len(sub_samps)
        sub_intents.append({
            "name": sub_name,
            "definition": l2_defs.get(sub_name, ""),
            "count": sub_count,
            "pct": round(100 * sub_count / total, 1),
            "samples": sub_samps[:5],
            "is_new": sub_name not in predefined,
        })
    if overflow_subs:
        overflow_count = sum(len(s) for _, s in overflow_subs)
        overflow_samples = [t for _, samps in overflow_subs for t in samps][:5]
        sub_intents.append({
            "name": "Other", "definition": "", "count": overflow_count,
            "pct": round(100 * overflow_count / total, 1),
            "samples": overflow_samples, "is_new": False,
        })
    no_l2_count = sum(1 for it in items if not it.get("l2"))
    if no_l2_count:
        for si in sub_intents:
            if si["name"] == "Other":
                si["count"] += no_l2_count
                si["pct"] = round(100 * si["count"] / total, 1)
                break
        else:
            sub_intents.append({
                "name": "Other", "definition": "", "count": no_l2_count,
                "pct": round(100 * no_l2_count / total, 1),
                "samples": [], "is_new": False,
            })
    return {
        "name": name, "definition": l1_def,
        "count": total, "pct": round(100 * total / grand_total, 1) if grand_total else 0.0,
        "sub_intents": sub_intents,
        "samples": [it.get("text", "") for it in items][:5],
        "is_new": is_new,
    }


def assemble_results(raw_items: dict, all_items: list, client,
                     run_id: str, items_path: str) -> dict:
    buckets: dict = defaultdict(list)
    for item in all_items:
        classified = raw_items.get(item["id"], {})
        l1 = classified.get("l1") or "Other"
        buckets[l1].append(dict(item, **classified))

    grand_total = len(all_items)
    if buckets.get("Other"):
        other_items = buckets.pop("Other")
        other_pct = len(other_items) / grand_total if grand_total else 0
        print(f"  [assemble] Other: {len(other_items)} ({other_pct*100:.1f}%) — clustering up to {MAX_NEW_L1} new L1s...")
        if MAX_NEW_L1 > 0:
            clusters, cluster_items = cluster_new_intents(other_items, list(TAXONOMY.keys()), client, max_new=MAX_NEW_L1)
            for cluster in clusters:
                name = cluster["name"]
                items_for_cluster = cluster_items.get(name, [])
                if name != "Other" and items_for_cluster:
                    buckets[name] = items_for_cluster
                    print(f"  [assemble] New L1 discovered: '{name}' ({len(items_for_cluster)} items)")
            if cluster_items.get("Other"):
                buckets["Other"] = cluster_items["Other"]
        else:
            buckets["Other"] = other_items

    # Generate definitions in parallel
    print("[assemble] Generating definitions...")
    l1_def_results: dict = {}

    def _def_task(l1_name):
        items = buckets[l1_name]
        predefined_l2s = TAXONOMY.get(l1_name, [])
        new_l2s = list({it.get("l2") or ""
                        for it in items
                        if (it.get("l2") or "") and (it.get("l2") or "") not in predefined_l2s} - {""})
        samples = [it.get("text", "") for it in items[:20]]
        return l1_name, _generate_l1_defs(l1_name, predefined_l2s, new_l2s, samples, client)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(_def_task, name): name for name in buckets if buckets[name]}
        for fut in as_completed(futs):
            name, result = fut.result()
            l1_def_results[name] = result

    known_entries = []
    new_entries = []
    ordered = [k for k in TAXONOMY if k in buckets]
    ordered += [k for k in buckets if k not in TAXONOMY]

    for l1_name in ordered:
        items = buckets.get(l1_name, [])
        if not items:
            continue
        defs = l1_def_results.get(l1_name, {})
        norm_map = defs.get("new_l2_normalized", {})
        if norm_map:
            for it in items:
                l2 = it.get("l2") or ""
                if l2 in norm_map:
                    it["l2"] = norm_map[l2]
        l1_def = defs.get("l1_def", FIXED_DESCRIPTIONS.get(l1_name, f"Customer messages related to {l1_name}."))
        l2_defs = defs.get("l2_defs", {})
        is_new = l1_name not in TAXONOMY
        entry = _build_intent_entry(l1_name, items, l1_def, l2_defs, is_new, grand_total)
        if is_new:
            new_entries.append(entry)
        else:
            known_entries.append(entry)

    total_classified = sum(e["count"] for e in known_entries + new_entries)

    # Save per-item detail for Excel export
    all_known_l1s = set(TAXONOMY.keys())
    item_rows = []
    for l1_name in ordered:
        items = buckets.get(l1_name, [])
        is_new_l1 = l1_name not in all_known_l1s
        predefined = set(TAXONOMY.get(l1_name, []))
        for it in items:
            l2 = it.get("l2") or ""
            item_rows.append({
                "id": it.get("id", ""),
                "title": it.get("title", ""),
                "first_message": it.get("first_message", "") or it.get("text", ""),
                "messages": it.get("messages", ""),
                "text": it.get("text", ""),
                "l1": l1_name, "l2": l2,
                "is_new_l1": is_new_l1,
                "is_new_l2": bool(l2 and l2 not in predefined),
            })
    with open(items_path, "w") as f:
        json.dump(item_rows, f, ensure_ascii=False, indent=2)
    print(f"[assemble] Items detail -> {items_path}")

    return {
        "meta": {
            "run_id": run_id,
            "total": grand_total, "classified": total_classified,
            "n_known": len(known_entries), "n_new": len(new_entries),
        },
        "intents": sorted(known_entries, key=lambda x: -x["count"]),
        "new_intents": sorted(new_entries, key=lambda x: -x["count"]),
    }


# ── No-excel mode: synthetic results from fixed TAXONOMY ─────────────────────

def generate_no_excel_results(run_id: str) -> dict:
    intents = []
    for name, l2s in TAXONOMY.items():
        sub_intents = [
            {"name": l2, "definition": "", "count": 0, "pct": 0.0, "samples": [], "is_new": False}
            for l2 in l2s
        ]
        intents.append({
            "name": name,
            "definition": FIXED_DESCRIPTIONS.get(name, ""),
            "count": 0, "pct": 0.0,
            "sub_intents": sub_intents,
            "samples": [], "is_new": False,
        })
    return {
        "meta": {
            "run_id": run_id,
            "total": 0, "classified": 0,
            "n_known": len(intents), "n_new": 0,
        },
        "intents": intents,
        "new_intents": [],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Shared intent classifier")
    parser.add_argument("--owner", choices=["poc", "delivery", "solvea-kit"], default="solvea-kit",
                        help="Business owner for workspace state/output paths")
    parser.add_argument("--xlsx", default=None, help="Path to complaints Excel file")
    parser.add_argument("--no-excel", action="store_true", help="Use fixed taxonomy, skip LLM classification")
    parser.add_argument("--max-rows", type=int, default=2000)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--title-col", default=None,
                        help="工单标题列名（可选）")
    parser.add_argument("--messages-col", default=None,
                        help="完整对话历史列名（必填，支持 JSON comments 数组或纯文本）")
    args = parser.parse_args()

    if not args.xlsx and not args.no_excel:
        parser.error("Must provide --xlsx <path> or --no-excel")
    if args.xlsx and not args.messages_col:
        parser.error("--messages-col is required when using --xlsx")

    global OUTPUTS_DIR, STATE_DIR
    if args.owner != "solvea-kit":
        OUTPUTS_DIR = WORKSPACE / "outputs" / args.owner
        STATE_DIR = WORKSPACE / "state" / args.owner

    run_id = args.run_id or timestamp()
    ts = run_id
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    results_path = str(OUTPUTS_DIR / f"results_{ts}.json")
    items_path = str(OUTPUTS_DIR / f"items_{ts}.json")

    if args.no_excel:
        final = generate_no_excel_results(run_id)
        with open(results_path, "w") as f:
            json.dump(final, f, ensure_ascii=False, indent=2)
        _sf = STATE_DIR / "progress.json"
        _sf.parent.mkdir(parents=True, exist_ok=True)
        _sf.write_text(json.dumps({
            "status": "no_excel",
            "run_id": run_id,
            "results_path": results_path,
            "updated_at": timestamp(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[classify] No-excel mode: {len(final['intents'])} fixed intents")
        print(f"[classify] Results -> {results_path}")
        for intent in final["intents"]:
            l2_names = [s["name"] for s in intent["sub_intents"]]
            l2_str = ", ".join(l2_names) if l2_names else "(no predefined L2)"
            print(f"  - {intent['name']}: {l2_str}")
        return

    client = OpenAI(timeout=60.0)

    _sf = STATE_DIR / "progress.json"
    _sf.parent.mkdir(parents=True, exist_ok=True)
    _sf.write_text(json.dumps({
        "status": "classifying",
        "run_id": run_id,
        "results_path": results_path,
        "updated_at": timestamp(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[classify] Loading {args.xlsx}...")
    all_items = load_xlsx(args.xlsx, max_rows=args.max_rows,
                          messages_col=args.messages_col,
                          title_col=args.title_col)
    print(f"[classify] {len(all_items)} items loaded")

    checkpoint = load_checkpoint(results_path)
    done_ids = set(checkpoint.get("raw_items", {}).keys())
    remaining = [it for it in all_items if it["id"] not in done_ids]
    print(f"[classify] {len(done_ids)} already done, {len(remaining)} remaining")

    batches = [remaining[i:i + BATCH_SIZE] for i in range(0, len(remaining), BATCH_SIZE)]
    print(f"[classify] {len(batches)} batches x {BATCH_SIZE}, {MAX_WORKERS} workers")

    def _process_batch(idx_batch):
        idx, batch = idx_batch
        results = classify_batch(batch, client)
        for classified in results:
            save_item(results_path, checkpoint, classified["id"], classified)
        print(f"  [batch {idx+1}/{len(batches)}] done ({len(batch)} items)")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        list(executor.map(_process_batch, enumerate(batches)))

    # Re-classify Other items if they exceed the threshold (up to MAX_RESEARCH_ROUNDS)
    def _make_reprocess(round_num: int, round_batches: list):
        def _inner(idx_batch):
            idx, batch = idx_batch
            results = classify_batch(batch, client)
            for classified in results:
                save_item(results_path, checkpoint, classified["id"], classified)
            print(f"  [re-round {round_num+1} batch {idx+1}/{len(round_batches)}] done ({len(batch)} items)")
        return _inner

    for _round in range(MAX_RESEARCH_ROUNDS):
        other_ids = {iid for iid, r in checkpoint["raw_items"].items() if r.get("l1") == "Other"}
        if not other_ids:
            break
        other_pct = len(other_ids) / len(all_items)
        if other_pct <= OTHER_THRESHOLD:
            break
        print(f"[classify] Other {other_pct*100:.1f}% > {OTHER_THRESHOLD*100:.0f}% — re-classify round {_round+1}/{MAX_RESEARCH_ROUNDS}...")
        round_items = [it for it in all_items if it["id"] in other_ids]
        round_batches = [round_items[i:i + BATCH_SIZE] for i in range(0, len(round_items), BATCH_SIZE)]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            list(executor.map(_make_reprocess(_round, round_batches), enumerate(round_batches)))

    print("[classify] Assembling results...")
    final = assemble_results(checkpoint["raw_items"], all_items, client,
                             run_id, items_path)

    final["meta"]["usage"] = _tracker.summary()

    with open(results_path, "w") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    _sf = STATE_DIR / "progress.json"
    _sf.parent.mkdir(parents=True, exist_ok=True)
    _sf.write_text(json.dumps({
        "status": "ready",
        "run_id": run_id,
        "results_path": results_path,
        "items_path": items_path,
        "updated_at": timestamp(),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    meta = final["meta"]
    total = meta["total"]
    print(f"[classify] Done. {meta['n_known']} known + {meta['n_new']} new intents, "
          f"{total} total items")
    print(f"[classify] Intent distribution:")
    for e in final.get("intents", []):
        tag = "[new]" if e.get("is_new") else "     "
        print(f"  {tag}  {e['name']}: {e['count']} ({e['pct']:.1f}%)")
    for e in final.get("new_intents", []):
        print(f"  [new]  {e['name']}: {e['count']} ({e['pct']:.1f}%)")
    print(f"[classify] Results -> {results_path}")


if __name__ == "__main__":
    main()
