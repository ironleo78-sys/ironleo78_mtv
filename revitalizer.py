"""
IronLeo78 2in1 Revitalizer  v0.4
------------------------------------------------------------
STANDALONE all-in-one custom node. It replaces the whole "H3 Latent Upscale" workflow in ONE node:

    load first-pass latent + conditioning saved by the IronLeo78 MTV
      -> (optional) model: UNET loader, turbo LoRA ON/OFF, attention backend
      -> Separate AV latent -> Minimax H3 Latent Upscaler (3D), or the built-in latent resize (v0.1.7) -> Concat AV latent
      -> BasicGuider + SamplerCustomAdvanced (RandomNoise, sampler, fixed 5-step sigmas)
      -> VAE Decode (video, normal) + VAE Decode Audio
      -> Create Video (24 fps, 8 bit, sRGB, audio)

v0.0.9: the node does NOT save the video any more (like the MTV): link its `video` output to a Save Video node. The sigmas
are a visible, editable text widget (default = the 5-step refine below).

v0.0.9c: three more LoRAs, LoRa_1 .. LoRa_3 (toggle, file, strength each, same names as the Model Loader), chained after the
existing LoRA (the Turbo slot). They are APPENDED after `sigmas` as optional widgets, so no saved value moves. The Model Loader's
"Set New Defaults" set reaches this node too: a NEW node starts from it, a button on the node ("Use Set New Defaults") loads it on
demand, and clicking "Set New Defaults" on a Model Loader sends it to the Revitalizers of the open workflow.

Outputs: the video, the images, the audio, the refined AV latent and a STATUS text (the steps are also
printed in the ComfyUI console).

The MTV saves, next to every clip (Save Latent ON):

    output/<Song>/<Song>_seg004_A_00001_video.latent
    output/<Song>/<Song>_seg004_A_00001_audio.latent
    output/<Song>/<Song>_seg004_A_00001.conditioning

Both the latent and the conditioning are chosen from dropdowns that list ComfyUI/output (newest first; press R to
refresh) plus uploaded files. The "Upload latent / conditioning files" button copies files from anywhere on your
computer into ComfyUI/input/ironleo78_revitalizer/ and selects them.

Fixed inside the node (no widget): weight dtype default, align 32, bit depth 8, color space sRGB, 24 fps, normal VAE decode.
The sigmas default to 0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000 (5 steps) and can be edited on the node.

Needs, besides ComfyUI itself (recent enough to have LTXVSeparateAVLatent / LTXVConcatAVLatent, CreateVideo and the
V3 video API) nothing else. v0.1.7: the third-party node "Comfyui_Minimax_h3_latent_Upscaler" + its model in
models/latent_upscale_models/ are OPTIONAL: when both are there they do the upscale (a trained model); otherwise the node
resizes the latent itself (resize_video_latent) and the refine pass redraws the detail. Every other step uses core ComfyUI
nodes, called by name, so they behave exactly as in your workflow.
"""

import collections
import json
import logging
import os
import time

import folder_paths

from . import model_cache as _models

_log = logging.getLogger("IronLeo78.Revitalizer")      # v0.0.9r (a module-level name `log` would clash with the local `log` lists below)

LATENT_SUFFIX = "_video.latent"
AUDIO_SUFFIX = "_audio.latent"
COND_SUFFIX = ".conditioning"

NONE_FOUND = "(none found: run the MTV with Save Latent ON, then press R)"
MATCH_LATENT = "(match the latent)"

UPLOAD_TAG = "[uploaded] "                 # entries that live in ComfyUI/input/ironleo78_revitalizer/
UPLOAD_SUBFOLDER = "ironleo78_revitalizer"

MAX_DEPTH = 3          # output/<Song>/file is depth 1; a prefix with sub folders still fits
MAX_LISTED = 3000
_SKIP_DIRS = {"stems"}

# defaults taken from the H3_Latent_Upscale_Scheme_Ready2Cook workflow
DEF_UNET = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
DEF_VAE_VIDEO = "minimax_h3_video_vae_int8_convrot.safetensors"
DEF_VAE_AUDIO = "minimax_h3_audio_vae_fp32.safetensors"
DEF_LORA = "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors"
DEF_UPSCALER = "h3_upscaler_sharpness_2000steps_v0.1_fp32.safetensors"   # v0.1.11: the user's tuned defaults (was h3_upscaler_lms_v0.1)
DEF_SIGMAS = "0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000"   # v0.0.9: the default of the editable `sigmas` widget (5-step refine)
SIGMAS = [0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000]        # the same, as numbers
MAX_SIGMAS = 1000
DEF_MEGAPIXELS = 0.4                                              # default target size of the upscale (v0.1.11: 0.4; 1.2 from v0.0.9, 2.0 before; the maximum is still 2.0)
DEF_SAMPLER = "res_multistep"                                     # v0.1.11 (was euler); same sampler as the MTV
DEF_SEED = 1978                                                   # v0.1.11: a node with no saved set starts at the MTV's seed (was 0)
WEIGHT_DTYPE = "default"                                         # fixed
ALIGN = 32                                                       # fixed
BIT_DEPTH = 8                                                    # fixed
COLOR_SPACE = "sRGB"                                             # fixed

ATTENTION = ["comfy kitchen attention", "pytorch attention", "(leave the model untouched)"]
FPS = 24.0                                  # frozen (not shown on the node)

LORA_NONE = "(none)"

# v0.0.9c: LoRa_1 .. LoRa_3, the same names / defaults as the Model Loader, so the saved set maps one to one
LORA_SLOTS = 3
SLOT_NONE = "None"                          # the Model Loader's empty LoRA entry
SLOT_STRENGTH = 1.0                         # v0.1.11 (0.65 until 0.1.10), same as the Model Loader
SLOT_KEYS = tuple(f"LoRa_{n}{suffix}" for n in range(1, LORA_SLOTS + 1) for suffix in ("_enabled", "", "_strength"))
# Model Loader widget name -> Revitalizer widget name (the Loader's Turbo LoRA file goes to the existing LoRA slot)
SET_MAP = {"unet_name": "unet_name", "turbo_lora_name": "lora_name", "turbo_lora_strength": "lora_strength", "video_vae_name": "vae_video",
           "audio_vae_name": "vae_audio", "noise_seed": "seed", **{k: k for k in SLOT_KEYS}}
SET_ROUTE = "/ironleo78/revitalizer/saved_set"


# ---------------------------------------------------------------------- #
# plain-python helpers (tested without ComfyUI)
# ---------------------------------------------------------------------- #
def _root():
    return os.path.abspath(folder_paths.get_output_directory())


def _upload_root():
    return os.path.abspath(os.path.join(folder_paths.get_input_directory(), UPLOAD_SUBFOLDER))


def entries(suffix):
    """Everything the dropdowns offer: files in output/ (newest first) and uploaded files (tagged)."""
    found = scan(_root(), suffix)
    up = _upload_root()
    if os.path.isdir(up):
        found += [UPLOAD_TAG + n for n in scan(up, suffix, max_depth=1)]
    return found


def locate(value):
    """Absolute path of a dropdown entry (output-relative name or '[uploaded] name')."""
    value = str(value)
    if value.startswith(UPLOAD_TAG):
        return resolve(_upload_root(), value[len(UPLOAD_TAG):])
    return resolve(_root(), value)


def clean_upload_name(filename):
    """The file name an upload is saved under, or None when it is not a .latent / .conditioning file."""
    name = os.path.basename(str(filename or "").replace("\\", "/")).strip()
    if not name or name.startswith(".") or not name.lower().endswith((".latent", COND_SUFFIX)):
        return None
    return name


def scan(root, suffix, max_depth=MAX_DEPTH, limit=MAX_LISTED):
    """Paths (relative to root, '/' separated) of every file ending in `suffix`, newest first."""
    root = os.path.abspath(root)
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        depth = 0 if dirpath == root else os.path.relpath(dirpath, root).count(os.sep) + 1
        dirnames[:] = [] if depth >= max_depth else [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.endswith(suffix):
                full = os.path.join(dirpath, name)
                try:
                    found.append((os.path.getmtime(full), os.path.relpath(full, root).replace(os.sep, "/")))
                except OSError as e:      # v0.0.9r: a file that vanished while listing is skipped
                    _log.debug("could not read the time of '%s' (%s)", full, e)
    found.sort(reverse=True)
    return [rel for _, rel in found[:limit]]


def resolve(root, rel):
    """Absolute path of an output-relative name; refuses anything that would leave the output folder."""
    rel = str(rel).replace("\\", "/")
    full = os.path.abspath(os.path.join(root, *[p for p in rel.split("/") if p]))
    try:
        inside = os.path.commonpath([root, full]) == root
    except ValueError:
        inside = False
    if not inside or full == root:
        raise ValueError(f"'{rel}' is outside the ComfyUI output folder.")
    return full


def sibling(latent_rel, kind):
    """The audio latent / conditioning that belongs to a '<clip>_video.latent'."""
    if not str(latent_rel).endswith(LATENT_SUFFIX):
        raise ValueError(f"'{latent_rel}' is not a '{LATENT_SUFFIX}' file written by the MTV.")
    base = str(latent_rel)[:-len(LATENT_SUFFIX)]
    return base + (AUDIO_SUFFIX if kind == "audio" else COND_SUFFIX)


def _is_placeholder(value):
    return value in (None, "", NONE_FOUND)


def check(latent, conditioning):
    """None when the selection is usable, else a message."""
    if _is_placeholder(latent):
        return ("2in1 Revitalizer: no latent selected. Use the Upload button, or run the MTV with "
                "Save Latent ON and press R.")
    try:
        sibling(latent, "audio")                         # refuses names that are not <clip>_video.latent
        if not os.path.isfile(locate(latent)):
            return f"2in1 Revitalizer: latent not found: {latent}"
        if not os.path.isfile(locate(sibling(latent, "audio"))):
            return (f"2in1 Revitalizer: the audio latent is missing: {sibling(latent, 'audio')}. "
                    f"Upload the _audio.latent too.")
        cond = sibling(latent, "cond") if conditioning in (None, "", MATCH_LATENT) else conditioning
        if not os.path.isfile(locate(cond)):
            return (f"2in1 Revitalizer: conditioning not found: {cond}. Upload the .conditioning file too (clips made "
                    f"before MTV 0.4 have none: pick one from another clip).")
    except ValueError as e:
        return str(e)
    return None


def _stamp(path):
    try:
        st = os.stat(path)
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return "missing"


def _names(folder, extensions=None):
    try:
        names = list(folder_paths.get_filename_list(folder))
    except Exception:
        names = []
    if extensions:
        names = [n for n in names if os.path.splitext(n)[1].lower() in extensions]
    return names or [f"(none found in models/{folder})"]


def _default(names, wanted):
    return wanted if wanted in names else names[0]


def _is_missing(name):
    return not name or str(name).startswith("(none")


def saved_set():
    """v0.0.9c: the Model Loader's saved set ("Set New Defaults"), by REVITALIZER widget name: ({widget: value}, seed control or None).
    Empty when nothing was saved (or when this file runs outside the pack, as in the tests): then nothing is forced."""
    try:
        from .mtv import _read_user_defaults, _read_user_seed_control
        saved = dict(_read_user_defaults())
        control = _read_user_seed_control()
    except Exception:
        return {}, None
    return {SET_MAP[k]: v for k, v in saved.items() if k in SET_MAP}, control


def _pick(names, wanted, fallback):
    """`wanted` when it is one of the installed names, else `fallback`."""
    return wanted if wanted in names else fallback


def lora_slot(kw, n):
    """(enabled, file, strength) of LoRa_n from a dict of widget values (anything missing = OFF / None / SLOT_STRENGTH)."""
    enabled = kw.get(f"LoRa_{n}_enabled")
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in ("true", "1", "on", "yes")
    name = kw.get(f"LoRa_{n}")
    name = str(name) if name not in (None, "") else SLOT_NONE
    strength = kw.get(f"LoRa_{n}_strength")
    return bool(enabled), name, SLOT_STRENGTH if strength is None else strength


def set_report(kw):
    """One line for the status: do the model widgets of this run match the saved set? '' when no set was saved."""
    saved, _ = saved_set()
    if not saved:
        return ""
    diffs = []
    for widget, want in saved.items():
        have = kw.get(widget)
        if have is None:
            continue
        same = abs(float(have) - float(want)) < 1e-9 if isinstance(want, float) and not isinstance(have, str) else have == want
        if not same:
            diffs.append(f"{widget}={have} (saved {want})")
    if diffs:
        return "models: DIFFERS from the saved set (Set New Defaults): " + ", ".join(diffs[:6]) + (f", +{len(diffs) - 6} more" if len(diffs) > 6 else "")
    return "models: same as the saved set (Set New Defaults)"


def slot_problem(n, enabled, name, strength):
    """None when LoRa_n is usable, else a plain-words message. Only a LoRa_n that is ON needs a file (the combo check of ComfyUI is replaced by this)."""
    if strength is not None:
        try:
            if not -100.0 <= float(strength) <= 100.0:
                return f"2in1 Revitalizer: LoRa_{n}_strength must be between -100 and 100."
        except (TypeError, ValueError):
            return f"2in1 Revitalizer: LoRa_{n}_strength must be a number."
    if not lora_slot({f"LoRa_{n}_enabled": enabled}, n)[0]:
        return None
    if name in (None, "", SLOT_NONE, LORA_NONE) or str(name).startswith("(none"):
        return f"2in1 Revitalizer: LoRa_{n} is ON but no file is selected. Pick one (ComfyUI/models/loras/, press R) or switch it OFF."
    if name not in _names("loras"):
        return f"2in1 Revitalizer: LoRa_{n} file not found: {name} (ComfyUI/models/loras/)"
    return None


def parse_sigmas(text):
    """v0.0.9: the `sigmas` widget text -> list of floats. Raises ValueError with a plain-words message.
    Separators: commas, semicolons, spaces, new lines. Needs 2 or more numbers, none below 0, going down (or staying equal)
    from left to right, and the last one lower than the first. N numbers = N - 1 steps."""
    if isinstance(text, (list, tuple)):
        raw = [str(x) for x in text]
    else:
        cleaned = str(text if text is not None else "").replace("[", " ").replace("]", " ")
        for sep in (",", ";", "\n", "\r", "\t"):
            cleaned = cleaned.replace(sep, " ")
        raw = cleaned.split()
    if not raw:
        raise ValueError("sigmas: the list is empty. Example: " + DEF_SIGMAS)
    values = []
    for item in raw:
        try:
            v = float(item)
        except ValueError:
            raise ValueError(f"sigmas: '{item}' is not a number. Write numbers separated by commas, for example: {DEF_SIGMAS}")
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError(f"sigmas: '{item}' is not a usable number.")
        if v < 0:
            raise ValueError(f"sigmas: {item} is below 0.")
        values.append(v)
    if len(values) < 2:
        raise ValueError("sigmas: at least 2 numbers are needed (N numbers = N - 1 steps).")
    if len(values) > MAX_SIGMAS:
        raise ValueError(f"sigmas: {len(values)} numbers is too many (limit {MAX_SIGMAS}).")
    for a, b in zip(values, values[1:]):
        if b > a:
            raise ValueError(f"sigmas: the numbers must go down from left to right ({a:g} is followed by {b:g}).")
    if values[-1] >= values[0]:
        raise ValueError("sigmas: the last number must be lower than the first.")
    return values


# ---------------------------------------------------------------------- #
# calling core ComfyUI nodes by name
# ---------------------------------------------------------------------- #
def _unwrap(res):
    if isinstance(res, dict) and "result" in res:
        return res["result"]
    if getattr(res, "result", None) is not None:
        return res.result
    if hasattr(res, "args"):
        return res.args
    return res


def _call(name, **kw):
    """Run a node by name (old V1 nodes and new V3 nodes alike); returns the tuple of its outputs."""
    import nodes
    cls = nodes.NODE_CLASS_MAPPINGS.get(name)
    if cls is None:
        raise RuntimeError(f"2in1 Revitalizer: node '{name}' not found in this ComfyUI"
                           + (" (install Comfyui_Minimax_h3_latent_Upscaler)." if name.startswith("MinimaxH3") else "."))
    return tuple(_unwrap(getattr(cls(), cls.FUNCTION)(**kw)))


def _has(name):
    import nodes
    return name in nodes.NODE_CLASS_MAPPINGS


# ---------------------------------------------------------------------- #
# v0.1.7: built-in latent upscale (the third-party upscaler node is optional now)
# ---------------------------------------------------------------------- #
UPSCALER_NODE = "MinimaxH3LatentUpscaler3D"      # third-party (Comfyui_Minimax_h3_latent_Upscaler): used when it is installed
H3_PIXELS_PER_LATENT = 16                        # the H3 video latent is [batch, 24, time, height / 16, width / 16]
                                                 # (comfy_extras/nodes_minimax_h3.py)


def builtin_upscale_size(latent_w, latent_h, megapixels, align=ALIGN):
    """(width, height in pixels, latent width, latent height) of the upscaled clip: about `megapixels`, the clip's own aspect,
    each side a multiple of `align` pixels (32 = 2 latent cells)."""
    import math
    w, h = latent_w * H3_PIXELS_PER_LATENT, latent_h * H3_PIXELS_PER_LATENT
    r = w / h
    tw = math.sqrt(float(megapixels) * 1_000_000 * r)
    th = tw / r
    tw = max(align, int(round(tw / align)) * align)
    th = max(align, int(round(th / align)) * align)
    return tw, th, tw // H3_PIXELS_PER_LATENT, th // H3_PIXELS_PER_LATENT


def resize_video_latent(latent, megapixels):
    """The built-in upscale: every frame of the video latent [B, C, T, H, W] resized (bilinear; antialiased when it gets
    smaller) to the size of builtin_upscale_size. It is the "resize" half of what the trained upscaler does (that model then
    cleans the resized latent up); here the Revitalizer's refine pass, which starts from heavy noise, redraws the detail.
    Returns (new latent dict without a noise mask, (width, height) in pixels)."""
    import torch.nn.functional as F
    x = latent["samples"]
    b, c, t, h, w = (int(v) for v in x.shape)
    tw, th, lw, lh = builtin_upscale_size(w, h, megapixels)
    out = {k: v for k, v in latent.items() if k != "noise_mask"}
    if (lw, lh) != (w, h):
        y = x.permute(0, 2, 1, 3, 4).reshape(b * t, c, h, w).float()
        y = F.interpolate(y, size=(lh, lw), mode="bilinear", align_corners=False, antialias=lw < w or lh < h)
        x = y.reshape(b, t, c, lh, lw).permute(0, 2, 1, 3, 4).to(x.dtype).contiguous()
    out["samples"] = x
    return out, (tw, th)


# ---------------------------------------------------------------------- #
# v0.1.4: the model and the VAEs stay loaded between runs (review item #6)
# ---------------------------------------------------------------------- #
# Until 0.1.3 every run loaded the diffusion model, its LoRAs and both VAEs from disk again, even when only the sigmas or the
# seed changed. Now one model (with its LoRA chain and attention backend) and up to two VAEs are kept, keyed by file name +
# modification time (+ LoRA strengths): changing a file, a LoRA, a strength or the attention backend loads again, and the
# old one is dropped BEFORE the new one loads. The MTV's free_cached_models() (its "free" route) clears this cache too.
_CACHE = {}                  # stage -> OrderedDict(key -> value)
_CACHE_LIMIT = {"vae": 2}    # the video VAE + the audio VAE; every other stage keeps one entry


def _file_stamp(folder, name):
    """(name, mtime) of a model file, so a file replaced under the same name is loaded again."""
    try:
        return (str(name), os.path.getmtime(folder_paths.get_full_path(folder, name)))
    except Exception:
        return (str(name), None)


def _cached(stage, key, build):
    """(value, True) when `key` is cached for `stage`, else (build(), False) after the oldest entry is dropped."""
    entries = _CACHE.setdefault(stage, collections.OrderedDict())
    if key in entries:
        entries.move_to_end(key)
        return entries[key], True
    while len(entries) >= _CACHE_LIMIT.get(stage, 1):
        entries.popitem(last=False)
    value = build()
    entries[key] = value
    return value, False


def free_cache():
    """Drop the kept model and VAEs (called by the MTV's free_cached_models)."""
    _CACHE.clear()


def _drop_built_model():
    """v0.1.5: another base diffusion model is about to load (model_cache.py): the model built on the old one goes first
    (cleared in place, like the MTV's)."""
    if "model" in _CACHE:
        _CACHE["model"].clear()


_models.on_switch(_drop_built_model)


# ---------------------------------------------------------------------- #
# live status: what the node is doing right now, sent to the status box on the node
# ---------------------------------------------------------------------- #
STAGES = ["Checking settings", "Loading clip", "Upscaling latent", "Loading model", "Sampling",
          "Decoding video", "Decoding audio", "Building video"]


def hint_for(exc):
    """A plain-words tip for the usual failures."""
    text = (type(exc).__name__ + " " + str(exc)).lower()
    if "out of memory" in text or "outofmemory" in text:
        return "Out of VRAM. Lower the megapixels, turn the upscale OFF, or close other GPU programs, then run again."
    if "not found in this comfyui" in text or "comfyui is too old" in text:
        return "A needed node is missing or ComfyUI is too old: see the Install section of the README."
    if "no upscale model" in text or "none found in models" in text:
        return "A model file is missing: put it in the matching models/ folder, press R, and select it."
    if "no such file" in text or "not found" in text or "missing" in text:
        return "A file is missing: check the clip's three files (video latent, audio latent, conditioning)."
    return ""


class Live:
    """Keeps the stage list for the STATUS output and prints each step (and any error) in the ComfyUI console."""

    def __init__(self, stages=STAGES):
        self.stages = stages
        self.t0 = time.time()
        self.lines = []
        self.cur = None
        self.cur_t = 0.0
        self.cur_detail = ""
        self.footer = ""

    def _tag(self, i):
        return f"[{i + 1}/{len(self.stages)}] {self.stages[i]}"

    @property
    def text(self):
        out = ["IronLeo78 2in1 Revitalizer v0.4"] + self.lines
        if self.cur is not None:
            out.append(f"\u25b6 {self._tag(self.cur)}" + (f": {self.cur_detail}" if self.cur_detail else "") + " ...")
        if self.footer:
            out.append(self.footer)
        return "\n".join(out)

    def start(self, i, detail=""):
        self.finish()
        self.cur, self.cur_t, self.cur_detail = i, time.time(), detail
        print(f"[Revitalizer] {self._tag(i)} {detail}".rstrip())

    def finish(self):
        if self.cur is None:
            return
        took = time.time() - self.cur_t
        self.lines.append(f"\u2714 {self._tag(self.cur)}" + (f": {self.cur_detail}" if self.cur_detail else "") + f" ({took:.1f}s)")
        self.cur = None
        self.cur_detail = ""

    def skip(self, i, why):
        self.finish()
        self.lines.append(f"- {self._tag(i)}: skipped ({why})")

    def done(self, note=""):
        self.finish()
        self.footer = f"\u2714 DONE in {time.time() - self.t0:.1f}s" + (f"  {note}" if note else "")
        print("[Revitalizer] " + self.footer)

    def error(self, exc):
        where = self._tag(self.cur) if self.cur is not None else "before the first step"
        msg = "\n".join(str(exc).strip().splitlines()[:6]) or type(exc).__name__
        tip = hint_for(exc)
        self.cur = None
        self.footer = f"\u2716 ERROR in {where}\n{type(exc).__name__}: {msg}" + (f"\nTip: {tip}" if tip else "")
        print("[Revitalizer] " + self.footer)


# ---------------------------------------------------------------------- #
# the node
# ---------------------------------------------------------------------- #
class IronLeo78_2in1_Revitalizer:
    @classmethod
    def INPUT_TYPES(cls):
        latents = entries(LATENT_SUFFIX) or [NONE_FOUND]
        conds = [MATCH_LATENT] + entries(COND_SUFFIX)
        unets = _names("diffusion_models")
        vaes = _names("vae")
        loras = [LORA_NONE] + [n for n in _names("loras") if not n.startswith("(none")]
        upscalers = _names("latent_upscale_models", (".pth", ".safetensors"))
        sset, _control = saved_set()      # v0.0.9c: a NEW node starts from the saved set (nothing saved = the old defaults)
        slot_loras = [SLOT_NONE] + [n for n in _names("loras") if not n.startswith("(none") and n != SLOT_NONE]
        optional = {}
        for n in range(1, LORA_SLOTS + 1):
            file = _pick(slot_loras, sset.get(f"LoRa_{n}"), SLOT_NONE)
            optional[f"LoRa_{n}_enabled"] = ("BOOLEAN", {
                "default": bool(sset.get(f"LoRa_{n}_enabled", False)) and file != SLOT_NONE, "label_on": "ON", "label_off": "OFF",
                "tooltip": f"LoRa_{n} ON / OFF (default OFF). Applied after the LoRA above" + ("." if n == 1 else f" and after LoRa_{n - 1}.")})
            optional[f"LoRa_{n}"] = (slot_loras, {"default": file, "tooltip": f"LoRa_{n}: LoRA file from ComfyUI/models/loras/ (same as the Model Loader's LoRa_{n})."})
            optional[f"LoRa_{n}_strength"] = ("FLOAT", {"default": float(sset.get(f"LoRa_{n}_strength", SLOT_STRENGTH)),
                                                         "min": -100.0, "max": 100.0, "step": 0.01, "tooltip": f"LoRa_{n} strength (default {SLOT_STRENGTH})."})
        return {
            "optional": optional,
            "required": {
                # ---- 1. the clip (what the Shampoo did)
                "latent": (latents, {"tooltip": "The first-pass latent (<clip>_video.latent). Lists ComfyUI/output (newest first) "
                                                "and uploaded files. Use the Upload button to add files from anywhere."}),
                "conditioning": (conds, {"default": MATCH_LATENT,
                                         "tooltip": "'(match the latent)' loads the <clip>.conditioning saved with the selected "
                                                    "latent. Pick another file to use a different clip's conditioning."}),
                "freeze_audio": ("BOOLEAN", {"default": True, "label_on": "ON", "label_off": "OFF",
                                             "tooltip": "ON: the audio latent gets a zero noise mask (as in the MTV), "
                                                        "so the refine pass does not re-noise the song."}),
                # ---- 2. models
                "unet_name": (unets, {"default": _pick(unets, sset.get("unet_name"), _default(unets, DEF_UNET)), "tooltip": "Diffusion model (UNETLoader)."}),
                "vae_video": (vaes, {"default": _pick(vaes, sset.get("vae_video"), _default(vaes, DEF_VAE_VIDEO)), "tooltip": "H3 video VAE."}),
                "vae_audio": (vaes, {"default": _pick(vaes, sset.get("vae_audio"), _default(vaes, DEF_VAE_AUDIO)), "tooltip": "H3 audio VAE."}),
                "lora_on": ("BOOLEAN", {"default": True, "label_on": "LoRA ON", "label_off": "LoRA OFF",      # v0.1.11: ON (was OFF)
                                        "tooltip": "The 'LoRa OFF/ON' switch of the workflow (model-only LoRA, e.g. the 4-step turbo)."}),
                "lora_name": (loras, {"default": _pick(loras, sset.get("lora_name"), _default(loras, DEF_LORA)),
                                     "tooltip": "The LoRA of the workflow (the 4-step turbo). A saved set puts the Model Loader's Turbo LoRA file here."}),
                "lora_strength": ("FLOAT", {"default": float(sset.get("lora_strength", 1.0)), "min": -100.0, "max": 100.0, "step": 0.01,      # v0.1.9: same range as LoRa_1-3 (was -10..10)
                                            "tooltip": "Strength of the LoRA above. A saved set puts the Model Loader's Turbo LoRA strength here (v0.1.11)."}),
                "attention_backend": (ATTENTION, {"default": ATTENTION[0],
                                                  "tooltip": "Model Attention Backend. 'comfy kitchen attention' falls back to "
                                                             "PyTorch attention by itself when it is not available."}),
                # ---- 3. latent upscale (Minimax H3 Latent Upscaler 3D)
                "upscale_on": ("BOOLEAN", {"default": True, "label_on": "Upscale ON", "label_off": "Upscale OFF",
                                           "tooltip": "OFF: refine at the saved size (no Separate / Upscaler / Concat). "
                                                      "ON: with the optional Minimax H3 Latent Upscaler node + a model file installed, "
                                                      "that trained upscaler is used; without them the latent is resized by this node "
                                                      "and the refine pass redraws the detail (the status says which)."}),
                "upscale_model": (upscalers, {"default": _default(upscalers, DEF_UPSCALER),
                                              "tooltip": "Only used when the optional Minimax H3 Latent Upscaler node is installed "
                                                         "(models/latent_upscale_models). Without it the built-in latent resize is used."}),
                "megapixels": ("FLOAT", {"default": DEF_MEGAPIXELS, "min": 0.1, "max": 2.0, "step": 0.1, "tooltip": "Target size of the upscaled video, in megapixels (max 2.0)."}),
                "temporal_chunking": ("BOOLEAN", {"default": False}),      # v0.1.11: OFF (was ON)
                "force_unload": ("BOOLEAN", {"default": False, "tooltip": "Unload the upscale model to CPU afterwards to free VRAM."}),      # v0.1.11: OFF (was ON)
                "upscale_device": (["cuda", "rocm", "cpu"], {"default": "cuda"}),
                "upscale_precision": (["fp16", "bf16", "fp32"], {"default": "fp16"}),
                # ---- 4. sampling
                "seed": ("INT", {"default": int(sset.get("seed", DEF_SEED)), "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True,
                                 "tooltip": "Use the clip's own seed to repeat it (the refine pass should use the same seed)."}),
                "sampler_name": (_samplers(), {"default": DEF_SAMPLER if DEF_SAMPLER in _samplers() else "euler"}),
                # ---- 5. sigmas (v0.0.9: visible and editable; it replaces filename_prefix, the node no longer saves the video)
                "sigmas": ("STRING", {"default": DEF_SIGMAS, "multiline": False,
                                      "tooltip": "The refine schedule, numbers separated by commas, going down from left to right "
                                                 "(N numbers = N - 1 steps). Default: the 5-step refine."}),
            },
        }

    RETURN_TYPES = ("VIDEO", "IMAGE", "AUDIO", "LATENT", "STRING")
    RETURN_NAMES = ("video", "images", "audio", "latent", "status")
    FUNCTION = "revitalize"
    CATEGORY = "IronLeo78/MTV"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "All-in-one: loads a first-pass latent + conditioning saved by the IronLeo78 MTV, upscales the video "
        "latent (the optional Minimax H3 Latent Upscaler 3D when installed, else a built-in latent resize), refines it "
        "(guider + sampler + sigmas), decodes video and audio, builds the "
        "video (link the video output to a Save Video node: this node does not save it).\nby IronLeo78"
    )

    # --- validation: the lists are read from disk, so the combo check is replaced by a file check
    @classmethod
    def VALIDATE_INPUTS(cls, latent=None, conditioning=MATCH_LATENT, sigmas=None,
                        LoRa_1_enabled=None, LoRa_1=None, LoRa_1_strength=None,
                        LoRa_2_enabled=None, LoRa_2=None, LoRa_2_strength=None,
                        LoRa_3_enabled=None, LoRa_3=None, LoRa_3_strength=None):
        problem = check(latent, conditioning)
        if problem:
            return problem
        if sigmas is not None:
            try:
                parse_sigmas(sigmas)
            except ValueError as e:
                return "2in1 Revitalizer: " + str(e)
        # v0.0.9c: a LoRa_n file is only checked while that LoRa_n is ON (a saved name that is not installed must not block the run when it is OFF)
        slots = {1: (LoRa_1_enabled, LoRa_1, LoRa_1_strength), 2: (LoRa_2_enabled, LoRa_2, LoRa_2_strength), 3: (LoRa_3_enabled, LoRa_3, LoRa_3_strength)}
        for n, (enabled, name, strength) in slots.items():
            problem = slot_problem(n, enabled, name, strength)
            if problem:
                return problem
        return True

    # --- re-run when a file is overwritten
    @classmethod
    def IS_CHANGED(cls, latent=None, conditioning=MATCH_LATENT, **kw):
        try:
            files = [latent, sibling(latent, "audio"),
                     sibling(latent, "cond") if conditioning in (None, "", MATCH_LATENT) else conditioning]
            return "|".join(_stamp(locate(f)) for f in files)
        except ValueError:
            return ""

    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_latent(path):
        import safetensors.torch
        data = safetensors.torch.load_file(path, device="cpu")
        if "latent_tensor" not in data:
            raise ValueError(f"'{os.path.basename(path)}' is not a ComfyUI .latent file (no latent_tensor).")
        scale = 1.0 if "latent_format_version_0" in data else 1.0 / 0.18215      # what Load Latent does
        return {"samples": data["latent_tensor"].float() * scale}

    @staticmethod
    def _read_size(path):
        """(width, height) the MTV wrote into the file's metadata, else a safe default."""
        try:
            from safetensors import safe_open
            with safe_open(path, framework="pt", device="cpu") as f:
                info = json.loads((f.metadata() or {}).get("ironleo78", "{}"))
            return max(8, int(info["width"])), max(8, int(info["height"]))
        except Exception:
            return 512, 512

    def _load_clip(self, latent, conditioning, freeze_audio):
        """The 2in1 Shampoo, AV mode: (av_latent, conditioning, cond_rel)."""
        from .conditioning_io import load_conditioning

        problem = check(latent, conditioning)
        if problem:
            raise RuntimeError(problem)
        cond_rel = sibling(latent, "cond") if conditioning in (None, "", MATCH_LATENT) else conditioning
        cond = load_conditioning(locate(cond_rel))

        video = self._read_latent(locate(latent))
        audio_path = locate(sibling(latent, "audio"))
        audio = self._read_latent(audio_path)
        if freeze_audio:
            w, h = self._read_size(audio_path)
            mask = _call("SolidMask", value=0.0, width=w, height=h)[0]
            audio = _call("SetLatentNoiseMask", samples=audio, mask=mask)[0]
        av = _call("LTXVConcatAVLatent", video_latent=video, audio_latent=audio)[0]
        return av, cond, cond_rel

    def _build_model(self, unet_name, lora_on, lora_name, lora_strength, attention_backend, log, slots=()):
        """UNET -> the LoRA (Turbo slot) -> LoRa_1 -> LoRa_2 -> LoRa_3 (v0.0.9c, each only when ON, the same order as the MTV) -> attention."""
        if _is_missing(unet_name):
            raise RuntimeError("2in1 Revitalizer: no diffusion model selected (put one in models/diffusion_models).")
        # v0.1.5: a clone of the ONE base model shared with the MTV (model_cache.py), instead of ComfyUI's UNETLoader node
        # (which loaded its own copy from disk); the LoRAs below go on the clone
        base, shared = _models.diffusion_model(unet_name, WEIGHT_DTYPE)
        model = base.clone()
        if shared:
            log.append("diffusion model: already in memory (shared with the MTV / an earlier run), not read from disk")
        if lora_on:
            if _is_missing(lora_name) or lora_name == LORA_NONE:
                raise RuntimeError("2in1 Revitalizer: LoRA is ON but no LoRA file is selected.")
            model = _call("LoraLoaderModelOnly", model=model, lora_name=lora_name, strength_model=float(lora_strength))[0]
            log.append(f"LoRA ON: {lora_name} x{lora_strength:g}")
        else:
            log.append("LoRA OFF")
        for n, enabled, name, strength in slots:
            if not enabled:
                continue
            if name in (None, "", SLOT_NONE, LORA_NONE) or str(name).startswith("(none"):
                raise RuntimeError(f"2in1 Revitalizer: LoRa_{n} is ON but no LoRA file is selected.")
            model = _call("LoraLoaderModelOnly", model=model, lora_name=name, strength_model=float(strength))[0]
            log.append(f"LoRa_{n} ON: {name} x{float(strength):g}")
        if attention_backend != ATTENTION[2]:
            if _has("ModelAttentionBackend"):
                model = _call("ModelAttentionBackend", model=model, attention=attention_backend)[0]
                log.append(f"attention: {attention_backend}")
            else:
                log.append("attention backend node not in this ComfyUI: skipped")
        return model

    def _model_cached(self, unet_name, lora_on, lora_name, lora_strength, attention_backend, log, slots):
        """v0.1.4: _build_model, kept between runs. The status gets the same LoRA / attention lines as when it is built."""
        key = (_file_stamp("diffusion_models", unet_name), WEIGHT_DTYPE,
               (_file_stamp("loras", lora_name), float(lora_strength)) if lora_on else None,
               tuple((n, _file_stamp("loras", name), float(strength)) for n, enabled, name, strength in slots if enabled),
               attention_backend)

        def build():
            lines = []
            return self._build_model(unet_name, lora_on, lora_name, lora_strength, attention_backend, lines, slots), lines

        (model, lines), hit = _cached("model", key, build)
        log.extend(lines)
        if hit:
            log.append("model: kept from the previous run (same files, LoRAs and strengths: not loaded again)")
        return model, hit

    @staticmethod
    def _vae_cached(name):
        """v0.1.4: a VAE, kept between runs (the video and the audio VAE: two entries)."""
        return _cached("vae", _file_stamp("vae", name), lambda: _call("VAELoader", vae_name=name)[0])

    def revitalize(self, **kw):
        """Runs the chain; every step (and any error, with a tip) is printed in the ComfyUI console."""
        live = Live()
        try:
            return self._run(live, **kw)
        except BaseException as e:                              # includes the user pressing Cancel
            live.error(e if not isinstance(e, KeyboardInterrupt) else RuntimeError("Interrupted by the user."))
            raise

    def _run(self, live, latent, conditioning, freeze_audio,
             unet_name, vae_video, vae_audio, lora_on, lora_name, lora_strength, attention_backend,
             upscale_on, upscale_model, megapixels,
             temporal_chunking, force_unload, upscale_device, upscale_precision,
             seed, sampler_name, sigmas=DEF_SIGMAS, **extra):
        log = [f"clip: {latent}"]
        # v0.0.9c: LoRa_1 .. LoRa_3 are optional inputs: an old API prompt without them runs with all three OFF
        slots = [(n,) + lora_slot(extra, n) for n in range(1, LORA_SLOTS + 1)]

        # 1. a wrong setting should fail before any heavy work
        live.start(0)
        try:
            sig_list = parse_sigmas(sigmas)
        except ValueError as e:
            raise RuntimeError("2in1 Revitalizer: " + str(e))
        if _is_missing(vae_video) or _is_missing(vae_audio):
            raise RuntimeError("2in1 Revitalizer: select the video VAE and the audio VAE (models/vae).")
        if _is_missing(unet_name):
            raise RuntimeError("2in1 Revitalizer: no diffusion model selected (put one in models/diffusion_models).")
        # (v0.1.7: no upscale model / no upscaler node is not an error any more: the built-in latent resize takes over)
        problem = check(latent, conditioning)
        if problem:
            raise RuntimeError(problem)
        for n, enabled, name, strength in slots:
            problem = slot_problem(n, enabled, name, strength)
            if problem:
                raise RuntimeError(problem)

        # 2. the clip
        live.start(1, os.path.basename(latent))
        av, cond, cond_rel = self._load_clip(latent, conditioning, freeze_audio)
        log.append(f"conditioning: {cond_rel}")

        # 3. upscale the video part only, audio goes back untouched
        if upscale_on:
            # v0.1.7: the third-party Minimax H3 Latent Upscaler is used when it is installed AND a model file is there;
            # otherwise the built-in latent resize (resize_video_latent) does the upscale and the refine pass below redraws the detail
            why = ("" if _has(UPSCALER_NODE) and not _is_missing(upscale_model) else
                   "the Minimax H3 Latent Upscaler node is not installed" if not _has(UPSCALER_NODE) else
                   "no model file in models/latent_upscale_models")
            live.start(2, f"{megapixels:g} MP" + (", built in" if why else ""))
            video_l, audio_l = _call("LTXVSeparateAVLatent", av_latent=av)
            if not why:
                mode = {"mode": "megapixels", "megapixels": round(float(megapixels), 2)}
                video_l = _call(UPSCALER_NODE, latent=video_l, model_name=upscale_model, mode=mode,
                                align=ALIGN, enable_temporal_chunking=bool(temporal_chunking),
                                force_unload=bool(force_unload), device=upscale_device, precision=upscale_precision)[0]
                log.append(f"upscale: {megapixels:g} MP (Minimax H3 Latent Upscaler 3D, {upscale_model})")
            else:
                video_l, (tw, th) = resize_video_latent(video_l, megapixels)
                log.append(f"upscale: {megapixels:g} MP built in: latent resized to {tw}x{th} ({why}); the refine pass redraws the detail")
            av = _call("LTXVConcatAVLatent", video_latent=video_l, audio_latent=audio_l)[0]
            del video_l, audio_l
        else:
            live.skip(2, "upscale OFF")
            log.append("upscale: OFF")

        # 4. model
        live.start(3, os.path.splitext(os.path.basename(unet_name))[0])
        model, kept = self._model_cached(unet_name, lora_on, lora_name, lora_strength, attention_backend, log, slots)
        if kept:
            live.cur_detail += " (kept from the previous run)"

        # 5. sampling
        live.start(4, f"{sampler_name}, {len(sig_list) - 1} steps, seed {seed}")
        import torch
        guider = _call("BasicGuider", model=model, conditioning=cond)[0]
        noise = _call("RandomNoise", noise_seed=int(seed))[0]
        sampler = _call("KSamplerSelect", sampler_name=sampler_name)[0]
        sig = torch.FloatTensor(sig_list)
        out = _call("SamplerCustomAdvanced", noise=noise, guider=guider, sampler=sampler, sigmas=sig, latent_image=av)[0]
        log.append(f"sampling: {sampler_name}, seed {seed}, {len(sig_list) - 1} steps")
        log.append("sigmas: " + ", ".join(f"{x:g}" for x in sig_list))
        del model, guider, av

        # 6. decode (the same refined AV latent goes to both VAEs, as in the workflow)
        live.start(5)
        vv, kept_v = self._vae_cached(vae_video)          # v0.1.4: kept between runs
        images = _call("VAEDecode", samples=out, vae=vv)[0]
        del vv
        live.start(6)
        va, kept_a = self._vae_cached(vae_audio)
        audio = _call("VAEDecodeAudio", samples=out, vae=va)[0]
        del va
        if kept_v and kept_a:
            log.append("VAEs: kept from the previous run")

        # 7. video
        live.start(7, f"{FPS:g} fps")
        try:
            video = _call("CreateVideo", images=images, fps=FPS, audio=audio, bit_depth=BIT_DEPTH,
                          color_space=COLOR_SPACE, codec="none")[0]
        except TypeError:                                   # an older CreateVideo without the extra options
            video = _call("CreateVideo", images=images, fps=FPS, audio=audio)[0]
        try:
            n, h, w = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
            log.append(f"video: {w}x{h}, {n} frames, {FPS:g} fps")
            size_note = f"{w}x{h}, {n} frames"
        except Exception:
            size_note = ""

        # no save step (v0.0.9): the `video` output goes to the user's own Save Video node
        live.done(size_note)

        used = {"unet_name": unet_name, "lora_name": lora_name, "vae_video": vae_video, "vae_audio": vae_audio, "seed": int(seed)}
        for n, enabled, name, strength in slots:
            used.update({f"LoRa_{n}_enabled": enabled, f"LoRa_{n}": name, f"LoRa_{n}_strength": float(strength)})
        report = set_report(used)
        if report:
            log.append(report)
        status = live.text + "\n\n" + "\n".join(log)      # v0.0.9w: live.text already starts with the node's name (it was printed twice)
        return {"result": (video, images, audio, out, status)}


def _samplers():
    try:
        import comfy.samplers
        return list(comfy.samplers.KSampler.SAMPLERS)
    except Exception:
        return ["euler"]


async def save_upload_part(part, target):
    """One uploaded file -> `target`, written to a temporary file first and renamed only when complete.
    v0.1.9: when the upload breaks off (a closed tab, a full disk), the half-written temporary file is removed (it used to stay
    in input/ironleo78_revitalizer/), and the error still reaches the caller."""
    tmp = target + ".tmp"
    try:
        with open(tmp, "wb") as f:
            while True:
                chunk = await part.read_chunk(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError as e:
                _log.debug("could not remove '%s' (%s)", tmp, e)


def _register_routes():
    """POST /ironleo78/revitalizer/upload: what the node's Upload button calls. Saves .latent / .conditioning
    files into ComfyUI/input/ironleo78_revitalizer/ (nothing else is accepted)."""
    try:
        from aiohttp import web
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception:
        return                                                  # not running inside ComfyUI (tests)

    @routes.get(SET_ROUTE)
    async def saved_set_route(request):
        """v0.0.9c: the Model Loader's saved set, already translated to this node's widget names (the node's button and the
        Model Loader's Set New Defaults call it)."""
        values, control = saved_set()
        return web.json_response({"ok": True, "custom": bool(values), "values": values, "seed_control": control})

    @routes.post("/ironleo78/revitalizer/upload")
    async def upload(request):
        reader = await request.multipart()
        folder = _upload_root()
        os.makedirs(folder, exist_ok=True)
        saved, refused = [], []
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.filename is None:
                continue
            name = clean_upload_name(part.filename)
            if name is None:
                refused.append(part.filename)
                await part.read()                               # drain it
                continue
            target = os.path.join(folder, name)
            await save_upload_part(part, target)
            saved.append(name)
        return web.json_response({"saved": saved, "refused": refused})


_register_routes()

NODE_CLASS_MAPPINGS = {"IronLeo78_2in1_Revitalizer": IronLeo78_2in1_Revitalizer}
NODE_DISPLAY_NAME_MAPPINGS = {"IronLeo78_2in1_Revitalizer": "IronLeo78 2in1 Revitalizer"}
