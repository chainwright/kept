/* Kept dashboard. Vanilla JS, no build step.
   Every piece of data goes into the DOM through textContent / attributes, never innerHTML.
   Colours live in CSS custom properties only; SVG parts get classes, never colour values. */
(() => {
  "use strict";

  // ------------------------------------------------------------------ helpers
  const $ = (sel, root = document) => root.querySelector(sel);

  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    if (props) {
      for (const [k, v] of Object.entries(props)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "text") el.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else if (k === "hidden") el.hidden = !!v;
        else if (k === "disabled") el.disabled = !!v;
        else el.setAttribute(k, v === true ? "" : String(v));
      }
    }
    append(el, kids);
    return el;
  }
  function append(el, kids) {
    for (const k of kids.flat(Infinity)) {
      if (k === null || k === undefined || k === false) continue;
      el.append(k instanceof Node ? k : document.createTextNode(String(k)));
    }
    return el;
  }
  function fill(el, ...kids) { el.replaceChildren(); return append(el, kids); }

  const NS = "http://www.w3.org/2000/svg";
  function s(tag, attrs, ...kids) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, String(v));
    for (const k of kids.flat()) if (k !== null && k !== undefined) el.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return el;
  }

  const ICONS = {
    check: ["M5 12.5l4.5 4.5L19 7.5"],
    shield: ["M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z", "M9.5 12h5"],
    mail: ["M3 6h18v12H3z", "M3 7l9 6 9-6"],
    link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
    chev: ["M6 9l6 6 6-6"],
    copy: ["M9 9h11v11H9z", "M5 15H4V4h11v1"],
  };
  function icon(name, cls = "ico ico-sm") {
    const svg = s("svg", { viewBox: "0 0 24 24", class: cls, "aria-hidden": "true" });
    for (const d of ICONS[name] || []) svg.append(s("path", { d }));
    return svg;
  }

  const chip = (text, cls = "", title) => h("span", { class: `chip ${cls}`.trim(), title }, text);

  function localISO(d = new Date()) {
    const z = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
  }
  function isoToDate(iso) {
    const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
    return y && m && d ? new Date(y, m - 1, d) : null;
  }
  function dayDiff(iso) {
    const a = isoToDate(iso);
    if (!a) return null;
    const t = new Date(); t.setHours(0, 0, 0, 0);
    return Math.round((a - t) / 86400000);
  }
  function fmtDay(iso, opts = { weekday: "short", month: "short", day: "numeric" }) {
    const d = isoToDate(iso);
    return d ? d.toLocaleDateString(undefined, opts) : String(iso || "");
  }
  const fmtShort = (iso) => fmtDay(iso, { month: "short", day: "numeric" });
  const fmtLong = (iso) => fmtDay(iso, { weekday: "long", month: "short", day: "numeric" });
  function parseTs(ts) { const d = new Date(ts); return isNaN(d) ? null : d; }
  function ago(ts) {
    const d = parseTs(ts);
    if (!d) return "";
    const sec = Math.round((Date.now() - d) / 1000);
    if (sec < 45) return "just now";
    if (sec < 3600) return `${Math.round(sec / 60)} min ago`;
    if (sec < 86400) return `${Math.round(sec / 3600)} h ago`;
    const days = Math.round(sec / 86400);
    return days === 1 ? "yesterday" : `${days} days ago`;
  }
  function clock(ts) {
    const d = parseTs(ts);
    return d ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "";
  }
  // model spend: small fractions of a dollar
  function money(usd) {
    const n = Number(usd) || 0;
    if (n === 0) return "$0.00";
    if (n < 0.0001) return "$" + n.toPrecision(2);
    if (n < 0.01) return "$" + n.toFixed(4);
    return "$" + n.toFixed(2);
  }
  // business money: whole dollars, real minus sign
  function usd(n) {
    const v = Number(n) || 0;
    const abs = Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: v % 1 ? 2 : 0, minimumFractionDigits: v % 1 ? 2 : 0 });
    return (v < 0 ? "−$" : "$") + abs;
  }
  const pct = (r) => `${Math.round((Number(r) || 0) * 100)}%`;
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;
  const personName = (from) => String(from || "").split("<")[0].trim().replace(/^"|"$/g, "") || String(from || "");
  const shortModel = (m) => String(m || "").split("/").pop();
  const safeUrl = (u) => { try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
  const tierName = (t) => ({ nano: "Nano", super: "Super", ultra: "Ultra" }[t] || t || "?");
  const slug = (c) => String(c || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const cap = (t) => { t = String(t || ""); return t.charAt(0).toUpperCase() + t.slice(1); };
  function mediaUrl(path) {
    const m = String(path || "").match(/^media\/([a-z0-9-]+)\/([A-Za-z0-9._-]+)$/);
    return m ? `/media/${m[1]}/${encodeURIComponent(m[2])}` : null;
  }
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  async function copyText(text, btn) {
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch {
      const ta = h("textarea", { class: "sr-only" }); ta.value = text; document.body.append(ta); ta.select();
      try { ok = document.execCommand("copy"); } catch { ok = false; }
      ta.remove();
    }
    if (btn) { const old = btn.textContent; btn.textContent = ok ? "Copied" : "Copy failed"; setTimeout(() => { btn.textContent = old; }, 1600); }
    announce(ok ? "Copied to the clipboard." : "Couldn't copy. Select the text and copy it by hand.");
  }
  const copyBtn = (text, label = "Copy") => {
    const b = h("button", { class: "btn btn-quiet btn-small copy-btn", type: "button" }, label);
    b.addEventListener("click", () => copyText(text, b));
    return b;
  };

  // ------------------------------------------------------------------ API
  class ApiError extends Error { constructor(msg, status) { super(msg); this.status = status; } }
  async function request(method, path, opts = {}) {
    let res;
    try { res = await fetch(path, { method, ...opts }); } catch { throw new ApiError("Can't reach Kept's server. Is it running?", 0); }
    const type = res.headers.get("content-type") || "";
    let data = null, text = "";
    if (type.includes("json")) { try { data = await res.json(); } catch { /* empty */ } }
    else { try { text = await res.text(); } catch { /* empty */ } }
    if (!res.ok) {
      let msg = "";
      if (data && data.detail) msg = Array.isArray(data.detail) ? data.detail.map((d) => d.msg || String(d)).join("; ") : String(data.detail);
      else msg = (text || res.statusText || "").trim().slice(0, 300);
      throw new ApiError(msg || `HTTP ${res.status}`, res.status);
    }
    return data;
  }
  const api = (method, path, body) => request(method, path, body === undefined ? {} :
    { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

  // ------------------------------------------------------------------ feedback
  const toasts = $("#toasts");
  function toast(msg, kind = "info", ms = 7000) {
    const close = h("button", { type: "button", "aria-label": "Dismiss" }, "×");
    const el = h("div", { class: `toast ${kind === "err" ? "err" : kind === "good" ? "good" : ""}`, role: kind === "err" ? "alert" : "status" },
      h("p", null, msg), close);
    const kill = () => el.remove();
    close.addEventListener("click", kill);
    toasts.append(el);
    if (ms) setTimeout(kill, kind === "err" ? Math.max(ms, 12000) : ms);
    while (toasts.children.length > 4) toasts.firstChild.remove();
  }
  const announcer = $("#announcer");
  function announce(msg) { announcer.textContent = ""; setTimeout(() => { announcer.textContent = msg; }, 50); }

  // ------------------------------------------------------------------ collapsible cards
  function initFolds() {
    for (const card of document.querySelectorAll("section.card[data-fold]")) {
      const head = card.querySelector(".card-head h2");
      const body = card.querySelector(".card-body");
      if (!head || !body) continue;
      body.id = body.id || `${card.id}-body`;
      const btn = h("button", { class: "fold-btn", type: "button", "aria-controls": body.id });
      btn.append(icon("chev", "ico chev"), ...head.childNodes);
      head.append(btn);
      const saved = store.get(`kept.fold.${card.id}`);
      setFold(card, saved === null ? !card.hasAttribute("data-folded") : saved === "open", false);
      btn.addEventListener("click", () => setFold(card, btn.getAttribute("aria-expanded") !== "true", true));
    }
    // a jump link to a folded card opens it
    document.addEventListener("click", (e) => {
      const a = e.target.closest && e.target.closest('a[href^="#"]');
      if (!a) return;
      const t = document.getElementById(a.getAttribute("href").slice(1));
      const card = t && t.closest("section.card[data-fold]");
      if (card && card.classList.contains("is-folded")) setFold(card, true, true);
    });
  }
  function setFold(card, open, remember) {
    const btn = card.querySelector(".fold-btn");
    const body = card.querySelector(".card-body");
    if (!btn || !body) return;
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    body.hidden = !open;
    card.classList.toggle("is-folded", !open);
    if (remember) store.set(`kept.fold.${card.id}`, open ? "open" : "closed");
    if (open && card.id === "money" && S) { delete sigs.money; render(S); }
  }

  // ------------------------------------------------------------------ state
  let S = null;
  const sigs = {};
  let localJob = null;
  let refreshing = false;
  let offline = false;
  let lastPending = null;
  let ledgerDir = "i_owe";
  let showAllApprovals = false;

  function changed(key, value) {
    const v = JSON.stringify(value);
    if (sigs[key] === v) return false;
    sigs[key] = v;
    return true;
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;
    try {
      const st = await api("GET", "/api/state");
      if (offline) { offline = false; toast("Connected to Kept again.", "good", 4000); }
      S = st;
      render(st);
    } catch (e) {
      if (!offline) { offline = true; toast(`Can't load Kept's state: ${e.message}. Retrying every 5 seconds.`, "err", 0); }
    } finally {
      refreshing = false;
    }
  }

  // ------------------------------------------------------------------ render
  const openIndex = () => Object.fromEntries((S?.open || []).map((r) => [r.id, r]));
  const inboxIndex = () => Object.fromEntries((S?.inbox || []).map((m) => [m.id, m]));
  const todayUTC = () => new Date().toISOString().slice(0, 10);
  const dirOf = (r) => (r.direction === "owed_to_me" ? "owed_to_me" : "i_owe");

  function render(st) {
    const safe = (name, fn) => { try { fn(); } catch (e) { console.error(`render ${name}`, e); } };
    safe("top", () => renderTop(st));
    if (changed("principles", [st.open, st.pending.length, st.abstained.length, st.calls.map((c) => c.ts), st.calibration?.overall, st.cash?.lowest, st.cash?.short])) safe("principles", () => renderPrinciples(st));
    if (changed("approvals", [st.pending, st.decided, st.open.map((r) => [r.id, r.text]), showAllApprovals])) safe("approvals", () => renderApprovals(st));
    if (changed("brief", [st.brief, st.open.map((r) => [r.id, r.due]), st.pending.map((a) => a.id), localISO()])) safe("brief", () => renderBrief(st));
    if (changed("money", [st.cash, st.invoices, st.habits, st.pending.map((a) => [a.id, a.args && a.args.invoice, a.args && a.args.step]), localISO(), $("#cash-chart").clientWidth])) safe("money", () => renderMoney(st));
    if (changed("rescue", [st.rescue, st.pending.map((a) => a.id)])) safe("rescue", () => renderRescue(st));
    if (changed("ledger", [st.open, st.closed, Object.keys(inboxIndex()), localISO(), ledgerDir])) safe("ledger", () => renderLedger(st));
    if (changed("scope", [st.scope, st.pending.map((a) => a.id)])) safe("scope", () => renderScope(st));
    if (changed("word", st.calibration)) safe("word", () => renderWord(st));
    if (changed("held", st.abstained)) safe("held", () => renderHeld(st));
    if (changed("inbox", [st.inbox, st.labels, st.open.map((r) => r.source)])) safe("inbox", () => renderInbox(st));
    if (changed("news", st.watch)) safe("news", () => renderNews(st));
    if (changed("growth", [st.offers_plan, st.growth, st.pending.map((a) => a.id)])) safe("growth", () => renderGrowth(st));
    if (changed("media", [st.media, st.invoices.map((i) => i.client)])) safe("media", () => renderMedia(st));
    if (changed("models", [st.tiers, st.routes, st.calls, st.spend_today, st.budget])) safe("models", () => renderModels(st));
    if (changed("activity", st.activity)) safe("activity", () => renderActivity(st));

    if (lastPending !== null && st.pending.length > lastPending) {
      announce(`${plural(st.pending.length - lastPending, "new item")} waiting for your Yes.`);
    }
    lastPending = st.pending.length;
  }

  function renderTop(st) {
    $("#owner-line").textContent = st.owner ? `Working for ${st.owner}.` : "";
    $("#demo-badge").hidden = !st.demo;
    $("#demo-reset").hidden = !st.demo;
    $("#reset-sep").hidden = !st.demo;
    const p = st.budget > 0 ? Math.min(100, (st.spend_today / st.budget) * 100) : 0;
    $("#spend-num").textContent = money(st.spend_today);
    $("#spend-of").textContent = `of ${money(st.budget)} budget`;
    const bar = $("#spend-bar");
    bar.setAttribute("aria-valuenow", String(Math.round(p)));
    bar.setAttribute("aria-valuetext", `${money(st.spend_today)} of ${money(st.budget)} daily budget`);
    bar.classList.toggle("warn", p >= 70 && p < 100);
    bar.classList.toggle("full", p >= 100);
    $("#spend-fill").style.width = `${Math.max(p, st.spend_today > 0 ? 2 : 0)}%`;
    setBusy(!!localJob || !!st.busy, st.busy && !localJob);
  }

  function renderPrinciples(st) {
    const mine = st.open.filter((r) => dirOf(r) === "i_owe");
    const over = mine.filter((r) => r.due && dayDiff(r.due) < 0).length;
    $("#p-open").textContent = st.open.length;
    const sub = $("#p-open-sub");
    sub.textContent = over ? `${over} overdue` : "until you close them with a note";
    sub.className = over ? "p-sub-over" : "";
    const pn = $("#p-pending");
    pn.textContent = st.pending.length;
    pn.classList.toggle("on", st.pending.length > 0);
    $("#p-held").textContent = st.abstained.length;
    const t = todayUTC();
    $("#p-calls").textContent = st.calls.filter((c) => String(c.ts).startsWith(t)).length;

    const ov = st.calibration && st.calibration.overall;
    $("#p-word").textContent = ov && ov.total ? pct(ov.rate) : "–";
    $("#p-word-sub").textContent = ov && ov.total ? `${ov.kept} of ${ov.total} on time` : "no closed promises yet";

    const c = st.cash;
    const num = $("#p-cash");
    if (c && c.lowest) {
      num.textContent = usd(Math.round(c.lowest.balance));
      num.classList.toggle("neg", c.lowest.balance < 0);
      $("#p-cash-label").textContent = c.short ? "short on cash" : "lowest balance, 30 days";
      const cs = $("#p-cash-sub");
      cs.textContent = c.short ? `on ${fmtShort(c.short.date)}` : `on ${fmtShort(c.lowest.date)}`;
      cs.className = c.short ? "p-sub-over" : "";
    } else {
      num.textContent = "–";
    }
  }

  // --- approvals
  const KIND = {
    send_email: { label: "Email", yes: "Yes, send it", hint: "Yes sends this email. No discards it.", sending: "Sending…" },
    publish_post: { label: "Post", yes: "Yes, publish", hint: "Yes publishes this post. No discards it.", sending: "Publishing…" },
    add_rule: { label: "New rule", yes: "Yes, add this rule", hint: "Yes adds the rule to Kept's skill file. No drops it.", sending: "Adding…" },
  };
  function renderApprovals(st) {
    const list = $("#approvals-list");
    const card = $("#approvals");
    card.classList.toggle("has-items", st.pending.length > 0);
    $("#approvals-count").textContent = st.pending.length ? plural(st.pending.length, "waiting", "waiting") : "";
    const ledger = openIndex();
    if (!st.pending.length) {
      fill(list, h("p", { class: "empty" },
        h("strong", null, "Nothing waiting. "),
        "When a promise comes due, an invoice runs late or a client is happy, Kept drafts the message, checks it, and puts it here for your Yes or No. Nothing is sent before you decide."));
    } else {
      const LIMIT = 3;
      const shown = showAllApprovals ? st.pending : st.pending.slice(0, LIMIT);
      const more = st.pending.length - shown.length;
      fill(list, shown.map((a) => approvalCard(a, ledger)),
        more > 0 ? h("button", { class: "btn btn-quiet more-btn", type: "button", onclick: () => { showAllApprovals = true; delete sigs.approvals; render(S); } },
          `Show ${plural(more, "more item")} waiting for your Yes`) : null);
    }

    const dw = $("#decided-wrap");
    dw.hidden = !st.decided.length;
    $("#decided-count").textContent = st.decided.length ? `(${st.decided.length})` : "";
    fill($("#decided-list"), st.decided.map((a) => {
      const done = a.kind === "publish_post" ? "Published" : a.kind === "add_rule" ? "Added" : "Sent";
      const map = { done: [done, "chip-ok"], approved: ["Approved", "chip-ok"], rejected: ["Declined", "chip-no"], failed: ["Failed", "chip-over"] };
      const [label, cls] = map[a.status] || [a.status, ""];
      return h("li", { class: "decided-row" },
        chip(label, cls),
        h("span", null, a.summary || a.kind),
        h("span", { class: "muted" }, ago(a.decided || a.created)),
        a.result ? h("span", { class: "res" }, String(a.result)) : null);
    }));
  }

  function approvalCard(a, ledger) {
    const args = a.args || {};
    const k = KIND[a.kind] || { label: a.kind, yes: "Yes", hint: "", sending: "Working…" };
    const row = a.ledger_id ? ledger[a.ledger_id] : null;
    const label = a.summary || "this action";
    const yes = h("button", { class: "btn btn-yes", type: "button", "aria-label": `${k.yes}: ${label}` }, icon("check", "ico"), k.yes);
    const no = h("button", { class: "btn btn-no", type: "button", "aria-label": `No: ${label}` }, "No");
    const status = h("span", { class: "hint", "aria-live": "polite" }, k.hint);
    const go = async (verdict) => {
      yes.disabled = no.disabled = true;
      status.textContent = verdict === "yes" ? k.sending : "Discarding…";
      try {
        const r = await api("POST", `/api/approvals/${encodeURIComponent(a.id)}/${verdict}`);
        if (verdict === "no") toast(row ? "Okay, not sent. The promise stays open in your ledger." : "Okay, discarded.", "good");
        else if (r && r.status === "failed") toast(`You said Yes, but it failed: ${r.result}`, "err");
        else toast(`Done. ${r && r.result ? r.result : ""}`.trim(), "good");
        announce(verdict === "yes" ? "Approved." : "Declined.");
      } catch (e) {
        toast(`Couldn't record your answer: ${e.message}`, "err");
        yes.disabled = no.disabled = false;
        status.textContent = k.hint;
      }
      refresh();
    };
    yes.addEventListener("click", () => go("yes"));
    no.addEventListener("click", () => go("no"));

    const tags = [chip(k.label, "chip-ask")];
    if (args.invoice) tags.push(chip(`Invoice #${args.invoice}`, "chip-outline"));
    if (args.step) tags.push(chip(`${cap(args.step)} reminder`, args.step === "final" ? "chip-over" : "chip-soon"));
    if (args.offer_client) tags.push(chip("Seasonal offer", "chip-super"));

    let content = null;
    if (a.kind === "publish_post") content = postPreview(args);
    else if (a.kind === "add_rule") content = h("div", { class: "rulecard" },
      h("div", { class: "kind-row" }, chip(`skill: ${args.skill || "?"}`, "chip-held")),
      h("p", { class: "rule" }, args.rule || ""),
      args.evidence ? h("p", { class: "ev" }, h("strong", null, "Evidence: "), args.evidence) : null);
    else if (a.kind === "send_email" || args.to) content = h("div", { class: "envelope" },
      h("dl", null,
        h("dt", null, "To"), h("dd", null, args.to || "?"),
        h("dt", null, "Subject"), h("dd", null, args.subject || "")),
      h("div", { class: "body", tabindex: "0", role: "region", "aria-label": `Draft: ${args.subject || label}` }, args.body || ""));

    return h("article", { class: `approval kind-${a.kind}`, "aria-label": `Waiting for your Yes: ${label}` },
      h("div", { class: "approval-head" },
        h("h3", { class: "approval-title" }, label),
        h("span", { class: "meta kind-row" }, tags, h("span", null, ago(a.created)))),
      content,
      h("p", { class: "why" }, h("strong", null, "Why: "), a.why || ""),
      a.reasoning ? h("details", { class: "reasoning" },
        h("summary", null, `How ${a.model_label || "the model"} weighed it`),
        h("div", { class: "body" }, a.reasoning)) : null,
      row ? h("p", { class: "why muted" }, "For the promise: ", h("a", { href: "#promises" }, row.text)) : null,
      a.checks && a.checks.length ? h("div", null,
        h("ul", { class: "checks", "aria-label": "Checks this passed" },
          a.checks.map((c) => h("li", null, icon("check"), c)))) : null,
      h("div", { class: "decide" }, yes, no, status));
  }

  function postPreview(args) {
    const imgs = (args.images || []).map((p, i) => {
      const u = mediaUrl(p);
      const which = /before/i.test(p) ? "Before" : /after/i.test(p) ? "After" : (i === 0 ? "Before" : "After");
      return u ? h("figure", null, h("img", { src: u, alt: `${which} picture`, loading: "lazy" }), h("figcaption", null, which)) : null;
    }).filter(Boolean);
    return h("div", { class: "post" },
      h("div", { class: "kind-row" }, chip(cap(args.platform || "post"), "chip-super"), h("span", { class: "muted" }, "Preview")),
      h("p", { class: "post-text" }, args.text || ""),
      imgs.length ? h("div", { class: "pics" }, imgs) : null);
  }

  // --- before you send
  const EXAMPLE = { to: "Maria Lopez", text: "Hi Maria,\n\nThanks for the call! I'll send the revised quote with the online ordering page by Friday, and the menu will show both sizes by tomorrow.\n\nAlex" };
  $("#pre-example").addEventListener("click", () => {
    $("#pre-text").value = EXAMPLE.text;
    $("#pre-to").value = EXAMPLE.to;
    $("#pre-text").focus();
  });
  $("#pre-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = $("#pre-text").value.trim();
    if (!text) { $("#pre-text").focus(); return; }
    const out = $("#pre-out");
    const btn = $("#pre-btn");
    btn.disabled = true;
    fill(out, h("p", { class: "loading" }, h("span", { class: "spinner", "aria-hidden": "true" }),
      "Nemotron Nano is finding the promises; code then checks each date against your record…"));
    try {
      const r = await api("POST", "/api/precheck", { text, to: $("#pre-to").value.trim() });
      fill(out, precheckResult(text, r || {}));
      announce(`${plural((r && r.promises || []).length, "promise")} found.`);
    } catch (e) {
      fill(out, h("div", { class: "answer notok" }, chip("Not checked", "chip-held"),
        h("p", null, `Kept couldn't check this draft: ${e.message}`),
        e.status >= 500 ? h("p", { class: "foot" }, "Model calls need a working Nebius Token Factory key. Nothing was guessed.") : null));
    } finally {
      btn.disabled = false;
      refresh();
    }
  });

  function precheckResult(original, r) {
    const ps = r.promises || [];
    if (!ps.length) {
      return h("div", { class: "pre-result" }, h("p", { class: "empty" }, r.note || "No promises found in this draft. Nothing to warn you about."));
    }
    const cards = ps.map((p) => {
      const a = p.advice;
      return h("article", { class: `promise-card ${a || (p.same_day && p.same_day.length) ? "is-risky" : ""}` },
        h("div", { class: "pc-top" },
          h("span", { class: "pc-text" }, p.text),
          p.due ? chip(`Due ${fmtDay(p.due)}`, a ? "chip-soon" : "chip-due") : chip("No date named", "chip-outline")),
        p.quote ? h("p", { class: "pc-quote" }, `“${p.quote}”`) : null,
        p.model_due ? h("p", { class: "note note-fix" },
          `The model said ${fmtLong(p.model_due)}; the calendar says ${fmtLong(p.due)}. Code re-read “${p.when_words}” and the words win.`) : null,
        a ? h("p", { class: "note note-advice" }, `${a.why} `, h("strong", null, `Suggest ${fmtLong(a.suggested)}.`)) : null,
        p.same_day && p.same_day.length ? h("p", { class: "note note-load" },
          `Already due that day: ${p.same_day.join("; ")}.`) : null);
    });
    let rw = null;
    if (r.rewrite) {
      if (r.rewrite.ok && r.rewrite.text) {
        rw = h("div", { class: "rewrite" },
          h("div", { class: "rewrite-head" }, h("span", null, "A version you'll keep"), copyBtn(r.rewrite.text, "Copy rewrite")),
          h("p", { class: "rewrite-text" }, wordDiff(original, r.rewrite.text)),
          h("p", { class: "sr-only" }, "Removed words are struck through; added words are highlighted."));
      } else {
        rw = h("div", { class: "answer notok" }, chip("Rewrite held back", "chip-held"),
          h("p", null, "Kept wrote a new version but it didn't pass the checks, so it isn't shown:"),
          h("ul", { class: "problems" }, (r.rewrite.problems || []).map((x) => h("li", null, plainProblem(x)))));
      }
    }
    return h("div", { class: "pre-result" }, cards, rw,
      r.model ? h("p", { class: "foot muted" }, `Promises found by ${shortModel(r.model)}; dates and your record checked by code.`) : null);
  }

  // word-level diff (LCS); fine for drafts of a few hundred words
  function wordDiff(a, b) {
    const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
    if (A.length * B.length > 600000) return b;
    const n = A.length, m = B.length;
    const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
      L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    const out = [];
    let i = 0, j = 0, del = [], add = [];
    const flush = () => {
      if (del.join("").trim()) out.push(h("del", { class: "d-del" }, del.join("")), " ");
      if (add.join("").trim()) out.push(h("ins", { class: "d-add" }, add.join("")));
      else if (add.length) out.push(add.join(""));
      del = []; add = [];
    };
    while (i < n && j < m) {
      if (A[i] === B[j]) { flush(); out.push(A[i]); i++; j++; }
      else if (L[i + 1][j] >= L[i][j + 1]) del.push(A[i++]);
      else add.push(B[j++]);
    }
    while (i < n) del.push(A[i++]);
    while (j < m) add.push(B[j++]);
    flush();
    return out;
  }

  // --- brief
  function renderBrief(st) {
    const out = $("#brief");
    const b = st.brief;
    const meta = $("#brief-meta");
    if (!b) {
      meta.textContent = "";
      fill(out, h("p", { class: "empty" },
        h("strong", null, "No brief yet. "),
        "Press ", h("strong", null, "Run morning loop"),
        " and Kept will sort the inbox, chase what's owed, check the news, and write today's brief. Overdue promises always come first."));
      return;
    }
    const stale = b.date && b.date !== localISO();
    fill(meta, stale ? chip(`from ${fmtDay(b.date)}`, "chip-soon") : null, " ",
      b.model ? `Written by ${shortModel(b.model)}` : "", b.ts ? ` · ${clock(b.ts)}` : "");
    const ledger = openIndex();
    const pending = new Set(st.pending.map((a) => a.id));
    const lines = (b.lines || []).filter((l) => l && typeof l === "object");
    const isOver = (l) => {
      const r = l.ref && ledger[l.ref];
      return (r && r.due && dayDiff(r.due) < 0) || /^overdue/i.test(l.text || "") ? 1 : 0;
    };
    const sorted = [...lines].sort((x, y) => isOver(y) - isOver(x));
    fill(out,
      h("p", { class: "headline" }, b.headline || "Today"),
      sorted.length ? h("ul", { class: "brief-lines" }, sorted.map((l) => {
        const over = isOver(l);
        const ask = l.ref && pending.has(l.ref);
        return h("li", { class: over ? "is-over" : ask ? "is-ask" : "" },
          over ? chip("Overdue", "chip-over") : ask ? chip("Needs your Yes", "chip-ask") : null,
          h("span", { class: "txt" }, l.text || ""),
          l.added_by === "rule" ? chip("added by rule", "rule-mark",
            "The model left this out. Code added it, because an overdue promise is never skipped.") : null);
      })) : h("p", { class: "muted" }, "Nothing urgent in today's brief."),
      b.plan && b.plan.length ? [h("h3", { class: "h3" }, "Plan for today"),
        h("ol", { class: "plan" }, b.plan.map((p) => h("li", null, String(p))))] : null);
  }

  // --- money
  function renderMoney(st) {
    const c = st.cash;
    const callout = $("#cash-callout");
    const chartEl = $("#cash-chart");
    if (!c) {
      fill(callout, h("p", { class: "empty" }, "No money data yet. Kept reads invoices, bills and your balance from money.json."));
      chartEl.replaceChildren();
      return;
    }
    $("#money-meta").textContent = `starting balance ${usd(c.start)}`;
    if (c.short) {
      const fix = (c.fix || []);
      fill(callout, h("div", { class: "callout callout-short", role: "status" },
        h("strong", { class: "big" }, `You'll be ${usd(c.short.gap)} short on ${fmtLong(c.short.date)}`),
        h("span", null, `when ${c.short.because} goes out.`),
        fix.length ? h("span", { class: "fix" }, "What fixes it: ", fix.map((f, i) => [i ? "; " : "",
          `${f.what} (${usd(f.amount)}) was due ${fmtShort(f.due)} but, at their usual pace, lands ${fmtShort(f.expected)}`]), ".") : null,
        st.rescue && st.rescue.needed ? h("a", { href: "#rescue" }, "See the rescue plan") : null));
    } else {
      fill(callout, h("div", { class: "callout callout-ok" },
        h("strong", null, "No shortfall in the next 30 days."),
        c.lowest ? h("span", null, `Lowest point ${usd(c.lowest.balance)} on ${fmtShort(c.lowest.date)}.`) : null));
    }
    drawCash(chartEl, c);

    const ev = c.timeline || [];
    $("#cash-events-count").textContent = ev.length ? `(${ev.length})` : "";
    fill($("#cash-events"), ev.length ? ev.map((e) => h("li", null,
      h("span", null, fmtShort(e.date)),
      h("span", null, e.what, e.kind === "in" && e.due && e.due.slice(0, 10) !== e.date ? h("span", { class: "muted" }, ` (due ${fmtShort(e.due)})`) : null),
      h("span", { class: e.kind === "in" ? "amt-in" : "amt-out" }, e.kind === "in" ? `+${usd(e.amount)}` : usd(e.amount)),
      h("span", { class: `bal ${e.balance < 0 ? "neg" : ""}` }, usd(e.balance)))) : h("li", { class: "muted" }, "Nothing scheduled in the next 30 days."));

    renderInvoices(st);
  }

  function drawCash(el, c) {
    const W = Math.max(280, el.clientWidth || 600), H = 210;
    const pad = { l: 52, r: 14, t: 18, b: 26 };
    const today = isoToDate(localISO());
    const end = new Date(today); end.setDate(end.getDate() + 30);
    const pts = [{ d: today, b: Number(c.start) || 0 }];
    for (const e of c.timeline || []) {
      const d = isoToDate(e.date);
      if (!d) continue;
      pts.push({ d, b: pts[pts.length - 1].b, step: true });
      pts.push({ d, b: Number(e.balance), e });
    }
    pts.push({ d: end, b: pts[pts.length - 1].b });
    const bals = pts.map((p) => p.b);
    let lo = Math.min(0, ...bals), hi = Math.max(0, ...bals);
    const span = hi - lo || 1;
    lo -= span * 0.08; hi += span * 0.1;
    const x = (d) => pad.l + ((d - today) / (end - today)) * (W - pad.l - pad.r);
    const y = (b) => pad.t + (1 - (b - lo) / (hi - lo)) * (H - pad.t - pad.b);
    const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.d).toFixed(1)},${y(p.b).toFixed(1)}`).join(" ");
    const area = `${path} L${x(end).toFixed(1)},${y(0).toFixed(1)} L${x(today).toFixed(1)},${y(0).toFixed(1)} Z`;
    const clipId = "cash-neg-clip";
    const lowest = c.lowest;
    const desc = `Balance over the next 30 days, from ${usd(c.start)} today. ` +
      (c.short ? `It drops below zero on ${fmtLong(c.short.date)}, ${usd(-c.short.gap)}, when ${c.short.because} goes out. ` : "") +
      (lowest ? `Lowest point ${usd(lowest.balance)} on ${fmtShort(lowest.date)}.` : "");
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": desc });
    svg.append(s("defs", null, s("clipPath", { id: clipId }, s("rect", { x: 0, y: y(0), width: W, height: Math.max(0, H - y(0)) }))));
    // y ticks: top, zero, bottom
    const ticks = [...new Set([Math.round(hi / 100) * 100, 0, lo < 0 ? Math.round(lo / 100) * 100 : null].filter((v) => v !== null))];
    for (const v of ticks) {
      if (y(v) < pad.t - 2 || y(v) > H - pad.b + 2) continue;
      svg.append(s("line", { class: v === 0 ? "zero" : "ax", x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) }));
      svg.append(s("text", { x: pad.l - 6, y: y(v) + 4, "text-anchor": "end" }, usd(v)));
    }
    // x ticks
    for (const k of [0, 10, 20, 30]) {
      const d = new Date(today); d.setDate(d.getDate() + k);
      svg.append(s("text", { x: x(d), y: H - 6, "text-anchor": k === 0 ? "start" : k === 30 ? "end" : "middle" },
        k === 0 ? "Today" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" })));
    }
    svg.append(s("path", { class: "neg-area", d: area, "clip-path": `url(#${clipId})` }));
    svg.append(s("path", { class: "line", d: path }));
    if (c.short) {
      const sd = isoToDate(c.short.date);
      const sx = x(sd);
      svg.append(s("line", { class: "short-mark", x1: sx, x2: sx, y1: pad.t - 6, y2: H - pad.b }));
      const right = sx > W * 0.6;
      svg.append(s("text", { class: "short-lbl", x: sx + (right ? -6 : 6), y: pad.t + 2, "text-anchor": right ? "end" : "start" },
        `${usd(-c.short.gap)} on ${fmtShort(c.short.date)}`));
    }
    for (const p of pts.filter((q) => q.e)) {
      const dot = s("circle", { class: p.e.kind === "in" ? "dot-in" : "dot-out", cx: x(p.d), cy: y(p.b), r: 4.5 },
        s("title", null, `${fmtShort(p.e.date)}: ${p.e.what} ${p.e.kind === "in" ? "+" : ""}${usd(p.e.amount)} → ${usd(p.e.balance)}`));
      svg.append(dot);
    }
    fill(el, svg, h("div", { class: "chart-legend", "aria-hidden": "true" },
      h("span", null, h("i", { class: "lg-in" }), "money in"), h("span", null, h("i", { class: "lg-out" }), "money out"),
      c.short ? h("span", null, h("i", { class: "lg-neg" }), "below zero") : null));
  }

  function renderInvoices(st) {
    const el = $("#invoices");
    const invs = st.invoices || [];
    if (!invs.length) { fill(el, h("p", { class: "empty" }, "No invoices on file yet.")); return; }
    const expected = Object.fromEntries((st.cash?.timeline || []).filter((e) => e.invoice).map((e) => [String(e.invoice), e.date]));
    const waiting = {};
    for (const a of st.pending) if (a.args && a.args.invoice) waiting[String(a.args.invoice)] = a.args.step || "reminder";
    const rank = (i) => (i.paid_on ? 2 : dayDiff(i.due) < 0 ? 0 : 1);
    const rows = [...invs].sort((p, q) => rank(p) - rank(q) || String(q.due).localeCompare(String(p.due)));
    const habitText = (client) => {
      const hb = (st.habits || {})[client];
      if (!hb || !hb.paid) return "no payment history yet";
      return hb.typical_days_late > 0 ? `usually pays ${plural(hb.typical_days_late, "day")} late` : `usually pays on time (${plural(hb.paid, "invoice")})`;
    };
    fill(el, h("div", { class: "table-wrap inv-wrap" }, h("table", { class: "inv" },
      h("thead", null, h("tr", null, h("th", { scope: "col" }, "Invoice"), h("th", { scope: "col", class: "num" }, "Amount"),
        h("th", { scope: "col" }, "Status"), h("th", { scope: "col" }, "Their habit · reminders"))),
      h("tbody", null, rows.map((i) => {
        const late = !i.paid_on && dayDiff(i.due) < 0;
        let status;
        if (i.paid_on) {
          const d = Math.round((isoToDate(i.paid_on) - isoToDate(i.due)) / 86400000);
          status = [chip("Paid", "chip-ok"), ` ${fmtShort(i.paid_on)}`, d > 0 ? h("span", { class: "muted" }, ` · ${plural(d, "day")} late`) : null];
        } else if (late) {
          status = [chip(`Overdue ${-dayDiff(i.due)}d`, "chip-over"), " ",
            expected[String(i.number)] ? h("span", { class: "muted" }, `expected ${fmtShort(expected[String(i.number)])}`) : null];
        } else {
          status = [chip(`Due ${fmtShort(i.due)}`, "chip-due"),
            expected[String(i.number)] && expected[String(i.number)] !== i.due ? h("span", { class: "muted" }, ` · expected ${fmtShort(expected[String(i.number)])}`) : null];
        }
        const sent = (i.reminders || []).map((r) => chip(`${cap(r.step)} sent`, "chip-outline", r.ts ? `Sent ${ago(r.ts)}` : null));
        const w = waiting[String(i.number)];
        return h("tr", { class: late ? "is-over" : "" },
          h("td", { class: "c-client" }, h("strong", null, `#${i.number}`), " ", i.client),
          h("td", { class: "num c-amt" }, usd(i.amount)),
          h("td", { class: "c-status" }, status),
          h("td", { class: "c-habit" }, h("span", { class: "habit" }, habitText(i.client)),
            sent.length || w ? h("div", { class: "steps-row" }, sent,
              w ? h("a", { href: "#approvals", class: "chip chip-ask" }, `${cap(w)} reminder waiting for your Yes`) : null) : null));
      })))));
  }

  // --- rescue
  function renderRescue(st) {
    const r = st.rescue;
    const sec = $("#rescue");
    const show = !!(r && r.needed);
    sec.hidden = !show;
    $("#jump-rescue").hidden = !show;
    if (!show) return;
    $("#rescue-meta").textContent = `${r.model ? shortModel(r.model) + " · " : ""}${ago(r.ts)}`;
    const gap = r.gap || {};
    const days = gap.date ? dayDiff(gap.date) : null;
    const steps = (r.steps || []).filter((x) => !/lead card/.test(x.type || ""));
    let running = 0;
    const pendingIds = new Set(st.pending.map((a) => a.id));
    const waitingDrafts = (r.drafts || []).filter((id) => pendingIds.has(id)).length;
    fill($("#rescue-body"),
      h("p", { class: "gapline" }, "Gap to close: ", h("strong", null, usd(gap.gap)),
        ` by ${fmtLong(gap.date)}`, days !== null ? ` (${plural(days, "day")} from now)` : "", gap.because ? `, when ${gap.because} goes out.` : "."),
      steps.length ? h("ol", { class: "steps", "aria-label": "Steps, fastest and likeliest first" }, steps.map((st_) => {
        running += Number(st_.amount) || 0;
        const closes = r.closes_gap_at === st_.id;
        return h("li", { class: closes ? "closes" : "" },
          h("div", { class: "st-top" }, chip(st_.type, "chip-rescue"), h("span", { class: "st-amt" }, usd(st_.amount)),
            h("span", { class: "muted" }, `cash in ~${plural(st_.days_to_cash, "day")}`),
            closes ? h("span", { class: "closes-flag" }, icon("check"), ` closes the gap (${usd(running)} so far)`) : null),
          h("p", { class: "st-action" }, st_.action || st_.detail || ""),
          h("p", { class: "st-why" }, [st_.who ? `${personName(st_.who)}. ` : "", st_.why || ""]));
      })) : h("p", { class: "empty" }, "No steps passed the checks this time."),
      waitingDrafts ? h("p", { class: "note" }, `${plural(waitingDrafts, "check-in email")} from this plan ${waitingDrafts === 1 ? "is" : "are"} `,
        h("a", { href: "#approvals" }, "waiting for your Yes"), ".") : null,
      (r.prospects || []).length ? [h("h3", { class: "h3" }, "New local businesses (lead cards, never cold emails)"),
        h("div", { class: "leads" }, r.prospects.map((p) => {
          const u = safeUrl(p.url);
          return h("article", { class: "lead" },
            h("h4", null, p.business),
            p.why ? h("p", null, cap(p.why)) : null,
            p.quote ? h("blockquote", null, `“${p.quote}”`) : null,
            u ? h("a", { href: u, target: "_blank", rel: "noopener noreferrer" }, icon("link"), " ", host(u), h("span", { class: "sr-only" }, " (opens in a new tab)")) : null,
            p.opener ? [h("p", { class: "opener" }, p.opener), copyBtn(p.opener, "Copy opener")] : null);
        }))] : null,
      r.reasoning ? h("details", { class: "reasoning" }, h("summary", null, "How Nemotron Ultra weighed it"), h("div", { class: "body" }, r.reasoning)) : null);
  }

  // --- scope
  const VERDICT = { in_scope: "In scope", out_of_scope: "Extra work", unclear: "Unclear: your call", already_promised: "Already promised" };
  function renderScope(st) {
    const el = $("#scope-list");
    const rows = (st.scope || []).filter((x) => (x.requests || []).length);
    $("#scope-meta").textContent = st.scope && st.scope.length ? `${plural(st.scope.length, "email")} checked` : "";
    if (!rows.length) {
      fill(el, h("p", { class: "empty" }, "No requests checked yet. When a client with an agreement on file asks for work, Kept checks it during ",
        h("strong", null, "Sort the inbox"), "."));
      return;
    }
    const pendingIds = new Set(st.pending.map((a) => a.id));
    fill(el, rows.map((x) => h("div", { class: "scope-mail" },
      h("h3", null, x.client, h("span", { class: "muted" }, `“${x.subject}”`), h("span", { class: "meta" }, ago(x.ts))),
      h("ul", { class: "reqs" }, x.requests.map((q) => h("li", { class: `req v-${q.verdict}` },
        h("div", { class: "req-top" }, h("span", { class: "req-text" }, q.request),
          h("span", { class: "kind-row" }, chip(VERDICT[q.verdict] || q.verdict, `v-chip-${q.verdict}`),
            q.price ? chip(`${usd(q.price)} · ${q.hours_low}–${q.hours_high} h`, "chip-outline") : null)),
        q.email_quote ? h("p", null, "They wrote: ", h("q", null, q.email_quote)) : null,
        q.agreement_quote ? h("blockquote", null, h("span", { class: "sr-only" }, "Agreement says: "), `Agreement: “${q.agreement_quote}”`) : null,
        q.reason ? h("p", { class: "reason" }, q.reason) : null))),
      x.approval ? h("p", { class: "note" }, pendingIds.has(x.approval) ? "An offer for the extra work is " : "An offer for the extra work was drafted; ",
        pendingIds.has(x.approval) ? h("a", { href: "#approvals" }, "waiting for your Yes") : "see Recently decided", ".") : null)));
  }

  // --- your word
  function renderWord(st) {
    const el = $("#word-body");
    const c = st.calibration;
    if (!c || !c.overall || !c.overall.total) {
      fill(el, h("p", { class: "empty" }, "No closed promises with a due date yet. As you close promises, Kept learns how often you're on time, and for which kinds of work."));
      return;
    }
    const o = c.overall;
    const cls = (r) => (r >= 0.8 ? "" : r >= 0.5 ? "mid" : "low");
    const bars = (obj, limit = 8) => {
      const rows = Object.entries(obj || {}).sort((a, b) => b[1].total - a[1].total || a[1].rate - b[1].rate).slice(0, limit);
      return h("ul", { class: "bars" }, rows.map(([k, v]) => h("li", null,
        h("span", { class: "lbl", title: k }, cap(k)),
        h("span", { class: "track", role: "img", "aria-label": `${k}: ${v.kept} of ${v.total} on time` }, h("span", { class: cls(v.rate), style: `width:${Math.max(3, v.rate * 100)}%` })),
        h("span", { class: "val" }, `${v.kept}/${v.total}${v.median_slip > 0 ? ` · +${v.median_slip}d` : ""}`))));
    };
    const worst = Object.entries(c.by_kind || {}).filter(([, v]) => v.total >= 3 && v.median_slip > 0).sort((a, b) => a[1].rate - b[1].rate)[0];
    const day = Object.entries(c.by_weekday || {}).filter(([, v]) => v.total >= 3 && v.median_slip > 0).sort((a, b) => a[1].rate - b[1].rate)[0];
    fill(el,
      h("div", { class: "word-top" }, h("span", { class: "word-big" }, pct(o.rate)),
        h("span", { class: "word-sub" }, `of your promises landed on time (${o.kept} of ${o.total}). `,
          o.median_slip > 0 ? `The typical one is ${plural(o.median_slip, "day")} late.` : "The typical one lands on the day.")),
      worst || day ? h("p", { class: "note note-advice word-insight" },
        worst ? `${cap(worst[0])} promises are your weak spot: ${worst[1].kept} of ${worst[1].total} on time, typically ${plural(worst[1].median_slip, "day")} late. ` : "",
        day ? `Promises due on a ${day[0]}: ${day[1].kept} of ${day[1].total} on time.` : "") : null,
      h("h3", { class: "h3" }, "By kind of work"), bars(c.by_kind),
      h("h3", { class: "h3" }, "By person"), bars(c.by_person, 6),
      h("h3", { class: "h3" }, "By weekday due"), bars(c.by_weekday, 7));
  }

  // --- ledger
  function dueChip(due, dir) {
    if (!due) return chip("No due date", "chip-outline");
    const d = dayDiff(due);
    if (d === null) return chip(`Due ${due}`, "chip-due");
    if (d < 0) return chip(dir === "owed_to_me" ? `Late ${-d}d` : `Overdue ${-d}d`, "chip-over", `Was due ${fmtDay(due)}`);
    if (d === 0) return chip("Due today", "chip-soon");
    if (d === 1) return chip("Due tomorrow", "chip-soon");
    return chip(`Due ${fmtDay(due)}`, "chip-due");
  }

  function renderLedger(st) {
    const list = $("#ledger-list");
    const mails = inboxIndex();
    const byDir = { i_owe: [], owed_to_me: [] };
    for (const r of st.open) byDir[dirOf(r)].push(r);
    const over = byDir.i_owe.filter((r) => r.due && dayDiff(r.due) < 0).length;
    $("#promises-count").textContent = `${st.open.length} open${over ? ` · ${over} overdue` : ""}`;
    $("#n-i_owe").textContent = `(${byDir.i_owe.length})`;
    $("#n-owed_to_me").textContent = `(${byDir.owed_to_me.length})`;
    for (const t of document.querySelectorAll(".tabs [role=tab]")) {
      const on = t.dataset.dir === ledgerDir;
      t.setAttribute("aria-selected", on ? "true" : "false");
      t.tabIndex = on ? 0 : -1;
    }
    $("#ledger-panel").setAttribute("aria-labelledby", `tab-${ledgerDir}`);
    const rows = byDir[ledgerDir];
    if (!rows.length) {
      fill(list, h("li", { class: "empty" }, ledgerDir === "i_owe"
        ? ["Nothing you owe is open. Kept adds promises when it finds one in your mail (", h("strong", null, "One step → Sort the inbox"), "), or add one below."]
        : ["Nobody owes you anything Kept knows of. When a client promises you something (a payment, content, a decision), it shows up here, or add one below with ", h("strong", null, "They owe me"), "."]));
    } else {
      fill(list, rows.map((r) => {
        const late = r.due && dayDiff(r.due) < 0;
        const src = r.source && mails[r.source];
        const btn = h("button", { class: "btn btn-quiet btn-small", type: "button", "aria-label": `Close promise: ${r.text}` }, "Close…");
        btn.addEventListener("click", () => openClose(r, btn));
        return h("li", { class: late ? "is-over" : "" },
          h("span", { class: "l-text" }, r.text),
          h("div", { class: "l-meta" },
            dueChip(r.due, ledgerDir),
            r.who ? h("span", null, ledgerDir === "i_owe" ? "to " : "from ", personName(r.who)) : null,
            src ? h("a", { href: `#mail-${cssId(src.id)}`, onclick: () => openMail(src.id) }, icon("mail"), " ", src.subject)
              : r.origin === "owner" ? h("span", null, "added by you") : r.origin ? h("span", null, `from ${r.origin}`) : null),
          h("div", { class: "l-actions" }, btn),
          r.quote ? h("details", { class: "l-quote" }, h("summary", null, "The exact words"), h("blockquote", null, `“${r.quote}”`)) : null,
          r.history && r.history.length ? h("details", { class: "l-hist" },
            h("summary", null, plural(r.history.length, "update")),
            h("ul", null, r.history.slice(-6).map((e) => h("li", null, `${ago(e.ts)}: ${e.event}`)))) : null);
      }));
    }
    const cw = $("#closed-wrap");
    cw.hidden = !st.closed.length;
    $("#closed-count").textContent = st.closed.length ? `(${st.closed.length})` : "";
    const res = { done: ["Done", "chip-ok"], dropped: ["Dropped", "chip-no"], handed_off: ["Handed off", "chip-super"] };
    fill($("#closed-list"), st.closed.map((r) => {
      const [l, c] = res[r.status] || [r.status, ""];
      return h("li", { class: "closed-row" }, chip(l, c), h("span", null, r.text),
        r.who ? h("span", { class: "muted" }, `· ${personName(r.who)}`) : null,
        h("span", { class: "muted" }, `· ${ago(r.closed)}`),
        r.note ? h("span", { class: "note" }, `Note: ${r.note}`) : null);
    }));
  }
  const tabs = [...document.querySelectorAll(".tabs [role=tab]")];
  function selectTab(dir, focus) {
    ledgerDir = dir;
    if (S) renderLedger(S);
    sigs.ledger = null;
    if (focus) $(`#tab-${dir}`).focus();
  }
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => selectTab(t.dataset.dir, false));
    t.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        e.preventDefault();
        const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        selectTab(n.dataset.dir, true);
      }
    });
  });

  const cssId = (x) => String(x).replace(/[^a-zA-Z0-9_-]/g, "_");
  function openMail(id) {
    const card = $("#inbox");
    if (card.classList.contains("is-folded")) setFold(card, true, true);
    const d = document.getElementById(`mail-${cssId(id)}`);
    if (d) { const det = d.querySelector("details"); if (det) det.open = true; }
  }

  // close dialog
  const dlg = $("#close-dialog");
  let closing = null;
  function openClose(row, trigger) {
    closing = { row, trigger };
    $("#close-text").textContent = row.text + (row.who ? ` (${dirOf(row) === "i_owe" ? "to" : "from"} ${personName(row.who)})` : "");
    $("#close-form").reset();
    $("#close-error").textContent = "";
    $("#close-submit").disabled = false;
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    $("#close-note").focus();
  }
  const endClose = () => { if (dlg.open) dlg.close(); };
  dlg.addEventListener("close", () => {
    const t = closing && closing.trigger;
    closing = null;
    if (t && document.body.contains(t)) { t.focus(); return; }
    const hd = $("#h-promises");
    hd.setAttribute("tabindex", "-1");
    hd.focus();
  });
  $("#close-cancel").addEventListener("click", endClose);
  $("#close-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!closing) return;
    const fd = new FormData(ev.target);
    const note = String(fd.get("note") || "").trim();
    const resolution = String(fd.get("resolution") || "done");
    if (note.length < 5) {
      $("#close-error").textContent = "Write a short note about what happened (at least 5 characters). Future you will want to know.";
      $("#close-note").focus();
      return;
    }
    $("#close-submit").disabled = true;
    try {
      await api("POST", `/api/ledger/${encodeURIComponent(closing.row.id)}/close`, { resolution, note });
      const text = closing.row.text;
      closing.trigger = null; // its row is about to disappear; send focus to the section heading
      endClose();
      toast(`Closed as ${resolution.replace("_", " ")}: ${text}`, "good");
      refresh();
    } catch (e) {
      $("#close-error").textContent = e.message;
      $("#close-submit").disabled = false;
    }
  });

  // add form
  $("#add-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target;
    const fd = new FormData(f);
    const text = String(fd.get("text") || "").trim();
    if (!text) { f.text.focus(); return; }
    const direction = String(fd.get("direction") || "i_owe");
    const btn = f.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      await api("POST", "/api/ledger", { text, who: String(fd.get("who") || "").trim(), due: fd.get("due") || null, direction });
      f.reset();
      toast(`Added to ${direction === "i_owe" ? "what you owe" : "what you're owed"}: ${text}`, "good");
      if (direction !== ledgerDir) selectTab(direction, false);
      refresh();
    } catch (e) {
      toast(`Couldn't add it: ${e.message}`, "err");
    } finally {
      btn.disabled = false;
    }
  });

  // --- held back
  const JOB_LABEL = {
    triage: "While sorting mail", extract: "While pulling promises from mail", follow_up: "While drafting a follow-up",
    watch: "While checking the news", overload: "While weighing the week", brief: "While writing the brief",
    precheck: "While checking your draft", chase: "While drafting a payment reminder", rescue: "While planning a cash rescue",
    prospects: "While looking for new clients", scope: "While checking scope", offers: "While weighing offers",
    growth: "While looking for happy clients", learn: "While learning from your history",
  };
  function renderHeld(st) {
    const list = $("#held-list");
    $("#held-count").textContent = st.abstained.length ? `${st.abstained.length} recent` : "";
    if (!st.abstained.length) {
      fill(list, h("li", { class: "empty" },
        h("strong", null, "Nothing held back yet. "),
        "If a model quotes words that aren't in the email, picks a date that makes no sense, or leaves a [NAME] hole in a draft, Kept stops and shows the reason here."));
      return;
    }
    fill(list, st.abstained.map((a) => h("li", null,
      h("div", { class: "held-top" },
        h("span", null, chip(JOB_LABEL[a.job] || a.job, "chip-held")),
        h("time", { datetime: a.ts }, ago(a.ts))),
      h("p", { class: "held-subject" }, a.subject || ""),
      h("ul", { class: "held-problems", "aria-label": "Why Kept held back" },
        (a.problems || []).map((p) => h("li", null, plainProblem(p)))),
      a.payload !== null && a.payload !== undefined ? h("details", null,
        h("summary", null, "What the model proposed"),
        h("pre", { class: "payload" }, JSON.stringify(a.payload, null, 2))) : null)));
  }
  function sourceName(id) {
    id = String(id);
    if (id === "agreement") return "the signed agreement";
    if (id === "draft") return "your draft";
    if (id === "email" || id === "m" || /^(demo|mail):/.test(id)) return "the email";
    if (/^web:/.test(id)) return "the web page it cites";
    if (/^ledger:/.test(id)) return "your ledger";
    return id;
  }
  function plainProblem(p) {
    const str = String(p);
    let m;
    if ((m = str.match(/^claim (\d+): the quoted words are not in source '(.+)'$/))) return `The quoted words aren't in ${sourceName(m[2])}, so it can't be trusted.`;
    if ((m = str.match(/^claim (\d+) cites '(.+)', which Kept never fetched$/))) return `It cited "${m[2]}", a source Kept never read.`;
    if (/has no usable quote/.test(str)) return "It gave no quote to back the claim.";
    if ((m = str.match(/^missing field '(.+)'$/))) return `The answer was missing "${m[1]}".`;
    if (/^model reply unusable/.test(str)) {
      const why = str.replace(/^model reply unusable:\s*/, "");
      if (/missing credentials|api[_ ]key/i.test(why)) return "No usable model reply: the model API key isn't set up yet, so Kept didn't guess.";
      if (/no JSON|syntax/i.test(why)) return "The model's reply wasn't readable structured data, so Kept didn't use it.";
      return `No usable model reply (${why.slice(0, 160)}), so Kept didn't guess.`;
    }
    if ((m = str.match(/^search failed: (.*)$/))) return `Web search failed (${m[1].slice(0, 120)}).`;
    return cap(str) + (/[.!?)]$/.test(str) ? "" : ".");
  }

  // --- inbox
  function renderInbox(st) {
    const list = $("#inbox-list");
    const labels = st.labels || {};
    const sources = new Set(st.open.map((r) => r.source).filter(Boolean));
    const mails = [...st.inbox].reverse();
    const sortedN = mails.filter((m) => labels[m.id]).length;
    $("#inbox-count").textContent = mails.length ? `${mails.length} emails · ${sortedN} sorted` : "";
    if (!mails.length) {
      fill(list, h("li", { class: "empty" }, "The inbox is empty. New mail shows up here, and Kept labels it when it sorts the inbox."));
      return;
    }
    const openNow = new Set([...list.querySelectorAll("details[open]")].map((d) => d.dataset.id));
    fill(list, mails.map((m) => {
      const lab = labels[m.id];
      return h("li", { id: `mail-${cssId(m.id)}` },
        h("details", { "data-id": m.id, open: openNow.has(m.id) || null },
          h("summary", null,
            h("span", { class: "m-from" }, personName(m.from)),
            h("span", { class: "m-date" }, m.date && /^\d{4}-\d\d-\d\d/.test(m.date) ? fmtDay(m.date) : (m.date || "")),
            h("span", { class: "m-subj" }, m.subject || "(no subject)"),
            h("span", { class: "m-tags" },
              lab ? chip(lab.kind, `kind-${["lead", "client", "bill", "personal", "noise"].includes(lab.kind) ? lab.kind : "noise"}`) : chip("not sorted yet", "chip-outline"),
              lab && lab.needs_reply ? chip("needs reply", "chip-ask") : null,
              sources.has(m.id) ? chip("promise tracked", "chip-ok") : null,
              lab && lab.one_line ? h("span", null, lab.one_line) : null)),
          h("div", { class: "m-body" }, m.body || "")));
    }));
  }

  // --- news
  function renderNews(st) {
    const out = $("#news-list");
    const w = st.watch;
    if (!w) {
      $("#news-meta").textContent = "";
      fill(out, h("p", { class: "empty" },
        h("strong", null, "No news check yet. "),
        "Kept searches the web for the topics in your notes and keeps only facts it can quote word for word from the page. Run it with ",
        h("strong", null, "One step → Check the news"), "."));
      return;
    }
    $("#news-meta").textContent = w.ts ? `checked ${ago(w.ts)}` : "";
    const topics = (w.topics && w.topics.length) ? w.topics : [...new Set((w.claims || []).map((c) => c.topic))];
    fill(out,
      topics.map((t) => {
        const cs = (w.claims || []).filter((c) => c.topic === t);
        return h("div", { class: "topic" },
          h("h3", null, t),
          cs.length ? cs.map((c) => {
            const u = safeUrl(c.url);
            return h("div", { class: "claim" },
              h("p", null, c.text),
              c.quote ? h("blockquote", null, `“${c.quote}”`) : null,
              u ? h("a", { href: u, target: "_blank", rel: "noopener noreferrer" }, icon("link"), " ", host(u),
                h("span", { class: "sr-only" }, " (opens in a new tab)")) : null);
          }) : h("p", { class: "muted" }, "Nothing quotable found this time."));
      }),
      h("p", { class: "news-foot" }, icon("shield"),
        `${plural((w.claims || []).length, "fact")} kept`,
        w.dropped ? ` · ${w.dropped} dropped because the quote wasn't on the page` : " · every quote checked against its page"));
  }

  // --- offers & growth
  function renderGrowth(st) {
    const el = $("#growth-body");
    const op = st.offers_plan, g = st.growth;
    const pendingIds = new Set(st.pending.map((a) => a.id));
    const waitingLink = (ids, one) => {
      const n = (ids || []).filter((id) => pendingIds.has(id)).length;
      return n ? h("a", { href: "#approvals" }, `${plural(n, one)} waiting for your Yes`) : null;
    };
    const offers = op ? h("div", { class: "gsec" },
      h("h3", null, "Seasonal offers", h("span", { class: "meta" }, ago(op.ts))),
      (op.offers || []).length ? h("p", null, waitingLink(op.offers, "offer") || plural(op.offers.length, "offer") + " drafted.")
        : h("p", { class: "muted" }, (op.considered || []).length
          ? `Considered ${op.considered.join(", ")}; no offer was worth making.`
          : "No offer this time. That's the default: a discount at the wrong moment teaches clients to wait for one."),
      (op.skipped || []).length ? [h("p", { class: "h3" }, "Left alone, and why"),
        h("ul", { class: "glist" }, op.skipped.map((x) => h("li", null, h("strong", null, x.client), `: ${x.why_not}.`)))] : null,
      (op.declined || []).length ? [h("p", { class: "h3" }, "Ultra decided against"),
        h("ul", { class: "glist" }, op.declined.map((x) => h("li", null, h("strong", null, x.client || "?"), x.why ? `: ${x.why}` : "")))] : null)
      : h("div", { class: "gsec" }, h("h3", null, "Seasonal offers"),
        h("p", { class: "empty" }, "Not considered yet. Run ", h("strong", null, "One step → Consider seasonal offers"), "; Kept checks the calendar, who pays on time, and your discount rules."));
    const grow = g ? h("div", { class: "gsec" },
      h("h3", null, "Reviews & proof of work", h("span", { class: "meta" }, ago(g.ts))),
      (g.asks || []).length || (g.posts || []).length
        ? h("p", null, [waitingLink(g.asks, "review ask"), (g.asks || []).length && (g.posts || []).length ? " · " : "", waitingLink(g.posts, "post")])
        : h("p", { class: "muted" }, "No happy client to ask this time."),
      (g.waiting || []).length ? [h("p", { class: "h3" }, "Happy, but not asking yet"),
        h("ul", { class: "glist" }, g.waiting.map((x) => h("li", null, h("strong", null, x.client), `: ${x.why}.`,
          x.quote ? [" They wrote ", h("q", null, x.quote)] : null)))] : null)
      : h("div", { class: "gsec" }, h("h3", null, "Reviews & proof of work"),
        h("p", { class: "empty" }, "Not checked yet. Run ", h("strong", null, "One step → Look for happy clients"), "; Kept asks for a review only when the work is done, paid and on time."));
    fill(el, offers, grow);
  }

  function renderMedia(st) {
    const el = $("#media-body");
    const media = st.media || {};
    const clients = [...new Map([...(st.invoices || []).map((i) => [slug(i.client), i.client]),
      ...Object.keys(media).map((k) => [k, null])]).entries()];
    if (!clients.length) { fill(el, h("p", { class: "empty" }, "Clients appear here once they have an invoice.")); return; }
    fill(el, clients.map(([sl, name]) => {
      const rec = media[sl] || {};
      const display = name || sl.replace(/-/g, " ");
      return h("div", { class: "media-row" },
        h("strong", null, cap(display)),
        h("div", { class: "media-slots" }, ["before", "after"].map((which) => {
          const u = rec[which] && mediaUrl(rec[which].path);
          if (u) return h("figure", { class: "slot" }, h("img", { src: u, alt: `${cap(which)} picture for ${display}`, loading: "lazy" }),
            h("figcaption", null, `${cap(which)} · ${rec[which].how || ""}`));
          const input = h("input", { type: "file", accept: "image/jpeg,image/png,image/webp", "aria-label": `Add the ${which} photo for ${display}` });
          input.addEventListener("change", () => upload(sl, which, input, display));
          return h("div", { class: "slot" }, h("label", { class: "upl" }, input, `+ Add ${which} photo`), h("span", { class: "muted" }, `No ${which} picture yet`));
        })));
    }));
  }
  async function upload(sl, which, input, display) {
    const f = input.files && input.files[0];
    if (!f) return;
    if (f.size > 8_000_000) { toast("That photo is larger than 8 MB.", "err"); input.value = ""; return; }
    const fd = new FormData();
    fd.append("file", f, f.name);
    input.disabled = true;
    try {
      await request("POST", `/api/media/${encodeURIComponent(sl)}/${which}`, { body: fd });
      toast(`Saved the ${which} photo for ${display}.`, "good");
      refresh();
    } catch (e) {
      toast(`Couldn't save the photo: ${e.message}`, "err");
      input.disabled = false;
      input.value = "";
    }
  }

  // --- ask
  $("#ask-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const q = $("#ask-q").value.trim();
    if (!q) { $("#ask-q").focus(); return; }
    const out = $("#ask-out");
    const btn = $("#ask-btn");
    btn.disabled = true;
    fill(out, h("p", { class: "loading" }, h("span", { class: "spinner", "aria-hidden": "true" }), "Reading your ledger, journal and notes…"));
    try {
      const r = await api("POST", "/api/ask", { question: q });
      const ok = !!r.verified;
      fill(out, h("div", { class: `answer ${ok ? "ok" : "notok"}` },
        h("div", null, ok ? chip("Verified", "chip-ok", "Every quote was found word for word in Kept's records")
          : chip("Not verified", "chip-held", "Kept couldn't match the answer's quotes to its records")),
        h("p", { class: "answer-text" }, r.answer || "(no answer)"),
        r.evidence && r.evidence.length ? [h("h3", { class: "h3" }, "Evidence"),
          h("ul", { class: "evidence" }, r.evidence.map((e) => h("li", null,
            chip(String(e.source || "?"), "chip-outline"), " ", h("q", null, e.quote || ""))))] : null,
        !ok && r.problems && r.problems.length ? [h("h3", { class: "h3" }, "Why it isn't verified"),
          h("ul", { class: "problems" }, r.problems.map((p) => h("li", null, plainProblem(p))))] : null,
        r.model ? h("p", { class: "foot" }, `Answered by ${shortModel(r.model)}`) : null));
    } catch (e) {
      fill(out, h("div", { class: "answer notok" },
        h("div", null, chip("No answer", "chip-held")),
        h("p", null, `Kept couldn't answer right now: ${e.message}`),
        e.status >= 500 ? h("p", { class: "foot" }, "Model calls need a working Nebius Token Factory key. Nothing was guessed.") : null));
    } finally {
      btn.disabled = false;
      refresh();
    }
  });

  // --- models
  function renderModels(st) {
    const t = todayUTC();
    const today = st.calls.filter((c) => String(c.ts).startsWith(t));
    const byTier = {};
    for (const c of today) { const b = (byTier[c.tier] ||= { n: 0, usd: 0 }); b.n++; b.usd += Number(c.usd) || 0; }
    const tasksFor = (tier) => Object.entries(st.routes || {}).filter(([, v]) => v === tier).map(([k]) => k);
    fill($("#tiers"), ["nano", "super", "ultra"].filter((k) => st.tiers && st.tiers[k]).map((k) => {
      const tr = st.tiers[k];
      const use = byTier[k] || { n: 0, usd: 0 };
      return h("div", { class: `tier ${k}` },
        h("div", { class: "tier-top" },
          chip(`Nemotron ${tierName(k)}`, `chip-${k}`),
          h("span", { class: "meta" }, `${plural(use.n, "call")} today · ${money(use.usd)}`)),
        h("span", { class: "tier-model" }, tr.model),
        h("span", { class: "tier-why" }, cap(tr.why)),
        h("span", { class: "tier-foot" },
          tasksFor(k).length ? h("span", null, `Used for: ${tasksFor(k).join(", ")}`) : null,
          h("span", null, `$${Number(tr.in).toFixed(2)} in / $${Number(tr.out).toFixed(2)} out per 1M tokens`)));
    }));

    const p = st.budget > 0 ? Math.min(100, (st.spend_today / st.budget) * 100) : 0;
    const total = today.reduce((sum, c) => sum + (Number(c.usd) || 0), 0) || 0;
    const split = h("span", { class: "split", style: `width:${Math.max(p, st.spend_today > 0 ? 2 : 0)}%` },
      ["nano", "super", "ultra"].map((k) => {
        const share = total > 0 ? ((byTier[k]?.usd || 0) / total) * 100 : 0;
        return share > 0 ? h("span", { class: `seg-${k}`, style: `width:${share}%`, title: `${tierName(k)}: ${money(byTier[k].usd)}` }) : null;
      }));
    fill($("#budget"),
      h("div", null, h("strong", null, money(st.spend_today)), ` of ${money(st.budget)} daily budget · ${plural(today.length, "call")} today`,
        p >= 100 ? h("span", null, " · ", chip("Budget reached: model calls paused until tomorrow", "chip-over")) : null),
      h("div", { class: "bar", role: "img", "aria-label": `Spend by model size: ${["nano", "super", "ultra"].map((k) => `${tierName(k)} ${money(byTier[k]?.usd || 0)}`).join(", ")}` }, split));

    const body = $("#calls-body");
    const empty = $("#calls-empty");
    const wrap = $("#calls-wrap");
    $("#calls-count").textContent = st.calls.length ? `(${Math.min(25, st.calls.length)} of ${st.calls.length})` : "";
    if (!st.calls.length) {
      wrap.hidden = true;
      empty.hidden = false;
      empty.textContent = "No model calls yet. Each call will appear here with the Nemotron size that handled it and why, how long it took, and what it cost.";
      body.replaceChildren();
      return;
    }
    wrap.hidden = false;
    empty.hidden = true;
    fill(body, st.calls.slice(0, 25).map((c) => h("tr", null,
      h("td", { class: "c-time" }, h("time", { datetime: c.ts }, clock(c.ts))),
      h("td", { class: "c-model" }, chip(tierName(c.tier), `chip-${c.tier}`, c.model || null)),
      h("td", { class: "purpose c-purpose" }, c.purpose || "", c.task ? h("span", { class: "sub" }, `task: ${c.task}`) : null),
      h("td", { class: "why-col" }, c.why || ""),
      h("td", { class: "num tok-col" }, `${c.prompt_tokens ?? 0} → ${c.completion_tokens ?? 0}`),
      h("td", { class: "num c-ms" }, `${Number(c.ms || 0).toLocaleString()} ms`),
      h("td", { class: "num c-cost" }, money(c.usd)))));
  }

  // --- activity
  function describe(a) {
    switch (a.kind) {
      case "ledger_add": return `New promise: ${a.text}${a.who ? ` (${a.direction === "owed_to_me" ? "from" : "to"} ${personName(a.who)})` : ""}`;
      case "ledger_close": return `Closed a promise as ${String(a.resolution).replace("_", " ")}: ${a.note}`;
      case "approval_requested": return `Asked for your Yes: ${a.summary}`;
      case "approval_decided": return `You said ${a.yes ? "Yes" : "No"} (${a.by || "owner"})`;
      case "action": return `${a.action === "send_email" ? "Email" : a.action === "publish_post" ? "Post" : a.action === "add_rule" ? "Rule" : a.action} ${a.status}: ${a.result || ""}`;
      case "abstained": return `Held back (${(JOB_LABEL[a.job] || a.job).toLowerCase()}): ${(a.problems || []).map(plainProblem).join(" ")}`;
      case "job_failed": return `Step "${a.job}" failed: ${a.error}`;
      case "llm_refused": return `Model call refused: ${a.reason}`;
      case "gate_blocked": return `Gate blocked "${a.action}" without your Yes`;
      case "media": return `Saved the ${a.which} picture for ${a.client} (${a.how})`;
      default: return String(a.kind || "").replace(/_/g, " ");
    }
  }
  function renderActivity(st) {
    $("#activity-count").textContent = st.activity.length ? `(${st.activity.length})` : "";
    const list = $("#activity-list");
    if (!st.activity.length) { fill(list, h("li", { class: "muted" }, "Nothing has happened yet.")); return; }
    fill(list, st.activity.map((a) => h("li", null, h("time", { datetime: a.ts }, clock(a.ts)), h("span", null, describe(a)))));
  }

  // ------------------------------------------------------------------ jobs
  const JOB_NAMES = {
    day: "Running the morning loop: mail, follow-ups, money, offers, news, the week, the brief",
    triage: "Sorting the inbox with Nemotron Nano", follow_ups: "Drafting follow-ups with Nemotron Super",
    watch: "Checking the news and verifying every quote", overload: "Weighing the week with Nemotron Ultra",
    brief: "Writing the morning brief with Nemotron Super", learn: "Looking for patterns in your history with Nemotron Ultra",
    money: "Checking unpaid invoices and drafting reminders", rescue: "Planning a cash rescue with Nemotron Ultra",
    offers: "Weighing seasonal offers with Nemotron Ultra", growth: "Looking for happy clients",
  };
  const jobButtons = () => document.querySelectorAll("[data-job]");
  let timer = null;

  function setBusy(busy, external) {
    for (const b of jobButtons()) b.disabled = busy;
    const rb = $("#runbar");
    if (busy) {
      rb.hidden = false;
      if (external) { $("#runbar-text").textContent = "Kept is working on a run (started elsewhere, e.g. the scheduler)…"; $("#runbar-time").textContent = ""; }
    } else if (!localJob) {
      rb.hidden = true;
    }
  }

  function summarize(job, r) {
    const fails = [];
    const one = (name, v) => {
      if (typeof v === "string" && /^(failed|stopped):/.test(v)) { fails.push(`${name}: ${v}`); return null; }
      switch (name) {
        case "triage": return v ? `sorted ${plural(v.new || 0, "new email")}, found ${plural((v.commitments || []).length, "promise")}${v.abstained ? `, held back ${v.abstained}` : ""}` : null;
        case "follow_ups": return Array.isArray(v) ? (v.length ? `${plural(v.length, "follow-up")} waiting for your Yes` : "no follow-ups due") : null;
        case "watch": return v ? `kept ${plural((v.claims || []).length, "news fact")}${v.dropped ? `, dropped ${v.dropped} unverifiable` : ""}` : null;
        case "overload": return v ? "Ultra picked one deadline to move (waiting for your Yes)" : "the week fits, no deadline needs to move";
        case "brief": return v ? "brief written" : null;
        case "learn": return Array.isArray(v) ? (v.length ? `${plural(v.length, "new rule")} proposed for your Yes` : "no pattern strong enough to make a rule") : null;
        case "money": return Array.isArray(v) ? (v.length ? `${plural(v.length, "payment reminder")} waiting for your Yes` : "no invoice needs a reminder") : null;
        case "rescue": return v ? `rescue plan: ${plural((v.steps || []).length, "step")} for a ${usd(v.gap && v.gap.gap)} gap` : "no cash gap in the next 30 days";
        case "offers": return v ? (v.note ? v.note : `${plural((v.offers || []).length, "offer")} proposed, ${(v.skipped || []).length} left alone`) : null;
        case "growth": return v ? `${plural((v.asks || []).length, "review ask")}, ${plural((v.posts || []).length, "post")}${(v.waiting || []).length ? `, ${v.waiting.length} happy but not asked yet` : ""}` : null;
        default: return null;
      }
    };
    const parts = job === "day" && r && typeof r === "object"
      ? Object.entries(r).map(([k, v]) => one(k, v)).filter(Boolean)
      : [one(job, r)].filter(Boolean);
    return { text: parts.join("; "), fails };
  }

  async function runJob(job) {
    if (localJob || (S && S.busy)) { toast("Kept is already working. Wait for the current run to finish.", "info"); return; }
    closeMenu(false);
    localJob = job;
    const t0 = Date.now();
    $("#runbar-text").textContent = (JOB_NAMES[job] || job) + "…";
    $("#runbar-time").textContent = "0s";
    setBusy(true, false);
    announce(`${JOB_NAMES[job] || job}. This takes 10 to 60 seconds.`);
    timer = setInterval(() => { $("#runbar-time").textContent = `${Math.round((Date.now() - t0) / 1000)}s`; }, 1000);
    const poll = setInterval(refresh, 4000);
    try {
      const r = await api("POST", `/api/run/${encodeURIComponent(job)}`);
      const { text, fails } = summarize(job, r && r.result);
      if (fails.length) {
        toast(`Finished with problems. ${text ? "Done: " + text + ". " : ""}Didn't finish: ${fails.join(" | ")}`, "err");
        announce("Finished with problems.");
      } else {
        const msg = text ? cap(text) + "." : "Done.";
        toast(msg, "good");
        announce(msg);
      }
    } catch (e) {
      if (e.status === 409) toast("Kept is already working on something. Try again when it's done.", "info");
      else if (e.status >= 500) toast(`That step failed on the server (${e.message}). Nothing was sent. If no Nebius API key is set yet, model steps can't run.`, "err");
      else toast(`That step failed: ${e.message}`, "err");
    } finally {
      clearInterval(timer); clearInterval(poll);
      localJob = null;
      $("#runbar").hidden = true;
      await refresh();
      setBusy(!!(S && S.busy), !!(S && S.busy));
    }
  }
  for (const b of jobButtons()) b.addEventListener("click", () => runJob(b.dataset.job));

  // demo reset
  $("#demo-reset").addEventListener("click", async () => {
    closeMenu(false);
    if (!confirm("Reset the demo? This puts back the seeded inbox and ledger and clears what Kept did.")) return;
    try {
      await api("POST", "/api/demo/reset");
      Object.keys(sigs).forEach((k) => delete sigs[k]);
      $("#ask-out").replaceChildren();
      $("#pre-out").replaceChildren();
      toast("Demo data reset.", "good");
      refresh();
    } catch (e) {
      toast(`Couldn't reset: ${e.message}`, "err");
    }
  });

  // ------------------------------------------------------------------ menu
  const toggle = $("#jobs-toggle");
  const menu = $("#jobs-menu");
  const items = () => [...menu.querySelectorAll("[role=menuitem]")].filter((b) => !b.hidden && !b.disabled);
  function openMenu() {
    menu.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    const first = items()[0];
    if (first) first.focus();
  }
  function closeMenu(focusToggle = true) {
    if (menu.hidden) return;
    menu.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    if (focusToggle) toggle.focus();
  }
  toggle.addEventListener("click", () => (menu.hidden ? openMenu() : closeMenu()));
  toggle.addEventListener("keydown", (e) => { if (e.key === "ArrowDown") { e.preventDefault(); openMenu(); } });
  menu.addEventListener("keydown", (e) => {
    const list = items();
    const i = list.indexOf(document.activeElement);
    if (e.key === "Escape") { e.preventDefault(); closeMenu(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); list[(i + 1) % list.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); list[(i - 1 + list.length) % list.length]?.focus(); }
    else if (e.key === "Home") { e.preventDefault(); list[0]?.focus(); }
    else if (e.key === "End") { e.preventDefault(); list[list.length - 1]?.focus(); }
    else if (e.key === "Tab") closeMenu(false);
  });
  document.addEventListener("click", (e) => { if (!menu.hidden && !menu.contains(e.target) && !toggle.contains(e.target)) closeMenu(false); });

  // ------------------------------------------------------------------ start
  initFolds();
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  let rz = null;
  window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { if (S) render(S); }, 200); });
  // relative times ("5 min ago") drift; re-render time-dependent sections each minute
  setInterval(() => { for (const k of ["ledger", "held", "brief", "rescue", "scope", "growth"]) delete sigs[k]; if (S) render(S); }, 60000);
})();
