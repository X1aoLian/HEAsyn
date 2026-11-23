"use strict";
const $ = (id) => document.getElementById(id);
const palette = {expert_curated: "#11795b", keyword_retrieved: "#2678b8", adjacent_domain: "#ad6c25", out_of_domain: "#a34d85"};
let config, result, activePaper, busy = false;
const categoryName = (key) => config.categories[key] || key || "Unlabelled";
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
async function api(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Request failed.");
  return body;
}
function status(message, error = false) {
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
}
function setBusy(value) {
  busy = value;
  document.body.classList.toggle("busy", value);
  document.querySelectorAll("#rank-form button, #rank-form input, #rank-form select, #rank-form textarea").forEach(node => node.disabled = value);
  $("run").textContent = value ? "Computing embeddings..." : "Run ranking";
}
function showResult(value) {
  result = value;
  activePaper = result.ranking[0]?.paper_id;
  $("selected-count").textContent = `${result.selected_count} / ${result.total}`;
  $("top-score").textContent = result.ranking[0]?.similarity.toFixed(4) || "--";
  $("model-name").textContent = result.model.split("/").pop();
  $("result-source").textContent = result.result_source === "saved" ? "Saved model run" : "Live model run";
  $("provenance").textContent = `Run: ${new Date(result.created_at).toLocaleString()} | ${result.elapsed_seconds}s | ${result.truncated_abstracts} abstracts exceeded the ${result.model_max_tokens}-token input limit. Dataset: ${result.dataset_sha256.slice(0, 12)}.`;
  $("category-bars").replaceChildren();
  for (const [key, name] of Object.entries(config.categories)) {
    const count = result.category_counts[key] || 0;
    const row = element("div", undefined, "category-row");
    const track = element("div", undefined, "bar-track");
    const bar = element("div", undefined, "bar");
    bar.style.width = `${100 * count / Math.max(result.selected_count, 1)}%`;
    bar.style.backgroundColor = palette[key];
    track.append(bar); row.append(element("span", name), track, element("span", count));
    $("category-bars").append(row);
  }
  $("export-csv").disabled = false; $("export-json").disabled = false;
  renderRows(); drawChart();
  status(`${result.result_source === "saved" ? "Saved" : "Live"} ranking loaded. ${result.selected_count} papers selected.`);
}
function visiblePapers() {
  const text = $("search").value.trim().toLowerCase();
  const group = $("category").value;
  const selected = new Set(result.selected_ids);
  return result.ranking.filter(p => (group === "all" || p.category === group)
    && (!$("selected-only").checked || selected.has(p.paper_id))
    && (!text || `${p.title} ${p.abstract}`.toLowerCase().includes(text)));
}
function renderRows() {
  if (!result) return;
  const rows = visiblePapers();
  if (!rows.some(p => p.paper_id === activePaper)) activePaper = rows[0]?.paper_id;
  const selected = new Set(result.selected_ids);
  $("rows").replaceChildren();
  for (const paper of rows) {
    const row = element("tr"); row.classList.toggle("active", activePaper === paper.paper_id);
    const titleCell = element("td");
    const button = element("button", paper.title, "paper-link");
    button.type = "button"; button.setAttribute("aria-pressed", String(activePaper === paper.paper_id));
    button.addEventListener("click", () => {activePaper = paper.paper_id; renderRows();});
    const meta = element("div", undefined, "paper-meta");
    const dot = element("span", undefined, "dot"); dot.style.backgroundColor = palette[paper.category] || "#777";
    meta.append(dot, element("span", `${categoryName(paper.category)}${paper.year ? ` / ${paper.year}` : ""}`));
    titleCell.append(button, meta);
    if (selected.has(paper.paper_id)) titleCell.append(element("div", "SELECTED", "selected-mark"));
    row.append(element("td", paper.rank), titleCell, element("td", paper.similarity.toFixed(4), "score"));
    $("rows").append(row);
  }
  $("empty").hidden = rows.length !== 0;
  $("visible-count").textContent = `${rows.length} / ${result.total}`;
  renderDetail(rows.find(p => p.paper_id === activePaper));
}
function renderDetail(paper) {
  const panel = $("detail"); panel.replaceChildren();
  if (!paper) { panel.append(element("p", "No paper selected.", "data-note")); return; }
  panel.append(element("p", `RANK ${paper.rank} / COSINE ${paper.similarity.toFixed(4)}`, "eyebrow"), element("h3", paper.title));
  panel.append(element("p", `${categoryName(paper.category)}${paper.year ? ` | ${paper.year}` : ""}`, "data-note"));
  panel.append(element("p", "ABSTRACT", "detail-label"), element("p", paper.abstract, "abstract"));
  const source = paper.doi ? `https://doi.org/${encodeURIComponent(paper.doi)}` : paper.url;
  if (source && /^https?:\/\//i.test(source)) {
    const link = element("a", paper.doi ? `DOI: ${paper.doi}` : "Source record");
    link.href = source; link.target = "_blank"; link.rel = "noopener noreferrer"; panel.append(link);
  }
  panel.append(element("p", `Archive source: ${paper.source_file || "User dataset"}`, "data-note"));
}
function drawChart() {
  if (!result) return;
  const canvas = $("score-chart"), width = canvas.clientWidth, height = 164, ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio); canvas.height = height * ratio;
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height);
  const left = 38, right = 10, top = 12, bottom = 26;
  const innerW = width - left - right, innerH = height - top - bottom;
  const min = Math.min(0, ...result.ranking.map(p => p.similarity));
  const max = Math.max(.1, ...result.ranking.map(p => p.similarity)) * 1.1;
  const y = score => top + (max - score) / (max - min) * innerH;
  ctx.font = "10px Arial"; ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const value = min + (max - min) * i / 3;
    ctx.fillStyle = "#5c6d66"; ctx.fillText(value.toFixed(2), 2, y(value) + 3);
    ctx.strokeStyle = "#dbe3df"; ctx.beginPath(); ctx.moveTo(left, y(value)); ctx.lineTo(width - right, y(value)); ctx.stroke();
  }
  const selected = new Set(result.selected_ids), step = innerW / result.total;
  result.ranking.forEach((paper, i) => {
    ctx.globalAlpha = selected.has(paper.paper_id) ? 1 : .4;
    ctx.fillStyle = palette[paper.category] || "#777";
    ctx.fillRect(left + i * step, Math.min(y(0), y(paper.similarity)), Math.max(1, step - 1), Math.max(1, Math.abs(y(0) - y(paper.similarity))));
  });
  ctx.globalAlpha = 1; ctx.fillStyle = "#5c6d66"; ctx.fillText("1", left, height - 7); ctx.fillText(`Rank ${result.total}`, width - 53, height - 7);
}
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], {type}));
  const link = element("a"); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$("export-json").addEventListener("click", () => download("heasyn-ranking.json", JSON.stringify(result, null, 2), "application/json"));
$("export-csv").addEventListener("click", () => {
  const selected = new Set(result.selected_ids);
  const fields = ["rank", "paper_id", "title", "category", "similarity", "selected", "doi"];
  const quote = value => `"${String(value ?? "").replace(/^[=+@-]/, "'$&").replaceAll('"', '""')}"`;
  const lines = [fields.join(","), ...visiblePapers().map(p => fields.map(f => quote(f === "selected" ? selected.has(p.paper_id) : p[f])).join(","))];
  download("heasyn-ranking.csv", lines.join("\r\n"), "text/csv;charset=utf-8");
});
$("rank-form").addEventListener("submit", async event => {
  event.preventDefault(); if (busy) return;
  const payload = {query: $("query").value, model: $("model").value, top_k: Number($("top-k").value), min_score: $("cutoff").value === "" ? null : Number($("cutoff").value)};
  setBusy(true); status("Computing dense embeddings. An uncached model may need to download first.");
  try {showResult(await api("/api/rank", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)}));}
  catch (error) {status(`${error.message}${result ? " Previous results remain displayed." : ""}`, true);}
  finally {setBusy(false);}
});
document.querySelectorAll("[data-preset]").forEach(button => button.addEventListener("click", () => {
  $("query").value = config.queries[button.dataset.preset];
  document.querySelectorAll("[data-preset]").forEach(node => {node.classList.toggle("active", node === button); node.setAttribute("aria-pressed", String(node === button));});
  status("Query changed. Displayed results are from the previous run.");
}));
$("query").addEventListener("input", () => document.querySelectorAll("[data-preset]").forEach(node => {node.classList.remove("active"); node.setAttribute("aria-pressed", "false");}));
["search", "category", "selected-only"].forEach(id => $(id).addEventListener("input", renderRows));
new ResizeObserver(drawChart).observe($("score-chart"));
(async function init() {
  setBusy(true);
  try {
    config = await api("/api/config");
    $("dataset-count").textContent = `${config.total} papers / ${Object.keys(config.counts).length} source groups`;
    $("query").value = config.queries.precise; $("top-k").max = config.total; $("top-k").value = Math.min(20, config.total);
    for (const model of config.models) {const option = element("option", model.split("/").pop()); option.value = model; $("model").append(option);}
    for (const [key, name] of Object.entries(config.categories)) {const option = element("option", name); option.value = key; $("category").append(option);}
    try {showResult(await api("/api/snapshot/precise"));} catch (error) {status(error.message);}
  } catch (error) {status(error.message, true);}
  finally {setBusy(false);}
})();
