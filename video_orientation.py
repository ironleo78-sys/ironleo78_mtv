"""
IronLeo78 MTV: which way up a decoded video frame must be turned (v0.1.3, review item #5)
------------------------------------------------------------
A phone stores a portrait video as a landscape picture plus a "display rotation" that tells players to turn it.
PyAV decodes the stored picture, so without this a portrait phone clip comes out lying on its side.

Recent FFmpeg (5+, ComfyUI ships FFmpeg 9 with PyAV 19) keeps that rotation in the stream's display matrix and PyAV
exposes it as `frame.rotation` (degrees, counter-clockwise, as FFmpeg's av_display_rotation_get: a portrait phone clip
is usually -90). The old `rotate` metadata tag (clockwise) is no longer filled by FFmpeg; it is still read as a fallback
for an older PyAV without `frame.rotation`. Mirror flips in the matrix (rare) are not applied.

Used by video_reader.py (since 0.1.6 the one reader of the MTV and the 9-Images node). numpy only, no torch.
"""

import numpy as np


def quarter_turns(frame, stream=None):
    """Counter-clockwise quarter turns (the k of np.rot90, 0..3) that stand `frame` upright.
    A rotation that is not a multiple of 90 degrees is rounded to the nearest quarter turn."""
    try:
        rotation = float(getattr(frame, "rotation", None) or 0.0)
    except (TypeError, ValueError):
        rotation = 0.0
    if rotation:
        return int(round(rotation / 90.0)) % 4
    try:      # older PyAV / FFmpeg: the clockwise "rotate" tag of the stream
        tag = float((getattr(stream, "metadata", None) or {}).get("rotate", 0) or 0)
    except (TypeError, ValueError, AttributeError):
        tag = 0.0
    return int(round(-tag / 90.0)) % 4


def upright(arr, turns):
    """arr [H,W,C] turned `turns` quarter turns counter-clockwise (a contiguous copy), or arr itself when turns == 0."""
    return arr if not turns else np.ascontiguousarray(np.rot90(arr, k=turns))
