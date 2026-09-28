"use strict";
const $ = (id) => document.getElementById(id);
const LABEL = { direct: "Direct", ocr: "OCR-assisted" };
const TAG = { direct: "image → Qwen3-VL", ocr: "RapidOCR text → Qwen3-VL" };
const STATUS_CHIP = { missing: ["missing", "missing"], invalid: ["invalid", "invalid"], conflict: ["conflict", "sum conflict"], not_found: ["muted", "not found"] };
let FIELDS = [], run = null, base = null, objectUrl = null;

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v);
  }
  kids.flat().forEach((k) => k != null && n.append(k));
  return n;
}
const chip = (cls, text, title) => el("span", { class: `chip ${cls}`, text, ...(title ? { title } : {}) });
function show(id, on) { $(id).hidden = !on; }
function fail(id, msg) { $(id).textContent = msg; show(id, !!msg); }

async function api(url, opts) {
  const r = await fetch(url, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(body.detail || `Request failed (${r.status})`); e.body = body; throw e; }
  return body;
}

async function init() {
  const cfg = await api("/api/config");
  FIELDS = cfg.fields;
  $("maxmb").textContent = cfg.max_mb;
  for (const s of cfg.samples) $("sample").append(el("option", { value: s.id, text: `${s.id} · ${s.layout} · ${s.condition.replace("_", " ")}` }));
  api("/api/health").then((h) => {
    const ok = h.ollama && h.model_installed;
    $("health").replaceChildren(el("span", { class: ok ? "ok" : "bad", text: ok ? "● " : "● " }),
      ok ? `${h.model} via Ollama ${h.ollama} · OCR ready` : (h.ollama ? `Model ${h.model} not installed — run: ollama pull ${h.model}` : "Ollama not reachable — start Ollama"));
  }).catch(() => { $("health").textContent = "Health check failed"; });
}

function setPreview(src, caption) {
  $("preview").src = src; $("preview").alt = caption; $("preview-cap").textContent = caption;
  show("preview-wrap", true); $("run").disabled = false;
}

$("sample").addEventListener("change", () => {
  fail("doc-error", ""); $("upload").value = "";
  const id = $("sample").value;
  if (!id) { show("preview-wrap", false); $("run").disabled = true; return; }
  setPreview(`/samples/${id}.png`, `Sample ${$("sample").selectedOptions[0].textContent} (synthetic receipt)`);
});

$("upload").addEventListener("change", () => {
  fail("doc-error", ""); $("sample").value = "";
  const f = $("upload").files[0];
  if (!f) return;
  if (!/\.(png|jpe?g)$/i.test(f.name)) { fail("doc-error", "Only .png, .jpg and .jpeg files are accepted."); $("run").disabled = true; return; }
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(f);
  setPreview(objectUrl, "Uploaded image (preview; the server validates it before any extraction)");
});

$("run").addEventListener("click", async () => {
  const method = document.querySelector("input[name=method]:checked").value;
  const fd = new FormData();
  fd.append("method", method);
  if ($("sample").value) fd.append("sample_id", $("sample").value); else if ($("upload").files[0]) fd.append("file", $("upload").files[0]);
  else return;
  fail("doc-error", ""); show("result", false); show("review", false); show("review-empty", true); show("draft-tag", false);
  $("run").disabled = true;
  const t0 = Date.now();
  const label = method === "both" ? "both paths" : `the ${LABEL[method]} path`;
  const tick = () => { $("progress").textContent = `Running ${label} on this machine… ${Math.round((Date.now() - t0) / 1000)} s`; };
  tick(); show("progress", true);
  const timer = setInterval(tick, 1000);
  try {
    run = await api("/api/extract", { method: "POST", body: fd });
    const ran = Object.keys(run.paths);
    $("progress").textContent = `Finished in ${Math.round((Date.now() - t0) / 1000)} s. Run ${run.run_id}.`;
    setPreview(`/api/runs/${run.run_id}/image`, `Source image of run ${run.run_id} (${run.source_kind === "sample" ? "sample " + run.source_name : "upload"}, ${run.width}×${run.height}, as given to the model)`);
    const firstOk = ran.find((m) => run.paths[m].ok) || ran[0];
    base = firstOk;
    renderReview();
  } catch (e) {
    fail("doc-error", e.message); show("progress", false);
    if (!$("sample").value) show("preview-wrap", false);  // a rejected upload is not shown as a document
  } finally { clearInterval(timer); $("run").disabled = false; }
});

function pathValue(m, key) { const p = run.paths[m]; return p.ok ? p.fields[key].value : null; }

function renderReview() {
  const ran = Object.keys(run.paths);
  show("review-empty", false); show("review", true); show("draft-tag", true);
  fail("review-error", ""); show("ack-row", false); $("ack").checked = false; $("note").value = ""; $("approve").disabled = false;
  show("base-row", ran.length > 1);
  document.querySelectorAll("input[name=base]").forEach((r) => { r.checked = r.value === base; r.onchange = () => { base = r.value; fillReviewed(); }; });

  const head = [el("th", { scope: "col", text: "Field" })];
  for (const m of ran) {
    const p = run.paths[m];
    head.push(el("th", { scope: "col", class: m }, `${LABEL[m]}`, el("span", { class: "tag", text: TAG[m] }), p.ok ? null : chip("fail", "run failed")));
  }
  head.push(el("th", { scope: "col", class: "reviewed" }, "Reviewed value", el("span", { class: "tag", text: "what you approve" })));
  $("thead-row").replaceChildren(...head);

  const rows = FIELDS.map((f) => {
    const tr = el("tr", {}, el("td", { class: "name", title: f.description }, f.label, f.required ? el("span", { class: "req", "aria-label": "required", text: "*" }) : null));
    for (const m of ran) {
      const p = run.paths[m];
      const td = el("td");
      if (!p.ok) { td.append(el("span", { class: "val none", text: "—" })); tr.append(td); continue; }
      const fv = p.fields[f.key];
      td.append(el("div", { class: fv.value == null ? "val none" : "val", text: fv.value ?? (p.raw[f.key] != null ? String(p.raw[f.key]) : "none") }));
      const acts = el("div", { class: "cell-actions" });
      const c = STATUS_CHIP[fv.status];
      if (c) acts.append(chip(c[0], c[1], fv.message));
      if (run.disagreements.includes(f.key)) acts.append(chip("differ", "paths differ", "The two paths returned different values for this field"));
      if (run.disagreements.includes(f.key)) {  // a choice only exists where the paths disagree
        const use = el("button", { class: "btn small", type: "button", text: "use this", "aria-label": `Use the ${LABEL[m]} value for ${f.label}` });
        use.addEventListener("click", () => { const i = $(`in-${f.key}`); i.value = fv.value ?? ""; markEdited(f.key); i.focus(); });
        acts.append(use);
      }
      td.append(acts);
      tr.append(td);
    }
    const inp = el("input", { id: `in-${f.key}`, type: "text", "aria-label": `Reviewed ${f.label}`, autocomplete: "off" });
    inp.addEventListener("input", () => markEdited(f.key));
    tr.append(el("td", {}, inp, el("div", { class: "cell-actions", id: `ed-${f.key}` })));
    return tr;
  });
  $("tbody").replaceChildren(...rows);
  fillReviewed();

  const t = ran.map((m) => {
    const p = run.paths[m], s = p.stages;
    const parts = s.ocr_s != null ? ` (OCR ${s.ocr_s} s + model ${s.model_s ?? "—"} s)` : "";
    return el("span", {}, el("strong", { text: `${LABEL[m]}: ` }), p.ok ? `${p.seconds} s${parts}` : `failed — ${p.error}`);
  });
  $("timings").replaceChildren(...t);
  const o = run.paths.ocr;
  show("ocr-details", !!(o && o.ocr_text));
  if (o && o.ocr_text) $("ocr-text").textContent = o.ocr_text;
}

function fillReviewed() {
  for (const f of FIELDS) { $(`in-${f.key}`).value = pathValue(base, f.key) ?? ""; markEdited(f.key); }
}

function norm(v) { return (v ?? "").trim(); }
function markEdited(key) {
  const i = $(`in-${key}`), box = $(`ed-${key}`);
  const edited = norm(i.value) !== norm(pathValue(base, key));
  i.classList.toggle("edited", edited);
  box.replaceChildren(edited ? chip("edited", `changed from ${LABEL[base]}`) : "");
}

$("approve").addEventListener("click", async () => {
  const values = Object.fromEntries(FIELDS.map((f) => [f.key, norm($(`in-${f.key}`).value) || null]));
  fail("review-error", "");
  $("approve").disabled = true;
  try {
    const rec = await api(`/api/runs/${run.run_id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values, base, note: $("note").value, acknowledge_conflicts: $("ack").checked }) });
    renderResult(rec);
  } catch (e) {
    fail("review-error", e.message);
    const conflict = e.body && e.body.problems && Object.values(e.body.problems).some((m) => /total/.test(m) && /confirm/.test(m));
    show("ack-row", !!conflict);
    $("approve").disabled = false;
  }
});

function renderResult(rec) {
  show("draft-tag", false); $("approve").disabled = true;
  document.querySelectorAll("#review input, #review .btn.small").forEach((n) => { n.disabled = true; });
  const label = (k) => (FIELDS.find((f) => f.key === k) || { label: k }).label;
  const changes = rec.changes.length
    ? el("ul", {}, rec.changes.map((c) => el("li", {}, `${label(c.field)}: `, el("code", { text: c.extracted ?? "none" }), " → ", el("code", { text: c.approved ?? "none" }),
        ` (${c.taken_from === "human" ? "typed by reviewer" : "taken from " + LABEL[c.taken_from]})`)))
    : el("p", { text: `No changes: the ${LABEL[rec.method.review_started_from]} values were approved as extracted.` });
  $("result").replaceChildren(
    el("h3", { text: `Approved · run ${rec.run_id}` }),
    el("p", { text: `Review started from the ${rec.method.label} result. Human changes:` }), changes,
    el("p", { text: "Approved values:" }),
    el("ul", {}, FIELDS.map((f) => el("li", {}, `${f.label}: `, el("code", { text: rec.approved[f.key] ?? "—" })))),
    el("p", {}, el("a", { href: `/api/runs/${rec.run_id}/export`, download: `receipt-${rec.run_id}.json`, text: "Download the export (JSON)" }),
      " · integrity sha256 ", el("code", { text: rec.integrity.sha256.slice(0, 16) + "…" })),
  );
  show("result", true);
  $("result").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

init().catch((e) => { $("health").textContent = `Could not load the app configuration: ${e.message}`; });
