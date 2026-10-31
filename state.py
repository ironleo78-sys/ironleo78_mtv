"""Where the pack keeps what it writes (ComfyUI/user/ironleo78_mtv), the segment counters per song, and the Guide's last frames. Moved out of mtv.py in v0.4.6."""

import logging
import contextlib
import csv
import hashlib
import json
import os
import re
import shutil
import threading
import numpy as np
import torch
from PIL import Image
import folder_paths

from .consts import NONE_CHOICE, SCENE_TAG, VIDEO_EXTS, _replace_retry
from .naming import _manifest_path
from .media_decode import _open_media

log = logging.getLogger("IronLeo78.MTV")


PACK_DIR = os.path.dirname(__file__)
DATA_FILES = ("mtv_state.json", "mtv_defaults.json", "mtv_last_frame.png")      # + mtv_last_frame_<sha>.png (one per song)


def _data_dir():
    """v0.1.10 (review #7): where the pack keeps what it writes while it runs (segment counters, the saved set, the Guide's
    last frames): ComfyUI/user/ironleo78_mtv/. Until 0.1.9 they sat in the pack folder, which an update / reinstall replaces.
    Falls back to the pack folder when ComfyUI gives no user directory (an old ComfyUI, the tests)."""
    try:
        base = folder_paths.get_user_directory()
    except Exception:
        base = None
    return os.path.join(base, "ironleo78_mtv") if isinstance(base, str) and base else PACK_DIR


def _move_old_data(src_dir, dst_dir):
    """v0.1.10: moves the files an older version left in the pack folder to the new place, once. A file that already exists
    at the new place is never overwritten (the old copy is then left where it is). Returns the moved names."""
    if os.path.abspath(src_dir) == os.path.abspath(dst_dir) or not os.path.isdir(src_dir):
        return []
    moved = []
    for name in sorted(os.listdir(src_dir)):
        if not (name in DATA_FILES or (name.startswith("mtv_last_frame_") and name.endswith(".png"))):
            continue
        target = os.path.join(dst_dir, name)
        if os.path.exists(target):
            continue
        try:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.move(os.path.join(src_dir, name), target)
            moved.append(name)
        except OSError as e:
            log.warning("could not move %s to %s: %s", name, dst_dir, e)
    return moved


DATA_DIR = _data_dir()
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    _moved = _move_old_data(PACK_DIR, DATA_DIR)
    if _moved:
        log.info("moved %s from the pack folder to %s (v0.1.10: kept outside the pack from now on)", ", ".join(_moved), DATA_DIR)
except OSError as _e:
    log.warning("could not prepare %s (%s): using the pack folder", DATA_DIR, _e)
    DATA_DIR = PACK_DIR
STATE_FILE = os.path.join(DATA_DIR, "mtv_state.json")

LAST_FRAME_FILE = os.path.join(DATA_DIR, "mtv_last_frame.png")
GUIDE_FRAME_IDX = 0           # the previous run's last frame guides the very first frame


# ---------------------------------------------------------------------- #
# segment counter state
# ---------------------------------------------------------------------- #
# v0.0.9l: ONE lock for every change of mtv_state.json. The panel routes (jump / reset / segments, served on the web server's
# thread) and a finishing Run (executor thread) both do read -> change -> write; without it one could read the file, the other
# write it, and the first would then write back its stale copy (a lost "furthest" or guide-frame marker). It is an RLock so a
# function that holds it can call another that takes it. It only protects ONE process (ComfyUI is one); it is never held while
# a model runs or a picture is saved, only around the few lines that touch the file.
_STATE_LOCK = threading.RLock()


def _load_state():
    # v0.4.12 (sweep B1): reads take the lock too, so the panel's read (route thread) never holds the file open while a Run
    # replaces it (Windows refuses to replace an open file). The lock is an RLock: a writer that already holds it reads freely.
    with _STATE_LOCK:
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        return {}


def _write_state(state):
    """v0.0.9j: atomic. The JSON goes to a temporary file next to mtv_state.json, is flushed to disk, then os.replace swaps it in
    in one step: a crash / kill mid-write leaves the OLD file intact instead of a truncated one (which _load_state reads as {} =
    the segment counter silently back at 0). UTF-8 explicit, like the manifests and the defaults file."""
    tmp = STATE_FILE + ".tmp"
    with _STATE_LOCK:       # v0.0.9l: two writers can no longer share the same .tmp
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f)
                f.flush()
                with contextlib.suppress(OSError):
                    os.fsync(f.fileno())
            _replace_retry(tmp, STATE_FILE)      # v0.4.12 (sweep B1): retried on a Windows "Access denied"
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(tmp)
            raise


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# v0.1.8 (review #8 / U2): ONE COUNTER PER SONG. Until 0.1.7 every MTV node and every song shared one counter (switching songs
# continued at the old song's segment). Now mtv_state.json keeps a counter per "counter key" under "songs":
#     {"index": .., "furthest": .., "guide_frame_for": ..,                  <- the shared counter (key ''), as before 0.1.8
#      "songs": {"audio:Song.wav": {"index": .., "furthest": .., "guide_frame_for": ..}, "video:clip.mp4": {..}},
#      "adopted": true}
# The key comes from the node's Custom Audio File (else its Video File): the Run, the panel's routes and the 9-Images Sync all
# send those widget values. Nodes on the SAME song share its counter (on purpose: it is the song's position). The first song
# that writes after the update to 0.1.8 inherits the old shared counter once ("adopted"), so nobody loses their place.
SONGS_STATE_KEY = "songs"
_COUNTER_FIELDS = ("index", "furthest", "guide_frame_for")


def _counter_key(params):
    """Whose counter: 'audio:<Custom Audio File>' when one is selected, else 'video:<Video File>', else '' (the shared one)."""
    for prefix, name in (("audio", "Custom Audio File"), ("video", "Video File")):
        value = str((params or {}).get(name) or "").replace(" [input]", "").strip()
        if value and value != NONE_CHOICE:
            return f"{prefix}:{value}"
    return ""


def _counter_label(key):
    """The counter's name for the panel: the file name, or 'shared'."""
    return key.split(":", 1)[1] if key else "shared"


def _counter(state, key):
    """(the dict that holds index / furthest / guide_frame_for of `key`, inherited). '' = the top level of the file itself.
    A song with no counter yet starts from the old shared one when that was never handed on (inherited = True: a writer
    then marks "adopted"), else from nothing."""
    if not key:
        return state, False
    songs = state.get(SONGS_STATE_KEY)
    if isinstance(songs, dict) and isinstance(songs.get(key), dict):
        counter = songs[key]
        # v0.4.13 (sweep O1): a counter remembers its file (size + date). Another file under the same name (a new video
        # copied over the old one) starts from nothing instead of continuing the old file's position.
        if FILE_FIELD in counter and counter[FILE_FIELD] != _file_fp(key):
            return {}, False
        return counter, False
    if not state.get("adopted") and (_to_int(state.get("index")) > 0 or _to_int(state.get("furthest")) > 0):
        return {k: state[k] for k in _COUNTER_FIELDS if k in state}, True
    return {}, False


FILE_FIELD = "file"          # v0.4.13 (sweep O1): [size, mtime_ns] of the song / video a counter belongs to (None: no file)


def _file_fp(key):
    """v0.4.13 (sweep O1): [size, mtime in ns] of the input file behind a counter key ('audio:<name>' / 'video:<name>'),
    None for the shared counter or a file that cannot be read."""
    if not key or ":" not in key:
        return None
    try:
        st = os.stat(folder_paths.get_annotated_filepath(key.split(":", 1)[1]))
        return [int(st.st_size), int(st.st_mtime_ns)]
    except Exception:
        return None


def _store_counter(state, key, counter, inherited):
    """Put a song's counter back into `state` (the shared one, key '', IS the state: nothing to do)."""
    if not key:
        return
    counter[FILE_FIELD] = _file_fp(key)      # v0.4.13 (sweep O1)
    if not isinstance(state.get(SONGS_STATE_KEY), dict):
        state[SONGS_STATE_KEY] = {}
    state[SONGS_STATE_KEY][key] = counter
    if inherited:
        state["adopted"] = True


def _load_index(key=""):
    try:
        return int(_counter(_load_state(), key)[0].get("index", 0))
    except (TypeError, ValueError):
        return 0


def _save_index(index, key=""):
    with _STATE_LOCK:          # v0.0.9l: read -> change -> write as one step
        state = _load_state()      # keep the other keys (guide_frame_for, the other songs)
        counter, inherited = _counter(state, key)
        counter["index"] = index
        counter["furthest"] = max(_to_int(counter.get("furthest")), int(index))     # v2.6: the "Latest" button
        _store_counter(state, key, counter, inherited)
        _write_state(state)


def _load_furthest(key=""):
    """v2.6: the highest counter value a Run (or a jump away from it) has left behind."""
    counter = _counter(_load_state(), key)[0]
    return max(_to_int(counter.get("furthest")), _to_int(counter.get("index")))


def _jump_to(segment, key=""):
    """v2.6: the NEXT Run makes segment number `segment` (1 = the first, as the panel counts).
    Returns (counter, furthest). The guide frames are kept (they are checked against the counter when used)."""
    segment = int(segment)
    if segment < 1:
        raise ValueError("segment numbers start at 1")
    with _STATE_LOCK:          # v0.0.9l
        state = _load_state()
        counter, inherited = _counter(state, key)
        counter["furthest"] = max(_to_int(counter.get("furthest")), _to_int(counter.get("index")))
        counter["index"] = segment - 1
        _store_counter(state, key, counter, inherited)
        _write_state(state)
    return counter["index"], counter["furthest"]


def _handle_jump(body):
    """The /jump route without the web layer: body = {"segment": N [, "total": T]} or {"latest": true}, plus (v0.1.8)
    "params" = the node's widget values, which pick the song's counter. Returns the JSON answer."""
    body = body if isinstance(body, dict) else {}
    key = _counter_key(body.get("params"))
    try:
        if body.get("latest"):
            target = _load_furthest(key) + 1
        else:
            target = int(body.get("segment"))
            total = body.get("total")
            if total not in (None, "") and target > int(total):
                return {"ok": False, "error": f"there are only {int(total)} segments"}
        if target < 1:
            return {"ok": False, "error": "segment numbers start at 1"}
    except (TypeError, ValueError):
        return {"ok": False, "error": "the segment must be a whole number (1 or more)"}
    index, furthest = _jump_to(target, key)
    log.info("segment counter of %s set: the next Run makes segment %d", _counter_label(key), index + 1)
    return {"ok": True, "index": index, "segment": index + 1, "furthest": furthest}


def _reset_state(key=""):
    """v2.5: the Reset button. Segment counter back to 0 (and the saved guide frames forgotten).
    v0.1.8: only the counter of `key` (the song on the node); the other songs keep theirs."""
    with _STATE_LOCK:
        state = _load_state()
        if key:
            _store_counter(state, key, {"index": 0}, False)      # (an entry of its own: it never inherits the old counter)
        else:
            for field in _COUNTER_FIELDS:
                state.pop(field, None)
            state["index"] = 0
        _write_state(state)


def _last_frame_file(key=""):
    """v0.1.8: the Guide's saved last frame, one file per counter (the shared one keeps the old name)."""
    if not key:
        return LAST_FRAME_FILE
    return os.path.join(os.path.dirname(LAST_FRAME_FILE),
                        "mtv_last_frame_%s.png" % hashlib.sha1(key.encode("utf-8")).hexdigest()[:12])


def _reset_on_new_version(current=None):
    """v0.4.9: an update / reinstall starts the segment counters from scratch. The counters live outside the pack, so a reinstall
    used to keep the old video's position and the next Run asked for frames past the end of the new one. The file records the
    version that wrote it; another version (or none, from an older pack) = counters, furthest points and saved last frames
    dropped, the new version recorded. Returns True when it reset."""
    from .settings import VERSION
    current = current or VERSION
    with _STATE_LOCK:
        state = _load_state()
        if state.get("version") == current:
            return False
        # v0.4.13 (sweep O1): counters that know their file (written by 0.4.13 or later) are KEPT across an update: a file
        # replaced under the same name is caught when the counter is read (_counter). Only counters from older versions,
        # which cannot tell, are dropped as in 0.4.9.
        songs = state.get(SONGS_STATE_KEY) if isinstance(state.get(SONGS_STATE_KEY), dict) else {}
        old_counters = [c for c in songs.values() if isinstance(c, dict) and FILE_FIELD not in c]      # (the shared counter has no file: kept)
        if not old_counters:
            state["version"] = current
            _write_state(state)
            log.info("new version %s: segment counters kept (each one checks its own file)", current)
            return False
        for name in os.listdir(DATA_DIR) if os.path.isdir(DATA_DIR) else ():
            if name.startswith("mtv_last_frame") and name.endswith(".png"):
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(DATA_DIR, name))
        _write_state({"index": 0, "version": current})
    log.info("new version %s: segment counters start again at segment 1", current)
    return True


try:
    _reset_on_new_version()
except Exception as _e:         # never stop the pack from loading over this
    log.warning("could not reset the segment counters: %s", _e)


def _last_frame_of(images):
    """The last frame of a decoded video as a small CPU tensor [1,H,W,3] (so the video itself can be freed)."""
    return images[-1].detach().float().cpu().clamp(0, 1)[None].clone()


def _save_last_frame(frame, segment, key=""):
    """Keep the last frame of this run (it was segment number `segment`) for the Guide of the next run.
    v0.1.8: per counter (the song's own file and marker)."""
    arr = frame[0].numpy()
    path = _last_frame_file(key)
    tmp = path + ".tmp"
    try:      # v0.4.12 (sweep B7): written to a .tmp and swapped in, so a kill mid-write never leaves a truncated PNG behind
        Image.fromarray((arr * 255.0 + 0.5).astype(np.uint8)).save(tmp, format="PNG")
        _replace_retry(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise
    with _STATE_LOCK:          # v0.0.9l (the picture above is saved OUTSIDE the lock: only the file update is locked)
        state = _load_state()
        counter, inherited = _counter(state, key)
        counter["guide_frame_for"] = int(segment)
        _store_counter(state, key, counter, inherited)
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
                if full and key == "file":      # v0.0.5: the user's own Save Video adds its own number to the clip name
                    near = _clip_saved_near(full)
                    if near:
                        found = near
                        break
    return found


def _clip_saved_near(planned):
    """v0.0.5: the manifest holds the PLANNED clip name (<tag>_00001_.mp4, see _plan_clip_name). The Save Video node that
    the user linked decides the real file name, usually the same stem with its own number. Only a planned name of exactly
    that shape is looked up: the newest video file in the same folder that starts with '<tag>_' is returned, or None."""
    folder, name = os.path.split(planned)
    m = re.match(r"^(.+)_\d{5}_\.[^./\\]+$", name)
    if not m or not os.path.isdir(folder):
        return None
    stem = m.group(1) + "_"
    best = None
    try:
        for f in os.listdir(folder):
            if f.startswith(stem) and f.lower().endswith(VIDEO_EXTS):
                path = os.path.join(folder, f)
                if best is None or os.path.getmtime(path) > os.path.getmtime(best):
                    best = path
    except OSError:
        return None
    return best


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


def _load_last_frame(index, song=None, key=""):
    """(image [1,H,W,3] or None, reason). Only valid when it comes from the segment right before `index`.
    v2.6: when the saved frame is from another segment (after a jump / a redo), and `song` is given, the frame
    is read back from the clip that segment saved (found through the manifest). reason then names the clip.
    v0.1.8: `key` = whose counter (and saved frame file)."""
    if index <= 0:
        return None, "first segment, nothing to continue from"
    path = _last_frame_file(key)
    if _counter(_load_state(), key)[0].get("guide_frame_for") == index - 1 and os.path.exists(path):
        try:      # v0.4.12 (sweep B7): an unreadable saved frame falls through to the read-back below instead of failing the Run
            with Image.open(path) as opened:      # v0.0.9q: close the file now (an open handle can block the next overwrite on Windows)
                img = opened.convert("RGB")
            arr = np.array(img).astype(np.float32) / 255.0
            return torch.from_numpy(arr)[None,], ""
        except Exception as e:
            log.warning("The saved last frame %s could not be read (%s): trying the previous clip instead", path, e)
    if song:      # v0.4.12 (sweep B6): no project name (pictures only) = no read-back: every such project shares one tag and folder
        try:
            clip = _clip_from_manifest(song, index - 1)
            arr = _clip_last_frame_array(clip) if clip else None
            if arr is not None:
                return (torch.from_numpy(arr.astype(np.float32) / 255.0)[None,],
                        f"read back from the saved clip {os.path.basename(clip)}")
        except Exception as e:
            log.warning("Could not read the last frame back from segment %d: %s", index - 1, e)
    return None, f"no saved last frame from segment {index - 1}"
