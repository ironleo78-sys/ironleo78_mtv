"""
IronLeo78 9-Images-to-batch-to-LLM  (part of IronLeo78 MTV since v0.1.0; it was the standalone pack
ComfyUI-IronLeo78-9Images up to its v0.0.2e)
Nine image slots with thumbnails + a built-in video slot (Start_From / Duration / Frame_Interval)
-> Output_To_LLM: the pictures first, then the video frames, all at the video's frame size, in one batch.
No dependency on VHS: video is decoded with PyAV (bundled with current ComfyUI).
Its frontend: web/ironleo78_9images.js (+ web/il78_sync_logic.js, web/il78_shadow.js). The pack's __init__.py registers the node.
"""
import hashlib
import os
import re

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw, ImageFont, ImageOps

import folder_paths

from . import video_orientation as _orient
from . import video_reader as _reader

try:
    import node_helpers
except Exception:
    node_helpers = None

SLOTS = 9
FORCE_FPS = 24                       # hardcoded force rate
MAX_LLM_FRAMES = 120                 # v0.3.6: at most this many video frames go to the LLM (evenly spaced); a vision LLM spends hundreds of tokens per image
INTERVALS = ["2", "4", "8", "12"]
LLM_V_BIAS = 0.25                    # pictures taller than the video frame: crop window starts 25% into the spare height (keeps heads)
RATIO_TOL = 0.06                     # a picture within 6% of the video ratio gets no advice
VIDEO_SIZES = ["512x288", "672x384", "896x512"]
NONE_MARK = "ironleo78_none"         # v0.0.2d: attribute set on every NONE placeholder, so the IronLeo78 MTV skips an empty slot
_none_cache = {}


# ---------------------------------------------------------------- images
def _none_image(H=512, W=512):
    """Default 'NONE' placeholder picture: [1,H,W,3].
    v0.0.2d: the copy carries NONE_MARK = True. The IronLeo78 MTV reads it (and, as a fallback, the picture's look) and does
    not send an empty slot's NONE picture to the model as a reference."""
    key = (H, W)
    if key not in _none_cache:
        img = Image.new("RGB", (W, H), (32, 32, 32))
        d = ImageDraw.Draw(img)
        size = max(12, min(H, W) // 5)
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:
            font = ImageFont.load_default()
        text = "NONE"
        try:
            l, t, r, b = d.textbbox((0, 0), text, font=font)
            x, y = (W - (r - l)) // 2 - l, (H - (b - t)) // 2 - t
        except Exception:
            x, y = W // 2 - 20, H // 2 - 5
        d.rectangle([2, 2, W - 3, H - 3], outline=(90, 90, 90), width=max(1, min(H, W) // 128))
        d.text((x, y), text, fill=(150, 150, 150), font=font)
        arr = np.array(img).astype(np.float32) / 255.0
        _none_cache[key] = torch.from_numpy(arr)[None,]
    out = _none_cache[key].clone()
    setattr(out, NONE_MARK, True)
    return out


def _open_image(path):
    if node_helpers is not None:
        return node_helpers.pillow(Image.open, path)
    return Image.open(path)


def _load_tensor(path):
    img = _open_image(path)
    img = ImageOps.exif_transpose(img)
    if img.mode == "I":
        img = img.point(lambda v: v * (1 / 255))
    img = img.convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None,]  # [1, H, W, 3]


def _resize(x, h, w):
    return F.interpolate(x, size=(h, w), mode="bicubic",
                         align_corners=False, antialias=True).clamp(0.0, 1.0)


def _crop_fill(t, H, W, vbias=0.5):
    """t: [1,h,w,3] -> [1,H,W,3], scale to cover then crop. Horizontal crop is always centred;
    vbias = where the vertical crop window starts inside the spare height (0.5 = centre, 0 = top)."""
    _, h, w, _ = t.shape
    if (h, w) == (H, W):
        return t
    x = t.permute(0, 3, 1, 2)
    s = max(H / h, W / w)
    nh, nw = max(H, round(h * s)), max(W, round(w * s))
    x = _resize(x, nh, nw)
    top, left = int((nh - H) * vbias), (nw - W) // 2
    out = x[:, :, top:top + H, left:left + W]
    return out.permute(0, 2, 3, 1).contiguous()


# ---------------------------------------------------------------- video
def _decode_video(path, start, duration, interval, size_str, want=None):
    """Seek to `start`, resample to FORCE_FPS, keep every `interval`-th frame,
    crop-to-fill to the preset size. Returns [N,H,W,3] float tensor.
    v0.1.6: the timing / seek / frame repeats / end of file / phone rotation are the pack's shared video_reader.read_frames
    (the same reader as the MTV, so a "Sync from MTV" window lines up with the MTV's segment even when a file does not
    start at time 0). Only the resize below is this node's own."""
    pw, ph = (int(v) for v in size_str.split("x"))
    total = max(1, int(round(duration * FORCE_FPS)))
    view = {}      # v0.1.3: set from the first frame: the frame size W x H (portrait video -> portrait preset)

    def convert(frame, turns):
        # v0.0.2e: the frame is scaled to cover W x H by PyAV (AREA when shrinking) while it is still 8-bit, then centre-cropped
        # and only then made float: a 1080p / 4K frame never exists as a full-size float array. Same crop as _crop_fill.
        # v0.1.3: a phone video stored on its side is turned upright, and portrait / landscape is chosen from the size AS SHOWN.
        fw, fh = int(frame.width), int(frame.height)
        dw, dh = (fh, fw) if turns % 2 else (fw, fh)          # this frame's size as shown
        if not view:
            view.update(W=ph if dh > dw else pw, H=pw if dh > dw else ph)
        W, H = view["W"], view["H"]
        sc = max(W / dw, H / dh)
        nw, nh = max(W, round(dw * sc)), max(H, round(dh * sc))
        try:
            sw, sh = (nh, nw) if turns % 2 else (nw, nh)      # the same size, in the stored (sideways) orientation
            arr = frame.to_ndarray(format="rgb24", width=sw, height=sh, interpolation="AREA" if sc < 1 else "BICUBIC")
            arr = _orient.upright(arr, turns)
            top, left = (nh - H) // 2, (nw - W) // 2
            return torch.from_numpy(np.ascontiguousarray(arr[top:top + H, left:left + W])).float().div_(255.0)[None,]
        except (TypeError, ValueError):      # an older PyAV without resize options: the old full-size path
            arr = _orient.upright(frame.to_ndarray(format="rgb24"), turns).astype(np.float32) / 255.0
            return _crop_fill(torch.from_numpy(arr)[None,], H, W)

    out, _ = _reader.read_frames(path, convert, rate=FORCE_FPS, first=float(start) * FORCE_FPS, count=total,
                                 every=int(interval), want=want)
    if not out:
        raise ValueError(f"IronLeo78 node: no frames found - Start_From ({start:.1f}s) is past the end of the video.")
    if want is not None:      # v0.3.17: the frames that were not wanted are None placeholders: return the wanted ones, plus how many there were
        return torch.cat([t for t in out if t is not None], dim=0), len(out)
    return torch.cat(out, dim=0)


def _decode_video_for_llm(path, start, duration, interval, size_str):
    """v0.3.17: -> (the frames the LLM gets, how many frames the window has). Only those frames (at most MAX_LLM_FRAMES) are resized and
    converted; the others are skipped while decoding. If the file ends before the window does, the frame count differs from the expected one
    and the picks are re-made for the real count (a second, full pass: rare)."""
    expected = -(-max(1, int(round(duration * FORCE_FPS))) // int(interval))      # kept frames of a window that fits in the file
    idx = _llm_frame_indices(expected)
    frames, n = _decode_video(path, start, duration, interval, size_str, want=set(idx))
    if n == expected:
        return frames, n
    return _decode_video(path, start, duration, interval, size_str, want=set(_llm_frame_indices(n)))


# ---------------------------------------------------------------- Output_To_LLM
def _combine_for_llm(pics, video, size_str):
    """pics: list of [1,h,w,3] (filled slots only, slot order). video: [N,H,W,3] or None (no video loaded).
    Everything is put at the VIDEO frame size (the video ratio always wins); pictures are cropped to fill,
    top-biased so heads survive. Pictures first, then the video frames. Nothing at all -> one NONE picture."""
    if video is not None:
        H, W = int(video.shape[1]), int(video.shape[2])
    else:
        pw, ph = (int(v) for v in size_str.split("x"))
        H, W = ph, pw
    parts = [_crop_fill(t, H, W, LLM_V_BIAS) for t in pics]
    if video is not None:
        parts.append(video)
    if not parts:
        return _none_image(H, W)
    return torch.cat(parts, dim=0)


def _off_ratio_slots(singles, H, W, tol=RATIO_TOL):
    """1-based slot numbers whose picture ratio differs from the video frame ratio by more than tol."""
    tr = W / H
    return [i + 1 for i, t in enumerate(singles)
            if t is not None and abs((t.shape[2] / t.shape[1]) / tr - 1.0) > tol]


# v0.1.15: the scenario presets. One .md file per preset in presets/ (edit them, no code); the file name (without .md) is what
# the Preset widget lists. A file has two parts: a line `# SYSTEM` (added after the guide in the LLM's system prompt) and a line
# `# TASK` (put in front of the user's prompt) and, since v0.1.24, `# PROMPT` (a suggested working prompt for the prompt box; EVERY
# preset has one). "None" = no preset (both texts empty).
PRESET_NONE = "None"
PRESET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")


def _preset_sort_key(name):
    """v0.3.0: "10 - x" comes after "9 - x" (the leading number is compared as a number). v0.4.11: "6b - x" comes right after "6 - x"."""
    m = re.match(r"(\d+)([a-z]?)(?=\s|$)", name.split(" ", 1)[0].lower())
    return (int(m.group(1)), m.group(2), name.lower()) if m else (10 ** 6, "", name.lower())


def _preset_names():
    try:
        return sorted((f[:-3] for f in os.listdir(PRESET_DIR) if f.lower().endswith(".md")), key=_preset_sort_key)
    except OSError:
        return []


def _preset_path(name):
    return os.path.join(PRESET_DIR, name + ".md")


# v0.5.0: the presets are named "Category - Name" (sorted alphabetically, grouped by category). A workflow or API prompt saved before
# 0.5.0 holds the OLD numbered name: it is translated here (and in the web UI, see il78_sync_logic.presetAlias), so old workflows load.
PRESET_ALIASES = {
    "1 - Replace main actor": "Swap - Main actor",
    "2 - Replace main actor and environment": "Swap - Main actor and environment",
    "3 - Replace two actors and environment": "Swap - Two actors and environment",
    "4 - Replace environment only": "Swap - Environment only",
    "5 - Restyle video": "Look - Restyle from a picture",
    "6 - Outfit swap": "Swap - Outfit",
    "6b - Outfit and Pose Swap": "Swap - Outfit and pose",
    "7 - Singer performance": "Musician - Singer",
    "8 - Drummer performance": "Musician - Drummer",
    "9 - Bassist performance": "Musician - Bassist",
    "10 - Guitarist performance": "Musician - Guitarist",
    "11 - Time of day or weather": "Weather - Any time of day or weather",
    "12 - IronLeo78 Mode": "Personal - IronLeo78 Mode",
    "13 - Camera retake": "Camera - Retake with a new move",
    "14 - Acting retake": "Performance - Acting retake",
    "15 - Film look and era": "Look - Film look and era",
    "16 - Storyboard shots": "Camera - Storyboard shots",
    "17 - Continue the scene": "Story - Continue the scene",
    "18 - First and last frame": "Camera - First and last frame",
    "19 - Prop swap": "Swap - Prop",
    "20 - Add a character": "Cast - Add a character",
    "21 - Motion transfer": "Performance - Motion transfer",
    "22 - Concert stage": "Stage - Concert",
    "23 - Visual effects": "FX - Visual effects",
    "24 - Clone performer": "Cast - Clone the performer",
}


def resolve_preset(name):
    """v0.5.0: the preset file to use for `name`: the name itself when its file exists, else its new name (an old numbered name), else
    its old name (a user who still has the old file, e.g. the personal preset not renamed yet). Unknown names come back unchanged."""
    if not name or name == PRESET_NONE or os.path.isfile(_preset_path(name)):
        return name
    new = PRESET_ALIASES.get(name)
    if new and os.path.isfile(_preset_path(new)):
        return new
    for old, newer in PRESET_ALIASES.items():
        if newer == name and os.path.isfile(_preset_path(old)):
            return old
    return name


def effective_aliases():
    """v0.6.0 (sweep M1): the aliases the web UI may apply: only those whose NEW file exists and whose OLD file does not. A user who still
    has an old file (the personal preset not renamed yet) keeps seeing and using it under its old name."""
    return {old: new for old, new in PRESET_ALIASES.items()
            if os.path.isfile(_preset_path(new)) and not os.path.isfile(_preset_path(old))}


def preset_choice_ok(name):
    """v0.5.0: True for "None", a preset on disk, or an old / new name that resolve_preset turns into one."""
    return not name or name == PRESET_NONE or os.path.isfile(_preset_path(resolve_preset(name)))


def _parse_preset_full(text):
    """-> {"system", "task", "prompt"}. Text before the first marker is ignored; a missing part is ''. v0.1.24: `# PROMPT` is the
    suggested working prompt the node puts in the prompt box when the preset is chosen (it is not sent to the LLM by itself)."""
    # v0.3.0: `# STEM` (Vocals / Drums / Bass / Guitars) and `# AUDIO` (Custom Audio): the MTV settings a musician preset starts from
    text = text.lstrip("\ufeff")      # v0.3.4: a file saved with a BOM (older Notepad) must not lose its first section
    parts = {"SYSTEM": [], "TASK": [], "PROMPT": [], "I2V SYSTEM": [], "I2V TASK": [], "I2V PROMPT": [], "STEM": [], "AUDIO": []}      # v0.2.5: the i2v version of each
    cur = None
    for line in text.replace("\r\n", "\n").split("\n"):
        key = line.strip()[2:].strip().upper() if line.strip().startswith("# ") else None
        if key in parts:
            cur = key
            continue
        if cur:
            parts[cur].append(line)
    return {k.lower().replace(" ", "_"): "\n".join(v).strip() for k, v in parts.items()}


def _parse_preset(text, mode="v2v"):
    """-> (system, task) of the video-to-video text, or (v0.2.5) of the image-to-video text when mode == "i2v"."""
    d = _parse_preset_full(text)
    return (d["i2v_system"], d["i2v_task"]) if mode == "i2v" else (d["system"], d["task"])


def preset_audio_info():
    """v0.3.0: {preset name: {"audio": Choose Audio latent value or "", "stem": Audio Stem value or ""}} (the musician presets set both
    on the MTV when they are chosen; the other presets give empty strings)."""
    out = {PRESET_NONE: {"audio": "", "stem": ""}}
    for name in _preset_names():
        try:
            with open(_preset_path(name), encoding="utf-8-sig") as f:
                d = _parse_preset_full(f.read())
            out[name] = {"audio": d["audio"].splitlines()[0].strip() if d["audio"] else "",
                         "stem": d["stem"].splitlines()[0].strip() if d["stem"] else ""}
        except OSError:
            out[name] = {"audio": "", "stem": ""}
    return out


def preset_prompts(mode="v2v"):
    """v0.1.24: {preset name: suggested working prompt} for every preset file (the web UI fills the prompt box with it).
    v0.2.5: mode "i2v" gives the image-to-video prompts."""
    out = {PRESET_NONE: ""}
    key = "i2v_prompt" if mode == "i2v" else "prompt"
    for name in _preset_names():
        try:
            with open(_preset_path(name), encoding="utf-8-sig") as f:
                out[name] = _parse_preset_full(f.read())[key]
        except OSError:
            out[name] = ""
    return out


def _read_preset(name, mode="v2v"):
    if not name or name == PRESET_NONE:
        return "", ""
    name = resolve_preset(name)      # v0.5.0: old numbered names still work
    path = _preset_path(name)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Preset file not found: presets/{name}.md")
    with open(path, encoding="utf-8-sig") as f:
        system, task = _parse_preset(f.read(), mode)
    if mode == "i2v" and not (system and task):
        raise ValueError(f"Preset '{name}' has no image-to-video version (add # I2V SYSTEM and # I2V TASK to presets/{name}.md)")
    return system, task


def _labels(slots):
    """v0.3.4: slot number -> the <Picture N> label the MTV gives it (it counts only the pictures that are sent, in slot order)."""
    return {s: i + 1 for i, s in enumerate(slots)}


def _pic_names(slots):
    """"<Picture 1>, <Picture 2> (slot 3)": the label, and the slot when it differs."""
    return ", ".join(f"<Picture {i + 1}>" + (f" (slot {s})" if s != i + 1 else "") for i, s in enumerate(slots))


def _gap_note(slots):
    """Only when a slot is empty between the filled ones (or the first ones): tell the LLM that labels and slots differ."""
    if not slots or slots == list(range(1, len(slots) + 1)):
        return ""
    return (" The numbers in <Picture N> already count only the pictures that are sent (the slot is shown in brackets): your output must use these labels. "
            "A request that names a picture by its slot number (for example \"Picture 3\") means that slot.")


def _relabel(text, slots):
    """v0.3.4: the preset rules name pictures by SLOT (<Picture 3> = the environment). Rewrite them with the labels the MTV will use;
    a slot that is not filled becomes "<slot N: not provided>", so it can never be mistaken for another picture."""
    lab = _labels(slots)
    return re.sub(r"<Picture (\d+)>", lambda m: f"<Picture {lab[int(m.group(1))]}>" if int(m.group(1)) in lab else f"<slot {m.group(1)}: not provided>", text)


def _llm_text(info, preset_system, preset_task):
    """v0.1.17: the one text for the LLM: frame layout + times, then the preset rules, then the preset task (which ends where the
    user's own prompt is appended by the generator). No preset = the frame info alone."""
    return "\n\n".join(p for p in (info, preset_system, preset_task) if p)


def _llm_frame_indices(n_frames):
    """v0.3.6: which frames of the window the LLM gets: all of them up to MAX_LLM_FRAMES, else that many evenly spaced ones (first and last kept)."""
    if n_frames <= MAX_LLM_FRAMES:
        return list(range(n_frames))
    return [round(i * (n_frames - 1) / (MAX_LLM_FRAMES - 1)) for i in range(MAX_LLM_FRAMES)]


def _frame_info(slots, n_frames, interval, indices=None):
    """v0.1.13: the sentence that tells the LLM how its image batch is laid out (pictures first, then the video at
    24 / Frame_Interval frames per second), so the user no longer types it. slots = 1-based numbers of the filled
    pictures, n_frames = frames of the video window (None = no video)."""
    fps = FORCE_FPS / int(interval)
    fps_txt = f"{fps:g}"
    if slots:
        head = (f"The first {len(slots)} image{'s are' if len(slots) > 1 else ' is'} the reference "
                f"picture{'s' if len(slots) > 1 else ''} ({_pic_names(slots)}, in this order){_gap_note(slots)}")
    else:
        head = "There are no reference pictures"
    if n_frames is None:
        return head + " and no video."
    # v0.1.16: the time of every frame is computed here (a small LLM does not do frame -> seconds reliably)
    idx = list(indices) if indices is not None else list(range(n_frames))
    times = ", ".join(f"frame {k + 1} = {_stamp(i / fps)}" for k, i in enumerate(idx))
    if len(idx) < n_frames:           # v0.3.6: only some of the frames are sent (a cap, to keep the request small)
        what = (f"{len(idx)} frames of Video 1 (evenly spaced out of its {n_frames} frames, to keep the request small; the first and the last are included), "
                f"seen at {fps_txt} frame{'s' if fps != 1 else ''} per second")
    else:
        what = (f"{n_frames} frames of Video 1, which is shown at {fps_txt} frame{'s' if fps != 1 else ''} per second "
                f"(one frame every {1 / fps:g} s)")
    return (f"{head}{', followed by' if slots else '. The images are'} the {what}. "
            f"Video 1 is sampled at {fps_txt} FPS and lasts {_stamp(n_frames / fps)}. "
            f"The video frames are at these exact times (use them for every time-stamp): {times}.")


def _frame_info_i2v(slots, duration):
    """v0.2.5: the frame text of the image-to-video mode: no video, only the pictures, and the length of the clip to describe."""
    if slots:
        head = (f"This is an image-to-video request: there is NO video and no Video 1. The {len(slots)} image{'s you receive are' if len(slots) > 1 else ' you receive is'} "
                f"the reference picture{'s' if len(slots) > 1 else ''} ({_pic_names(slots)}, in this order).{_gap_note(slots)}")
    else:
        head = "This is an image-to-video request: there is NO video and no Video 1, and there are no reference pictures."
    end = _stamp(float(duration))
    return (f"{head} The target clip lasts about {round(float(duration), 2):g} seconds: write the timeline between 00:00.000 and {end} "
            f"and use no time-stamp after {end}.")


def _stamp(seconds):
    """MM:SS.mmm, the time-stamp format of the guide."""
    ms = int(round(seconds * 1000))
    return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}"


# ---------------------------------------------------------------- node
class IronLeo78_9ImagesToBatchToLLM:
    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        # Hidden by the web extension; the thumbnail grid / video cell drive these.
        for i in range(1, SLOTS + 1):
            required[f"image_{i}"] = ("STRING", {"default": "", "socketless": True})
        required["video"] = ("STRING", {"default": "", "socketless": True})
        required["Start_From"] = ("FLOAT", {"default": 0.0, "min": 0.0, "max": 36000.0, "step": 0.1,
                                            "tooltip": "Start of the video window, in seconds."})
        required["Duration"] = ("FLOAT", {"default": 5.0, "min": 1.0, "max": 20.0, "step": 0.5,
                                          "tooltip": "Length of the video window, 1-20 seconds."})
        required["Frame_Interval"] = (INTERVALS, {"default": "12",      # v0.1.11: the user's tuned defaults (was "2")
                                                  "tooltip": "Keep every Nth frame (of 24 fps) for the LLM."})
        required["Video_Size"] = (VIDEO_SIZES, {"default": "512x288"})      # v0.6.1: the user's default (was 672x384)
        # v0.1.15: appended LAST (a saved workflow without it simply gets the default)
        required["Preset"] = ([PRESET_NONE] + _preset_names(), {"default": PRESET_NONE,
                              "tooltip": "Scenario preset for the LLM prompt generator (files in the pack's presets/ folder). "
                                         "None = no preset. The preset travels inside the LLM_Frame_Info output."})
        return {"required": required}

    RETURN_TYPES = ("IMAGE",) * (SLOTS + 2) + ("STRING",)
    # v0.1.17: ONE text output carries everything the LLM needs besides the pictures (frame layout + times + the preset); it is LAST
    RETURN_NAMES = (("Output_To_LLM",) + tuple(f"Picture_{i}" for i in range(1, SLOTS + 1))
                    + ("video_frames", "LLM_Frame_Info"))
    FUNCTION = "run"
    CATEGORY = "IronLeo78/MTV"           # v0.1.0: next to the other nodes of the pack (was "IronLeo78"; workflows are not affected)
    DESCRIPTION = ("9 pictures + 1 video in one node. Output_To_LLM = the filled pictures first, then the video "
                   "frames, all at the video frame size (pictures are cropped to fill, top-biased; empty slots "
                   "skipped). Picture_1..9 = each slot alone at its original size (NONE picture if empty); "
                   "video_frames = the video window alone (24 fps, every Nth frame). Tip: feed 16:9 pictures "
                   "so nothing you need gets cropped in Output_To_LLM.")

    @classmethod
    def IS_CHANGED(cls, **kw):
        m = hashlib.sha256()
        for k in sorted(kw):
            if k.startswith("image_") or k == "video":
                continue
            m.update(f"{k}={kw[k]}|".encode())
        # v0.0.2e: every file (pictures too) is identified by name + size + mtime, never read: a picture replaced under the
        # same name still changes its size or mtime, and a queue no longer reads up to nine full pictures from disk
        p = resolve_preset(kw.get("Preset"))      # v0.5.0: an old numbered name hashes its renamed file
        if p and p != PRESET_NONE and os.path.isfile(_preset_path(p)):      # v0.1.15: an edited preset file re-runs the node
            st = os.stat(_preset_path(p))
            m.update(f"|preset:{st.st_size}:{st.st_mtime_ns}".encode())
        for key in [f"image_{i}" for i in range(1, SLOTS + 1)] + ["video"]:
            v = (kw.get(key) or "").strip()
            m.update(f"|{key}:{v}".encode())
            if v and folder_paths.exists_annotated_filepath(v):
                st = os.stat(folder_paths.get_annotated_filepath(v))
                m.update(f"{st.st_size}:{st.st_mtime_ns}".encode())
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, Preset=None):
        """v0.5.0: the Preset combo is checked here instead of by ComfyUI, so a workflow saved with an old numbered preset name (renamed in
        0.5.0) still runs: resolve_preset translates it. Only this input skips the built-in combo check."""
        if Preset is None or preset_choice_ok(Preset):
            return True
        return f"Preset not found: {Preset} (no file presets/{Preset}.md)"

    def run(self, Start_From, Duration, Frame_Interval, Video_Size, Preset=PRESET_NONE, Mode="v2v", **kw):
        # ---- pictures
        singles = [None] * SLOTS
        for i in range(1, SLOTS + 1):
            v = (kw.get(f"image_{i}") or "").strip()
            if not v:
                continue
            if not folder_paths.exists_annotated_filepath(v):
                raise FileNotFoundError(f"Image slot {i}: file not found: {v}")
            singles[i - 1] = _load_tensor(folder_paths.get_annotated_filepath(v))
        filled = [t for t in singles if t is not None]
        pics = [t if t is not None else _none_image() for t in singles]

        # ---- video (None = no video loaded)
        i2v = Mode == "i2v"                                      # v0.2.5: image-to-video: a loaded video is ignored (not even decoded)
        vname = "" if i2v else (kw.get("video") or "").strip()
        video, n_video = None, 0
        if vname:
            if not folder_paths.exists_annotated_filepath(vname):
                raise FileNotFoundError(f"Video file not found: {vname}")
            video, n_video = _decode_video_for_llm(folder_paths.get_annotated_filepath(vname),
                                                   float(Start_From), float(Duration), Frame_Interval, Video_Size)
        if video is not None:
            video_out = video      # v0.3.17: only the frames the LLM gets (the Prompt Generator does not use this output)
        else:
            pw, ph = (int(v) for v in Video_Size.split("x"))
            video_out = _none_image(ph, pw)

        # ---- Output_To_LLM: pictures first, then the video frames, all at the video frame size
        llm_idx = None if video is None else _llm_frame_indices(n_video)      # v0.3.6: the LLM gets at most MAX_LLM_FRAMES frames
        batch = _combine_for_llm(filled, video, Video_Size)
        off = _off_ratio_slots(singles, batch.shape[1], batch.shape[2])
        if off:
            names = ", ".join(f"Picture_{i}" for i in off)
            print(f"[IronLeo78] Tip: {names} {'is' if len(off) == 1 else 'are'} not the video ratio "
                  f"({batch.shape[2]}x{batch.shape[1]}): the copy in Output_To_LLM is cropped to fill. "
                  f"Use 16:9 pictures to keep everything you need in frame (Picture_N outputs are untouched).")

        slots = [i + 1 for i, t in enumerate(singles) if t is not None]
        if i2v:
            info = _frame_info_i2v(slots, Duration)
        else:
            info = _frame_info(slots, None if video is None else n_video, Frame_Interval, llm_idx)
        preset_system, preset_task = _read_preset(Preset, "i2v" if i2v else "v2v")
        preset_system, preset_task = _relabel(preset_system, slots), _relabel(preset_task, slots)      # v0.3.4: the rules use the labels the MTV gives
        return (batch, *pics, video_out, _llm_text(info, preset_system, preset_task))


# v0.1.21: the standalone "IronLeo78 9-Images-to-batch-to-LLM" node is REMOVED from the pack (nothing registered here). This module
# stays as the internal base of the IronLeo78-MTV-Prompt-Generator (prompt_generator.py), which subclasses the class above.
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
