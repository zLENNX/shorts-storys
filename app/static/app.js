const $app = document.getElementById("app");
let pollTimer = null;
let statusCache = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function toast(msg, ms = 3500) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.style.display = "block";
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.style.display = "none"), ms);
}

function badge(status) {
  const cls = { gerendert: "ok", bereit: "ok", freigegeben: "ok", fertig: "ok", fehler: "err", rendert: "warn", schreibt: "warn", offen: "" }[status] ?? "";
  return `<span class="badge ${cls}">${esc(status)}</span>`;
}

function fmtDate(d) {
  if (!d) return "–";
  const [y, m, day] = d.split("-");
  return `${day}.${m}.${y}`;
}

// ---------------- Router ----------------
async function route() {
  clearInterval(pollTimer);
  const hash = location.hash.slice(1) || "ideen";
  const [tab, id] = hash.split("/");
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("active", a.dataset.tab === (tab === "serie" ? "serien" : tab)));
  try {
    if (tab === "ideen") await viewIdeas();
    else if (tab === "serien") await viewSeriesList();
    else if (tab === "serie") await viewSeries(+id);
    else if (tab === "plan") await viewPlan();
    else if (tab === "einstellungen") await viewSettings();
  } catch (e) {
    $app.innerHTML = `<div class="card err">${esc(e.message)}</div>`;
  }
}
window.addEventListener("hashchange", route);

// ---------------- Ideen ----------------
async function viewIdeas() {
  const ideas = await api("/api/ideas");
  $app.innerHTML = `
    <h2>Story-Ideen</h2>
    <div class="card">
      <div class="row">
        <div style="flex:1;min-width:240px"><label>Genres (optional)</label>
          <input id="genres" placeholder="z. B. Horror, True Crime, Mystery – leer = gemischt"></div>
        <div style="width:110px"><label>Anzahl</label><input id="count" type="number" value="8" min="3" max="10"></div>
        <div style="align-self:flex-end"><button class="primary" id="gen">✨ Ideen erzeugen</button></div>
      </div>
      <p class="muted small">Claude erzeugt Ideen mit Hook-Bewertung. Du wählst eine aus, erst dann wird die ganze Serie geschrieben und geschnitten.</p>
    </div>
    <div class="grid">${ideas.map(ideaCard).join("") || '<p class="muted">Noch keine Ideen. Klicke auf „Ideen erzeugen“.</p>'}</div>`;
  document.getElementById("gen").onclick = async (ev) => {
    ev.target.disabled = true;
    ev.target.innerHTML = '<span class="spin"></span> Claude denkt nach …';
    try {
      await api("/api/ideas", { method: "POST", body: { count: +document.getElementById("count").value, genres: document.getElementById("genres").value } });
      await viewIdeas();
    } catch (e) { toast(e.message, 6000); ev.target.disabled = false; ev.target.textContent = "✨ Ideen erzeugen"; }
  };
  document.querySelectorAll("[data-make]").forEach((b) => (b.onclick = async () => {
    const wish = document.getElementById("wish-" + b.dataset.make).value;
    b.disabled = true;
    try {
      const r = await api("/api/series", { method: "POST", body: { idea_id: +b.dataset.make, wish } });
      location.hash = "serie/" + r.id;
    } catch (e) { toast(e.message, 6000); b.disabled = false; }
  }));
  document.querySelectorAll("[data-drop]").forEach((b) => (b.onclick = async () => {
    await api("/api/ideas/" + b.dataset.drop, { method: "DELETE" });
    viewIdeas();
  }));
}

function ideaCard(i) {
  const d = i.data;
  return `<div class="card">
    <div class="row" style="justify-content:space-between">
      <span class="badge">${esc(d.genre)}${d.is_fiction ? " · Fiktion" : " · Fakten"}</span>
      <span class="score">${esc(d.hook_score)}/10</span>
    </div>
    <h3 style="margin:8px 0 4px">${esc(d.title)}</h3>
    <p>${esc(d.pitch)}</p>
    <p class="small"><b>Hook:</b> „${esc(d.hook)}“</p>
    <p class="small muted"><b>Cliffhanger:</b> ${esc(d.cliffhanger_plan)}</p>
    <p class="small muted">${esc(d.parts_count)} Teile</p>
    <input id="wish-${i.id}" placeholder="Optionaler Wunsch (z. B. düsterer, Ende offen …)">
    <div class="row" style="margin-top:10px">
      <button class="primary" data-make="${i.id}">🎬 Serie erstellen</button>
      <button data-drop="${i.id}">Verwerfen</button>
    </div>
  </div>`;
}

// ---------------- Serienliste ----------------
async function viewSeriesList() {
  const list = await api("/api/series");
  $app.innerHTML = `<h2>Serien</h2>
    ${list.length ? `<table><tr><th>Titel</th><th>Genre</th><th>Status</th><th>Teile</th><th></th></tr>
      ${list.map((s) => `<tr>
        <td><a href="#serie/${s.id}" style="color:var(--accent)">${esc(s.data.title)}</a></td>
        <td>${esc(s.data.genre || "")}</td><td>${badge(s.status)}</td>
        <td>${s.n_done}/${s.n_parts || "?"}</td>
        <td><a class="btn" href="#serie/${s.id}">Öffnen</a></td></tr>`).join("")}</table>`
      : '<p class="muted">Noch keine Serien. Wähle unter „Ideen“ eine Idee aus.</p>'}`;
  if (list.some((s) => ["schreibt", "rendert"].includes(s.status))) pollTimer = setInterval(viewSeriesList, 4000);
}

// ---------------- Serie / Review ----------------
async function viewSeries(sid) {
  const s = await api("/api/series/" + sid);
  if (!statusCache) statusCache = await api("/api/status");
  const voices = statusCache.voices;
  const locked = ["freigegeben", "fertig"].includes(s.status);
  const allRendered = s.parts.length && s.parts.every((p) => p.status === "gerendert");

  $app.innerHTML = `
    <div class="row" style="justify-content:space-between">
      <h2 style="margin:0">${esc(s.data.title)} ${badge(s.status)} ${s.busy ? '<span class="spin"></span>' : ""}</h2>
      <div class="row">
        ${locked
          ? `<button id="unapprove">Plan zurücknehmen</button>`
          : `<button class="primary" id="approve" ${!allRendered || s.busy ? "disabled" : ""}>✅ Serie freigeben</button>`}
        <button class="danger" id="delete">Löschen</button>
      </div>
    </div>
    <p class="muted">${esc(s.data.genre || "")} ${s.data.is_fiction ? "· Fiktion" : "· basiert auf Fakten"} · Musik-Stimmung: ${esc(s.data.mood || "–")}</p>
    ${s.error ? `<div class="card err">${esc(s.error)}</div>` : ""}
    ${s.status === "schreibt" ? '<div class="card"><span class="spin"></span> Claude schreibt die Serie … (ca. 1–2 Minuten)</div>' : ""}
    <div class="card row">
      <div><label>Stimme</label><select id="voice" ${locked ? "disabled" : ""}>${voices.map(([v, n]) => `<option value="${v}" ${v === s.voice ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></div>
      <div><label>Tempo</label><select id="rate" ${locked ? "disabled" : ""}>${["-10%", "+0%", "+8%", "+15%", "+25%"].map((r) => `<option ${r === s.rate ? "selected" : ""}>${r}</option>`).join("")}</select></div>
      <div style="align-self:flex-end"><button id="rerender" ${locked || s.busy ? "disabled" : ""}>🔁 Alle Teile neu vertonen &amp; rendern</button></div>
    </div>
    ${s.parts.map((p) => partView(p, s.parts.length, locked)).join("")}`;

  const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
  on("approve", async () => {
    if (!confirm("Serie freigeben? Die Teile werden ab dem nächsten freien Tag täglich um " + statusCache.post_time + " veröffentlicht.")) return;
    try { await api(`/api/series/${sid}/approve`, { method: "POST" }); toast("Freigegeben! Siehe Tab „Plan“."); viewSeries(sid); } catch (e) { toast(e.message, 6000); }
  });
  on("unapprove", async () => { await api(`/api/series/${sid}/unapprove`, { method: "POST" }); viewSeries(sid); });
  on("delete", async () => {
    if (!confirm("Serie wirklich löschen? (Bereits hochgeladene Videos bleiben auf den Plattformen.)")) return;
    await api(`/api/series/${sid}`, { method: "DELETE" }); location.hash = "serien";
  });
  on("rerender", async () => {
    await api(`/api/series/${sid}`, { method: "PUT", body: { voice: val("voice"), rate: val("rate") } });
    await api(`/api/series/${sid}/rerender`, { method: "POST" }); viewSeries(sid);
  });
  ["voice", "rate"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.onchange = () => api(`/api/series/${sid}`, { method: "PUT", body: { [id]: el.value } }).then(() => toast("Gespeichert. Zum Anwenden: neu vertonen."));
  });

  s.parts.forEach((p) => {
    on(`save-${p.id}`, async () => {
      const r = await api(`/api/parts/${p.id}`, { method: "PUT", body: collectPart(p) });
      if (r.needs_render) { await api(`/api/parts/${p.id}/render`, { method: "POST" }); toast("Gespeichert, Teil wird neu gerendert …"); }
      else toast("Gespeichert.");
      viewSeries(sid);
    });
    on(`render-${p.id}`, async () => { await api(`/api/parts/${p.id}/render`, { method: "POST" }); viewSeries(sid); });
    on(`regen-${p.id}`, async () => {
      const wish = prompt("Teil komplett neu schreiben lassen. Optionaler Wunsch an Claude:", "");
      if (wish === null) return;
      await api(`/api/parts/${p.id}/regenerate`, { method: "POST", body: { wish } }); viewSeries(sid);
    });
    p.data.scenes.forEach((_, i) => on(`swap-${p.id}-${i}`, async () => {
      await api(`/api/parts/${p.id}/scenes/${i}/swap`, { method: "POST" }); toast("Anderer Clip wird gesucht …"); viewSeries(sid);
    }));
  });

  if (s.busy || ["schreibt", "rendert"].includes(s.status)) {
    // Nur neu zeichnen, wenn sich ein Status geändert hat (damit Eingaben nicht verloren gehen)
    const sig = (x) => JSON.stringify([x.status, x.busy, x.parts.map((p) => [p.status, p.video_path])]);
    const before = sig(s);
    pollTimer = setInterval(async () => {
      const now = await api("/api/series/" + sid).catch(() => null);
      if (now && sig(now) !== before) viewSeries(sid);
    }, 4000);
  }
}

const val = (id) => document.getElementById(id)?.value;

function collectPart(p) {
  return {
    yt_title: val(`title-${p.id}`),
    description: val(`desc-${p.id}`),
    hashtags: val(`tags-${p.id}`).split(/[\s,]+/).map((t) => t.replace(/^#/, "")).filter(Boolean),
    scenes: p.data.scenes.map((_, i) => ({
      text: val(`sc-${p.id}-${i}`),
      keywords: val(`kw-${p.id}-${i}`).split(",").map((k) => k.trim()).filter(Boolean),
    })),
  };
}

function partView(p, total, locked) {
  const d = p.data;
  const dis = locked ? "disabled" : "";
  const video = p.status === "gerendert"
    ? `<video controls preload="metadata" src="/video/${p.id}?t=${Date.now()}"></video>`
    : `<div class="placeholder">${p.status === "rendert" ? '<span class="spin"></span>&nbsp; wird erstellt …' : p.status === "fehler" ? "Fehler" : "noch nicht gerendert"}</div>`;
  return `<div class="card">
    <h3 style="margin-top:0">Teil ${p.idx + 1}/${total} – ${esc(d.part_title || "")} ${badge(p.status)}
      ${p.scheduled_date ? `<span class="badge">📅 ${fmtDate(p.scheduled_date)}</span>` : ""}
      ${p.yt_video_id ? `<a class="badge ok" target="_blank" href="https://youtube.com/shorts/${p.yt_video_id}">YouTube ✓</a>` : ""}
      ${p.tiktok_publish_id ? `<span class="badge ok">TikTok-Entwurf ✓</span>` : ""}</h3>
    ${p.error ? `<div class="err">${esc(p.error)}</div>` : ""}
    <div class="part">
      <div>${video}</div>
      <div>
        <label>Titel</label><input id="title-${p.id}" value="${esc(d.yt_title)}" ${dis}>
        <label>Beschreibung</label><textarea id="desc-${p.id}" ${dis}>${esc(d.description)}</textarea>
        <label>Hashtags</label><input id="tags-${p.id}" value="${esc((d.hashtags || []).map((h) => "#" + h.replace(/^#/, "")).join(" "))}" ${dis}>
        <label>Szenen (Sprechtext + englische Suchbegriffe für den Clip)</label>
        ${d.scenes.map((sc, i) => `<div class="scene">
          <textarea id="sc-${p.id}-${i}" rows="2" ${dis}>${esc(sc.text)}</textarea>
          <div class="row">
            <input id="kw-${p.id}-${i}" style="flex:1" value="${esc(sc.keywords.join(", "))}" ${dis}>
            <button id="swap-${p.id}-${i}" ${dis} title="Anderen Clip für diese Szene">🔀 Clip</button>
          </div>
          <div class="small muted">${sc.clip ? `Clip: ${esc(sc.clip.source)} – ${esc(sc.clip.credit || sc.clip.id)}` : "noch kein Clip"}</div>
        </div>`).join("")}
        <div class="row" style="margin-top:10px">
          <button class="primary" id="save-${p.id}" ${dis}>💾 Speichern</button>
          <button id="render-${p.id}" ${dis}>🔁 Neu vertonen &amp; rendern</button>
          <button id="regen-${p.id}" ${dis}>✍️ Teil neu schreiben</button>
        </div>
      </div>
    </div>
  </div>`;
}

// ---------------- Plan ----------------
async function viewPlan() {
  const rows = await api("/api/schedule");
  const st = await api("/api/status");
  $app.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">Veröffentlichungsplan</h2>
      <button id="run">⟳ Jetzt prüfen &amp; hochladen</button></div>
    <p class="muted">Jeden Tag um ${esc(st.post_time)} Uhr ein Teil. YouTube wird im Voraus geplant hochgeladen.
      TikTok bekommt den Teil am jeweiligen Tag als Entwurf (die App muss dafür laufen) → in der TikTok-App auf „Posten“ tippen.</p>
    <div class="card">${rows.length ? `<table><tr><th>Datum</th><th>Teil</th><th>YouTube</th><th>TikTok</th><th></th></tr>
      ${rows.map((r) => `<tr>
        <td>${fmtDate(r.date)}</td>
        <td><a href="#serie/${r.sid}" style="color:var(--accent)">${esc(r.title)}</a><div class="small muted">${esc(r.series)}</div></td>
        <td>${r.yt ? `<a class="badge ok" target="_blank" href="https://youtube.com/shorts/${r.yt}">geplant ✓</a>` : r.yt_error ? `<span class="badge err" title="${esc(r.yt_error)}">Fehler</span>` : '<span class="badge">wartet</span>'}</td>
        <td>${r.tiktok ? '<span class="badge ok">Entwurf ✓</span>' : r.tiktok_error ? `<span class="badge err" title="${esc(r.tiktok_error)}">Fehler</span>` : '<span class="badge">wartet</span>'}</td>
        <td><button data-copy="${r.id}" title="Text für TikTok kopieren">📋 TikTok-Text</button>
            ${!r.tiktok ? `<button data-tt="${r.id}">Jetzt an TikTok</button>` : ""}</td></tr>`).join("")}</table>`
      : '<p class="muted">Noch nichts geplant. Gib eine fertige Serie frei.</p>'}</div>
    <h3>Protokoll</h3><pre class="log">${esc(st.log.join("\n")) || "–"}</pre>`;
  document.getElementById("run").onclick = async () => { await api("/api/schedule/run", { method: "POST" }); toast("Wird geprüft …"); setTimeout(viewPlan, 5000); };
  document.querySelectorAll("[data-copy]").forEach((b) => (b.onclick = () => {
    const r = rows.find((x) => x.id == b.dataset.copy);
    const text = `${r.title}\n${r.description}\n${r.hashtags.map((h) => "#" + h).join(" ")}`;
    navigator.clipboard.writeText(text).then(() => toast("Kopiert – in TikTok einfügen."));
  }));
  document.querySelectorAll("[data-tt]").forEach((b) => (b.onclick = async () => {
    b.disabled = true;
    try { await api(`/api/parts/${b.dataset.tt}/tiktok_now`, { method: "POST" }); toast("An TikTok gesendet."); viewPlan(); }
    catch (e) { toast(e.message, 6000); b.disabled = false; }
  }));
}

// ---------------- Einstellungen ----------------
async function viewSettings() {
  const st = (statusCache = await api("/api/status"));
  const chk = (ok, txt) => `<span class="badge ${ok ? "ok" : "err"}">${ok ? "✓" : "✗"}</span> ${txt}`;
  $app.innerHTML = `<h2>Einstellungen &amp; Konten</h2>
    <div class="grid">
      <div class="card"><h3>YouTube</h3>
        <p>${chk(st.youtube.connected, esc(st.youtube.info))}</p>
        ${st.youtube.connected ? `<button data-disc="youtube">Trennen</button>` : `<a class="btn primary" href="/auth/youtube">Mit YouTube verbinden</a>`}
        <p class="small muted">Anleitung: docs/YOUTUBE.md</p></div>
      <div class="card"><h3>TikTok</h3>
        <p>${chk(st.tiktok.connected, esc(st.tiktok.info))}</p>
        ${st.tiktok.connected ? `<button data-disc="tiktok">Trennen</button>` : `<a class="btn primary" href="/auth/tiktok">Mit TikTok verbinden</a>`}
        <p class="small muted">Anleitung: docs/TIKTOK.md</p></div>
      <div class="card"><h3>System</h3>
        <p>${chk(st.ffmpeg, "FFmpeg")}</p>
        <p>${chk(st.claude, "Claude-API-Key")}</p>
        <p>${chk(st.pexels || st.pixabay, "Stock-Videos (Pexels/Pixabay-Key)")}</p>
        <p>${chk(st.piper, "Piper (Ersatzstimme, optional)")}</p>
        <p class="small muted">Eigene Clips in library/: ${st.library_count} · Musik in music/: ${st.music_count}</p>
        <p class="small muted">Postzeit: ${esc(st.post_time)} Uhr (änderbar in .env)</p></div>
    </div>`;
  document.querySelectorAll("[data-disc]").forEach((b) => (b.onclick = async () => {
    await api("/api/disconnect/" + b.dataset.disc, { method: "POST" }); viewSettings();
  }));
}

route();
