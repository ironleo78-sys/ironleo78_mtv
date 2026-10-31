"""
IronLeo78 MTV: ONE shared copy of the base diffusion model (v0.1.5, review item #4)
------------------------------------------------------------
The MTV and the 2in1 Revitalizer both load the same big MiniMax H3 diffusion model. Until 0.1.4 each kept its own copy,
and the MTV rebuilt its copy FROM DISK whenever a LoRA, a LoRA strength or the Turbo switch changed (its cache key held
the LoRAs), keeping up to two full copies in RAM.

Now the base model (the file, before any LoRA) is loaded once here and shared. Each node takes a clone of it (cheap:
the weights are shared) and adds its own LoRAs / attention backend on that clone, so a LoRA change only re-applies the
LoRAs. Only one base is kept: before another file (or another weight dtype) loads, every node that registered with
on_switch() drops what it built on the old base, so the old weights can leave memory first.

comfy / torch are imported only when a model really loads (the tests replace _load).
"""

import gc
import logging
import os

import folder_paths

log = logging.getLogger("IronLeo78.MTV.models")

_BASE = {}           # (abs path, mtime, weight dtype) -> the loaded base model (one entry at most)
_ON_SWITCH = []      # callables run before a DIFFERENT base loads (each node drops its models built on the old one)


def on_switch(callback):
    """Register `callback()` (once): it is run before another base model replaces the current one."""
    if callback not in _ON_SWITCH:
        _ON_SWITCH.append(callback)


def _key(name, weight_dtype):
    path = folder_paths.get_full_path_or_raise("diffusion_models", name)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = None
    return (os.path.abspath(path), mtime, str(weight_dtype)), path


def _load(path, weight_dtype):
    """The diffusion model file -> a ModelPatcher (what ComfyUI's own UNETLoader node does)."""
    import comfy.sd
    import torch
    model_options = {}
    if weight_dtype == "fp8_e4m3fn":
        model_options["dtype"] = torch.float8_e4m3fn
    elif weight_dtype == "fp8_e4m3fn_fast":
        model_options["dtype"] = torch.float8_e4m3fn
        model_options["fp8_matrix_mult"] = True
    elif weight_dtype == "fp8_e5m2":
        model_options["dtype"] = torch.float8_e5m2
    if hasattr(comfy.sd, "load_diffusion_model"):
        return comfy.sd.load_diffusion_model(path, model_options=model_options)
    return comfy.sd.load_unet(path)      # older ComfyUI


def diffusion_model(name, weight_dtype="default"):
    """(base model, True when it was already loaded). Never patch the base itself: take base.clone()."""
    key, path = _key(name, weight_dtype)
    hit = _BASE.get(key)
    if hit is not None:
        return hit, True
    if _BASE:      # another file / dtype: everything built on the old base goes first, then the base itself
        for callback in list(_ON_SWITCH):
            try:
                callback()
            except Exception as e:      # a node that cannot drop its models must not stop the load
                log.debug("model switch hook failed: %s", e)
        _BASE.clear()
        gc.collect()
    model = _load(path, weight_dtype)
    _BASE[key] = model
    log.info("diffusion model loaded once for the whole pack: %s", os.path.basename(path))
    return model, False


def held():
    """How many base models are kept (0 or 1)."""
    return len(_BASE)


def free():
    """Drop the shared base model (called by the MTV's free_cached_models)."""
    _BASE.clear()
