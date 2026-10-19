"""
Generate intent classification detail Excel from items_*.json + results_*.json.

Columns: L1 Intent | L2 Intent | Case Text
L1 and L2 cells are merged across rows of the same value.

Usage:
  python3 scripts/gen_excel.py [--brand "Acme"]
"""

import os, sys
sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *

import json, argparse
import openpyxl


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
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter


COLOR_PALETTE = [
    "FEF3C7", "DBEAFE", "D1FAE5", "FCE7F3", "EDE9FE",
    "FEE2E2", "ECFDF5", "FFF7ED", "F0F9FF", "F7FEE7",
]


def thin_border():
    s = Side(style="thin", color="D1D5DB")
    return Border(left=s, right=s, top=s, bottom=s)


def build_excel(items, results, brand=""):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Intent Detail"

    all_intents = results.get("intents", []) + results.get("new_intents", [])
    l1_color = {}
    for i, intent in enumerate(all_intents):
        l1_color[intent["name"]] = COLOR_PALETTE[i % len(COLOR_PALETTE)]

    l1_canonical_l2s = {}
    for intent in all_intents:
        l1_canonical_l2s[intent["name"]] = {
            s["name"] for s in intent.get("sub_intents", []) if s["name"] != "Other"
        }

    def canonical_l2(l1, l2):
        allowed = l1_canonical_l2s.get(l1, set())
        if not allowed:
            return l2 or "Other"
        return l2 if l2 in allowed else "Other"

    l1_order = {intent["name"]: i for i, intent in enumerate(all_intents)}
    items_sorted = sorted(items, key=lambda x: (
        l1_order.get(x["l1"], 999),
        canonical_l2(x["l1"], x.get("l2") or ""),
    ))

    headers = ["L1意图", "L2意图", "分类依据(LLM)", "title", "first_message", "messages"]
    col_widths = [22, 28, 45, 25, 55, 70]

    header_fill = PatternFill("solid", fgColor="1E3A5F")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col, (h, w) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
        cell.border = thin_border()
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"

    row_num = 2

    for item in items_sorted:
        l1 = item["l1"]
        l2 = item.get("l2") or "(unclassified)"
        title_val = item.get("title", "")
        first_msg_val = item.get("first_message", "") or item.get("text", "")
        messages_val = item.get("messages", "")
        raw_text = item.get("text", "")
        text_val = raw_text[:1000] + f"...[截断 {len(raw_text)-1000} 字]" if len(raw_text) > 1000 else raw_text
        color = l1_color.get(l1, "F9FAFB")

        fill = PatternFill("solid", fgColor=color)
        border = thin_border()

        c1 = ws.cell(row=row_num, column=1, value=l1)
        c1.fill = fill
        c1.border = border
        c1.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
        c1.font = Font(bold=True, size=10)

        l2_display = canonical_l2(l1, l2)
        l2_label = l2_display
        if item.get("is_new_l2") and l2_display not in ("Other", ""):
            l2_label = f"★ {l2_display}"
        if item.get("is_new_l1"):
            l2_label = f"[新] {l2_display}"

        c2 = ws.cell(row=row_num, column=2, value=l2_label)
        c2.fill = PatternFill("solid", fgColor="F8FAFC")
        c2.border = border
        c2.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        c2.font = Font(size=10)

        for col_idx, val in [(3, text_val), (4, title_val), (5, first_msg_val), (6, messages_val)]:
            cx = ws.cell(row=row_num, column=col_idx, value=val)
            cx.fill = PatternFill("solid", fgColor="FFFFFF")
            cx.border = border
            cx.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            cx.font = Font(size=9)
        ws.row_dimensions[row_num].height = max(15, min(80, len(first_msg_val) // 3))

        row_num += 1

    # Summary sheet
    ws2 = wb.create_sheet("Summary")
    ws2.column_dimensions["A"].width = 28
    ws2.column_dimensions["B"].width = 28
    ws2.column_dimensions["C"].width = 10
    ws2.column_dimensions["D"].width = 10

    h_fill = PatternFill("solid", fgColor="1E3A5F")
    h_font = Font(bold=True, color="FFFFFF", size=11)
    for col, val in enumerate(["一级意图", "二级意图", "数量", "占比 %"], start=1):
        c = ws2.cell(row=1, column=col, value=val)
        c.fill = h_fill
        c.font = h_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin_border()
    ws2.row_dimensions[1].height = 28
    ws2.freeze_panes = "A2"

    sr = 2
    for intent in all_intents:
        l1n = intent["name"]
        color = l1_color.get(l1n, "F9FAFB")
        fill = PatternFill("solid", fgColor=color)
        subs = intent.get("sub_intents", [])
        if not subs:
            c = ws2.cell(row=sr, column=1, value=l1n)
            c.fill = fill; c.font = Font(bold=True, size=10); c.border = thin_border()
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws2.cell(row=sr, column=2, value="(no sub-intents)").border = thin_border()
            ws2.cell(row=sr, column=3, value=intent["count"]).border = thin_border()
            ws2.cell(row=sr, column=4, value=round(intent["pct"], 1)).border = thin_border()
            sr += 1
        else:
            l1_start_row = sr
            for sub in subs:
                c = ws2.cell(row=sr, column=1, value=l1n)
                c.fill = fill; c.font = Font(bold=True, size=10); c.border = thin_border()
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                ws2.cell(row=sr, column=2, value=sub["name"]).border = thin_border()
                ws2.cell(row=sr, column=2).alignment = Alignment(horizontal="left", vertical="center")
                ws2.cell(row=sr, column=3, value=sub["count"]).border = thin_border()
                ws2.cell(row=sr, column=3).alignment = Alignment(horizontal="center")
                ws2.cell(row=sr, column=4, value=round(sub["pct"], 1)).border = thin_border()
                ws2.cell(row=sr, column=4).alignment = Alignment(horizontal="center")
                sr += 1
            if sr - 1 > l1_start_row:
                ws2.merge_cells(start_row=l1_start_row, start_column=1,
                                end_row=sr - 1, end_column=1)
                ws2.cell(row=l1_start_row, column=1).alignment = Alignment(
                    horizontal="center", vertical="center", wrap_text=True)

    return wb


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", default="")
    parser.add_argument("--results", default=None,
                        help="Override results JSON path (default: read from state)")
    parser.add_argument("--items", default=None,
                        help="Override items JSON path (default: read from state)")
    args = parser.parse_args()

    state = _read_state()
    results_path = args.results or state.get("results_path")
    items_path = args.items or state.get("items_path")

    if not results_path or not os.path.exists(results_path):
        raise FileNotFoundError(
            f"Results file missing (state.results_path={results_path}). Run classify.py first."
        )
    if not items_path or not os.path.exists(items_path):
        raise FileNotFoundError(
            f"Items file missing (state.items_path={items_path}). "
            "Run classify.py with --xlsx first."
        )

    with open(items_path) as f:
        items = json.load(f)
    with open(results_path) as f:
        results = json.load(f)

    wb = build_excel(items, results, args.brand)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = str(OUTPUTS_DIR / f"detail_{timestamp()}.xlsx")
    wb.save(out_path)
    print(f"[gen_excel] Excel -> {out_path} ({len(items)} rows)")

    state = _read_state()
    state["excel_path"] = out_path
    state["updated_at"] = timestamp()
    _write_state(state)


if __name__ == "__main__":
    main()
