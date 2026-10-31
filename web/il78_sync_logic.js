// IronLeo78 9-Images-to-batch-to-LLM - optional "Sync from MTV" logic (v0.0.2b).
// Pure functions, no imports, no DOM: the loader's JS calls them, tests/test_sync_logic.mjs runs them in plain node.
// Nothing here talks to the network except planSync(), and that only runs when the button is clicked.

export const MTV_NODE = "IronLeo78_MTV";
export const SEGMENT_ROUTE = "/ironleo78/mtv/segments";
export const FPS = 24;
// the MTV widgets the segment route needs (same list as MTV's own segment panel)
export const MTV_SEG_WIDGETS = ["Use Video", "Video File", "Custom Audio File", "Choose Audio latent", "duration", "Next Segment On Run"];

// "clip.mp4", "sub/clip.mp4 [input]" -> "sub/clip.mp4" (type suffix and spaces stripped)
export function normFile(v) {
  return String(v ?? "").trim().replace(/ \[(input|output|temp)\]$/, "").trim();
}
const widgetValue = (node, name) => node?.widgets?.find((w) => w.name === name)?.value;
const truthy = (v) => v === true || v === "true" || v === "True" || v === 1;

// v0.1.9: every node of the given graphs AND of all their subgraphs, each once. The frontend keeps a subgraph's nodes in their
// own graph (a subgraph node's `.subgraph`, or the root graph's `subgraphs` map), so an MTV inside a subgraph, or a loader
// inside one, was not found when only the loader's own graph was searched.
export function collectNodes(...graphs) {
  const out = [];
  const seenGraphs = new Set();
  const seenNodes = new Set();
  const listOf = (g) => (Array.isArray(g?._nodes) ? g._nodes : Array.isArray(g?.nodes) ? g.nodes : []);
  const subgraphsOf = (g) => {
    const s = g?.subgraphs;
    if (!s) return [];
    if (typeof s.values === "function") return [...s.values()];
    return typeof s === "object" ? Object.values(s) : [];
  };
  const walk = (g) => {
    if (!g || typeof g !== "object" || seenGraphs.has(g)) return;
    seenGraphs.add(g);
    for (const n of listOf(g)) {
      if (!n || seenNodes.has(n)) continue;
      seenNodes.add(n);
      out.push(n);
      if (n.subgraph) walk(n.subgraph);
    }
    for (const sg of subgraphsOf(g)) walk(sg);
  };
  graphs.forEach(walk);
  return out;
}

// v0.5.0: the presets were renamed "Category - Name". A workflow saved before holds the old numbered name ("1 - Replace main actor"): the
// new name when `value` is an old one (aliases = the presets route's "aliases" map), else null (nothing to change).
// v0.6.0 (sweep M1): `options` = the combo's list; when given, the new name must be in it (never switch to a name that is not offered).
export function presetAlias(value, aliases, options) {
  if (!value || !aliases || typeof aliases !== "object") return null;
  const next = aliases[value];
  if (typeof next !== "string" || !next || next === value) return null;
  if (Array.isArray(options) && !options.includes(next)) return null;
  return next;
}

// v0.4.14 (sweep N2): the nodes that are really IN the workflow: the graph's own nodes and, through each subgraph NODE (`.subgraph`),
// the nodes of the subgraphs actually placed. Unlike collectNodes it never reads a graph's `subgraphs` map, which can still hold the
// definition of a subgraph whose last instance was deleted (an MTV in there would count as "still there" and the models never freed).
export function liveNodes(graph) {
  const out = [];
  const seenGraphs = new Set();
  const listOf = (g) => (Array.isArray(g?._nodes) ? g._nodes : Array.isArray(g?.nodes) ? g.nodes : []);
  const walk = (g) => {
    if (!g || typeof g !== "object" || seenGraphs.has(g)) return;
    seenGraphs.add(g);
    for (const n of listOf(g)) {
      if (!n) continue;
      out.push(n);
      if (n.subgraph) walk(n.subgraph);
    }
  };
  walk(graph);
  return out;
}

// v0.1.12: "load the video once". When a video is picked / uploaded in one of the two nodes (the MTV's Video File or the
// loader's video), the same file is put in the other kind of node. Only a real file is copied (never "None" / empty: removing a
// video in one node leaves the other alone). Returns the nodes that were changed.
// v0.1.22: loading a video sets the MTV's "Choose Audio latent" to "Audio From Video" (the user can change it afterwards).
// Returns true when the value changed.
export const AUDIO_FROM_VIDEO = "Audio From Video";
export const AUDIO_MINIMAX = "MiniMax Audio";
export function setMtvWidget(mtv, name, value) {
  const a = mtv?.widgets?.find((x) => x.name === name);
  if (!a || a.value === value) return false;
  const opts = a.options?.values;
  if (Array.isArray(opts) && !opts.includes(value)) return false;      // a value this widget does not offer is never forced
  a.value = value;
  try { a.callback?.(value); } catch (e) { /* the value is set, the callback is cosmetic */ }
  return true;
}
export const setAudioMode = (mtv, value) => setMtvWidget(mtv, "Choose Audio latent", value);
// v0.3.7: an MTV that is set up for a SONG (Choose Audio latent = Custom Audio AND a Custom Audio File picked) is never switched automatically by a
// video load or a Mode change: that would silently drop the song. (A musician preset sets Custom Audio itself; leaving it puts the Mode audio back.)
export function isSongSetup(mtv) {
  if (widgetValue(mtv, "Choose Audio latent") !== "Custom Audio") return false;
  const f = normFile(widgetValue(mtv, "Custom Audio File"));
  return !!f && f.toLowerCase() !== "none";
}
export const useVideoAudio = (mtv) => (isSongSetup(mtv) ? false : setAudioMode(mtv, AUDIO_FROM_VIDEO));
// (v0.2.6 - v0.3.14: a Mode change sets the MTV's Choose Audio latent through applyPresetAudio below: v2v -> Audio From Video, i2v -> MiniMax Audio.)
// v0.1.24: the prompt box follows the Preset. `suggestions` = {preset: suggested prompt}. Returns the new text for the box, or null to
// leave it alone: only an EMPTY box or one that still holds some preset's suggestion is replaced (text the user wrote is never lost).
// v0.3.1: `force` (the user CHOSE a preset) fills the example even over text the user typed; v0.3.2: the node also forces it when the Mode changes.
// Without it only an empty box or an untouched suggestion is replaced. Choosing "None" (no example) never wipes typed text: it only clears an untouched suggestion.
export function suggestPrompt(current, suggestions, chosen, force = false) {
  const cur = String(current ?? "").trim();
  const known = Object.values(suggestions || {}).map((s) => String(s ?? "").trim()).filter(Boolean);
  const next = String(suggestions?.[chosen] ?? "").trim();
  if (force && next) return next === cur ? null : next;
  if (cur && !known.includes(cur)) return null;
  return next === cur ? null : next;
}
// v0.3.0: a MUSICIAN preset (singer, drummer, bassist, guitarist) starts the MTV from Choose Audio latent = Custom Audio and the matching
// Audio Stem (Vocals / Drums / Bass / Guitars). info = {audio, stem} of the chosen preset ("" when it has none), prev = what the
// previous preset applied (or null). v0.3.12: the first musician preset remembers what each MTV had before (`before`, saved with the workflow);
// leaving it gives THOSE values back (else the Mode's audio and Full), but only where the value is still the preset's own: a change made by
// hand in between is left alone. fromMode = the Mode was changed: the audio follows the preset if it has one, else the Mode (a song setup is kept).
// Returns what was applied (keep it for the next call). The user can change every value afterwards.
export function applyPresetAudio(nodes, mode, info, prev, fromMode = false) {
  const mtvs = (nodes || []).filter((n) => n && n.comfyClass === MTV_NODE);
  const modeAudio = mode === "i2v" ? AUDIO_MINIMAX : AUDIO_FROM_VIDEO;
  const cur = { audio: (info && info.audio) || "", stem: (info && info.stem) || "" };
  if (cur.audio) {
    // v0.3.12: remember what each MTV had BEFORE the (first) musician preset, so leaving it gives the user''s own settings back
    const before = {};
    for (const n of mtvs) {
      const key = String(n.id);
      const kept = prev && prev.audio && prev.before && prev.before[key];
      before[key] = kept || { audio: widgetValue(n, "Choose Audio latent"), stem: widgetValue(n, "Audio Stem") };
      setAudioMode(n, cur.audio);
      if (cur.stem) setMtvWidget(n, "Audio Stem", cur.stem);
    }
    cur.before = before;
    return cur;
  }
  const leaving = !!(prev && prev.audio);      // coming back from a musician preset
  if (leaving) {
    for (const n of mtvs) {
      const b = prev.before && prev.before[String(n.id)];
      // only what is still the preset''s own setting is put back (something the user changed by hand since is left alone)
      if (widgetValue(n, "Choose Audio latent") === prev.audio) {
        if (b && b.audio) {
          if (b.audio !== prev.audio && !setAudioMode(n, b.audio)) setAudioMode(n, modeAudio);      // (the same value: nothing to do; a value the widget does not offer: the Mode's audio)
        } else {
          setAudioMode(n, modeAudio);
        }
      }
      if (prev.stem && widgetValue(n, "Audio Stem") === prev.stem) setMtvWidget(n, "Audio Stem", (b && b.stem) || "Full");
    }
  } else if (fromMode) {
    for (const n of mtvs) if (!isSongSetup(n)) setAudioMode(n, modeAudio);
  }
  return cur;
}export const PROMPT_GEN_NODE = "IronLeo78_MTV_PromptGenerator";      // v0.1.18: the all-in-one sister node has the same loader UI
export const LOADER_NODES = [PROMPT_GEN_NODE];      // v0.1.21: the old standalone 9-Images node is gone
export function mirrorVideo(source, value, nodes, opts = {}) {      // opts.audio === false: do not touch Choose Audio latent (the generator is in i2v)
  const file = normFile(value);
  if (!file || file === "None") return [];
  const toLoaders = source?.comfyClass === MTV_NODE ? true : LOADER_NODES.includes(source?.comfyClass) ? false : null;
  if (toLoaders === null) return [];
  const changed = [];
  for (const n of nodes || []) {
    if (!n || n === source || (toLoaders ? !LOADER_NODES.includes(n.comfyClass) : n.comfyClass !== MTV_NODE)) continue;
    if (toLoaders) {
      if (normFile(widgetValue(n, "video")) === file || typeof n._il78?.setVideo !== "function") continue;
      n._il78.setVideo(file);
    } else {
      const w = n.widgets?.find((x) => x.name === "Video File");
      if (!w) continue;
      const audioChanged = opts.audio === false ? false : useVideoAudio(n);       // v0.1.22: a video was loaded -> the MTV takes its sound from the video
      if (normFile(w.value) === file) { if (audioChanged) changed.push(n); continue; }
      if (Array.isArray(w.options?.values) && !w.options.values.includes(file)) w.options.values.push(file);   // a fresh upload is not in the list yet
      w.value = file;
      w.__il78Mirroring = true;                     // the MTV's own callback wrapper must not mirror this back
      try { w.callback?.(file); } catch (e) { /* the value is set, the callback is cosmetic */ }
      w.__il78Mirroring = false;
    }
    changed.push(n);
  }
  return changed;
}

// v0.3.5: SYNC IN i2v (no video): only the clip length is copied, from the MTV's `duration` widget (the LLM writes its timeline to the Prompt
// Generator's Duration, so the two must be equal). Needs an MTV node, no video, no request.
export function gateI2v(nodes) {
  const mtvs = (nodes || []).filter((n) => n && n.comfyClass === MTV_NODE && n.mode !== 2 && n.mode !== 4);
  if (!mtvs.length) return { ok: false, reason: "No MTV node in this graph." };
  return { ok: true, mtv: mtvs[0], note: mtvs.length > 1 ? `${mtvs.length} MTV nodes; synced with #${mtvs[0].id}.` : "" };
}
// v0.3.10: the length the MTV REALLY renders: its frame count is padded up so that frames % 17 == 5 (same rule as mtv.py _minimax_frames),
// e.g. 5 s -> 124 frames = 5.1667 s, 7.5 s -> 192 frames = 8 s.
export function paddedSeconds(seconds) {
  const base = Math.max(5, Math.round(seconds * 24));
  return (base + ((5 - (base % 17)) % 17 + 17) % 17) / 24;
}
export function planSyncI2v(mtv, limits) {
  const d = Number(widgetValue(mtv, "duration"));
  if (!(d > 0)) return { ok: false, text: "The MTV has no usable duration." };
  const maxD = limits?.maxDuration ?? 20, minD = limits?.minDuration ?? 1;
  let duration = paddedSeconds(d);
  const warn = [];
  if (duration > maxD) {                       // padding alone may pass the loader maximum (20 s -> 20.04 s): that is not worth a warning
    if (d > maxD) warn.push(`Duration clamped to ${maxD}s (loader maximum)`);
    duration = maxD;
  }
  if (duration < minD) { duration = minD; warn.push(`Duration raised to ${minD}s (loader minimum)`); }
  const r2 = (x) => Math.round(x * 100) / 100;
  return { ok: true, duration, warn, text: `Synced: duration ${r2(duration)}s (the MTV's ${r2(d)}s, padded to the frames it renders)` + (warn.length ? `  ⚠ ${warn.join("; ")}` : "") };
}

// v0.3.5: true when a MTV node is set to Custom Audio but has no Custom Audio File (a musician preset is driven by that file).
export function customAudioMissing(nodes) {
  return (nodes || []).some((n) => {
    if (!n || n.comfyClass !== MTV_NODE) return false;
    if (widgetValue(n, "Choose Audio latent") !== "Custom Audio") return false;
    const f = normFile(widgetValue(n, "Custom Audio File"));
    return !f || f === "None";
  });
}

// Local checks only (no request). `nodes` = the graph's node list. Returns { ok, mtv, reason, note }.
export function gate(loaderVideo, nodes) {
  const mine = normFile(loaderVideo);
  if (!mine) return { ok: false, reason: "Load a video in this node first." };
  const mtvs = (nodes || []).filter((n) => n && n.comfyClass === MTV_NODE && n.mode !== 2 && n.mode !== 4);   // not muted / bypassed
  if (!mtvs.length) return { ok: false, reason: "No MTV node in this graph." };
  const sameFile = mtvs.filter((n) => normFile(widgetValue(n, "Video File")) === mine);
  if (!sameFile.length) return { ok: false, reason: "The MTV node has another Video File (or none). Load the same file in both nodes." };
  const usable = sameFile.filter((n) => {
    if (truthy(widgetValue(n, "Use Video"))) return true;
    const a = widgetValue(n, "Choose Audio latent");
    return a === false || a === "Audio From Video";       // old workflows stored false = Audio From Video
  });
  if (!usable.length) return { ok: false, reason: "MTV is not stepping through this video: turn Use Video ON, or Use Video OFF + Choose Audio latent = Audio From Video." };
  const mtv = usable[0];
  return { ok: true, mtv, note: usable.length > 1 ? `${usable.length} MTV nodes use this file; synced with #${mtv.id}.` : "" };
}

// Click time: ask MTV's read-only route and turn the answer into the values for THIS loader (the NEXT segment).
// limits = { maxStart, maxDuration } = the loader widgets' maxima. Returns { ok, start, duration, text } or { ok:false, text }.
export async function planSync(fetchApi, mtv, limits) {
  const qs = new URLSearchParams();
  for (const n of MTV_SEG_WIDGETS) { const v = widgetValue(mtv, n); qs.set(n, v === undefined || v === null ? "" : String(v)); }
  let info;
  try { info = await (await fetchApi(`${SEGMENT_ROUTE}?${qs.toString()}`)).json(); }
  catch (e) { return { ok: false, text: "Could not reach the MTV segment route." }; }
  if (!info || !info.ok) return { ok: false, text: `MTV could not read the segment info${info && info.error ? `: ${info.error}` : "."}` };
  if (info.running) return { ok: false, text: "MTV is running right now. Sync again when the Run has ended." };
  if (info.total === null || info.total === undefined) return { ok: false, text: "MTV has no segment total for this selection (no video found)." };
  if (info.stepping && info.finished) return { ok: false, text: `All ${info.total} MTV segments are done. Press Reset in MTV, then sync again.` };
  const frames = Number(info.frames);
  if (!(frames > 0)) return { ok: false, text: "MTV answered without a frame count." };
  // v0.2.2: Sync follows the counter (the Go-to position) whether or not Next Segment On Run is ON, so the user can pick any scene of a
  // long video. v0.2.3: the MTV's own OFF Run now repeats that same segment. A FINISHED OFF counter (index at the total) means nothing
  // to follow: segment 1, exactly what the MTV makes then.
  const saved = Math.max(0, Number(info.index) || 0);
  const index = (!info.stepping && info.finished) ? 0 : saved;
  let duration = frames / FPS;                  // full precision: 5.1667 must stay 5.1667 (5.2 would drift ~0.7 s by segment 20)
  let start = (index * frames) / FPS;
  const warn = [];
  if (limits && duration > limits.maxDuration) { duration = limits.maxDuration; warn.push(`Duration clamped to ${limits.maxDuration}s (loader maximum): the loader sees only part of the segment`); }
  if (limits && start > limits.maxStart) { start = limits.maxStart; warn.push(`Start_From clamped to ${limits.maxStart}s (loader maximum)`); }
  const r2 = (x) => Math.round(x * 100) / 100;
  return {
    ok: true, start, duration, warn,
    text: `Synced: segment ${index + 1} of ${info.total}  (${r2(start)}s + ${r2(duration)}s)` + (warn.length ? `  ⚠ ${warn.join("; ")}` : ""),
  };
}
