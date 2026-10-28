"""
IronLeo78 2in1 Revitalizer  v0.4
------------------------------------------------------------
STANDALONE all-in-one custom node. It replaces the whole "H3 Latent Upscale" workflow in ONE node:

    load first-pass latent + conditioning saved by the IronLeo78 MTV
      -> (optional) model: UNET loader, turbo LoRA ON/OFF, attention backend
      -> Separate AV latent -> Minimax H3 Latent Upscaler (3D) -> Concat AV latent
      -> BasicGuider + SamplerCustomAdvanced (RandomNoise, sampler, fixed 5-step sigmas)
      -> VAE Decode (video, normal) + VAE Decode Audio
      -> Create Video (24 fps, 8 bit, sRGB, audio) -> Save Video (always, auto)

Outputs: the video, the images, the audio, the refined AV latent and a STATUS text (the steps are also
printed in the ComfyUI console).

The MTV saves, next to every clip (Save Latent ON):

    output/<Song>/<Song>_seg004_A_00001_video.latent
    output/<Song>/<Song>_seg004_A_00001_audio.latent
    output/<Song>/<Song>_seg004_A_00001.conditioning

Both the latent and the conditioning are chosen from dropdowns that list ComfyUI/output (newest first; press R to
refresh) plus uploaded files. The "Upload latent / conditioning files" button copies files from anywhere on your
computer into ComfyUI/input/ironleo78_revitalizer/ and selects them.

Fixed inside the node (no widget): weight dtype default, align 32, bit depth 8, color space sRGB, 24 fps, the 5-step sigmas
(0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000), normal VAE decode, and the video is always saved (format / codec / quality auto).

Needs, besides ComfyUI itself (recent enough to have LTXVSeparateAVLatent / LTXVConcatAVLatent, CreateVideo and the
V3 video API): the third-party node "Comfyui_Minimax_h3_latent_Upscaler" (only when upscale is ON) and its model in
models/latent_upscale_models/. Every other step uses core ComfyUI nodes, called by name, so they behave exactly as in
your workflow.
"""

import json
import os
import time

import folder_paths

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
DEF_UPSCALER = "h3_upscaler_lms_v0.1.safetensors"
SIGMAS = [0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000]      # fixed: the 5-step refine
WEIGHT_DTYPE = "default"                                         # fixed
ALIGN = 32                                                       # fixed
BIT_DEPTH = 8                                                    # fixed
COLOR_SPACE = "sRGB"                                             # fixed
DEF_PREFIX = "video/MiniMax_H3"

ATTENTION = ["comfy kitchen attention", "pytorch attention", "(leave the model untouched)"]
FPS = 24.0                                  # frozen (not shown on the node)

LORA_NONE = "(none)"


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
                except OSError:
                    pass
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


def _save_video(video, prefix, fmt, codec, crf, prompt, extra_pnginfo):
    """Same as ComfyUI's SaveVideo node (same file names, same preview). Returns (file, subfolder, full path)."""
    try:
        from comfy_api.latest import Types
    except ImportError:
        raise RuntimeError("2in1 Revitalizer: this ComfyUI is too old (no comfy_api.latest video types). Update ComfyUI.")
    width, height = video.get_dimensions()
    out_dir, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
        prefix, folder_paths.get_output_directory(), width, height)
    container = fmt
    if container == "auto":
        container = "webm" if codec == "av1" else "mp4"
    file = f"{filename}_{counter:05}_.{Types.VideoContainer.get_extension(container)}"
    full = os.path.join(out_dir, file)

    metadata = None
    try:
        from comfy.cli_args import args
        disabled = bool(args.disable_metadata)
    except Exception:
        disabled = False
    if not disabled:
        meta = {}
        if extra_pnginfo is not None:
            meta.update(extra_pnginfo)
        if prompt is not None:
            meta["prompt"] = prompt
        metadata = meta or None

    kw = dict(format=Types.VideoContainer(container), codec=Types.VideoCodec(codec), metadata=metadata)
    if crf is not None and crf >= 0:
        kw["crf"] = float(crf)
    try:
        video.save_to(full, **kw)
    except TypeError:                                   # an older ComfyUI without crf
        kw.pop("crf", None)
        video.save_to(full, **kw)
    return file, subfolder, full



# ---------------------------------------------------------------------- #
# live status: what the node is doing right now, sent to the status box on the node
# ---------------------------------------------------------------------- #
STAGES = ["Checking settings", "Loading clip", "Upscaling latent", "Loading model", "Sampling",
          "Decoding video", "Decoding audio", "Building video", "Saving video"]


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
        return {
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
                "unet_name": (unets, {"default": _default(unets, DEF_UNET), "tooltip": "Diffusion model (UNETLoader)."}),
                "vae_video": (vaes, {"default": _default(vaes, DEF_VAE_VIDEO), "tooltip": "H3 video VAE."}),
                "vae_audio": (vaes, {"default": _default(vaes, DEF_VAE_AUDIO), "tooltip": "H3 audio VAE."}),
                "lora_on": ("BOOLEAN", {"default": False, "label_on": "LoRA ON", "label_off": "LoRA OFF",
                                        "tooltip": "The 'LoRa OFF/ON' switch of the workflow (model-only LoRA, e.g. the 4-step turbo)."}),
                "lora_name": (loras, {"default": _default(loras, DEF_LORA)}),
                "lora_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "attention_backend": (ATTENTION, {"default": ATTENTION[0],
                                                  "tooltip": "Model Attention Backend. 'comfy kitchen attention' falls back to "
                                                             "PyTorch attention by itself when it is not available."}),
                # ---- 3. latent upscale (Minimax H3 Latent Upscaler 3D)
                "upscale_on": ("BOOLEAN", {"default": True, "label_on": "Upscale ON", "label_off": "Upscale OFF",
                                           "tooltip": "OFF: refine at the saved size (no Separate / Upscaler / Concat)."}),
                "upscale_model": (upscalers, {"default": _default(upscalers, DEF_UPSCALER)}),
                "megapixels": ("FLOAT", {"default": 2.0, "min": 0.1, "max": 2.0, "step": 0.1, "tooltip": "Target size of the upscaled video, in megapixels (max 2.0)."}),
                "temporal_chunking": ("BOOLEAN", {"default": True}),
                "force_unload": ("BOOLEAN", {"default": True, "tooltip": "Unload the upscale model to CPU afterwards to free VRAM."}),
                "upscale_device": (["cuda", "rocm", "cpu"], {"default": "cuda"}),
                "upscale_precision": (["fp16", "bf16", "fp32"], {"default": "fp16"}),
                # ---- 4. sampling
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True,
                                 "tooltip": "Use the clip's own seed to repeat it (the refine pass should use the same seed)."}),
                "sampler_name": (_samplers(), {"default": "euler"}),
                # ---- 5. saving
                "filename_prefix": ("STRING", {"default": DEF_PREFIX, "tooltip": "The video is always saved (format, codec and quality: auto)."}),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ("VIDEO", "IMAGE", "AUDIO", "LATENT", "STRING")
    RETURN_NAMES = ("video", "images", "audio", "latent", "status")
    FUNCTION = "revitalize"
    CATEGORY = "IronLeo78/MTV"
    OUTPUT_NODE = True
    DESCRIPTION = (
        "All-in-one: loads a first-pass latent + conditioning saved by the IronLeo78 MTV, upscales the video "
        "latent (Minimax H3 Latent Upscaler 3D), refines it (guider + sampler + sigmas), decodes video and audio, builds the "
        "video and saves it.\nby IronLeo78"
    )

    # --- validation: the lists are read from disk, so the combo check is replaced by a file check
    @classmethod
    def VALIDATE_INPUTS(cls, latent=None, conditioning=MATCH_LATENT):
        return check(latent, conditioning) or True

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

    def _build_model(self, unet_name, lora_on, lora_name, lora_strength, attention_backend, log):
        if _is_missing(unet_name):
            raise RuntimeError("2in1 Revitalizer: no diffusion model selected (put one in models/diffusion_models).")
        model = _call("UNETLoader", unet_name=unet_name, weight_dtype=WEIGHT_DTYPE)[0]
        if lora_on:
            if _is_missing(lora_name) or lora_name == LORA_NONE:
                raise RuntimeError("2in1 Revitalizer: LoRA is ON but no LoRA file is selected.")
            model = _call("LoraLoaderModelOnly", model=model, lora_name=lora_name, strength_model=float(lora_strength))[0]
            log.append(f"LoRA ON: {lora_name} x{lora_strength:g}")
        else:
            log.append("LoRA OFF")
        if attention_backend != ATTENTION[2]:
            if _has("ModelAttentionBackend"):
                model = _call("ModelAttentionBackend", model=model, attention=attention_backend)[0]
                log.append(f"attention: {attention_backend}")
            else:
                log.append("attention backend node not in this ComfyUI: skipped")
        return model

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
             seed, sampler_name, filename_prefix,
             prompt=None, extra_pnginfo=None):
        log = [f"clip: {latent}"]

        # 1. a wrong setting should fail before any heavy work
        live.start(0)
        sig_list = SIGMAS
        if _is_missing(vae_video) or _is_missing(vae_audio):
            raise RuntimeError("2in1 Revitalizer: select the video VAE and the audio VAE (models/vae).")
        if _is_missing(unet_name):
            raise RuntimeError("2in1 Revitalizer: no diffusion model selected (put one in models/diffusion_models).")
        if upscale_on and _is_missing(upscale_model):
            raise RuntimeError("2in1 Revitalizer: no upscale model found in models/latent_upscale_models.")
        problem = check(latent, conditioning)
        if problem:
            raise RuntimeError(problem)

        # 2. the clip
        live.start(1, os.path.basename(latent))
        av, cond, cond_rel = self._load_clip(latent, conditioning, freeze_audio)
        log.append(f"conditioning: {cond_rel}")

        # 3. upscale the video part only, audio goes back untouched
        if upscale_on:
            live.start(2, f"{megapixels:g} MP")
            video_l, audio_l = _call("LTXVSeparateAVLatent", av_latent=av)
            mode = {"mode": "megapixels", "megapixels": round(float(megapixels), 2)}
            video_l = _call("MinimaxH3LatentUpscaler3D", latent=video_l, model_name=upscale_model, mode=mode,
                            align=ALIGN, enable_temporal_chunking=bool(temporal_chunking),
                            force_unload=bool(force_unload), device=upscale_device, precision=upscale_precision)[0]
            av = _call("LTXVConcatAVLatent", video_latent=video_l, audio_latent=audio_l)[0]
            del video_l, audio_l
            log.append(f"upscale: {megapixels:g} MP")
        else:
            live.skip(2, "upscale OFF")
            log.append("upscale: OFF")

        # 4. model
        live.start(3, os.path.splitext(os.path.basename(unet_name))[0])
        model = self._build_model(unet_name, lora_on, lora_name, lora_strength, attention_backend, log)

        # 5. sampling
        live.start(4, f"{sampler_name}, {len(sig_list) - 1} steps, seed {seed}")
        import torch
        guider = _call("BasicGuider", model=model, conditioning=cond)[0]
        noise = _call("RandomNoise", noise_seed=int(seed))[0]
        sampler = _call("KSamplerSelect", sampler_name=sampler_name)[0]
        sig = torch.FloatTensor(sig_list)
        out = _call("SamplerCustomAdvanced", noise=noise, guider=guider, sampler=sampler, sigmas=sig, latent_image=av)[0]
        log.append(f"sampling: {sampler_name}, seed {seed}, {len(sig_list) - 1} steps")
        del model, guider, av

        # 6. decode (the same refined AV latent goes to both VAEs, as in the workflow)
        live.start(5)
        vv = _call("VAELoader", vae_name=vae_video)[0]
        images = _call("VAEDecode", samples=out, vae=vv)[0]
        del vv
        live.start(6)
        va = _call("VAELoader", vae_name=vae_audio)[0]
        audio = _call("VAEDecodeAudio", samples=out, vae=va)[0]
        del va

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

        # 8. save (always)
        live.start(8, filename_prefix)
        file, subfolder, full = _save_video(video, filename_prefix, "auto", "auto", None, prompt, extra_pnginfo)
        ui = {"images": [{"filename": file, "subfolder": subfolder, "type": "output"}], "animated": (True,)}
        log.append(f"saved: {full}")
        live.done(size_note)

        status = live.text + "\n\n" + "IronLeo78 2in1 Revitalizer v0.4\n" + "\n".join(log)
        return {"ui": ui, "result": (video, images, audio, out, status)}


def _samplers():
    try:
        import comfy.samplers
        return list(comfy.samplers.KSampler.SAMPLERS)
    except Exception:
        return ["euler"]


def _register_routes():
    """POST /ironleo78/revitalizer/upload: what the node's Upload button calls. Saves .latent / .conditioning
    files into ComfyUI/input/ironleo78_revitalizer/ (nothing else is accepted)."""
    try:
        from aiohttp import web
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception:
        return                                                  # not running inside ComfyUI (tests)

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
            tmp = target + ".tmp"
            with open(tmp, "wb") as f:
                while True:
                    chunk = await part.read_chunk(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, target)
            saved.append(name)
        return web.json_response({"saved": saved, "refused": refused})


_register_routes()

NODE_CLASS_MAPPINGS = {"IronLeo78_2in1_Revitalizer": IronLeo78_2in1_Revitalizer}
NODE_DISPLAY_NAME_MAPPINGS = {"IronLeo78_2in1_Revitalizer": "IronLeo78 2in1 Revitalizer"}
