# Stub-based test of the v0.6 orchestration (one clip per Run, phase order, Save Latent toggle, caches, no output sockets / no preview, song name from the
# custom audio file, error paths, Model Loader overrides, segment count, quiet end,
# prompt sidecar, manifest upgrade, reset, jump to segment, guide read back from a clip).
# Needs no ComfyUI, GPU or torch:   python tests/test_phased_run.py
# ComfyUI only imports __init__.py, so this folder is ignored at runtime.
import sys, types, os, tempfile, importlib, collections
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

cx = types.ModuleType("comfy_extras"); nm = types.ModuleType("comfy_extras.nodes_minimax_h3")
COND_CALLS = []
class MiniMaxH3ReferenceToVideo:
    @staticmethod
    def execute(**kw):
        COND_CALLS.append(kw["prompt"])
        if kw["prompt"] == "BOOM":
            raise RuntimeError("encoder exploded")
        return ([["emb", {"p": kw["prompt"]}]], {"samples": "EMPTY:" + kw["prompt"]})
nm.MiniMaxH3ReferenceToVideo = MiniMaxH3ReferenceToVideo
sys.modules["comfy_extras"] = cx; sys.modules["comfy_extras.nodes_minimax_h3"] = nm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
mod = importlib.import_module(PKG + ".mtv")
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
def fake_core(name, provided, strict=(), hidden=None, notes=None, hoist=False):
    if name == "SaveVideo":
        pre = provided["filename_prefix"]
        EVENTS.append(("save", pre)); SAVES.append(pre)
        if COUNT_SAVES: SAVE_N[pre] = SAVE_N.get(pre, 0) + 1      # like ComfyUI: the next free number of this prefix
        else: SAVE_N[pre] = 1
        return (), {"images": [{"filename": pre.split("/")[-1] + "_%05d_.mp4" % SAVE_N[pre], "subfolder": pre.split("/")[0]}]}
    if name == "SamplerCustomAdvanced":
        try:
            SIGMA_CALLS.append([round(float(x), 4) for x in provided["sigmas"]])
        except (TypeError, ValueError):
            SIGMA_CALLS.append(None)           # the first pass uses a stub scheduler output
        EVENTS.append(("sample", provided["latent_image"]))
        return (("S(" + str(provided["latent_image"]) + ")",), None)
    if name == "LTXVSeparateAVLatent":
        EVENTS.append(("separate",)); return (({"samples": "vlat"}, {"samples": "alat"}), None)
    if name == "VAEDecode":
        EVENTS.append(("decode", provided["samples"])); return (("IMAGES",), None)
    if name == "VAEDecodeAudio": return (("AUDIO",), None)
    if name == "CreateVideo": return (("VIDEO",), None)
    if name == "LTXVConcatAVLatent": return (({"samples": "CAT"},), None)
    if name == "MiniMaxH3AddGuide": return (([["g", {}]], ), None)
    if name == "BasicScheduler":
        STEPS.append(provided["steps"]); return ((name,), None)
    if name in ("RandomNoise", "BasicGuider", "KSamplerSelect", "BasicScheduler", "TrimAudioDuration",
                "VAEEncodeAudio", "SolidMask", "SetLatentNoiseMask"):
        return ((name,), None)
    raise AssertionError("unexpected core node " + name)
mod._core = fake_core
LATENTS = []      # v0.3: what the node would write to disk for a later upscale
def _fake_write_latent(path, samples, metadata):
    LATENTS.append((path, samples, metadata)); open(path, "wb").write(b"L")
mod._write_latent_file = _fake_write_latent
CONDS = []        # v0.4: what the node would write to disk next to the latents
def _fake_write_conditioning(path, conditioning, metadata):
    CONDS.append((path, conditioning, metadata)); open(path, "wb").write(b"C"); return {"unsupported": []}
mod._write_conditioning_file = _fake_write_conditioning

orig_cond = mod.IronLeo78_MTV._conditioning_cached
def traced_cond(self, clip, vv, va, kw, media, mk):
    EVENTS.append(("cond", kw["prompt"]))
    return orig_cond(self, clip, vv, va, kw, media, mk)
mod.IronLeo78_MTV._conditioning_cached = traced_cond

mod._last_frame_of = lambda images: "FRAME"
FRAMES = []
mod._save_last_frame = lambda frame, seg: FRAMES.append(seg)
INDEX = []
REAL_LOAD_INDEX = mod._load_index
REAL_SAVE_INDEX = mod._save_index
mod._save_index = lambda i: INDEX.append(i)
ROWS = []
REAL_APPEND = mod._append_manifest
mod._append_manifest = lambda song, rows: (ROWS.extend(rows), "Song/manifest.csv")[1]

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
        "Bypassed Audio Latent": False,
        "Save Latent": False, "Guide": False})
    for i in range(1, 4):
        d["picture_%d" % i] = "pic%d.png" % i
    d.update(over)
    return d

def run(prompt_graph=None, **over):
    EVENTS.clear(); SAVES.clear(); FRAMES.clear(); INDEX.clear(); ROWS.clear()
    node = mod.IronLeo78_MTV()
    return node.run(unique_id="7", workflow_prompt=prompt_graph, extra_pnginfo=None, **kw(**over))

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
check(res["result"] == () and Cls.RETURN_TYPES == (), "no output sockets (v2.4)")
check("run order" not in status_of(res) and "upscal" not in status_of(res).lower(), "the status no longer talks about run order or upscaling")
check("SONG: Song | segment 1 (seg000)" in status_of(res), "status header names the song and the segment (custom audio)")
check("scene" not in status_of(res).lower() and "Picture4" not in status_of(res), "the report no longer mentions scenes")
check("--- Song_seg000_A ---" in status_of(res) and "manifest: Song/manifest.csv" in status_of(res), "report block is headed by the file tag, with the manifest line")
check("saved: Song/Song_seg000_A_00001_.mp4" in status_of(res), "the report names the saved clip")

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
mod._COND_CACHE.clear(); COND_CALLS.clear()
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
    m = make_media(); m["cond_id"]["pics"] = list(m["cond_id"]["pics"]); m["cond_id"]["pics"][1] = ("p", ("OTHER.png", 2, 2), (512, 512)); return m
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
got[0][0][1]["MUTATED"] = True; got[1]["samples"] = "MUTATED"
check(repr(entry[0]) + repr(entry[1]) == snapshot or "MUTATED" not in repr(entry), "a caller mutating the returned copy does not touch the cached entry")

# 5 ---- no outputs, song naming (v2.4)
print("5. no outputs + song name")
r = run(NOT_CONNECTED)
check(r["result"] == () and "text" in r["ui"] and "images" not in r["ui"], "result is empty, only the status text is returned (no video preview)")
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

# 6 ---- Scene 2 is gone (v2.8)
print("6. Scene 2 is gone")
t = Cls.INPUT_TYPES()["required"]
check(not any(k in t for k in ("Scene 2", "prompt_2", "picture_4", "picture_5", "picture_6")), "no Scene 2 / prompt_2 / Picture4-6 widgets")
check(Cls.SLOTS == 3 and [k for k in t if k.startswith("picture_")] == ["picture_1", "picture_2", "picture_3"], "exactly Picture1-3")
check(list(t)[-3:] == ["picture_1", "picture_2", "picture_3"] and list(t)[-4] == "Guide", "v2.8.2: the picture pickers are the LAST widgets (right above the thumbnails)")
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
# something fails AFTER the clip was saved: the clip is still logged in the manifest, the counter does not move
real_last = mod._last_frame_of
def boom_last(images): raise RuntimeError("last frame exploded")
mod._last_frame_of = boom_last
try:
    run(CONNECTED)
    check(False, "should have raised")
except RuntimeError as e:
    check("last frame exploded" in str(e), "a failure after the save is raised")
mod._last_frame_of = real_last
check(SAVES == ["Song/Song_seg000_A"] and len(ROWS) == 1 and ROWS[0]["file"] and INDEX == [],
      "the clip that was already saved is logged in the manifest, the counter did not move")

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
mod._cached("1", "video vae", ("v1",), lambda: object()); mod._cached("1", "video vae", ("v2",), lambda: object())
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
a = mod._load_custom_audio("song.wav"); b = mod._load_custom_audio("song.wav")
check(len(calls) == 1 and a is b, "decoded once, second Run reuses it")
os.utime(os.path.join(TMP, "song.wav"), (1, 1))
mod._load_custom_audio("song.wav")
check(len(calls) == 2, "file changed on disk -> decoded again")
check(mod._load_custom_audio("None") is None, "None -> no audio")

# 9 ---- widget list
print("9. widgets")
t = mod.IronLeo78_MTV.INPUT_TYPES()["required"]
keys = list(t)
check(keys[-4] == "Guide" and "Unload After Run" not in keys, "Guide comes right before the pictures, Unload After Run is gone: %s" % keys[-5:])
check(not any(k.startswith("prompt_list") for k in keys), "no per-segment prompt list widgets (just prompt)")
check("Phased Run" not in keys, "Phased Run widget is gone")
check(keys[-5] == "Save Latent" and keys[keys.index("Bypassed Audio Latent") + 1] == "Save Latent",
      "Save Latent sits right after Bypassed Audio Latent (where Latent Upscale was) and right before Guide; Song / Section widgets are gone")
check(len(keys) == 15, "15 widgets in all (the same count as the saved-workflow migration in the JS expects): %d" % len(keys))

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
check(d["megapixels"] == 0.2 and d["duration"] == 15.0, "defaults: megapixels 0.2, duration 15 s")
check(d["Turbo"] is True and d["Guide"] is True, "defaults: Turbo and Guide are ON")
check(d["Save Latent"] is False and mod.DEFAULT_SAVE_LATENT is False, "defaults: Save Latent is OFF")
check(not any(k in d for k in ("custom_lora_enabled", "Custom_LoRa", "Custom_LoRa_STR")), "v2.8.6: no custom LoRA widgets on the MTV")
check(mod.DEFAULT_CUSTOM_LORA_ENABLED is False and mod.FIXED_SETTINGS["custom_lora_enabled"] is False
      and mod.FIXED_SETTINGS["custom_lora_name"] == "H3_Unlocked_V2.safetensors" and mod.FIXED_SETTINGS["custom_lora_strength"] == 0.65,
      "hardcoded custom LoRA: OFF, H3_Unlocked_V2.safetensors, 0.65")
check(not d["Use Video"] and not d["Next Segment On Run"] and "noise_seed" not in d,
      "defaults: Use Video, Next Segment OFF; no noise_seed widget on the MTV (v2.8.5)")
opt = mod.IronLeo78_MTV.INPUT_TYPES()["optional"]
check(list(opt) == ["models"] and opt["models"][0] == "IRONLEO78_MTV_MODELS", "optional 'models' socket, no widget")
fp.get_filename_list = lambda k: [mod.DEFAULT_UNET, mod.DEFAULT_QWEN_VL, mod.DEFAULT_VIDEO_VAE,
                                  mod.DEFAULT_AUDIO_VAE, mod.DEFAULT_TURBO_LORA]
good = mod.IronLeo78_MTV.VALIDATE_INPUTS(**kw())
check(good is True, "validate passes with the default widgets (got %r)" % (good,))
check(mod.IronLeo78_MTV.VALIDATE_INPUTS(**{**kw(), "Save Latent": True, "upscale_megapixels": "junk", "Upscale Output": "bogus"}) is True,
      "validate no longer looks at any upscale value (old leftovers are harmless)")

# 10 ---- old workflow (no v2.1 / v2.2 widgets)
print("10. workflow without the Save Latent widget")
node = mod.IronLeo78_MTV()
k = kw(); [k.pop(x) for x in ("Save Latent",)]
EVENTS.clear()
r = node.run(unique_id="7", workflow_prompt=None, extra_pnginfo=None, **k)
check(status_of(r).startswith("Video OFF"), "runs with defaults")
check("models: hardcoded defaults" in status_of(r) and "latent saved" not in status_of(r), "status: hardcoded models, no latent saved (Save Latent defaults to OFF)")


# 11 ---- Model Loader (v2.3)
print("11. Model Loader")
mod._COND_CACHE.clear()
r = run(CONNECTED)
check(LAST["unet_name"] == mod.DEFAULT_UNET and STEPS[-1] == 4,
      "no manager: hardcoded models, Turbo = 4 steps")
STEPS.clear()
run(CONNECTED, Turbo=False)
check(STEPS[-1] == 25, "no manager: Turbo OFF = 25 steps")
fp.get_filename_list = lambda k: {"diffusion_models": ["d1.safetensors", mod.DEFAULT_UNET],
                                  "loras": ["t1.safetensors"], "text_encoders": ["c1.safetensors", mod.DEFAULT_QWEN_VL],
                                  "vae": ["v1.safetensors", "a1.safetensors", mod.DEFAULT_VIDEO_VAE,
                                          mod.DEFAULT_AUDIO_VAE]}.get(k, [])
ins = mgr.IronLeo78_MTV_ModelLoader.INPUT_TYPES()["required"]
check(list(ins) == ["unet_name", "custom_lora_enabled", "custom_lora_name", "custom_lora_strength", "turbo_lora_name", "qwen_vl_name", "video_vae_name", "audio_vae_name",
                    "turbo_steps", "full_steps", "noise_seed"], "manager widgets (no upscale model any more): %s" % list(ins))
check(ins["unet_name"][1]["default"] == mod.DEFAULT_UNET, "hardcoded diffusion model pre-selected when installed")
check(ins["turbo_lora_name"][1]["default"] == "t1.safetensors", "default missing: first installed file")
check(ins["turbo_steps"][1]["default"] == 4 and ins["full_steps"][1]["default"] == 25, "step defaults 4 / 25")
M = mgr.IronLeo78_MTV_ModelLoader()
models = M.build(unet_name="d1.safetensors", custom_lora_enabled=True, custom_lora_name="t1.safetensors", custom_lora_strength=0.5,
                 turbo_lora_name="t1.safetensors", qwen_vl_name="c1.safetensors",
                 video_vae_name="v1.safetensors", audio_vae_name="a1.safetensors",
                 turbo_steps=6, full_steps=40, noise_seed=4242)[0]
check(models["unet_name"] == "d1.safetensors" and models["turbo_steps"] == 6, "manager output dict")
STEPS.clear(); LAST.clear()
r = run(CONNECTED, models=models)
check(LAST["unet_name"] == "d1.safetensors" and LAST["turbo_lora_name"] == "t1.safetensors"
      and LAST["qwen_vl_name"] == "c1.safetensors" and LAST["video_vae_name"] == "v1.safetensors"
      and LAST["audio_vae_name"] == "a1.safetensors",
      "all five model names overridden")
check(STEPS[-1] == 6, "Turbo ON uses turbo_steps (6)")
check(ins["custom_lora_enabled"][1]["default"] is False and ins["custom_lora_strength"][1]["default"] == 0.65
      and ins["custom_lora_name"][0][0] == "None", "manager custom LoRA: OFF by default, strength 0.65, list starts with None")
check(LAST["custom_lora_enabled"] is True and LAST["custom_lora_name"] == "t1.safetensors" and LAST["custom_lora_strength"] == 0.5
      and "custom_lora=ON" in status_of(r), "v2.8.6: custom LoRA toggle / file / strength come from the Model Loader")
try:
    run(CONNECTED, models=dict(models, custom_lora_name="gone.safetensors")) if False else mod.apply_model_overrides({}, dict(models, custom_lora_strength="x"))
    check(False, "bad lora strength accepted")
except RuntimeError as e:
    check("custom_lora_strength" in str(e), "bad custom LoRA strength is refused")
check(mgr.IronLeo78_MTV_ModelLoader.VALIDATE_INPUTS(**dict(models, custom_lora_name="gone.safetensors"))
      .startswith("Custom LoRA: file not found"), "manager validate: missing LoRA refused while ON")
check(mgr.IronLeo78_MTV_ModelLoader.VALIDATE_INPUTS(**dict(models, custom_lora_enabled=False, custom_lora_name="None")) is True,
      "manager validate: LoRA None is fine while OFF")
check(models["noise_seed"] == 4242 and LAST["noise_seed"] == 4242 and "seed 4242" in status_of(r), "v2.8.5: the seed comes from the Model Loader (4242)")
check(ins["noise_seed"][1]["default"] == 1978 and ins["noise_seed"][1]["control_after_generate"], "manager seed widget: default 1978, control after generate")
LAST.clear(); run(CONNECTED)
check(LAST["noise_seed"] == 1978, "no manager: seed 1978")
check(LAST["custom_lora_enabled"] is False and LAST["custom_lora_strength"] == 0.65, "no manager: custom LoRA OFF at 0.65")
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
        run(CONNECTED, models=bad); check(False, "bad models input must raise")
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

# 12 ---- segment count (v2.5)
print("12. segment count")
real_probe = mod._probe_seconds
mod._probe_seconds = lambda name, kind: {"video": 100.0, "audio": 100.0, "short": 60.0}.get(
    "short" if name == "short.wav" else kind)
base = {"Use Video": True, "Video File": "v.mp4", "Custom Audio File": "None",
        "Bypassed Audio Latent": False, "duration": 5.0}
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
mod._load_index = lambda: 7
_kw = {"Use Video": False, "Video File": "None", "Custom Audio File": "song.wav", "Bypassed Audio Latent": True,
       "megapixels": 0.2, "duration": 5.0, "Next Segment On Run": True, "Guide": False,
       "picture_1": "None", "picture_2": "None", "picture_3": "None"}
_m = REAL_LOAD_MEDIA(Cls(), _kw)
_seg = 124 / 24.0
check(SLICES and abs(SLICES[-1][0] - 7 * _seg) < 1e-6 and abs(_m["timeline_start"] - 7 * _seg) < 1e-6,
      "counter at segment 8 (index 7): audio chunk starts at 7 x %.3f s = %.3f s, timeline matches" % (_seg, 7 * _seg))
mod._load_index = lambda: 0
_m = REAL_LOAD_MEDIA(Cls(), _kw)
check(abs(SLICES[-1][0]) < 1e-9 and _m["timeline_start"] == 0.0, "counter at segment 1: the audio starts at second 0")
mod._load_index = _real_index
check(mod._segment_plan({**base, "duration": 10.0})["total"] == mod._segment_plan({**base, "duration": 10.0})["total"] and
      mod._segment_plan({**base, "duration": 10.0})["total"] == 10, "10 s segments (249 frames... 10.375 s): 10 segments")
pa = mod._segment_plan({**base, "Use Video": False, "Video File": "None", "Custom Audio File": "song.wav", "Bypassed Audio Latent": True})
check(pa["total"] == 20 and pa["limit"] == "custom audio", "custom audio, Use Video OFF: 20 segments by audio chunks")
pm = mod._segment_plan({**base, "Custom Audio File": "short.wav", "Bypassed Audio Latent": True})
check(pm["total"] == 12 and pm["limit"] == "custom audio" and len(pm["sources"]) == 2, "video + shorter audio: the shortest ends the run (12)")
ps = mod._segment_plan({**base, "Use Video": False})
check(ps["total"] == 20 and ps["limit"] == "video soundtrack", "Use Video OFF + bypass + Audio From Video: the soundtrack is counted")
check(mod._segment_plan({**base, "Use Video": False, "Video File": "None"})["total"] is None, "nothing steps through a file: total unknown (None)")
check(mod._segment_plan({**base, "Use Video": "false", "Bypassed Audio Latent": "true", "Custom Audio File": "song.wav"})["total"] == 20, "query-string booleans work")
mod._load_index = lambda: 7
info = mod._segment_info({**{k: str(v) for k, v in base.items()}, "Next Segment On Run": "true"})
check(info["index"] == 7 and info["total"] == 20 and info["stepping"] and not info["finished"], "segment info: counter 7 of 20")
mod._load_index = lambda: 20
check(mod._segment_info(base)["finished"], "segment info: counter 20 of 20 = finished")

# 13 ---- quiet end (v2.5)
print("13. quiet end")
mod._COND_CACHE.clear(); COND_CALLS.clear()
mod._segment_plan = lambda p: {"total": 20}
r = run(CONNECTED)
check(status_of(r).startswith("FINISHED") and "all 20 segments are done" in status_of(r), "counter at the end: quiet FINISHED report, no error")
check(SAVES == [] and COND_CALLS == [] and INDEX == [] and r["result"] == () and "images" not in r["ui"], "nothing generated, counter did not move")
mod._load_index = lambda: 3
r = run(CONNECTED, **{"Next Segment On Run": False})
check(not status_of(r).startswith("FINISHED"), "Next Segment On Run OFF never stops")
mod._segment_plan = lambda p: {"total": 20}
patch_media(mod.IronLeo78_MTV, lambda: {**make_media(), "index": mod._load_index()})   # like the real loader
r = run(CONNECTED)
check("segment 4 of 20 (seg003)" in status_of(r) and "progress: 4 of 20" in status_of(r) and "16 left" in status_of(r), "progress line: segment 4 of 20, 16 left")
mod._load_index = lambda: 19
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
mod._load_index = lambda: 0
r = run(CONNECTED, **{"prompt": LONG})
side = os.path.join(TMP, "Song", "Song_seg000_A_00001_.json")
check(os.path.exists(side), "sidecar written next to the clip")
d = _json.load(open(side, encoding="utf-8"))
check(d["prompt"] == LONG and d["tag"] == "Song_seg000_A" and d["segment_number"] == 1 and d["version"] == mod.VERSION and "scene" not in d, "sidecar holds the FULL prompt + segment info (no scene field any more)")
check(not [f for f in os.listdir(os.path.join(TMP, "Song")) if "upscaled" in f] and not os.path.exists(os.path.join(TMP, "Song", "Song_seg000_B_00001_.json")),
      "no upscaled clip / sidecar, and there is no B sidecar")
check(d["kind"] == "clip" and "upscaled_file" not in d and "latent_upscale" not in d and "upscale_quality" not in d and d["save_latent"] is False,
      "the sidecar has no upscale fields, and records save_latent = false")
check(len(ROWS[0]["prompt"]) == mod.MANIFEST_PROMPT_CHARS and ROWS[0]["prompt"].endswith("\u2026"), "the CSV prompt stays short, marked with an ellipsis")
check(ROWS[0]["prompt_json"] == "Song/Song_seg000_A_00001_.json", "manifest row points at the sidecar")
check("manifest:" in status_of(r) and "full prompt: Song/Song_seg000_A_00001_.json" in status_of(r), "status lists the sidecar of the clip")
check(mod.VERSION == "0.01", "VERSION is 0.01")

# 15 ---- manifest upgrade (v2.5)
print("15. manifest upgrade")
os.makedirs(os.path.join(TMP, "Old"), exist_ok=True)
oldp = os.path.join(TMP, "Old", "Old_manifest.csv")
old_fields = [f for f in mod.MANIFEST_FIELDS if f != "prompt_json"]
with open(oldp, "w", newline="", encoding="utf-8-sig") as f:
    w = _csv.DictWriter(f, fieldnames=old_fields); w.writeheader(); w.writerow({"song": "Old", "segment": 0, "scene": "A", "prompt": "old prompt"})
row = {k: "x" for k in mod.MANIFEST_FIELDS}; row.update(song="Old", segment=1, prompt_json="Old/new.json")
REAL_APPEND("Old", [row])
rows_back = list(_csv.DictReader(open(oldp, newline="", encoding="utf-8-sig")))
check(list(rows_back[0].keys())[-1] == "prompt_json" and len(rows_back) == 2, "old manifest got the prompt_json column, rows kept")
check(rows_back[0]["prompt"] == "old prompt" and rows_back[0]["prompt_json"] == "" and rows_back[1]["prompt_json"] == "Old/new.json", "old row untouched, new row filled")
# a manifest written by 0.5 (with the upscale columns) is still appended to, its columns are kept
old05 = os.path.join(TMP, "Old05"); os.makedirs(old05, exist_ok=True)
f05 = list(mod.MANIFEST_FIELDS) + ["upscale_mp", "upscaled_file"]
with open(os.path.join(old05, "Old05_manifest.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = _csv.DictWriter(f, fieldnames=f05); w.writeheader(); w.writerow({"song": "Old05", "segment": 0, "scene": "A", "upscale_mp": "0.4", "upscaled_file": "Old05/up.mp4"})
REAL_APPEND("Old05", [{**row, "song": "Old05", "segment": 1, "file": "Old05/new.mp4"}])
rows05 = list(_csv.DictReader(open(os.path.join(old05, "Old05_manifest.csv"), newline="", encoding="utf-8-sig")))
check(len(rows05) == 2 and rows05[0]["upscaled_file"] == "Old05/up.mp4" and rows05[1]["file"] == "Old05/new.mp4" and rows05[1]["upscaled_file"] == "",
      "a 0.5 manifest (with upscale columns) keeps its columns and old rows, the new row has them empty")
REAL_APPEND("Fresh", [row])
check(open(os.path.join(TMP, "Fresh", "Fresh_manifest.csv"), encoding="utf-8-sig").readline().strip().split(",") == mod.MANIFEST_FIELDS, "a new manifest starts with the full header")

# 16 ---- reset (v2.5)
print("16. reset")
mod.STATE_FILE = os.path.join(TMP, "state.json")
open(mod.STATE_FILE, "w").write(_json.dumps({"index": 5, "guide_frame_for": 4}))
mod._load_index = REAL_LOAD_INDEX
check(mod._load_index() == 5, "state says segment 5")
mod._reset_state()
check(mod._load_index() == 0 and _json.load(open(mod.STATE_FILE)) == {"index": 0}, "reset: counter 0, guide frame forgotten")

# 17 ---- jump to segment (v2.6)
print("17. jump to segment")
open(mod.STATE_FILE, "w").write(_json.dumps({"index": 5, "guide_frame_for": 4}))
out = mod._handle_jump({"segment": 3, "total": 37})
st = _json.load(open(mod.STATE_FILE))
check(out == {"ok": True, "index": 2, "segment": 3, "furthest": 5} and st["index"] == 2, "jump to segment 3: counter 2, furthest 5 remembered")
check(st["guide_frame_for"] == 4 and mod._load_index() == 2, "the saved guide frame is kept (it is checked against the counter when used)")
out = mod._handle_jump({"latest": True})
check(out["ok"] and out["segment"] == 6 and _json.load(open(mod.STATE_FILE))["index"] == 5, "Latest: back to segment 6 (the furthest counter)")
for bad, word in (({"segment": 0}, "start at 1"), ({"segment": "abc"}, "whole number"), ({}, "whole number"),
                  ({"segment": 40, "total": 37}, "only 37")):
    before = open(mod.STATE_FILE).read()
    o = mod._handle_jump(bad)
    check(o["ok"] is False and word in o["error"] and open(mod.STATE_FILE).read() == before, "bad jump %r is refused, state untouched" % (bad,))
check(mod._handle_jump({"segment": 37, "total": 37})["ok"], "the last segment itself is allowed")
mod._write_state({"index": 2})
REAL_SAVE_INDEX(7)
check(_json.load(open(mod.STATE_FILE)) == {"index": 7, "furthest": 7}, "a normal run saves the counter and the furthest point")
REAL_SAVE_INDEX(3)
check(mod._load_furthest() == 7 and _json.load(open(mod.STATE_FILE))["index"] == 3, "furthest never goes down")
mod._segment_plan = lambda p: {"total": 20}
check(mod._segment_info({})["furthest"] == 7 and mod._segment_info({})["index"] == 3, "segment info carries the furthest point for the panel")
mod._reset_state()
check(_json.load(open(mod.STATE_FILE)) == {"index": 0}, "reset forgets the furthest point too")

# 18 ---- guide frame read back from a saved clip (v2.6)
print("18. guide read back from a clip")
import numpy as _np
from PIL import Image as _Image
SONG_DIR = os.path.join(TMP, "Song"); os.makedirs(SONG_DIR, exist_ok=True)
for n in ("x_1.mp4", "x_2.mp4", "x_up.mp4", "y.mp4"):
    open(os.path.join(SONG_DIR, n), "wb").write(b"v")
mpath = os.path.join(SONG_DIR, "Song_manifest.csv")
with open(mpath, "w", newline="", encoding="utf-8-sig") as f:
    w = _csv.DictWriter(f, fieldnames=mod.MANIFEST_FIELDS + ["upscaled_file"]); w.writeheader()      # a manifest of 0.5 or older
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

mod.LAST_FRAME_FILE = os.path.join(TMP, "lf.png")
_Image.fromarray(_np.zeros((4, 4, 3), _np.uint8)).save(mod.LAST_FRAME_FILE)
REAL_CLIP_READER = mod._clip_last_frame_array
READS = []
mod._clip_last_frame_array = lambda path: READS.append(os.path.basename(path)) or _np.zeros((4, 4, 3), _np.uint8)
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
mod._clip_last_frame_array = lambda path: (_ for _ in ()).throw(RuntimeError("cannot decode"))
img, why = mod._load_last_frame(4, "Song")
check(img is None, "an unreadable clip never breaks the Run (no guide)")
mod._clip_last_frame_array = lambda path: READS.append(os.path.basename(path)) or _np.zeros((4, 4, 3), _np.uint8)

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
            REAL_CLIP_READER(os.path.join(TMP, "not_a_video.mp4")); check(False, "missing clip accepted")
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

# 19 ---- Audio Stem (Song / Vocals / Guitars / Drums / Bass): separated once per song, kept on disk
print("19. audio stems")
import numpy as _np19, contextlib as _cl19
keys = list(Cls.INPUT_TYPES()["required"])
check(keys[keys.index("Custom Audio File") + 1] == "Audio Stem", "the Audio Stem dropdown sits right under Custom Audio File: %s" % keys[keys.index("Custom Audio File"):][:3])
spec = Cls.INPUT_TYPES()["required"]["Audio Stem"]
check(spec[0] == ["Song", "Vocals", "Guitars", "Drums", "Bass"] and spec[1]["default"] == "Song", "options Song, Vocals, Guitars, Drums, Bass; default Song")
check(mod._stem_choice({}) == "Song" and mod._stem_choice({"Audio Stem": "Banjo"}) == "Song", "an old workflow (no widget) or an unknown value = Song")
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
mod._STEMS_READY.clear(); mod._AUDIO_CACHE.clear()

check(Cls._prepare_stems({"Audio Stem": "Song", "Custom Audio File": "song.wav"}) == "" and SEP["n"] == 0, "Song: no separation, nothing written")
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
mod._load_index = lambda: 0
_kw19 = {"Use Video": False, "Video File": "None", "Custom Audio File": "song.wav", "Bypassed Audio Latent": True,
         "megapixels": 0.2, "duration": 5.0, "Next Segment On Run": True, "Guide": False,
         "picture_1": "None", "picture_2": "None", "picture_3": "None"}
ids = {}
for stem in ("Song", "Vocals", "Guitars", "Drums", "Bass"):
    DECODED.clear(); mod._AUDIO_CACHE.clear()
    m = REAL_LOAD_MEDIA(Cls(), {**_kw19, "Audio Stem": stem})
    ids[stem] = m["cond_id"]["audio2"]
    check(m["audio_stem"] == stem, "%s: media records the stem" % stem)
    if stem != "Song":
        check(DECODED == ["song_%s.wav" % stem], "%s: the stem file is what gets decoded (%s)" % (stem, DECODED))
check(len(set(ids.values())) == 5, "conditioning / audio-latent cache ids differ for every stem")
check(ids["Song"] == ("a2c", mod._file_id("song.wav"), 0.0, round(124 / 24.0, 6)), "Song keeps the exact same cache id as before the feature")
_n19 = Cls(); _n19._pending_index = None      # run() sets this before _load_media
m = REAL_LOAD_MEDIA(_n19, {**_kw19, "Audio Stem": "Vocals", "Custom Audio File": "None"})
check(m["audio_stem"] == "" and m["audio2"] is None, "a stem without a Custom Audio File: silence, no stem recorded")
DECODED.clear()
mod._load_audio_for_stem("song.wav", "Vocals"); mod._load_audio_for_stem("song.wav", "Vocals")
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
LATENTS.clear(); CONDS.clear()
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

LATENTS.clear(); CONDS.clear()
run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "LatSong.wav"})
check(P(LATENTS[0][0]).endswith("_00002_video.latent") and P(CONDS[0][0]).endswith("_00002.conditioning"),
      "a redo: everything gets the next number, nothing is overwritten, and the numbers still match the clip")

# with the guide: still only the plain conditioning (the guide belongs to the first-pass size)
patch_media(mod.IronLeo78_MTV, lambda: {**make_media(), "index": 4})
_real_load_last = mod._load_last_frame
mod._load_last_frame = lambda index, song=None: ("FRAME", "")
LATENTS.clear(); CONDS.clear()
r = run(CONNECTED, **{"Save Latent": True, "Guide": True, "Custom Audio File": "GuideSong.wav"})
mod._load_last_frame = _real_load_last
check("guide: ON | last frame" in status_of(r), "(the guide was applied in this run)")
check(len(CONDS) == 1 and CONDS[0][1] == [["emb", {"p": "P1"}]], "Guide used: still ONE .conditioning, the plain one (not the guided one)")
patch_media(mod.IronLeo78_MTV)

LATENTS.clear(); CONDS.clear()
r = run(CONNECTED, **{"Save Latent": False, "Custom Audio File": "LatSong.wav"})
check(LATENTS == [] and CONDS == [] and SAVES and "latent saved" not in status_of(r), "Save Latent OFF: no latent or conditioning files, only the clip")
side_off = _j20.load(open(os.path.join(TMP, "LatSong", "LatSong_seg000_A_00003_.json"), encoding="utf-8"))
check(side_off["save_latent"] is False and side_off["latent"] is None and side_off["latent_details"] is None and ROWS[-1]["latent_file"] == "" and ROWS[-1]["conditioning_file"] == "",
      "...and the sidecar / manifest list no latent files")
LATENTS.clear(); CONDS.clear()
node_nokey = mod.IronLeo78_MTV()
_k = kw(**{"Custom Audio File": "LatSong.wav"}); _k.pop("Save Latent")
EVENTS.clear(); node_nokey.run(unique_id="7", workflow_prompt=None, extra_pnginfo=None, **_k)
check(LATENTS == [] and CONDS == [], "a node without the Save Latent value (old workflow): nothing is saved")

# the number of the mp4 is not shifted by the saved files (SaveVideo counts every file that starts with the prefix)
SAVE_N.clear(); LATENTS.clear(); CONDS.clear()
run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "OrderSong.wav"})
names = [e[0] for e in EVENTS]
check(names.index("save") < names.index("separate"), "the clip is saved BEFORE the latent files are written, so their numbers cannot shift the clip's")

# a decode error still keeps the sampled latent and the conditioning
real_core = mod._core
def _core_decode_boom(name, provided, **k):
    if name == "VAEDecode": raise RuntimeError("decode exploded")
    return real_core(name, provided, **k)
mod._core = _core_decode_boom
LATENTS.clear(); CONDS.clear()
try:
    run(CONNECTED, **{"Save Latent": True, "Custom Audio File": "BoomSong.wav"}); failed = False
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
check(t21["Save Latent"][0] == "BOOLEAN" and t21["Save Latent"][1]["default"] is False
      and t21["Save Latent"][1]["label_on"] == "ON" and t21["Save Latent"][1]["label_off"] == "OFF", "Save Latent is an OFF / ON toggle, default OFF")
tip = t21["Save Latent"][1]["tooltip"]
check(".latent" in tip and ".conditioning" in tip, "its tooltip names the files it writes")
# ON: the files exist and the clip number matches; OFF: nothing; the toggle is the ONLY thing that decides
for flag in (True, False, True):
    LATENTS.clear(); CONDS.clear(); SAVE_N.clear()
    r = run(CONNECTED, **{"Save Latent": flag, "Custom Audio File": "ToggleSong.wav"})
    check((len(LATENTS), len(CONDS)) == ((2, 1) if flag else (0, 0)), "Save Latent %s: %s" % ("ON" if flag else "OFF", "2 latents + 1 conditioning" if flag else "no files"))
# the toggle works with the guide and with other widgets set any way (nothing else switches saving on or off)
LATENTS.clear(); CONDS.clear()
run(CONNECTED, **{"Save Latent": True, "Guide": True, "Turbo": False, "Next Segment On Run": False, "Custom Audio File": "ToggleSong.wav"})
check(len(LATENTS) == 2 and len(CONDS) == 1, "Save Latent ON also works with Guide ON / Turbo OFF / Next Segment OFF")
check(mod.IronLeo78_MTV.VALIDATE_INPUTS(**{**kw(), "Save Latent": True}) is True, "validate accepts Save Latent ON")

print("\nALL %d CHECKS PASSED" % ok)
