// Test of the v0.6 workflow migration in web/ironleo78_mtv.js (no jsdom needed, only node).
//   node tests/test_migration.mjs
// Workflows saved with 0.5 (or 0.4.1 and older) still carry the removed upscale widgets; the extension must drop them
// without shifting the other values, and map "Latent Upscale OFF" (= latents were saved) to "Save Latent ON".
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ironleo78_mig_"));
fs.mkdirSync(path.join(tmp, "scripts")); fs.mkdirSync(path.join(tmp, "ext", "web"), { recursive: true });
fs.writeFileSync(path.join(tmp, "scripts", "app.js"), "export const app = { registerExtension() {}, graph: { _nodes: [] } };\n");
fs.writeFileSync(path.join(tmp, "scripts", "api.js"), "export const api = { apiURL: (p) => p, addEventListener() {}, removeEventListener() {}, async fetchApi() { return { json: async () => ({}) }; } };\n");
fs.copyFileSync(path.join(here, "..", "web", "ironleo78_mtv.js"), path.join(tmp, "ext", "web", "ext.mjs"));
const { migrateMakerValues, migrateLoaderValues } = await import(pathToFileURL(path.join(tmp, "ext", "web", "ext.mjs")).href);

let fails = 0;
const check = (c, m) => { if (!c) { fails++; console.log("  FAIL -", m); } else console.log("  ok -", m); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const NEW = ["Turbo", "Use Video", "Video File", "Custom Audio File", "Audio Stem", "megapixels", "duration",
  "Next Segment On Run", "prompt", "Bypassed Audio Latent", "Save Latent", "Guide", "picture_1", "picture_2", "picture_3"];
const head = [true, false, "None", "Song.wav", "Vocals", 0.2, 15, true, "my prompt", true];      // Turbo .. Bypassed Audio Latent
const pics = ["a.png", "b.png", "None"];

console.log("1. a workflow saved with 0.5");
for (const [upscale, saveLatent] of [[true, false], [false, true]]) {
  const v05 = [...head, upscale, true, 0.4, "HIGH", true, "Upscaled only", ...pics];
  const out = migrateMakerValues(NEW, v05);
  check(out && out.length === NEW.length, `Latent Upscale ${upscale ? "ON" : "OFF"}: ${NEW.length} values come out`);
  check(same(out, [...head, saveLatent, true, ...pics]),
    `Latent Upscale ${upscale ? "ON" : "OFF"} -> Save Latent ${saveLatent ? "ON" : "OFF"}; Guide, pictures and the rest stay where they were`);
}

console.log("2. a workflow saved with 0.4.1 or older (no Temporal Chunking / Upscale Quality)");
const v04 = [...head, false, 0.4, false, "Draft + Upscaled", ...pics];
check(same(migrateMakerValues(NEW, v04), [...head, true, false, ...pics]), "Latent Upscale OFF -> Save Latent ON, Guide OFF kept");

console.log("3. nothing to do");
check(migrateMakerValues(NEW, [...head, true, true, ...pics]) === null, "a workflow already in the 0.6 format is left alone");
check(migrateMakerValues(NEW, undefined) === null && migrateMakerValues(NEW, [1, 2, 3]) === null, "missing / odd value lists are left alone");
check(migrateMakerValues([...NEW.slice(0, 10), "Latent Upscale", ...NEW.slice(11)], [...head, true, ...NEW.slice(11).map(() => 1)]) === null,
  "a node that still has the old widget list is not touched");

console.log("4. Model Loader saved with 0.5 (one value more: upscale_model_name)");
const LOADER = ["unet_name", "custom_lora_enabled", "custom_lora_name", "custom_lora_strength", "turbo_lora_name", "qwen_vl_name",
  "video_vae_name", "audio_vae_name", "turbo_steps", "full_steps", "noise_seed", "control_after_generate"];
const oldLoader = ["u.safetensors", false, "None", 0.65, "t.safetensors", "q.safetensors", "v.safetensors", "a.safetensors",
  "h3_upscaler.safetensors", 4, 25, 1978, "fixed"];
check(same(migrateLoaderValues(LOADER, oldLoader),
  ["u.safetensors", false, "None", 0.65, "t.safetensors", "q.safetensors", "v.safetensors", "a.safetensors", 4, 25, 1978, "fixed"]),
  "the upscale model value is dropped, steps and seed keep their values");
check(migrateLoaderValues(LOADER, oldLoader.filter((_, i) => i !== 8)) === null, "a new-format Model Loader is left alone");

fs.rmSync(tmp, { recursive: true, force: true });
console.log(fails ? `\n${fails} FAILED` : "\nALL MIGRATION CHECKS PASSED");
process.exit(fails ? 1 : 0);
