"""IronLeo78-MTV-Prompt-Generator (v0.1.18): the 9-Images-to-batch-to-LLM loader and the MTV-LLM Prompt Generator subgraph in ONE node.

Same pictures / video / Start_From / Duration / Frame_Interval / Video_Size / Preset widgets as the loader (same web UI), plus the
user's prompt and the LLM file. It builds the batch and the LLM text exactly like the loader, runs ComfyUI's own "Generate Text"
(TextGenerate) with the Claude Minimax guide (guide/Claude.Minimax.md) as the system prompt, and returns Pictures (all nine slots on one wire for the MTV node) followed by
MTV_Prompt, the text for the MTV node's prompt. The LLM settings the user does not need are fixed here.
"""
import gc
import hashlib
import os

import folder_paths

from .nine_images import IronLeo78_9ImagesToBatchToLLM as _Loader, SLOTS, preset_prompts, preset_audio_info
from .mtv import PICTURES_TYPE

NODE_ID = "IronLeo78_MTV_PromptGenerator"
GUIDE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guide", "Claude.Minimax.md")
DEFAULT_LLM = "Huihui-Qwen3-VL-4B-Instruct-abliterated-int8_convrot.safetensors"
CLIP_TYPE = "ideogram4"                    # how ComfyUI loads this Qwen3-VL text encoder (same as the subgraph's CLIPLoader)
MAX_LENGTH = 8192
SAMPLING = {"sampling_mode": "on", "temperature": 0.7, "top_k": 64, "top_p": 0.95, "min_p": 0.05,
            "repetition_penalty": 1.05, "seed": 0, "presence_penalty": 0.0}


def _llm_files():
    try:
        return list(folder_paths.get_filename_list("text_encoders"))
    except Exception:
        return []


def _read_guide():
    with open(GUIDE_FILE, encoding="utf-8-sig") as f:
        return f.read().strip()


def build_request(frame_text, user_prompt):
    """What the LLM is asked: the loader's text (frame layout + times + preset), then the user's own prompt."""
    return "\n\n".join(p for p in (frame_text, (user_prompt or "").strip()) if p)


def generate(clip, request, image, system_prompt, seed=0):
    """ComfyUI's own Generate Text node, with the fixed settings above."""
    from comfy_extras.nodes_textgen import TextGenerate
    out = TextGenerate.execute(clip=clip, prompt=request, max_length=MAX_LENGTH, sampling_mode=dict(SAMPLING, seed=int(seed)), image=image,
                               thinking=False, use_default_template=True, mtp="auto", system_prompt=system_prompt)
    return out.args[0]


def _load_clip(name):
    import nodes
    return nodes.CLIPLoader().load_clip(name, CLIP_TYPE, "default")[0]


# v0.3.16: the switch "Keep LLM in RAM": the loaded model stays referenced between runs (only the GPU is freed), so the next run skips the
# read from disk. Key: file name + its date; v0.3.17: up to KEEP_MAX models (two Generators with two LLMs do not swap each run), the least
# recently used one is dropped. Off (the default): nothing is kept and the RAM is given back.
KEEP_MAX = 2
_KEPT = {}                      # key -> clip, oldest first


def _drop_kept():
    _KEPT.clear()
    gc.collect()


def _clip_key(name):
    try:
        import folder_paths as _fp
        return (name, os.stat(_fp.get_full_path("text_encoders", name)).st_mtime_ns)
    except Exception:
        return (name, None)


def _get_clip(name, keep):
    """-> (clip, reused). With keep: the kept model when it is the same file, else a fresh load that is kept; without keep: a fresh load and
    whatever was kept is dropped first."""
    key = _clip_key(name)
    for k in [k for k in _KEPT if k[0] == name and k != key]:      # the same name with another file date: the old copy is stale
        del _KEPT[k]
    if keep and key in _KEPT:
        _KEPT[key] = _KEPT.pop(key)                                # most recently used goes last
        print("[IronLeo78] LLM reused from RAM (no reload from disk)")
        return _KEPT[key], True
    if not keep:
        _KEPT.clear()                                              # the switch is off: give the RAM back
    while len(_KEPT) >= KEEP_MAX:
        del _KEPT[next(iter(_KEPT))]
    gc.collect()
    clip = _load_clip(name)
    if keep:
        _KEPT[key] = clip
    return clip, False


def _vram_mb():
    """v0.3.7: GPU memory in use by this process in MB, or None without CUDA (used only for the unload log line)."""
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / (1024 * 1024)
    except Exception:
        pass
    return None


def _needs_forced_unload(base, before, after):
    """v0.3.12: True when the LLM is still sitting in GPU memory after the normal unload: it added more than 512 MB (before - base) and
    less than 70 % of that went away (before - after). Memory already used before the LLM (base) is never counted."""
    if base is None or before is None or after is None:
        return False
    used = before - base
    return used > 512 and (before - after) < 0.7 * used


def _force_unload():
    """Ask ComfyUI's model manager to unload everything (the other models reload on demand): the fallback when the LLM stayed on the GPU, and
    the way the kept LLM (Keep LLM in RAM) leaves the GPU while its CPU copy stays referenced by _CLIP."""
    gc.collect()
    try:
        import comfy.model_management as mm
        mm.unload_all_models()
        mm.soft_empty_cache()
    except Exception:
        pass


def _offload_clip(clip):
    """v0.4.4: the kept LLM leaves the GPU and ONLY it: ComfyUI's unload_model_and_clones keeps every other loaded model (the MTV / Revitalizer
    diffusion models) on the GPU. An older ComfyUI without it, or any error: the old way (unload everything)."""
    gc.collect()
    try:
        import comfy.model_management as mm
        mm.unload_model_and_clones(clip.patcher)
        mm.soft_empty_cache()
    except Exception:
        _force_unload()


def _free():
    gc.collect()
    try:
        import comfy.model_management as mm
        mm.soft_empty_cache()
    except Exception:
        pass


class IronLeo78_MTV_PromptGenerator(_Loader):
    @classmethod
    def INPUT_TYPES(cls):
        required = _Loader.INPUT_TYPES()["required"]
        required["prompt"] = ("STRING", {"default": "", "multiline": True,
                                         "tooltip": "Your short request, e.g. 'Replace the main character of Video 1.' "
                                                    "The preset and the frame information are added for you."})
        files = _llm_files()
        required["LLM"] = (files if files else [DEFAULT_LLM],
                           {"default": DEFAULT_LLM if (DEFAULT_LLM in files or not files) else files[0],
                            "tooltip": "The vision LLM (a Qwen3-VL text encoder in models/text_encoders)."})
        # v0.1.25: appended LAST (a saved workflow without it gets ON). OFF = no LLM at all: MTV_Prompt is the prompt as typed.
        required["Use LLM"] = ("BOOLEAN", {"default": True, "label_on": "LLM ON", "label_off": "LLM OFF",
                                           "tooltip": "ON: the LLM writes MTV_Prompt from the pictures, the video, the Preset and your prompt. "
                                                      "OFF: the LLM is not loaded or run, and MTV_Prompt is your prompt exactly as typed "
                                                      "(Pictures still go to the MTV)."})
        # v0.2.5: appended LAST (a saved workflow without it gets v2v). i2v = no video: Picture 1 is the SCENE that replaces Video 1.
        required["Mode"] = (["v2v", "i2v"], {"default": "v2v",
                                             "tooltip": "v2v: the presets work on the video you load (Picture 1 = the first character, as before). "
                                                        "i2v: no video; Picture 1 becomes the SCENE that replaces Video 1 and the characters move up one slot "
                                                        "(preset 1: Picture 2 = the new character). A loaded video is ignored in i2v."})
        # v0.3.6: the LLM seed, appended LAST (a saved workflow without it gets 0 / fixed). "control after generate" = fixed by default: the
        # same inputs give the same text (and ComfyUI keeps the result); set it to randomize, or change the seed, to re-roll.
        required["Seed"] = ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True,
                                    "tooltip": "Seed of the LLM. Same seed + same inputs = the same MTV_Prompt. Change it, or set control after generate to randomize, to get another text."})
        # v0.3.16: appended LAST (v0.4.3: ON by default; a saved workflow without it gets ON too). ON: the LLM stays in RAM between runs (about the size of its file) and only leaves the GPU: no reload from disk next time.
        required["Keep LLM in RAM"] = ("BOOLEAN", {"default": True, "label_on": "LLM kept in RAM", "label_off": "LLM unloaded",
                                                   "tooltip": "OFF: the LLM is unloaded after each run and read from disk again next time. "
                                                              "ON (default): it stays in RAM (about the size of its file, several GB) and only leaves the GPU, so the next run starts faster. "
                                                              "Choosing another LLM file, or switching this OFF, gives the RAM back."})
        return {"required": required}

    # v0.1.19: the nine pictures leave on ONE wire (a list of nine; empty slot = the grey NONE picture) into the MTV's `Pictures` input
    RETURN_TYPES = (PICTURES_TYPE, "STRING")
    RETURN_NAMES = ("Pictures", "MTV_Prompt")
    CATEGORY = "IronLeo78/MTV"
    DESCRIPTION = ("9 pictures + 1 video + your prompt in one node. Pictures (the nine slots on one wire) goes to the MTV node's Pictures input; "
                   "MTV_Prompt (written by the LLM from the pictures, the video, the Preset and your prompt) goes to the MTV prompt.")

    @classmethod
    def IS_CHANGED(cls, **kw):
        """v0.3.4: the loader's hash (every widget, the pictures, the video, the preset file) + the guide file: editing the guide re-runs the node."""
        try:
            st = os.stat(GUIDE_FILE)
            g = f"{st.st_size}:{st.st_mtime_ns}"
        except OSError:
            g = ""
        kw = {k: v for k, v in kw.items() if k != "Keep LLM in RAM"}      # v0.3.17: the switch changes no text: toggling it must not re-run the LLM
        return hashlib.sha256(f"{_Loader.IS_CHANGED(**kw)}|guide:{g}".encode()).hexdigest()

    def run(self, Start_From, Duration, Frame_Interval, Video_Size, Preset="None", prompt="", LLM=DEFAULT_LLM, Mode="v2v", Seed=0, **kw):
        use_llm = kw.pop("Use LLM", True)           # v0.1.25 (the widget name has a space: it cannot be a parameter)
        keep_ram = bool(kw.pop("Keep LLM in RAM", True))       # v0.3.16 (v0.4.3: ON when not sent)
        if not use_llm:
            _drop_kept()                                                 # LLM OFF: nothing stays in RAM (v0.3.17, also with Keep ON)
            # v0.3.6: LLM OFF needs only the pictures: no video decode, no preset file, nothing about the LLM (the prompt is passed through)
            kw["video"] = ""
            out = super().run(Start_From, Duration, Frame_Interval, Video_Size, Preset="None", Mode=Mode, **kw)
            return (list(out[1:1 + SLOTS]), prompt)
        out = super().run(Start_From, Duration, Frame_Interval, Video_Size, Preset=Preset, Mode=Mode, **kw)
        batch, pics, frame_text = out[0], out[1:1 + SLOTS], out[-1]
        if LLM not in _llm_files():
            raise FileNotFoundError(f"LLM file not found in models/text_encoders: {LLM}")
        request = build_request(frame_text, prompt)
        base = _vram_mb()                           # v0.3.12: what the GPU already holds before the LLM
        clip, _reused = _get_clip(LLM, keep_ram)
        try:
            text = generate(clip, request, batch, _read_guide(), Seed)
        finally:
            before = _vram_mb()
            if keep_ram:
                _offload_clip(clip)                  # v0.3.16: the GPU is freed, the model stays in RAM (the cache keeps it); v0.4.4: only the LLM leaves
            else:
                del clip
                _free()                              # the MTV / Revitalizer get the VRAM back
            after = _vram_mb()
            if before is not None and after is not None:      # v0.3.7: the console shows whether the unload really freed the memory
                print(f"[IronLeo78] LLM {'left the GPU (kept in RAM)' if keep_ram else 'unloaded'}: GPU memory in use {before:.0f} MB -> {after:.0f} MB")
                if not keep_ram and _needs_forced_unload(base, before, after):      # v0.3.12: it did not: unload everything (the next model loads again when needed)
                    _force_unload()
                    after2 = _vram_mb()
                    print(f"[IronLeo78] the LLM was still in GPU memory: forced unload, now {after2:.0f} MB" if after2 is not None else "[IronLeo78] forced unload done")
        return (list(pics), text)


PRESETS_ROUTE = "/ironleo78/mtv/presets"


def _register_routes():
    """GET /ironleo78/mtv/presets -> {"presets": {name: suggested prompt}, "i2v": {...}} (v0.2.5: one map per mode): the node's Preset widget fills the prompt box with it."""
    try:
        from aiohttp import web
        from server import PromptServer
        routes = PromptServer.instance.routes
    except Exception:
        return                                                  # not running inside ComfyUI (tests)

    @routes.get(PRESETS_ROUTE)
    async def presets_route(request):
        info = preset_audio_info()
        return web.json_response({"ok": True, "presets": preset_prompts(), "i2v": preset_prompts("i2v"),
                                  "audio": {k: v["audio"] for k, v in info.items()}, "stems": {k: v["stem"] for k, v in info.items()}})


_register_routes()

NODE_CLASS_MAPPINGS = {NODE_ID: IronLeo78_MTV_PromptGenerator}
NODE_DISPLAY_NAME_MAPPINGS = {NODE_ID: "IronLeo78-MTV-Prompt-Generator"}
