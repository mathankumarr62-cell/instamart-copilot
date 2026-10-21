/* Instamart Copilot dashboard: hash router, API client and one renderer per section.
   Every value shown comes from the local API; all text is inserted with textContent (no innerHTML). */
"use strict";

(() => {
  const VIEWS = ["overview", "data", "sql", "segments", "lapse", "triage", "policy", "agent", "about"];
  const TITLES = {
    overview: "Overview", data: "Data Quality", sql: "SQL Insights", segments: "Customer Segments",
    lapse: "Lapse Risk", triage: "Support Triage", policy: "Policy Assistant", agent: "Refund Agent", about: "About",
  };
  const apiCache = {};
  const rendered = {};

  /* ---------------- formatting (INR everywhere, never a currency symbol) ---------------- */
  const fmt2 = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmt0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const isNum = (v) => typeof v === "number" && Number.isFinite(v);
  const inr = (v) => (isNum(v) ? ("INR " + (v < 0 ? "−" : "") + (fmt2.format(Math.abs(v)))) : "–");
  const int = (v) => (isNum(v) ? fmt0.format(v) : "–");
  const dec = (v, d = 3) => (isNum(v) ? new Intl.NumberFormat("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }).format(v) : "–");
  const pct = (v, d = 1) => (isNum(v) ? ("" + (dec(v, d)) + "%") : "–");
  const isMoneyKey = (k) => k.endsWith("_inr") || k === "total_spend";
  const cell = (k, v) => (v === null || v === undefined || v === "" ? "–" : isMoneyKey(k) && isNum(v) ? inr(v) : isNum(v) ? (Number.isInteger(v) ? int(v) : String(v)) : String(v));

  /* ---------------- DOM helpers ---------------- */
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : String(v));
    }
    add(el, kids);
    return el;
  }
  function add(el, kids) {
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid instanceof Node ? kid : String(kid));
    }
    return el;
  }
  const card = (title, ...kids) => h("div", { class: "card" }, h("h2", { text: title }), kids);
  const sub = (text) => h("p", { class: "card-sub", text });
  const kpi = (label, value, note) => h("div", { class: "kpi" }, h("div", { class: "kpi-label", text: label }),
    h("div", { class: "kpi-value", text: value }), note ? h("div", { class: "kpi-note", text: note }) : null);
  const kv = (pairs) => h("dl", { class: "kv" }, pairs.map(([k, v]) => [h("dt", { text: k }), h("dd", {}, v)]));
  const STATUS_TONE = {
    PASS: "success", FAIL: "danger", INFO: "info", REFUND: "success", ESCALATE: "warning", DENIED: "neutral",
    NOT_FOUND: "neutral", classified_json: "success", classified_keyword: "success", flagged_invalid_output: "warning",
    skipped_empty: "neutral", flagged_long: "warning", budget_exhausted: "warning", passed: "success",
    security_team: "danger", premium_desk: "accent", human_review: "warning", support_queue: "neutral",
    HIGH: "danger", NORMAL: "neutral",
  };
  const tone = (s) => STATUS_TONE[s] || (String(s).startsWith("FALLBACK") ? "danger" : "neutral");
  const badge = (text, t) => h("span", { class: ("badge badge-" + (t || tone(text))), text });

  const announce = (msg) => { const el = document.getElementById("status-live"); el.textContent = ""; setTimeout(() => { el.textContent = msg; }, 30); };
  const loadingState = (msg) => h("div", { class: "state", role: "status" }, h("span", { class: "spinner", "aria-hidden": "true" }), msg);
  const emptyState = (msg) => h("div", { class: "state", text: msg });
  const errorState = (err, retry) => h("div", { class: "state state-error", role: "alert" },
    h("strong", { text: "Something went wrong. " }), err.message,
    retry ? h("div", { class: "row" }, h("button", { class: "btn btn-secondary btn-small", type: "button", onclick: retry, text: "Try again" })) : null);

  /* ---------------- API client ---------------- */
  async function api(path, { method = "GET", body, timeout = 60000 } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(path, {
        method, signal: ctrl.signal,
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      let data = null;
      try { data = await res.json(); } catch (_) { data = null; }
      if (!res.ok) throw new Error((data && data.error) || ("Request failed with status " + (res.status) + "."));
      if (data === null) throw new Error("The server returned an empty response.");
      return data;
    } catch (err) {
      if (err.name === "AbortError") throw new Error("The request timed out.");
      if (err instanceof TypeError) throw new Error("Cannot reach the dashboard server. Is python app/server.py running?");
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }
  function getCached(path) {
    if (!apiCache[path]) apiCache[path] = api(path).catch((err) => { delete apiCache[path]; throw err; });
    return apiCache[path];
  }
  /** Disable the given controls while fn runs; the first one shows busyText. */
  async function busy(controls, busyText, fn) {
    const [main] = controls;
    const label = main.textContent;
    controls.forEach((c) => { c.disabled = true; });
    main.textContent = busyText;
    try { return await fn(); } finally {
      controls.forEach((c) => { c.disabled = false; });
      main.textContent = label;
    }
  }

  /* ---------------- tables ---------------- */
  /** columns: [{key, label, num, fmt(v,row), cls, rowHeader, sort}] */
  function table(columns, rows, opts = {}) {
    const { caption, sortable = false, rowClass, tall = false, label, emptyText = "No rows to show." } = opts;
    let data = rows.slice();
    let sortKey = null;
    let dir = 1;
    const wrap = h("div", { class: ("table-wrap" + (tall ? " tall" : "")), tabindex: "0", role: "region", "aria-label": label || caption || "Table" });
    const tbl = h("table", {}, caption ? h("caption", { text: caption }) : null);
    const headRow = h("tr");
    const heads = columns.map((c) => {
      const th = h("th", { scope: "col", class: c.num ? "num" : null });
      if (sortable && c.sort !== false) {
        const ind = h("span", { class: "sort-ind", "aria-hidden": "true", text: "↕" });
        th.setAttribute("aria-sort", "none");
        th.append(h("button", { class: "sort-btn", type: "button", onclick: () => sortBy(c.key) }, c.label, ind));
        return { th, ind, key: c.key };
      }
      th.textContent = c.label;
      return { th, key: c.key };
    });
    heads.forEach((x) => headRow.append(x.th));
    const tbody = h("tbody");
    tbl.append(h("thead", {}, headRow), tbody);
    wrap.append(tbl);

    function render() {
      if (!data.length) {
        tbody.replaceChildren(h("tr", {}, h("td", { colspan: String(columns.length), class: "muted", text: emptyText })));
        return;
      }
      tbody.replaceChildren(...data.map((r) => h("tr", { class: rowClass ? rowClass(r) : null }, columns.map((c) => {
        const v = r[c.key];
        const content = c.fmt ? c.fmt(v, r) : cell(c.key, v);
        const extra = typeof c.cls === "function" ? c.cls(r) : c.cls;
        const node = h(c.rowHeader ? "th" : "td", { scope: c.rowHeader ? "row" : null, class: [c.num ? "num" : "", extra || ""].join(" ").trim() || null }, content);
        if (c.decorate) c.decorate(node, v, r);
        return node;
      }))));
    }
    function sortBy(key) {
      if (sortKey === key) dir = -dir; else { sortKey = key; dir = 1; }
      applySort();
    }
    function applySort() {
      data.sort((a, b) => {
        const x = a[sortKey]; const y = b[sortKey];
        if (isNum(x) && isNum(y)) return (x - y) * dir;
        return String(x ?? "").localeCompare(String(y ?? ""), undefined, { numeric: true }) * dir;
      });
      heads.forEach((x) => {
        if (!x.ind) return;
        const on = x.key === sortKey;
        x.th.setAttribute("aria-sort", on ? (dir === 1 ? "ascending" : "descending") : "none");
        x.ind.textContent = on ? (dir === 1 ? "▲" : "▼") : "↕";
      });
      render();
    }
    wrap.setRows = (next) => { data = next.slice(); if (sortKey) applySort(); else render(); };
    render();
    return wrap;
  }

  /** Horizontal CSS bars: items [{label, value, text, negative}] scaled to max |value|. */
  function bars(items, label) {
    const max = Math.max(...items.map((i) => Math.abs(i.value)), 1e-9);
    return h("div", { class: "bars", role: "list", "aria-label": label }, items.map((i) => {
      const fill = h("div", { class: ("bar-fill" + (i.negative ? " neg" : "")) });
      fill.style.width = ("" + ((Math.abs(i.value) / max) * 100) + "%");
      return h("div", { class: "bar-row", role: "listitem" },
        h("span", { class: "bar-label", text: i.label }),
        h("div", { class: "bar-track", "aria-hidden": "true" }, fill),
        h("span", { class: "num", text: i.text }));
    }));
  }

  /** 2x2 confusion matrix [[TN, FP], [FN, TP]] for the lapsed class. */
  function confusion(title, m) {
    const c = (n, tag, ok) => h("div", { class: ("cm-cell " + (ok ? "cm-ok" : "cm-bad")) }, int(n), h("small", { text: tag }));
    return h("figure", { class: "stack", "aria-label": ("" + (title) + " confusion matrix") },
      h("figcaption", {}, h("strong", { text: title })),
      h("div", { class: "cm" },
        h("div", {}), h("div", { class: "cm-head", text: "Pred. stayed" }), h("div", { class: "cm-head", text: "Pred. lapsed" }),
        h("div", { class: "cm-head", text: "Stayed" }), c(m[0][0], "TN", true), c(m[0][1], "FP", false),
        h("div", { class: "cm-head", text: "Lapsed" }), c(m[1][0], "FN", false), c(m[1][1], "TP", true)));
  }

  function codeBlock(text, label) {
    const pre = h("pre", { tabindex: "0", "aria-label": label }, h("code", { text }));
    const btn = h("button", { class: "btn btn-secondary btn-small copy-btn", type: "button", text: "Copy" });
    btn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text);
        btn.textContent = "Copied";
      } catch (_) {
        const range = document.createRange();
        range.selectNodeContents(pre);
        const sel = window.getSelection();
        sel.removeAllRanges(); sel.addRange(range);
        btn.textContent = "Selected";
      }
      announce(("" + (label) + " copied"));
      setTimeout(() => { btn.textContent = "Copy"; }, 1500);
    });
    return h("div", { class: "code-block" }, pre, btn);
  }

  /** Accessible tabs with arrow-key navigation: tabs [{id, label, panel: () => Node}] */
  function tabs(name, items) {
    const list = h("div", { class: "tablist", role: "tablist", "aria-label": name });
    const panels = h("div");
    const buttons = items.map((it, i) => {
      const btn = h("button", {
        class: "tab", type: "button", role: "tab", id: ("tab-" + (it.id)), "aria-controls": ("panel-" + (it.id)),
        "aria-selected": i === 0 ? "true" : "false", tabindex: i === 0 ? "0" : "-1", text: it.label,
      });
      const panel = h("div", { role: "tabpanel", id: ("panel-" + (it.id)), "aria-labelledby": ("tab-" + (it.id)), tabindex: "0" });
      if (i !== 0) panel.hidden = true;
      it.panelEl = panel;
      panels.append(panel);
      btn.addEventListener("click", () => select(i));
      list.append(btn);
      return btn;
    });
    const built = new Set();
    function select(i, focus = false) {
      buttons.forEach((b, j) => {
        b.setAttribute("aria-selected", j === i ? "true" : "false");
        b.tabIndex = j === i ? 0 : -1;
        items[j].panelEl.hidden = j !== i;
      });
      if (!built.has(i)) { items[i].panelEl.append(items[i].panel()); built.add(i); }
      if (focus) buttons[i].focus();
    }
    list.addEventListener("keydown", (e) => {
      const i = buttons.indexOf(document.activeElement);
      if (i < 0) return;
      const keys = { ArrowRight: (i + 1) % buttons.length, ArrowLeft: (i - 1 + buttons.length) % buttons.length, Home: 0, End: buttons.length - 1 };
      if (e.key in keys) { e.preventDefault(); select(keys[e.key], true); }
    });
    select(0);
    return h("div", {}, list, panels);
  }

  /* ---------------- 1 Overview ---------------- */
  async function renderOverview() {
    const d = await getCached("/api/overview");
    const k = d.kpis;
    const cp = d.checkpoints;
    const kpis = h("div", { class: "grid grid-kpi" },
      kpi("Clean orders", int(k.clean_orders), ("" + (int(k.completed_orders)) + " completed")),
      kpi("Completed revenue", inr(k.completed_revenue_inr), "completed orders only"),
      kpi("Customers", int(k.customers), ("" + (int(k.customers_with_orders)) + " with a completed order")),
      kpi("Segments", int(k.segments), "K-means on recency, frequency, monetary"),
      kpi("Lapse rate", pct(k.lapse_rate_pct, 2), "of the lapse cohort in September"),
      kpi("Tickets triaged", int(k.tickets_triaged), ("few-shot accuracy " + (pct(k.few_shot_accuracy_pct)))),
      kpi("Agent scenarios", ("" + (k.scenarios_passed) + "/" + (k.scenarios_total)), "ended with the expected outcome"));

    const steps = [
      ["Raw data", "generate_data.py writes dirty CSV exports, tickets and five policy files"],
      ["Part A", ("clean, store in SQLite, SQL Q1\u2013Q7: " + (int(k.clean_orders)) + " clean orders")],
      ["Part B", ("RFM segments (K = " + (k.segments) + ") and a lapse model")],
      ["Part C", ("triage of " + (int(k.tickets_triaged)) + " tickets with guardrails and routing")],
      ["Part D", ("policy RAG and refund agent: " + (k.scenarios_passed) + "/" + (k.scenarios_total) + " scenarios")],
    ];
    const flow = h("ol", { class: "flow", "aria-label": "Pipeline flow" });
    steps.forEach(([title, text], i) => {
      if (i) flow.append(h("li", { class: "flow-arrow", "aria-hidden": "true", text: "→" }));
      flow.append(h("li", { class: "flow-step" }, h("strong", { text: title }), h("span", { class: "small muted", text })));
    });

    const partSel = h("select", { id: "cp-part" }, ["All parts", "Part A", "Part B", "Part C", "Part D"].map((p) => h("option", { value: p, text: p })));
    const statusSel = h("select", { id: "cp-status" }, ["All", "PASS", "FAIL", "INFO"].map((s) => h("option", { value: s, text: s })));
    const tbl = table([
      { key: "part", label: "Part", cls: "nowrap" },
      { key: "name", label: "Checkpoint", cls: "wrap" },
      { key: "expected", label: "Expected", cls: "wrap mono" },
      { key: "actual", label: "Actual", cls: "wrap mono" },
      { key: "status", label: "Result", fmt: (v) => badge(v) },
    ], cp.checks, { label: "Checkpoint results", tall: true, sortable: true });
    const count = h("p", { class: "small muted", role: "status" });
    const apply = () => {
      const rows = cp.checks.filter((r) => (partSel.value === "All parts" || r.part === partSel.value) && (statusSel.value === "All" || r.status === statusSel.value));
      tbl.setRows(rows);
      count.textContent = ("Showing " + (rows.length) + " of " + (cp.checks.length) + " rows.");
    };
    partSel.addEventListener("change", apply);
    statusSel.addEventListener("change", apply);
    apply();
    const info = cp.checks.length - cp.total;
    return [
      kpis,
      card("Pipeline", sub("Each part reads the previous part's outputs."), flow),
      card("Reference checkpoints",
        h("p", {}, badge(cp.all_passed ? "ALL CHECKPOINTS PASSED" : ("" + (cp.total - cp.passed) + " FAILED"), cp.all_passed ? "success" : "danger"), " ",
          ("" + (cp.passed) + " of " + (cp.total) + " gating checks pass" + (info ? ("; " + (info) + " informational row" + (info > 1 ? "s" : "") + " (never gating)") : "") + ". Same list as python validate.py.")),
        h("div", { class: "check-filters" },
          h("div", { class: "field" }, h("label", { for: "cp-part", text: "Part" }), partSel),
          h("div", { class: "field" }, h("label", { for: "cp-status", text: "Result" }), statusSel)),
        count, tbl),
    ];
  }

  /* ---------------- 2 Data quality ---------------- */
  const AUDIT_LABELS = {
    orders_rows: "Raw orders.csv rows", exact_duplicate_rows: "Exact duplicate rows", pending_rows: "Rows with status pending",
    distinct_order_id: "Distinct order_id", non_numeric_amounts: "order_amount entries that are not numbers",
    negative_delivery_minutes: "Negative delivery_minutes", blank_delivery_minutes: "Blank delivery_minutes",
    blank_age: "Blank age", age_outside_10_100: "Age outside 10–100", raw_city_spellings: "Distinct raw city spellings",
    raw_gender_spellings: "Distinct non-blank raw gender spellings", blank_gender: "Blank gender",
  };
  async function renderData() {
    const d = await getCached("/api/part-a");
    const tables = Object.entries(d.audit.tables).map(([name, t]) => {
      const missing = Object.entries(t.missing).filter(([, m]) => m.count > 0).map(([col, m]) => ("" + (col) + " " + (int(m.count)) + " (" + (pct(m.pct, 2)) + ")"));
      return { table: ("" + (name) + ".csv"), rows: t.rows, columns: t.columns, missing: missing.length ? missing.join(", ") : "none",
        dtypes: Object.entries(t.dtypes).map(([c, dt]) => ("" + (c) + ": " + (dt))).join(", ") };
    });
    const figures = Object.entries(d.audit.figures).map(([k, v]) => ({ figure: AUDIT_LABELS[k] || k, value: v }));
    const rules = [];
    ["customers", "orders"].forEach((t) => (d.cleaning_rules[t] || []).forEach((r) => rules.push({ step: rules.length + 1, table: t, rule: r.rule, changed: r.changed })));
    const f = d.audit.figures; const o = d.orders_clean; const c = d.customers_clean;
    const beforeAfter = [
      { item: "Order rows", before: f.orders_rows, after: o.rows },
      { item: "Exact duplicate rows", before: f.exact_duplicate_rows, after: 0 },
      { item: "Extra rows beyond one per order_id", before: f.orders_rows - f.distinct_order_id, after: o.rows - o.distinct_order_id },
      { item: "Pending orders", before: f.pending_rows, after: o.pending },
      { item: "Unusable order_amount", before: f.non_numeric_amounts, after: o.missing_order_amount },
      { item: "Blank delivery_minutes (completed orders after cleaning)", before: f.blank_delivery_minutes, after: o.missing_delivery_completed },
      { item: "Blank age", before: f.blank_age, after: c.missing_age },
      { item: "City spellings", before: f.raw_city_spellings, after: Object.keys(c.city_counts).length },
      { item: "Blank gender", before: f.blank_gender, after: 0 },
    ];
    return [
      card("Raw audit", sub("Only empty cells count as missing, so junk text such as N/A stays visible."),
        table([{ key: "table", label: "Table", rowHeader: true }, { key: "rows", label: "Rows", num: true }, { key: "columns", label: "Columns", num: true },
          { key: "missing", label: "Columns with missing values", cls: "wrap" }, { key: "dtypes", label: "Types as loaded", cls: "wrap small" }], tables, { label: "Raw table audit" })),
      h("div", { class: "grid grid-2" },
        card("Audit figures", table([{ key: "figure", label: "Figure", rowHeader: true, cls: "wrap" }, { key: "value", label: "Value", num: true }], figures, { label: "Audit figures" })),
        card("Before and after cleaning",
          table([{ key: "item", label: "Item", rowHeader: true, cls: "wrap" }, { key: "before", label: "Raw", num: true }, { key: "after", label: "Clean", num: true }], beforeAfter, { label: "Before and after counts" }),
          h("p", { class: "small muted" }, ("Completed revenue after cleaning: " + (inr(o.completed_revenue_inr)) + " from " + (int(o.completed)) + " completed orders; " + (int(o.cancelled)) + " cancelled orders keep delivery_minutes blank.")))),
      card("Cleaning-rule log", sub("Applied in this order; counts are rows or values changed."),
        table([{ key: "step", label: "#", num: true }, { key: "table", label: "Table" }, { key: "rule", label: "Rule", cls: "wrap" }, { key: "changed", label: "Changed", num: true }], rules, { label: "Cleaning rules" })),
      h("div", { class: "grid grid-3" },
        card("Clean customers by city", table([{ key: "city", label: "City", rowHeader: true }, { key: "n", label: "Customers", num: true }],
          Object.entries(c.city_counts).map(([city, n]) => ({ city, n })), { label: "Customers by city" })),
        card("Clean customers by gender", table([{ key: "g", label: "Gender", rowHeader: true }, { key: "n", label: "Customers", num: true }],
          Object.entries(c.gender_counts).map(([g, n]) => ({ g, n })), { label: "Customers by gender" }),
          h("p", { class: "small muted" }, ("Ages now range from " + (c.age_min) + " to " + (c.age_max) + "."))),
        card("SQLite tables", table([{ key: "t", label: "Table", rowHeader: true }, { key: "n", label: "Rows", num: true }],
          Object.entries(d.database_row_counts).map(([t, n]) => ({ t, n })), { label: "Database row counts" }))),
    ];
  }

  /* ---------------- 3 SQL insights ---------------- */
  function q2Pivot(q) {
    const cities = [...new Set(q.rows.map((r) => r[0]))].sort();
    const cats = [...new Set(q.rows.map((r) => r[1]))].sort();
    const val = {};
    q.rows.forEach(([city, cat, v]) => { val[("" + (city) + "|" + (cat))] = v; });
    const max = Math.max(...q.rows.map((r) => r[2]));
    const rows = cities.map((city) => {
      const row = { city };
      cats.forEach((cat) => { row[cat] = val[("" + (city) + "|" + (cat))] ?? 0; });
      row.Total = cats.reduce((s, cat) => s + row[cat], 0);
      return row;
    });
    const totals = { city: "All", _total: true };
    cats.concat("Total").forEach((cat) => { totals[cat] = rows.reduce((s, r) => s + r[cat], 0); });
    const cols = [{ key: "city", label: "City", rowHeader: true }].concat(cats.map((cat) => ({
      key: cat, label: cat, num: true, fmt: (v) => inr(v), cls: (r) => (r._total ? "" : "heat"),
      decorate: (node, v, r) => { if (!r._total) node.style.setProperty("--h", (v / max).toFixed(3)); },
    })), [{ key: "Total", label: "Total", num: true, fmt: (v) => inr(v) }]);
    return table(cols, rows.concat(totals), { label: "Completed revenue by city and category", rowClass: (r) => (r._total ? "total-row" : null),
      caption: "Completed revenue (INR); darker cells earned more" });
  }
  function sqlPanel(name, q) {
    const facts = Object.entries(q.summary || {}).map(([k, v]) => h("span", { class: "chip chip-static" }, ("" + (k.replace(/_/g, " ")) + ": "), h("strong", { text: cell(k, v) })));
    const shown = q.rows.length;
    const result = name === "Q2" ? q2Pivot(q)
      : table(q.columns.map((col) => ({ key: col, label: col, num: q.rows.some((r) => isNum(r[q.columns.indexOf(col)])) })),
        q.rows.map((r) => Object.fromEntries(q.columns.map((col, i) => [col, r[i]]))), { label: ("" + (name) + " result"), tall: true, sortable: true });
    return h("div", { class: "stack" },
      h("h3", {}, ("" + (name) + " \u00b7 " + (q.technique || ""))),
      h("p", { class: "muted", text: q.description || "" }),
      facts.length ? h("div", { class: "row" }, facts) : null,
      codeBlock(q.sql, ("" + (name) + " SQL")),
      h("p", { class: "small muted" }, ("" + (int(q.row_count)) + " result row" + (q.row_count === 1 ? "" : "s") + (shown < q.row_count ? ("; showing the first " + (int(shown))) : "") + ".")),
      result);
  }
  async function renderSql() {
    const d = await getCached("/api/part-a");
    const names = Object.keys(d.sql);
    if (!names.length) return [emptyState("No SQL results in the report.")];
    return [card("Queries", tabs("SQL queries", names.map((n) => ({ id: ("sql-" + (n)), label: n, panel: () => sqlPanel(n, d.sql[n]) }))))];
  }

  /* ---------------- 4 Customer segments ---------------- */
  function lookupForm() {
    const input = h("input", { type: "text", id: "cust-id", name: "customer_id", autocomplete: "off", spellcheck: "false", maxlength: "5", "aria-describedby": "cust-hint", required: true });
    const btn = h("button", { class: "btn", type: "submit", text: "Look up" });
    const out = h("div", { "aria-live": "polite" });
    const form = h("form", { class: "form-grid", novalidate: true },
      h("div", { class: "field" }, h("label", { for: "cust-id", text: "Customer id" }), input,
        h("span", { class: "hint", id: "cust-hint", text: "Format C followed by four digits, for example C0060." })),
      h("div", {}, btn));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = input.value.trim().toUpperCase();
      if (id.length !== 5 || !/^C\d{4}/.test(id)) { out.replaceChildren(errorState(new Error("Enter an id such as C0060."))); input.focus(); return; }
      out.replaceChildren(loadingState(("Looking up " + (id) + "\u2026")));
      try {
        const c = await busy([btn], "Looking up…", () => api(("/api/customers/" + (encodeURIComponent(id)))));
        out.replaceChildren(customerCard(c));
      } catch (err) { out.replaceChildren(errorState(err)); }
    });
    return h("div", { class: "stack" }, form, out);
  }
  function customerCard(c) {
    const seg = c.segment;
    const lapse = c.lapse;
    const items = [["City", c.city], ["Age", String(c.age)], ["Gender", c.gender], ["Signed up", c.signup_date]];
    if (seg) {
      items.push(["Segment", h("span", {}, seg.segment_name, " ", seg.is_premium ? badge("Premium", "warning") : null)],
        ["Recency", ("" + (int(seg.recency)) + " days")], ["Frequency", ("" + (int(seg.frequency)) + " orders")], ["Monetary", inr(seg.monetary)]);
    } else items.push(["Segment", "none (no completed order)"]);
    if (lapse) {
      items.push(["Lapse probability", h("span", {}, h("strong", { text: pct(lapse.lapse_probability * 100) }),
        " ", badge(lapse.in_test_set ? "test set: out-of-sample" : "training set: in-sample", lapse.in_test_set ? "info" : "neutral"))],
      ["Actually lapsed in September", lapse.actually_lapsed ? "yes" : "no"]);
    } else items.push(["Lapse probability", "not in the lapse cohort (no completed order before the cutoff)"]);
    return h("div", { class: "card" }, h("h3", { text: c.customer_id }), kv(items));
  }
  async function renderSegments() {
    const d = await getCached("/api/part-b");
    const s = d.segments;
    const total = s.profile.reduce((n, p) => n + p.size, 0);
    const cards = s.profile.slice().sort((a, b) => b.monetary - a.monetary).map((p) => h("article", { class: ("card seg-card" + (p.is_premium ? " premium" : "")) },
      h("div", { class: "row" }, h("h3", { text: p.segment_name }), p.is_premium ? badge("Premium", "warning") : null),
      h("p", { class: "small muted" }, ("Segment id " + (p.segment_id) + " \u00b7 " + (int(p.size)) + " customers (" + (pct((100 * p.size) / total)) + ")")),
      h("dl", { class: "seg-stats" },
        h("div", {}, h("dt", { text: "Mean recency" }), h("dd", { text: ("" + (dec(p.recency, 1)) + " d") })),
        h("div", {}, h("dt", { text: "Mean frequency" }), h("dd", { text: dec(p.frequency, 1) })),
        h("div", {}, h("dt", { text: "Mean monetary" }), h("dd", { text: inr(p.monetary) }))),
      h("p", {}, h("strong", { text: "Action: " }), p.action)));
    const best = Math.max(...s.k_sweep.map((r) => r.silhouette));
    return [
      h("div", { class: "grid grid-kpi" },
        kpi("Customers segmented", int(s.rfm.customers), "with at least one completed order"),
        kpi("Chosen K", String(s.chosen_k), "elbow plus best silhouette"),
        kpi("PCA variance kept", pct(s.pca_total * 100), "two components"),
        kpi("Mean monetary", inr(s.rfm.monetary_mean), ("max " + (inr(s.rfm.monetary_max))))),
      h("div", { class: "grid grid-2" }, cards),
      h("div", { class: "grid grid-2" },
        card("K selection", sub("Standardised R, F, M; n_init = 10, random_state = 42."),
          table([{ key: "k", label: "K", rowHeader: true, num: true }, { key: "inertia", label: "Inertia", num: true, fmt: (v) => dec(v, 1) },
            { key: "silhouette", label: "Silhouette", num: true, fmt: (v) => h("span", {}, dec(v, 3), v === best ? " (best)" : "") },
            { key: "k", label: "Chosen", fmt: (v) => (v === s.chosen_k ? badge("chosen", "accent") : "") }],
          s.k_sweep, { label: "K sweep", rowClass: (r) => (r.k === s.chosen_k ? "highlight" : null) })),
        card("PCA on scaled RFM", sub("Share of variance explained by each component."),
          bars(s.pca_explained_variance_ratio.map((v, i) => ({ label: ("PC" + (i + 1)), value: v, text: dec(v, 3) })), "PCA explained variance"),
          h("p", { class: "small" }, ("Together: " + (dec(s.pca_total, 3)) + ".")))),
      card("Customer lookup", sub("Segment and RFM from customer_segments.csv; lapse probability from the saved model."), lookupForm()),
    ];
  }

  /* ---------------- 5 Lapse risk ---------------- */
  async function renderLapse() {
    const d = await getCached("/api/part-b");
    const l = d.lapse;
    const gs = l.grid_search;
    const lrC = gs.logistic_regression.best_params.C;
    const rfP = gs.random_forest.best_params;
    const models = [
      { id: "baseline", model: "Baseline (never lapsed)", ...l.baseline, cv: null },
      { id: "logistic_regression", model: ("Logistic regression (C = " + (lrC) + ")"), ...l.test.logistic_regression, cv: gs.logistic_regression.best_cv_f1 },
      { id: "random_forest", model: ("Random forest (depth " + (rfP.max_depth) + ", leaf " + (rfP.min_samples_leaf) + ")"), ...l.test.random_forest, cv: gs.random_forest.best_cv_f1 },
    ];
    const m3 = (v) => dec(v, 3);
    const o = l.oversampling;
    const coh = l.cohort;
    const coefs = l.lr_coefficients.slice().sort((a, b) => Math.abs(b.coef) - Math.abs(a.coef)).slice(0, 8);
    return [
      h("div", { class: "grid grid-kpi" },
        kpi("Lapse cohort", int(coh.customers), "completed order before the cutoff"),
        kpi("Lapsed", int(coh.lapsed), ("" + (pct(coh.lapsed_pct, 2)) + " of the cohort")),
        kpi("Train / test", ("" + (int(coh.train_rows)) + " / " + (int(coh.test_rows))), ("" + (int(coh.train_lapsed)) + " / " + (int(coh.test_lapsed)) + " lapsed")),
        kpi("Selected model", l.selected_model.replace("_", " "), ("test F1 " + (m3(l.test[l.selected_model].f1))))),
      card("Baseline versus tuned models", sub("Test set, lapsed = positive class. GridSearchCV (cv = 5, scoring = F1) on training rows only."),
        table([{ key: "model", label: "Model", rowHeader: true, cls: "wrap" }, { key: "accuracy", label: "Accuracy", num: true, fmt: m3 },
          { key: "precision", label: "Precision", num: true, fmt: m3 }, { key: "recall", label: "Recall", num: true, fmt: m3 },
          { key: "f1", label: "F1", num: true, fmt: m3 }, { key: "cv", label: "Best CV F1", num: true, fmt: (v) => (v === null ? "–" : m3(v)) },
          { key: "id", label: "", fmt: (v) => (v === l.selected_model ? badge("selected", "accent") : "") }],
        models, { label: "Model comparison", rowClass: (r) => (r.id === l.selected_model ? "highlight" : null) }),
        h("div", { class: "grid grid-3" }, models.map((m) => confusion(m.model, m.confusion_matrix)))),
      h("div", { class: "grid grid-2" },
        card("Oversampling the training set", sub(("Training rows only; lapsed rows drawn with replacement to " + (int(o.class_counts["1"])) + " per class. Test set unchanged.")),
          table([{ key: "name", label: "Logistic regression", rowHeader: true, cls: "wrap" }, { key: "classes", label: "Stayed / lapsed rows", num: true },
            { key: "precision", label: "Precision", num: true, fmt: m3 }, { key: "recall", label: "Recall", num: true, fmt: m3 }, { key: "f1", label: "F1", num: true, fmt: m3 }],
          [{ name: "Unbalanced training", classes: ("" + (int(coh.train_rows - coh.train_lapsed)) + " / " + (int(coh.train_lapsed))), ...o.original_lr },
            { name: "Oversampled", classes: ("" + (int(o.class_counts["0"])) + " / " + (int(o.class_counts["1"]))), ...o.balanced_lr }], { label: "Oversampling comparison" }),
          h("p", {}, ("Recall moves the most: " + (m3(o.original_lr.recall)) + " \u2192 " + (m3(o.balanced_lr.recall)) + ", while precision goes " + (m3(o.original_lr.precision)) + " \u2192 " + (m3(o.balanced_lr.precision)) + ".")),
          h("div", { class: "grid grid-2" }, confusion("Unbalanced", o.original_lr.confusion_matrix), confusion("Oversampled", o.balanced_lr.confusion_matrix))),
        card("What drives lapse", sub("Random-forest importances (top 5) and the largest logistic-regression coefficients on scaled features."),
          bars(l.rf_top_importances.map((f) => ({ label: f.feature, value: f.importance, text: dec(f.importance, 3) })), "Random forest feature importances"),
          h("h3", { class: "small muted", text: "Logistic-regression coefficients (orange = lowers lapse odds)" }),
          bars(coefs.map((c) => ({ label: c.feature, value: c.coef, negative: c.coef < 0, text: ("" + (c.coef > 0 ? "+" : "−") + (dec(Math.abs(c.coef), 2))) })), "Logistic regression coefficients"))),
      card("Premium retention list",
        h("div", { class: "callout", role: "note" }, h("strong", { text: "Post-hoc label. " }), d.retention_caveat),
        h("p", {}, ("" + (int(l.retention_list.truly_lapsed)) + " of these " + (int(l.retention_list.rows)) + " customers actually lapsed.")),
        table([{ key: "customer_id", label: "Customer", rowHeader: true }, { key: "lapse_probability", label: "Lapse probability", num: true, fmt: (v) => dec(v, 4) },
          { key: "actually_lapsed", label: "Actually lapsed", fmt: (v) => (v ? badge("yes", "danger") : badge("no", "neutral")) }],
        l.retention_list.table, { label: "Retention list", sortable: true }),
        h("p", { class: "small muted" }, ("Leakage controls: scaler mean of frequency " + (dec(l.scaler_check.scaler_mean_frequency, 4)) + " (training rows) vs " + (dec(l.scaler_check.cohort_mean_frequency, 4)) + " (whole cohort); reloaded model reproduces test predictions: " + (l.model_reload_identical ? "yes" : "no") + "."))),
    ];
  }

  /* ---------------- 6 Support triage ---------------- */
  const EXAMPLE_TICKETS = [
    "I was charged twice for ORD-100048. Please call me on 9876543210.",
    "Someone hacked my account and placed an order I never made. Email me at asha.k@example.com",
    "The app freezes at checkout every time I try to pay.",
  ];
  function triageTry() {
    const text = h("textarea", { id: "try-text", maxlength: "4000", "aria-describedby": "try-hint", required: true });
    const prompt = h("select", { id: "try-prompt" }, h("option", { value: "few_shot", text: "Few-shot (used for the final run)" }), h("option", { value: "zero_shot", text: "Zero-shot" }));
    const cust = h("input", { type: "text", id: "try-cust", maxlength: "5", autocomplete: "off", "aria-describedby": "try-cust-hint" });
    const btn = h("button", { class: "btn", type: "submit", text: "Triage ticket" });
    const chips = EXAMPLE_TICKETS.map((t) => h("button", { class: "chip", type: "button", text: t, onclick: () => { text.value = t; text.focus(); } }));
    const out = h("div", { "aria-live": "polite" });
    const form = h("form", { class: "stack", novalidate: true },
      h("div", { class: "field" }, h("label", { for: "try-text", text: "Ticket text" }), text,
        h("span", { class: "hint", id: "try-hint", text: "Emails, 10-digit mobile numbers and order ids are redacted before the model sees the text." })),
      h("div", { class: "row", role: "group", "aria-label": "Example tickets" }, chips),
      h("div", { class: "form-grid" },
        h("div", { class: "field" }, h("label", { for: "try-prompt", text: "Prompt" }), prompt),
        h("div", { class: "field" }, h("label", { for: "try-cust", text: "Customer id (optional)" }), cust,
          h("span", { class: "hint", id: "try-cust-hint", text: "A Premium customer routes to the premium desk." })),
        h("div", {}, btn)));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      out.replaceChildren(loadingState("Triaging…"));
      try {
        const r = await busy([btn, ...chips], "Triaging…", () => api("/api/triage/try", { method: "POST", body: { text: text.value, prompt: prompt.value, customer_id: cust.value } }));
        out.replaceChildren(triageSteps(r));
        announce(("Ticket triaged: " + (r.status) + ", routed to " + (r.route)));
      } catch (err) { out.replaceChildren(errorState(err)); announce("Triage failed"); }
    });
    return h("div", { class: "stack" }, form, out);
  }
  function triageSteps(r) {
    const guardText = { passed: "Passed: not empty and within the 400-token limit.", skipped_empty: "Empty ticket: never sent to the model.",
      flagged_long: "Too long for the model: never sent, goes to human review." };
    const step = (title, ...body) => h("li", {}, h("div", { class: "step-body" }, h("div", { class: "step-title" }, title), body));
    const c = r.redaction_counts;
    return h("ol", { class: "steps", "aria-label": "Triage steps" },
      step(h("span", { text: ("Original ticket (about " + (int(r.estimated_tokens)) + " tokens)") }), h("pre", { text: r.original || "(empty)" })),
      step(h("span", {}, "Guardrail ", badge(r.guardrail)), h("p", { class: "small", text: guardText[r.guardrail] || r.guardrail })),
      step(h("span", {}, "Redaction ", badge(("" + (r.pii_left) + " PII left"), r.pii_left ? "danger" : "success")),
        h("p", { class: "small", text: ("" + (c.email) + " email, " + (c.phone) + " phone, " + (c.order_id) + " order id replaced.") }), h("pre", { text: r.redacted || "(empty)" })),
      step(h("span", {}, "Model call ", r.sent_to_model ? badge(r.prompt.replace("_", "-"), "info") : badge("not sent", "neutral")),
        r.sent_to_model ? [h("pre", { text: r.reply }), h("p", { class: "small muted", text: ("" + (int(r.tokens_used)) + " tokens; " + (r.retries.length ? ("" + (r.retries.length) + " retry after a transient error") : "no retries") + ".") })]
          : h("p", { class: "small", text: "The guardrail stopped this ticket before any model call." })),
      step(h("span", {}, "Validation ", badge(r.status)), h("p", { class: "small", text: r.category ? ("Category: " + (r.category)) : "No category accepted: a human reviews this ticket." })),
      step(h("span", {}, "Route ", badge(r.route), " ", badge(r.priority)),
        h("p", { class: "small", text: r.segment ? ("Customer " + (r.customer_id) + ": " + (r.segment.segment_name) + (r.segment.is_premium ? " (Premium)" : "") + ".") : r.customer_id ? ("Customer " + (r.customer_id) + " has no segment, so is treated as not Premium.") : "No customer id given, so treated as not Premium." })));
  }
  async function renderTriage() {
    const d = await getCached("/api/part-c");
    const z = d.zero_shot; const f = d.few_shot; const p = d.prompts;
    const cmp = [
      { prompt: "Zero-shot", ptok: p.zero_shot_tokens, ...z },
      { prompt: "Few-shot", ptok: p.few_shot_tokens, ...f },
    ];
    const statusRows = Object.entries(d.final.status_counts).map(([s, n]) => ({ status: s, n }));
    const cats = ["billing", "delivery", "technical", "fraud"];
    const routes = Object.entries(d.final.route_counts).sort((a, b) => b[1] - a[1]);
    const routePriority = {};
    d.triage_rows.forEach((r) => { routePriority[r.route] = r.priority; });

    const all = d.triage_rows;
    const uniq = (k) => [...new Set(all.map((r) => r[k]).filter(Boolean))].sort();
    const mkSel = (id, label, k) => {
      const sel = h("select", { id }, h("option", { value: "", text: "All" }), uniq(k).map((v) => h("option", { value: v, text: v })));
      return [sel, h("div", { class: "field" }, h("label", { for: id, text: label }), sel)];
    };
    const search = h("input", { type: "search", id: "tk-search", placeholder: "T0024 or C0486", autocomplete: "off" });
    const [stSel, stField] = mkSel("tk-status", "Status", "status");
    const [rtSel, rtField] = mkSel("tk-route", "Route", "route");
    const [ctSel, ctField] = mkSel("tk-cat", "Category", "category");
    const tkTable = table([
      { key: "ticket_id", label: "Ticket", rowHeader: true }, { key: "customer_id", label: "Customer" },
      { key: "status", label: "Status", fmt: (v) => badge(v) }, { key: "category", label: "Category" },
      { key: "segment_name", label: "Segment" }, { key: "priority", label: "Priority", fmt: (v) => badge(v) },
      { key: "route", label: "Route", fmt: (v) => badge(v) }, { key: "tokens_used", label: "Tokens", num: true },
    ], all, { label: "Triage results", sortable: true, tall: true, emptyText: "No tickets match these filters." });
    const tkCount = h("p", { class: "small muted", role: "status" });
    const applyFilters = () => {
      const q = search.value.trim().toUpperCase();
      const rows = all.filter((r) => (!q || r.ticket_id.includes(q) || r.customer_id.includes(q)) && (!stSel.value || r.status === stSel.value)
        && (!rtSel.value || r.route === rtSel.value) && (!ctSel.value || r.category === ctSel.value));
      tkTable.setRows(rows);
      tkCount.textContent = ("Showing " + (rows.length) + " of " + (all.length) + " tickets.");
    };
    [search, stSel, rtSel, ctSel].forEach((el) => el.addEventListener("input", applyFilters));
    applyFilters();

    return [
      h("div", { class: "grid grid-kpi" },
        kpi("Tickets", int(d.tickets), ("" + (int(d.guardrails.eligible)) + " eligible for the model")),
        kpi("Guardrail stops", int(d.guardrails.empty + d.guardrails.long), ("" + (d.guardrails.empty) + " empty, " + (d.guardrails.long) + " too long")),
        kpi("PII redacted", int(d.redaction.total), ("" + (d.redaction.email) + " emails, " + (d.redaction.phone) + " phones, " + (d.redaction.order_id) + " order ids")),
        kpi("Transient errors", int(d.retries.count), ("all recovered on retry " + (d.retries.retry_numbers.join(", "))))),
      card("Try a ticket", sub("Runs the real Part C guardrail, redaction, retry, validation and routing code against mock_llm. Nothing is written to disk."), triageTry()),
      h("div", { class: "grid grid-2" },
        card("Zero-shot versus few-shot", sub("Full runs without a budget; accuracy over classified tickets."),
          table([{ key: "prompt", label: "Prompt", rowHeader: true }, { key: "ptok", label: "Prompt tokens", num: true }, { key: "classified", label: "Classified", num: true },
            { key: "correct", label: "Correct", num: true }, { key: "accuracy_pct", label: "Accuracy", num: true, fmt: (v) => pct(v) },
            { key: "total_tokens", label: "Total tokens", num: true }, { key: "tokens_per_classified", label: "Tokens / ticket", num: true, fmt: (v) => dec(v, 1) }],
          cmp, { label: "Prompt comparison" }),
          h("p", { class: "small" }, ("Few-shot costs " + (int(f.total_tokens - z.total_tokens)) + " more tokens per run (" + (dec(f.tokens_per_classified - z.tokens_per_classified, 1)) + " per classified ticket) and fixes " + (int(f.correct - z.correct)) + " errors."))),
        card("Zero-shot confusion", sub("Rows = true category, columns = predicted (classified tickets only)."),
          table([{ key: "true", label: "true \\ predicted", rowHeader: true }].concat(cats.map((c) => ({ key: c, label: c, num: true,
            cls: (r) => (r.true === c ? "cell-ok" : r[c] ? "cell-bad" : ""),
            fmt: (v, r) => (r.true !== c && v ? h("strong", { text: int(v) }) : int(v)) }))), d.zero_shot_confusion, { label: "Zero-shot confusion table" }))),
      h("div", { class: "grid grid-2" },
        card("Final run: status counts", table([{ key: "status", label: "Status", fmt: (v) => badge(v) }, { key: "n", label: "Tickets", num: true }], statusRows, { label: "Status counts" })),
        card("Routing breakdown", sub("Few-shot run with TOKEN_BUDGET 100,000; Premium from Part B segments."),
          bars(routes.map(([rt, n]) => ({ label: ("" + (rt) + " (" + (routePriority[rt] || "") + ")"), value: n, text: int(n) })), "Tickets per route"),
          h("p", { class: "small muted" }, ("Budget demo: zero-shot with TOKEN_BUDGET " + (int(d.budget_demo.token_budget)) + " used " + (int(d.budget_demo.total_tokens)) + " tokens; " + (int(d.budget_demo.budget_exhausted)) + " tickets ended budget_exhausted and went to human review.")))),
      card("All tickets", h("div", { class: "check-filters" },
        h("div", { class: "field" }, h("label", { for: "tk-search", text: "Ticket or customer id" }), search), stField, rtField, ctField), tkCount, tkTable),
    ];
  }

  /* ---------------- 7 Policy assistant ---------------- */
  function answerCard(r) {
    return h("div", { class: "card stack" },
      h("div", { class: "row" }, h("h3", { text: "Answer" }), r.grounded ? badge("grounded in retrieved text", "success") : badge("fallback: not found", "warning")),
      h("p", { class: "answer-text", text: r.answer }),
      h("div", { class: "row", "aria-label": "Sources" }, r.sources.map((s) => h("span", { class: "chip chip-static source-chip" }, s.source, h("span", { class: "muted", text: ("cosine " + (dec(s.score, 4))) })))),
      h("details", {}, h("summary", { text: "Show the retrieved chunks" }),
        h("ol", { class: "plain-list" }, r.sources.map((s) => h("li", {}, h("strong", { text: ("" + (s.source) + " (" + (dec(s.score, 4)) + ") ") }), s.text)))));
  }
  async function renderPolicy() {
    const d = await getCached("/api/part-d");
    const ev10 = d.evaluation.overlap_10; const ev0 = d.evaluation.overlap_0;
    const q = h("input", { type: "text", id: "policy-q", maxlength: "500", autocomplete: "off", required: true });
    const btn = h("button", { class: "btn", type: "submit", text: "Ask" });
    const out = h("div", { "aria-live": "polite" });
    const chips = d.example_questions.map((text) => h("button", { class: "chip", type: "button", text, onclick: () => { q.value = text; form.requestSubmit(); } }));
    const form = h("form", { class: "stack", novalidate: true },
      h("div", { class: "form-grid" }, h("div", { class: "field" }, h("label", { for: "policy-q", text: "Question about Instamart policy" }), q), h("div", {}, btn)),
      h("div", { class: "row", role: "group", "aria-label": "Example questions from policy_eval.csv" }, chips));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!q.value.trim()) { out.replaceChildren(errorState(new Error("Type a question first."))); q.focus(); return; }
      out.replaceChildren(loadingState("Retrieving and answering…"));
      try {
        const r = await busy([btn, ...chips], "Asking…", () => api("/api/policy/ask", { method: "POST", body: { question: q.value } }));
        out.replaceChildren(answerCard(r));
        announce(r.grounded ? "Answer ready" : "No answer found in the policies");
      } catch (err) { out.replaceChildren(errorState(err)); }
    });
    const fail0 = new Set(ev0.failures.map((f) => f.question));
    const byQ = Object.fromEntries(ev0.rows.map((r) => [r.question, r]));
    const evalRows = ev10.rows.map((r) => ({ ...r, o0: byQ[r.question] }));
    const tick = (ok) => (ok ? badge("yes", "success") : badge("no", "danger"));
    const score = (e) => (e.answerable ? ("" + (e.fact_in_answer) + "/" + (e.answerable)) : "");
    return [
      card("Ask the policy assistant", sub("Real TF-IDF retrieval (40-word chunks, overlap 10, top 3) and the mock POLICY ASSISTANT."), form, out),
      h("div", { class: "grid grid-2" },
        card("Chunks per policy (overlap 10)", table([{ key: "s", label: "Source", rowHeader: true }, { key: "n", label: "Chunks", num: true }],
          Object.entries(d.chunks.per_source).map(([s, n]) => ({ s, n })).concat([{ s: "Total", n: d.chunks.total, _t: true }]), { label: "Chunks per source", rowClass: (r) => (r._t ? "total-row" : null) }),
          h("p", { class: "small muted" }, ("Query \"" + (d.retrieval_example.query) + "\" retrieves: " + (d.retrieval_example.top3.map((t) => ("" + (t.source) + " " + (dec(t.score, 4)))).join(", ")) + "."))),
        card("Evaluation: overlap 10 versus 0", table([{ key: "m", label: "Metric", rowHeader: true, cls: "wrap" }, { key: "a", label: "Overlap 10", num: true }, { key: "b", label: "Overlap 0", num: true }], [
          { m: "Chunks", a: ev10.chunks, b: ev0.chunks },
          { m: "Expected document in top 3", a: ("" + (ev10.doc_in_top3) + "/" + (ev10.answerable)), b: ("" + (ev0.doc_in_top3) + "/" + (ev0.answerable)) },
          { m: "Expected fact in answer", a: score(ev10), b: score(ev0) },
          { m: "Fallback on unanswerable", a: ("" + (ev10.fallback_on_unanswerable) + "/" + (ev10.unanswerable)), b: ("" + (ev0.fallback_on_unanswerable) + "/" + (ev0.unanswerable)) },
        ], { label: "Evaluation summary" }), h("p", { class: "small muted", text: "Without overlap, sentences are cut at chunk boundaries and the needed fact lands in a chunk that is not retrieved." }))),
      card("Evaluation questions", sub("Rows that fail with overlap 0 are highlighted."),
        table([{ key: "question", label: "Question", rowHeader: true, cls: "wrap" }, { key: "expected_doc", label: "Expected doc" },
          { key: "expected_fact", label: "Expected fact", cls: "wrap" },
          { key: "fact_in_answer", label: "Overlap 10", fmt: (v, r) => (r.answerable ? tick(r.doc_in_top3 && v) : tick(r.fallback)) },
          { key: "o0", label: "Overlap 0", fmt: (v, r) => (r.answerable ? tick(v.doc_in_top3 && v.fact_in_answer) : tick(v.fallback)) },
          { key: "o0", label: "Overlap 0 answer", cls: "wrap small", fmt: (v) => v.answer }],
        evalRows, { label: "Evaluation questions", rowClass: (r) => (fail0.has(r.question) ? "row-fail" : null) })),
    ];
  }

  /* ---------------- 8 Refund agent ---------------- */
  function compactObservation(obs) {
    if (obs && Array.isArray(obs.results)) {
      return { results: obs.results.map((r) => ({ source: r.source, score: r.score, text: r.text.length > 90 ? ("" + (r.text.slice(0, 90)) + "\u2026") : r.text })) };
    }
    return obs;
  }
  /** Vertical timeline: model call -> tool -> observation ... -> final answer or stop. */
  function timeline(r, { crashAfter = null } = {}) {
    const list = h("ol", { class: "timeline", "aria-label": "Agent steps" });
    r.steps.forEach((s, i) => {
      if (crashAfter !== null && i === crashAfter) {
        list.append(h("li", { class: "t-crash" }, h("div", { class: "t-kind", text: "Simulated crash, then resume_agent" }),
          h("p", { class: "small", text: ("Checkpoint held " + (crashAfter) + " executed tools; the resumed run continues without repeating them.") })));
      }
      list.append(h("li", { class: "t-model" }, h("div", { class: "t-kind", text: ("Model call " + (i + 1)) }),
        h("p", {}, "Requests tool ", h("code", { text: s.tool })), h("pre", { class: "obs", text: JSON.stringify(s.arguments) })));
      const o = s.observation || {};
      list.append(h("li", { class: "t-obs" }, h("div", { class: "t-kind", text: "Tool observation" }),
        h("div", { class: "row" }, h("code", { text: s.tool }), o.error ? badge("error", "danger") : null,
          o.duplicate_prevented ? badge("duplicate prevented", "warning") : null, isNum(o.refund_inr) ? badge(inr(o.refund_inr), "info") : null),
        h("pre", { class: "obs", text: JSON.stringify(compactObservation(o), null, 2) })));
    });
    const fallback = String(r.status).startsWith("FALLBACK");
    if (fallback) {
      const skipped = r.llm_calls > r.steps.length;
      list.append(h("li", { class: "t-stop" }, h("div", { class: "t-kind", text: "Stopped safely" }), h("div", { class: "row" }, badge(r.status)),
        skipped && r.status === "FALLBACK_TOKEN_LIMIT" ? h("p", { class: "small", text: ("Model call " + (r.llm_calls) + " pushed the total over the limit, so its requested tool was not run.") }) : null,
        h("p", { class: "small", text: r.final_answer })));
    } else {
      list.append(h("li", { class: "t-final" }, h("div", { class: "t-kind", text: ("Model call " + (r.llm_calls) + ": final answer") }),
        h("div", { class: "row" }, badge(r.status)), h("p", { text: r.final_answer })));
    }
    return list;
  }
  const counters = (r) => h("div", { class: "counters", "aria-label": "Run counters" },
    h("span", { class: "counter" }, "Status ", badge(r.status)),
    h("span", { class: "counter" }, "Model calls ", h("b", { text: int(r.llm_calls) })),
    h("span", { class: "counter" }, "Tokens ", h("b", { text: int(r.tokens_used) })),
    h("span", { class: "counter" }, "Tools run ", h("b", { text: int(r.steps.length) })),
    h("span", { class: "counter" }, "Refund ", h("b", { text: inr(r.refund_inr) })));

  function agentRunner(out) {
    const cust = h("input", { type: "text", id: "ag-cust", maxlength: "5", autocomplete: "off" });
    const msg = h("textarea", { id: "ag-msg", maxlength: "2000", required: true });
    const iters = h("input", { type: "number", id: "ag-iter", min: "1", max: "12", value: "6", inputmode: "numeric" });
    const tokens = h("input", { type: "number", id: "ag-tok", min: "50", max: "20000", value: "6000", step: "50", inputmode: "numeric" });
    const runBtn = h("button", { class: "btn", type: "submit", text: "Run agent" });
    const resetBtn = h("button", { class: "btn btn-secondary", type: "button", text: "Reset demo ledger" });
    const form = h("form", { class: "stack", novalidate: true },
      h("div", { class: "field" }, h("label", { for: "ag-msg", text: "Customer message" }), msg),
      h("div", { class: "form-grid" },
        h("div", { class: "field" }, h("label", { for: "ag-cust", text: "Customer id (optional)" }), cust),
        h("div", { class: "field" }, h("label", { for: "ag-iter", text: "Max iterations (1–12)" }), iters),
        h("div", { class: "field" }, h("label", { for: "ag-tok", text: "Token limit (50–20,000)" }), tokens)),
      h("div", { class: "row" }, runBtn, resetBtn),
      h("p", { class: "small muted", text: "Live runs use the real agent and tools, but write only to state/demo/refund_ledger.jsonl; the graded ledger and run log are never touched. Running the same order twice shows the duplicate guard." }));
    const run = async (body, label) => {
      out.replaceChildren(loadingState(("Running " + (label) + "\u2026")));
      try {
        const r = await busy([runBtn, resetBtn, ...document.querySelectorAll("[data-run]")], "Running…", () => api("/api/agent/run", { method: "POST", body }));
        out.replaceChildren(h("div", { class: "stack" }, h("h3", { text: ("Live run: " + (label)) }), counters(r), timeline(r),
          r.demo_ledger.length ? table([{ key: "tool", label: "Tool" }, { key: "order_id", label: "Order" }, { key: "refund_inr", label: "Refund", num: true }, { key: "run_id", label: "Run" }],
            r.demo_ledger, { caption: "Demo ledger (state/demo/refund_ledger.jsonl)", label: "Demo ledger" }) : h("p", { class: "small muted", text: "Demo ledger is empty." })));
        announce(("Agent finished with " + (r.status)));
      } catch (err) { out.replaceChildren(errorState(err)); announce("Agent run failed"); }
    };
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const it = Number(iters.value); const tk = Number(tokens.value);
      if (!msg.value.trim()) { out.replaceChildren(errorState(new Error("Type a customer message first."))); msg.focus(); return; }
      if (!Number.isInteger(it) || it < 1 || it > 12 || !Number.isInteger(tk) || tk < 50 || tk > 20000) {
        out.replaceChildren(errorState(new Error("Max iterations must be 1–12 and the token limit 50–20,000."))); return;
      }
      run({ message: msg.value, customer_id: cust.value, max_iterations: it, token_limit: tk }, "custom message");
    });
    resetBtn.addEventListener("click", async () => {
      try { await busy([resetBtn, runBtn], "Resetting…", () => api("/api/agent/reset", { method: "POST", body: {} }));
        out.replaceChildren(h("p", { class: "callout callout-info", text: "Demo ledger cleared. The next refund will be issued afresh." })); announce("Demo ledger cleared");
      } catch (err) { out.replaceChildren(errorState(err)); }
    });
    return { form, run, fill: (s) => { msg.value = s.message; cust.value = s.customer_id || ""; iters.value = "6"; tokens.value = "6000"; } };
  }

  async function renderAgent() {
    const d = await getCached("/api/part-d");
    const scen = d.scenarios;
    const out = h("div", { "aria-live": "polite" });
    const runner = agentRunner(out);
    const showRecorded = (label, r, opts) => {
      out.replaceChildren(h("div", { class: "stack" }, h("h3", { text: ("Recorded run: " + (label)) }),
        h("p", { class: "small muted", text: "From outputs/agent_runs.jsonl (the graded run)." }), counters(r), timeline(r, opts)));
      out.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    const scTable = table([
      { key: "scenario_id", label: "Scenario", rowHeader: true }, { key: "message", label: "Message", cls: "wrap" },
      { key: "expected_outcome", label: "Expected" }, { key: "status", label: "Status", fmt: (v) => badge(v) },
      { key: "refund_inr", label: "Refund", num: true, fmt: (v) => inr(v) }, { key: "llm_calls", label: "Calls", num: true },
      { key: "tokens_used", label: "Tokens", num: true }, { key: "tools_executed", label: "Tools executed", cls: "small", fmt: (v) => v.join(", ") },
      { key: "scenario_id", label: "Actions", fmt: (id, r) => h("div", { class: "row" },
        h("button", { class: "btn btn-small", type: "button", "data-run": "", "aria-label": ("Run scenario " + (id) + " live"), text: "Run live",
          onclick: () => { runner.fill(r); runner.run({ message: r.message, customer_id: r.customer_id || "" }, ("scenario " + (id))); out.scrollIntoView({ behavior: "smooth", block: "start" }); } }),
        h("button", { class: "btn btn-secondary btn-small", type: "button", "aria-label": ("Show recorded trace for " + (id)), text: "Trace", onclick: () => showRecorded(("scenario " + (id)), r) })) },
    ], scen, { label: "Agent scenarios" });
    const demos = d.demos;
    const demoCard = (title, r, note) => h("div", { class: "card stack" }, h("h3", { text: title }), h("div", { class: "row" }, badge(r.status)),
      kv([["Model calls", int(r.llm_calls)], ["Tokens", int(r.tokens_used)], ["Tools run", r.tools_executed.length ? r.tools_executed.join(", ") : "none"]]),
      h("p", { class: "small muted", text: note }), h("details", {}, h("summary", { text: "Hand-off summary and steps" }), h("p", { class: "small", text: r.final_answer }), timeline(r)));
    const s7 = scen.find((s) => s.scenario_id === "S7");
    const cr = demos.crash_resume;
    return [
      card("Seven scenarios", sub("Default limits: 6 iterations, 6,000 tokens, 10 s. \"Run live\" re-runs a scenario in the demo sandbox; \"Trace\" shows the graded run."), scTable),
      card("Run the agent", runner.form, out),
      h("div", {}, h("h2", { text: "Stopping safely" }), h("div", { class: "grid grid-3" },
        s7 ? demoCard("S7: iteration limit", s7, "The [LOOP] message keeps requesting search_policy; all model calls fit under the token limit.") : null,
        demoCard("S1 with token_limit 200", demos.token_limit_200, "Stops after the call that crosses the limit, before running the tool it asked for."),
        demoCard("S1 with time_limit 0", demos.time_limit_0, "Checked at the top of each iteration, so it stops before the first model call."))),
      card("Crash and resume (S1)", sub("A simulated crash after the second tool; resume_agent continues from the checkpoint in state/."),
        h("div", { class: "grid grid-2" },
          kv([["Before the crash", ("" + (cr.tools_before_crash.join(", ")) + " (" + (cr.llm_calls_before_crash) + " model calls)")],
            ["After resume", ("" + (cr.tools_after_resume.join(", ")) + " (" + (cr.llm_calls_after_resume) + " model calls)")],
            ["Overall", cr.tools_executed.join(", ")], ["Final", h("span", {}, badge(cr.status), " ", inr(cr.refund_inr))]]),
          h("div", { class: "callout callout-info" }, h("strong", { text: "Idempotent ledger. " }), "S1 already refunded this order, so the resumed issue_refund returns duplicate_prevented and the ledger keeps one line per order.")),
        h("details", {}, h("summary", { text: "Show the full crash-and-resume trace" }), timeline(cr, { crashAfter: cr.tools_before_crash.length })),
        table([{ key: "tool", label: "Tool" }, { key: "order_id", label: "Order" }, { key: "refund_inr", label: "Refund", num: true }, { key: "run_id", label: "Run" }],
          d.ledger_lines, { caption: "Graded ledger (outputs/refund_ledger.jsonl, timestamps omitted)", label: "Graded ledger" })),
    ];
  }

  /* ---------------- router and shell ---------------- */
  const RENDER = { overview: renderOverview, data: renderData, sql: renderSql, segments: renderSegments, lapse: renderLapse,
    triage: renderTriage, policy: renderPolicy, agent: renderAgent };

  async function loadView(name) {
    const body = document.querySelector(("#view-" + (name) + " [data-body]"));
    body.setAttribute("aria-busy", "true");
    body.replaceChildren(loadingState(("Loading " + (TITLES[name]) + "\u2026")), h("div", { class: "skeleton", "aria-hidden": "true" }));
    announce(("Loading " + (TITLES[name])));
    try {
      const nodes = await RENDER[name]();
      body.replaceChildren(...nodes.filter(Boolean));
      rendered[name] = true;
      announce(("" + (TITLES[name]) + " loaded"));
    } catch (err) {
      body.replaceChildren(errorState(err, () => loadView(name)));
      announce(("" + (TITLES[name]) + " failed to load"));
    } finally {
      body.removeAttribute("aria-busy");
    }
  }

  const currentView = () => { const v = location.hash.slice(1); return VIEWS.includes(v) ? v : "overview"; };
  function route(focus) {
    const v = currentView();
    VIEWS.forEach((n) => { document.getElementById(("view-" + (n))).hidden = n !== v; });
    document.querySelectorAll("[data-nav]").forEach((a) => {
      if (a.dataset.nav === v) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    document.title = ("" + (TITLES[v]) + " \u00b7 Instamart Copilot");
    setMenu(false);
    if (RENDER[v] && !rendered[v]) loadView(v);
    if (focus) { window.scrollTo(0, 0); document.getElementById(("h-" + (v))).focus(); }
  }

  const menuBtn = document.getElementById("menu-toggle");
  const sidebar = document.getElementById("sidebar");
  function setMenu(open) {
    sidebar.classList.toggle("open", open);
    menuBtn.setAttribute("aria-expanded", open ? "true" : "false");
  }
  menuBtn.addEventListener("click", () => setMenu(!sidebar.classList.contains("open")));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebar.classList.contains("open")) { setMenu(false); menuBtn.focus(); }
  });

  const themeBtn = document.getElementById("theme-toggle");
  const dark = window.matchMedia("(prefers-color-scheme: dark)");
  const effectiveTheme = () => document.documentElement.dataset.theme || (dark.matches ? "dark" : "light");
  function applyTheme(theme) {
    if (theme) document.documentElement.dataset.theme = theme; else delete document.documentElement.dataset.theme;
    themeBtn.setAttribute("aria-pressed", effectiveTheme() === "dark" ? "true" : "false");
  }
  let saved = null;
  try { saved = window.localStorage.getItem("instamart-theme"); } catch (_) { saved = null; }
  applyTheme(saved === "light" || saved === "dark" ? saved : null);
  dark.addEventListener("change", () => applyTheme(document.documentElement.dataset.theme || null));
  themeBtn.addEventListener("click", () => {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    try { window.localStorage.setItem("instamart-theme", next); } catch (_) { /* storage unavailable: theme lasts this visit */ }
  });

  async function loadBadge() {
    const el = document.getElementById("checkpoint-badge");
    try {
      const d = await getCached("/api/overview");
      const c = d.checkpoints;
      el.textContent = ("Checkpoints: " + (c.passed) + "/" + (c.total) + " passed");
      el.className = ("badge badge-" + (c.all_passed ? "success" : "danger"));
    } catch (_) {
      el.textContent = "Checkpoints: unavailable";
      el.className = "badge badge-danger";
    }
  }

  window.addEventListener("hashchange", () => route(true));
  route(false);
  loadBadge();
})();
