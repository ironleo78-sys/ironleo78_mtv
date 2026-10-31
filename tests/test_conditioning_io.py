# Test of conditioning_io.py (saving / loading conditioning) with FAKE tensors: needs no torch / ComfyUI / GPU.
#   python tests/test_conditioning_io.py
import importlib.util, json, os, sys, types

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("cio", os.path.join(HERE, "..", "conditioning_io.py"))
cio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cio)

ok = 0
def check(cond, msg):
    global ok
    assert cond, "FAIL: " + msg
    ok += 1
    print("  ok -", msg)

class T:                                   # a fake tensor
    def __init__(self, name): self.name = name
    def numel(self): return 10
    def element_size(self): return 2
    def detach(self): return self
    def cpu(self): return self
    def contiguous(self): return self
    def clone(self): return T(self.name + "'")

def roundtrip(obj):
    tensors, lost = {}, []
    st = json.loads(json.dumps(cio.encode(obj, tensors, lambda x: isinstance(x, T), lambda t: t, lost)))   # through real JSON
    return cio.decode(st, tensors), tensors, lost, st

print("1. a MiniMax-style conditioning")
a, b, ref = T("emb"), T("ref"), T("pooled")
cond = [[a, {"reference_latents": [ref, ref], "guide": (b, 3), "frame_idx": 0, "flag": True, "name": "x\u00e9", "none": None, "f": 0.5}]]
back, tensors, lost, st = roundtrip(cond)
check(lost == [] and len(tensors) == 3, "3 distinct tensors stored for 4 uses (a repeated tensor is stored once)")
check(back[0][0] is a and back[0][1]["reference_latents"][0] is ref and back[0][1]["reference_latents"][1] is ref, "tensors come back, the shared one is shared again")
check(back[0][1]["guide"] == (b, 3) and isinstance(back[0][1]["guide"], tuple), "tuples stay tuples")
check(back[0][1]["frame_idx"] == 0 and back[0][1]["flag"] is True and back[0][1]["none"] is None and back[0][1]["f"] == 0.5 and back[0][1]["name"] == "x\u00e9",
      "ints, bools, None, floats and unicode strings survive")
check(isinstance(back, list) and isinstance(back[0], list) and isinstance(back[0][1], dict), "list of [tensor, dict] stays a list of lists")

print("2. several entries, empty cases, odd dict keys")
back, tensors, lost, _ = roundtrip([[T("a"), {}], [T("b"), {"k": [T("c")]}]])
check(len(tensors) == 3 and back[1][1]["k"][0].name == "c", "two entries")
check(roundtrip([])[0] == [] and roundtrip([[T("x"), {}]])[0][0][1] == {}, "empty conditioning / empty options")
back, _, lost, _ = roundtrip([[T("x"), {1: "int key", "s": 2}]])
check(back[0][1] == {1: "int key", "s": 2} and lost == [], "int dict keys are kept")

print("3. what cannot be stored is reported, never silent")
class Odd: pass
back, _, lost, _ = roundtrip([[T("x"), {"weird": Odd(), "ok": 1}]])
check(back[0][1] == {"weird": None, "ok": 1}, "an unsupported object loads back as None, the rest is intact")
check(len(lost) == 1 and "weird" in lost[0] and "Odd" in lost[0], "and it is reported with its path: %s" % lost)
try:
    cio.decode({"__bogus__": 1}, {})
    check(False, "unknown node accepted")
except ValueError:
    check(True, "an unknown structure node is refused")

print("4. save_conditioning / load_conditioning glue (torch, comfy, safetensors replaced by in-memory fakes)")
FILES = {}
torch = types.ModuleType("torch")
torch.is_tensor = lambda x: isinstance(x, T)
comfy = types.ModuleType("comfy")
cu = types.ModuleType("comfy.utils")
comfy.utils = cu
def save_torch_file(sd, path, metadata=None): FILES[path] = (dict(sd), dict(metadata or {}))
cu.save_torch_file = save_torch_file
st_mod = types.ModuleType("safetensors")
class _Open:
    def __init__(self, path, framework=None, device=None): self.sd, self.meta = FILES[path]
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def metadata(self): return self.meta
    def keys(self): return list(self.sd)
    def get_tensor(self, k): return self.sd[k]
st_mod.safe_open = _Open
sys.modules.update({"torch": torch, "comfy": comfy, "comfy.utils": cu, "safetensors": st_mod})

info = cio.save_conditioning("/x/clip_positive.conditioning", cond, {"part": "conditioning", "seed": 1978})
saved_tensors, saved_meta = FILES["/x/clip_positive.conditioning"]
check(info == {"tensors": 3, "bytes": 3 * 10 * 2, "unsupported": []}, "save reports tensor count and size: %s" % info)
check(all(t.name.endswith("'") for t in saved_tensors.values()), "tensors are stored as private copies (safetensors refuses shared memory)")
check(saved_meta["ironleo78_format"] == cio.FORMAT and saved_meta["part"] == "conditioning" and saved_meta["seed"] == "1978",
      "metadata: format marker + the caller's fields (as strings)")
check(all(isinstance(v, str) for v in saved_meta.values()), "every metadata value is a string (safetensors requires it)")
loaded = cio.load_conditioning("/x/clip_positive.conditioning")
check(loaded[0][1]["guide"][1] == 3 and loaded[0][1]["reference_latents"][0] is loaded[0][1]["reference_latents"][1]
      and loaded[0][0].name == "emb'", "load rebuilds the conditioning from the file")
FILES["/x/foreign.latent"] = ({"latent_tensor": T("z")}, {"format": "pt"})
try:
    cio.load_conditioning("/x/foreign.latent")
    check(False, "a foreign safetensors file was accepted")
except ValueError as e:
    check("not an IronLeo78 conditioning file" in str(e), "a file that is not ours is refused with a clear message")
check(cio.EXTENSION == ".conditioning", "extension is .conditioning")

print("\nALL %d CHECKS PASSED" % ok)
