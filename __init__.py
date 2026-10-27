"""
IronLeo78 MTV  v0.01  (pre-alpha)  -  a ComfyUI node pack

Install: put this whole folder (ironleo78_mtv) into ComfyUI/custom_nodes/ and restart ComfyUI.
Hard-refresh the browser (Ctrl+F5). Nodes appear under  IronLeo78 > MTV :
    IronLeo78 MTV (v0.01)           makes a music-video clip per Run, synced to your own audio
    IronLeo78 MTV Model Loader      optional: models, LoRAs, steps and seed for the MTV node
    IronLeo78 2in1 Revitalizer      upscales + refines a clip saved by the MTV (Save Latent = ON)

Needs ComfyUI's own MiniMax H3 nodes; video / audio are decoded with PyAV (bundled with ComfyUI).
The Revitalizer also needs the third-party Comfyui_Minimax_h3_latent_Upscaler node (see README.md).
"""

__version__ = "0.01"

from .mtv import NODE_CLASS_MAPPINGS as _MTV_NODES
from .mtv import NODE_DISPLAY_NAME_MAPPINGS as _MTV_NAMES
from .model_loader import NODE_CLASS_MAPPINGS as _LOADER_NODES
from .model_loader import NODE_DISPLAY_NAME_MAPPINGS as _LOADER_NAMES
from .revitalizer import NODE_CLASS_MAPPINGS as _REV_NODES
from .revitalizer import NODE_DISPLAY_NAME_MAPPINGS as _REV_NAMES

NODE_CLASS_MAPPINGS = {**_MTV_NODES, **_LOADER_NODES, **_REV_NODES}
NODE_DISPLAY_NAME_MAPPINGS = {**_MTV_NAMES, **_LOADER_NAMES, **_REV_NAMES}

# Frontend extensions (web/): MTV segment panel + thumbnails + status box, Revitalizer Upload button.
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
