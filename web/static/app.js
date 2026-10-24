/* Kept dashboard. Vanilla JS, no build step.
   Every piece of data goes into the DOM through textContent / attributes, never innerHTML. */
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

  const ICONS = {
    check: ["M5 12.5l4.5 4.5L19 7.5"],
    shield: ["M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z", "M9.5 12h5"],
    mail: ["M3 6h18v12H3z", "M3 7l9 6 9-6"],
    clock: ["M12 7v5l3 2", "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"],
    rule: ["M4 6h16M4 12h10M4 18h6"],
    link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
  };
  function icon(name, cls = "ico ico-sm") {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("class", cls);
    svg.setAttribute("aria-hidden", "true");
    for (const d of ICONS[name] || []) {
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", d);
      svg.append(p);
    }
    return svg;
  }

  const chip = (text, cls = "", title) => h("span", { class: `chip ${cls}`.trim(), title }, text);

  function localISO(d = new Date()) {
    const z = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())}`;
  }
  function dayDiff(iso) {
    // whole days from today (local) to iso date; negative = in the past
    const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
    if (!y || !m || !d) return null;
    const a = new Date(y, m - 1, d);
    const t = new Date(); t.setHours(0, 0, 0, 0);
    return Math.round((a - t) / 86400000);
  }
  function fmtDay(iso) {
    const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number);
    if (!y) return String(iso);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
  }
  function parseTs(ts) {
    const d = new Date(ts);
    return isNaN(d) ? null : d;
  }
  function ago(ts) {
    const d = parseTs(ts);
    if (!d) return "";
    const s = Math.round((Date.now() - d) / 1000);
    if (s < 45) return "just now";
    if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`;
    const days = Math.round(s / 86400);
    return days === 1 ? "yesterday" : `${days} days ago`;
  }
  function clock(ts) {
    const d = parseTs(ts);
    if (!d) return "";
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  function money(usd) {
    const n = Number(usd) || 0;
    if (n === 0) return "$0.00";
    if (n < 0.0001) return "$" + n.toPrecision(2);
    if (n < 0.01) return "$" + n.toFixed(4);
    return "$" + n.toFixed(2);
  }
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;
  const personName = (from) => String(from || "").split("<")[0].trim().replace(/^"|"$/g, "") || String(from || "");
  const shortModel = (m) => String(m || "").split("/").pop();
  const safeUrl = (u) => { try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
  const tierName = (t) => ({ nano: "Nano", super: "Super", ultra: "Ultra" }[t] || t || "?");

  // ------------------------------------------------------------------ API
  class ApiError extends Error {
    constructor(msg, status) { super(msg); this.status = status; }
  }
  async function api(method, path, body) {
    let res;
    try {
      res = await fetch(path, {
        method,
        headers: body !== undefined ? { "Content-Type": "application/json" } : {},
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError("Can't reach Kept's server. Is it running?", 0);
    }
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

  // ------------------------------------------------------------------ state
  let S = null;
  const sigs = {};
  let localJob = null;
  let refreshing = false;
  let offline = false;
  let lastPending = null;

  function changed(key, value) {
    const s = JSON.stringify(value);
    if (sigs[key] === s) return false;
    sigs[key] = s;
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

  function render(st) {
    renderTop(st);
    if (changed("principles", [st.open, st.pending.length, st.abstained.length, st.calls.map((c) => c.ts)])) renderPrinciples(st);
    if (changed("approvals", [st.pending, st.decided, st.open.map((r) => [r.id, r.text])])) renderApprovals(st);
    if (changed("brief", [st.brief, st.open.map((r) => [r.id, r.due]), st.pending.map((a) => a.id), localISO()])) renderBrief(st);
    if (changed("ledger", [st.open, st.closed, Object.keys(inboxIndex()), localISO()])) renderLedger(st);
    if (changed("held", st.abstained)) renderHeld(st);
    if (changed("inbox", [st.inbox, st.labels, st.open.map((r) => r.source)])) renderInbox(st);
    if (changed("news", st.watch)) renderNews(st);
    if (changed("models", [st.tiers, st.routes, st.calls, st.spend_today, st.budget])) renderModels(st);
    if (changed("activity", st.activity)) renderActivity(st);

    if (lastPending !== null && st.pending.length > lastPending) {
      announce(`${plural(st.pending.length - lastPending, "new item")} waiting for your Yes.`);
    }
    lastPending = st.pending.length;
  }

  function renderTop(st) {
    $("#owner-line").textContent = `${st.owner || "Owner"}'s operator`;
    $("#demo-badge").hidden = !st.demo;
    $("#demo-reset").hidden = !st.demo;
    $("#reset-sep").hidden = !st.demo;
    const pct = st.budget > 0 ? Math.min(100, (st.spend_today / st.budget) * 100) : 0;
    $("#spend-num").textContent = money(st.spend_today);
    $("#spend-of").textContent = `of ${money(st.budget)} budget`;
    const bar = $("#spend-bar");
    bar.setAttribute("aria-valuenow", String(Math.round(pct)));
    bar.setAttribute("aria-valuetext", `${money(st.spend_today)} of ${money(st.budget)} daily budget`);
    bar.classList.toggle("warn", pct >= 70 && pct < 100);
    bar.classList.toggle("full", pct >= 100);
    $("#spend-fill").style.width = `${Math.max(pct, st.spend_today > 0 ? 2 : 0)}%`;
    setBusy(!!localJob || !!st.busy, st.busy && !localJob);
  }

  function renderPrinciples(st) {
    const over = st.open.filter((r) => r.due && dayDiff(r.due) < 0).length;
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
  }

  // --- approvals
  function renderApprovals(st) {
    const list = $("#approvals-list");
    const card = $("#approvals");
    card.classList.toggle("has-items", st.pending.length > 0);
    $("#approvals-count").textContent = st.pending.length ? plural(st.pending.length, "waiting", "waiting") : "";
    const ledger = openIndex();
    if (!st.pending.length) {
      fill(list, h("p", { class: "empty" },
        h("strong", null, "Nothing waiting. "),
        "When a promise comes due, Kept drafts the email, checks it, and puts it here for your Yes or No. Nothing is sent before you decide."));
    } else {
      fill(list, st.pending.map((a) => approvalCard(a, ledger)));
    }

    const dw = $("#decided-wrap");
    dw.hidden = !st.decided.length;
    $("#decided-count").textContent = st.decided.length ? `(${st.decided.length})` : "";
    fill($("#decided-list"), st.decided.map((a) => {
      const map = { done: ["Sent", "chip-ok"], approved: ["Approved", "chip-ok"], rejected: ["Not sent", "chip-no"], failed: ["Failed", "chip-over"] };
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
    const row = a.ledger_id ? ledger[a.ledger_id] : null;
    const yes = h("button", { class: "btn btn-yes", type: "button" }, icon("check", "ico"), "Yes, send it");
    const no = h("button", { class: "btn btn-no", type: "button" }, "No");
    const label = a.summary || "this action";
    yes.setAttribute("aria-label", `Yes, send: ${label}`);
    no.setAttribute("aria-label", `No, don't send: ${label}`);
    const status = h("span", { class: "hint", "aria-live": "polite" }, a.kind === "send_email" ? "Yes sends this email. No discards it." : "");
    const go = async (verdict) => {
      yes.disabled = no.disabled = true;
      status.textContent = verdict === "yes" ? "Sending…" : "Discarding…";
      try {
        const r = await api("POST", `/api/approvals/${encodeURIComponent(a.id)}/${verdict}`);
        if (verdict === "no") toast("Okay, not sent. The promise stays open in your ledger.", "good");
        else if (r && r.status === "failed") toast(`You said Yes, but sending failed: ${r.result}`, "err");
        else toast(`Done. ${r && r.result ? r.result : "Sent."}`, "good");
        announce(verdict === "yes" ? "Approved." : "Rejected.");
      } catch (e) {
        toast(`Couldn't record your answer: ${e.message}`, "err");
        yes.disabled = no.disabled = false;
        status.textContent = "";
      }
      refresh();
    };
    yes.addEventListener("click", () => go("yes"));
    no.addEventListener("click", () => go("no"));

    return h("article", { class: "approval", "aria-label": `Waiting for your Yes: ${label}` },
      h("div", { class: "approval-head" },
        h("h3", { class: "approval-title" }, label),
        h("span", { class: "meta" }, chip(a.kind === "send_email" ? "Email" : a.kind, "chip-ask"), " ", ago(a.created))),
      a.kind === "send_email" || args.to ? h("div", { class: "envelope" },
        h("dl", null,
          h("dt", null, "To"), h("dd", null, args.to || "?"),
          h("dt", null, "Subject"), h("dd", null, args.subject || "")),
        h("div", { class: "body" }, args.body || "")) : null,
      h("p", { class: "why" }, h("strong", null, "Why: "), a.why || ""),
      row ? h("p", { class: "why muted" }, "For the promise: ", h("a", { href: "#promises" }, row.text)) : null,
      a.checks && a.checks.length ? h("div", null,
        h("p", { class: "sr-only" }, "Checks passed:"),
        h("ul", { class: "checks", "aria-label": "Checks this draft passed" },
          a.checks.map((c) => h("li", null, icon("check"), c)))) : null,
      h("div", { class: "decide" }, yes, no, status));
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
        " and Kept will sort the inbox, draft follow-ups, check the news, and write today's brief. Overdue promises always come first."));
      return;
    }
    const stale = b.date && b.date !== localISO();
    fill(meta, stale ? chip(`from ${fmtDay(b.date)}`, "chip-soon") : null, " ",
      b.model ? `Written by ${shortModel(b.model)}` : "", b.ts ? ` · ${clock(b.ts)}` : "");
    const ledger = openIndex();
    const pending = new Set(st.pending.map((a) => a.id));
    const lines = (b.lines || []).filter((l) => l && typeof l === "object");
    const sorted = [...lines].sort((x, y) => isOver(y) - isOver(x));
    function isOver(l) {
      const r = l.ref && ledger[l.ref];
      return (r && r.due && dayDiff(r.due) < 0) || /^overdue/i.test(l.text || "") ? 1 : 0;
    }
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

  // --- ledger
  function dueChip(due) {
    if (!due) return chip("No due date", "chip-outline");
    const d = dayDiff(due);
    if (d === null) return chip(`Due ${due}`, "chip-due");
    if (d < 0) return chip(`Overdue ${-d}d`, "chip-over", `Was due ${fmtDay(due)}`);
    if (d === 0) return chip("Due today", "chip-soon");
    if (d === 1) return chip("Due tomorrow", "chip-soon");
    return chip(`Due ${fmtDay(due)}`, "chip-due");
  }

  function renderLedger(st) {
    const list = $("#ledger-list");
    const mails = inboxIndex();
    const over = st.open.filter((r) => r.due && dayDiff(r.due) < 0).length;
    $("#promises-count").textContent = `${st.open.length} open${over ? ` · ${over} overdue` : ""}`;
    if (!st.open.length) {
      fill(list, h("li", { class: "empty" },
        "No open promises. Kept adds them when it finds one in your mail (", h("strong", null, "One step → Sort the inbox"),
        "), or add one yourself below."));
    } else {
      fill(list, st.open.map((r) => {
        const isOver = r.due && dayDiff(r.due) < 0;
        const src = r.source && mails[r.source];
        const btn = h("button", { class: "btn btn-quiet btn-small", type: "button", "aria-label": `Close promise: ${r.text}` }, "Close…");
        btn.addEventListener("click", () => openClose(r, btn));
        return h("li", { class: isOver ? "is-over" : "" },
          h("span", { class: "l-text" }, r.text),
          h("div", { class: "l-meta" },
            dueChip(r.due),
            r.who ? h("span", null, "to ", personName(r.who)) : null,
            src ? h("a", { href: `#mail-${cssId(src.id)}`, onclick: () => openMail(src.id) }, icon("mail"), " ", src.subject)
              : r.origin === "owner" ? h("span", null, "added by you") : r.origin ? h("span", null, `from ${r.origin}`) : null),
          h("div", { class: "l-actions" }, btn),
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

  const cssId = (s) => String(s).replace(/[^a-zA-Z0-9_-]/g, "_");
  function openMail(id) {
    const d = document.getElementById(`mail-${cssId(id)}`);
    if (d) { const det = d.querySelector("details"); if (det) det.open = true; }
  }

  // close dialog
  const dlg = $("#close-dialog");
  let closing = null;
  function openClose(row, trigger) {
    closing = { row, trigger };
    $("#close-text").textContent = row.text + (row.who ? ` (to ${personName(row.who)})` : "");
    $("#close-form").reset();
    $("#close-error").textContent = "";
    $("#close-submit").disabled = false;
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    $("#close-note").focus();
  }
  function endClose() {
    if (dlg.open) dlg.close();
  }
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
    const btn = f.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      await api("POST", "/api/ledger", { text, who: String(fd.get("who") || "").trim(), due: fd.get("due") || null });
      f.reset();
      toast(`Added to your promises: ${text}`, "good");
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
  function plainProblem(p) {
    const s = String(p);
    let m;
    if ((m = s.match(/^claim (\d+): the quoted words are not in source '(.+)'$/))) return `The quoted words aren't in ${m[2]}, so the claim can't be trusted.`;
    if ((m = s.match(/^claim (\d+) cites '(.+)', which Kept never fetched$/))) return `It cited "${m[2]}", a source Kept never read.`;
    if (/has no usable quote/.test(s)) return "It gave no quote to back the claim.";
    if ((m = s.match(/^missing field '(.+)'$/))) return `The answer was missing "${m[1]}".`;
    if (/^model reply unusable/.test(s)) {
      const why = s.replace(/^model reply unusable:\s*/, "");
      if (/missing credentials|api[_ ]key/i.test(why)) return "No usable model reply: the model API key isn't set up yet, so Kept didn't guess.";
      if (/no JSON/i.test(why)) return "The model's reply had no structured answer in it, so Kept didn't use it.";
      return `No usable model reply (${why.slice(0, 160)}), so Kept didn't guess.`;
    }
    if ((m = s.match(/^search failed: (.*)$/))) return `Web search failed (${m[1].slice(0, 120)}).`;
    return s.charAt(0).toUpperCase() + s.slice(1) + (/[.!?]$/.test(s) ? "" : ".");
  }

  // --- inbox
  function renderInbox(st) {
    const list = $("#inbox-list");
    const labels = st.labels || {};
    const sources = new Set(st.open.map((r) => r.source).filter(Boolean));
    const mails = [...st.inbox].reverse();
    const sorted = mails.filter((m) => labels[m.id]).length;
    $("#inbox-count").textContent = mails.length ? `${mails.length} emails · ${sorted} sorted` : "";
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

  // --- ask
  $("#ask-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const q = $("#ask-q").value.trim();
    if (!q) { $("#ask-q").focus(); return; }
    const out = $("#ask-out");
    const btn = $("#ask-btn");
    btn.disabled = true;
    fill(out, h("p", { class: "answer" }, h("span", { class: "muted" }, "Reading your ledger, journal and notes… (Nemotron Super)")));
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
        h("span", { class: "tier-why" }, tr.why ? tr.why.charAt(0).toUpperCase() + tr.why.slice(1) : ""),
        h("span", { class: "tier-foot" },
          tasksFor(k).length ? h("span", null, `Used for: ${tasksFor(k).join(", ")}`) : null,
          h("span", null, `$${Number(tr.in).toFixed(2)} in / $${Number(tr.out).toFixed(2)} out per 1M tokens`)));
    }));

    const pct = st.budget > 0 ? Math.min(100, (st.spend_today / st.budget) * 100) : 0;
    const total = today.reduce((s, c) => s + (Number(c.usd) || 0), 0) || 0;
    const split = h("span", { class: "split", style: `width:${Math.max(pct, st.spend_today > 0 ? 2 : 0)}%` },
      ["nano", "super", "ultra"].map((k) => {
        const share = total > 0 ? ((byTier[k]?.usd || 0) / total) * 100 : 0;
        return share > 0 ? h("span", { style: `width:${share}%;background:var(--${k})`, title: `${tierName(k)}: ${money(byTier[k].usd)}` }) : null;
      }));
    fill($("#budget"),
      h("div", null, h("strong", null, money(st.spend_today)), ` of ${money(st.budget)} daily budget · ${plural(today.length, "call")} today`,
        pct >= 100 ? h("span", null, " · ", chip("Budget reached: model calls paused until tomorrow", "chip-over")) : null),
      h("div", { class: "bar", role: "img", "aria-label": `Spend by model size: ${["nano", "super", "ultra"].map((k) => `${tierName(k)} ${money(byTier[k]?.usd || 0)}`).join(", ")}` }, split));

    const body = $("#calls-body");
    const empty = $("#calls-empty");
    const wrap = $("#calls-wrap");
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
      case "ledger_add": return `New promise: ${a.text}${a.who ? ` (to ${personName(a.who)})` : ""}`;
      case "ledger_close": return `Closed a promise as ${String(a.resolution).replace("_", " ")}: ${a.note}`;
      case "approval_requested": return `Asked for your Yes: ${a.summary}`;
      case "approval_decided": return `You said ${a.yes ? "Yes" : "No"} (${a.by || "owner"})`;
      case "action": return `${a.action === "send_email" ? "Email" : a.action} ${a.status}: ${a.result || ""}`;
      case "abstained": return `Held back (${(JOB_LABEL[a.job] || a.job).toLowerCase()}): ${(a.problems || []).map(plainProblem).join(" ")}`;
      case "job_failed": return `Step "${a.job}" failed: ${a.error}`;
      case "llm_refused": return `Model call refused: ${a.reason}`;
      case "gate_blocked": return `Gate blocked "${a.action}" without your Yes`;
      default: return a.kind.replace(/_/g, " ");
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
    day: "Running the morning loop: sort mail, draft follow-ups, check news, weigh the week, write the brief",
    triage: "Sorting the inbox with Nemotron Nano", follow_ups: "Drafting follow-ups with Nemotron Super",
    watch: "Checking the news and verifying every quote", overload: "Weighing the week with Nemotron Ultra",
    brief: "Writing the morning brief with Nemotron Super",
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
        default: return null;
      }
    };
    let parts;
    if (job === "day" && r && typeof r === "object") parts = Object.entries(r).map(([k, v]) => one(k, v)).filter(Boolean);
    else parts = [one(job, r)].filter(Boolean);
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
        const msg = text ? text.charAt(0).toUpperCase() + text.slice(1) + "." : "Done.";
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
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 5000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
  // relative times ("5 min ago") drift; re-render time-dependent sections each minute
  setInterval(() => { delete sigs.ledger; delete sigs.held; delete sigs.brief; if (S) render(S); }, 60000);
})();
