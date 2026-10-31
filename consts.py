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


def _truthy(value, default=False):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)
