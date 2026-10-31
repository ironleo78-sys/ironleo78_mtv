// Test of the Prompt Generator's browser code (web/ironleo78_9images.js): the Preset / Mode callbacks (example prompt, the MTV's Choose Audio latent
// and Audio Stem), the seed control default, the info line and the i2v Sync button, in a real DOM (jsdom) with ComfyUI's app / api stubbed.
// Optional: needs node and `npm install jsdom`.   node tests/test_generator_jsdom.mjs
import { JSDOM } from "jsdom";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ironleo78_gen_"));
fs.mkdirSync(path.join(tmp, "scripts")); fs.mkdirSync(path.join(tmp, "ext", "web"), { recursive: true });
fs.writeFileSync(path.join(tmp, "scripts", "app.js"),
  "export const app = { exts: [], registerExtension(e) { this.exts.push(e); }, graph: { _nodes: [] }, canvas: { setDirty() {} }, extensionManager: { toast: { add(o) { (globalThis.__toasts ||= []).push(o); } } } };\n");
fs.writeFileSync(path.join(tmp, "scripts", "api.js"), `export const api = {
  calls: [], apiURL: (p) => p, addEventListener() {}, removeEventListener() {},
  async fetchApi(url, opts) {
    this.calls.push({ url, opts });
    if (url.includes("/ironleo78/mtv/presets")) return { json: async () => globalThis.__presets };
    if (url.includes("/ironleo78/mtv/segments")) return { json: async () => globalThis.__segInfo };
    return { json: async () => ({}) };
  },
};\n`);
for (const f of ["ironleo78_9images.js", "il78_sync_logic.js", "il78_shadow.js"]) fs.copyFileSync(path.join(here, "..", "web", f), path.join(tmp, "ext", "web", f === "ironleo78_9images.js" ? "ext.mjs" : f));

const dom = new JSDOM("<!doctype html><body></body>", { pretendToBeVisual: true });
globalThis.window = dom.window; globalThis.document = dom.window.document;
globalThis.__presets = {
  ok: true,
  presets: { None: "", "1 - Replace main actor": "Replace the main character of Video 1.", "8 - Drummer performance": "Replace the drummer of Video 1 with Picture 1. The drummer performs to the audio." },
  i2v: { None: "", "1 - Replace main actor": "Replace the main character of Picture 1 with the character of Picture 2.", "8 - Drummer performance": "Put the character of Picture 2 in the scene of Picture 1 as the drummer." },
  audio: { None: "", "1 - Replace main actor": "", "8 - Drummer performance": "Custom Audio" },
  stems: { None: "", "1 - Replace main actor": "", "8 - Drummer performance": "Drums" },
};
const { app } = await import(pathToFileURL(path.join(tmp, "scripts", "app.js")).href);
await import(pathToFileURL(path.join(tmp, "ext", "web", "ext.mjs")).href);
const ext = app.exts[0];
let fails = 0; const check = (c, m) => { if (!c) { fails++; console.log("  FAIL -", m); } else console.log("  ok -", m); };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const W = (name, value, options = {}) => ({ name, value, options, callback: null });
const NAMES = [...Array.from({ length: 9 }, (_, i) => `image_${i + 1}`), "video", "Start_From", "Duration", "Frame_Interval", "Video_Size", "Preset", "prompt", "LLM", "Use LLM", "Mode", "Seed", "control_after_generate"];
const VALUES = { video: "", Start_From: 0, Duration: 5, Frame_Interval: "12", Video_Size: "672x384", Preset: "None", prompt: "", LLM: "x.safetensors", "Use LLM": true, Mode: "v2v", Seed: 0, control_after_generate: "randomize" };
const mtvNode = (over = {}) => ({
  comfyClass: "IronLeo78_MTV", id: 9, mode: 0,
  widgets: [W("Choose Audio latent", over.audio ?? "Audio From Video", { values: ["MiniMax Audio", "Audio From Video", "Custom Audio"] }), W("Custom Audio File", over.file ?? "None"),
            W("Audio Stem", over.stem ?? "Full", { values: ["Full", "Vocals", "Guitars", "Drums", "Bass"] }), W("Video File", "None", { values: ["None"] }), W("duration", over.duration ?? 5), W("Use Video", true)],
});
async function makeGenerator(mtv) {
  const nodeType = { prototype: {} };
  await ext.beforeRegisterNodeDef(nodeType, { name: "IronLeo78_MTV_PromptGenerator" });
  const dom_widgets = {};
  const widgets = NAMES.map((n) => W(n, n.startsWith("image_") ? "" : VALUES[n]));
  const node = Object.create(nodeType.prototype);
  Object.assign(node, { comfyClass: "IronLeo78_MTV_PromptGenerator", id: 3, widgets, size: [400, 700], properties: {},
    addDOMWidget(name, type, el, opts) { const w = { name, type, element: el, serialize: opts.serialize }; dom_widgets[name] = w; widgets.push(w); return w; },
    setSize() {}, setDirtyCanvas() {}, graph: { change() {}, _nodes: [] } });
  app.graph = { _nodes: [node, mtv] }; app.rootGraph = app.graph; node.graph = app.graph;
  node.onNodeCreated();
  return { node, widgets, dom_widgets, W: (n) => widgets.find((w) => w.name === n) };
}
const choose = async (g, name, value) => { g.W(name).value = value; g.W(name).callback?.(value); await wait(40); };

console.log("1. the seed control starts at fixed (and a loaded workflow keeps its own)");
{
  const g = await makeGenerator(mtvNode());
  await wait(450);
  check(g.W("control_after_generate").value === "fixed", "a new node: control after generate = fixed (it was randomize)");
  g.node.onRemoved?.();
  const g2 = await makeGenerator(mtvNode());
  g2.node.onConfigure({ widgets_values: [], properties: {} });                      // a saved workflow is loaded right after creation
  g2.W("control_after_generate").value = "randomize";                              // ... and holds randomize
  await wait(450);
  check(g2.W("control_after_generate").value === "randomize", "a loaded workflow keeps its own control value");
  g2.node.onRemoved?.();
}

console.log("2. choosing a preset: the example, the MTV audio and stem, the warning");
{
  const mtv = mtvNode();
  const g = await makeGenerator(mtv);
  const box = g.W("prompt"), mv = (n) => mtv.widgets.find((w) => w.name === n).value;
  box.value = "my own idea";
  await choose(g, "Preset", "1 - Replace main actor");
  check(box.value === "Replace the main character of Video 1.", "choosing a preset fills its example even over typed text");
  await choose(g, "Preset", "8 - Drummer performance");
  check(box.value.startsWith("Replace the drummer of Video 1"), "the drummer example replaces the previous one");
  check(mv("Choose Audio latent") === "Custom Audio" && mv("Audio Stem") === "Drums", "the MTV is set to Custom Audio with the Drums stem");
  const msg = g.dom_widgets["video_slot"].element.querySelector(".il78-sync-msg");
  check(msg && msg.textContent.includes("Custom Audio File") && msg.classList.contains("warn"), "no Custom Audio File: a warning line on the node");
  check((globalThis.__toasts || []).some((t) => t.summary === "Custom Audio File missing"), "... and a pop-up");
  const saved = g.node.properties.il78_audio;
  check(saved && saved.audio === "Custom Audio" && saved.stem === "Drums" && saved.before && saved.before["9"] && saved.before["9"].audio === "Audio From Video", "what was applied (and what the MTV had before) is saved with the workflow: " + JSON.stringify(saved));
  await choose(g, "Preset", "1 - Replace main actor");
  check(mv("Choose Audio latent") === "Audio From Video" && mv("Audio Stem") === "Full", "leaving the musician preset gives the MTV settings back");
  await choose(g, "Preset", "None");
  check(box.value === "Replace the main character of Video 1." || box.value === "", "None: typed text is never wiped (an untouched example may be cleared)");
  g.node.onRemoved?.();
}

console.log("3. the Mode: example, MTV audio, info line, the Sync button");
{
  const mtv = mtvNode({ duration: 5 });
  const g = await makeGenerator(mtv);
  const box = g.W("prompt"), mv = (n) => mtv.widgets.find((w) => w.name === n).value;
  await choose(g, "Preset", "1 - Replace main actor");
  await choose(g, "Mode", "i2v");
  check(box.value.startsWith("Replace the main character of Picture 1"), "Mode i2v: the i2v example of the chosen preset");
  check(mv("Choose Audio latent") === "MiniMax Audio", "Mode i2v: the MTV goes to MiniMax Audio");
  await wait(600);
  const root = g.dom_widgets["video_slot"].element;
  const info = root.querySelector(".il78-info"), btn = root.querySelector(".il78-sync");
  check(info.textContent.startsWith("image-to-video: the LLM writes a timeline for 5s"), "i2v info line: " + info.textContent);
  check(btn.textContent === "⟳ Sync duration from MTV" && !btn.classList.contains("il78-off"), "i2v: the Sync button copies the duration (and is usable without a video)");
  btn.click(); await wait(60);
  check(Math.abs(g.W("Duration").value - 124 / 24) < 1e-9, "Sync in i2v: Duration = the padded length the MTV renders (5 s -> 124 frames): " + g.W("Duration").value);
  await choose(g, "Mode", "v2v");
  await wait(600);
  check(box.value.startsWith("Replace the main character of Video 1") && mv("Choose Audio latent") === "Audio From Video", "Mode v2v: the v2v example and Audio From Video");
  check(btn.textContent === "⟳ Sync from MTV (next segment)" && info.textContent.includes("frames"), "v2v: the normal Sync label and the frames info line");
  // a song setup is kept when the Mode changes
  mtv.widgets.find((w) => w.name === "Choose Audio latent").value = "Custom Audio"; mtv.widgets.find((w) => w.name === "Custom Audio File").value = "song.wav";
  await choose(g, "Mode", "i2v");
  check(mv("Choose Audio latent") === "Custom Audio", "a song setup (Custom Audio + a file) is not switched by a Mode change");
  g.node.onRemoved?.();
}

console.log("4. v0.3.14: the automatic sync (what the MTV's Go / Go time / Latest trigger)");
{
  globalThis.__segInfo = { ok: true, total: 10, frames: 124, index: 4, stepping: true, finished: false, running: false };
  const mtv = mtvNode();
  mtv.widgets.find((w) => w.name === "Video File").value = "clip.mp4";           // the same video in both nodes: the sync gate opens
  const g = await makeGenerator(mtv);
  g.W("video").value = "clip.mp4";
  const msg = g.dom_widgets["video_slot"].element.querySelector(".il78-sync-msg");
  check(typeof g.node._il78.autoSync === "function", "the node exposes autoSync");
  await g.node._il78.autoSync();
  check(Math.abs(g.W("Start_From").value - 4 * 124 / 24) < 1e-9 && Math.abs(g.W("Duration").value - 124 / 24) < 1e-9, "segment 5 of the MTV: Start_From and Duration copied with no click: " + g.W("Start_From").value + " / " + g.W("Duration").value);
  check(msg.textContent.startsWith("Auto-synced: segment 5 of 10"), "the node says it synced by itself: " + msg.textContent);
  // another video in the MTV: the automatic sync stays silent and changes nothing
  g.W("Start_From").value = 1.5; msg.textContent = "";
  mtv.widgets.find((w) => w.name === "Video File").value = "other.mp4";
  await g.node._il78.autoSync();
  check(g.W("Start_From").value === 1.5 && msg.textContent === "", "a different video: nothing changes and no message (the button would explain)");
  // the button still works as a fail-safe (it explains)
  g.dom_widgets["video_slot"].element.querySelector(".il78-sync").click(); await wait(60);
  check(msg.textContent.includes("another Video File") && msg.classList.contains("warn"), "the Sync button is still there and still explains why it cannot sync");
  // i2v: the duration of the MTV
  await choose(g, "Mode", "i2v");
  mtv.widgets.find((w) => w.name === "duration").value = 7.5;
  await g.node._il78.autoSync();
  check(g.W("Duration").value === 8, "i2v: the automatic sync copies the padded MTV duration (7.5 s -> 8 s)");
  g.node.onRemoved?.();
}

console.log("5. v0.4.1: the preview shows the frame where the window starts");
{
  globalThis.__segInfo = { ok: true, total: 10, frames: 124, index: 4, stepping: true, finished: false, running: false };
  const mtv = mtvNode();
  mtv.widgets.find((w) => w.name === "Video File").value = "clip.mp4";
  const g = await makeGenerator(mtv);
  g.node._il78.setVideo("clip.mp4");                                              // the preview <video> is built
  const ve = g.dom_widgets["video_slot"].element.querySelector("video");
  let cur = 0.1;
  Object.defineProperty(ve, "readyState", { value: 4, configurable: true });
  Object.defineProperty(ve, "duration", { value: 60, configurable: true });
  Object.defineProperty(ve, "currentTime", { get: () => cur, set: (v) => { cur = v; }, configurable: true });
  await choose(g, "Start_From", 12.5);
  check(Math.abs(cur - 12.5) < 1e-9, "typing a Start_From moves the preview to it: " + cur);
  await g.node._il78.autoSync();
  check(Math.abs(cur - 4 * 124 / 24) < 1e-9, "Auto-sync moves the preview to the synced start: " + cur);
  await choose(g, "Start_From", 0);
  check(Math.abs(cur - 0.1) < 1e-9, "Start_From 0 shows the first frame (0.1 s, as before): " + cur);
  await choose(g, "Start_From", 500);
  check(cur < 60, "a start past the end of the file stays inside it: " + cur);
  g.node.onRemoved?.();
}
console.log(fails ? `\n${fails} FAILED` : "\nALL GENERATOR JS CHECKS PASSED");
process.exit(fails ? 1 : 0);
