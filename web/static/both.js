/* Kept, both sides: the client writes on the left, Alex (with Kept) answers on the right.
   Vanilla JS, no build step. Data goes into the DOM through textContent only. */
(() => {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "hidden") el.hidden = !!v;
      else el.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return el;
  }
  const fill = (el, ...kids) => { el.replaceChildren(); for (const c of kids.flat(Infinity)) if (c) el.append(c instanceof Node ? c : document.createTextNode(String(c))); return el; };
  const chip = (t, cls = "") => h("span", { class: `chip ${cls}`.trim() }, t);
  const usd = (n) => "$" + Math.round(Number(n) || 0).toLocaleString("en-US");
  const money = (n) => (Number(n) || 0) < 0.01 ? "$" + (Number(n) || 0).toFixed(4) : "$" + (Number(n) || 0).toFixed(2);
  const isoDate = (iso) => { const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
  const fmtDay = (iso) => isoDate(iso).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
  function ago(ts) {
    const s = Math.round((Date.now() - new Date(ts)) / 1000);
    if (!isFinite(s)) return "";
    if (s < 45) return "just now"; if (s < 3600) return `${Math.round(s / 60)} min ago`;
    if (s < 86400) return `${Math.round(s / 3600)} h ago`; return `${Math.round(s / 86400)} days ago`;
  }
  function stamp(word, kind) {
    const el = h("span", { class: `stamp stamp-${kind} stamp-sm is-fresh`, "aria-hidden": "true" }, word);
    el.style.setProperty("--rot", `${(Math.random() * 10 - 6).toFixed(1)}deg`);
    return el;
  }
  const clock = (t) => { const [hh, mm] = String(t || "").split(":").map(Number); return isFinite(hh) ? `${hh > 12 ? hh - 12 : hh}:${String(mm || 0).padStart(2, "0")} ${hh >= 12 ? "pm" : "am"}` : ""; };
  function toast(msg, kind = "info") {
    const el = h("div", { class: `toast ${kind === "err" ? "err" : kind === "good" ? "good" : ""}`, role: kind === "err" ? "alert" : "status" }, h("p", null, msg));
    $("#toasts").append(el); setTimeout(() => el.remove(), kind === "err" ? 12000 : 6000);
  }
  async function api(method, path, body) {
    let res;
    try { res = await fetch(path, body === undefined ? { method } : { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); }
    catch { throw new Error("Can't reach Kept's server. It may be waking up; try again in a moment."); }
    let data = null; try { data = await res.json(); } catch { /* not json */ }
    if (!res.ok) throw new Error((data && data.detail) ? String(data.detail) : `HTTP ${res.status}`);
    return data;
  }

  // ------------------------------------------------------------------ who's writing
  let PEOPLE = [], PHOTO = "";
  const EXAMPLES = [
    { label: "Old kitchen, with a photo", who: "new", name: "Jo Rivera", email: "jo@riverahome.example", photo: "old-kitchen.jpg",
      subject: "Our old kitchen", body: "Hi Alex, we just bought a house and the kitchen is from the 90s (photo attached). We'd love it to look modern. What would you suggest, and roughly what would it cost?\n\nThanks, Jo" },
    { label: "A broken hinge, with a photo", who: "new", name: "Sam Lee", email: "sam.lee@example.com", photo: "cabinet-repair.jpg",
      subject: "Cabinet door under the sink", body: "Hello, the cabinet door under our sink came off its hinge and the drawer below is loose. Could you fix it? We're in Sellwood. Photo attached.\n\nSam" },
    { label: "Maria wants extra work", who: "maria", subject: "Two more things",
      body: "Hi Alex! While you're here, could you also tile the backsplash behind the stove? And the new pantry door doesn't close all the way.\n\nMaria" },
    { label: "Priya promises to pay", who: "priya", subject: "Re: invoice #118",
      body: "Hi Alex, so sorry again. Our office manager is back, we will pay invoice #118 next Wednesday.\n\nPriya" },
  ];
  const whoValue = (p) => (p.key === "new" ? `new:${p.email}` : p.key);
  function current() {
    const v = $("#who").value;
    if (v === "new") return { who: "new", name: $("#name").value.trim(), email: $("#email").value.trim() };
    if (v.startsWith("new:")) { const p = PEOPLE.find((x) => whoValue(x) === v); return { who: "new", name: p.name, email: p.email }; }
    const p = PEOPLE.find((x) => x.key === v);
    return { who: v, name: p ? p.name : "", email: p ? p.email : "" };
  }
  function whoChanged() {
    const v = $("#who").value;
    $("#newbox").hidden = v !== "new";
    const p = PEOPLE.find((x) => whoValue(x) === v);
    $("#who-about").textContent = v === "new" ? "You're new to Alex. Name a real business and city and Kept looks it up on the web (Tavily) first."
      : p ? `Playing ${p.name}: ${p.about}.` : "";
    loadClientThread();
  }
  async function loadPeople(keep) {
    PEOPLE = await api("GET", "/api/people");
    const sel = $("#who");
    fill(sel, h("option", { value: "new" }, "Me, a new client"),
      h("optgroup", { label: "Or play one of Alex's clients" }, PEOPLE.map((p) => h("option", { value: whoValue(p) }, `${p.name}${p.key === "new" ? " (new)" : ""}`))));
    if (keep && [...sel.options].some((o) => o.value === keep)) sel.value = keep;
    whoChanged();
  }
  $("#who").addEventListener("change", whoChanged);

  // ------------------------------------------------------------------ photo
  function setPhoto(url) {
    PHOTO = url || "";
    $("#thumb").hidden = !PHOTO; $("#clear").hidden = !PHOTO;
    if (PHOTO) $("#thumb").src = PHOTO; else { $("#thumb").removeAttribute("src"); $("#file").value = ""; }
  }
  const shrink = (src) => new Promise((ok, bad) => {
    const img = new Image();
    img.onload = () => { const k = Math.min(1, 1600 / Math.max(img.width, img.height)); const c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext("2d").drawImage(img, 0, 0, c.width, c.height); ok(c.toDataURL("image/jpeg", 0.85)); };
    img.onerror = bad; img.src = src;
  });
  $("#file").addEventListener("change", async () => {
    const f = $("#file").files[0]; if (!f) return;
    if (!/^image\/(jpeg|png|webp)$/.test(f.type)) { toast("Use a JPEG, PNG or WebP photo.", "err"); $("#file").value = ""; return; }
    const u = URL.createObjectURL(f); try { setPhoto(await shrink(u)); } catch { toast("Couldn't read that photo.", "err"); } finally { URL.revokeObjectURL(u); }
  });
  $("#clear").addEventListener("click", () => setPhoto(""));
  fill($("#ideas"), EXAMPLES.map((ex) => h("button", { type: "button", onclick: async () => {
    $("#who").value = ex.who; whoChanged();
    if (ex.who === "new") { $("#name").value = ex.name; $("#email").value = ex.email; }
    $("#subject").value = ex.subject; $("#body").value = ex.body;
    if (ex.photo) { try { setPhoto(await shrink(`/demo_media/${ex.photo}`)); } catch { setPhoto(""); } } else setPhoto("");
    $("#send").focus();
  } }, ex.label)));

  // ------------------------------------------------------------------ the client's view of the conversation
  async function loadClientThread() {
    const { email } = current();
    const list = $("#client-thread");
    if (!email) { fill(list, h("li", { class: "muted b-empty" }, "Nothing yet. Send Alex a message.")); return; }
    let t = [];
    try { t = await api("GET", `/api/thread?email=${encodeURIComponent(email)}`); } catch { return; }
    const items = [];
    for (const m of t) {
      if (m.dir === "in") items.push(h("li", { class: "t-in" }, h("div", { class: "t-meta" }, `You · ${ago(m.ts)}${m.subject ? " · " + m.subject : ""}`), h("div", { class: "t-body" }, m.body)));
      else if (m.dir === "out") items.push(h("li", { class: "t-out" }, h("div", { class: "t-meta" }, `Alex · ${ago(m.ts)}`), h("div", { class: "t-body" }, m.body)));
    }
    if (t.some((m) => m.dir === "draft")) items.push(h("li", { class: "t-pending" }, "Alex hasn't answered yet. Kept has drafted a reply; it appears here once Alex says Yes (on the right)."));
    fill(list, items.length ? items : h("li", { class: "muted b-empty" }, "Nothing yet. Send Alex a message."));
  }

  // ------------------------------------------------------------------ Alex's side
  const JOB = { small_repair: "Small repair", fronts: "New cabinet fronts", countertop: "New countertop", backsplash: "New backsplash",
    full_kitchen: "Full kitchen", commercial: "Cafe or office kitchen", question: "A question", other: "Something else" };
  function alexView(r) {
    const from = (r.mail && r.mail.from) || "";
    const rows = [];
    const lab = r.label || {};
    rows.push(h("li", null, h("span", { class: "w-step" }, "Sorted (Nemotron Nano)"), h("span", null, chip(lab.kind || "?", "chip-nano"), " ", lab.one_line || "")));
    const ph = r.photo;
    if (ph && ph.seen) rows.push(h("li", null, h("span", { class: "w-step" }, "The photo, as Nemotron Super VL sees it"),
      ph.path ? h("img", { class: "w-seen-img", src: `/media/${ph.path.replace(/^media\//, "")}`, alt: "The client's photo" }) : null,
      h("span", null, ph.seen.shows || ""),
      (ph.seen.damage || []).length ? h("div", { class: "foot muted" }, "Damage: " + ph.seen.damage.join("; ")) : null,
      ph.seen.style ? h("div", { class: "foot muted" }, "Style to match: " + ph.seen.style) : null));
    const pl = r.plan;
    if (pl && pl.job) {
      let next = null;
      if (pl.booked_label) next = h("span", null, chip("booked", "chip-ok"), ` Measuring visit ${pl.booked_label}, now in Alex's calendar.`);
      else if (pl.payment_plan) next = h("span", null, chip("payment plan", "chip-ask"), ` ${pl.payment_plan.pct}% up front (${usd(pl.payment_plan.deposit)}), then ${pl.payment_plan.months} × ${usd(pl.payment_plan.monthly)}, on the ${usd(pl.payment_plan.total)} estimate.`);
      else if (pl.job === "small_repair") next = h("span", null, `Priced now: ${pl.hours} h at Alex's rate = ${usd(pl.price)} plus hardware.`);
      else if ((pl.slots || []).length) next = h("span", null, "Free measuring times from Alex's calendar: ", pl.slots.map((s) => s.label).join(" · "));
      const est = pl.estimate && !pl.payment_plan ? pl.estimate : null;
      rows.push(h("li", null, h("span", { class: "w-step" }, "The job and the next step (Super names it, code does the maths)"),
        h("span", null, chip(JOB[pl.job] || pl.job, "chip-super"), " ", pl.what || ""), next ? h("div", null, next) : null,
        est ? h("div", { class: "estimate" }, h("strong", null, `Preliminary ${usd(est.low)} – ${usd(est.high)}`),
          h("span", { class: "muted" }, ` · sizes from ${est.sizes_from}`),
          h("ul", { class: "plain" }, est.lines.map((l) => h("li", null, l.unit ? `${l.what}: ${l.qty} ${l.unit} × ${usd(l.price)} = ${usd(l.total)}` : `${l.what}: ${usd(l.total)}`)))) : null));
    }
    const sc = (r.scope && r.scope.requests) || [];
    if (sc.length) rows.push(h("li", null, h("span", { class: "w-step" }, "Checked against the signed agreement (Nemotron Ultra, twice)"),
      h("ul", { class: "plain" }, sc.map((x) => h("li", null, chip(x.verdict.replace(/_/g, " "), x.verdict === "out_of_scope" ? "chip-ask" : x.verdict === "in_scope" ? "chip-ok" : "chip-outline"), " ", x.request,
        x.price ? ` · ${usd(x.price)} at Alex's rate` : "")))));
    const web = r.research;
    if (web && (web.business || web.domain)) {
      const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };
      rows.push(h("li", null, h("span", { class: "w-step" }, "Who is writing? (Tavily Search + Extract, checked by code)"),
        h("div", { class: "foot muted" }, (web.searched || []).join(" · "),
          web.pages_seen !== undefined ? ` · ${web.pages_seen} pages found, ${(web.pages_used || []).length} name the business` : ""),
        (web.facts || []).length ? h("ul", { class: "plain" }, web.facts.map((f) => h("li", null, chip("kept", "chip-ok"), " ", f.text, " ",
          h("a", { href: f.url, target: "_blank", rel: "noopener" }, host(f.url)), h("div", { class: "foot muted" }, `"${f.quote}"`))))
          : h("span", { class: "muted" }, web.note || "Nothing checked out, so Kept isn't using anything from the web."),
        (web.dropped || []).length ? h("ul", { class: "plain" }, web.dropped.map((d) => h("li", { class: "muted" }, chip("dropped", "chip-held"), " ", d.text, h("div", { class: "foot muted" }, d.why)))) : null,
        r.plan && r.plan.verified_business ? h("div", null, chip("verified business", "chip-super"), " so Kept treats it as a commercial job: priced after a visit.") : null));
    }
    const ps = r.promises || [];
    if (ps.length) rows.push(h("li", null, h("span", { class: "w-step" }, "Promises noted in Alex's ledger"),
      h("ul", { class: "plain" }, ps.map((p) => h("li", null, chip(p.direction === "owed_to_me" ? "they owe Alex" : "Alex owes", p.direction === "owed_to_me" ? "chip-super" : "chip-due"), " ", p.text)))));
    const rp = r.reply && r.reply.approval;
    const g = r.growth || {};
    if (g.asks && g.asks.length) rows.push(h("li", null, h("span", { class: "w-step" }, "A delighted client"),
      "Kept drafted a thank-you with Alex's review link and a before/after post; they wait in ", h("a", { href: "/dashboard#approvals" }, "Alex's dashboard"), "."));
    if (rp) rows.push(h("li", null, h("span", { class: "w-step" }, "The reply Kept drafted, waiting for Alex's Yes"),
      h("div", { class: "w-draft" }, rp.args.body), decide(rp)));
    else if (!(g.asks && g.asks.length)) rows.push(h("li", null, h("span", { class: "w-step" }, "No reply drafted"),
      h("span", { class: "muted" }, (r.held_back || []).length ? "A check failed, so Kept held back rather than guess: " + r.held_back.map((x) => x.problems.join("; ")).join(" / ") : "Nothing to answer here.")));
    const calls = r.calls || [];
    return h("div", { class: "b-card" },
      h("p", { class: "b-arrive" }, `New email · ${from.split("<")[0].trim()} · ${(r.mail && r.mail.subject) || ""}`),
      h("ol", { class: "w-steps" }, rows),
      h("p", { class: "foot muted" }, `${calls.length} model calls · ${r.seconds}s · ${money(r.usd)}`));
  }
  function decide(a) {
    const status = h("span", { class: "muted" }, "Nothing is sent until Alex decides.");
    const go = async (verdict) => {
      yes.disabled = no.disabled = true;
      try {
        await api("POST", `/api/approvals/${encodeURIComponent(a.id)}/${verdict}`);
        fill(status, verdict === "yes" ? stamp("APPROVED", "approved") : stamp("DECLINED", "declined"),
          verdict === "yes" ? "  Sent. Look left: the client has Alex's reply. Write back to keep going." : "  Not sent.");
        loadClientThread(); loadCalendar();
        if (verdict === "yes" && window.innerWidth < 960) setTimeout(() => $("#client-thread").scrollIntoView({ behavior: "smooth", block: "center" }), 600);
      } catch (e) { toast(e.message, "err"); yes.disabled = no.disabled = false; }
    };
    const no = h("button", { class: "btn btn-quiet btn-small", type: "button", onclick: () => go("no") }, "No");
    const yes = h("button", { class: "btn btn-primary btn-small", type: "button", onclick: () => go("yes") }, "Yes, send");
    return h("div", { class: "decide" }, no, yes, status);
  }

  async function loadCalendar() {
    try {
      const st = await api("GET", "/api/state");
      const ev = (st.calendar || []).filter((e) => e.kind === "visit");
      fill($("#cal"), ev.length ? ev.map((e) => h("li", { class: "c-visit" }, h("span", { class: "c-day" }, `${fmtDay(e.date)} · ${clock(e.time)}`),
        h("span", { class: "c-what" }, `Measuring visit: ${e.who}`))) : h("li", null, h("span", { class: "muted" }, "No visits booked.")));
    } catch { /* not critical */ }
  }

  // ------------------------------------------------------------------ send
  $("#f").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = $("#body").value.trim();
    if (!body) { $("#body").focus(); return; }
    const who = current();
    if (who.who === "new" && !who.email) { toast("Give yourself an email address (nothing is sent).", "err"); $("#email").focus(); return; }
    const btn = $("#send"); btn.disabled = true;
    const t0 = Date.now();
    const secs = h("span", { class: "muted" }, " 0s");
    const timer = setInterval(() => { secs.textContent = ` ${Math.round((Date.now() - t0) / 1000)}s`; }, 1000);
    if (window.innerWidth < 960) setTimeout(() => $("#alex-out").scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    fill($("#alex-out"), h("div", { class: "b-card" }, h("p", { class: "b-arrive" }, "New email arriving…"),
      h("p", { class: "loading" }, h("span", { class: "spinner", "aria-hidden": "true" }),
        PHOTO ? "Kept is reading the email and looking at the photo, working out the job and drafting Alex's reply…" : "Kept is reading the email and drafting Alex's reply…", secs)));
    // the client's side shows their message straight away
    $("#client-thread").append(h("li", { class: "t-in" }, h("div", { class: "t-meta" }, "You · just now"), h("div", { class: "t-body" }, body)));
    try {
      const r = await api("POST", "/api/demo/mail", { who: who.who, name: who.name, email: who.email, subject: $("#subject").value.trim(), body, image: PHOTO });
      fill($("#alex-out"), alexView(r));
      // on a phone the two sides are stacked: take the visitor to Alex's side
      if (window.innerWidth < 960) $("#alex-out").scrollIntoView({ behavior: "smooth", block: "start" });
      $("#body").value = ""; setPhoto("");
      const addr = (String(r.mail.from).match(/<([^>]+)>/) || [])[1];
      await loadPeople(who.who === "new" ? `new:${addr}` : who.who);
      loadCalendar();
    } catch (e) {
      fill($("#alex-out"), h("div", { class: "b-card" }, chip("Not handled", "chip-held"), h("p", null, e.message)));
      loadClientThread();
    } finally { clearInterval(timer); btn.disabled = false; }
  });

  loadPeople().catch((e) => toast(e.message, "err"));
  loadCalendar();
})();
