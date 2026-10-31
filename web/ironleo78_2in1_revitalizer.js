// IronLeo78 2in1 Revitalizer: "Upload latent / conditioning files" button.
// v0.0.9: the node no longer saves the video (link `video` to a Save Video) and the last widget, `filename_prefix`, was
// replaced by `sigmas` (editable text). A workflow saved before holds the old prefix text where `sigmas` now sits:
// migrateRevitalizerSigmas puts the default sigmas there (detected by WHAT the value is, never by counting).
// v0.0.9c: three more LoRAs (LoRa_1 .. LoRa_3, appended after `sigmas` as optional widgets) and the Model Loader's saved set
// ("Set New Defaults"): a button on this node loads it, and clicking Set New Defaults on a Model Loader sends it to the
// Revitalizers of the open workflow. A workflow saved before has no value for the nine new widgets: loraRepairs gives them OFF /
// None / LORA_STRENGTH (detected by WHAT is there, never by counting), so an old workflow never starts using a LoRA by itself.
// v0.0.9u: like the Model Loader and the MTV node, the Revitalizer keeps a copy of its values BY NAME in its properties
// (`ironleo78_values`, written on every save). Its saved list is positional AND holds the seed's "control after generate" word
// in the MIDDLE (right after the seed), so a restored list gets that word inserted at its place, not appended.
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE = "IronLeo78_2in1_Revitalizer";
const TAG = "[uploaded] ";
export const DEFAULT_SIGMAS = "0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000";
const CONTROL_VALUES = ["fixed", "increment", "decrement", "randomize"];

// true when `text` is a usable sigma list (same rules as parse_sigmas in revitalizer.py)
export function sigmasOk(text) {
  if (typeof text !== "string") return false;
  const parts = text.replace(/[\[\]]/g, " ").split(/[\s,;]+/).filter(Boolean);
  if (parts.length < 2) return false;
  const nums = parts.map((x) => (/^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(x) ? Number(x) : NaN));
  if (nums.some((n) => !Number.isFinite(n) || n < 0)) return false;
  for (let i = 1; i < nums.length; i++) if (nums[i] > nums[i - 1]) return false;
  return nums[nums.length - 1] < nums[0];
}

// names = serialized widget names (the "control after generate" widget is not in it), vals = widgets_values as saved.
// Returns the index of the saved value that belongs to `sigmas` and holds something else (the old filename_prefix), or -1.
export function oldPrefixIndex(names, vals) {
  if (!Array.isArray(vals)) return -1;
  const s = names.indexOf("seed");
  if (s < 0 || names.indexOf("sigmas") < 0) return -1;
  let k = s + 1;
  if (typeof vals[k] === "string" && CONTROL_VALUES.includes(vals[k])) k++;     // the saved "control after generate" value sits right after the seed
  // k = sampler_name, k + 1 = what `sigmas` now is
  if (k + 1 >= vals.length || typeof vals[k + 1] !== "string") return -1;
  return sigmasOk(vals[k + 1]) ? -1 : k + 1;
}


// ---------------------------------------------------------------- v0.0.9c: LoRa_1 .. LoRa_3 + the saved set
export const SET_ROUTE = "/ironleo78/revitalizer/saved_set";
export const SET_EVENT = "ironleo78-set-saved";          // the Model Loader fires it after a successful "Set New Defaults"
export const LORA_SLOTS = 3;
export const LORA_NONE = "None";
export const LORA_STRENGTH = 1.0;          // v0.1.11 (0.65 until 0.1.10), same as revitalizer.py SLOT_STRENGTH
export const LORA_NAMES = [1, 2, 3].flatMap((n) => [`LoRa_${n}_enabled`, `LoRa_${n}`, `LoRa_${n}_strength`]);
const loraDefault = (name) => (name.endsWith("_enabled") ? false : name.endsWith("_strength") ? LORA_STRENGTH : LORA_NONE);
const loraValueOk = (name, v) => (name.endsWith("_enabled") ? typeof v === "boolean" : name.endsWith("_strength") ? typeof v === "number" && Number.isFinite(v) : typeof v === "string" && v !== "");
const sameValue = (a, b) => (typeof a === "number" && typeof b === "number" ? Math.abs(a - b) < 1e-9 : a === b);

// names = serialized widget names, vals = widgets_values as saved. Returns [{name, index, value}] for every one of the nine LoRa_n values
// that the saved list does not hold in a usable form (a workflow saved before 0.0.9c holds nothing, or the Upload button's value, there).
// `index` = where that value sits in the saved list (the saved \"control after generate\" word right after the seed shifts it by one).
export function loraRepairs(names, vals) {
  if (!Array.isArray(vals) || !Array.isArray(names)) return [];
  const seed = names.indexOf("seed");
  let shift = 0;
  if (seed >= 0 && !names.includes("control_after_generate") && typeof vals[seed + 1] === "string" && CONTROL_VALUES.includes(vals[seed + 1])) shift = 1;
  const out = [];
  for (const name of LORA_NAMES) {
    const at = names.indexOf(name);
    if (at < 0) continue;                                // this node does not have the widget: nothing to repair
    const index = at + shift;
    if (!loraValueOk(name, vals[index])) out.push({ name, index, value: loraDefault(name) });
  }
  return out;
}


// ---------------------------------------------------------------- v0.0.9u: the named copy of the values
// Same key, same `__layout` rule and same idea as the Model Loader / MTV node (web/ironleo78_mtv.js); the few lines are repeated here
// on purpose: importing that file would run its extension a second time under another module URL (and the tests load each file alone).
// A workflow saved with this release or later holds {widgetName: value, ..., control_after_generate, __layout}. On load, when the
// widget order is no longer the one it was saved with, every value is put back on ITS widget by name, so a later update that moves
// or adds widgets cannot shift the saved values any more. Workflows saved before keep using the position-based repairs above.
export const SHADOW_KEY = "ironleo78_values";
export const LAYOUT_KEY = "__layout";
export const CONTROL_KEY = "control_after_generate";
const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const REV_TYPES = {
  latent: "string", conditioning: "string", freeze_audio: "boolean", unet_name: "string", vae_video: "string", vae_audio: "string",
  lora_on: "boolean", lora_name: "string", lora_strength: "number", attention_backend: "string", upscale_on: "boolean", upscale_model: "string",
  megapixels: "number", temporal_chunking: "boolean", force_unload: "boolean", upscale_device: "string", upscale_precision: "string",
  seed: "number", sampler_name: "string", sigmas: "string",
};
// a value must have the type its widget has (a widget this table does not know: any plain value; an empty LoRa_n file name is not usable)
export function revTypeOk(name, v) {
  if (LORA_NAMES.includes(name)) return loraValueOk(name, v);
  const t = REV_TYPES[name];
  if (t === "number") return typeof v === "number" && Number.isFinite(v);
  if (t) return typeof v === t;
  return typeof v === "string" || typeof v === "boolean" || (typeof v === "number" && Number.isFinite(v));
}
// the widgets whose value is a setting: serialized, and not a button (the Upload button holds no setting)
export const dataWidgets = (node) => (node.widgets || []).filter((w) => w.serialize !== false && w.options?.serialize !== false && w.type !== "button");
// the copy to write on every save. serial = dataWidgets(node), control = the seed's "control after generate" widget (or null/undefined)
export function buildRevShadow(serial, control) {
  const copy = {};
  for (const w of serial) copy[w.name] = w.value;
  if (control && typeof control.value === "string") copy[CONTROL_KEY] = control.value;
  copy[LAYOUT_KEY] = serial.map((w) => w.name).join("|");
  return copy;
}
// names = dataWidgets names (current order), shadow = the saved copy, defaults = {name: value} of a fresh node.
// Returns {list, byName, control} or null (no usable copy / the order did not change since the save / a widget with no default).
//   list   = the values in the SAVED-LIST order of this node: current widget order, with the control word right after the seed
//   byName = the same values by widget name
export function restoreRevFromShadow(names, shadow, defaults) {
  if (!shadow || typeof shadow !== "object" || Array.isArray(shadow) || !Array.isArray(names)) return null;
  if (!names.some((n) => hasOwn(shadow, n))) return null;
  // same order as when the workflow was saved: the positional values are right (a value edited by hand in the file stays)
  if (shadow[LAYOUT_KEY] === names.join("|")) return null;
  const byName = {};
  for (const n of names) {
    if (hasOwn(shadow, n) && revTypeOk(n, shadow[n])) byName[n] = shadow[n];
    else if (defaults && defaults[n] !== undefined && defaults[n] !== null) byName[n] = defaults[n];      // added after the copy was made, or damaged
    else return null;
  }
  const control = typeof shadow[CONTROL_KEY] === "string" && CONTROL_VALUES.includes(shadow[CONTROL_KEY]) ? shadow[CONTROL_KEY] : "fixed";
  const list = [];
  for (const n of names) {
    list.push(byName[n]);
    if (n === "seed") list.push(control);
  }
  return { list, byName, control };
}
// the values of a fresh node (before any workflow is loaded into it); the LoRa_n ones are always OFF / None / LORA_STRENGTH, never the saved set's
export function freshDefaults(node) {
  const out = {};
  for (const w of dataWidgets(node)) if (w.value !== null && w.value !== undefined) out[w.name] = w.value;
  for (const n of LORA_NAMES) out[n] = loraDefault(n);
  return out;
}

// the set to the widgets. widgets = [{name, value, values}] (values = the list of a combo, else null); mapped = {widget name: value}
// (the backend already translated the Model Loader's names). A combo file that is not installed keeps the current value and is
// reported; a LoRa_n file that is not installed becomes None and that LoRa_n is switched OFF (never ON with no file).
export function planRevitalizerSet(widgets, mapped) {
  const set = {}, missing = [];
  if (!mapped || typeof mapped !== "object") return { set, missing };
  const byName = Object.fromEntries(widgets.map((w) => [w.name, w]));
  for (const w of widgets) {
    if (!Object.prototype.hasOwnProperty.call(mapped, w.name)) continue;
    const want = mapped[w.name];
    if (Array.isArray(w.values) && !w.values.includes(want)) {
      if (/^LoRa_\d$/.test(w.name) && w.values.includes(LORA_NONE)) {
        set[w.name] = LORA_NONE;
        if (byName[w.name + "_enabled"]) set[w.name + "_enabled"] = false;
        missing.push({ name: w.name, want, keep: "None, OFF" });
      } else missing.push({ name: w.name, want, keep: w.value });
    } else set[w.name] = want;
  }
  return { set, missing };
}
export function verifyRevitalizerSet(widgets, plan) {
  const now = Object.fromEntries(widgets.map((w) => [w.name, w.value]));
  const names = Object.keys(plan.set);
  const bad = names.filter((n) => !sameValue(now[n], plan.set[n]));
  return { total: names.length, ok: names.length - bad.length, bad };
}
// sets the widgets and reads them back. serial = the node's serialized widgets, control = the seed's \"control after generate\" widget (or null),
// controlValue = the saved seed control (null = leave it)
export function applyRevitalizerSet(serial, control, mapped, controlValue) {
  const comboValues = (w) => {
    const v = w.options?.values;
    return Array.isArray(v) ? v : typeof v === "function" ? v() : null;
  };
  const view = () => serial.map((w) => ({ name: w.name, value: w.value, values: comboValues(w) }));
  const plan = planRevitalizerSet(view(), mapped);
  for (const w of serial) {
    if (!(w.name in plan.set)) continue;
    w.value = plan.set[w.name];
    try { w.callback?.(w.value); } catch (e) { /* the value is set, the callback is cosmetic */ }
  }
  if (control && typeof controlValue === "string" && Object.prototype.hasOwnProperty.call(plan.set, "seed")) control.value = controlValue;
  const check = verifyRevitalizerSet(view(), plan);
  if (control && typeof controlValue === "string" && Object.prototype.hasOwnProperty.call(plan.set, "seed")) {
    check.total += 1;
    if (control.value === controlValue) check.ok += 1; else check.bad.push("control_after_generate");
  }
  return { plan, check };
}
// [{name, from, to}] for every value the set changed (what the node held before and the set replaced)
export function changedValues(before, set, controlFrom, controlTo) {
  const out = [];
  for (const n of Object.keys(set || {})) {
    if (Object.prototype.hasOwnProperty.call(before, n) && !sameValue(before[n], set[n])) out.push({ name: n, from: before[n], to: set[n] });
  }
  if (typeof controlTo === "string" && typeof controlFrom === "string" && controlFrom !== controlTo) out.push({ name: "control_after_generate", from: controlFrom, to: controlTo });
  return out;
}
export const NO_SET_TEXT = "⚠ No saved set yet: set a Model Loader the way you want and click Set New Defaults there, then click here.";
export function setMessage(result, changed, origin) {
  const { plan, check } = result;
  const lead = origin === "sent" ? "Sent by the Model Loader's Set New Defaults. " : "";
  if (check.bad.length) return { level: "error", text: `✖ ${lead}Saved set: ${check.ok} of ${check.total} values loaded. Did not take: ${check.bad.join(", ")}` };
  const miss = plan.missing.length ? ` Not installed here: ${plan.missing.map((m) => `${m.name} (${m.want}) kept as ${m.keep}`).join(", ")}.` : "";
  const shown = changed.length
    ? ` Replaced: ${changed.slice(0, 6).map((c) => `${c.name} ${c.from} → ${c.to}`).join(", ")}${changed.length > 6 ? `, +${changed.length - 6} more` : ""}.`
    : " Nothing differed.";
  return { level: plan.missing.length ? "warn" : "ok", text: `${plan.missing.length ? "⚠" : "✔"} ${lead}Saved set loaded: ${check.ok} of ${check.total} values (diffusion model, VAEs, Turbo LoRA file, LoRa_1-3 toggle / file / strength, seed + its control).${shown}${miss}` };
}
// wires the Model Loader's event to every Revitalizer of the open workflow (win / getNodes are parameters so a test can drive it)
export function listenForSavedSet(win, getNodes) {
  if (!win || typeof win.addEventListener !== "function") return false;
  win.addEventListener(SET_EVENT, () => {
    for (const n of getNodes() || []) {
      if (n && n.comfyClass === NODE && typeof n.ironleo78UseSet === "function") n.ironleo78UseSet("sent");
    }
  });
  return true;
}

const serializedWidgets = (node) => (node.widgets || []).filter((w) => w.serialize !== false && w.options?.serialize !== false);

async function refreshLists(node) {
  const r = await api.fetchApi("/object_info/" + NODE);
  const info = (await r.json())[NODE].input.required;
  for (const [name, spec] of [["latent", info.latent], ["conditioning", info.conditioning]]) {
    const w = node.widgets?.find((x) => x.name === name);
    if (w) w.options.values = spec[0];
  }
}

async function upload(node, files) {
  const body = new FormData();
  for (const f of files) body.append("file", f, f.name);
  let result;
  try {
    const resp = await api.fetchApi("/ironleo78/revitalizer/upload", { method: "POST", body });
    if (!resp.ok) throw new Error(resp.status + " " + resp.statusText);
    result = await resp.json();
  } catch (e) {
    alert("2in1 Revitalizer upload failed: " + e);
    return;
  }
  await refreshLists(node);
  const latent = node.widgets.find((w) => w.name === "latent");
  const cond = node.widgets.find((w) => w.name === "conditioning");
  const video = result.saved.find((n) => n.endsWith("_video.latent"));
  const conditioning = result.saved.find((n) => n.endsWith(".conditioning"));
  if (video) latent.value = TAG + video;
  if (conditioning) cond.value = TAG + conditioning;
  node.setDirtyCanvas(true, true);
  const notes = [];
  if (result.refused.length) notes.push("Not accepted (only .latent and .conditioning files): " + result.refused.join(", "));
  if (result.saved.length && !video) notes.push("No _video.latent among the files: pick the latent in the list.");
  if (notes.length) alert("2in1 Revitalizer\n" + notes.join("\n"));
}

function pick(node) {
  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = ".latent,.conditioning";
  input.onchange = () => { if (input.files.length) upload(node, [...input.files]); };
  input.click();
}

app.registerExtension({
  name: "IronLeo78.2in1Revitalizer",
  // v0.0.9c: "Use Set New Defaults" panel, FIRST widget (serialize:false like the Model Loader's panel: no saved value moves)
  async nodeCreated(node) {
    if (node.comfyClass !== NODE) return;
    let show = null;
    try {
      if (typeof node.addDOMWidget === "function" && typeof document !== "undefined") {
        const root = document.createElement("div");
        root.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:2px 4px;box-sizing:border-box;width:100%;";
        const btn = document.createElement("button");
        btn.textContent = "Use Set New Defaults";
        btn.title = "Loads the Model Loader's saved set (Set New Defaults) into this node: diffusion model, VAEs, Turbo LoRA file, LoRa_1-3 toggle / file / strength and the seed with its control. Clicking Set New Defaults on a Model Loader does the same for every Revitalizer of the open workflow.";
        btn.style.cssText = "padding:5px 8px;cursor:pointer;border-radius:4px;";
        const msg = document.createElement("div");
        msg.style.cssText = "font-size:11px;line-height:1.3;min-height:14px;white-space:normal;word-break:break-word;";
        root.append(btn, msg);
        const SET_H = 74;
        const dw = node.addDOMWidget("set_view", "ironleo78_set", root, {
          serialize: false, hideOnZoom: false, getMinHeight: () => SET_H, getMaxHeight: () => SET_H,
        });
        dw.serialize = false;
        dw.computeSize = (width) => [width, SET_H];
        const toTop = () => {
          const ws = node.widgets;
          const i = ws ? ws.indexOf(dw) : -1;
          if (i > 0) { ws.splice(i, 1); ws.unshift(dw); node.setDirtyCanvas?.(true, true); }
        };
        toTop();
        setTimeout(toTop, 0);
        setTimeout(toTop, 400);
        const colors = { ok: "#5fbf6a", warn: "#e0a93b", error: "#e0605a" };
        show = (m) => {
          msg.textContent = `${m.text}  (${new Date().toLocaleTimeString()})`;
          msg.style.color = colors[m.level] || "inherit";
          try {
            app.extensionManager?.toast?.add({ severity: m.level === "ok" ? "success" : m.level, summary: "2in1 Revitalizer", detail: m.text, life: 5000 });
          } catch (e) { /* the line under the button is the confirmation */ }
          node.setDirtyCanvas?.(true, true);
        };
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          await node.ironleo78UseSet("button");
          btn.disabled = false;
        });
      }
    } catch (e) {
      console.warn("[IronLeo78] Revitalizer set button not added:", e);
    }
    // the set -> this node's widgets (called by the button and by the Model Loader's event)
    node.ironleo78UseSet = async (origin) => {
      const say = (m) => { if (show) show(m); else console.warn("[IronLeo78] " + m.text); };
      try {
        const res = await api.fetchApi(SET_ROUTE);
        const info = await res.json();
        if (!info?.ok) throw new Error(info?.error || "the backend did not answer");
        if (!info.custom || !info.values) { say({ level: "warn", text: NO_SET_TEXT }); return; }
        const serial = serializedWidgets(node);
        const ctl = (node.widgets || []).find((w) => w.name === "control_after_generate");
        const before = Object.fromEntries(serial.map((w) => [w.name, w.value]));
        const ctlFrom = ctl && typeof ctl.value === "string" ? ctl.value : undefined;
        const ctlTo = typeof info.seed_control === "string" ? info.seed_control : null;
        const result = applyRevitalizerSet(serial, ctl, info.values, ctlTo);
        say(setMessage(result, changedValues(before, result.plan.set, ctlFrom, ctlTo), origin));
        node.setDirtyCanvas?.(true, true);
      } catch (e) {
        say({ level: "error", text: `✖ Saved set NOT loaded: ${e?.message || e}` });
      }
    };
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created ? created.apply(this, arguments) : undefined;
      try { this.__ilRevDefaults = freshDefaults(this); } catch (e) { /* the copy then falls back to the positional route */ }
      this.addWidget("button", "Upload latent / conditioning files...", null, () => pick(this));
      return r;
    };
    // v0.0.9u: every save carries the named copy (same as the Model Loader and the MTV node)
    const serialized = nodeType.prototype.onSerialize;
    nodeType.prototype.onSerialize = function (o) {
      try {
        const copy = buildRevShadow(dataWidgets(this), (this.widgets || []).find((w) => w.name === CONTROL_KEY));
        this.properties = this.properties || {};
        this.properties[SHADOW_KEY] = copy;
        if (o) {
          o.properties = o.properties || {};
          o.properties[SHADOW_KEY] = copy;
        }
      } catch (e) {
        /* the copy is a safety net only */
      }
      return serialized ? serialized.apply(this, arguments) : undefined;
    };
    // v0.0.9: a workflow saved with the old `filename_prefix` text where `sigmas` now is -> the default sigmas
    const configured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function (info) {
      try {
        // v0.0.9u: saved with this release or later and the widgets moved since: every value goes back by NAME, the control word
        // is inserted right after the seed. Same order as at save time / no copy (an older workflow): the repairs below.
        const dnames = dataWidgets(this).map((w) => w.name);
        const shadow = info?.properties?.[SHADOW_KEY] ?? this.properties?.[SHADOW_KEY];
        if (!this.__ilRevDefaults) this.__ilRevDefaults = freshDefaults(this);
        const restored = Array.isArray(info?.widgets_values) ? restoreRevFromShadow(dnames, shadow, this.__ilRevDefaults) : null;
        if (restored) {
          info.widgets_values.splice(0, info.widgets_values.length, ...restored.list);       // IN PLACE: the frontend may assign from its own reference
          const final = { ...restored.byName, [CONTROL_KEY]: restored.control };
          const again = () => {
            try {
              for (const w of (this.widgets || [])) {
                if (w.name in final && w.type !== "button" && w.value !== final[w.name]) w.value = final[w.name];
              }
              this.setDirtyCanvas?.(true, true);
            } catch (e) {
              /* cosmetic only */
            }
          };
          again();
          setTimeout(again, 0);
          setTimeout(again, 400);
          return configured ? configured.apply(this, arguments) : undefined;
        }
        const names = serializedWidgets(this).map((w) => w.name);
        const at = oldPrefixIndex(names, info?.widgets_values);
        const oldPrefix = at >= 0 ? info.widgets_values[at] : null;
        if (at >= 0) info.widgets_values[at] = DEFAULT_SIGMAS;        // in place: the frontend may assign from its own reference
        // v0.0.9c: the nine LoRa_n values a workflow saved before does not hold: OFF / None / LORA_STRENGTH (written in place too, without leaving a gap)
        const repairs = loraRepairs(names, info?.widgets_values);
        for (const r of repairs) if (r.index <= info.widgets_values.length) info.widgets_values[r.index] = r.value;
        const fix = () => {
          try {
            const w = (this.widgets || []).find((x) => x.name === "sigmas");
            if (w && oldPrefix !== null && w.value === oldPrefix) w.value = DEFAULT_SIGMAS;      // also covers the old text being assigned after this hook
            for (const r of repairs) {
              const lw = (this.widgets || []).find((x) => x.name === r.name);
              if (lw) lw.value = r.value;                  // also covers the frontend leaving the new widgets at the saved set's values
            }
            this.setDirtyCanvas?.(true, true);
          } catch (e) {
            /* cosmetic only */
          }
        };
        fix();
        setTimeout(fix, 0);
        setTimeout(fix, 400);
      } catch (e) {
        console.warn("[IronLeo78] Revitalizer migration skipped:", e);
      }
      return configured ? configured.apply(this, arguments) : undefined;
    };
  },
});

// the Model Loader's "Set New Defaults" fires SET_EVENT after its read-back: every Revitalizer of the open workflow loads the set
listenForSavedSet(typeof window !== "undefined" ? window : null, () => app.graph?._nodes ?? app.graph?.nodes ?? []);
