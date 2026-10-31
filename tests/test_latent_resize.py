"""v0.1.7: the Revitalizer's built-in latent upscale (used when the third-party Minimax H3 Latent Upscaler is not installed),
with real torch. Needs torch (any ComfyUI Python has it):
    <ComfyUI python> tests/test_latent_resize.py
Skips itself when torch is missing."""
import importlib
import os
import sys
import types
from unittest.mock import MagicMock

try:
    import torch
except Exception:
    print("SKIPPED: torch is not installed in this Python (run it with ComfyUI's Python).")
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
for name in ("comfy", "comfy.sd", "comfy.utils", "comfy.model_management", "nodes", "server"):
    sys.modules[name] = MagicMock()
fp = types.ModuleType("folder_paths")
fp.get_input_directory = fp.get_output_directory = lambda: HERE
fp.get_filename_list = lambda k: []
sys.modules["folder_paths"] = fp
sys.modules["comfy_extras"] = types.ModuleType("comfy_extras")
sys.modules["comfy_extras.nodes_minimax_h3"] = types.ModuleType("comfy_extras.nodes_minimax_h3")
sys.path.insert(0, os.path.dirname(PACK))
rv = importlib.import_module(os.path.basename(PACK) + ".revitalizer")

ok = 0


def check(cond, msg):
    global ok
    assert cond, "FAIL: " + msg
    ok += 1
    print("  ok -", msg)


# the MTV's default first pass: 0.2 MP = 608x320 pixels = a 38x20 latent, 124 frames = 32 latent frames
check(rv.H3_PIXELS_PER_LATENT == 16, "one H3 latent cell = 16x16 pixels")
tw, th, lw, lh = rv.builtin_upscale_size(38, 20, 1.2)
check(tw % 32 == 0 and th % 32 == 0 and (lw, lh) == (tw // 16, th // 16), "the size is a multiple of 32 pixels: %dx%d (latent %dx%d)" % (tw, th, lw, lh))
check(abs(tw * th / 1e6 - 1.2) < 0.08 and abs((tw / th) / (608 / 320) - 1) < 0.03, "about 1.2 MP and the clip's own shape: %dx%d" % (tw, th))
check(rv.builtin_upscale_size(38, 20, 2.0)[0] > tw and rv.builtin_upscale_size(20, 38, 1.2)[1] > rv.builtin_upscale_size(20, 38, 1.2)[0],
      "a bigger target gives a bigger size; a portrait clip stays portrait")

latent = {"samples": torch.randn(1, 24, 32, 20, 38), "noise_mask": torch.zeros(1)}
out, (w, h) = rv.resize_video_latent(latent, 1.2)
check(tuple(out["samples"].shape) == (1, 24, 32, lh, lw) and (w, h) == (tw, th),
      "a [1, 24, 32, 20, 38] latent becomes [1, 24, 32, %d, %d]: channels and frames kept" % (lh, lw))
check("noise_mask" not in out and "noise_mask" in latent, "the noise mask is dropped from the result (the input is not changed)")
flat = {"samples": torch.full((1, 24, 4, 20, 38), 0.7)}
check(torch.allclose(rv.resize_video_latent(flat, 1.2)[0]["samples"], torch.full((1, 24, 4, lh, lw), 0.7), atol=1e-5),
      "a flat latent stays flat (nothing invented)")
ramp = torch.linspace(-1, 1, 38).view(1, 1, 1, 1, 38).expand(1, 24, 2, 20, 38).contiguous()
row = rv.resize_video_latent({"samples": ramp}, 1.2)[0]["samples"][0, 0, 0, 0]
check(bool((row[1:] >= row[:-1] - 1e-6).all()) and float(row.min()) >= -1 - 1e-5 and float(row.max()) <= 1 + 1e-5,
      "a left-to-right ramp stays a ramp, within its range (bilinear: no overshoot)")
frames = torch.stack([torch.full((24, 20, 38), float(i)) for i in range(5)], dim=1)[None]
res = rv.resize_video_latent({"samples": frames}, 1.2)[0]["samples"]
check(all(abs(float(res[0, :, i].mean()) - i) < 1e-4 for i in range(5)), "each frame is resized on its own (no mixing between frames)")
half = rv.resize_video_latent({"samples": torch.randn(1, 24, 2, 20, 38).to(torch.bfloat16)}, 1.2)[0]["samples"]
check(half.dtype == torch.bfloat16, "the latent keeps its number type (bf16 stays bf16)")
same = {"samples": torch.randn(1, 24, 3, lh, lw)}
check(rv.resize_video_latent(same, 1.2)[0]["samples"] is same["samples"], "already the target size: returned as it is")
small = rv.resize_video_latent({"samples": torch.randn(1, 24, 2, 80, 152)}, 1.2)[0]["samples"]
check(tuple(small.shape[-2:]) == (lh, lw), "a latent bigger than the target is made smaller (antialiased)")
print("\nALL %d LATENT-RESIZE CHECKS PASSED" % ok)
