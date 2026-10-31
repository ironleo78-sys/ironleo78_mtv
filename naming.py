"""Song / project / clip names, the manifest CSV and the .json sidecar. Moved out of mtv.py in v0.3.17."""

import csv
import json
import os
import re
import folder_paths
from .consts import MANIFEST_FIELDS, MANIFEST_NO_SONG, NONE_CHOICE, SCENE_TAG


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


def _project_name(kw, media):
    """v0.0.9: the name of the output SUBFOLDER (clips' sidecars, latents, conditioning, manifest): the song (Custom Audio File)
    when there is one, else the name of the video file (Use Video ON; what media["filename"] holds), else ''. (Pictures come in through
    inputs only and have no file name, so Use Video OFF + no custom audio gives ''.)"""
    return _song_name(kw) or _safe_name((media or {}).get("filename", ""))


def _clip_prefix(kw, media):
    """(SaveVideo filename_prefix, tag) for the clip of this Run.
    <Song>/<Song>_seg004_A   (ComfyUI adds its own _00001_ counter after it).
    No custom audio (v0.0.9): <video name>/<video name>_seg004_A, a subfolder just like the song's
    (nothing at all to name it after, e.g. Use Video OFF: video/ComfyUI_seg004_A)."""
    base = _project_name(kw, media) or "ComfyUI"
    folder = _project_name(kw, media) or "video"
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
