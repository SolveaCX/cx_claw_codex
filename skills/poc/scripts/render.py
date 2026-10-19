"""Auto-generated render module for intent-classifier.
Extracted from intent-optimizer; do NOT import from intent-optimizer.
"""
import json

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Segoe UI', sans-serif; background: #f0f2f5; }
.page-header { background: linear-gradient(135deg, #1a1a2e 0%, #0f3460 100%); color: white; padding: 24px 40px 20px; }
.page-header h1 { font-size: 19px; font-weight: 700; }
.page-header .sub { font-size: 11.5px; color: rgba(255,255,255,0.45); margin-top: 3px; }
.kpis { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; }
.kpi { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; padding: 8px 16px; text-align: center; }
.kpi .v { font-size: 20px; font-weight: 900; }
.kpi .l { font-size: 10px; color: rgba(255,255,255,0.38); margin-top: 1px; text-transform: uppercase; letter-spacing: 0.3px; }
.c1 .v{color:#60d3f7} .c2 .v{color:#a78bfa} .c3 .v{color:#34d399} .c4 .v{color:#fbbf24} .c5 .v{color:#f87171}
.principle { background: #1e293b; color: rgba(255,255,255,0.7); font-size: 11px; padding: 10px 40px; border-top: 1px solid rgba(255,255,255,0.08); display: flex; gap: 24px; flex-wrap: wrap; }
.principle b { color: #60d3f7; }
#flow-outer { padding: 28px 24px 60px; overflow-x: auto; }
#flow { position: relative; width: 1280px; min-height: 1200px; margin: 0 auto; }
#svg-lines { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; }
.col-hdr { position: absolute; top: 0; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: white; padding: 4px 12px; border-radius: 4px; text-align: center; }
.agent { position: absolute; z-index: 4; background: white; border-radius: 10px; border-left: 5px solid transparent; box-shadow: 0 1px 6px rgba(0,0,0,0.08); padding: 10px 12px 28px 12px; cursor: default; }
.agent:hover { box-shadow: 0 4px 18px rgba(0,0,0,0.13); z-index: 10; }
.agent .aname { font-size: 12px; font-weight: 800; color: #111827; }
.agent .covers { font-size: 10px; color: #6b7280; margin-top: 3px; line-height: 1.5; }
.agent .covers span { display: inline-block; background: #f3f4f6; border-radius: 3px; padding: 1px 5px; margin: 1px 2px 1px 0; }
.agent .afoot { display: flex; align-items: center; gap: 8px; margin-top: 7px; }
.agent .vol { font-size: 16px; font-weight: 900; }
.agent .vol-sub { font-size: 10px; color: #9ca3af; }
.complexity-badge { margin-left: auto; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }
.cx-low { background: #d1fae5; color: #065f46; }
.cx-mid { background: #fef3c7; color: #92400e; }
.cx-high { background: #fee2e2; color: #991b1b; }
.cfg-btn { position:absolute; bottom:8px; right:10px; font-size:9px; font-weight:700; letter-spacing:0.3px; padding:2px 8px; border-radius:8px; border:1px solid #e5e7eb; background:#f9fafb; color:#6b7280; cursor:pointer; transition:all 0.15s; }
.cfg-btn:hover { background:#1a1a2e; color:white; border-color:#1a1a2e; }
.dr-hdr { padding:16px 20px 12px; position:sticky; top:0; background:white; z-index:2; border-bottom:1px solid #f3f4f6; display:flex; align-items:flex-start; gap:10px; }
.dr-hdr .dr-title { flex:1; }
.dr-hdr .dr-name { font-size:15px; font-weight:800; color:#111; }
.dr-hdr .dr-vol { font-size:11px; color:#9ca3af; margin-top:4px; }
.dr-close { font-size:18px; color:#9ca3af; cursor:pointer; line-height:1; padding:2px 4px; }
.dr-close:hover { color:#111; }
.dr-type-badge { font-size:9.5px; font-weight:800; padding:3px 9px; border-radius:12px; text-transform:uppercase; letter-spacing:0.4px; margin-top:4px; display:inline-block; }
.dr-single { background:#dbeafe; color:#1d4ed8; }
.dr-chatflow { background:#fce7f3; color:#9d174d; }
.dr-body { padding:14px 20px; }
.dr-node { margin-bottom:10px; padding:10px 12px; border-radius:8px; background:#f9fafb; border-left:3px solid #e5e7eb; }
.dr-node:last-child { margin-bottom:0; }
.dr-node-name { font-size:11px; font-weight:700; color:#111; margin-bottom:4px; }
.dr-node-row { font-size:10.5px; color:#4b5563; margin-bottom:3px; line-height:1.5; }
.dr-node-row b { color:#374151; }
.dr-node-row code { background:#e5e7eb; padding:1px 5px; border-radius:3px; font-size:10px; color:#374151; }
.dr-footer { margin:16px 20px 0; padding:10px 14px; background:#f8fafc; border-radius:8px; font-size:10.5px; color:#6b7280; line-height:1.6; }
.dr-footer b { color:#374151; }
.l2-node { position: absolute; z-index: 4; background: white; border-radius: 8px; border-left: 4px solid transparent; box-shadow: 0 1px 4px rgba(0,0,0,0.08); padding: 7px 10px 6px; }
.l2-node:hover { box-shadow: 0 3px 12px rgba(0,0,0,0.12); z-index: 10; }
.l2-node .nn { font-size: 10.5px; font-weight: 700; color: #1a1a2e; }
.l2-node .nc { font-size: 10px; color: #4b5563; margin-top: 1px; }
.l2-node .nct { font-size: 14px; font-weight: 900; margin-top: 4px; }
.l2-shared { border-top: 2px dashed #f59e0b; background: #fffbeb; }
.shared-tag { font-size: 9px; font-weight: 700; color: #d97706; background: #fef3c7; border-radius: 3px; padding: 0 4px; margin-left: 4px; }
.filter-block { position: absolute; z-index: 4; background: #f8fafc; border: 1.5px dashed #cbd5e1; border-radius: 10px; padding: 10px 12px; }
.filter-block .fn { font-size: 11.5px; font-weight: 700; color: #94a3b8; }
.filter-block .fc { font-size: 10px; color: #b0bec5; margin-top: 3px; }
.filter-block .fct { font-size: 16px; font-weight: 900; color: #cbd5e1; margin-top: 5px; }

.sm-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.55); z-index:200; align-items:center; justify-content:center; }
.sm-overlay.open { display:flex; }
.sm-box { background:white; border-radius:14px; width:600px; max-width:95vw; max-height:80vh; overflow:hidden; display:flex; flex-direction:column; box-shadow:0 16px 60px rgba(0,0,0,0.3); animation: smIn 0.2s cubic-bezier(0.34,1.56,0.64,1); }
@keyframes smIn { from { opacity:0; transform:scale(0.94) translateY(8px); } to { opacity:1; transform:scale(1) translateY(0); } }
.sm-header { padding:18px 22px 14px; border-bottom:1px solid #f0f0f0; display:flex; align-items:flex-start; gap:10px; }
.sm-hdr-left { flex:1; min-width:0; }
.sm-title { font-size:15px; font-weight:800; color:#111; }
.sm-meta { font-size:11.5px; color:#6b7280; margin-top:5px; }
.sm-badge { display:inline-block; font-size:11px; font-weight:700; padding:1px 9px; border-radius:10px; margin-left:6px; }
.sm-close { font-size:22px; color:#9ca3af; cursor:pointer; line-height:1; padding:0 2px; flex-shrink:0; }
.sm-close:hover { color:#111; }
.sm-body { padding:16px 20px 20px; overflow-y:auto; flex:1; }
.sm-empty { text-align:center; color:#9ca3af; font-size:13px; padding:32px 0; }
.sm-msg { background:#f8fafc; border-radius:8px; padding:11px 14px; margin-bottom:9px; font-size:12.5px; color:#374151; line-height:1.7; border-left:3px solid #e5e7eb; }
.sm-msg:last-child { margin-bottom:0; }
.sm-msg-num { font-size:9.5px; color:#9ca3af; font-weight:700; margin-bottom:4px; text-transform:uppercase; letter-spacing:0.3px; }

.apply-btn { background: linear-gradient(135deg, #6366f1, #8b5cf6); color: white; border: none; border-radius: 8px; padding: 8px 18px; font-size: 13px; font-weight: 700; cursor: pointer; letter-spacing: 0.3px; transition: opacity 0.2s; }
.apply-btn:hover { opacity: 0.88; }
.modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.5); z-index:200; align-items:center; justify-content:center; }
.modal-overlay.open { display:flex; }
.modal-box { background:white; border-radius:12px; width:620px; max-width:95vw; max-height:85vh; overflow:hidden; display:flex; flex-direction:column; box-shadow:0 8px 40px rgba(0,0,0,0.25); }
.modal-header { padding:18px 22px 14px; border-bottom:1px solid #f0f0f0; display:flex; align-items:center; justify-content:space-between; }
.modal-header h3 { font-size:16px; font-weight:800; color:#111; }
.modal-close { font-size:20px; color:#9ca3af; cursor:pointer; line-height:1; }
.modal-close:hover { color:#111; }
.modal-body { padding:18px 22px; overflow-y:auto; flex:1; }
.modal-footer { padding:14px 22px; border-top:1px solid #f0f0f0; display:flex; gap:10px; justify-content:flex-end; }
.btn-cancel { background:#f3f4f6; color:#374151; border:none; border-radius:8px; padding:8px 18px; font-size:13px; font-weight:600; cursor:pointer; }
.btn-confirm { background:#6366f1; color:white; border:none; border-radius:8px; padding:8px 20px; font-size:13px; font-weight:700; cursor:pointer; }
.btn-confirm:hover { background:#4f46e5; }
.btn-confirm.danger { background:#ef4444; }
.btn-confirm.danger:hover { background:#dc2626; }
.intent-preview-table { width:100%; border-collapse:collapse; font-size:12px; }
.intent-preview-table th { background:#f8fafc; padding:7px 10px; text-align:left; font-weight:700; color:#374151; border-bottom:2px solid #e5e7eb; }
.intent-preview-table td { padding:7px 10px; border-bottom:1px solid #f3f4f6; color:#4b5563; vertical-align:top; }
.intent-preview-table tr:last-child td { border-bottom:none; }
.intent-name-cell { font-weight:700; color:#111; width:160px; }
.apply-status { margin-top:12px; padding:12px 14px; border-radius:8px; background:#f0fdf4; border:1px solid #86efac; font-size:12px; line-height:1.8; }
.apply-status.error { background:#fef2f2; border-color:#fca5a5; }
"""


EDGE_JS = """
function getRect(id) {
  const flow = document.getElementById('flow');
  if (!flow) return null;
  const fr = flow.getBoundingClientRect();
  const el = document.getElementById(id);
  if (!el) return null;
  const er = el.getBoundingClientRect();
  return { left:er.left-fr.left, top:er.top-fr.top, right:er.right-fr.left,
           bottom:er.bottom-fr.top, w:er.width, h:er.height };
}
function drawEdges() {
  const svg = document.getElementById('svg-lines');
  const flow = document.getElementById('flow');
  if (!svg || !flow || typeof EDGES === 'undefined') return;
  svg.setAttribute('viewBox', `0 0 ${flow.offsetWidth} ${flow.offsetHeight}`);
  const srcTot = {}, dstTot = {};
  EDGES.forEach(e => {
    srcTot[e.from] = (srcTot[e.from]||0) + e.count;
    dstTot[e.to]   = (dstTot[e.to]  ||0) + e.count;
  });
  const srcCum = {}, dstCum = {};
  const maxCount = Math.max(...EDGES.map(e=>e.count), 1);
  EDGES.forEach(e => {
    const sr = getRect(e.from);
    const dr = getRect(e.to);
    if (!sr || !dr) return;
    const sFrac = ((srcCum[e.from]||0) + e.count/2) / srcTot[e.from];
    const dFrac = ((dstCum[e.to]  ||0) + e.count/2) / dstTot[e.to];
    srcCum[e.from] = (srcCum[e.from]||0) + e.count;
    dstCum[e.to]   = (dstCum[e.to]  ||0) + e.count;
    const sy = sr.top + sr.h*(0.15 + sFrac*0.7);
    const dy = dr.top + dr.h*(0.15 + dFrac*0.7);
    const x1=sr.right, x2=dr.left, cx=(x1+x2)/2;
    const w = Math.max(1, Math.round(e.count/maxCount*18));
    const opacity = 0.35 + (e.count/maxCount)*0.55;
    const path = document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d',`M${x1},${sy} C${cx},${sy} ${cx},${dy} ${x2},${dy}`);
    path.setAttribute('fill','none');
    path.setAttribute('stroke',e.color);
    path.setAttribute('stroke-width',w);
    path.setAttribute('stroke-opacity',opacity);
    svg.appendChild(path);
  });
}
window.addEventListener('load', drawEdges);
window.addEventListener('resize', () => {
  const svg = document.getElementById('svg-lines');
  if (svg) while(svg.firstChild) svg.removeChild(svg.firstChild);
  drawEdges();
});
"""


def complexity_badge(n: int) -> str:
    if n == 0:
        return '<div class="complexity-badge cx-low">节点 ×0 ✓✓</div>'
    elif n <= 2:
        return f'<div class="complexity-badge cx-low">节点 ×{n} ✓</div>'
    elif n <= 3:
        return f'<div class="complexity-badge cx-mid">节点 ×{n} ⚠️</div>'
    else:
        return f'<div class="complexity-badge cx-high">节点 ×{n} ❌</div>'


def render_html(config: dict, data: dict, brand: str = "", project_id: str = "") -> str:
    agents = config.get("agents", [])
    filter_block = config.get("filter_block", {})
    node_summary = config.get("node_summary", {})
    edges = config.get("edges", [])
    shared_node_ids = {s["node_id"] for s in config.get("shared_nodes", [])}
    fuzzy_samples = data.get("fuzzy_samples", {})

    tree = data.get("tree", {})
    turn_dist = data.get("turn_distribution", {})
    meta = data.get("_meta", {})
    total = meta.get("total", 0)
    brand_name = brand or meta.get("brand", "")

    t1 = turn_dist.get(1, turn_dist.get("1", 0))
    t2 = turn_dist.get(2, turn_dist.get("2", 0))
    t3 = turn_dist.get(3, turn_dist.get("3", 0))
    t4 = turn_dist.get(4, turn_dist.get("4", 0))
    l1_total = tree.get("layer_1", {}).get("n_conversations", total)
    l2_total = tree.get("layer_2", {}).get("n_conversations", 0)
    l3_total = tree.get("layer_3", {}).get("n_conversations", 0)

    n_agents = len(agents)
    total_nodes = node_summary.get("total_nodes", 0)
    max_nodes = max((len(a.get("l2_nodes", [])) for a in agents), default=0)
    covered = sum(a.get("total_count", 0) for a in agents)

    # ── KPIs ──
    kpis = f"""
    <div class="kpis">
      <div class="kpi c1"><div class="v">{n_agents}</div><div class="l">Agent 总数（含过滤）</div></div>
      <div class="kpi c3"><div class="v">{total_nodes}</div><div class="l">总 Agent 节点数</div></div>
      <div class="kpi c2"><div class="v">≤{max_nodes}</div><div class="l">最大单 Agent 节点</div></div>
      <div class="kpi c4"><div class="v">{covered:,}</div><div class="l">Agent 覆盖对话</div></div>
      <div class="kpi c5"><div class="v">{total:,}</div><div class="l">数据总量</div></div>
    </div>"""

    # ── Flow canvas ──
    # Layout constants
    AG_X, AG_W = 0, 373
    L2_X, L2_W = 490, 295
    SUM_X, SUM_W = 905, 295
    AG_GAP = 185   # vertical spacing between agent blocks
    L2_NODE_H = 70  # height per L2 node slot
    TOP_START = 50
    COLORS = ["#6366f1","#8b5cf6","#ec4899","#f59e0b","#10b981","#3b82f6","#ef4444","#14b8a6","#f97316","#84cc16"]

    # Build agent blocks HTML + track L2 node positions
    agent_blocks = ""
    l2_nodes_html = ""
    l2_pos = {}   # l2_node_id → (top_px)

    # We'll track all L2 node ids per agent to place them
    # L2 nodes are placed sequentially under their primary agent's vertical region
    l2_y_cursor = TOP_START

    for i, agent in enumerate(agents):
        ag_id = f"ag-{agent['id'].replace('_','-')}"
        color = agent.get("color", COLORS[i % len(COLORS)])
        ag_top = TOP_START + i * AG_GAP
        name = agent.get("name", f"Agent {i+1}")
        count = agent.get("total_count", 0)
        pct = agent.get("total_pct", 0.0)
        l1_intents = agent.get("l1_intents", [])
        l2_nodes = agent.get("l2_nodes", [])
        n_nodes = len(l2_nodes)

        covers_html = "".join(f'<span>{intent}</span>' for intent in l1_intents)
        is_new_agent = agent.get("is_new", False)
        new_badge = '<span style="display:inline-block;background:#fef3c7;color:#d97706;font-size:9px;font-weight:700;padding:1px 6px;border-radius:4px;margin-left:6px;vertical-align:middle;">🆕 新发现意图</span>' if is_new_agent else ''

        agent_blocks += f"""
  <!-- {name} -->
  <div class="agent" id="{ag_id}" style="left:{AG_X}px;top:{ag_top}px;width:{AG_W}px;border-left-color:{color};">
    <div class="aname">{name}{new_badge}</div>
    <div class="covers">覆盖：{covers_html}</div>
    <div class="afoot">
      <span class="vol" style="color:{color}">{count:,}</span>
      <span class="vol-sub">条 · {pct:.1f}%</span>
      {complexity_badge(n_nodes)}
    </div>
    <button class="cfg-btn" onclick="openDrawer('{agent['id']}')">⚙ 配置</button>
  </div>"""

        # Place L2 nodes for this agent
        # Space them starting from the agent's top position
        node_start_y = max(l2_y_cursor, ag_top)
        for j, node in enumerate(l2_nodes):
            n_id = node["id"]
            n_top = node_start_y + j * L2_NODE_H
            l2_pos[n_id] = n_top
            l2_y_cursor = n_top + L2_NODE_H + 4

            is_shared = node.get("is_shared", False) or n_id in shared_node_ids
            shared_class = " l2-shared" if is_shared else ""
            shared_tag = '<span class="shared-tag">共享节点</span>' if is_shared else ""
            n_color = color if not is_shared else "#f59e0b"

            l2_nodes_html += f"""
  <div class="l2-node{shared_class}" id="{n_id}" style="left:{L2_X}px;top:{n_top}px;width:{L2_W}px;border-left-color:{n_color};cursor:pointer;" onclick="openSamplesModal('{n_id}')" title="点击查看样本消息">
    <div class="nn">{node['name']}{shared_tag}</div>
    <div class="nc">{node.get('desc','')}</div>
    <div class="nct" style="color:{n_color};">{node.get('count',0):,} <span style="font-size:11px;font-weight:400;color:#9ca3af;">条</span></div>
  </div>"""

    # Filter block
    filter_html = ""
    if filter_block and filter_block.get("count", 0) > 0:
        filter_top = TOP_START + len(agents) * AG_GAP
        types_str = " · ".join(filter_block.get("types", []))
        f_count = filter_block.get("count", 0)
        filter_html = f"""
  <div class="filter-block" id="ag-filter" style="left:{AG_X}px;top:{filter_top}px;width:{AG_W}px;">
    <div class="fn">🚫 过滤层（无需 Agent）</div>
    <div class="fc">{types_str}</div>
    <div class="fct">{f_count:,} <span style="font-size:11px;font-weight:400;color:#94a3b8">条 · 直接过滤，不路由</span></div>
  </div>"""

    # Node summary panel
    sum_rows = ""
    for row in node_summary.get("rows", []):
        sum_rows += f"""
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;font-size:11px;">
      <span style="color:{row.get('color','#6b7280')}">{row.get('agent_name','')}</span>
      <span style="font-weight:800;color:{row.get('color','#6b7280')}">{row.get('badge','')}</span>
    </div>"""

    opt_notes = node_summary.get("optimization_notes", "")
    opt_html = ""
    for line in opt_notes.split("\\n"):
        line = line.strip()
        if not line:
            opt_html += "<br>"
            continue
        if line.startswith("✅"):
            opt_html += f'<span style="color:#22c55e;font-weight:700;">{line}</span><br>'
        elif line.startswith("⚡"):
            opt_html += f'<span style="color:#f59e0b;font-weight:700;">{line}</span><br>'
        elif line.startswith("📊"):
            opt_html += f'<span style="color:#3b82f6;font-weight:700;">{line}</span><br>'
        else:
            opt_html += f'{line}<br>'

    canvas_height = max(1200, l2_y_cursor + 200, TOP_START + (len(agents)+1)*AG_GAP + 200)
    sum_top = min(TOP_START + 2*AG_GAP, canvas_height - 400)

    summary_panel = f"""
  <div style="position:absolute;top:{sum_top}px;left:{SUM_X}px;width:{SUM_W}px;z-index:5;
              background:white;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.10);padding:14px 18px;">
    <div style="font-size:11px;font-weight:700;color:#111;margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px;">节点统计</div>
    {sum_rows}
    <hr style="border:none;border-top:1px solid #f3f4f6;margin:8px 0;">
    <div style="display:flex;justify-content:space-between;font-size:12px;font-weight:800;color:#111;">
      <span>合计</span><span>{total_nodes} 节点</span>
    </div>
    <div style="margin-top:10px;font-size:10px;color:#6b7280;line-height:1.7;">
      {opt_html}
    </div>
  </div>"""

    # Build AGENT_CONFIGS JS for drawer
    agent_configs_js = _build_agent_configs_js(agents, fuzzy_samples)

    # Build L2 samples data for click-to-samples modal
    l2_samples_data = {}
    for _ag in agents:
        for _nd in _ag.get("l2_nodes", []):
            _samps = _nd.get("samples", [])
            if _samps or _nd.get("count", 0) > 0:
                l2_samples_data[_nd["id"]] = {
                    "name": _nd["name"],
                    "definition": _nd.get("definition", ""),
                    "count": _nd.get("count", 0),
                    "samples": _samps,
                }
    l2_samples_js = json.dumps(l2_samples_data, ensure_ascii=False)

    # Edges JS
    edges_js = json.dumps(edges, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{brand_name or "意图分析"} — Agent 意图设计图</title>
<style>{CSS}</style>
</head>
<body>

<div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;">
  <div style="flex:1;min-width:0;">
    <h1>{brand_name or "意图分析"} — 意图设计图</h1>
    <div class="sub">{brand_name + ' · ' if brand_name else ''}基于 {total:,} 条对话 · 一个意图 = 一个 Agent · 线宽 = 对话量 · L1→L2→L3 层层流转</div>
    {kpis}
  </div>
  <div style="padding-top:4px;">
    <button class="apply-btn" onclick="openApplyModal()">🚀 批量应用意图</button>
  </div>
</div>

<div class="principle">
  <span>· <b>设计原则1</b>：一个意图 = 一个 Agent，首轮入口唯一</span>
  <span>· <b>设计原则2</b>：Agent 内部节点越少越好（维护成本低，稳定性高）</span>
  <span>· <b>设计原则3</b>：共享节点（黄色）说明两个 Agent 可合并——但需权衡决策树差异</span>
  <span>· <b>设计原则4</b>：总节点数固定，意图分合决定每个 Agent 的复杂度分布</span>
</div>

<div id="flow-outer">
<div id="flow" style="min-height:{canvas_height}px;">
<svg id="svg-lines"></svg>

<div class="col-hdr" style="left:0;width:{AG_W}px;top:4px;background:#2563eb;">路由层 · 首轮判断意图 → 进入 Agent</div>
<div class="col-hdr" style="left:{L2_X}px;width:{L2_W}px;top:4px;background:#7c3aed;">Agent 内部节点 · 多轮处理</div>
<div class="col-hdr" style="left:{SUM_X}px;width:{SUM_W}px;top:4px;background:#0f766e;">总结 · 节点统计与优化</div>

{agent_blocks}
{filter_html}
{l2_nodes_html}
{summary_panel}

</div>
</div>

<!-- SAMPLES MODAL -->
<div class="sm-overlay" id="sm-overlay" onclick="closeSamplesModal()">
  <div class="sm-box" onclick="event.stopPropagation()">
    <div class="sm-header">
      <div class="sm-hdr-left">
        <div class="sm-title" id="sm-title"></div>
        <div class="sm-meta" id="sm-meta"></div>
      </div>
      <span class="sm-close" onclick="closeSamplesModal()">&#215;</span>
    </div>
    <div class="sm-body" id="sm-body"></div>
  </div>
</div>

<!-- DRAWER OVERLAY -->
<div id="cfg-overlay" onclick="closeDrawer()" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.35);z-index:100;"></div>
<!-- DRAWER PANEL -->
<div id="cfg-drawer" style="display:none;position:fixed;top:0;right:0;width:440px;height:100vh;background:white;z-index:101;overflow-y:auto;box-shadow:-4px 0 24px rgba(0,0,0,0.18);transform:translateX(100%);transition:transform 0.25s ease;">
  <div id="cfg-drawer-inner" style="padding:0 0 40px;"></div>
</div>

<script>
const TENANT = '{project_id}';
const REPORT_TOKEN = '__RT__';
const EDGES = {edges_js};
const L2_SAMPLES = {l2_samples_js};

function openSamplesModal(nodeId) {{
  document.body.style.overflow = 'hidden';
  var data = L2_SAMPLES[nodeId];
  if (!data) return;
  var el = document.getElementById(nodeId);
  var color = el ? el.style.borderLeftColor : '#6b7280';
  document.getElementById('sm-title').innerHTML =
    data.name + ' <span class="sm-badge" style="background:' + color + '22;color:' + color + ';">' + data.count + ' 条</span>';
  document.getElementById('sm-meta').textContent = data.definition || '以下为该子意图的样本消息';
  var samples = data.samples || [];
  var body = document.getElementById('sm-body');
  if (samples.length === 0) {{
    body.innerHTML = '<div class="sm-empty">暂无样本消息</div>';
  }} else {{
    body.innerHTML = samples.map(function(s, i) {{
      return '<div class="sm-msg"><div class="sm-msg-num">样本 ' + (i+1) + '</div>' + s + '</div>';
    }}).join('');
  }}
  document.getElementById('sm-overlay').classList.add('open');
}}
function closeSamplesModal() {{
  document.body.style.overflow = '';
  document.getElementById('sm-overlay').classList.remove('open');
}}
document.addEventListener('keydown', function(e) {{ if (e.key === 'Escape') closeSamplesModal(); }});



{EDGE_JS}

const AGENT_CONFIGS = {agent_configs_js};

function openDrawer(key) {{
  const cfg = AGENT_CONFIGS[key];
  if (!cfg) return;
  const c = cfg.color;
  const agentTypeBadge = cfg.agent_type === 'single'
    ? '<span class="dr-type-badge dr-single">Single Agent</span>'
    : '<span class="dr-type-badge dr-chatflow">Chatflow Agent</span>';

  const examplesHtml = (cfg.examples||[]).map(e =>
    `<div style="padding:3px 0;color:#4b5563;font-size:10.5px;">· ${{e}}</div>`
  ).join('');

  const coversHtml = (cfg.covers||[]).map(cv =>
    `<span style="display:inline-block;background:#f3f4f6;border-radius:3px;padding:1px 6px;margin:2px 3px 2px 0;font-size:10px;color:#374151;">${{cv}}</span>`
  ).join('');

  const excludesHtml = (cfg.excludes||[]).map(e =>
    `<div style="font-size:10.5px;color:#7f1d1d;padding:2px 0;line-height:1.6;">✗ ${{e}}</div>`
  ).join('');

  const splitHtml = cfg.split_note
    ? `<div style="margin-top:8px;padding:8px 10px;border-radius:6px;background:#fff7ed;border-left:3px solid #f97316;font-size:10.5px;color:#4b5563;line-height:1.6;">${{cfg.split_note}}</div>`
    : '';

  // Fuzzy match samples section
  let fuzzyHtml = '';
  const fuzzyData = cfg.fuzzy_samples || {{}};
  const fuzzyIntents = Object.keys(fuzzyData);
  if (fuzzyIntents.length > 0) {{
    let fuzzyItems = '';
    fuzzyIntents.forEach(intentName => {{
      const fd = fuzzyData[intentName];
      const total = fd.total_fuzzy || 0;
      const samples = fd.samples || [];
      fuzzyItems += `<div style="font-size:10px;font-weight:700;color:#92400e;margin-bottom:4px;">⚠ ${{total}} 条对话因相似性归入 "${{intentName}}"（非精确匹配）</div>`;
      samples.forEach(s => {{
        const msg = s.first_msg && s.first_msg.length > 50 ? s.first_msg.slice(0, 50) + '...' : (s.first_msg || '');
        fuzzyItems += `<div style="font-size:10px;color:#78350f;padding:2px 0;line-height:1.5;">· [${{s.chat_id}}] "${{msg}}"</div>`;
      }});
    }});
    fuzzyHtml = `
      <div style="margin:12px 0 6px;">
        <div style="font-size:10px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:5px;">模糊匹配样本</div>
        <div style="background:#fffbeb;border-left:3px solid #f59e0b;border-radius:0 6px 6px 0;padding:9px 12px;">
          ${{fuzzyItems}}
        </div>
      </div>`;
  }}

  const nodesHtml = (cfg.nodes||[]).map(n => `
    <div class="dr-node" style="border-left-color:${{c}};">
      <div class="dr-node-name">${{n.name}}</div>
      <div class="dr-node-row"><b>触发条件：</b>${{n.trigger}}</div>
      <div class="dr-node-row"><b>动作：</b>${{n.action}}</div>
    </div>`).join('');

  document.getElementById('cfg-drawer-inner').innerHTML = `
    <div class="dr-hdr" style="border-top:4px solid ${{c}};">
      <div class="dr-title">
        <div class="dr-name">${{cfg.name}}</div>
        <div class="dr-vol" style="margin-top:3px;">${{cfg.vol}}</div>
      </div>
      <span class="dr-close" onclick="closeDrawer()">✕</span>
    </div>
    <div class="dr-body">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
        <div style="width:3px;height:16px;background:${{c}};border-radius:2px;flex-shrink:0;"></div>
        <div style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;color:#111;">① 意图配置</div>
        <div style="font-size:9px;color:#9ca3af;">Solvea 路由层 → 先建意图</div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">
        <div style="font-family:monospace;font-size:12px;font-weight:700;color:#111;background:#f3f4f6;border:1px solid #e5e7eb;display:inline-block;padding:3px 10px;border-radius:4px;">${{cfg.intent_id}}</div>
        <div style="font-size:11.5px;font-weight:700;color:#374151;">${{cfg.display_name}}</div>
      </div>
      <div style="margin-bottom:4px;">${{coversHtml}}</div>
      <div style="margin:10px 0 8px;">
        <div style="font-size:10px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:5px;">意图定义</div>
        <div style="background:#eff6ff;border-left:3px solid ${{c}};border-radius:0 6px 6px 0;padding:9px 12px;font-size:11px;color:#1e3a5f;line-height:1.7;">${{cfg.definition}}</div>
      </div>
      <div style="margin-bottom:10px;">
        <div style="font-size:10px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:5px;">排除条件（边界）</div>
        <div style="background:#fef2f2;border-radius:6px;padding:8px 11px;">${{excludesHtml}}</div>
      </div>
      <div style="margin-bottom:6px;">
        <div style="font-size:10px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:0.4px;margin-bottom:5px;">触发示例语句</div>
        <div style="background:#f9fafb;border-radius:6px;padding:8px 11px;">${{examplesHtml}}</div>
      </div>
      ${{splitHtml}}
      ${{fuzzyHtml}}
      <div style="display:flex;align-items:center;gap:8px;margin:18px 0 10px;">
        <div style="width:3px;height:16px;background:${{c}};border-radius:2px;flex-shrink:0;"></div>
        <div style="font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:0.5px;color:#111;">② Agent 配置</div>
        <div>${{agentTypeBadge}}</div>
      </div>
      ${{nodesHtml}}
    </div>
    <div class="dr-footer">${{cfg.footer}}</div>`;

  const drawer = document.getElementById('cfg-drawer');
  const overlay = document.getElementById('cfg-overlay');
  drawer.style.display = 'block';
  overlay.style.display = 'block';
  requestAnimationFrame(() => {{ drawer.style.transform = 'translateX(0)'; }});
}}

function closeDrawer() {{
  const drawer = document.getElementById('cfg-drawer');
  drawer.style.transform = 'translateX(100%)';
  setTimeout(() => {{
    drawer.style.display = 'none';
    document.getElementById('cfg-overlay').style.display = 'none';
  }}, 260);
}}

function openApplyModal() {{
  const intents = Object.values(AGENT_CONFIGS).map(cfg => ({{
    name: cfg.display_name || cfg.name,
    description: cfg.definition || '',
  }}));
  const tbody = intents.map(it =>
    `<tr><td class="intent-name-cell">${{it.name}}</td><td>${{it.description.slice(0,120)}}${{it.description.length>120?'…':''}}</td></tr>`
  ).join('');
  document.getElementById('apply-preview-body').innerHTML = tbody;
  document.getElementById('apply-count').textContent = intents.length;
  document.getElementById('apply-step').value = '1';
  document.getElementById('apply-modal-title').textContent = '批量应用意图 · 预览';
  document.getElementById('apply-confirm-btn').textContent = '确认应用';
  document.getElementById('apply-confirm-btn').className = 'btn-confirm';
  document.getElementById('apply-warning').style.display = 'none';
  document.getElementById('apply-status').style.display = 'none';
  document.getElementById('apply-modal').classList.add('open');
}}

function closeApplyModal() {{
  document.getElementById('apply-modal').classList.remove('open');
}}

async function confirmApply() {{
  const step = document.getElementById('apply-step').value;
  if (step === '1') {{
    // Move to step 2: irreversible warning
    document.getElementById('apply-step').value = '2';
    document.getElementById('apply-modal-title').textContent = '⚠️ 最终确认';
    document.getElementById('apply-warning').style.display = 'block';
    document.getElementById('apply-confirm-btn').textContent = '确认，不可撤销';
    document.getElementById('apply-confirm-btn').className = 'btn-confirm danger';
    return;
  }}
  // Step 2: actually apply
  const btn = document.getElementById('apply-confirm-btn');
  btn.disabled = true;
  btn.textContent = '应用中…';
  const intents = Object.values(AGENT_CONFIGS).map(cfg => ({{
    name: cfg.display_name || cfg.name,
    description: cfg.definition || '',
  }}));
  try {{
    const resp = await fetch(`https://slg.ericstory.me/intent/apply/${{TENANT}}?rt=${{REPORT_TOKEN}}`, {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ intents }}),
    }});
    const result = await resp.json();
    const statusEl = document.getElementById('apply-status');
    statusEl.style.display = 'block';
    if (resp.ok) {{
      statusEl.className = 'apply-status';
      const detailLines = (result.details || []).join('<br>');
      statusEl.innerHTML = `✅ 完成 · 创建 ${{result.created}} · 更新 ${{result.updated}} · 失败 ${{result.failed}}<br><br>${{detailLines}}`;
      document.getElementById('apply-confirm-btn').style.display = 'none';
      document.getElementById('apply-modal-cancel-btn').textContent = '关闭';
    }} else {{
      statusEl.className = 'apply-status error';
      statusEl.textContent = `❌ 失败: ${{result.error || JSON.stringify(result)}}`;
      btn.disabled = false;
      btn.textContent = '重试';
    }}
  }} catch (e) {{
    document.getElementById('apply-status').style.display = 'block';
    document.getElementById('apply-status').className = 'apply-status error';
    document.getElementById('apply-status').textContent = `❌ 网络错误: ${{e.message}}`;
    btn.disabled = false;
    btn.textContent = '重试';
  }}
}}
</script>

<!-- APPLY MODAL -->
<div class="modal-overlay" id="apply-modal" onclick="if(event.target===this)closeApplyModal()">
  <div class="modal-box">
    <div class="modal-header">
      <h3 id="apply-modal-title">批量应用意图 · 预览</h3>
      <span class="modal-close" onclick="closeApplyModal()">✕</span>
    </div>
    <div class="modal-body">
      <div style="font-size:13px;color:#374151;margin-bottom:12px;">
        将把以下 <b><span id="apply-count">0</span> 个意图</b>应用到当前 Solvea 项目中。
        已有同名意图将被更新，不存在则新建。
      </div>
      <table class="intent-preview-table">
        <thead><tr><th>意图名称</th><th>意图定义</th></tr></thead>
        <tbody id="apply-preview-body"></tbody>
      </table>
      <div id="apply-warning" style="display:none;margin-top:14px;padding:12px 14px;border-radius:8px;background:#fff7ed;border:1px solid #fdba74;font-size:12.5px;color:#92400e;line-height:1.7;">
        ⚠️ <b>此操作不可撤销。</b>继续将直接修改 Solvea 生产数据库中的意图配置，请确认无误后再继续。
      </div>
      <div id="apply-status" style="display:none;" class="apply-status"></div>
      <input type="hidden" id="apply-step" value="1">
    </div>
    <div class="modal-footer">
      <button class="btn-cancel" id="apply-modal-cancel-btn" onclick="closeApplyModal()">取消</button>
      <button class="btn-confirm" id="apply-confirm-btn" onclick="confirmApply()">确认应用</button>
    </div>
  </div>
</div>

</body>
</html>"""

    return html


def _build_agent_configs_js(agents: list, fuzzy_samples: dict = None) -> str:
    """Build the AGENT_CONFIGS JS object for drawer."""
    fuzzy_samples = fuzzy_samples or {}
    configs = {}
    for agent in agents:
        ag_id = agent["id"]
        ic = agent.get("intent_config", {})
        ac = agent.get("agent_config", {})
        count = agent.get("total_count", 0)
        pct = agent.get("total_pct", 0.0)

        # Collect fuzzy samples for this agent's L1 intents
        agent_fuzzy = {}
        for l1_intent in agent.get("l1_intents", []):
            if l1_intent in fuzzy_samples:
                agent_fuzzy[l1_intent] = fuzzy_samples[l1_intent]

        configs[ag_id] = {
            "name": agent.get("name", ag_id),
            "color": agent.get("color", "#6b7280"),
            "vol": f"{count:,}条 · {pct:.1f}%",
            "intent_id": ic.get("id", ag_id),
            "display_name": ic.get("display_name", ""),
            "definition": ic.get("definition", ""),
            "excludes": ic.get("excludes", []),
            "examples": ic.get("examples", []),
            "covers": ic.get("covers", []),
            "split_note": ic.get("split_note"),
            "agent_type": ac.get("type", "chatflow"),
            "nodes": ac.get("nodes", []),
            "footer": ac.get("footer", ""),
            "is_new": agent.get("is_new", False),
            "fuzzy_samples": agent_fuzzy,
        }
    return json.dumps(configs, ensure_ascii=False, indent=2)
