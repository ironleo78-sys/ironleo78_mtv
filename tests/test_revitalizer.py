# Test of revitalizer.py with fake files and fake ComfyUI nodes: needs no torch / ComfyUI / GPU.
#   python tests/test_revitalizer.py
import importlib.util, json, os, sys, tempfile, time, types

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.abspath(os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp()
OUT = os.path.join(TMP, "output")
os.makedirs(OUT)
IN = os.path.join(TMP, "input")
os.makedirs(IN)

LORAS = []        # the installed LoRA files (v0.0.9c tests fill it)
fp = types.ModuleType("folder_paths")
fp.get_output_directory = lambda: OUT
fp.get_input_directory = lambda: IN
fp.get_filename_list = lambda folder: {"diffusion_models": ["minimax_h3_ref2va_pruned_int8_convrot.safetensors"],
                                       "vae": ["minimax_h3_video_vae_int8_convrot.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
                                       "loras": LORAS, "latent_upscale_models": ["h3_upscaler_lms_v0.1.safetensors"]}.get(folder, [])
MODELS = os.path.join(TMP, "models")      # v0.1.5: where the (fake) model files live, for the shared model cache's file stamps
os.makedirs(MODELS)
fp.get_full_path = lambda folder, name: os.path.join(MODELS, name)
fp.get_full_path_or_raise = fp.get_full_path
sys.modules["folder_paths"] = fp

# the pack's __init__ also imports the MTV node (needs torch / ComfyUI), so only an empty package shell is made here
pkg = types.ModuleType("rev_pkg")
pkg.__path__ = [PKG_DIR]
sys.modules["rev_pkg"] = pkg
# v0.0.9c: the saved set ("Set New Defaults") is read from mtv.py; a stand-in module holds it here (empty = nothing saved)
SAVED = {"values": {}, "control": None}
mtv_stub = types.ModuleType("rev_pkg.mtv")
mtv_stub._read_user_defaults = lambda: dict(SAVED["values"])
mtv_stub._read_user_seed_control = lambda: SAVED["control"]
sys.modules["rev_pkg.mtv"] = mtv_stub
rv = importlib.import_module("rev_pkg.revitalizer")
pkg.NODE_CLASS_MAPPINGS = rv.NODE_CLASS_MAPPINGS

ok = 0
def check(cond, msg):
    global ok
    assert cond, "FAIL: " + msg
    ok += 1
    print("  ok -", msg)

def touch(rel, age=0, data=b"x"):
    p = os.path.join(OUT, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data)
    t = time.time() - age
    os.utime(p, (t, t))

N = rv.IronLeo78_2in1_Revitalizer
print("1. node definition")
check(N.RETURN_TYPES == ("VIDEO", "IMAGE", "AUDIO", "LATENT", "STRING") and N.OUTPUT_NODE, "outputs: video, images, audio, latent, status; output node")
check(set(pkg.NODE_CLASS_MAPPINGS) == {"IronLeo78_2in1_Revitalizer"}, "node id IronLeo78_2in1_Revitalizer")
check(N.INPUT_TYPES()["required"]["latent"][0] == [rv.NONE_FOUND], "empty output: one placeholder entry")
check("no latent selected" in N.VALIDATE_INPUTS(latent=rv.NONE_FOUND), "placeholder refused with a clear message")
req = N.INPUT_TYPES()["required"]
check(req["unet_name"][1]["default"] == rv.DEF_UNET and rv.SIGMAS == [0.9231, 0.878, 0.8, 0.6316, 0.3158, 0.0], "workflow defaults / fixed sigmas")
check(req["lora_on"][1]["default"] is True and req["upscale_on"][1]["default"] is True, "v0.1.11: LoRA ON, upscale ON")
check(req["temporal_chunking"][1]["default"] is False and req["force_unload"][1]["default"] is False and rv.DEF_UPSCALER == "h3_upscaler_sharpness_2000steps_v0.1_fp32.safetensors",
      "v0.1.11: temporal chunking OFF, force unload OFF, default upscaler h3_upscaler_sharpness_2000steps_v0.1_fp32")
check(rv.DEF_SAMPLER == "res_multistep" and req["sampler_name"][1]["default"] in ("res_multistep", "euler"), "v0.1.11: sampler res_multistep when ComfyUI lists it (euler otherwise)")
check(not {"fps", "save_video", "save_format", "save_codec", "crf", "upscale_mode", "scale", "target_width", "target_height",
           "tiled_decode", "tile_size", "tile_overlap", "temporal_size", "temporal_overlap",
           "bit_depth", "color_space", "sigmas_from", "align", "weight_dtype", "filename_prefix"} & set(req), "all the hardcoded settings are not shown, and no filename_prefix (v0.0.9: the node does not save)")
check("sigmas" in req and req["sigmas"][0] == "STRING" and req["sigmas"][1]["default"] == rv.DEF_SIGMAS and list(req)[-1] == "sigmas", "v0.0.9: sigmas is a visible text widget, the LAST one (where filename_prefix was)")
check(not N.INPUT_TYPES().get("hidden"), "v0.0.9: no hidden prompt / extra_pnginfo inputs (nothing is saved)")
check(rv.parse_sigmas(rv.DEF_SIGMAS) == rv.SIGMAS, "the default text parses to the 5-step refine")
check(rv.BIT_DEPTH == 8 and rv.COLOR_SPACE == "sRGB" and rv.ALIGN == 32 and rv.WEIGHT_DTYPE == "default", "bit depth 8, sRGB, align 32, weight dtype default")
check(req["megapixels"][1] == {"default": 0.4, "min": 0.1, "max": 2.0, "step": 0.1, "tooltip": req["megapixels"][1]["tooltip"]}, "v0.1.11: megapixels default 0.4, max 2.0, steps of 0.1")
check("status_box" not in open(os.path.join(PKG_DIR, "web", "ironleo78_2in1_revitalizer.js")).read(), "no status box in the frontend script")
check(rv.FPS == 24.0 and "megapixels" in req and "filename_prefix" not in req, "fps frozen to 24, only the megapixels option")
check(not hasattr(rv, "_save_video") and not hasattr(rv, "DEF_PREFIX"), "the save code is gone")

print("2. scanning, pairing, validation")
for n, age in (("S/S_seg000_A_00001", 300), ("S/S_seg001_A_00001", 100), ("S/S_seg002_A_00001", 10)):
    touch(n + "_video.latent", age)
    touch(n + "_audio.latent", age)
    touch(n + ".conditioning", age)
touch("S/stems/S_Vocals_video.latent")
touch("deep/a/b/c/x_video.latent")
lat = rv.scan(OUT, rv.LATENT_SUFFIX)
check(lat[0] == "S/S_seg002_A_00001_video.latent" and len(lat) == 3, "newest first, stems / too-deep folders skipped")
V = N.VALIDATE_INPUTS
check(V(latent=lat[1]) is True, "a complete clip is valid")
os.remove(os.path.join(OUT, "S", "S_seg001_A_00001_audio.latent"))
check("audio latent is missing" in V(latent=lat[1]), "missing audio latent is reported (AV is always needed)")
touch("S/S_seg001_A_00001_audio.latent", 100)
os.remove(os.path.join(OUT, "S", "S_seg001_A_00001.conditioning"))
check("conditioning not found" in V(latent=lat[1]), "missing conditioning is reported")
check(V(latent=lat[0], conditioning="S/S_seg000_A_00001.conditioning") is True, "another clip's conditioning can be chosen")
check("outside" in V(latent="../secret_video.latent"), "paths leaving the output folder are refused")
check("not a" in V(latent="S/foo.latent"), "a file that is not <clip>_video.latent is refused")

print("3. IS_CHANGED follows the files")
a = N.IS_CHANGED(latent=lat[0], seed=1)
open(os.path.join(OUT, "S", "S_seg002_A_00001.conditioning"), "wb").write(b"changed!")
check(a != N.IS_CHANGED(latent=lat[0], seed=1), "overwriting a file triggers a re-run")

print("4. uploads")
up = os.path.join(IN, "ironleo78_revitalizer")
os.makedirs(up)
for n in ("U_seg009_A_00001_video.latent", "U_seg009_A_00001_audio.latent", "U_seg009_A_00001.conditioning"):
    open(os.path.join(up, n), "wb").write(b"x")
U = rv.UPLOAD_TAG + "U_seg009_A_00001_video.latent"
check(U in N.INPUT_TYPES()["required"]["latent"][0] and V(latent=U) is True, "an uploaded clip is listed and valid")
check(rv.locate(U) == os.path.join(up, "U_seg009_A_00001_video.latent"), "the tag maps to input/ironleo78_revitalizer/")
check(rv.clean_upload_name("C:\\x\\a_video.latent") == "a_video.latent" and rv.clean_upload_name("a.conditioning") == "a.conditioning", ".latent / .conditioning names reduced to the file name")
check(all(rv.clean_upload_name(n) is None for n in ("evil.py", "../x.txt", ".latent", "", "a.json")), "anything else is refused")

print("5. the whole chain with fake ComfyUI nodes")
calls = []
class Fake:
    FUNCTION = "run"
    def __init__(s, name, nout=1): s.n = name
def make(name, fn):
    c = type(name, (), {"FUNCTION": "run", "run": lambda self, **kw: (calls.append((name, kw)), fn(kw))[1]})
    return c
nodes_mod = types.ModuleType("nodes")
nodes_mod.NODE_CLASS_MAPPINGS = {
    "SolidMask": make("SolidMask", lambda k: ("mask",)),
    "SetLatentNoiseMask": make("SetLatentNoiseMask", lambda k: ({"samples": k["samples"]["samples"], "noise_mask": k["mask"]},)),
    "LTXVConcatAVLatent": make("LTXVConcatAVLatent", lambda k: ({"samples": "AV(%s,%s)" % (k["video_latent"]["samples"], k["audio_latent"]["samples"])},)),
    "LTXVSeparateAVLatent": make("LTXVSeparateAVLatent", lambda k: ({"samples": "V"}, {"samples": "A"})),
    "MinimaxH3LatentUpscaler3D": make("Up", lambda k: ({"samples": "V2x"},)),
    "UNETLoader": make("UNETLoader", lambda k: ("model",)),
    "LoraLoaderModelOnly": make("Lora", lambda k: ("model+lora",)),
    "ModelAttentionBackend": make("Attn", lambda k: ("model+attn",)),
    "BasicGuider": make("BasicGuider", lambda k: ("guider",)),
    "RandomNoise": make("RandomNoise", lambda k: ("noise",)),
    "KSamplerSelect": make("KSamplerSelect", lambda k: ("sampler",)),
    "SamplerCustomAdvanced": make("Sampler", lambda k: ({"samples": "REFINED"}, {"samples": "den"})),
    "VAELoader": make("VAELoader", lambda k: ("vae:" + k["vae_name"],)),
    "VAEDecode": make("VAEDecode", lambda k: (FakeImages(),)),
    "VAEDecodeTiled": make("VAEDecodeTiled", lambda k: (FakeImages(),)),
    "VAEDecodeAudio": make("VAEDecodeAudio", lambda k: ("audio",)),
    "CreateVideo": make("CreateVideo", lambda k: ("VIDEO",)),
}
class FakeImages:
    shape = (121, 1088, 1920, 3)
sys.modules["nodes"] = nodes_mod
# v0.1.5: the base diffusion model comes from the pack's shared model cache (not ComfyUI's UNETLoader node any more); its
# file loader is replaced here and still recorded as "UNETLoader", so "the model file was read" stays countable
class FakeBase:
    def clone(self):
        return "model"
mc = importlib.import_module("rev_pkg.model_cache")
mc._load = lambda path, dtype: (calls.append(("UNETLoader", {"unet_name": os.path.basename(path), "weight_dtype": dtype})), FakeBase())[1]
class FakeT:
    def __init__(s, v): s.v = v
    def __len__(s): return len(s.v)
torch_mod = types.ModuleType("torch")
torch_mod.FloatTensor = FakeT
sys.modules["torch"] = torch_mod
cond_mod = importlib.import_module("rev_pkg.conditioning_io")
cond_mod.load_conditioning = lambda p: [["cond", {}]]
node = N()
node._read_latent = staticmethod(lambda p: {"samples": os.path.basename(p)})
node._read_size = staticmethod(lambda p: (640, 352))
args = dict(latent=lat[0], conditioning=rv.MATCH_LATENT, freeze_audio=True, unet_name=rv.DEF_UNET,
            vae_video=rv.DEF_VAE_VIDEO, vae_audio=rv.DEF_VAE_AUDIO, lora_on=False, lora_name=rv.LORA_NONE, lora_strength=1.0,
            attention_backend=rv.ATTENTION[0], upscale_on=True, upscale_model=rv.DEF_UPSCALER,
            megapixels=2.0, temporal_chunking=True, force_unload=True,
            upscale_device="cuda", upscale_precision="fp16", seed=639560415612468, sampler_name="euler",
            sigmas=rv.DEF_SIGMAS)
import contextlib, io
def run(**kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = node.revitalize(**kw)
    return r, buf.getvalue()
res, console = run(**args)
names = [c[0] for c in calls]
order = ["SolidMask", "SetLatentNoiseMask", "LTXVConcatAVLatent", "LTXVSeparateAVLatent", "Up", "LTXVConcatAVLatent", "UNETLoader",
         "Attn", "BasicGuider", "RandomNoise", "KSamplerSelect", "Sampler", "VAELoader", "VAEDecode", "VAELoader", "VAEDecodeAudio", "CreateVideo"]
check(names == order, "same order as the workflow: %s" % names)
up_kw = [c[1] for c in calls if c[0] == "Up"][0]
check(up_kw["mode"] == {"mode": "megapixels", "megapixels": 2.0} and up_kw["align"] == 32 and up_kw["precision"] == "fp16", "upscaler gets the workflow settings (align 32 fixed)")
check([c[1] for c in calls if c[0] == "UNETLoader"][0]["weight_dtype"] == "default", "weight dtype fixed to default")
sk = [c[1] for c in calls if c[0] == "Sampler"][0]
check(sk["sigmas"].v == [0.9231, 0.878, 0.8, 0.6316, 0.3158, 0.0] and sk["latent_image"]["samples"] == "AV(V2x,A)", "sampler: fixed sigmas, upscaled video + untouched audio")
check([c[1] for c in calls if c[0] == "RandomNoise"][0]["noise_seed"] == 639560415612468, "seed passed")
check(res["result"][3]["samples"] == "REFINED" and res["result"][0] == "VIDEO" and res["result"][2] == "audio", "outputs: video, audio, refined latent")
check("ui" not in res and "SaveVideo" not in names, "v0.0.9: nothing is saved and there is no preview: the video leaves on the output")
cv = [c[1] for c in calls if c[0] == "CreateVideo"][0]
check(cv["fps"] == 24.0 and cv["bit_depth"] == 8 and cv["color_space"] == "sRGB", "CreateVideo gets 24 fps, 8 bit, sRGB")
st = res["result"][4]
check("1920x1088, 121 frames" in st and "seed 639560415612468" in st and "5 steps" in st and "LoRA OFF" in st and "DONE" in st, "status output: %s" % st.replace("\n", " | "))
check("[8/8] Building video" in console and "Saving" not in console and "DONE" in console, "the steps are printed in the console (8 stages, no saving)")
check("sigmas: 0.9231, 0.878, 0.8, 0.6316, 0.3158, 0" in st, "the sigmas used are listed in the status")
check(st.count("IronLeo78 2in1 Revitalizer") == 1 and st.startswith("IronLeo78 2in1 Revitalizer"), "v0.0.9w: the node's name heads the status once (it was printed twice)")
calls.clear()
a2 = dict(args, upscale_on=False, lora_on=True, lora_name="turbo.safetensors", lora_strength=0.8, attention_backend=rv.ATTENTION[2])
res, _ = run(**a2)
names = [c[0] for c in calls]
check("Up" not in names and "LTXVSeparateAVLatent" not in names and "Lora" in names and "VAEDecode" in names and "Attn" not in names, "upscale OFF, LoRA ON, normal decode, attention untouched")
check("VAEDecodeTiled" not in names, "the VAE is always decoded normally")
check("saved:" not in res["result"][4] and "ui" not in res, "still nothing saved with the other settings")
try:
    run(**dict(args, lora_on=True, lora_name=rv.LORA_NONE))
    good = False
except RuntimeError as e: good = "LoRA is ON" in str(e)
check(good, "LoRA ON without a file: clear error")

print("6. console steps and errors")
calls.clear()
nodes_mod.NODE_CLASS_MAPPINGS["SamplerCustomAdvanced"] = make("Sampler", lambda k: (_ for _ in ()).throw(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")))
try:
    run(**args)
    good = False
except RuntimeError: good = True
check(good, "the error is still raised (ComfyUI shows it as usual)")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try: node.revitalize(**args)
    except RuntimeError: pass
t = buf.getvalue()
check("ERROR in [5/8] Sampling" in t and "CUDA out of memory" in t and "Tip: Out of VRAM" in t, "console: failed step, message and a tip")
check(rv.hint_for(RuntimeError("node 'X' not found in this ComfyUI")).startswith("A needed node"), "missing node tip")

print("7. v0.0.9: editable sigmas")
nodes_mod.NODE_CLASS_MAPPINGS["SamplerCustomAdvanced"] = make("Sampler", lambda k: ({"samples": "REFINED"}, {"samples": "den"}))
calls.clear()
res, console = run(**dict(args, sigmas="1.0, 0.75 , 0.5;0.25\n0"))
sk = [c[1] for c in calls if c[0] == "Sampler"][0]
check(sk["sigmas"].v == [1.0, 0.75, 0.5, 0.25, 0.0] and "4 steps" in res["result"][4], "typed sigmas reach the sampler (commas, semicolons, new lines, spaces), steps = numbers - 1")
check(rv.parse_sigmas("[0.9, 0.5, 0]") == [0.9, 0.5, 0.0], "brackets are tolerated")
bad = {"": "empty", "0.9": "at least 2", "0.9, abc, 0": "not a number", "0.9, -0.1": "below 0", "0.5, 0.9, 0": "go down", "0.5, 0.5": "lower than the first", "nan, 0": "not", "inf, 0": "not"}
for text, word in bad.items():
    try:
        rv.parse_sigmas(text)
        good = False
    except ValueError as e:
        good = word in str(e)
    check(good, "refused with a clear message (%r)" % text)
check("go down" in V(latent=lat[0], sigmas="0.5, 0.9, 0") and V(latent=lat[0], sigmas=rv.DEF_SIGMAS) is True, "validation reports bad sigmas before the run")
calls.clear()
try:
    run(**dict(args, sigmas="0.9, x"))
    good = False
except RuntimeError as e:
    good = "not a number" in str(e)
check(good and not calls, "bad sigmas stop the run before any node is called")

print("8. v0.0.9c: LoRa_1 .. LoRa_3 and the Model Loader's saved set")
TURBO, L1, L2, L3, GONE = "turbo.safetensors", "H3_Unlocked_V2.safetensors", "second.safetensors", "third.safetensors", "gone.safetensors"
LORAS[:] = [TURBO, L1, L2, L3]
FULL = N.INPUT_TYPES()
req, opt = FULL["required"], FULL["optional"]
names9 = [f"LoRa_{n}{suffix}" for n in (1, 2, 3) for suffix in ("_enabled", "", "_strength")]
check(list(opt) == names9 and list(opt) == list(rv.SLOT_KEYS), "nine OPTIONAL widgets LoRa_1..3 (toggle, file, strength), same names as the Model Loader: %s" % list(opt))
check(list(req)[-1] == "sigmas" and not set(names9) & set(req), "required widgets unchanged: sigmas is still the last required one, the new ones come after it (no saved value moves)")
check(all(opt[f"LoRa_{n}_enabled"][0] == "BOOLEAN" and opt[f"LoRa_{n}_enabled"][1]["default"] is False for n in (1, 2, 3)), "every LoRa_n starts OFF")
check(all(opt[f"LoRa_{n}"][0][0] == "None" and opt[f"LoRa_{n}"][1]["default"] == "None" and L1 in opt[f"LoRa_{n}"][0] for n in (1, 2, 3)), "every LoRa_n file list starts with None and lists the installed LoRAs; default None")
check(all(opt[f"LoRa_{n}_strength"][1]["default"] == 1.0 and opt[f"LoRa_{n}_strength"][1]["min"] == -100.0 and opt[f"LoRa_{n}_strength"][1]["max"] == 100.0 for n in (1, 2, 3)), "strength 1.0 (v0.1.11), range -100..100 (same as the Model Loader)")
check(req["seed"][1]["default"] == 1978 and req["unet_name"][1]["default"] == rv.DEF_UNET and req["lora_strength"][1]["default"] == 1.0, "nothing saved: the node's own defaults (v0.1.11: seed 1978, the workflow's UNET, LoRA strength 1.0)")
check(rv.saved_set() == ({}, None) and rv.set_report({"seed": 1}) == "", "nothing saved: no set, no status line")

SAVED["values"] = {"unet_name": rv.DEF_UNET, "turbo_lora_name": TURBO, "video_vae_name": "minimax_h3_audio_vae_fp32.safetensors",
                   "audio_vae_name": "minimax_h3_audio_vae_fp32.safetensors", "noise_seed": 4242,
                   "LoRa_1_enabled": True, "LoRa_1": L1, "LoRa_1_strength": 0.5,
                   "LoRa_2_enabled": True, "LoRa_2": GONE, "LoRa_2_strength": 1.25,
                   "LoRa_3_enabled": False, "LoRa_3": "None", "LoRa_3_strength": 0.65,
                   "qwen_vl_name": "q.safetensors", "turbo_steps": 3, "full_steps": 40}
SAVED["control"] = "increment"
mapped, ctl = rv.saved_set()
check(mapped["lora_name"] == TURBO and mapped["vae_video"] == "minimax_h3_audio_vae_fp32.safetensors" and mapped["seed"] == 4242 and mapped["LoRa_1"] == L1 and mapped["LoRa_2_strength"] == 1.25 and ctl == "increment",
      "the saved set is translated to this node's widget names (Turbo LoRA file -> lora_name, video VAE -> vae_video, noise_seed -> seed, LoRa_n as they are)")
check(len(mapped) == 14 and not {"qwen_vl_name", "turbo_steps", "full_steps", "turbo_lora_name", "video_vae_name", "noise_seed"} & set(mapped),
      "what has no place on this node (text encoder, steps) is not sent: %d values (5 + the nine LoRa_n values)" % len(mapped))
FULL = N.INPUT_TYPES()
req, opt = FULL["required"], FULL["optional"]
check(req["lora_name"][1]["default"] == TURBO and req["vae_video"][1]["default"] == "minimax_h3_audio_vae_fp32.safetensors" and req["seed"][1]["default"] == 4242,
      "a NEW node starts from the saved set (Turbo LoRA file, VAE, seed)")
check(opt["LoRa_1_enabled"][1]["default"] is True and opt["LoRa_1"][1]["default"] == L1 and opt["LoRa_1_strength"][1]["default"] == 0.5, "LoRa_1 ON / file / strength come from the set")
check(opt["LoRa_2_enabled"][1]["default"] is False and opt["LoRa_2"][1]["default"] == "None" and opt["LoRa_2_strength"][1]["default"] == 1.25,
      "a saved LoRa that is not installed here: file None and OFF (never ON with no file), its strength kept")
check(req["lora_on"][1]["default"] is True, "the LoRA ON / OFF switch is not part of the set (the Model Loader has no such switch for the Turbo LoRA): its own default ON")

print("   validation of the new widgets")
V = N.VALIDATE_INPUTS
check(V(latent=lat[0], LoRa_1_enabled=True, LoRa_1=L1, LoRa_1_strength=0.5) is True, "LoRa_1 ON with an installed file is valid")
check("LoRa_2 is ON but no file" in V(latent=lat[0], LoRa_2_enabled=True, LoRa_2="None"), "ON with None: clear message naming the slot")
check("LoRa_3 file not found: %s" % GONE in V(latent=lat[0], LoRa_3_enabled=True, LoRa_3=GONE), "ON with a file that is not installed: clear message")
check(V(latent=lat[0], LoRa_3_enabled=False, LoRa_3=GONE) is True, "OFF with a file that is not installed does NOT block the run")
check("between -100 and 100" in V(latent=lat[0], LoRa_1_strength=101) and "must be a number" in V(latent=lat[0], LoRa_1_strength="abc"), "strength out of range / not a number refused")
check("go down" in V(latent=lat[0], sigmas="0.5, 0.9, 0", LoRa_1_enabled=False), "the other checks still work")

print("   the chain: UNET -> LoRA -> LoRa_1 -> LoRa_2 -> LoRa_3 -> attention")
calls.clear()
a3 = dict(args, lora_on=True, lora_name=TURBO, lora_strength=1.0, attention_backend=rv.ATTENTION[0],
          LoRa_1_enabled=True, LoRa_1=L1, LoRa_1_strength=0.5,
          LoRa_2_enabled=False, LoRa_2=L2, LoRa_2_strength=0.9,
          LoRa_3_enabled=True, LoRa_3=L3, LoRa_3_strength=-0.25)
res, console = run(**a3)
lc = [c[1] for c in calls if c[0] == "Lora"]
order = [c[0] for c in calls]
check([(c["lora_name"], c["strength_model"]) for c in lc] == [(TURBO, 1.0), (L1, 0.5), (L3, -0.25)], "the LoRAs are applied in this order, only the ones that are ON: %s" % [(c["lora_name"], c["strength_model"]) for c in lc])
check(("UNETLoader" not in order or order.index("UNETLoader") < order.index("Lora")) and order.index("Lora") < order.index("Attn") < order.index("BasicGuider"),
      "after the model (v0.1.5: already in memory here, shared), before the attention backend and the guider")
st = res["result"][4]
check("LoRa_1 ON: %s x0.5" % L1 in st and "LoRa_3 ON: %s x-0.25" % L3 in st and "LoRa_2 ON" not in st, "status lists the LoRa_n that were applied")
check("DIFFERS from the saved set" in st and "LoRa_2_enabled=False (saved True)" in st and "LoRa_3_enabled=True (saved False)" in st and "more" in st, "status says the run differs from the saved set and names the values: %s" % [l for l in st.split("\n") if l.startswith("models:")])
calls.clear()
same_args = dict(args, lora_on=False, lora_name=TURBO, unet_name=rv.DEF_UNET, vae_video="minimax_h3_audio_vae_fp32.safetensors", vae_audio="minimax_h3_audio_vae_fp32.safetensors", seed=4242,
                 LoRa_1_enabled=True, LoRa_1=L1, LoRa_1_strength=0.5, LoRa_2_enabled=True, LoRa_2=GONE, LoRa_2_strength=1.25,
                 LoRa_3_enabled=False, LoRa_3="None", LoRa_3_strength=0.65)
SAVED["values"]["LoRa_2_enabled"] = False       # (the run below must not need a missing file)
res, _ = run(**dict(same_args, LoRa_2_enabled=False))
check("models: same as the saved set (Set New Defaults)" in res["result"][4] and not any(c[0] == "Lora" and c[1]["lora_name"] == GONE for c in calls), "the same values as the set: status says so, an OFF slot is not loaded even when its file is missing")

print("   errors and old API prompts")
for n in (1, 2, 3):
    try:
        run(**dict(args, **{f"LoRa_{n}_enabled": True, f"LoRa_{n}": "None"}))
        good = False
    except RuntimeError as e:
        good = f"LoRa_{n} is ON but no file" in str(e)
    check(good, f"LoRa_{n} ON without a file stops the run with a clear message")
calls.clear()
old_prompt = {k: v for k, v in args.items()}          # an API prompt saved before 0.0.9c: none of the nine keys
res, _ = run(**old_prompt)
check(not any(c[0] == "Lora" for c in calls) and "LoRa_1 ON" not in res["result"][4], "an old API prompt without the LoRa_n keys runs with all three OFF")
check("LoRa_1_enabled=False (saved True)" in res["result"][4], "an old prompt counts as all OFF when it is compared with the saved set")
check(rv.lora_slot({"LoRa_1_enabled": "true"}, 1) == (True, "None", 1.0) and rv.lora_slot({}, 3) == (False, "None", 1.0), "slot values: text 'true' counts, a missing slot is OFF / None / 1.0")

print("   the route payload")
SAVED["values"], SAVED["control"] = {}, None
check(rv.saved_set() == ({}, None), "after Factory (nothing saved) the set is empty again: nothing is forced")
src = open(os.path.join(PKG_DIR, "revitalizer.py"), encoding="utf-8").read()
check("@routes.get(SET_ROUTE)" in src and rv.SET_ROUTE == "/ironleo78/revitalizer/saved_set", "the GET route the node's button calls is registered")

print("9. v0.1.4: the model and the VAEs stay loaded between runs")
for f in (rv.DEF_UNET, rv.DEF_VAE_VIDEO, rv.DEF_VAE_AUDIO, TURBO):
    open(os.path.join(MODELS, f), "wb").write(b"m")
LORAS[:] = [TURBO, L1, L2, L3]
rv.free_cache()
mc.free()
count = lambda name: sum(1 for c in calls if c[0] == name)
# (v0.1.5) "UNETLoader" = the model FILE read from disk (shared base); "Attn" = the model chain built again on the base
calls.clear()
res, console = run(**args)
check(count("UNETLoader") == 1 and count("VAELoader") == 2, "first run: the model and both VAEs are loaded")
calls.clear()
res, console = run(**dict(args, seed=7, sigmas="0.9, 0.5, 0"))
st = res["result"][4]
check(count("UNETLoader") == 0 and count("Attn") == 0 and count("VAELoader") == 0 and count("Sampler") == 1,
      "another seed + other sigmas: nothing is loaded again, the sampling still runs")
check("model: kept from the previous run" in st and "VAEs: kept from the previous run" in st and "attention: comfy kitchen attention" in st,
      "the status says the model and the VAEs were kept, and still lists the attention backend")
check("[4/8] Loading model" in st and "(kept from the previous run)" in st, "the stage line says so too")
calls.clear()
res, _ = run(**dict(args, lora_on=True, lora_name=TURBO, lora_strength=0.8))
check(count("UNETLoader") == 0 and count("Lora") == 1 and count("Attn") == 1 and count("VAELoader") == 0,
      "LoRA switched ON: the LoRA chain is built again ON the model already in memory (v0.1.5: the file is NOT read again), VAEs kept")
check("diffusion model: already in memory" in res["result"][4], "the status says the model file was not read again")
calls.clear()
run(**dict(args, lora_on=True, lora_name=TURBO, lora_strength=0.6))
check(count("UNETLoader") == 0 and count("Lora") == 1, "another LoRA strength: only the LoRA is applied again")
calls.clear()
run(**dict(args, lora_on=True, lora_name=TURBO, lora_strength=0.6, LoRa_1_enabled=True, LoRa_1=L1, LoRa_1_strength=0.5))
check(count("UNETLoader") == 0 and count("Lora") == 2, "a LoRa_n switched ON: the chain again, not the file")
calls.clear()
run(**dict(args, lora_on=True, lora_name=TURBO, lora_strength=0.6, LoRa_1_enabled=True, LoRa_1=L1, LoRa_1_strength=0.5))
check(count("UNETLoader") == 0 and count("Lora") == 0 and count("Attn") == 0, "the same chain again: kept as a whole")
calls.clear()
run(**dict(args, lora_on=True, lora_name=TURBO, lora_strength=0.6, LoRa_1_enabled=True, LoRa_1=L1, LoRa_1_strength=0.5,
           LoRa_2_enabled=False, LoRa_2=L2, LoRa_2_strength=0.9))
check(count("Lora") == 0 and count("Attn") == 0, "a LoRa_n that is OFF (whatever its file / strength) does not count: kept")
calls.clear()
run(**dict(args, attention_backend=rv.ATTENTION[1]))
check(count("UNETLoader") == 0 and count("Attn") == 1, "another attention backend: the chain again, not the file")
calls.clear()
t = time.time() + 5
os.utime(os.path.join(MODELS, rv.DEF_UNET), (t, t))
run(**dict(args, attention_backend=rv.ATTENTION[1]))
check(count("UNETLoader") == 1, "the model file replaced under the same name (new mtime): loaded again")
calls.clear()
os.utime(os.path.join(MODELS, rv.DEF_VAE_AUDIO), (t + 5, t + 5))
run(**dict(args, attention_backend=rv.ATTENTION[1]))
check(count("UNETLoader") == 0 and count("VAELoader") == 1, "the audio VAE replaced: only that VAE is loaded again")
calls.clear()
run(**dict(args, attention_backend=rv.ATTENTION[1], vae_video=rv.DEF_VAE_AUDIO))
check(count("VAELoader") == 0, "the same file for both VAEs: one copy, kept")
check(len(rv._CACHE["model"]) == 1 and len(rv._CACHE["vae"]) <= 2, "never more than one model and two VAEs are kept")
rv.free_cache()
calls.clear()
run(**args)
check(count("UNETLoader") == 0 and count("Attn") == 1 and count("VAELoader") == 2,
      "after the Revitalizer's own free_cache(): its chain and VAEs load again, the shared model file stays in memory")
rv.free_cache()
mc.free()
calls.clear()
run(**args)
check(count("UNETLoader") == 1 and count("VAELoader") == 2, "after the MTV's free route (both caches + the shared model) everything is loaded again")
print("   v0.1.5: one shared base model, and switching to another file frees the old one first")
OTHER = "other_model.safetensors"
open(os.path.join(MODELS, OTHER), "wb").write(b"m")
dropped = []
mc.on_switch(lambda: dropped.append(len(rv._CACHE["model"])))
calls.clear()
run(**dict(args, unet_name=OTHER))
check(count("UNETLoader") == 1 and mc.held() == 1, "another model file: read once, and still ONE base model in memory")
check(dropped == [0], "before the new file loaded, the Revitalizer's model built on the old one was already dropped (switch hook)")
check([c[1]["unet_name"] for c in calls if c[0] == "UNETLoader"] == [OTHER], "the new file is the one that was read")
calls.clear()
run(**args)
check(count("UNETLoader") == 1 and mc.held() == 1, "back to the first file: read again (only one base is kept), still one in memory")
mc._ON_SWITCH.pop()
try:
    run(**dict(args, lora_on=True, lora_name=rv.LORA_NONE))
    good = False
except RuntimeError as e:
    good = "LoRA is ON" in str(e)
check(good and "model" in rv._CACHE and len(rv._CACHE["model"]) == 0, "a model that fails to build is not kept (and the old one was already dropped to free the memory)")
mtv_src = open(os.path.join(PKG_DIR, "mtv.py"), encoding="utf-8").read()
check("_rev.free_cache()" in mtv_src, "the MTV's free_cached_models() also frees the Revitalizer's cache")

print("10. v0.1.7: the third-party upscaler is optional (built-in latent resize)")
resized = []
_real_resize = rv.resize_video_latent
rv.resize_video_latent = lambda latent, mp: (resized.append((latent["samples"], mp)), ({"samples": "V_builtin"}, (1472, 832)))[1]
_up_node = nodes_mod.NODE_CLASS_MAPPINGS.pop("MinimaxH3LatentUpscaler3D")
try:
    calls.clear()
    res, console = run(**dict(args, megapixels=1.2))
    names = [c[0] for c in calls]
    st = res["result"][4]
    check("Up" not in names and resized == [("V", 1.2)], "upscaler node not installed: no call to it, the built-in resize gets the video latent and the megapixels")
    sk = [c[1] for c in calls if c[0] == "Sampler"][0]
    check(sk["latent_image"]["samples"] == "AV(V_builtin,A)", "the resized video latent + the untouched audio go to the refine pass")
    check("upscale: 1.2 MP built in: latent resized to 1472x832 (the Minimax H3 Latent Upscaler node is not installed)" in st,
          "the status says the built-in resize was used, the size, and why")
    check("[3/8] Upscaling latent" in st and "built in" in st, "the stage line says so too")
    calls.clear()
    res, _ = run(**dict(args, upscale_model="(none found in models/latent_upscale_models)"))
    check("Up" not in [c[0] for c in calls] and len(resized) == 2, "no model file: no error any more, the built-in resize is used")
    calls.clear()
    res, _ = run(**dict(args, upscale_on=False))
    check(len(resized) == 2 and "upscale: OFF" in res["result"][4], "upscale OFF: no resize at all, as before")
finally:
    nodes_mod.NODE_CLASS_MAPPINGS["MinimaxH3LatentUpscaler3D"] = _up_node
    rv.resize_video_latent = _real_resize
calls.clear()
res, _ = run(**dict(args, megapixels=1.2))
check("Up" in [c[0] for c in calls] and "Minimax H3 Latent Upscaler 3D, " + rv.DEF_UPSCALER in res["result"][4],
      "node installed + a model file: the trained upscaler is used as before, and the status names it")
calls.clear()
rv.resize_video_latent = lambda latent, mp: (resized.append((latent["samples"], mp)), ({"samples": "V_builtin"}, (1472, 832)))[1]
try:
    res, _ = run(**dict(args, megapixels=1.2, upscale_model="(none found in models/latent_upscale_models)"))
finally:
    rv.resize_video_latent = _real_resize
check("Up" not in [c[0] for c in calls] and "no model file in models/latent_upscale_models" in res["result"][4] and len(resized) == 3,
      "node installed but no model file: the built-in resize, and the status says why")

print("11. v0.1.9: small fixes")
ls = N.INPUT_TYPES()["required"]["lora_strength"][1]
check((ls["min"], ls["max"], ls["default"]) == (-100.0, 100.0, 1.0), "lora_strength allows -100..100 like LoRa_1-3 (was -10..10); default 1.0 unchanged")
import asyncio


class _Part:
    def __init__(self, chunks, fail_after=None):
        self.chunks, self.fail_after, self.n = list(chunks), fail_after, 0

    async def read_chunk(self, size):
        self.n += 1
        if self.fail_after is not None and self.n > self.fail_after:
            raise ConnectionResetError("the browser tab was closed")
        return self.chunks.pop(0) if self.chunks else b""


UP11 = os.path.join(TMP, "up11")
os.makedirs(UP11)
target = os.path.join(UP11, "a_video.latent")
asyncio.run(rv.save_upload_part(_Part([b"abc", b"def"]), target))
check(open(target, "rb").read() == b"abcdef" and not os.path.exists(target + ".tmp"), "a complete upload: the file, no .tmp left")
target2 = os.path.join(UP11, "b_video.latent")
try:
    asyncio.run(rv.save_upload_part(_Part([b"abc", b"def"], fail_after=1), target2))
    good = False
except ConnectionResetError:
    good = True
check(good and not os.path.exists(target2) and not os.path.exists(target2 + ".tmp"),
      "an upload that breaks off: the error is reported, and no half-written file or .tmp stays behind")
asyncio.run(rv.save_upload_part(_Part([b"new"]), target))
check(open(target, "rb").read() == b"new", "uploading the same name again replaces the file")

print("\nALL %d CHECKS PASSED" % ok)
