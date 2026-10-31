// v0.0.9H: the Picture1-9 pickers, the "More References" switch and the thumbnail gallery are gone from the node: the nine reference
//         pictures only come in through the optional IMAGE inputs Picture_1 .. Picture_9 (always on). Those widgets were the LAST ones,
//         so no saved value moves; the extra values an old workflow still holds are trimmed on load (dropOldPictureValues).
// v0.0.9: Model Loader: "Set New Defaults" button (a panel above the widgets, serialize:false so no saved value moves): SAVES the loader's
//         current values as the new defaults (POST /save_defaults, mtv_defaults.json), reads them back from the backend, prints a
//         confirmation line + a toast. The MTV uses them from its next run. "Factory" goes back to the built-in values.
// v0.0.9: Model Loader: three custom LoRAs (LoRa_1..3), all after the Turbo LoRA; every saved value of the loader moved, so
//         migrateLoaderLayout re-orders old workflows (by what the values are). full_steps now starts at 40.
// v0.0.8: six more reference pictures (Picture4-9 = <Picture 4> ... <Picture 9>) behind a "More References" OFF / ON switch.
//         OFF (default) hides their pickers and thumbnails (and the backend ignores them); the thumbnail grid grows to three rows with ON.
//         Old workflows load as before (migrateMoreReferences repairs the values that land on the new widgets).
// v0.0.7: Audio Stem "Song" is now called "Full" (saved workflows are converted on load: migrateAudioStem).
//         New nodes start with duration 5 s (megapixels stays 0.2).
// v0.0.6: the "Video failed to load" box at the bottom of the node is gone. It appeared when the Video File picker was on
//         "None" (ComfyUI's frontend then tries to preview a file called "None"). That placeholder preview is removed; the
//         preview of a real picked video is kept. ALWAYS_HIDE_VIDEO_PREVIEW (top of this file) = true hides it in every case.
// v0.0.5: the widget "Bypassed Audio Latent" is now called "Choose Audio latent" (same position, same values: saved workflows
//         load as before). The node has two outputs (video, filename) and saves no clip itself; the video preview at the
//         bottom of the node (the one the Video File picker adds) is hidden, and the last-step preview is still dropped.
// v0.0.3: the audio source is a list now: MiniMax Audio | Audio From Video | Custom Audio (old OFF / ON values are converted).
// v0.0.2: workflow migration now looks at the saved values, not at how many there are (it used to shift the Model Loader's
//         steps / seed out of place on every load + save). A Model Loader whose numbers are already damaged is repaired on load.
// v0.6: the Latent Upscale stage is gone. "Latent Upscale", "Temporal Chunking", "upscale_megapixels", "Upscale Quality" and
//       "Upscale Output" were removed and "Save Latent" (OFF / ON) took the place of "Latent Upscale". A workflow saved with
//       0.5 or older still holds the old values: migrateMakerValues (below) drops the removed ones and maps the old switch
//       (Latent Upscale OFF = the latents were saved) to Save Latent. The Model Loader lost "upscale_model_name" the same way
//       (migrateLoaderValues).
// IronLeo78 MTV (v0.6.3): segment panel (count, next, progress, Reset, Jump / Latest), always-visible
// (no picture thumbnails since v0.0.9H). (The status box at the bottom of the node is gone since v0.0.9: the report leaves on the
// third output, `status` (STRING).)
// The segment panel is the FIRST widget. It is display only: never
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
//       it is dropped when the node finishes, and a preview is cleared right after a change.

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { mirrorVideo, collectNodes, liveNodes, useVideoAudio, normFile, PROMPT_GEN_NODE } from "./il78_sync_logic.js";

// v0.0.6: ComfyUI's frontend stores a "preview" of every file picker (Video File; and picture_1..3 until v0.0.9H) in app.nodeOutputs and
// draws it at the bottom of the node. With the picker on "None" that preview points at a file called "None": for the
// Video File picker the frontend then prints "Video failed to load". Only that placeholder is removed; a real picked
// video keeps its preview. Set this to true to hide the video preview even when a real video is picked.
const ALWAYS_HIDE_VIDEO_PREVIEW = false;
const VIDEO_NAME = /\.(mp4|webm|mov|mkv|avi|m4v)$/i;

// true when this stored output is only the "None" placeholder (or, with alwaysHideVideo, a video preview)
export function isPlaceholderPreview(output, alwaysHideVideo = false) {
  const images = output && Array.isArray(output.images) ? output.images.filter(Boolean) : [];
  if (!images.length) return false;
  const names = images.map((im) => String(im.filename ?? "").trim());
  if (names.every((n) => n === "" || n === "None")) return true;
  return !!alwaysHideVideo && names.every((n) => VIDEO_NAME.test(n));
}

// Removes the placeholder preview of node `nodeId` from `outputs` (app.nodeOutputs). Returns true when something went.
// A node inside a subgraph is stored as "<subgraph id>:<node id>": those keys are only touched for the "None" case.
export function dropNonePreview(outputs, nodeId, alwaysHideVideo = false) {
  if (!outputs) return false;
  const id = String(nodeId);
  let dropped = false;
  for (const key of Object.keys(outputs)) {
    const exact = key === id;
    if (!exact && !key.endsWith(":" + id)) continue;
    if (isPlaceholderPreview(outputs[key], exact && alwaysHideVideo)) {
      delete outputs[key];
      dropped = true;
    }
  }
  return dropped;
}

const NODE_ID = "IronLeo78_MTV";
const FREE_ROUTE = "/ironleo78/mtv/free";
const SEGMENT_ROUTE = "/ironleo78/mtv/segments";
const RESET_ROUTE = "/ironleo78/mtv/reset";
const JUMP_ROUTE = "/ironleo78/mtv/jump";
const MIN_NODE_W = 340;
const SEG_H = 172;      // v0.2.4: room for the "Jump to time" row (146 before)
const POLL_MS = 3000;           // the counter is also re-read this often (and after every run)
// the widgets the segment count depends on (names as in the node)
const SEG_WIDGETS = [
  "Use Video", "Video File", "Custom Audio File", "Choose Audio latent",
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
  const all = names;
  const at = names.indexOf("Save Latent");
  const next = vals[at + 1], after = vals[at + 2];
  let block, tail;
  if (typeof next === "boolean" && typeof after === "number") { block = OLD_UPSCALE_BLOCK_05; tail = ["Upscale Output"]; }   // saved with 0.5: ... Temporal Chunking (bool), upscale_megapixels (number)
  else if (typeof next === "number") { block = OLD_UPSCALE_BLOCK_04; tail = ["Upscale Output"]; }                           // saved with 0.4.1 or older: Latent Upscale, upscale_megapixels (number)
  else return null;                                                                                                       // new format: Save Latent, Guide (bool), then nothing (the pictures are inputs now)
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
  return all.map((n) => (n === "Save Latent" ? old["Latent Upscale"] === false : old[n]));
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

// v0.0.9: the Model Loader has three custom LoRAs (LoRa_1..3, each: _enabled, file, _strength) right AFTER turbo_lora_name.
// Before, one "custom_lora_enabled / custom_lora_name / custom_lora_strength" block sat right after unet_name, so every
// value from position 1 to 4 moved. The saved values are re-ordered here, and recognised by WHAT they are, never by count:
//   layout A (0.0.8 and older): [unet, <bool> enabled, <text> lora, <number> strength, turbo, qwen, vvae, avae, (upscale), steps...]
//   layout C (before the custom LoRA existed): [unet, <text> turbo, <text> qwen, vvae, avae, (upscale), steps...]
//   layout D (0.0.9 to 0.1.10): [unet, <text> turbo, <bool> LoRa_1_enabled, ...]
//   new layout (v0.1.11): [unet, <text> turbo, <number> turbo_lora_strength, <bool> LoRa_1_enabled, ...]
const LORA_SLOTS = 3;
const LORA_DEFAULT_STRENGTH = 1.0;         // v0.1.11 (0.65 until 0.1.10)
const TURBO_DEFAULT_STRENGTH = 1.0;        // v0.1.11: the Turbo LoRA strength was hardcoded to this before it got a widget
const NONE_LORA = "None";
export function migrateLoaderLayout(names, vals) {
  if (!Array.isArray(vals) || !names.includes("LoRa_1_enabled")) return null;
  const hasTurboStr = names.includes("turbo_lora_strength");
  let a;                                   // the old layout: where the model files start
  if (typeof vals[1] === "boolean") a = "A";
  else if (typeof vals[1] === "string" && typeof vals[2] === "string") a = "C";
  else if (hasTurboStr && typeof vals[1] === "string" && typeof vals[2] === "boolean") a = "D";
  else return null;                        // the new layout (or something unknown): left alone
  if (a === "D") {                         // v0.1.11: only the Turbo LoRA strength is new, right after the Turbo LoRA file
    const out = vals.slice();
    out.splice(names.indexOf("turbo_lora_strength"), 0, TURBO_DEFAULT_STRENGTH);
    return out;
  }
  let i = 0;
  const unet = vals[i++];
  let en = false, lora = NONE_LORA, str = LORA_DEFAULT_STRENGTH;
  if (a === "A") { en = vals[i++]; lora = vals[i++]; str = vals[i++]; }
  const turbo = vals[i++], qwen = vals[i++], vvae = vals[i++], avae = vals[i++];
  // 0.5 and older: one text value more (upscale_model_name) before the numbers
  if (typeof vals[i] === "string" && typeof vals[i + 1] === "number") i++;
  const rest = vals.slice(i);              // turbo_steps, full_steps, noise_seed, then values without a name (control after generate)
  const byName = { unet_name: unet, turbo_lora_name: turbo, turbo_lora_strength: TURBO_DEFAULT_STRENGTH, qwen_vl_name: qwen, video_vae_name: vvae, audio_vae_name: avae,
    turbo_steps: rest[0], full_steps: rest[1], noise_seed: rest[2],
    LoRa_1_enabled: en, LoRa_1: lora, LoRa_1_strength: str };
  for (let n = 2; n <= LORA_SLOTS; n++) {
    byName[`LoRa_${n}_enabled`] = false; byName[`LoRa_${n}`] = NONE_LORA; byName[`LoRa_${n}_strength`] = LORA_DEFAULT_STRENGTH;
  }
  const out = names.map((n) => byName[n]);
  return out.concat(rest.slice(3));
}

// Repairs a Model Loader whose values were damaged (for example by the old migration bug: steps / seed saved as "fixed").
// Returns the repaired list, or null when nothing was wrong. The defaults are the Model Loader's own.
const LOADER_DEFAULTS = { turbo_lora_strength: TURBO_DEFAULT_STRENGTH, turbo_steps: 6, full_steps: 30, noise_seed: 1978 };      // v0.1.11: 6 / 30 (was 4 / 40)
for (let n = 1; n <= LORA_SLOTS; n++) LOADER_DEFAULTS[`LoRa_${n}_strength`] = LORA_DEFAULT_STRENGTH;
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
  for (let n = 1; n <= LORA_SLOTS; n++) {
    const e = names.indexOf(`LoRa_${n}_enabled`);
    if (e >= 0 && e < out.length && typeof out[e] !== "boolean") { out[e] = false; changed = true; }
    const f = names.indexOf(`LoRa_${n}`);
    if (f >= 0 && f < out.length && typeof out[f] !== "string") { out[f] = NONE_LORA; changed = true; }
  }
  return changed ? out : null;
}

// v0.0.9: the Model Loader also keeps a copy of its values BY NAME in its properties (`ironleo78_values`, written on every
// save). Saved values are positional, so every update that moves a widget used to shift them on load. The named copy does not
// care about the order: on load, a workflow that holds it is restored by name. Workflows saved before this release do not hold
// it yet: they still go through the position-based migrations above (and carry the copy from their next save on).
export const SHADOW_KEY = "ironleo78_values";
export const CONTROL_KEY = "control_after_generate";
export const LAYOUT_KEY = "__layout";          // the widget names in their saved order: when it equals the current order nothing moved
const typeOk = (name, v) => {
  if (name.endsWith("_enabled")) return typeof v === "boolean";
  if (name.endsWith("_steps") || name.endsWith("_strength") || name === "noise_seed") return typeof v === "number" && Number.isFinite(v);
  return typeof v === "string";
};
// names = serialized widget names (current order), shadow = {name: value, ...}, defaults = {name: value} of a fresh node.
// Returns the values list in the current order (+ the control value at the end), or null when there is no usable copy.
export function restoreFromShadow(names, shadow, defaults, opts = {}) {
  const ok = typeof opts.typeOk === "function" ? opts.typeOk : typeOk;     // v0.0.9t: the Maker brings its own type rules
  if (!shadow || typeof shadow !== "object" || Array.isArray(shadow)) return null;
  if (!names.some((n) => Object.prototype.hasOwnProperty.call(shadow, n))) return null;
  // the widgets are in the same order as when the workflow was saved: the positional values are right (and a value edited
  // by hand in the workflow file stays as edited), the named copy is not needed
  if (shadow[LAYOUT_KEY] === names.join("|")) return null;
  const out = names.map((n) => {
    const v = shadow[n];
    if (Object.prototype.hasOwnProperty.call(shadow, n) && ok(n, v)) return v;
    return defaults ? defaults[n] : undefined;           // a widget added after the copy was made (or a damaged value): its default
  });
  if (out.some((v) => v === undefined)) return null;
  if (opts.control === false) return out;                 // v0.0.9t: a node without a "control after generate" value (the Maker)
  const ctl = typeof shadow[CONTROL_KEY] === "string" ? shadow[CONTROL_KEY] : "fixed";
  return out.concat([ctl]);
}

// v0.0.9t: the MAKER node keeps the same kind of named copy (`properties.ironleo78_values`, same key and same `__layout` rule as
// the Model Loader). Until now only the Loader had it, so the next time a Maker widget moved, old workflows depended on
// position-based migrations again. The Maker has no seed, so its copy holds no control value.
const MAKER_TYPES = { Turbo: "boolean", "Use Video": "boolean", "Video File": "string", "Custom Audio File": "string", "Audio Stem": "string",
  megapixels: "number", duration: "number", "Next Segment On Run": "boolean", prompt: "string", "Choose Audio latent": "string",
  "Save Latent": "boolean", Guide: "boolean" };
// a value must have the type its widget has (a widget this table does not know: any plain value)
export function makerTypeOk(name, v) {
  const t = MAKER_TYPES[name];
  if (t === "number") return typeof v === "number" && Number.isFinite(v);
  if (t) return typeof v === t;
  return typeof v === "string" || typeof v === "boolean" || (typeof v === "number" && Number.isFinite(v));
}
// the copy to write on every save: {widgetName: value, ..., __layout}. serial = the node's serialized widgets
export function buildShadow(serial) {
  const copy = {};
  for (const w of serial) copy[w.name] = w.value;
  copy[LAYOUT_KEY] = serial.map((w) => w.name).join("|");
  return copy;
}

// v0.0.9: "Set New Defaults" on the Model Loader. Pure helpers (unit-tested without a browser).
export const LOADER_DEFAULTS_ROUTE = "/ironleo78/mtv/loader_defaults";
export const SAVE_DEFAULTS_ROUTE = "/ironleo78/mtv/save_defaults";
export const RESET_DEFAULTS_ROUTE = "/ironleo78/mtv/reset_defaults";
const sameValue = (a, b) => (typeof a === "number" && typeof b === "number" ? Math.abs(a - b) < 1e-9 : a === b);

// the values to save: what the Model Loader's serialized widgets hold right now, by name
export function collectLoaderValues(serial) {
  const out = {};
  for (const w of serial) out[w.name] = w.value;
  return out;
}
// after saving, the backend is asked again for the defaults it now holds: every value we sent must come back the same
// (v0.0.9: sentControl / backControl = the seed's "control after generate", saved with the values; only compared when one was sent)
export function verifySavedDefaults(sent, backendDefaults, sentControl, backControl) {
  const names = Object.keys(sent);
  const bad = names.filter((n) => !backendDefaults || !Object.prototype.hasOwnProperty.call(backendDefaults, n) || !sameValue(backendDefaults[n], sent[n]));
  let total = names.length;
  if (typeof sentControl === "string") {
    total += 1;
    if (backControl !== sentControl) bad.push(CONTROL_KEY);
  }
  return { total, ok: total - bad.length, bad };
}
export function savedMessage(check, missing) {
  if (check.bad.length) return { level: "error", text: `✖ Saved, but ${check.ok} of ${check.total} values came back the same. Different: ${check.bad.join(", ")}` };
  if (missing && missing.length) return { level: "warn", text: `⚠ New defaults saved (${check.ok} of ${check.total} values read back), but these files are not installed: ${missing.join(", ")}` };
  return { level: "ok", text: `✔ New defaults saved: ${check.ok} of ${check.total} values stored and read back from the backend. The MTV uses them from its next run, and this Model Loader loads the same set again every time it is opened.` };
}

// "Factory": widgets back to the built-in values. widgets = [{name, value, values}] (values = the list of a combo, else null).
// A combo whose factory file is NOT installed keeps its current value and is reported (an optional LoRa_n file falls back to None).
export function planLoaderDefaults(widgets, defaults) {
  const set = {}, missing = [];
  if (!defaults || typeof defaults !== "object") return { set, missing };
  for (const w of widgets) {
    if (!Object.prototype.hasOwnProperty.call(defaults, w.name)) continue;
    const want = defaults[w.name];
    if (Array.isArray(w.values)) {
      if (w.values.includes(want)) set[w.name] = want;
      else if (/^LoRa_\d+$/.test(w.name) && w.values.includes(NONE_LORA)) set[w.name] = NONE_LORA;
      else missing.push({ name: w.name, want, keep: w.value });
    } else set[w.name] = want;
  }
  return { set, missing };
}
// reads the values back (what the widgets hold NOW) and compares them with what was meant to be set
export function verifyLoaderDefaults(widgets, plan) {
  const now = Object.fromEntries(widgets.map((w) => [w.name, w.value]));
  const names = Object.keys(plan.set);
  const bad = names.filter((n) => !sameValue(now[n], plan.set[n]));
  return { total: names.length, ok: names.length - bad.length, bad };
}
export function defaultsMessage(plan, check) {
  if (check.bad.length) return { level: "error", text: `✖ Factory defaults: ${check.ok} of ${check.total} values set. Did not take: ${check.bad.join(", ")}` };
  if (plan.missing.length) {
    return { level: "warn", text: `⚠ Factory defaults: ${check.ok} of ${check.total} values set and verified. Not installed (kept as they were): `
      + plan.missing.map((m) => `${m.name} (default ${m.want})`).join(", ") };
  }
  return { level: "ok", text: `✔ Factory defaults restored (the saved defaults are cleared): ${check.ok} of ${check.total} values verified` };
}
// v0.2.4: "Jump to time". parseClock("83") / ("1:23") / ("01:23.5") / ("1:02:03") -> seconds, or null when it is not a time.
export function parseClock(text) {
  const s = String(text ?? "").trim();
  if (!/^\d+(\.\d+)?(:\d{1,2}(\.\d+)?){0,2}$/.test(s)) return null;
  const parts = s.split(":").map(Number);
  if (parts.length > 1 && parts.slice(1).some((p) => p >= 60)) return null;      // 1:75 is not a time
  return parts.reduce((acc, p) => acc * 60 + p, 0);
}
export function fmtClock(seconds) {
  const ms = Math.round(Math.max(0, seconds) * 1000);
  const h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60, s = Math.floor(ms / 1000) % 60, f = ms % 1000;
  const mmss = `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}${f ? "." + String(f).padStart(3, "0").replace(/0+$/, "") : ""}`;
  return h ? `${h}:${mmss}` : mmss;
}
// the segment that contains `seconds` (segments are segSeconds long, counted from 1, like the panel): {ok, segment, start} or {ok:false, error}.
export function segmentForTime(seconds, segSeconds, total) {
  if (!(seconds >= 0) || !(segSeconds > 0)) return { ok: false, error: "Not a time" };
  const segment = Math.floor(seconds / segSeconds + 1e-9) + 1;
  if (total && segment > total) return { ok: false, error: `Ends at ${fmtClock(total * segSeconds)}` };
  return { ok: true, segment, start: (segment - 1) * segSeconds };
}

// v0.1.20: a workflow saved before the nine Picture_<n> sockets were removed still lists them: drop the ones with no wire (a wired one
// stays and keeps working, the backend still honours a Picture_<n> key). Returns how many were dropped.
export function dropLegacyPictureInputs(node) {
  let n = 0;
  const ins = node.inputs || [];
  for (let i = ins.length - 1; i >= 0; i--) {
    if (/^Picture_[1-9]$/.test(ins[i]?.name || "") && (ins[i].link === null || ins[i].link === undefined)) {
      node.removeInput?.(i);
      n++;
    }
  }
  return n;
}
// sets the node's widgets to the given values and checks them. serial = the node's serialized widgets, control = the "control after generate" widget (or null)
// controlValue (v0.0.9): what the seed control becomes ("fixed" for Factory, the saved one when a saved set is loaded; null = leave it as it is)
export function applyLoaderDefaults(serial, control, defaults, controlValue = "fixed") {
  const comboValues = (w) => {
    const v = w.options?.values;
    return Array.isArray(v) ? v : typeof v === "function" ? v() : null;
  };
  const view = () => serial.map((w) => ({ name: w.name, value: w.value, values: comboValues(w) }));
  const plan = planLoaderDefaults(view(), defaults);
  for (const w of serial) {
    if (!(w.name in plan.set)) continue;
    w.value = plan.set[w.name];
    try { w.callback?.(w.value); } catch (e) { /* the value is set, the callback is cosmetic */ }
  }
  if (control && controlValue !== null) control.value = controlValue;
  const check = verifyLoaderDefaults(view(), plan);
  if (control && controlValue !== null) { check.total += 1; if (control.value === controlValue) check.ok += 1; else check.bad.push(CONTROL_KEY); }
  return { plan, check, message: defaultsMessage(plan, check) };
}

// v0.0.9: the SAVED SET is loaded again every time a Model Loader is created or a workflow is opened (when a set was saved).
// before = {name: value} of the widgets before the set was applied, set = {name: value} that was applied.
// Returns [{name, from, to}] for every value that was different (what the workflow held and the saved set replaced).
export function changedBySet(before, set, controlFrom, controlTo) {
  const out = [];
  for (const n of Object.keys(set || {})) {
    if (Object.prototype.hasOwnProperty.call(before, n) && !sameValue(before[n], set[n])) out.push({ name: n, from: before[n], to: set[n] });
  }
  if (typeof controlTo === "string" && typeof controlFrom === "string" && controlFrom !== controlTo) out.push({ name: CONTROL_KEY, from: controlFrom, to: controlTo });
  return out;
}
export function loadedSetMessage(result, changed) {
  const { plan, check } = result;
  if (check.bad.length) return { level: "error", text: `✖ Saved set: ${check.ok} of ${check.total} values loaded. Did not take: ${check.bad.join(", ")}` };
  const miss = plan.missing.length ? ` Not installed (kept as they were): ${plan.missing.map((m) => `${m.name} (${m.want})`).join(", ")}.` : "";
  if (changed.length) {
    const shown = changed.slice(0, 6).map((c) => `${c.name} ${c.from} → ${c.to}`).join(", ") + (changed.length > 6 ? `, +${changed.length - 6} more` : "");
    return { level: "warn", text: `⚠ Saved set loaded (${check.ok} of ${check.total} values). This node held other values, now replaced: ${shown}. Click Set New Defaults to keep different ones.${miss}` };
  }
  return { level: plan.missing.length ? "warn" : "ok", text: `✔ Saved set loaded: ${check.ok} of ${check.total} values, same as the MTV uses.${miss}` };
}

// v0.0.3: the audio widget (called "Bypassed Audio Latent" until v0.0.5) was an OFF / ON switch (OFF = Audio From Video, ON = Custom Audio); it is now a list
// (MiniMax Audio | Audio From Video | Custom Audio) at the same position, so only the saved value is converted.
export function migrateAudioMode(names, vals) {
  if (!Array.isArray(vals)) return null;
  const at = names.indexOf("Choose Audio latent");
  if (at < 0 || typeof vals[at] !== "boolean") return null;
  const out = vals.slice();
  out[at] = vals[at] ? "Custom Audio" : "Audio From Video";
  return out;
}

// v0.0.9H: the picture_1..9 pickers and the More References switch were the LAST widgets of the node (right after Guide). They are
// gone, so an old workflow holds 10 to 19 values more than the node has widgets. Nothing before them moves; the surplus at the END
// is simply cut. Recognised by WHAT the values are (picker file names, the switch, the upload button's "image" / null), never by
// count alone: a surplus value that is a number or an object (something else) means "not recognised", nothing is touched.
export function dropOldPictureValues(names, vals) {
  if (!Array.isArray(vals) || !names.includes("Guide")) return null;
  const n = names.length;
  if (vals.length <= n) return null;
  const surplus = vals.slice(n);
  if (!surplus.every((v) => v === null || typeof v === "string" || typeof v === "boolean")) return null;
  return vals.slice(0, n);
}

// v0.0.7: the Audio Stem choice "Song" (the whole mix) is now called "Full". A saved workflow still holds "Song".
export function migrateAudioStem(names, vals) {
  if (!Array.isArray(vals)) return null;
  const at = names.indexOf("Audio Stem");
  if (at < 0 || vals[at] !== "Song") return null;
  const out = vals.slice();
  out[at] = "Full";
  return out;
}

// v0.1.11: "Choose Audio latent" MOVED from right after "prompt" (position 9) to right under "Video File" (position 3).
// Workflows with the named copy are restored by name (restoreFromShadow). The rest (saved before v0.0.9t, or a copy that says the
// order did not change) go through the positional route: the old migrations above all expect the OLD order, so they run against
// legacyMakerNames(names) and the result is then put in the new order. Recognised by WHAT the values are, never by count:
// old order = position 3 holds the Custom Audio File (not an audio mode) and position 9 the audio mode (a boolean before v0.0.3).
export const AUDIO_MODES = ["MiniMax Audio", "Audio From Video", "Custom Audio"];
const MOVED = "Choose Audio latent";
export function legacyMakerNames(names) {
  if (!names.includes(MOVED) || !names.includes("prompt")) return null;
  const out = names.filter((n) => n !== MOVED);
  out.splice(out.indexOf("prompt") + 1, 0, MOVED);
  return out;
}
export function isLegacyMakerOrder(names, vals) {
  const legacy = legacyMakerNames(names);
  if (!legacy || !Array.isArray(vals) || legacy.join("|") === names.join("|")) return false;
  const now = names.indexOf(MOVED), old = legacy.indexOf(MOVED);
  if (now >= vals.length || old >= vals.length) return false;
  if (AUDIO_MODES.includes(vals[now])) return false;                                    // already in the new order
  return AUDIO_MODES.includes(vals[old]) || typeof vals[old] === "boolean";
}
// the values (in the old order, after the old migrations) put in the current order; values past the widgets stay at the end
export function moveAudioLatentUp(legacy, names, vals) {
  const byName = {};
  legacy.forEach((n, i) => { if (i < vals.length) byName[n] = vals[i]; });
  const out = names.map((n) => byName[n]);
  if (out.some((v) => v === undefined)) return null;
  return out.concat(vals.slice(legacy.length));
}
// the whole positional route of the Maker as ONE pure step: returns {vals, dropped} (dropped = old picture values were cut) or null
export function migrateMakerPositional(names, vals) {
  if (!Array.isArray(vals)) return null;
  const legacy = isLegacyMakerOrder(names, vals) ? legacyMakerNames(names) : null;
  const order = legacy || names;
  let cur = vals, changed = false, dropped = false;
  for (const m of [migrateMakerValues, migrateAudioMode, migrateAudioStem, dropOldPictureValues]) {
    const fixed = m(order, cur);
    if (fixed) { cur = fixed; changed = true; if (m === dropOldPictureValues) dropped = true; }
  }
  if (legacy) {
    const moved = moveAudioLatentUp(legacy, names, cur);
    if (!moved) return null;
    cur = moved; changed = true;
  }
  return changed ? { vals: cur, dropped } : null;
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
  // v0.0.9: rewrite the saved array IN PLACE (not just replace the property): if the frontend kept its own reference to the
  // array and assigns the widget values from it AFTER this hook, it must see the corrected values too.
  if (Array.isArray(info.widgets_values)) info.widgets_values.splice(0, info.widgets_values.length, ...fixed);
  else info.widgets_values = fixed;
  ws.forEach((w, i) => { if (i < fixed.length) w.value = fixed[i]; });
  return true;
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
  reset.title = "Put the segment counter of this song (or video) back to segment 1 (the other songs keep theirs)";
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

  // v0.2.4: the same jump by TIME in the video / song (MM:SS), snapped to the segment that contains it
  const jumpT = document.createElement("div");
  jumpT.style.cssText = "display:flex;align-items:center;gap:5px;";
  const jumpTLabel = document.createElement("span");
  jumpTLabel.textContent = "Jump to time";
  jumpTLabel.style.cssText = "font:11px sans-serif;white-space:nowrap;opacity:0.85;";
  const timeInput = document.createElement("input");
  timeInput.type = "text";
  timeInput.placeholder = "MM:SS";
  timeInput.title = "A time in the video / song, for example 1:23 (or 83 for seconds). The next Run makes the segment that contains it, so it can start up to one segment earlier than the time you typed.";
  timeInput.style.cssText = jumpInput.style.cssText;
  const goTime = document.createElement("button");
  goTime.textContent = "Go time";
  goTime.title = "Same as Go, but you give a time (MM:SS) instead of a segment number";
  goTime.style.cssText = btnCss;
  jumpT.appendChild(jumpTLabel);
  jumpT.appendChild(timeInput);
  jumpT.appendChild(goTime);

  root.appendChild(top);
  root.appendChild(next);
  root.appendChild(bar);
  root.appendChild(detail);
  root.appendChild(jump);
  root.appendChild(jumpT);
  return { root, title, reset, next, fill, detail, jumpInput, go, latest, timeInput, goTime };
}

app.registerExtension({
  name: "IronLeo78.MTV.Panel",

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

    let shrinkOnce = false;    // true when an old workflow (with the picture widgets) was loaded: its saved height is too tall now

    const getWidget = (name) => node.widgets?.find((w) => w.name === name);
    // v0.3.9: the prompt box is shown as "MTV_Prompt" (the name of the Prompt Generator output that goes in here). Display only: the widget keeps
    // its name "prompt", so nothing saved or wired changes.
    { const pw = getWidget("prompt"); if (pw) { pw.label = "MTV_Prompt"; try { if (pw.element) pw.element.placeholder = "MTV_Prompt"; } catch (e) { /* cosmetic */ } } }

    // the values of a fresh node (before any workflow is loaded into it): the defaults for a widget the saved copy lacks.
    // (a widget with no usable value here is left out: then a copy that lacks it is not used, the migrations below take over)
    const makerDefaults = {};
    for (const w of serializedWidgets(node)) if (w.value !== null && w.value !== undefined) makerDefaults[w.name] = w.value;

    // ---- v0.6: workflows saved with the Latent Upscale widgets keep their other settings ----
    const prevConfigure = node.onConfigure;
    node.onConfigure = function (info) {
      try {
        // v0.0.9t: a workflow saved with this release or later holds a named copy of the values: when the widgets moved since
        // it was saved, the values are restored BY NAME (immune to later updates). The copy is read from the saved node only.
        const names = serializedWidgets(this).map((w) => w.name);
        const restored = restoreFromShadow(names, info?.properties?.[SHADOW_KEY], makerDefaults, { typeOk: makerTypeOk, control: false });
        if (restored && Array.isArray(info?.widgets_values)) {
          info.widgets_values.splice(0, info.widgets_values.length, ...restored);        // IN PLACE, like applyMigration
          serializedWidgets(this).forEach((w, i) => { w.value = restored[i]; });
        } else {
          // no copy (a workflow saved before v0.0.9t), or the widgets are in the same order as at save time: the positional route
          // (v0.1.11: one pure step, it also moves "Choose Audio latent" up from its old place)
          let dropped = false;
          applyMigration(this, info, (n, v) => {
            const r = migrateMakerPositional(n, v);
            if (r) dropped = r.dropped;
            return r ? r.vals : null;
          });
          if (dropped) shrinkOnce = true;      // v0.0.9H: pictures are inputs now
        }
      } catch (e) {
        console.warn("[IronLeo78] widget migration skipped:", e);
      }
      const r = prevConfigure ? prevConfigure.apply(this, arguments) : undefined;
      try { dropLegacyPictureInputs(this); } catch (e) { /* cosmetic */ }      // v0.1.20: the nine Picture_n sockets are gone
      return r;
    };
    // every save carries the named copy (same as the Model Loader)
    const prevSerialize = node.onSerialize;
    node.onSerialize = function (o) {
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
      return prevSerialize ? prevSerialize.apply(this, arguments) : undefined;
    };

    // Segment panel first. All our widgets are serialize:false, so moving
    // them never shifts the saved widget values of the real widgets.
    const keepPanelFirst = () => {
      const ws = node.widgets;
      if (!ws || ws.length < 2) return;
      const s0 = ws.indexOf(segWidget);
      if (s0 > 0) {
        ws.splice(s0, 1);
        ws.unshift(segWidget);
        node.setDirtyCanvas?.(true, true);
      }
    };

    // v0.1.8: the widget values that pick the song's counter (one counter per song / video); sent with Reset and Jump too
    const segParams = () => Object.fromEntries(SEG_WIDGETS.map((n) => {
      const v = getWidget(n)?.value;
      return [n, v === undefined || v === null ? "" : String(v)];
    }));

    // ---- segment info: asks the backend how many segments the selection holds ----
    let segInfo = null;
    let segSig = null;
    let segFetchedAt = 0;
    let segBusy = false;

    // v0.3.11: Custom Audio mode with no file: the song is skipped. A quiet hint on the node, not a warning (it is the default of a new node)
    const songHint = () => {
      const a = getWidget("Choose Audio latent")?.value, f = getWidget("Custom Audio File")?.value;
      return a === "Custom Audio" && (!f || String(f).toLowerCase() === "none") ? "  \u00b7  audio: no Custom Audio File, no song is used" : "";
    };
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
          "Nothing is stepped through. Use Video ON with a video, or Choose Audio latent = Custom Audio with a " +
          "Custom Audio File, or Use Video OFF + Audio From Video with a Video File." + songHint();
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
          : `Next Segment On Run is OFF: every Run repeats segment ${done + 1} of ${total} (set it with Go)`;
        seg.fill.style.width = `${Math.min(100, (100 * done) / total).toFixed(1)}%`;
      }
      const parts = (i.sources || []).map((x) => `${x.name} ${fmtTime(x.seconds)} \u2192 ${x.segments} segments`);
      const len = `${Number(i.seg_seconds).toFixed(2)} s per segment (${i.frames} frames)`;
      const lim = (i.sources || []).length > 1 ? `  \u00b7  shortest ends the run: ${i.limit}` : "";
      const own = i.counter ? `  \u00b7  counter: ${i.counter}` : "";      // v0.1.8: one counter per song / video
      seg.detail.textContent = `${parts.join("  \u00b7  ")}  \u00b7  ${len}${lim}${own}${songHint()}`;
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
        const res = await api.fetchApi(RESET_ROUTE, {      // v0.1.8: resets only this song's counter
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ params: segParams() }),
        });
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
    const doJump = async (button, label, body, okText) => {
      try {
        const res = await api.fetchApi(JUMP_ROUTE, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...body, params: segParams() }),      // v0.1.8: moves only this song's counter
        });
        const out = await res.json();
        if (out && out.busy) return flash(button, "A Run is active", label);
        if (out && !out.ok) return flash(button, out.error || "Not possible", label);
        seg.jumpInput.value = "";
        if (okText) flash(button, okText, label);
        // v0.3.14: the segment is set, so the Prompt Generator(s) of the workflow copy its window now (the Sync button stays as a fail-safe)
        try { for (const g of collectNodes(app.rootGraph || app.graph, node.graph)) if (g && g.comfyClass === PROMPT_GEN_NODE) g._il78?.autoSync?.(); } catch (e) { /* a convenience */ }
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
    const onGoTime = (ev) => {      // v0.2.4
      ev?.preventDefault?.();
      ev?.stopPropagation?.();
      const secs = parseClock(seg.timeInput.value);
      if (secs === null) return flash(seg.goTime, "MM:SS", "Go time");
      if (!(segInfo && segInfo.ok && Number(segInfo.seg_seconds) > 0)) return flash(seg.goTime, "No video / song", "Go time");
      const total = segInfo.total || null;
      const hit = segmentForTime(secs, Number(segInfo.seg_seconds), total);
      if (!hit.ok) return flash(seg.goTime, hit.error, "Go time");
      seg.timeInput.value = "";
      doJump(seg.goTime, "Go time", { segment: hit.segment, total }, `\u2192 segment ${hit.segment} (${fmtClock(hit.start)})`);
    };
    seg.goTime.addEventListener("click", onGoTime);
    seg.timeInput.addEventListener("keydown", (ev) => {
      ev.stopPropagation();
      if (ev.key === "Enter") onGoTime(ev);
    });
    seg.timeInput.addEventListener("keyup", (ev) => ev.stopPropagation());
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
    //  - the last step preview when the node has finished (the node returns no saved video).
    // v0.0.6: the "Video failed to load" box at the bottom of the node. ComfyUI's frontend builds a preview from the
    // value of a file picker even when that value is "None" (it asks the server for a file called "None", which fails).
    // The preview of a REAL selected video is left alone; only the "None" placeholder is removed (see dropNonePreview at
    // the top of this file). Set ALWAYS_HIDE_VIDEO_PREVIEW to true to hide the video preview in every case.
    const hideVideoPreview = () => {
      try {
        const hid = dropNonePreview(app.nodeOutputs, node.id, ALWAYS_HIDE_VIDEO_PREVIEW);
        if (hid) {
          node.imgs = null;
          node.setDirtyCanvas?.(true, true);
        }
        if (ALWAYS_HIDE_VIDEO_PREVIEW) {
          const vc = node.videoContainer;
          if (vc && vc.style && vc.style.display !== "none") {
            vc.style.display = "none";
            node.setDirtyCanvas?.(true, true);
          }
        }
      } catch (e) {
        /* cosmetic only */
      }
    };

    // Run the clean-up right after the frontend's own callback of the Video File picker (it is the one that creates the
    // preview), so the error box does not even flash. The 400 ms refresh below is the safety net.
    {
      const w = getWidget("Video File");
      if (w && !w.__ironleo78Wrapped) {
        w.__ironleo78Wrapped = true;
        const origCb = w.callback;
        w.callback = function (...args) {
          const r = origCb ? origCb.apply(this, args) : undefined;
          hideVideoPreview();
          if (normFile(w.value) && normFile(w.value) !== "None") {      // v0.1.22: a video was picked -> Choose Audio latent = Audio From Video
            try { useVideoAudio(node); } catch (e) { /* a convenience */ }
          }
          if (!w.__il78Mirroring) {       // v0.1.12: a video picked here is put in the 9-Images loader too (load it once)
            try { mirrorVideo(node, w.value, collectNodes(app.rootGraph || app.graph, node.graph)); } catch (e) { /* a convenience */ }
          }
          return r;
        };
      }
    }

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
      if (typeof document !== "undefined" && document.hidden) return;      // v0.1.9: no polling while the browser tab is hidden
      dropPreview(false);
      hideVideoPreview();
      keepPanelFirst();
      fetchSegments(false);
    };

    // After every run: re-read the counter, drop any preview. (v0.0.9: the report is no longer drawn on the node, it
    // leaves on the `status` output; the node still sends its text so this event fires.)
    const onExecuted = (e) => {
      if (String(e?.detail?.node) !== String(node.id)) return;
      try {
        dropPreview(true);
        hideVideoPreview();
        node.setDirtyCanvas?.(true, true);
        setTimeout(keepPanelFirst, 100);
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
          // v0.4.12 (sweep B5): subgraphs included (an MTV inside a subgraph still counts); v0.4.14 (sweep N2): only subgraphs that
          // are really placed (liveNodes), not a leftover definition whose last instance was deleted
          const stillThere = liveNodes(app.rootGraph || app.graph).some((n) => n && n.comfyClass === NODE_ID);
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
        // v0.0.9H: an old workflow keeps its saved height, which still counted the pickers and the thumbnails: fit it once
        const h = shrinkOnce ? size[1] : Math.max(node.size[1], size[1]);
        shrinkOnce = false;
        node.setSize([Math.max(node.size[0], MIN_NODE_W), h]);
        node.setDirtyCanvas?.(true, true);
      } catch (e) {
        /* sizing is cosmetic */
      }
      refresh();
      fetchSegments(true);
    }, 100);
  },
});

// v2.8.5: the Model Loader owns noise_seed now: its "control after generate" defaults to "fixed" (new node only; a
// loaded workflow restores its own saved value right after this).
app.registerExtension({
  name: "IronLeo78.ModelLoader.SeedFixed",
  async nodeCreated(node) {
    if (node.comfyClass !== "IronLeo78_MTV_ModelLoader") return;
    let showMsg = null;      // set by the panel below (line under the button + toast); stays null when the panel could not be built
    // ---- v0.0.9: "Set New Defaults" panel, FIRST widget (serialize:false like the MTV's segment panel: no saved value moves) ----
    try {
      if (typeof node.addDOMWidget === "function" && typeof document !== "undefined") {
        const root = document.createElement("div");
        root.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:2px 4px;box-sizing:border-box;width:100%;";
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:4px;";
        const btn = document.createElement("button");
        btn.textContent = "Set New Defaults";
        btn.title = "Saves the values below (models, LoRAs, steps, seed + its control) as the SET. The MTV uses it from its next run, every Model Loader loads the same set again when it is created or a workflow is opened, and the 2in1 Revitalizers of the open workflow load it too (models, LoRAs, seed).";
        btn.style.cssText = "flex:1;padding:5px 8px;cursor:pointer;border-radius:4px;";
        const fac = document.createElement("button");
        fac.textContent = "Factory";
        fac.title = "Back to the built-in defaults (also saved as the defaults).";
        fac.style.cssText = "padding:5px 8px;cursor:pointer;border-radius:4px;font-size:11px;";
        row.append(btn, fac);
        const msg = document.createElement("div");
        msg.style.cssText = "font-size:11px;line-height:1.3;min-height:14px;white-space:normal;word-break:break-word;";
        root.append(row, msg);
        const DEFAULTS_H = 74;
        const dw = node.addDOMWidget("defaults_view", "ironleo78_defaults", root, {
          serialize: false, hideOnZoom: false, getMinHeight: () => DEFAULTS_H, getMaxHeight: () => DEFAULTS_H,
        });
        dw.serialize = false;
        dw.computeSize = (width) => [width, DEFAULTS_H];
        const toTop = () => {
          const ws = node.widgets;
          const i = ws ? ws.indexOf(dw) : -1;
          if (i > 0) { ws.splice(i, 1); ws.unshift(dw); node.setDirtyCanvas?.(true, true); }
        };
        toTop();
        setTimeout(toTop, 0);
        setTimeout(toTop, 400);
        const colors = { ok: "#5fbf6a", warn: "#e0a93b", error: "#e0605a" };
        const show = (m, quiet = false) => {
          msg.textContent = `${m.text}  (${new Date().toLocaleTimeString()})`;
          msg.style.color = colors[m.level] || "inherit";
          if (!quiet) {
            try {
              app.extensionManager?.toast?.add({ severity: m.level === "ok" ? "success" : m.level, summary: "Model Loader", detail: m.text, life: 5000 });
            } catch (e) { /* the line under the button is the confirmation */ }
          }
          node.setDirtyCanvas?.(true, true);
        };
        showMsg = show;
        const post = async (url, body) => {
          const res = await api.fetchApi(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
          return res.json();
        };
        const busy = (on) => { btn.disabled = on; fac.disabled = on; };
        btn.addEventListener("click", async () => {
          busy(true);
          try {
            const sent = collectLoaderValues(serializedWidgets(node));
            const ctlW = (node.widgets || []).find((w) => w.name === CONTROL_KEY);
            const sentControl = ctlW && typeof ctlW.value === "string" ? ctlW.value : undefined;      // the seed's control after generate is part of the set
            const ans = await post(SAVE_DEFAULTS_ROUTE, { values: sent, seed_control: sentControl });
            if (!ans?.ok) throw new Error(ans?.error || "the backend did not answer");
            const res = await api.fetchApi(LOADER_DEFAULTS_ROUTE);          // read back what the backend now holds
            const back = await res.json();
            const saved = savedMessage(verifySavedDefaults(sent, back?.defaults, sentControl, back?.seed_control), ans.missing);
            show(saved);
            // v0.0.9c: the saved set is also sent to every 2in1 Revitalizer of the open workflow (they load it themselves, see web/ironleo78_2in1_revitalizer.js)
            if (saved.level !== "error") {
              try { window.dispatchEvent(new CustomEvent("ironleo78-set-saved")); } catch (e) { /* the Revitalizer has its own button */ }
            }
          } catch (e) {
            show({ level: "error", text: `✖ NOT saved: ${e?.message || e}` });
          }
          busy(false);
        });
        fac.addEventListener("click", async () => {
          busy(true);
          try {
            const ans = await post(RESET_DEFAULTS_ROUTE);
            if (!ans?.ok) throw new Error(ans?.error || "the backend did not answer");
            const res = await api.fetchApi(LOADER_DEFAULTS_ROUTE);
            const info = await res.json();
            if (!info?.ok || !info.factory) throw new Error(info?.error || "the backend did not answer");
            const ctl = (node.widgets || []).find((w) => w.name === CONTROL_KEY);
            show(applyLoaderDefaults(serializedWidgets(node), ctl, info.factory).message);
          } catch (e) {
            show({ level: "error", text: `✖ Factory defaults NOT restored: ${e?.message || e}` });
          }
          busy(false);
        });
      }
    } catch (e) {
      console.warn("[IronLeo78] Set New Defaults button not added:", e);
    }
    // v0.0.9: the SAVED SET (Set New Defaults) is loaded into this node every time it is created or a workflow is opened, so the
    // loader and the MTV hold the same values after every reload. No saved set = the workflow keeps its own values.
    const applySavedSet = async () => {
      try {
        const res = await api.fetchApi(LOADER_DEFAULTS_ROUTE);
        const info = await res.json();
        if (!info?.ok || !info.custom || !info.defaults) return;
        const serial = serializedWidgets(node);
        if (!serial.length) return;
        const ctl = (node.widgets || []).find((w) => w.name === CONTROL_KEY);
        const before = collectLoaderValues(serial);
        const ctlFrom = ctl && typeof ctl.value === "string" ? ctl.value : undefined;
        const ctlTo = typeof info.seed_control === "string" ? info.seed_control : null;      // null: the saved set holds no seed control, leave it
        const result = applyLoaderDefaults(serial, ctl, info.defaults, ctlTo);
        const changed = changedBySet(before, result.plan.set, ctlFrom, ctlTo);
        const m = loadedSetMessage(result, changed);
        if (showMsg) showMsg(m, m.level === "ok");      // a toast only when something was replaced / not installed / failed
        else if (m.level !== "ok") console.warn("[IronLeo78] " + m.text);
        node.setDirtyCanvas?.(true, true);
      } catch (e) {
        console.warn("[IronLeo78] saved set not loaded:", e);
      }
    };
    let applyTimer = null;
    // after the 0 / 400 ms re-apply of the workflow's own values below, so the saved set is the last word
    const scheduleApply = () => {
      clearTimeout(applyTimer);
      applyTimer = setTimeout(applySavedSet, 600);
    };
    scheduleApply();      // a node just created from the menu (a workflow being opened calls onConfigure next, which schedules it again)
    const prevConfigure = node.onConfigure;
    // the values of a fresh node (before any workflow is loaded into it): the defaults for a widget the saved copy lacks
    const defaults = {};
    for (const w of serializedWidgets(node)) defaults[w.name] = w.value;
    const namedValues = () => {
      const out = {};
      for (const w of serializedWidgets(node)) out[w.name] = w.value;
      const ctl = (node.widgets || []).find((w) => w.name === CONTROL_KEY);
      if (ctl && typeof ctl.value === "string") out[CONTROL_KEY] = ctl.value;
      return out;
    };
    node.onConfigure = function (info) {
      try {
        let done = false;
        // 1) a workflow saved with this release or later: restore BY NAME (immune to widgets moving in later updates)
        const shadow = info?.properties?.[SHADOW_KEY] ?? this.properties?.[SHADOW_KEY];
        const names = serializedWidgets(this).map((w) => w.name);
        const restored = restoreFromShadow(names, shadow, defaults);
        if (restored && Array.isArray(info?.widgets_values)) {
          info.widgets_values.splice(0, info.widgets_values.length, ...restored);
          serializedWidgets(this).forEach((w, i) => { w.value = restored[i]; });
          const ctl = (this.widgets || []).find((w) => w.name === CONTROL_KEY);
          if (ctl) ctl.value = restored[restored.length - 1];
          done = true;
        }
        // 2) older workflows: re-order by what the values are
        if (!done) {
          applyMigration(this, info, migrateLoaderLayout);       // v0.0.9: first: it also drops the 0.5 upscale value
          applyMigration(this, info, migrateLoaderValues);
          applyMigration(this, info, repairLoaderValues);
        }
        // the final values by name, set once more right after the load: whatever order the frontend assigns the saved values
        // in, the corrected ones win (nobody edits a widget within the first moments of a load)
        // (taken from the final saved list, NOT from the widgets: they may not have received their values yet)
        const final = {};
        const fnames = serializedWidgets(this).map((w) => w.name);
        const fvals = Array.isArray(info?.widgets_values) ? info.widgets_values : [];
        fnames.forEach((n, i) => { if (i < fvals.length) final[n] = fvals[i]; });
        if (typeof fvals[fnames.length] === "string") final[CONTROL_KEY] = fvals[fnames.length];
        const again = () => {
          try {
            for (const w of (this.widgets || [])) {
              if (w.name in final && w.value !== final[w.name] && (w.name === CONTROL_KEY || w.serialize !== false)) w.value = final[w.name];
            }
            this.setDirtyCanvas?.(true, true);
          } catch (e) {
            /* cosmetic only */
          }
        };
        setTimeout(again, 0);
        setTimeout(again, 400);
      } catch (e) {
        console.warn("[IronLeo78] Model Loader migration skipped:", e);
      }
      scheduleApply();      // v0.0.9: then the saved set (if any) replaces whatever the workflow held
      return prevConfigure ? prevConfigure.apply(this, arguments) : undefined;
    };
    // every save carries the named copy
    const prevSerialize = node.onSerialize;
    node.onSerialize = function (o) {
      try {
        const copy = namedValues();
        copy[LAYOUT_KEY] = serializedWidgets(this).map((w) => w.name).join("|");
        this.properties = this.properties || {};
        this.properties[SHADOW_KEY] = copy;
        if (o) {
          o.properties = o.properties || {};
          o.properties[SHADOW_KEY] = copy;
        }
      } catch (e) {
        /* the copy is a safety net only */
      }
      return prevSerialize ? prevSerialize.apply(this, arguments) : undefined;
    };
    try {
      const ctl = (node.widgets || []).find((w) => w.name === "control_after_generate");
      if (ctl) ctl.value = "fixed";
    } catch (e) {
      /* cosmetic only */
    }
  },
});
