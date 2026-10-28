// v0.0.2: workflow migration now looks at the saved values, not at how many there are (it used to shift the Model Loader's
//         steps / seed out of place on every load + save). A Model Loader whose numbers are already damaged is repaired on load.
// v0.6: the Latent Upscale stage is gone. "Latent Upscale", "Temporal Chunking", "upscale_megapixels", "Upscale Quality" and
//       "Upscale Output" were removed and "Save Latent" (OFF / ON) took the place of "Latent Upscale". A workflow saved with
//       0.5 or older still holds the old values: migrateMakerValues (below) drops the removed ones and maps the old switch
//       (Latent Upscale OFF = the latents were saved) to Save Latent. The Model Loader lost "upscale_model_name" the same way
//       (migrateLoaderValues).
// IronLeo78 MTV (v0.0.2): segment panel (count, next, progress, Reset, Jump / Latest), always-visible
// labelled picture thumbnails and a status box.
// The segment panel is the FIRST widget and the status box the LAST. Thumbnails are display only: never
// serialized, never sent to the backend. The segment counter decides where cutting starts (there are no
// Start Frame / audio_start widgets). The IronLeo78 MTV Model Loader's noise_seed defaults to "fixed" (second
// extension at the end of this file).
// v2.2: when the last node of this type is deleted, the cached models are freed (backend route).
// v2.3: no layout change (the Phased Run widget is gone; the optional 'models' input is a plain socket).
// v2.4: Song Name / Section Name / Section Number widgets and the four output sockets are gone.
//       noise_seed is now the only control_after_generate widget (fixed).
// v2.5: segment panel at the TOP of the node: how many segments the selected video / custom audio holds
//       (for the current segment duration), which one is next, a progress bar and a Reset button.
//       It asks two small backend routes (GET /segments, POST /reset); nothing is serialized.
//       The node shows no saved-video preview any more: the backend returns none.
// v2.6: jump row in the segment panel (number field + Go, and Latest = back to the furthest point reached;
//       POST /jump).
// v2.5.1: ComfyUI's live latent preview during sampling is kept (it is never cleared while a Run is going);
//       it is dropped when the node finishes, and the picked-picture preview is cleared right after a change.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_ID = "IronLeo78_MTV";
const FREE_ROUTE = "/ironleo78/mtv/free";
const SEGMENT_ROUTE = "/ironleo78/mtv/segments";
const RESET_ROUTE = "/ironleo78/mtv/reset";
const JUMP_ROUTE = "/ironleo78/mtv/jump";
const SLOTS = 3;
const NONE = "None";
const THUMB_H = 54;
const WIDGET_H = 90;            // thumbnail grid, one row of three
const MIN_NODE_W = 340;
const STATUS_H = 130;
const CLEAR_WINDOW_MS = 3000;   // how long after a picture change / load the upload preview is cleared
const SEG_H = 146;
const POLL_MS = 3000;           // the counter is also re-read this often (and after every run)
// the widgets the segment count depends on (names as in the node)
const SEG_WIDGETS = [
  "Use Video", "Video File", "Custom Audio File", "Bypassed Audio Latent",
  "duration", "Next Segment On Run",
];

// ---- v0.6: old saved workflows -------------------------------------------------------------------------------
// `names` = the names of the serialized widgets of the node as it is now, `vals` = widgets_values as saved.
// Returns the values in the new order, or null when the workflow already is in the new format (or is not recognised).
const OLD_UPSCALE_BLOCK_05 = ["Latent Upscale", "Temporal Chunking", "upscale_megapixels", "Upscale Quality"];
const OLD_UPSCALE_BLOCK_04 = ["Latent Upscale", "upscale_megapixels"];
// v0.0.2: the old format is recognised by WHAT the values are, never by how many there are. ComfyUI's frontend does not
// always list every saved value as a widget name (the "control after generate" and upload-button values are saved
// without being in `names`), so counting values made the migration fire on workflows that were already in the new
// format and shift the Model Loader's steps / seed out of place.
export function migrateMakerValues(names, vals) {
  if (!Array.isArray(vals) || !names.includes("Save Latent") || names.includes("Latent Upscale")) return null;
  const at = names.indexOf("Save Latent");
  const next = vals[at + 1], after = vals[at + 2];
  let block, tail;
  if (typeof next === "boolean" && typeof after === "number") { block = OLD_UPSCALE_BLOCK_05; tail = ["Upscale Output"]; }   // saved with 0.5: ... Temporal Chunking (bool), upscale_megapixels (number)
  else if (typeof next === "number") { block = OLD_UPSCALE_BLOCK_04; tail = ["Upscale Output"]; }                           // saved with 0.4.1 or older: Latent Upscale, upscale_megapixels (number)
  else return null;                                                                                                       // new format: Save Latent, Guide (bool), picture_1 (text)
  // the old list = the new one with "Save Latent" replaced by the old block, and "Upscale Output" right after "Guide"
  const oldNames = [];
  for (const n of names) {
    if (n === "Save Latent") oldNames.push(...block);
    else if (n === "Guide") oldNames.push(n, ...tail);
    else oldNames.push(n);
  }
  if (vals.length < oldNames.length) return null;
  const old = {};
  oldNames.forEach((n, i) => { old[n] = vals[i]; });
  // old "Latent Upscale" OFF meant "the first-pass latent and conditioning are saved" -> Save Latent ON
  return names.map((n) => (n === "Save Latent" ? old["Latent Upscale"] === false : old[n]));
}

// A Model Loader saved with 0.5 or older has one value more, "upscale_model_name" (text), right after "audio_vae_name";
// in the current format a number (turbo_steps) sits there.
export function migrateLoaderValues(names, vals) {
  if (!Array.isArray(vals) || names.includes("upscale_model_name")) return null;
  const at = names.indexOf("audio_vae_name");
  if (at < 0) return null;
  if (!(typeof vals[at + 1] === "string" && typeof vals[at + 2] === "number")) return null;
  const out = vals.slice();
  out.splice(at + 1, 1);
  return out;
}

// Repairs a Model Loader whose numbers were damaged (for example by the old migration bug: steps / seed saved as "fixed").
// Returns the repaired list, or null when nothing was wrong. The defaults are the Model Loader's own.
const LOADER_DEFAULTS = { custom_lora_strength: 0.65, turbo_steps: 4, full_steps: 25, noise_seed: 1978 };
export function repairLoaderValues(names, vals) {
  if (!Array.isArray(vals)) return null;
  const out = vals.slice();
  let changed = false;
  for (const [key, def] of Object.entries(LOADER_DEFAULTS)) {
    const i = names.indexOf(key);
    if (i < 0 || i >= out.length) continue;
    const v = out[i];
    if (typeof v !== "number" || !Number.isFinite(v)) { out[i] = def; changed = true; }
  }
  const e = names.indexOf("custom_lora_enabled");
  if (e >= 0 && e < out.length && typeof out[e] !== "boolean") { out[e] = false; changed = true; }
  return changed ? out : null;
}

function serializedWidgets(node) {
  return (node.widgets || []).filter((w) => w.serialize !== false && w.options?.serialize !== false);
}

// Applies the migration to the saved info AND to the widgets themselves (litegraph may already have assigned the values
// by the time onConfigure runs, so setting them again is what makes this independent of that order).
function applyMigration(node, info, migrate) {
  const ws = serializedWidgets(node);
  const fixed = migrate(ws.map((w) => w.name), info?.widgets_values);
  if (!fixed) return false;
  info.widgets_values = fixed;
  ws.forEach((w, i) => { if (i < fixed.length) w.value = fixed[i]; });
  return true;
}

function viewUrl(name) {
  return api.apiURL(
    `/view?filename=${encodeURIComponent(name)}&type=input&subfolder=`
  );
}

function fmtTime(sec) {
  sec = Math.max(0, Math.round(Number(sec) || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), r = sec % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(r)}` : `${m}:${pad(r)}`;
}

function buildSegmentPanel() {
  const root = document.createElement("div");
  root.style.cssText = [
    "width:100%", "box-sizing:border-box", "padding:5px 7px", "border-radius:4px",
    "background:var(--comfy-input-bg, #222)", "border:1px solid var(--border-color, #444)",
    "color:var(--input-text, #ddd)", "font:11px sans-serif", "display:flex", "flex-direction:column", "gap:3px",
  ].join(";");

  const top = document.createElement("div");
  top.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:6px;";
  const title = document.createElement("div");
  title.style.cssText = "font:bold 14px sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
  title.textContent = "Segments: \u2026";
  const reset = document.createElement("button");
  reset.textContent = "Reset";
  reset.title = "Put the segment counter back to segment 1";
  reset.style.cssText = [
    "flex:none", "cursor:pointer", "padding:2px 9px", "font:11px sans-serif", "border-radius:4px",
    "background:var(--comfy-menu-bg, #353535)", "color:var(--input-text, #ddd)",
    "border:1px solid var(--border-color, #555)",
  ].join(";");
  top.appendChild(title);
  top.appendChild(reset);

  const next = document.createElement("div");
  next.style.cssText = "font:12px sans-serif;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";

  const bar = document.createElement("div");
  bar.style.cssText = "height:6px;border-radius:3px;background:var(--border-color, #444);overflow:hidden;";
  const fill = document.createElement("div");
  fill.style.cssText = "height:100%;width:0%;background:#3ba776;transition:width .3s;";
  bar.appendChild(fill);

  const detail = document.createElement("div");
  detail.style.cssText = "font:10px/1.3 sans-serif;opacity:0.7;";

  // v2.6: jump row. "Go" sets the counter so the NEXT Run makes that segment; "Latest" goes back to the
  // furthest point reached (only shown while the counter is somewhere before it).
  const btnCss = [
    "flex:none", "cursor:pointer", "padding:2px 9px", "font:11px sans-serif", "border-radius:4px",
    "background:var(--comfy-menu-bg, #353535)", "color:var(--input-text, #ddd)",
    "border:1px solid var(--border-color, #555)",
  ].join(";");
  const jump = document.createElement("div");
  jump.style.cssText = "display:flex;align-items:center;gap:5px;";
  const jumpLabel = document.createElement("span");
  jumpLabel.textContent = "Jump to segment";
  jumpLabel.style.cssText = "font:11px sans-serif;white-space:nowrap;opacity:0.85;";
  const jumpInput = document.createElement("input");
  jumpInput.type = "number";
  jumpInput.min = "1";
  jumpInput.step = "1";
  jumpInput.placeholder = "#";
  jumpInput.title = "Segment number as shown in the panel (1 = the first). The next Run makes that segment.";
  jumpInput.style.cssText = [
    "width:56px", "box-sizing:border-box", "padding:1px 4px", "font:11px sans-serif", "border-radius:4px",
    "background:var(--comfy-input-bg, #222)", "color:var(--input-text, #ddd)",
    "border:1px solid var(--border-color, #555)",
  ].join(";");
  const go = document.createElement("button");
  go.textContent = "Go";
  go.title = "The next Run makes this segment (redo one bad segment without a Reset)";
  go.style.cssText = btnCss;
  const latest = document.createElement("button");
  latest.textContent = "Latest";
  latest.title = "Back to the furthest point reached (where you were before the jump)";
  latest.style.cssText = btnCss + ";display:none;";
  jump.appendChild(jumpLabel);
  jump.appendChild(jumpInput);
  jump.appendChild(go);
  jump.appendChild(latest);


  root.appendChild(top);
  root.appendChild(next);
  root.appendChild(bar);
  root.appendChild(detail);
  root.appendChild(jump);
  return { root, title, reset, next, fill, detail, jumpInput, go, latest };
}

function buildGrid() {
  const root = document.createElement("div");
  root.style.cssText = [
    "display:grid",
    "grid-template-columns:repeat(3,1fr)",
    "gap:4px",
    "width:100%",
    "box-sizing:border-box",
    "padding:2px 0",
    "pointer-events:none",
  ].join(";");

  const cells = [];
  for (let i = 1; i <= SLOTS; i++) {
    const cell = document.createElement("div");
    cell.style.cssText =
      "display:flex;flex-direction:column;align-items:stretch;min-width:0;";

    const frame = document.createElement("div");
    frame.style.cssText = [
      `height:${THUMB_H}px`,
      "border-radius:4px",
      "overflow:hidden",
      "background:var(--comfy-input-bg, #222)",
      "border:1px solid var(--border-color, #444)",
      "display:flex",
      "align-items:center",
      "justify-content:center",
    ].join(";");

    const img = document.createElement("img");
    img.style.cssText = "max-width:100%;max-height:100%;object-fit:contain;display:none;";
    img.draggable = false;

    const empty = document.createElement("span");
    empty.textContent = "empty";
    empty.style.cssText =
      "font:10px sans-serif;opacity:0.45;color:var(--input-text, #ccc);";

    frame.appendChild(img);
    frame.appendChild(empty);

    const label = document.createElement("div");
    label.textContent = `Picture${i}`;
    label.style.cssText =
      "font:bold 11px sans-serif;text-align:center;margin-top:2px;color:var(--input-text, #ddd);";

    const fname = document.createElement("div");
    fname.style.cssText = [
      "font:9px sans-serif",
      "text-align:center",
      "opacity:0.6",
      "white-space:nowrap",
      "overflow:hidden",
      "text-overflow:ellipsis",
      "height:11px",
      "color:var(--input-text, #ccc)",
    ].join(";");

    cell.appendChild(frame);
    cell.appendChild(label);
    cell.appendChild(fname);
    root.appendChild(cell);
    cells.push({ cell, img, empty, fname, last: undefined });
  }
  return { root, cells };
}

app.registerExtension({
  name: "IronLeo78.MTV.Thumbnails",

  async nodeCreated(node) {
    if (node.comfyClass !== NODE_ID) return;

    // ---- segment panel (v2.5): FIRST widget, count + next + progress + Reset ----
    const seg = buildSegmentPanel();
    const segWidget = node.addDOMWidget("segments_view", "ironleo78_segments", seg.root, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => SEG_H,
      getMaxHeight: () => SEG_H,
    });
    segWidget.serialize = false;
    segWidget.computeSize = (width) => [width, SEG_H];

    const { root, cells } = buildGrid();

    const widget = node.addDOMWidget("thumbnails", "ironleo78_thumbs", root, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => WIDGET_H,
      getMaxHeight: () => WIDGET_H,
    });
    widget.serialize = false;
    widget.computeSize = (width) => [width, WIDGET_H];

    // ---- status box: filled from the node's own "text" UI output after every run ----
    const statusBox = document.createElement("textarea");
    statusBox.readOnly = true;
    statusBox.spellcheck = false;
    statusBox.placeholder = "Status appears here after a run.";
    statusBox.style.cssText = [
      "width:100%", "height:100%", "box-sizing:border-box", "resize:none",
      "font:10px/1.35 ui-monospace,Consolas,monospace",
      "background:var(--comfy-input-bg, #222)", "color:var(--input-text, #ddd)",
      "border:1px solid var(--border-color, #444)", "border-radius:4px",
      "padding:4px 6px", "white-space:pre-wrap", "overflow:auto",
    ].join(";");
    const statusWidget = node.addDOMWidget("status_view", "ironleo78_status", statusBox, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => STATUS_H,
    });
    statusWidget.serialize = false;
    const showStatus = (text) => {
      statusBox.value = text || "";
      statusBox.scrollTop = 0;
    };

    const getWidget = (name) => node.widgets?.find((w) => w.name === name);

    // ---- v0.6: workflows saved with the Latent Upscale widgets keep their other settings ----
    const prevConfigure = node.onConfigure;
    node.onConfigure = function (info) {
      try {
        applyMigration(this, info, migrateMakerValues);
      } catch (e) {
        console.warn("[IronLeo78] widget migration skipped:", e);
      }
      return prevConfigure ? prevConfigure.apply(this, arguments) : undefined;
    };

    // Segment panel first, status box last. All our widgets are serialize:false, so moving
    // them never shifts the saved widget values of the real widgets.
    const keepStatusLast = () => {
      const ws = node.widgets;
      if (!ws || ws.length < 2) return;
      let moved = false;
      const s0 = ws.indexOf(segWidget);
      if (s0 > 0) {
        ws.splice(s0, 1);
        ws.unshift(segWidget);
        moved = true;
      }
      const i = ws.indexOf(statusWidget);
      if (i >= 0 && i !== ws.length - 1) {
        ws.splice(i, 1);
        ws.push(statusWidget);
        moved = true;
      }
      if (moved) node.setDirtyCanvas?.(true, true);
    };

    // ---- segment info: asks the backend how many segments the selection holds ----
    let segInfo = null;
    let segSig = null;
    let segFetchedAt = 0;
    let segBusy = false;

    const renderSegments = () => {
      const i = segInfo;
      if (!i || !i.ok) {
        seg.title.textContent = "Segments: \u2014";
        seg.next.textContent = "";
        seg.fill.style.width = "0%";
        seg.detail.textContent = i && i.error ? `Could not read the segment info: ${i.error}` : "Waiting for the backend\u2026";
        return;
      }
      const total = i.total;
      const done = Math.max(0, i.index);
      seg.fill.style.background = "#3ba776";
      const furthest = Math.max(0, Number(i.furthest) || 0);
      seg.latest.style.display = furthest > done ? "" : "none";
      seg.latest.title = `Back to the furthest point reached: the next Run makes segment ${furthest + 1}`;
      if (total) seg.jumpInput.max = String(total);
      if (total === null || total === undefined) {
        seg.title.textContent = "Segments: unknown";
        seg.next.textContent = i.stepping ? `Counter: next is segment ${done + 1}` : "Next Segment On Run is OFF";
        seg.fill.style.width = "0%";
        seg.detail.textContent =
          "Nothing is stepped through. Use Video ON with a video, or Bypassed Audio Latent = Custom Audio with a " +
          "Custom Audio File, or Use Video OFF + Audio From Video with a Video File.";
        return;
      }
      seg.title.textContent = `${total} segment${total === 1 ? "" : "s"}`;
      if (i.finished) {
        seg.next.textContent = i.stepping
          ? `All ${total} done \u2014 the next Run stops quietly. Press Reset to start over.`
          : `Counter is at the end (${done} of ${total} done)`;
        seg.fill.style.width = "100%";
        seg.fill.style.background = "#d9a22b";
      } else {
        seg.next.textContent = i.stepping
          ? `Next: segment ${done + 1} of ${total}  \u00b7  ${done} done, ${total - done} left`
          : `Next Segment On Run is OFF: every Run makes segment 1 (counter at ${done + 1} of ${total})`;
        seg.fill.style.width = `${Math.min(100, (100 * done) / total).toFixed(1)}%`;
      }
      const parts = (i.sources || []).map((x) => `${x.name} ${fmtTime(x.seconds)} \u2192 ${x.segments} segments`);
      const len = `${Number(i.seg_seconds).toFixed(2)} s per segment (${i.frames} frames)`;
      const lim = (i.sources || []).length > 1 ? `  \u00b7  shortest ends the run: ${i.limit}` : "";
      seg.detail.textContent = `${parts.join("  \u00b7  ")}  \u00b7  ${len}${lim}`;
    };

    const fetchSegments = async (force) => {
      if (segBusy) return;
      const values = SEG_WIDGETS.map((n) => getWidget(n)?.value);
      const sig = JSON.stringify(values);
      const now = Date.now();
      if (!force && sig === segSig && now - segFetchedAt < POLL_MS) return;
      segBusy = true;
      segSig = sig;
      segFetchedAt = now;
      try {
        const qs = new URLSearchParams();
        SEG_WIDGETS.forEach((n, k) => qs.set(n, values[k] === undefined || values[k] === null ? "" : String(values[k])));
        const res = await api.fetchApi(`${SEGMENT_ROUTE}?${qs.toString()}`);
        segInfo = await res.json();
      } catch (e) {
        segInfo = null;
      }
      segBusy = false;
      renderSegments();
    };

    // Reset: two clicks (the second within 3 s) so a stray click cannot lose the position.
    let resetArmed = null;
    const resetLabel = (text) => { seg.reset.textContent = text; };
    seg.reset.addEventListener("click", async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (!resetArmed) {
        resetLabel("Sure? Click again");
        resetArmed = setTimeout(() => { resetArmed = null; resetLabel("Reset"); }, 3000);
        return;
      }
      clearTimeout(resetArmed);
      resetArmed = null;
      resetLabel("Reset");
      try {
        const res = await api.fetchApi(RESET_ROUTE, { method: "POST" });
        const out = await res.json();
        if (out && out.busy) {
          resetLabel("A Run is active");
          setTimeout(() => resetLabel("Reset"), 2500);
        }
      } catch (e) {
        /* the next poll shows the real counter */
      }
      fetchSegments(true);
    });

    // v2.6: Go / Latest. A jump is harmless (no confirmation): the guide frames and the clips stay.
    const flash = (button, text, label) => {
      button.textContent = text;
      setTimeout(() => { button.textContent = label; }, 2200);
    };
    const doJump = async (button, label, body) => {
      try {
        const res = await api.fetchApi(JUMP_ROUTE, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const out = await res.json();
        if (out && out.busy) return flash(button, "A Run is active", label);
        if (out && !out.ok) return flash(button, out.error || "Not possible", label);
        seg.jumpInput.value = "";
      } catch (e) {
        /* the next poll shows the real counter */
      }
      fetchSegments(true);
    };
    const onGo = (ev) => {
      ev?.preventDefault?.();
      ev?.stopPropagation?.();
      const n = parseInt(seg.jumpInput.value, 10);
      const total = segInfo && segInfo.ok ? segInfo.total : null;
      if (!Number.isInteger(n) || n < 1 || (total && n > total)) {
        return flash(seg.go, total ? `1 to ${total}` : "1 or more", "Go");
      }
      doJump(seg.go, "Go", { segment: n, total: total || null });
    };
    seg.go.addEventListener("click", onGo);
    seg.latest.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      doJump(seg.latest, "Latest", { latest: true });
    });
    // typing must not trigger ComfyUI shortcuts; Enter = Go
    seg.jumpInput.addEventListener("keydown", (ev) => {
      ev.stopPropagation();
      if (ev.key === "Enter") onGo(ev);
    });
    seg.jumpInput.addEventListener("keyup", (ev) => ev.stopPropagation());

    // The live latent preview (while sampling) is left alone. Two things are dropped:
    //  - the frontend's big preview of a picked picture (it would cover the thumbnail grid), only
    //    right after a picture changed or at load, never during a run;
    //  - the last step preview when the node has finished (the node returns no saved video).
    let clearUntil = Date.now() + 5000;
    const dropPreview = (force) => {
      try {
        if (!force && Date.now() >= clearUntil) return;
        if (force) {
          const id = String(node.id);
          if (app.nodePreviewImages && app.nodePreviewImages[id]) delete app.nodePreviewImages[id];
        }
        if (node.imgs) {
          node.imgs = null;
          node.setDirtyCanvas?.(true, true);
        }
      } catch (e) {
        /* cosmetic only */
      }
    };

    const refresh = () => {
      for (let i = 1; i <= SLOTS; i++) {
        const value = getWidget(`picture_${i}`)?.value;
        const cell = cells[i - 1];
        if (cell.last === value) continue;
        cell.last = value;
        clearUntil = Date.now() + CLEAR_WINDOW_MS;

        if (!value || value === NONE) {
          cell.img.style.display = "none";
          cell.img.removeAttribute("src");
          cell.empty.style.display = "";
          cell.fname.textContent = "";
          cell.fname.title = "";
        } else {
          cell.empty.style.display = "none";
          cell.img.style.display = "";
          cell.img.src = viewUrl(value);
          cell.fname.textContent = value;
          cell.fname.title = value;
        }
      }

      dropPreview(false);
      keepStatusLast();
      fetchSegments(false);
    };

    // After every run: show the report, re-read the counter, drop any preview.
    const onExecuted = (e) => {
      if (String(e?.detail?.node) !== String(node.id)) return;
      try {
        const t = e?.detail?.output?.text;
        const text = Array.isArray(t) ? t.join("\n") : (typeof t === "string" ? t : "");
        if (text) {
          showStatus(text);
          node.properties = node.properties || {};
          node.properties.last_status = text;   // survives reload / save
        }
        dropPreview(true);
        node.setDirtyCanvas?.(true, true);
        setTimeout(keepStatusLast, 100);
        setTimeout(() => fetchSegments(true), 300);    // the counter was saved before this event
      } catch (err) {
        /* cosmetic only */
      }
    };
    api.addEventListener("executed", onExecuted);

    const timer = setInterval(refresh, 400);

    const origRemoved = node.onRemoved;
    node.onRemoved = function (...args) {
      clearInterval(timer);
      if (resetArmed) clearTimeout(resetArmed);
      api.removeEventListener("executed", onExecuted);
      // v2.2: when the LAST MTV is gone, ask the backend to free the cached models.
      // Delayed + re-checked, so loading another workflow that has the node does not unload anything.
      setTimeout(() => {
        try {
          const stillThere = (app.graph?._nodes || []).some((n) => n.comfyClass === NODE_ID);
          if (!stillThere) {
            api.fetchApi(FREE_ROUTE, { method: "POST" }).catch(() => {});
          }
        } catch (e) {
          /* cosmetic only */
        }
      }, 3000);
      return origRemoved ? origRemoved.apply(this, args) : undefined;
    };

    setTimeout(() => {
      try {
        const size = node.computeSize ? node.computeSize() : node.size;
        node.setSize([Math.max(node.size[0], MIN_NODE_W), Math.max(node.size[1], size[1])]);
        node.setDirtyCanvas?.(true, true);
      } catch (e) {
        /* sizing is cosmetic */
      }
      refresh();
      fetchSegments(true);
      if (node.properties?.last_status) showStatus(node.properties.last_status);
    }, 100);
  },
});

// v2.8.5: the Model Loader owns noise_seed now: its "control after generate" defaults to "fixed" (new node only; a
// loaded workflow restores its own saved value right after this).
app.registerExtension({
  name: "IronLeo78.ModelLoader.SeedFixed",
  async nodeCreated(node) {
    if (node.comfyClass !== "IronLeo78_MTV_ModelLoader") return;
    // v0.6: a Model Loader saved with 0.5 or older has one value more (upscale_model_name): drop it
    const prevConfigure = node.onConfigure;
    node.onConfigure = function (info) {
      try {
        applyMigration(this, info, migrateLoaderValues);
        applyMigration(this, info, repairLoaderValues);
      } catch (e) {
        console.warn("[IronLeo78] Model Loader migration skipped:", e);
      }
      return prevConfigure ? prevConfigure.apply(this, arguments) : undefined;
    };
    try {
      const ctl = (node.widgets || []).find((w) => w.name === "control_after_generate");
      if (ctl) ctl.value = "fixed";
    } catch (e) {
      /* cosmetic only */
    }
  },
});
