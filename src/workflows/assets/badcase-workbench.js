(() => {
  "use strict";
  const D = JSON.parse(document.getElementById("report-data").textContent);
  const main = document.getElementById("main");
  const E = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
    );
  const displayTime = (value) =>
    String(value || "").replace(
      /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}):\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/,
      (_, date, time, zone) =>
        `${date} ${time} ${["Z", "+00:00"].includes(zone) ? "UTC" : `UTC${zone}`}`,
    );
  const prose = (c, field) =>
    `<div class="markdown">${D.presentation.cases[c.caseId][field].html}</div>`;
  const chatIdButton = (id) =>
    id
      ? `<button type="button" class="copy-id" data-copy-chat-id="${E(id)}" title="复制 chatId" aria-label="复制 chatId ${E(id)}">${E(id)}</button>`
      : "未确认";
  let toastTimer;
  async function copyChatId(id) {
    let copied = false;
    try {
      await navigator.clipboard.writeText(id);
      copied = true;
    } catch {
      // Local HTML files may lack clipboard permission; keep a browser fallback.
      const active = document.activeElement;
      const input = document.createElement("textarea");
      input.value = id;
      input.readOnly = true;
      input.style.cssText = "position:fixed;left:-9999px;top:0";
      document.body.append(input);
      input.select();
      try {
        copied = document.execCommand("copy");
      } catch {
        copied = false;
      } finally {
        input.remove();
        active?.focus({ preventScroll: true });
      }
    }
    const toast = document.getElementById("toast");
    clearTimeout(toastTimer);
    toast.textContent = copied ? "chatId 已复制" : "复制失败，请选中 chatId 手动复制";
    toast.style.display = "block";
    toastTimer = setTimeout(() => {
      toast.style.display = "none";
    }, 2500);
  }
  const cases = new Map(D.cases.map((c) => [c.caseId, c]));
  const conversations = new Map(D.conversations.map((c) => [c.conversationId, c]));
  const fixes = new Map(D.fixes.map((f) => [f.fixId, f]));
  const titles = {
    overview: "总览",
    categories: "按分类排查",
    agents: "按 Agent 排查",
    fixes: "修复与补证",
  };
  const S = {
    view: "overview",
    q: "",
    primary: "",
    secondary: "",
    agent: "",
    certainty: "",
    status: "",
    treatment: "",
    priority: "",
    fix: "",
    blank: false,
    reason: "",
    suggestion: "",
    scroll: 0,
    selected: "",
    pane: "conversation",
  };
  const count = (arr, key) =>
    Object.entries(
      arr.reduce((a, c) => {
        const k = key(c);
        a[k] = (a[k] || 0) + 1;
        return a;
      }, Object.create(null)),
    ).sort((a, b) => b[1] - a[1]);
  const badge = (text, style = "") => `<span class="badge ${style}">${E(text)}</span>`;
  const link = (id) => `<button class="caselink" data-case="${E(id)}">${E(id)} ↗</button>`;
  const filtered = () =>
    D.cases.filter(
      (c) =>
        (!S.primary || (S.primary === "__uncategorized" ? !c.primary : c.primary === S.primary)) &&
        (!S.secondary || c.secondary === S.secondary) &&
        (!S.agent || (S.agent === "__unknown" ? !c.agentId : c.agentId === S.agent)) &&
        (!S.certainty || c.certainty === S.certainty) &&
        (!S.status || c.status === S.status) &&
        (!S.priority || c.priority === S.priority) &&
        (!S.treatment || c.treatment === S.treatment) &&
        (!S.fix || c.fixId === S.fix) &&
        (!S.blank || !c.secondary) &&
        (!S.reason || c.classificationReason === S.reason) &&
        (!S.suggestion || c.suggestedCategory === S.suggestion) &&
        (!S.q ||
          [c.caseId, c.chatId, c.problem, c.agentName, c.diagnosis]
            .join(" ")
            .toLowerCase()
            .includes(S.q.toLowerCase())),
    );
  function resetFilters() {
    for (const k of [
      "q",
      "primary",
      "secondary",
      "agent",
      "certainty",
      "status",
      "treatment",
      "priority",
      "fix",
      "reason",
      "suggestion",
    ])
      S[k] = "";
    S.blank = false;
  }
  function navigate(view) {
    if (S.view !== view) {
      resetFilters();
      S.scroll = 0;
    }
    S.view = view;
    location.hash = view;
    if (location.hash === "#" + view) render();
  }
  function openCase(id) {
    if (!cases.has(id)) return;
    if (!S.selected) S.scroll = window.scrollY;
    location.hash = "case/" + encodeURIComponent(id);
  }
  const caseTable = (list) =>
    list.length
      ? `<div class="tablewrap"><table><thead><tr><th>问题 / 会话</th><th>Agent</th><th>分类</th><th>处理进度</th><th>优先级</th></tr></thead><tbody>${list.map((c) => `<tr><td><button class="case-title" data-case="${E(c.caseId)}">${E(c.problem)}</button><small>${E(c.caseId)} · chatId ${chatIdButton(c.chatId)}</small></td><td>${E(c.agentName || "Agent未确认")}<small>${E(c.agentId)}</small></td><td>${E(c.primary || "未定类")}<small>${E(c.secondary || (c.suggestedCategory ? "建议：" + c.suggestedCategory : "二级待复核"))}</small></td><td>${badge(c.status, c.status === "待补充信息" ? "amber" : "")}<small>${c.certainty === "confirmed" ? "直接原因已确认" : "仍需补证"}</small></td><td>${badge(c.priority, c.priority === "P0" ? "p0" : "")}</td></tr>`).join("")}</tbody></table></div>`
      : '<div class="panel empty">没有符合条件的问题。<br><button class="textbtn" data-clear>清除筛选</button></div>';
  function options(key, label, values) {
    return `<select aria-label="${label}" data-filter="${key}"><option value="">${label}</option>${values.map((v) => `<option value="${E(v[0])}" ${S[key] === v[0] ? "selected" : ""}>${E(v[1])}</option>`).join("")}</select>`;
  }
  function filtersBar() {
    return `<div class="filterbar"><input aria-label="搜索问题" data-search placeholder="搜索问题、chatId、caseId…" value="${E(S.q)}">${options("agent", "全部 Agent", [...new Map(D.cases.map((c) => [c.agentId || "__unknown", c.agentName || c.agentId || "Agent未确认"]))])}${options(
      "status",
      "全部状态",
      [...new Set(D.cases.map((c) => c.status))].map((x) => [x, x]),
    )}${options(
      "treatment",
      "全部处理方式",
      [...new Set(D.cases.map((c) => c.treatment).filter(Boolean))].map((x) => [x, x]),
    )}${options(
      "priority",
      "全部优先级",
      ["P0", "P1", "P2", "P3"].map((x) => [x, x]),
    )}${options("reason", "全部分类情况", [
      ["uncovered", "分类未覆盖"],
      ["insufficient", "分类证据不足"],
      ["nonissue", "非问题"],
      ["unreviewed", "旧分类待复核"],
    ])}${options("certainty", "全部定位程度", [
      ["confirmed", "直接原因已确认"],
      ["partial", "待补证"],
    ])}<button class="button" data-clear>清除</button></div>`;
  }
  function groupPanel() {
    const categoryGroups = count(D.cases, (c) => c.primary || "未定类");
    const supplemental = count(
      D.cases.filter((c) => !c.secondary),
      (c) => c.classificationReason,
    )
      .map(
        ([reason, n]) =>
          `<button data-reason="${E(reason)}">${E({ uncovered: "分类未覆盖", insufficient: "证据不足", nonissue: "非问题", unreviewed: "旧分类待复核" }[reason])}<b>${n}</b></button>`,
      )
      .join("");
    const suggestions = count(
      D.cases.filter((c) => c.classificationReason === "uncovered" && c.suggestedCategory),
      (c) => c.suggestedCategory,
    )
      .map(
        ([name, n]) =>
          `<button class="sub" data-suggestion="${E(name)}">建议：${E(name)}<b>${n}</b></button>`,
      )
      .join("");
    return `<div class="groups"><button data-group="" class="${!S.primary && !S.blank ? "selected" : ""}">全部问题 <b>${D.cases.length}</b></button>${categoryGroups
      .map(
        ([name, n]) =>
          `<button data-group="${E(name)}" class="${S.primary === name || (name === "未定类" && S.primary === "__uncategorized") ? "selected" : ""}">${E(name)}<b>${n}</b></button>${
            S.primary === name
              ? count(
                  D.cases.filter((c) => c.primary === name),
                  (c) => c.secondary || "二级待复核",
                )
                  .map(
                    ([sub, num]) =>
                      `<button class="sub ${S.secondary === sub ? "selected" : ""}" data-secondary="${E(sub)}">${E(sub)}<b>${num}</b></button>`,
                  )
                  .join("")
              : ""
          }`,
      )
      .join(
        "",
      )}<button data-blank class="${S.blank ? "selected" : ""}">二级待复核 <b>${D.cases.filter((c) => !c.secondary).length}</b></button>${supplemental}${suggestions}</div>`;
  }
  function renderList() {
    const list = filtered();
    main.innerHTML = `<div class="pagehead"><div><h1>${titles[S.view]}</h1><p>${S.fix ? `修复项 ${E(S.fix)} · ` : ""}${E(D.batch.tenantName)} · ${D.cases.length} 个问题</p></div></div>${filtersBar()}<div class="results">${
      S.view === "agents"
        ? `<div class="groups"><button data-agent="">全部 Agent <b>${D.cases.length}</b></button>${count(
            D.cases,
            (c) => c.agentId,
          )
            .map(
              ([id, n]) =>
                `<button data-agent="${E(id || "__unknown")}" class="${S.agent === (id || "__unknown") ? "selected" : ""}">${E(D.cases.find((c) => c.agentId === id).agentName || "Agent未确认")}<b>${n}</b></button>`,
            )
            .join("")}</div>`
        : groupPanel()
    }<div><div class="countline"><span id="result-count">${list.length} 个问题 / 全部 ${D.cases.length} 个</span></div><div id="case-list">${caseTable(list)}</div></div></div>`;
  }
  function overview() {
    const confirmed = D.cases.filter((c) => c.certainty === "confirmed").length;
    const unique = new Set(D.cases.map((c) => c.chatId).filter(Boolean)).size;
    const cats = count(D.cases, (c) => c.primary || "未定类");
    const agentCounts = count(D.cases, (c) => c.agentId);
    main.innerHTML = `<div class="pagehead"><div><h1>排查总览</h1><p>${E(D.batch.tenantName)} · ${E(D.batch.scope)}</p></div></div>${D.batch.notice ? `<div class="notice">${E(D.batch.notice)}</div>` : ""}<div class="stats"><button class="stat accent" data-drill="all"><span class="label">问题总数</span><b>${D.cases.length}</b><small>${D.batch.includedCount} 条纳入记录 · ${unique} 个会话</small></button><button class="stat" data-drill="confirmed"><span class="label">已定位原因</span><b>${confirmed}</b><small>${D.cases.filter((c) => c.status === "已验证通过").length} 个已验证通过</small></button><button class="stat" data-drill="partial"><span class="label">待补充证据</span><b>${D.cases.length - confirmed}</b><small>${D.fixes.filter((f) => !f.ready).length} 项方案待补证</small></button><button class="stat" data-drill="P0"><span class="label">P0 优先处理</span><b>${D.cases.filter((c) => c.priority === "P0").length}</b><small>查看关联问题与修复建议</small></button></div><div class="grid2"><section class="panel"><div class="panelhead"><h2>问题分布</h2><button class="textbtn" data-view="categories">按分类排查 ↗</button></div>${cats.map(([name, n]) => `<button class="barrow" data-category-drill="${E(name)}"><span>${E(name)}</span><span class="bartrack"><i style="width:${(n / D.cases.length) * 100}%"></i></span><b>${n}</b></button>`).join("")}<p class="muted" style="font-size:11px">共 ${D.cases.length} 个问题 · <button class="textbtn" data-drill="blank">${D.cases.filter((c) => !c.secondary).length} 项二级分类待复核 ↗</button></p></section><section class="panel"><div class="panelhead"><h2>Agent 分布</h2><button class="textbtn" data-view="agents">查看全部 ↗</button></div>${agentCounts
      .slice(0, 5)
      .map(
        ([id, n]) =>
          `<button class="barrow" style="grid-template-columns:1fr 80px 24px" data-agent-drill="${E(id || "__unknown")}"><span>${E(D.cases.find((c) => c.agentId === id).agentName || "Agent未确认")}</span><span class="bartrack"><i style="width:${(n / D.cases.length) * 100}%"></i></span><b>${n}</b></button>`,
      )
      .join(
        "",
      )}</section></div><div class="grid2"><section class="panel"><div class="panelhead"><h2>主要发现</h2></div>${D.batch.findings.map((f) => `<article class="finding"><h3>${E(f.title)}</h3><p>${E(f.summary)}</p>${f.caseIds.map(link).join("")}</article>`).join("")}</section><section class="panel"><div class="panelhead"><h2>优先修复与补证</h2><button class="textbtn" data-view="fixes">全部 ${D.fixes.length} 项 ↗</button></div>${D.fixes
      .slice()
      .sort((a, b) => a.priority.localeCompare(b.priority))
      .slice(0, 4)
      .map(
        (f) =>
          `<article class="finding">${badge(f.priority, f.priority === "P0" ? "p0" : "")}<button class="textbtn" data-fix="${E(f.fixId)}">${E(f.fixId)} · ${D.cases.filter((c) => c.fixId === f.fixId).length} 个问题 ↗</button><p>${E(f.title)}</p>${badge(f.ready ? "方案就绪" : "方案待核验", f.ready ? "green" : "amber")}</article>`,
      )
      .join(
        "",
      )}</section></div><p class="muted" style="font-size:11px">源记录 ${D.batch.sourceCount} 条 · 纳入 ${D.batch.includedCount} 条 · 排除 ${D.batch.excludedCount} 条。会话按获取时的内容展示，缺失或发送状态不明处单独标注。生成：${E(displayTime(D.batch.generatedAt))}</p>`;
  }
  function renderFixes() {
    const selected = S.fix && fixes.get(S.fix);
    const fs = selected ? [selected] : D.fixes;
    main.innerHTML = `<div class="pagehead"><div><h1>修复与补证</h1><p>按共同修复项组织，逐条对照证据后再实施</p></div>${selected ? '<button class="button" data-all-fixes>全部修复项</button>' : badge(`${fs.length} 项`)}</div><div class="fixgrid">${fs
      .map((f) => {
        const cs = D.cases.filter((c) => c.fixId === f.fixId);
        return `<article class="fixcard">${badge(f.priority, f.priority === "P0" ? "p0" : "")}${badge(f.ready ? "方案就绪" : "方案待核验", f.ready ? "green" : "amber")}<h3>${E(f.title)}</h3><p class="muted" style="font-size:12px">${E(f.fixId)} · ${cs.length} 个关联问题 · ${cs.filter((c) => c.certainty === "confirmed").length} 个直接原因已确认</p>${selected ? cs.map((c) => `<div class="fixcontent">${link(c.caseId)}${prose(c, "recommendation")}${c.gaps ? `<p class="muted">待补证：${E(c.gaps)}</p>` : ""}</div>`).join("") : ""}<footer><span>${cs
          .slice(0, 3)
          .map((c) => link(c.caseId))
          .join(
            "",
          )}</span><button class="textbtn" data-fix="${E(f.fixId)}">${selected ? "查看关联问题" : "展开方案"} ↗</button></footer></article>`;
      })
      .join("")}</div>`;
  }
  function detail(id) {
    const c = cases.get(id);
    if (!c) {
      main.innerHTML =
        '<div class="empty">未找到该 case。<button class="textbtn" data-view="overview">回到总览</button></div>';
      return;
    }
    S.selected = id;
    const conv = conversations.get(c.conversationId);
    const list = filtered();
    const index = list.findIndex((x) => x.caseId === id);
    const labels = {
      customer: "客户",
      ai: "AI 回复",
      human: "人工回复",
      event: "流程记录",
      unknown: "角色未确认",
    };
    main.innerHTML = `<div class="detailtop"><button class="button" data-back>← 返回${titles[S.view]}</button><span class="muted">${E(c.caseId)} · ${E(c.source)}</span><span class="spacer"></span><button class="button" data-prev ${index <= 0 ? "disabled" : ""} aria-label="上一条问题">← 上一条</button><button class="button" data-next ${index < 0 || index >= list.length - 1 ? "disabled" : ""} aria-label="下一条问题">下一条 →</button></div><h1 class="detailtitle">${E(c.problem)}</h1><div class="detailmeta">${badge(c.priority, c.priority === "P0" ? "p0" : "")}${badge(c.status, c.status === "待补充信息" ? "amber" : "")}</div><dl class="case-context"><div><dt>chatId</dt><dd>${chatIdButton(c.chatId)}</dd></div><div><dt>Agent名称</dt><dd>${E(c.agentName || "未确认")}</dd></div><div><dt>agentId</dt><dd>${E(c.agentId || "未确认")}</dd></div><div><dt>Flow版本</dt><dd>会话运行 ${E(c.flowVersion?.historical || "未取得")} · 当前 ${E(c.flowVersion?.current || "未取得")}</dd></div></dl><div class="mobiletabs"><button class="${S.pane === "conversation" ? "active" : ""}" data-pane="conversation">对话</button><button class="${S.pane === "diagnosis" ? "active" : ""}" data-pane="diagnosis">诊断与建议</button></div><div class="workspace" data-pane="${S.pane}"><section class="conversation"><div class="panehead"><h2>会话记录</h2><button class="textbtn" data-target>定位问题消息 ↓</button></div><details class="convnote"><summary>${conv ? `${conv.messages.length} 条会话记录` : "会话记录待补充"}</summary><p>${conv ? `${E(conv.completeness)}<br>取证时间：${E(displayTime(conv.snapshotAt))}` : "缺口见问题定位。"}</p></details><div class="message-scroll">${conv ? conv.messages.map((m, i) => `<article id="message-${i}" class="message ${E(m.role)} ${m.id === c.targetMessageId ? "target" : ""}" data-message-index="${i}"><div class="message-head"><span class="avatar">${m.role === "customer" ? "客" : m.role === "ai" ? "AI" : m.role === "human" ? "人" : "·"}</span><span>${labels[m.role]}</span><span>${E(displayTime(m.time))}</span>${m.turn ? `<span>第 ${E(m.turn)} 轮</span>` : ""}${m.id === c.targetMessageId ? '<span class="targetlabel">本问题目标消息</span>' : ""}</div><div class="bubble">${m.text ? `<div class="markdown">${D.presentation.messages[conv.conversationId][m.id]}</div>` : '<span class="muted">无可展示的对客文本</span>'}${m.attachments.map((a) => `<span class="attachment">附件 · ${E(a)}</span>`).join("")}</div></article>`).join("") : '<div class="empty">会话原文不可用</div>'}</div></section><section class="diagnosis"><div class="panehead"><h2>定位与修复建议</h2>${badge(c.certainty === "confirmed" ? "直接原因已确认" : "待补证", c.certainty === "confirmed" ? "green" : "amber")}</div><div class="diagnosis-content"><section><h3>问题分类</h3><p>${E(c.primary || "未确定")} ${c.secondary ? " / " + E(c.secondary) : " / 二级待复核"}</p>${c.suggestedCategory ? `<p>模型建议分类：${E(c.suggestedCategory)}</p>` : ""}${c.classificationGap ? `<p class="muted" style="font-size:12px;margin-top:8px">${E(c.classificationGap)}</p>` : ""}</section><section><h3>问题定位</h3>${prose(c, "diagnosis")}</section><section><h3>关键证据 <button class="textbtn" data-target>对照目标消息 ↗</button></h3>${prose(c, "evidence")}</section><section class="recommendation"><h3>${E(c.treatment || "处理方式待确认")} · 修复建议</h3>${prose(c, "recommendation")}${c.fixId ? `<button class="textbtn" data-fix="${E(c.fixId)}">关联修复项 ${E(c.fixId)} ↗</button>` : ""}</section>${c.gaps ? `<section class="gap"><h3>待补证</h3>${prose(c, "gaps")}</section>` : ""}<details class="tech"><summary>技术证据与来源</summary><pre>${E(c.technical)}\n\n目标消息：${E(c.targetMessageId || "未取得")}\n${E(c.source)}</pre></details></div></section></div>`;
    requestAnimationFrame(() => focusTarget(false));
  }
  function focusTarget(switchPane = true) {
    if (switchPane) {
      S.pane = "conversation";
      document.querySelector(".workspace")?.setAttribute("data-pane", "conversation");
      document.querySelectorAll("[data-pane].active").forEach((b) => b.classList.remove("active"));
      document.querySelector('button[data-pane="conversation"]')?.classList.add("active");
    }
    const target = document.querySelector(".message.target");
    const sc = document.querySelector(".message-scroll");
    if (target && sc)
      sc.scrollTo({
        top:
          sc.scrollTop + target.getBoundingClientRect().top - sc.getBoundingClientRect().top - 20,
        behavior: "instant",
      });
  }
  function render() {
    let hash;
    try {
      hash = decodeURIComponent(location.hash.slice(1));
    } catch {
      hash = "overview";
    }
    document.getElementById("breadcrumb").textContent =
      `${titles[S.view]}${hash.startsWith("case/") ? " / 问题详情" : ""}`;
    document
      .querySelectorAll("nav button")
      .forEach((b) => b.classList.toggle("active", b.dataset.view === S.view));
    if (hash.startsWith("case/")) {
      detail(hash.slice(5));
      return;
    }
    S.selected = "";
    if (titles[hash]) S.view = hash;
    document
      .querySelectorAll("nav button")
      .forEach((b) => b.classList.toggle("active", b.dataset.view === S.view));
    document.getElementById("breadcrumb").textContent = `${titles[S.view]}`;
    if (S.view === "overview") overview();
    else if (S.view === "fixes") renderFixes();
    else renderList();
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.hasAttribute("data-copy-chat-id")) {
      void copyChatId(b.dataset.copyChatId);
    } else if (b.dataset.view) {
      navigate(b.dataset.view);
      window.scrollTo(0, 0);
    } else if (b.dataset.case) openCase(b.dataset.case);
    else if (b.hasAttribute("data-back")) {
      location.hash = S.view;
      render();
      requestAnimationFrame(() => window.scrollTo(0, S.scroll));
    } else if (b.hasAttribute("data-prev") || b.hasAttribute("data-next")) {
      const list = filtered(),
        i = list.findIndex((c) => c.caseId === S.selected);
      const next = list[i + (b.hasAttribute("data-prev") ? -1 : 1)];
      if (next) openCase(next.caseId);
    } else if (b.hasAttribute("data-target")) focusTarget();
    else if (b.dataset.pane) {
      S.pane = b.dataset.pane;
      document.querySelector(".workspace").dataset.pane = S.pane;
      document
        .querySelectorAll(".mobiletabs button")
        .forEach((x) => x.classList.toggle("active", x.dataset.pane === S.pane));
    } else if (b.hasAttribute("data-clear")) {
      resetFilters();
      render();
    } else if (b.hasAttribute("data-group")) {
      S.primary = b.dataset.group === "未定类" ? "__uncategorized" : b.dataset.group;
      S.secondary = "";
      S.blank = false;
      render();
    } else if (b.hasAttribute("data-secondary")) {
      S.secondary = b.dataset.secondary === "二级待复核" ? "" : b.dataset.secondary;
      S.blank = b.dataset.secondary === "二级待复核";
      render();
    } else if (b.hasAttribute("data-blank")) {
      S.primary = "";
      S.secondary = "";
      S.blank = true;
      render();
    } else if (b.dataset.reason) {
      resetFilters();
      S.reason = b.dataset.reason;
      render();
    } else if (b.dataset.suggestion) {
      resetFilters();
      S.suggestion = b.dataset.suggestion;
      render();
    } else if (b.hasAttribute("data-agent")) {
      S.agent = b.dataset.agent;
      render();
    } else if (b.dataset.drill) {
      resetFilters();
      const k = b.dataset.drill;
      if (k === "P0") S.priority = "P0";
      if (["confirmed", "partial"].includes(k)) S.certainty = k;
      if (k === "blank") S.blank = true;
      S.view = "categories";
      location.hash = "categories";
      render();
    } else if (b.dataset.categoryDrill) {
      resetFilters();
      if (b.dataset.categoryDrill === "未定类") S.primary = "__uncategorized";
      else S.primary = b.dataset.categoryDrill;
      S.view = "categories";
      location.hash = "categories";
      render();
    } else if (b.dataset.agentDrill) {
      resetFilters();
      S.agent = b.dataset.agentDrill;
      S.view = "agents";
      location.hash = "agents";
      render();
    } else if (b.dataset.fix) {
      const id = b.dataset.fix;
      const wasFix = S.view === "fixes" && S.fix === id && !S.selected;
      resetFilters();
      S.fix = id;
      if (wasFix) {
        S.view = "categories";
        location.hash = "categories";
      } else {
        S.view = "fixes";
        S.fix = id;
        location.hash = "fixes";
      }
      render();
      window.scrollTo(0, 0);
    } else if (b.hasAttribute("data-all-fixes")) {
      S.fix = "";
      render();
    }
  });
  main.addEventListener("change", (e) => {
    if (e.target.dataset.filter) {
      S[e.target.dataset.filter] = e.target.value;
      render();
    }
  });
  main.addEventListener("input", (e) => {
    if (e.target.hasAttribute("data-search")) {
      S.q = e.target.value;
      const list = filtered();
      document.getElementById("result-count").textContent =
        `${list.length} 个问题 / 全部 ${D.cases.length} 个`;
      document.getElementById("case-list").innerHTML = caseTable(list);
    }
  });
  window.addEventListener("hashchange", render);
  document.getElementById("tenant").textContent = D.batch.tenantName;
  document.getElementById("scope").textContent =
    `${D.batch.accountId} · ${{ prod: "生产环境", staging: "测试环境" }[D.batch.environment] || D.batch.environment}`;
  document.getElementById("snapshot").textContent = `分析时间 · ${displayTime(D.batch.snapshotAt)}`;
  document.title = `${D.batch.tenantName} · CXClaw 排查工作台`;
  render();
})();
