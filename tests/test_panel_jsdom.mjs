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
    return { json: async () => ({ ok: true }) };
  },
};\n`);
fs.copyFileSync(path.join(here, "..", "web", "ironleo78_mtv.js"), path.join(tmp, "ext", "web", "ext.mjs"));

const dom = new JSDOM("<!doctype html><body></body>");
globalThis.window = dom.window; globalThis.document = dom.window.document;
const { app } = await import(pathToFileURL(path.join(tmp, "scripts", "app.js")).href);
const { api } = await import(pathToFileURL(path.join(tmp, "scripts", "api.js")).href);
await import(pathToFileURL(path.join(tmp, "ext", "web", "ext.mjs")).href);
const ext = app.exts[0];
let fails = 0; const check = (c, m) => { if (!c) { fails++; console.log("  FAIL -", m); } else console.log("  ok -", m); };

const W = (name, value) => ({ name, value });
const widgets = [W("Use Video", true), W("Video File", "v.mp4"), W("Custom Audio File", "Song.wav"), W("Bypassed Audio Latent", false), W("duration", 5), W("Next Segment On Run", true)];
for (let i = 1; i <= 3; i++) widgets.push(W(`picture_${i}`, "None"));
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
// v2.8: Scene 2 is gone: one row of three labelled thumbnails, nothing hidden or renamed
const thumbs = dom_widgets["thumbnails"].element;
const labels = [...thumbs.querySelectorAll("div")].map((d) => d.textContent).filter((t) => /^Picture\d$/.test(t));
check(labels.join(",") === "Picture1,Picture2,Picture3", "thumbnail labels: Picture1, Picture2, Picture3 (no S1 / S2 prefix): " + labels.join(","));
check(dom_widgets["thumbnails"].computeSize(300)[1] === 90, "thumbnail grid is one row high (90 px)");
check(widgets.every((w) => w.type !== "converted-widget" && !w.hidden), "no widget is hidden by the extension any more");
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

// Latest
api.calls.length = 0;
LATEST.click(); await new Promise((r) => setTimeout(r, 50));
const lc = api.calls.find((c) => c.url.includes("/jump"));
check(lc && JSON.parse(lc.opts.body).latest === true, "Latest posts {latest: true}");

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

fs.rmSync(tmp, { recursive: true, force: true });
console.log(fails ? `\n${fails} FAILED` : "\nALL JS CHECKS PASSED");
process.exit(fails ? 1 : 0);
