/* Damage Vision front end: upload -> findings + boxes -> JSON / CSV. Talks to app/api.py. */
(() => {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nice = (v) => String(v ?? "").replace(/_/g, " ");
  const boxColor = (f) => (f.uncertain ? "var(--warn)" : "var(--accent)");
  const pct = (v) => (v == null ? "–" : Math.round(v * 100) + "%");
  const store = {
    get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
    set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };
  const state = { api: null, health: null, result: null, source: null, metrics: null, comparison: null, agreement: null };

  /* ---------- connection ---------- */
  const normalise = (u) => { u = (u || "").trim().replace(/\/+$/, ""); if (u && !/^https?:\/\//i.test(u)) u = "https://" + u; return u || null; };
  async function health(url) {
    const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), 25000); // covers serverless cold starts
    try { const r = await fetch(url + "/health", { signal: ctrl.signal }); if (!r.ok) throw new Error("HTTP " + r.status); return await r.json(); }
    finally { clearTimeout(t); }
  }
  function setStatus(kind, text) { $("#statusPill").className = "status" + (kind ? " " + kind : ""); $("#statusText").textContent = text; }
  async function connect(url, quiet) {
    state.api = normalise(url); state.health = null;
    if (!state.api) return setStatus(null, "Not connected");
    setStatus(null, "Connecting…");
    try {
      let h;
      try { h = await health(state.api); } catch { await new Promise((r) => setTimeout(r, 1500)); h = await health(state.api); }
      state.health = h;
      const model = String((h.agents && h.agents[0]?.model) || h.model || "model").split("/").pop();
      const more = h.agents && h.agents.length > 1 ? ` +${h.agents.length - 1}` : "";
      setStatus(h.mock ? "mock" : "live", h.mock ? "mock model" : model + more);
    } catch { setStatus("down", "Offline"); if (!quiet) toast("Could not reach the model"); }
  }

  const connectDialog = $("#connectDialog");
  $("#statusPill").onclick = () => { $("#apiInput").value = state.api || ""; $("#testResult").textContent = ""; connectDialog.showModal(); };
  $("#testBtn").onclick = async () => {
    const out = $("#testResult"), url = normalise($("#apiInput").value);
    if (!url) { out.textContent = "Enter an address first."; out.className = "test bad"; return; }
    if (location.protocol === "https:" && url.startsWith("http:")) { out.textContent = "The API must use https."; out.className = "test bad"; return; }
    out.textContent = "Testing…"; out.className = "test";
    try { const h = await health(url); out.textContent = `Connected · ${h.model}${h.mock ? " · mock" : ""}`; out.className = "test ok"; }
    catch (e) { out.textContent = "No answer (" + (e.name === "AbortError" ? "timeout" : e.message) + ")"; out.className = "test bad"; }
  };
  $("#saveBtn").onclick = async () => { const u = normalise($("#apiInput").value); store.set("dv_api", u); connectDialog.close(); await connect(u); if (state.health) toast("Connected"); };
  $("#disconnectBtn").onclick = () => { store.set("dv_api", null); connectDialog.close(); connectDefault(); };

  /* ---------- upload ---------- */
  const drop = $("#drop");
  let selection = 0;
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
    const current = ++selection;
    const upload = await downscale(file);
    if (current !== selection) return;
    showPhoto(URL.createObjectURL(upload));
    $("#busy").hidden = true; $("#out").hidden = true; $("#uploadStatus").hidden = true;
    await connectionReady;
    if (!state.health && state.api) await connect(state.api, true);
    if (current !== selection) return;
    if (!state.health || state.health.mock) {
      $("#uploadStatus").textContent = "No model connected. Set the API address in the connection menu.";
      $("#uploadStatus").hidden = false;
      return;
    }
    $("#busy").hidden = false;
    const steps = ["Analysing", "Cross-checking models", "Reviewing findings"]; let k = 0;
    $("#busyText").textContent = steps[0];
    const timer = setInterval(() => { k = Math.min(k + 1, steps.length - 1); $("#busyText").textContent = steps[k]; }, 3500);
    try {
      const fd = new FormData(); fd.append("image", upload, upload.name || "upload.jpg");
      const r = await fetch(state.api + "/analyze", { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.json().then((j) => j.detail).catch(() => "HTTP " + r.status));
      const result = await r.json();
      if (current === selection) render(result, "live");
    } catch (e) { if (current === selection) toast("Analysis failed: " + e.message); }
    finally { clearInterval(timer); if (current === selection) $("#busy").hidden = true; }
  }

  /* ---------- render ---------- */
  function render(res, source) {
    state.result = res; state.source = source;
    const img = $("#photo");
    const draw = () => drawBoxes(res, img);
    if (img.complete && img.naturalWidth) draw(); else img.onload = draw;

    const n = $("#notice"); n.hidden = true; n.className = "notice";
    if (res.status === "error") { n.hidden = false; n.className = "notice error"; n.textContent = "The analysis failed for this photo. No findings were produced; the reason is listed under limitations."; }
    else if (res.meta?.backend === "mock") { n.hidden = false; n.textContent = "Mock model: this output is not a real analysis."; }

    const fs = res.findings || [];
    $("#summary").textContent = `${fs.length} ${fs.length === 1 ? "finding" : "findings"} · damage ${res.damage_present} · image ${res.image_quality}`;
    $("#findings").innerHTML = fs.length ? fs.map((f, i) => {
      const conf = f.confidence != null ? Math.round(f.confidence * 100) : null;
      const tags = [
        `<span class="tag">${esc(nice(f.status))}</span>`,
        f.uncertain ? `<span class="tag warn">uncertain</span>` : "",
        f.verified === true ? `<span class="tag ok">reviewed</span>` : f.verified === false ? `<span class="tag warn">not confirmed</span>` : "",
        f.agreement != null && (res.meta?.agents || []).length > 1 ? `<span class="tag">agreement ${pct(f.agreement)}</span>` : "",
      ].join("");
      return `<li class="finding"><span class="idx">${String(i + 1).padStart(2, "0")}</span>
        <div><h4>${esc(nice(f.damage_type))}</h4>
          <p class="sub">${esc(nice(f.component))} · ${esc(nice(f.material))} · ${esc(nice(f.extent))}${f.location ? " · " + esc(f.location) : ""}</p>
          <div class="tags">${tags}</div></div>
        <div class="conf">${conf != null ? `<b>${conf}%</b><small>confidence</small><div class="meter"><i style="width:${conf}%"></i></div>` : ""}</div></li>`;
    }).join("") : `<li class="empty">${res.damage_present === "unclear" ? "The photo did not allow a confident judgement." : "No damage visible in this photo."}</li>`;

    const need = res.missing_information || [];
    $("#needed").hidden = !need.length;
    $("#neededList").innerHTML = need.map((x) => `<li>${esc(x)}</li>`).join("");
    $("#caveatList").innerHTML = caveatsFor(res).map((x) => `<li>${esc(x)}</li>`).join("");
    const ag = res.meta?.agents || [];
    $("#agents").innerHTML = ag.length ? ag.map((a) => `<span class="${a.ok ? "" : "bad"}" title="${esc(a.error || "")}">${a.role === "judge" ? "judge · " : ""}${
      esc(String(a.model).split("/").pop())}${a.seconds != null ? " · " + a.seconds + "s" : ""}${a.ok ? "" : " · failed"}</span>`).join("")
      : `<span>${esc(String(res.meta?.model || "unknown").split("/").pop())}</span>`;
    $("#json").innerHTML = highlight(JSON.stringify(res, null, 2));
    $("#out").hidden = false;
    recordRun(res, source);
  }

  function drawBoxes(res, img) {
    const W = res.width || img.naturalWidth, H = res.height || img.naturalHeight;
    $("#boxes").innerHTML = (res.findings || []).map((f, i) => {
      if (!f.bbox || !W || !H) return "";
      const [x, y, w, h] = f.bbox, top = (y / H) * 100;
      return `<div class="bbox${top < 6 ? " below" : ""}" style="--c:${boxColor(f)};left:${(x / W) * 100}%;top:${top}%;width:${(w / W) * 100}%;height:${(h / H) * 100}%">
        <span>${String(i + 1).padStart(2, "0")} ${esc(nice(f.damage_type))}</span></div>`;
    }).join("");
  }

  function highlight(json) {
    return esc(json).replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?\b/g, (m, s, colon, lit) =>
      s ? (colon ? `<span class="k">${s}</span>${colon}` : `<span class="s">${s}</span>`) : lit ? `<span class="b">${m}</span>` : `<span class="n">${m}</span>`);
  }

  /* ---------- limitations specific to this result ---------- */
  function caveatsFor(res) {
    const c = [], m = res.meta || {}, fs = res.findings || [];
    if (res.status === "error") c.push("The model failed on this photo.");
    (res.limitations || []).forEach((l) => c.push(l));
    const failed = (m.agents || []).filter((a) => !a.ok);
    if (failed.length) c.push(`${failed.map((a) => a.agent || a.model).join(", ")} did not answer; agreement uses fewer models.`);
    if (m.backend === "orchestrator" && (m.agents || []).filter((a) => a.ok && a.role !== "judge").length === 1) c.push("Only one model answered, so there is no cross-model check.");
    if (!m.verifier && fs.length) c.push("No independent review of these findings.");
    if (res.image_quality && res.image_quality !== "good") c.push(`Image quality is ${res.image_quality}; damage may be missed.`);
    if (res.dropped_findings?.length) c.push(`${res.dropped_findings.length} unsupported ${res.dropped_findings.length === 1 ? "finding was" : "findings were"} removed.`);
    if (!m.calibrated && fs.length) c.push("Confidence is not yet calibrated on labelled photos.");
    if (!state.metrics) c.push("Accuracy on the labelled test set is not yet published.");
    c.push("Evidence for a reviewer, not a coverage decision.");
    return [...new Set(c)];
  }

  /* ---------- export ---------- */
  const CSV_COLS = ["image_id", "damage_present", "image_quality", "quality_issues", "scene", "finding_no", "damage_type", "component",
    "material", "location", "extent", "status", "uncertain", "confidence", "agreement", "verified", "bbox_x", "bbox_y", "bbox_w", "bbox_h",
    "visible_traits", "age_indicators", "notes", "limitations", "missing_information"];
  function toCSV(res) {
    const join = (a) => (a || []).join(" | ");
    const base = { image_id: res.image_id, damage_present: res.damage_present, image_quality: res.image_quality,
      quality_issues: join(res.quality_issues), scene: res.scene, limitations: join(res.limitations), missing_information: join(res.missing_information) };
    const rows = (res.findings || []).length ? res.findings.map((f, i) => ({
      ...base, finding_no: i + 1, damage_type: f.damage_type, component: f.component, material: f.material, location: f.location,
      extent: f.extent, status: f.status, uncertain: f.uncertain, confidence: f.confidence, agreement: f.agreement, verified: f.verified,
      bbox_x: f.bbox?.[0], bbox_y: f.bbox?.[1], bbox_w: f.bbox?.[2], bbox_h: f.bbox?.[3],
      visible_traits: join(f.visible_traits), age_indicators: join(f.age_indicators), notes: f.notes,
    })) : [base];
    const cell = (v) => { let s = v == null ? "" : String(v); if (/^[=+\-@]/.test(s)) s = "'" + s; return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    return "﻿" + [CSV_COLS.join(","), ...rows.map((r) => CSV_COLS.map((c) => cell(r[c])).join(","))].join("\r\n");
  }
  function download(text, name, type) {
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text], { type })), download: name });
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  $("#csvBtn").onclick = () => state.result && download(toCSV(state.result), (state.result.image_id || "result") + ".csv", "text/csv;charset=utf-8");
  $("#jsonBtn").onclick = () => state.result && download(JSON.stringify(state.result, null, 2), (state.result.image_id || "result") + ".json", "application/json");
  $("#copyBtn").onclick = async () => { try { await navigator.clipboard.writeText(JSON.stringify(state.result, null, 2)); toast("Copied"); } catch { toast("Copy not allowed here"); } };

  /* ---------- method / evaluation sheet ---------- */
  const sheet = $("#sheet");
  function openSheet(tab) {
    $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
    $$(".tabpanel").forEach((p) => (p.hidden = p.dataset.panel !== tab));
    if (tab === "evaluation") renderEvaluation();
    if (!sheet.open) sheet.showModal();
  }
  $$("[data-open]").forEach((b) => (b.onclick = () => openSheet(b.dataset.open)));
  $$(".tab").forEach((t) => (t.onclick = () => openSheet(t.dataset.tab)));
  $("#sheetClose").onclick = () => sheet.close();
  sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });

  async function loadJSON(path) { try { const r = await fetch(path, { cache: "no-cache" }); return r.ok ? await r.json() : null; } catch { return null; } }
  async function loadMetrics() {
    [state.metrics, state.comparison, state.agreement] = await Promise.all(
      [loadJSON("data/metrics.json"), loadJSON("data/comparison.json"), loadJSON("data/agreement.json")]);
  }

  const runs = [];
  function recordRun(res, source) {
    if (source !== "live" || res.meta?.backend === "mock") return;
    const fs = res.findings || [], ag = (res.meta?.agents || []).filter((a) => a.role !== "judge");
    runs.push({ ok: res.status !== "error", secs: Number(res.meta?.runtime_s) || null, findings: fs.length,
      agreement: fs.length ? fs.reduce((a, f) => a + (f.agreement ?? 0), 0) / fs.length : null,
      uncertain: fs.length ? fs.filter((f) => f.uncertain).length / fs.length : null,
      dropped: (res.dropped_findings || []).length, agentsOk: ag.length ? ag.filter((a) => a.ok).length / ag.length : null });
  }
  const mean = (xs) => { xs = xs.filter((x) => x != null && !Number.isNaN(x)); return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null; };
  const p95 = (xs) => { xs = xs.filter((x) => x != null).sort((a, b) => a - b); return xs.length ? xs[Math.min(xs.length - 1, Math.floor(0.95 * xs.length))] : null; };
  const sec = (v) => (v == null ? "–" : v.toFixed(1) + " s");

  function renderEvaluation() {
    const m = state.metrics, k = state.agreement?.kappa_damage_type_presence, c = state.comparison;
    const p = (v) => (v == null ? `<span class="pending">pending</span>` : v);
    $("#verdict").textContent = m
      ? `Measured on ${m.images_evaluated} hand-labelled photos${k != null ? `, labeller agreement κ = ${k.toFixed(2)}` : ""}. Ranges are 95% bootstrap intervals.`
      : "The evaluation harness is complete and tested. Results appear here once the labelled test set is scored.";
    const rows = [
      ["Extraction quality", "30%", "Model ensemble with a fixed schema: 13 damage types, 12 components, 12 materials, boxes, extent, long-term indicators.",
        m ? `P ${pct(m.findings?.precision)} · R ${pct(m.findings?.recall)}` : null],
      ["Evaluation approach", "30%", "100 hand-labelled photos, blind double labelling, Cohen's κ, bootstrap intervals, comparison with simpler setups.",
        k != null ? `κ ${k.toFixed(2)}` : null],
      ["Uncertainty & robustness", "20%", "Status separate from confidence, cross-model agreement, independent review, clean-photo test, 8 image perturbations.",
        m ? `false alarms ${pct(m.negatives?.hallucination_rate)}` : null],
      ["Reproducibility", "10%", "Published JSON schemas, 20 automated tests, one-command run, failures returned as records.",
        "20 tests passing"],
      ["Efficiency", "10%", "Models run in parallel, runtime and tokens logged per image, images capped at 1280 px.",
        m?.runtime_s_per_image?.mean != null ? sec(m.runtime_s_per_image.mean) + " / image" : (runs.length ? sec(mean(runs.map((r) => r.secs))) + " / image" : null)],
    ];
    $("#criteria").innerHTML = rows.map((r) => `<tr><td>${r[0]}</td><td>${r[1]}</td><td>${r[2]}</td><td>${p(r[3])}</td></tr>`).join("");

    if (m) {
      const ci = m.ci95 || {};
      const row = (name, val, range, note) => `<div class="acc-row"><div class="acc-top"><span class="nm">${name}</span><span>${pct(val)}</span></div>${
        range ? `<div class="range"><i style="left:${range[0] * 100}%;width:${Math.max(1, (range[1] - range[0]) * 100)}%"></i>${val != null ? `<em style="left:${val * 100}%"></em>` : ""}</div>` : ""}
        <small>${range ? `95% interval ${pct(range[0])} to ${pct(range[1])}. ` : ""}${note}</small></div>`;
      $("#accuracy").innerHTML = `<h3>Accuracy</h3>${row("Precision", m.findings?.precision, ci.precision, "Reported findings that are real.")}${
        row("Recall", m.findings?.recall, ci.recall, "Real damage that was found.")}${
        row("False alarms on clean photos", m.negatives?.hallucination_rate, ci.hallucination_rate, `${m.negatives?.with_any_finding ?? "–"} of ${m.negatives?.images ?? "–"} undamaged photos received a finding.`)}`;
    } else $("#accuracy").innerHTML = "";

    $("#comparison").innerHTML = c?.setups?.length ? `<h3>Compared with simpler setups</h3><table class="cmp"><thead><tr><th>Setup</th><th>Precision</th><th>Recall</th><th>False alarms</th><th>s / image</th></tr></thead><tbody>${
      c.setups.map((r) => `<tr class="${/full pipeline/i.test(r.setup) ? "ours" : ""}"><td>${esc(r.setup)}</td><td>${pct(r.precision)}</td><td>${pct(r.recall)}</td><td>${pct(r.hallucination_rate)}</td><td>${r.s_per_image != null ? r.s_per_image.toFixed(1) : "–"}</td></tr>`).join("")}</tbody></table>` : "";

    const ok = runs.filter((r) => r.ok), secs = runs.map((r) => r.secs);
    const kv = [["Analyses", String(runs.length)], ["Mean runtime", sec(mean(secs))], ["95th percentile runtime", sec(p95(secs))],
      ["Without error", runs.length ? pct(ok.length / runs.length) : "–"], ["Model availability", pct(mean(runs.map((r) => r.agentsOk)))],
      ["Mean cross-model agreement", pct(mean(ok.map((r) => r.agreement)))], ["Findings flagged uncertain", pct(mean(ok.map((r) => r.uncertain)))],
      ["Unsupported findings removed", String(runs.reduce((a, r) => a + r.dropped, 0))]];
    $("#session").innerHTML = kv.map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join("");
  }

  /* ---------- samples ---------- */
  async function loadSamples() {
    const list = await loadJSON("examples/samples.json");
    if (!list?.length) return;
    const row = $("#samples");
    row.innerHTML = list.map((x, i) => `<button class="sample" type="button" data-i="${i}"><img src="${esc(x.thumb)}" alt="" loading="lazy">${esc(x.label)}</button>`).join("");
    row.querySelectorAll(".sample").forEach((b) => b.addEventListener("click", async () => {
      const x = list[+b.dataset.i];
      row.querySelectorAll(".sample").forEach((o) => o.classList.toggle("active", o === b));
      b.classList.add("loading");
      try { const blob = await (await fetch(x.image)).blob(); await handleFile(new File([blob], x.id + ".jpg", { type: blob.type || "image/jpeg" })); }
      catch { toast("Could not load the sample"); }
      finally { b.classList.remove("loading"); }
    }));
    const credited = list.filter((x) => x.credit?.license);
    if (credited.length) {
      $("#credits").innerHTML = credited.map((x) => `<li>${esc(x.label)}: <a href="${esc(x.credit.source)}" target="_blank" rel="noopener">${esc(x.credit.title)}</a>, ${esc(x.credit.author || "unknown")}, ${esc(x.credit.license)}, Wikimedia Commons (resized)</li>`).join("");
      $("#creditsBox").hidden = false;
    }
  }

  let tt;
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(tt); tt = setTimeout(() => t.classList.remove("show"), 3000); }

  const qs = new URLSearchParams(location.search).get("api");
  if (qs) store.set("dv_api", normalise(qs));
  loadSamples();
  loadMetrics();
  async function connectDefault() {
    const saved = store.get("dv_api");
    if (saved) return connect(saved, true);
    const cfg = await loadJSON("data/api-config.json");
    return connect(cfg?.api_url || null, true);
  }
  const connectionReady = connectDefault();
})();
