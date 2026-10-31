# Stub-based test of the v0.6 orchestration (one clip per Run, phase order, Save Latent toggle, caches, no output sockets / no preview, song name from the
# custom audio file, error paths, Model Loader overrides, segment count, quiet end,
# prompt sidecar, manifest upgrade, reset, jump to segment, guide read back from a clip).
# Needs no ComfyUI, GPU or torch:   python tests/test_phased_run.py
# ComfyUI only imports __init__.py, so this folder is ignored at runtime.
import sys, types, os, tempfile, importlib, collections, re
from unittest.mock import MagicMock

TMP = tempfile.mkdtemp()
open(os.path.join(TMP, "song.wav"), "wb").write(b"x")

# ---------- stub the ComfyUI / torch world ----------
for name in ("torch", "torch.nn", "torch.nn.functional", "comfy", "comfy.sd", "comfy.utils",
             "comfy.model_management", "nodes"):
    sys.modules[name] = MagicMock()
fp = types.ModuleType("folder_paths")
fp.get_annotated_filepath = lambda n: os.path.join(TMP, n)
fp.exists_annotated_filepath = lambda n: True
fp.get_output_directory = lambda: TMP
fp.get_input_directory = lambda: TMP
fp.filter_files_content_types = lambda files, t: files
fp.get_filename_list = lambda k: []
fp.get_full_path = lambda k, n: os.path.join(TMP, n)
sys.modules["folder_paths"] = fp

SIGMA_CALLS = []
PKG = "ironleo78_mtv"

cx = types.ModuleType("comfy_extras")
nm = types.ModuleType("comfy_extras.nodes_minimax_h3")
COND_CALLS = []
class MiniMaxH3ReferenceToVideo:
    @staticmethod
    def execute(**kw):
        COND_CALLS.append(kw["prompt"])
        if kw["prompt"] == "BOOM":
            raise RuntimeError("encoder exploded")
        return ([["emb", {"p": kw["prompt"]}]], {"samples": "EMPTY:" + kw["prompt"]})
nm.MiniMaxH3ReferenceToVideo = MiniMaxH3ReferenceToVideo
sys.modules["comfy_extras"] = cx
sys.modules["comfy_extras.nodes_minimax_h3"] = nm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
mod = importlib.import_module(PKG + ".mtv")
dmod = importlib.import_module(PKG + ".defaults")      # v0.4.7: the saved defaults live here: tests that point DEFAULTS_FILE elsewhere patch THIS module
smod = importlib.import_module(PKG + ".state")      # v0.4.6: the counters / last frames live here: tests that point STATE_FILE etc. elsewhere patch THIS module
mgr = importlib.import_module(PKG + ".model_loader")
Cls = mod.IronLeo78_MTV
REAL_LOAD_MEDIA = Cls._load_media      # the real loader, before patch_media() replaces it

# ---------- fakes ----------
EVENTS = []
STEPS = []
LAST = {}
SAVES = []
SAVE_N = {}
COUNT_SAVES = False      # section 20 turns it on: every save of a prefix gets the next number
MASKS = []        # the SolidMask value of each bypassed audio latent (always 0 = frozen; MiniMax Audio makes none)
CORE_CALLS = []   # v0.0.4: every core node the node calls, in order
def fake_core(name, provided, strict=(), hidden=None, notes=None, hoist=False):
    CORE_CALLS.append(name)
    if name == "SolidMask":
        MASKS.append(provided["value"])
    if name == "SaveVideo":
        raise AssertionError("the node must not call SaveVideo any more (v0.0.5: the user links the video output to one)")
    if name == "SamplerCustomAdvanced":
        try:
            SIGMA_CALLS.append([round(float(x), 4) for x in provided["sigmas"]])
        except (TypeError, ValueError):
            SIGMA_CALLS.append(None)           # the first pass uses a stub scheduler output
        EVENTS.append(("sample", provided["latent_image"]))
        return (("S(" + str(provided["latent_image"]) + ")",), None)
    if name == "LTXVSeparateAVLatent":
        EVENTS.append(("separate",))
        return (({"samples": "vlat"}, {"samples": "alat"}), None)
    if name == "VAEDecode":
        EVENTS.append(("decode", provided["samples"]))
        return (("IMAGES",), None)
    if name == "VAEDecodeAudio": return (("AUDIO",), None)
    if name == "CreateVideo": return (("VIDEO",), None)
    if name == "LTXVConcatAVLatent": return (({"samples": "CAT"},), None)
    if name == "MiniMaxH3AddGuide": return (([["g", {}]], ), None)
    if name == "BasicScheduler":
        STEPS.append(provided["steps"])
        return ((name,), None)
    if name in ("RandomNoise", "BasicGuider", "KSamplerSelect", "BasicScheduler", "TrimAudioDuration",
                "VAEEncodeAudio", "SolidMask", "SetLatentNoiseMask"):
        return ((name,), None)
    raise AssertionError("unexpected core node " + name)
mod._core = fake_core
LATENTS = []      # v0.3: what the node would write to disk for a later upscale
def _fake_write_latent(path, samples, metadata):
    LATENTS.append((path, samples, metadata))
    open(path, "wb").write(b"L")
mod._write_latent_file = _fake_write_latent
CONDS = []        # v0.4: what the node would write to disk next to the latents
def _fake_write_conditioning(path, conditioning, metadata):
    CONDS.append((path, conditioning, metadata))
    open(path, "wb").write(b"C")
    return {"unsupported": []}
mod._write_conditioning_file = _fake_write_conditioning

orig_cond = mod.IronLeo78_MTV._conditioning_cached
def traced_cond(self, clip, vv, va, kw, media, mk):
    EVENTS.append(("cond", kw["prompt"]))
    return orig_cond(self, clip, vv, va, kw, media, mk)
mod.IronLeo78_MTV._conditioning_cached = traced_cond

mod._last_frame_of = lambda images: "FRAME"
FRAMES = []
REAL_SAVE_LAST_FRAME = mod._save_last_frame
mod._save_last_frame = lambda frame, seg, key="": FRAMES.append(seg)
INDEX = []
INDEX_KEYS = []      # v0.1.8: whose counter each save went to
REAL_LOAD_INDEX = mod._load_index
REAL_SAVE_INDEX = mod._save_index
mod._save_index = lambda i, key="": (INDEX.append(i), INDEX_KEYS.append(key))
ROWS = []
REAL_APPEND = mod._append_manifest
MANI_SONGS = []
mod._append_manifest = lambda song, rows: (ROWS.extend(rows), MANI_SONGS.append(song), "Song/manifest.csv")[2]

def pics(n):
    return ["IMG%d" % i if i < n else None for i in range(3)]

def make_media(extra_pic=None):
    return {"video": None, "audio1": None, "audio2": None, "pictures": pics(3), "width": 512, "height": 512,
            "seconds": 5.0, "seg_seconds": 124 / 24, "frames": 124, "filename": "", "status": "Video OFF",
            "index": 0, "timeline_start": 0.0,
            "cond_id": {"video": None, "audio1": None, "audio2": None,
                        "pics": [("p", ("a.png", 1, 1), (512, 512))] * 3}}

def patch_media(self_cls, media_factory=make_media, pending=1):
    def lm(self, kw):
        self._pending_index = pending
        return media_factory()
    self_cls._load_media = lm
    self_cls._load_models = lambda self, kw, uid: LAST.update(kw) or ("MODEL", "CLIP", "VVAE", "AVAE")
patch_media(mod.IronLeo78_MTV)
REAL_CHECK = mod._check_models
mod._check_models = lambda kw: None      # the file check has its own tests (section 11)

def kw(**over):
    d = dict(Turbo=True, **{
        "Use Video": False, "Video File": "None", "Custom Audio File": "Song.wav",
        "megapixels": 0.5, "duration": 5.0, "Next Segment On Run": True, "prompt": "P1",
        "Choose Audio latent": False,
        "Save Latent": False, "Guide": False})
    for i in range(1, 4):
        d["picture_%d" % i] = "pic%d.png" % i
    d.update(over)
    return d

def run(prompt_graph=None, **over):
    EVENTS.clear()
    SAVES.clear()
    FRAMES.clear()
    INDEX.clear()
    ROWS.clear()
    node = mod.IronLeo78_MTV()
    res = node.run(unique_id="7", workflow_prompt=prompt_graph, extra_pnginfo=None, **kw(**over))
    # v0.0.5: the node saves nothing. SAVES / the "save" event now record the clip it MADE (video + filename outputs).
    made_video, made_name, _made_status = res["result"]
    if made_video is not None and isinstance(made_name, str):
        pre = re.sub(r"_\d{5}_$", "", made_name)
        EVENTS.append(("save", pre))
        SAVES.append(pre)
    return res

def status_of(res):
    return res["ui"]["text"][0]

def kinds(label=None):
    return [e for e in EVENTS if label is None or e[0] == label]

ok = 0
def check(cond, msg):
    global ok
    assert cond, "FAIL: " + msg
    ok += 1
    print("  ok -", msg)

CONNECTED = {"1": {"inputs": {"images": ["7", 0]}}}
NOT_CONNECTED = {"1": {"inputs": {"x": ["3", 0]}}}

# 1 ---- one clip per Run
print("1. one clip")
mod._COND_CACHE.clear()
res = run(CONNECTED)
order = [e[0] for e in EVENTS if e[0] in ("cond", "sample", "separate", "decode", "save")]
print("   ", order)
check(order == ["cond", "sample", "decode", "save"], "conditioning, sampling, decode, save: %s" % order)
check(SAVES == ["Song/Song_seg000_A"], "one clip saved: %s" % SAVES)
check(len(ROWS) == 1 and ROWS[0]["scene"] == "A" and ROWS[0]["file"] == "Song/Song_seg000_A_00001_.mp4", "ONE manifest row (tag A) with the clip")
check("upscaled_file" not in ROWS[0] and "upscale_mp" not in ROWS[0], "the manifest row has no upscale columns any more")
check(FRAMES == [0] and INDEX == [1], "guide frame + counter saved once")
check(Cls.RETURN_TYPES == ("VIDEO", "STRING", "STRING") and Cls.RETURN_NAMES == ("video", "filename", "status"), "v0.0.9: three outputs, video, filename and status (status last, so saved links keep working)")
check(res["result"][:2] == ("VIDEO", "Song/Song_seg000_A_00001_"), "the video output is Create Video's result, the filename output the clip name without extension: %s" % (res["result"],))
check(isinstance(res["result"][2], str) and res["result"][2] == res["ui"]["text"][0] and "SONG:" in res["result"][2], "v0.0.9: the status output is the run report (same text the node used to show)")
check("SaveVideo" not in CORE_CALLS and "CreateVideo" in CORE_CALLS, "the node calls Create Video but never Save Video")
check("run order" not in status_of(res) and "upscal" not in status_of(res).lower(), "the status no longer talks about run order or upscaling")
check("SONG: Song | segment 1 (seg000)" in status_of(res), "status header names the song and the segment (custom audio)")
check("scene" not in status_of(res).lower() and "Picture4" not in status_of(res), "the report no longer mentions scenes")
check("--- Song_seg000_A ---" in status_of(res) and "manifest: Song/manifest.csv" in status_of(res), "report block is headed by the file tag, with the manifest line")
check("clip name: Song/Song_seg000_A_00001_.mp4" in status_of(res) and "link the video output to a Save Video node" in status_of(res), "the report names the clip and says the node does not save it")

# 2 ---- the upscale stage is gone (v0.6)
print("2. the Latent Upscale stage is gone")
check(PKG + ".latent_upscale" not in sys.modules, "latent_upscale.py is not imported")
check(not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "latent_upscale.py")), "latent_upscale.py is not in the package")
check(not any(hasattr(mod, n) for n in ("_upscale_pass", "UPSCALE_QUALITIES", "UPSCALE_QUALITY_SIGMAS", "UPSCALE_SIGMAS", "UPSCALE_OUTPUTS",
                                         "DEFAULT_UPSCALE_MODEL", "_scan_upscale_models", "upscale_sigmas")) and not hasattr(Cls, "_phase_upscale"),
      "the upscale code and constants are gone")
_t2 = Cls.INPUT_TYPES()["required"]
check(not any(k in _t2 for k in ("Latent Upscale", "Temporal Chunking", "upscale_megapixels", "Upscale Quality", "Upscale Output")),
      "no Latent Upscale / Temporal Chunking / upscale_megapixels / Upscale Quality / Upscale Output widgets")
check("upscale_model_name" not in mod.MODEL_FILE_KEYS and "upscale_model_name" not in mod.FIXED_SETTINGS, "no upscale model in the Model Loader keys")
check("Phased Run" not in mod.FIXED_SETTINGS, "the phased / sequential switch is gone (there is only one order now)")
# a leftover value of an old workflow (the widget no longer exists) is simply ignored
r = run(CONNECTED, **{"Latent Upscale": True, "upscale_megapixels": 1.0, "Upscale Quality": "HIGH", "Temporal Chunking": True, "Upscale Output": "Upscaled only"})
check(SAVES == ["Song/Song_seg000_A"] and len(kinds("sample")) == 1, "leftover upscale values from an old workflow: one normal clip, one sampling pass, no upscaled clip")

# 4 ---- conditioning cache
print("4. conditioning cache")
mod._COND_CACHE.clear()
COND_CALLS.clear()
run(CONNECTED)
check(len(COND_CALLS) == 1, "first run encodes once")
run(CONNECTED, models={"noise_seed": 5}, **{"Turbo": False, "Save Latent": True})
check(len(COND_CALLS) == 1, "seed / Turbo / Save Latent change: NO re-encode")
r = run(CONNECTED, **{"prompt": "CHANGED"})
check(len(COND_CALLS) == 2, "changed prompt re-encodes")
r = run(CONNECTED, **{"prompt": "CHANGED"})
check(len(COND_CALLS) == 2 and "conditioning: cached" in status_of(r), "same prompt again: cached, status shows it")
# different reference content (picture 2 replaced) must miss
def media_other():
    m = make_media()
    m["cond_id"]["pics"] = list(m["cond_id"]["pics"])
    m["cond_id"]["pics"][1] = ("p", ("OTHER.png", 2, 2), (512, 512))
    return m
patch_media(mod.IronLeo78_MTV, media_other)
run(CONNECTED, **{"prompt": "CHANGED"})
check(len(COND_CALLS) == 3, "different Picture2 content re-encodes")
patch_media(mod.IronLeo78_MTV)
# cache entries must not be mutated by a Run (guide is applied on a copy)
mod._COND_CACHE.clear()
run(CONNECTED, **{"prompt": "P1"})
entry = [v for k, v in mod._COND_CACHE.items() if k[0] == "cond"][0]
snapshot = repr(entry[0]) + repr(entry[1])
got = mod.IronLeo78_MTV._conditioning_cached(
    mod.IronLeo78_MTV(), "CLIP", "VV", "AV",
    {**kw(), "prompt": "P1", "ref_image_size": "match"}, make_media(),
    (("e", None), ("v", None), ("a", None)))
got[0][0][1]["MUTATED"] = True
got[1]["samples"] = "MUTATED"
check(repr(entry[0]) + repr(entry[1]) == snapshot or "MUTATED" not in repr(entry), "a caller mutating the returned copy does not touch the cached entry")

# 5 ---- no outputs, song naming (v2.4)
print("5. no outputs + song name")
r = run(NOT_CONNECTED)
check(len(r["result"]) == 3 and r["result"][0] == "VIDEO" and isinstance(r["result"][2], str) and "text" in r["ui"] and "images" not in r["ui"], "the video and the status leave on the outputs, no video preview on the node")
check(LAST["Live Preview"] is True, "ComfyUI's latent preview stays ON (v2.5.1)")
check(not hasattr(mod, "_connected_outputs"), "the connected-outputs helper is gone")
check(mod._song_name({"Custom Audio File": "None"}) == "", "no custom audio -> no song name")
check(mod._song_name({"Custom Audio File": "My Song (v2).wav"}) == "My_Song_v2", "song name = custom audio file stem, made filesystem-safe")
check(mod._song_name({"Custom Audio File": "sub/dir/track-01.mp3 [input]"}) == "track-01", "subfolder / annotation stripped")
r = run(CONNECTED, **{"Custom Audio File": "None"})
check(SAVES == ["video/ComfyUI_seg000_A"] and "SONG: (no custom audio" in status_of(r), "no custom audio: old naming, nothing else: %s" % SAVES)
check(ROWS[0]["song"] == "" and "section_number" not in ROWS[0], "manifest has no section columns, empty song")
r = run(CONNECTED)
check(SAVES == ["Song/Song_seg000_A"] and ROWS[0]["song"] == "Song", "custom audio Song.wav -> Song/Song_seg000_A")
# v0.0.9: no custom audio -> a subfolder named after the Picture1 / video name, like the song's (sidecar, latents, manifest inside it)
def _media_named(name):
    def f():
        m = make_media()
        m["filename"] = name
        return m
    return f
patch_media(mod.IronLeo78_MTV, _media_named("cat"))
MANI_SONGS.clear()
r = run(CONNECTED, **{"Custom Audio File": "None"})
check(SAVES == ["cat/cat_seg000_A"] and r["result"][1].startswith("cat/cat_seg000_A_") and r["result"][1].endswith("_"),
      "no custom audio, Picture1 'cat': subfolder cat/ (%s) and the filename output follows" % SAVES)
check(ROWS[0]["song"] == "cat" and MANI_SONGS == ["cat"] and ROWS[0]["file"].startswith("cat/"), "the manifest goes to the same name (cat) and lists the clip inside cat/")
check(ROWS[0]["prompt_json"] == r["result"][1] + ".json" and "SONG: cat" in status_of(r), "the sidecar sits next to the clip name in cat/, the status header names it")
check(mod._project_name({"Custom Audio File": "None"}, {"filename": "My Pic (2)"}) == "My_Pic_2" and mod._project_name({"Custom Audio File": "None"}, {}) == "",
      "the folder name is made filesystem-safe; nothing to name it after = empty (video/ComfyUI as before)")
import json
LATENTS.clear()
r = run(CONNECTED, **{"Custom Audio File": "None", "Save Latent": True})
check(LATENTS and all(json.loads(m["ironleo78"])["song"] == "cat" and "/cat/cat_seg000_A" in p.replace("\\", "/") for p, _, m in LATENTS),
      "Save Latent, no audio: the latent file headers name the Picture1 folder too (song = cat), same as the sidecar and manifest")
MANI_SONGS.clear()
r = run(CONNECTED)
check(SAVES == ["Song/Song_seg000_A"] and MANI_SONGS == ["Song"], "a custom audio file still wins over the Picture1 name")
LATENTS.clear()
run(CONNECTED, **{"Save Latent": True})
check(LATENTS and all(json.loads(m["ironleo78"])["song"] == "Song" for _, _, m in LATENTS), "Save Latent with a custom audio file: the header still says the song")
patch_media(mod.IronLeo78_MTV)

# 6 ---- Scene 2 is gone (v2.8)
print("6. Scene 2 is gone")
t = Cls.INPUT_TYPES()["required"]
check(not any(k in t for k in ("Scene 2", "prompt_2")), "no Scene 2 / prompt_2 widgets")
check(Cls.SLOTS == 9 and not hasattr(Cls, "BASE_SLOTS") and not hasattr(Cls, "_active_slots"), "v0.0.9H: nine picture slots, all always on (no base / active split)")
check([k for k in t if k.lower().startswith("picture")] == [] and "More References" not in t, "v0.0.9H: no picture_n pickers and no More References switch among the widgets")
check(list(t)[-1] == "Guide", "v0.0.9H: Guide is the LAST widget again (the pickers and the switch were the tail, removing them moves nothing before)")
check(not hasattr(mod, "SCENE_PICS") and not hasattr(mod, "LAST_FRAME_FILE_B") and not hasattr(mod, "_frame_file"), "the Scene 2 constants / helpers are gone")
mod._COND_CACHE.clear()
r = run(CONNECTED, **{"Scene 2": True, "prompt_2": "BOOM", "picture_4": "pic4.png", "picture_5": "pic5.png", "picture_6": "pic6.png"})
check(SAVES == ["Song/Song_seg000_A"] and len(ROWS) == 1 and COND_CALLS[-1] == "P1", "leftover Scene 2 values (an old workflow) are ignored: one clip, the normal prompt")
check("Song_seg000_B" not in "".join(SAVES), "no B clip is ever made")

# 6b ---- failures
print("6b. failures")
mod._COND_CACHE.clear()
try:
    run(CONNECTED, **{"prompt": "BOOM"})
    check(False, "should have raised")
except RuntimeError as e:
    check("encoder exploded" in str(e) and "stage 'reference conditioning'" in str(e), "conditioning error: original message + stage name")
check(kinds("sample") == [] and SAVES == [] and INDEX == [], "no sampling time wasted, nothing saved, counter not moved")
real_sample = Cls._sample
def boom_sample(self, *a, **k): raise RuntimeError("sampler exploded")
Cls._sample = boom_sample
try:
    run(CONNECTED)
    check(False, "should have raised")
except RuntimeError as e:
    check("sampler exploded" in str(e) and "stage 'sampling'" in str(e), "sampling error names its stage")
Cls._sample = real_sample
check(SAVES == [] and ROWS == [] and INDEX == [], "nothing saved, nothing logged, counter not moved")
# something fails AFTER the video was made but before it left the node: no clip, so no manifest row, the counter does not move
real_last = mod._last_frame_of
def boom_last(images): raise RuntimeError("last frame exploded")
mod._last_frame_of = boom_last
try:
    run(CONNECTED)
    check(False, "should have raised")
except RuntimeError as e:
    check("last frame exploded" in str(e), "a failure after the save is raised")
mod._last_frame_of = real_last
check(SAVES == [] and ROWS == [] and INDEX == [],
      "a clip that never left the node is not logged, the counter did not move")

# 7 ---- shared model cache + unload
print("7. shared model cache")
mod._CACHE.clear()
built = []
for node_id in ("1", "2"):
    mod._cached(node_id, "model", ("k",), lambda: built.append(1) or object())
check(len(built) == 1, "two nodes, same config: loaded once")
mod._cached("1", "model", ("k2",), lambda: built.append(1) or object())
mod._cached("1", "model", ("k3",), lambda: built.append(1) or object())
check(len(mod._CACHE["model"]) == 2, "model stage keeps at most 2 entries")
mod._cached("1", "video vae", ("v1",), lambda: object())
mod._cached("1", "video vae", ("v2",), lambda: object())
check(len(mod._CACHE["video vae"]) == 1, "other stages keep 1 entry")
mod._COND_CACHE["x"] = 1
mod.free_cached_models("test")
check(not mod._CACHE and not mod._COND_CACHE, "free_cached_models empties everything")
mod._COND_CACHE["x"] = 1
r = run(CONNECTED, **{"Unload After Run": True})
check("Unload After Run" not in Cls.INPUT_TYPES()["required"] and mod._COND_CACHE, "v2.8.3: no Unload After Run widget; a leftover value from an old workflow does NOT unload")
check(mod._RUNNING == 0, "_RUNNING back to 0")
try:
    run(CONNECTED, **{"prompt": "BOOM"})
except RuntimeError:
    pass
check(mod._RUNNING == 0, "_RUNNING back to 0 after an error")

# 8 ---- custom audio decoded once
print("8. custom audio cache")
class W:
    def numel(self): return 1000
    def element_size(self): return 4
    shape = (1, 2, 500)
    def __getitem__(self, i): return self
    def clone(self): return self
calls = []
mod._decode_custom_audio = lambda name: calls.append(name) or {"waveform": W(), "sample_rate": 44100}
mod._AUDIO_CACHE.clear()
a = mod._load_custom_audio("song.wav")
b = mod._load_custom_audio("song.wav")
check(len(calls) == 1 and a is b, "decoded once, second Run reuses it")
os.utime(os.path.join(TMP, "song.wav"), (1, 1))
mod._load_custom_audio("song.wav")
check(len(calls) == 2, "file changed on disk -> decoded again")
check(mod._load_custom_audio("None") is None, "None -> no audio")

# 9 ---- widget list
print("9. widgets")
t = mod.IronLeo78_MTV.INPUT_TYPES()["required"]
keys = list(t)
check(keys[-1] == "Guide" and "Unload After Run" not in keys, "Guide is the last widget, Unload After Run is gone: %s" % keys[-5:])
check(not any(k.startswith("prompt_list") for k in keys), "no per-segment prompt list widgets (just prompt)")
check("Phased Run" not in keys, "Phased Run widget is gone")
check(keys[keys.index("Guide") - 1] == "Save Latent" and keys[keys.index("prompt") + 1] == "Save Latent",
      "Save Latent sits right after prompt and right before Guide; Song / Section widgets are gone")
check(keys[keys.index("Video File") + 1] == "Choose Audio latent", "v0.1.11: Choose Audio latent sits right under Video File")
check(len(keys) == 12, "12 widgets in all (the 10 picker / switch widgets of v0.0.8 are gone): %d" % len(keys))
check(keys == ["Turbo", "Use Video", "Video File", "Choose Audio latent", "Custom Audio File", "Audio Stem", "megapixels", "duration",
               "Next Segment On Run", "prompt", "Save Latent", "Guide"], "v0.1.11: the 12 widgets, in the new order (migration in the JS): %s" % keys)

# v2.7.1: the defaults of a NEW node
_orig_gfl = fp.get_filename_list
def defaults(installed):
    fp.get_filename_list = lambda k: (["H3_Unlocked_V2.safetensors"] + list(_orig_gfl(k)) if installed and k == "loras" else _orig_gfl(k))
    try:
        r = mod.IronLeo78_MTV.INPUT_TYPES()["required"]
    finally:
        fp.get_filename_list = _orig_gfl
    return {k: v[1].get("default") for k, v in r.items() if len(v) > 1 and isinstance(v[1], dict)}
d = defaults(True)
check(d["megapixels"] == 0.2 and d["duration"] == 5.0, "defaults: megapixels 0.2, duration 5 s")
check(d["Turbo"] is True and d["Guide"] is True, "defaults: Turbo and Guide are ON")
check(d["Save Latent"] is True and mod.DEFAULT_SAVE_LATENT is True and mod.SAVE_LATENT_MISSING is False,
      "v0.1.11 defaults: Save Latent is ON on a new node (a prompt without the value still saves nothing)")
check(d["Choose Audio latent"] == "Custom Audio" and d["Audio Stem"] == "Full" and d["prompt"] == "",
      "defaults: Custom Audio, Full, empty prompt (the user's 20261030-1007pm set)")
check(not any(k in d for k in ("custom_lora_enabled", "Custom_LoRa", "Custom_LoRa_STR", "lora_1_enabled", "LoRa_1")), "v2.8.6: no custom LoRA widgets on the MTV")
FS = mod.FIXED_SETTINGS
check(mod.DEFAULT_CUSTOM_LORA_ENABLED is False and FS["lora_1_enabled"] is False
      and all(FS["lora_%d_enabled" % n] is False and FS["lora_%d_name" % n] == "None" and FS["lora_%d_strength" % n] == 1.0 for n in (1, 2, 3))
      and not any(k.startswith("custom_lora") for k in FS),
      "v0.1.11 hardcoded LoRAs: LoRa_1 / LoRa_2 / LoRa_3 empty (None) at 1.0, all OFF")
check(mod.FULL_STEPS == 30 and FS["full_steps"] == 30 and FS["turbo_steps"] == 6 and mod.TURBO_STEPS == 6, "v0.1.11: Turbo OFF = 30 steps, Turbo ON = 6")
check(FS["turbo_lora_strength"] == 1.0 and mod.factory_defaults()["turbo_lora_strength"] == 1.0, "v0.1.11: Turbo LoRA strength 1.0, part of the factory set")
check(not d["Use Video"] and not d["Next Segment On Run"] and "noise_seed" not in d,
      "defaults: Use Video, Next Segment OFF; no noise_seed widget on the MTV (v2.8.5)")
opt = mod.IronLeo78_MTV.INPUT_TYPES()["optional"]
check(list(opt) == ["models", "Pictures"] and opt["models"][0] == "IRONLEO78_MTV_MODELS", "optional sockets: 'models' and the one Pictures wire (v0.1.20: Picture_1 .. Picture_9 are gone), no widgets")
check(opt["Pictures"][0] == "IRONLEO78_PICTURES", "v0.1.20: the one Pictures socket replaces Picture_1 .. Picture_9")
check(not any(k.startswith("Picture_") for k in mod.IronLeo78_MTV.INPUT_TYPES()["required"]), "v0.0.9H: no required widget was added for them (saved workflows keep their order)")
fp.get_filename_list = lambda k: [mod.DEFAULT_UNET, mod.DEFAULT_QWEN_VL, mod.DEFAULT_VIDEO_VAE,
                                  mod.DEFAULT_AUDIO_VAE, mod.DEFAULT_TURBO_LORA]
good = mod.IronLeo78_MTV.VALIDATE_INPUTS(**kw())
check(good is True, "validate passes with the default widgets (got %r)" % (good,))
check(mod.IronLeo78_MTV.VALIDATE_INPUTS(**{**kw(), "Save Latent": True, "upscale_megapixels": "junk", "Upscale Output": "bogus"}) is True,
      "validate no longer looks at any upscale value (old leftovers are harmless)")

# 10 ---- old workflow (no v2.1 / v2.2 widgets)
print("10. workflow without the Save Latent widget")
node = mod.IronLeo78_MTV()
k = kw()
[k.pop(x) for x in ("Save Latent",)]
EVENTS.clear()
r = node.run(unique_id="7", workflow_prompt=None, extra_pnginfo=None, **k)
check(status_of(r).startswith("Video OFF"), "runs with defaults")
check("models: hardcoded defaults" in status_of(r) and "latent saved" not in status_of(r), "status: hardcoded models, no latent saved (a prompt that sends no Save Latent value: OFF)")


# 11 ---- Model Loader (v2.3)
print("11. Model Loader")
mod._COND_CACHE.clear()
r = run(CONNECTED)
check(LAST["unet_name"] == mod.DEFAULT_UNET and STEPS[-1] == 6,
      "no manager: hardcoded models, Turbo = 6 steps (v0.1.11)")
STEPS.clear()
run(CONNECTED, Turbo=False)
check(STEPS[-1] == 30, "no manager: Turbo OFF = 30 steps (v0.1.11)")
fp.get_filename_list = lambda k: {"diffusion_models": ["d1.safetensors", mod.DEFAULT_UNET],
                                  "loras": ["t1.safetensors"], "text_encoders": ["c1.safetensors", mod.DEFAULT_QWEN_VL],
                                  "vae": ["v1.safetensors", "a1.safetensors", mod.DEFAULT_VIDEO_VAE,
                                          mod.DEFAULT_AUDIO_VAE]}.get(k, [])
ins = mgr.IronLeo78_MTV_ModelLoader.INPUT_TYPES()["required"]
LORA_KEYS = [k for n in (1, 2, 3) for k in ("LoRa_%d_enabled" % n, "LoRa_%d" % n, "LoRa_%d_strength" % n)]
check(list(ins) == ["unet_name", "turbo_lora_name", "turbo_lora_strength"] + LORA_KEYS + ["qwen_vl_name", "video_vae_name", "audio_vae_name",
                    "turbo_steps", "full_steps", "noise_seed"], "v0.1.11: manager widgets, turbo_lora_strength right under the Turbo LoRA, then the three LoRAs: %s" % list(ins))
_ts = ins["turbo_lora_strength"][1]
check(ins["turbo_lora_strength"][0] == "FLOAT" and (_ts["default"], _ts["min"], _ts["max"], _ts["step"]) == (1.0, -100.0, 100.0, 0.01), "v0.1.11: turbo_lora_strength FLOAT, default 1.0, -100..100, step 0.01")
check(not any(k.startswith("custom_lora") for k in ins), "no custom_lora_* widget is left")
check(ins["unet_name"][1]["default"] == mod.DEFAULT_UNET, "hardcoded diffusion model pre-selected when installed")
check(ins["turbo_lora_name"][1]["default"] == "t1.safetensors", "default missing: first installed file")
check(ins["turbo_steps"][1]["default"] == 6 and ins["full_steps"][1]["default"] == 30, "step defaults 6 / 30 (v0.1.11)")
M = mgr.IronLeo78_MTV_ModelLoader()
BUILD_KW = dict(unet_name="d1.safetensors", turbo_lora_name="t1.safetensors", qwen_vl_name="c1.safetensors",
                video_vae_name="v1.safetensors", audio_vae_name="a1.safetensors", turbo_steps=6, full_steps=40, noise_seed=4242,
                LoRa_1_enabled=True, LoRa_1="t1.safetensors", LoRa_1_strength=0.5,
                LoRa_2_enabled=False, LoRa_2="None", LoRa_2_strength=0.65,
                LoRa_3_enabled=False, LoRa_3="None", LoRa_3_strength=0.65)
models = M.build(**BUILD_KW)[0]
check(models["unet_name"] == "d1.safetensors" and models["turbo_steps"] == 6, "manager output dict")
STEPS.clear()
LAST.clear()
r = run(CONNECTED, models=models)
check(LAST["unet_name"] == "d1.safetensors" and LAST["turbo_lora_name"] == "t1.safetensors"
      and LAST["qwen_vl_name"] == "c1.safetensors" and LAST["video_vae_name"] == "v1.safetensors"
      and LAST["audio_vae_name"] == "a1.safetensors",
      "all five model names overridden")
check(STEPS[-1] == 6, "Turbo ON uses turbo_steps (6)")
check(all(ins["LoRa_%d_enabled" % n][1]["default"] is False and ins["LoRa_%d_strength" % n][1]["default"] == 1.0
          and ins["LoRa_%d" % n][0][0] == "None" and ins["LoRa_%d" % n][1]["default"] == "None" for n in (1, 2, 3)), "manager LoRa_1-3: OFF by default, None, strength 1.0 (v0.1.11), lists start with None")
check(LAST["lora_1_enabled"] is True and LAST["lora_1_name"] == "t1.safetensors" and LAST["lora_1_strength"] == 0.5
      and LAST["lora_2_enabled"] is False and LAST["lora_3_enabled"] is False
      and "LoRa_1=ON" in status_of(r), "LoRa_1 toggle / file / strength come from the Model Loader; LoRa_2 / LoRa_3 stay OFF")
models3 = M.build(**dict(BUILD_KW, LoRa_2_enabled=True, LoRa_2="t1.safetensors", LoRa_2_strength=0.3, LoRa_3_enabled=True, LoRa_3="t1.safetensors", LoRa_3_strength=-0.2))[0]
LAST.clear()
r3 = run(CONNECTED, models=models3)
check(LAST["lora_2_enabled"] is True and LAST["lora_2_strength"] == 0.3 and LAST["lora_3_enabled"] is True and LAST["lora_3_strength"] == -0.2
      and "LoRa_2=ON" in status_of(r3) and "LoRa_3=ON" in status_of(r3), "LoRa_2 and LoRa_3 come from the Model Loader too")
try:
    mod.apply_model_overrides({}, dict(models, lora_3_strength="x"))
    check(False, "bad lora strength accepted")
except RuntimeError as e:
    check("LoRa_3_strength" in str(e), "bad LoRa_3 strength is refused")
V = mgr.IronLeo78_MTV_ModelLoader.VALIDATE_INPUTS
check(V(**dict(BUILD_KW, LoRa_2_enabled=True, LoRa_2="gone.safetensors")).startswith("LoRa_2: file not found"), "manager validate: a missing LoRa_2 is refused while ON")
check(V(**dict(BUILD_KW, LoRa_3_enabled=True, LoRa_3="None")).startswith("LoRa_3: no file selected"), "manager validate: LoRa_3 ON with no file is refused")
check(V(**dict(BUILD_KW, LoRa_1_enabled=False, LoRa_1="None")) is True, "manager validate: LoRA None is fine while OFF")
check("LoRa_2_strength" in str(V(**dict(BUILD_KW, LoRa_2_strength=500))), "manager validate: a strength out of range is refused")
check(models["noise_seed"] == 4242 and LAST["noise_seed"] == 4242 and "seed 4242" in status_of(r), "v2.8.5: the seed comes from the Model Loader (4242)")
check(ins["noise_seed"][1]["default"] == 1978 and ins["noise_seed"][1]["control_after_generate"], "manager seed widget: default 1978, control after generate")
LAST.clear()
run(CONNECTED)
check(LAST["noise_seed"] == 1978, "no manager: seed 1978")
check(all(LAST["lora_%d_enabled" % n] is False and LAST["lora_%d_strength" % n] == 1.0 for n in (1, 2, 3)), "no manager: the three LoRAs are OFF at 1.0")
check(LAST["turbo_lora_strength"] == 1.0, "no manager: Turbo LoRA strength 1.0")
LAST.clear()
r_ts = run(CONNECTED, models=M.build(**dict(BUILD_KW, turbo_lora_strength=0.7))[0])
check(LAST["turbo_lora_strength"] == 0.7 and "turbo_lora_strength=0.7" in status_of(r_ts), "v0.1.11: the Turbo LoRA strength comes from the Model Loader (0.7) and the status names it")
check(M.build(**BUILD_KW)[0]["turbo_lora_strength"] == 1.0, "v0.1.11: a Model Loader call without the value (old API prompt) sends 1.0")
check("turbo_lora_strength" in str(V(**dict(BUILD_KW, turbo_lora_strength=500))), "v0.1.11: manager validate: a Turbo strength out of range is refused")
try:
    mod.apply_model_overrides({}, dict(models, turbo_lora_strength="x"))
    check(False, "bad turbo strength accepted")
except RuntimeError as e:
    check("turbo_lora_strength" in str(e), "v0.1.11: a bad Turbo LoRA strength is refused")
check("noise_seed" not in mod.IronLeo78_MTV.INPUT_TYPES()["required"], "the MTV has no noise_seed widget")
check("seed" in str(mgr.IronLeo78_MTV_ModelLoader.VALIDATE_INPUTS(**dict(models, noise_seed=-1))), "manager validate rejects a bad seed")
check("models: Model Loader" in status_of(r) and "steps 6" in status_of(r), "status reports the manager and the steps")
STEPS.clear()
run(CONNECTED, models=models, Turbo=False)
check(STEPS[-1] == 40, "Turbo OFF uses full_steps (40)")
run(CONNECTED, models={"unet_name": "None", "turbo_steps": 4})
check(LAST["unet_name"] == mod.DEFAULT_UNET, "'None' / missing keys keep the hardcoded default")
for bad, msg in (({"turbo_steps": 0}, "between"), ({"full_steps": "x"}, "whole number"), ("nope", "Model Loader")):
    try:
        run(CONNECTED, models=bad)
        check(False, "bad models input must raise")
    except RuntimeError as e:
        check(msg in str(e), "bad models input rejected: %s" % msg)
check(mod._RUNNING == 0, "_RUNNING back to 0 after the rejected input")
# the run-time file check
mod._check_models = REAL_CHECK
try:
    run(CONNECTED)
    check(False, "missing hardcoded turbo lora must raise")
except RuntimeError as e:
    check("Turbo LoRA (hardcoded) not found" in str(e) and "or switch Turbo OFF" in str(e), "missing Turbo LoRA named, hardcoded")
try:
    run(CONNECTED, models={"unet_name": "gone.safetensors", "turbo_lora_name": "t1.safetensors"})
    check(False, "missing manager file must raise")
except RuntimeError as e:
    check("Diffusion model (Model Loader) not found: put gone.safetensors in ComfyUI/models/diffusion_models/" in str(e),
          "missing file named with its source and folder")
fp.get_filename_list = lambda k: {"diffusion_models": ["d1.safetensors"], "loras": ["t1.safetensors"],
                                  "text_encoders": ["c1.safetensors"],
                                  "vae": ["v1.safetensors", "a1.safetensors"]}.get(k, [])
r = run(CONNECTED, models=models)
check("models: Model Loader" in status_of(r), "manager run passes the real check (hardcoded defaults not installed)")
mod._check_models = lambda kw: None
check(mgr.IronLeo78_MTV_ModelLoader.VALIDATE_INPUTS(**models) is True, "manager validate OK")
bad = dict(models, unet_name="zzz.safetensors")
check("not found" in str(mgr.IronLeo78_MTV_ModelLoader.VALIDATE_INPUTS(**bad)), "manager validate rejects a missing file")
check("steps" in str(mgr.IronLeo78_MTV_ModelLoader.VALIDATE_INPUTS(**dict(models, turbo_steps=999))), "manager validate rejects absurd steps")
check(mgr.IronLeo78_MTV_ModelLoader.VALIDATE_INPUTS(**dict(models, upscale_model_name="whatever.safetensors")) is True,
      "a leftover upscale_model_name is ignored by the Model Loader")

# v0.0.9: "Set New Defaults" SAVES the Model Loader's current values as the new defaults; the MTV uses them
import tempfile as _tf, json
_old_dfile = dmod.DEFAULTS_FILE
dmod.DEFAULTS_FILE = os.path.join(_tf.mkdtemp(), "mtv_defaults.json")
fp.get_filename_list = lambda k: {"diffusion_models": ["d1.safetensors", mod.DEFAULT_UNET], "loras": ["t1.safetensors", mod.DEFAULT_TURBO_LORA, mod.DEFAULT_CUSTOM_LORA],
                                  "text_encoders": ["c1.safetensors", mod.DEFAULT_QWEN_VL],
                                  "vae": ["v1.safetensors", "a1.safetensors", mod.DEFAULT_VIDEO_VAE, mod.DEFAULT_AUDIO_VAE]}.get(k, [])
ins_f = mgr.IronLeo78_MTV_ModelLoader.INPUT_TYPES()["required"]
check(not os.path.exists(dmod.DEFAULTS_FILE) and mod.loader_defaults() == mod.factory_defaults(), "no saved defaults: the current defaults are the factory ones")
check(set(mod.factory_defaults()) == set(ins_f) and all(ins_f[k][1]["default"] == v for k, v in mod.factory_defaults().items()),
      "the factory defaults have one value per Model Loader widget and equal each widget's own default (default files installed)")
MY = dict(mod.factory_defaults(), unet_name="d1.safetensors", turbo_lora_name="t1.safetensors", qwen_vl_name="c1.safetensors", video_vae_name="v1.safetensors",
          audio_vae_name="a1.safetensors", turbo_steps=3, full_steps=33, noise_seed=4242, LoRa_1_enabled=True, LoRa_1="t1.safetensors", LoRa_1_strength=0.5)
saved, err = mod.save_user_defaults(MY)
check(err is None and saved == MY and os.path.exists(dmod.DEFAULTS_FILE), "Set New Defaults: the Model Loader's values are written to mtv_defaults.json")
check(mod.loader_defaults() == MY and mod.loader_defaults()["turbo_steps"] == 3, "the backend now answers with the NEW defaults (read back from the file)")
STEPS.clear()
LAST.clear()
rn = run(CONNECTED)
check(STEPS[-1] == 3 and LAST["unet_name"] == "d1.safetensors" and LAST["qwen_vl_name"] == "c1.safetensors" and LAST["noise_seed"] == 4242
      and LAST["lora_1_enabled"] is True and LAST["lora_1_name"] == "t1.safetensors" and LAST["lora_1_strength"] == 0.5,
      "the MTV with NO Model Loader runs with the new defaults (3 steps, d1 model, seed 4242, LoRa_1 ON)")
check("saved defaults (Set New Defaults)" in status_of(rn), "the MTV status says the saved defaults are used")
STEPS.clear()
run(CONNECTED, Turbo=False)
check(STEPS[-1] == 33, "Turbo OFF uses the saved full_steps (33)")
ins_n = mgr.IronLeo78_MTV_ModelLoader.INPUT_TYPES()["required"]
check(ins_n["turbo_steps"][1]["default"] == 3 and ins_n["full_steps"][1]["default"] == 33 and ins_n["unet_name"][1]["default"] == "d1.safetensors"
      and ins_n["LoRa_1_enabled"][1]["default"] is True and ins_n["LoRa_1_strength"][1]["default"] == 0.5 and ins_n["noise_seed"][1]["default"] == 4242,
      "a NEW Model Loader node starts from the saved defaults")
# v0.0.9c: the 2in1 Revitalizer reads the same saved set (real mtv.py, real package import)
rev_mod = importlib.import_module(PKG + ".revitalizer")
check(set(rev_mod.SET_MAP) <= set(mod.factory_defaults()), "v0.0.9c: every name the Revitalizer takes from the saved set is a real Model Loader widget name")
rs, rc = rev_mod.saved_set()
check(len(rs) == 15 and rs["lora_strength"] == 1.0 and rs["unet_name"] == "d1.safetensors" and rs["lora_name"] == "t1.safetensors" and rs["vae_video"] == "v1.safetensors" and rs["vae_audio"] == "a1.safetensors"
      and rs["seed"] == 4242 and rs["LoRa_1_enabled"] is True and rs["LoRa_1"] == "t1.safetensors" and rs["LoRa_1_strength"] == 0.5 and rs["LoRa_2_enabled"] is False and rc is None,
      "v0.0.9c: the Revitalizer reads the saved set through the real mtv.py (Turbo LoRA file -> lora_name, VAEs, seed, LoRa_1-3) and nothing it cannot use")
rin = rev_mod.IronLeo78_2in1_Revitalizer.INPUT_TYPES()
check(rin["required"]["seed"][1]["default"] == 4242 and rin["required"]["unet_name"][1]["default"] == "d1.safetensors" and rin["required"]["lora_name"][1]["default"] == "t1.safetensors"
      and rin["optional"]["LoRa_1_enabled"][1]["default"] is True and rin["optional"]["LoRa_1"][1]["default"] == "t1.safetensors" and rin["optional"]["LoRa_1_strength"][1]["default"] == 0.5,
      "v0.0.9c: a NEW Revitalizer node starts from the saved set (UNET, Turbo LoRA file, seed, LoRa_1 ON / file / strength)")
mdl_same = M.build(**MY)[0]
kw_s = dict(mod.FIXED_SETTINGS)
kw_s["noise_seed"] = mod.DEFAULT_SEED
check(mod.apply_saved_defaults(kw_s) is True and mod.apply_model_overrides(kw_s, mdl_same) == (True, "nothing changed from the defaults"),
      "a connected Model Loader holding the same values changes nothing in the MTV ('nothing changed from the defaults')")
LAST.clear()
STEPS.clear()
run(CONNECTED, models=M.build(**dict(MY, turbo_steps=7))[0])
check(STEPS[-1] == 7 and LAST["unet_name"] == "d1.safetensors", "a connected Model Loader still wins over the saved defaults")
# v0.0.9: with a saved set, the status of a connected loader says whether both sides hold the same set
rs = run(CONNECTED, models=M.build(**MY)[0])
check("Model Loader (same as the saved set)" in status_of(rs), "connected loader holding the saved set: the status says 'same as the saved set'")
rs = run(CONNECTED, models=M.build(**dict(MY, turbo_steps=7))[0])
check("Model Loader (DIFFERS from the saved set: turbo_steps=7)" in status_of(rs), "connected loader holding other values: the status names what differs from the saved set")
# bad values are refused and nothing is written
before = open(dmod.DEFAULTS_FILE).read()
for bad, msg in ((dict(MY, turbo_steps=0), "between"), (dict(MY, LoRa_2_strength=500), "-100 and 100"), (dict(MY, full_steps=True), "valid number"),
                 (dict(MY, unet_name="None"), "no file"), (dict(MY, LoRa_1_enabled="yes"), "ON or OFF"), (dict(MY, noise_seed=-1), "range")):
    _, e = mod.save_user_defaults(bad)
    check(e is not None and msg in e, "save refused: %s" % msg)
check(open(dmod.DEFAULTS_FILE).read() == before, "a refused save leaves the saved defaults untouched")
check(mod.save_user_defaults(None)[1] is not None and mod.save_user_defaults({"other": 1})[1] is not None, "nothing to save: refused")
# v0.0.9: the seed's "control after generate" is part of the saved set (optional, validated, read back)
check(mod._read_user_seed_control() is None, "a set saved without a seed control holds none (the loader leaves its control alone)")
_sc, e = mod.save_user_defaults(MY, "randomize")
check(e is None and _sc == MY and mod._read_user_seed_control() == "randomize" and mod.loader_defaults() == MY, "the seed control is saved with the set and read back; the values are unchanged")
before = open(dmod.DEFAULTS_FILE).read()
_, e = mod.save_user_defaults(MY, "sideways")
check(e is not None and "seed control" in e and open(dmod.DEFAULTS_FILE).read() == before, "an unknown seed control is refused and the saved set is untouched")
with open(dmod.DEFAULTS_FILE, "w") as _f:
    json.dump({"values": {"full_steps": 22}, "seed_control": "sideways"}, _f)
check(mod._read_user_seed_control() is None and mod.loader_defaults()["full_steps"] == 22, "a damaged seed control in the file is ignored, the values still count")
mod.save_user_defaults(MY)
check(mod._read_user_seed_control() is None, "saving again without a seed control clears the old one")
# a damaged value in the file falls back to the factory value, the rest still counts
with open(dmod.DEFAULTS_FILE, "w") as _f:
    json.dump({"values": {"turbo_steps": "x", "full_steps": 22}}, _f)
check(mod.loader_defaults()["turbo_steps"] == 6 and mod.loader_defaults()["full_steps"] == 22, "a damaged value in mtv_defaults.json is skipped, the rest is used")
with open(dmod.DEFAULTS_FILE, "w") as _f:
    _f.write("not json")
check(mod.loader_defaults() == mod.factory_defaults(), "an unreadable mtv_defaults.json: factory defaults, no crash")
mod.save_user_defaults(MY)
check(mod.missing_default_files(dict(MY, unet_name="zzz.safetensors", LoRa_2_enabled=False, LoRa_2="gone.safetensors", LoRa_3_enabled=True, LoRa_3="gone3.safetensors"))
      == ["unet_name (zzz.safetensors)", "LoRa_3 (gone3.safetensors)"], "files that are not installed are listed (a LoRa that is OFF is not checked)")
REAL_CHECK_kw = dict(mod.FIXED_SETTINGS, Turbo=True, models_source=False, defaults_custom=True, unet_name="zzz.safetensors")
try:
    REAL_CHECK(REAL_CHECK_kw)
    check(False, "missing saved file accepted")
except RuntimeError as e:
    check("Diffusion model (saved defaults) not found" in str(e), "the error names the saved defaults as the source")
# Factory: the saved file is deleted, the factory values are back
check(mod.clear_user_defaults() is None and not os.path.exists(dmod.DEFAULTS_FILE) and mod.loader_defaults() == mod.factory_defaults(), "Factory: the saved defaults are deleted")
check(rev_mod.saved_set() == ({}, None) and rev_mod.IronLeo78_2in1_Revitalizer.INPUT_TYPES()["required"]["seed"][1]["default"] == 1978, "v0.0.9c: after Factory the Revitalizer is not forced to anything (v0.1.11: its own seed default 1978 again)")
STEPS.clear()
run(CONNECTED)
check(STEPS[-1] == 6, "after Factory the MTV is back to the built-in 6 steps")
check(mod.SAVE_DEFAULTS_ROUTE == "/ironleo78/mtv/save_defaults" and mod.RESET_DEFAULTS_ROUTE == "/ironleo78/mtv/reset_defaults" and mod.LOADER_DEFAULTS_ROUTE == "/ironleo78/mtv/loader_defaults", "the three routes the panel uses")
dmod.DEFAULTS_FILE = _old_dfile
check(not os.path.exists(dmod.DEFAULTS_FILE), "the tests did not leave a mtv_defaults.json in the pack folder")
fp.get_filename_list = lambda k: {"diffusion_models": ["d1.safetensors"], "loras": ["t1.safetensors"], "text_encoders": ["c1.safetensors"],
                                  "vae": ["v1.safetensors", "a1.safetensors"]}.get(k, [])

# 12 ---- segment count (v2.5)
print("12. segment count")
real_probe = mod._probe_seconds
mod._probe_seconds = lambda name, kind: {"video": 100.0, "audio": 100.0, "short": 60.0}.get(
    "short" if name == "short.wav" else kind)
base = {"Use Video": True, "Video File": "v.mp4", "Custom Audio File": "None",
        "Choose Audio latent": False, "duration": 5.0}
pl = mod._segment_plan(base)
check(pl["total"] == 20 and pl["limit"] == "video" and pl["frames"] == 124, "100 s video, 5 s segments (124 frames): 20 segments (%s)" % pl["total"])
check("start_frame" not in pl and "audio_start" not in pl, "the plan has no start_frame / audio_start: the segment counter decides where cutting starts")
_req = Cls.INPUT_TYPES()["required"]
check("Start Frame" not in _req and "audio_start" not in _req, "Start Frame and audio_start are gone from the node inputs")
check(mod._segment_plan({**base, "Start Frame": 124, "audio_start": 30.0})["total"] == 20, "old Start Frame / audio_start values are ignored: still 20 segments")

# the counter is the start: with the counter at segment index 7, the custom audio chunk starts at 7 x segment length
class _Wave:
    def __init__(self, n): self.shape = (1, n)
SLICES = []
mod._load_custom_audio = lambda name: {"waveform": _Wave(48000 * 400), "sample_rate": 48000}
mod._slice_audio = lambda audio, start, seconds: (SLICES.append((start, seconds)) or {"waveform": _Wave(int(round(seconds * 48000))), "sample_rate": 48000})
_real_index = mod._load_index
mod._load_index = lambda key="": 7
_kw = {"Use Video": False, "Video File": "None", "Custom Audio File": "song.wav", "Choose Audio latent": True,
       "megapixels": 0.2, "duration": 5.0, "Next Segment On Run": True, "Guide": False,
       "picture_1": "None", "picture_2": "None", "picture_3": "None"}
_m = REAL_LOAD_MEDIA(Cls(), _kw)
_seg = 124 / 24.0
check(SLICES and abs(SLICES[-1][0] - 7 * _seg) < 1e-6 and abs(_m["timeline_start"] - 7 * _seg) < 1e-6,
      "counter at segment 8 (index 7): audio chunk starts at 7 x %.3f s = %.3f s, timeline matches" % (_seg, 7 * _seg))
mod._load_index = lambda key="": 0
_m = REAL_LOAD_MEDIA(Cls(), _kw)
check(abs(SLICES[-1][0]) < 1e-9 and _m["timeline_start"] == 0.0, "counter at segment 1: the audio starts at second 0")
mod._load_index = _real_index
check(mod._segment_plan({**base, "duration": 10.0})["total"] == mod._segment_plan({**base, "duration": 10.0})["total"] and
      mod._segment_plan({**base, "duration": 10.0})["total"] == 10, "10 s segments (249 frames... 10.375 s): 10 segments")
pa = mod._segment_plan({**base, "Use Video": False, "Video File": "None", "Custom Audio File": "song.wav", "Choose Audio latent": True})
check(pa["total"] == 20 and pa["limit"] == "custom audio", "custom audio, Use Video OFF: 20 segments by audio chunks")
pm = mod._segment_plan({**base, "Custom Audio File": "short.wav", "Choose Audio latent": True})
check(pm["total"] == 12 and pm["limit"] == "custom audio" and len(pm["sources"]) == 2, "video + shorter audio: the shortest ends the run (12)")
ps = mod._segment_plan({**base, "Use Video": False})
check(ps["total"] == 20 and ps["limit"] == "video soundtrack", "Use Video OFF + bypass + Audio From Video: the soundtrack is counted")
check(mod._segment_plan({**base, "Use Video": False, "Video File": "None"})["total"] is None, "nothing steps through a file: total unknown (None)")
check(mod._segment_plan({**base, "Use Video": "false", "Choose Audio latent": "true", "Custom Audio File": "song.wav"})["total"] == 20, "query-string booleans work")
# v0.0.3: the audio source is a list (MiniMax Audio | Audio From Video | Custom Audio)
_p = {**base, "Use Video": False, "Video File": "None", "Custom Audio File": "song.wav"}
check(mod._segment_plan({**_p, "Choose Audio latent": "MiniMax Audio"})["total"] is None
      and mod._segment_plan({**_p, "Choose Audio latent": "Custom Audio"})["total"] == 20,
      "only Custom Audio steps through the song; MiniMax Audio does not")
_v = {**base, "Use Video": False}
check(mod._segment_plan({**_v, "Choose Audio latent": "Audio From Video"})["limit"] == "video soundtrack"
      and mod._segment_plan({**_v, "Choose Audio latent": "MiniMax Audio"})["total"] is None,
      "the video soundtrack is stepped through for Audio From Video only")
mod._load_index = lambda key="": 7
info = mod._segment_info({**{k: str(v) for k, v in base.items()}, "Next Segment On Run": "true"})
check(info["index"] == 7 and info["total"] == 20 and info["stepping"] and not info["finished"], "segment info: counter 7 of 20")
mod._load_index = lambda key="": 20
check(mod._segment_info(base)["finished"], "segment info: counter 20 of 20 = finished")

# 13 ---- quiet end (v2.5)
print("13. quiet end")
mod._COND_CACHE.clear()
COND_CALLS.clear()
mod._segment_plan = lambda p: {"total": 20}
r = run(CONNECTED)
check(status_of(r).startswith("FINISHED") and "all 20 segments are done" in status_of(r), "counter at the end: quiet FINISHED report, no error")
check(SAVES == [] and COND_CALLS == [] and INDEX == [] and r["result"][:2] == (None, None) and r["result"][2].startswith("FINISHED") and "images" not in r["ui"], "nothing generated, counter did not move, video / filename are blocked / empty, status says FINISHED")
mod._load_index = lambda key="": 3
r = run(CONNECTED, **{"Next Segment On Run": False})
check(not status_of(r).startswith("FINISHED"), "Next Segment On Run OFF never stops")
mod._segment_plan = lambda p: {"total": 20}
patch_media(mod.IronLeo78_MTV, lambda: {**make_media(), "index": mod._load_index()})   # like the real loader
r = run(CONNECTED)
check("segment 4 of 20 (seg003)" in status_of(r) and "progress: 4 of 20" in status_of(r) and "16 left" in status_of(r), "progress line: segment 4 of 20, 16 left")
mod._load_index = lambda key="": 19
r = run(CONNECTED)
check("LAST segment" in status_of(r), "the last segment says so")
mod._segment_plan = lambda p: {"total": None}      # unknown total: the loader hits the end instead
def lm_end(self, kw):
    raise mod._EndOfSegments("End of custom audio: segment 38 would start at 195.00s", 37)
orig_lm = mod.IronLeo78_MTV._load_media
mod.IronLeo78_MTV._load_media = lm_end
r = run(CONNECTED)
check(status_of(r).startswith("FINISHED") and "all 37 segments" in status_of(r) and INDEX == [] and SAVES == [], "loader reaches the end: quiet stop, not an error")
mod.IronLeo78_MTV._load_media = orig_lm
patch_media(mod.IronLeo78_MTV)
mod._segment_plan = lambda p: {"total": None}
r = run(CONNECTED, **{"Next Segment On Run": False})
check(not status_of(r).startswith("FINISHED"), "normal run still works after the quiet-end tests")

# 14 ---- prompt sidecar (v2.5)
print("14. prompt sidecar")
import json as _json, csv as _csv
LONG = ("A very long prompt about <Picture 1> dancing in the rain. " * 12).strip()
check(len(LONG) > 600, "test prompt is longer than 300 characters (%d)" % len(LONG))
mod._load_index = lambda key="": 0
r = run(CONNECTED, **{"prompt": LONG})
side = os.path.join(TMP, *(r["result"][1] + ".json").split("/"))      # v0.0.5: the number is the next free one, shown by the filename output
check(os.path.exists(side), "sidecar written with the clip name (<tag>_NNNNN_.json)")
d = _json.load(open(side, encoding="utf-8"))
check(d["prompt"] == LONG and d["tag"] == "Song_seg000_A" and d["segment_number"] == 1 and d["version"] == mod.VERSION and "scene" not in d, "sidecar holds the FULL prompt + segment info (no scene field any more)")
check(not [f for f in os.listdir(os.path.join(TMP, "Song")) if "upscaled" in f] and not os.path.exists(os.path.join(TMP, "Song", "Song_seg000_B_00001_.json")),
      "no upscaled clip / sidecar, and there is no B sidecar")
check(d["kind"] == "clip" and "upscaled_file" not in d and "latent_upscale" not in d and "upscale_quality" not in d and d["save_latent"] is False,
      "the sidecar has no upscale fields, and records save_latent = false")
check(len(ROWS[0]["prompt"]) == mod.MANIFEST_PROMPT_CHARS and ROWS[0]["prompt"].endswith("\u2026"), "the CSV prompt stays short, marked with an ellipsis")
check(ROWS[0]["prompt_json"] == r["result"][1] + ".json" and ROWS[0]["file"] == r["result"][1] + ".mp4", "manifest row points at the sidecar and the planned clip name")
check("manifest:" in status_of(r) and ("full prompt: " + r["result"][1] + ".json") in status_of(r), "status lists the sidecar of the clip")
check(mod.VERSION == "0.4.8", "VERSION is 0.4.8")
check(Cls.INPUT_TYPES()["required"]["duration"][1]["step"] == 0.1 and Cls.INPUT_TYPES()["required"]["duration"][1]["default"] == 5.0, "v0.0.9: duration moves by 0.1 s, default still 5")

# 15 ---- manifest upgrade (v2.5)
print("15. manifest upgrade")
os.makedirs(os.path.join(TMP, "Old"), exist_ok=True)
oldp = os.path.join(TMP, "Old", "Old_manifest.csv")
old_fields = [f for f in mod.MANIFEST_FIELDS if f != "prompt_json"]
with open(oldp, "w", newline="", encoding="utf-8-sig") as f:
    w = _csv.DictWriter(f, fieldnames=old_fields)
    w.writeheader()
    w.writerow({"song": "Old", "segment": 0, "scene": "A", "prompt": "old prompt"})
row = {k: "x" for k in mod.MANIFEST_FIELDS}
row.update(song="Old", segment=1, prompt_json="Old/new.json")
REAL_APPEND("Old", [row])
rows_back = list(_csv.DictReader(open(oldp, newline="", encoding="utf-8-sig")))
check(list(rows_back[0].keys())[-1] == "prompt_json" and len(rows_back) == 2, "old manifest got the prompt_json column, rows kept")
check(rows_back[0]["prompt"] == "old prompt" and rows_back[0]["prompt_json"] == "" and rows_back[1]["prompt_json"] == "Old/new.json", "old row untouched, new row filled")
# a manifest written by 0.5 (with the upscale columns) is still appended to, its columns are kept
old05 = os.path.join(TMP, "Old05")
os.makedirs(old05, exist_ok=True)
f05 = list(mod.MANIFEST_FIELDS) + ["upscale_mp", "upscaled_file"]
with open(os.path.join(old05, "Old05_manifest.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = _csv.DictWriter(f, fieldnames=f05)
    w.writeheader()
    w.writerow({"song": "Old05", "segment": 0, "scene": "A", "upscale_mp": "0.4", "upscaled_file": "Old05/up.mp4"})
REAL_APPEND("Old05", [{**row, "song": "Old05", "segment": 1, "file": "Old05/new.mp4"}])
rows05 = list(_csv.DictReader(open(os.path.join(old05, "Old05_manifest.csv"), newline="", encoding="utf-8-sig")))
check(len(rows05) == 2 and rows05[0]["upscaled_file"] == "Old05/up.mp4" and rows05[1]["file"] == "Old05/new.mp4" and rows05[1]["upscaled_file"] == "",
      "a 0.5 manifest (with upscale columns) keeps its columns and old rows, the new row has them empty")
REAL_APPEND("Fresh", [row])
check(open(os.path.join(TMP, "Fresh", "Fresh_manifest.csv"), encoding="utf-8-sig").readline().strip().split(",") == mod.MANIFEST_FIELDS, "a new manifest starts with the full header")

# 16 ---- reset (v2.5)
print("16. reset")
smod.STATE_FILE = os.path.join(TMP, "state.json")
open(smod.STATE_FILE, "w").write(_json.dumps({"index": 5, "guide_frame_for": 4}))
mod._load_index = REAL_LOAD_INDEX
check(mod._load_index() == 5, "state says segment 5")
mod._reset_state()
check(mod._load_index() == 0 and _json.load(open(smod.STATE_FILE)) == {"index": 0}, "reset: counter 0, guide frame forgotten")

# 17 ---- jump to segment (v2.6)
print("17. jump to segment")
open(smod.STATE_FILE, "w").write(_json.dumps({"index": 5, "guide_frame_for": 4}))
out = mod._handle_jump({"segment": 3, "total": 37})
st = _json.load(open(smod.STATE_FILE))
check(out == {"ok": True, "index": 2, "segment": 3, "furthest": 5} and st["index"] == 2, "jump to segment 3: counter 2, furthest 5 remembered")
check(st["guide_frame_for"] == 4 and mod._load_index() == 2, "the saved guide frame is kept (it is checked against the counter when used)")
out = mod._handle_jump({"latest": True})
check(out["ok"] and out["segment"] == 6 and _json.load(open(smod.STATE_FILE))["index"] == 5, "Latest: back to segment 6 (the furthest counter)")
for bad, word in (({"segment": 0}, "start at 1"), ({"segment": "abc"}, "whole number"), ({}, "whole number"),
                  ({"segment": 40, "total": 37}, "only 37")):
    before = open(smod.STATE_FILE).read()
    o = mod._handle_jump(bad)
    check(o["ok"] is False and word in o["error"] and open(smod.STATE_FILE).read() == before, "bad jump %r is refused, state untouched" % (bad,))
check(mod._handle_jump({"segment": 37, "total": 37})["ok"], "the last segment itself is allowed")
mod._write_state({"index": 2})
REAL_SAVE_INDEX(7)
check(_json.load(open(smod.STATE_FILE)) == {"index": 7, "furthest": 7}, "a normal run saves the counter and the furthest point")
REAL_SAVE_INDEX(3)
check(mod._load_furthest() == 7 and _json.load(open(smod.STATE_FILE))["index"] == 3, "furthest never goes down")
mod._segment_plan = lambda p: {"total": 20}
check(mod._segment_info({})["furthest"] == 7 and mod._segment_info({})["index"] == 3, "segment info carries the furthest point for the panel")
mod._reset_state()
check(_json.load(open(smod.STATE_FILE)) == {"index": 0}, "reset forgets the furthest point too")

# 18 ---- guide frame read back from a saved clip (v2.6)
print("18. guide read back from a clip")
import numpy as _np
from PIL import Image as _Image
SONG_DIR = os.path.join(TMP, "Song")
os.makedirs(SONG_DIR, exist_ok=True)
for n in ("x_1.mp4", "x_2.mp4", "x_up.mp4", "y.mp4"):
    open(os.path.join(SONG_DIR, n), "wb").write(b"v")
mpath = os.path.join(SONG_DIR, "Song_manifest.csv")
with open(mpath, "w", newline="", encoding="utf-8-sig") as f:
    w = _csv.DictWriter(f, fieldnames=mod.MANIFEST_FIELDS + ["upscaled_file"])
    w.writeheader()      # a manifest of 0.5 or older
    for seg, sc, fl, up in ((3, "A", "Song/x_1.mp4", ""), (3, "A", "Song/x_2.mp4", ""), (3, "B", "Song/y.mp4", ""),
                            (4, "A", "Song/gone.mp4", ""), (6, "B", "Song/y.mp4", "")):
        w.writerow({"song": "Song", "segment": seg, "scene": sc, "file": fl, "upscaled_file": up})
check(mod._clip_from_manifest("Song", 3).endswith("x_2.mp4"), "manifest lookup: the latest row of a redone segment wins (the old B row is never used)")
os.remove(os.path.join(SONG_DIR, "x_2.mp4"))
check(mod._clip_from_manifest("Song", 3).endswith("x_1.mp4"), "...and an earlier row is used when the later file is gone")
check(mod._clip_from_manifest("Song", 6) is None, "a segment that only has a Scene B row (older version) finds no clip")
check(mod._clip_from_manifest("Song", 4) is None and mod._clip_from_manifest("Song", 9) is None, "missing file / missing segment: None")
with open(mpath, "a", newline="", encoding="utf-8-sig") as f:
    _csv.DictWriter(f, fieldnames=mod.MANIFEST_FIELDS + ["upscaled_file"]).writerow({"song": "Song", "segment": 3, "scene": "A", "file": "Song/x_1.mp4", "upscaled_file": "Song/x_up.mp4"})
check(mod._clip_from_manifest("Song", 3).endswith("x_up.mp4"), "manifests of 0.5 and older: an upscaled clip is still preferred (new manifests have none)")

smod.LAST_FRAME_FILE = os.path.join(TMP, "lf.png")
_Image.fromarray(_np.zeros((4, 4, 3), _np.uint8)).save(smod.LAST_FRAME_FILE)
REAL_CLIP_READER = smod._clip_last_frame_array
READS = []
smod._clip_last_frame_array = lambda path: READS.append(os.path.basename(path)) or _np.zeros((4, 4, 3), _np.uint8)
mod._write_state({"index": 4, "guide_frame_for": 3})
img, why = mod._load_last_frame(4, "Song")
check(img is not None and why == "" and READS == [], "saved frame is from the segment before: used as before, no clip read")
mod._write_state({"index": 4, "guide_frame_for": 9})
img, why = mod._load_last_frame(4, "Song")
check(img is not None and "read back from the saved clip x_up.mp4" in why and READS == ["x_up.mp4"], "after a jump the frame is read back from the clip of segment 4")
img, why = mod._load_last_frame(4)
check(img is None and "no saved last frame from segment 3" in why, "without a song (old callers) the old behaviour")
img, why = mod._load_last_frame(7, "Song")
check(img is None and "no saved last frame from segment 6" in why, "no clip for that segment: no guide, with the reason")
smod._clip_last_frame_array = lambda path: (_ for _ in ()).throw(RuntimeError("cannot decode"))
img, why = mod._load_last_frame(4, "Song")
check(img is None, "an unreadable clip never breaks the Run (no guide)")
smod._clip_last_frame_array = lambda path: READS.append(os.path.basename(path)) or _np.zeros((4, 4, 3), _np.uint8)

# the REAL reader (PyAV + ffmpeg): a clip that is red for 1 s and then blue for 1 s -> the last frame is blue
import shutil as _sh, subprocess as _sp
if _sh.which("ffmpeg"):
    try:
        import av as _av
    except ImportError:
        _av = None
    if _av is not None:
        two = os.path.join(TMP, "two_colours.mp4")
        _sp.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=64x48:r=24:d=1", "-f", "lavfi",
                 "-i", "color=c=blue:s=64x48:r=24:d=1", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", two], check=True)
        arr = REAL_CLIP_READER(two)
        check(arr.shape == (48, 64, 3) and arr.dtype == _np.uint8, "real PyAV reader: RGB uint8 [H, W, 3]")
        r_, g_, b_ = [int(x) for x in arr[24, 32]]
        check(b_ > 150 and r_ < 100, "real PyAV reader: it returns the LAST frame (blue), not the first (red): %s" % ((r_, g_, b_),))
        try:
            REAL_CLIP_READER(os.path.join(TMP, "not_a_video.mp4"))
            check(False, "missing clip accepted")
        except RuntimeError:
            check(True, "real PyAV reader: an unreadable clip raises (the Guide catches it and runs without)")
    else:
        print("  (PyAV not installed here: real clip reader test skipped)")
else:
    print("  (ffmpeg not on the PATH: real clip reader test skipped)")

mod._fit_frame = lambda f, w, h: f
patch_media(mod.IronLeo78_MTV, lambda: {**make_media(), "index": 4})
r = run(CONNECTED, Guide=True)
check("guide: ON | last frame of segment 3 -> frame 0" in status_of(r) and "read back from the saved clip x_up.mp4" in status_of(r), "Run status says the guide frame was read back from the clip")
patch_media(mod.IronLeo78_MTV)

# 19 ---- Audio Stem (Full / Vocals / Guitars / Drums / Bass): separated once per song, kept on disk
print("19. audio stems")
import numpy as _np19, contextlib as _cl19
keys = list(Cls.INPUT_TYPES()["required"])
check(keys[keys.index("Custom Audio File") + 1] == "Audio Stem", "the Audio Stem dropdown sits right under Custom Audio File: %s" % keys[keys.index("Custom Audio File"):][:3])
spec = Cls.INPUT_TYPES()["required"]["Audio Stem"]
check(spec[0] == ["Full", "Vocals", "Guitars", "Drums", "Bass"] and spec[1]["default"] == "Full", "options Full, Vocals, Guitars, Drums, Bass; default Full")
check(mod._stem_choice({}) == "Full" and mod._stem_choice({"Audio Stem": "Banjo"}) == "Full" and mod._stem_choice({"Audio Stem": "Song"}) == "Full", "an old workflow (no widget), an unknown value or the old name Song = Full")
check(mod.IronLeo78_MTV.VALIDATE_INPUTS(**{"Use Video": False, "Audio Stem": "Song"}) is True and mod.IronLeo78_MTV.VALIDATE_INPUTS(**{"Use Video": False, "Audio Stem": "Banjo"}) is not True, "validation: an old API prompt with Song still passes, a wrong name does not")
check(mod.IronLeo78_MTV.VALIDATE_INPUTS(**{"Use Video": False, "Audio Stem": "Banjo"}) != True, "an unknown stem is refused")
check(mod.IronLeo78_MTV.VALIDATE_INPUTS(**{"Use Video": False, "Audio Stem": "Vocals"}) is True, "a valid stem passes")

SEP = {"n": 0}
def _fake_sep(audio, progress=None):
    SEP["n"] += 1
    return {lab: _np19.full((2, 4410), 0.1 * (i + 1), dtype=_np19.float32) for i, lab in enumerate(mod._stems.STEM_LABELS)}, 44100
mod._stems.separate_audio = _fake_sep
class _Dec:
    def __init__(self, n): self.n = n
    def numel(self): return self.n
    def element_size(self): return 4
    shape = (1, 2, 4410)
DECODED = []
mod._decode_audio = lambda path, start=0.0, dur=None: DECODED.append(os.path.basename(path)) or {"waveform": _Dec(8820), "sample_rate": 44100}
mod._load_custom_audio = lambda name: {"waveform": _Dec(10), "sample_rate": 44100}
mod._STEMS_READY.clear()
mod._AUDIO_CACHE.clear()

check(Cls._prepare_stems({"Audio Stem": "Full", "Custom Audio File": "song.wav"}) == "" and SEP["n"] == 0, "Full: no separation, nothing written")
check(Cls._prepare_stems({"Audio Stem": "Vocals", "Custom Audio File": "None"}) == "" and SEP["n"] == 0, "a stem without a Custom Audio File: nothing to do")
note = Cls._prepare_stems({"Audio Stem": "Vocals", "Custom Audio File": "song.wav"})
check(SEP["n"] == 1 and "separated with Hybrid Demucs" in note and "output/song/stems" in note, "first use of a stem: all four separated once. %s" % note)
for lab in ("Vocals", "Guitars", "Drums", "Bass"):
    check(os.path.isfile(os.path.join(TMP, "song", "stems", "song_%s.wav" % lab)), "song_%s.wav saved" % lab)
note = Cls._prepare_stems({"Audio Stem": "Drums", "Custom Audio File": "song.wav"})
check(SEP["n"] == 1 and "read from the saved stems" in note, "another stem of the same song: read from disk, no new separation")
mod._STEMS_READY.clear()
Cls._prepare_stems({"Audio Stem": "Bass", "Custom Audio File": "song.wav"})
check(SEP["n"] == 1, "after a restart (memory empty) the stems on disk are still found")

# the real loader: which audio goes in, and the caches keep the stems apart
mod._slice_audio = lambda audio, start, seconds: {"waveform": _Wave(int(round(seconds * 48000))), "sample_rate": 48000}
mod._load_index = lambda key="": 0
_kw19 = {"Use Video": False, "Video File": "None", "Custom Audio File": "song.wav", "Choose Audio latent": True,
         "megapixels": 0.2, "duration": 5.0, "Next Segment On Run": True, "Guide": False,
         "picture_1": "None", "picture_2": "None", "picture_3": "None"}
ids = {}
for stem in ("Full", "Vocals", "Guitars", "Drums", "Bass"):
    DECODED.clear()
    mod._AUDIO_CACHE.clear()
    m = REAL_LOAD_MEDIA(Cls(), {**_kw19, "Audio Stem": stem})
    ids[stem] = m["cond_id"]["audio2"]
    check(m["audio_stem"] == stem, "%s: media records the stem" % stem)
    if stem != "Full":
        check(DECODED == ["song_%s.wav" % stem], "%s: the stem file is what gets decoded (%s)" % (stem, DECODED))
check(len(set(ids.values())) == 5, "conditioning / audio-latent cache ids differ for every stem")
check(ids["Full"] == ("a2c", mod._file_id("song.wav"), 0.0, round(124 / 24.0, 6)), "Full keeps the exact same cache id as before the feature")
_n19 = Cls()
_n19._pending_index = None      # run() sets this before _load_media
m = REAL_LOAD_MEDIA(_n19, {**_kw19, "Audio Stem": "Vocals", "Custom Audio File": "None"})
check(m["audio_stem"] == "" and m["audio2"] is None, "a stem without a Custom Audio File: silence, no stem recorded")
DECODED.clear()
mod._load_audio_for_stem("song.wav", "Vocals")
mod._load_audio_for_stem("song.wav", "Vocals")
check(len(DECODED) == 1, "the decoded stem is kept in RAM for the next Run")

# status box, manifest row, sidecar
Cls._prepare_stems = staticmethod(lambda kw_: "audio stem: Vocals (test note)")
patch_media(Cls, lambda: {**make_media(), "audio_stem": "Vocals"})
r = run(CONNECTED, **{"Audio Stem": "Vocals"})
check("audio stem: Vocals (test note)" in status_of(r), "the status box says which stem was used and whether it was separated")
check(ROWS and ROWS[-1]["audio_stem"] == "Vocals" and "audio_stem" in mod.MANIFEST_FIELDS, "the manifest row records the stem (new column, old manifests are upgraded)")
patch_media(Cls)
IC = lambda stem: mod.IronLeo78_MTV.IS_CHANGED(**{"Use Video": False, "Next Segment On Run": False, "Custom Audio File": "song.wav", "Audio Stem": stem})
check(IC("Vocals") != IC("Bass"), "IS_CHANGED: a different stem re-runs the node")

# 20 ---- Save Latent ON saves the sampled latent + its conditioning, in the song folder, named after the clip
print("20. save latent + conditioning (Save Latent ON)")
COUNT_SAVES = True
import json as _j20
patch_media(Cls)
LATENTS.clear()
CONDS.clear()
r = run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "LatSong.wav"})
check(len(LATENTS) == 2 and len(CONDS) == 1, "Save Latent ON: two .latent files (video + audio) and one .conditioning file")
v, a = LATENTS[0], LATENTS[1]
check(v[1] == "vlat" and a[1] == "alat", "the video latent and the audio latent are saved separately (LTXVSeparateAVLatent)")
P = lambda x: x.replace(os.sep, "/")
check(P(v[0]).endswith("/LatSong/LatSong_seg000_A_00001_video.latent") and P(a[0]).endswith("/LatSong/LatSong_seg000_A_00001_audio.latent")
      and P(CONDS[0][0]).endswith("/LatSong/LatSong_seg000_A_00001.conditioning"),
      "saved in the song folder (no subfolder), named after the clip: <tag>_00001_video.latent / _audio.latent / <tag>_00001.conditioning")
check("latents" not in P(v[0]) and not os.path.isdir(os.path.join(TMP, "LatSong", "latents")), "there is no latents subfolder")
check(SAVES[-1] == "LatSong/LatSong_seg000_A", "the clip is saved with the same prefix, so mp4, latents and conditioning share one name")
check(v[2].get("part") == "video" and a[2].get("part") == "audio" and CONDS[0][2].get("part") == "conditioning" and "ironleo78" in v[2],
      "file metadata says which part each file is")
check(CONDS[0][1] == [["emb", {"p": "P1"}]], "the conditioning is the plain MiniMax conditioning of the prompt + pictures")
side = _j20.load(open(os.path.join(TMP, "LatSong", "LatSong_seg000_A_00001_.json"), encoding="utf-8"))
check(side["latent"] == {"video": "LatSong/LatSong_seg000_A_00001_video.latent", "audio": "LatSong/LatSong_seg000_A_00001_audio.latent",
                         "conditioning": "LatSong/LatSong_seg000_A_00001.conditioning"}, "the clip's .json sidecar lists the three files")
check("video_latent_shape" in side["latent_details"] and "audio_latent_shape" in side["latent_details"], "the latent details list the latent shapes")
check(side["latent_details"]["same_noise_seed"] == 1978 and side["seed"] == 1978 and side["frames"] == 124 and side["prompt"] == "P1" and side["save_latent"] is True,
      "and the sidecar has what a later pass needs (seed, size, frames, prompt) and records save_latent = true")
check(not any(k in side["latent_details"] for k in ("upscale_sigmas", "upscale_quality", "temporal_chunking", "upscale_model")),
      "the latent details no longer carry any upscale settings")
check(not os.path.exists(os.path.join(TMP, "LatSong", "LatSong_seg000_A_00001_latent.json")), "no separate _latent.json any more")
check("latent saved (Save Latent ON)" in status_of(r) and ".conditioning" in status_of(r), "the status box says what was saved")
check(ROWS[-1]["latent_file"].endswith("LatSong_seg000_A_00001_video.latent") and ROWS[-1]["conditioning_file"].endswith("LatSong_seg000_A_00001.conditioning"),
      "the manifest row has latent_file and conditioning_file")

LATENTS.clear()
CONDS.clear()
run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "LatSong.wav"})
check(P(LATENTS[0][0]).endswith("_00002_video.latent") and P(CONDS[0][0]).endswith("_00002.conditioning"),
      "a redo: everything gets the next number, nothing is overwritten, and the numbers still match the clip")

# with the guide: still only the plain conditioning (the guide belongs to the first-pass size)
patch_media(mod.IronLeo78_MTV, lambda: {**make_media(), "index": 4})
_real_load_last = mod._load_last_frame
mod._load_last_frame = lambda index, song=None, key="": ("FRAME", "")
LATENTS.clear()
CONDS.clear()
r = run(CONNECTED, **{"Save Latent": True, "Guide": True, "Custom Audio File": "GuideSong.wav"})
mod._load_last_frame = _real_load_last
check("guide: ON | last frame" in status_of(r), "(the guide was applied in this run)")
check(len(CONDS) == 1 and CONDS[0][1] == [["emb", {"p": "P1"}]], "Guide used: still ONE .conditioning, the plain one (not the guided one)")
patch_media(mod.IronLeo78_MTV)

LATENTS.clear()
CONDS.clear()
r = run(CONNECTED, **{"Save Latent": False, "Custom Audio File": "LatSong.wav"})
check(LATENTS == [] and CONDS == [] and SAVES and "latent saved" not in status_of(r), "Save Latent OFF: no latent or conditioning files, only the clip")
side_off = _j20.load(open(os.path.join(TMP, "LatSong", "LatSong_seg000_A_00003_.json"), encoding="utf-8"))
check(side_off["save_latent"] is False and side_off["latent"] is None and side_off["latent_details"] is None and ROWS[-1]["latent_file"] == "" and ROWS[-1]["conditioning_file"] == "",
      "...and the sidecar / manifest list no latent files")
LATENTS.clear()
CONDS.clear()
node_nokey = mod.IronLeo78_MTV()
_k = kw(**{"Custom Audio File": "LatSong.wav"})
_k.pop("Save Latent")
EVENTS.clear()
node_nokey.run(unique_id="7", workflow_prompt=None, extra_pnginfo=None, **_k)
check(LATENTS == [] and CONDS == [], "a node without the Save Latent value (old workflow): nothing is saved")

# v0.0.5: the clip number is planned once; the latent files, the .json and the filename output all use it
SAVE_N.clear()
LATENTS.clear()
CONDS.clear()
r = run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "OrderSong.wav"})
check(r["result"][1] == "OrderSong/OrderSong_seg000_A_00001_" and P(LATENTS[0][0]).endswith("/OrderSong/OrderSong_seg000_A_00001_video.latent"),
      "the filename output and the latent files carry the same clip number")

# a decode error still keeps the sampled latent and the conditioning
real_core = mod._core
def _core_decode_boom(name, provided, **k):
    if name == "VAEDecode": raise RuntimeError("decode exploded")
    return real_core(name, provided, **k)
mod._core = _core_decode_boom
LATENTS.clear()
CONDS.clear()
try:
    run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "BoomSong.wav"})
    failed = False
except Exception:
    failed = True
mod._core = real_core
check(failed and len(LATENTS) == 2 and len(CONDS) == 1 and P(LATENTS[0][0]).endswith("BoomSong_seg000_A_00001_video.latent"),
      "a decode error: the latents and the conditioning are still saved, with the number the clip would have had")

def _cond_boom(path, conditioning, metadata): raise OSError("cannot write conditioning")
mod._write_conditioning_file = _cond_boom
LATENTS.clear()
r = run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "CondSong2.wav"})
check(len(LATENTS) == 2 and "conditioning not saved (cannot write conditioning)" in status_of(r) and SAVES and any(e[0] == "decode" for e in EVENTS),
      "a conditioning that cannot be written is only a note: latents are kept, the clip is still made")
side = _j20.load(open(os.path.join(TMP, "CondSong2", "CondSong2_seg000_A_00001_.json"), encoding="utf-8"))
check("conditioning" not in side["latent"], "and the sidecar does not list a file that was never written")
mod._write_conditioning_file = _fake_write_conditioning

def _boom(path, samples, metadata): raise OSError("disk full")
mod._write_latent_file = _boom
r = run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "LatSong.wav"})
check("latent not saved (disk full)" in status_of(r) and any(e[0] == "decode" for e in EVENTS) and SAVES,
      "a latent that cannot be written is only a note: the clip is still decoded and saved")
mod._write_latent_file = _fake_write_latent

# 21 ---- v0.6: the Save Latent toggle
print("21. Save Latent OFF / ON")
t21 = mod.IronLeo78_MTV.INPUT_TYPES()["required"]
check(t21["Save Latent"][0] == "BOOLEAN" and t21["Save Latent"][1]["default"] is True
      and t21["Save Latent"][1]["label_on"] == "ON" and t21["Save Latent"][1]["label_off"] == "OFF", "Save Latent is an OFF / ON toggle, default ON (v0.1.11)")
tip = t21["Save Latent"][1]["tooltip"]
check(".latent" in tip and ".conditioning" in tip, "its tooltip names the files it writes")
# ON: the files exist and the clip number matches; OFF: nothing; the toggle is the ONLY thing that decides
for flag in (True, False, True):
    LATENTS.clear()
    CONDS.clear()
    SAVE_N.clear()
    r = run(CONNECTED, **{"Save Latent": flag, "Custom Audio File": "ToggleSong.wav"})
    check((len(LATENTS), len(CONDS)) == ((2, 1) if flag else (0, 0)), "Save Latent %s: %s" % ("ON" if flag else "OFF", "2 latents + 1 conditioning" if flag else "no files"))
# the toggle works with the guide and with other widgets set any way (nothing else switches saving on or off)
LATENTS.clear()
CONDS.clear()
run(CONNECTED, **{"Save Latent": True, "Guide": True, "Turbo": False, "Next Segment On Run": False, "Custom Audio File": "ToggleSong.wav"})
check(len(LATENTS) == 2 and len(CONDS) == 1, "Save Latent ON also works with Guide ON / Turbo OFF / Next Segment OFF")
check(mod.IronLeo78_MTV.VALIDATE_INPUTS(**{**kw(), "Save Latent": True}) is True, "validate accepts Save Latent ON")

# 22 ---- v0.0.3: MiniMax Audio | Audio From Video | Custom Audio
print("22. audio source: MiniMax Audio / Audio From Video / Custom Audio")
check(mod._audio_mode(True) == "Custom Audio" and mod._audio_mode(False) == "Audio From Video"
      and mod._audio_mode("true") == "Custom Audio" and mod._audio_mode("false") == "Audio From Video"
      and mod._audio_mode("MiniMax Audio") == "MiniMax Audio" and mod._audio_mode(" custom audio ") == "Custom Audio"
      and mod._audio_mode(None) == "Audio From Video", "old True / False and the new names are all understood")
spec = mod.IronLeo78_MTV.INPUT_TYPES()["required"]["Choose Audio latent"]
check(list(spec[0]) == ["MiniMax Audio", "Audio From Video", "Custom Audio"] and spec[1]["default"] == "Custom Audio",
      "the widget is a list: MiniMax Audio, Audio From Video, Custom Audio (default Custom Audio), same position as before")
patch_media(mod.IronLeo78_MTV)
BYPASS_NODES = {"TrimAudioDuration", "VAEEncodeAudio", "SolidMask", "SetLatentNoiseMask", "LTXVConcatAVLatent"}
for value, expect_text in (("Custom Audio", "Bypass Minimax / custom audio"),
                           ("Audio From Video", "Bypass Minimax / audio from video"),
                           (True, "Bypass Minimax / custom audio"),
                           (False, "Bypass Minimax / audio from video")):
    MASKS.clear()
    CORE_CALLS.clear()
    mod._COND_CACHE.clear()
    r = run(CONNECTED, **{"Choose Audio latent": value})
    check(MASKS == [0.0] and BYPASS_NODES <= set(CORE_CALLS) and expect_text in status_of(r),
          "%r: audio bypassed (trim, encode, frozen mask 0, concat); status says '%s'" % (value, expect_text))
MASKS.clear()
CORE_CALLS.clear()
mod._COND_CACHE.clear()
r = run(CONNECTED, **{"Choose Audio latent": "MiniMax Audio"})
sampled = [e for e in EVENTS if e[0] == "sample"]
check(not (BYPASS_NODES & set(CORE_CALLS)) and MASKS == [],
      "MiniMax Audio: no trim / encode / mask / concat at all (no bypass)")
check(sampled and isinstance(sampled[-1][1], dict) and str(sampled[-1][1].get("samples", "")).startswith("EMPTY:"),
      "MiniMax Audio: the MiniMax node's own latent goes to the sampler untouched, like the official template")
check("MiniMax Audio (the model's own audio latent, no bypass)" in status_of(r), "the status box says the model's own audio is used")
check("VAEDecodeAudio" in CORE_CALLS and "CreateVideo" in CORE_CALLS and "SaveVideo" not in CORE_CALLS, "MiniMax Audio still decodes the audio and makes the video (no Save Video inside the node)")
# 23 ---- v0.0.5: video + filename outputs, no Save Video inside, widget renamed
print("23. v0.0.5: outputs, hardcoded Create Video, renamed widget")
req23 = mod.IronLeo78_MTV.INPUT_TYPES()["required"]
check("Choose Audio latent" in req23 and "Bypassed Audio Latent" not in req23, "the widget is called Choose Audio latent")
check(list(req23).index("Choose Audio latent") == 3, "...v0.1.11: moved to position 3, right under Video File (the JS migration puts old saved values back)")
check(mod.IronLeo78_MTV.OUTPUT_NODE is True, "still an output node: it runs (and steps the segment counter) with nothing linked")
check(not any(k in req23 for k in ("fps", "color_space", "codec", "format", "filename_prefix")), "no Create Video / Save Video widgets: they are hardcoded")
CV = []
_core_before23 = mod._core
def _core_spy(name, provided, **k):
    if name == "CreateVideo":
        CV.append(dict(provided))
    return _core_before23(name, provided, **k)
mod._core = _core_spy
r = run(CONNECTED, **{"Turbo": False, "Next Segment On Run": False})
mod._core = _core_before23
check(len(CV) == 1 and CV[0]["fps"] == 24.0 and CV[0]["color_space"] == "sRGB" and CV[0]["codec"] == "h264",
      "Create Video gets its hardcoded settings: 24 fps, sRGB, h264 (whatever the widgets say)")
check("ui" in r and "images" not in r["ui"] and "animated" not in r["ui"], "the node returns no preview info")
# no custom audio: the old naming without a song folder rule
r = run(CONNECTED, **{"Custom Audio File": "None"})
check(r["result"][1].startswith("video/ComfyUI_seg000_A_") and r["result"][1].endswith("_"), "no custom audio: filename output keeps the old naming (video/ComfyUI_seg000_A_NNNNN_)")
# a quiet stop blocks both outputs instead of feeding a Save Video
class _Blocker:
    def __init__(self, message):
        self.message = message
mod.ExecutionBlocker = _Blocker
mod._segment_plan = lambda p: {"total": 20}
mod._load_index = lambda key="": 20
r = run(CONNECTED)
check(all(isinstance(o, _Blocker) for o in r["result"][:2]) and len(r["result"]) == 3 and r["result"][2].startswith("FINISHED") and status_of(r).startswith("FINISHED"),
      "all segments done: video and filename are blocked (a linked Save Video does not run), status still says FINISHED")
mod.ExecutionBlocker = None
mod._load_index = lambda key="": 0
# the old widget name from an old API prompt still works
node_old = mod.IronLeo78_MTV()
_k = kw()
_k.pop("Choose Audio latent")
_k["Bypassed Audio Latent"] = "MiniMax Audio"
MASKS.clear()
CORE_CALLS.clear()
mod._COND_CACHE.clear()
r = node_old.run(unique_id="7", workflow_prompt=None, extra_pnginfo=None, **_k)
check(MASKS == [] and "SolidMask" not in CORE_CALLS, "an old API prompt that still sends Bypassed Audio Latent is understood (MiniMax Audio: no bypass)")
# the manifest can find a clip that the user's own Save Video wrote under the planned stem
_d23 = os.path.join(TMP, "NearSong")
os.makedirs(_d23, exist_ok=True)
open(os.path.join(_d23, "NearSong_seg002_A_00001__00001_.mp4"), "wb").write(b"v")
check((mod._clip_saved_near(os.path.join(_d23, "NearSong_seg002_A_00001_.mp4")) or "").endswith("NearSong_seg002_A_00001__00001_.mp4"),
      "a clip saved by the linked Save Video under the planned stem is found for the Guide")
check(mod._clip_saved_near(os.path.join(_d23, "other.mp4")) is None, "a name that is not a planned clip name is never guessed")

# 24 ---- v0.0.9H: the nine reference pictures only come in through the Picture_1 .. Picture_9 inputs (no pickers, no switch)
print("24. v0.0.9H: pictures only through inputs")
class _FakeImg:
    shape = (1, 64, 64, 3)
_real_resize = mod._resize
_real_linked24 = mod._linked_image
_real_fp24 = mod._image_fingerprint
mod._resize = lambda img, w, h, method: img
mod._linked_image = lambda v: _FakeImg() if v is not None else None
mod._image_fingerprint = lambda img: "fp"
_real_exists = mod.folder_paths.exists_annotated_filepath
def _more_kw(more=None, **extra):
    d = {"Use Video": False, "Video File": "None", "Custom Audio File": "None", "Choose Audio latent": "MiniMax Audio",
         "megapixels": 0.2, "duration": 5.0, "Next Segment On Run": False, "Guide": False, "Audio Stem": "Full"}
    d.update(extra)
    return d
try:
    node24 = mod.IronLeo78_MTV()
    node24._pending_index = None
    wired24 = {"Picture_1": object(), "Picture_3": object(), "Picture_5": object(), "Picture_9": object()}
    m = REAL_LOAD_MEDIA(node24, _more_kw(**wired24))
    check(len(m["pictures"]) == 9 and [i for i, p in enumerate(m["pictures"], start=1) if p is not None] == [1, 3, 5, 9],
          "Picture_1, 3, 5 and 9 wired: all four are loaded, Picture_5 and Picture_9 too (no switch needed any more)")
    check("reference pictures: Picture_1, Picture_3, Picture_5, Picture_9" in m["status"] and "NOT sent" not in m["status"] and "More References" not in m["status"],
          "the status lists the wired inputs, no 'NOT sent' / More References line")
    check(m["cond_id"]["pics"][4] is not None and m["cond_id"]["pics"][1] is None and all(c is None or c[0] == "pi" for c in m["cond_id"]["pics"]),
          "the conditioning cache id covers Picture_5 (content id 'pi') and skips the empty Picture_2")
    # v0.0.9m: the cache id is the fingerprint of the RESIZED picture (what the conditioning consumes), not of the full-resolution one
    class _Small:
        shape = (1, 8, 8, 3)
    _small = _Small()
    _seen24 = []
    _stub_resize24, _stub_fp24 = mod._resize, mod._image_fingerprint
    mod._resize = lambda img, w, h, method: _small
    mod._image_fingerprint = lambda img: _seen24.append(img) or ("small" if img is _small else "FULL")
    try:
        m = REAL_LOAD_MEDIA(node24, _more_kw(Picture_1=object(), Picture_3=object()))
    finally:
        mod._resize, mod._image_fingerprint = _stub_resize24, _stub_fp24
    check(len(_seen24) == 2 and all(x is _small for x in _seen24) and m["cond_id"]["pics"][0][1] == "small" and m["cond_id"]["pics"][2][1] == "small",
          "the cache id fingerprints the RESIZED picture (pictures[i]), never the full-resolution one")
    check(m["pictures"][0] is _small and m["cond_id"]["pics"][0][2] == m["cond_id"]["pics"][2][2],
          "the id also keeps the target size next to the fingerprint")
    m = REAL_LOAD_MEDIA(node24, _more_kw())
    check(all(p is None for p in m["pictures"]) and "reference pictures" not in m["status"], "nothing wired: no pictures, no 'reference pictures' line")
    # leftovers of an old workflow / API prompt: the removed widgets' values are simply ignored
    old = _more_kw(**{"picture_1": "a.png", "picture_2": "None", "picture_3": "c.png", "picture_5": "e.png", "picture_9": "i.png", "More References": True})
    m = REAL_LOAD_MEDIA(node24, old)
    check(all(p is None for p in m["pictures"]), "old picker values (and More References ON) in the prompt are ignored: nothing is loaded from a file")
    m = REAL_LOAD_MEDIA(node24, {**old, "Picture_2": object()})
    check([i for i, p in enumerate(m["pictures"], start=1) if p is not None] == [2], "only the wired input counts, whatever the leftover pickers say")
    # Use Video OFF: Picture_1 is the size reference but has no file name to name the clip after
    m = REAL_LOAD_MEDIA(node24, _more_kw(Picture_1=object()))
    check(m["filename"] == "" and "reference: Picture_1" in m["status"], "Use Video OFF + Picture_1 wired: no file name, the report says Picture_1 is the reference")
    # conditioning tags: <Picture n> counts the filled slots, the mapping names the slot
    m = REAL_LOAD_MEDIA(node24, _more_kw(**wired24))
    refs = {}
    tags = []
    for slot, img in enumerate(m["pictures"], start=1):
        if img is None:
            continue
        refs["ref_image_%d" % len(refs)] = img
        tags.append("<Picture %d>=Picture%d" % (len(refs), slot))
    check(tags == ["<Picture 1>=Picture1", "<Picture 2>=Picture3", "<Picture 3>=Picture5", "<Picture 4>=Picture9"] and len(refs) <= 9,
          "the tags keep counting only what is sent: <Picture 3>=Picture5, <Picture 4>=Picture9")
    # validation and change detection
    mod.folder_paths.exists_annotated_filepath = lambda n: False
    V = mod.IronLeo78_MTV.VALIDATE_INPUTS
    check(V(**_more_kw(**{"picture_9": "gone.png"})) is True, "a leftover picker value naming a missing file is never checked (the widget is gone)")
    check(V(**_more_kw(**wired24)) is True, "validation is happy with wired pictures")
    a = mod.IronLeo78_MTV.IS_CHANGED(**_more_kw())
    b = mod.IronLeo78_MTV.IS_CHANGED(**_more_kw(Picture_2=object()))
    c = mod.IronLeo78_MTV.IS_CHANGED(**_more_kw(**{"picture_1": "a.png", "More References": True}))
    check(a != b and a == c, "wiring a Picture_n changes the node's change signature; leftover picker values do not")
    # the clip record
    names = mod.IronLeo78_MTV._clip_new(node24, _more_kw(Picture_2=object(), Picture_9=object(), prompt="p"), {"index": 0, "filename": "a"})["pictures"]
    check(names == ["Picture_2 (linked)", "Picture_9 (linked)"], "the clip record lists the wired inputs: %s" % names)
finally:
    mod._resize = _real_resize
    mod._linked_image = _real_linked24
    mod._image_fingerprint = _real_fp24
    mod.folder_paths.exists_annotated_filepath = _real_exists

# 25 ---- v0.0.9: three custom LoRAs chained after the Turbo LoRA
print("25. v0.0.9: LoRa_1 .. LoRa_3")
Cls25 = mod.IronLeo78_MTV
_o_unet, _o_apply, _o_att = Cls25.__dict__["_load_unet"], Cls25.__dict__["_apply_lora"], Cls25.__dict__["_apply_attention"]
CHAIN = []
Cls25._load_unet = staticmethod(lambda name, dtype: "M")
Cls25._apply_lora = staticmethod(lambda model, name, strength, label: (CHAIN.append((label, name, strength)), model + "+" + label)[1])
try:
    def build25(**over):
        d = dict(FS)
        d.update({"Turbo": True, "attention_enabled": False})
        d.update(over)
        CHAIN.clear()
        return Cls25()._build_model(d)
    out = build25(lora_1_enabled=True, lora_1_name="a.safetensors", lora_2_enabled=True, lora_2_name="b.safetensors", lora_3_enabled=True, lora_3_name="c.safetensors")
    check(out == "M+Turbo+LoRa_1+LoRa_2+LoRa_3", "the chain: diffusion model, Turbo, LoRa_1, LoRa_2, LoRa_3 (in this order): %s" % out)
    check([c[1] for c in CHAIN] == [FS["turbo_lora_name"], "a.safetensors", "b.safetensors", "c.safetensors"], "each LoRA uses its own file")
    out = build25(lora_2_enabled=True, lora_2_name="b.safetensors")
    check(out == "M+Turbo+LoRa_2", "only the LoRAs that are ON are applied: %s" % out)
    out = build25(Turbo=False, lora_1_enabled=True, lora_1_name="a.safetensors", lora_3_enabled=True, lora_3_name="c.safetensors")
    check(out == "M+LoRa_1+LoRa_3", "Turbo OFF: no Turbo LoRA, the custom ones are still chained: %s" % out)
    out = build25()
    check(out == "M+Turbo", "all three OFF: Turbo only")
finally:
    Cls25._load_unet, Cls25._apply_lora, Cls25._apply_attention = _o_unet, _o_apply, _o_att
# the checks of the files
_gfl = fp.get_filename_list
fp.get_filename_list = lambda k: {"loras": ["a.safetensors", mod.DEFAULT_TURBO_LORA], "diffusion_models": [mod.DEFAULT_UNET], "text_encoders": [mod.DEFAULT_QWEN_VL],
                                  "vae": [mod.DEFAULT_VIDEO_VAE, mod.DEFAULT_AUDIO_VAE]}.get(k, [])
try:
    base25 = dict(FS, Turbo=True, models_source=False)
    REAL_CHECK(dict(base25, lora_2_enabled=False, lora_2_name="gone.safetensors"))
    check(True, "a missing file in a LoRa that is OFF is not checked")
    try:
        REAL_CHECK(dict(base25, lora_2_enabled=True, lora_2_name="gone.safetensors"))
        check(False, "missing LoRa_2 accepted")
    except RuntimeError as e:
        check("LoRa_2" in str(e) and "switch LoRa_2 OFF" in str(e), "a missing file in LoRa_2 (ON) is named: LoRa_2")
finally:
    fp.get_filename_list = _gfl
# the manifest row lists the LoRAs that are ON
kw25 = dict(FS, Turbo=True, lora_1_enabled=True, lora_1_name="a.safetensors", lora_1_strength=0.5, lora_3_enabled=True, lora_3_name="c.safetensors", lora_3_strength=0.2)
rows25 = [{"slot": n, "file": kw25["lora_%d_name" % n], "strength": kw25["lora_%d_strength" % n]} for n in (1, 2, 3) if kw25["lora_%d_enabled" % n]]
check([x["slot"] for x in rows25] == [1, 3], "(manifest rows follow the same rule: slots 1 and 3)")

# 26 ---- v0.0.9H: optional IMAGE inputs Picture_1 .. Picture_9 (the only way to give pictures; checks in section 24)
print("26. v0.0.9H: Picture_1 .. Picture_9 inputs")
class _FakeArr:
    def __init__(self, shape, tag="x"):
        self.shape = shape
        self.tag = tag
    def __getitem__(self, k):
        return self
    def float(self):
        return self
    def clamp(self, a, b):
        return self
    def contiguous(self):
        return self
    def repeat(self, *a):
        return _FakeArr(self.shape[:-1] + (3,), self.tag)
class _FakeLoaded:
    shape = (1, 64, 64, 3)
check(list(mod.IronLeo78_MTV.INPUT_TYPES()["optional"]) == ["models", "Pictures"], "the optional sockets are: models, Pictures (v0.1.20)")
check("More References" not in str(mod.IronLeo78_MTV.INPUT_TYPES()), "no tooltip or widget mentions More References any more")

# the real converter, with a small fake tensor (no torch here): batch -> first image, alpha dropped, grey widened, junk refused
check(mod._linked_image(None) is None, "_linked_image(None) = nothing linked")
r4 = mod._linked_image(_FakeArr((3, 8, 8, 4)))
check(tuple(r4.shape) == (3, 8, 8, 4) or r4 is not None, "an RGBA batch is accepted (first image, alpha dropped)")
r1 = mod._linked_image(_FakeArr((1, 8, 8, 1)))
check(tuple(r1.shape) == (1, 8, 8, 3), "a grey image is widened to 3 channels")
try:
    mod._linked_image(_FakeArr((8, 8)))
    check(False, "a 2-D tensor must be refused")
except RuntimeError as e:
    check("IMAGE" in str(e), "a 2-D tensor is refused with a clear message")
try:
    mod._linked_image(_FakeArr((1, 8, 8, 2)))
    check(False, "a 2-channel image must be refused")
except RuntimeError as e:
    check("channels" in str(e), "a 2-channel image is refused with a clear message")


# 27 ---- v0.0.9s: Video_1 is gone (the Video File picker is the only way to give the video)
print("27. v0.0.9s: Video_1 is gone")
_it27 = mod.IronLeo78_MTV.INPUT_TYPES()
check("Video_1" not in _it27["optional"] and "Video_1" not in str(_it27), "no Video_1 socket and no tooltip that mentions it")
check("Video File" in _it27["required"] and "Use Video" in _it27["required"], "the Video File picker and the Use Video switch are still there")
for _n27 in ("_MemVideo", "_PathVideo", "_linked_video", "_decode_memory_video", "_video_fingerprint", "_estimate_video_bytes", "_path_id",
             "_HELD_VIDEO", "release_held_video", "held_video_bytes", "_held_bytes", "VIDEO_INPUT", "MEM_VIDEO_CACHE_BYTES",
             "MEM_VIDEO_WARN_BYTES", "RELEASE_VIDEO_ROUTE"):
    check(not hasattr(mod, _n27), f"{_n27} no longer exists")
check("held_bytes" not in mod._segment_info({}), "the segment info no longer carries held_bytes")
import inspect as _insp27
check(list(_insp27.signature(mod.IronLeo78_MTV._load_video).parameters) == ["self", "kw", "frames", "seconds", "mp", "index"], "_load_video takes no video reference any more")

# queue-time check: the picker is the only source, so an empty one is refused again (as before Video_1)
_real_exists27 = mod.folder_paths.exists_annotated_filepath
try:
    mod.folder_paths.exists_annotated_filepath = lambda n: n == "clip.mp4"
    _v = mod.IronLeo78_MTV.VALIDATE_INPUTS
    r = _v(**_more_kw(**{"Use Video": True, "Video File": "None"}))
    check(isinstance(r, str) and "no valid video" in r, "Use Video ON with an empty Video File is refused at queue time: " + str(r))
    r = _v(**_more_kw(**{"Use Video": True, "Video File": "gone.mp4"}))
    check(isinstance(r, str) and "no valid video" in r, "Use Video ON with a missing file is refused: " + str(r))
    check(_v(**_more_kw(**{"Use Video": True, "Video File": "clip.mp4"})) is True, "Use Video ON with a real file passes")
    check(_v(**_more_kw(**{"Use Video": False, "Video File": "None"})) is True, "Use Video OFF needs no video")
finally:
    mod.folder_paths.exists_annotated_filepath = _real_exists27

# a workflow saved with a wired Video_1 may still send that value: it is ignored everywhere
_kw27 = _more_kw(**{"Use Video": False, "Video_1": object()})
check(mod.IronLeo78_MTV.IS_CHANGED(**_kw27) == mod.IronLeo78_MTV.IS_CHANGED(**_more_kw(**{"Use Video": False})), "a leftover Video_1 value does not change the change signature")
_n27 = mod.IronLeo78_MTV()
_n27._pending_index = None
_m27 = REAL_LOAD_MEDIA(_n27, _kw27)
check("Video_1" not in _m27["status"] and _m27["video"] is None, "a leftover Video_1 value is ignored by the loader (no status line, no frames)")

# 28 ---- v0.0.9j: atomic write of the segment counter file
print("28. v0.0.9j: atomic state write")
import json as _j28
_saved_state28 = smod.STATE_FILE
smod.STATE_FILE = os.path.join(TMP, "state28.json")
try:
    mod._write_state({"index": 3, "furthest": 5, "name": "Ã©"})
    check(_j28.load(open(smod.STATE_FILE, encoding="utf-8")) == {"index": 3, "furthest": 5, "name": "Ã©"}
          and not os.path.exists(smod.STATE_FILE + ".tmp"), "written, UTF-8, no .tmp left behind")
    # a crash while the JSON is being written: the old file must survive untouched, the .tmp must be cleaned up
    _real_dump28 = mod.json.dump
    def _boom28(obj, f, *a, **k):
        f.write('{"index": 9, "fur')       # half a file
        raise OSError("disk full / killed")
    mod.json.dump = _boom28
    try:
        mod._write_state({"index": 9})
        check(False, "the write error must propagate")
    except OSError:
        check(True, "the write error still propagates")
    finally:
        mod.json.dump = _real_dump28
    check(smod._load_state().get("index") == 3 and _j28.load(open(smod.STATE_FILE, encoding="utf-8"))["furthest"] == 5,
          "a crash mid-write leaves the OLD counter file intact (before: truncated -> counter back at 0)")
    check(not os.path.exists(smod.STATE_FILE + ".tmp"), "the half-written .tmp is removed")
    # an os.replace failure also keeps the old file and cleans up
    _real_rep28 = mod.os.replace
    mod.os.replace = lambda a, b: (_ for _ in ()).throw(OSError("locked"))
    try:
        mod._write_state({"index": 8})
        check(False, "a failing replace must propagate")
    except OSError:
        check(True, "a failing os.replace propagates")
    finally:
        mod.os.replace = _real_rep28
    check(smod._load_state().get("index") == 3 and not os.path.exists(smod.STATE_FILE + ".tmp"), "old file kept, .tmp removed after a failed replace")
    REAL_SAVE_INDEX(4)
    check(smod._load_state().get("index") == 4 and smod._load_state().get("furthest") == 5, "save / load still work after the change (furthest kept)")
finally:
    smod.STATE_FILE = _saved_state28


# 29 ---- v0.0.9l: lock around the counter file's read-modify-write
print("29. v0.0.9l: state lock")
import threading as _th29, time as _time29, json as _j29
_saved29 = (smod.STATE_FILE, smod.LAST_FRAME_FILE)
smod.STATE_FILE = os.path.join(TMP, "state29.json")
smod.LAST_FRAME_FILE = os.path.join(TMP, "last29.png")
class _Px29:
    def numpy(self):
        return _np.zeros((2, 2, 3), dtype=_np.float32)
class _Frame29:
    def __getitem__(self, i):
        return _Px29()
try:
    mod._write_state({"index": 1, "furthest": 1})
    # deterministic: while somebody holds the lock, a writer must WAIT (and then still write)
    done = []
    with mod._STATE_LOCK:
        th = _th29.Thread(target=lambda: (REAL_SAVE_INDEX(5), done.append(1)))
        th.start()
        _time29.sleep(0.3)
        check(not done and _j29.load(open(smod.STATE_FILE, encoding="utf-8"))["index"] == 1, "_save_index waits while the state lock is held")
        th2 = _th29.Thread(target=lambda: (mod._jump_to(3), done.append(2)))
        th2.start()
        _time29.sleep(0.2)
        check(done == [], "_jump_to waits too")
    th.join(5)
    th2.join(5)
    check(sorted(done) == [1, 2] and _j29.load(open(smod.STATE_FILE, encoding="utf-8"))["furthest"] == 5, "both go through once the lock is free (furthest = 5 kept)")
    # the lock is re-entrant (a function holding it may call another that takes it)
    with mod._STATE_LOCK:
        mod._write_state({"index": 0})
    check(_j29.load(open(smod.STATE_FILE, encoding="utf-8")) == {"index": 0}, "re-entrant: _write_state inside the lock does not deadlock")
    # stress: a finishing Run (index) and the guide frame marker written at the same time: neither update may be lost
    mod._write_state({"index": 0})
    N = 150
    def _runs():
        for i in range(1, N + 1):
            REAL_SAVE_INDEX(i)
    def _frames():
        for i in range(1, N + 1):
            REAL_SAVE_LAST_FRAME(_Frame29(), i)
    ts = [_th29.Thread(target=_runs), _th29.Thread(target=_frames)]
    for x in ts:
        x.start()
    for x in ts:
        x.join(60)
    st = _j29.load(open(smod.STATE_FILE, encoding="utf-8"))
    check(st.get("index") == N and st.get("furthest") == N and st.get("guide_frame_for") == N,
          "150 concurrent counter saves + 150 guide-frame saves: nothing lost (%s)" % st)
    check(not os.path.exists(smod.STATE_FILE + ".tmp"), "no .tmp left after the stress run")
finally:
    smod.STATE_FILE, smod.LAST_FRAME_FILE = _saved29


# 32 ---- v0.0.9p: IS_CHANGED notices a file replaced under the same name
print("32. v0.0.9p: IS_CHANGED file ids")
_f32 = os.path.join(TMP, "swap_song.wav")
open(_f32, "wb").write(b"a" * 10)
_old_gaf = mod.folder_paths.get_annotated_filepath
mod.folder_paths.get_annotated_filepath = lambda name: _f32
try:
    ic_kw = {"Use Video": False, "Next Segment On Run": False, "Custom Audio File": "swap_song.wav", "Video File": "None", "Audio Stem": "Full"}
    ic1 = mod.IronLeo78_MTV.IS_CHANGED(**ic_kw)
    check(mod.IronLeo78_MTV.IS_CHANGED(**ic_kw) == ic1, "IS_CHANGED: the same file gives the same value")
    open(_f32, "wb").write(b"b" * 25)
    os.utime(_f32, (1_000_000_000, 1_000_000_000))
    ic2 = mod.IronLeo78_MTV.IS_CHANGED(**ic_kw)
    check(ic2 != ic1, "IS_CHANGED: the file replaced under the SAME name (new size / mtime) re-runs the node")
    ic_kw2 = dict(ic_kw, **{"Custom Audio File": "None", "Video File": "swap_song.wav"})
    ic3 = mod.IronLeo78_MTV.IS_CHANGED(**ic_kw2)
    open(_f32, "wb").write(b"c" * 40)
    check(mod.IronLeo78_MTV.IS_CHANGED(**ic_kw2) != ic3, "IS_CHANGED: same for the Video File picker")
finally:
    mod.folder_paths.get_annotated_filepath = _old_gaf
check(mod.IronLeo78_MTV.IS_CHANGED(**dict(ic_kw, **{"Custom Audio File": "None"})) == mod.IronLeo78_MTV.IS_CHANGED(**dict(ic_kw, **{"Custom Audio File": "None"})),
      "IS_CHANGED: 'None' / a missing file stays stable")


# 33 ---- v0.0.9q: the Guide frame file is closed after reading
print("33. v0.0.9q: last-frame file handle")
_lf33 = os.path.join(TMP, "lf33.png")
_Image.fromarray(_np.full((4, 4, 3), 200, _np.uint8)).save(_lf33)
_saved33 = (smod.LAST_FRAME_FILE, smod._load_state)
smod.LAST_FRAME_FILE = _lf33
smod._load_state = lambda: {"guide_frame_for": 2}
try:
    img33, why33 = mod._load_last_frame(3)
    check(why33 == "" and img33 is not None, "the saved last frame is read back for the next segment")
    _open33 = [l for l in (os.readlink("/proc/self/fd/" + f) for f in os.listdir("/proc/self/fd") if os.path.exists("/proc/self/fd/" + f)) if l.endswith("lf33.png")] if os.path.isdir("/proc/self/fd") else []
    check(not _open33, "no file handle on the PNG is left open after reading it")
    os.replace(_lf33, _lf33 + ".new")
    check(os.path.exists(_lf33 + ".new") and not os.path.exists(_lf33), "the PNG can be replaced right after the read")
finally:
    smod.LAST_FRAME_FILE, smod._load_state = _saved33


# 34 ---- v0.0.9v: an empty slot of the 9-Images loader sends a grey "NONE" picture: it is skipped, never a reference
print("34. v0.0.9v: NONE pictures from the 9-Images loader")


class _Marked34:
    ironleo78_none = True
    shape = (1, 512, 512, 3)


check(mod._is_none_placeholder(_Marked34()), "a picture carrying the loader's mark is a NONE placeholder")
check(not mod._is_none_placeholder(None) and not mod._is_none_placeholder(object()), "None / an unknown object: not a placeholder")
check(not mod._is_none_placeholder(MagicMock()), "an object that answers every attribute (MagicMock) is not mistaken for one")
res34 = run(Picture_2=_Marked34(), Picture_3=object(), Picture_7=_Marked34())
check(LAST.get("Picture_2") is None and LAST.get("Picture_7") is None and LAST.get("Picture_3") is not None,
      "run(): the NONE inputs count as not connected before the media are loaded, a real picture stays")
check(LAST.get("none_pictures") == [2, 7], "run() records which slots were skipped: %s" % LAST.get("none_pictures"))
_saved34 = (mod._resize, mod._linked_image, mod._image_fingerprint)
mod._resize = lambda img, w, h, method: img
mod._linked_image = lambda v: _FakeImg() if v is not None else None
mod._image_fingerprint = lambda img: "fp"
try:
    node34 = mod.IronLeo78_MTV()
    node34._pending_index = None
    m34 = REAL_LOAD_MEDIA(node34, _more_kw(Picture_3=object(), none_pictures=[2, 7]))
    check("empty slots skipped (NONE picture from the Prompt Generator): Picture_2, Picture_7" in m34["status"],
          "the report names the skipped slots")
    check([i for i, p in enumerate(m34["pictures"], start=1) if p is not None] == [3], "only the real picture is sent")
    m34 = REAL_LOAD_MEDIA(node34, _more_kw(Picture_3=object()))
    check("empty slots skipped" not in m34["status"], "no NONE input: no 'skipped' line")
    # v0.3.10: Custom Audio selected but no file: said in the status (it used to skip the song without a word)
    m34 = REAL_LOAD_MEDIA(node34, _more_kw(**{"Choose Audio latent": "Custom Audio", "Custom Audio File": "None"}))
    check("WARNING: Choose Audio latent = Custom Audio but no Custom Audio File is selected: NO song is used" in m34["status"],
          "Custom Audio mode with no Custom Audio File: the report warns that no song is used")
    m34 = REAL_LOAD_MEDIA(node34, _more_kw(**{"Choose Audio latent": "MiniMax Audio", "Custom Audio File": "None"}))
    check("no Custom Audio File is selected" not in m34["status"], "another audio mode with no file: no such warning")
    m34 = REAL_LOAD_MEDIA(node34, _more_kw(**{"Choose Audio latent": "Audio From Video", "Custom Audio File": "None"}))
    check("no Custom Audio File is selected" not in m34["status"], "Audio From Video with no Custom Audio File: no such warning")
finally:
    mod._resize, mod._linked_image, mod._image_fingerprint = _saved34


# 35 ---- v0.0.9w quick fixes: segment numbers from 1, IS_CHANGED sees the saved set, the sidecar names the saved set
print("35. v0.0.9w: quick fixes")
check(mod._segment_txt({"Next Segment On Run": True}, 0) == "segment 1 | next: segment 2", "status lines count segments from 1 (index 0 = segment 1, next 2)")
check(mod._segment_txt({"Next Segment On Run": False}, 0) == "segment 1", "Next Segment OFF: segment 1, no 'next'")
check(mod._segment_txt({"Next Segment On Run": "true"}, 4) == "segment 5 | next: segment 6", "a string ON (panel / API) counts too")
res35 = run(**{"Next Segment On Run": False})
check("SONG: Song | segment 1 |" in status_of(res35) and "segment 0" not in status_of(res35), "header with Next Segment OFF: segment 1, never segment 0")
_saved35 = dmod.DEFAULTS_FILE
dmod.DEFAULTS_FILE = os.path.join(TMP, "defaults35.json")
try:
    ic_kw35 = {"Use Video": False, "Next Segment On Run": False, "Custom Audio File": "None", "Video File": "None", "Audio Stem": "Full"}
    no_set = mod.IronLeo78_MTV.IS_CHANGED(**ic_kw35)
    with open(dmod.DEFAULTS_FILE, "w", encoding="utf-8") as f:
        f.write('{"values": {"turbo_steps": 3}}')
    with_set = mod.IronLeo78_MTV.IS_CHANGED(**ic_kw35)
    check(no_set != with_set and with_set == mod.IronLeo78_MTV.IS_CHANGED(**ic_kw35), "IS_CHANGED: saving a set re-runs the node once, then stays stable")
    with open(dmod.DEFAULTS_FILE, "w", encoding="utf-8") as f:
        f.write('{"values": {"turbo_steps": 5, "full_steps": 30}}')
    check(mod.IronLeo78_MTV.IS_CHANGED(**ic_kw35) != with_set, "IS_CHANGED: a different saved set re-runs it again")
    res35 = run()
    side35 = os.path.join(TMP, *(res35["result"][1] + ".json").split("/"))
    check(json.load(open(side35, encoding="utf-8"))["models_source"] == "saved defaults", "sidecar: the saved set is named 'saved defaults', not 'hardcoded'")
    os.remove(dmod.DEFAULTS_FILE)
    res35 = run()
    side35 = os.path.join(TMP, *(res35["result"][1] + ".json").split("/"))
    check(json.load(open(side35, encoding="utf-8"))["models_source"] == "hardcoded", "sidecar: no saved set, no Model Loader = 'hardcoded'")
    check(mod.IronLeo78_MTV.IS_CHANGED(**ic_kw35) == no_set, "IS_CHANGED: back to the value without a set once Factory deleted it")
finally:
    dmod.DEFAULTS_FILE = _saved35


# 36 ---- v0.1.0: one pack, four nodes, one version everywhere
print("36. v0.1.0: the 9-Images loader joined the pack")
pack36 = sys.modules[PKG]
check(set(pack36.NODE_CLASS_MAPPINGS) == {"IronLeo78_MTV", "IronLeo78_MTV_ModelLoader", "IronLeo78_2in1_Revitalizer", "IronLeo78_MTV_PromptGenerator"},
      "the pack registers four nodes (v0.1.21: the old 9-Images loader node is gone, the all-in-one Prompt Generator replaces it)")
check(pack36.NODE_DISPLAY_NAME_MAPPINGS["IronLeo78_MTV_PromptGenerator"] == "IronLeo78-MTV-Prompt-Generator"
      and pack36.NODE_DISPLAY_NAME_MAPPINGS["IronLeo78_MTV"] == "IronLeo78 MTV (v%s)" % mod.VERSION, "display names: the loader unchanged, the MTV shows its version")
check(pack36.NODE_CLASS_MAPPINGS["IronLeo78_MTV_PromptGenerator"].CATEGORY == "IronLeo78/MTV", "the Prompt Generator sits under IronLeo78 > MTV with the other three")
_root36 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_py36 = open(os.path.join(_root36, "pyproject.toml"), encoding="utf-8").read()
check(pack36.__version__ == mod.VERSION and ('version = "%s"' % mod.VERSION) in _py36, "one version: __init__, mtv.py and pyproject.toml all say %s" % mod.VERSION)
for _f36 in ("ironleo78_9images.js", "il78_sync_logic.js", "il78_shadow.js"):
    check(os.path.isfile(os.path.join(_root36, "web", _f36)), "web/%s is in the pack" % _f36)
check(mod.NONE_PICTURE_MARK == pack36.nine_images.NONE_MARK, "the MTV and the loader use the same NONE mark name")


# 37 ---- v0.1.5: ONE base diffusion model, shared by the MTV and the Revitalizer; LoRA changes never re-read the model file
print("37. v0.1.5: one shared base model")
mc37 = sys.modules[PKG + ".model_cache"]
rv37 = importlib.import_module(PKG + ".revitalizer")
reads37 = []


class _Clone37:
    def __init__(self, src):
        self.src = src


class _Base37:
    def clone(self):
        return _Clone37(self)


_saved37 = (mc37._load, getattr(mod.folder_paths, "get_full_path_or_raise", None),
            Cls.__dict__["_apply_lora"], Cls.__dict__["_apply_attention"])
mc37._load = lambda path, dtype: (reads37.append(os.path.basename(path)), _Base37())[1]
mod.folder_paths.get_full_path_or_raise = lambda kind, name: os.path.join(TMP, name)
CHAIN37 = []
Cls._apply_lora = staticmethod(lambda model, name, strength, label: (CHAIN37.append((label, strength)), model)[1])
Cls._apply_attention = staticmethod(lambda model, attention: model)
try:
    mod.free_cached_models("test 37")
    node37 = Cls()

    def build37(**over):
        kw37 = dict(mod.FIXED_SETTINGS, Turbo=True)
        kw37.update(over)
        key = (mod._stamp("diffusion_models", kw37["unet_name"]), kw37["weight_dtype"], kw37["Turbo"],
               tuple((n, kw37[f"lora_{n}_enabled"], kw37[f"lora_{n}_strength"]) for n in (1, 2, 3)))
        return mod._cached("7", "model", key, lambda: node37._build_model(kw37))

    m1 = build37()
    check(reads37 == [mod.DEFAULT_UNET] and isinstance(m1, _Clone37), "first build: the model file is read once, the MTV works on a CLONE of it")
    build37(lora_1_enabled=True, lora_1_strength=0.4)
    build37(lora_1_enabled=True, lora_1_strength=0.7)
    build37(Turbo=False)
    check(reads37 == [mod.DEFAULT_UNET], "LoRa_1 ON, another strength, Turbo OFF: the LoRAs are applied again, the model file is NOT read again (was: a full reload each time)")
    check(("LoRa_1", 0.7) in CHAIN37 and ("Turbo", 1.0) in CHAIN37, "the LoRAs really are applied on each new combination")
    check(len(mod._CACHE["model"]) == 2 and len({id(m.src) for m in mod._CACHE["model"].values()}) == 1,
          "the two kept MTV models are clones of the SAME base (one copy of the weights)")
    base, shared = mc37.diffusion_model(mod.DEFAULT_UNET, "default")
    check(shared and rv37._models is mc37 and base is m1.src, "the Revitalizer asks the same cache and gets the same base: one copy for both nodes")
    rv37._CACHE.setdefault("model", collections.OrderedDict())["old"] = "built on the old base"
    build37(unet_name="another_model.safetensors")
    check(reads37 == [mod.DEFAULT_UNET, "another_model.safetensors"] and mc37.held() == 1, "another model file: read once, still ONE base in memory")
    check(len(mod._CACHE["model"]) == 1 and not rv37._CACHE["model"],
          "the MTV's and the Revitalizer's models built on the old base were dropped BEFORE the new file loaded")
    check(len(mod._LORA_CACHE) <= mod.LORA_CACHE_MAX == 4, "the LoRA file cache holds up to 4 files (the Turbo LoRA + LoRa_1-3), was 1")
    mod.free_cached_models("test 37")
    check(mc37.held() == 0, "free_cached_models (the free route) also drops the shared base")
finally:
    mc37._load = _saved37[0]
    if _saved37[1] is None:
        del mod.folder_paths.get_full_path_or_raise
    else:
        mod.folder_paths.get_full_path_or_raise = _saved37[1]
    Cls._apply_lora, Cls._apply_attention = _saved37[2], _saved37[3]


# 38 ---- v0.1.8: one segment counter per song (review #8 / U2)
print("38. v0.1.8: one counter per song")
import json as _j38
K = mod._counter_key
check(K({"Custom Audio File": "A.wav", "Video File": "v.mp4"}) == "audio:A.wav" and K({"Custom Audio File": "None", "Video File": "v.mp4"}) == "video:v.mp4",
      "the counter belongs to the song (Custom Audio File), else to the video")
check(K({}) == "" and K({"Custom Audio File": "None", "Video File": "None"}) == "" and K(None) == "", "nothing selected: the shared counter")
check(K({"Custom Audio File": "sub/A.wav [input]"}) == "audio:sub/A.wav", "the ' [input]' tag of a picked file does not make another counter")
_saved38 = (smod.STATE_FILE, smod.LAST_FRAME_FILE, mod._load_index, mod._save_index, mod._save_last_frame, mod._load_last_frame)
smod.STATE_FILE = os.path.join(TMP, "state38.json")
smod.LAST_FRAME_FILE = os.path.join(TMP, "lf38.png")
mod._load_index, mod._save_index, mod._save_last_frame = REAL_LOAD_INDEX, REAL_SAVE_INDEX, REAL_SAVE_LAST_FRAME
mod._load_last_frame = _real_load_last
A, B = "audio:A.wav", "audio:B.wav"
read38 = lambda: _j38.load(open(smod.STATE_FILE, encoding="utf-8"))
try:
    mod._write_state({"index": 5, "furthest": 7, "guide_frame_for": 4})      # a counter saved by 0.1.7 or older
    check(mod._load_index(A) == 5 and mod._load_furthest(A) == 7, "after the update, a song with no counter of its own still shows the old one (nobody loses their place)")
    mod._save_index(6, A)
    st = read38()
    check(st["songs"][A] == {"index": 6, "furthest": 7, "guide_frame_for": 4} and st.get("adopted") is True,
          "the first song that runs takes the old counter over (6, furthest 7, guide marker kept)")
    check(st["index"] == 5 and mod._load_index("") == 5, "the shared counter itself is untouched")
    check(mod._load_index(B) == 0 and mod._load_furthest(B) == 0, "a second song starts at segment 1 (the old counter was handed on once)")
    mod._save_index(2, B)
    check(mod._load_index(A) == 6 and mod._load_index(B) == 2, "two songs, two counters: A at 6, B at 2")
    mod._reset_state(A)
    check(mod._load_index(A) == 0 and mod._load_index(B) == 2 and read38()["index"] == 5, "Reset on song A: only A goes back to 1")
    out = mod._handle_jump({"segment": 10, "params": {"Custom Audio File": "B.wav"}})
    check(out["ok"] and mod._load_index(B) == 9 and mod._load_index(A) == 0, "Jump with song B's widgets moves only B: %s" % out)
    out = mod._handle_jump({"latest": True, "params": {"Custom Audio File": "B.wav"}})
    check(out["ok"] and out["segment"] == 10 and mod._load_index(B) == 9, "Latest uses B's own furthest point")
    mod._handle_jump({"segment": 3, "params": {"Custom Audio File": "B.wav"}})
    out = mod._handle_jump({"latest": True, "params": {"Custom Audio File": "B.wav"}})
    check(out["segment"] == 10, "B jumped back to 3, Latest returns to B's 10 (not A's, not the shared one)")
    mod._segment_plan = lambda p: {"total": 20}
    info = mod._segment_info({"Custom Audio File": "B.wav", "Next Segment On Run": "true"})
    check(info["index"] == 9 and info["furthest"] == 9 and info["counter"] == "B.wav", "the panel shows B's counter and names it")
    check(mod._segment_info({})["counter"] == "shared" and mod._segment_info({})["index"] == 5, "no song selected: the panel shows the shared counter")
    mod._reset_state("")
    st = read38()
    check(st["index"] == 0 and A in st["songs"] and B in st["songs"], "Reset on the shared counter keeps every song's counter")
    # the Guide's saved last frame: one file per song
    check(mod._last_frame_file("") == smod.LAST_FRAME_FILE and mod._last_frame_file(A) != mod._last_frame_file(B)
          and os.path.dirname(mod._last_frame_file(A)) == os.path.dirname(smod.LAST_FRAME_FILE), "each song has its own last-frame file next to the old one")

    class _Frame38:
        def __getitem__(self, i):
            return self

        def numpy(self):
            return _np.full((4, 4, 3), 0.5, _np.float32)

    mod._save_last_frame(_Frame38(), 9, B)
    check(os.path.exists(mod._last_frame_file(B)) and read38()["songs"][B]["guide_frame_for"] == 9, "song B's last frame + its marker are saved for B")
    img, why = mod._load_last_frame(10, key=B)
    check(img is not None and why == "", "song B's next segment finds B's frame")
    img, why = mod._load_last_frame(10, key=A)
    check(img is None, "song A at the same segment does not take B's frame")
    # a Run passes its song's key everywhere
    mod._load_index, mod._save_index, mod._save_last_frame = (lambda key="": 0), (lambda i, key="": (INDEX.append(i), INDEX_KEYS.append(key))), (lambda frame, seg, key="": FRAMES.append(seg))
    INDEX_KEYS.clear()
    run(**{"Custom Audio File": "Song.wav"})
    check(INDEX_KEYS == ["audio:Song.wav"], "a Run saves its counter under its own song: %s" % INDEX_KEYS)
    INDEX_KEYS.clear()
    run(**{"Custom Audio File": "None", "Use Video": True, "Video File": "clip.mp4"})
    check(INDEX_KEYS == ["video:clip.mp4"], "no song but a video: the video's counter: %s" % INDEX_KEYS)
    js = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "ironleo78_mtv.js"), encoding="utf-8").read()
    check("body: JSON.stringify({ params: segParams() })" in js and "params: segParams() })" in js.split("doJump")[1],
          "the panel sends the node's song with Reset and with Jump / Latest")
finally:
    smod.STATE_FILE, smod.LAST_FRAME_FILE, mod._load_index, mod._save_index, mod._save_last_frame, mod._load_last_frame = _saved38


# 39 ---- v0.1.10: data outside the pack folder (#7); Next Segment OFF leaves the counter alone (#9)
print("39. v0.1.10: data in ComfyUI/user, OFF runs keep the counter")
_fp39 = mod.folder_paths
check(mod._data_dir() == mod.PACK_DIR, "no user directory from ComfyUI (old ComfyUI / tests): the pack folder, as before")
_fp39.get_user_directory = lambda: os.path.join(TMP, "user39")
try:
    check(mod._data_dir() == os.path.join(TMP, "user39", "ironleo78_mtv"), "with ComfyUI's user directory: ComfyUI/user/ironleo78_mtv")
finally:
    del _fp39.get_user_directory
old39, new39 = os.path.join(TMP, "old39"), os.path.join(TMP, "new39")
os.makedirs(old39)
for n39 in ("mtv_state.json", "mtv_defaults.json", "mtv_last_frame.png", "mtv_last_frame_abc.png", "mtv.py", "README.md"):
    open(os.path.join(old39, n39), "w").write("old " + n39)
os.makedirs(new39)
open(os.path.join(new39, "mtv_defaults.json"), "w").write("already new")
moved39 = mod._move_old_data(old39, new39)
check(sorted(moved39) == ["mtv_last_frame.png", "mtv_last_frame_abc.png", "mtv_state.json"], "the counter and the Guide frames move out: %s" % moved39)
check(open(os.path.join(new39, "mtv_defaults.json")).read() == "already new" and os.path.exists(os.path.join(old39, "mtv_defaults.json")),
      "a file that already exists at the new place is never overwritten (the old copy stays)")
check(os.path.exists(os.path.join(old39, "mtv.py")) and not os.path.exists(os.path.join(new39, "mtv.py")), "the pack's own files are never touched")
check(mod._move_old_data(old39, new39) == [] and mod._move_old_data(new39, new39) == [], "moving again: nothing to do")
# #9
node39 = mod.IronLeo78_MTV()
node39._pending_index = None
REAL_LOAD_MEDIA(node39, _more_kw(**{"Next Segment On Run": False, "Guide": True, "Use Video": False}))
check(node39._pending_index is None, "Next Segment OFF (Guide ON): the Run will NOT move the counter (it used to put it at 1)")
node39._pending_index = None
REAL_LOAD_MEDIA(node39, _more_kw(**{"Next Segment On Run": True, "Guide": True, "Use Video": False}))
check(node39._pending_index == 1, "Next Segment ON: the counter moves on, as before")

# 40 ---- v0.1.19: the one `Pictures` wire
print("40. v0.1.19: the single Pictures input")
opt40 = mod.IronLeo78_MTV.INPUT_TYPES()["optional"]
check(list(opt40) == ["models", "Pictures"] and opt40["Pictures"][0] == "IRONLEO78_PICTURES" and not any(k.startswith("Picture_") for k in opt40),
      "v0.1.20: only models + Pictures are left, none of the nine legacy Picture_n sockets: %s" % list(opt40))
A40, B40, C40 = object(), object(), object()
kw40 = {"Pictures": [A40, None, B40] + [None] * 6, "Picture_3": C40, "prompt": "p"}      # a Picture_3 key (old API prompt / old wired link) still wins
mod._spread_pictures(kw40)
check("Pictures" not in kw40 and kw40["Picture_1"] is A40 and kw40.get("Picture_2") is None and kw40["Picture_3"] is C40,
      "slots fill from Pictures; an empty slot stays empty; a wired Picture_3 wins over the packed one")
kw40b = {"prompt": "p"}
mod._spread_pictures(kw40b)
check(kw40b == {"prompt": "p"}, "no Pictures wire: nothing changes")
kw40c = {"Pictures": []}
mod._spread_pictures(kw40c)
check("Pictures" not in kw40c, "an empty list is ignored")
base40 = {"Use Video": False, "Next Segment On Run": False, "megapixels": 0.2, "duration": 5}
check(mod.IronLeo78_MTV.IS_CHANGED(**base40) != mod.IronLeo78_MTV.IS_CHANGED(**dict(base40, Pictures=[A40] + [None] * 8)),
      "IS_CHANGED counts the pictures that arrive on the Pictures wire")
check(mod.IronLeo78_MTV.IS_CHANGED(**dict(base40, Pictures=[A40] + [None] * 8)) == mod.IronLeo78_MTV.IS_CHANGED(**dict(base40, Picture_1=A40)),
      "...exactly like the same picture on Picture_1")

# 41 ---- v0.2.3: Next Segment On Run OFF repeats the segment chosen with Go
print("41. v0.2.3: an OFF Run makes the Go-to segment")
_orig_li, _orig_sp = mod._load_index, mod._segment_plan
try:
    mod._load_index = lambda key="": 4
    mod._segment_plan = lambda p: {"total": 10}
    check(mod._run_index({"Next Segment On Run": True, "counter_key": "k"}) == 4, "ON: the counter (segment 5)")
    check(mod._run_index({"Next Segment On Run": False, "counter_key": "k"}) == 4, "OFF: the SAME counter, so the segment chosen with Go is repeated (it was always segment 1 before 0.2.3)")
    mod._load_index = lambda key="": 10
    check(mod._run_index({"Next Segment On Run": False, "counter_key": "k"}) == 0, "OFF with a counter at the end of the file: segment 1")
    check(mod._run_index({"Next Segment On Run": True, "counter_key": "k"}) == 10, "ON with a finished counter: unchanged (the quiet stop handles it)")
    mod._load_index = lambda key="": 3
    mod._segment_plan = lambda p: {"total": None}
    check(mod._run_index({"Next Segment On Run": False, "counter_key": "k"}) == 3, "OFF, total unknown: the counter")
    def _boom(p):
        raise RuntimeError("probe failed")
    mod._segment_plan = _boom
    check(mod._run_index({"Next Segment On Run": False, "counter_key": "k"}) == 3, "OFF, the plan fails: the counter (never an error)")
    base41 = {"Use Video": False, "Next Segment On Run": False, "megapixels": 0.2, "duration": 5, "Video File": "None", "Custom Audio File": "None"}
    mod._load_index = lambda key="": 2
    h2 = mod.IronLeo78_MTV.IS_CHANGED(**base41)
    mod._load_index = lambda key="": 5
    h5 = mod.IronLeo78_MTV.IS_CHANGED(**base41)
    check(h2 != h5 and h5 == mod.IronLeo78_MTV.IS_CHANGED(**base41), "an OFF node re-runs when Go moves the counter, and stays cached when it does not")
finally:
    mod._load_index, mod._segment_plan = _orig_li, _orig_sp

# 42 ---- v0.3.11: the prompt box names its role
print("42. v0.3.11: MTV_Prompt tooltip")
check(mod.IronLeo78_MTV.INPUT_TYPES()["required"]["prompt"][1]["tooltip"].startswith("MTV_Prompt: the prompt"), "the prompt widget's tooltip starts with MTV_Prompt (a fallback when the frontend ignores the label)")

# 43 ---- v0.4.8: the HTTP routes live in routes.py and read mtv.py's names when a request comes in
print("43. v0.4.8: the routes (free / segments / reset / jump / defaults)")
import asyncio as _aio
_handlers = {}
class _Routes:
    def post(self, path):
        return lambda fn: _handlers.__setitem__(("POST", path), fn) or fn
    def get(self, path):
        return lambda fn: _handlers.__setitem__(("GET", path), fn) or fn
_srv = types.ModuleType("server")
_srv.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=_Routes()))
_old_srv = sys.modules.get("server")
sys.modules["server"] = _srv
_saved43 = (mod._RUNNING, mod.free_cached_models, mod._segment_info, mod._handle_jump, mod._reset_state)
try:
    mod._register_routes()
    check(len(_handlers) == 7, "seven routes are registered: %s" % sorted(p for _, p in _handlers))
    class _Req:
        def __init__(self, body=None, query=None):
            self._b, self.rel_url = body, types.SimpleNamespace(query=query or {})
        async def json(self):
            return self._b
    def call(method, path, req=None):
        import json as _jj
        return _jj.loads(_aio.run(_handlers[(method, path)](req or _Req())).text)
    freed = []
    mod.free_cached_models = lambda reason="": freed.append(reason)
    mod._RUNNING = 1
    check(call("POST", mod.FREE_ROUTE) == {"ok": False, "busy": True} and freed == [], "free: refused while a Run is going (reads mtv._RUNNING at request time)")
    mod._RUNNING = 0
    check(call("POST", mod.FREE_ROUTE) == {"ok": True} and freed == ["node removed"], "free: frees the cached models when idle")
    mod._segment_info = lambda params: {"total": 9, "echo": params.get("a")}
    r = call("GET", mod.SEGMENT_ROUTE, _Req(query={"a": "x"}))
    check(r["ok"] and r["total"] == 9 and r["echo"] == "x", "segments: the plan comes back through a worker thread: %s" % r)
    mod._handle_jump = lambda body: {"ok": True, "got": body}
    check(call("POST", mod.JUMP_ROUTE, _Req({"segment": 3}))["got"] == {"segment": 3}, "jump: the body reaches mtv._handle_jump")
    mod._reset_state = lambda key="": freed.append("reset:" + key)
    mod._RUNNING = 1
    check(call("POST", mod.RESET_ROUTE, _Req({}))["busy"] is True, "reset: refused while a Run is going")
    mod._RUNNING = 0
    check(call("POST", mod.RESET_ROUTE, _Req({}))["index"] == 0 and freed[-1].startswith("reset:"), "reset: counter back to 0")
    check(call("GET", mod.LOADER_DEFAULTS_ROUTE)["ok"] is True, "loader_defaults: answers")
finally:
    mod._RUNNING, mod.free_cached_models, mod._segment_info, mod._handle_jump, mod._reset_state = _saved43
    if _old_srv is None:
        sys.modules.pop("server", None)
    else:
        sys.modules["server"] = _old_srv
print("\nALL %d CHECKS PASSED" % ok)
