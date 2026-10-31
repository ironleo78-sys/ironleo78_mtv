"""
IronLeo78 MTV  v0.4.8  (pre-alpha)  -  a ComfyUI node pack

Install: put this whole folder (ironleo78_mtv) into ComfyUI/custom_nodes/ and restart ComfyUI.
Hard-refresh the browser (Ctrl+F5). Nodes appear under  IronLeo78 > MTV :
    IronLeo78 MTV (v0.4.8)               makes a music-video clip per Run, synced to your own audio
    IronLeo78 MTV Model Loader            optional: models, LoRAs, steps and seed for the MTV node
    IronLeo78 2in1 Revitalizer            upscales + refines a clip saved by the MTV (Save Latent = ON)
    IronLeo78-MTV-Prompt-Generator        9 pictures + 1 video + your prompt: writes the MTV prompt with a vision LLM and sends the
                                          nine pictures on ONE wire (Pictures) to the MTV (v0.1.21: it replaces the old 9-Images
                                          loader node and the prompt-generator subgraph, which are gone)

Needs ComfyUI's own MiniMax H3 nodes; video / audio are decoded with PyAV (bundled with ComfyUI).
The Revitalizer can use the third-party Comfyui_Minimax_h3_latent_Upscaler node when it is installed (optional since v0.1.7:
without it the Revitalizer resizes the latent itself; see README.md).
"""

__version__ = "0.4.8"

from .mtv import NODE_CLASS_MAPPINGS as _MTV_NODES
from .mtv import NODE_DISPLAY_NAME_MAPPINGS as _MTV_NAMES
from .model_loader import NODE_CLASS_MAPPINGS as _LOADER_NODES
from .model_loader import NODE_DISPLAY_NAME_MAPPINGS as _LOADER_NAMES
from .revitalizer import NODE_CLASS_MAPPINGS as _REV_NODES
from .revitalizer import NODE_DISPLAY_NAME_MAPPINGS as _REV_NAMES

from .prompt_generator import NODE_CLASS_MAPPINGS as _GEN_NODES
from .prompt_generator import NODE_DISPLAY_NAME_MAPPINGS as _GEN_NAMES

NODE_CLASS_MAPPINGS = {**_MTV_NODES, **_LOADER_NODES, **_REV_NODES, **_GEN_NODES}
NODE_DISPLAY_NAME_MAPPINGS = {**_MTV_NAMES, **_LOADER_NAMES, **_REV_NAMES, **_GEN_NAMES}

# Frontend extensions (web/): MTV segment panel, Model Loader Set New Defaults, Revitalizer Upload button + "Use Set New Defaults" +
# sigmas / LoRa migration, Prompt Generator thumbnail grid + Sync from MTV (il78_sync_logic.js) + named copy (il78_shadow.js).
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
