"""
IronLeo78 MTV  v0.01  (pre-alpha)
------------------------------------------------------------
Makes a music video clip by clip, synced to YOUR audio (a singer / musician performance track).
Loader + MiniMax H3 reference-to-video conditioning + sampling + decode + save, in ONE node, one clip per Run.

  LOADS     diffusion model -> Turbo LoRA (toggle) -> custom LoRA (Model Loader) -> core Model
            Attention Backend; Qwen3-VL text encoder; video VAE + audio VAE.
  MEDIA     Custom Audio (the song) is cut into segment-long chunks, one per Run; an optional Video
            File can drive the frames (Use Video ON) or supply the soundtrack. Up to three reference
            pictures (singer / musician, location ...), megapixel sizing (multiples of 32), Minimax
            frame count.
  AUDIO     Bypass Minimax is hardcoded: the audio chunk is encoded, frozen (noise mask 0) and joined
            to the video latent, so the model never invents sound; the picture follows the music.
  SAMPLES   RandomNoise -> BasicGuider -> KSamplerSelect -> BasicScheduler -> SamplerCustomAdvanced,
            then VAE Decode / VAE Decode Audio, Create Video and Save Video, all inside this node.

Upscaling is not done here: switch Save Latent ON and refine / upscale the clip afterwards with the
IronLeo78 2in1 Revitalizer node of this pack.

Where to start (no Start Frame / audio_start widgets)
  The segment counter at the top of the node decides where cutting starts. Segment 1 begins at second 0
  of the audio (or frame 0 of the video); every following segment is one real clip length later
  (frames / 24 fps, e.g. duration 5 s = 124 frames = 5.17 s). Jump to any segment N and the next Run
  starts at (N - 1) x segment length. Needs Next Segment On Run = ON to step through the file.

Selectable on the node
  Turbo                   ON (default) | OFF   (ON: Turbo LoRA, 4 steps. OFF: 25 steps, no Turbo LoRA.)
  Use Video / Video File / Custom Audio File / megapixels / duration / Next Segment On Run / prompt
  Audio Stem              Song | Vocals | Guitars | Drums | Bass   (right under Custom Audio File: which part of
                          the song is used. The first time a stem is chosen for a NEW song, Hybrid Demucs
                          separates all four and saves them to output/<Song>/stems/<Song>_<Stem>.wav; every
                          later Run, and every later session, just reads the file. See stems.py.)
  Bypassed Audio Latent   Audio From Video | Custom Audio   (which audio is bypassed into the latent
                          AND stepped through segment by segment)
  Save Latent             OFF (default) | ON
  Guide
  Picture1-3              reference pictures (with upload buttons and thumbnails)
  (models, custom LoRA, step counts, noise seed: on the IronLeo78 MTV Model Loader node, optional input
   "models". Nothing connected = hardcoded defaults, seed 1978.)

Save Latent ON (v0.4.1, now a toggle) the sampled latent and its conditioning are saved in the song folder, next to the
                          clip and sharing its name: <clip>_video.latent, <clip>_audio.latent (ComfyUI .latent files)
                          and <clip>.conditioning (prompt + pictures, no guide). Their numbers are listed in the clip's
                          .json sidecar, so the clip can be refined / upscaled later in another workflow.

Also on the node: segment panel (count, next, progress, Reset, Jump / Latest), one phase per model + conditioning
cache + shared model cache, quiet stop after the last segment, <clip>.json sidecar with the full prompt,
manifest CSV (<Song>_manifest.csv).
"""

import collections
import contextlib
import csv
import datetime
import gc
import hashlib
import json
import logging
import math
import os
import re

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps

import folder_paths
import comfy.sd
import comfy.utils
import nodes
import nodes as comfy_nodes

from . import stems as _stems
from . import conditioning_io as _cond_io
log = logging.getLogger("IronLeo78.MTV")

VERSION = "0.01"

NONE_CHOICE = "None"       # empty selection for every file slot
NONE_LORA = NONE_CHOICE
RESIZE_METHOD = "lanczos"  # images: fixed
DIVISIBLE_BY = 32          # every width/height is a multiple of 32
CREDIT = "IronLeo78 MTV"

CORE_ATTN_NODE = "ModelAttentionBackend"
CORE_CLIP_NODE = "CLIPLoader"
CORE_VAE_NODE = "VAELoader"
FALLBACK_ATTN_OPTIONS = ["pytorch attention", "comfy kitchen attention"]
FALLBACK_CLIP_TYPES = ["stable_diffusion", "minimax"]

# Default values (taken from the reference workflow settings).
# A file default is only applied if that file is installed, otherwise "None".
DEFAULT_UNET = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
DEFAULT_TURBO_LORA = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
DEFAULT_ATTENTION = "comfy kitchen attention"
DEFAULT_QWEN_VL = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
DEFAULT_VIDEO_VAE = "minimax_h3_video_vae_int8_convrot.safetensors"
DEFAULT_AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
DEFAULT_MEGAPIXELS = 0.2          # v2.7.1 (was 0.5)
DEFAULT_DURATION = 15.0           # v2.7.1 (was 5.0)
DEFAULT_CUSTOM_LORA = "H3_Unlocked_V2.safetensors"   # v2.7.1: pre-selected (and ON) when it is installed
DEFAULT_CUSTOM_LORA_STR = 0.65    # v2.7.1 (was 1.0)
DEFAULT_CUSTOM_LORA_ENABLED = False   # v2.8.6: OFF by default (the Model Loader can switch it ON)
MIN_REF_AUDIO_SECONDS = 0.25  # shorter audio can't be encoded by the audio VAE
MAX_REF_AUDIO_SECONDS = 15.0  # longer audio (a whole song) runs the audio VAE out of memory

# Hardcoded settings: not shown on the node any more.
FIXED_SETTINGS = {
    "unet_name": DEFAULT_UNET,
    "weight_dtype": "default",
    "turbo_lora_name": DEFAULT_TURBO_LORA,
    "turbo_lora_strength": 1.0,
    "custom_lora_enabled": DEFAULT_CUSTOM_LORA_ENABLED,   # v2.8.6: hardcoded; the Model Loader can change all three
    "custom_lora_name": DEFAULT_CUSTOM_LORA,
    "custom_lora_strength": DEFAULT_CUSTOM_LORA_STR,
    "attention_enabled": True,
    "attention": DEFAULT_ATTENTION,
    "qwen_vl_name": DEFAULT_QWEN_VL,
    "qwen_vl_type": "minimax",
    "qwen_vl_device": "default",
    "video_vae_name": DEFAULT_VIDEO_VAE,
    "audio_vae_name": DEFAULT_AUDIO_VAE,
    "ref_image_size": "match",
    "Live Preview": True,        # v2.5.1: ComfyUI's latent preview during sampling stays ON (the saved video is never previewed)
    "force_rate": 24.0,          # always 24 fps
    "turbo_steps": 4,            # Turbo ON  (the Model Loader can change it)
    "full_steps": 25,            # Turbo OFF (the Model Loader can change it)
}

# v2.3: what the optional "models" input (Model Loader) may override. key -> (label, folder)
MODELS_TYPE = "IRONLEO78_MTV_MODELS"
MODEL_FILE_KEYS = {
    "unet_name": ("Diffusion model", "diffusion_models"),
    "turbo_lora_name": ("Turbo LoRA", "loras"),
    "qwen_vl_name": ("Qwen3-VL text encoder", "text_encoders"),
    "video_vae_name": ("Video VAE", "vae"),
    "audio_vae_name": ("Audio VAE", "vae"),
}
MODEL_STEP_KEYS = ("turbo_steps", "full_steps")
# (the seed, "noise_seed", is read from the Model Loader too, see apply_model_overrides; v2.8.5)
MIN_STEPS, MAX_STEPS = 1, 200

# Hardcoded sampling / output settings.
SAMPLER_NAME = "res_multistep"
SCHEDULER_NAME = "simple"
DENOISE = 1.0
VIDEO_COLOR_SPACE = "sRGB"
VIDEO_CODEC = "h264"          # Create Video
SAVE_FORMAT = "mp4"
SAVE_CODEC = "h264"
SAVE_ENCODING = "auto"
DEFAULT_FPS = 24.0            # Minimax runs at 24 fps: used everywhere
DEFAULT_PREFIX = "video/ComfyUI"
MAX_SEED = 0xFFFFFFFFFFFFFFFF
DEFAULT_SEED = 1978
TURBO_STEPS = 4               # Turbo LoRA ON
FULL_STEPS = 25               # Turbo LoRA OFF (official r2v template path: no LoRA, more steps)
DEFAULT_SAVE_LATENT = False   # v0.6: the "Save Latent" toggle of a NEW node (OFF: no .latent / .conditioning files)

STATE_FILE = os.path.join(os.path.dirname(__file__), "mtv_state.json")
LAST_FRAME_FILE = os.path.join(os.path.dirname(__file__), "mtv_last_frame.png")
GUIDE_FRAME_IDX = 0           # the previous run's last frame guides the very first frame

# v2.8: one clip per Run. The file tag / manifest "scene" value stays "A" so earlier clips and manifests still match.
SCENE_TAG = "A"
MANIFEST_NO_SONG = "mtv_manifest.csv"
MANIFEST_FIELDS = ["timestamp", "song", "segment", "scene",
                   "start_s", "end_s", "duration_s", "frames", "width", "height", "seed", "turbo",
                   "pictures", "prompt", "file", "prompt_json", "audio_stem", "latent_file", "conditioning_file"]
MANIFEST_PROMPT_CHARS = 300   # the CSV shows this much of the prompt; the full text is in the clip's sidecar .json

# v2.2: routing / performance
COND_CACHE_MAX = 6                         # conditioning A / B + audio latent + headroom
AUDIO_CACHE_MAX_BYTES = 768 * 1024 * 1024  # a decoded custom audio file is kept in RAM up to this size
FREE_ROUTE = "/ironleo78/mtv/free"
SEGMENT_ROUTE = "/ironleo78/mtv/segments"   # v2.5: GET  = segment count + counter
RESET_ROUTE = "/ironleo78/mtv/reset"        # v2.5: POST = counter back to segment 1
JUMP_ROUTE = "/ironleo78/mtv/jump"          # v2.6: POST = counter to any segment

VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".gif")
AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma")


# ---------------------------------------------------------------------- #
# model-side helpers
# ---------------------------------------------------------------------- #
def _first_output(result):
    """Normalise V1 tuples and V3 NodeOutput objects to the first output."""
    if isinstance(result, tuple):
        return result[0]
    for attr in ("result", "args"):
        val = getattr(result, attr, None)
        if val:
            return val[0]
    return result


def _core_options(node_name, input_name, fallback):
    """Read a combo list from a core node so it stays in sync with ComfyUI."""
    try:
        cls = comfy_nodes.NODE_CLASS_MAPPINGS[node_name]
        options = cls.INPUT_TYPES()["required"][input_name][0]
        if isinstance(options, (list, tuple)) and len(options) > 0:
            return list(options)
    except Exception as e:
        log.debug("Could not read %s.%s: %s", node_name, input_name, e)
    return list(fallback)


def _lora_choices():
    return [NONE_LORA] + folder_paths.get_filename_list("loras")


def _pick_default(choices, wanted):
    return wanted if wanted in choices else choices[0]


def _default_file(choices, wanted):
    """Preferred default if that file exists in the list, otherwise None."""
    return wanted if wanted in choices else NONE_CHOICE


def _with_none(names):
    return [NONE_CHOICE] + [n for n in names if n != NONE_CHOICE]


def _vae_options():
    return _core_options(CORE_VAE_NODE, "vae_name", folder_paths.get_filename_list("vae"))


# ---- shared stage cache (keeps models loaded while the media part re-runs)
# v2.2: keyed by stage + settings (file names + mtimes), NOT by node id: two nodes with the same
# models share one copy, and nothing is left behind per deleted node.
_CACHE = {}       # stage -> OrderedDict(key -> value)
_CACHE_LIMIT = {"model": 2}   # every other stage keeps one entry
_LORA_CACHE = {}  # path -> loaded lora state dict (single entry)
_COND_CACHE = collections.OrderedDict()    # conditioning / audio-latent results (small, LRU)
_AUDIO_CACHE = {}                          # file id -> decoded custom audio (single entry)
_STEMS_READY = {}                          # file id -> ({stem: wav path}, info): stems known to be on disk
_RUNNING = 0                               # >0 while a Run is executing (the free route refuses then)


def _stamp(folder, name):
    """(name, mtime) so replacing a file on disk invalidates the cache."""
    if not name or name == NONE_CHOICE:
        return (name, None)
    try:
        return (name, os.path.getmtime(folder_paths.get_full_path(folder, name)))
    except Exception:
        return (name, None)


def _file_id(name):
    """(name, mtime_ns, size) of an input-folder file: identifies its CONTENT for the caches."""
    if not name or name == NONE_CHOICE:
        return None
    try:
        st = os.stat(folder_paths.get_annotated_filepath(name))
        return (str(name), int(st.st_mtime_ns), int(st.st_size))
    except Exception:
        return (str(name), None, None)


def _cached(uid, stage, key, builder):
    entries = _CACHE.setdefault(stage, collections.OrderedDict())
    if key in entries:
        entries.move_to_end(key)
        return entries[key]
    limit = _CACHE_LIMIT.get(stage, 1)
    while len(entries) >= limit:      # free the old one(s) before loading the new one
        entries.popitem(last=False)
    value = builder()
    entries[key] = value
    return value


def _lru_get(cache, key):
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    return None


def _lru_put(cache, key, value, limit=COND_CACHE_MAX):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)


def _clone_cond(positive):
    """Light copy of a conditioning list (tensors shared, dicts copied) so a cached entry is never mutated."""
    try:
        return [[t, dict(d)] for t, d in positive]
    except Exception:
        return positive


def free_cached_models(reason=""):
    """Drop every cached model / conditioning / audio and ask ComfyUI to unload what it holds."""
    _CACHE.clear()
    _LORA_CACHE.clear()
    _COND_CACHE.clear()
    _AUDIO_CACHE.clear()
    gc.collect()
    try:
        import comfy.model_management as mm
        mm.unload_all_models()
        mm.soft_empty_cache()
    except Exception as e:
        log.debug("Could not ask ComfyUI to unload models: %s", e)
    log.info("cached models freed%s", f" ({reason})" if reason else "")


def _register_routes():
    """POST .../free (the node's JS calls it after the last node was removed),
    GET .../segments (v2.5: segment count + counter for the node's segment panel),
    POST .../reset (v2.5: the Reset button), POST .../jump (v2.6: Go / Latest)."""
    try:
        from aiohttp import web
        from server import PromptServer
        if PromptServer.instance is None:
            return
        routes = PromptServer.instance.routes

        @routes.post(FREE_ROUTE)
        async def _free_route(request):
            if _RUNNING > 0:
                return web.json_response({"ok": False, "busy": True})
            free_cached_models("node removed")
            return web.json_response({"ok": True})

        @routes.get(SEGMENT_ROUTE)
        async def _segment_route(request):
            import asyncio
            params = dict(request.rel_url.query)
            try:      # the file probing runs in a worker thread: never block the server
                info = await asyncio.get_running_loop().run_in_executor(None, _segment_info, params)
            except Exception as e:
                log.debug("segment info failed: %s", e)
                return web.json_response({"ok": False, "error": str(e)})
            info["ok"] = True
            return web.json_response(info)

        @routes.post(RESET_ROUTE)
        async def _reset_route(request):
            if _RUNNING > 0:
                return web.json_response({"ok": False, "busy": True})
            _reset_state()
            log.info("segment counter reset to 0")
            return web.json_response({"ok": True, "index": 0})

        @routes.post(JUMP_ROUTE)
        async def _jump_route(request):
            if _RUNNING > 0:
                return web.json_response({"ok": False, "busy": True})
            try:
                body = await request.json()
            except Exception:
                body = {}
            return web.json_response(_handle_jump(body))
    except Exception as e:
        log.debug("routes not registered: %s", e)


def _is_interrupt(e):
    return type(e).__name__ == "InterruptProcessingException"


def _stage(label, fn, *args):
    """Run one stage; on failure raise an error that names the stage."""
    try:
        return fn(*args)
    except Exception as e:
        if _is_interrupt(e):  # the user pressed Cancel: let ComfyUI handle it
            raise
        log.error("Stage '%s' failed: %s", label, e)
        raise RuntimeError(f"[IronLeo78 MTV] stage '{label}' failed: {e}") from e


# ---------------------------------------------------------------------- #
# calling ComfyUI's own nodes (V1 and V3 style) by name
# ---------------------------------------------------------------------- #
_MISSING = object()


def _spec_options(spec):
    """Combo options of an INPUT_TYPES entry, or None when it is not a combo."""
    if not isinstance(spec, (list, tuple)) or not spec:
        return None
    first = spec[0]
    if isinstance(first, (list, tuple)):
        return list(first)
    if first == "COMBO" and len(spec) > 1 and isinstance(spec[1], dict):
        return list(spec[1].get("options") or [])
    return None


def _spec_default(spec):
    """The widget default of an INPUT_TYPES entry, _MISSING for link inputs."""
    if not isinstance(spec, (list, tuple)) or not spec:
        return _MISSING
    opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    combo = _spec_options(spec)
    if combo is not None:
        return opts.get("default", combo[0] if combo else _MISSING)
    kind = spec[0]
    if kind == "BOOLEAN":
        return opts.get("default", False)
    if kind == "STRING":
        return opts.get("default", "")
    if kind in ("INT", "FLOAT"):
        return opts.get("default", opts.get("min", 0))
    return _MISSING


def _is_dynamic(spec):
    """V3 'DynamicCombo' input: a combo whose chosen option brings its own sub-inputs."""
    return (isinstance(spec, (list, tuple)) and bool(spec) and isinstance(spec[0], str)
            and "DYNAMICCOMBO" in spec[0].upper())


def _dyn_options(spec):
    """{option key: {sub-input name: sub-input spec}} of a dynamic combo."""
    raw = spec[1].get("options") if len(spec) > 1 and isinstance(spec[1], dict) else None
    out = {}
    for opt in raw or []:
        if isinstance(opt, dict):
            key, inputs = opt.get("key"), opt.get("inputs")
        elif isinstance(opt, (list, tuple)) and len(opt) >= 2:
            key, inputs = opt[0], opt[1]
        else:
            continue
        subs = {}
        if isinstance(inputs, dict):
            for section in ("required", "optional"):
                subs.update(inputs.get(section) or {})
        out[key] = subs
    return out


def _nested_names(spec):
    """Every sub-input name found inside a dynamic combo, at any depth."""
    names = set()
    for subs in _dyn_options(spec).values():
        for sub, sub_spec in subs.items():
            names.add(sub)
            if _is_dynamic(sub_spec):
                names |= _nested_names(sub_spec)
    return names


def _dyn_value(key, spec, provided, consumed, notes, node):
    """
    Build the dict a dynamic combo expects: {key: chosen option, sub-input: value, ...}.
    Sub-inputs we know (by name, e.g. codec / encoding) are filled from `provided`;
    the others get their own default.
    """
    options = _dyn_options(spec)
    if not options:
        return provided.get(key)
    chosen = provided.get(key)
    if chosen not in options:
        if chosen is not None and notes is not None:
            notes.append(f"{node}: '{key}' has no option '{chosen}' here, using its default")
        opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
        chosen = opts.get("default", next(iter(options)))
        if chosen not in options:
            chosen = next(iter(options))
    value = {key: chosen}
    for sub, sub_spec in options[chosen].items():
        if _is_dynamic(sub_spec):          # a dynamic combo inside a dynamic combo (format -> codec -> encoding)
            value[sub] = _dyn_value(sub, sub_spec, provided, consumed, notes, node)
            consumed.add(sub)
            continue
        combo = _spec_options(sub_spec)
        if sub in provided and (not combo or provided[sub] in combo):
            value[sub] = provided[sub]
            consumed.add(sub)
            continue
        if sub in provided and notes is not None:
            notes.append(f"{node}: '{sub}' has no option '{provided[sub]}' here, using its default")
            consumed.add(sub)
        default = _spec_default(sub_spec)
        if default is not _MISSING:
            value[sub] = default
    return value


def _describe_spec(spec):
    if not _is_dynamic(spec):
        return ""
    parts = []
    for opt, subs in _dyn_options(spec).items():
        inner = ", ".join(k + ("=" + _describe_spec(v) if _is_dynamic(v) else "") for k, v in subs.items())
        parts.append(f"{opt}({inner})" if inner else str(opt))
    return "dynamic{" + " | ".join(parts) + "}"


def _describe_schema(schema):
    """Compact one-line description of a node's inputs (for the notes when something is off)."""
    return ", ".join(key + ("=" + _describe_spec(spec) if _is_dynamic(spec) else "")
                     for key, (_, spec) in schema.items())


def _split_result(res):
    """Any node result (tuple / dict / V3 NodeOutput) -> (outputs tuple, ui dict or None)."""
    ui = None
    if isinstance(res, dict):
        ui = res.get("ui")
        outs = res.get("result", ())
    elif isinstance(res, tuple):
        outs = res
    elif hasattr(res, "args") or hasattr(res, "result"):
        ui = getattr(res, "ui", None)
        outs = getattr(res, "args", None) or getattr(res, "result", None) or ()
    else:
        outs = (res,)
    if ui is not None and hasattr(ui, "as_dict"):
        ui = ui.as_dict()
    return tuple(outs), (ui if isinstance(ui, dict) else None)


def _core(name, provided, strict=(), hidden=None, notes=None, hoist=False):
    """
    Run a core ComfyUI node by name.
    - `provided` = the inputs we set; the node's own schema is read at run time, so
      inputs we do not set get the node's OWN default (survives ComfyUI updates).
    - `strict` = names that MUST exist in the schema (else a clear error).
    - Dynamic combos (V3) are built as the dict the node expects, nested to any depth.
      Inputs that the schema ALSO lists at top level but that live inside a dynamic combo
      are normally not passed separately; hoist=True passes them as well.
    - Names in `provided` that do not exist in this ComfyUI version are skipped and
      reported in `notes`; a combo value the node does not offer falls back to its default.
    Returns (outputs tuple, ui dict or None).
    """
    cls = comfy_nodes.NODE_CLASS_MAPPINGS.get(name)
    if cls is None:
        raise RuntimeError(f"core node '{name}' not found in this ComfyUI.")

    try:
        types = cls.INPUT_TYPES()
        schema = {}
        for section in ("required", "optional"):
            for key, spec in (types.get(section) or {}).items():
                schema[key] = (section, spec)
    except Exception as e:
        log.debug("No schema for %s (%s); passing inputs unchanged.", name, e)
        schema = None

    if schema is None:
        kwargs = dict(provided)
    else:
        for key in strict:
            if key not in schema:
                raise RuntimeError(f"core node '{name}' has no input '{key}' (ComfyUI changed?).")
        kwargs = {}
        consumed = set()   # names that live inside a dynamic combo
        nested = set()
        for _, spec in schema.values():
            if _is_dynamic(spec):
                nested |= _nested_names(spec)
        for key, (section, spec) in schema.items():
            if _is_dynamic(spec) and (key in provided or section == "required"):
                if key in nested and not hoist:
                    continue
                kwargs[key] = _dyn_value(key, spec, provided, set() if key in nested else consumed, notes, name)
        for key, value in provided.items():
            if key in consumed or key in nested or (key in schema and _is_dynamic(schema[key][1])):
                continue
            if key not in schema:
                msg = (f"{name}: input '{key}' does not exist in this ComfyUI, skipped "
                       f"(inputs here: {_describe_schema(schema)})")
                log.warning(msg)
                if notes is not None:
                    notes.append(msg)
                continue
            options = _spec_options(schema[key][1])
            if options and value not in options:
                msg = f"{name}: '{key}' has no option '{value}' here, using its default"
                log.warning(msg)
                if notes is not None:
                    notes.append(msg)
                continue
            kwargs[key] = value
        for key, (section, spec) in schema.items():
            if key in kwargs or section != "required":
                continue
            if key in nested and not hoist:
                continue
            default = _spec_default(spec)
            if default is _MISSING:
                raise RuntimeError(f"core node '{name}': required input '{key}' was not supplied.")
            kwargs[key] = default

    target = cls
    if hidden is not None and hasattr(cls, "PREPARE_CLASS_CLONE"):  # V3 nodes reading cls.hidden
        try:
            target = cls.PREPARE_CLASS_CLONE(hidden)
        except Exception as e:
            log.warning("PREPARE_CLASS_CLONE failed for %s: %s", name, e)
            target = cls

    # Safety net: V3 nodes such as SaveVideo read cls.hidden.extra_pnginfo. If the clone did
    # not provide it (hidden is None), set a plain holder on the class for the duration of the call.
    patched = []
    if hidden is not None:
        import types as _types
        holder = _types.SimpleNamespace(
            unique_id=hidden.get("UNIQUE_ID"), prompt=hidden.get("PROMPT"),
            extra_pnginfo=hidden.get("EXTRA_PNGINFO"), dynprompt=None,
            auth_token_comfy_org=None, api_key_comfy_org=None)
        for obj in {id(cls): cls, id(target): target}.values():
            if getattr(obj, "hidden", None) is None:
                try:
                    old_hidden = getattr(obj, "hidden", None)
                    obj.hidden = holder
                    patched.append((obj, old_hidden))
                except Exception as e:
                    log.debug("Could not set hidden on %s: %s", name, e)
    try:
        if hasattr(target, "EXECUTE_NORMALIZED"):
            res = target.EXECUTE_NORMALIZED(**kwargs)
        elif hasattr(cls, "FUNCTION") and callable(getattr(cls, cls.FUNCTION, None)):
            res = getattr(cls(), cls.FUNCTION)(**kwargs)
        else:
            res = cls.execute(**kwargs)
    finally:
        for obj, old_hidden in patched:
            try:
                obj.hidden = old_hidden
            except Exception:
                pass
    return _split_result(res)


@contextlib.contextmanager
def _preview_scope(enabled):
    """
    Live Preview OFF: ComfyUI's latent previews are switched off while the sampler
    runs (restored afterwards), so the node's last picture is the saved video.
    Live Preview ON: ComfyUI's own --preview-method decides.
    """
    args = no_preview = old = None
    if not enabled:
        try:
            from comfy.cli_args import args, LatentPreviewMethod
            no_preview = LatentPreviewMethod.NoPreviews
            old = args.preview_method
            args.preview_method = no_preview
        except Exception as e:
            log.debug("Could not switch previews off: %s", e)
            args = None
    try:
        yield
    finally:
        if args is not None and old is not None:
            args.preview_method = old


# ---------------------------------------------------------------------- #
# segment counter state
# ---------------------------------------------------------------------- #
def _load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _write_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def _load_index():
    try:
        return int(_load_state().get("index", 0))
    except (TypeError, ValueError):
        return 0


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _save_index(index):
    state = _load_state()      # keep the other keys (guide_frame_for)
    state["index"] = index
    state["furthest"] = max(_to_int(state.get("furthest")), int(index))     # v2.6: the "Latest" button
    _write_state(state)


def _load_furthest():
    """v2.6: the highest counter value a Run (or a jump away from it) has left behind."""
    return max(_to_int(_load_state().get("furthest")), _load_index())


def _jump_to(segment):
    """v2.6: the NEXT Run makes segment number `segment` (1 = the first, as the panel counts).
    Returns (counter, furthest). The guide frames are kept (they are checked against the counter when used)."""
    segment = int(segment)
    if segment < 1:
        raise ValueError("segment numbers start at 1")
    state = _load_state()
    state["furthest"] = max(_to_int(state.get("furthest")), _to_int(state.get("index")))
    state["index"] = segment - 1
    _write_state(state)
    return state["index"], state["furthest"]


def _handle_jump(body):
    """The /jump route without the web layer: body = {"segment": N [, "total": T]} or {"latest": true}.
    Returns the JSON answer."""
    body = body if isinstance(body, dict) else {}
    try:
        if body.get("latest"):
            target = _load_furthest() + 1
        else:
            target = int(body.get("segment"))
            total = body.get("total")
            if total not in (None, "") and target > int(total):
                return {"ok": False, "error": f"there are only {int(total)} segments"}
        if target < 1:
            return {"ok": False, "error": "segment numbers start at 1"}
    except (TypeError, ValueError):
        return {"ok": False, "error": "the segment must be a whole number (1 or more)"}
    index, furthest = _jump_to(target)
    log.info("segment counter set: the next Run makes segment %d", index + 1)
    return {"ok": True, "index": index, "segment": index + 1, "furthest": furthest}


def _reset_state():
    """v2.5: the Reset button. Segment counter back to 0 (and the saved guide frames forgotten)."""
    _write_state({"index": 0})


def _last_frame_of(images):
    """The last frame of a decoded video as a small CPU tensor [1,H,W,3] (so the video itself can be freed)."""
    return images[-1].detach().float().cpu().clamp(0, 1)[None].clone()


def _save_last_frame(frame, segment):
    """Keep the last frame of this run (it was segment number `segment`) for the Guide of the next run."""
    arr = frame[0].numpy()
    Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8)).save(LAST_FRAME_FILE)
    state = _load_state()
    state["guide_frame_for"] = int(segment)
    _write_state(state)


def _clip_from_manifest(song, segment):
    """v2.6: the clip saved for `segment` (0-based, as in the file names), found through the
    manifest (rows of other scene tags, from older versions, are ignored). The LATEST row that still has a
    file on disk wins (a redo adds a row). Manifests of 0.5 and older may also list an upscaled clip: it is preferred.
    None when there is none."""
    path = _manifest_path(song)
    if not os.path.exists(path):
        return None
    out_dir = folder_paths.get_output_directory()
    found = None
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if _to_int(row.get("segment"), -1) != int(segment) or (row.get("scene") or SCENE_TAG) != SCENE_TAG:
                continue
            for key in ("upscaled_file", "file"):
                rel = (row.get(key) or "").strip()
                full = os.path.join(out_dir, *rel.split("/")) if rel else ""
                if full and os.path.exists(full):
                    found = full
                    break
    return found


def _clip_last_frame_array(path):
    """v2.6: the last video frame of a saved clip as an RGB uint8 array [H, W, 3] (PyAV), None when empty."""
    container = _open_media(path)
    try:
        last = None
        for frame in container.decode(video=0):
            last = frame
        return None if last is None else last.to_ndarray(format="rgb24")
    finally:
        container.close()


def _load_last_frame(index, song=None):
    """(image [1,H,W,3] or None, reason). Only valid when it comes from the segment right before `index`.
    v2.6: when the saved frame is from another segment (after a jump / a redo), and `song` is given, the frame
    is read back from the clip that segment saved (found through the manifest). reason then names the clip."""
    if index <= 0:
        return None, "first segment, nothing to continue from"
    if _load_state().get("guide_frame_for") == index - 1 and os.path.exists(LAST_FRAME_FILE):
        img = Image.open(LAST_FRAME_FILE).convert("RGB")
        arr = np.array(img).astype(np.float32) / 255.0
        return torch.from_numpy(arr)[None,], ""
    if song is not None:
        try:
            clip = _clip_from_manifest(song, index - 1)
            arr = _clip_last_frame_array(clip) if clip else None
            if arr is not None:
                return (torch.from_numpy(arr.astype(np.float32) / 255.0)[None,],
                        f"read back from the saved clip {os.path.basename(clip)}")
        except Exception as e:
            log.warning("Could not read the last frame back from segment %d: %s", index - 1, e)
    return None, f"no saved last frame from segment {index - 1}"


# ---------------------------------------------------------------------- #
# v2.1: file names / manifest for musical sections
# ---------------------------------------------------------------------- #
def _safe_name(text, max_len=60):
    """Letters (accents kept), digits, '_' and '-' only; everything else becomes '_'."""
    out = re.sub(r"[^\w\-]+", "_", str(text or "").strip())
    return out.strip("_-")[:max_len].strip("_-")


def _song_name(kw):
    """v2.4: the song name is the Custom Audio File name (no extension), or '' when none is selected."""
    f = kw.get("Custom Audio File", NONE_CHOICE)
    if not f or f == NONE_CHOICE:
        return ""
    base = os.path.basename(str(f).replace("\\", "/").split(" [")[0])   # 'sub/song.wav [input]' -> 'song.wav'
    return _safe_name(os.path.splitext(base)[0])


def _clip_prefix(kw, media):
    """(SaveVideo filename_prefix, tag) for the clip of this Run.
    <Song>/<Song>_seg004_A   (ComfyUI adds its own _00001_ counter after it).
    No custom audio: <video or Picture1 name>_seg004_A in the output folder (or video/ComfyUI_seg004_A)."""
    song = _song_name(kw)
    stem = _safe_name(media.get("filename", ""))
    base = song or stem or "ComfyUI"
    folder = song if song else ("" if stem else "video")
    tag = f"{base}_seg{int(media.get('index', 0)):03d}_{SCENE_TAG}"
    return (f"{folder}/{tag}" if folder else tag), tag


def _manifest_fields(path):
    """Header of an existing manifest. A manifest from an older version gets the new columns
    (v2.5: prompt_json) added in place. None = the file is empty (a header must be written)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = list(reader.fieldnames or [])
        rows = list(reader) if header else []
    if not header:
        return None
    missing = [c for c in MANIFEST_FIELDS if c not in header]
    if not missing:
        return header
    fields = header + missing
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, path)
    return fields


def _manifest_path(song):
    out_dir = folder_paths.get_output_directory()
    song_s = _safe_name(song)
    folder = os.path.join(out_dir, song_s) if song_s else out_dir
    return os.path.join(folder, f"{song_s}_manifest.csv" if song_s else MANIFEST_NO_SONG)


def _append_manifest(song, rows):
    """Append one CSV row per saved clip. Returns the manifest path relative to the output folder."""
    out_dir = folder_paths.get_output_directory()
    path = _manifest_path(song)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fields = _manifest_fields(path) if os.path.exists(path) else None
    is_new = fields is None
    if is_new:
        fields = list(MANIFEST_FIELDS)
    with open(path, "a", newline="", encoding="utf-8-sig" if is_new else "utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore", restval="")
        if is_new:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return os.path.relpath(path, out_dir).replace(os.sep, "/")


def _write_sidecar(saved, data):
    """v2.5: <clip>.json next to a saved clip. `saved` = 'subfolder/file.mp4' as SaveVideo reported it.
    Returns the sidecar path relative to the output folder ('' when there is nothing to attach it to)."""
    if not saved or saved == "?":
        return ""
    out_dir = folder_paths.get_output_directory()
    path = os.path.splitext(os.path.join(out_dir, *saved.split("/")))[0] + ".json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return os.path.relpath(path, out_dir).replace(os.sep, "/")


# ---------------------------------------------------------------------- #
# file listings
# ---------------------------------------------------------------------- #
def _image_files():
    input_dir = folder_paths.get_input_directory()
    files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
    try:
        files = folder_paths.filter_files_content_types(files, ["image"])
    except Exception:
        pass
    return sorted(files)


def _video_files():
    d = folder_paths.get_input_directory()
    try:
        files = [f for f in os.listdir(d)
                 if os.path.isfile(os.path.join(d, f)) and f.lower().endswith(VIDEO_EXTS)]
    except Exception:
        files = []
    return sorted(files)


def _audio_files():
    d = folder_paths.get_input_directory()
    try:
        files = [f for f in os.listdir(d)
                 if os.path.isfile(os.path.join(d, f)) and f.lower().endswith(AUDIO_EXTS)]
    except Exception:
        files = []
    return [NONE_CHOICE] + sorted(files)


# ---------------------------------------------------------------------- #
# audio helpers
# ---------------------------------------------------------------------- #
def _silent_audio(seconds=None):
    """Silence. Default is the old 1-sample placeholder; the Audio1/Audio2 outputs
    use a real length (up to 30 s) so later nodes (VAE Encode Audio...) still work."""
    n = 1 if seconds is None else max(44100, int(min(float(seconds), 30.0) * 44100))
    return {"waveform": torch.zeros((1, 2, n)), "sample_rate": 44100}


def _load_custom_audio(name):
    """The whole custom audio file, decoded ONCE and kept in RAM (a Run only slices a chunk out of it).
    Files bigger than AUDIO_CACHE_MAX_BYTES are decoded every Run as before. Never mutate the result."""
    if not name or name == NONE_CHOICE:
        return None
    fid = _file_id(name)
    hit = _AUDIO_CACHE.get(fid)
    if hit is not None:
        return hit
    audio = _decode_custom_audio(name)
    if audio is not None and fid is not None and fid[1] is not None:
        _AUDIO_CACHE.clear()          # one entry only
        if audio["waveform"].numel() * audio["waveform"].element_size() <= AUDIO_CACHE_MAX_BYTES:
            _AUDIO_CACHE[fid] = audio
    return audio


def _decode_custom_audio(name):
    path = folder_paths.get_annotated_filepath(name)
    cls = nodes.NODE_CLASS_MAPPINGS.get("LoadAudio")
    if cls is not None:
        try:
            return cls().load(name)[0]
        except Exception:
            pass
    audio = _decode_audio(path)
    if audio is None:
        raise RuntimeError(f"No audio stream found in custom audio file: {name}")
    return audio


def _slice_audio(audio, start, dur):
    """Window [start, start+dur) seconds of an AUDIO dict. dur <= 0 = to the end.
    Returns None when `start` is at or past the end of the audio."""
    wave = audio["waveform"]
    sr = float(audio["sample_rate"])
    total = wave.shape[-1]
    first = int(round(max(0.0, start) * sr))
    if first >= total:
        return None
    last = total if dur is None or dur <= 0 else min(total, int(round((max(0.0, start) + dur) * sr)))
    if last <= first:
        return None
    return {**audio, "waveform": wave[..., first:last].clone()}   # clone: never alias the cached audio


# ---------------------------------------------------------------------- #
# v0.3 / v0.6: saving the sampled latent + conditioning (Save Latent ON) for a later refine / upscale in another workflow
# ---------------------------------------------------------------------- #
def _clip_counter(st):
    """The number the first-pass clip has (or is about to get): <tag>_NNNNN_.mp4. The saved latents and conditioning use
    the same number. Taken from the saved file name when there is one, else the number SaveVideo would use next."""
    m = re.search(r"_(\d+)_\.[^./\\]+$", str(st.get("file") or ""))
    if m:
        return int(m.group(1))
    out_dir = folder_paths.get_output_directory()
    try:
        return int(folder_paths.get_save_image_path(str(st["prefix"]), out_dir)[2])
    except Exception:
        folder = os.path.join(out_dir, *os.path.dirname(str(st["prefix"]).replace("\\", "/")).split("/"))
        pattern = re.compile(re.escape(st["tag"]) + r"_(\d{5})_")
        best = 0
        try:
            for name in os.listdir(folder):
                m = pattern.match(name)
                if m:
                    best = max(best, int(m.group(1)))
        except OSError:
            pass
        return best + 1


def _write_latent_file(path, samples, metadata):
    """A ComfyUI .latent file: what Save Latent writes and Load Latent reads (copy it to ComfyUI/input/ to load it)."""
    tensors = {"latent_tensor": samples.detach().cpu().contiguous(),
               "latent_format_version_0": torch.tensor([])}
    comfy.utils.save_torch_file(tensors, path, metadata=metadata)


def _write_conditioning_file(path, conditioning, metadata):
    """v0.4: a conditioning saved beside its latents (see conditioning_io.py). Returns what could not be stored."""
    return _cond_io.save_conditioning(path, conditioning, metadata)


def _shape_of(latent):
    try:
        return [int(x) for x in latent["samples"].shape]
    except Exception:
        return None


# ---------------------------------------------------------------------- #
# song stems (Audio Stem): Hybrid Demucs once per song, then read from disk
# ---------------------------------------------------------------------- #
def _stem_choice(kw):
    """The Audio Stem of this Run. A missing / unknown value (a workflow saved before the widget existed) = Song."""
    value = kw.get("Audio Stem", _stems.STEM_SONG)
    return value if value in _stems.STEM_CHOICES else _stems.STEM_SONG


def _stem_song_name(name):
    return _song_name({"Custom Audio File": name}) or "song"


def _ensure_song_stems(name, progress=None):
    """The four stems of a Custom Audio File on disk ({label: path}, info). Separates only when they are not there yet."""
    fid = _file_id(name)
    hit = _STEMS_READY.get(fid) if fid and fid[1] is not None else None
    if hit and all(os.path.isfile(p) for p in hit[0].values()):
        return hit[0], {**hit[1], "cached": True, "seconds": 0.0}
    source = folder_paths.get_annotated_filepath(name)
    paths, info = _stems.ensure_stems(
        source, _stem_song_name(name), folder_paths.get_output_directory(),
        get_audio=lambda: _load_custom_audio(name), progress=progress)
    if fid and fid[1] is not None:
        while len(_STEMS_READY) >= 8:
            _STEMS_READY.pop(next(iter(_STEMS_READY)))
        _STEMS_READY[fid] = (paths, info)
    return paths, info


def _load_audio_for_stem(name, stem):
    """Song = the Custom Audio File itself. Any other stem = that stem's WAV (made on first use, then cached on disk).
    The decoded stem is kept in RAM like the song (one entry); never mutate the result."""
    if not name or name == NONE_CHOICE:
        return None
    if stem == _stems.STEM_SONG:
        return _load_custom_audio(name)
    paths, _ = _ensure_song_stems(name)
    path = paths[stem]
    st = os.stat(path)
    key = ("stem", stem, os.path.abspath(path), int(st.st_mtime_ns), int(st.st_size))
    hit = _AUDIO_CACHE.get(key)
    if hit is not None:
        return hit
    audio = _decode_audio(path)
    if audio is None:
        raise RuntimeError(f"Could not read the {stem} stem: {path}")
    _AUDIO_CACHE.clear()
    if audio["waveform"].numel() * audio["waveform"].element_size() <= AUDIO_CACHE_MAX_BYTES:
        _AUDIO_CACHE[key] = audio
    return audio


# ---------------------------------------------------------------------- #
# video helpers
# ---------------------------------------------------------------------- #
def _resolve_video_path(video):
    if not video or video == NONE_CHOICE:
        raise ValueError("Use Video is ON but no video is selected. Upload one, or switch Use Video OFF.")
    return folder_paths.get_annotated_filepath(video)


def _minimax_frames(seconds):
    # MiniMax H3 frame count: 24 fps, minimum 5, padded up so frames % 17 == 5
    base = max(5, round(seconds * 24))
    return base + (5 - (base % 17)) % 17


def _require_av():
    try:
        import av
        return av
    except ImportError as e:
        raise RuntimeError(
            "PyAV ('av') is required to decode video/audio. It is normally installed with ComfyUI; "
            "otherwise run:  pip install av"
        ) from e


def _open_media(path):
    av = _require_av()
    try:
        return av.open(path)
    except Exception as e:
        raise RuntimeError(f"Could not open '{os.path.basename(path)}': {e}") from e


def _container_t0(container):
    st = container.start_time  # microseconds, or None
    return (st / 1_000_000.0) if st else 0.0


def _seek(container, stream, t_abs):
    """Seek back to the keyframe at/before t_abs (seconds). Silently stays at the start on failure."""
    try:
        container.seek(max(0, int(t_abs / float(stream.time_base))),
                       stream=stream, backward=True, any_frame=False)
    except Exception:
        pass


def _decode_video(path, force_rate, skip, cap):
    """
    Decode `cap` frames starting at output-frame `skip`.
    force_rate > 0 resamples to that fps (frames dropped/duplicated by timestamp),
    force_rate == 0 keeps the native rate.
    Returns (uint8 array [N,H,W,3] or None if past the end, info dict).
    """
    container = _open_media(path)
    try:
        if not container.streams.video:
            raise RuntimeError(f"'{os.path.basename(path)}' has no video stream.")
        stream = container.streams.video[0]
        try:
            stream.thread_type = "AUTO"
        except Exception:
            pass

        tb = float(stream.time_base)
        t0 = _container_t0(container)
        src_fps = float(stream.average_rate or stream.guessed_rate or 24)
        rate = float(force_rate) if force_rate and force_rate > 0 else src_fps

        if container.duration:
            duration = container.duration / 1_000_000.0
        elif stream.duration:
            duration = float(stream.duration * tb)
        else:
            duration = 0.0

        try:
            rotate = int(float(stream.metadata.get("rotate", 0))) % 360
        except Exception:
            rotate = 0

        def to_arr(frame):
            arr = frame.to_ndarray(format="rgb24")
            if rotate:
                arr = np.ascontiguousarray(np.rot90(arr, k=(rotate // 90) % 4 * -1))
            return arr

        end = skip + cap
        k = skip
        out = []
        prev = None
        prev_arr = None
        last_t = None
        EPS = 1e-6

        if skip > 0:
            _seek(container, stream, t0 + skip / rate)

        for frame in container.decode(stream):
            if frame.pts is not None:
                t = float(frame.pts * tb) - t0
            else:
                t = (last_t + 1.0 / src_fps) if last_t is not None else 0.0
            last_t = t

            if prev is None:
                prev = frame
                continue

            # prev stays "current" until this frame's timestamp
            while k < end and k / rate < t - EPS:
                if prev_arr is None:
                    prev_arr = to_arr(prev)
                out.append(prev_arr)
                k += 1
            prev, prev_arr = frame, None
            if k >= end:
                break

        # end of stream: the last frame lasts one source frame
        if prev is not None and k < end:
            end_t = (last_t if last_t is not None else 0.0) + 1.0 / src_fps
            while k < end and k / rate < end_t - EPS:
                if prev_arr is None:
                    prev_arr = to_arr(prev)
                out.append(prev_arr)
                k += 1

        info = {"rate": rate, "src_fps": src_fps, "duration": duration}
        return (np.stack(out) if out else None), info
    finally:
        container.close()


def _decode_audio(path, start=0.0, dur=None):
    """
    Decode audio from `start` seconds for `dur` seconds (dur=None -> to the end).
    Returns an AUDIO dict, or None when the file has no audio stream / nothing in that range.
    """
    av = _require_av()
    container = _open_media(path)
    try:
        if not container.streams.audio:
            return None
        stream = container.streams.audio[0]
        tb = float(stream.time_base)
        t0 = _container_t0(container)
        stop_t = None if dur is None else start + dur

        if start > 0:
            _seek(container, stream, t0 + max(0.0, start - 0.5))

        resampler = None
        sr = None
        chunks = []
        chunk_start = None
        n_samples = 0

        def take(frames):
            nonlocal n_samples
            if frames is None:
                return
            if not isinstance(frames, (list, tuple)):
                frames = [frames]
            for f in frames:
                arr = f.to_ndarray()  # fltp -> [channels, samples]
                chunks.append(arr)
                n_samples += arr.shape[1]

        done = False
        for frame in container.decode(stream):
            if resampler is None:
                sr = int(frame.sample_rate)
                resampler = av.AudioResampler(format="fltp", layout=frame.layout.name, rate=sr)
                chunk_start = (float(frame.pts * tb) - t0) if frame.pts is not None else start
            take(resampler.resample(frame))
            if stop_t is not None and chunk_start + n_samples / sr >= stop_t:
                done = True
                break
        if resampler is not None and not done:
            try:
                take(resampler.resample(None))
            except Exception:
                pass

        if not chunks:
            return None
        wave = np.concatenate(chunks, axis=1).astype(np.float32, copy=False)

        offset = int(round((start - chunk_start) * sr))
        if offset > 0:
            wave = wave[:, offset:]
        elif offset < 0:
            wave = np.pad(wave, ((0, 0), (-offset, 0)))
        if dur is not None:
            wave = wave[:, :int(round(dur * sr))]
        if wave.shape[1] == 0:
            return None
        return {"waveform": torch.from_numpy(np.ascontiguousarray(wave))[None], "sample_rate": sr}
    finally:
        container.close()


# ---------------------------------------------------------------------- #
# image helpers
# ---------------------------------------------------------------------- #
def _target_size(src_w, src_h, megapixels, multiple):
    """Width/height at ~megapixels, keeping the src aspect ratio."""
    multiple = max(1, int(multiple))
    aspect = src_w / src_h
    pixels = megapixels * 1_000_000.0
    h = math.sqrt(pixels / aspect)
    w = h * aspect
    w = max(multiple, int(round(w / multiple)) * multiple)
    h = max(multiple, int(round(h / multiple)) * multiple)
    return w, h


def _resize(img, w, h, method):
    """img: [1,H,W,3] float tensor -> [1,h,w,3]."""
    if img.shape[2] == w and img.shape[1] == h:
        return img
    if method == "lanczos":
        pil = Image.fromarray((img[0].clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8))
        pil = pil.resize((w, h), Image.LANCZOS)
        arr = np.array(pil).astype(np.float32) / 255.0
        return torch.from_numpy(arr)[None,]
    x = img.movedim(-1, 1)
    x = F.interpolate(x, size=(h, w), mode=method, align_corners=False, antialias=True)
    return x.clamp(0, 1).movedim(1, -1).contiguous()


def _fit_frame(img, w, h):
    """Center-crop img [1,H,W,3] to the aspect of w x h (nothing stretched), then resize to w x h."""
    ih, iw = int(img.shape[1]), int(img.shape[2])
    if iw / ih > w / h:
        ch, cw = ih, int(round(ih * w / h))
    else:
        cw, ch = iw, int(round(iw * h / w))
    cw, ch = max(1, min(cw, iw)), max(1, min(ch, ih))
    sx, sy = (iw - cw) // 2, (ih - ch) // 2
    return _resize(img[:, sy:sy + ch, sx:sx + cw, :], w, h, RESIZE_METHOD)


# ---------------------------------------------------------------------- #
# v2.5: how many segments does the selected video / audio hold? (panel, progress, quiet end)
# ---------------------------------------------------------------------- #
class _EndOfSegments(Exception):
    """Every segment of the video / audio has been made. A quiet stop, not an error."""

    def __init__(self, message, index=0):
        super().__init__(message)
        self.index = int(index)       # segments completed = the 0-based number of the segment that does not exist


_DURATION_CACHE = {}              # (kind, file id) -> seconds


def _probe_seconds(name, kind):
    """Length in seconds of a video / audio file of the input folder, from the container header (cached).
    kind = 'video' | 'audio'. None when it cannot be read."""
    fid = _file_id(name)
    if fid is None:
        return None
    key = (kind, fid)
    if fid[1] is not None and key in _DURATION_CACHE:
        return _DURATION_CACHE[key]
    seconds = None
    try:
        container = _open_media(folder_paths.get_annotated_filepath(name))
        try:
            if container.duration:
                seconds = container.duration / 1_000_000.0
            else:
                streams = container.streams.video if kind == "video" else container.streams.audio
                if streams and streams[0].duration:
                    seconds = float(streams[0].duration * streams[0].time_base)
        finally:
            container.close()
    except Exception as e:
        log.debug("could not probe %s: %s", name, e)
    if not seconds and kind == "audio":
        try:
            audio = _load_custom_audio(name)
            if audio is not None:
                seconds = audio["waveform"].shape[-1] / float(audio["sample_rate"])
        except Exception:
            seconds = None
    if seconds and fid[1] is not None:
        while len(_DURATION_CACHE) >= 16:
            _DURATION_CACHE.pop(next(iter(_DURATION_CACHE)))
        _DURATION_CACHE[key] = seconds
    return seconds or None


def _truthy(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _num(value, default, cast=float):
    try:
        return cast(float(value))
    except (TypeError, ValueError):
        return default


def _segment_plan(p):
    """How many segments the selection holds. `p` = the node's widget values (strings are fine).
    Mirrors what _load_media steps through:
      Use Video ON                                    -> the video frames
      Bypassed Audio Latent = Custom Audio + a file    -> the custom audio chunks
      Use Video OFF + Bypass Minimax + Audio From Video + a video -> the video soundtrack
    When several apply, the shortest one ends the run. total = None when nothing steps through a file."""
    use_video = _truthy(p.get("Use Video"), True)
    chunk_custom = _truthy(p.get("Bypassed Audio Latent"))
    bypass = True   # v2.8.4: Bypass Minimax is hardcoded
    frames = _minimax_frames(_num(p.get("duration"), 5.0))
    seg_seconds = frames / DEFAULT_FPS

    def usable(key):
        name = p.get(key)
        return bool(name) and name != NONE_CHOICE and folder_paths.exists_annotated_filepath(name)

    sources = []
    if use_video and usable("Video File"):
        length = _probe_seconds(p["Video File"], "video")
        if length:
            total_frames = int(round(length * DEFAULT_FPS))
            sources.append({"name": "video", "seconds": length,
                            "segments": max(0, math.ceil(total_frames / frames))})
    if chunk_custom and usable("Custom Audio File"):
        length = _probe_seconds(p["Custom Audio File"], "audio")
        if length:
            sources.append({"name": "custom audio", "seconds": length,
                            "segments": max(0, math.ceil(length / seg_seconds - 1e-9))})
    if not use_video and bypass and not chunk_custom and usable("Video File"):
        length = _probe_seconds(p["Video File"], "video")
        if length:
            sources.append({"name": "video soundtrack", "seconds": length,
                            "segments": max(0, math.ceil(length / seg_seconds - 1e-9))})

    limit = min(sources, key=lambda x: x["segments"]) if sources else None
    return {"total": limit["segments"] if limit else None, "limit": limit["name"] if limit else None,
            "sources": sources, "frames": int(frames), "seg_seconds": round(seg_seconds, 4)}


def _segment_info(params):
    """What the node's segment panel shows: the plan + the stored counter."""
    info = _segment_plan(params)
    index = _load_index()
    total = info["total"]
    info.update(index=index, furthest=max(_to_int(_load_state().get("furthest")), index),
                stepping=_truthy(params.get("Next Segment On Run")),
                running=_RUNNING > 0, finished=bool(total is not None and index >= total))
    return info


# ---------------------------------------------------------------------- #
# the node
# ---------------------------------------------------------------------- #
# ---------------------------------------------------------------------- #
# v2.3: Model Loader overrides + run-time model check
# ---------------------------------------------------------------------- #
def apply_model_overrides(kw, models):
    """Apply the dict of the optional "models" input to kw. Returns (from_manager, 'what changed' text).
    Only whitelisted keys count; an empty / "None" file name keeps the hardcoded default."""
    if models is None:
        return False, ""
    if not isinstance(models, dict):
        raise RuntimeError("[IronLeo78 MTV] the 'models' input must come from the "
                           "IronLeo78 MTV Model Loader node.")
    changed = []
    for key in MODEL_FILE_KEYS:
        value = models.get(key)
        if isinstance(value, str) and value.strip() and value != NONE_CHOICE:
            if value != kw.get(key):
                changed.append(f"{key.replace('_name', '')}={value}")
            kw[key] = value
    for key in MODEL_STEP_KEYS:
        if models.get(key) is None:
            continue
        try:
            n = int(models[key])
        except (TypeError, ValueError):
            raise RuntimeError(f"[IronLeo78 MTV] Model Loader: {key} must be a whole number.")
        if not MIN_STEPS <= n <= MAX_STEPS:
            raise RuntimeError(f"[IronLeo78 MTV] Model Loader: {key} must be between "
                               f"{MIN_STEPS} and {MAX_STEPS}.")
        if n != kw.get(key):
            changed.append(f"{key}={n}")
        kw[key] = n
    if models.get("custom_lora_enabled") is not None:      # v2.8.6: custom LoRA toggle / file / strength
        enabled = _truthy(models["custom_lora_enabled"])
        if enabled != kw.get("custom_lora_enabled"):
            changed.append(f"custom_lora={'ON' if enabled else 'OFF'}")
        kw["custom_lora_enabled"] = enabled
    lora = models.get("custom_lora_name")
    if isinstance(lora, str) and lora.strip() and lora != NONE_CHOICE:
        if lora != kw.get("custom_lora_name"):
            changed.append(f"custom_lora_name={lora}")
        kw["custom_lora_name"] = lora
    if models.get("custom_lora_strength") is not None:
        try:
            strength = float(models["custom_lora_strength"])
        except (TypeError, ValueError):
            raise RuntimeError("[IronLeo78 MTV] Model Loader: custom_lora_strength must be a number.")
        if not -100.0 <= strength <= 100.0:
            raise RuntimeError("[IronLeo78 MTV] Model Loader: custom_lora_strength must be between -100 and 100.")
        if strength != kw.get("custom_lora_strength"):
            changed.append(f"custom_lora_strength={strength:g}")
        kw["custom_lora_strength"] = strength
    if models.get("noise_seed") is not None:      # v2.8.5: the seed lives on the Model Loader
        try:
            seed = int(models["noise_seed"])
        except (TypeError, ValueError):
            raise RuntimeError("[IronLeo78 MTV] Model Loader: noise_seed must be a whole number.")
        if not 0 <= seed <= MAX_SEED:
            raise RuntimeError("[IronLeo78 MTV] Model Loader: noise_seed is out of range.")
        if seed != kw.get("noise_seed"):
            changed.append(f"noise_seed={seed}")
        kw["noise_seed"] = seed
    return True, ", ".join(changed) if changed else "nothing changed from the defaults"


def _check_models(kw):
    """Friendly error (before any model is loaded or a segment is used) for a missing model file."""
    source = "Model Loader" if kw.get("models_source") else "hardcoded"
    wanted = [("unet_name", folder_paths.get_filename_list("diffusion_models")),
              ("qwen_vl_name", folder_paths.get_filename_list("text_encoders")),
              ("video_vae_name", _vae_options()),
              ("audio_vae_name", _vae_options())]
    if kw.get("Turbo"):
        wanted.append(("turbo_lora_name", folder_paths.get_filename_list("loras")))
    if kw.get("custom_lora_enabled"):      # v2.8.6: only checked when the custom LoRA is switched ON
        name = kw.get("custom_lora_name")
        if not name or name == NONE_LORA or name not in folder_paths.get_filename_list("loras"):
            raise RuntimeError(f"[IronLeo78 MTV] Custom LoRA ({source}) not found: put "
                               f"{name if name and name != NONE_LORA else DEFAULT_CUSTOM_LORA} in ComfyUI/models/loras/ "
                               f"(or switch the custom LoRA OFF on the Model Loader)")
    for key, options in wanted:
        label, folder = MODEL_FILE_KEYS[key]
        name = kw[key]
        if name not in options:
            where = f"ComfyUI/models/{folder}/"
            extra = " (or switch Turbo OFF)" if key == "turbo_lora_name" else ""
            raise RuntimeError(f"[IronLeo78 MTV] {label} ({source}) not found: "
                               f"put {name} in {where}{extra}")


class IronLeo78_MTV:
    SLOTS = 3

    def __init__(self):
        pass

    # ------------------------------------------------------------------ #
    @classmethod
    def INPUT_TYPES(cls):
        img_files = _image_files()
        vid_files = _video_files()

        r = {
            # ===== turbo (the Turbo LoRA itself is hardcoded) =====
            "Turbo": ("BOOLEAN", {
                "default": True, "label_on": "ON", "label_off": "OFF",
                "tooltip": "ON: Turbo LoRA applied, 4 steps. OFF: no Turbo LoRA, 25 steps "
                           "(BasicGuider, no CFG, like the official r2v template).",
            }),
            # ===== video / audio =====
            "Use Video": ("BOOLEAN", {
                "default": False, "label_on": "ON", "label_off": "OFF",
                "tooltip": "ON = v2v: the video is loaded and is the reference for megapixels/width/height. "
                           "OFF = i2v: no frames are loaded, Picture1 is the reference. "
                           "Exception: with Bypassed Audio Latent = "
                           "Audio From Video, a selected Video File still supplies its soundtrack "
                           "(audio only). Set Video File to None for silence.",
            }),
            "Video File": ([NONE_CHOICE] + vid_files,
                           {"default": NONE_CHOICE, "video_upload": True}),
            "Custom Audio File": (_audio_files(), {"audio_upload": True}),
            "Audio Stem": (list(_stems.STEM_CHOICES), {
                "default": _stems.STEM_SONG,
                "tooltip": "Which part of the Custom Audio File is used. Song = the whole mix. "
                           "Vocals / Guitars / Drums / Bass = only that stem (Guitars is Demucs' 'other' stem: "
                           "guitars + keys + synths). The first time a stem is chosen for a NEW song, Hybrid Demucs "
                           "separates all four (about 13 s for a 2 minute song) and saves them to "
                           "output/<Song>/stems/<Song>_<Stem>.wav. After that every Run just reads the file. "
                           "Needs a Custom Audio File.",
            }),
        }
        r["megapixels"] = ("FLOAT", {
            "default": DEFAULT_MEGAPIXELS, "min": 0.1, "max": 1.0, "step": 0.1,
            "tooltip": "Target size. Use Video ON: the video sets the aspect ratio and width/height. "
                       "Use Video OFF: Picture1 does. Pictures 2-3 always keep their own aspect ratio.",
        })
        r["duration"] = ("FLOAT", {
            "default": DEFAULT_DURATION, "min": 0.0, "max": 10000.0, "step": 0.01,
            "tooltip": "Duration in seconds. Also sets the video segment length when Use Video is ON. "
                       "durationS = this value unchanged; durationF = Minimax frame count.",
        })
        r["Next Segment On Run"] = ("BOOLEAN", {
            "default": False, "label_on": "ON", "label_off": "OFF",
            "tooltip": "ON: every Run moves on to the next segment (video frames, and/or the custom audio "
                       "chunk when Bypassed Audio Latent = Custom Audio). OFF: always the first segment.",
        })
        # ===== MiniMax H3 reference-to-video =====
        r["prompt"] = ("STRING", {
            "multiline": True, "dynamic_prompts": True, "default": "",
            "tooltip": "Prompt. Refer to references as <Picture i> / <Video 1> / <Audio j>. "
                       "Numbers count only what is actually sent: an empty picture slot is skipped "
                       "(Picture1 + Picture3 filled = <Picture 1> and <Picture 2>). "
                       "Audio order: video soundtrack first (if any), then custom audio. "
                       "The status box lists the exact mapping.",
        })

        # ===== sampling =====
        # ===== audio latent =====
        r["Bypassed Audio Latent"] = ("BOOLEAN", {
            "default": False, "label_off": "Audio From Video", "label_on": "Custom Audio",
            "tooltip": "Which audio is used (and stepped through). "
                       "This audio is encoded into the audio latent (Bypass Minimax is always on). "
                       "Audio From Video = the video soundtrack (silence if none). "
                       "Custom Audio = the Custom Audio File (silence if none). "
                       "It also decides which audio Next Segment On Run moves through: "
                       "Custom Audio = the song is cut into chunks as long as the real video "
                       "segment (frames / fps: duration 5 s = 124 frames = 5.17 s), one chunk per Run "
                       "(works with Use Video OFF too); the segment counter at the top of the node "
                       "decides which chunk is next (Jump). "
                       "Audio From Video = the video soundtrack follows its frames, "
                       "the custom audio is then used whole.",
        })
        # ===== save latent (v0.6). Takes the place of the old "Latent Upscale" widget =====
        r["Save Latent"] = ("BOOLEAN", {
            "default": DEFAULT_SAVE_LATENT, "label_on": "ON", "label_off": "OFF",
            "tooltip": "ON: besides the clip, the sampled latent (video + audio .latent files) and the conditioning "
                       "(.conditioning: prompt + pictures, no guide) are saved in the song folder, next to the clip and "
                       "sharing its name, so you can refine / upscale it later in another workflow. "
                       "OFF (default): only the clip is saved.",
        })
        # ===== guide (v2.0). Appended LAST so saved workflows keep their widget order =====
        r["Guide"] = ("BOOLEAN", {
            "default": True, "label_on": "ON", "label_off": "OFF",
            "tooltip": "Only works with Next Segment On Run = ON. ON: the last frame of the previous run "
                       "is used as a guide for the first frame of this segment, so the clips continue "
                       "each other. The first segment (or a run with no saved frame from the segment "
                       "before) runs without a guide. OFF: no guide.",
        })
        # ===== pictures (v2.8.2): the LAST widgets, so the pickers sit right above the thumbnail row =====
        for i in range(1, cls.SLOTS + 1):
            r[f"picture_{i}"] = ([NONE_CHOICE] + img_files, {"default": NONE_CHOICE, "image_upload": True})

        # v2.3: optional link-only input (no widget, so saved widget values never shift).
        optional = {
            "models": (MODELS_TYPE, {
                "tooltip": "Optional. Plug in the IronLeo78 MTV Model Loader to replace "
                           "the hardcoded diffusion model, Turbo LoRA, text encoder, VAEs and "
                           "step counts. Nothing connected = the hardcoded defaults.",
            }),
        }

        return {"required": r, "optional": optional, "hidden": {"unique_id": "UNIQUE_ID",
                                          "workflow_prompt": "PROMPT",
                                          "extra_pnginfo": "EXTRA_PNGINFO"}}

    RETURN_TYPES = ()          # v2.4: no output sockets (the status is shown inside the node)
    RETURN_NAMES = ()
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "IronLeo78/MTV"
    DESCRIPTION = (
        "Minimax MTV: loader + MiniMax H3 reference-to-video + sampling + decode + "
        "Create Video + Save Video, in one node.\n"
        "Models: Turbo + custom LoRA; diffusion model, attention backend, Qwen3-VL text encoder "
        "and the 2 VAEs are hardcoded (v2.3: the optional 'models' input takes a Model Loader node "
        "that can replace them, and the step counts).\n"
        "Media: video (segment by segment) + up to three images + custom audio (whole song, or only its Vocals / Guitars / Drums / Bass: "
        "Audio Stem; the stems are separated once per song and saved to output/<Song>/stems/).\n"
        "Sampling is hardcoded (BasicGuider, res_multistep, simple, denoise 1.0); "
        "Turbo ON = 4 steps, Turbo OFF = 25 steps. The noise seed (default 1978) is set on the Model Loader node.\n"
        "Audio Latent: always Bypass Minimax (hardcoded): the audio you give "
        "(from the video or custom) is kept as is, the model never generates audio.\n"
        "Save Latent ON: the sampled latent (video + audio .latent files) and its conditioning (.conditioning) are "
        "saved next to the clip for a later refine / upscale in another workflow. OFF (default): only the clip is saved.\n"
        "Files are tagged <Song>_seg<segment>_A (Song = the Custom Audio File name, if one is selected) "
        "and logged in a manifest CSV.\n"
        "No outputs, no saved-video preview (the live latent preview stays): the clips are saved to the output folder and the run report is shown in the node.\n"
        "v2.5: segment panel (count / next / Reset), progress in the report, a quiet stop after the last segment, "
        "and a <clip>.json sidecar with the full prompt next to every clip.\n"
        "v2.6: jump to any segment (number field + Go / Latest in the panel), and the Guide can read "
        "the previous segment's last frame back from its clip.\n"
        "v2.8: Scene 2 / prompt_2 / Picture4-6 are gone (one clip per Run).\n"
        "by IronLeo78"
    )

    # ================================================================== #
    # MODEL stage
    # ================================================================== #
    @staticmethod
    def _load_unet(unet_name, weight_dtype):
        model_options = {}
        if weight_dtype == "fp8_e4m3fn":
            model_options["dtype"] = torch.float8_e4m3fn
        elif weight_dtype == "fp8_e4m3fn_fast":
            model_options["dtype"] = torch.float8_e4m3fn
            model_options["fp8_matrix_mult"] = True
        elif weight_dtype == "fp8_e5m2":
            model_options["dtype"] = torch.float8_e5m2

        path = folder_paths.get_full_path_or_raise("diffusion_models", unet_name)
        if hasattr(comfy.sd, "load_diffusion_model"):
            return comfy.sd.load_diffusion_model(path, model_options=model_options)
        return comfy.sd.load_unet(path)  # older ComfyUI

    @staticmethod
    def _apply_lora(model, lora_name, strength, label):
        if lora_name == NONE_LORA or strength == 0:
            return model
        path = folder_paths.get_full_path_or_raise("loras", lora_name)

        lora = _LORA_CACHE.get(path)
        if lora is None:
            _LORA_CACHE.clear()
            lora = comfy.utils.load_torch_file(path, safe_load=True)
            _LORA_CACHE[path] = lora

        model, _ = comfy.sd.load_lora_for_models(model, None, lora, strength, 0)
        log.info("[%s] applied %s @ %.2f", label, lora_name, strength)
        return model

    @staticmethod
    def _apply_attention(model, attention):
        try:
            cls = comfy_nodes.NODE_CLASS_MAPPINGS[CORE_ATTN_NODE]
        except Exception:
            log.warning("Core node '%s' not found; skipping attention step.", CORE_ATTN_NODE)
            return model
        try:
            fn = getattr(cls(), cls.FUNCTION)
            return _first_output(fn(model=model, attention=attention))
        except Exception as e:
            log.warning("Attention backend step failed (%s); using model as-is.", e)
            return model

    def _build_model(self, kw):
        model = _stage("diffusion model", self._load_unet, kw["unet_name"], kw["weight_dtype"])
        if kw["Turbo"]:
            model = _stage("turbo lora", self._apply_lora, model,
                           kw["turbo_lora_name"], kw["turbo_lora_strength"], "Turbo")
        if kw["custom_lora_enabled"]:
            model = _stage("lora", self._apply_lora, model,
                           kw["custom_lora_name"], kw["custom_lora_strength"], "Custom LoRA")
        if kw["attention_enabled"]:
            model = self._apply_attention(model, kw["attention"])  # optional: never fatal
        return model

    # ================================================================== #
    # CLIP stage
    # ================================================================== #
    @staticmethod
    def _load_clip(clip_name, clip_type_name, device, label):
        clip_type = getattr(comfy.sd.CLIPType, clip_type_name.upper(),
                            comfy.sd.CLIPType.STABLE_DIFFUSION)
        model_options = {}
        if device == "cpu":
            model_options["load_device"] = model_options["offload_device"] = torch.device("cpu")

        path = folder_paths.get_full_path_or_raise("text_encoders", clip_name)
        log.info("[%s] loading %s (type=%s, device=%s)", label, clip_name, clip_type_name, device)
        return comfy.sd.load_clip(
            ckpt_paths=[path],
            embedding_directory=folder_paths.get_folder_paths("embeddings"),
            clip_type=clip_type,
            model_options=model_options,
        )

    # ================================================================== #
    # VAE stage
    # ================================================================== #
    @staticmethod
    def _load_vae_direct(vae_name):
        path = folder_paths.get_full_path_or_raise("vae", vae_name)
        sd, metadata = comfy.utils.load_torch_file(path, return_metadata=True)
        vae = comfy.sd.VAE(sd=sd, metadata=metadata)
        vae.throw_exception_if_invalid()
        return vae

    def _load_vae(self, vae_name, label):
        log.info("[%s] loading %s", label, vae_name)
        try:
            cls = comfy_nodes.NODE_CLASS_MAPPINGS[CORE_VAE_NODE]
            return _first_output(getattr(cls(), cls.FUNCTION)(vae_name))
        except KeyError:
            log.warning("Core '%s' not found; using direct loader.", CORE_VAE_NODE)
        return self._load_vae_direct(vae_name)

    # ------------------------------------------------------------------ #
    def _load_models(self, kw, uid):
        turbo_key = (_stamp("loras", kw["turbo_lora_name"]), kw["turbo_lora_strength"]) if kw["Turbo"] else None
        custom_key = ((_stamp("loras", kw["custom_lora_name"]), kw["custom_lora_strength"])
                      if kw["custom_lora_enabled"] else None)

        model_key = (_stamp("diffusion_models", kw["unet_name"]), kw["weight_dtype"],
                     turbo_key, custom_key,
                     (kw["attention"] if kw["attention_enabled"] else None))
        model = _cached(uid, "model", model_key, lambda: self._build_model(kw))

        def clip(tag, label, stage):
            name, ctype, dev = kw[f"{tag}_name"], kw[f"{tag}_type"], kw[f"{tag}_device"]
            key = (_stamp("text_encoders", name), ctype, dev)
            return _cached(uid, stage, key,
                           lambda: _stage(stage, self._load_clip, name, ctype, dev, label))

        def vae(tag, label, stage):
            name = kw[f"{tag}_name"]
            key = _stamp("vae", name)
            return _cached(uid, stage, key, lambda: _stage(stage, self._load_vae, name, label))

        return (model,
                clip("qwen_vl", "Qwen-VL", "clip qwen-vl"),
                vae("video_vae", "Video VAE", "video vae"),
                vae("audio_vae", "Audio VAE", "audio vae"))

    # ================================================================== #
    # MEDIA stage (video / audio / pictures) - unchanged logic
    # ================================================================== #
    @staticmethod
    def _load_one_image(name):
        path = folder_paths.get_annotated_filepath(name)
        img = Image.open(path)
        try:
            img.seek(0)
        except Exception:
            pass
        img = ImageOps.exif_transpose(img)
        if img.mode == "I":
            img = img.point(lambda px: px * (1 / 255))
        img = img.convert("RGB")
        arr = np.array(img).astype(np.float32) / 255.0
        return torch.from_numpy(arr)[None,]

    def _load_video(self, kw, frames, seconds, mp, index):
        """Returns (images, audio, w, h, filename, status).
        index = segment number (0 when Next Segment On Run is OFF; the segment counter sets it)."""
        video = _resolve_video_path(kw.get("Video File"))
        filename = os.path.splitext(os.path.basename(video))[0]

        span = frames
        skip = index * span

        arr, info = _decode_video(video, DEFAULT_FPS, skip, frames)
        if arr is None:
            if index > 0:      # v2.5: every segment is done: stop quietly (the Run reports it, no error)
                raise _EndOfSegments(f"End of video: segment {index + 1} would start at frame {skip}, "
                                     f"past the last frame.", index)
            raise RuntimeError("No frames could be loaded from this video.")

        images = torch.from_numpy(arr).float().div_(255.0)
        rate = info["rate"]
        audio = _decode_audio(video, skip / rate, images.shape[0] / rate)  # None = no sound

        orig_height = int(images.shape[1])
        orig_width = int(images.shape[2])
        r = orig_width / orig_height

        # target size at the megapixel budget, multiples of 32
        tw = math.sqrt(mp * 1_000_000 * r)
        th = tw / r
        target_width = max(32, int(round(tw / 32.0)) * 32)
        target_height = max(32, int(round(th / 32.0)) * 32)

        # center-crop to the final aspect so nothing is stretched
        final_r = target_width / target_height
        if orig_width / orig_height > final_r:
            crop_h = orig_height
            crop_w = int(round(orig_height * final_r))
        else:
            crop_w = orig_width
            crop_h = int(round(orig_width / final_r))
        crop_w = max(1, min(crop_w, orig_width))
        crop_h = max(1, min(crop_h, orig_height))
        sx = (orig_width - crop_w) // 2
        sy = (orig_height - crop_h) // 2
        images = images[:, sy:sy + crop_h, sx:sx + crop_w, :]

        if images.shape[2] != target_width or images.shape[1] != target_height:
            images = images.permute(0, 3, 1, 2)
            images = F.interpolate(images, size=(target_height, target_width),
                                   mode="bicubic", align_corners=False)
            images = torch.clamp(images, 0.0, 1.0)
            images = images.permute(0, 2, 3, 1)

        total = int(round(info["duration"] * rate)) if info["duration"] > 0 else 0
        end = skip + span - 1
        if total > 0:
            end = min(end, total - 1)

        h, w = int(images.shape[1]), int(images.shape[2])
        status = (f"Video ON | segment {index} | frames {skip} to {end} | next: {index + 1}"
                  f" | resolution: {w}x{h} | total frames: {total}\n{CREDIT}")
        return images, audio, w, h, filename, status

    @staticmethod
    def _load_video_audio(path, kw, frames, seg_seconds, out_fps, index):
        """Use Video OFF but a Video File is selected: only its soundtrack is read.
        Same position as the frames would have (segment * frames, at out_fps).
        Returns (audio or None, status line)."""
        name = os.path.basename(path)
        container = _open_media(path)
        try:
            has_audio = bool(container.streams.audio)
        finally:
            container.close()
        if not has_audio:
            return None, f"video audio only: '{name}' has no audio stream (silence)"
        start_s = (index * frames) / out_fps
        audio = _decode_audio(path, start_s, seg_seconds)
        if audio is None:
            msg = f"End of video audio: segment {index + 1} would start at {start_s:.2f}s, past the end of '{name}'."
            if index > 0:      # v2.5: quiet stop
                raise _EndOfSegments(msg, index)
            raise RuntimeError(msg)
        sr = float(audio["sample_rate"])
        got = audio["waveform"].shape[-1] / sr
        note = (f"video audio only (Use Video OFF): {name} | segment {index} | "
                f"{start_s:.2f}s to {start_s + got:.2f}s | next: {index + 1}")
        missing = int(round(seg_seconds * sr)) - audio["waveform"].shape[-1]
        if missing > 0:
            audio = {**audio, "waveform": F.pad(audio["waveform"], (0, missing))}
            note += f" | end of audio: padded with {missing / sr:.2f}s of silence"
        return audio, note

    # ------------------------------------------------------------------ #
    @staticmethod
    def _prepare_stems(kw):
        """Audio Stem other than Song: make sure the song's stems are on disk. Returns the line for the status box
        ('' when no stem is used). Runs before the models are loaded so Demucs gets the GPU memory to itself."""
        stem = _stem_choice(kw)
        name = kw.get("Custom Audio File")
        if stem == _stems.STEM_SONG or not name or name == NONE_CHOICE:
            return ""
        bar = None
        try:
            bar = comfy.utils.ProgressBar(100)
        except Exception:
            pass

        def progress(done, total):
            if bar is not None:
                with contextlib.suppress(Exception):
                    bar.update_absolute(int(100 * done / max(1, total)), 100)

        _, info = _ensure_song_stems(name, progress)
        where = os.path.relpath(info["folder"], folder_paths.get_output_directory()).replace(os.sep, "/")
        if info["cached"]:
            return f"audio stem: {stem} (read from the saved stems in output/{where})"
        return (f"audio stem: {stem} | all four stems separated with Hybrid Demucs in {info['seconds']:.1f} s "
                f"and saved to output/{where} (next Runs read them from disk)")

    def _load_media(self, kw):
        use_video = bool(kw.get("Use Video", True))
        mp = float(kw["megapixels"])
        seconds = float(kw["duration"])
        frames = _minimax_frames(seconds)
        # The video is generated with a PADDED frame count (5 s -> 124 frames = 5.17 s), so the
        # audio chunks must use the REAL segment length, not the raw `duration`, or the audio
        # is cut short and every following chunk starts early.
        out_fps = DEFAULT_FPS
        seg_seconds = frames / out_fps

        # segment number, shared by the video frames and the custom audio chunks
        chunk_custom = bool(kw["Bypassed Audio Latent"])  # True = chunk the Custom Audio
        index = _load_index() if kw["Next Segment On Run"] else 0
        # Always advance (even when OFF) so the first ON run continues at segment 1.
        # Saved by run() only after the whole node succeeded (no burnt segment on error).
        stem = _stem_choice(kw)
        custom_full = _load_audio_for_stem(kw.get("Custom Audio File"), stem)  # None if not selected

        # Use Video OFF only drops the images: with Bypass Minimax (always on) and
        # Bypassed Audio Latent = Audio From Video, a selected Video File still supplies its
        # soundtrack (audio only, no frames are decoded, Picture1 still sets the size).
        audio_only_path = None
        if not use_video and not chunk_custom:
            sel = kw.get("Video File")
            if sel and sel != NONE_CHOICE and folder_paths.exists_annotated_filepath(sel):
                audio_only_path = _resolve_video_path(sel)

        if use_video or (chunk_custom and custom_full is not None) or audio_only_path or kw.get("Guide", False):
            self._pending_index = index + 1

        custom_audio, audio_note = custom_full, ""
        custom_id = _file_id(kw.get("Custom Audio File")) if custom_full is not None else None
        if custom_id is not None and stem != _stems.STEM_SONG:
            custom_id = custom_id + (stem,)       # the conditioning / audio-latent caches must tell the stems apart
        cond_audio2 = None
        cond_audio1 = None
        cond_video = None
        if custom_full is not None and chunk_custom:
            c_start = index * seg_seconds
            custom_audio = _slice_audio(custom_full, c_start, seg_seconds)
            if custom_audio is None:
                total_s = custom_full["waveform"].shape[-1] / float(custom_full["sample_rate"])
                msg = (f"End of custom audio: segment {index + 1} would start at {c_start:.2f}s, "
                       f"past its end ({total_s:.2f}s).")
                if index > 0:      # v2.5: quiet stop
                    raise _EndOfSegments(msg, index)
                raise RuntimeError(msg)
            sr = float(custom_audio["sample_rate"])
            got = custom_audio["waveform"].shape[-1] / sr
            cond_audio2 = ("a2c", custom_id, round(float(c_start), 4), round(float(seg_seconds), 6))
            audio_note = (f"custom audio chunk: segment {index} | {c_start:.2f}s to {c_start + got:.2f}s"
                          f" | segment {seg_seconds:.3f}s = {frames} frames @ {out_fps:g} fps | next: {index + 1}")
            missing = int(round(seg_seconds * sr)) - custom_audio["waveform"].shape[-1]
            if missing > 0:
                # last chunk: pad with silence so it is as long as the video (audio latent stays aligned)
                padded = F.pad(custom_audio["waveform"], (0, missing))
                custom_audio = {**custom_audio, "waveform": padded}
                audio_note += f" | end of audio: padded with {missing / sr:.2f}s of silence"
        elif custom_full is not None:
            cond_audio2 = ("a2w", custom_id)
            audio_note = "custom audio: whole file (Bypassed Audio Latent = Audio From Video)"

        # 1) load pictures at native size
        raw = []
        for i in range(1, self.SLOTS + 1):
            name = kw[f"picture_{i}"]
            if name == NONE_CHOICE:
                raw.append(None)
                continue
            try:
                raw.append(self._load_one_image(name))
            except Exception as e:
                log.error("[Picture%d] failed to load %s: %s", i, name, e)
                raise RuntimeError(
                    f"[IronLeo78 MTV] Picture{i} ('{name}') failed: {e}"
                ) from e

        # 2) every picture -> megapixel target, keeping its OWN aspect ratio
        sizes = [None if img is None else _target_size(img.shape[2], img.shape[1], mp, DIVISIBLE_BY)
                 for img in raw]

        # 3) reference size + video
        if use_video:
            video1, audio1, w, h, filename, status = self._load_video(
                kw, frames, seconds, mp, index)
            v_fid = _file_id(kw.get("Video File"))
            v_skip = index * int(frames)
            cond_video = ("v", v_fid, v_skip, int(frames), round(mp, 4))
            cond_audio1 = ("a1v", v_fid, v_skip, int(frames))
        else:
            if sizes[0] is not None:
                w, h = sizes[0]
            else:
                w, h = _target_size(1, 1, mp, DIVISIBLE_BY)
            video1, audio1 = None, None
            video_audio_note = ""
            if audio_only_path:
                audio1, video_audio_note = self._load_video_audio(
                    audio_only_path, kw, frames, seg_seconds, out_fps, index)
                cond_audio1 = ("a1o", _file_id(kw.get("Video File")),
                               (index * int(frames)) / out_fps,
                               round(float(seg_seconds), 6))
            p1 = kw.get("picture_1", NONE_CHOICE)
            filename = os.path.splitext(os.path.basename(p1))[0] if p1 != NONE_CHOICE else ""
            status = f"Video OFF | reference: Picture1 | filename: {filename} | resolution: {w}x{h}\n{CREDIT}"
            if video_audio_note:
                status += "\n" + video_audio_note

        if audio_note:
            status += "\n" + audio_note

        # position of this segment in the song / video (seconds), for the manifest
        if custom_full is not None and chunk_custom:
            timeline = index * seg_seconds
        elif use_video or audio_only_path:
            timeline = (index * frames) / out_fps
        else:
            timeline = index * seg_seconds if self._pending_index is not None else 0.0

        # 4) resize pictures (empty slots stay None: nothing is sent for them)
        pictures = [None if img is None else _resize(img, size[0], size[1], RESIZE_METHOD)
                    for img, size in zip(raw, sizes)]
        pic_ids = [None if img is None else ("p", _file_id(kw[f"picture_{i}"]), size)
                   for i, (img, size) in enumerate(zip(raw, sizes), start=1)]

        return {"video": video1, "audio1": audio1, "audio2": custom_audio,
                "pictures": pictures, "width": w, "height": h,
                "seconds": seconds, "seg_seconds": seg_seconds, "frames": int(frames),
                "filename": filename, "status": status, "index": index,
                "audio_stem": stem if custom_full is not None else "",
                "timeline_start": float(timeline),
                # what the references CONTAIN (for the conditioning cache): file ids + the slice taken
                "cond_id": {"video": cond_video, "audio1": cond_audio1, "audio2": cond_audio2,
                            "pics": pic_ids}}

    # ================================================================== #
    # REFERENCE stage: ComfyUI's own MiniMax H3 Reference-to-Video logic,
    # fed with the hardcoded references (no placeholders, nothing extra).
    # ================================================================== #
    @staticmethod
    def _outputs(res):
        if isinstance(res, tuple):
            return res
        for attr in ("result", "args"):
            val = getattr(res, attr, None)
            if val:
                return tuple(val)
        raise RuntimeError("unexpected result from MiniMax H3 Reference to Video")

    @staticmethod
    def _usable_audio(audio, label, notes):
        if audio is None:
            return None
        wave = audio["waveform"]
        if wave.shape[-1] / float(audio["sample_rate"]) < MIN_REF_AUDIO_SECONDS:
            notes.append(f"{label} skipped (shorter than {MIN_REF_AUDIO_SECONDS}s)")
            return None
        max_len = int(MAX_REF_AUDIO_SECONDS * float(audio["sample_rate"]))
        if wave.shape[-1] > max_len:
            audio = {**audio, "waveform": wave[..., :max_len]}
            notes.append(f"{label} trimmed to its first {MAX_REF_AUDIO_SECONDS:g}s")
        return audio

    def _build_conditioning(self, clip, vae_video, vae_audio, kw, media):
        try:
            from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo
        except Exception as e:
            raise RuntimeError(
                "ComfyUI's MiniMax H3 nodes (comfy_extras/nodes_minimax_h3.py) are not available. "
                "Update ComfyUI.") from e

        notes = []          # what was left out and why
        tags = []           # <Picture i> / <Video k> / <Audio j> -> source

        ref_images = {}
        for slot, img in enumerate(media["pictures"], start=1):
            if img is None:
                continue
            ref_images[f"ref_image_{len(ref_images)}"] = img
            tags.append(f"<Picture {len(ref_images)}>=Picture{slot}")

        ref_videos = {}
        if media["video"] is not None:
            ref_videos["ref_video_0"] = media["video"]
            tags.append("<Video 1>=video")

        ref_audios = {}
        for label, source, audio in (("Video soundtrack", "video soundtrack", media["audio1"]),
                                     ("Custom audio", "custom audio", media["audio2"])):
            audio = self._usable_audio(audio, label, notes)
            if audio is not None:
                ref_audios[f"ref_audio_{len(ref_audios)}"] = audio
                tags.append(f"<Audio {len(ref_audios)}>={source}")

        try:
            res = MiniMaxH3ReferenceToVideo.execute(
                clip=clip, vae=vae_video, audio_vae=vae_audio,
                prompt=kw["prompt"], width=media["width"], height=media["height"],
                length=media["frames"], ref_image_size=kw["ref_image_size"],
                ref_images=ref_images or None, ref_videos=ref_videos or None,
                ref_video_audios=None, ref_audios=ref_audios or None)
        except Exception as e:
            raise RuntimeError(f"{e} | sent: {', '.join(tags) if tags else 'no references'}"
                               f" | resolution {media['width']}x{media['height']},"
                               f" {media['frames']} frames") from e
        positive, latent = self._outputs(res)[:2]

        line = "references: " + (", ".join(tags) if tags else "none")
        if notes:
            line += " | " + "; ".join(notes)
        return positive, latent, line

    def _conditioning_cached(self, clip, vae_video, vae_audio, kw, media, models_key):
        """_build_conditioning with a content-addressed cache: same encoder / VAEs, prompt, size, frame count
        and the same reference CONTENT (file ids + the video / audio slice) = the encode is skipped."""
        cid = media["cond_id"]
        key = ("cond", models_key, str(kw["prompt"]), int(media["width"]), int(media["height"]),
               int(media["frames"]), kw["ref_image_size"],
               cid["video"], cid["audio1"], cid["audio2"], tuple(cid["pics"]))
        hit = _lru_get(_COND_CACHE, key)
        if hit is not None:
            positive, latent, line = hit
            return _clone_cond(positive), dict(latent), line + " | conditioning: cached"
        positive, latent, line = self._build_conditioning(clip, vae_video, vae_audio, kw, media)
        _lru_put(_COND_CACHE, key, (positive, latent, line))
        return _clone_cond(positive), dict(latent), line

    # ================================================================== #
    # GUIDE stage (v2.0): the previous run's last frame -> MiniMax H3 Add Guide
    # ================================================================== #
    def _apply_guide(self, positive, latent, vae_video, media, notes):
        index = int(media["index"])
        frame, why = _load_last_frame(index, media.get("song"))
        if frame is None:
            return positive, latent, f"guide: ON, not used ({why})"
        frame = _fit_frame(frame, int(media["width"]), int(media["height"]))
        outs, _ = _core("MiniMaxH3AddGuide",
                        {"positive": positive, "latent": latent, "vae": vae_video,
                         "image": frame, "frame_idx": GUIDE_FRAME_IDX},
                        strict=("positive", "latent", "image"), notes=notes)
        positive = outs[0]
        if len(outs) > 1 and isinstance(outs[-1], dict) and "samples" in outs[-1]:
            latent = outs[-1]       # in case this ComfyUI version also returns the latent
        return (positive, latent, f"guide: ON | last frame of segment {index - 1} -> frame {GUIDE_FRAME_IDX}"
                + (f" ({why})" if why else ""))

    # ================================================================== #
    # AUDIO LATENT stage (the "Bypass Minimax" branch of the old switches)
    # ================================================================== #
    def _build_latent(self, latent, vae_audio, kw, media, notes, models_key):
        """v2.8.4: always Bypass Minimax -> TrimAudioDuration -> VAEEncodeAudio ->
        SetLatentNoiseMask(SolidMask 0) -> LTXVConcatAVLatent(minimax latent, audio latent).
        The encoded audio latent is cached (so a re-run does not encode it again)."""
        custom = bool(kw["Bypassed Audio Latent"])
        audio = media["audio2"] if custom else media["audio1"]
        source = "custom audio" if custom else "audio from video"
        ident = media["cond_id"]["audio2" if custom else "audio1"]
        if audio is None:
            source += " (none: silence)"

        key = ("alat", models_key[2], ident, audio is None, round(float(media["seg_seconds"]), 6),
               int(media["width"]), int(media["height"]))
        audio_latent = _lru_get(_COND_CACHE, key)
        if audio_latent is None:
            if audio is None:
                audio = _silent_audio(media["seg_seconds"])
            trimmed = _core("TrimAudioDuration",
                            {"audio": audio, "start_index": 0.0, "duration": float(media["seg_seconds"])},
                            strict=("audio", "duration"), notes=notes)[0][0]
            audio_latent = _core("VAEEncodeAudio", {"audio": trimmed, "vae": vae_audio},
                                 strict=("audio", "vae"), notes=notes)[0][0]
            mask = _core("SolidMask", {"value": 0.0, "width": int(media["width"]), "height": int(media["height"])},
                         strict=("width", "height"), notes=notes)[0][0]
            audio_latent = _core("SetLatentNoiseMask", {"samples": audio_latent, "mask": mask},
                                 strict=("samples", "mask"), notes=notes)[0][0]
            _lru_put(_COND_CACHE, key, audio_latent)
        else:
            source += " [cached]"
        joined = _core("LTXVConcatAVLatent", {"video_latent": latent, "audio_latent": audio_latent},
                       strict=("video_latent", "audio_latent"), notes=notes)[0][0]
        return joined, f"audio: Bypass Minimax / {source}"

    # ================================================================== #
    # SAMPLING stage
    # ================================================================== #
    def _sample(self, model, positive, latent, kw, notes):
        seed, steps = int(kw["noise_seed"]), int(kw["steps"])
        noise = _core("RandomNoise", {"noise_seed": seed}, strict=("noise_seed",), notes=notes)[0][0]
        guider = _core("BasicGuider", {"model": model, "conditioning": positive},
                       strict=("model", "conditioning"), notes=notes)[0][0]
        sampler = _core("KSamplerSelect", {"sampler_name": SAMPLER_NAME},
                        strict=("sampler_name",), notes=notes)[0][0]
        sigmas = _core("BasicScheduler",
                       {"model": model, "scheduler": SCHEDULER_NAME, "steps": steps, "denoise": DENOISE},
                       strict=("model", "scheduler", "steps", "denoise"), notes=notes)[0][0]
        with _preview_scope(bool(kw["Live Preview"])):
            outs, _ = _core("SamplerCustomAdvanced",
                            {"noise": noise, "guider": guider, "sampler": sampler,
                             "sigmas": sigmas, "latent_image": latent},
                            strict=("noise", "guider", "sampler", "sigmas", "latent_image"), notes=notes)
        return outs[0], sampler

    # ================================================================== #
    # DECODE / VIDEO / SAVE stages
    # ================================================================== #
    @staticmethod
    def _decode(samples, vae_video, vae_audio, notes):
        images = _core("VAEDecode", {"samples": samples, "vae": vae_video},
                       strict=("samples", "vae"), notes=notes)[0][0]
        audio = _core("VAEDecodeAudio", {"samples": samples, "vae": vae_audio},
                      strict=("samples", "vae"), notes=notes)[0][0]
        return images, audio

    @staticmethod
    def _create_video(images, audio, kw, notes):
        fps = DEFAULT_FPS
        provided = {"images": images, "fps": fps, "audio": audio,
                    "color_space": VIDEO_COLOR_SPACE, "codec": VIDEO_CODEC}
        video = _core("CreateVideo", provided, strict=("images", "fps"), notes=notes)[0][0]
        return video, fps

    @staticmethod
    def _save_manual(video, prefix, hidden):
        """Last resort when the core SaveVideo node cannot be driven: plain mp4/h264 save."""
        try:
            from comfy_api.latest import Types
        except Exception:
            from comfy_api.input_impl import VideoFromComponents  # noqa: F401 (older layout)
            from comfy_api.util import VideoCodec, VideoContainer
            Types = type("Types", (), {"VideoCodec": VideoCodec, "VideoContainer": VideoContainer})
        width, height = video.get_dimensions()
        folder, name, counter, subfolder, _ = folder_paths.get_save_image_path(
            prefix, folder_paths.get_output_directory(), width, height)
        meta = {}
        try:
            from comfy.cli_args import args
            skip_meta = bool(args.disable_metadata)
        except Exception:
            skip_meta = False
        if not skip_meta:
            if hidden.get("EXTRA_PNGINFO"):
                meta.update(hidden["EXTRA_PNGINFO"])
            if hidden.get("PROMPT") is not None:
                meta["prompt"] = hidden["PROMPT"]
        file = f"{name}_{counter:05}_.{SAVE_FORMAT}"
        video.save_to(os.path.join(folder, file),
                      format=Types.VideoContainer(SAVE_FORMAT), codec=Types.VideoCodec(SAVE_CODEC),
                      metadata=meta or None)
        return {"images": [{"filename": file, "subfolder": subfolder, "type": "output"}],
                "animated": (True,)}

    def _save_video(self, video, prefix, hidden, notes):
        provided = {"video": video, "filename_prefix": prefix, "format": SAVE_FORMAT,
                    "codec": SAVE_CODEC, "encoding": SAVE_ENCODING}
        errors = []
        # Layout 1: nested dynamic combos only. Layout 2: also pass the inputs that the schema
        # lists at top level as separate arguments. The first one the node accepts wins.
        for hoist in (False, True):
            attempt_notes = []
            try:
                _, ui = _core("SaveVideo", provided, strict=("video", "filename_prefix"),
                              hidden=hidden, notes=attempt_notes, hoist=hoist)
                notes.extend(attempt_notes)
                if ui:
                    return ui
                notes.append("SaveVideo returned no preview info")
                return None
            except Exception as e:
                if _is_interrupt(e):
                    raise
                log.warning("Core SaveVideo (layout %d) failed: %s", 2 if hoist else 1, e)
                errors.append(str(e))

        try:
            cls = comfy_nodes.NODE_CLASS_MAPPINGS["SaveVideo"]
            types = cls.INPUT_TYPES()
            sch = {k: (sec, sp) for sec in ("required", "optional")
                   for k, sp in (types.get(sec) or {}).items()}
            detail = f" [SaveVideo inputs: {_describe_schema(sch)}]"
        except Exception:
            detail = ""
        notes.append(f"core SaveVideo failed ({' / '.join(errors)}); saved with the built-in fallback{detail}")
        return self._save_manual(video, prefix, hidden)

    @staticmethod
    def _saved_name(ui):
        """'subfolder/filename' of what SaveVideo reported (for the status text)."""
        try:
            img = (ui or {})["images"][0]
            return "/".join(p for p in (img.get("subfolder"), img.get("filename")) if p)
        except Exception:
            return "?"

    # ================================================================== #
    # CLIP PIPELINE (one clip per Run). The stages are separate steps so the text encoder, the diffusion model and
    # the VAEs are each swapped in once per Run:   prepare -> sample -> decode / save (+ latent files when asked)
    # ================================================================== #
    def _clip_new(self, kw, media):
        prefix, tag = _clip_prefix(kw, media)
        names = [kw[f"picture_{i}"] for i in range(1, self.SLOTS + 1) if kw[f"picture_{i}"] != NONE_CHOICE]
        return {
            "prompt": kw["prompt"], "prefix": prefix, "tag": tag,
            "pictures": names, "notes": [], "fps": DEFAULT_FPS,
            "positive": None, "positive_plain": None, "latent": None, "samples": None, "sampler": None,
            "refs_line": "", "guide_line": "", "audio_line": "",
            "images": None, "audio": None, "video": None, "ui": {},
            "file": "", "last_frame": None, "logged": False,
            "latent_files": None, "latent_info": None, "latent_line": "",
            "clip_meta": {"index": int(media.get("index", 0)), "frames": int(media.get("frames", 0)),
                          "width": int(media.get("width", 0)), "height": int(media.get("height", 0)),
                          "seg_seconds": float(media.get("seg_seconds", 0.0)),
                          "timeline_start": float(media.get("timeline_start", 0.0)),
                          "audio_stem": media.get("audio_stem") or ""},
        }

    @staticmethod
    def _maybe_drop(st):
        """v2.4: there are no output sockets, so the decoded frames / audio / video are freed at once."""
        st["images"] = st["audio"] = st["video"] = None

    def _phase_prepare(self, st, clip, vae_video, vae_audio, kw, media, models_key):
        notes = st["notes"]
        positive, latent, st["refs_line"] = _stage("reference conditioning", self._conditioning_cached,
                                                   clip, vae_video, vae_audio, kw, media, models_key)
        st["positive_plain"] = positive      # what Save Latent stores (prompt + pictures, no guide)
        if kw.get("Guide", False):
            if kw["Next Segment On Run"]:
                positive, latent, st["guide_line"] = _stage("guide", self._apply_guide,
                                                            positive, latent, vae_video, media, notes)
            else:
                st["guide_line"] = "guide: ON but ignored (Next Segment On Run is OFF)"
        latent, st["audio_line"] = _stage("audio latent", self._build_latent,
                                          latent, vae_audio, kw, media, notes, models_key)
        st["positive"], st["latent"] = positive, latent

    def _phase_sample(self, st, model, kw):
        st["samples"], st["sampler"] = _stage("sampling", self._sample, model, st["positive"], st["latent"],
                                              kw, st["notes"])
        st["positive"] = st["latent"] = None   # (the conditioning cache keeps what a re-run needs)

    def _save_latents(self, st, kw):
        """Save Latent ON: save the sampled latent and its conditioning for a later refine / upscale, in the
        song folder next to the clip, all sharing the clip's name:
            <tag>_NNNNN_.mp4   <tag>_NNNNN_video.latent   <tag>_NNNNN_audio.latent   <tag>_NNNNN.conditioning
        Called once the clip is saved (writing these files earlier would make SaveVideo skip a number), and also when the
        decode / save fails, so an error never loses the sampled latent.
        The conditioning is the plain one (prompt + pictures, no guide).
        Never fatal: a problem here is a note, the clip is still made."""
        if not kw.get("Save Latent", DEFAULT_SAVE_LATENT) or st["samples"] is None or st.get("latent_files"):
            return
        notes = st["notes"]
        try:
            outs, _ = _core("LTXVSeparateAVLatent", {"av_latent": st["samples"]}, strict=("av_latent",), notes=notes)
            video_latent, audio_latent = outs[0], outs[1]
            out_dir = folder_paths.get_output_directory()
            parent = os.path.dirname(str(st["prefix"]).replace("\\", "/"))
            base = f"{st['tag']}_{_clip_counter(st):05d}"
            names = {"video": f"{base}_video.latent", "audio": f"{base}_audio.latent"}
            if st.get("positive_plain") is not None:
                names["conditioning"] = f"{base}.conditioning"
            files = {k: "/".join(p for p in (parent, n) if p) for k, n in names.items()}
            os.makedirs(os.path.dirname(os.path.join(out_dir, *files["video"].split("/"))), exist_ok=True)
            m = st["clip_meta"]
            meta = {"ironleo78": json.dumps({"version": VERSION, "song": _song_name(kw), "tag": st["tag"],
                                             "segment": m["index"], "seed": int(kw["noise_seed"]),
                                             "width": m["width"], "height": m["height"],
                                             "frames": m["frames"], "fps": st["fps"]})}
            _write_latent_file(os.path.join(out_dir, *files["video"].split("/")), video_latent["samples"],
                               {**meta, "part": "video"})
            _write_latent_file(os.path.join(out_dir, *files["audio"].split("/")), audio_latent["samples"],
                               {**meta, "part": "audio"})
            details = {"video_latent_shape": _shape_of(video_latent), "audio_latent_shape": _shape_of(audio_latent),
                       "same_noise_seed": int(kw["noise_seed"])}
            # the conditioning goes last and is never fatal: the latents are already safe
            if "conditioning" in files:
                try:
                    lost = _write_conditioning_file(os.path.join(out_dir, *files["conditioning"].split("/")),
                                                    st["positive_plain"], {**meta, "part": "conditioning"})
                    unsupported = list(lost.get("unsupported", [])) if isinstance(lost, dict) else []
                    details["conditioning_unsupported_items"] = unsupported
                    if unsupported:
                        notes.append(f"conditioning: {len(unsupported)} item(s) could not be stored (see the clip's .json)")
                except Exception as e:
                    if _is_interrupt(e):
                        raise
                    log.warning("Could not save the conditioning: %s", e)
                    notes.append(f"conditioning not saved ({e})")
                    del files["conditioning"]
            st["latent_files"] = files
            st["latent_info"] = details
            st["latent_line"] = "latent saved (Save Latent ON): " + " + ".join(
                [files["video"]] + [os.path.basename(files[k]) for k in ("audio", "conditioning") if k in files])
        except Exception as e:
            if _is_interrupt(e):
                raise
            log.warning("Could not save the latent: %s", e)
            notes.append(f"latent not saved ({e})")

    def _phase_clip(self, st, vae_video, vae_audio, kw, hidden):
        """decode -> Create Video -> Save Video, then the latent files when Save Latent is ON."""
        notes = st["notes"]
        try:
            images, audio = _stage("decode", self._decode, st["samples"], vae_video, vae_audio, notes)
            video, st["fps"] = _stage("create video", self._create_video, images, audio, kw, notes)
            st["ui"] = _stage("save video", self._save_video, video, st["prefix"], hidden, notes) or {}
        except Exception as e:
            if not _is_interrupt(e):
                self._save_latents(st, kw)      # a decode / save error still keeps the sampled latent
            raise
        st["file"] = self._saved_name(st["ui"])
        self._save_latents(st, kw)              # Save Latent ON: latent + conditioning, named after the clip
        st["last_frame"] = _last_frame_of(images)
        st["images"], st["audio"], st["video"] = images, audio, video
        self._maybe_drop(st)
        images = audio = video = None
        st["samples"] = None                    # the sampled latent is not needed any more
        st["positive_plain"] = None

    def _clip_lines(self, st, kw):
        return ([st["refs_line"]]
                + ([st["guide_line"]] if st["guide_line"] else [])
                + [st["audio_line"] + f" | seed {int(kw['noise_seed'])} | steps {int(kw['steps'])} | {st['fps']:g} fps"
                   + f" | turbo {'ON' if kw['Turbo'] else 'OFF'}"]
                + ([st["latent_line"]] if st["latent_line"] else [])
                + [f"saved: {st['file']}"])

    def _manifest_row(self, res, kw, media, prompt_json=""):
        start = float(media.get("timeline_start", 0.0))
        seg = float(media["seg_seconds"])
        prompt = " ".join(str(res["prompt"]).split())
        if len(prompt) > MANIFEST_PROMPT_CHARS:      # the full text is in the sidecar .json
            prompt = prompt[:MANIFEST_PROMPT_CHARS - 1].rstrip() + "\u2026"
        return {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "song": _song_name(kw),
            "segment": int(media["index"]),
            "scene": SCENE_TAG,
            "start_s": f"{start:.2f}", "end_s": f"{start + seg:.2f}", "duration_s": f"{seg:.3f}",
            "frames": int(media["frames"]), "width": int(media["width"]), "height": int(media["height"]),
            "seed": int(kw["noise_seed"]), "turbo": "ON" if kw["Turbo"] else "OFF",
            "pictures": ";".join(res["pictures"]),
            "prompt": prompt,
            "file": res["file"],
            "prompt_json": prompt_json,
            "audio_stem": media.get("audio_stem") or "",
            "latent_file": (res.get("latent_files") or {}).get("video", ""),
            "conditioning_file": (res.get("latent_files") or {}).get("conditioning", ""),
        }

    def _sidecar_data(self, st, kw, media):
        """Everything about one saved clip, with the FULL prompt (v2.5)."""
        start = float(media.get("timeline_start", 0.0))
        seg = float(media["seg_seconds"])
        idx = int(media["index"])
        return {
            "version": VERSION, "kind": "clip",
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "song": _song_name(kw), "tag": st["tag"],
            "segment": idx, "segment_number": idx + 1, "segment_total": media.get("segment_total"),
            "file": st["file"],
            "start_s": round(start, 2), "end_s": round(start + seg, 2), "duration_s": round(seg, 3),
            "frames": int(media["frames"]), "width": int(media["width"]), "height": int(media["height"]),
            "fps": st["fps"], "seed": int(kw["noise_seed"]), "turbo": bool(kw["Turbo"]), "steps": int(kw["steps"]),
            "save_latent": bool(kw.get("Save Latent", DEFAULT_SAVE_LATENT)),
            "custom_lora": ({"file": kw["custom_lora_name"], "strength": kw["custom_lora_strength"]}
                            if kw.get("custom_lora_enabled") else None),
            "pictures": list(st["pictures"]), "references": st["refs_line"],
            "audio": st["audio_line"], "audio_stem": media.get("audio_stem") or None,
            "latent": st.get("latent_files") or None,
            "latent_details": st.get("latent_info") or None,
            "guide": st["guide_line"] or None,
            "models": {k: kw[k] for k in MODEL_FILE_KEYS}, "models_source": "Model Loader" if kw["models_source"] else "hardcoded",
            "prompt": str(st["prompt"]),
        }

    def _log_clip(self, st, kw, media, run_notes):
        """One manifest row for the clip (never fatal). Returns the manifest path text or ''."""
        if st["logged"]:
            return ""
        st["logged"] = True
        sidecar = ""
        if st["file"]:
            try:      # the full prompt next to the clip (never fatal)
                sidecar = _write_sidecar(st["file"], self._sidecar_data(st, kw, media))
            except Exception as e:
                log.warning("Could not write the prompt sidecar for %s: %s", st["file"], e)
                run_notes.append(f"prompt sidecar for {st['file']} not written ({e})")
        first = sidecar
        try:
            note = f"manifest: {_append_manifest(_song_name(kw), [self._manifest_row(st, kw, media, first)])}"
            return note + (f" | full prompt: {first}" if first else "")
        except Exception as e:
            log.warning("Could not write the manifest: %s", e)
            run_notes.append(f"manifest not written ({e})")
            return ""

    # ================================================================== #
    def run(self, unique_id=None, workflow_prompt=None, extra_pnginfo=None, models=None, **kw):
        global _RUNNING
        kw.update(FIXED_SETTINGS)  # hardcoded values (no widgets for them)
        kw["noise_seed"] = DEFAULT_SEED   # v2.8.5: no widget; the Model Loader may replace it (below)
        # v2.3: the Model Loader (optional "models" input) may replace the hardcoded models / steps
        kw["models_source"], kw["models_changed"] = apply_model_overrides(kw, models)
        kw["steps"] = kw["turbo_steps"] if kw["Turbo"] else kw["full_steps"]   # default: Turbo ON = 4, OFF = 25
        kw.setdefault("Save Latent", DEFAULT_SAVE_LATENT)              # v0.6 (a workflow without the widget: OFF)
        self._pending_index = None
        _RUNNING += 1
        try:
            return self._run(unique_id, workflow_prompt, extra_pnginfo, kw)
        finally:
            _RUNNING -= 1

    def _finished(self, kw, done, detail=""):
        """v2.5: every segment is made. Nothing is generated, nothing is raised, the counter does not move."""
        song = _song_name(kw) or "(no custom audio)"
        status = (f"FINISHED | {song} | all {done} segments are done\n"
                  "Nothing was generated and the segment counter did not move.\n"
                  "To start over: press Reset in the segment panel of the node.")
        if detail:
            status += "\n" + detail
        log.info("\n%s", status)
        return {"ui": {"text": [status]}, "result": ()}

    def _run(self, unique_id, workflow_prompt, extra_pnginfo, kw):
        notes = []
        # v2.5: how many segments are there? (only when this Run steps through them)
        total = None
        if kw["Next Segment On Run"]:
            try:
                total = _segment_plan(kw)["total"]
            except Exception as e:
                log.debug("segment plan failed: %s", e)
            if total is not None and _load_index() >= total:
                return self._finished(kw, _load_index())     # quiet stop BEFORE any model is loaded
        # Models first: a model error must not burn a video segment.
        _check_models(kw)
        stem_note = self._prepare_stems(kw)      # Hybrid Demucs (first use of a new song only), BEFORE the big models load
        model, clip, vae_video, vae_audio = self._load_models(kw, unique_id)
        models_key = (_stamp("text_encoders", kw["qwen_vl_name"]), _stamp("vae", kw["video_vae_name"]),
                      _stamp("vae", kw["audio_vae_name"]))
        try:
            media = self._load_media(kw)
        except _EndOfSegments as e:      # the plan could not know (or was off by a hair): still a quiet stop
            return self._finished(kw, e.index, str(e))
        media["segment_total"] = total
        if stem_note:
            media["status"] += "\n" + stem_note
        media["song"] = _song_name(kw)         # v2.6: the Guide can read a last frame back from the manifest clips
        hidden = {"UNIQUE_ID": unique_id, "PROMPT": workflow_prompt, "EXTRA_PNGINFO": extra_pnginfo}

        st = self._clip_new(kw, media)

        manifest_note = ""
        try:
            self._phase_prepare(st, clip, vae_video, vae_audio, kw, media, models_key)
            self._phase_sample(st, model, kw)
            self._phase_clip(st, vae_video, vae_audio, kw, hidden)
        except Exception:
            # a clip that is already on disk (saved, then something failed) is logged (never fatal)
            if st["file"] and not st["logged"]:
                self._log_clip(st, kw, media, notes)
            raise
        manifest_note = self._log_clip(st, kw, media, notes)

        # Everything worked: only now does the video segment counter move on.
        if self._pending_index is not None:
            if st["last_frame"] is not None:
                try:      # the last frame of this clip, for the Guide of the next run (never fatal)
                    _save_last_frame(st["last_frame"], self._pending_index - 1)
                except Exception as e:
                    log.warning("Could not save the last frame for the guide: %s", e)
                    notes.append(f"last frame not saved ({e})")
            _save_index(self._pending_index)

        # ---- status text ----
        start = float(media.get("timeline_start", 0.0))
        idx = int(media["index"])
        if kw["Next Segment On Run"]:
            seg_txt = (f"segment {idx + 1} of {total}" if total else f"segment {idx + 1}") + f" (seg{idx:03d})"
        else:
            seg_txt = f"segment {idx}"
        header = (f"SONG: {_song_name(kw) or '(no custom audio: video / Picture1 name)'} | {seg_txt}"
                  f" | {start:.2f}s to {start + float(media['seg_seconds']):.2f}s")
        if kw["Next Segment On Run"] and total:
            left = total - (idx + 1)
            header += (f"\nprogress: {idx + 1} of {total} segments done ({100.0 * (idx + 1) / total:.0f} %)"
                       + (" | that was the LAST segment: the next Run stops quietly" if left <= 0 else f" | {left} left"))
        header += "\nmodels: " + (f"Model Loader ({kw['models_changed']})" if kw["models_source"] else "hardcoded defaults")
        status = media["status"] + "\n" + header
        status += f"\n--- {st['tag']} ---\n" + "\n".join(self._clip_lines(st, kw))
        if st["notes"]:
            status += "\nnotes: " + "; ".join(st["notes"])
        if manifest_note:
            status += "\n" + manifest_note
        if notes:
            status += "\nnotes: " + "; ".join(notes)
        log.info("\n%s", status)

        # v2.5: only the text for the node's own status box. No "images" entry = no video preview on the node.
        return {"ui": {"text": [status]}, "result": ()}

    # ------------------------------------------------------------------ #
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        if kwargs.get("Use Video", True) or kwargs.get("Next Segment On Run", False):
            return float("nan")  # segment stepping (video or custom audio chunks): always re-run
        m = hashlib.sha256()
        for i in range(1, cls.SLOTS + 1):
            name = kwargs.get(f"picture_{i}", NONE_CHOICE)
            m.update(name.encode("utf-8"))
            if name != NONE_CHOICE:
                try:
                    with open(folder_paths.get_annotated_filepath(name), "rb") as f:
                        m.update(f.read())
                except Exception:
                    pass
        for key in ("megapixels", "duration", "Custom Audio File", "Audio Stem", "Video File"):
            m.update(str(kwargs.get(key, "")).encode("utf-8"))
        return m.digest().hex()

    @classmethod
    def VALIDATE_INPUTS(cls, **kw):
        # ---- models: the hardcoded / Model Loader files are checked when the Run starts (_check_models),
        #      because a linked "models" input is not visible here ----
        # ---- media ----
        if kw.get("Use Video", True):
            video = kw.get("Video File")
            if not video or video == NONE_CHOICE or not folder_paths.exists_annotated_filepath(video):
                return "Use Video is ON but no valid video is selected. Upload one, or switch Use Video OFF."
        custom_audio = kw.get("Custom Audio File")
        if custom_audio and custom_audio != NONE_CHOICE and not folder_paths.exists_annotated_filepath(custom_audio):
            return f"Custom audio file not found: {custom_audio}"
        if kw.get("Audio Stem", _stems.STEM_SONG) not in _stems.STEM_CHOICES:
            return f"Audio Stem must be one of: {', '.join(_stems.STEM_CHOICES)}."
        for i in range(1, cls.SLOTS + 1):
            name = kw.get(f"picture_{i}", NONE_CHOICE)
            if name != NONE_CHOICE and not folder_paths.exists_annotated_filepath(name):
                return f"Picture{i}: invalid image file: {name}"
        return True


_register_routes()

NODE_CLASS_MAPPINGS = {"IronLeo78_MTV": IronLeo78_MTV}
NODE_DISPLAY_NAME_MAPPINGS = {"IronLeo78_MTV": "IronLeo78 MTV (v0.01)"}
