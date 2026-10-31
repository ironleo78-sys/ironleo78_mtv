"""v0.0.9v: the MTV must recognise the REAL "NONE" picture of the IronLeo78 9-Images loader (empty slot), with and without the
loader's mark, and never a real picture. Needs torch, numpy and Pillow (any ComfyUI Python has them):
    <ComfyUI python> tests/test_none_placeholder.py
Skips itself when torch is missing or the 9-Images loader is not found (nine_images.py in this pack since v0.1.0; the old
standalone folder next to the pack is still accepted)."""
import importlib
import importlib.util
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
CANDIDATES = [os.path.join(PACK, "nine_images.py"),
              os.path.join(os.path.dirname(PACK), "ComfyUI-IronLeo78-9Images", "__init__.py")]
LOADER = next((p for p in CANDIDATES if os.path.isfile(p)), None)
if LOADER is None:
    print("SKIPPED: the 9-Images loader was not found next to this pack.")
    sys.exit(0)

# ComfyUI stubs (torch / numpy / Pillow stay real)
for name in ("comfy", "comfy.sd", "comfy.utils", "comfy.model_management", "nodes", "server"):
    sys.modules[name] = MagicMock()
fp = types.ModuleType("folder_paths")
fp.get_input_directory = lambda: HERE
fp.get_output_directory = lambda: HERE
fp.get_filename_list = lambda k: []
sys.modules["folder_paths"] = fp
sys.modules["comfy_extras"] = types.ModuleType("comfy_extras")
sys.modules["comfy_extras.nodes_minimax_h3"] = types.ModuleType("comfy_extras.nodes_minimax_h3")

sys.path.insert(0, os.path.dirname(PACK))
mtv = importlib.import_module(os.path.basename(PACK) + ".mtv")
if LOADER == CANDIDATES[0]:      # v0.1.3: inside the pack it imports video_orientation.py, so it is loaded through the pack
    nine = importlib.import_module(os.path.basename(PACK) + ".nine_images")
else:                            # the old standalone folder (no relative imports)
    spec = importlib.util.spec_from_file_location("il78_nine_images", LOADER)
    nine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nine)

ok = 0


def check(cond, msg):
    global ok
    assert cond, "FAIL: " + msg
    ok += 1
    print("  ok -", msg)


none = nine._none_image()
check(getattr(none, "ironleo78_none", False) is True, "the loader marks its NONE picture")
check(mtv._is_none_placeholder(none), "the MTV recognises it by the mark")
plain = none.clone()
check(not hasattr(plain, "ironleo78_none"), "a copy of the picture loses the mark (as after another node)")
check(mtv._is_none_placeholder(plain), "the MTV still recognises it by its look (512x512, grey corners, lighter border)")
check(mtv._is_none_placeholder(nine._none_image()), "a second NONE picture (from the loader's cache) too")
video_none = nine._none_image(288, 512)
check(mtv._is_none_placeholder(video_none), "the loader's other NONE sizes carry the mark too")
check(not mtv._is_none_placeholder(video_none.clone()), "without the mark, only the 512x512 look is recognised (no guessing on other sizes)")

torch.manual_seed(0)
check(not mtv._is_none_placeholder(torch.rand(1, 512, 512, 3)), "a random 512x512 picture is a real picture")
check(not mtv._is_none_placeholder(torch.full((1, 512, 512, 3), 32 / 255.0)), "a flat grey 512x512 picture (no border) is a real picture")
check(not mtv._is_none_placeholder(torch.zeros(1, 512, 512, 4)), "a 4-channel picture is not the placeholder")
check(not mtv._is_none_placeholder(torch.zeros(2, 512, 512, 3)), "a batch of two is not the placeholder")
check(not mtv._is_none_placeholder(plain[:, :256]), "a cropped copy is a real picture")
print("\nALL %d NONE-PLACEHOLDER CHECKS PASSED" % ok)
