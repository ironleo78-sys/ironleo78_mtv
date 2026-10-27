# Test of revitalizer.py with fake files and fake ComfyUI nodes: needs no torch / ComfyUI / GPU.
#   python tests/test_revitalizer.py
import importlib.util, json, os, sys, tempfile, time, types

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.abspath(os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(); OUT = os.path.join(TMP, "output"); os.makedirs(OUT); IN = os.path.join(TMP, "input"); os.makedirs(IN)

fp = types.ModuleType("folder_paths")
fp.get_output_directory = lambda: OUT
fp.get_input_directory = lambda: IN
fp.get_filename_list = lambda folder: {"diffusion_models": ["minimax_h3_ref2va_pruned_int8_convrot.safetensors"],
                                       "vae": ["minimax_h3_video_vae_int8_convrot.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
                                       "loras": [], "latent_upscale_models": ["h3_upscaler_lms_v0.1.safetensors"]}.get(folder, [])
sys.modules["folder_paths"] = fp

# the pack's __init__ also imports the MTV node (needs torch / ComfyUI), so only an empty package shell is made here
pkg = types.ModuleType("rev_pkg"); pkg.__path__ = [PKG_DIR]; sys.modules["rev_pkg"] = pkg
rv = importlib.import_module("rev_pkg.revitalizer")
pkg.NODE_CLASS_MAPPINGS = rv.NODE_CLASS_MAPPINGS

ok = 0
def check(cond, msg):
    global ok
    assert cond, "FAIL: " + msg
    ok += 1; print("  ok -", msg)

def touch(rel, age=0, data=b"x"):
    p = os.path.join(OUT, *rel.split("/")); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data); t = time.time() - age; os.utime(p, (t, t))

N = rv.IronLeo78_2in1_Revitalizer
print("1. node definition")
check(N.RETURN_TYPES == ("VIDEO", "IMAGE", "AUDIO", "LATENT", "STRING") and N.OUTPUT_NODE, "outputs: video, images, audio, latent, status; output node")
check(set(pkg.NODE_CLASS_MAPPINGS) == {"IronLeo78_2in1_Revitalizer"}, "node id IronLeo78_2in1_Revitalizer")
check(N.INPUT_TYPES()["required"]["latent"][0] == [rv.NONE_FOUND], "empty output: one placeholder entry")
check("no latent selected" in N.VALIDATE_INPUTS(latent=rv.NONE_FOUND), "placeholder refused with a clear message")
req = N.INPUT_TYPES()["required"]
check(req["unet_name"][1]["default"] == rv.DEF_UNET and rv.SIGMAS == [0.9231, 0.878, 0.8, 0.6316, 0.3158, 0.0], "workflow defaults / fixed sigmas")
check(req["lora_on"][1]["default"] is False and req["upscale_on"][1]["default"] is True, "LoRA OFF, upscale ON")
check(not {"fps", "save_video", "save_format", "save_codec", "crf", "upscale_mode", "scale", "target_width", "target_height",
           "tiled_decode", "tile_size", "tile_overlap", "temporal_size", "temporal_overlap",
           "bit_depth", "color_space", "sigmas", "sigmas_from", "align", "weight_dtype"} & set(req), "all the hardcoded settings are not shown")
check(rv.BIT_DEPTH == 8 and rv.COLOR_SPACE == "sRGB" and rv.ALIGN == 32 and rv.WEIGHT_DTYPE == "default", "bit depth 8, sRGB, align 32, weight dtype default")
check(req["megapixels"][1] == {"default": 2.0, "min": 0.1, "max": 2.0, "step": 0.1, "tooltip": req["megapixels"][1]["tooltip"]}, "megapixels: max 2.0, steps of 0.1")
check("status_box" not in open(os.path.join(PKG_DIR, "web", "ironleo78_2in1_revitalizer.js")).read(), "no status box in the frontend script")
check(rv.FPS == 24.0 and "megapixels" in req and "filename_prefix" in req, "fps frozen to 24, only the megapixels option, prefix kept")

print("2. scanning, pairing, validation")
for n, age in (("S/S_seg000_A_00001", 300), ("S/S_seg001_A_00001", 100), ("S/S_seg002_A_00001", 10)):
    touch(n + "_video.latent", age); touch(n + "_audio.latent", age); touch(n + ".conditioning", age)
touch("S/stems/S_Vocals_video.latent"); touch("deep/a/b/c/x_video.latent")
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
up = os.path.join(IN, "ironleo78_revitalizer"); os.makedirs(up)
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
class FakeT:
    def __init__(s, v): s.v = v
    def __len__(s): return len(s.v)
torch_mod = types.ModuleType("torch"); torch_mod.FloatTensor = FakeT; sys.modules["torch"] = torch_mod
cond_mod = importlib.import_module("rev_pkg.conditioning_io"); cond_mod.load_conditioning = lambda p: [["cond", {}]]
saved = {}
rv._save_video = lambda video, prefix, fmt, codec, crf, prompt, info: (saved.update(prefix=prefix, fmt=fmt, codec=codec, crf=crf) or ("f_00001_.mp4", "video", "/o/video/f_00001_.mp4"))
node = N()
node._read_latent = staticmethod(lambda p: {"samples": os.path.basename(p)})
node._read_size = staticmethod(lambda p: (640, 352))
args = dict(latent=lat[0], conditioning=rv.MATCH_LATENT, freeze_audio=True, unet_name=rv.DEF_UNET,
            vae_video=rv.DEF_VAE_VIDEO, vae_audio=rv.DEF_VAE_AUDIO, lora_on=False, lora_name=rv.LORA_NONE, lora_strength=1.0,
            attention_backend=rv.ATTENTION[0], upscale_on=True, upscale_model=rv.DEF_UPSCALER,
            megapixels=2.0, temporal_chunking=True, force_unload=True,
            upscale_device="cuda", upscale_precision="fp16", seed=639560415612468, sampler_name="euler",
            filename_prefix=rv.DEF_PREFIX)
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
check(res["ui"]["images"][0]["filename"] == "f_00001_.mp4" and res["ui"]["animated"] == (True,), "preview of the saved video")
check(saved == {"prefix": rv.DEF_PREFIX, "fmt": "auto", "codec": "auto", "crf": None}, "always saved, format / codec / quality auto")
cv = [c[1] for c in calls if c[0] == "CreateVideo"][0]
check(cv["fps"] == 24.0 and cv["bit_depth"] == 8 and cv["color_space"] == "sRGB", "CreateVideo gets 24 fps, 8 bit, sRGB")
st = res["result"][4]
check("1920x1088, 121 frames" in st and "seed 639560415612468" in st and "5 steps" in st and "LoRA OFF" in st and "DONE" in st, "status output: %s" % st.replace("\n", " | "))
check("[9/9] Saving video" in console and "DONE" in console, "the steps are printed in the console")
calls.clear()
a2 = dict(args, upscale_on=False, lora_on=True, lora_name="turbo.safetensors", lora_strength=0.8, attention_backend=rv.ATTENTION[2])
res, _ = run(**a2)
names = [c[0] for c in calls]
check("Up" not in names and "LTXVSeparateAVLatent" not in names and "Lora" in names and "VAEDecode" in names and "Attn" not in names, "upscale OFF, LoRA ON, normal decode, attention untouched")
check("VAEDecodeTiled" not in names, "the VAE is always decoded normally")
check(res["ui"]["images"] and "saved:" in res["result"][4], "saving cannot be turned off")
try: run(**dict(args, lora_on=True, lora_name=rv.LORA_NONE)); good = False
except RuntimeError as e: good = "LoRA is ON" in str(e)
check(good, "LoRA ON without a file: clear error")

print("6. console steps and errors")
calls.clear()
nodes_mod.NODE_CLASS_MAPPINGS["SamplerCustomAdvanced"] = make("Sampler", lambda k: (_ for _ in ()).throw(RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")))
try: run(**args); good = False
except RuntimeError: good = True
check(good, "the error is still raised (ComfyUI shows it as usual)")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    try: node.revitalize(**args)
    except RuntimeError: pass
t = buf.getvalue()
check("ERROR in [5/9] Sampling" in t and "CUDA out of memory" in t and "Tip: Out of VRAM" in t, "console: failed step, message and a tip")
check(rv.hint_for(RuntimeError("node 'X' not found in this ComfyUI")).startswith("A needed node"), "missing node tip")
print("\nALL %d CHECKS PASSED" % ok)
