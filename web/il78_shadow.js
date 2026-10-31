// IronLeo78 9-Images-to-batch-to-LLM - named copy of the widget values (v0.0.2d).
// Saved workflows store widget values BY POSITION: a widget added, removed or moved in a later version would shift them.
// So every save also writes a copy BY NAME in the node's properties (`ironleo78_values`, plus `__layout` = the widget names
// in their saved order). On load, when the widgets are no longer in that order, the values are restored by name.
// Same key and same `__layout` rule as the IronLeo78 MTV nodes, so the copy keeps working once this node joins the MTV pack.
// Pure functions, no imports, no DOM: ironleo78_9images.js calls them, tests/test_shadow.mjs runs them in plain node.

export const SHADOW_KEY = "ironleo78_values";
export const LAYOUT_KEY = "__layout";
const NUMBERS = new Set(["Start_From", "Duration"]);

// a saved value must have its widget's type: numbers for Start_From / Duration, text for everything else
// (image_1..9 / video file names, Frame_Interval, Video_Size)
export function nineTypeOk(name, v) {
  if (NUMBERS.has(name)) return typeof v === "number" && Number.isFinite(v);
  return typeof v === "string";
}

// the copy to write on every save. serial = the node's serialized widgets [{name, value}]
export function buildShadow(serial) {
  const copy = {};
  for (const w of serial) copy[w.name] = w.value;
  copy[LAYOUT_KEY] = serial.map((w) => w.name).join("|");
  return copy;
}

// names = serialized widget names (current order), shadow = the saved copy, defaults = {name: value} of a fresh node.
// Returns the values in the current order, or null when the positional values are right (same layout) or there is no usable copy.
export function restoreFromShadow(names, shadow, defaults) {
  if (!shadow || typeof shadow !== "object" || Array.isArray(shadow)) return null;
  if (!names.some((n) => Object.prototype.hasOwnProperty.call(shadow, n))) return null;
  if (shadow[LAYOUT_KEY] === names.join("|")) return null;
  const out = names.map((n) => {
    if (Object.prototype.hasOwnProperty.call(shadow, n) && nineTypeOk(n, shadow[n])) return shadow[n];
    return defaults ? defaults[n] : undefined;       // a widget added after the copy was made (or a damaged value): its default
  });
  return out.some((v) => v === undefined) ? null : out;
}
