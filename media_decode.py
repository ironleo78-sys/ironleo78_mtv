"""Video / audio decoding and the picture sizing helpers. Moved out of mtv.py in v0.3.17."""

import logging
import math
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
import folder_paths
from . import video_orientation as _orient
from . import video_reader as _reader
from .consts import NONE_CHOICE, RESIZE_METHOD

log = logging.getLogger("IronLeo78.MTV")


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


# v0.1.6: opening, seeking and reading video now live in video_reader.py (one reader for the MTV and the 9-Images node).
# These names stay here because the audio side (_decode_audio, _probe_seconds, ...) and the tests use them.
_require_av = _reader.require_av
_open_media = _reader.open_media
_container_t0 = _reader.container_t0
_seek = _reader.seek


def _decode_video(path, force_rate, skip, cap, shape=None):
    """
    Decode `cap` frames starting at output-frame `skip`.
    force_rate > 0 resamples to that fps (frames dropped/duplicated by timestamp),
    force_rate == 0 keeps the native rate.
    Returns (uint8 array [N,H,W,3] or None if past the end, info dict).
    v0.1.1: `shape` (optional) is applied to every decoded frame (uint8 [H,W,3], already rotated) as soon as it is decoded, and
    the result is a torch.stack of what it returns. The MTV uses it to crop + shrink each frame at once, so a 1080p / 4K segment
    never exists in memory at full size (it used to: about 2.9 GB of float32 for a 5 s 1080p segment, 11.5 GB for 4K).
    v0.1.3: a phone video stored on its side is turned upright (video_orientation.py).
    v0.1.6: the timing / seek / repeats / rotation are the shared video_reader.read_frames (the same reader as the 9-Images node).
    """
    def convert(frame, turns):
        arr = _orient.upright(frame.to_ndarray(format="rgb24"), turns)
        return arr if shape is None else shape(arr)

    out, info = _reader.read_frames(path, convert, rate=force_rate if force_rate and force_rate > 0 else None,
                                    first=skip, count=cap)
    if not out:
        return None, info
    return (np.stack(out) if shape is None else torch.stack(out)), info


def _video_frame_plan(src_w, src_h, mp):
    """v0.1.1 (the maths of _load_video until 0.1.0, unchanged): the target size at the megapixel budget (multiples of 32) and
    the centre crop to its aspect, so nothing is stretched. Returns (target_w, target_h, (x, y, crop_w, crop_h))."""
    r = src_w / src_h
    tw = math.sqrt(mp * 1_000_000 * r)
    th = tw / r
    target_width = max(32, int(round(tw / 32.0)) * 32)
    target_height = max(32, int(round(th / 32.0)) * 32)
    final_r = target_width / target_height
    if src_w / src_h > final_r:
        crop_h = src_h
        crop_w = int(round(src_h * final_r))
    else:
        crop_w = src_w
        crop_h = int(round(src_w / final_r))
    crop_w = max(1, min(crop_w, src_w))
    crop_h = max(1, min(crop_h, src_h))
    return target_width, target_height, ((src_w - crop_w) // 2, (src_h - crop_h) // 2, crop_w, crop_h)


def _shape_video_frame(arr, plan):
    """v0.1.1: ONE decoded frame (uint8 [H,W,3]) -> float [h,w,3] at the target size: crop first (in uint8), then to float, then
    bicubic resize. Only one full-size frame is ever in memory.
    v0.1.2: antialias=True (review item #3). A 1920 px frame shrunk to about 600 px without it skips most source pixels, so fine
    detail turns into jagged, shimmering edges in the reference video; with it every source pixel counts (like the Picture_n
    inputs, which already used it). It is only switched on when the frame is shrunk: torch's antialiased bicubic also uses a
    slightly different curve when enlarging, and an enlarged video has no detail to lose, so it keeps the pixels of v0.1.1."""
    target_w, target_h, (sx, sy, cw, ch) = plan
    t = torch.from_numpy(np.ascontiguousarray(arr[sy:sy + ch, sx:sx + cw])).float().div_(255.0)
    if (cw, ch) == (target_w, target_h):
        return t
    t = F.interpolate(t.permute(2, 0, 1)[None], size=(target_h, target_w), mode="bicubic", align_corners=False,
                      antialias=cw > target_w or ch > target_h)
    return torch.clamp(t, 0.0, 1.0)[0].permute(1, 2, 0)


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
            except Exception as e:      # v0.0.9r
                log.debug("audio resampler flush failed (%s)", e)

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
