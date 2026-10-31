"""
IronLeo78 MTV: song stems  (Hybrid Demucs + on-disk cache)
------------------------------------------------------------
Splits a song into Bass / Drums / Guitars / Vocals ONCE and keeps the four stems on disk, so every later
Run (and every later session) just reads a file:

    ComfyUI/output/<Song>/stems/<Song>_Vocals.wav
                                <Song>_Guitars.wav     (Demucs' "other" stem: guitars + keys + synths ...)
                                <Song>_Drums.wav
                                <Song>_Bass.wav
                                <Song>_stems.json      (what the stems were made from; written LAST)

The cache folder is named after the song; what is inside is only reused when it still matches the song's
CONTENT (SHA-1), the model and the separation settings, so:
  * re-uploading or touching the same song (same name, same content) does not trigger a new separation,
  * an edited / different song under the same name, or changed settings, does.
Nothing here runs unless a stem (not "Full") is selected, and this module imports no torch / torchaudio /
comfy at import time (they are imported inside separate_audio only).

Credit: https://pytorch.org/audio/stable/tutorials/hybrid_demucs_tutorial.html
"""

import contextlib
import datetime
import gc
import hashlib
import json
import logging
import os
import threading
import time
import wave as _wave
from zipfile import BadZipFile

import numpy as np

log = logging.getLogger("IronLeo78.MTV.stems")

STEM_FULL = "Full"                                              # the original audio, no separation (called "Song" until v0.0.6)
STEM_LEGACY_SONG = "Song"                                       # the old name: still accepted, means Full
STEM_LABELS = ("Vocals", "Guitars", "Drums", "Bass")            # the four stems, in the order shown on the node
STEM_CHOICES = (STEM_FULL,) + STEM_LABELS
DEMUCS_KEY = {"Vocals": "vocals", "Guitars": "other", "Drums": "drums", "Bass": "bass"}   # label -> Demucs source

MODEL_NAME = "HDEMUCS_HIGH_MUSDB_PLUS"
CACHE_SCHEMA = 1                      # bump to invalidate every stem cache on disk
STEMS_SUBFOLDER = "stems"

# Hardcoded separation settings (same as the standalone IronLeo78 Song to Stems v0.2).
# They are part of the cache key: change one and the stems are made again.
CHUNK_FADE_SHAPE = "linear"
CHUNK_LENGTH = 10.0                   # seconds per chunk
CHUNK_OVERLAP = 0.1

_LOCK = threading.Lock()              # one separation at a time (two queued Runs never write the same files)
_HASHES = {}                          # (path, mtime_ns, size) -> sha1 of the song file


# ---------------------------------------------------------------------- #
# cache location / identity
# ---------------------------------------------------------------------- #
def stem_folder(output_dir, song):
    return os.path.join(output_dir, song, STEMS_SUBFOLDER)


def stem_file(output_dir, song, label):
    return os.path.join(stem_folder(output_dir, song), f"{song}_{label}.wav")


def meta_file(output_dir, song):
    return os.path.join(stem_folder(output_dir, song), f"{song}_stems.json")


def file_sha1(path):
    """SHA-1 of a file's content (streamed). Memoised per (path, mtime, size): a re-check costs nothing."""
    st = os.stat(path)
    key = (os.path.abspath(path), int(st.st_mtime_ns), int(st.st_size))
    hit = _HASHES.get(key)
    if hit:
        return hit
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    if len(_HASHES) > 32:
        _HASHES.pop(next(iter(_HASHES)))
    _HASHES[key] = h.hexdigest()
    return _HASHES[key]


def _settings():
    return {"fade": CHUNK_FADE_SHAPE, "chunk_length": CHUNK_LENGTH, "chunk_overlap": CHUNK_OVERLAP}


def cache_name(output_dir, song, source_sha1, source_name):
    """v0.1.9: the name the stems of this song are kept under. Normally the cleaned song name. But two DIFFERENT song files
    can clean to the same name ("My Song!.wav" and "My Song?.mp3", or "song.wav" and "song.mp3"): until 0.1.9 they kept
    replacing each other's stems (each one ran Demucs again). When the folder already holds the stems of ANOTHER file
    (another content and another file name), this song uses "<song>_<first 8 characters of its SHA-1>" instead.
    The same file edited (same name, new content) still replaces its own stems, as before."""
    try:
        with open(meta_file(output_dir, song), encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return song
    if not isinstance(meta, dict):
        return song
    other_content = meta.get("source_sha1") not in (None, source_sha1)
    other_file = meta.get("source_name") not in (None, source_name)
    return f"{song}_{source_sha1[:8]}" if other_content and other_file else song


def read_cache(output_dir, song, source_sha1):
    """The cached stems of this song as {label: path}, or None when anything is missing / stale / truncated."""
    try:
        with open(meta_file(output_dir, song), encoding="utf-8") as f:
            meta = json.load(f)
        if (meta.get("schema") != CACHE_SCHEMA or meta.get("model") != MODEL_NAME
                or meta.get("settings") != _settings() or meta.get("source_sha1") != source_sha1):
            return None
        paths = {}
        for label in STEM_LABELS:
            path = stem_file(output_dir, song, label)
            if not os.path.isfile(path) or os.path.getsize(path) != int(meta["files"][label]["bytes"]):
                return None
            paths[label] = path
        return paths
    except (OSError, ValueError, KeyError, TypeError):
        return None


# ---------------------------------------------------------------------- #
# writing
# ---------------------------------------------------------------------- #
def write_wav(path, samples, sample_rate):
    """16-bit PCM WAV from a float array [channels, frames] (stdlib only: no soundfile / torchaudio.save needed).
    Written to a temp file and renamed, so a crash never leaves a half-written stem under the real name."""
    data = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    tmp = path + ".tmp"
    try:
        with contextlib.closing(_wave.open(tmp, "wb")) as w:
            w.setnchannels(int(data.shape[0]))
            w.setsampwidth(2)
            w.setframerate(int(sample_rate))
            step = 1 << 20
            for i in range(0, data.shape[1], step):
                block = data[:, i:i + step].T                      # [frames, channels] interleaved
                w.writeframes((block * 32767.0).round().astype("<i2").tobytes())
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)


# ---------------------------------------------------------------------- #
# Hybrid Demucs (ported from the standalone Song to Stems node)
# ---------------------------------------------------------------------- #
def _ensure_stereo(audio):
    """[channels, frames] -> stereo: mono is duplicated, multichannel is downmixed from its first two channels."""
    if audio.shape[0] == 2:
        return audio
    if audio.shape[0] == 1:
        return audio.repeat(2, 1)
    return audio.narrow(0, 0, 2).mean(dim=0, keepdim=True).repeat(2, 1)


def _separate_sources(model, mix, sample_rate, device, progress=None):
    """Apply the model chunk by chunk with fades and add the overlaps up (torchaudio's Hybrid Demucs tutorial)."""
    import torch
    from torchaudio.transforms import Fade

    batch, channels, length = mix.shape
    chunk_len = int(sample_rate * CHUNK_LENGTH * (1 + CHUNK_OVERLAP))
    start, end = 0, chunk_len
    overlap_frames = CHUNK_OVERLAP * sample_rate
    fade = Fade(fade_in_len=0, fade_out_len=int(overlap_frames), fade_shape=CHUNK_FADE_SHAPE)
    final = torch.zeros(batch, len(model.sources), channels, length, device=device)

    step_total = max(1, int(np.ceil(length / max(1, chunk_len - overlap_frames))))
    done = 0
    while start < length - overlap_frames:
        try:      # lets the Cancel button stop a long separation
            import comfy.model_management as mm
            mm.throw_exception_if_processing_interrupted()
        except ImportError:
            pass
        chunk = mix[:, :, start:end]
        with torch.no_grad():
            out = model.forward(chunk)
        out = fade(out)
        final[:, :, :, start:end] += out
        if start == 0:
            fade.fade_in_len = int(overlap_frames)
            start += int(chunk_len - overlap_frames)
        else:
            start += chunk_len
        end += chunk_len
        if end >= length:
            fade.fade_out_len = 0
        done += 1
        if progress:
            progress(min(done, step_total), step_total)
    return final


def separate_audio(audio, progress=None):
    """AUDIO dict ({"waveform": [1, C, N], "sample_rate": sr}) -> ({label: float32 [2, N']}, model sample rate).
    Runs Hybrid Demucs on the ComfyUI device and gives the memory back afterwards."""
    import comfy.model_management as mm
    import torch
    from torchaudio.pipelines import HDEMUCS_HIGH_MUSDB_PLUS
    from torchaudio.transforms import Resample

    device = mm.get_torch_device()
    bundle = HDEMUCS_HIGH_MUSDB_PLUS
    try:
        model = bundle.get_model()
    except (BadZipFile, RuntimeError) as exc:
        raise RuntimeError(
            "Failed to load the Hybrid Demucs model: the downloaded checkpoint appears to be corrupted. "
            "Delete the cached model file and run again to download it afresh "
            "(usually in ~/.cache/torch/hub/checkpoints/).") from exc
    model_sr = int(bundle.sample_rate)

    def attempt():
        net = model.to(device).eval()
        wave = audio["waveform"].squeeze(0).to(device).float()
        wave = _ensure_stereo(wave)
        if int(audio["sample_rate"]) != model_sr:
            wave = Resample(int(audio["sample_rate"]), model_sr).to(device)(wave)
        ref = wave.mean(0)
        ref_mean, ref_std = ref.mean(), ref.std().clamp_min(1e-8)       # silent input: no divide by zero
        wave = (wave - ref_mean) / ref_std
        out = _separate_sources(net, wave[None], model_sr, device, progress)[0]
        out = out * ref_std + ref_mean
        return {name: out[i].cpu().numpy() for i, name in enumerate(net.sources)}

    try:
        try:
            result = attempt()
        except RuntimeError as exc:
            if "out of memory" not in str(exc).lower():
                raise
            log.warning("Stem separation ran out of memory: unloading ComfyUI models and retrying once")
            mm.unload_all_models()
            mm.soft_empty_cache()
            result = attempt()
    finally:
        with contextlib.suppress(Exception):
            model.to("cpu")
        del model
        gc.collect()
        with contextlib.suppress(Exception):
            mm.soft_empty_cache()
        if torch.cuda.is_available():
            with contextlib.suppress(Exception):
                torch.cuda.empty_cache()
    stems = {}
    for label, key in DEMUCS_KEY.items():
        if key not in result:
            raise ValueError(f"Hybrid Demucs returned no '{key}' source")
        stems[label] = result[key]
    return stems, model_sr


# ---------------------------------------------------------------------- #
# the public entry point
# ---------------------------------------------------------------------- #
def ensure_stems(source_path, song, output_dir, get_audio, progress=None, separate=None):
    """Make sure the four stems of this song are on disk. Returns ({label: path}, info).

    get_audio  callable -> AUDIO dict of the song; only called when a separation is needed.
    separate   test hook: replaces separate_audio.
    info       {"cached": bool, "seconds": separation time (0 when cached), "folder": str}
    """
    sha = file_sha1(source_path)
    with _LOCK:
        song = cache_name(output_dir, song, sha, os.path.basename(source_path))      # v0.1.9
        paths = read_cache(output_dir, song, sha)
        folder = stem_folder(output_dir, song)
        if paths:
            return paths, {"cached": True, "seconds": 0.0, "folder": folder}

        t0 = time.time()
        audio = get_audio()
        if audio is None:
            raise RuntimeError(f"Could not read the audio of '{os.path.basename(source_path)}' to separate it into stems.")
        stems, sr = (separate or separate_audio)(audio, progress)

        peak = max(float(np.abs(s).max()) if s.size else 0.0 for s in stems.values())
        gain = 0.999 / peak if peak > 1.0 else 1.0     # one common gain: stems stay balanced, nothing clips
        os.makedirs(folder, exist_ok=True)
        with contextlib.suppress(OSError):
            os.remove(meta_file(output_dir, song))     # invalid until every stem is rewritten
        files = {}
        for label in STEM_LABELS:
            path = stem_file(output_dir, song, label)
            write_wav(path, stems[label] * gain, sr)
            files[label] = {"file": os.path.basename(path), "bytes": os.path.getsize(path)}
        meta = {"schema": CACHE_SCHEMA, "model": MODEL_NAME, "settings": _settings(),
                "source_name": os.path.basename(source_path), "source_sha1": sha,
                "sample_rate": int(sr), "frames": int(next(iter(stems.values())).shape[-1]),
                "peak_gain": round(gain, 6), "files": files,
                "created": datetime.datetime.now().isoformat(timespec="seconds")}
        tmp = meta_file(output_dir, song) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        os.replace(tmp, meta_file(output_dir, song))   # written LAST: its presence means the cache is complete
        seconds = time.time() - t0
        log.info("stems of '%s' separated in %.1f s and saved to %s", song, seconds, folder)
        return {label: stem_file(output_dir, song, label) for label in STEM_LABELS}, \
            {"cached": False, "seconds": seconds, "folder": folder}
