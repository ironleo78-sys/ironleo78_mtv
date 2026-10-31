"""
IronLeo78 MTV: ONE video reader for the MTV and the 9-Images loader (v0.1.6, review upgrade U5)
------------------------------------------------------------
Both nodes read a window of a video at a fixed frame rate (24 fps). Until 0.1.5 each had its own copy of the decode loop,
with small differences: the 9-Images node measured time from the file's raw timestamps while the MTV measured it from the
start of the file (they disagree when a file does not start at 0, which shifted the "Sync from MTV" window), and it skipped
frames without a timestamp. Now the timing, the seek, the frame repeats, the end of the file and the phone rotation
(video_orientation.py) live here once; each node only says what to do with a decoded frame (`convert`).

How a window is read: output frame k (k = first, first + 1 ...) shows the source frame that is on screen at k / rate seconds
from the start of the file. A source frame stays on screen until the next one's timestamp; the last one lasts one source frame.
A source frame that fills several outputs is converted once. PyAV only (imported when a file is read); no torch.
"""

import logging
import os

from . import video_orientation as _orient

log = logging.getLogger("IronLeo78.MTV.video")
EPS = 1e-6


def require_av():
    try:
        import av
        return av
    except ImportError as e:
        raise RuntimeError(
            "PyAV ('av') is required to decode video/audio. It is normally installed with ComfyUI; "
            "otherwise run:  pip install av"
        ) from e


def open_media(path):
    av = require_av()
    try:
        return av.open(path)
    except Exception as e:
        raise RuntimeError(f"Could not open '{os.path.basename(path)}': {e}") from e


def container_t0(container):
    """The file's start time in seconds (0 when it has none): every time below is measured from it."""
    st = container.start_time  # microseconds, or None
    return (st / 1_000_000.0) if st else 0.0


def seek(container, stream, t_abs):
    """Seek back to the keyframe at/before t_abs (seconds). Silently stays at the start on failure."""
    try:
        container.seek(max(0, int(t_abs / float(stream.time_base))),
                       stream=stream, backward=True, any_frame=False)
    except Exception as e:      # v0.0.9r
        log.debug("seek to %.2fs failed (%s): decoding from the start", t_abs, e)


def read_frames(path, convert, rate=None, first=0, count=1, every=1, want=None):
    """Output frames first .. first + count - 1 (first may be fractional: the 9-Images node starts at Start_From x 24) at
    `rate` fps (None = the file's own rate). Only every `every`-th of them (counting from first) is kept.
    convert(frame, turns) -> the kept item; `turns` = quarter turns counter-clockwise that stand the picture upright.
    v0.3.17: `want` = the set of kept-frame numbers (0 .. kept - 1) to convert; every other kept frame is a None placeholder in the list
    (never converted: no resize, no float copy), so a caller that needs only some of the frames pays for those alone.
    Returns (items, info); info = rate, src_fps, duration, quarter_turns, t0. No item at all = the window is past the end."""
    container = open_media(path)
    try:
        if not container.streams.video:
            raise RuntimeError(f"'{os.path.basename(path)}' has no video stream.")
        stream = container.streams.video[0]
        try:
            stream.thread_type = "AUTO"
        except Exception:      # intentionally silent: a speed hint only
            pass

        tb = float(stream.time_base)
        t0 = container_t0(container)
        src_fps = float(stream.average_rate or stream.guessed_rate or 24)
        rate = float(rate) if rate and rate > 0 else src_fps
        if container.duration:
            duration = container.duration / 1_000_000.0
        elif stream.duration:
            duration = float(stream.duration * tb)
        else:
            duration = 0.0

        every = max(1, int(every))
        turns = []
        out = []
        i = 0                      # outputs done (0 .. count)
        prev = None                # the source frame on screen
        prev_item = None           # what convert() made of it (made once)
        last_t = None

        def keep(frame):
            nonlocal prev_item
            if i % every:
                return
            if not turns:          # read once, from the first frame used
                turns.append(_orient.quarter_turns(frame, stream))
            if want is not None and len(out) not in want:
                out.append(None)
                return
            if prev_item is None:
                prev_item = convert(frame, turns[0])
            out.append(prev_item)

        if first > 0:
            seek(container, stream, t0 + first / rate)

        for frame in container.decode(stream):
            if frame.pts is not None:
                t = float(frame.pts * tb) - t0
            else:
                t = (last_t + 1.0 / src_fps) if last_t is not None else 0.0
            last_t = t
            if prev is None:
                prev = frame
                continue
            # prev stays on screen until this frame's timestamp
            while i < count and (first + i) / rate < t - EPS:
                keep(prev)
                i += 1
            prev, prev_item = frame, None
            if i >= count:
                break

        # end of the file: the last frame lasts one source frame
        if prev is not None and i < count:
            end_t = (last_t if last_t is not None else 0.0) + 1.0 / src_fps
            while i < count and (first + i) / rate < end_t - EPS:
                keep(prev)
                i += 1

        info = {"rate": rate, "src_fps": src_fps, "duration": duration,
                "quarter_turns": turns[0] if turns else 0, "t0": t0}
        return out, info
    finally:
        container.close()
