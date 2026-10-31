// Test of web/il78_sync_logic.js (gating + sync maths) with a fake MTV node and a fake fetchApi. Plain node, no dependencies:
//   node tests/test_sync_logic.mjs        (ComfyUI only loads web/, so this folder is ignored at runtime)
import assert from "node:assert/strict";
import { gate, planSync, normFile, collectNodes } from "../web/il78_sync_logic.js";
import fs from "node:fs";

const mtv = (over = {}, id = 7, mode = 0) => ({
  id, mode, comfyClass: "IronLeo78_MTV",
  widgets: Object.entries({ "Use Video": true, "Video File": "clip.mp4", "Custom Audio File": "None", "Choose Audio latent": "Custom Audio",
                            duration: 5, "Next Segment On Run": true, ...over }).map(([name, value]) => ({ name, value })),
});
const api = (info, seen = []) => async (url) => { seen.push(url); return { json: async () => info }; };
const lim = { maxStart: 36000, maxDuration: 20 };
let n = 0; const t = async (name, fn) => { await fn(); n++; console.log("ok -", name); };

await t("normFile strips the type suffix", () => assert.equal(normFile("sub/a.mp4 [input]"), "sub/a.mp4"));

await t("mirrorVideo: loader -> MTV (option added, callback run once, no echo), MTV -> loader, None/empty ignored", async () => {
  const { mirrorVideo } = await import("../web/il78_sync_logic.js");
  let cbs = 0;
  const m = mtv({ "Video File": "None" });
  const w = m.widgets.find((x) => x.name === "Video File");
  w.options = { values: ["None", "a.mp4"] };
  w.callback = () => { cbs++; };
  let set = [];
  const ld = { id: 9, mode: 0, comfyClass: "IronLeo78_MTV_PromptGenerator", widgets: [{ name: "video", value: "" }],
               _il78: { setVideo: (v) => { set.push(v); ld.widgets[0].value = v; } } };
  assert.deepEqual(mirrorVideo(ld, "new.mp4 [input]", [m, ld]), [m]);
  assert.equal(w.value, "new.mp4"); assert.ok(w.options.values.includes("new.mp4")); assert.equal(cbs, 1);
  assert.equal(mirrorVideo(ld, "new.mp4", [m, ld]).length, 0);                       // already the same: nothing
  assert.deepEqual(mirrorVideo(m, "sub/b.mp4", [m, ld]), [ld]); assert.deepEqual(set, ["sub/b.mp4"]);
  assert.equal(mirrorVideo(m, "None", [m, ld]).length + mirrorVideo(m, "", [m, ld]).length, 0);
  assert.equal(mirrorVideo({ comfyClass: "Other" }, "x.mp4", [m, ld]).length, 0);
});

await t("v0.1.22: loading a video sets Choose Audio latent = Audio From Video on the MTV (also when it already had the file); None / MTV-source untouched", async () => {
  const { mirrorVideo, useVideoAudio } = await import("../web/il78_sync_logic.js");
  const m = mtv({ "Video File": "clip.mp4", "Choose Audio latent": "Custom Audio" });
  const audio = m.widgets.find((x) => x.name === "Choose Audio latent"); let cbs = 0; audio.callback = () => { cbs++; };
  const ld = { id: 9, mode: 0, comfyClass: "IronLeo78_MTV_PromptGenerator", widgets: [{ name: "video", value: "" }], _il78: { setVideo: () => {} } };
  assert.deepEqual(mirrorVideo(ld, "clip.mp4", [m, ld]), [m]);                       // same file already there: only the audio mode changes
  assert.equal(audio.value, "Audio From Video"); assert.equal(cbs, 1);
  assert.equal(mirrorVideo(ld, "clip.mp4", [m, ld]).length, 0);                      // nothing left to change
  audio.value = "MiniMax Audio";
  assert.equal(mirrorVideo(ld, "None", [m, ld]).length, 0); assert.equal(audio.value, "MiniMax Audio");     // None never touches it
  assert.equal(useVideoAudio(m), true); assert.equal(useVideoAudio(m), false); assert.equal(useVideoAudio({}), false);
  const m2 = mtv({ "Video File": "None", "Choose Audio latent": "Custom Audio" });
  m2.widgets.find((x) => x.name === "Video File").options = { values: [] };
  mirrorVideo(ld, "new.mp4", [m2, ld]);
  assert.equal(m2.widgets.find((x) => x.name === "Choose Audio latent").value, "Audio From Video");
});

await t("mirrorVideo: the all-in-one prompt generator is a loader too (both directions)", async () => {
  const { mirrorVideo } = await import("../web/il78_sync_logic.js");
  const m = mtv({ "Video File": "None" });
  const w = m.widgets.find((x) => x.name === "Video File"); w.options = { values: ["None"] }; w.callback = () => {};
  let set = [];
  const pg = { id: 11, mode: 0, comfyClass: "IronLeo78_MTV_PromptGenerator", widgets: [{ name: "video", value: "" }],
               _il78: { setVideo: (v) => { set.push(v); pg.widgets[0].value = v; } } };
  assert.deepEqual(mirrorVideo(m, "a.mp4", [m, pg]), [pg]); assert.deepEqual(set, ["a.mp4"]);
  assert.deepEqual(mirrorVideo(pg, "b.mp4", [m, pg]), [m]); assert.equal(w.value, "b.mp4");
});

await t("v0.1.24: suggestPrompt fills an empty box or a box holding a suggestion, never the user's own text", async () => {
  const { suggestPrompt } = await import("../web/il78_sync_logic.js");
  const S = { None: "", "1 - A": "Replace the main character of Video 1.", "2 - B": "Replace the main character and the environment of Video 1." };
  assert.equal(suggestPrompt("", S, "1 - A"), S["1 - A"]);                      // empty box -> the suggestion
  assert.equal(suggestPrompt("  ", S, "2 - B"), S["2 - B"]);
  assert.equal(suggestPrompt(S["1 - A"], S, "2 - B"), S["2 - B"]);              // still the previous suggestion -> follows the new preset
  assert.equal(suggestPrompt(S["2 - B"], S, "None"), "");                       // None clears an untouched suggestion
  assert.equal(suggestPrompt("make him a pirate", S, "1 - A"), null);          // the user wrote it: left alone (default / Mode change)
  assert.equal(suggestPrompt("make him a pirate", S, "1 - A", true), S["1 - A"]);        // v0.3.1: choosing a preset fills the example anyway
  assert.equal(suggestPrompt("make him a pirate", S, "None", true), null);                // ...but choosing None never wipes typed text
  assert.equal(suggestPrompt(S["1 - A"], S, "None", true), "");                           // it only clears an untouched example
  assert.equal(suggestPrompt(S["1 - A"], S, "1 - A", true), null);                        // nothing to change
  assert.equal(suggestPrompt(S["1 - A"], S, "1 - A"), null);                    // nothing to change
  assert.equal(suggestPrompt("", S, "None"), null);
  assert.equal(suggestPrompt("", null, "x"), null);
});

await t("v0.2.3: Sync follows the Go-to counter with Next Segment ON and OFF (the MTV's OFF Run repeats that same segment)", async () => {
  const lim2 = { maxStart: 36000, maxDuration: 20 };
  const on = await planSync(api({ ok: true, total: 10, frames: 120, index: 4, stepping: true, finished: false, running: false }), mtv(), lim2);
  assert.equal(on.ok, true); assert.equal(on.start, 20); assert.match(on.text, /segment 5 of 10/); assert.deepEqual(on.warn, []);
  const off = await planSync(api({ ok: true, total: 10, frames: 120, index: 4, stepping: false, finished: false, running: false }), mtv({ "Next Segment On Run": false }), lim2);
  assert.equal(off.ok, true); assert.equal(off.start, 20); assert.match(off.text, /segment 5 of 10/);          // v0.2.2: follows Go even with OFF
  assert.deepEqual(off.warn, []);                                                                  // v0.2.3: the MTV Run repeats that segment too, nothing to warn about
  const offDone = await planSync(api({ ok: true, total: 10, frames: 120, index: 10, stepping: false, finished: true, running: false }), mtv({ "Next Segment On Run": false }), lim2);
  assert.equal(offDone.ok, true); assert.equal(offDone.start, 0); assert.match(offDone.text, /segment 1 of 10/);    // a finished counter with OFF: segment 1
  const onDone = await planSync(api({ ok: true, total: 10, frames: 120, index: 10, stepping: true, finished: true, running: false }), mtv(), lim2);
  assert.equal(onDone.ok, false); assert.match(onDone.text, /All 10 MTV segments are done/);                        // ON + finished: unchanged
  const off0 = await planSync(api({ ok: true, total: 10, frames: 120, index: 0, stepping: false, finished: false, running: false }), mtv({ "Next Segment On Run": false }), lim2);
  assert.deepEqual(off0.warn, []);                                                  // nothing to explain when the counter is at 1
});

await t("v0.2.5: suggestPrompt with one map per mode (\"mode|preset\"): switching Mode swaps a suggestion, never user text", async () => {
  const { suggestPrompt } = await import("../web/il78_sync_logic.js");
  const S = { "v2v|None": "", "i2v|None": "", "v2v|1 - A": "Replace the main character of Video 1.", "i2v|1 - A": "Replace the main character of Picture 1 with the character of Picture 2." };
  assert.equal(suggestPrompt(S["v2v|1 - A"], S, "i2v|1 - A"), S["i2v|1 - A"]);       // v2v suggestion -> the i2v one when Mode changes
  assert.equal(suggestPrompt(S["i2v|1 - A"], S, "v2v|1 - A"), S["v2v|1 - A"]);       // and back
  assert.equal(suggestPrompt(S["i2v|1 - A"], S, "i2v|None"), "");                    // None clears it in either mode
  assert.equal(suggestPrompt("my own idea", S, "i2v|1 - A"), null);                  // without force, typed text is kept (the node now forces on Preset AND Mode changes, v0.3.2)
  assert.equal(suggestPrompt("my own idea", S, "i2v|1 - A", true), S["i2v|1 - A"]);   // choosing a Preset or changing the Mode shows the example of that mode (v0.3.1 / v0.3.2)
  assert.equal(suggestPrompt(S["v2v|1 - A"], S, "i2v|1 - A", true), S["i2v|1 - A"]);   // v2v -> i2v with the v2v example in the box: the i2v example
  assert.equal(suggestPrompt("my own idea", S, "i2v|None", true), null);               // Mode change with preset None: typed text is kept (no example to show)
});

await t("v0.2.6: Mode v2v -> Audio From Video, i2v -> MiniMax Audio on every MTV; i2v video loading leaves the audio alone", async () => {
  const { applyPresetAudio, mirrorVideo, setAudioMode } = await import("../web/il78_sync_logic.js");
  const modeAudio = (mode, nodes) => applyPresetAudio(nodes, mode, { audio: "", stem: "" }, null, true);      // what a Mode change does (the old applyModeAudio)
  const m1 = mtv({ "Choose Audio latent": "Custom Audio" }), m2 = mtv({ "Choose Audio latent": "Audio From Video" });
  const a = (m) => m.widgets.find((x) => x.name === "Choose Audio latent");
  const other = { comfyClass: "Other", widgets: [{ name: "Choose Audio latent", value: "x" }] };
  modeAudio("i2v", [m1, m2, other]);                                                      // both change to MiniMax Audio, a foreign node is left alone
  assert.equal(a(m1).value, "MiniMax Audio"); assert.equal(a(m2).value, "MiniMax Audio"); assert.equal(other.widgets[0].value, "x");
  modeAudio("v2v", [m1, m2]); assert.equal(a(m1).value, "Audio From Video"); assert.equal(a(m2).value, "Audio From Video");
  modeAudio("v2v", [m1, m2]); assert.equal(a(m1).value, "Audio From Video");              // nothing left to change
  assert.doesNotThrow(() => modeAudio("v2v", null)); assert.equal(setAudioMode({}, "x"), false);
  const m3 = mtv({ "Video File": "None", "Choose Audio latent": "MiniMax Audio" });
  m3.widgets.find((x) => x.name === "Video File").options = { values: [] };
  const ld = { id: 9, mode: 0, comfyClass: "IronLeo78_MTV_PromptGenerator", widgets: [{ name: "video", value: "" }], _il78: { setVideo: () => {} } };
  mirrorVideo(ld, "clip.mp4", [m3, ld], { audio: false });                               // generator in i2v
  assert.equal(m3.widgets.find((x) => x.name === "Video File").value, "clip.mp4"); assert.equal(a(m3).value, "MiniMax Audio");
  mirrorVideo(ld, "clip2.mp4", [m3, ld]);                                                // v2v (default): the video's sound
  assert.equal(a(m3).value, "Audio From Video");
});

await t("v0.3.0: a musician preset sets Custom Audio + its Audio Stem; leaving it puts the Mode audio and Full back; Mode changes keep a musician preset's audio", async () => {
  const { applyPresetAudio, setMtvWidget } = await import("../web/il78_sync_logic.js");
  const mk = (stem = "Full", audio = "Audio From Video") => {
    const m = mtv({ "Choose Audio latent": audio });
    m.widgets.push({ name: "Audio Stem", value: stem, options: { values: ["Full", "Vocals", "Guitars", "Drums", "Bass"] } });
    m.widgets.find((x) => x.name === "Choose Audio latent").options = { values: ["MiniMax Audio", "Audio From Video", "Custom Audio"] };
    return m;
  };
  const val = (m, n) => m.widgets.find((x) => x.name === n).value;
  const drum = { audio: "Custom Audio", stem: "Drums" }, none = { audio: "", stem: "" };
  const m = mk(), other = { comfyClass: "Other", widgets: [] };
  let st = applyPresetAudio([m, other], "v2v", drum, null);                         // choose the drummer preset
  assert.equal(st.audio, "Custom Audio"); assert.equal(st.stem, "Drums"); assert.ok(st.before && Object.keys(st.before).length === 1);   // v0.3.12: what the MTV had before is remembered
  assert.equal(val(m, "Choose Audio latent"), "Custom Audio"); assert.equal(val(m, "Audio Stem"), "Drums");
  st = applyPresetAudio([m], "i2v", drum, st, true);                                 // the Mode changes while the musician preset is chosen: it keeps Custom Audio
  assert.equal(val(m, "Choose Audio latent"), "Custom Audio"); assert.equal(val(m, "Audio Stem"), "Drums");
  m.widgets.find((x) => x.name === "Audio Stem").value = "Bass";                      // the user picks another stem by hand
  st = applyPresetAudio([m], "v2v", none, st, false);                                // then another preset without audio settings
  assert.equal(val(m, "Choose Audio latent"), "Audio From Video");                    // the Mode audio is back
  assert.equal(val(m, "Audio Stem"), "Bass");                                         // the hand-picked stem is NOT reset
  const m2 = mk("Drums", "Custom Audio");
  applyPresetAudio([m2], "i2v", none, drum, false);                                   // leaving the drummer preset with its stem still set
  assert.equal(val(m2, "Choose Audio latent"), "MiniMax Audio"); assert.equal(val(m2, "Audio Stem"), "Full");
  const m3 = mk("Bass", "Custom Audio");
  applyPresetAudio([m3], "v2v", none, null, false);                                   // no musician preset before: nothing is touched
  assert.equal(val(m3, "Choose Audio latent"), "Custom Audio"); assert.equal(val(m3, "Audio Stem"), "Bass");
  const m4 = mk("Full", "Custom Audio");
  applyPresetAudio([m4], "v2v", none, null, true);                                    // a Mode change with a plain preset: the Mode audio (as in 0.2.6)
  assert.equal(val(m4, "Choose Audio latent"), "Audio From Video");
  assert.equal(setMtvWidget(m4, "Audio Stem", "Banjo"), false); assert.equal(val(m4, "Audio Stem"), "Full");          // a value the widget does not offer is never forced
  assert.deepEqual(applyPresetAudio(null, "v2v", null, null), none);

  // v0.3.12: leaving a musician preset gives back what the user had BEFORE it
  const songBefore = mtv({ "Choose Audio latent": "Custom Audio", "Custom Audio File": "song.wav" }, 21);
  songBefore.widgets.push({ name: "Audio Stem", value: "Vocals", options: { values: ["Full", "Vocals", "Guitars", "Drums", "Bass"] } });
  songBefore.widgets.find((x) => x.name === "Choose Audio latent").options = { values: ["MiniMax Audio", "Audio From Video", "Custom Audio"] };
  let s1 = applyPresetAudio([songBefore], "v2v", drum, null);                          // a song project with the Vocals stem picks the drummer preset
  assert.equal(val(songBefore, "Audio Stem"), "Drums");
  s1 = JSON.parse(JSON.stringify(s1));                                                 // saved with the workflow and read back
  applyPresetAudio([songBefore], "v2v", none, s1, false);                              // ... then a plain preset
  assert.equal(val(songBefore, "Choose Audio latent"), "Custom Audio"); assert.equal(val(songBefore, "Audio Stem"), "Vocals");   // the song project is back, not the Mode audio
  // musician -> musician keeps the ORIGINAL settings
  const mm = mk("Bass", "Audio From Video");
  const a1 = applyPresetAudio([mm], "v2v", drum, null);
  const a2 = applyPresetAudio([mm], "v2v", { audio: "Custom Audio", stem: "Guitars" }, a1);
  assert.equal(val(mm, "Audio Stem"), "Guitars");
  applyPresetAudio([mm], "v2v", none, a2, false);
  assert.equal(val(mm, "Choose Audio latent"), "Audio From Video"); assert.equal(val(mm, "Audio Stem"), "Bass");              // the very first values
  // a change made by hand after the preset is left alone
  const hand = mk("Full", "Audio From Video");
  const h1 = applyPresetAudio([hand], "v2v", drum, null);
  hand.widgets.find((x) => x.name === "Choose Audio latent").value = "MiniMax Audio";                                         // the user switches the audio by hand
  applyPresetAudio([hand], "v2v", none, h1, false);
  assert.equal(val(hand, "Choose Audio latent"), "MiniMax Audio"); assert.equal(val(hand, "Audio Stem"), "Full");             // audio kept; the stem was still the preset's, so it goes back to what it was
});

await t("v0.3.5: i2v Sync copies the MTV duration (no video needed); the Custom Audio warning check", async () => {
  const { gateI2v, planSyncI2v, customAudioMissing } = await import("../web/il78_sync_logic.js");
  const m = mtv({ duration: 7.5 });
  assert.equal(gateI2v([]).ok, false); assert.match(gateI2v([]).reason, /No MTV/);
  assert.equal(gateI2v([mtv({}, 7, 4)]).ok, false);                                       // bypassed: ignored
  const g = gateI2v([m, mtv({}, 8)]); assert.equal(g.ok, true); assert.equal(g.mtv, m); assert.match(g.note, /2 MTV nodes/);
  const lim = { maxDuration: 20, minDuration: 1 };
  const { paddedSeconds } = await import("../web/il78_sync_logic.js");
  assert.equal(paddedSeconds(5), 124 / 24); assert.equal(paddedSeconds(7.5), 8); assert.equal(paddedSeconds(0.1), 5 / 24);          // same frames as mtv.py _minimax_frames
  assert.equal(paddedSeconds(10), 243 / 24);                                                                                   // 240 % 17 = 2 -> +3 = 243 frames
  assert.deepEqual(planSyncI2v(m, lim), { ok: true, duration: 8, warn: [], text: "Synced: duration 8s (the MTV's 7.5s, padded to the frames it renders)" });   // 7.5 s -> 192 frames
  assert.equal(planSyncI2v(mtv({ duration: 5 }), lim).duration, 124 / 24);
  assert.equal(planSyncI2v(mtv({ duration: 20 }), lim).duration, 20); assert.deepEqual(planSyncI2v(mtv({ duration: 20 }), lim).warn, []);   // 20 s pads to 20.04 s: held at the maximum, no warning
  assert.equal(planSyncI2v(mtv({ duration: 45 }), lim).duration, 20); assert.equal(planSyncI2v(mtv({ duration: 45 }), lim).warn.length, 1);
  assert.equal(planSyncI2v(mtv({ duration: 0.4 }), lim).duration, 1); assert.equal(planSyncI2v(mtv({ duration: 0.4 }), lim).warn.length, 1);
  assert.equal(planSyncI2v(mtv({ duration: "x" }), lim).ok, false);
  const none = mtv({ "Choose Audio latent": "Custom Audio", "Custom Audio File": "None" });
  assert.equal(customAudioMissing([none]), true);
  assert.equal(customAudioMissing([mtv({ "Choose Audio latent": "Custom Audio", "Custom Audio File": "song.wav" })]), false);
  assert.equal(customAudioMissing([mtv({ "Choose Audio latent": "Audio From Video", "Custom Audio File": "None" })]), false);   // another audio mode: nothing to warn about
  assert.equal(customAudioMissing([{ comfyClass: "Other", widgets: [] }, null]), false); assert.equal(customAudioMissing(null), false);
});

await t("v0.3.7: a song setup (Custom Audio + a file) is never switched automatically; coming back from a musician preset still restores the Mode audio", async () => {
  const { isSongSetup, useVideoAudio, applyPresetAudio, mirrorVideo } = await import("../web/il78_sync_logic.js");
  const song = () => mtv({ "Choose Audio latent": "Custom Audio", "Custom Audio File": "song.wav" });
  const a = (m) => m.widgets.find((x) => x.name === "Choose Audio latent").value;
  assert.equal(isSongSetup(song()), true);
  assert.equal(isSongSetup(mtv({ "Choose Audio latent": "Custom Audio", "Custom Audio File": "None" })), false);
  assert.equal(isSongSetup(mtv({ "Choose Audio latent": "Custom Audio", "Custom Audio File": "none" })), false);        // any case
  assert.equal(isSongSetup(mtv({ "Choose Audio latent": "Audio From Video", "Custom Audio File": "song.wav" })), false);   // another mode: not a song setup
  const m = song();
  assert.equal(useVideoAudio(m), false); assert.equal(a(m), "Custom Audio");                                         // loading a video keeps the song
  applyPresetAudio([m], "v2v", { audio: "", stem: "" }, null, true); assert.equal(a(m), "Custom Audio");           // so does a Mode change
  applyPresetAudio([m], "i2v", { audio: "", stem: "" }, null, true); assert.equal(a(m), "Custom Audio");              // ... and the preset fallback
  const ld = { id: 9, mode: 0, comfyClass: "IronLeo78_MTV_PromptGenerator", widgets: [{ name: "video", value: "" }], _il78: { setVideo: () => {} } };
  const mv = song(); mv.widgets.find((x) => x.name === "Video File").options = { values: [] };
  mirrorVideo(ld, "clip.mp4", [mv, ld]); assert.equal(mv.widgets.find((x) => x.name === "Video File").value, "clip.mp4"); assert.equal(a(mv), "Custom Audio");   // the file is copied, the audio is kept
  const free = mtv({ "Choose Audio latent": "Audio From Video", "Custom Audio File": "song.wav" });
  assert.equal(useVideoAudio(free), false); assert.equal(a(free), "Audio From Video");                              // (already set: nothing to do)
  // musician preset: sets Custom Audio itself, and leaving it puts the Mode audio back even though a file is picked
  const drum = { audio: "Custom Audio", stem: "Drums" }, none = { audio: "", stem: "" };
  const x = mtv({ "Choose Audio latent": "Audio From Video", "Custom Audio File": "song.wav" });
  x.widgets.push({ name: "Audio Stem", value: "Full", options: { values: ["Full", "Vocals", "Guitars", "Drums", "Bass"] } });
  const st = applyPresetAudio([x], "v2v", drum, null); assert.equal(a(x), "Custom Audio");
  applyPresetAudio([x], "v2v", none, st, false); assert.equal(a(x), "Audio From Video");
  assert.equal(x.widgets.find((w) => w.name === "Audio Stem").value, "Full");
});

await t("gate: no video / no MTV / other file / wrong mode", () => {
  assert.equal(gate("", [mtv()]).ok, false);
  assert.equal(gate("clip.mp4", []).ok, false);
  assert.match(gate("clip.mp4", [mtv({ "Video File": "other.mp4" })]).reason, /same file/);
  assert.match(gate("clip.mp4", [mtv({ "Use Video": false })]).reason, /Use Video/);
  assert.equal(gate("clip.mp4", [mtv({}, 7, 4)]).ok, false);                      // bypassed MTV is ignored
});
await t("gate: [input] suffix ignored, Use Video OFF + Audio From Video ok (also the old bool false)", () => {
  assert.equal(gate("clip.mp4 [input]", [mtv()]).ok, true);
  assert.equal(gate("clip.mp4", [mtv({ "Use Video": false, "Choose Audio latent": "Audio From Video" })]).ok, true);
  assert.equal(gate("clip.mp4", [mtv({ "Use Video": false, "Choose Audio latent": false })]).ok, true);
});
await t("gate: two matching MTV nodes -> first one + a note", () => {
  const g = gate("clip.mp4", [mtv({}, 3), mtv({}, 9)]);
  assert.equal(g.mtv.id, 3); assert.match(g.note, /2 MTV nodes/);
});

await t("sync: 5 s = 124 frames; segment 4 starts at 4 x 124/24, full precision", async () => {
  const seen = [];
  const r = await planSync(api({ ok: true, total: 30, index: 3, frames: 124, stepping: true, finished: false, running: false }, seen), mtv(), lim);
  assert.equal(r.ok, true);
  assert.equal(r.duration, 124 / 24); assert.equal(r.start, (3 * 124) / 24);
  assert.ok(Math.abs(r.start - 15.5) < 1e-12);
  assert.match(r.text, /segment 4 of 30/);
  assert.match(seen[0], /\/ironleo78\/mtv\/segments\?/); assert.match(seen[0], /Next\+Segment\+On\+Run=true/);
});
await t("sync: no drift - segment 20 start is 20 x 5.1667, not 20 x 5.2", async () => {
  const r = await planSync(api({ ok: true, total: 40, index: 19, frames: 124, stepping: true, finished: false, running: false }), mtv(), lim);
  assert.ok(Math.abs(r.start - 98.1666666667) < 1e-6);
});
await t("sync: Next Segment OFF -> follows the Go-to counter (v0.2.2; it was start 0 until 0.2.1), duration unchanged", async () => {
  const r = await planSync(api({ ok: true, total: 30, index: 5, frames: 124, stepping: false, finished: false, running: false }), mtv(), lim);
  assert.ok(Math.abs(r.start - 5 * 124 / 24) < 1e-9); assert.equal(r.duration, 124 / 24);
  const r0 = await planSync(api({ ok: true, total: 30, index: 0, frames: 124, stepping: false, finished: false, running: false }), mtv(), lim);
  assert.equal(r0.start, 0); assert.deepEqual(r0.warn, []);
});
await t("sync: fresh counter (index 0) is segment 1", async () => {
  const r = await planSync(api({ ok: true, total: 30, index: 0, frames: 124, stepping: true, finished: false, running: false }), mtv(), lim);
  assert.equal(r.start, 0); assert.match(r.text, /segment 1 of 30/);
});
await t("sync: refused when running / finished / no total / backend error / network error", async () => {
  const base = { ok: true, total: 30, index: 3, frames: 124, stepping: true, finished: false, running: false };
  assert.match((await planSync(api({ ...base, running: true }), mtv(), lim)).text, /running/);
  assert.match((await planSync(api({ ...base, index: 30, finished: true }), mtv(), lim)).text, /Reset/);
  assert.equal((await planSync(api({ ...base, total: null }), mtv(), lim)).ok, false);
  assert.match((await planSync(api({ ok: false, error: "boom" }), mtv(), lim)).text, /boom/);
  assert.equal((await planSync(async () => { throw new Error("x"); }, mtv(), lim)).ok, false);
});
await t("sync: finished counter does NOT block when Next Segment is OFF (always segment 1)", async () => {
  const r = await planSync(api({ ok: true, total: 30, index: 30, frames: 124, stepping: false, finished: true, running: false }), mtv(), lim);
  assert.equal(r.ok, true); assert.equal(r.start, 0);
});
await t("sync: duration above the loader maximum is clamped with a warning", async () => {
  const r = await planSync(api({ ok: true, total: 5, index: 1, frames: 29 * 17 + 5 - 0, stepping: true, finished: false, running: false }), mtv(), lim);
  assert.equal(r.duration, 20); assert.ok(r.warn.length >= 1); assert.match(r.text, /clamped/);
});
// v0.1.9: the MTV can sit in a subgraph (or the loader can)
await t("collectNodes: the root graph, a subgraph node's own graph and the root's subgraphs map, each node once", () => {
  const inner = mtv({}, 21);
  const deep = mtv({ "Video File": "deep.mp4" }, 31);
  const deepGraph = { _nodes: [deep] };
  const subGraph = { _nodes: [inner, { id: 22, subgraph: deepGraph }] };
  const loader = { id: 1, comfyClass: "IronLeo78_MTV_PromptGenerator" };
  const root = { _nodes: [loader, { id: 2, subgraph: subGraph }], subgraphs: new Map([["a", subGraph], ["b", deepGraph]]) };
  const all = collectNodes(root, subGraph);
  assert.deepEqual(all.map((x) => x.id).sort((a, b) => a - b), [1, 2, 21, 22, 31]);
  assert.equal(gate("clip.mp4", all).mtv, inner);                  // found inside the subgraph
  assert.equal(gate("deep.mp4", all).mtv, deep);                   // and two levels down
  assert.equal(gate("clip.mp4", root._nodes).ok, false);           // what the old code searched: the root level only
});
await t("collectNodes: a plain object of subgraphs, a `nodes` list, cycles and missing graphs", () => {
  const g1 = { nodes: [mtv({}, 1)] };
  const g2 = { _nodes: [{ id: 2, subgraph: g1 }], subgraphs: { x: g1 } };
  g1.nodes.push({ id: 3, subgraph: g2 });                          // a loop must not hang
  assert.deepEqual(collectNodes(g2, null, undefined).map((x) => x.id).sort(), [1, 2, 3]);
  assert.deepEqual(collectNodes(), []);
});
await t("no polling while the browser tab is hidden (both panels)", () => {
  const nine = fs.readFileSync(new URL("../web/ironleo78_9images.js", import.meta.url), "utf8");
  const mtvjs = fs.readFileSync(new URL("../web/ironleo78_mtv.js", import.meta.url), "utf8");
  assert.match(nine, /setInterval\(\(\) => \{ if \(!document\.hidden\) updateSyncGate\(\); \}, 500\)/);
  assert.match(mtvjs, /const refresh = \(\) => \{\s*if \(typeof document !== "undefined" && document\.hidden\) return;/);
  assert.match(nine, /collectNodes\(app\.rootGraph \|\| app\.graph, node\.graph\)/);
});

console.log(`${n} tests passed`);
