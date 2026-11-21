/* Damage Evidence Extractor: one screen. Upload -> photo with boxes -> CSV / JSON download -> JSON. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const COLORS = { visible: "var(--visible)", inferred: "var(--inferred)", not_assessable: "var(--na)" };
  const colorOf = (f) => (f.uncertain ? "var(--uncertain)" : COLORS[f.status] || "var(--na)");
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  const state = { api: null, health: null, result: null, examples: [] };

  /* ---------- connection ---------- */
  const normalise = (u) => { u = (u || "").trim().replace(/\/+$/, ""); if (u && !/^https?:\/\//i.test(u)) u = "https://" + u; return u || null; };
  async function health(url) {
    const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), 6000);
    try { const r = await fetch(url + "/health", { signal: ctrl.signal }); if (!r.ok) throw new Error("HTTP " + r.status); return await r.json(); }
    finally { clearTimeout(t); }
  }
  function setStatus(kind, text) {
    const p = $("#statusPill"); p.className = "status" + (kind ? " " + kind : ""); $("#statusText").textContent = text;
  }
  async function connect(url, quiet) {
    state.api = normalise(url); state.health = null;
    if (!state.api) return setStatus(null, "Demo mode");
    setStatus(null, "Connecting…");
    try {
      const h = await health(state.api); state.health = h;
      setStatus(h.mock ? "mock" : "live", h.mock ? "Mock model" : "Live · " + String(h.model).split("/").pop());
    } catch { setStatus("down", "Model offline"); if (!quiet) toast("Could not reach the model"); }
  }

  const dialog = $("#connectDialog");
  $("#statusPill").onclick = () => { $("#apiInput").value = state.api || ""; $("#testResult").textContent = ""; dialog.showModal(); };
  $("#testBtn").onclick = async () => {
    const out = $("#testResult"), url = normalise($("#apiInput").value);
    if (!url) { out.textContent = "Enter an address first."; out.className = "test bad"; return; }
    if (location.protocol === "https:" && url.startsWith("http:")) { out.textContent = "The API must be https (use a tunnel)."; out.className = "test bad"; return; }
    out.textContent = "Testing…"; out.className = "test";
    try { const h = await health(url); out.textContent = `Connected: ${h.model} · ${h.runs} runs${h.mock ? " · MOCK" : ""}`; out.className = "test ok"; }
    catch (e) { out.textContent = "No answer (" + (e.name === "AbortError" ? "timeout" : e.message) + ")"; out.className = "test bad"; }
  };
  $("#saveBtn").onclick = async () => { const u = normalise($("#apiInput").value); store.set("dv_api", u); dialog.close(); await connect(u); if (state.health) toast("Model connected"); };
  $("#disconnectBtn").onclick = () => { store.set("dv_api", null); connect(null); dialog.close(); };

  /* ---------- upload ---------- */
  const drop = $("#drop");
  $("#fileInput").onchange = (e) => handleFile(e.target.files[0]);
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
  drop.addEventListener("drop", (e) => handleFile(e.dataTransfer.files[0]));
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#fileInput").click(); } });
  window.addEventListener("paste", (e) => { const it = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/")); if (it) handleFile(it.getAsFile()); });

  function showPhoto(src) {
    $("#dropEmpty").hidden = true; $("#stage").hidden = false; drop.classList.add("has-photo");
    $("#boxes").innerHTML = ""; $("#photo").src = src;
  }

  async function downscale(file, maxSide = 1600) {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" }).catch(() => null);
    if (!bmp) return file;
    const s = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    if (s === 1 && file.size < 3e6) return file;
    const c = Object.assign(document.createElement("canvas"), { width: Math.round(bmp.width * s), height: Math.round(bmp.height * s) });
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    return new Promise((res) => c.toBlob((b) => res(b ? new File([b], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : file), "image/jpeg", 0.9));
  }

  async function handleFile(file) {
    if (!file || !file.type.startsWith("image/")) return toast("Please choose an image");
    const upload = await downscale(file);
    showPhoto(URL.createObjectURL(upload));
    $("#out").hidden = true;
    if (!state.health) {
      toast("Connect the model first, or try an example");
      $("#statusPill").click();
      return;
    }
    const busy = $("#busy"); busy.hidden = false;
    const msgs = ["Analysing…", "Cross-checking runs…", "Verifying findings…"]; let k = 0;
    $("#busyText").textContent = msgs[0];
    const timer = setInterval(() => { k = Math.min(k + 1, msgs.length - 1); $("#busyText").textContent = msgs[k]; }, 3000);
    try {
      const fd = new FormData(); fd.append("image", upload, upload.name || "upload.jpg");
      const r = await fetch(state.api + "/analyze", { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.json().then((j) => j.detail).catch(() => "HTTP " + r.status));
      render(await r.json(), "live");
    } catch (e) { toast("Analysis failed: " + e.message); }
    finally { clearInterval(timer); busy.hidden = true; }
  }

  /* ---------- examples ---------- */
  async function loadExamples() {
    try { const r = await fetch("examples/index.json", { cache: "no-cache" }); state.examples = r.ok ? await r.json() : []; } catch { state.examples = []; }
    const el = $("#examples");
    if (!state.examples.length) return;
    el.innerHTML = "Try an example: " + state.examples.map((ex, i) => `<button type="button" data-i="${i}">${esc(ex.title)}</button>`).join(" · ");
    el.querySelectorAll("button").forEach((b) => (b.onclick = () => openExample(+b.dataset.i)));
  }
  async function openExample(i) {
    const ex = state.examples[i];
    try { const res = await (await fetch(ex.result)).json(); showPhoto(ex.image); render(res, ex.illustrative ? "illustrative" : "example"); }
    catch { toast("Could not load the example"); }
  }

  /* ---------- render ---------- */
  function render(res, source) {
    state.result = res; state.source = source;
    const img = $("#photo");
    const draw = () => drawBoxes(res, img);
    if (img.complete && img.naturalWidth) draw(); else img.onload = draw;

    const n = $("#notice"); n.hidden = true; n.className = "notice";
    if (res.status === "error") { n.hidden = false; n.className = "notice error"; n.textContent = "Extraction failed for this photo. Nothing was guessed, the error is in limitations."; }
    else if (source === "illustrative") { n.hidden = false; n.textContent = "Illustrative example of the output format, not a model result."; }
    else if (res.meta?.backend === "mock") { n.hidden = false; n.textContent = "Mock model: fake output for testing the interface."; }

    const m = res.meta || {};
    $("#meta").textContent = [
      `${(res.findings || []).length} finding${(res.findings || []).length === 1 ? "" : "s"}`, `damage ${res.damage_present}`,
      m.runtime_s ? `${Number(m.runtime_s).toFixed(1)} s` : "", m.model && m.model !== m.backend ? String(m.model).split("/").pop() : "",
    ].filter(Boolean).join(" · ");
    renderCaveats(res, source);
    $("#json").innerHTML = highlight(JSON.stringify(res, null, 2));
    $("#out").hidden = false;
    $("#out").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function drawBoxes(res, img) {
    const W = res.width || img.naturalWidth, H = res.height || img.naturalHeight;
    $("#boxes").innerHTML = (res.findings || []).map((f, i) => {
      if (!f.bbox || !W || !H) return "";
      const [x, y, w, h] = f.bbox, top = (y / H) * 100;
      const conf = f.confidence != null ? ` ${Math.round(f.confidence * 100)}%` : "";
      return `<div class="bbox${top < 7 ? " below" : ""}" style="--c:${colorOf(f)};left:${(x / W) * 100}%;top:${top}%;width:${(w / W) * 100}%;height:${(h / H) * 100}%">
        <span>${i + 1} ${esc(String(f.damage_type).replace(/_/g, " "))}${conf}</span></div>`;
    }).join("");
  }

  function highlight(json) {
    return esc(json).replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?\b/g, (m, s, colon, lit) =>
      s ? (colon ? `<span class="k">${s}</span>${colon}` : `<span class="s">${s}</span>`) : lit ? `<span class="b">${m}</span>` : `<span class="n">${m}</span>`);
  }

  /* ---------- CSV: one row per finding, image fields repeated ---------- */
  const CSV_COLS = ["image_id", "damage_present", "image_quality", "quality_issues", "scene", "finding_no", "damage_type", "component",
    "material", "location", "extent", "status", "uncertain", "confidence", "agreement", "verified", "bbox_x", "bbox_y", "bbox_w", "bbox_h",
    "visible_traits", "age_indicators", "notes", "limitations"];
  function toCSV(res) {
    const join = (a) => (a || []).join(" | ");
    const base = { image_id: res.image_id, damage_present: res.damage_present, image_quality: res.image_quality,
      quality_issues: join(res.quality_issues), scene: res.scene, limitations: join(res.limitations) };
    const rows = (res.findings || []).length ? res.findings.map((f, i) => ({
      ...base, finding_no: i + 1, damage_type: f.damage_type, component: f.component, material: f.material, location: f.location,
      extent: f.extent, status: f.status, uncertain: f.uncertain, confidence: f.confidence, agreement: f.agreement, verified: f.verified,
      bbox_x: f.bbox?.[0], bbox_y: f.bbox?.[1], bbox_w: f.bbox?.[2], bbox_h: f.bbox?.[3],
      visible_traits: join(f.visible_traits), age_indicators: join(f.age_indicators), notes: f.notes,
    })) : [base];
    const cell = (v) => {
      let s = v == null ? "" : String(v);
      if (/^[=+\-@]/.test(s)) s = "'" + s; // spreadsheet formula injection guard
      return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    return "﻿" + [CSV_COLS.join(","), ...rows.map((r) => CSV_COLS.map((c) => cell(r[c])).join(","))].join("\r\n");
  }
  function download(text, name, type) {
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text], { type })), download: name });
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  $("#csvBtn").onclick = () => state.result && download(toCSV(state.result), (state.result.image_id || "result") + ".csv", "text/csv;charset=utf-8");
  $("#jsonBtn").onclick = () => state.result && download(JSON.stringify(state.result, null, 2), (state.result.image_id || "result") + ".json", "application/json");
  $("#copyBtn").onclick = async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(state.result, null, 2)); toast("JSON copied"); } catch { toast("Copy not allowed here"); }
  };

  /* ---------- per-result caveats: the system states its own blind spots ---------- */
  function caveatsFor(res, source) {
    const c = [], m = res.meta || {}, fs = res.findings || [];
    if (source === "illustrative") c.push("This is a hand-made illustration of the output format. Nothing here was measured.");
    if (m.backend === "mock") c.push("Mock model: the findings are fake.");
    if (res.status === "error") c.push("The model failed on this photo. No findings should be trusted.");
    if (!state.metrics) c.push("The model has not been validated on labelled photos yet. Treat every finding as unverified.");
    if (!m.calibrated && source !== "illustrative") c.push("Confidence percentages are a heuristic, not calibrated against labelled photos.");
    if (m.runs === 1) c.push("Single run: no consistency check across repeated runs.");
    if (m.backend && m.backend !== "illustrative" && !m.verifier) c.push("No independent detector checked these findings.");
    const unc = fs.filter((f) => f.uncertain).length;
    if (unc) c.push(`${unc} of ${fs.length} findings are uncertain: low agreement between runs or not confirmed by the detector.`);
    const unconfirmed = fs.filter((f) => f.verified === false).length;
    if (unconfirmed) c.push(`${unconfirmed} finding${unconfirmed > 1 ? "s were" : " was"} not found by the detector at the claimed position.`);
    if (res.image_quality && res.image_quality !== "good") c.push(`Photo quality is ${res.image_quality}${res.quality_issues?.length ? " (" + res.quality_issues.join(", ").replace(/_/g, " ") + ")" : ""}: damage may be missed or misread.`);
    if (res.damage_present === "unclear") c.push("The system could not decide whether damage is present.");
    if (res.damage_present === "no") c.push("No damage found means none was visible in this frame, not that the property is undamaged.");
    if (fs.some((f) => f.material === "unknown")) c.push("Material could not be identified for at least one finding.");
    if (fs.some((f) => f.bbox == null) && fs.length) c.push("At least one finding has no location in the image.");
    if (res.dropped_findings?.length) c.push(`${res.dropped_findings.length} possible finding${res.dropped_findings.length > 1 ? "s were" : " was"} dropped as unsupported. It may still be real.`);
    (res.limitations || []).forEach((l) => c.push("Model: " + l));
    c.push("Cause, wetness, depth and hidden damage cannot be judged from one photo.");
    c.push("This is evidence for a reviewer, not a coverage decision.");
    return [...new Set(c)];
  }
  function renderCaveats(res, source) {
    const list = caveatsFor(res, source);
    $("#caveatBtn").textContent = `${list.length} caveats`;
    $("#caveatList").innerHTML = list.map((x) => `<li>${esc(x)}</li>`).join("");
    $("#caveatPop").hidden = true; $("#caveatBtn").setAttribute("aria-expanded", "false");
  }
  $("#caveatBtn").onclick = (e) => {
    e.stopPropagation();
    const pop = $("#caveatPop"); pop.hidden = !pop.hidden; $("#caveatBtn").setAttribute("aria-expanded", String(!pop.hidden));
  };
  document.addEventListener("click", (e) => { if (!e.target.closest(".caveat-wrap")) $("#caveatPop").hidden = true; });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#caveatPop").hidden = true; });

  /* ---------- reliability drawer: only measured numbers, never placeholders ---------- */
  const pct = (v) => (v == null ? "–" : Math.round(v * 100) + "%");
  async function loadJSON(path) { try { const r = await fetch(path, { cache: "no-cache" }); return r.ok ? await r.json() : null; } catch { return null; } }
  async function loadReliability() {
    [state.metrics, state.comparison, state.agreement] = await Promise.all(
      [loadJSON("data/metrics.json"), loadJSON("data/comparison.json"), loadJSON("data/agreement.json")]);
    const m = state.metrics, v = $("#verdict");
    if (!m) {
      v.textContent = "Not yet validated on labelled photos. Until it is, treat every result as unverified.";
      v.className = "verdict warn";
      $("#accuracy").innerHTML = `<p class="label">Accuracy</p><p class="empty">Measured accuracy appears here once the 100 hand-labelled test photos are scored. We do not show numbers we have not measured.</p>`;
    } else {
      const k = state.agreement?.kappa_damage_type_presence;
      v.textContent = `Tested on ${m.images_evaluated} hand-labelled photos.` + (k != null ? ` Two humans agree with kappa ${k.toFixed(2)}.` : "");
      v.className = "verdict";
      const ci = m.ci95 || {};
      const row = (name, val, range, note, lowerIsBetter) => {
        const r = range ? `<div class="range"><i style="left:${range[0] * 100}%;width:${Math.max(1, (range[1] - range[0]) * 100)}%"></i>${val != null ? `<em style="left:${val * 100}%"></em>` : ""}</div>` : "";
        const wide = range && range[1] - range[0] > 0.3 ? "Too few photos to pin this number down. " : "";
        const rtxt = range ? `95% range ${pct(range[0])} to ${pct(range[1])}. ${wide}` : "";
        return `<div class="acc-row"><div class="acc-top"><b>${name}</b><span>${pct(val)}</span></div>${r}<small>${rtxt}${note}${lowerIsBetter ? " Lower is better." : ""}</small></div>`;
      };
      $("#accuracy").innerHTML = `<p class="label">Accuracy</p><div class="acc">
        ${row("Precision", m.findings?.precision, ci.precision, "Share of reported findings that are real.")}
        ${row("Recall", m.findings?.recall, ci.recall, "Share of real damage that was found.")}
        ${row("Invented damage on clean photos", m.negatives?.hallucination_rate, ci.hallucination_rate, `${m.negatives?.with_any_finding ?? "–"} of ${m.negatives?.images ?? "–"} undamaged photos got a finding.`, true)}
        ${m.uncertainty?.flagged_share_wrong != null ? row("Wrong findings flagged uncertain", m.uncertainty.flagged_share_wrong, null, "Does the system know when it is wrong?") : ""}
      </div>`;
    }
    const c = state.comparison;
    $("#comparison").innerHTML = `<p class="label">Compared with simpler setups</p>` + (c?.setups?.length
      ? `<table class="cmp"><thead><tr><th>Setup</th><th>Precision</th><th>Recall</th><th>Invented</th><th>s/img</th></tr></thead><tbody>${
          c.setups.map((r) => `<tr class="${/full pipeline/i.test(r.setup) ? "ours" : ""}"><td>${esc(r.setup)}</td><td>${pct(r.precision)}</td><td>${pct(r.recall)}</td><td>${pct(r.hallucination_rate)}</td><td>${r.s_per_image != null ? r.s_per_image.toFixed(1) : "–"}</td></tr>`).join("")
        }</tbody></table>`
      : `<p class="empty">The comparison against a CLIP baseline, a single unchecked run and a frontier model appears here once measured.</p>`);
  }
  const drawer = $("#infoDrawer");
  $("#infoBtn").onclick = () => drawer.showModal();
  $("#infoClose").onclick = () => drawer.close();
  drawer.addEventListener("click", (e) => { if (e.target === drawer) drawer.close(); });

  let tt;
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("show"), 3000); }

  const qs = new URLSearchParams(location.search).get("api");
  if (qs) store.set("dv_api", normalise(qs));
  loadReliability().then(() => { if (state.result) renderCaveats(state.result, state.source); });
  loadExamples();
  connect(store.get("dv_api"), true);
})();
