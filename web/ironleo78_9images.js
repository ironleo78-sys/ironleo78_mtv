import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { gate as syncGate, planSync, collectNodes, mirrorVideo, suggestPrompt, applyPresetAudio, gateI2v, planSyncI2v, customAudioMissing, presetAlias } from "./il78_sync_logic.js";
import { SHADOW_KEY, buildShadow, restoreFromShadow } from "./il78_shadow.js";

const NODE_ALL = "IronLeo78_MTV_PromptGenerator";
const N = 9;
const FPS = 24;

// ---------- helpers ----------
function parseValue(value) {
  let v = (value || "").trim();
  let type = "input";
  const m = v.match(/^(.*) \[(input|output|temp)\]$/);
  if (m) { v = m[1]; type = m[2]; }
  const i = v.lastIndexOf("/");
  return { filename: i >= 0 ? v.slice(i + 1) : v, subfolder: i >= 0 ? v.slice(0, i) : "", type };
}
function viewUrl(value) {
  return api.apiURL("/view?" + new URLSearchParams(parseValue(value)).toString());
}
async function uploadFile(file) {
  const body = new FormData();
  body.append("image", file);
  body.append("type", "input");
  body.append("subfolder", "");
  const r = await api.fetchApi("/upload/image", { method: "POST", body });
  if (r.status !== 200) throw new Error(`${r.status} ${r.statusText}`);
  const j = await r.json();
  return j.subfolder ? `${j.subfolder}/${j.name}` : j.name;
}
async function listFiles(nodeName, inputName) {
  try {
    const r = await api.fetchApi(`/object_info/${nodeName}`);
    const j = await r.json();
    const spec = j[nodeName].input.required[inputName];
    return Array.isArray(spec[0]) ? spec[0] : (spec[1]?.options || []);
  } catch (e) { return []; }
}
const IMG_RE = /\.(png|jpe?g|webp|bmp|gif|tiff?)$/i;
const VID_RE = /\.(mp4|mov|m4v|webm|mkv|avi|gif)$/i;

function injectStyle() {
  if (document.getElementById("il78-style")) return;
  const s = document.createElement("style");
  s.id = "il78-style";
  s.textContent = `
  .il78-grid{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(3,1fr);gap:6px;
    width:100%;height:100%;box-sizing:border-box;padding:2px;}
  .il78-gwrap{display:flex;flex-direction:column;gap:3px;width:100%;height:100%;box-sizing:border-box;}
  .il78-gwrap .il78-grid{flex:1;min-height:0;height:auto;}
  .il78-tip{font:11px sans-serif;color:#7fb7e6;text-align:center;min-height:0;white-space:normal;line-height:14px;}
  .il78-cell{position:relative;min-height:0;background:#1b1b1b;border:1px solid #484848;border-radius:6px;
    overflow:hidden;cursor:pointer;}
  .il78-cell:hover{border-color:#9a9a9a;}
  .il78-cell.il78-drop{border-color:#4aa3ff;box-shadow:0 0 0 2px #4aa3ff55;}
  .il78-cell img,.il78-cell video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;pointer-events:none;}
  .il78-badge{position:absolute;top:3px;left:4px;font:600 11px sans-serif;color:#fff;background:#000a;
    padding:1px 5px;border-radius:8px;z-index:2;}
  .il78-name{position:absolute;left:0;right:0;bottom:0;font:10px sans-serif;color:#ddd;background:#000b;
    padding:1px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;z-index:2;}
  .il78-x{position:absolute;top:2px;right:3px;z-index:3;font:700 12px sans-serif;color:#fff;background:#c33;
    width:18px;height:18px;line-height:18px;text-align:center;border-radius:9px;display:none;opacity:.8;}
  .il78-cell.il78-has .il78-x{display:block;}
  .il78-x:hover{opacity:1;background:#e33;}
  .il78-empty{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
    color:#777;font:12px sans-serif;}
  .il78-empty b{font-size:22px;font-weight:700;letter-spacing:2px;line-height:26px;color:#8a8a8a;}
  .il78-empty span{font-size:10px;margin-top:2px;}
  .il78-vwrap{display:flex;flex-direction:column;gap:4px;width:100%;height:100%;box-sizing:border-box;padding:2px;}
  .il78-vcell{flex:1;min-height:60px;}
  .il78-info{font:11px sans-serif;color:#aaa;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .il78-info.warn{color:#f0a030;}
  .il78-sync{padding:4px 6px;text-align:center;font:12px sans-serif;color:#fff;background:#335c8a;border-radius:4px;cursor:pointer;user-select:none;}
  .il78-sync:hover{background:#3f72a8;}
  .il78-sync.il78-off{background:#3a3a3a;color:#888;cursor:not-allowed;}
  .il78-sync-msg{font:11px sans-serif;color:#9ab;text-align:center;min-height:14px;white-space:normal;}
  .il78-sync-msg.warn{color:#f0a030;}
  .il78-panel{position:fixed;z-index:10000;width:280px;max-height:360px;display:flex;flex-direction:column;
    background:#222;border:1px solid #666;border-radius:8px;box-shadow:0 6px 24px #000a;font:12px sans-serif;color:#ddd;}
  .il78-panel input[type=text]{margin:6px;padding:4px 6px;background:#111;color:#ddd;border:1px solid #555;border-radius:4px;}
  .il78-panel .il78-btn{margin:6px 6px 0;padding:6px;text-align:center;background:#335c8a;border-radius:4px;cursor:pointer;}
  .il78-panel .il78-btn:hover{background:#3f72a8;}
  .il78-list{overflow:auto;flex:1;margin-bottom:4px;}
  .il78-item{padding:3px 10px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
  .il78-item:hover{background:#3a3a3a;}
  .il78-item.il78-none{color:#f88;border-bottom:1px solid #444;}`;
  document.head.appendChild(s);
}

// ---------- shared picker panel ----------
let panel = null, outsideHandler = null;
function closePanel() {
  panel?.remove(); panel = null;
  if (outsideHandler) { document.removeEventListener("pointerdown", outsideHandler, true); outsideHandler = null; }
}
async function openPicker(ev, { files, hasValue, uploadLabel, noneLabel, onPick, onClear, onUpload }) {
  closePanel();
  panel = document.createElement("div");
  panel.className = "il78-panel";
  const up = document.createElement("div");
  up.className = "il78-btn";
  up.textContent = uploadLabel;
  up.onclick = () => { closePanel(); onUpload(); };
  const filter = document.createElement("input");
  filter.type = "text";
  filter.placeholder = "Filter input folder…";
  const list = document.createElement("div");
  list.className = "il78-list";
  panel.append(up, filter, list);
  document.body.appendChild(panel);
  panel.style.left = Math.max(4, Math.min(ev.clientX, window.innerWidth - 290)) + "px";
  panel.style.top = Math.max(4, Math.min(ev.clientY, window.innerHeight - 370)) + "px";

  const all = await files();
  const render = () => {
    const q = filter.value.toLowerCase();
    list.innerHTML = "";
    if (hasValue()) {
      const none = document.createElement("div");
      none.className = "il78-item il78-none";
      none.textContent = noneLabel;
      none.onclick = () => { onClear(); closePanel(); };
      list.appendChild(none);
    }
    all.filter((f) => f.toLowerCase().includes(q)).slice(0, 300).forEach((f) => {
      const it = document.createElement("div");
      it.className = "il78-item";
      it.textContent = f;
      it.title = f;
      it.onclick = () => { onPick(f); closePanel(); };
      list.appendChild(it);
    });
  };
  filter.addEventListener("input", render);
  render();
  filter.focus();
  outsideHandler = (e) => { if (panel && !panel.contains(e.target)) closePanel(); };
  setTimeout(() => document.addEventListener("pointerdown", outsideHandler, true), 0);
}

// the widgets whose values are saved in the workflow (the DOM grid / video cell are serialize:false)
function serializedWidgets(node) {
  return (node.widgets || []).filter((w) => w.serialize !== false && w.options?.serialize !== false);
}

// ---------- per-node setup ----------
function setup(node) {
  injectStyle();
  const W = (name) => node.widgets.find((w) => w.name === name);
  const get = (name) => (W(name)?.value ?? "");
  function set(name, value) {
    const w = W(name);
    if (!w) return;
    w.value = value;
    w.callback?.(value);
    node.graph?.change?.();
    app.canvas?.setDirty(true, true);
  }

  // hide the string widgets under the hood
  for (const name of [...Array.from({ length: N }, (_, k) => `image_${k + 1}`), "video"]) {
    const w = W(name);
    if (!w) continue;
    w.hidden = true;
    w.computeSize = () => [0, -4];
  }

  // =========== picture grid ===========
  const grid = document.createElement("div");
  grid.className = "il78-grid";
  const cells = [];
  const fileInput = document.createElement("input");
  fileInput.type = "file"; fileInput.accept = "image/*"; fileInput.multiple = true; fileInput.style.display = "none";
  let uploadTarget = 1;
  fileInput.addEventListener("change", async () => {
    const files = [...fileInput.files]; fileInput.value = "";
    if (files.length) await assignFiles(uploadTarget, files);
  });

  const imgName = (i) => `image_${i}`;
  // ---- friendly advice: pictures that are not the video ratio get cropped in Output_To_LLM
  const ratios = Array(N + 1).fill(0);          // natural width/height per slot (0 = empty / not loaded yet)
  let videoPortrait = false;
  const RATIO_TOL = 0.06;                       // same tolerance as the Python side
  function targetRatio() {
    const m = String(get("Video_Size")).match(/^(\d+)x(\d+)$/);
    const r = m ? Number(m[1]) / Number(m[2]) : 16 / 9;
    return videoPortrait ? 1 / r : r;
  }
  function offRatioSlots() {
    const tr = targetRatio();
    const out = [];
    for (let i = 1; i <= N; i++) if (ratios[i] > 0 && Math.abs(ratios[i] / tr - 1) > RATIO_TOL) out.push(i);
    return out;
  }
  function updateTip() {
    const off = offRatioSlots();
    for (let i = 1; i <= N; i++) {
      const badge = cells[i - 1]?.badge;
      if (badge) badge.textContent = off.includes(i) ? `${i} ✂` : String(i);
    }
    tip.textContent = "";      // v0.4.2: the written tip under the grid is gone; the ✂ on a picture's number still marks a cropped one
  }
  async function assignFiles(start, files) {
    const images = files.filter((f) => f.type.startsWith("image/") || IMG_RE.test(f.name));
    let slot = start;
    for (let k = 0; k < images.length; k++) {
      if (k > 0) { while (slot <= N && String(get(imgName(slot))).trim()) slot++; }
      if (slot > N) break;
      try { set(imgName(slot), await uploadFile(images[k])); refreshCell(slot); }
      catch (e) { alert(`Upload failed for ${images[k].name}: ${e.message}`); }
      slot++;
    }
  }
  function refreshCell(i) {
    const c = cells[i - 1];
    const v = String(get(imgName(i))).trim();
    c.body.innerHTML = "";
    ratios[i] = 0;
    if (v) {
      const img = document.createElement("img");
      img.draggable = false;
      img.onload = () => { ratios[i] = img.naturalHeight ? img.naturalWidth / img.naturalHeight : 0; updateTip(); };
      img.src = viewUrl(v);
      c.body.appendChild(img);
      const nm = document.createElement("div");
      nm.className = "il78-name"; nm.textContent = parseValue(v).filename;
      c.body.appendChild(nm);
      c.el.title = `${v}\n(✕ or right-click = remove)`;
    } else {
      c.body.innerHTML = `<div class="il78-empty"><b>NONE</b><span>click to add</span></div>`;
      c.el.title = `Picture_${i}: NONE. Click to choose or upload`;
    }
    c.el.classList.toggle("il78-has", !!v);
    updateTip();
  }
  for (let i = 1; i <= N; i++) {
    const el = document.createElement("div");
    el.className = "il78-cell";
    const body = document.createElement("div");
    body.style.cssText = "position:absolute;inset:0;";
    const badge = document.createElement("div");
    badge.className = "il78-badge"; badge.textContent = i;
    const x = document.createElement("div");
    x.className = "il78-x"; x.textContent = "✕"; x.title = "Remove this picture";
    x.onclick = (e) => { e.stopPropagation(); set(imgName(i), ""); refreshCell(i); };
    el.append(body, badge, x);
    el.addEventListener("click", (e) => openPicker(e, {
      files: () => listFiles("LoadImage", "image"),
      hasValue: () => !!String(get(imgName(i))).trim(),
      uploadLabel: "Upload image(s)…",
      noneLabel: "✕ NONE (remove this picture)",
      onPick: (f) => { set(imgName(i), f); refreshCell(i); },
      onClear: () => { set(imgName(i), ""); refreshCell(i); },
      onUpload: () => { uploadTarget = i; fileInput.click(); },
    }));
    el.addEventListener("contextmenu", (e) => {
      if (!String(get(imgName(i))).trim()) return;
      e.preventDefault(); e.stopPropagation();
      set(imgName(i), ""); refreshCell(i);
    });
    el.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); el.classList.add("il78-drop"); });
    el.addEventListener("dragleave", () => el.classList.remove("il78-drop"));
    el.addEventListener("drop", async (e) => {
      e.preventDefault(); e.stopPropagation(); el.classList.remove("il78-drop");
      const files = [...(e.dataTransfer?.files || [])];
      if (files.length) await assignFiles(i, files);
    });
    grid.appendChild(el);
    cells.push({ el, body, badge });
  }
  grid.appendChild(fileInput);
  const tip = document.createElement("div");
  tip.className = "il78-tip";
  const gwrap = document.createElement("div");
  gwrap.className = "il78-gwrap";
  gwrap.append(grid, tip);

  // =========== video cell ===========
  const vwrap = document.createElement("div");
  vwrap.className = "il78-vwrap";
  const vcell = document.createElement("div");
  vcell.className = "il78-cell il78-vcell";
  const vbody = document.createElement("div");
  vbody.style.cssText = "position:absolute;inset:0;";
  const vbadge = document.createElement("div");
  vbadge.className = "il78-badge"; vbadge.textContent = "🎬 Video";
  const vx = document.createElement("div");
  vx.className = "il78-x"; vx.textContent = "✕"; vx.title = "Remove the video";
  vcell.append(vbody, vbadge, vx);
  const info = document.createElement("div");
  info.className = "il78-info";
  const syncBtn = document.createElement("div");
  syncBtn.className = "il78-sync il78-off";
  syncBtn.textContent = "⟳ Sync from MTV (next segment)";
  const syncMsg = document.createElement("div");
  syncMsg.className = "il78-sync-msg";
  vwrap.append(vcell, info, syncBtn, syncMsg);
  const vInput = document.createElement("input");
  vInput.type = "file"; vInput.accept = "video/*,.mp4,.mov,.m4v,.webm,.mkv,.avi"; vInput.style.display = "none";
  vwrap.appendChild(vInput);

  // v0.1.12: a video loaded here is put in the MTV's Video File too (load it once)
  function mirrorToMtv() {
    if (get("Mode") === "i2v") return;      // v0.3.5: in i2v the video is ignored here, so it is not copied to the MTV either
    try { mirrorVideo(node, get("video"), collectNodes(app.rootGraph || app.graph, node.graph), { audio: get("Mode") !== "i2v" }); }
    catch (e) { /* a convenience: never breaks the load */ }
  }
  async function setVideoFile(file) {
    try { set("video", await uploadFile(file)); refreshVideo(); mirrorToMtv(); }
    catch (e) { alert(`Upload failed for ${file.name}: ${e.message}`); }
  }
  vInput.addEventListener("change", async () => {
    const f = vInput.files[0]; vInput.value = "";
    if (f) await setVideoFile(f);
  });
  // v0.4.1: the preview shows the frame where the window starts (Start_From), not the first frame: it follows Sync, Auto-sync and typing
  let previewEl = null;
  function seekPreview() {
    const ve = previewEl;
    if (!ve || ve.readyState < 1 || get("Mode") === "i2v") return;
    const dur = Number.isFinite(ve.duration) ? ve.duration : Infinity;
    const t = Math.min(Math.max(0.1, Number(get("Start_From")) || 0), Math.max(0.1, dur - 0.05));
    if (Math.abs(ve.currentTime - t) > 0.02) { try { ve.currentTime = t; } catch (e) { /* a preview only */ } }
  }
  function refreshVideo() {
    const v = String(get("video")).trim();
    vbody.innerHTML = "";
    videoPortrait = false;
    previewEl = null;
    if (v) {
      const ve = document.createElement("video");
      ve.src = viewUrl(v) + "#t=0.1";
      ve.muted = true; ve.preload = "metadata"; ve.playsInline = true;
      ve.onloadedmetadata = () => { videoPortrait = ve.videoHeight > ve.videoWidth; updateTip(); seekPreview(); };
      previewEl = ve;
      vbody.appendChild(ve);
      const nm = document.createElement("div");
      nm.className = "il78-name"; nm.textContent = parseValue(v).filename;
      vbody.appendChild(nm);
      vcell.title = `${v}\n(✕ or right-click = remove)\nOptional Sync from MTV: load this SAME file in the MTV node's Video File.`;
    } else {
      vbody.innerHTML = `<div class="il78-empty"><b>NONE</b><span>click to add a video</span></div>`;
      vcell.title = "Video: NONE. Click to choose or upload";
    }
    vcell.classList.toggle("il78-has", !!v);
    updateInfo();
    updateSyncGate();
    updateTip();
  }
  function updateInfo() {
    seekPreview();
    const st = Number(get("Start_From")) || 0;
    const dur = Number(get("Duration")) || 0;
    const iv = Number(get("Frame_Interval")) || 2;
    const frames = Math.ceil(Math.max(1, Math.round(dur * FPS)) / iv);     // same count as the Python side
    const r2 = (x) => Math.round(x * 100) / 100;                         // a synced 5.1667 must not look like 5.2
    if (get("Mode") === "i2v") {                                         // v0.3.10: no video in i2v: Duration is only the length the LLM writes its timeline for
      info.textContent = `image-to-video: the LLM writes a timeline for ${r2(dur)}s (no video frames)`;
      info.classList.toggle("warn", false);
      return;
    }
    // v0.3.10: at most 120 frames go to the LLM (the rest of the window is simply thinned), so this is information, not a warning
    info.textContent = `${r2(st)}s → ${r2(st + dur)}s  |  ≈ ${frames} frames @ ${get("Video_Size")}` +
      (frames > 120 ? `  |  120 of them go to the LLM` : "");
    info.classList.toggle("warn", false);
  }
  vcell.addEventListener("click", (e) => openPicker(e, {
    files: () => listFiles("LoadVideo", "file"),
    hasValue: () => !!String(get("video")).trim(),
    uploadLabel: "Upload video…",
    noneLabel: "✕ NONE (remove the video)",
    onPick: (f) => { set("video", f); refreshVideo(); mirrorToMtv(); },
    onClear: () => { set("video", ""); refreshVideo(); },
    onUpload: () => vInput.click(),
  }));
  vcell.addEventListener("contextmenu", (e) => {
    if (!String(get("video")).trim()) return;
    e.preventDefault(); e.stopPropagation();
    set("video", ""); refreshVideo();
  });
  vx.onclick = (e) => { e.stopPropagation(); set("video", ""); refreshVideo(); };
  vcell.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); vcell.classList.add("il78-drop"); });
  vcell.addEventListener("dragleave", () => vcell.classList.remove("il78-drop"));
  vcell.addEventListener("drop", async (e) => {
    e.preventDefault(); e.stopPropagation(); vcell.classList.remove("il78-drop");
    const f = [...(e.dataTransfer?.files || [])].find((x) => x.type.startsWith("video/") || VID_RE.test(x.name));
    if (f) await setVideoFile(f);
  });

  // =========== optional: Sync from MTV (passive: no request until the button is clicked) ===========
  const SYNC_HINT = "Optional add-on. Copies Start_From and Duration of the NEXT segment MTV will make. " +
    "Load the SAME video file in both nodes. Press it again after each MTV Run (the counter moves on).";
  let syncReason = "";
  let syncBusy = false;
  const SYNC_HINT_I2V = "Image-to-video: copies the MTV's duration into this node's Duration, so the LLM writes its timeline for the clip the MTV will make.";
  function updateSyncGate() {
    const nodes = collectNodes(app.rootGraph || app.graph, node.graph);      // v0.1.9: the whole workflow, subgraphs included
    const i2v = get("Mode") === "i2v";                                       // v0.3.5: no video in i2v: the button copies the duration only
    const g = i2v ? gateI2v(nodes) : syncGate(get("video"), nodes);
    syncReason = g.ok ? "" : g.reason;
    const label = i2v ? "⟳ Sync duration from MTV" : "⟳ Sync from MTV (next segment)";
    if (syncBtn.textContent !== label) syncBtn.textContent = label;
    const hint = i2v ? SYNC_HINT_I2V : SYNC_HINT;
    syncBtn.classList.toggle("il78-off", !g.ok);
    syncBtn.title = g.ok ? `${hint}${g.note ? "\n" + g.note : ""}` : `${syncReason}\n\n${hint}`;
  }
  // v0.3.14: the button's work is a function so the MTV's Go / Go time / Latest can run it too (silent = no message when it cannot sync)
  async function doSync(silent) {
    const i2v = get("Mode") === "i2v";
    const g = i2v ? gateI2v(collectNodes(app.rootGraph || app.graph, node.graph)) : syncGate(get("video"), collectNodes(app.rootGraph || app.graph, node.graph));
    if (!g.ok) { if (!silent) { syncMsg.textContent = g.reason; syncMsg.classList.add("warn"); } return; }
    if (syncBusy) return;
    syncBusy = true;
    const limits = { maxStart: W("Start_From")?.options?.max ?? 36000, maxDuration: W("Duration")?.options?.max ?? 20, minDuration: W("Duration")?.options?.min ?? 1 };
    const r = i2v ? planSyncI2v(g.mtv, limits) : await planSync((u) => api.fetchApi(u), g.mtv, limits);
    syncBusy = false;
    if (r.ok) {
      const ws = W("Start_From"), wd = W("Duration");
      if (ws && !i2v) ws.value = r.start;           // set directly, full precision (the widget may display it rounded)
      if (wd) wd.value = r.duration;
      node.graph?.change?.();
      app.canvas?.setDirty(true, true);
      updateInfo();
    }
    if (silent && !r.ok) return;                                                  // an automatic sync that cannot run stays quiet
    syncMsg.textContent = (silent ? "Auto-" + r.text.charAt(0).toLowerCase() + r.text.slice(1) : r.text) + (g.note ? `  (${g.note})` : "");
    syncMsg.classList.toggle("warn", !r.ok || (r.warn && r.warn.length > 0));
  }
  syncBtn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); doSync(false); });
  const syncTimer = setInterval(() => { if (!document.hidden) updateSyncGate(); }, 500);     // local checks only, no request; v0.1.9: not while the tab is hidden

  // keep the info line live when the visible widgets change
  for (const name of ["Start_From", "Duration", "Frame_Interval", "Video_Size"]) {
    const w = W(name);
    if (!w) continue;
    const cb = w.callback;
    w.callback = function () { const r = cb?.apply(this, arguments); updateInfo(); updateTip(); return r; };
  }

  // v0.1.24: choosing a Preset puts its suggested working prompt in the prompt box (never over text the user wrote)
  // v0.2.5: the suggestion also follows the Mode (v2v / i2v): the route sends one map per mode, merged here as "mode|preset"
  {
    // v0.3.0: the same fetch also carries the MTV settings of a musician preset (Custom Audio + the matching Audio Stem), see applyPresetAudio
    const applySuggestion = async (fromMode) => {
      const wp = W("Preset"), wm = W("Mode"), box = W("prompt");
      if (!wp) return;
      const mode = wm?.value === "i2v" ? "i2v" : "v2v";
      let j = null;
      try { j = await (await api.fetchApi("/ironleo78/mtv/presets")).json(); } catch (e) { /* a convenience */ }
      // v0.6.0 (sweep M2): an old preset name not renamed yet (the silent rename is still on its way) is looked up under its new name
      const pname = presetAlias(wp.value, j?.aliases) || wp.value;
      try {
        if (j && box) {
          const all = {};
          for (const [k, v] of Object.entries(j.presets || {})) all[`v2v|${k}`] = v;
          for (const [k, v] of Object.entries(j.i2v || {})) all[`i2v|${k}`] = v;
          const next = suggestPrompt(box.value, all, `${mode}|${pname}`, true);      // v0.3.1: choosing a Preset always fills the example; v0.3.2: so does changing the Mode (the example of the other mode is shown)
          if (next !== null) { box.value = next; box.callback?.(next); node.graph?.change?.(); app.canvas?.setDirty(true, true); }
        }
      } catch (e) { /* a convenience */ }
      try {
        const info = { audio: j?.audio?.[pname] || "", stem: j?.stems?.[pname] || "" };
        const nodesNow = collectNodes(app.rootGraph || app.graph, node.graph);
        const prevAudio = node._il78Audio || node.properties?.il78_audio || null;      // v0.3.7: kept in the saved workflow, so it survives a reload
        node._il78Audio = applyPresetAudio(nodesNow, mode, info, prevAudio, !!fromMode);
        node.properties = node.properties || {};
        node.properties.il78_audio = node._il78Audio;
        if (info.audio === "Custom Audio" && customAudioMissing(nodesNow)) {      // v0.3.5: this preset is driven by the Custom Audio File: say it is missing
          syncMsg.textContent = "This preset follows your Custom Audio: pick a Custom Audio File in the MTV node.";
          syncMsg.classList.add("warn");
          try { app.extensionManager?.toast?.add({ severity: "warn", summary: "Custom Audio File missing", detail: "Pick a Custom Audio File in the MTV node: this preset is driven by it.", life: 6000 }); } catch (e) { /* the line on the node is enough */ }
        }
        app.canvas?.setDirty(true, true);
      } catch (e) { /* a convenience */ }
    };
    for (const name of ["Preset", "Mode"]) {
      const w = W(name);
      if (!w) continue;
      const cb = w.callback;
      w.callback = function () {
        const r = cb?.apply(this, arguments);
        applySuggestion(name === "Mode");
        if (name === "Mode") updateInfo();      // v0.3.10: the info line differs between v2v and i2v      // v0.2.6: Mode v2v -> Audio From Video, i2v -> MiniMax Audio on the MTV node(s); v0.3.0: unless the preset is a musician one
        return r;
      };
    }
  }

  node.addDOMWidget("thumbnails", "il78_grid", gwrap, { serialize: false, hideOnZoom: false, getMinHeight: () => 290 });
  node.addDOMWidget("video_slot", "il78_video", vwrap, {
    serialize: false, hideOnZoom: false, getMinHeight: () => 175, getMaxHeight: () => 230,
  });

  function refresh() {
    for (let i = 1; i <= N; i++) refreshCell(i);
    refreshVideo();
  }
  node._il78 = { refresh, closePanel, setVideo: (v) => { set("video", v); refreshVideo(); }, autoSync: () => doSync(true) };
  const onRemoved = node.onRemoved;
  node.onRemoved = function () { closePanel(); clearInterval(syncTimer); return onRemoved?.apply(this, arguments); };

  node.setSize([Math.max(node.size[0], 400), Math.max(node.size[1], node.comfyClass === NODE_ALL ? 840 : 690)]);      // the all-in-one also has the prompt box
  refresh();
}

app.registerExtension({
  name: "IronLeo78.9ImagesToBatchToLLM",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_ALL) return;      // v0.1.18: the all-in-one prompt generator shares this UI
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = onNodeCreated?.apply(this, arguments);
      // v0.3.6: the LLM seed does not change by itself. v0.3.11: robust to WHEN the frontend creates the control widget: now, on the next tick
      // and a little later, and only for a fresh node (a loaded workflow keeps its own value)
      const fixSeed = () => {
        if (this._il78Configured) return;
        const ctl = this.widgets?.find((w) => w.name === "control_after_generate");
        if (!ctl) return;
        if (ctl.value !== "fixed") ctl.value = "fixed";
        if (this._il78Defaults) this._il78Defaults[ctl.name] = "fixed";
      };
      fixSeed();
      // v0.0.2d: the values of a fresh node = the defaults for a widget a saved copy lacks
      this._il78Defaults = {};
      for (const w of serializedWidgets(this)) if (w.value !== null && w.value !== undefined) this._il78Defaults[w.name] = w.value;
      setup(this);
      setTimeout(fixSeed, 0);
      setTimeout(fixSeed, 400);
      return r;
    };
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      this._il78Configured = true;      // v0.3.11: a loaded workflow: its own seed control is kept
      // v0.0.2d: a workflow saved with this version or later holds a named copy of the values: when the widgets moved since it
      // was saved, the values are restored BY NAME. Same layout (or no copy): the positional values stay as they are.
      try {
        const ws = serializedWidgets(this);
        const restored = restoreFromShadow(ws.map((w) => w.name), info?.properties?.[SHADOW_KEY], this._il78Defaults);
        if (restored && Array.isArray(info?.widgets_values)) {
          info.widgets_values.splice(0, info.widgets_values.length, ...restored);      // in place: the frontend may hold this array
          ws.forEach((w, i) => { w.value = restored[i]; });
        }
      } catch (e) {
        console.warn("[IronLeo78] 9-Images: named values not restored:", e);
      }
      const r = onConfigure?.apply(this, arguments);
      this._il78?.refresh();
      // v0.5.0: an old numbered preset name (saved before the presets were renamed "Category - Name") is shown under its new name.
      // The value is set directly, WITHOUT the widget's callback, so the user's prompt is not replaced by the preset's example.
      (async () => {
        try {
          const w = this.widgets?.find((x) => x.name === "Preset");
          if (!w || !w.value || w.value === "None") return;
          const j = await (await api.fetchApi("/ironleo78/mtv/presets")).json();
          const next = presetAlias(w.value, j?.aliases, w.options?.values);      // v0.6.0 (M1): only to a name the list offers
          if (next) {
            w.value = next;
            app.canvas?.setDirty(true, true);
          }
        } catch (e) { /* the backend translates old names too */ }
      })();
      return r;
    };
    // v0.0.2d: every save carries the named copy
    const onSerialize = nodeType.prototype.onSerialize;
    nodeType.prototype.onSerialize = function (o) {
      try {
        const copy = buildShadow(serializedWidgets(this));
        this.properties = this.properties || {};
        this.properties[SHADOW_KEY] = copy;
        if (o) {
          o.properties = o.properties || {};
          o.properties[SHADOW_KEY] = copy;
        }
      } catch (e) {
        /* the copy is a safety net only */
      }
      return onSerialize?.apply(this, arguments);
    };
  },
});
