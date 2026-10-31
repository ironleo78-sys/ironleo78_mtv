// Test of the segment panel in web/ironleo78_mtv.js (jump row, Go / Latest)
// in a real DOM (jsdom) with ComfyUI's app / api stubbed.   Optional: needs node and `npm install jsdom`
// (run it from this folder or the package root):   node tests/test_panel_jsdom.mjs
// ComfyUI only loads web/, so this folder is ignored at runtime.
import { JSDOM } from "jsdom";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ironleo78_panel_"));
fs.mkdirSync(path.join(tmp, "scripts")); fs.mkdirSync(path.join(tmp, "ext", "web"), { recursive: true });
fs.writeFileSync(path.join(tmp, "scripts", "app.js"),
  "export const app = { exts: [], registerExtension(e) { this.exts.push(e); }, graph: { _nodes: [] }, nodePreviewImages: {} };\n");
fs.writeFileSync(path.join(tmp, "scripts", "api.js"), `export const api = {
  calls: [], info: null, jumpAnswer: null, apiURL: (p) => p, addEventListener() {}, removeEventListener() {},
  async fetchApi(url, opts) {
    this.calls.push({ url, opts });
    if (url.includes("/segments")) return { json: async () => this.info };
    if (url.includes("/jump")) return { json: async () => this.jumpAnswer || { ok: true } };
    if (url.includes("/save_defaults")) { const b = JSON.parse(opts.body); if (this.refuseSave) return { json: async () => ({ ok: false, error: "refused" }) }; this.saved = b.values; this.savedControl = typeof b.seed_control === "string" ? b.seed_control : null; return { json: async () => ({ ok: true, missing: [] }) }; }
    if (url.includes("/reset_defaults")) { this.saved = null; this.savedControl = null; return { json: async () => ({ ok: true }) }; }
    if (url.includes("/loader_defaults")) return { json: async () => ({ ok: true, defaults: this.saved || this.factory, factory: this.factory, seed_control: this.savedControl ?? null }) };
    return { json: async () => ({ ok: true }) };
  },
};\n`);
fs.copyFileSync(path.join(here, "..", "web", "ironleo78_mtv.js"), path.join(tmp, "ext", "web", "ext.mjs"));
fs.copyFileSync(path.join(here, "..", "web", "il78_sync_logic.js"), path.join(tmp, "ext", "web", "il78_sync_logic.js"));

// pretendToBeVisual: like a browser tab you are looking at (jsdom otherwise reports the page as hidden, and since v0.1.9 the
// panel does not poll while the tab is hidden)
const dom = new JSDOM("<!doctype html><body></body>", { pretendToBeVisual: true });
globalThis.window = dom.window; globalThis.document = dom.window.document;
const { app } = await import(pathToFileURL(path.join(tmp, "scripts", "app.js")).href);
const { api } = await import(pathToFileURL(path.join(tmp, "scripts", "api.js")).href);
await import(pathToFileURL(path.join(tmp, "ext", "web", "ext.mjs")).href);
const ext = app.exts[0];
let fails = 0; const check = (c, m) => { if (!c) { fails++; console.log("  FAIL -", m); } else console.log("  ok -", m); };

const W = (name, value) => ({ name, value });
const widgets = [W("Use Video", true), W("Video File", "v.mp4"), W("Custom Audio File", "Song.wav"), W("Choose Audio latent", false), W("duration", 5), W("Next Segment On Run", true)];
// v0.0.9H: no picture_n pickers and no More References switch any more (the pictures are Picture_1..9 inputs)
const dom_widgets = {};
const node = { comfyClass: "IronLeo78_MTV", id: 7, widgets, size: [400, 600], properties: {},
  addDOMWidget(name, type, el, opts) { const w = { name, type, element: el, serialize: opts.serialize }; dom_widgets[name] = w; widgets.push(w); return w; },
  computeSize: () => [400, 600], setSize() {}, setDirtyCanvas() {} };

api.info = { ok: true, total: 37, index: 4, furthest: 9, stepping: true, finished: false, running: false,
  sources: [{ name: "custom audio", seconds: 190, segments: 37 }], limit: "custom audio", seg_seconds: 5.17, frames: 124 };
await ext.nodeCreated(node);
await new Promise((r) => setTimeout(r, 450));
const root = dom_widgets["segments_view"].element;
const $ = (sel) => root.querySelector(sel);
const buttons = [...root.querySelectorAll("button")];
const byText = (t) => buttons.find((b) => b.textContent === t);
const input = $("input");
const GO = buttons.find((b) => b.textContent === "Go"), LATEST = buttons.find((b) => b.textContent === "Latest");

check(dom_widgets["segments_view"].serialize === false, "panel widget is not serialized");
// v0.0.9H: the thumbnail gallery is gone: only the segment panel is added, nothing else
check(!("thumbnails" in dom_widgets) && Object.keys(dom_widgets).join(",") === "segments_view", "v0.0.9H: no thumbnails DOM widget, the segment panel is the only one: " + Object.keys(dom_widgets).join(","));
check(!widgets.some((w) => /^picture_\d$/.test(w.name) || w.name === "More References"), "no picture picker / More References widget on the node");
check(!widgets.find((w) => w.name === "Video File").hidden, "Video File stays visible");
check(widgets.every((w) => w.type !== "converted-widget"), "no widget type is swapped");
check(root.textContent.includes("37 segments") && root.textContent.includes("Next: segment 5 of 37"), "panel shows the count and the next segment");
check(!!input && !!GO, "jump row exists: number field + Go");
check(LATEST.style.display !== "none", "Latest is visible while the counter (5) is before the furthest point (10)");

// Go with a valid number
api.calls.length = 0;
input.value = "12"; GO.click();
await new Promise((r) => setTimeout(r, 50));
const jumpCall = api.calls.find((c) => c.url.includes("/jump"));
check(jumpCall && jumpCall.opts.method === "POST" && JSON.parse(jumpCall.opts.body).segment === 12 && JSON.parse(jumpCall.opts.body).total === 37,
  "Go posts {segment: 12, total: 37} to /jump: " + (jumpCall && jumpCall.opts.body));
check(input.value === "", "the field is cleared after a successful jump");
check(api.calls.some((c) => c.url.includes("/segments")), "the panel re-reads the counter after the jump");

// out of range / empty: no request
api.calls.length = 0;
input.value = "99"; GO.click(); await new Promise((r) => setTimeout(r, 20));
check(!api.calls.some((c) => c.url.includes("/jump")) && GO.textContent === "1 to 37", "99 (> 37): no request, the button says the range");
input.value = ""; GO.click(); await new Promise((r) => setTimeout(r, 20));
check(!api.calls.some((c) => c.url.includes("/jump")), "empty field: no request");

// Enter key = Go, and keydown does not bubble to ComfyUI
api.calls.length = 0;
input.value = "3";
let bubbled = false; dom.window.document.body.addEventListener("keydown", () => { bubbled = true; });
root.ownerDocument.body.appendChild(root);
input.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
await new Promise((r) => setTimeout(r, 50));
check(api.calls.some((c) => c.url.includes("/jump") && JSON.parse(c.opts.body).segment === 3), "Enter in the field = Go");
check(!bubbled, "keydown is stopped (ComfyUI shortcuts are not triggered while typing)");

// v0.3.14: a successful Go / Latest makes the Prompt Generator(s) of the workflow sync themselves; a refused jump does not
let autoSyncs = 0;
app.graph._nodes.push({ comfyClass: "IronLeo78_MTV_PromptGenerator", id: 50, widgets: [], _il78: { autoSync: () => { autoSyncs++; } } });
api.calls.length = 0; autoSyncs = 0;
input.value = "6"; GO.click(); await new Promise((r) => setTimeout(r, 60));
check(autoSyncs === 1, "v0.3.14: Go (accepted) triggers the Prompt Generator's automatic sync once: " + autoSyncs);
input.value = "99"; GO.click(); await new Promise((r) => setTimeout(r, 30));
check(autoSyncs === 1, "...a refused Go (out of range) does not");

// Latest
api.calls.length = 0; autoSyncs = 0;
LATEST.click(); await new Promise((r) => setTimeout(r, 50));
check(autoSyncs === 1, "v0.3.14: Latest triggers it too");
const lc = api.calls.find((c) => c.url.includes("/jump"));
check(lc && JSON.parse(lc.opts.body).latest === true, "Latest posts {latest: true}");

// v0.3.11: a quiet hint on the node when Custom Audio is selected but no file is (the song would be skipped)
{
  const wv = (n) => widgets.find((w) => w.name === n);
  const keep = [wv("Choose Audio latent").value, wv("Custom Audio File").value];
  wv("Choose Audio latent").value = "Custom Audio"; wv("Custom Audio File").value = "None";
  input.value = "4"; GO.click(); await new Promise((r) => setTimeout(r, 80));
  check(root.textContent.includes("audio: no Custom Audio File, no song is used"), "v0.3.11: Custom Audio with no file: the panel says no song is used");
  wv("Custom Audio File").value = "Song.wav";
  input.value = "4"; GO.click(); await new Promise((r) => setTimeout(r, 80));
  check(!root.textContent.includes("no song is used"), "...and the hint is gone once a file is picked");
  wv("Choose Audio latent").value = "Audio From Video"; wv("Custom Audio File").value = "None";
  input.value = "4"; GO.click(); await new Promise((r) => setTimeout(r, 80));
  check(!root.textContent.includes("no song is used"), "...and it never shows for another audio mode");
  wv("Choose Audio latent").value = keep[0]; wv("Custom Audio File").value = keep[1];
}

// busy + error answers show on the button
api.jumpAnswer = { ok: false, busy: true };
input.value = "5"; GO.click(); await new Promise((r) => setTimeout(r, 50));
check(GO.textContent === "A Run is active", "a Run in progress: the button says so");
api.jumpAnswer = { ok: false, error: "there are only 37 segments" };
await new Promise((r) => setTimeout(r, 2300));
input.value = "5"; GO.click(); await new Promise((r) => setTimeout(r, 50));
check(GO.textContent.includes("only 37"), "a backend error is shown on the button");
api.jumpAnswer = null;

// Latest hidden when the counter is at the furthest point
api.info = { ...api.info, index: 9, furthest: 9 };
await new Promise((r) => setTimeout(r, 3400));
check(LATEST.style.display === "none", "Latest hides when the counter is at the furthest point");

// v0.0.9s: Video_1 is gone, so is the Free video button
check(!buttons.some((b) => /Free video/.test(b.textContent)), "no Free video button in the segment panel")

// v0.0.9: the Model Loader node loads an OLD saved workflow (the real onConfigure hook, the real widget objects)
const loaderExt = app.exts.find((e) => e.name === "IronLeo78.ModelLoader.SeedFixed");
check(!!loaderExt, "the Model Loader extension is registered");
const LNAMES = ["unet_name", "turbo_lora_name", "LoRa_1_enabled", "LoRa_1", "LoRa_1_strength", "LoRa_2_enabled", "LoRa_2", "LoRa_2_strength",
  "LoRa_3_enabled", "LoRa_3", "LoRa_3_strength", "qwen_vl_name", "video_vae_name", "audio_vae_name", "turbo_steps", "full_steps", "noise_seed"];
const lw = LNAMES.map((n) => W(n, null));
lw.push({ name: "control_after_generate", value: "randomize", serialize: false });
const loaderDom = {};
const loaderNode = { comfyClass: "IronLeo78_MTV_ModelLoader", id: 9, widgets: lw, size: [400, 600], properties: {}, setDirtyCanvas() {},
  addDOMWidget(name, type, el, opts) { const w = { name, type, element: el, serialize: opts.serialize }; loaderDom[name] = w; lw.push(w); return w; } };
await loaderExt.nodeCreated(loaderNode);
const oldInfo = { widgets_values: ["u.safetensors", true, "H3.safetensors", 0.5, "t.safetensors", "q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"] };
loaderNode.onConfigure(oldInfo);
const got = Object.fromEntries(lw.filter((w) => w.serialize !== false).map((w) => [w.name, w.value]));
check(got.unet_name === "u.safetensors" && got.turbo_lora_name === "t.safetensors" && got.LoRa_1_enabled === true && got.LoRa_1 === "H3.safetensors" && got.LoRa_1_strength === 0.5,
  "an old saved Model Loader: the custom LoRA values land on LoRa_1, the Turbo LoRA keeps its file");
check(got.qwen_vl_name === "q.safetensors" && got.video_vae_name === "v.safetensors" && got.audio_vae_name === "a.safetensors" && got.turbo_steps === 8 && got.full_steps === 30 && got.noise_seed === 2026,
  "models, steps and seed did not shift");
check(got.LoRa_2_enabled === false && got.LoRa_2 === "None" && got.LoRa_3_enabled === false && got.LoRa_3 === "None", "LoRa_2 / LoRa_3 start OFF with no file");
check(oldInfo.widgets_values.length === 18 && oldInfo.widgets_values[17] === "fixed", "the saved list is rewritten in the new order (the control value stays at the end)");
// loading the NEW layout again must not change anything
const before = JSON.stringify(lw.map((w) => w.value));
loaderNode.onConfigure({ widgets_values: oldInfo.widgets_values.slice() });
check(JSON.stringify(lw.map((w) => w.value)) === before, "loading the new layout again changes nothing");

// v0.0.9: the "Set New Defaults" panel: first widget, not serialized, the button sets + verifies + prints the confirmation
await new Promise((r) => setTimeout(r, 450));
check(!!loaderDom.defaults_view && loaderDom.defaults_view.serialize === false && lw[0] === loaderDom.defaults_view, "the Set New Defaults panel is the first widget and is not serialized");
const dBtn = loaderDom.defaults_view.element.querySelector("button");
check(!!dBtn && dBtn.textContent === "Set New Defaults", "the panel holds a button called Set New Defaults");
lw.find((w) => w.name === "unet_name").options = { values: ["unet.safetensors", "mine.safetensors"] };
api.factory = { unet_name: "unet.safetensors", turbo_steps: 4, full_steps: 40, noise_seed: 1978, LoRa_1_enabled: false, LoRa_1_strength: 0.65 };
const setW = (n, v) => { lw.find((w) => w.name === n).value = v; };
const getW = (n) => lw.find((w) => w.name === n).value;
setW("turbo_steps", 3);
setW("unet_name", "mine.safetensors");
dBtn.click();
await new Promise((r) => setTimeout(r, 100));
const dMsg = loaderDom.defaults_view.element.children[1].textContent;
check(getW("turbo_steps") === 3 && getW("unet_name") === "mine.safetensors", "Set New Defaults does NOT reset the widgets: steps 3 stays 3");
check(api.saved && api.saved.turbo_steps === 3 && api.saved.unet_name === "mine.safetensors", "the loader's current values were sent to the backend to be saved");
check(dMsg.startsWith("✔ New defaults saved") && dMsg.includes("read back"), "the confirmation line says the new defaults were saved and read back: " + dMsg);
api.refuseSave = true;
dBtn.click();
await new Promise((r) => setTimeout(r, 100));
check(loaderDom.defaults_view.element.children[1].textContent.startsWith("✖ NOT saved: refused"), "a refused save says so");
api.refuseSave = false;
const facBtn = loaderDom.defaults_view.element.querySelectorAll("button")[1];
check(!!facBtn && facBtn.textContent === "Factory", "a small Factory button sits next to it");
facBtn.click();
await new Promise((r) => setTimeout(r, 100));
check(getW("turbo_steps") === 4 && api.saved === null && loaderDom.defaults_view.element.children[1].textContent.startsWith("✔ Factory defaults restored"), "Factory: widgets back to the built-in values and the saved defaults cleared");

fs.rmSync(tmp, { recursive: true, force: true });
console.log(fails ? `\n${fails} FAILED` : "\nALL JS CHECKS PASSED");
process.exit(fails ? 1 : 0);
