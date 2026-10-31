"""
IronLeo78 MTV  v0.6.3  (pre-alpha)
------------------------------------------------------------
Makes a music video clip by clip, synced to YOUR audio (a singer / musician performance track).
Loader + MiniMax H3 reference-to-video conditioning + sampling + decode + save, in ONE node, one clip per Run.

  LOADS     diffusion model -> Turbo LoRA (toggle) -> custom LoRA (Model Loader) -> core Model
            Attention Backend; Qwen3-VL text encoder; video VAE + audio VAE.
  MEDIA     Custom Audio (the song) is cut into segment-long chunks, one per Run; an optional Video
            File can drive the frames (Use Video ON) or supply the soundtrack. Up to three reference
            pictures (singer / musician, location ...), megapixel sizing (multiples of 32), Minimax
            frame count.
  AUDIO     Choose Audio latent = Custom Audio (default) or Audio From Video: the audio chunk is encoded, frozen
            (noise mask 0) and joined to the video latent, so the model never invents sound; the picture follows
            the music. MiniMax Audio: no bypass, like the official ref2v template: the model's own latent goes
            straight to the sampler and the model generates the sound itself.
  SAMPLES   RandomNoise -> BasicGuider -> KSamplerSelect -> BasicScheduler -> SamplerCustomAdvanced,
            then VAE Decode / VAE Decode Audio and Create Video, all inside this node. v0.0.5: the node does NOT
            save the clip any more: Create Video's result leaves on the `video` output (link it to a Save Video node)
            and the clip's name on the `filename` output (the old file name, without extension).

To refine / upscale a clip later: switch Save Latent ON, then use the IronLeo78 2in1 Revitalizer node of this pack.

Where to start (no Start Frame / audio_start widgets)
  The segment counter at the top of the node decides where cutting starts. Segment 1 begins at second 0
  of the audio (or frame 0 of the video); every following segment is one real clip length later
  (frames / 24 fps, e.g. duration 5 s = 124 frames = 5.17 s). Jump to any segment N and the next Run
  starts at (N - 1) x segment length. Needs Next Segment On Run = ON to step through the file.

Selectable on the node
  Turbo                   ON (default) | OFF   (ON: Turbo LoRA, 4 steps. OFF: 40 steps, no Turbo LoRA.)
  Use Video / Video File / Custom Audio File / megapixels / duration / Next Segment On Run / prompt
  Audio Stem              Full | Vocals | Guitars | Drums | Bass   (right under Custom Audio File: which part of
                          the song is used. The first time a stem is chosen for a NEW song, Hybrid Demucs
                          separates all four and saves them to output/<Song>/stems/<Song>_<Stem>.wav; every
                          later Run, and every later session, just reads the file. See stems.py.)
  Choose Audio latent   MiniMax Audio | Audio From Video | Custom Audio   (Custom Audio / Audio From Video are
                          bypassed into the latent; Custom Audio is also stepped through segment by segment)
  Save Latent             OFF (default) | ON
  Guide
  (optional inputs Picture_1 ... Picture_9, IMAGE: the ONLY way to give reference pictures. Always on: a connected input is
   sent as <Picture n> (numbers count only the connected ones). No picker, no More References switch, no thumbnails. v0.0.9H)
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
import datetime
import gc
import hashlib
import json
import logging
import math
import os
import re
import sys

import numpy as np
import torch
import torch.nn.functional as F

import folder_paths
import comfy.sd
import comfy.utils
import nodes
import nodes as comfy_nodes

from . import stems as _stems
from . import conditioning_io as _cond_io
from . import model_cache as _models
from .consts import _truthy, NONE_CHOICE, RESIZE_METHOD, SCENE_TAG, MANIFEST_FIELDS, VIDEO_EXTS, AUDIO_EXTS
from .core_call import (_core, _preview_scope, _first_output)
from .naming import (_append_manifest, _clip_prefix, _project_name, _song_name, _write_sidecar)      # v0.3.17: moved to naming.py
from .media_decode import (_decode_audio, _decode_video, _fit_frame, _minimax_frames, _open_media, _resize, _resolve_video_path, _seek, _shape_video_frame, _target_size, _video_frame_plan)      # v0.3.17: moved to media_decode.py
from .state import (DATA_DIR, GUIDE_FRAME_IDX, LAST_FRAME_FILE, PACK_DIR, STATE_FILE, _STATE_LOCK, _clip_from_manifest, _clip_last_frame_array, _clip_saved_near, _counter_key, _counter_label, _data_dir, _handle_jump, _jump_to, _last_frame_file, _last_frame_of, _load_furthest, _load_index, _load_last_frame, _load_state, _move_old_data, _reset_state, _save_index, _save_last_frame, _write_state)
from .settings import (AUDIO_CACHE_MAX_BYTES, COND_CACHE_MAX, CORE_ATTN_NODE, CORE_VAE_NODE, CREDIT, DEFAULT_AUDIO_VAE, DEFAULT_CUSTOM_LORA, DEFAULT_CUSTOM_LORA_ENABLED, DEFAULT_DURATION, DEFAULT_FPS, DEFAULT_GUIDE, DEFAULT_MEGAPIXELS, DEFAULT_QWEN_VL, DEFAULT_SAVE_LATENT, DEFAULT_SEED, DEFAULT_TURBO_LORA, DEFAULT_UNET, DEFAULT_VIDEO_VAE, DENOISE, DIVISIBLE_BY, FIXED_SETTINGS, FREE_ROUTE, FULL_STEPS, JUMP_ROUTE, LOADER_DEFAULTS_ROUTE, LORA_SLOTS, MAX_REF_AUDIO_SECONDS, MIN_REF_AUDIO_SECONDS, MODELS_TYPE, MODEL_FILE_KEYS, NONE_LORA, PICTURES_INPUT, PICTURES_TYPE, PICTURE_INPUT, RESET_DEFAULTS_ROUTE, RESET_ROUTE, SAMPLER_NAME, SAVE_DEFAULTS_ROUTE, SAVE_FORMAT, SAVE_LATENT_MISSING, SCHEDULER_NAME, SEGMENT_ROUTE, TURBO_STEPS, VERSION, VIDEO_CODEC, VIDEO_COLOR_SPACE)
from .defaults import (DEFAULTS_FILE, _check_models, _defaults_stamp, _read_user_defaults, _read_user_seed_control, apply_model_overrides, apply_saved_defaults, clear_user_defaults, factory_defaults, loader_defaults, missing_default_files, save_user_defaults)

try:      # v0.0.5: a quiet stop (all segments done) must not feed anything to a Save Video linked to the outputs
    from comfy_execution.graph_utils import ExecutionBlocker
except Exception:      # an old / different ComfyUI: plain None outputs are used instead
    ExecutionBlocker = None
log = logging.getLogger("IronLeo78.MTV")

# v2.8: one clip per Run. The file tag / manifest "scene" value stays "A" so earlier clips and manifests still match.
MANIFEST_PROMPT_CHARS = 300   # the CSV shows this much of the prompt; the full text is in the clip's sidecar .json

# ---- shared stage cache (keeps models loaded while the media part re-runs)
# v2.2: keyed by stage + settings (file names + mtimes), NOT by node id: two nodes with the same
# models share one copy, and nothing is left behind per deleted node.
_CACHE = {}       # stage -> OrderedDict(key -> value)
_CACHE_LIMIT = {"model": 2}   # every other stage keeps one entry (v0.1.5: the 2 models are cheap clones of ONE shared base)
_LORA_CACHE = collections.OrderedDict()  # path -> loaded lora state dict (v0.1.5: up to LORA_CACHE_MAX, was 1)
LORA_CACHE_MAX = 4                       # the Turbo LoRA + LoRa_1-3: a chain is read from disk once, not once per rebuild
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


def _picture_input(i):
    """v0.0.9H: name of the optional IMAGE input of picture slot i (Picture_1 .. Picture_9)."""
    return PICTURE_INPUT.format(i)


def _spread_pictures(kw):
    """v0.1.19: the one `Pictures` input (list of up to nine pictures) fills the Picture_<n> inputs that are not wired on their own;
    everything after this point sees the same nine optional inputs as before. Removes `Pictures` from kw."""
    packed = kw.pop(PICTURES_INPUT, None)
    if not packed:
        return
    for i, img in enumerate(list(packed)[:9], start=1):
        if img is not None and kw.get(_picture_input(i)) is None:
            kw[_picture_input(i)] = img


def _linked_image(value):
    """v0.0.9H: an IMAGE coming from another node -> one [1,H,W,3] float picture (or None when nothing is linked).
    A batch gives its FIRST image (each socket feeds one slot); an alpha channel is dropped; a grey image is widened to RGB."""
    if value is None:
        return None
    img = value
    if len(img.shape) == 3:                       # [H,W,C] -> [1,H,W,C]
        img = img[None,]
    if len(img.shape) != 4:
        raise RuntimeError(f"expected an IMAGE [batch,height,width,channels], got shape {tuple(img.shape)}")
    img = img[:1]
    channels = int(img.shape[-1])
    if channels == 1:
        img = img.repeat(1, 1, 1, 3)
    elif channels >= 3:
        img = img[..., :3]
    else:
        raise RuntimeError(f"expected 1, 3 or 4 channels, got {channels}")
    return img.float().clamp(0, 1).contiguous()


NONE_PICTURE_MARK = "ironleo78_none"   # v0.0.9v: the IronLeo78-MTV-Prompt-Generator sets this attribute on its "NONE" pictures
_NONE_BG, _NONE_BORDER = 32 / 255.0, 90 / 255.0
_NONE_PROBES = ((0, 0, _NONE_BG), (511, 511, _NONE_BG), (2, 2, _NONE_BORDER), (509, 509, _NONE_BORDER),
                (2, 256, _NONE_BORDER), (256, 2, _NONE_BORDER))      # (y, x, value) on the 512x512 placeholder


def _is_none_placeholder(value):
    """v0.0.9v: True for the grey "NONE" picture the IronLeo78-MTV-Prompt-Generator sends from an EMPTY slot (inside its Pictures wire).
    It is not a reference: the slot counts as empty. Recognised by the loader's mark, else by its look (512x512, the grey
    background in the corners and the lighter border; a real picture matching all six probes exactly is not expected).
    Never raises: anything it cannot read is a real picture."""
    if value is None:
        return False
    if getattr(value, NONE_PICTURE_MARK, False) is True:
        return True
    try:
        if tuple(int(x) for x in value.shape) != (1, 512, 512, 3):
            return False
        return all(abs(float(value[0, y, x, c]) - want) < 1e-4 for y, x, want in _NONE_PROBES for c in range(3))
    except Exception:
        return False


def _image_fingerprint(img):
    """v0.0.9H: identifies the CONTENT of a linked picture for the conditioning cache (the files use name + mtime).
    v0.0.9m: called with the RESIZED picture (pictures[i]), not the full-resolution one."""
    arr = img.detach().cpu().numpy()
    return hashlib.sha1(np.ascontiguousarray(arr).tobytes()).hexdigest()[:20]


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


def _drop_built_models():
    """v0.1.5: another base diffusion model is about to load (model_cache.py): the models built on the old one go first.
    Cleared IN PLACE: a _cached() call that is building right now keeps its reference to this same dict."""
    if "model" in _CACHE:
        _CACHE["model"].clear()


_models.on_switch(_drop_built_models)


def free_cached_models(reason=""):
    """Drop every cached model / conditioning / audio and ask ComfyUI to unload what it holds."""
    _CACHE.clear()
    _LORA_CACHE.clear()
    _COND_CACHE.clear()
    _AUDIO_CACHE.clear()
    _models.free()      # v0.1.5: the base diffusion model shared with the Revitalizer
    try:      # v0.1.4: the 2in1 Revitalizer keeps its own model + VAEs between runs too
        from . import revitalizer as _rev
        _rev.free_cache()
    except Exception as e:
        log.debug("Could not free the Revitalizer's cache: %s", e)
    gc.collect()
    try:
        import comfy.model_management as mm
        mm.unload_all_models()
        mm.soft_empty_cache()
    except Exception as e:
        log.debug("Could not ask ComfyUI to unload models: %s", e)
    log.info("cached models freed%s", f" ({reason})" if reason else "")


def _register_routes():
    """v0.4.8: the routes live in routes.py; they read this module's names (counters, defaults, _RUNNING) when a request comes in."""
    from . import routes
    routes.register(sys.modules[__name__])


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
# file listings
# ---------------------------------------------------------------------- #
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
        except Exception as e:      # v0.0.9r: the pack's own decoder takes over
            log.debug("LoadAudio failed for '%s' (%s): using the pack's own decoder", name, e)
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
        except OSError as e:      # v0.0.9r: the number then starts at 1
            log.debug("could not list '%s' to number the clip (%s)", folder, e)
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
    """The Audio Stem of this Run. A missing / unknown value (a workflow saved before the widget existed) = Full.
    v0.0.6: the old name "Song" (workflows and API prompts saved before) means Full."""
    value = kw.get("Audio Stem", _stems.STEM_FULL)
    return value if value in _stems.STEM_CHOICES else _stems.STEM_FULL


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
    """Full = the Custom Audio File itself. Any other stem = that stem's WAV (made on first use, then cached on disk).
    The decoded stem is kept in RAM like the song (one entry); never mutate the result."""
    if not name or name == NONE_CHOICE:
        return None
    if stem == _stems.STEM_FULL:
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
    kind = 'video' (the picture stream) | 'soundtrack' (a video's audio stream, v0.4.12) | 'audio' (a custom audio file).
    None when it cannot be read."""
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
            streams = container.streams.video if kind == "video" else container.streams.audio
            # v0.4.12 (sweep B8): a video's length is its PICTURE stream's own length when the file states it (kind 'video'), and
            # a video's soundtrack is its AUDIO stream's (kind 'soundtrack'). The container length is the longest stream, and a
            # soundtrack that runs past the picture counted one segment too many.
            if kind in ("video", "soundtrack") and streams and streams[0].duration:
                seconds = float(streams[0].duration * streams[0].time_base)
            elif container.duration:
                seconds = container.duration / 1_000_000.0
            elif streams and streams[0].duration:
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


AUDIO_MINIMAX = "MiniMax Audio"       # v0.0.3, reworked in v0.0.4: no bypass, the model's own latent goes to the sampler (official ref2v template)
AUDIO_VIDEO = "Audio From Video"      # bypass: the video soundtrack, encoded and frozen
AUDIO_CUSTOM = "Custom Audio"         # bypass: your song, chunked per segment, encoded and frozen
AUDIO_MODES = (AUDIO_MINIMAX, AUDIO_VIDEO, AUDIO_CUSTOM)
DEFAULT_AUDIO_MODE = AUDIO_CUSTOM


def _audio_mode(value):
    """The 'Choose Audio latent' widget as one of AUDIO_MODES. Workflows saved before v0.0.3 stored a bool there
    (False = Audio From Video, True = Custom Audio); the segment-panel route sends strings."""
    if isinstance(value, str):
        v = value.strip().lower()
        for mode in AUDIO_MODES:
            if v == mode.lower():
                return mode
        return AUDIO_CUSTOM if v in ("1", "true", "yes", "on") else AUDIO_VIDEO
    return AUDIO_CUSTOM if value else AUDIO_VIDEO


def _segment_txt(kw, index):
    """v0.0.9w: 'segment N | next: segment N+1' for the status lines, counted from 1 like the panel and the header
    (index is 0-based). Next Segment On Run OFF: every Run makes segment 1, so no 'next'."""
    text = f"segment {int(index) + 1}"
    if _truthy(kw.get("Next Segment On Run")):
        text += f" | next: segment {int(index) + 2}"
    return text


def _num(value, default, cast=float):
    try:
        return cast(float(value))
    except (TypeError, ValueError):
        return default


def _segment_plan(p):
    """How many segments the selection holds. `p` = the node's widget values (strings are fine).
    Mirrors what _load_media steps through:
      Use Video ON                                    -> the video frames
      Choose Audio latent = Custom Audio + a file    -> the custom audio chunks
      Use Video OFF + Bypass Minimax + Audio From Video + a video -> the video soundtrack
    When several apply, the shortest one ends the run. total = None when nothing steps through a file."""
    use_video = _truthy(p.get("Use Video"), True)
    mode = _audio_mode(p.get("Choose Audio latent"))
    chunk_custom = mode == AUDIO_CUSTOM
    bypass = mode != AUDIO_MINIMAX   # MiniMax Audio = no bypass: nothing is read from a video soundtrack
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
        length = _probe_seconds(p["Video File"], "soundtrack")      # v0.4.12: the soundtrack's own length
        if length:
            sources.append({"name": "video soundtrack", "seconds": length,
                            "segments": max(0, math.ceil(length / seg_seconds - 1e-9))})

    limit = min(sources, key=lambda x: x["segments"]) if sources else None
    return {"total": limit["segments"] if limit else None, "limit": limit["name"] if limit else None,
            "sources": sources, "frames": int(frames), "seg_seconds": round(seg_seconds, 4)}


def _run_index(kw):
    """v0.2.3: the 0-based segment this Run makes. Next Segment On Run ON: the song's counter (it moves on after the Run). OFF: the
    SAME counter, so the segment chosen with Go is repeated on every Run and the counter does not move; a counter that is already
    at the end of the file (a finished session) gives segment 1, as an OFF Run always did before 0.2.3."""
    idx = _load_index(kw.get("counter_key", ""))
    if kw.get("Next Segment On Run"):
        return idx
    try:
        total = _segment_plan(kw)["total"]
    except Exception as e:
        log.debug("segment plan failed: %s", e)
        total = None
    return 0 if (total is not None and idx >= total) else idx


def _segment_info(params):
    """What the node's segment panel shows: the plan + the stored counter."""
    info = _segment_plan(params)
    key = _counter_key(params)      # v0.1.8: the counter of the song / video selected on the node
    index = _load_index(key)
    total = info["total"]
    info.update(index=index, furthest=max(_load_furthest(key), index), counter=_counter_label(key),
                stepping=_truthy(params.get("Next Segment On Run")),
                running=_RUNNING > 0, finished=bool(total is not None and index >= total))
    return info


def _custom_audio_chunk(kw, custom_full, custom_id, chunk_custom, audio_mode, index, seg_seconds, frames, out_fps):
    """v0.4.5 (split out of _load_media): the Custom Audio of this Run -> (audio, status note, cache id). Chunk mode: segment `index` cut
    from the song and padded with silence to the clip length (past the end: the quiet stop, or an error for segment 1); the whole file
    in the other bypass mode; nothing without a file."""
    if custom_full is None:
        return None, "", None
    if not chunk_custom:
        return custom_full, f"custom audio: whole file (Choose Audio latent = {audio_mode})", ("a2w", custom_id)
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
    audio_note = (f"custom audio chunk: {_segment_txt(kw, index)} | {c_start:.2f}s to {c_start + got:.2f}s"
                  f" | length {seg_seconds:.3f}s = {frames} frames @ {out_fps:g} fps")
    missing = int(round(seg_seconds * sr)) - custom_audio["waveform"].shape[-1]
    if missing > 0:
        # last chunk: pad with silence so it is as long as the video (audio latent stays aligned)
        padded = F.pad(custom_audio["waveform"], (0, missing))
        custom_audio = {**custom_audio, "waveform": padded}
        audio_note += f" | end of audio: padded with {missing / sr:.2f}s of silence"
    return custom_audio, audio_note, cond_audio2


def _reference_pictures(kw, slots, mp):
    """v0.4.5 (split out of _load_media): the wired Picture_1 .. Picture_<slots> at native size (an empty input = an empty slot, nothing
    sent) -> (raw pictures, {slot: True} for the wired ones, each picture's megapixel target keeping its OWN aspect ratio)."""
    raw = []
    linked = {}         # slot -> True when an IMAGE is wired into Picture_<slot>
    for i in range(1, slots + 1):
        wired = kw.get(_picture_input(i))
        if wired is None:
            raw.append(None)
            continue
        try:
            raw.append(_linked_image(wired))
        except Exception as e:
            log.error("[%s] failed to read the linked image: %s", _picture_input(i), e)
            raise RuntimeError(
                f"[IronLeo78 MTV] {_picture_input(i)} (linked image) failed: {e}"
            ) from e
        linked[i] = True
    sizes = [None if img is None else _target_size(img.shape[2], img.shape[1], mp, DIVISIBLE_BY)
             for img in raw]
    return raw, linked, sizes


def _resized_pictures(raw, sizes):
    """v0.4.5 (split out of _load_media): the pictures resized to their targets (empty slots stay None) and their cache ids. v0.0.9m: the
    fingerprint is taken of the RESIZED picture (what the conditioning really consumes, ~23 ms for 12 MP, not ~290 ms at full size)."""
    pictures = [None if img is None else _resize(img, size[0], size[1], RESIZE_METHOD)
                for img, size in zip(raw, sizes)]
    pic_ids = [None if img is None else ("pi", _image_fingerprint(img), size)
               for img, size in zip(pictures, sizes)]
    return pictures, pic_ids


def _media_status_lines(audio_note, chunk_custom, custom_full, linked, kw):
    """v0.4.5 (split out of _load_media): the lines appended to the status text: the audio note, the missing-song warning, the pictures."""
    out = ""
    if audio_note:
        out += "\n" + audio_note
    if chunk_custom and custom_full is None:      # v0.3.10: it used to skip the song without a word
        warn_song = ("WARNING: Choose Audio latent = Custom Audio but no Custom Audio File is selected: NO song is used "
                     "(pick a file, or choose another Choose Audio latent)")
        log.warning("[IronLeo78 MTV] %s", warn_song)
        out += "\n" + warn_song
    if linked:
        out += "\n" + f"reference pictures: {', '.join(_picture_input(i) for i in sorted(linked))}"
    if kw.get("none_pictures"):      # v0.0.9v (set by run())
        out += "\n" + ("empty slots skipped (NONE picture from the Prompt Generator): "
                       + ", ".join(_picture_input(i) for i in kw["none_pictures"]))
    return out


class IronLeo78_MTV:
    SLOTS = 9               # Picture_1 .. Picture_9 (the core MiniMax H3 node takes at most 9 reference pictures), all always on

    def __init__(self):
        pass

    # ------------------------------------------------------------------ #
    @classmethod
    def INPUT_TYPES(cls):
        vid_files = _video_files()

        r = {
            # ===== turbo (the Turbo LoRA itself is hardcoded) =====
            "Turbo": ("BOOLEAN", {
                "default": True, "label_on": "ON", "label_off": "OFF",
                "tooltip": "ON: Turbo LoRA applied, 6 steps. OFF: no Turbo LoRA, 30 steps (both and the Turbo LoRA strength can be changed on the Model Loader) "
                           "(BasicGuider, no CFG, like the official r2v template).",
            }),
            # ===== video / audio =====
            "Use Video": ("BOOLEAN", {
                "default": False, "label_on": "ON", "label_off": "OFF",
                "tooltip": "ON = v2v: the video is loaded and is the reference for megapixels/width/height. "
                           "OFF = i2v: no frames are loaded, the Picture_1 input is the reference. "
                           "Exception: with Choose Audio latent = "
                           "Audio From Video, a selected Video File still supplies its soundtrack "
                           "(audio only). Set Video File to None for silence.",
            }),
            "Video File": ([NONE_CHOICE] + vid_files,
                           {"default": NONE_CHOICE, "video_upload": True}),
            # ===== audio latent. v0.1.11: MOVED here, right under Video File (was after prompt, position 9 -> 3). Saved workflows
            # are put back in order by name (named copy) or, without one, by moveAudioLatentUp in web/ironleo78_mtv.js =====
            "Choose Audio latent": (list(AUDIO_MODES), {
                "default": DEFAULT_AUDIO_MODE,
                "tooltip": "Where the sound of the clip comes from. "
                           "MiniMax Audio = like the official MiniMax H3 ref2v template: no bypass, the model's own audio "
                           "latent goes to the sampler and the model generates the sound itself (voice, effects, music). "
                           "A Custom Audio File / video soundtrack, if any, is then only sent as a reference "
                           "(use <Audio 1> in the prompt). "
                           "Audio From Video = the video soundtrack is encoded into the audio latent and frozen "
                           "(silence if none). "
                           "Custom Audio = the Custom Audio File is encoded into the audio latent and frozen "
                           "(silence if none): the model never invents sound, the picture follows your music. "
                           "Custom Audio also decides which audio Next Segment On Run moves through: "
                           "the song is cut into chunks as long as the real video "
                           "segment (frames / fps: duration 5 s = 124 frames = 5.17 s), one chunk per Run "
                           "(works with Use Video OFF too); the segment counter at the top of the node "
                           "decides which chunk is next (Jump).",
            }),
            "Custom Audio File": (_audio_files(), {"audio_upload": True}),
            "Audio Stem": (list(_stems.STEM_CHOICES), {
                "default": _stems.STEM_FULL,
                "tooltip": "Which part of the Custom Audio File is used. Full = the whole mix. "
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
                       "Use Video OFF: Picture_1 does. The other pictures always keep their own aspect ratio.",
        })
        r["duration"] = ("FLOAT", {
            "default": DEFAULT_DURATION, "min": 0.0, "max": 10000.0, "step": 0.1,      # v0.0.9: the arrows move it by 0.1 s (was 0.01)
            "tooltip": "Duration in seconds. Also sets the video segment length when Use Video is ON. "
                       "durationS = this value unchanged; durationF = Minimax frame count.",
        })
        r["Next Segment On Run"] = ("BOOLEAN", {
            "default": False, "label_on": "ON", "label_off": "OFF",
            "tooltip": "ON: every Run moves on to the next segment (video frames, and/or the custom audio "
                       "chunk when Choose Audio latent = Custom Audio). OFF: the same segment on every Run: the first one, "
                       "or the one you chose with Go in the panel (the counter does not move).",
        })
        # ===== MiniMax H3 reference-to-video =====
        r["prompt"] = ("STRING", {
            "multiline": True, "dynamic_prompts": True, "default": "",
            "tooltip": "MTV_Prompt: the prompt, e.g. the output of the IronLeo78-MTV-Prompt-Generator. Refer to references as <Picture i> (the connected Picture_n inputs) / <Video 1> / <Audio j>. "
                       "Numbers count only what is actually sent: an empty picture slot is skipped "
                       "(Picture_1 + Picture_3 connected = <Picture 1> and <Picture 2>). "
                       "Audio order: video soundtrack first (if any), then custom audio. "
                       "The status output lists the exact mapping.",
        })
        # ===== save latent (v0.6). Takes the place of the old "Latent Upscale" widget =====
        r["Save Latent"] = ("BOOLEAN", {
            "default": DEFAULT_SAVE_LATENT, "label_on": "ON", "label_off": "OFF",
            "tooltip": "OFF by default (v0.6.2). ON: the sampled latent (video + audio .latent files) and the conditioning "
                       "(.conditioning: prompt + pictures, no guide) are saved in the song folder, named like the clip "
                       "(see the filename output), so you can refine / upscale it later in another workflow (2in1 Revitalizer). "
                       "OFF: no latent files. (The clip itself is saved by the Save Video node you link.)",
        })
        # ===== guide (v2.0) =====
        r["Guide"] = ("BOOLEAN", {
            "default": DEFAULT_GUIDE, "label_on": "ON", "label_off": "OFF",      # v0.6.2: OFF on a new node
            "tooltip": "OFF by default (v0.6.2). Only works with Next Segment On Run = ON. ON: the last frame of the previous run "
                       "is used as a guide for the first frame of this segment, so the clips continue "
                       "each other. The first segment (or a run with no saved frame from the segment "
                       "before) runs without a guide. OFF: no guide.",
        })
        # ===== pictures: NO widgets any more (v0.0.9H): the nine reference pictures come in through the optional IMAGE inputs
        # Picture_1 .. Picture_9 below. The old picture_1..9 pickers and the More References switch were the LAST widgets, so
        # removing them moves no saved value (the extra values of an old workflow are trimmed by the JS migration).

        # v2.3: optional link-only input (no widget, so saved widget values never shift).
        optional = {
            "models": (MODELS_TYPE, {
                "tooltip": "Optional. Plug in the IronLeo78 MTV Model Loader to replace "
                           "the hardcoded diffusion model, Turbo LoRA, text encoder, VAEs and "
                           "step counts. Nothing connected = the hardcoded defaults.",
            }),
        }
        # v0.1.20: the nine legacy IMAGE sockets Picture_1 .. Picture_9 are GONE from the node. The reference pictures come in
        # on ONE wire, `Pictures`, from the IronLeo78-MTV-Prompt-Generator (v0.1.19). No widget, so no saved widget value moves.
        # (Old API prompts / old saved links that still carry a Picture_<n> key are still honoured in run(): see _spread_pictures.)
        optional[PICTURES_INPUT] = (PICTURES_TYPE, {
            "tooltip": "Optional. All nine reference pictures on one wire: connect the IronLeo78-MTV-Prompt-Generator's Pictures output. "
                       "Empty slots are skipped (the <Picture n> numbers count only the filled ones).",
        })

        return {"required": r, "optional": optional, "hidden": {"unique_id": "UNIQUE_ID",
                                          "workflow_prompt": "PROMPT",
                                          "extra_pnginfo": "EXTRA_PNGINFO"}}

    # v0.0.5: two output sockets. `video` = what Create Video made (hardcoded settings), to be linked by the user to a
    # Save Video node; `filename` = the clip's name as the node always named it (see _plan_clip_name). The node itself
    # no longer saves the clip and returns no saved-video preview.
    # v0.0.9: a third output, `status` (STRING) = the run report. The status box at the bottom of the node is gone (it took
    # space); link `status` to a Preview Any / text node to read it. It is the LAST output, so saved links keep working.
    RETURN_TYPES = ("VIDEO", "STRING", "STRING")
    RETURN_NAMES = ("video", "filename", "status")
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "IronLeo78/MTV"
    DESCRIPTION = (
        "Minimax MTV: loader + MiniMax H3 reference-to-video + sampling + decode + "
        "Create Video, in one node.\n"
        "v0.0.5: the node does not save the clip any more. Outputs: video (Create Video's result, settings hardcoded: "
        "24 fps, sRGB, h264) -> link it to a Save Video node; filename (the clip's name as always named, "
        "<Song>/<Song>_seg004_A_00001_, no extension: it names the .json, the manifest row and the latent files; "
        "if you link it to a Save Video's filename_prefix, Save Video adds its own _00001_ after it).\n"
        "Models: Turbo + custom LoRA; diffusion model, attention backend, Qwen3-VL text encoder "
        "and the 2 VAEs are hardcoded (v2.3: the optional 'models' input takes a Model Loader node "
        "that can replace them, and the step counts).\n"
        "Media: video (segment by segment) + up to nine reference images (the Pictures input) + custom audio (whole song, or only its Vocals / Guitars / Drums / Bass: "
        "Audio Stem; the stems are separated once per song and saved to output/<Song>/stems/).\n"
        "Sampling is hardcoded (BasicGuider, res_multistep, simple, denoise 1.0); "
        "Turbo ON = 4 steps, Turbo OFF = 40 steps. The noise seed (default 1978) is set on the Model Loader node.\n"
        "Choose Audio latent: Custom Audio / Audio From Video keep the audio you give as is (the model never "
        "generates audio); MiniMax Audio works like the official ref2v template (the model generates the sound).\n"
        "Save Latent ON: the sampled latent (video + audio .latent files) and its conditioning (.conditioning) are "
        "saved in the song folder with the clip's name, for a later refine / upscale in another workflow. OFF (default): "
        "no latent files.\n"
        "Files are tagged <Song>_seg<segment>_A (Song = the Custom Audio File name, if one is selected) "
        "and logged in a manifest CSV.\n"
        "No video preview on the node (the live latent preview while sampling stays). v0.0.9: no status box on the node either; "
        "the run report leaves on the third output, status (STRING): link it to a Preview Any / text node to read it.\n"
        "v2.5: segment panel (count / next / Reset), progress in the report, a quiet stop after the last segment, "
        "and a <clip>.json sidecar with the full prompt next to every clip.\n"
        "v2.6: jump to any segment (number field + Go / Latest in the panel), and the Guide can read "
        "the previous segment's last frame back from its clip.\n"
        "v2.8: Scene 2 / prompt_2 / Picture4-6 are gone (one clip per Run).\n"
        "Pictures (optional input, since v0.1.20 the only way to give reference pictures): the IronLeo78-MTV-Prompt-Generator's nine slots on "
        "one wire; every filled slot is sent as <Picture n>.\n"
        "by IronLeo78"
    )

    # ================================================================== #
    # MODEL stage
    # ================================================================== #
    @staticmethod
    def _load_unet(unet_name, weight_dtype):
        """v0.1.5: a clone of the ONE shared base model (model_cache.py; the Revitalizer uses the same one). The clone shares
        the weights, so applying LoRAs to it never touches the base and never reads the model file again."""
        base, _ = _models.diffusion_model(unet_name, weight_dtype)
        return base.clone()

    @staticmethod
    def _apply_lora(model, lora_name, strength, label):
        if lora_name == NONE_LORA or strength == 0:
            return model
        path = folder_paths.get_full_path_or_raise("loras", lora_name)

        lora = _lru_get(_LORA_CACHE, path)
        if lora is None:
            lora = comfy.utils.load_torch_file(path, safe_load=True)
            _lru_put(_LORA_CACHE, path, lora, LORA_CACHE_MAX)

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
        for n in range(1, LORA_SLOTS + 1):       # v0.0.9: chained after the Turbo LoRA, in order
            if kw[f"lora_{n}_enabled"]:
                model = _stage(f"lora {n}", self._apply_lora, model,
                               kw[f"lora_{n}_name"], kw[f"lora_{n}_strength"], f"LoRa_{n}")
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
        custom_key = tuple((n, _stamp("loras", kw[f"lora_{n}_name"]), kw[f"lora_{n}_strength"])
                           for n in range(1, LORA_SLOTS + 1) if kw[f"lora_{n}_enabled"])

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
            # v0.4.13 (sweep O2): the loaded VAE is the pack's shared copy (model_cache.vae), the same one the Revitalizer uses
            return _cached(uid, stage, key, lambda: _stage(stage, _models.vae, name, lambda: self._load_vae(name, label)))

        return (model,
                clip("qwen_vl", "Qwen-VL", "clip qwen-vl"),
                vae("video_vae", "Video VAE", "video vae"),
                vae("audio_vae", "Audio VAE", "audio vae"))

    # ================================================================== #
    # MEDIA stage (video / audio / pictures) - unchanged logic
    # ================================================================== #
    def _load_video(self, kw, frames, seconds, mp, index):
        """Returns (images, audio, w, h, filename, status).
        index = segment number (0 when Next Segment On Run is OFF; the segment counter sets it)."""
        video = _resolve_video_path(kw.get("Video File"))
        filename = os.path.splitext(os.path.basename(video))[0]

        span = frames
        skip = index * span

        # v0.1.1: every frame is cropped + shrunk right after it is decoded (see _video_frame_plan / _shape_video_frame), so only
        # the target-size frames are kept: the same pixels as before, without the full-size float32 copy of the whole segment
        plan = {}

        def shape(arr):
            if not plan:
                plan["p"] = _video_frame_plan(int(arr.shape[1]), int(arr.shape[0]), mp)
            return _shape_video_frame(arr, plan["p"])

        images, info = _decode_video(video, DEFAULT_FPS, skip, frames, shape=shape)
        if images is None:
            if index > 0:      # v2.5: every segment is done: stop quietly (the Run reports it, no error)
                raise _EndOfSegments(f"End of video: segment {index + 1} would start at frame {skip}, "
                                     f"past the last frame.", index)
            raise RuntimeError("No frames could be loaded from this video.")

        rate = info["rate"]
        audio = _decode_audio(video, skip / rate, images.shape[0] / rate)  # None = no sound

        # v0.4.16 (sweep N5): the picture stream's own length, the same one the segment panel counts with (B8, 0.4.12);
        # info["duration"] is the container's (the longest stream) and could disagree when the soundtrack runs longer
        try:
            seconds_total = _probe_seconds(kw.get("Video File"), "video") or info["duration"]
        except Exception:
            seconds_total = info["duration"]
        total = int(round(seconds_total * rate)) if seconds_total and seconds_total > 0 else 0
        end = skip + span - 1
        if total > 0:
            end = min(end, total - 1)

        h, w = int(images.shape[1]), int(images.shape[2])
        turned = (f" | turned upright ({info['quarter_turns'] * 90} degrees: phone video)"
                  if info.get("quarter_turns") else "")      # v0.1.3
        status = (f"Video ON | {_segment_txt(kw, index)} | frames {skip} to {end}"
                  f" | resolution: {w}x{h}{turned} | total frames: {total}\n{CREDIT}")
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
        note = (f"video audio only (Use Video OFF): {name} | {_segment_txt(kw, index)} | "
                f"{start_s:.2f}s to {start_s + got:.2f}s")
        missing = int(round(seg_seconds * sr)) - audio["waveform"].shape[-1]
        if missing > 0:
            audio = {**audio, "waveform": F.pad(audio["waveform"], (0, missing))}
            note += f" | end of audio: padded with {missing / sr:.2f}s of silence"
        return audio, note

    # ------------------------------------------------------------------ #
    @staticmethod
    def _prepare_stems(kw):
        """Audio Stem other than Full: make sure the song's stems are on disk. Returns the line for the status output
        ('' when no stem is used). Runs before the models are loaded so Demucs gets the GPU memory to itself."""
        stem = _stem_choice(kw)
        name = kw.get("Custom Audio File")
        if stem == _stems.STEM_FULL or not name or name == NONE_CHOICE:
            return ""
        bar = None
        try:
            bar = comfy.utils.ProgressBar(100)
        except Exception:      # intentionally silent: the progress bar is optional
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
        audio_mode = _audio_mode(kw["Choose Audio latent"])
        chunk_custom = audio_mode == AUDIO_CUSTOM  # True = chunk the Custom Audio
        index = _run_index(kw)      # v0.1.8: this song's counter; v0.2.3: an OFF Run repeats the segment chosen with Go
        # (until 0.1.9 an OFF Run also advanced the counter to 1; since 0.1.10 it leaves it alone, see below)
        # Saved by run() only after the whole node succeeded (no burnt segment on error).
        stem = _stem_choice(kw)
        custom_full = _load_audio_for_stem(kw.get("Custom Audio File"), stem)  # None if not selected

        # Use Video OFF only drops the images: with a bypassed audio latent and
        # Choose Audio latent = Audio From Video, a selected Video File still supplies its
        # soundtrack (audio only, no frames are decoded, Picture_1 still sets the size).
        audio_only_path = None
        if not use_video and audio_mode == AUDIO_VIDEO:
            sel = kw.get("Video File")
            if sel and sel != NONE_CHOICE and folder_paths.exists_annotated_filepath(sel):
                audio_only_path = _resolve_video_path(sel)

        # v0.1.9 -> v0.1.10 (review #9, the user's decision): a Run with Next Segment On Run OFF no longer moves the counter
        # (it used to set it to 1, losing a Jump position); only stepping Runs advance it.
        if kw["Next Segment On Run"] and (use_video or (chunk_custom and custom_full is not None) or audio_only_path
                                          or kw.get("Guide", False)):
            self._pending_index = index + 1

        custom_id = _file_id(kw.get("Custom Audio File")) if custom_full is not None else None
        if custom_id is not None and stem != _stems.STEM_FULL:
            custom_id = custom_id + (stem,)       # the conditioning / audio-latent caches must tell the stems apart
        cond_audio1 = None
        cond_video = None
        custom_audio, audio_note, cond_audio2 = _custom_audio_chunk(kw, custom_full, custom_id, chunk_custom, audio_mode,
                                                                    index, seg_seconds, frames, out_fps)

        # 1) + 2) the wired pictures at native size, each with its megapixel target (own aspect ratio)
        raw, linked, sizes = _reference_pictures(kw, self.SLOTS, mp)

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
            # a Picture_1 input has no file name: nothing to name the clip after (custom audio still wins)
            filename = ""
            status = (f"Video OFF | reference: Picture_1{'' if 1 in linked else ' (not connected: 1x1 size)'} | "
                      f"filename: {filename} | resolution: {w}x{h}\n{CREDIT}")
            if video_audio_note:
                status += "\n" + video_audio_note

        status += _media_status_lines(audio_note, chunk_custom, custom_full, linked, kw)

        # position of this segment in the song / video (seconds), for the manifest
        if custom_full is not None and chunk_custom:
            timeline = index * seg_seconds
        elif use_video or audio_only_path:
            timeline = (index * frames) / out_fps
        else:
            timeline = index * seg_seconds if self._pending_index is not None else 0.0

        # 4) resize pictures (empty slots stay None: nothing is sent for them) and fingerprint the RESIZED ones
        pictures, pic_ids = _resized_pictures(raw, sizes)

        return {"video": video1, "audio1": audio1, "audio2": custom_audio,
                "pictures": pictures, "width": w, "height": h,
                "seconds": seconds, "seg_seconds": seg_seconds, "frames": int(frames),
                "filename": filename, "status": status, "index": index,
                "audio_stem": stem if custom_full is not None else "",
                "timeline_start": float(timeline), "counter_key": kw.get("counter_key", ""),      # v0.1.8
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
        frame, why = _load_last_frame(index, media.get("song"), key=media.get("counter_key", ""))      # v0.1.8: this song's frame
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
        """Custom Audio / Audio From Video (bypass): TrimAudioDuration -> VAEEncodeAudio ->
        SetLatentNoiseMask(SolidMask 0) -> LTXVConcatAVLatent(minimax latent, audio latent).
        The encoded audio latent is cached (so a re-run does not encode it again).

        MiniMax Audio (v0.0.4): NO bypass. Exactly like ComfyUI's official ref2v template, the LATENT output of
        MiniMaxH3ReferenceToVideo goes to the sampler as it is, so the model generates the audio itself (it already
        holds the audio latent) and VAE Decode / VAE Decode Audio read the sampled latent. Nothing is trimmed,
        encoded, masked or concatenated here."""
        mode = _audio_mode(kw["Choose Audio latent"])
        if mode == AUDIO_MINIMAX:
            return latent, "audio: MiniMax Audio (the model's own audio latent, no bypass)"
        custom = mode == AUDIO_CUSTOM
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
    def _plan_clip_name(st):
        """v0.0.5: the node no longer saves the clip (the user links the `video` output to a Save Video node), but every
        other file keeps the old naming: <tag>_NNNNN_ is the number the clip WOULD have got. The planned name
        '<Song>/<Song>_seg004_A_00001_.mp4' is what the sidecar .json, the manifest row, the latent files and the
        `filename` output use. Chosen once per clip (a redo gets the next free number, so nothing is overwritten)."""
        if st.get("file"):
            return st["file"]
        parent = os.path.dirname(str(st["prefix"]).replace("\\", "/"))
        name = f"{st['tag']}_{_clip_counter(st):05d}_.{SAVE_FORMAT}"
        st["file"] = "/".join(p for p in (parent, name) if p)
        return st["file"]

    @staticmethod
    def _filename_out(st):
        """The `filename` output: the planned clip name without its extension (e.g. Song/Song_seg004_A_00001_)."""
        return os.path.splitext(str(st.get("file") or ""))[0]

    # ================================================================== #
    # CLIP PIPELINE (one clip per Run). The stages are separate steps so the text encoder, the diffusion model and
    # the VAEs are each swapped in once per Run:   prepare -> sample -> decode / save (+ latent files when asked)
    # ================================================================== #
    def _clip_new(self, kw, media):
        prefix, tag = _clip_prefix(kw, media)
        names = []
        for i in range(1, self.SLOTS + 1):
            if kw.get(_picture_input(i)) is not None:      # a linked image has no file: the slot's socket name stands in
                names.append(f"{_picture_input(i)} (linked)")
        return {
            "prompt": kw["prompt"], "prefix": prefix, "tag": tag,
            "pictures": names, "notes": [], "fps": DEFAULT_FPS,
            "positive": None, "positive_plain": None, "latent": None, "samples": None, "sampler": None,
            "refs_line": "", "guide_line": "", "audio_line": "",
            "images": None, "audio": None, "video": None,
            "file": "", "last_frame": None, "logged": False,
            "latent_files": None, "latent_info": None, "latent_line": "",
            "clip_meta": {"index": int(media.get("index", 0)), "frames": int(media.get("frames", 0)),
                          "width": int(media.get("width", 0)), "height": int(media.get("height", 0)),
                          "seg_seconds": float(media.get("seg_seconds", 0.0)),
                          "timeline_start": float(media.get("timeline_start", 0.0)),
                          "audio_stem": media.get("audio_stem") or "",
                          "project": _project_name(kw, media)},      # v0.0.9: song, else video name (latent file headers)
        }

    @staticmethod
    def _maybe_drop(st):
        """The decoded frames / audio are freed at once; the created video stays: it leaves on the `video` output."""
        st["images"] = st["audio"] = None

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
        Called once the clip is made (v0.0.5: the number comes from _plan_clip_name: the next free one for this prefix,
        counting these files too, so a redo never overwrites), and also when the decode fails, so an error never loses
        the sampled latent.
        The conditioning is the plain one (prompt + pictures, no guide).
        Never fatal: a problem here is a note, the clip is still made."""
        if not kw.get("Save Latent", SAVE_LATENT_MISSING) or st["samples"] is None or st.get("latent_files"):
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
            meta = {"ironleo78": json.dumps({"version": VERSION, "song": m.get("project", ""), "tag": st["tag"],
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
        """decode -> Create Video (hardcoded settings), then the latent files when Save Latent is ON.
        v0.0.5: no Save Video here: the video goes out on the node's `video` output."""
        notes = st["notes"]
        try:
            self._plan_clip_name(st)            # the clip's name (old naming), also for the latent files
        except Exception as e:
            if _is_interrupt(e):
                raise
            log.warning("Could not plan the clip name: %s", e)
            notes.append(f"clip name not planned ({e})")
        try:
            images, audio = _stage("decode", self._decode, st["samples"], vae_video, vae_audio, notes)
            video, st["fps"] = _stage("create video", self._create_video, images, audio, kw, notes)
        except Exception as e:
            if not _is_interrupt(e):
                self._save_latents(st, kw)      # a decode error still keeps the sampled latent
            raise
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
                + [f"clip name: {st['file'] or '?'} (not saved by this node: link the video output to a Save Video node)"])

    def _manifest_row(self, res, kw, media, prompt_json=""):
        start = float(media.get("timeline_start", 0.0))
        seg = float(media["seg_seconds"])
        prompt = " ".join(str(res["prompt"]).split())
        if len(prompt) > MANIFEST_PROMPT_CHARS:      # the full text is in the sidecar .json
            prompt = prompt[:MANIFEST_PROMPT_CHARS - 1].rstrip() + "\u2026"
        return {
            "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
            "song": _project_name(kw, media),
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
            "song": _project_name(kw, media), "tag": st["tag"],
            "segment": idx, "segment_number": idx + 1, "segment_total": media.get("segment_total"),
            "file": st["file"],
            "start_s": round(start, 2), "end_s": round(start + seg, 2), "duration_s": round(seg, 3),
            "frames": int(media["frames"]), "width": int(media["width"]), "height": int(media["height"]),
            "fps": st["fps"], "seed": int(kw["noise_seed"]), "turbo": bool(kw["Turbo"]), "steps": int(kw["steps"]),
            "save_latent": bool(kw.get("Save Latent", SAVE_LATENT_MISSING)),
            "custom_loras": [{"slot": n, "file": kw[f"lora_{n}_name"], "strength": kw[f"lora_{n}_strength"]}
                             for n in range(1, LORA_SLOTS + 1) if kw.get(f"lora_{n}_enabled")] or None,
            "pictures": list(st["pictures"]), "references": st["refs_line"],
            "audio": st["audio_line"], "audio_stem": media.get("audio_stem") or None,
            "latent": st.get("latent_files") or None,
            "latent_details": st.get("latent_info") or None,
            "guide": st["guide_line"] or None,
            "models": {k: kw[k] for k in MODEL_FILE_KEYS},
            "models_source": ("Model Loader" if kw["models_source"]          # v0.0.9w: the saved set was reported as "hardcoded"
                              else "saved defaults" if kw.get("defaults_custom") else "hardcoded"),
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
            note = f"manifest: {_append_manifest(_project_name(kw, media), [self._manifest_row(st, kw, media, first)])}"
            return note + (f" | full prompt: {first}" if first else "")
        except Exception as e:
            log.warning("Could not write the manifest: %s", e)
            run_notes.append(f"manifest not written ({e})")
            return ""

    # ================================================================== #
    def run(self, unique_id=None, workflow_prompt=None, extra_pnginfo=None, models=None, **kw):
        global _RUNNING
        _spread_pictures(kw)      # v0.1.19
        if "Bypassed Audio Latent" in kw:      # v0.0.5: the widget was renamed (old API prompts / scripts)
            kw.setdefault("Choose Audio latent", kw["Bypassed Audio Latent"])
            del kw["Bypassed Audio Latent"]
        if kw.get("Audio Stem") == _stems.STEM_LEGACY_SONG:      # v0.0.6: the stem "Song" is now called "Full" (old API prompts)
            kw["Audio Stem"] = _stems.STEM_FULL
        kw.update(FIXED_SETTINGS)  # hardcoded values (no widgets for them)
        kw["noise_seed"] = DEFAULT_SEED   # v2.8.5: no widget; the Model Loader may replace it (below)
        kw["defaults_custom"] = apply_saved_defaults(kw)   # v0.0.9: the defaults the user saved with the Model Loader's "Set New Defaults"
        # v2.3: the Model Loader (optional "models" input) may replace the hardcoded models / steps
        kw["models_source"], kw["models_changed"] = apply_model_overrides(kw, models)
        kw["steps"] = kw["turbo_steps"] if kw["Turbo"] else kw["full_steps"]   # default: Turbo ON = 6, OFF = 30 (v0.1.11)
        kw.setdefault("Save Latent", SAVE_LATENT_MISSING)              # v0.6 (a workflow without the widget: OFF; a NEW node is ON since 0.1.11)
        kw["counter_key"] = _counter_key(kw)      # v0.1.8: whose segment counter this Run uses (its song, else its video)
        # v0.0.9v: an empty slot of the Prompt Generator still sends its grey "NONE" picture: that input counts as not connected
        kw["none_pictures"] = [i for i in range(1, self.SLOTS + 1) if _is_none_placeholder(kw.get(_picture_input(i)))]
        for i in kw["none_pictures"]:
            kw[_picture_input(i)] = None
        self._pending_index = None
        _RUNNING += 1
        try:
            return self._run(unique_id, workflow_prompt, extra_pnginfo, kw)
        finally:
            _RUNNING -= 1

    @staticmethod
    def _loader_label(kw):
        """v0.0.9: status text for a connected Model Loader. With a saved set (Set New Defaults) it says whether the loader still
        holds that set (same on both sides) or which values differ from it (the loader's live values win for this run)."""
        changed = kw["models_changed"]
        if not kw.get("defaults_custom"):
            return f"Model Loader ({changed})"
        if changed == "nothing changed from the defaults":
            return "Model Loader (same as the saved set)"
        return f"Model Loader (DIFFERS from the saved set: {changed})"

    def _finished(self, kw, done, detail=""):
        """v2.5: every segment is made. Nothing is generated, nothing is raised, the counter does not move."""
        song = _song_name(kw) or "(no custom audio)"
        status = (f"FINISHED | {song} | all {done} segments are done\n"
                  "Nothing was generated and the segment counter did not move.\n"
                  "To start over: press Reset in the segment panel of the node.")
        if detail:
            status += "\n" + detail
        log.info("\n%s", status)
        blocked = ExecutionBlocker(None) if ExecutionBlocker is not None else None
        # nothing reaches a linked Save Video; the status text itself still leaves (it says why nothing was made)
        return {"ui": {"text": [status]}, "result": (blocked, blocked, status)}

    def _run(self, unique_id, workflow_prompt, extra_pnginfo, kw):
        notes = []
        # v2.5: how many segments are there? (only when this Run steps through them)
        total = None
        if kw["Next Segment On Run"]:
            try:
                total = _segment_plan(kw)["total"]
            except Exception as e:
                log.debug("segment plan failed: %s", e)
            at = _load_index(kw["counter_key"])
            if total is not None and at >= total:
                return self._finished(kw, at)     # quiet stop BEFORE any model is loaded
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
        media["song"] = _project_name(kw, media)         # v2.6: the Guide can read a last frame back from the manifest clips
        hidden = {"UNIQUE_ID": unique_id, "PROMPT": workflow_prompt, "EXTRA_PNGINFO": extra_pnginfo}

        st = self._clip_new(kw, media)

        manifest_note = ""
        try:
            self._phase_prepare(st, clip, vae_video, vae_audio, kw, media, models_key)
            self._phase_sample(st, model, kw)
            self._phase_clip(st, vae_video, vae_audio, kw, hidden)
        except Exception:
            # a clip that is already on disk (saved, then something failed) is logged (never fatal)
            if st["file"] and st["video"] is not None and not st["logged"]:      # only a clip that was really made
                self._log_clip(st, kw, media, notes)
            raise
        manifest_note = self._log_clip(st, kw, media, notes)

        # Everything worked: only now does the video segment counter move on.
        if self._pending_index is not None:
            if st["last_frame"] is not None:
                try:      # the last frame of this clip, for the Guide of the next run (never fatal)
                    _save_last_frame(st["last_frame"], self._pending_index - 1, kw["counter_key"])
                except Exception as e:
                    log.warning("Could not save the last frame for the guide: %s", e)
                    notes.append(f"last frame not saved ({e})")
            try:      # v0.4.12 (sweep B1): the clip is made: a counter that cannot be saved must not lose it (Windows "Access denied")
                _save_index(self._pending_index, kw["counter_key"])
            except Exception as e:
                if _is_interrupt(e):
                    raise
                warn = (f"WARNING: the segment counter could not be saved ({e}): the next Run makes segment "
                        f"{self._pending_index} AGAIN. Use Go in the segment panel to move on to segment {self._pending_index + 1}.")
                log.warning("[IronLeo78 MTV] %s", warn)
                notes.append(warn)

        # ---- status text ----
        start = float(media.get("timeline_start", 0.0))
        idx = int(media["index"])
        if kw["Next Segment On Run"]:
            seg_txt = (f"segment {idx + 1} of {total}" if total else f"segment {idx + 1}") + f" (seg{idx:03d})"
        else:
            seg_txt = f"segment {idx + 1}"       # v0.0.9w: counted from 1 like everywhere else (the segment chosen with Go; 1 by default)
        header = (f"SONG: {_project_name(kw, media) or '(no custom audio, no video name)'} | {seg_txt}"
                  f" | {start:.2f}s to {start + float(media['seg_seconds']):.2f}s")
        if kw["Next Segment On Run"] and total:
            left = total - (idx + 1)
            header += (f"\nprogress: {idx + 1} of {total} segments done ({100.0 * (idx + 1) / total:.0f} %)"
                       + (" | that was the LAST segment: the next Run stops quietly" if left <= 0 else f" | {left} left"))
        header += "\nmodels: " + (self._loader_label(kw) if kw["models_source"] else "saved defaults (Set New Defaults)" if kw.get("defaults_custom") else "hardcoded defaults")
        status = media["status"] + "\n" + header
        status += f"\n--- {st['tag']} ---\n" + "\n".join(self._clip_lines(st, kw))
        if st["notes"]:
            status += "\nnotes: " + "; ".join(st["notes"])
        if manifest_note:
            status += "\n" + manifest_note
        if notes:
            status += "\nnotes: " + "; ".join(notes)
        log.info("\n%s", status)

        # No "images" entry = no video preview on the node (v0.0.5: there is no saved clip any more). The video, the clip
        # name and the report leave on the three outputs (v0.0.9: no status box on the node any more; the "text" entry
        # stays only so the frontend still gets its "executed" event after a run).
        video = st["video"]
        st["video"] = None
        return {"ui": {"text": [status]}, "result": (video, self._filename_out(st), status)}

    # ------------------------------------------------------------------ #
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        if kwargs.get("Use Video", True) or kwargs.get("Next Segment On Run", False):
            return float("nan")  # segment stepping (video or custom audio chunks): always re-run
        m = hashlib.sha256()
        kwargs = dict(kwargs)
        m.update(b"segment:" + str(_load_index(_counter_key(kwargs))).encode("utf-8"))      # v0.2.3: a Go to another segment re-runs an OFF node
        _spread_pictures(kwargs)                               # v0.1.19: the one Pictures wire counts like the nine
        for i in range(1, cls.SLOTS + 1):
            if kwargs.get(_picture_input(i)) is not None:      # linked image: its content is in ComfyUI's own cache key
                m.update(b"linked:" + str(i).encode("utf-8"))
        for key in ("megapixels", "duration", "Audio Stem"):
            m.update(str(kwargs.get(key, "")).encode("utf-8"))
        for key in ("Custom Audio File", "Video File"):      # v0.0.9p: name + mtime + size, so a file replaced under the same name is noticed
            m.update(repr(_file_id(kwargs.get(key))).encode("utf-8"))
        m.update(repr(_defaults_stamp()).encode("utf-8"))      # v0.0.9w: "Set New Defaults" / Factory re-run the node
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
        if kw.get("Audio Stem", _stems.STEM_FULL) not in _stems.STEM_CHOICES + (_stems.STEM_LEGACY_SONG,):
            return f"Audio Stem must be one of: {', '.join(_stems.STEM_CHOICES)}."
        return True


_register_routes()

NODE_CLASS_MAPPINGS = {"IronLeo78_MTV": IronLeo78_MTV}
NODE_DISPLAY_NAME_MAPPINGS = {"IronLeo78_MTV": "IronLeo78 MTV (v0.6.3)"}
