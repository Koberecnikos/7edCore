"use strict";
/* 7edCore web UI - plain JS, no build step. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtBytes = (b) => { if (b == null) return "–"; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; b = Number(b); while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; } return b.toFixed(i ? 1 : 0) + " " + u[i]; };
const fmtTime = (ts) => ts ? new Date(ts * 1000).toLocaleString(LANG === "cs" ? "cs-CZ" : "en-GB") : "–";
const fmtDur = (s) => { s = Math.max(0, Math.floor(s)); const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return (d ? d + "d " : "") + (h ? h + "h " : "") + m + "m"; };
const h = (html) => { const tpl = document.createElement("template"); tpl.innerHTML = html.trim(); return tpl.content; };

let CUR = null, OV = { instances: [] }, S = { status: {}, stats: {}, settings: {} }, META = null, PRESETS = [];
let TAB = "overview", ES = null, OFFLINE = false, ME = { role: "viewer" };
const isAdmin = () => ME.role === "admin";
const sp = (p) => `/api/s/${encodeURIComponent(CUR)}${p}`;

// ------------------------------------------------------------------ API + connection state
class ApiError extends Error { constructor(msg, status, data) { super(msg); this.status = status; this.data = data; } }
async function api(method, url, body) {
  const opt = { method, credentials: "same-origin", headers: { "X-Requested-With": "7edcore" } };
  if (body instanceof FormData) opt.body = body;
  else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  let r;
  try { r = await fetch(url, opt); } catch { setOffline(true); throw new ApiError(t("err.network"), 0); }
  setOffline(false);
  if (r.status === 401 && !url.startsWith("/api/login")) { showGate(false); throw new ApiError("401", 401); }
  let data = {};
  try { data = await r.json(); } catch { /* empty */ }
  if (!r.ok) throw new ApiError(data.error || r.statusText, r.status, data);
  return data;
}
function setOffline(v) {
  if (v === OFFLINE) return;
  OFFLINE = v;
  $("#conn").hidden = !v;
  if (v) { const ping = async () => { try { await fetch("/api/session"); setOffline(false); reconnect(); } catch { setTimeout(ping, 3000); } }; setTimeout(ping, 3000); }
}
function reconnect() { if (CUR) { openEvents(); loadOverview(); } }
function toast(msg, err) {
  if (!msg) return;
  const el = document.createElement("div");
  el.className = "toast" + (err ? " err" : "");
  el.textContent = msg;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), err ? 8000 : 3500);
}
/* Run an action; network errors are shown by the banner, not as toasts. */
async function act(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg); return r; }
  catch (e) {
    if (e.status === 409 && e.data?.compat) return compatDialog(e.data.compat, e.message).then((go) => go ? act(() => fn(true), okMsg) : null);
    if (e.status !== 0 && e.status !== 401) toast(e.message, true);
    return null;
  }
}

// ------------------------------------------------------------------ dialogs
function dialog(title, body, okText = t("act.apply"), danger = false, cancelText = t("act.cancel")) {
  return new Promise((res) => {
    const d = $("#dlg");
    $("#dlgTitle").textContent = title;
    const b = $("#dlgBody"); b.innerHTML = ""; typeof body === "string" ? b.innerHTML = body : b.append(body);
    $("#dlgOk").textContent = okText; $("#dlgOk").className = danger ? "danger" : "primary";
    $("#dlgCancel").textContent = cancelText; $("#dlgCancel").hidden = !cancelText;
    let done = false;
    const fin = (v) => { if (done) return; done = true; d.close(); res(v); };
    $("#dlgForm").onsubmit = (e) => { e.preventDefault(); fin(true); };
    $("#dlgCancel").onclick = () => fin(false);
    d.onclose = () => fin(false);
    d.showModal();
    $("input:not([type=checkbox]),select", b)?.focus();
  });
}
const confirmDlg = (text, okText = t("act.yes"), danger = true) => dialog(t("confirm.title"), `<p>${esc(text)}</p>`, okText, danger);
async function promptDlg(title, label, value = "") {
  const ok = await dialog(title, `<div class="field"><label>${esc(label)}</label><input id="dlgIn" value="${esc(value)}"></div>`);
  return ok ? $("#dlgIn").value : null;
}
function compatText(c) { return t("compat." + c.level, { save: c.save_version || "?", game: c.game || "?" }); }
function compatDialog(c, msg) {
  return dialog(t("compat.title"), `<div class="alert ${c.level}">${esc(compatText(c))}</div><p class="muted small">${esc(c.save || "")}</p>`,
    t("compat.force"), true);
}

// ------------------------------------------------------------------ language picker
function initLangPickers() {
  $$(".lang-pick").forEach((s) => {
    s.innerHTML = Object.entries(LANGS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
    s.value = LANG;
    s.onchange = () => { setLang(s.value); $$(".lang-pick").forEach((x) => x.value = LANG); applyI18n(); rerender(); };
  });
}
function rerender() {
  if (!$("#gate").hidden) { showGate(GATE_SETUP); return; }
  renderTabs(); renderHeader(); renderNotices();
  if (!$("#pageView").hidden) PAGE?.(); else openTab(TAB);
}

// ------------------------------------------------------------------ login / first setup
let GATE_SETUP = false;
function showGate(setup) {
  GATE_SETUP = setup;
  $("#app").hidden = true; $("#gate").hidden = false;
  if (ES) { ES.close(); ES = null; }
  $("#gateTitle").textContent = t(setup ? "setup.title" : "login.title");
  $("#gateText").textContent = setup ? t("setup.text") : "";
  $("#gateUser").placeholder = t("login.user");
  if (!$("#gateUser").value) $("#gateUser").value = setup ? "admin" : (localStorage.getItem("lastUser") || "");
  $("#gatePw").placeholder = t("login.password");
  $("#gatePw2").placeholder = t("setup.pw2");
  $("#gatePw2").hidden = !setup;
  $("#gateBtn").textContent = t(setup ? "setup.submit" : "login.submit");
  ($("#gateUser").value ? $("#gatePw") : $("#gateUser")).focus();
}
$("#gateForm").onsubmit = async (e) => {
  e.preventDefault();
  const pw = $("#gatePw").value;
  $("#gateErr").textContent = "";
  try {
    if (GATE_SETUP) {
      if (pw.length < 8) throw new Error(t("setup.short"));
      if (pw !== $("#gatePw2").value) throw new Error(t("setup.mismatch"));
      await api("POST", "/api/setup", { username: $("#gateUser").value.trim(), password: pw });
    } else await api("POST", "/api/login", { username: $("#gateUser").value.trim(), password: pw });
    try { localStorage.setItem("lastUser", $("#gateUser").value.trim()); } catch { /* private mode */ }
    $("#gatePw").value = $("#gatePw2").value = "";
    boot();
  } catch (err) { $("#gateErr").textContent = err.message; }
};
$("#btnLogout").onclick = async () => { await api("POST", "/api/logout", {}).catch(() => {}); location.hash = ""; location.reload(); };

// ------------------------------------------------------------------ boot, server tabs, overview polling
async function boot() {
  let s;
  try { s = await (await fetch("/api/session")).json(); } catch { setOffline(true); setTimeout(boot, 3000); return; }
  if (!s.ok) return showGate(s.setup);
  ME = s.user;
  document.body.dataset.role = ME.role;
  $("#meInfo").textContent = `${ME.name} · ${t("role." + ME.role)}`;
  $("#gate").hidden = true; $("#app").hidden = false;
  [META, PRESETS] = await Promise.all([api("GET", "/api/configmeta"), api("GET", "/api/presets").then((d) => d.presets)]);
  await loadOverview();
  const [hid, htab] = decodeURIComponent(location.hash.slice(1)).split("/");
  selectServer(OV.instances.some((i) => i.id === hid) ? hid : OV.instances[0]?.id, htab || "overview");
  setInterval(() => { if (!OFFLINE && !$("#app").hidden) loadOverview(); }, 10000);
}
async function loadOverview() {
  try { OV = await api("GET", "/api/overview"); } catch { return; }
  renderTabs(); renderNotices();
  $("#steamInfo").textContent = OV.steam_busy ? `SteamCMD ${OV.steam_busy} ${OV.steam_progress ?? 0} %` : "";
}
function renderTabs() {
  $("#srvTabs").innerHTML = "";
  for (const i of OV.instances) {
    const el = h(`<div class="srv-tab${i.id === CUR ? " active" : ""}"><span class="dot ${i.state}"></span>${esc(i.name)}
      <small>${i.state === "running" ? i.players + " 👤" : esc(i.version || i.branch)}</small>${i.notices ? '<span class="bell">●</span>' : ""}</div>`).firstChild;
    el.onclick = () => selectServer(i.id, TAB);
    $("#srvTabs").append(el);
  }
  $("#btnNew").disabled = OV.instances.length >= OV.max;
}
function selectServer(id, tab = "overview") {
  if (!id) { showPage(() => { $("#pageView").innerHTML = `<p class="empty">${esc(t(isAdmin() ? "u.noServersAdmin" : "u.noServers"))}</p>`; }); return; }
  CUR = id; S = { status: {}, stats: {}, settings: {} };
  $("#console").innerHTML = "";
  showPage(null);
  renderTabs();
  openEvents();
  openTab(tab);
}
$("#btnNew").onclick = newServerDialog;
$("#btnVersions").onclick = () => showPage(pageVersions);
$("#btnPanel").onclick = () => showPage(pagePanel);
$(".brand").onclick = (e) => { e.preventDefault(); showPage(null); };

let PAGE = null;
function showPage(fn) {
  PAGE = fn;
  $("#srvView").hidden = !!fn; $("#pageView").hidden = !fn;
  if (fn) { history.replaceState(null, "", "#"); fn(); }
}

// ------------------------------------------------------------------ live events
function openEvents() {
  if (ES) ES.close();
  const id = CUR;
  ES = new EventSource(sp("/events"));
  ES.onmessage = (ev) => {
    if (id !== CUR) return;
    const m = JSON.parse(ev.data);
    if (m.type === "snapshot") {
      S.status = m.status; S.stats = m.stats || {};
      $("#console").innerHTML = ""; m.console.forEach(addLine);
      renderHeader(); if (TAB === "overview") renderOverview();
    } else if (m.type === "log") addLine(m);
    else if (m.type === "state") { const was = S.status.state; S.status = m; renderHeader(); if (TAB === "overview") renderOverview(); if (was !== m.state) loadOverview(); }
    else if (m.type === "stats") { S.stats = m; if (TAB === "overview") renderOverview(); }
    else if (m.type === "deleted") { loadOverview().then(() => selectServer(OV.instances[0]?.id)); }
  };
  ES.onerror = () => { if (ES.readyState === EventSource.CLOSED) { setOffline(true); } };
  ES.onopen = () => setOffline(false);
}
function addLine(m) {
  const c = $("#console");
  const lvl = (m.line.match(/ (INF|WRN|ERR|EXC) /) || [])[1] || "";
  const d = document.createElement("div");
  d.className = `s-${m.src} l-${lvl}`;
  d.innerHTML = `<span class="ts">${new Date(m.t * 1000).toLocaleTimeString(LANG === "cs" ? "cs-CZ" : "en-GB")}</span>${esc(m.line)}`;
  c.append(d);
  while (c.childElementCount > 3000) c.firstChild.remove();
  if ($("#autoScroll").checked && TAB === "console") c.scrollTop = c.scrollHeight;
}
$("#cmdForm").onsubmit = async (e) => {
  e.preventDefault();
  const cmd = $("#cmdInput").value.trim();
  if (!cmd) return;
  $("#cmdInput").value = "";
  const r = await act(() => api("POST", sp("/command"), { command: cmd }));
  if (r) { addLine({ t: Date.now() / 1000, src: "cmd", line: "> " + cmd }); r.output.forEach((l) => addLine({ t: Date.now() / 1000, src: "cmd", line: l })); }
};

// ------------------------------------------------------------------ header + notices
const live = () => ["running", "starting"].includes(S.status.state);
function renderHeader() {
  const st = S.status;
  if (!st.id) return;
  $("#srvTitle").textContent = st.name;
  const b = $("#stateBadge"); b.className = "badge " + st.state; b.textContent = t("state." + st.state);
  const g = st.game || {}, c = st.compat || {};
  const vc = $("#verChip");
  vc.textContent = (g.version || g.branch) + (g.branch !== "public" ? ` · ${g.branch}` : "");
  vc.className = "chip" + (["major", "downgrade"].includes(c.level) ? " badc" : ["newer_minor", "unknown"].includes(c.level) ? " warnc" : "");
  vc.title = compatText(c);
  $("#busyText").textContent = (g.busy ? t("ov.installing", { b: g.busy, p: g.progress ?? 0 }) + "  " : "") + (st.busy || "");
  $("#btnStart").disabled = live() || st.state === "stopping" || !g.installed || g.busy === g.branch;
  $("#btnStop").disabled = !live();
  $("#btnRestart").disabled = !live();
  $("#btnKill").disabled = !(live() || st.state === "stopping");
  renderNotices();
}
$("#btnStart").onclick = () => act((force) => api("POST", sp("/server/start" + (force ? "?force=1" : ""))));
$("#btnStop").onclick = () => act(() => api("POST", sp("/server/stop")));
$("#btnRestart").onclick = () => act(() => api("POST", sp("/server/restart")));
$("#btnKill").onclick = async () => { if (await confirmDlg(t("kill.hint"))) act(() => api("POST", sp("/server/kill"))); };

function renderNotices() {
  const box = $("#notices"); box.innerHTML = "";
  const n = S.status.notices || {};
  if (n.game_update && $("#pageView").hidden) {
    const u = n.game_update;
    const el = h(`<div class="notice${u.kind === "major" ? " bad" : ""}"><span>${esc(t("notice.game", { b: S.status.game?.branch, cur: u.current, target: u.target || "build " + u.build, kind: t("kind." + u.kind) }))}</span>
      <span class="muted small">${esc(t("notice.gamePolicy"))}</span><span class="sp"></span><button class="small primary">${esc(t("act.update"))}</button></div>`).firstChild;
    el.querySelector("button").onclick = async () => { if (u.kind !== "major" || await confirmDlg(t("kind.major"))) act(() => api("POST", `/api/versions/${S.status.game.branch}/update`), t("ok.queued")); };
    box.append(el);
  }
  if (n.mods?.length && $("#pageView").hidden) {
    const el = h(`<div class="notice info"><span>${esc(t("notice.mods", { n: n.mods.length }))} ${n.mods.map((m) => esc(m.name + " → " + m.latest)).join(", ")}</span><span class="sp"></span><button class="small">${esc(t("tab.mods"))}</button></div>`).firstChild;
    el.querySelector("button").onclick = () => openTab("mods");
    box.append(el);
  }
  if (OV.panel?.update) {
    const el = h(`<div class="notice info"><span>${esc(t("notice.panel", { v: OV.panel.update.version }))}</span><span class="sp"></span><button class="small">${esc(t("top.panel"))}</button></div>`).firstChild;
    el.querySelector("button").onclick = () => showPage(pagePanel);
    box.append(el);
  }
}

// ------------------------------------------------------------------ tabs
$$("#tabs button").forEach((b) => b.onclick = () => openTab(b.dataset.tab));
function openTab(name) {
  if (!isAdmin() && ["world", "settings", "mods", "files", "automation"].includes(name)) name = "overview";
  TAB = name;
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".tab").forEach((x) => x.classList.toggle("active", x.id === "tab-" + name));
  if (CUR) history.replaceState(null, "", `#${CUR}/${name}`);
  ({ overview: renderOverview, console: () => { const c = $("#console"); c.scrollTop = c.scrollHeight; $("#cmdInput").disabled = !S.status.console_connected; },
     players: loadPlayers, world: loadWorld, settings: loadSettings, mods: loadMods, backups: loadBackups,
     files: () => loadFiles(FPATH ?? `/instances/${CUR}`), automation: loadAutomation })[name]?.();
}

// ------------------------------------------------------------------ overview
function renderOverview() {
  const st = S.status, s = S.stats || {}, g = st.game || {}, w = st.world || {}, mi = st.meminfo || {};
  if (!st.id) return;
  const lim = st.ram_limit_gb;
  const card = (title, big, sub = "") => `<div class="card"><h3>${esc(title)}</h3><div class="big">${big}</div><div class="sub">${sub}</div></div>`;
  let top = "";
  if (!g.installed) {
    top = g.busy === g.branch
      ? `<div class="card wide"><h3>${esc(t("ov.installing", { b: g.branch, p: g.progress ?? 0 }))}</h3><div class="progress"><div style="width:${g.progress ?? 0}%"></div></div></div>`
      : `<div class="card wide row"><span class="sp">${esc(t("ov.notinstalled", { b: g.branch }))}</span><button class="primary" id="ovInstall">${esc(t("ov.install"))}</button></div>`;
  }
  const c = st.compat || {};
  const compat = ["same", "new"].includes(c.level) ? "" : `<div class="alert ${c.level} wide">${esc(compatText(c))}</div>`;
  $("#tab-overview").innerHTML = `<div class="grid">${top}${compat}
    ${card(t("ov.players"), st.state === "running" ? `${(st.players || []).length} / ${esc(w.ServerMaxPlayerCount || "?")}` : "–", esc((st.players || []).map((p) => p.name).join(", ")))}
    ${card(t("ov.time"), esc(st.gametime || "–"), st.started_at ? esc(t("ov.up", { d: fmtDur(Date.now() / 1000 - st.started_at) })) : "")}
    ${card(t("ov.world"), esc(w.GameWorld || "–"), esc(w.GameName || ""))}
    ${card(t("ov.version"), esc(g.version || "?"), esc(g.branch + (g.build ? " · build " + g.build : "")))}
    ${card(t("ov.cpu"), live() && s.srv_cpu != null ? s.srv_cpu + " %" : "–", s.host_cpu != null ? `${esc(t("ov.machine"))} ${s.host_cpu} % · load ${(s.load || []).map((x) => x.toFixed(2)).join(" ")}` : "")}
    ${card(t("ov.ram"), live() && s.srv_mem ? fmtBytes(s.srv_mem) : "–", (lim ? esc(t("ov.limit", { n: lim })) + " · " : "") + (s.host_mem_total ? `${esc(t("ov.machine"))} ${fmtBytes(s.host_mem)} / ${fmtBytes(s.host_mem_total)}` : ""))}
    ${card(t("ov.fps"), mi.fps ? esc(mi.fps) : "–", mi.fps ? `chunks ${esc(mi.chunks)} · zombies ${esc(mi.zombies)} · entities ${esc(mi.entities)}` : "")}
    ${card(t("ov.temp"), s.cpu_temp != null ? Math.round(s.cpu_temp) + " °C" : "–", s.disk_total ? `${esc(t("ov.disk"))} ${fmtBytes(s.disk_used)} / ${fmtBytes(s.disk_total)}` : "")}
    ${card(t("ov.ports"), esc(st.ports?.game || "–"), esc(t("ov.portsHint", { g: st.ports?.game, w: st.ports?.web })))}
    ${card(t("ov.lastbackup"), st.last_backup ? esc(fmtTime(st.last_backup)) : "–")}
  </div>`;
  $("#tab-overview").append(quickActions());
  const bi = $("#ovInstall"); if (bi) bi.onclick = () => act(() => api("POST", `/api/versions/${g.branch}/install`), t("ok.queued"));
}

let QA_MIN = "5";
function quickActions() {
  const st = S.status, n = st.notices || {}, run = st.state === "running";
  const box = h(`<div class="card op-only" style="margin-top:14px"><h3>${t("qa.title")}</h3>
    ${st.pending ? `<div class="alert newer_minor row"><span class="sp">${esc(t("qa.pending", { w: st.pending }))}</span><button class="small" data-q="cancel">${t("qa.cancel")}</button></div>` : ""}
    <div class="row">
      <button data-q="saveworld"${run ? "" : " disabled"}>💾 ${t("qa.save")}</button>
      <button data-q="backup">🗄 ${t("qa.backup")}</button>
      <button data-q="say"${run ? "" : " disabled"}>💬 ${t("qa.say")}</button>
      <button data-q="check">🔎 ${t("qa.check")}</button>
    </div>
    <div class="row">
      <label class="small">${t("qa.warnIn")} <select id="qaMin">${[["0", t("qa.now")], ["1", "1 " + t("unit.min")], ["5", "5 " + t("unit.min")], ["10", "10 " + t("unit.min")], ["15", "15 " + t("unit.min")], ["30", "30 " + t("unit.min")]].map(([v, l]) => `<option value="${v}"${v === QA_MIN ? " selected" : ""}>${esc(l)}</option>`).join("")}</select></label>
      <button data-q="restart"${run ? "" : " disabled"}>↻ ${t("qa.restart")}</button>
      <button data-q="stop"${run ? "" : " disabled"}>■ ${t("qa.stop")}</button>
      <button data-q="update_game"${n.game_update ? ' class="primary"' : " disabled"}>⬆ ${t("qa.updGame")}</button>
      <button data-q="update_mods"${n.mods?.length ? ' class="primary"' : ""}>🧩 ${t("qa.updMods")}</button>
      <button data-q="update_all"${n.game_update || n.mods?.length ? ' class="primary"' : ""}>⏫ ${t("qa.updAll")}</button>
    </div></div>`).firstChild;
  $("#qaMin", box).onchange = (e) => { QA_MIN = e.target.value; };
  $$("[data-q]", box).forEach((b) => b.onclick = async () => {
    const q = b.dataset.q, minutes = Number(QA_MIN);
    if (q === "backup") return act(() => api("POST", sp("/backups/create")), t("ok.queued"));
    if (q === "say") { const m = await promptDlg(t("qa.say"), t("qa.sayPh")); if (m) act(() => api("POST", sp("/quick/say"), { message: m }), t("ok.saved")); return; }
    if (q === "update_game" && n.game_update?.kind === "major" && !await confirmDlg(t("kind.major"))) return;
    b.disabled = true;
    const r = await act(() => api("POST", sp("/quick/" + q), { minutes }), q === "saveworld" ? t("ok.saved") : q === "check" ? "" : t("ok.queued"));
    if (q === "check" && r) { toast(r.notices.game_update || r.notices.mods?.length ? "" : t("qa.nothing")); loadOverview(); }
    b.disabled = false;
  });
  return box;
}

// ------------------------------------------------------------------ players
async function loadPlayers() {
  const el = $("#tab-players");
  if (S.status.state !== "running") { el.innerHTML = `<p class="empty">${esc(t("pl.offline"))}</p>`; return; }
  const d = await act(() => api("GET", sp("/players")));
  if (!d) return;
  if (!d.players.length) { el.innerHTML = `<p class="empty">${esc(t("pl.none"))}</p>`; return; }
  el.innerHTML = `<table><tr><th>${t("pl.name")}</th><th class="num">${t("pl.level")}</th><th class="num">${t("pl.health")}</th><th class="num">${t("pl.deaths")}</th><th class="num">${t("pl.zombies")}</th><th class="num">${t("pl.ping")}</th><th></th></tr>
    ${d.players.map((p, i) => `<tr><td>${esc(p.name)}<div class="muted small">${esc(p.pltfmid)}</div></td><td class="num">${esc(p.level)}</td><td class="num">${esc(p.health)}</td><td class="num">${esc(p.deaths)}</td><td class="num">${esc(p.zombies)}</td><td class="num">${esc(p.ping)}</td>
    <td class="row op-only"><button class="small" data-k="${i}">${t("pl.kick")}</button><button class="small danger" data-b="${i}">${t("pl.ban")}</button><button class="small" data-a="${i}">${t("pl.admin")}</button></td></tr>`).join("")}</table>`;
  const cmd = (c) => act(() => api("POST", sp("/command"), { command: c })).then(loadPlayers);
  const id = (p) => p.crossid || p.pltfmid || p.entityid;
  $$("[data-k]", el).forEach((b) => b.onclick = async () => { const p = d.players[b.dataset.k]; const r = await promptDlg(t("pl.kick"), t("pl.kickReason")); if (r !== null) cmd(`kick ${p.entityid} "${r.replace(/"/g, "'")}"`); });
  $$("[data-b]", el).forEach((b) => b.onclick = async () => { const p = d.players[b.dataset.b]; const r = await promptDlg(t("pl.ban"), t("pl.kickReason")); if (r !== null) cmd(`ban add ${id(p)} 10 years "${r.replace(/"/g, "'")}"`); });
  $$("[data-a]", el).forEach((b) => b.onclick = async () => { const p = d.players[b.dataset.a]; if (await confirmDlg(t("pl.admin") + ": " + p.name, t("act.yes"), false)) cmd(`admin add ${id(p)} 0 "${p.name.replace(/"/g, "'")}"`); });
}

// ------------------------------------------------------------------ world
let VERS = null;
async function getVersions(refresh) { VERS = await api("GET", "/api/versions" + (refresh ? "?refresh=1" : "")); return VERS; }
function versionOptions(sel) {
  const list = (VERS?.branches || []).filter((b) => !b.password);
  return list.map((b) => `<option value="${esc(b.name)}"${b.name === sel ? " selected" : ""}>${esc(b.name)} - ${esc(b.version || b.description || "?")}${b.installed ? " ✓" : ""}</option>`).join("");
}
async function loadWorld() {
  const el = $("#tab-world");
  const [d] = await Promise.all([act(() => api("GET", sp("/worlds"))), VERS ? null : getVersions().catch(() => null)]);
  if (!d) return;
  const cur = d.current, c = S.status.compat || {};
  const maps = [...d.builtin, ...d.generated.map((g) => g.name)];
  el.innerHTML = `
  <div class="card"><h3>${t("w.version")}</h3>
    <div class="row"><select id="wVer">${versionOptions(d.branch)}</select><button id="wVerBtn" class="primary">${t("w.change")}</button><span class="muted small">${esc(t("w.versionHint"))}</span></div>
    <div id="wVerCompat"></div>
  </div>
  <div class="card"><h3>${t("w.current")}</h3>
    <div class="row"><b>${esc(cur.GameWorld || "–")}</b><span class="muted">/</span><b>${esc(cur.GameName || "–")}</b>
    ${cur.GameWorld === "RWG" ? `<span class="muted small">seed ${esc(cur.WorldGenSeed)} · ${esc(cur.WorldGenSize)}</span>` : ""}</div>
    <div class="alert ${c.level}">${esc(compatText(c))}</div>
  </div>
  <div class="card"><h3>${t("w.new")}</h3><p class="muted small">${esc(t("w.newHint"))}</p>
    <div class="form-grid">
      <div class="field"><label>${t("w.map")}</label><select id="wMap"><option value="RWG">${esc(t("w.rwg"))}</option>${maps.map((m) => `<option${m === cur.GameWorld ? " selected" : ""}>${esc(m)}</option>`).join("")}</select></div>
      <div class="field"><label>${t("w.gamename")}</label><input id="wName" value="${esc(cur.GameName)}"></div>
      <div class="field rwg"><label>${t("w.seed")}</label><input id="wSeed" value="${esc(cur.WorldGenSeed)}"></div>
      <div class="field rwg"><label>${t("w.size")}</label><select id="wSize">${["4096", "6144", "8192", "10240"].map((x) => `<option${x === cur.WorldGenSize ? " selected" : ""}>${x}</option>`).join("")}</select></div>
    </div>
    <div class="row" style="margin-top:10px"><button class="primary" id="wApply">${t("act.apply")}</button><span class="muted small">${esc(t("w.applyRestart"))}</span></div>
  </div>
  <h2>${t("w.saves")}</h2>
  ${d.saves.length ? `<table><tr><th>${t("w.map")}</th><th>${t("w.save")}</th><th>${t("w.made")}</th><th>${t("w.last")}</th><th class="num">${t("w.size2")}</th><th>${t("w.changed")}</th><th></th></tr>
    ${d.saves.map((s, i) => `<tr><td>${esc(s.world)}</td><td>${esc(s.game)} ${d.active === s.world + "/" + s.game ? `<span class="tag on">${t("w.active")}</span>` : ""}</td><td>${esc(s.created || "?")}</td><td>${esc(s.last || "?")}</td>
    <td class="num">${fmtBytes(s.size)}</td><td>${fmtTime(s.mtime)}</td><td class="row"><button class="small" data-use="${i}">${t("act.select")}</button><button class="small danger" data-ds="${i}">${t("act.delete")}</button></td></tr>`).join("")}</table>`
    : `<p class="empty">–</p>`}
  <h2>${t("w.generated")}</h2>
  ${d.generated.length ? `<table>${d.generated.map((g, i) => `<tr><td>${esc(g.name)}</td><td class="num">${fmtBytes(g.size)}</td><td>${fmtTime(g.mtime)}</td><td><button class="small danger" data-dw="${i}">${t("act.delete")}</button></td></tr>`).join("")}</table>` : `<p class="empty">–</p>`}
  <h2>${t("w.import")}</h2>
  <div class="card"><p class="muted small">${esc(t("w.importHint"))}</p>
    <div class="form-grid">
      <div class="field"><label>${t("w.importVersion")}</label><input id="impVer" placeholder="V 2.6 / Alpha 21.2"><div class="hint">${esc(t("w.importVersionHint"))}</div></div>
      <div class="field"><label class="check"><input type="checkbox" id="impOver"> ${esc(t("w.overwrite"))}</label></div>
    </div>
    <div class="drop" id="impDrop">ZIP ⤓ <button class="small" id="impPick">${t("act.upload")}</button></div>
  </div>`;
  const rwg = () => $$(".rwg", el).forEach((x) => x.hidden = $("#wMap").value !== "RWG");
  $("#wMap").onchange = rwg; rwg();
  const showCompat = async () => {
    const r = await api("GET", sp("/compat?branch=" + encodeURIComponent($("#wVer").value))).catch(() => null);
    $("#wVerCompat").innerHTML = r ? `<div class="alert ${r.level}">${esc(compatText(r))}</div>` : "";
  };
  $("#wVer").onchange = showCompat;
  $("#wVerBtn").onclick = () => act((force) => api("POST", sp("/version"), { branch: $("#wVer").value, force: !!force }), t("ok.saved")).then(loadWorld);
  $("#wApply").onclick = () => {
    const m = $("#wMap").value, body = { GameWorld: m, GameName: $("#wName").value };
    if (m === "RWG") Object.assign(body, { WorldGenSeed: $("#wSeed").value, WorldGenSize: $("#wSize").value });
    act(() => api("POST", sp("/worlds/select"), body), t("ok.saved")).then(loadWorld);
  };
  $$("[data-use]", el).forEach((b) => b.onclick = () => { const s = d.saves[b.dataset.use]; act(() => api("POST", sp("/worlds/select"), { GameWorld: s.world, GameName: s.game }), t("ok.saved")).then(loadWorld); });
  $$("[data-ds]", el).forEach((b) => b.onclick = async () => { const s = d.saves[b.dataset.ds]; if (await confirmDlg(t("w.deleteSave", { s: s.world + "/" + s.game }))) act(() => api("POST", sp("/worlds/delete"), { type: "save", world: s.world, game: s.game })).then(loadWorld); });
  $$("[data-dw]", el).forEach((b) => b.onclick = async () => { const g = d.generated[b.dataset.dw]; if (await confirmDlg(t("w.deleteWorld", { s: g.name }))) act(() => api("POST", sp("/worlds/delete"), { type: "generated", world: g.name })).then(loadWorld); });
  const upload = async (file) => {
    const fd = new FormData(); fd.append("file", file); fd.append("version", $("#impVer").value); fd.append("overwrite", $("#impOver").checked ? "1" : "0");
    $("#impDrop").textContent = "…";
    const r = await act(() => api("POST", sp("/worlds/import"), fd));
    if (r) { toast(t("w.imported", { s: r.imported.join(", ") })); (r.warnings || []).forEach((w) => toast(w, true)); }
    loadWorld();
  };
  $("#impPick").onclick = () => pickFile(".zip", upload);
  dropZone($("#impDrop"), upload);
}
function pickFile(accept, cb) { const f = $("#filePick"); f.accept = accept; f.value = ""; f.onchange = () => f.files[0] && cb(f.files[0]); f.click(); }
function dropZone(el, cb) {
  el.ondragover = (e) => { e.preventDefault(); el.classList.add("over"); };
  el.ondragleave = () => el.classList.remove("over");
  el.ondrop = (e) => { e.preventDefault(); el.classList.remove("over"); if (e.dataTransfer.files[0]) cb(e.dataTransfer.files[0]); };
}

// ------------------------------------------------------------------ game settings (basic / detailed / advanced)
let LEVEL = "basic", CFG = null, SB = null, CHANGES = {}, SBCH = {};
const SB_BASIC = ["IncomingDamage", "EntityDamage", "XPMultiplier", "DayNightLength", "ZombieMove", "ZombieMoveNight",
  "BloodMoonFrequency", "BloodMoonEnemyCount", "GlobalLootCount", "DeathPenalty", "DropOnDeath"];
const SB_CATS = { General: ["General", "Obecné"], Entities: ["Zombies & animals", "Zombíci a zvířata"], World: ["World", "Svět"],
  Resources: ["Loot & resources", "Loot a suroviny"], Crafting: ["Crafting", "Craftění"], Tasks: ["Quests & skills", "Questy a dovednosti"],
  Traders: ["Traders", "Obchodníci"], Misc: ["Fun & misc", "Zábava a ostatní"] };
async function loadSettings() {
  const [d, sb] = await Promise.all([act(() => api("GET", sp("/config"))), api("GET", sp("/sandbox")).catch(() => ({ supported: false }))]);
  if (!d) return;
  CFG = d; SB = sb.supported ? sb : null; CHANGES = {}; SBCH = {};
  renderSettings();
}
function cfgValue(n) { return n in CHANGES ? CHANGES[n] : CFG.props.find((p) => p.name === n)?.value; }
function sbField(o) {
  const cur = o.name in SBCH ? SBCH[o.name] : SB.current[o.name];
  return `<div class="cfg-item${o.name in SBCH ? " changed" : ""}${cur !== o.default ? " nondefault" : ""}"><label>${esc(o.label)}</label><div class="key">${esc(o.name)}</div>
    <select data-sb="${o.name}">${o.values.map((v, i) => `<option value="${i}"${i === cur ? " selected" : ""}>${esc(v)}${i === o.default ? " ·" : ""}</option>`).join("")}</select>
    <div class="hint">${esc(o.desc)}</div></div>`;
}
function sbGroup(id, title, opts) {
  return opts.length ? `<div class="cfg-group" id="cat-${id}"><h2>${esc(title)}</h2><div class="cfg-grid">${opts.map(sbField).join("")}</div></div>` : "";
}
function renderSettings() {
  const el = $("#tab-settings");
  if (!CFG.exists) { el.innerHTML = `<p class="empty">${esc(t("st.noconfig"))}</p>`; return; }
  const have = new Map(CFG.props.map((p) => [p.name, p]));
  const cats = META.categories.filter((c) => c.level === LEVEL);
  const byCat = {};
  for (const p of CFG.props) {
    if (p.name === "SandboxCode") continue;
    const m = META.props[p.name];
    (byCat[m ? m.cat : "other"] ||= []).push(p.name);
  }
  const order = Object.keys(META.props);
  for (const c of Object.keys(byCat)) byCat[c].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  const sbOpts = SB ? SB.options : [];
  let html = `<div class="seg">${["basic", "detailed", "advanced"].map((l) => `<button data-lv="${l}" class="${l === LEVEL ? "active" : ""}">${t("st." + l)}</button>`).join("")}</div>`;
  if (SB) html += `<p class="muted small">${esc(t("sb.info", { v: SB.game }))}</p>`;
  if (LEVEL === "basic") {
    html += `<h2>${t("st.presets")}</h2><p class="muted small">${esc(t("st.presetsHint"))}</p><div class="preset-layout"><div class="preset-main">`;
    const cur = S.status.preset || "";
    for (const tier of ["easy", "medium", "hard", "extreme"]) {
      const list = PRESETS.filter((p) => p.tier === tier);
      if (!list.length) continue;
      html += `<h4 class="tier tier-${tier}">${esc(t("tier." + tier))}</h4><div class="presets">${list.map((p) => presetCard(p, cur)).join("")}${tier === "medium" ? randomCard() : ""}</div>`;
    }
    html += `</div><aside class="stack card" id="stackBox"></aside></div>`;
  } else {
    html += `<div class="row" style="margin-bottom:10px"><input id="cfgSearch" placeholder="${esc(t("st.search"))}" style="flex:1;max-width:360px"></div>`;
    if (LEVEL === "advanced") html += `<div class="alert newer_minor">${esc(t("st.advancedWarn"))}</div>`;
    const nav = cats.filter((c) => byCat[c.id]?.length).map((c) => [c.id, L(c.label)]);
    if (SB && LEVEL === "detailed") Object.keys(SB_CATS).forEach((c) => nav.unshift(["sb-" + c, SB_CATS[c][LANG === "cs" ? 1 : 0]]));
    html += `<div class="cat-nav">${nav.map(([id, lab]) => `<a data-go="${id}">${esc(lab)}</a>`).join("")}</div>`;
  }
  if (SB && LEVEL === "basic") html += sbGroup("sb-basic", t("sb.basic"), SB_BASIC.map((n) => sbOpts.find((o) => o.name === n)).filter(Boolean));
  if (SB && LEVEL === "detailed") for (const c of Object.keys(SB_CATS).reverse().reverse()) html += sbGroup("sb-" + c, SB_CATS[c][LANG === "cs" ? 1 : 0], sbOpts.filter((o) => o.category === c));
  for (const c of cats) {
    const names = byCat[c.id] || [];
    if (names.length) html += `<div class="cfg-group" id="cat-${c.id}"><h2>${esc(L(c.label))}</h2><div class="cfg-grid">${names.map((n) => cfgField(n, have.get(n))).join("")}</div></div>`;
  }
  if (SB && LEVEL === "advanced") html += `<div class="cfg-group"><h2>SandboxCode</h2><p class="muted small">${esc(t("sb.codeHint"))}</p>
    <div class="row"><input id="sbCode" value="${esc(SB.code)}" style="flex:1;font-family:var(--mono)"><button id="sbCodeSave">${t("act.apply")}</button></div></div>`;
  html += `<div class="row" style="margin-top:18px"><button type="button" id="cxDl">⤓ ${t("cx.export")}</button>
    <button id="cxSave">🗄 ${t("cx.exportServer")}</button><button id="cxImp">⤒ ${t("cx.import")}</button></div>`;
  html += `<div class="savebar" id="saveBar" hidden><span id="saveInfo"></span><span class="sp"></span><button id="cfgReset">${t("act.cancel")}</button><button class="primary" id="cfgSave">${t("act.save")}</button></div>
    <p class="small"><a href="#" id="rawCfg">${esc(t("st.raw"))}</a></p>`;
  el.innerHTML = html;
  $$("[data-lv]", el).forEach((b) => b.onclick = () => { LEVEL = b.dataset.lv; renderSettings(); });
  $$("[data-go]", el).forEach((a) => a.onclick = () => $("#cat-" + a.dataset.go)?.scrollIntoView({ behavior: "smooth" }));
  $$("[data-pr]", el).forEach((b) => b.onclick = () => presetDialog({ id: b.dataset.pr }));
  $$("[data-rnd]", el).forEach((b) => b.onclick = () => presetDialog({ tier: b.dataset.rnd }));
  $$("[data-add]", el).forEach((b) => b.onclick = () => stackAdd({ id: b.dataset.add }));
  $$("[data-addrnd]", el).forEach((b) => b.onclick = async () => {
    const plan = await act(() => api("POST", sp("/preset/preview"), { tier: b.dataset.addrnd }));
    if (plan) stackAdd({ tier: plan.preset.tier, seed: plan.preset.seed, name: plan.preset.name, desc: plan.preset.desc });
  });
  if ($("#stackBox")) renderStack();
  const dirty = () => { const k = Object.keys(CHANGES).length + Object.keys(SBCH).length; $("#saveBar").hidden = !k; $("#saveInfo").textContent = t("st.unsaved", { n: k }); };
  $$("[data-cfg]", el).forEach((inp) => inp.oninput = inp.onchange = () => {
    const n = inp.dataset.cfg, orig = have.get(n).value;
    const v = inp.type === "checkbox" ? String(inp.checked) : inp.value;
    if (v === orig) delete CHANGES[n]; else CHANGES[n] = v;
    inp.closest(".cfg-item").classList.toggle("changed", n in CHANGES);
    dirty();
  });
  $$("[data-sb]", el).forEach((sel) => sel.onchange = () => {
    const n = sel.dataset.sb, v = Number(sel.value);
    if (v === SB.current[n]) delete SBCH[n]; else SBCH[n] = v;
    sel.closest(".cfg-item").classList.toggle("changed", n in SBCH);
    dirty();
  });
  const srch = $("#cfgSearch");
  if (srch) srch.oninput = () => { const q = srch.value.toLowerCase(); $$(".cfg-item", el).forEach((i) => i.hidden = q && !i.textContent.toLowerCase().includes(q)); };
  $("#cfgReset").onclick = () => { CHANGES = {}; SBCH = {}; renderSettings(); };
  $("#cfgSave").onclick = async () => {
    if (Object.keys(CHANGES).length && !await act(() => api("POST", sp("/config"), { changes: CHANGES }))) return;
    if (Object.keys(SBCH).length && !await act(() => api("POST", sp("/sandbox"), { values: SBCH }))) return;
    toast(t("st.saved")); loadSettings();
  };
  const sc = $("#sbCodeSave"); if (sc) sc.onclick = async () => { if (await act(() => api("POST", sp("/sandbox"), { code: $("#sbCode").value }), t("st.saved"))) loadSettings(); };
  $("#cxDl").onclick = () => { location.href = sp("/export"); };
  $("#cxSave").onclick = async () => { const r = await act(() => api("POST", sp("/export"))); if (r) toast(t("cx.saved", { p: r.path })); };
  $("#cxImp").onclick = importConfigDialog;
  $("#rawCfg").onclick = (e) => { e.preventDefault(); openTab("files"); editFile(CFG.path); };
}
function presetCard(p, cur) {
  return `<div class="preset${cur === p.id ? " active" : ""}"><h4>${p.icon} ${esc(L(p.name))}</h4><div class="skulls" title="${esc(t("st.level"))}">${"☠".repeat(p.level)}${"·".repeat(5 - p.level)}</div>
    <p>${esc(L(p.desc))}</p><div class="row">${cur === p.id ? `<span class="tag on">${esc(t("st.preset.active"))}</span>` : ""}
    ${p.modlets?.length ? `<span class="tag warnt" title="${esc(t("st.preset.modletHint"))}">XML</span>` : ""}<span class="sp"></span>
    <button class="small" data-add="${p.id}" title="${esc(t("stk.add"))}">＋</button><button class="small primary" data-pr="${p.id}">${t("st.preset.show")}</button></div></div>`;
}
function randomCard() {
  return `<div class="preset random"><h4>🎲 ${esc(t("rnd.title"))}</h4><p>${esc(t("rnd.desc"))}</p>
    <div class="row"><button class="small" data-rnd="easy">${t("tier.easy")}</button><button class="small" data-rnd="medium">${t("tier.medium")}</button><button class="small danger" data-rnd="hard">${t("tier.hard")}</button></div>
    <div class="row small muted">${esc(t("stk.addRandom"))} <button class="small" data-addrnd="easy">＋${t("tier.easy")}</button><button class="small" data-addrnd="medium">＋${t("tier.medium")}</button><button class="small" data-addrnd="hard">＋${t("tier.hard")}</button></div></div>`;
}
function cfgField(n, p) {
  const m = META.props[n] || { type: /^(true|false)$/.test(p.value) ? "bool" : /^-?\d+(\.\d+)?$/.test(p.value) ? "number" : "text", label: { en: n } };
  const v = n in CHANGES ? CHANGES[n] : p.value;
  const locked = m.managed === "locked";
  const help = L(m.help) || p.comment || "";
  const lab = `<label>${esc(L(m.label) || n)}${m.managed ? `<span class="managed">${esc(t("st.managed"))}</span>` : ""}</label><div class="key">${esc(n)}</div>`;
  const dis = locked ? " disabled" : "";
  if (m.type === "bool") return `<div class="cfg-item bool${n in CHANGES ? " changed" : ""}"><input type="checkbox" data-cfg="${n}"${v === "true" ? " checked" : ""}${dis}><div>${lab}<div class="hint">${esc(help)}</div></div></div>`;
  let input;
  if (m.type === "select") {
    const opts = m.options.some((o) => o[0] === v) ? m.options : [...m.options, [v, v, v]];
    input = `<select data-cfg="${n}"${dis}>${opts.map((o) => `<option value="${esc(o[0])}"${o[0] === v ? " selected" : ""}>${esc(LANG === "cs" ? o[2] : o[1])}</option>`).join("")}</select>`;
  } else input = `<input data-cfg="${n}" value="${esc(v)}" type="${m.type === "number" ? "number" : m.type === "password" ? "password" : "text"}"${m.min != null ? ` min="${m.min}"` : ""}${m.max != null ? ` max="${m.max}"` : ""}${dis}>`;
  return `<div class="cfg-item${n in CHANGES ? " changed" : ""}">${lab}${input}<div class="hint">${esc(help)}</div></div>`;
}
// ---- preset combination (first = highest priority, overrides everything below it)
let STACK = null, STACK_FOR = null;
function stackItem(x) {
  if (x.tier && x.seed) {
    const tierName = t("tier." + x.tier);
    return { tier: x.tier, seed: x.seed, icon: "🎲", name: x.name || { en: `Random · ${tierName} #${x.seed}`, cs: `Náhodný · ${tierName} #${x.seed}` }, desc: x.desc };
  }
  const p = PRESETS.find((q) => q.id === x.id);
  return p ? { id: p.id, icon: p.icon, name: p.name, desc: p.desc } : null;
}
function stackAdd(x) {
  const it = stackItem(x);
  if (!it || (it.id && STACK.some((s) => s.id === it.id))) return;
  STACK.unshift(it);
  renderStack();
}
function renderStack() {
  if (STACK_FOR !== CUR) { STACK = (S.status.preset_stack || []).map(stackItem).filter(Boolean); STACK_FOR = CUR; }
  const box = $("#stackBox");
  box.innerHTML = `<h3>🧩 ${t("stk.title")}</h3><p class="muted small">${esc(t("stk.hint"))}</p>
    ${STACK.length ? `<ol class="stack-list">${STACK.map((x, i) => `<li draggable="true" data-i="${i}"><span class="grip" title="${esc(t("stk.drag"))}">⠿</span>
      <span class="sname">${x.icon} ${esc(L(x.name))}</span><span class="sp"></span>
      <button class="small ghost" data-up="${i}"${i ? "" : " disabled"} title="↑">↑</button><button class="small ghost" data-down="${i}"${i < STACK.length - 1 ? "" : " disabled"} title="↓">↓</button>
      <button class="small ghost" data-rm="${i}" title="${esc(t("act.remove"))}">✕</button></li>`).join("")}</ol>
      <div class="muted small stack-legend"><span>▲ ${esc(t("stk.top"))}</span><span>▼ ${esc(t("stk.bottom"))}</span></div>`
      : `<p class="empty">${esc(t("stk.empty"))}</p>`}
    <div class="row"><button class="primary" id="stkApply"${STACK.length ? "" : " disabled"}>${t("stk.apply")}</button><button id="stkClear"${STACK.length ? "" : " disabled"}>${t("stk.clear")}</button></div>`;
  const move = (from, to) => { if (to < 0 || to >= STACK.length || from === to) return; const [x] = STACK.splice(from, 1); STACK.splice(to, 0, x); renderStack(); };
  $$("[data-up]", box).forEach((b) => b.onclick = () => move(+b.dataset.up, +b.dataset.up - 1));
  $$("[data-down]", box).forEach((b) => b.onclick = () => move(+b.dataset.down, +b.dataset.down + 1));
  $$("[data-rm]", box).forEach((b) => b.onclick = () => { STACK.splice(+b.dataset.rm, 1); renderStack(); });
  let dragFrom = null;
  $$(".stack-list li", box).forEach((li) => {
    li.ondragstart = (e) => { dragFrom = +li.dataset.i; li.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", li.dataset.i); };
    li.ondragend = () => li.classList.remove("dragging");
    li.ondragover = (e) => { e.preventDefault(); const r = li.getBoundingClientRect(); li.classList.toggle("drop-before", e.clientY < r.top + r.height / 2); li.classList.toggle("drop-after", e.clientY >= r.top + r.height / 2); };
    li.ondragleave = () => li.classList.remove("drop-before", "drop-after");
    li.ondrop = (e) => {
      e.preventDefault();
      const to = +li.dataset.i + (li.classList.contains("drop-after") ? 1 : 0);
      li.classList.remove("drop-before", "drop-after");
      if (dragFrom === null) return;
      move(dragFrom, dragFrom < to ? to - 1 : to);
      dragFrom = null;
    };
  });
  $("#stkClear").onclick = () => { STACK = []; renderStack(); };
  $("#stkApply").onclick = () => presetDialog({ stack: STACK.map((x) => x.seed ? { tier: x.tier, seed: x.seed } : { id: x.id }) });
}
async function presetDialog(req) {
  for (;;) {
    const plan = await act(() => api("POST", sp("/preset/preview"), req));
    if (!plan) return;
    const p = plan.preset;
    const rows = plan.diff.map((d) => `${esc(d.label)}: ${esc(d.old)} → <b>${esc(d.new)}</b>${p.stack && d.from ? ` <span class="muted">· ${esc(L(d.from))}</span>` : ""}`).join("<br>") || esc(t("st.preset.nochange"));
    const ov = (plan.overridden || []).map((o) => esc(t("stk.overrides", { w: L(o.winner), l: L(o.loser), k: o.key }))).join("<br>");
    const body = h(`<div class="skulls">${"☠".repeat(p.level)}${"·".repeat(5 - p.level)}</div>
      ${p.stack ? `<ol class="twists">${p.stack.map((x) => `<li>${x.icon} ${esc(L(x.name))}</li>`).join("")}</ol>${ov ? `<div class="alert unknown small"><b>${esc(t("stk.conflicts"))}</b><br>${ov}</div>` : ""}` : p.twists ? `<ul class="twists">${p.twists.map((x) => `<li><span class="tag ${x.score > 0 ? "no" : x.score < 0 ? "yes" : ""}">${x.score > 0 ? "+" : ""}${x.score}</span> ${esc(L(x.name))}</li>`).join("")}</ul>` : `<p>${esc(L(p.desc))}</p>`}
      <h4>${esc(t("st.preset.diff"))} (${plan.diff.length})</h4><div class="diff">${rows}</div>
      ${plan.modlets.length ? `<div class="alert newer_minor small"><b>XML modlet:</b> ${plan.modlet_desc.map(esc).join("; ")}<br>${esc(t("st.preset.modletHint"))}</div>` : ""}
      ${plan.skipped.length ? `<p class="muted small">${esc(t("st.preset.skipped", { n: plan.skipped.join(", ") }))}</p>` : ""}
      <p class="muted small">${esc(t("w.applyRestart"))}</p>
      ${req.tier ? `<button type="button" id="reroll">🎲 ${t("rnd.reroll")}</button>` : ""}`);
    let reroll = false;
    const rb = body.querySelector("#reroll");
    if (rb) rb.onclick = () => { reroll = true; $("#dlg").close(); };
    const okd = await dialog(`${p.icon} ${L(p.name)}`, body, t("st.preset.apply"));
    if (reroll) { req = { tier: req.tier }; continue; }
    if (!okd) return;
    const send = req.stack ? req : p.seed ? { tier: p.tier, seed: p.seed } : { id: p.id };
    if (await act(() => api("POST", sp("/preset"), send), t("st.saved"))) {
      S.status.preset = p.seed ? `${p.id}#${p.seed}` : p.id;
      S.status.preset_stack = req.stack || [p.seed ? { tier: p.tier, seed: p.seed } : { id: p.id }];
      STACK_FOR = null;
      loadSettings();
    }
    return;
  }
}
async function importConfigDialog() {
  const ex = await act(() => api("GET", "/api/exports"));
  if (!ex) return;
  const others = ex.servers.filter((x) => x.id !== CUR);
  const body = h(`<div class="field"><label>${t("cx.from")}</label>
      <label class="check"><input type="radio" name="cxSrc" value="pc" checked> ${esc(t("cx.fromPc"))}</label>
      <input type="file" id="cxFile" accept=".zip,.xml" style="margin:4px 0 8px 24px">
      <label class="check"><input type="radio" name="cxSrc" value="file"${ex.exports.length ? "" : " disabled"}> ${esc(t("cx.fromFile"))}</label>
      <select id="cxPath" style="margin:4px 0 8px 24px">${ex.exports.map((f) => `<option value="${esc(f.path)}">${esc(f.name)}</option>`).join("") || `<option>${esc(t("cx.none"))}</option>`}</select>
      <label class="check"><input type="radio" name="cxSrc" value="srv"${others.length ? "" : " disabled"}> ${esc(t("cx.fromSrv"))}</label>
      <select id="cxSrv" style="margin:4px 0 8px 24px">${others.map((x) => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("")}</select></div>
    <div class="field"><label>${t("cx.parts")}</label>
      ${["game", "panel", "admins"].map((p) => `<label class="check"><input type="checkbox" class="cxPart" value="${p}"${p === "admins" ? "" : " checked"}> ${esc(t("cx." + p))}</label>`).join("")}
      <div class="hint">${esc(t("cx.keep"))}</div></div>`);
  if (!await dialog(t("cx.import"), body, t("cx.import"))) return;
  const src = $("input[name=cxSrc]:checked").value, parts = $$(".cxPart:checked").map((x) => x.value);
  let r;
  if (src === "pc") {
    const f = $("#cxFile").files[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f); fd.append("parts", parts.join(","));
    r = await act(() => api("POST", sp("/import-config"), fd));
  } else r = await act(() => api("POST", sp("/import-config"), src === "file" ? { path: $("#cxPath").value, parts } : { from_server: $("#cxSrv").value, parts }));
  if (r) { toast(t("cx.done", { p: r.imported.join(", ") })); loadSettings(); }
}
// ------------------------------------------------------------------ mods
async function loadMods() {
  const el = $("#tab-mods");
  const d = await act(() => api("GET", sp("/mods")));
  if (!d) return;
  const gv = d.game || "?";
  const compatTag = (c) => c ? `<span class="tag ${c === "yes" ? "yes" : c === "no" ? "no" : "warnt"}">${esc(t("mods.compat." + c, { v: gv }))}</span>` : "";
  const checkInfo = (m) => {
    const c = m.check;
    if (!m.source) return `<span class="muted small">${esc(t("mods.noSource"))}</span>`;
    if (!c) return "";
    if (c.status === "nexus_key_needed") return `<span class="warn small">${esc(t("mods.nexusKey"))}</span>`;
    if (c.status === "none_compatible") return `<span class="err small">${esc(t("mods.noneCompat"))}</span>`;
    if (c.status === "error") return `<span class="err small">${esc(c.error)}</span>`;
    if (c.status !== "ok") return "";
    return c.update ? `<span class="warn small">${esc(t("mods.latest", { v: c.latest }))}</span> ${compatTag(c.compat)}` + (c.manual ? ` <a href="${esc(c.url)}" target="_blank" rel="noopener" class="small">${esc(t("mods.manual"))}</a>` : "")
      : `<span class="ok small">${esc(t("mods.uptodate"))}</span>`;
  };
  el.innerHTML = `<p class="muted">${esc(t("mods.hint"))} <span class="small">${esc(t("mods.eac"))}</span></p>
    <div class="row" style="margin-bottom:12px"><button class="primary" id="mZip">${t("mods.addZip")}</button>
      <input id="mUrl" placeholder="${esc(t("mods.urlPh"))}" style="flex:1;min-width:260px"><button id="mUrlBtn">${t("mods.addUrl")}</button>
      <button id="mCheck">${t("mods.checkAll")}</button></div>
    <div class="drop" id="mDrop">ZIP ⤓</div>
    ${d.mods.length ? `<table style="margin-top:12px"><tr><th>${t("mods.title")}</th><th>${t("mods.version")}</th><th>${t("mods.source")}</th><th></th></tr>
    ${d.mods.map((m, i) => `<tr><td><b>${esc(m.name)}</b> ${m.enabled ? "" : `<span class="tag">${t("mods.disabled")}</span>`}<div class="muted small">${esc(m.folder)} · ${fmtBytes(m.size)}${m.author ? " · " + esc(m.author) : ""}</div><div class="small">${esc(m.description).slice(0, 160)}</div></td>
      <td>${esc(m.version || "–")}${m.release ? `<div class="muted small">${esc(m.release)}</div>` : ""} ${compatTag(m.compat)}</td>
      <td>${m.source ? `<span class="small">${esc(m.source.url || m.source.repo || "")}</span>` : ""}<div>${checkInfo(m)}</div></td>
      <td class="row"><button class="small" data-src="${i}">${t("mods.source")}</button>${m.source ? `<button class="small" data-chk="${i}">${t("mods.find")}</button>` : ""}
        ${m.check?.update && !m.check.manual ? `<button class="small primary" data-upd="${i}">${t("act.update")}</button>` : ""}
        <button class="small" data-tog="${i}">${m.enabled ? t("act.disable") : t("act.enable")}</button><button class="small danger" data-del="${i}">${t("act.delete")}</button></td></tr>`).join("")}</table>`
    : `<p class="empty">${esc(t("mods.none"))}</p>`}`;
  const up = async (file) => { const fd = new FormData(); fd.append("file", file); if (await act(() => api("POST", sp("/mods/upload"), fd), t("ok.saved"))) loadMods(); };
  $("#mZip").onclick = () => pickFile(".zip", up);
  dropZone($("#mDrop"), up);
  $("#mUrlBtn").onclick = async () => { const v = $("#mUrl").value.trim(); if (v && await act(() => api("POST", sp("/mods/install"), { source: v }), t("ok.saved"))) loadMods(); };
  $("#mCheck").onclick = async () => { $("#mCheck").disabled = true; await act(() => api("POST", sp("/mods/check"))); loadMods(); };
  const mod = (b, k) => d.mods[b.dataset[k]];
  $$("[data-src]", el).forEach((b) => b.onclick = async () => { const m = mod(b, "src"); const v = await promptDlg(t("mods.source"), t("mods.sourcePh"), m.source?.url || ""); if (v !== null && await act(() => api("POST", sp(`/mods/${encodeURIComponent(m.folder)}/source`), { source: v }))) loadMods(); });
  $$("[data-chk]", el).forEach((b) => b.onclick = async () => { b.disabled = true; await act(() => api("POST", sp(`/mods/${encodeURIComponent(mod(b, "chk").folder)}/check`))); loadMods(); });
  $$("[data-upd]", el).forEach((b) => b.onclick = async () => {
    if (live()) return toast(t("mods.stopFirst"), true);
    b.disabled = true;
    const r = await act(() => api("POST", sp(`/mods/${encodeURIComponent(mod(b, "upd").folder)}/update`)));
    if (r) for (const x of r.report) { toast(t("mods.updateDone", { k: x.kept.length })); if (x.conflicts.length) toast(t("mods.conflicts", { n: x.conflicts.length }) + " " + x.conflicts.join(", "), true); }
    loadMods();
  });
  $$("[data-tog]", el).forEach((b) => b.onclick = async () => { await act(() => api("POST", sp(`/mods/${encodeURIComponent(mod(b, "tog").folder)}/toggle`))); loadMods(); });
  $$("[data-del]", el).forEach((b) => b.onclick = async () => { const m = mod(b, "del"); if (await confirmDlg(t("f.deleteQ", { n: m.name }))) { await act(() => api("POST", sp(`/mods/${encodeURIComponent(m.folder)}/delete`))); loadMods(); } });
}

// ------------------------------------------------------------------ backups
async function loadBackups() {
  const el = $("#tab-backups");
  const d = await act(() => api("GET", sp("/backups")));
  if (!d) return;
  el.innerHTML = `<div class="row op-only" style="margin-bottom:12px"><button class="primary" id="bkNew"${d.busy ? " disabled" : ""}>${t("bk.create")}</button><span class="busy">${esc(d.busy || "")}</span><span class="sp"></span><span class="muted small">${esc(d.path)}</span></div>
    ${d.backups.length ? `<table><tr><th>${t("f.name")}</th><th>${t("bk.kind")}</th><th class="num">${t("f.size")}</th><th>${t("f.changed")}</th><th></th></tr>
    ${d.backups.map((b, i) => `<tr><td>${esc(b.name)}</td><td><span class="tag">${esc(t("bk.kind." + b.kind))}</span></td><td class="num">${fmtBytes(b.size)}</td><td>${fmtTime(b.mtime)}</td>
      <td class="row"><a class="small admin-only" href="/api/files/download?path=${encodeURIComponent(d.path + "/" + b.name)}">${t("act.download")}</a><button class="small op-only" data-rs="${i}">${t("act.restore")}</button><button class="small danger admin-only" data-bd="${i}">${t("act.delete")}</button></td></tr>`).join("")}</table>`
    : `<p class="empty">${esc(t("bk.none"))}</p>`}`;
  $("#bkNew").onclick = async () => { await act(() => api("POST", sp("/backups/create")), t("ok.queued")); setTimeout(loadBackups, 1500); };
  $$("[data-rs]", el).forEach((b) => b.onclick = async () => { const n = d.backups[b.dataset.rs].name; if (await confirmDlg(t("bk.restoreQ", { n }))) { await act(() => api("POST", sp("/backups/restore"), { name: n }), t("ok.queued")); setTimeout(loadBackups, 1500); } });
  $$("[data-bd]", el).forEach((b) => b.onclick = async () => { const n = d.backups[b.dataset.bd].name; if (await confirmDlg(t("f.deleteQ", { n }))) { await act(() => api("POST", sp("/backups/delete"), { name: n })); loadBackups(); } });
}

// ------------------------------------------------------------------ files
let FPATH = null;
async function loadFiles(path) {
  const el = $("#tab-files");
  const d = await act(() => api("GET", "/api/files?path=" + encodeURIComponent(path)));
  if (!d) { if (path !== "/") loadFiles("/"); return; }
  FPATH = d.path;
  const parts = d.path.split("/").filter(Boolean);
  const crumbs = [`<a data-p="/">${esc(t("f.root"))}</a>`, ...parts.map((p, i) => `<a data-p="/${parts.slice(0, i + 1).join("/")}">${esc(p)}</a>`)].join(" / ");
  const full = (n) => (d.path === "/" ? "" : d.path) + "/" + n;
  el.innerHTML = `<div class="row" style="margin-bottom:10px"><div class="crumbs">${crumbs}</div><span class="sp"></span>
    <button class="small" id="fUp">${t("act.upload")}</button><button class="small" id="fMk">${t("f.newFolder")}</button></div>
    <table><tr><th>${t("f.name")}</th><th class="num">${t("f.size")}</th><th>${t("f.changed")}</th><th></th></tr>
    ${parts.length ? `<tr><td><span class="fname dir" data-p="/${parts.slice(0, -1).join("/")}">..</span></td><td></td><td></td><td></td></tr>` : ""}
    ${d.items.map((f, i) => `<tr><td><span class="fname${f.dir ? " dir" : ""}" data-i="${i}">${f.dir ? "📁 " : ""}${esc(f.name)}</span></td><td class="num">${f.dir ? "" : fmtBytes(f.size)}</td><td>${fmtTime(f.mtime)}</td>
      <td class="row">${f.dir ? "" : `<a class="small" href="/api/files/download?path=${encodeURIComponent(full(f.name))}">${t("act.download")}</a>`}
      ${/\.zip$/i.test(f.name) ? `<button class="small" data-x="${i}">${t("f.extract")}</button>` : ""}
      <button class="small" data-rn="${i}">${t("act.rename")}</button><button class="small danger" data-rm="${i}">${t("act.delete")}</button></td></tr>`).join("")}
    </table>${d.items.length ? "" : `<p class="empty">${esc(t("f.empty"))}</p>`}`;
  $$("[data-p]", el).forEach((a) => a.onclick = () => loadFiles(a.dataset.p || "/"));
  $$(".fname[data-i]", el).forEach((a) => a.onclick = () => { const f = d.items[a.dataset.i]; f.dir ? loadFiles(full(f.name)) : editFile(full(f.name)); });
  $$("[data-x]", el).forEach((b) => b.onclick = async () => { await act(() => api("POST", "/api/files/extract", { path: full(d.items[b.dataset.x].name) }), t("ok.saved")); loadFiles(d.path); });
  $$("[data-rn]", el).forEach((b) => b.onclick = async () => { const f = d.items[b.dataset.rn]; const n = await promptDlg(t("act.rename"), t("f.name"), f.name); if (n && n !== f.name) { await act(() => api("POST", "/api/files/rename", { path: full(f.name), newname: n })); loadFiles(d.path); } });
  $$("[data-rm]", el).forEach((b) => b.onclick = async () => { const f = d.items[b.dataset.rm]; if (await confirmDlg(t("f.deleteQ", { n: f.name }))) { await act(() => api("POST", "/api/files/delete", { path: full(f.name) })); loadFiles(d.path); } });
  $("#fMk").onclick = async () => { const n = await promptDlg(t("f.newFolder"), t("f.name")); if (n) { await act(() => api("POST", "/api/files/mkdir", { path: full(n) })); loadFiles(d.path); } };
  $("#fUp").onclick = () => pickFile("", async (file) => { const fd = new FormData(); fd.append("file", file); await act(() => api("POST", "/api/files/upload?path=" + encodeURIComponent(d.path), fd), t("ok.saved")); loadFiles(d.path); });
}
async function editFile(path) {
  const d = await act(() => api("GET", "/api/files/read?path=" + encodeURIComponent(path)));
  if (!d) return;
  const el = $("#tab-files");
  el.innerHTML = `<div class="row" style="margin-bottom:8px"><b class="crumbs">${esc(d.path)}</b><span class="sp"></span><button id="edBack">${t("act.back")}</button><button class="primary" id="edSave">${t("act.save")}</button></div>
    <textarea id="editor" spellcheck="false"></textarea>`;
  $("#editor").value = d.content;
  $("#edBack").onclick = () => loadFiles(d.path.replace(/\/[^/]*$/, "") || "/");
  $("#edSave").onclick = () => act(() => api("POST", "/api/files/write", { path: d.path, content: $("#editor").value }), t("f.saved"));
}

// ------------------------------------------------------------------ automation (schedule, updates, resources, backups)
async function loadAutomation() {
  const el = $("#tab-automation");
  const st = await act(() => api("GET", sp("/settings")));
  if (!st) return;
  const days = t("days").split(",");
  const sel = (key, opts) => `<select data-set="${key}">${opts.map(([v, lab]) => `<option value="${v}"${String(st[key]) === v ? " selected" : ""}>${esc(lab)}</option>`).join("")}</select>`;
  const num = (key, step = 1) => `<input type="number" step="${step}" min="0" data-set="${key}" value="${esc(st[key])}">`;
  const chk = (key, label) => `<label class="check"><input type="checkbox" data-set="${key}"${st[key] ? " checked" : ""}> ${esc(label)}</label>`;
  const field = (label, input, hint = "") => `<div class="field"><label>${esc(label)}</label>${input}${hint ? `<div class="hint">${esc(hint)}</div>` : ""}</div>`;
  const ruleRow = (r, i) => `<tr data-r="${i}"><td><input type="checkbox" class="rEn"${r.enabled ? " checked" : ""}></td>
    <td><div class="days">${days.map((dn, k) => `<label><input type="checkbox" value="${k + 1}"${r.days.includes(k + 1) ? " checked" : ""}>${esc(dn)}</label>`).join("")}</div></td>
    <td><input type="time" class="rTime" value="${esc(r.time)}"></td>
    <td><select class="rAct">${["start", "stop", "restart", "update_restart", "backup"].map((a) => `<option value="${a}"${r.action === a ? " selected" : ""}>${esc(a === "update_restart" || a === "backup" ? t("act." + a) : t("act." + a))}</option>`).join("")}</select></td>
    <td><input class="rWarn" value="${esc(r.warn.join(", "))}" placeholder="15, 5, 1" style="width:90px"></td>
    <td><input class="rMsg" value="${esc(r.message)}" style="width:100%"></td><td><button class="small danger rDel">✕</button></td></tr>`;
  let rules = st.schedule.map((r) => ({ ...r }));
  el.innerHTML = `
  <div class="card"><h3>${t("au.schedule")}</h3><p class="muted small">${esc(t("au.scheduleHint"))}</p>
    <table id="rules"><tr><th>${t("au.enabled")}</th><th>${t("au.days")}</th><th>${t("au.time")}</th><th>${t("au.action")}</th><th>${t("au.warn")}</th><th>${t("au.message")}</th><th></th></tr></table>
    <div class="row" style="margin-top:8px"><button id="rAdd">${t("au.addRule")}</button><span class="sp"></span><button class="primary" id="rSave">${t("act.save")}</button></div>
  </div>
  <div class="card"><h3>${t("au.updates")}</h3><div class="form-grid">
    ${field(t("au.gameUpdates"), sel("game_updates", ["off", "notify", "patch", "minor"].map((v) => [v, t("au.gu." + v)])), t("au.guHint"))}
    ${field(t("au.modUpdates"), sel("mod_updates", ["off", "notify", "auto"].map((v) => [v, t("au.mu." + v)])))}
    ${field(t("au.window"), sel("update_window", ["empty", "stopped", "restart"].map((v) => [v, t("au.w." + v)])))}
  </div><div class="row" style="margin-top:10px"><button id="chkNow">${t("au.checkNow")}</button></div></div>
  <div class="card"><h3>${t("au.resources")}</h3><div class="form-grid">
    ${field(t("au.ram"), num("ram_limit_gb", 0.5))}
    ${field(t("au.ramAction"), sel("ram_action", ["warn", "restart"].map((v) => [v, t("au.ra." + v)])))}
    ${field(t("au.cpus"), `<input data-set="server_cpus" value="${esc(st.server_cpus)}">`, t("au.cpusHint"))}
    ${field(t("au.backupCpus"), `<input data-set="backup_cpus" value="${esc(st.backup_cpus)}">`)}
  </div></div>
  <div class="card"><h3>${t("au.startup")}</h3><div class="form-grid">
    ${field(t("au.autostart"), sel("autostart", ["off", "always", "last"].map((v) => [v, t("au.as." + v)])))}
    ${field(t("au.shutdown"), num("shutdown_timeout"))}
    <div class="field">${chk("crash_restart", t("au.crash"))}</div>
  </div></div>
  <div class="card"><h3>${t("au.backups")}</h3><div class="form-grid">
    ${field(t("au.bInterval"), num("backup_interval_hours", 0.5))}${field(t("au.bKeep"), num("backup_keep"))}
    <div class="field">${chk("backup_include_worlds", t("au.bWorlds"))}${chk("backup_only_when_running", t("au.bRunning"))}</div>
  </div></div>
  <div class="card"><h3>${t("au.danger")}</h3><div class="row"><button id="srvRename">${t("act.rename")}</button><button class="danger" id="srvDel">${t("au.delete")}</button></div></div>`;
  const drawRules = () => {
    $$("#rules tr[data-r]").forEach((r) => r.remove());
    $("#rules").insertAdjacentHTML("beforeend", rules.map(ruleRow).join("") || `<tr data-r><td colspan="7" class="empty">${esc(t("au.noRules"))}</td></tr>`);
    $$("#rules .rDel").forEach((b) => b.onclick = () => { collect(); rules.splice(+b.closest("tr").dataset.r, 1); drawRules(); });
  };
  const collect = () => {
    rules = $$("#rules tr[data-r]").filter((tr) => tr.dataset.r !== "").map((tr) => ({
      id: rules[+tr.dataset.r]?.id, enabled: $(".rEn", tr).checked, days: $$(".days input:checked", tr).map((x) => +x.value),
      time: $(".rTime", tr).value, action: $(".rAct", tr).value, message: $(".rMsg", tr).value,
      warn: $(".rWarn", tr).value.split(/[ ,;]+/).filter(Boolean).map(Number).filter((x) => x > 0) }));
  };
  drawRules();
  $("#rAdd").onclick = () => { collect(); rules.push({ enabled: true, days: [1, 2, 3, 4, 5, 6, 7], time: "05:00", action: "restart", warn: [15, 5, 1], message: "" }); drawRules(); };
  $("#rSave").onclick = async () => { collect(); if (await act(() => api("POST", sp("/settings"), { schedule: rules }), t("ok.saved"))) loadAutomation(); };
  $$("[data-set]", el).forEach((inp) => inp.onchange = () => {
    const v = inp.type === "checkbox" ? inp.checked : inp.value;
    act(() => api("POST", sp("/settings"), { [inp.dataset.set]: v }), t("ok.saved"));
  });
  $("#chkNow").onclick = async () => { $("#chkNow").disabled = true; await act(() => api("POST", "/api/updates/check")); $("#chkNow").disabled = false; loadOverview(); };
  $("#srvRename").onclick = async () => { const n = await promptDlg(t("act.rename"), t("new.name"), S.status.name); if (n) { await act(() => api("POST", sp("/rename"), { name: n })); loadOverview(); } };
  $("#srvDel").onclick = async () => {
    const n = await promptDlg(t("au.delete"), t("au.deleteQ", { n: S.status.name }));
    if (n !== null && await act(() => api("POST", sp("/delete"), { confirm: n }))) { await loadOverview(); selectServer(OV.instances[0]?.id); }
  };
}

// ------------------------------------------------------------------ new server
async function newServerDialog() {
  if (!VERS) await getVersions().catch(() => null);
  const body = h(`<p class="muted small">${esc(t("new.hint"))}</p>
    <div class="field"><label>${t("new.name")}</label><input id="nName" maxlength="40"></div>
    <div class="field"><label>${t("new.version")}</label><select id="nVer">${versionOptions("public")}</select></div>
    <div class="field"><label>${t("new.clone")}</label><select id="nClone"><option value="">${esc(t("new.none"))}</option>${OV.instances.map((i) => `<option value="${esc(i.id)}">${esc(i.name)}</option>`).join("")}</select></div>`);
  if (!await dialog(t("new.title"), body, t("act.add"))) return;
  const r = await act(() => api("POST", "/api/servers", { name: $("#nName").value, game_version: $("#nVer").value, clone_from: $("#nClone").value }));
  if (r) { await loadOverview(); selectServer(r.id); }
}

// ------------------------------------------------------------------ page: game versions
async function pageVersions() {
  const el = $("#pageView");
  el.innerHTML = `<h2>${t("gv.title")}</h2><p class="muted">…</p>`;
  let d;
  try { d = await getVersions(); } catch (e) { el.innerHTML += `<p class="err">${esc(e.message)}</p>`; return; }
  if (PAGE !== pageVersions) return;
  const exp = (b) => /experimental|unstable|latest_/i.test(b.name + b.description);
  el.innerHTML = `<h2>${t("gv.title")}</h2><p class="muted">${esc(t("gv.hint"))}</p>
    ${d.error ? `<div class="alert major">${esc(d.error)}</div>` : ""}
    <div class="row" style="margin-bottom:10px"><button id="gvRefresh">${t("gv.refresh")}</button><span class="muted small">${d.fetched ? esc(t("gv.fetched", { t: fmtTime(d.fetched) })) : ""}</span>
      ${d.busy ? `<span class="busy">SteamCMD ${esc(d.busy)} ${d.progress ?? 0} %</span>` : ""}</div>
    <table><tr><th>${t("gv.branch")}</th><th>${t("gv.version")}</th><th>${t("gv.build")}</th><th>${t("gv.usedBy")}</th><th></th></tr>
    ${d.branches.filter((b) => !b.password).map((b, i) => `<tr><td><b>${esc(b.name)}</b> ${exp(b) ? `<span class="tag warnt">${t("gv.experimental")}</span>` : ""}<div class="muted small">${esc(b.description)}</div></td>
      <td>${esc(b.version || "?")}</td><td>${esc(b.installed_build || b.build || "")}${b.update?.available ? ` <span class="tag warnt">${esc(t("gv.update", { b: b.update.target || b.update.build }))}</span>` : ""}</td>
      <td>${esc((b.used_by || []).join(", "))}</td>
      <td class="row">${d.queued.includes(b.name) || d.busy === b.name ? `<span class="busy">${t("gv.queued")}</span>` :
        b.installed ? `${b.update?.available ? `<button class="small primary" data-gu="${i}">${t("act.update")}</button>` : `<span class="tag on">${t("gv.installed")}</span>`}
          <button class="small" data-gv="${i}">${t("act.validate")}</button>${(b.used_by || []).length ? "" : `<button class="small danger" data-gr="${i}">${t("act.remove")}</button>`}`
        : `<button class="small" data-gi="${i}">${t("act.install")}</button>`}</td></tr>`).join("")}</table>`;
  const list = d.branches.filter((b) => !b.password);
  const run = (b, a) => act(() => api("POST", `/api/versions/${encodeURIComponent(b.name)}/${a}`), t("ok.queued")).then(() => setTimeout(() => PAGE === pageVersions && pageVersions(), 800));
  $("#gvRefresh").onclick = async () => { await act(() => getVersions(true)); pageVersions(); };
  $$("[data-gi]", el).forEach((x) => x.onclick = () => run(list[x.dataset.gi], "install"));
  $$("[data-gv]", el).forEach((x) => x.onclick = () => run(list[x.dataset.gv], "validate"));
  $$("[data-gu]", el).forEach((x) => x.onclick = async () => { const b = list[x.dataset.gu]; if (b.update.kind !== "major" || await confirmDlg(t("kind.major"))) run(b, "update"); });
  $$("[data-gr]", el).forEach((x) => x.onclick = async () => { const b = list[x.dataset.gr]; if (await confirmDlg(t("gv.removeQ", { b: b.name }))) run(b, "remove"); });
  if (d.busy || d.queued.length) setTimeout(() => PAGE === pageVersions && pageVersions(), 3000);
}

// ------------------------------------------------------------------ page: panel settings
async function pagePanel() {
  const el = $("#pageView");
  const g = isAdmin() ? await act(() => api("GET", "/api/global")) : { self_update: {} };
  if (!g || PAGE !== pagePanel) return;
  const users = isAdmin() ? await act(() => api("GET", "/api/users")) : null;
  const su = g.self_update || {};
  el.innerHTML = `<h2>${t("p.title")}</h2>
  ${users ? usersCard(users) : ""}
  <div class="card admin-only"><h3>${t("p.self")}</h3>
    <p>${esc(t("p.version", { v: OV.panel?.version }))}${OV.panel?.update ? ` → <b>${esc(OV.panel.update.version)}</b> <a href="${esc(OV.panel.update.url)}" target="_blank" rel="noopener">changelog</a>` : ""}</p>
    <div class="form-grid"><div class="field"><label>${t("p.selfPolicy")}</label><select id="spPol">${["auto", "notify", "off"].map((v) => `<option value="${v}"${su.policy === v ? " selected" : ""}>${esc(t("p.sp." + v))}</option>`).join("")}</select></div>
      <div class="field"><label>${t("p.version2")}</label><div class="row"><select id="spVer" style="flex:1"><option value="latest">${esc(t("p.latest"))}</option></select><button id="spVerBtn">${t("act.apply")}</button></div>
        <div class="hint" id="spVerHint">${esc(t("p.versionHint"))}</div></div></div>
    ${su.updater ? `<div class="row" style="margin-top:10px"><button id="spNow"${OV.panel?.update ? ' class="primary"' : ""}>${t("p.selfNow")}</button></div>` : `<p class="muted small">${esc(t("p.selfNoUpdater"))}</p>`}
  </div>
  <div class="card"><h3>${t("p.password")} <span class="muted small">(${esc(ME.name)})</span></h3>${g.password_env && ME.name === "admin" ? `<p class="muted">${esc(t("p.pwEnv"))}</p>` : `
    <div class="form-grid"><div class="field"><label>${t("p.current")}</label><input type="password" id="pwCur" autocomplete="current-password"></div>
    <div class="field"><label>${t("p.new")}</label><input type="password" id="pwNew" autocomplete="new-password"></div></div>
    <div class="row" style="margin-top:10px"><button class="primary" id="pwSave">${t("act.save")}</button></div>`}</div>
  <div class="card admin-only"><h3>${t("p.tokens")}</h3><div class="form-grid">
    <div class="field"><label>${t("p.github")} <span class="tag${g.github_token_set ? " on" : ""}">${t(g.github_token_set ? "p.set" : "p.notset")}</span></label><input type="password" id="tkGh" autocomplete="off"></div>
    <div class="field"><label>${t("p.nexus")} <span class="tag${g.nexus_key_set ? " on" : ""}">${t(g.nexus_key_set ? "p.set" : "p.notset")}</span></label><input type="password" id="tkNx" autocomplete="off"></div>
  </div><div class="row" style="margin-top:10px"><button class="primary" id="tkSave">${t("act.save")}</button></div></div>
  <div class="card"><h3>${t("p.lang")}</h3><select class="lang-pick"></select></div>
  <div class="card"><h3>${t("p.about")}</h3><p class="muted small">7edCore · <a href="https://github.com/${esc(OV.panel?.repo || "Koberecnikos/7edCore")}" target="_blank" rel="noopener">GitHub</a></p></div>`;
  initLangPickers();
  if (users) bindUsers(users);
  if (!isAdmin()) { const pw0 = $("#pwSave"); if (pw0) pw0.onclick = () => act(() => api("POST", "/api/password", { current: $("#pwCur").value, new: $("#pwNew").value }), t("p.pwChanged")); return; }
  $("#spPol").onchange = () => act(() => api("POST", "/api/selfupdate", { policy: $("#spPol").value }), t("ok.saved"));
  api("GET", "/api/selfupdate/releases").then((r) => {
    const sel = $("#spVer"); if (!sel) return;
    sel.insertAdjacentHTML("beforeend", r.releases.map((x) => `<option value="${esc(x.version)}">${esc(x.version)}${x.version === r.current ? " · " + esc(t("p.running")) : ""}${x.prerelease ? " (pre-release)" : ""} - ${esc((x.published || "").slice(0, 10))}</option>`).join(""));
    sel.value = su.version || "latest";
    sel.onchange = () => {
      const x = r.releases.find((q) => q.version === sel.value);
      $("#spVerHint").innerHTML = x ? `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a> · ${esc(x.notes.split("\n").filter(Boolean).slice(0, 6).join(" · "))}` : esc(t("p.versionHint"));
    };
  }).catch(() => {});
  $("#spVerBtn").onclick = async () => {
    const v = $("#spVer").value, cur = OV.panel?.version || "";
    const older = v !== "latest" && /^\d/.test(cur) && v.split(".").map(Number).join(".") !== cur && v.localeCompare(cur, undefined, { numeric: true }) < 0;
    if (older && !await confirmDlg(t("p.downgradeQ", { v, c: cur }))) return;
    act(() => api("POST", "/api/selfupdate", { version: v }), t("p.selfRequested"));
  };
  const now = $("#spNow"); if (now) now.onclick = () => act(() => api("POST", "/api/selfupdate/now"), t("p.selfRequested"));
  const pw = $("#pwSave"); if (pw) pw.onclick = () => act(() => api("POST", "/api/password", { current: $("#pwCur").value, new: $("#pwNew").value }), t("p.pwChanged"));
  $("#tkSave").onclick = async () => {
    const b = {}; if ($("#tkGh").value) b.github_token = $("#tkGh").value; if ($("#tkNx").value) b.nexus_key = $("#tkNx").value;
    if (await act(() => api("POST", "/api/global", b), t("ok.saved"))) pagePanel();
  };
}

// ------------------------------------------------------------------ users (admin)
function serverChecks(cls, sel) {
  const all = sel === "*";
  return `<label class="check"><input type="checkbox" class="${cls}-all"${all ? " checked" : ""}> ${esc(t("u.allServers"))}</label>
    <div class="${cls}-list"${all ? " hidden" : ""}>${OV.instances.map((i) => `<label class="check"><input type="checkbox" class="${cls}" value="${esc(i.id)}"${!all && sel.includes(i.id) ? " checked" : ""}> ${esc(i.name)}</label>`).join("")}</div>`;
}
function readServers(root, cls) {
  return $(`.${cls}-all`, root).checked ? "*" : $$(`.${cls}:checked`, root).map((x) => x.value);
}
function usersCard(d) {
  return `<div class="card"><h3>${t("u.title")}</h3><p class="muted small">${esc(t("u.hint"))}</p>
    <table><tr><th>${t("u.name")}</th><th>${t("u.role")}</th><th>${t("u.servers")}</th><th></th></tr>
    ${d.users.map((u, i) => `<tr data-u="${i}"><td><b>${esc(u.name)}</b>${u.name === ME.name ? ` <span class="tag on">${esc(t("u.you"))}</span>` : ""}</td>
      <td><select class="uRole">${d.roles.map((r) => `<option value="${r}"${r === u.role ? " selected" : ""}>${esc(t("role." + r))}</option>`).join("")}</select></td>
      <td>${u.role === "admin" ? `<span class="muted small">${esc(t("u.allServers"))}</span>` : serverChecks("uSrv" + i, u.servers)}</td>
      <td class="row"><button class="small uPw">${t("u.resetPw")}</button>${u.name === ME.name ? "" : `<button class="small danger uDel">${t("act.delete")}</button>`}</td></tr>`).join("")}</table>
    <h4>${t("u.add")}</h4><div class="form-grid" id="uNew">
      <div class="field"><label>${t("u.name")}</label><input id="nuName" autocomplete="off"></div>
      <div class="field"><label>${t("p.new")}</label><input id="nuPw" type="password" autocomplete="new-password"></div>
      <div class="field"><label>${t("u.role")}</label><select id="nuRole">${d.roles.map((r) => `<option value="${r}"${r === "operator" ? " selected" : ""}>${esc(t("role." + r))}</option>`).join("")}</select>
        <div class="hint">${esc(t("u.roleHint"))}</div></div>
      <div class="field"><label>${t("u.servers")}</label>${serverChecks("nuSrv", "*")}</div>
    </div><div class="row" style="margin-top:10px"><button class="primary" id="nuAdd">${t("act.add")}</button></div></div>`;
}
function bindUsers(d) {
  const toggleAll = (root, cls) => { const a = $(`.${cls}-all`, root); if (a) a.onchange = () => { $(`.${cls}-list`, root).hidden = a.checked; a.dispatchEvent(new Event("saved")); }; };
  $$("tr[data-u]").forEach((tr) => {
    const i = +tr.dataset.u, u = d.users[i], cls = "uSrv" + i;
    const save = (body) => act(() => api("POST", `/api/users/${encodeURIComponent(u.name)}`, body), t("ok.saved")).then(() => pagePanel());
    $(".uRole", tr).onchange = (e) => save({ role: e.target.value });
    toggleAll(tr, cls);
    $$(`.${cls}, .${cls}-all`, tr).forEach((c) => c.addEventListener("change", () => act(() => api("POST", `/api/users/${encodeURIComponent(u.name)}`, { servers: readServers(tr, cls) }), t("ok.saved"))));
    $(".uPw", tr).onclick = async () => { const pw = await promptDlg(t("u.resetPw") + ": " + u.name, t("p.new")); if (pw) save({ password: pw }); };
    const del = $(".uDel", tr); if (del) del.onclick = async () => { if (await confirmDlg(t("u.deleteQ", { n: u.name }))) act(() => api("POST", `/api/users/${encodeURIComponent(u.name)}/delete`), t("ok.saved")).then(() => pagePanel()); };
  });
  toggleAll($("#uNew"), "nuSrv");
  $("#nuAdd").onclick = async () => {
    const r = await act(() => api("POST", "/api/users", { username: $("#nuName").value.trim(), password: $("#nuPw").value, role: $("#nuRole").value, servers: readServers($("#uNew"), "nuSrv") }), t("ok.saved"));
    if (r) pagePanel();
  };
}

// ------------------------------------------------------------------ start
applyI18n();
initLangPickers();
boot();
