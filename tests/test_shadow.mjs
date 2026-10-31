// Tests for the named copy of the widget values (v0.0.2d): web/il78_shadow.js (pure) and the real hooks of
// web/ironleo78_9images.js (onSerialize / onConfigure), loaded with stub app / api modules and a tiny fake DOM.
//   node tests/test_shadow.mjs
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "il78_shadow_"));
fs.mkdirSync(path.join(tmp, "scripts"));
fs.mkdirSync(path.join(tmp, "ext", "web"), { recursive: true });
fs.writeFileSync(path.join(tmp, "scripts", "app.js"), "export const app = { registerExtension(e) { (globalThis.__exts ||= []).push(e); }, graph: { _nodes: [] } };\n");
fs.writeFileSync(path.join(tmp, "scripts", "api.js"), "export const api = { apiURL: (p) => p, async fetchApi() { return { status: 200, json: async () => ({}) }; } };\n");
for (const f of ["ironleo78_9images.js", "il78_sync_logic.js", "il78_shadow.js"]) {
  fs.copyFileSync(path.join(here, "..", "web", f), path.join(tmp, "ext", "web", f));
}

// ---- a tiny fake DOM: enough for setup() to build its grid without a browser
const fakeEl = () => ({
  style: {}, dataset: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
  append() {}, appendChild() {}, remove() {}, addEventListener() {}, removeEventListener() {}, focus() {}, click() {},
  contains: () => false, innerHTML: "", textContent: "", title: "",
});
globalThis.document = { createElement: fakeEl, getElementById: () => null, head: fakeEl(), body: fakeEl(),
  addEventListener() {}, removeEventListener() {} };
globalThis.window = { innerWidth: 1600, innerHeight: 900 };

const shadow = await import(pathToFileURL(path.join(tmp, "ext", "web", "il78_shadow.js")).href);
await import(pathToFileURL(path.join(tmp, "ext", "web", "ironleo78_9images.js")).href);

let fails = 0;
let passed = 0;
const check = (c, m) => { if (!c) { fails++; console.log("FAIL - " + m); } else { passed++; console.log("ok - " + m); } };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const NAMES = [...Array.from({ length: 9 }, (_, k) => `image_${k + 1}`), "video", "Start_From", "Duration", "Frame_Interval", "Video_Size"];
const FRESH = { ...Object.fromEntries(NAMES.slice(0, 10).map((n) => [n, ""])), Start_From: 0, Duration: 5, Frame_Interval: "2", Video_Size: "672x384" };
const SAVED = ["a.png", "", "c.png", "", "", "", "", "", "i.png", "clip.mp4", 12.5, 5.1667, "4", "896x512"];

// ---------------- pure functions
const copy = shadow.buildShadow(NAMES.map((n, i) => ({ name: n, value: SAVED[i] })));
check(copy.image_1 === "a.png" && copy.Duration === 5.1667 && copy[shadow.LAYOUT_KEY] === NAMES.join("|"), "buildShadow: every value by name + the layout");
check(shadow.restoreFromShadow(NAMES, copy, FRESH) === null, "same layout: nothing restored (the positional values are right)");
check(shadow.restoreFromShadow(NAMES, null, FRESH) === null && shadow.restoreFromShadow(NAMES, [], FRESH) === null, "no copy (an older workflow): nothing restored");
check(shadow.restoreFromShadow(NAMES, { unrelated: 1 }, FRESH) === null, "a copy that names none of the widgets: nothing restored");
const moved = ["Video_Size", ...NAMES.filter((n) => n !== "Video_Size")];
check(same(shadow.restoreFromShadow(moved, copy, FRESH), ["896x512", ...SAVED.slice(0, 13)]), "a widget moved: the values follow their names");
const added = [...NAMES, "New_Widget"];
check(same(shadow.restoreFromShadow(added, copy, { ...FRESH, New_Widget: "x" }), [...SAVED, "x"]), "a widget added later: it gets its fresh default, the rest by name");
check(shadow.restoreFromShadow(added, copy, FRESH) === null, "a widget added later with no default known: nothing restored (no guessing)");
const damaged = { ...copy, Duration: "abc", image_3: 7, [shadow.LAYOUT_KEY]: "old" };
const fixedVals = shadow.restoreFromShadow(NAMES, damaged, FRESH);
check(fixedVals[11] === 5 && fixedVals[2] === "" && fixedVals[0] === "a.png", "a value of the wrong type falls back to the fresh default");
check(shadow.nineTypeOk("Start_From", 1) && !shadow.nineTypeOk("Start_From", NaN) && shadow.nineTypeOk("Frame_Interval", "2") && !shadow.nineTypeOk("image_1", null),
  "type rules: numbers for Start_From / Duration, text for the rest");

// ---------------- the real hooks
const ext = globalThis.__exts.find((e) => e.name === "IronLeo78.9ImagesToBatchToLLM");
check(!!ext, "the extension is registered");
function NodeType() {}
await ext.beforeRegisterNodeDef(NodeType, { name: "IronLeo78_MTV_PromptGenerator" });
const makeNode = (order = NAMES) => {
  const node = Object.create(NodeType.prototype);
  node.widgets = order.map((n) => ({ name: n, value: FRESH[n], options: {} }));
  node.size = [400, 690];
  node.properties = {};
  node.graph = { _nodes: [], change() {} };
  node.setSize = (s) => { node.size = s; };
  node.addDOMWidget = (name, type, el, opts) => { const w = { name, type, serialize: false, options: opts }; node.widgets.push(w); return w; };
  node.onNodeCreated();
  return node;
};
// what litegraph does on load: assign the saved values by position to the saved widgets, then call onConfigure
const load = (node, info) => {
  const ws = node.widgets.filter((w) => w.serialize !== false && w.options?.serialize !== false);
  ws.forEach((w, i) => { if (i < info.widgets_values.length) w.value = info.widgets_values[i]; });
  node.onConfigure(info);
  return Object.fromEntries(ws.map((w) => [w.name, w.value]));
};
const done = [];

const n1 = makeNode();
done.push(n1);
n1.widgets.filter((w) => w.serialize !== false).forEach((w, i) => { w.value = SAVED[i]; });
const o = {};
n1.onSerialize(o);
const saved = o.properties?.[shadow.SHADOW_KEY];
check(!!saved && saved.image_9 === "i.png" && saved.Video_Size === "896x512" && saved[shadow.LAYOUT_KEY] === NAMES.join("|"),
  "onSerialize writes the named copy into the saved properties");
check(!("thumbnails" in saved) && !("video_slot" in saved), "the DOM grid / video cell (not saved widgets) are not in the copy");

const n2 = makeNode();
done.push(n2);
const v2 = load(n2, { widgets_values: SAVED.slice(), properties: { [shadow.SHADOW_KEY]: saved } });
check(same(Object.values(v2), SAVED), "load, same layout: every value as saved");

// a future version moves Video_Size to the top: the old workflow's positional values would be shifted, the copy fixes it
const n3 = makeNode(moved);
done.push(n3);
const info3 = { widgets_values: SAVED.slice(), properties: { [shadow.SHADOW_KEY]: saved } };
const v3 = load(n3, info3);
check(v3.Video_Size === "896x512" && v3.image_1 === "a.png" && v3.Duration === 5.1667 && v3.video === "clip.mp4",
  "load after a widget moved: the values are restored by name");
check(info3.widgets_values[0] === "896x512" && info3.widgets_values.length === SAVED.length, "the saved list itself is corrected in place");

const n4 = makeNode();
done.push(n4);
const v4 = load(n4, { widgets_values: SAVED.slice(), properties: {} });
check(same(Object.values(v4), SAVED), "an older workflow (no copy): loads by position, as before");

for (const n of done) n.onRemoved?.();      // stops the per-node sync timer so node can exit
console.log(fails ? `\n${fails} FAILED` : `\nALL ${passed} SHADOW CHECKS PASSED`);
process.exit(fails ? 1 : 0);
