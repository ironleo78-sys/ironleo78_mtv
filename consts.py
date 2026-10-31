"""Constants shared by mtv.py and the modules split out of it in v0.3.17."""

NONE_CHOICE = "None"       # empty selection for every file slot
RESIZE_METHOD = "lanczos"  # images: fixed
SCENE_TAG = "A"
MANIFEST_NO_SONG = "mtv_manifest.csv"
MANIFEST_FIELDS = ["timestamp", "song", "segment", "scene",
                   "start_s", "end_s", "duration_s", "frames", "width", "height", "seed", "turbo",
                   "pictures", "prompt", "file", "prompt_json", "audio_stem", "latent_file", "conditioning_file"]
VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".m4v", ".gif")
AUDIO_EXTS = (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma")


REPLACE_TRIES = 5            # v0.4.12: os.replace attempts on Windows "Access denied" (a reader / antivirus holds the file)
REPLACE_PAUSE = 0.05         # seconds between two attempts


def _replace_retry(src, dst, tries=REPLACE_TRIES, pause=REPLACE_PAUSE):
    """v0.4.12 (sweep B1): os.replace, retried on PermissionError. On Windows a file that another thread has open (the segment
    panel's read) or that an antivirus is scanning cannot be replaced for a moment (WinError 5); a short retry gets through."""
    import os
    import time
    for attempt in range(max(1, int(tries))):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt + 1 >= tries:
                raise
            time.sleep(pause)


def _truthy(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
