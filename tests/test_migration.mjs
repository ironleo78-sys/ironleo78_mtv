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
fs.writeFileSync(path.join(tmp, "scripts", "app.js"), "export const app = { registerExtension(e) { (globalThis.__exts ||= []).push(e); }, graph: { _nodes: [] } };\n");
fs.writeFileSync(path.join(tmp, "scripts", "api.js"), "export const api = { apiURL: (p) => p, addEventListener() {}, removeEventListener() {}, async fetchApi(url, opts) { return globalThis.__api ? globalThis.__api(url, opts) : { json: async () => ({}) }; } };\n");
fs.copyFileSync(path.join(here, "..", "web", "ironleo78_mtv.js"), path.join(tmp, "ext", "web", "ext.mjs"));
fs.copyFileSync(path.join(here, "..", "web", "il78_sync_logic.js"), path.join(tmp, "ext", "web", "il78_sync_logic.js"));
fs.copyFileSync(path.join(here, "..", "web", "ironleo78_2in1_revitalizer.js"), path.join(tmp, "ext", "web", "rev.mjs"));
const { SHADOW_KEY, LAYOUT_KEY, CONTROL_KEY, restoreFromShadow, makerTypeOk, buildShadow, migrateMakerValues, migrateLoaderValues, repairLoaderValues, migrateAudioMode, isPlaceholderPreview, dropNonePreview, migrateAudioStem, dropOldPictureValues, migrateLoaderLayout, planLoaderDefaults, verifyLoaderDefaults, defaultsMessage, applyLoaderDefaults, collectLoaderValues, verifySavedDefaults, savedMessage, changedBySet, loadedSetMessage } = await import(pathToFileURL(path.join(tmp, "ext", "web", "ext.mjs")).href);

const rev = await import(pathToFileURL(path.join(tmp, "ext", "web", "rev.mjs")).href);
let fails = 0;
const check = (c, m) => { if (!c) { fails++; console.log("  FAIL -", m); } else console.log("  ok -", m); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const NEW = ["Turbo", "Use Video", "Video File", "Custom Audio File", "Audio Stem", "megapixels", "duration",
  "Next Segment On Run", "prompt", "Choose Audio latent", "Save Latent", "Guide"];     // v0.0.9H: 12 widgets (the picture pickers are gone); the 0.0.9H..0.1.10 order (v0.1.11 moved the audio widget up: section 22)
const head = [true, false, "None", "Song.wav", "Vocals", 0.2, 15, true, "my prompt", true];      // Turbo .. Choose Audio latent
const pics = ["a.png", "b.png", "None"];      // what an OLD workflow still holds after Guide: the picture_1..3 values

console.log("1. a workflow saved with 0.5");
for (const [upscale, saveLatent] of [[true, false], [false, true]]) {
  const v05 = [...head, upscale, true, 0.4, "HIGH", true, "Upscaled only", ...pics];
  const out = migrateMakerValues(NEW, v05);
  check(out && out.length === NEW.length, `Latent Upscale ${upscale ? "ON" : "OFF"}: ${NEW.length} values come out`);
  check(same(out, [...head, saveLatent, true]),
    `Latent Upscale ${upscale ? "ON" : "OFF"} -> Save Latent ${saveLatent ? "ON" : "OFF"}; Guide and the rest stay where they were (the old picture values have no widget now)`);
}

console.log("2. a workflow saved with 0.4.1 or older (no Temporal Chunking / Upscale Quality)");
const v04 = [...head, false, 0.4, false, "Draft + Upscaled", ...pics];
check(same(migrateMakerValues(NEW, v04), [...head, true, false]), "Latent Upscale OFF -> Save Latent ON, Guide OFF kept");

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

console.log("5. v0.0.2: the real frontend does NOT list the control_after_generate value among the widget names");
const LOADER_NOCTL = LOADER.slice(0, 11);                       // 11 names, but 12 saved values
const cur = ["u.safetensors", false, "H3.safetensors", 0.64, "t.safetensors", "q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"];
check(migrateLoaderValues(LOADER_NOCTL, cur) === null, "a current-format Model Loader (12 values, 11 names) is NOT migrated (this shifted steps / seed before)");
let v = cur;
for (let i = 0; i < 4; i++) { const m = migrateLoaderValues(LOADER_NOCTL, v); if (m) v = m; }
check(same(v, cur), "loading + saving it again and again never changes a value");
check(migrateLoaderValues(LOADER_NOCTL, oldLoader) !== null && migrateLoaderValues(LOADER_NOCTL, oldLoader).length === 12,
  "a real 0.5 Model Loader is still migrated (upscale model dropped)");
const NEW_UPLOAD = [...head, true, false, ...pics, "image"];     // an upload-button value saved at the end
check(migrateMakerValues(NEW, NEW_UPLOAD) === null, "a current-format MTV with an extra upload value is left alone");
check(same(migrateMakerValues(NEW, [...head, false, true, 0.4, "HIGH", true, "Upscaled only", ...pics, "image"]), [...head, true, true]),
  "a 0.5 MTV that also has an upload value is still migrated");

console.log("6. repairing a Model Loader whose numbers were damaged (v0.0.9 widget list)");
const NL = ["unet_name", "turbo_lora_name", "LoRa_1_enabled", "LoRa_1", "LoRa_1_strength", "LoRa_2_enabled", "LoRa_2", "LoRa_2_strength",
  "LoRa_3_enabled", "LoRa_3", "LoRa_3_strength", "qwen_vl_name", "video_vae_name", "audio_vae_name", "turbo_steps", "full_steps", "noise_seed"];
const curNL = ["u.safetensors", "t.safetensors", false, "H3.safetensors", 0.64, false, "None", 0.65, false, "None", 0.65,
  "q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"];
const damaged = [...curNL.slice(0, 14), "fixed", "fixed", "fixed", "fixed"];
check(same(repairLoaderValues(NL, damaged), [...curNL.slice(0, 14), 6, 30, 1978, "fixed"]),
  "steps and seed saved as 'fixed' come back as 6 / 30 / 1978 (v0.1.11 defaults), everything else stays");
check(repairLoaderValues(NL, curNL) === null, "a healthy Model Loader is left alone");
check(repairLoaderValues(NL, curNL.map((v, i) => (i === 4 ? "x" : v)))?.[4] === 1.0 && repairLoaderValues(NL, curNL.map((v, i) => (i === 5 ? "yes" : v)))?.[5] === false
  && repairLoaderValues(NL, curNL.map((v, i) => (i === 9 ? 3 : v)))?.[9] === "None",
  "a damaged LoRa strength / switch / file is reset too (any of the three)");
check(repairLoaderValues(NL, undefined) === null, "missing values are left alone");

console.log("7. v0.0.3: the audio source became a list");
const withBool = (b) => [...head.slice(0, 9), b, true, false, ...pics];
check(migrateAudioMode(NEW, withBool(false))[9] === "Audio From Video", "an old OFF becomes Audio From Video");
check(migrateAudioMode(NEW, withBool(true))[9] === "Custom Audio", "an old ON becomes Custom Audio");
check(migrateAudioMode(NEW, withBool("MiniMax Audio")) === null, "a value that is already text is left alone");
check(migrateAudioMode(["a", "b"], [1, 2]) === null && migrateAudioMode(NEW, undefined) === null, "other node layouts / missing values are left alone");
check(same(migrateAudioMode(NEW, withBool(true)).filter((_, i) => i !== 9), withBool(true).filter((_, i) => i !== 9)), "nothing else changes");

console.log("8. v0.0.6: the \"Video failed to load\" placeholder preview");
const img = (filename) => ({ filename, subfolder: "", type: "input" });
check(isPlaceholderPreview({ images: [img("None")] }) === true, "a preview of the file called None is a placeholder");
check(isPlaceholderPreview({ images: [img("clip.mp4")] }) === false, "the preview of a real video is kept");
check(isPlaceholderPreview({ images: [img("a.png")] }) === false, "the preview of a real picture is kept");
check(isPlaceholderPreview({ text: ["report"] }) === false && isPlaceholderPreview(undefined) === false && isPlaceholderPreview({ images: [] }) === false, "no images / no output: nothing to drop");
check(isPlaceholderPreview({ images: [img("clip.mp4")] }, true) === true, "ALWAYS_HIDE_VIDEO_PREVIEW: a real video preview goes too");
check(isPlaceholderPreview({ images: [img("a.png")] }, true) === false, "ALWAYS_HIDE_VIDEO_PREVIEW: a picture preview stays");
const store = { "12": { images: [img("None")], text: ["x"] }, "13": { images: [img("None")] }, "sub-uuid:12": { images: [img("None")] }, "14": { images: [img("clip.mp4")] } };
check(dropNonePreview(store, 12) === true && !("12" in store) && !("sub-uuid:12" in store), "the placeholder of node 12 is removed (also inside a subgraph)");
check("13" in store && "14" in store, "other nodes are untouched");
check(dropNonePreview(store, 14) === false && "14" in store, "a real video preview of node 14 stays");
check(dropNonePreview(store, 14, true) === true && !("14" in store), "...unless ALWAYS_HIDE_VIDEO_PREVIEW is on");
check(dropNonePreview(undefined, 1) === false && dropNonePreview({}, 1) === false, "no store / empty store is fine");

console.log("9. v0.0.7: the Audio Stem \"Song\" is now called \"Full\"");
const withStem = (v) => [...head.slice(0, 4), v, ...head.slice(5), true, false, ...pics];
check(migrateAudioStem(NEW, withStem("Song"))[4] === "Full", "a saved Song becomes Full");
check(migrateAudioStem(NEW, withStem("Vocals")) === null && migrateAudioStem(NEW, withStem("Full")) === null, "Vocals / Full are left alone");
check(same(migrateAudioStem(NEW, withStem("Song")).filter((_, i) => i !== 4), withStem("Song").filter((_, i) => i !== 4)), "nothing else changes");
check(migrateAudioStem(["a", "b"], ["Song", 1]) === null && migrateAudioStem(NEW, undefined) === null, "other layouts / missing values are left alone");

console.log("10. v0.0.9H: picture_1..9 and More References are gone (they were the LAST widgets): the surplus values are cut");
const v07 = [...head, true, false, ...pics];                                           // saved by 0.0.7: Guide, then picture_1..3
const v08 = [...head, true, false, ...pics, false, "None", "None", "None", "None", "None", "None"];   // 0.0.8 / 0.0.9H-before: + More References OFF + picture_4..9
const v08on = [...head, true, false, "a.png", "b.png", "c.png", true, "d.png", "None", "e.png", "None", "None", "i.png"];
const trimmed = dropOldPictureValues(NEW, v07);
check(trimmed && same(trimmed, [...head, true, false]), "a 0.0.7 workflow: the three picker values are cut, the 12 real values stay in place");
check(same(dropOldPictureValues(NEW, v08), [...head, true, false]) && same(dropOldPictureValues(NEW, v08on), [...head, true, false]), "a 0.0.8 workflow (More References OFF or ON, 22 values): cut to the same 12 values, nothing before moves");
check(same(dropOldPictureValues(NEW, [...v07, "image"]), [...head, true, false]), "the upload-button value 'image' at the end goes too");
check(same(dropOldPictureValues(NEW, [...v07, null, "image"]), [...head, true, false]), "a null at the end (a button without a value) goes too");
check(dropOldPictureValues(NEW, [...head, true, false]) === null, "a workflow already in the new layout (12 values) is left alone: idempotent");
check(dropOldPictureValues(NEW, [...head, true, false, 7]) === null && dropOldPictureValues(NEW, [...head, true, false, {}]) === null, "a surplus value that is a number / object is NOT recognised: nothing is touched");
check(dropOldPictureValues(NEW.filter((n) => n !== "Guide"), v07) === null && dropOldPictureValues(NEW, undefined) === null && dropOldPictureValues(NEW, [1, 2]) === null, "other layouts / missing values are left alone");
check(same(dropOldPictureValues(NEW, dropOldPictureValues(NEW, v08)) ?? dropOldPictureValues(NEW, v08), [...head, true, false]), "running it twice gives the same 12 values");
// every value is compared BY NAME before / after (the hard rule): the 12 widgets hold what the old workflow held
const byName = (names, vals) => Object.fromEntries(names.map((n, i) => [n, vals[i]]));
const oldNames = [...NEW, "picture_1", "picture_2", "picture_3"];
const was = byName(oldNames, v07), now = byName(NEW, trimmed);
check(NEW.every((n) => was[n] === now[n]), "all 12 values are identical by name before and after: " + NEW.map((n) => n + "=" + JSON.stringify(now[n])).join(" "));
// a workflow saved with 0.5 still migrates with the short widget list, and nothing is left over to cut
const mig05 = migrateMakerValues(NEW, [...head, false, true, 0.4, "HIGH", true, "Upscaled only", ...pics]);   // the real 0.5 layout, Latent Upscale OFF
check(mig05 && mig05.length === 12 && mig05[10] === true && mig05[11] === true && dropOldPictureValues(NEW, mig05) === null, "a 0.5 workflow still migrates with the 12-widget list (Latent Upscale OFF -> Save Latent ON); nothing is left to cut");

console.log("11. v0.0.9: the Model Loader's saved values moved (three LoRAs right after the Turbo LoRA)");
const NLN = NL;                       // the new widget list (the control value is saved without a name)
const WANT = ["u.safetensors", "t.safetensors", true, "H3.safetensors", 0.5, false, "None", 1.0, false, "None", 1.0,
  "q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"];
const layoutA = ["u.safetensors", true, "H3.safetensors", 0.5, "t.safetensors", "q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"];
check(same(migrateLoaderLayout(NLN, layoutA), WANT), "a 0.0.8 Model Loader: the custom LoRA block moves behind the Turbo LoRA, models / steps / seed keep their values, LoRa_2 / LoRa_3 are OFF");
const withUpscale = [...layoutA.slice(0, 8), "h3_upscaler.safetensors", ...layoutA.slice(8)];
check(same(migrateLoaderLayout(NLN, withUpscale), WANT), "a 0.5 Model Loader (upscale model value too) comes out the same");
const layoutC = ["u.safetensors", "t.safetensors", "q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"];
const fromC = migrateLoaderLayout(NLN, layoutC);
check(fromC && fromC[1] === "t.safetensors" && fromC[2] === false && fromC[3] === "None" && fromC[4] === 1.0 && same(fromC.slice(11), ["q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"]),
  "a Model Loader from before the custom LoRA existed: nothing shifts, the LoRAs start OFF");
check(migrateLoaderLayout(NLN, WANT) === null, "a workflow already in the new layout is left alone (even with the unnamed control value)");
let loop = layoutA;
for (let i = 0; i < 4; i++) { const m = migrateLoaderLayout(NLN, loop); if (m) loop = m; }
check(same(loop, WANT), "load + save again and again never changes a value");
check(same(migrateLoaderLayout(NLN, layoutA.slice(0, 11)).slice(14), [8, 30, 2026]), "a list without the control value is fine");
check(migrateLoaderLayout(["unet_name", "turbo_lora_name"], layoutA) === null && migrateLoaderLayout(NLN, undefined) === null && migrateLoaderLayout(NLN, [1, 2]) === null,
  "an old widget list / missing / odd values are left alone");
// the whole chain, like the extension runs it: layout first, then the 0.5 upscale drop, then the repair
const chain = (v) => { for (const fn of [migrateLoaderLayout, migrateLoaderValues, repairLoaderValues]) { const m = fn(NLN, v); if (m) v = m; } return v; };
check(same(chain(layoutA), WANT) && same(chain(withUpscale), WANT) && same(chain(WANT), WANT), "layout -> upscale drop -> repair: every old format ends in the same values, the new one is untouched");
check(same(chain([...layoutA.slice(0, 8), "fixed", "fixed", "fixed", "fixed"]).slice(14), [6, 30, 1978, "fixed"]), "an old damaged Model Loader is moved AND repaired (steps 6 / 30, seed 1978)");

console.log("11b. v0.1.11: turbo_lora_strength right under turbo_lora_name (a saved value moves)");
const NL11 = ["unet_name", "turbo_lora_name", "turbo_lora_strength", ...NL.slice(2)];
const want11 = (src) => [src[0], src[1], 1.0, ...src.slice(2)];                    // the 0.1.10 values with the old hardcoded strength 1.0 inserted
const v0110 = ["u.safetensors", "t.safetensors", true, "H3.safetensors", 0.5, false, "None", 0.65, false, "x.safetensors", -2, "q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "randomize"];
check(same(migrateLoaderLayout(NL11, v0110), want11(v0110)), "a 0.0.9 .. 0.1.10 Model Loader (no copy): 1.0 is inserted after the Turbo LoRA file, every other value keeps its own (also the control value at the end)");
const was11 = Object.fromEntries(NL.map((n, i) => [n, v0110[i]])), now11 = Object.fromEntries(NL11.map((n, i) => [n, migrateLoaderLayout(NL11, v0110)[i]]));
check(NL.every((n) => was11[n] === now11[n]) && now11.turbo_lora_strength === 1.0, "compared BY NAME: all 17 old values identical, turbo_lora_strength = 1.0");
check(migrateLoaderLayout(NL11, want11(v0110)) === null, "a 0.1.11 Model Loader is left alone (idempotent)");
check(migrateLoaderLayout(NL11, want11(v0110).map((v, i) => (i === 2 ? 0.7 : v))) === null, "a 0.1.11 Model Loader with its own Turbo strength (0.7) is left alone");
const A11 = migrateLoaderLayout(NL11, layoutA);
check(A11 && A11[2] === 1.0 && A11[1] === "t.safetensors" && A11[3] === true && A11[4] === "H3.safetensors" && same(A11.slice(15), [8, 30, 2026, "fixed"]), "a 0.0.8 Model Loader into the 0.1.11 list: Turbo strength 1.0, LoRA block and steps / seed in place");
const C11 = migrateLoaderLayout(NL11, layoutC);
check(C11 && C11[2] === 1.0 && C11[3] === false && same(C11.slice(12), ["q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"]), "a Model Loader from before the custom LoRA: Turbo strength 1.0, nothing shifts");
const chain11 = (v) => { for (const fn of [migrateLoaderLayout, migrateLoaderValues, repairLoaderValues]) { const m = fn(NL11, v); if (m) v = m; } return v; };
let loop11 = v0110;
for (let i = 0; i < 4; i++) loop11 = chain11(loop11);
check(same(loop11, want11(v0110)) && same(chain11(withUpscale), A11), "the whole chain, load + save x4: the same values every time; a 0.5 loader ends like the 0.0.8 one");
check(repairLoaderValues(NL11, want11(v0110).map((v, i) => (i === 2 ? "x" : v)))?.[2] === 1.0, "a damaged Turbo strength is repaired to 1.0");

console.log("12. v0.0.9: the Model Loader keeps a copy of its values BY NAME (immune to widgets moving)");
const LN = ["unet_name", "turbo_lora_name", "LoRa_1_enabled", "LoRa_1", "LoRa_1_strength", "LoRa_2_enabled", "LoRa_2", "LoRa_2_strength",
  "LoRa_3_enabled", "LoRa_3", "LoRa_3_strength", "qwen_vl_name", "video_vae_name", "audio_vae_name", "turbo_steps", "full_steps", "noise_seed"];
const USER_FIXED = ["minimax_unet.safetensors", "turbo.safetensors", true, "H3_Unlocked_V2.safetensors", 0.65, true, "Astro.safetensors", 1, true, "swap.safetensors", 1,
  "qwen.safetensors", "vvae.safetensors", "avae.safetensors", 4, 40, 1978, "fixed"];
const DEF = { unet_name: "u0", turbo_lora_name: "t0", LoRa_1_enabled: false, LoRa_1: "None", LoRa_1_strength: 0.65, LoRa_2_enabled: false, LoRa_2: "None", LoRa_2_strength: 0.65,
  LoRa_3_enabled: false, LoRa_3: "None", LoRa_3_strength: 0.65, qwen_vl_name: "q0", video_vae_name: "v0", audio_vae_name: "a0", turbo_steps: 4, full_steps: 40, noise_seed: 1978 };
const shadowOf = (names, vals, extra = {}) => ({ ...Object.fromEntries(names.map((n, i) => [n, vals[i]])), [CONTROL_KEY]: vals[names.length], [LAYOUT_KEY]: names.join("|"), ...extra });
// (a) same order as when saved: positional values are used (a hand-edited value stays), the copy is not needed
check(restoreFromShadow(LN, shadowOf(LN, USER_FIXED), DEF) === null, "same widget order as at save time: nothing to restore");
// (b) the widgets moved in a later update: the values follow their NAMES
const MOVED = ["unet_name", "turbo_lora_name", "qwen_vl_name", "video_vae_name", "audio_vae_name", "LoRa_1_enabled", "LoRa_1", "LoRa_1_strength", "LoRa_2_enabled", "LoRa_2", "LoRa_2_strength",
  "LoRa_3_enabled", "LoRa_3", "LoRa_3_strength", "turbo_steps", "full_steps", "noise_seed"];
const back = restoreFromShadow(MOVED, shadowOf(LN, USER_FIXED), DEF);
const byN = Object.fromEntries(MOVED.map((n, i) => [n, back[i]]));
check(byN.LoRa_2 === "Astro.safetensors" && byN.LoRa_3_strength === 1 && byN.qwen_vl_name === "qwen.safetensors" && byN.turbo_steps === 4 && byN.full_steps === 40 && byN.noise_seed === 1978 && back[MOVED.length] === "fixed" && back.length === MOVED.length + 1,
  "a later update moved the widgets: every value still lands on its own widget, the control value stays last");
// (c) a widget added by a later update gets its default, a damaged value too
const GROWN = [...LN, "extra_flag"];
const g = restoreFromShadow(GROWN, shadowOf(LN.slice().reverse(), [...USER_FIXED.slice(0, 17).reverse(), "fixed"]), { ...DEF, extra_flag: true });
check(g && g[17] === true && g[0] === USER_FIXED[0], "a widget the copy does not know gets its own default");
const dmg = restoreFromShadow(MOVED, { ...shadowOf(LN, USER_FIXED), full_steps: "fixed" }, DEF);
check(dmg[MOVED.indexOf("full_steps")] === 40, "a damaged value in the copy falls back to the default");
check(restoreFromShadow(MOVED, null, DEF) === null && restoreFromShadow(MOVED, { other: 1 }, DEF) === null && restoreFromShadow(MOVED, [], DEF) === null, "no / unusable copy: null");
// (d) the real extension hook, with the frontend assigning from a reference it kept BEFORE our hook ran
const lext = globalThis.__exts.find((e) => e.name === "IronLeo78.ModelLoader.SeedFixed");
const mkLoader = (names) => {
  const ws = names.map((n) => ({ name: n, value: DEF[n] ?? null }));
  ws.push({ name: CONTROL_KEY, value: "randomize", serialize: false });
  return { comfyClass: "IronLeo78_MTV_ModelLoader", id: 3, widgets: ws, properties: {}, setDirtyCanvas() {} };
};
let node = mkLoader(LN);
await lext.nodeCreated(node);
const ser = {};
node.onSerialize(ser);
check(ser.properties[SHADOW_KEY].LoRa_2 === "u0" || ser.properties[SHADOW_KEY].LoRa_2 === "None", "every save writes the named copy");
check(ser.properties[SHADOW_KEY][LAYOUT_KEY] === LN.join("|"), "the copy carries the widget order of the save");
// old 0.0.8 workflow, frontend keeps its own reference to the saved array
node = mkLoader(LN);
await lext.nodeCreated(node);
const oldVals = ["u.safetensors", true, "H3.safetensors", 0.5, "t.safetensors", "q.safetensors", "v.safetensors", "a.safetensors", 8, 30, 2026, "fixed"];
const kept = oldVals;                                           // the frontend's own reference
node.onConfigure({ widgets_values: oldVals, properties: {} });
const ser2 = node.widgets.filter((w) => w.serialize !== false);
for (let i = 0; i < kept.length; i++) if (ser2[i]) ser2[i].value = kept[i];     // the frontend assigns AFTER our hook
const got2 = Object.fromEntries(ser2.map((w) => [w.name, w.value]));
check(got2.unet_name === "u.safetensors" && got2.turbo_lora_name === "t.safetensors" && got2.LoRa_1 === "H3.safetensors" && got2.LoRa_1_strength === 0.5 && got2.qwen_vl_name === "q.safetensors" && got2.turbo_steps === 8 && got2.full_steps === 30 && got2.noise_seed === 2026,
  "an old workflow still lands right when the frontend assigns the values from its own array after the hook (the array is fixed in place)");
// a workflow saved by this release but loaded after the widgets moved
node = mkLoader(MOVED);
await lext.nodeCreated(node);
const saved = shadowOf(LN, USER_FIXED);
node.onConfigure({ widgets_values: USER_FIXED.slice(), properties: { [SHADOW_KEY]: saved } });
const got3 = Object.fromEntries(node.widgets.filter((w) => w.serialize !== false).map((w) => [w.name, w.value]));
check(got3.LoRa_3 === "swap.safetensors" && got3.qwen_vl_name === "qwen.safetensors" && got3.turbo_lora_name === "turbo.safetensors" && got3.full_steps === 40 && got3.LoRa_2_enabled === true,
  "saved by this release, loaded after the widgets moved: restored by name");
await new Promise((r) => setTimeout(r, 450));
check(node.widgets.find((w) => w.name === CONTROL_KEY).value === "fixed", "the control value is restored too");
// idempotence: loading the fixed (user) file layout again changes nothing
node = mkLoader(LN);
await lext.nodeCreated(node);
const info4 = { widgets_values: USER_FIXED.slice(), properties: {} };
node.onConfigure(info4);
const ws4 = node.widgets.filter((w) => w.serialize !== false);
for (let i = 0; i < info4.widgets_values.length; i++) if (ws4[i]) ws4[i].value = info4.widgets_values[i];     // what the frontend does
check(JSON.stringify(info4.widgets_values) === JSON.stringify(USER_FIXED), "the user's fixed values pass the whole chain untouched (saved array)");
await new Promise((r) => setTimeout(r, 450));
check(JSON.stringify(ws4.map((w) => w.value)) === JSON.stringify(USER_FIXED.slice(0, 17)), "the user's fixed values load unchanged (widgets, also after the delayed re-apply)");

console.log("13. v0.0.9: Revitalizer, filename_prefix became sigmas (last widget, so nothing else moved)");
const RN = ["latent", "conditioning", "freeze_audio", "unet_name", "vae_video", "vae_audio", "lora_on", "lora_name", "lora_strength", "attention_backend",
  "upscale_on", "upscale_model", "megapixels", "temporal_chunking", "force_unload", "upscale_device", "upscale_precision", "seed", "sampler_name", "sigmas"];
const rHead = ["S/S_seg000_A_00001_video.latent", "(match the latent)", true, "unet.safetensors", "v.safetensors", "a.safetensors", false, "(none)", 1, "comfy kitchen attention",
  true, "up.safetensors", 2, true, true, "cuda", "fp16", 639560415612468];
check(rev.sigmasOk(rev.DEFAULT_SIGMAS) && !rev.sigmasOk("video/MiniMax_H3") && !rev.sigmasOk("0.9, 0.95") && !rev.sigmasOk("0.5, 0.5") && !rev.sigmasOk("1") && rev.sigmasOk("[1, 0.5, 0]"), "sigmasOk follows the Python rules");
// old workflow, control value counted in the saved list (it sits right after the seed)
let oldA = [...rHead, "randomize", "euler", "video/MiniMax_H3"];
check(rev.oldPrefixIndex(RN, oldA) === 20, "old workflow (control value saved after the seed): the prefix is found at the right place");
// old workflow, control value NOT in the list
let oldB = [...rHead, "euler", "My/Prefix_2"];
check(rev.oldPrefixIndex(RN, oldB) === 19, "old workflow without a saved control value: found too");
// the Upload button may add one more saved value at the end
check(rev.oldPrefixIndex(RN, [...oldA, null]) === 20, "a trailing button value does not confuse it");
// new workflow: untouched
check(rev.oldPrefixIndex(RN, [...rHead, "fixed", "euler", "0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000"]) === -1, "new layout (sigmas already there): left alone");
check(rev.oldPrefixIndex(RN, [...rHead, "fixed", "euler", "0.9, 0.5, 0.1, 0"]) === -1, "edited sigmas: left alone");
check(rev.oldPrefixIndex(RN, [...rHead, "euler"]) === -1 && rev.oldPrefixIndex(RN, null) === -1, "a short / missing list: nothing to do");
// the real hook
const rext = globalThis.__exts.find((e) => e.name === "IronLeo78.2in1Revitalizer");
const nodeType = { prototype: {} };
await rext.beforeRegisterNodeDef(nodeType, { name: "IronLeo78_2in1_Revitalizer" });
const mkRev = () => {
  const ws = RN.map((n) => ({ name: n, value: n === "sigmas" ? rev.DEFAULT_SIGMAS : null }));
  ws.push({ name: "control_after_generate", value: "randomize", serialize: false });
  const n = Object.create(nodeType.prototype);
  n.widgets = ws; n.setDirtyCanvas = () => {};
  return n;
};
let rn = mkRev();
let info = { widgets_values: oldA.slice() };
const keep = info.widgets_values;                             // the frontend's own reference
rn.onConfigure(info);
check(keep[20] === rev.DEFAULT_SIGMAS && keep.length === oldA.length, "an old workflow: the saved list is fixed IN PLACE (default sigmas), nothing else moved");
check(JSON.stringify(keep.slice(0, 20)) === JSON.stringify(oldA.slice(0, 20)), "all other saved values are untouched");
rn.widgets.find((w) => w.name === "sigmas").value = "video/MiniMax_H3";      // the frontend assigns the old text AFTER the hook
await new Promise((r) => setTimeout(r, 450));
check(rn.widgets.find((w) => w.name === "sigmas").value === rev.DEFAULT_SIGMAS, "the old text assigned after the hook is replaced by the default sigmas");
rn = mkRev();
const edited = [...rHead, "fixed", "euler", "1, 0.6, 0.2, 0"];
rn.onConfigure({ widgets_values: edited.slice() });
rn.widgets.find((w) => w.name === "sigmas").value = "1, 0.6, 0.2, 0";
await new Promise((r) => setTimeout(r, 450));
check(rn.widgets.find((w) => w.name === "sigmas").value === "1, 0.6, 0.2, 0", "edited sigmas survive a load unchanged");

console.log("14. v0.0.9: Model Loader \"Set New Defaults\" (saves the loader's values as the new defaults) and \"Factory\"");
const BUILTIN = { unet_name: "unet.safetensors", turbo_lora_name: "turbo.safetensors", LoRa_1_enabled: false, LoRa_1: "H3.safetensors", LoRa_1_strength: 0.65,
  LoRa_2_enabled: false, LoRa_2: "None", LoRa_2_strength: 0.65, LoRa_3_enabled: false, LoRa_3: "None", LoRa_3_strength: 0.65,
  qwen_vl_name: "qwen.safetensors", video_vae_name: "vv.safetensors", audio_vae_name: "av.safetensors", turbo_steps: 4, full_steps: 40, noise_seed: 1978 };
// --- Set New Defaults: what the widgets hold NOW is what gets saved (the user's own settings, e.g. steps 3)
const userW = Object.keys(BUILTIN).map((n) => ({ name: n, value: n === "turbo_steps" ? 3 : n === "unet_name" ? "mine.safetensors" : BUILTIN[n] }));
const sent = collectLoaderValues(userW);
check(sent.turbo_steps === 3 && sent.unet_name === "mine.safetensors" && Object.keys(sent).length === 17, "the values to save are the widgets' CURRENT values (steps 3 stays 3, nothing is reset)");
check(JSON.stringify(userW.map((w) => w.value)) === JSON.stringify(Object.keys(BUILTIN).map((n) => sent[n])), "collecting changes no widget");
let chk = verifySavedDefaults(sent, { ...sent });
check(chk.ok === 17 && chk.total === 17 && chk.bad.length === 0, "the backend answers with the same values: 17 of 17 read back");
let sm = savedMessage(chk, []);
check(sm.level === "ok" && sm.text.startsWith("✔ New defaults saved") && sm.text.includes("17 of 17") && sm.text.includes("MTV uses them"), "confirmation line: " + sm.text);
chk = verifySavedDefaults(sent, { ...sent, turbo_steps: 4 });
check(chk.bad.join() === "turbo_steps" && savedMessage(chk, []).level === "error", "the backend still holds steps 4: reported as an error, not as a success");
check(verifySavedDefaults(sent, null).bad.length === 17 && verifySavedDefaults(sent, { ...sent, noise_seed: undefined }).bad.includes("noise_seed"), "no answer / a missing value is an error");
check(verifySavedDefaults({ LoRa_1_strength: 0.65 }, { LoRa_1_strength: 0.6500000000001 }).bad.length === 0, "float compare tolerates rounding");
sm = savedMessage(verifySavedDefaults(sent, { ...sent }), ["unet_name (mine.safetensors)"]);
check(sm.level === "warn" && sm.text.includes("not installed") && sm.text.includes("mine.safetensors"), "saved, but a file is not installed: a warning names it");
// --- Factory: widgets back to the built-in values, read back
const mkW = (installed = {}) => Object.keys(BUILTIN).map((n) => {
  const combo = typeof BUILTIN[n] === "string";
  const list = installed[n] ?? (combo ? [BUILTIN[n], "other.safetensors", "None"] : null);
  return { name: n, value: combo ? "other.safetensors" : (typeof BUILTIN[n] === "boolean" ? true : 99), options: list ? { values: list } : {} };
});
let sw = mkW();
let ctl = { name: CONTROL_KEY, value: "randomize" };
let out = applyLoaderDefaults(sw, ctl, BUILTIN);
check(sw.every((w) => w.value === BUILTIN[w.name]) && ctl.value === "fixed", "Factory: every widget holds its built-in value afterwards, the seed control is 'fixed'");
check(out.message.level === "ok" && out.check.total === 18 && out.check.ok === 18 && out.message.text.startsWith("✔") && out.message.text.includes("18 of 18"), "Factory confirmation: 18 of 18 values verified");
sw = mkW({ unet_name: ["only_other.safetensors", "None"] });
ctl = { name: CONTROL_KEY, value: "randomize" };
out = applyLoaderDefaults(sw, ctl, BUILTIN);
check(sw.find((w) => w.name === "unet_name").value === "other.safetensors" && sw.find((w) => w.name === "turbo_steps").value === 4, "Factory: a missing default file is left as it was, everything else is set");
check(out.message.level === "warn" && out.message.text.includes("unet_name") && out.message.text.includes("unet.safetensors") && out.plan.missing.length === 1, "Factory: the warning names the file that is not installed");
sw = mkW({ LoRa_1: ["None", "x.safetensors"] });
out = applyLoaderDefaults(sw, { name: CONTROL_KEY, value: "fixed" }, BUILTIN);
check(sw.find((w) => w.name === "LoRa_1").value === "None" && out.message.level === "ok", "Factory: an optional LoRa file that is not installed becomes None, no warning");
sw = mkW();
Object.defineProperty(sw.find((w) => w.name === "full_steps"), "value", { get: () => 7, set: () => {} });
out = applyLoaderDefaults(sw, { name: CONTROL_KEY, value: "fixed" }, BUILTIN);
check(out.message.level === "error" && out.check.bad.includes("full_steps"), "Factory: a value that did not take is reported by the read-back");
sw = mkW();
const cbs = [];
sw.forEach((w) => { w.callback = (v) => cbs.push(w.name); });
applyLoaderDefaults(sw, null, BUILTIN);
check(cbs.length === 17, "Factory: each widget's callback is called (the frontend hears about the change)");
sw = mkW();
const untouched = JSON.stringify(sw.map((w) => w.value));
applyLoaderDefaults(sw, null, null);
check(JSON.stringify(sw.map((w) => w.value)) === untouched, "Factory: no defaults from the backend: nothing is changed");
// the real extension: no DOM here, so the panel is skipped, the node still loads and no saved value moves
const lext2 = globalThis.__exts.find((e) => e.name === "IronLeo78.ModelLoader.SeedFixed");
const n14 = { comfyClass: "IronLeo78_MTV_ModelLoader", id: 14, widgets: LN_PLAIN().map((n) => ({ name: n, value: null })), properties: {}, setDirtyCanvas() {} };
function LN_PLAIN() { return Object.keys(BUILTIN); }
await lext2.nodeCreated(n14);
check(n14.widgets.length === 17, "without a DOM the node is left as it is (no extra widget, nothing serialized changes)");

console.log("15. v0.0.9: the SAVED SET is loaded again on every create / open (loader and MTV hold the same values after a reload)");
// --- pure helpers
let c15 = verifySavedDefaults(sent, { ...sent }, "randomize", "randomize");
check(c15.total === 18 && c15.ok === 18 && c15.bad.length === 0, "the seed control is saved and read back with the values: 18 of 18");
c15 = verifySavedDefaults(sent, { ...sent }, "randomize", "fixed");
check(c15.bad.join() === CONTROL_KEY && savedMessage(c15, []).level === "error", "the backend holds another seed control: reported as an error");
check(verifySavedDefaults(sent, { ...sent }).total === 17, "no seed control sent: 17 values, as before");
check(savedMessage(verifySavedDefaults(sent, { ...sent }), []).text.includes("loads the same set again"), "the confirmation says the loader reloads the same set");
const bef = { ...BUILTIN, turbo_steps: 5, unet_name: "old.safetensors" };
const chg = changedBySet(bef, { ...BUILTIN, turbo_steps: 3, unet_name: "mine.safetensors" }, "randomize", "fixed");
check(chg.map((c) => c.name).join() === "unet_name,turbo_steps," + CONTROL_KEY && chg[1].from === 5 && chg[1].to === 3, "changedBySet lists what the workflow held and the set replaced (incl. the seed control)");
check(changedBySet(BUILTIN, { ...BUILTIN }, "fixed", "fixed").length === 0 && changedBySet(BUILTIN, { ...BUILTIN }, "fixed", null).length === 0, "same values (or no saved control): nothing replaced");
let sw15 = mkW();
let ctl15 = { name: CONTROL_KEY, value: "fixed" };
let r15 = applyLoaderDefaults(sw15, ctl15, BUILTIN, "increment");
check(ctl15.value === "increment" && r15.check.total === 18 && r15.check.bad.length === 0, "applying a saved set restores the saved seed control (increment)");
ctl15 = { name: CONTROL_KEY, value: "randomize" };
r15 = applyLoaderDefaults(mkW(), ctl15, BUILTIN, null);
check(ctl15.value === "randomize" && r15.check.total === 17, "a saved set without a seed control leaves the control alone");
let lm = loadedSetMessage(applyLoaderDefaults(mkW(), null, BUILTIN, null), []);
check(lm.level === "ok" && lm.text.startsWith("✔ Saved set loaded: 17 of 17"), "same values: a quiet confirmation: " + lm.text);
r15 = applyLoaderDefaults(mkW(), null, BUILTIN, null);
lm = loadedSetMessage(r15, [{ name: "turbo_steps", from: 5, to: 3 }]);
check(lm.level === "warn" && lm.text.includes("turbo_steps 5 → 3") && lm.text.includes("Set New Defaults"), "the workflow held other values: a warning names them: " + lm.text);
// --- the real hook: a workflow saved with steps 5 / seed control randomize is opened while the saved set says steps 3 / increment
const SET15 = { ...DEF, turbo_steps: 3, full_steps: 33, noise_seed: 4242, unet_name: "u0", LoRa_1_enabled: true, LoRa_1: "None" };
globalThis.__api = async (url) => ({ json: async () => (url.includes("loader_defaults") ? { ok: true, custom: true, defaults: SET15, factory: DEF, seed_control: "increment" } : { ok: true }) });
const mkL15 = () => {
  const ws = LN.map((n) => ({ name: n, value: DEF[n], options: typeof DEF[n] === "string" ? { values: [DEF[n], "None", "other"] } : {} }));
  ws.push({ name: CONTROL_KEY, value: "fixed", serialize: false });
  return { comfyClass: "IronLeo78_MTV_ModelLoader", id: 15, widgets: ws, properties: {}, setDirtyCanvas() {} };
};
const val15 = (n, name) => n.widgets.find((w) => w.name === name).value;
let n15 = mkL15();
await lext.nodeCreated(n15);
const wf15 = LN.map((n) => DEF[n]);
wf15[LN.indexOf("turbo_steps")] = 5;
wf15[LN.indexOf("noise_seed")] = 111;
n15.onConfigure({ widgets_values: [...wf15, "randomize"], properties: {} });
const sers15 = n15.widgets.filter((w) => w.serialize !== false);
sers15.forEach((w, i) => { w.value = wf15[i]; });                       // the frontend assigns the workflow's values
n15.widgets.find((w) => w.name === CONTROL_KEY).value = "randomize";
await new Promise((r) => setTimeout(r, 1000));                          // past the 0 / 400 ms re-apply and the 600 ms saved set
check(val15(n15, "turbo_steps") === 3 && val15(n15, "full_steps") === 33 && val15(n15, "noise_seed") === 4242 && val15(n15, "LoRa_1_enabled") === true,
  "opening a workflow: the saved set replaces the workflow's own values (steps 5 -> 3, seed 111 -> 4242, LoRa_1 ON)");
check(val15(n15, CONTROL_KEY) === "increment", "the seed's control after generate comes back as saved (increment)");
// a node created from the menu (no workflow) starts from the set even before a page refresh
n15 = mkL15();
n15.widgets.find((w) => w.name === "turbo_steps").value = 9;
await lext.nodeCreated(n15);
await new Promise((r) => setTimeout(r, 800));
check(val15(n15, "turbo_steps") === 3, "a new node gets the saved set too (no page refresh needed after Set New Defaults)");
// nothing saved: the workflow keeps its own values
globalThis.__api = async () => ({ json: async () => ({ ok: true, custom: false, defaults: DEF, factory: DEF, seed_control: null }) });
n15 = mkL15();
await lext.nodeCreated(n15);
n15.onConfigure({ widgets_values: [...wf15, "randomize"], properties: {} });
n15.widgets.filter((w) => w.serialize !== false).forEach((w, i) => { w.value = wf15[i]; });
n15.widgets.find((w) => w.name === CONTROL_KEY).value = "randomize";
await new Promise((r) => setTimeout(r, 1000));
check(val15(n15, "turbo_steps") === 5 && val15(n15, "noise_seed") === 111 && val15(n15, CONTROL_KEY) === "randomize", "NO saved set: the workflow keeps its own values (nothing is forced)");
// the backend does not answer: nothing breaks, nothing changes
globalThis.__api = async () => { throw new Error("offline"); };
n15 = mkL15();
await lext.nodeCreated(n15);
n15.onConfigure({ widgets_values: [...wf15, "randomize"], properties: {} });
n15.widgets.filter((w) => w.serialize !== false).forEach((w, i) => { w.value = wf15[i]; });
await new Promise((r) => setTimeout(r, 1000));
check(val15(n15, "turbo_steps") === 5, "no answer from the backend: the workflow's values stay, no error");
// a saved file that is not installed here: kept as it was, reported (no crash)
globalThis.__api = async () => ({ json: async () => ({ ok: true, custom: true, defaults: { ...SET15, unet_name: "gone.safetensors" }, factory: DEF, seed_control: null }) });
n15 = mkL15();
await lext.nodeCreated(n15);
await new Promise((r) => setTimeout(r, 800));
check(val15(n15, "unet_name") === "u0" && val15(n15, "turbo_steps") === 3, "a saved model file that is not installed keeps the current one, the other values still load");
globalThis.__api = null;

{
console.log("16. v0.0.9c: Revitalizer LoRa_1 .. LoRa_3 (appended after sigmas) and the Model Loader's saved set");
const LN = rev.LORA_NAMES;
check(LN.length === 9 && LN[0] === "LoRa_1_enabled" && LN[1] === "LoRa_1" && LN[2] === "LoRa_1_strength" && LN[8] === "LoRa_3_strength", "the nine widget names are the Model Loader's");
const RN2 = [...RN, ...LN];
const LDEF = [false, "None", 1.0, false, "None", 1.0, false, "None", 1.0];      // v0.1.11: 1.0 (0.65 until 0.1.10)
check(rev.LORA_STRENGTH === 1.0, "v0.1.11: a repaired LoRa_n strength is 1.0");
const sigmasNow = rev.DEFAULT_SIGMAS;
// a workflow saved with 0.0.9 / 0.0.9b: nothing after the sigmas (or only the Upload button's value)
const old9A = [...rHead, "randomize", "euler", sigmasNow];            // control word saved after the seed
const old9B = [...rHead, "euler", sigmasNow];                          // no control word
let rp = rev.loraRepairs(RN2, old9A);
check(rp.length === 9 && rp[0].index === 21 && rp[8].index === 29 && JSON.stringify(rp.map((r) => r.value)) === JSON.stringify(LDEF), "old workflow with the saved control word: nine repairs at positions 21..29, OFF / None / 1.0");
rp = rev.loraRepairs(RN2, old9B);
check(rp.length === 9 && rp[0].index === 20, "old workflow without the control word: positions 20..28");
rp = rev.loraRepairs(RN2, [...old9A, null]);
check(rp.length === 9 && rp[0].index === 21, "the Upload button's trailing null sits where LoRa_1_enabled now is: it is replaced, not mistaken for a value");
const good9 = [...old9A, true, "H3.safetensors", 0.5, false, "None", 0.65, true, "x.safetensors", -2];
check(rev.loraRepairs(RN2, good9).length === 0, "a workflow saved with 0.0.9c is left alone (ON, files and strengths kept)");
check(rev.loraRepairs(RN2, [...old9A, true, "H3.safetensors", 0.5]).map((r) => r.name).join() === LN.slice(3).join(), "only the missing slots are repaired, the filled ones stay");
check(rev.loraRepairs(RN2, [...old9A, "true", "H3.safetensors", "abc", false, "", 0.65, 1, "x", NaN]).map((r) => r.name).join() === ["LoRa_1_enabled", "LoRa_1_strength", "LoRa_2", "LoRa_3_enabled", "LoRa_3_strength"].join(),
      "values of the wrong type are repaired slot by slot (text for a switch, text / NaN for a strength, an empty file name)");
check(rev.loraRepairs(RN, old9A).length === 0 && rev.loraRepairs(RN2, null).length === 0 && rev.loraRepairs(null, old9A).length === 0, "a node without the widgets / a missing list: nothing to do");
const bef16 = rev.loraRepairs(RN2, old9A);
check(rev.loraRepairs(RN2, old9A.map((v, i) => v)).length === bef16.length, "repeating it gives the same answer (nothing is changed by looking)");

console.log("   the real hook: an old workflow must not start using a LoRA by itself");
const mkRev2 = (setValues) => {
  const ws = RN2.map((n) => ({ name: n, value: n === "sigmas" ? rev.DEFAULT_SIGMAS : (setValues && n in setValues ? setValues[n] : LN.includes(n) ? LDEF[LN.indexOf(n)] : null) }));
  ws.push({ name: "control_after_generate", value: "randomize", serialize: false });
  const n = Object.create(nodeType.prototype);
  n.widgets = ws; n.setDirtyCanvas = () => {};
  return n;
};
const SETV = { LoRa_1_enabled: true, LoRa_1: "H3.safetensors", LoRa_1_strength: 0.5 };       // what a new node's widgets hold when a set is saved
let r2 = mkRev2(SETV);
let info2 = { widgets_values: old9A.slice() };
const keep2 = info2.widgets_values;
r2.onConfigure(info2);
check(keep2.length === 30 && JSON.stringify(keep2.slice(21)) === JSON.stringify(LDEF) && JSON.stringify(keep2.slice(0, 21)) === JSON.stringify(old9A), "the saved list is completed IN PLACE with OFF / None / 1.0, the 21 old values are untouched");
check(r2.widgets.find((w) => w.name === "LoRa_1_enabled").value === false && r2.widgets.find((w) => w.name === "LoRa_1").value === "None", "the widgets are OFF / None at once (not the saved set's ON that a fresh node holds)");
r2.widgets.find((w) => w.name === "LoRa_1_enabled").value = true;      // the frontend leaves / assigns other values after the hook
await new Promise((r) => setTimeout(r, 450));
check(r2.widgets.find((w) => w.name === "LoRa_1_enabled").value === false, "still OFF after the 400 ms re-apply");
r2 = mkRev2(SETV);
const new9 = [...old9A, true, "H3.safetensors", 0.5, false, "None", 0.65, true, "x.safetensors", -2];
const keep3 = new9.slice();
r2.onConfigure({ widgets_values: keep3 });
r2.widgets.forEach((w, i) => { const at = RN2.indexOf(w.name); if (at >= 0) w.value = new9[at + (at > 17 ? 1 : 0)]; });      // assigned by the frontend
await new Promise((r) => setTimeout(r, 450));
check(JSON.stringify(keep3) === JSON.stringify(new9) && r2.widgets.find((w) => w.name === "LoRa_1_enabled").value === true && r2.widgets.find((w) => w.name === "LoRa_3_strength").value === -2, "a workflow saved with 0.0.9c loads unchanged (ON, files, strengths)");
const k4 = [...rHead, "randomize", "euler", "video/MiniMax_H3"];      // the oldest layout: prefix text where sigmas is, no LoRa values
r2 = mkRev2(SETV);
r2.onConfigure({ widgets_values: k4 });
check(k4[20] === rev.DEFAULT_SIGMAS && k4.length === 30 && k4[21] === false && k4[22] === "None", "the oldest layout (filename_prefix text where sigmas sits, no LoRa values): the sigmas fix of section 13 and the LoRa repair both run, in place");

console.log("   the saved set -> the widgets");
const mkSerial = () => [
  { name: "unet_name", value: "u0.safetensors", options: { values: ["u0.safetensors", "u1.safetensors"] } },
  { name: "vae_video", value: "v0", options: { values: ["v0", "v1"] } },
  { name: "vae_audio", value: "a0", options: { values: ["a0", "a1"] } },
  { name: "lora_on", value: false, options: {} },
  { name: "lora_name", value: "(none)", options: { values: ["(none)", "turbo.safetensors"] } },
  { name: "seed", value: 0, options: {} },
  ...[1, 2, 3].flatMap((n) => [
    { name: `LoRa_${n}_enabled`, value: false, options: {} },
    { name: `LoRa_${n}`, value: "None", options: { values: ["None", "H3.safetensors", "two.safetensors"] } },
    { name: `LoRa_${n}_strength`, value: 0.65, options: {} }]),
];
const MAPPED = { unet_name: "u1.safetensors", lora_name: "turbo.safetensors", vae_video: "v1", vae_audio: "a1", seed: 4242,
  LoRa_1_enabled: true, LoRa_1: "H3.safetensors", LoRa_1_strength: 0.5, LoRa_2_enabled: true, LoRa_2: "gone.safetensors", LoRa_2_strength: 1.25,
  LoRa_3_enabled: false, LoRa_3: "None", LoRa_3_strength: 0.65 };
let ser = mkSerial();
const before16 = Object.fromEntries(ser.map((w) => [w.name, w.value]));
let ctl16 = { name: "control_after_generate", value: "fixed" };
let ap = rev.applyRevitalizerSet(ser, ctl16, MAPPED, "increment");
const nowV = (n) => ser.find((w) => w.name === n).value;
check(nowV("unet_name") === "u1.safetensors" && nowV("lora_name") === "turbo.safetensors" && nowV("vae_video") === "v1" && nowV("seed") === 4242 && nowV("LoRa_1_enabled") === true && nowV("LoRa_1_strength") === 0.5 && ctl16.value === "increment",
      "models, Turbo LoRA file, VAEs, LoRa_1 and the seed with its control are set");
check(nowV("LoRa_2") === "None" && nowV("LoRa_2_enabled") === false && ap.plan.missing.length === 1 && ap.plan.missing[0].name === "LoRa_2" && nowV("LoRa_2_strength") === 1.25,
      "a LoRa file that is not installed: None and OFF (never ON with no file), its strength is kept, and it is reported");
check(ap.check.bad.length === 0 && ap.check.ok === 15 && ap.check.total === 15, "read back: every value that was set took (14 widgets + the seed control = 15 of 15)");
check(nowV("lora_on") === false, "the LoRA ON / OFF switch is not touched by the set");
const ch16 = rev.changedValues(before16, ap.plan.set, "fixed", "increment");
check(ch16.some((c) => c.name === "seed" && c.from === 0 && c.to === 4242) && ch16.some((c) => c.name === "control_after_generate") && !ch16.some((c) => c.name === "lora_on"), "changedValues lists what the node held and the set replaced (incl. the seed control)");
let m16 = rev.setMessage(ap, ch16, "button");
check(m16.level === "warn" && m16.text.includes("Replaced:") && m16.text.includes("LoRa_2 (gone.safetensors) kept as None, OFF"), "a missing LoRa file makes it a warning that names the file");
ser = mkSerial();
ap = rev.applyRevitalizerSet(ser, { name: "control_after_generate", value: "fixed" }, { ...MAPPED, LoRa_2_enabled: false, LoRa_2: "two.safetensors" }, "increment");
m16 = rev.setMessage(ap, rev.changedValues(before16, ap.plan.set), "sent");
check(m16.level === "ok" && m16.text.startsWith("✔ Sent by the Model Loader's Set New Defaults.") && ap.plan.missing.length === 0, "everything installed: a green line, and it says the Model Loader sent it");
ser = mkSerial();
rev.applyRevitalizerSet(ser, null, { unet_name: "not-installed.safetensors", seed: 7 }, null);
check(ser[0].value === "u0.safetensors" && ser.find((w) => w.name === "seed").value === 7, "a model file that is not installed keeps the current one, the other values still load");
ser = mkSerial();
const c2 = { name: "control_after_generate", value: "randomize" };
rev.applyRevitalizerSet(ser, c2, { unet_name: "u1.safetensors" }, "increment");
check(c2.value === "randomize", "the seed control only changes together with the seed");
ser = mkSerial();
ser[0].callback = () => { throw new Error("cosmetic"); };
check(rev.applyRevitalizerSet(ser, null, { unet_name: "u1.safetensors" }, null).check.bad.length === 0, "a failing widget callback does not stop the load");
ap = { plan: { set: { seed: 1 }, missing: [] }, check: { total: 1, ok: 0, bad: ["seed"] } };
check(rev.setMessage(ap, [], "button").level === "error", "a value that did not take: red line");

console.log("   the node: button / event / no saved set");
const mkNode16 = () => {
  const n = { comfyClass: "IronLeo78_2in1_Revitalizer", widgets: mkSerial().concat([{ name: "control_after_generate", value: "fixed", serialize: false }]), setDirtyCanvas() {} };
  return n;
};
let n16 = mkNode16();
await rext.nodeCreated(n16);
check(typeof n16.ironleo78UseSet === "function", "the node gets its loader function (no DOM here: the panel is skipped, nothing breaks)");
globalThis.__api = async (url) => ({ json: async () => (url === rev.SET_ROUTE ? { ok: true, custom: true, values: MAPPED, seed_control: "increment" } : {}) });
await n16.ironleo78UseSet("button");
const w16 = (n) => n16.widgets.find((w) => w.name === n).value;
check(w16("unet_name") === "u1.safetensors" && w16("LoRa_1_enabled") === true && w16("seed") === 4242 && w16("control_after_generate") === "increment", "the button loads the saved set through the real route name");
n16 = mkNode16();
await rext.nodeCreated(n16);
globalThis.__api = async () => ({ json: async () => ({ ok: true, custom: false, values: {}, seed_control: null }) });
await n16.ironleo78UseSet("button");
check(n16.widgets.find((w) => w.name === "unet_name").value === "u0.safetensors" && n16.widgets.find((w) => w.name === "seed").value === 0, "no saved set: nothing is changed");
globalThis.__api = async () => { throw new Error("offline"); };
await n16.ironleo78UseSet("button");
check(n16.widgets.find((w) => w.name === "seed").value === 0, "no answer from the backend: nothing is changed, no crash");
globalThis.__api = null;
// the Model Loader's event
const listeners = {};
const fakeWin = { addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); } };
const hits = [];
const nodesA = [{ comfyClass: "IronLeo78_2in1_Revitalizer", ironleo78UseSet: (o) => hits.push("rev1:" + o) }, { comfyClass: "IronLeo78_MTV_ModelLoader" },
                { comfyClass: "IronLeo78_2in1_Revitalizer", ironleo78UseSet: (o) => hits.push("rev2:" + o) }, { comfyClass: "IronLeo78_2in1_Revitalizer" }];
check(rev.listenForSavedSet(fakeWin, () => nodesA) === true && rev.listenForSavedSet(null, () => []) === false, "the listener is installed on a window, and refused without one");
listeners[rev.SET_EVENT].forEach((fn) => fn());
check(hits.join() === "rev1:sent,rev2:sent", "Set New Defaults on a Model Loader reaches every Revitalizer of the workflow (and nothing else)");
check(rev.SET_EVENT === "ironleo78-set-saved" && fs.readFileSync(path.join(here, "..", "web", "ironleo78_mtv.js"), "utf8").includes('"ironleo78-set-saved"'), "the Model Loader fires the same event name");
}

console.log("18. v0.0.9H: an old MTV workflow (22 values, pickers + More References) through the REAL hook of the node");
{
  // a tiny fake DOM so the real nodeCreated of the MTV node can run in plain node (the jsdom test is the fuller one)
  const mkEl = () => {
    const store = { style: { cssText: "" }, children: [], textContent: "", value: "", dataset: {} };
    const noop = () => {};
    return new Proxy(store, {
      get: (t, k) => (k in t ? t[k] : (["appendChild", "append", "addEventListener", "removeEventListener", "setAttribute", "removeAttribute", "remove", "focus", "click", "querySelector"].includes(k) ? noop : undefined)),
      set: (t, k, v) => { t[k] = v; return true; },
    });
  };
  globalThis.document = { createElement: () => mkEl(), body: mkEl() };
  globalThis.window = { addEventListener() {}, removeEventListener() {} };
  const mext = globalThis.__exts.find((e) => e.name === "IronLeo78.MTV.Panel");
  check(!!mext && !globalThis.__exts.some((e) => e.name === "IronLeo78.MTV.Thumbnails"), "the node extension is registered (as 'IronLeo78.MTV.Panel'; the old 'Thumbnails' name is gone)");
  const values = [true, false, "v.mp4", "Song.wav", "Vocals", 0.35, 8, true, "my prompt", "Custom Audio", true, false];   // the 12 real values, all different
  const mkMtv = (savedHeight) => {
    const ws = NEW.map((n) => ({ name: n, value: null }));
    const node = { comfyClass: "IronLeo78_MTV", id: 21, widgets: ws, size: [420, savedHeight], properties: {}, sizes: [],
      addDOMWidget(name, type, el, opts) { const w = { name, type, element: el, serialize: opts.serialize }; ws.push(w); return w; },
      computeSize: () => [420, 520], setSize(sz) { node.size = sz.slice(); node.sizes.push(sz.slice()); }, setDirtyCanvas() {} };
    return node;
  };
  const named = (node) => Object.fromEntries(node.widgets.filter((w) => w.serialize !== false).map((w) => [w.name, w.value]));
  const want = Object.fromEntries(NEW.map((n, i) => [n, values[i]]));
  // what the real frontend does after the extension's onConfigure: widget i takes the saved value i (extra saved values are ignored)
  const frontendAssign = (node, info) => node.widgets.filter((w) => w.serialize !== false).forEach((w, i) => { if (i < info.widgets_values.length) w.value = info.widgets_values[i]; });
  // (a) a workflow saved with v0.0.8: 12 values + More References OFF + nine picker values (22 in all)
  const v22 = [...values, false, "a.png", "None", "c.png", "None", "e.png", "None", "None", "None", "i.png"];
  let node = mkMtv(900);
  await mext.nodeCreated(node);
  const info = { widgets_values: v22.slice(), size: [420, 900] };
  const keepRef = info.widgets_values;                      // the frontend keeps its own reference to the array
  node.onConfigure(info);
  frontendAssign(node, { widgets_values: keepRef });
  check(same(named(node), want), "old 22-value workflow: every one of the 12 widgets holds its own value by name: " + JSON.stringify(named(node)));
  check(same(keepRef, values), "the saved array is cut IN PLACE to the 12 real values (a frontend holding the reference sees it too)");
  { const inf = { widgets_values: values.slice() }; node.onConfigure(inf); frontendAssign(node, inf); }
  check(same(named(node), want), "loading the NEW layout again changes nothing");
  // saving then loading again and again is stable
  let cur = v22.slice();
  for (let i = 0; i < 3; i++) { const inf = { widgets_values: cur }; node.onConfigure(inf); cur = Object.values(named(node)); }
  check(same(cur, values), "load + save repeated: still the same 12 values");
  await new Promise((r) => setTimeout(r, 180));
  check(node.sizes.length >= 1 && node.size[1] === 520, "the old tall saved height (900) is fitted once to the node's own height (520): " + JSON.stringify(node.sizes));
  // (b) a workflow already in the new layout keeps its (possibly user-resized) height
  node = mkMtv(900);
  await mext.nodeCreated(node);
  { const inf = { widgets_values: values.slice(), size: [420, 900] }; node.onConfigure(inf); frontendAssign(node, inf); }
  await new Promise((r) => setTimeout(r, 180));
  check(same(named(node), want) && node.size[1] === 900, "a new-layout workflow keeps its saved height (900): " + JSON.stringify(node.sizes) + " " + JSON.stringify(named(node)));
  // (c) a 0.0.7 workflow: 15 values
  node = mkMtv(800);
  await mext.nodeCreated(node);
  { const inf = { widgets_values: [...values, "a.png", "None", "None"], size: [420, 800] }; node.onConfigure(inf); frontendAssign(node, inf); }
  check(same(named(node), want), "a 0.0.7 workflow (Guide + picture_1..3) loads onto the same 12 values");
  // the removed widgets are not on a new node, and only the segment panel is added
  const names = node.widgets.map((w) => w.name);
  check(names.join(",") === NEW.join(",") + ",segments_view", "a new node has exactly the 12 widgets + the segment panel (no picture pickers, no switch, no thumbnails): " + names.join(","));
  check(node.widgets.find((w) => w.name === "segments_view").serialize === false, "the segment panel is still not serialized");
  node.onRemoved?.();
  delete globalThis.document;
  delete globalThis.window;
}

console.log("19. v0.0.9s: Video_1 and its Free video button are gone");
{
  const src = fs.readFileSync(path.join(here, "..", "web", "ironleo78_mtv.js"), "utf8");
  check(!/Video_1|release_video|held_bytes|fmtBytes|freeVideo|Free video/.test(src), "no Video_1 / Free video / held-video code is left in the panel script");
  check(!/easter|eggFeed|EGG_/i.test(src), "no easter egg code is left");
}

console.log("20. v0.0.9t: the MAKER keeps a named copy of its values too (`properties.ironleo78_values`), like the Model Loader");
{
  // pure helpers
  check(makerTypeOk("megapixels", 0.3) && !makerTypeOk("megapixels", "0.3") && !makerTypeOk("duration", NaN) && makerTypeOk("Turbo", false) && !makerTypeOk("Turbo", "true")
    && makerTypeOk("prompt", "") && !makerTypeOk("prompt", 5) && makerTypeOk("some_new_widget", 1) && !makerTypeOk("some_new_widget", null), "makerTypeOk: each widget keeps its own type; an unknown widget takes any plain value");
  const MD = { Turbo: true, "Use Video": false, "Video File": "None", "Custom Audio File": "None", "Audio Stem": "Full", megapixels: 0.2, duration: 5, "Next Segment On Run": false, prompt: "",
    "Choose Audio latent": "Custom Audio", "Save Latent": false, Guide: false };
  const MV = [true, false, "v.mp4", "Song.wav", "Vocals", 0.35, 8, true, "my prompt", "Custom Audio", true, true];       // 12 values, all different from MD
  const mshadow = Object.fromEntries(NEW.map((n, i) => [n, MV[i]])); mshadow[LAYOUT_KEY] = NEW.join("|");
  const MOPT = { typeOk: makerTypeOk, control: false };
  check(restoreFromShadow(NEW, mshadow, MD, MOPT) === null, "same widget order as at save time: nothing to restore (positional values are used, a hand edit stays)");
  // a later update moves widgets and adds one in the middle
  const FUT = ["Guide", "Turbo", "Use Video", "Video File", "Custom Audio File", "Audio Stem", "new_flag", "megapixels", "duration", "Next Segment On Run", "prompt", "Choose Audio latent", "Save Latent"];
  const r = restoreFromShadow(FUT, mshadow, { ...MD, new_flag: true }, MOPT);
  const rn = r && Object.fromEntries(FUT.map((n, i) => [n, r[i]]));
  check(r && r.length === FUT.length && same(NEW.map((n) => rn[n]), MV) && rn.new_flag === true, "widgets moved + one added: every old value lands on its own widget by name, the new one gets its default, NO trailing control value");
  const dm = restoreFromShadow(NEW, { ...mshadow, megapixels: "0.35", [LAYOUT_KEY]: "other" }, MD, MOPT);
  check(dm && dm[NEW.indexOf("megapixels")] === 0.2 && dm[NEW.indexOf("prompt")] === "my prompt", "a value of the wrong type in the copy falls back to the widget's default");
  check(restoreFromShadow(FUT, mshadow, { ...MD }, MOPT) === null, "a new widget with no default: the copy is not used (the positional route stays in charge)");
  check(restoreFromShadow(NEW, null, MD, MOPT) === null && restoreFromShadow(NEW, [], MD, MOPT) === null && restoreFromShadow(NEW, { other: 1 }, MD, MOPT) === null, "no / unusable copy: null");
  check(same(buildShadow(NEW.map((n, i) => ({ name: n, value: MV[i] }))), mshadow), "buildShadow: {name: value} for every serialized widget + __layout, nothing else");

  // the REAL hooks of the node (fake DOM as in section 18)
  const mkEl = () => {
    const store = { style: { cssText: "" }, children: [], textContent: "", value: "", dataset: {} };
    const noop = () => {};
    return new Proxy(store, { get: (t, k) => (k in t ? t[k] : (["appendChild", "append", "addEventListener", "removeEventListener", "setAttribute", "removeAttribute", "remove", "focus", "click", "querySelector"].includes(k) ? noop : undefined)), set: (t, k, v) => { t[k] = v; return true; } });
  };
  globalThis.document = { createElement: () => mkEl(), body: mkEl() };
  globalThis.window = { addEventListener() {}, removeEventListener() {} };
  const mext = globalThis.__exts.find((e) => e.name === "IronLeo78.MTV.Panel");
  const mk = (names) => {
    const ws = names.map((n) => ({ name: n, value: n in MD ? MD[n] : (n === "new_flag" ? true : null) }));
    const node = { comfyClass: "IronLeo78_MTV", id: 31, widgets: ws, size: [420, 520], properties: {}, sizes: [],
      addDOMWidget(name, type, el, opts) { const w = { name, type, element: el, serialize: opts.serialize }; ws.push(w); return w; },
      computeSize: () => [420, 520], setSize(sz) { node.size = sz.slice(); }, setDirtyCanvas() {} };
    return node;
  };
  const named = (node) => Object.fromEntries(node.widgets.filter((w) => w.serialize !== false).map((w) => [w.name, w.value]));
  const frontendAssign = (node, info) => node.widgets.filter((w) => w.serialize !== false).forEach((w, i) => { if (i < info.widgets_values.length) w.value = info.widgets_values[i]; });
  const saveOf = (node) => { const o = { widgets_values: node.widgets.filter((w) => w.serialize !== false).map((w) => w.value), properties: { ...node.properties } }; node.onSerialize(o); return o; };

  // (a) every save writes the copy
  let node = mk(NEW);
  await mext.nodeCreated(node);
  { const inf = { widgets_values: MV.slice() }; node.onConfigure(inf); frontendAssign(node, inf); }
  const out1 = saveOf(node);
  const cp = out1.properties[SHADOW_KEY];
  check(cp && same(NEW.map((n) => cp[n]), MV) && cp[LAYOUT_KEY] === NEW.join("|") && Object.keys(cp).length === NEW.length + 1, "a save writes the copy: the 12 values by name + __layout, and not the segment panel: " + JSON.stringify(Object.keys(cp || {})));
  check(node.properties[SHADOW_KEY] === cp, "the copy is also kept on the node's own properties");
  // (b) same layout: positional route, a hand edit in widgets_values stays
  node = mk(NEW);
  await mext.nodeCreated(node);
  { const pw = node.widgets.find((w) => w.name === "prompt"); check(pw && pw.label === "MTV_Prompt" && pw.name === "prompt", "v0.3.9: the prompt box is labelled MTV_Prompt, its name stays prompt (nothing saved or wired changes)"); }
  { const edited = MV.slice(); edited[5] = 0.7; const inf = { widgets_values: edited, properties: { [SHADOW_KEY]: cp } }; node.onConfigure(inf); frontendAssign(node, inf); }
  check(named(node).megapixels === 0.7 && named(node).prompt === "my prompt", "same widget order: the positional values are used (a value edited by hand in the workflow file stays)");
  // (c) a later update moved the widgets: what the positional route would do (shift), and what the copy does
  node = mk(FUT);
  await mext.nodeCreated(node);
  const keepRef = MV.slice();
  { const inf = { widgets_values: keepRef, properties: { [SHADOW_KEY]: cp } }; node.onConfigure(inf); frontendAssign(node, { widgets_values: keepRef }); }
  const got = named(node);
  check(same(NEW.map((n) => got[n]), MV) && got.new_flag === true, "saved by this release, loaded after widgets moved: every value by name, the new widget at its default: " + JSON.stringify(got));
  check(keepRef.length === FUT.length && same(FUT.map((n) => got[n]), keepRef), "the saved array is rewritten IN PLACE (a frontend holding the reference sees the corrected values)");
  { const shifted = Object.fromEntries(FUT.map((n, i) => [n, MV[i]])); check(shifted.Turbo === false && got.Turbo === true && shifted.Guide === true && shifted["Audio Stem"] === 0.35 && got["Audio Stem"] === "Vocals", "(control) the same file read by POSITION would have shifted values: Turbo would read false (is true), Audio Stem would read 0.35 (is Vocals)"); }
  // (d) load + save + load again on the future layout is stable
  { const o2 = saveOf(node); const n2 = mk(FUT); await mext.nodeCreated(n2); const inf = { widgets_values: o2.widgets_values.slice(), properties: o2.properties }; n2.onConfigure(inf); frontendAssign(n2, inf);
    check(same(named(n2), got) && o2.properties[SHADOW_KEY][LAYOUT_KEY] === FUT.join("|"), "load + save + load on the new layout: stable, and the copy now carries the new order"); }
  // (e) a workflow saved BEFORE this release (no copy): the old migrations still run, same result as section 18
  node = mk(NEW);
  await mext.nodeCreated(node);
  { const v22 = [...MV, false, "a.png", "None", "c.png", "None", "e.png", "None", "None", "None", "i.png"]; const inf = { widgets_values: v22, properties: {} }; node.onConfigure(inf); frontendAssign(node, inf); }
  check(same(NEW.map((n) => named(node)[n]), MV), "a workflow without the copy (22 old values): the position-based migrations still cut and map it");
  // (f) a damaged copy never breaks the load: bad type -> default, junk shadow -> positional route
  node = mk(FUT);
  await mext.nodeCreated(node);
  { const inf = { widgets_values: MV.slice(), properties: { [SHADOW_KEY]: { ...cp, duration: "x" } } }; node.onConfigure(inf); frontendAssign(node, inf); }
  check(named(node).duration === 5 && named(node).megapixels === 0.35, "a damaged value in the copy: that widget takes its default, the others keep theirs");
  node = mk(NEW);
  await mext.nodeCreated(node);
  { const inf = { widgets_values: MV.slice(), properties: { [SHADOW_KEY]: "garbage" } }; node.onConfigure(inf); frontendAssign(node, inf); }
  check(same(NEW.map((n) => named(node)[n]), MV), "an unusable copy is ignored: the positional values load as before");
  node.onRemoved?.();
  delete globalThis.document;
  delete globalThis.window;
}

console.log("22. v0.1.11: \"Choose Audio latent\" MOVED right under \"Video File\" (position 9 -> 3)");
{
  const ext22 = await import(pathToFileURL(path.join(tmp, "ext", "web", "ext.mjs")).href);
  const { legacyMakerNames, isLegacyMakerOrder, moveAudioLatentUp, migrateMakerPositional, AUDIO_MODES } = ext22;
  const NEW11 = ["Turbo", "Use Video", "Video File", "Choose Audio latent", "Custom Audio File", "Audio Stem", "megapixels", "duration",
    "Next Segment On Run", "prompt", "Save Latent", "Guide"];
  check(same(legacyMakerNames(NEW11), NEW) && legacyMakerNames(NEW) && same(legacyMakerNames(["a", "b"]), null), "legacyMakerNames: the 0.1.10 order is the new one with the audio widget back after prompt");
  check(same(AUDIO_MODES, ["MiniMax Audio", "Audio From Video", "Custom Audio"]), "the three audio modes (same as AUDIO_MODES in mtv.py)");
  // the values by NAME, the only fair comparison (hard rule)
  const V = { Turbo: true, "Use Video": false, "Video File": "v.mp4", "Custom Audio File": "Song.wav", "Audio Stem": "Vocals", megapixels: 0.35, duration: 8,
    "Next Segment On Run": true, prompt: "my prompt", "Choose Audio latent": "Audio From Video", "Save Latent": true, Guide: false };
  const inOld = NEW.map((n) => V[n]), inNew = NEW11.map((n) => V[n]);
  const asNamed = (names, vals) => Object.fromEntries(names.map((n, i) => [n, vals?.[i]]));
  const sameNamed = (a, b) => Object.keys(a).length === Object.keys(b).length && Object.keys(a).every((k) => a[k] === b[k]);      // key order does not count
  check(isLegacyMakerOrder(NEW11, inOld) && !isLegacyMakerOrder(NEW11, inNew) && !isLegacyMakerOrder(NEW, inOld), "the old order is recognised by WHAT the values are; the new order and an old node are not");
  check(same(moveAudioLatentUp(NEW, NEW11, inOld), inNew), "moveAudioLatentUp: the 12 values in the new order");
  const r1 = migrateMakerPositional(NEW11, [...inOld, "image"]);
  check(r1 && same(r1.vals, inNew) && r1.dropped === true, "a 0.1.10 workflow without a copy (12 values + the upload button's 'image'): cut and moved");
  check(sameNamed(asNamed(NEW11, r1.vals), V), "...every one of the 12 values identical BY NAME before and after");
  check(migrateMakerPositional(NEW11, inNew) === null && migrateMakerPositional(NEW11, [...inNew]) === null, "a 0.1.11 workflow is left alone (idempotent)");
  let loop22 = [...inOld, "image"];
  for (let i = 0; i < 4; i++) { const r = migrateMakerPositional(NEW11, loop22); if (r) loop22 = r.vals; }
  check(same(loop22, inNew), "load + save x4: the same values every time");
  const edge = NEW11.map((n) => (n === "prompt" ? "Custom Audio" : V[n]));
  check(migrateMakerPositional(NEW11, edge) === null, "a new-order workflow whose prompt is literally 'Custom Audio' is not mistaken for the old order");
  // older formats go through their own migrations against the OLD order first, then the move
  const v22old = [...inOld, false, "a.png", "None", "c.png", "None", "e.png", "None", "None", "None", "i.png"];
  check(same(migrateMakerPositional(NEW11, v22old)?.vals, inNew), "a 0.0.8 workflow (22 values): picker values cut, then moved");
  const v05 = [...inOld.slice(0, 10), false, true, 0.4, "HIGH", false, "Upscaled only", ...pics];         // 0.5: Latent Upscale OFF (= Save Latent ON), Guide OFF
  check(sameNamed(asNamed(NEW11, migrateMakerPositional(NEW11, v05)?.vals), { ...V, "Save Latent": true, Guide: false }), "a 0.5 workflow (upscale block): Latent Upscale OFF -> Save Latent ON, then moved");
  const vBool = inOld.map((v, i) => (i === 9 ? true : v));
  check(asNamed(NEW11, migrateMakerPositional(NEW11, vBool)?.vals)["Choose Audio latent"] === "Custom Audio", "a workflow from before 0.0.3 (ON/OFF switch): Custom Audio, at its new place");
  const vSong = inOld.map((v, i) => (i === 4 ? "Song" : v));
  check(sameNamed(asNamed(NEW11, migrateMakerPositional(NEW11, vSong)?.vals), { ...V, "Audio Stem": "Full" }), "an Audio Stem 'Song' (0.0.6): Full, and moved");
  check(migrateMakerPositional(NEW11, undefined) === null && migrateMakerPositional(NEW11, [1, 2]) === null, "missing / odd values are left alone");

  // the REAL hook of the node, with the 0.1.11 widget order
  const mkEl = () => {
    const store = { style: { cssText: "" }, children: [], textContent: "", value: "", dataset: {} };
    const noop = () => {};
    return new Proxy(store, { get: (t, k) => (k in t ? t[k] : (["appendChild", "append", "addEventListener", "removeEventListener", "setAttribute", "removeAttribute", "remove", "focus", "click", "querySelector"].includes(k) ? noop : undefined)), set: (t, k, v) => { t[k] = v; return true; } });
  };
  globalThis.document = { createElement: () => mkEl(), body: mkEl() };
  globalThis.window = { addEventListener() {}, removeEventListener() {} };
  const mext = globalThis.__exts.find((e) => e.name === "IronLeo78.MTV.Panel");
  const FRESH = { Turbo: true, "Use Video": false, "Video File": "None", "Choose Audio latent": "Custom Audio", "Custom Audio File": "None", "Audio Stem": "Full", megapixels: 0.2,
    duration: 5, "Next Segment On Run": false, prompt: "", "Save Latent": true, Guide: true };
  const mk = (h = 520) => {
    const ws = NEW11.map((n) => ({ name: n, value: FRESH[n] }));
    const node = { comfyClass: "IronLeo78_MTV", id: 41, widgets: ws, size: [420, h], properties: {}, sizes: [],
      addDOMWidget(name, type, el, opts) { const w = { name, type, element: el, serialize: opts.serialize }; ws.push(w); return w; },
      computeSize: () => [420, 520], setSize(sz) { node.size = sz.slice(); node.sizes.push(sz.slice()); }, setDirtyCanvas() {} };
    return node;
  };
  const named = (node) => Object.fromEntries(node.widgets.filter((w) => w.serialize !== false).map((w) => [w.name, w.value]));
  const frontendAssign = (node, info) => node.widgets.filter((w) => w.serialize !== false).forEach((w, i) => { if (i < info.widgets_values.length) w.value = info.widgets_values[i]; });
  const load = async (info, h) => { const node = mk(h); await mext.nodeCreated(node); const keep = info.widgets_values; node.onConfigure(info); frontendAssign(node, { widgets_values: keep }); return { node, keep }; };
  // (a) the user's own file (new defaults values 20261030-1007pm.json): saved by 0.1.10 WITH the named copy
  const userVals = [true, false, "None", "None", "Full", 0.2, 5, false, "", "Custom Audio", true, true, "image"];
  const userCopy = { Turbo: true, "Use Video": false, "Video File": "None", "Custom Audio File": "None", "Audio Stem": "Full", megapixels: 0.2, duration: 5, "Next Segment On Run": false,
    prompt: "", "Choose Audio latent": "Custom Audio", "Save Latent": true, Guide: true, [LAYOUT_KEY]: NEW.join("|") };
  let { node, keep } = await load({ widgets_values: userVals.slice(), properties: { [SHADOW_KEY]: userCopy } });
  const want = { ...userCopy }; delete want[LAYOUT_KEY];
  check(same(named(node), Object.fromEntries(NEW11.map((n) => [n, want[n]]))) && same(keep, NEW11.map((n) => want[n])),
    "the user's 0.1.10 workflow (with its copy): every value by name, the saved array rewritten in the new order: " + JSON.stringify(named(node)));
  // (b) a 0.1.10 workflow with a copy and values that are all different
  ({ node, keep } = await load({ widgets_values: [...inOld, "image"], properties: { [SHADOW_KEY]: { ...asNamed(NEW, inOld), [LAYOUT_KEY]: NEW.join("|") } } }));
  check(same(named(node), Object.fromEntries(NEW11.map((n) => [n, V[n]]))), "a 0.1.10 workflow with a copy: all 12 different values on their own widgets");
  // (c) the same without a copy (positional route)
  ({ node, keep } = await load({ widgets_values: [...inOld, "image"], properties: {} }));
  check(same(named(node), Object.fromEntries(NEW11.map((n) => [n, V[n]]))) && same(keep, inNew), "a 0.1.10 workflow WITHOUT a copy: moved by the positional route, saved array fixed in place");
  // (d) a 0.0.8 workflow (22 values, no copy): cut + moved, the tall height fitted once
  ({ node, keep } = await load({ widgets_values: v22old.slice(), size: [420, 900], properties: {} }, 900));
  await new Promise((r) => setTimeout(r, 180));
  check(same(named(node), Object.fromEntries(NEW11.map((n) => [n, V[n]]))) && node.size[1] === 520, "a 0.0.8 workflow: 12 values by name at the new places, old height fitted once: " + JSON.stringify(node.sizes));
  // (e) a 0.1.11 workflow: stable through load + save x3, and the copy carries the new order
  ({ node } = await load({ widgets_values: inNew.slice(), properties: {} }));
  let cur = inNew.slice(), props = {};
  for (let i = 0; i < 3; i++) {
    const o = { widgets_values: Object.values(named(node)), properties: {} };
    node.onSerialize(o);
    cur = o.widgets_values; props = o.properties;
    ({ node } = await load({ widgets_values: cur.slice(), properties: props }));
  }
  check(same(Object.values(named(node)), inNew) && props[SHADOW_KEY][LAYOUT_KEY] === NEW11.join("|"), "a 0.1.11 workflow: load + save x3 never changes a value; the copy holds the new order");
  node.onRemoved?.();
  delete globalThis.document;
  delete globalThis.window;
}

console.log("23. v0.1.11: the Model Loader's REAL hook with turbo_lora_strength");
{
  const NL11 = ["unet_name", "turbo_lora_name", "turbo_lora_strength", "LoRa_1_enabled", "LoRa_1", "LoRa_1_strength", "LoRa_2_enabled", "LoRa_2", "LoRa_2_strength",
    "LoRa_3_enabled", "LoRa_3", "LoRa_3_strength", "qwen_vl_name", "video_vae_name", "audio_vae_name", "turbo_steps", "full_steps", "noise_seed"];
  const NL10 = NL11.filter((n) => n !== "turbo_lora_strength");
  const D11 = { unet_name: "u0", turbo_lora_name: "t0", turbo_lora_strength: 1.0, LoRa_1_enabled: false, LoRa_1: "None", LoRa_1_strength: 1, LoRa_2_enabled: false, LoRa_2: "None",
    LoRa_2_strength: 1, LoRa_3_enabled: false, LoRa_3: "None", LoRa_3_strength: 1, qwen_vl_name: "q0", video_vae_name: "v0", audio_vae_name: "a0", turbo_steps: 6, full_steps: 30, noise_seed: 1978 };
  const lext = globalThis.__exts.find((e) => e.name === "IronLeo78.ModelLoader.SeedFixed");
  const mkL = () => {
    const ws = NL11.map((n) => ({ name: n, value: D11[n] }));
    ws.push({ name: CONTROL_KEY, value: "fixed", serialize: false });
    return { comfyClass: "IronLeo78_MTV_ModelLoader", id: 5, widgets: ws, properties: {}, setDirtyCanvas() {} };
  };
  const vals = (node) => Object.fromEntries(node.widgets.map((w) => [w.name, w.value]));
  // the user's 0.1.10 Model Loader (from the json), loaded by the frontend after the hook
  const user = ["minimax_h3_ref2va_pruned_int8_convrot.safetensors", "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors", false, "None", 1, false, "None", 1, false, "None", 1,
    "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "minimax_h3_video_vae_int8_convrot.safetensors", "minimax_h3_audio_vae_fp32.safetensors", 6, 30, 1978, "fixed"];
  const userCopy = { ...Object.fromEntries(NL10.map((n, i) => [n, user[i]])), [CONTROL_KEY]: "fixed", [LAYOUT_KEY]: NL10.join("|") };
  const assign = (node, arr) => { const s = node.widgets.filter((w) => w.serialize !== false); s.forEach((w, i) => { if (i < arr.length) w.value = arr[i]; }); };
  for (const [label, props] of [["with its copy", { [SHADOW_KEY]: userCopy }], ["without a copy", {}]]) {
    const node = mkL();
    await lext.nodeCreated(node);
    const info = { widgets_values: user.slice(), properties: props };
    const keep = info.widgets_values;
    node.onConfigure(info);
    assign(node, keep);
    await new Promise((r) => setTimeout(r, 450));
    const got = vals(node);
    check(NL10.every((n, i) => got[n] === user[i]) && got.turbo_lora_strength === 1.0 && got[CONTROL_KEY] === "fixed" && keep.length === 19 && keep[2] === 1.0,
      `the user's 0.1.10 Model Loader ${label}: every value by name, turbo_lora_strength 1.0, control 'fixed': ` + JSON.stringify(got));
  }
}

console.log("21. v0.0.9u: the REVITALIZER keeps a named copy of its values too (control word in the MIDDLE of the saved list)");
{
  const R_SHADOW = rev.SHADOW_KEY, R_LAYOUT = rev.LAYOUT_KEY, R_CTL = rev.CONTROL_KEY;
  check(R_SHADOW === SHADOW_KEY && R_LAYOUT === LAYOUT_KEY && R_CTL === CONTROL_KEY, "same copy key / layout key / control key as the Model Loader and the MTV node");
  const ALL = [...RN, ...rev.LORA_NAMES];                         // the 29 data widgets in the node's order (seed is followed by the control word in the saved list)
  const V = { latent: "S/x_video.latent", conditioning: "(match the latent)", freeze_audio: false, unet_name: "u.safetensors", vae_video: "v1", vae_audio: "a1", lora_on: true,
    lora_name: "t.safetensors", lora_strength: 0.9, attention_backend: "pytorch attention", upscale_on: false, upscale_model: "up2", megapixels: 1.5, temporal_chunking: false,
    force_unload: false, upscale_device: "cpu", upscale_precision: "bf16", seed: 12345, sampler_name: "dpmpp_2m", sigmas: "1, 0.5, 0",
    LoRa_1_enabled: true, LoRa_1: "H3.safetensors", LoRa_1_strength: 0.5, LoRa_2_enabled: false, LoRa_2: "None", LoRa_2_strength: 0.65, LoRa_3_enabled: true, LoRa_3: "x.safetensors", LoRa_3_strength: -2 };
  const FRESH = { latent: "(none)", conditioning: "(match the latent)", freeze_audio: true, unet_name: "d_unet", vae_video: "d_v", vae_audio: "d_a", lora_on: false, lora_name: "d_lora", lora_strength: 1,
    attention_backend: "comfy kitchen attention", upscale_on: true, upscale_model: "d_up", megapixels: 1.2, temporal_chunking: true, force_unload: true, upscale_device: "cuda", upscale_precision: "fp16",
    seed: 7, sampler_name: "euler", sigmas: rev.DEFAULT_SIGMAS, LoRa_1_enabled: true, LoRa_1: "SetLora.safetensors", LoRa_1_strength: 0.3, LoRa_2_enabled: false, LoRa_2: "None", LoRa_2_strength: 0.65,
    LoRa_3_enabled: false, LoRa_3: "None", LoRa_3_strength: 0.65, new_flag: true };        // a NEW node: LoRa_1 holds the Model Loader's saved set (ON), like a fresh node does
  const same2 = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  // a node as the real frontend builds it: the control widget right after the seed (it takes a slot in the saved list: only options.serialize is false),
  // and the Upload button (added by the real hook) at the end
  const mkReal = (names) => {
    const ws = [];
    for (const n of names) {
      ws.push({ name: n, value: FRESH[n] });
      if (n === "seed") ws.push({ name: "control_after_generate", value: "fixed", options: { serialize: false } });
    }
    const n = Object.create(nodeType.prototype);
    n.widgets = ws; n.properties = {}; n.setDirtyCanvas = () => {};
    n.addWidget = (type, name, value) => { ws.push({ name, type, value: null }); };
    n.onNodeCreated();                                           // the real hook: the fresh values are remembered, the Upload button is added
    return n;
  };
  const dataOf = (node) => Object.fromEntries(node.widgets.filter((w) => w.type !== "button" && w.name !== "control_after_generate").map((w) => [w.name, w.value]));
  const ctlOf = (node) => node.widgets.find((w) => w.name === "control_after_generate").value;
  const savedList = (node) => node.widgets.filter((w) => w.serialize !== false).map((w) => w.value);             // what the frontend writes: the control word IS in it
  const frontendAssign2 = (node, list) => { let i = 0; for (const w of node.widgets) { if (w.serialize === false) continue; if (i >= list.length) break; w.value = list[i++]; } };
  const setAll = (node, vals, ctl) => { for (const w of node.widgets) { if (w.name in vals) w.value = vals[w.name]; if (w.name === "control_after_generate") w.value = ctl; } };
  const saveOf2 = (node) => { const o = { widgets_values: savedList(node), properties: { ...node.properties } }; node.onSerialize(o); return o; };
  const settle = () => new Promise((r) => setTimeout(r, 450));

  // pure helpers
  check(rev.revTypeOk("seed", 5) && !rev.revTypeOk("seed", "5") && rev.revTypeOk("lora_on", false) && !rev.revTypeOk("lora_on", "true") && rev.revTypeOk("sigmas", "1, 0") && !rev.revTypeOk("sigmas", 3)
    && rev.revTypeOk("LoRa_1_strength", -2) && !rev.revTypeOk("LoRa_1_strength", NaN) && !rev.revTypeOk("LoRa_2", "") && rev.revTypeOk("LoRa_2", "None") && rev.revTypeOk("some_new_widget", 1) && !rev.revTypeOk("some_new_widget", null),
    "revTypeOk: each widget keeps its own type (an empty LoRa file name is not usable; an unknown widget takes any plain value)");
  const wsOf = (names) => names.map((n) => ({ name: n, value: V[n] }));
  const SH = rev.buildRevShadow(wsOf(ALL), { name: "control_after_generate", value: "randomize" });
  check(Object.keys(SH).length === ALL.length + 2 && SH[R_CTL] === "randomize" && SH[R_LAYOUT] === ALL.join("|") && ALL.every((n) => SH[n] === V[n]), "buildRevShadow: every data widget by name + the control word + __layout");
  check(!("control_after_generate" in rev.buildRevShadow(wsOf(ALL), null)) && rev.buildRevShadow(wsOf(ALL), null)[R_LAYOUT] === ALL.join("|"), "no control widget: the copy simply has no control word");
  check(rev.restoreRevFromShadow(ALL, SH, FRESH) === null, "same widget order as at save time: nothing to restore (a hand edit of the saved list stays)");
  const FUTN = ["latent", "conditioning", "freeze_audio", "new_flag", ...ALL.slice(3, 17), "sigmas", "seed", "sampler_name", ...rev.LORA_NAMES];      // a later update: one widget added early, sigmas moved before the seed
  const rr = rev.restoreRevFromShadow(FUTN, SH, FRESH);
  const seedAt = FUTN.indexOf("seed");
  check(rr && rr.list.length === FUTN.length + 1 && rr.list[seedAt] === 12345 && rr.list[seedAt + 1] === "randomize" && rr.list.filter((v) => v === "randomize").length === 1, "the control word is INSERTED right after the seed, not appended: " + JSON.stringify(rr && rr.list.slice(seedAt - 1, seedAt + 3)));
  check(rr && FUTN.every((n) => n === "new_flag" ? rr.byName[n] === true : rr.byName[n] === V[n]), "every old value lands on its own widget by name; the new widget gets its default");
  check(rev.restoreRevFromShadow(FUTN, { ...SH, [R_CTL]: "bogus" }, FRESH).control === "fixed" && rev.restoreRevFromShadow(FUTN, { ...SH, [R_CTL]: undefined }, FRESH).control === "fixed", "a missing / unknown control word becomes fixed");
  check(rev.restoreRevFromShadow(FUTN.filter((n) => n !== "seed"), SH, FRESH).list.length === FUTN.length - 1, "a layout without a seed gets no control word");
  const dm2 = rev.restoreRevFromShadow(FUTN, { ...SH, seed: "7", sigmas: 3 }, FRESH);
  check(dm2 && dm2.byName.seed === 7 && dm2.byName.sigmas === rev.DEFAULT_SIGMAS && dm2.byName.megapixels === 1.5, "a value of the wrong type in the copy takes the widget's default, the others keep theirs");
  check(rev.restoreRevFromShadow(FUTN, SH, { ...FRESH, new_flag: null }) === null && rev.restoreRevFromShadow(FUTN, SH, { ...FRESH, new_flag: undefined }) === null, "a new widget with no default: the copy is not used (the positional repairs stay in charge)");
  check(rev.restoreRevFromShadow(FUTN, null, FRESH) === null && rev.restoreRevFromShadow(FUTN, [], FRESH) === null && rev.restoreRevFromShadow(FUTN, "garbage", FRESH) === null && rev.restoreRevFromShadow(FUTN, { other: 1 }, FRESH) === null, "no / unusable copy: null");
  const lack = Object.fromEntries(Object.entries(SH).filter(([k]) => !k.startsWith("LoRa_1")));
  const lr = rev.restoreRevFromShadow(FUTN, lack, rev.freshDefaults({ widgets: wsOf(FUTN).map((w) => ({ ...w, value: FRESH[w.name] })) }));
  check(lr && lr.byName.LoRa_1_enabled === false && lr.byName.LoRa_1 === "None" && lr.byName.LoRa_1_strength === 1.0, "a LoRa_n the copy lacks is OFF / None / 1.0, NOT the saved set's values that a fresh node holds");

  // the REAL hooks (onNodeCreated / onSerialize / onConfigure of the node type)
  // (a) every save writes the copy: data widgets + control word + layout; not the Upload button
  let node = mkReal(ALL);
  setAll(node, V, "randomize");
  const o1 = saveOf2(node);
  const cp = o1.properties[R_SHADOW];
  check(cp && ALL.every((n) => cp[n] === V[n]) && cp[R_CTL] === "randomize" && cp[R_LAYOUT] === ALL.join("|") && Object.keys(cp).length === ALL.length + 2, "a save writes the copy: 29 values by name + control + __layout, nothing else: " + Object.keys(cp || {}).filter((k) => !ALL.includes(k)).join());
  check(node.properties[R_SHADOW] === cp, "the copy is also kept on the node's own properties");
  check(o1.widgets_values.length === ALL.length + 2, "(control) the saved list holds the 29 values + the control word + the Upload button's slot: " + o1.widgets_values.length);
  check(o1.widgets_values[ALL.indexOf("seed")] === 12345 && o1.widgets_values[ALL.indexOf("seed") + 1] === "randomize" && o1.widgets_values[ALL.indexOf("seed") + 2] === "dpmpp_2m", "the saved list: seed, control word, sampler_name");
  // (b) same layout: positional route, a hand edit stays; the old repairs still run (nothing to repair here)
  node = mkReal(ALL);
  { const list = o1.widgets_values.slice(); list[ALL.indexOf("seed")] = 999; const inf = { widgets_values: list, properties: { [R_SHADOW]: cp } }; node.onConfigure(inf); frontendAssign2(node, inf.widgets_values); }
  await settle();
  check(dataOf(node).seed === 999 && dataOf(node).LoRa_3 === "x.safetensors" && ctlOf(node) === "randomize", "same widget order: the positional values are used (a value edited by hand in the workflow file stays), the control word too");
  // (c) a later update moved / added widgets: the copy restores by name; what a positional load would do instead
  node = mkReal(FUTN);
  const oldSaved = o1.widgets_values.slice();
  const keepRef = oldSaved.slice();
  { const inf = { widgets_values: keepRef, properties: { [R_SHADOW]: cp } }; node.onConfigure(inf); frontendAssign2(node, keepRef); }
  let got = dataOf(node);
  check(ALL.every((n) => got[n] === V[n]) && got.new_flag === true && ctlOf(node) === "randomize", "saved by this release, loaded after widgets moved: all 29 values by name, new_flag at its default, control word 'randomize' on the control widget");
  check(keepRef.length === FUTN.length + 1 && keepRef[seedAt] === 12345 && keepRef[seedAt + 1] === "randomize", "the saved array is rewritten IN PLACE with the control word right after the seed (a frontend holding the reference sees it)");
  { const wrong = mkReal(FUTN); frontendAssign2(wrong, oldSaved); const g = dataOf(wrong); check(g.new_flag !== true || g.seed !== 12345 || ctlOf(wrong) !== "randomize", "(control) the same file read by POSITION would shift values: new_flag=" + JSON.stringify(g.new_flag) + " seed=" + JSON.stringify(g.seed) + " control=" + JSON.stringify(ctlOf(wrong))); }
  // (d) the frontend assigns the OLD positional values AFTER the hook: the 0 / 400 ms re-apply wins
  node = mkReal(FUTN);
  { const inf = { widgets_values: oldSaved.slice(), properties: { [R_SHADOW]: cp } }; node.onConfigure(inf); frontendAssign2(node, oldSaved); }       // assigned late, from its own old copy
  await settle();
  got = dataOf(node);
  check(ALL.every((n) => got[n] === V[n]) && got.new_flag === true && ctlOf(node) === "randomize", "values assigned after the hook (from the frontend's old copy) are corrected again by name");
  // (e) load + save + load again on the new layout is stable and the copy carries the new order
  { const o2 = saveOf2(node); const n2 = mkReal(FUTN); const inf = { widgets_values: o2.widgets_values.slice(), properties: o2.properties }; n2.onConfigure(inf); frontendAssign2(n2, inf.widgets_values); await settle();
    check(same2(dataOf(n2), dataOf(node)) && ctlOf(n2) === "randomize" && o2.properties[R_SHADOW][R_LAYOUT] === FUTN.join("|") && !(("Upload latent / conditioning files...") in o2.properties[R_SHADOW]), "load + save + load on the new layout: stable, the copy now carries the new order, no Upload button in it"); }
  // (f) a workflow saved BEFORE this release (no copy): the position-based repairs still run (sigmas + LoRa_1-3)
  node = mkReal(ALL.slice(0, 20));
  { const oldList = [...rHead, "randomize", "euler", "video/MiniMax_H3"]; const inf = { widgets_values: oldList, properties: {} }; node.onConfigure(inf);
    check(oldList[20] === rev.DEFAULT_SIGMAS, "no copy (the oldest layout): the old filename_prefix text is replaced by the default sigmas, in place, as in section 13"); }
  node = mkReal(ALL);
  { const oldList = savedList(node); const base = [...rHead, "randomize", "euler", rev.DEFAULT_SIGMAS]; const inf = { widgets_values: base.slice(), properties: {} }; node.onConfigure(inf);
    check(inf.widgets_values.length === 30 && same2(inf.widgets_values.slice(21), [false, "None", 1.0, false, "None", 1.0, false, "None", 1.0]), "no copy (saved with 0.0.9 / 0.0.9b): the nine LoRa values are completed OFF / None / 1.0, as in section 16");
    await settle();
    check(dataOf(node).LoRa_1_enabled === false && dataOf(node).LoRa_1 === "None", "...and the widgets are OFF / None, not the saved set's ON that the fresh node holds"); }
  // (g) a damaged / unusable copy never breaks the load
  node = mkReal(FUTN);
  { const inf = { widgets_values: oldSaved.slice(), properties: { [R_SHADOW]: { ...cp, seed: "x", sigmas: 3 } } }; node.onConfigure(inf); frontendAssign2(node, inf.widgets_values); await settle(); }
  check(dataOf(node).seed === 7 && dataOf(node).sigmas === rev.DEFAULT_SIGMAS && dataOf(node).megapixels === 1.5 && dataOf(node).LoRa_3 === "x.safetensors", "a damaged value in the copy: that widget takes its default, the others keep theirs");
  node = mkReal(ALL);
  { const inf = { widgets_values: oldSaved.slice(), properties: { [R_SHADOW]: "garbage" } }; node.onConfigure(inf); frontendAssign2(node, inf.widgets_values); await settle(); }
  check(ALL.every((n) => dataOf(node)[n] === V[n]) && ctlOf(node) === "randomize", "an unusable copy is ignored: the positional values load as before");
  // (h) no onNodeCreated (e.g. a node type created some other way): the fresh values are taken at the first load, nothing throws
  { const n3 = Object.create(nodeType.prototype); n3.widgets = ALL.map((n) => ({ name: n, value: FRESH[n] })); n3.properties = {}; n3.setDirtyCanvas = () => {};
    let threw = false; try { n3.onConfigure({ widgets_values: [], properties: { [R_SHADOW]: cp } }); } catch (e) { threw = true; }
    check(!threw, "a load on a node that never ran onNodeCreated does not throw"); }
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log("24. v0.1.20: the legacy Picture_1..9 sockets of an old saved MTV are dropped (wired ones stay)");
{
  const extM = await import(pathToFileURL(path.join(tmp, "ext", "web", "ext.mjs")).href);
  const mk = (names, wired = []) => {
    const node = { inputs: names.map((n, i) => ({ name: n, link: wired.includes(n) ? 100 + i : null })), removed: [] };
    node.removeInput = (i) => { node.removed.push(node.inputs[i].name); node.inputs.splice(i, 1); };
    return node;
  };
  const old = mk(["models", ...Array.from({ length: 9 }, (_, i) => `Picture_${i + 1}`), "Pictures"]);
  check(extM.dropLegacyPictureInputs(old) === 9 && old.inputs.map((i) => i.name).join() === "models,Pictures", "an old node: the nine empty Picture_n sockets are removed, models and Pictures stay");
  const wired = mk(["models", "Picture_1", "Picture_2", "Pictures"], ["Picture_2"]);
  check(extM.dropLegacyPictureInputs(wired) === 1 && wired.inputs.map((i) => i.name).join() === "models,Picture_2,Pictures", "a Picture_n that still has a wire stays (it keeps working)");
  const fresh = mk(["models", "Pictures"]);
  check(extM.dropLegacyPictureInputs(fresh) === 0 && fresh.inputs.length === 2 && extM.dropLegacyPictureInputs({}) === 0, "a new node (or no inputs) is left alone");
}

console.log("25. v0.2.4: Jump to time (MM:SS snapped to the segment that contains it)");
{
  const extT = await import(pathToFileURL(path.join(tmp, "ext", "web", "ext.mjs")).href);
  const { parseClock, fmtClock, segmentForTime } = extT;
  check(parseClock("1:23") === 83 && parseClock("83") === 83 && parseClock("01:23.5") === 83.5 && parseClock("1:02:03") === 3723 && parseClock(" 0:05 ") === 5, "1:23, 83, 01:23.5, 1:02:03 and a padded 0:05 are times");
  check(["", "abc", "1:75", "-5", "1::2", "1:2:3:4", null, undefined, "1,5"].every((v) => parseClock(v) === null), "empty, text, minutes/seconds >= 60 and 4 parts are refused");
  check(fmtClock(83) === "01:23" && fmtClock(82.75) === "01:22.75" && fmtClock(3723) === "1:02:03" && fmtClock(0) === "00:00", "fmtClock: 01:23, 01:22.75, 1:02:03, 00:00");
  const seg = 124 / 24;                                                   // 5.1667 s per segment, like a 5 s duration
  const a = segmentForTime(83, seg, 40);
  check(a.ok && a.segment === 17 && Math.abs(a.start - 16 * seg) < 1e-9 && a.start <= 83 && 83 - a.start < seg, "01:23 -> segment 17, starting at 01:22.67 (never later than the time, less than one segment earlier)");
  check(segmentForTime(0, seg, 40).segment === 1 && segmentForTime(5.1, seg, 40).segment === 1 && segmentForTime(5.17, seg, 40).segment === 2, "the boundaries: 0 and 5.1 s are segment 1, 5.17 s is segment 2");
  check(segmentForTime(10 * seg, seg, 40).segment === 11 && segmentForTime(10 * seg - 0.0001, seg, 40).segment === 10, "an exact boundary belongs to the segment that starts there");
  const past = segmentForTime(300, seg, 40);
  check(!past.ok && /Ends at 03:26/.test(past.error), "past the end: refused with the end time (" + past.error + ")");
  check(segmentForTime(300, seg, null).ok && !segmentForTime(-1, seg, 40).ok && !segmentForTime(5, 0, 40).ok, "unknown total is accepted; negative time or no segment length is refused");
}

console.log(fails ? `\n${fails} FAILED` : "\nALL MIGRATION CHECKS PASSED");
process.exit(fails ? 1 : 0);
