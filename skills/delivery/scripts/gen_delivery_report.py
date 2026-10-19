#!/usr/bin/env python3
"""Delivery 批测报告生成器：读 batch_test.py 输出的 results JSON，渲染 HTML+MD。

输入 results JSON schema（与 batch_test.py 输出一致）：
  {
    "summary": {total_conversations, total_messages, total_replied, reply_rate,
                agents:[...], handoff:[...], errors:[...], no_reply_reasons:[...]},
    "details": [{source_chat_id, new_chat_id, intent, action, round,
                 question, answer, no_reply_reason, judge, correct}, ...]
  }

输出：
  - HTML：交互式（KPI / agent / handoff / error / 详情 / Judge / CSV 下载）
  - MD  ：纯文本表格

用法：
  python3 gen_delivery_report.py --results results.json
  python3 gen_delivery_report.py --results results.json --html out.html --md out.md
  python3 gen_delivery_report.py --results results.json --no-md
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.environ.get("SOLVEA_LIB_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "__lib__"))), "skill-runtime"))
from bootstrap import *  # noqa: F401,F403


def _pct(v):
    """Format float 0-1 as percentage string, or '-' if None."""
    if v is None:
        return '-'
    return f"{v * 100:.1f}%"


def generate_html_report(summary: dict, details: list, output_path: str):
    """Generate a self-contained HTML report and write to output_path."""
    agents_rows = ""
    for a in summary.get('agents', []):
        agents_rows += f"""
        <tr>
          <td>{a.get('name','')}</td>
          <td>{a.get('total_conversations',0)}</td>
          <td>{a.get('total_messages',0)}</td>
          <td>{_pct(a.get('reply_rate'))}</td>
          <td>{_pct(a.get('r1_reply_rate'))}</td>
          <td>{_pct(a.get('r2_reply_rate'))}</td>
          <td>{_pct(a.get('r3_reply_rate'))}</td>
          <td>{_pct(a.get('rs_reply_rate'))}</td>
        </tr>"""

    handoff_rows = "".join(
        f"<tr><td>{h['type']}</td><td>{h['count']}</td><td>{_pct(h.get('rate'))}</td></tr>"
        for h in summary.get('handoff', [])
    ) or "<tr><td colspan='3' style='color:#999'>无</td></tr>"

    error_rows = "".join(
        f"<tr><td>{e['type']}</td><td>{e['count']}</td><td>{_pct(e.get('rate'))}</td></tr>"
        for e in summary.get('errors', [])
    ) or "<tr><td colspan='3' style='color:#999'>无</td></tr>"

    detail_rows = ""
    for d in details:
        src = d.get('source_chat_id', '')
        new = d.get('new_chat_id', '')
        chat_display = f"{new}<br><small style='color:#999'>{src}</small>" if src else new
        answer_raw = d.get('answer', '')
        if isinstance(answer_raw, dict):
            answer_raw = answer_raw.get('content', str(answer_raw))
        answer = str(answer_raw).replace('<', '&lt;').replace('>', '&gt;')
        question_raw = d.get('question', '')
        if isinstance(question_raw, dict):
            question_raw = question_raw.get('content', str(question_raw))
        question = str(question_raw).replace('<', '&lt;').replace('>', '&gt;')
        ng_cls = ' active' if d.get('judge', '') in ('✗', 'ng', 'fail', 'FAIL', '0') else ''
        correct_esc = d.get('correct', '').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        detail_rows += f"""
        <tr>
          <td class='col-chatid'><div class='cc'>{chat_display}</div></td>
          <td class='col-round' style='text-align:center'>{d.get('round','')}</td>
          <td class='col-intent'><div class='cc'>{d.get('intent','')}</div></td>
          <td class='col-agent'><div class='cc'>{d.get('action','')}</div></td>
          <td class='col-q'><div class='cc'>{question}</div></td>
          <td class='col-a'><div class='cc'>{answer}</div></td>
          <td class='col-judge'><div class='jcell'><button type='button' class='jbtn ng{ng_cls}' onclick='toggleJudge(this)'>&#10007;</button></div></td>
          <td class='col-correct'><textarea class='rinp' rows='3' placeholder='填写正确回答...'>{correct_esc}</textarea></td>
        </tr>"""

    reply_rate_pct = _pct(summary.get('reply_rate'))
    html = rf"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>批测报告</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        background:#f5f6fa;color:#2d3436;font-size:14px;padding:24px}}
  h1{{font-size:20px;font-weight:700;margin-bottom:20px;color:#1a1a2e}}
  h2{{font-size:15px;font-weight:600;margin:28px 0 12px;color:#444}}
  .kpi-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:8px}}
  .kpi{{background:#fff;border-radius:10px;padding:18px 20px;
        box-shadow:0 1px 4px rgba(0,0,0,.08)}}
  .kpi .label{{font-size:12px;color:#888;margin-bottom:6px}}
  .kpi .value{{font-size:26px;font-weight:700;color:#2d3436}}
  .kpi .value.green{{color:#00b894}}
  table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;
         box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden}}
  th{{background:#f0f0f5;padding:10px 14px;text-align:left;
      font-size:12px;font-weight:600;color:#555;white-space:nowrap}}
  td{{padding:9px 14px;border-top:1px solid #f0f0f0;vertical-align:top;line-height:1.5}}
  tr:hover td{{background:#fafbff}}
  .dist-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
  .detail-wrap{{overflow-x:auto;border-radius:10px;
                box-shadow:0 1px 4px rgba(0,0,0,.08)}}
  .detail-wrap table{{border-radius:0;table-layout:fixed;width:100%}}
  .col-chatid{{width:155px}}.col-round{{width:44px}}.col-intent{{width:110px}}
  .col-agent{{width:130px}}.col-q{{width:240px}}.col-a{{width:280px}}
  .col-judge{{width:44px}}.col-correct{{width:222px}}
  .cc{{max-height:80px;overflow:hidden;word-break:break-word;
       white-space:pre-wrap;font-size:13px;line-height:1.45;position:relative}}
  .cc.open{{max-height:none}}
  .xbtn{{display:none;color:#0984e3;font-size:11px;cursor:pointer;
          margin-top:3px;user-select:none;white-space:nowrap}}
  .xbtn.vis{{display:inline-block}}
  .jcell{{display:flex;gap:5px;justify-content:center;padding-top:2px}}
  .jbtn{{-webkit-appearance:none;appearance:none;border:1px solid #ddd;
          background:#f7f7f7;border-radius:5px;padding:4px 9px;cursor:pointer;
          font-size:15px;color:#bbb;
          transition:background .15s,color .15s,border-color .15s;line-height:1}}
  .jbtn.ng.active{{background:#e17055 !important;border-color:#e17055 !important;color:#fff !important}}
  .jbtn:hover:not(.active){{background:#eee;color:#666}}
  .rinp{{width:100%;box-sizing:border-box;border:1px solid #e0e0e0;border-radius:5px;
          padding:5px 7px;font-size:12px;font-family:inherit;color:#444;
          resize:vertical;min-height:54px;line-height:1.4}}
  .rinp:focus{{outline:none;border-color:#0984e3;box-shadow:0 0 0 2px rgba(9,132,227,.1)}}
  .dl-btn{{background:#0984e3;color:#fff;border:none;border-radius:6px;
            padding:6px 14px;font-size:13px;cursor:pointer;white-space:nowrap}}
  .dl-btn:hover{{background:#076dc1}}
  small{{font-size:11px}}
</style>
</head>
<body>
<h1>批测报告</h1>

<h2>KPI 总览</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="label">总会话数</div>
    <div class="value">{summary.get('total_conversations',0)}</div></div>
  <div class="kpi"><div class="label">总消息数</div>
    <div class="value">{summary.get('total_messages',0)}</div></div>
  <div class="kpi"><div class="label">回复消息数</div>
    <div class="value">{summary.get('total_replied',0)}</div></div>
  <div class="kpi"><div class="label">整体回复率</div>
    <div class="value green">{reply_rate_pct}</div></div>
</div>

<h2>Agent Performance</h2>
<table>
  <thead><tr>
    <th>Action</th><th>会话数</th><th>消息数</th><th>回复率</th>
    <th>R1</th><th>R2</th><th>R3</th><th>Rs</th>
  </tr></thead>
  <tbody>{agents_rows}</tbody>
</table>

<h2>分布详情</h2>
<div class="dist-grid">
  <div>
    <h2 style="margin-top:0">Handoff 分布</h2>
    <table>
      <thead><tr><th>类型</th><th>数量</th><th>占比</th></tr></thead>
      <tbody>{handoff_rows}</tbody>
    </table>
  </div>
  <div>
    <h2 style="margin-top:0">Error 分布</h2>
    <table>
      <thead><tr><th>类型</th><th>数量</th><th>占比</th></tr></thead>
      <tbody>{error_rows}</tbody>
    </table>
  </div>
</div>

<div style='display:flex;align-items:center;justify-content:space-between;margin:28px 0 12px'><h2 style='margin:0'>回复详情</h2><button class='dl-btn' onclick='downloadCSV()'>&#11015; 下载 CSV</button></div>
<div class="detail-wrap">
<table>
  <thead><tr>
    <th class='col-chatid'>Chat ID</th><th class='col-round'>Round</th>
    <th class='col-intent'>意图</th><th class='col-agent'>Action</th>
    <th class='col-q'>Question</th><th class='col-a'>Answer</th>
    <th class='col-judge'>Judge</th><th class='col-correct'>Correct</th>
  </tr></thead>
  <tbody>{detail_rows}</tbody>
</table>
</div>

<script>
document.querySelectorAll('.cc').forEach(function(el){{
  if(el.scrollHeight > el.clientHeight + 4){{
    var b = document.createElement('span');
    b.className = 'xbtn vis';
    b.textContent = '展开';
    b.onclick = function(){{
      var open = el.classList.toggle('open');
      b.textContent = open ? '收起' : '展开';
    }};
    el.parentNode.appendChild(b);
  }}
}});
function toggleJudge(btn){{ btn.classList.toggle('active'); }}
function downloadCSV(){{
  var hdr = ['new_chat_id','source_chat_id','round','intent','action','question','answer','judge','correct'];
  var rows = [hdr];
  document.querySelectorAll('.detail-wrap tbody tr').forEach(function(tr){{
    var td = tr.querySelectorAll('td');
    function txt(el){{ return el ? (el.innerText||el.textContent||'').replace(/\s+/g,' ').trim() : ''; }}
    var chatRaw = txt(td[0].querySelector('.cc'));
    var parts = chatRaw.split('\\n');
    var newId = parts[0]||''; var srcId = parts[1]||'';
    var round  = txt(td[1]);
    var intent = txt(td[2].querySelector('.cc'));
    var action = txt(td[3].querySelector('.cc'));
    var question = txt(td[4].querySelector('.cc'));
    var answer   = txt(td[5].querySelector('.cc'));
    var ab = td[6].querySelector('.jbtn.active');
    var judge = ab ? '✗' : '';
    var correct = td[7].querySelector('.rinp') ? td[7].querySelector('.rinp').value : '';
    rows.push([newId,srcId,round,intent,action,question,answer,judge,correct]);
  }});
  var csv = rows.map(function(r){{
    return r.map(function(v){{
      return '"' + (v||'').replace(/\\r?\\n/g,' ').replace(/"/g,'""') + '"';
    }}).join(',');
  }}).join('\\r\\n');
  var blob = new Blob(['﻿'+csv],{{type:'text/csv;charset=utf-8'}});
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href=url; a.download='batch_test_result.csv';
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}}
</script>
</body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)


def generate_md_report(summary: dict, details: list, output_path: str):
    """Generate a Markdown report and write to output_path."""
    lines = ["# 批测报告\n"]

    lines.append("## KPI 总览\n")
    lines.append("| 总会话 | 总消息数 | 回复消息数 | 回复率 |")
    lines.append("|--------|---------|-----------|--------|")
    lines.append(f"| {summary.get('total_conversations',0)} "
                 f"| {summary.get('total_messages',0)} "
                 f"| {summary.get('total_replied',0)} "
                 f"| {_pct(summary.get('reply_rate'))} |\n")

    lines.append("## Agent Performance\n")
    lines.append("| Action | 会话数 | 消息数 | 回复率 | R1 | R2 | R3 | Rs |")
    lines.append("|--------|--------|--------|--------|----|----|----|----|")
    for a in summary.get('agents', []):
        lines.append(f"| {a.get('name','')} | {a.get('total_conversations',0)} "
                     f"| {a.get('total_messages',0)} | {_pct(a.get('reply_rate'))} "
                     f"| {_pct(a.get('r1_reply_rate'))} | {_pct(a.get('r2_reply_rate'))} "
                     f"| {_pct(a.get('r3_reply_rate'))} | {_pct(a.get('rs_reply_rate'))} |")
    lines.append("")

    lines.append("## Handoff 分布\n")
    for h in summary.get('handoff', []):
        lines.append(f"- {h['type']}: {h['count']} 条 ({_pct(h.get('rate'))})")
    lines.append("")

    lines.append("## Error 分布\n")
    for e in summary.get('errors', []):
        lines.append(f"- {e['type']}: {e['count']} 条 ({_pct(e.get('rate'))})")
    lines.append("")

    lines.append("## 回复详情\n")
    lines.append("| Chat ID | Round | 意图 | Action | Question | Answer | Judge | Correct |")
    lines.append("|---------|-------|------|-------|----------|--------|-------|--------|")
    for d in details:
        q = d.get('question', '').replace('|', '｜')
        a = d.get('answer', '').replace('|', '｜').replace('\n', ' ')
        lines.append(f"| {d.get('new_chat_id','')} | {d.get('round','')} "
                     f"| {d.get('intent','')} | {d.get('action','')} "
                     f"| {q} | {a} | {d.get('judge','')} | {d.get('correct','')} |")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    parser = argparse.ArgumentParser(description="Delivery 批测报告生成器")
    parser.add_argument("--results", required=True,
                        help="batch_test.py 输出的 results JSON 路径")
    parser.add_argument("--html", default=None,
                        help="HTML 输出路径，默认 <results基名>.html")
    parser.add_argument("--md", default=None,
                        help="MD 输出路径，默认 <results基名>.md")
    parser.add_argument("--no-html", action="store_true", help="跳过 HTML 渲染")
    parser.add_argument("--no-md", action="store_true", help="跳过 MD 渲染")
    args = parser.parse_args()

    if not os.path.exists(args.results):
        print(f"results file not found: {args.results}", file=sys.stderr)
        sys.exit(1)

    with open(args.results, "r", encoding="utf-8") as f:
        data = json.load(f)
    summary = data.get("summary", {})
    details = data.get("details", [])

    base = os.path.splitext(os.path.abspath(args.results))[0]
    html_path = args.html or (base + ".html")
    md_path = args.md or (base + ".md")

    if not args.no_html:
        os.makedirs(os.path.dirname(os.path.abspath(html_path)) or ".", exist_ok=True)
        generate_html_report(summary, details, html_path)
        print(f"Report rendered → {html_path}", file=sys.stderr)
    if not args.no_md:
        os.makedirs(os.path.dirname(os.path.abspath(md_path)) or ".", exist_ok=True)
        generate_md_report(summary, details, md_path)
        print(f"Report rendered → {md_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
