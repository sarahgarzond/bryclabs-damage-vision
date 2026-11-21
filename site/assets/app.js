/* Damage Evidence Extractor: static front end for GitHub Pages.
 * Talks to app/api.py when connected. Otherwise shows the bundled examples (site/examples).
 */
(() => {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nice = (v) => String(v ?? "").replace(/_/g, " ");
  const COLORS = { visible: "var(--visible)", inferred: "var(--inferred)", not_assessable: "var(--na)", uncertain: "var(--uncertain)" };
  const colorOf = (f) => (f.uncertain ? COLORS.uncertain : COLORS[f.status] || COLORS.not_assessable);

  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
  };

  const state = { api: null, health: null, file: null, current: null, examples: [] };

  /* ---------------- connection ---------------- */
  function normalise(url) {
    url = (url || "").trim().replace(/\/+$/, "");
    if (url && !/^https?:\/\//i.test(url)) url = "https://" + url;
    return url || null;
  }

  async function checkHealth(url, timeoutMs = 6000) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const r = await fetch(url + "/health", { signal: ctrl.signal });
      if (!r.ok) throw new Error("HTTP " + r.status);
      return await r.json();
    } finally { clearTimeout(t); }
  }

  function setStatus(kind, text) {
    const pill = $("#statusPill");
    pill.classList.remove("live", "mock", "down");
    if (kind) pill.classList.add(kind);
    $("#statusText").textContent = text;
    updateAnalyseButton();
  }

  async function connect(url, { quiet = false } = {}) {
    state.api = normalise(url);
    state.health = null;
    if (!state.api) { setStatus(null, "Demo mode"); return false; }
    setStatus(null, "Connecting…");
    try {
      const h = await checkHealth(state.api);
      state.health = h;
      const model = String(h.model || "model").split("/").pop();
      setStatus(h.mock ? "mock" : "live", h.mock ? "Connected · mock model" : "Live · " + model);
      return true;
    } catch (e) {
      setStatus("down", "Model offline");
      if (!quiet) toast("Could not reach the model API");
      return false;
    }
  }

  /* ---------------- dialog ---------------- */
  const dialog = $("#connectDialog");
  $("#statusPill").addEventListener("click", () => {
    $("#apiInput").value = state.api || "";
    $("#testResult").textContent = "";
    $("#testResult").className = "test-result";
    dialog.showModal();
  });
  $("#testBtn").addEventListener("click", async () => {
    const out = $("#testResult");
    const url = normalise($("#apiInput").value);
    if (!url) { out.textContent = "Enter an address first."; out.className = "test-result bad"; return; }
    if (location.protocol === "https:" && url.startsWith("http:")) {
      out.textContent = "This page is https, so the API must be https too (use a tunnel, see docs).";
      out.className = "test-result bad"; return;
    }
    out.textContent = "Testing…"; out.className = "test-result";
    try {
      const h = await checkHealth(url);
      out.textContent = `Connected: ${h.backend} · ${h.model} · ${h.runs} runs${h.verifier ? " · verifier on" : ""}${h.mock ? " · MOCK" : ""}`;
      out.className = "test-result ok";
    } catch (e) {
      out.textContent = "No answer from " + url + "/health (" + (e.name === "AbortError" ? "timeout" : e.message) + ")";
      out.className = "test-result bad";
    }
  });
  $("#saveBtn").addEventListener("click", async () => {
    const url = normalise($("#apiInput").value);
    store.set("dv_api", url);
    dialog.close();
    if (await connect(url)) toast("Model connected");
  });
  $("#disconnectBtn").addEventListener("click", () => {
    store.set("dv_api", null);
    connect(null);
    dialog.close();
    toast("Demo mode: examples only");
  });

  /* ---------------- input ---------------- */
  const dz = $("#dropzone");
  function setFile(file) {
    if (!file || !file.type.startsWith("image/")) { toast("Please choose an image file"); return; }
    state.file = file;
    const url = URL.createObjectURL(file);
    $("#dzPreview").src = url;
    $("#dzPreview").hidden = false;
    $("#dzEmpty").hidden = true;
    $$(".example").forEach((e) => e.classList.remove("active"));
    updateAnalyseButton();
  }
  $("#fileInput").addEventListener("change", (e) => setFile(e.target.files[0]));
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));
  dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#fileInput").click(); } });
  window.addEventListener("paste", (e) => {
    const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (item) setFile(item.getAsFile());
  });

  function updateAnalyseButton() {
    const btn = $("#analyseBtn"), hint = $("#analyseHint");
    btn.disabled = !state.file;
    hint.className = "hint";
    if (!state.file) { hint.textContent = ""; return; }
    if (!state.health) {
      hint.textContent = "The model is not connected. Click the status button at the top right, or try an example.";
      hint.className = "hint warn";
    } else hint.textContent = "Usually takes 5 to 30 seconds.";
  }

  async function downscale(file, maxSide = 1600) {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" }).catch(() => null);
    if (!bmp) return file;
    const scale = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    if (scale === 1 && file.size < 3e6) return file;
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * scale); c.height = Math.round(bmp.height * scale);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    return await new Promise((res) => c.toBlob((b) => res(b ? new File([b], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : file), "image/jpeg", 0.9));
  }

  let stepTimer = null;
  function showLoading(on) {
    $("#placeholder").hidden = true;
    $("#loading").hidden = !on;
    $("#result").hidden = on || !state.current;
    clearInterval(stepTimer);
    const items = $$("#steps li");
    items.forEach((li) => li.className = "");
    if (!on) return;
    let i = 0;
    items[0].className = "active";
    stepTimer = setInterval(() => {
      if (i < items.length - 1) { items[i].className = "done"; i++; items[i].className = "active"; }
    }, 2600);
  }

  $("#analyseBtn").addEventListener("click", async () => {
    if (!state.file) return;
    if (!state.health) { $("#statusPill").click(); return; }
    const btn = $("#analyseBtn");
    btn.disabled = true;
    showLoading(true);
    try {
      const upload = await downscale(state.file);
      const fd = new FormData();
      fd.append("image", upload, upload.name || "upload.jpg");
      fd.append("claimant_text", $("#claimText").value || "");
      const r = await fetch(state.api + "/analyze", { method: "POST", body: fd });
      if (!r.ok) {
        const msg = await r.json().then((j) => j.detail).catch(() => r.statusText);
        throw new Error(msg || "HTTP " + r.status);
      }
      const result = await r.json();
      render(result, URL.createObjectURL(upload), { source: "live" });
    } catch (e) {
      showLoading(false);
      toast("Analysis failed: " + e.message);
      if (!state.current) $("#placeholder").hidden = false;
    } finally {
      btn.disabled = false;
    }
  });

  /* ---------------- examples ---------------- */
  async function loadExamples() {
    try {
      const r = await fetch("examples/index.json", { cache: "no-cache" });
      state.examples = r.ok ? await r.json() : [];
    } catch { state.examples = []; }
    const grid = $("#exampleGrid");
    if (!state.examples.length) { grid.innerHTML = `<p class="hint">No examples bundled yet.</p>`; return; }
    grid.innerHTML = state.examples.map((ex, i) =>
      `<button class="example" type="button" data-i="${i}"><img src="${esc(ex.image)}" alt="" loading="lazy"><span>${esc(ex.title)}</span></button>`).join("");
    $$(".example", grid).forEach((b) => b.addEventListener("click", () => openExample(+b.dataset.i)));
  }

  async function openExample(i) {
    const ex = state.examples[i];
    if (!ex) return;
    $$(".example").forEach((e) => e.classList.toggle("active", +e.dataset.i === i));
    try {
      const result = await (await fetch(ex.result)).json();
      render(result, ex.image, { source: ex.illustrative ? "illustrative" : "example", claim: ex.claimant_text });
      if (window.matchMedia("(max-width: 900px)").matches) $("#output").scrollIntoView({ behavior: "smooth" });
    } catch { toast("Could not load the example"); }
  }
  $("#heroExample").addEventListener("click", () => {
    $("#analyse").scrollIntoView({ behavior: "smooth" });
    setTimeout(() => openExample(0), 350);
  });

  /* ---------------- render ---------------- */
  function render(res, imgSrc, { source, claim } = {}) {
    state.current = res;
    showLoading(false);
    $("#placeholder").hidden = true;
    $("#result").hidden = false;

    const banner = $("#banner");
    const meta = res.meta || {};
    banner.hidden = false;
    banner.className = "banner";
    if (res.status === "error") {
      banner.className = "banner error";
      banner.textContent = "The extraction failed for this photo. The error is listed under limitations, nothing was guessed.";
    } else if (source === "illustrative") {
      banner.className = "banner warn";
      banner.textContent = "Illustrative example showing the output format. It is not a model result.";
    } else if (meta.backend === "mock") {
      banner.className = "banner warn";
      banner.textContent = "Mock model connected: this output is fake and only tests the interface.";
    } else if (source === "example") {
      banner.innerHTML = "Precomputed result from our pipeline" + (claim ? `. Claimant said: <i>“${esc(claim)}”</i>` : ".");
    } else banner.hidden = true;

    const img = $("#resultImg");
    img.onload = () => drawBoxes(res, img);
    img.src = imgSrc;
    if (img.complete) drawBoxes(res, img);

    const dp = res.damage_present;
    $("#badges").innerHTML = [
      `<span class="badge ${esc(dp)}">Damage present: <b>${esc(dp)}</b></span>`,
      `<span class="badge">Photo quality: <b>${esc(res.image_quality)}</b>${res.quality_issues?.length ? " · " + esc(res.quality_issues.map(nice).join(", ")) : ""}</span>`,
      `<span class="badge">Scene: <b>${esc(nice(res.scene))}</b></span>`,
      `<span class="badge">Findings: <b>${(res.findings || []).length}</b></span>`,
    ].join("");

    renderFindings(res);
    renderReadiness(res.readiness, res);
    $("#json").innerHTML = highlight(JSON.stringify(res, null, 2));

    const parts = [];
    if (meta.model) parts.push(meta.model === meta.backend ? meta.backend : `${meta.backend} · ${String(meta.model).split("/").pop()}`);
    if (meta.runs) parts.push(`${meta.runs} runs`);
    if (meta.verifier) parts.push("verified with " + String(meta.verifier).split("/").pop());
    if (meta.runtime_s != null) parts.push(`${Number(meta.runtime_s).toFixed(1)} s`);
    if (meta.device) parts.push(meta.device);
    if (meta.est_cost_usd != null) parts.push(`≈ $${Number(meta.est_cost_usd).toFixed(4)} per image`);
    $("#meta").textContent = parts.join(" · ");
    selectTab("evidence");
  }

  function drawBoxes(res, img) {
    const W = res.width || img.naturalWidth, H = res.height || img.naturalHeight;
    const host = $("#boxes");
    host.classList.remove("focus");
    host.innerHTML = (res.findings || []).map((f, i) => {
      if (!f.bbox || !W || !H) return "";
      const [x, y, w, h] = f.bbox;
      const top = (y / H) * 100;
      return `<div class="bbox ${top < 8 ? "below" : ""}" data-i="${i}" style="--c:${colorOf(f)};left:${(x / W) * 100}%;top:${top}%;width:${(w / W) * 100}%;height:${(h / H) * 100}%">
        <span class="tag">${i + 1} · ${esc(nice(f.damage_type))}</span></div>`;
    }).join("");
    $$(".bbox", host).forEach((b) => {
      b.addEventListener("mouseenter", () => focus(+b.dataset.i, true));
      b.addEventListener("mouseleave", () => focus(null));
      b.addEventListener("click", () => { selectTab("evidence"); $(`.finding[data-i="${b.dataset.i}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }); });
    });
  }

  function focus(i) {
    const host = $("#boxes");
    host.classList.toggle("focus", i != null);
    $$(".bbox", host).forEach((b) => b.classList.toggle("hot", +b.dataset.i === i));
    $$(".finding").forEach((c) => c.classList.toggle("hot", +c.dataset.i === i));
  }

  function renderFindings(res) {
    const el = $("#findings");
    const fs = res.findings || [];
    if (!fs.length) {
      el.innerHTML = `<div class="empty-findings"><b>No damage found in this photo.</b><br>${res.damage_present === "unclear" ? "The photo did not allow a confident judgement." : "The visible area looks undamaged."}</div>`;
    } else {
      el.innerHTML = fs.map((f, i) => {
        const c = colorOf(f);
        const conf = f.confidence != null ? Math.round(f.confidence * 100) : null;
        const chips = [
          `<span class="chip">${esc(nice(f.status))}</span>`,
          f.uncertain ? `<span class="chip warn">uncertain</span>` : "",
          f.verified === true ? `<span class="chip ok">✓ detector confirmed</span>` : "",
          f.verified === false ? `<span class="chip warn">not confirmed by detector</span>` : "",
          f.agreement != null ? `<span class="chip">seen in ${Math.round(f.agreement * 100)}% of runs</span>` : "",
          ...(f.age_indicators || []).filter((a) => a !== "none_visible").map((a) => `<span class="chip">${esc(nice(a))}</span>`),
        ].join("");
        return `<div class="finding" data-i="${i}" style="--c:${c}">
          <span class="n">${i + 1}</span>
          <div>
            <h4>${esc(nice(f.damage_type))}</h4>
            <p class="sub">on ${esc(nice(f.component))} · material ${esc(nice(f.material))} · ${esc(nice(f.extent))} extent${f.location ? " · " + esc(f.location) : ""}</p>
            <div class="chips">${chips}</div>
            ${f.visible_traits?.length ? `<p class="traits">Visible: ${esc(f.visible_traits.join(", "))}</p>` : ""}
            ${f.notes ? `<p class="traits">Note: ${esc(f.notes)}</p>` : ""}
          </div>
          <div class="conf">${conf != null ? `<div class="v">${conf}%</div><div class="l">confidence</div><div class="bar"><i style="width:${conf}%"></i></div>` : ""}</div>
        </div>`;
      }).join("");
    }
    if (res.dropped_findings?.length) {
      el.innerHTML += `<p class="dropped">Removed as unsupported (seen in too few runs and not confirmed): ${esc(res.dropped_findings.map((f) => nice(f.damage_type)).join(", "))}</p>`;
    }
    $$(".finding", el).forEach((c) => {
      c.addEventListener("mouseenter", () => focus(+c.dataset.i));
      c.addEventListener("mouseleave", () => focus(null));
    });
  }

  function renderReadiness(r, res) {
    const el = $("#readiness");
    if (!r) { el.innerHTML = `<p class="hint">No readiness summary in this result.</p>`; return; }
    const block = (title, items, color, empty, full = false) => `
      <div class="ready ${full ? "full" : ""}" style="--c:${color}">
        <h4><i></i>${title}</h4>
        ${items?.length ? `<ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="none">${empty}</p>`}
      </div>`;
    el.innerHTML = `<div class="ready-grid">
      ${block("Established", r.established, "var(--visible)", "Nothing established with high confidence")}
      ${block("Indicated, needs confirmation", r.indicated, "var(--inferred)", "None")}
      ${block("Missing or not assessable", r.missing, "var(--na)", "None")}
      ${block("Follow-up photo requests", r.follow_up_requests, "var(--accent)", "None needed")}
      ${r.claim_text_consistency?.length ? block("Claimant text vs photo", r.claim_text_consistency, "var(--uncertain)", "", true) : ""}
    </div><p class="note">${esc(r.note || "")}</p>`;
  }

  function highlight(json) {
    return esc(json).replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\b/gi, (m, str, colon, lit) => {
      if (str) return colon ? `<span class="k">${str}</span>${colon}` : `<span class="s">${str}</span>`;
      if (lit) return `<span class="b">${m}</span>`;
      return `<span class="n">${m}</span>`;
    });
  }

  /* ---------------- tabs, json actions ---------------- */
  function selectTab(name) {
    $$(".tab").forEach((t) => { const on = t.dataset.tab === name; t.classList.toggle("active", on); t.setAttribute("aria-selected", on); });
    $$(".tabpanel").forEach((p) => p.hidden = p.dataset.panel !== name);
  }
  $$(".tab").forEach((t) => t.addEventListener("click", () => selectTab(t.dataset.tab)));
  $("#copyJson").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(JSON.stringify(state.current, null, 2)); toast("JSON copied"); }
    catch { toast("Copy not allowed in this browser"); }
  });
  $("#downloadJson").addEventListener("click", () => {
    if (!state.current) return;
    const blob = new Blob([JSON.stringify(state.current, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: (state.current.image_id || "result") + ".json" });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  /* ---------------- evaluation results ---------------- */
  const pct = (v) => (v == null ? "–" : Math.round(v * 100) + "%");
  async function loadMetrics() {
    const el = $("#metrics");
    let m = null, agree = null;
    try { const r = await fetch("data/metrics.json", { cache: "no-cache" }); if (r.ok) m = await r.json(); } catch { /* none yet */ }
    try { const r = await fetch("data/agreement.json", { cache: "no-cache" }); if (r.ok) agree = await r.json(); } catch { /* optional */ }
    if (!m) {
      el.innerHTML = `<div class="empty-state"><b>Evaluation in progress</b>Results from our hand-labelled test set will appear here.</div>`;
      return;
    }
    $("#resultsLead").textContent = `Measured on ${m.images_evaluated} hand-labelled photos. No reference labels were supplied, so we built our own test set.`;
    const f = m.findings || {};
    const cards = [
      ["Precision", pct(f.precision), "Share of reported findings that are real"],
      ["Recall", pct(f.recall), "Share of real damage we found"],
      ["Hallucination on clean photos", pct(m.negatives?.hallucination_rate), `${m.negatives?.with_any_finding ?? "–"} of ${m.negatives?.images ?? "–"} undamaged photos got a finding`],
      ["Seconds per image", m.runtime_s_per_image?.mean != null ? m.runtime_s_per_image.mean.toFixed(1) : "–", "Including repeated runs and verification"],
      ["Box overlap (IoU)", m.boxes?.mean_iou != null ? m.boxes.mean_iou.toFixed(2) : "–", `${m.boxes?.pairs ?? 0} boxed findings compared`],
      ["Confidence AUROC", m.confidence_auroc != null ? m.confidence_auroc.toFixed(2) : "–", "How well confidence separates right from wrong"],
      ["Labeller agreement", agree?.kappa_damage_type_presence != null ? agree.kappa_damage_type_presence.toFixed(2) : "–", "Cohen's kappa between two humans: the realistic ceiling"],
      ["Extraction errors", String(m.extraction_errors ?? 0), "Photos where the model failed, reported not hidden"],
    ];
    el.innerHTML = `<div class="metric-grid">${cards.map(([l, v, d]) => `<div class="metric"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div><div class="d">${esc(d)}</div></div>`).join("")}</div>
      <div class="charts" id="charts"></div>`;
    const charts = $("#charts");
    [["data/robustness.png", "Stability of findings under blur, darkness, compression, cropping and repeated runs"],
     ["data/calibration.png", "Confidence calibration: predicted confidence vs share actually correct"]].forEach(([src, cap]) => {
      const fig = document.createElement("figure");
      fig.innerHTML = `<img src="${src}" alt="${esc(cap)}" loading="lazy"><figcaption>${esc(cap)}</figcaption>`;
      fig.querySelector("img").onerror = () => fig.remove();
      charts.appendChild(fig);
    });
  }

  /* ---------------- toast ---------------- */
  let toastTimer;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
  }

  /* ---------------- init ---------------- */
  const qs = new URLSearchParams(location.search).get("api");
  if (qs) store.set("dv_api", normalise(qs));
  loadExamples();
  loadMetrics();
  connect(store.get("dv_api"), { quiet: true });
})();
