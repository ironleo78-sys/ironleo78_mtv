"""v0.1.1: the MTV crops + shrinks every video frame as soon as it is decoded (review item #2). This test encodes small REAL
videos with PyAV and checks that _load_video gives exactly the frames the old way gave (whole segment decoded at full size,
made float32, then cropped and resized in one batch), with the antialias of v0.1.2 (review item #3) as the only difference. Needs torch, numpy, Pillow and PyAV (any ComfyUI Python has them):
    <ComfyUI python> tests/test_video_decode.py
Skips itself when torch or PyAV is missing."""
import importlib
import math
import os
import shutil
import sys
import tempfile
import types
from unittest.mock import MagicMock

try:
    import torch
    import torch.nn.functional as F
    import av
except Exception:
    print("SKIPPED: torch / PyAV are not installed in this Python (run it with ComfyUI's Python).")
    sys.exit(0)
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
TMP = tempfile.mkdtemp()

for name in ("comfy", "comfy.sd", "comfy.utils", "comfy.model_management", "nodes", "server"):
    sys.modules[name] = MagicMock()
fp = types.ModuleType("folder_paths")
fp.get_input_directory = lambda: TMP
fp.get_output_directory = lambda: TMP
fp.get_filename_list = lambda k: []
fp.get_annotated_filepath = lambda n: os.path.join(TMP, n)
fp.exists_annotated_filepath = lambda n: os.path.exists(os.path.join(TMP, n))
sys.modules["folder_paths"] = fp
sys.modules["comfy_extras"] = types.ModuleType("comfy_extras")
sys.modules["comfy_extras.nodes_minimax_h3"] = types.ModuleType("comfy_extras.nodes_minimax_h3")
sys.path.insert(0, os.path.dirname(PACK))
mtv = importlib.import_module(os.path.basename(PACK) + ".mtv")

ok = 0


def check(cond, msg):
    global ok
    assert cond, "FAIL: " + msg
    ok += 1
    print("  ok -", msg)


def make(name, w, h, seconds, fps):
    """A real encoded video with moving detail (gradients + a checkerboard that shifts every frame)."""
    with av.open(os.path.join(TMP, name), "w") as c:
        s = c.add_stream("mpeg4", rate=fps)
        s.width, s.height, s.pix_fmt = w, h, "yuv420p"
        yy, xx = np.mgrid[0:h, 0:w]
        for i in range(int(seconds * fps)):
            img = np.stack([(xx * 255 // w + i * 7) % 256, (yy * 255 // h) % 256,
                            (((xx + 3 * i) // 24 + yy // 24) % 2) * 255], -1).astype(np.uint8)
            for p in s.encode(av.VideoFrame.from_ndarray(img, format="rgb24")):
                c.mux(p)
        for p in s.encode():
            c.mux(p)
    return name


def old_way(path, frames, mp, index, antialias=True):
    """What _load_video did until 0.1.0, step by step: full-size uint8 stack -> float32 -> crop -> batch bicubic.
    antialias=True = the same with the v0.1.2 antialias; False = exactly the pre-0.1.2 pixels."""
    arr, _ = mtv._decode_video(path, mtv.DEFAULT_FPS, index * frames, frames)
    if arr is None:
        return None
    images = torch.from_numpy(arr).float().div_(255.0)
    oh, ow = int(images.shape[1]), int(images.shape[2])
    r = ow / oh
    tw = math.sqrt(mp * 1_000_000 * r)
    th = tw / r
    target_width = max(32, int(round(tw / 32.0)) * 32)
    target_height = max(32, int(round(th / 32.0)) * 32)
    final_r = target_width / target_height
    if ow / oh > final_r:
        crop_h, crop_w = oh, int(round(oh * final_r))
    else:
        crop_w, crop_h = ow, int(round(ow / final_r))
    crop_w, crop_h = max(1, min(crop_w, ow)), max(1, min(crop_h, oh))
    sx, sy = (ow - crop_w) // 2, (oh - crop_h) // 2
    images = images[:, sy:sy + crop_h, sx:sx + crop_w, :]
    if images.shape[2] != target_width or images.shape[1] != target_height:
        images = images.permute(0, 3, 1, 2)
        images = F.interpolate(images, size=(target_height, target_width), mode="bicubic", align_corners=False,
                               antialias=antialias and (crop_w > target_width or crop_h > target_height))
        images = torch.clamp(images, 0.0, 1.0).permute(0, 2, 3, 1)
    return images


node = mtv.IronLeo78_MTV()
cases = [
    ("1080p, segment 1", make("hd.mp4", 1920, 1080, 2.5, 30), 1.0, 0.2, 0),
    ("1080p, segment 2 (seek)", "hd.mp4", 1.0, 0.2, 1),
    ("portrait phone size", make("portrait.mp4", 720, 1280, 1.5, 25), 1.0, 0.3, 0),
    ("small video made bigger", make("small.mp4", 320, 180, 1.5, 24), 1.0, 0.5, 0),
    ("already the target size (no resize)", make("exact.mp4", 608, 352, 1.5, 24), 1.0, 0.2, 0),
    ("shorter than the segment (last frames repeated)", make("short.mp4", 640, 360, 0.5, 24), 1.0, 0.2, 0),
]
try:
    for label, name, seconds, mp, index in cases:
        frames = mtv._minimax_frames(seconds)
        kw = {"Video File": name, "Next Segment On Run": True}
        new, audio, w, h, filename, status = node._load_video(kw, frames, seconds, mp, index)
        ref = old_way(os.path.join(TMP, name), frames, mp, index)
        check(tuple(new.shape) == tuple(ref.shape) and (w, h) == (int(ref.shape[2]), int(ref.shape[1])),
              "%s: same size %s" % (label, tuple(new.shape)))
        diff = float((new - ref).abs().max())
        check(diff < 1e-5, "%s: the same pixels as the full-size way (largest difference %.2e)" % (label, diff))
        before = old_way(os.path.join(TMP, name), frames, mp, index, antialias=False)
        shrunk = name in ("hd.mp4", "portrait.mp4", "short.mp4")      # small.mp4 is enlarged, exact.mp4 only cropped
        moved = float((new - before).abs().mean())
        if shrunk:
            check(moved > 1e-4, "%s: shrunk, so the antialias changes the pixels (mean change %.4f)" % (label, moved))
        else:
            check(moved < 1e-6, "%s: not shrunk, so the pixels are exactly those of v0.1.1 (mean change %.2e)" % (label, moved))
        check(new.dtype == torch.float32 and float(new.min()) >= 0.0 and float(new.max()) <= 1.0, "%s: float32 in 0..1" % label)
        check(w % 32 == 0 and h % 32 == 0 and filename == os.path.splitext(name)[0], "%s: %dx%d, multiples of 32" % (label, w, h))
    # past the end: still a quiet stop (index > 0) or an error (index 0), as before
    try:
        node._load_video({"Video File": "short.mp4"}, 22, 1.0, 0.2, 5)
        check(False, "past the end must stop")
    except mtv._EndOfSegments:
        check(True, "a segment past the end of the video is still a quiet stop")
    # v0.1.2: what the antialias is for. One-pixel stripes (fine detail, e.g. hair, fabric, a grille) shrunk 1920 -> 608 px:
    # without it, the result keeps hard stripes that jump around from frame to frame (shimmer); with it, they average to grey
    stripes = np.zeros((1080, 1920, 3), np.uint8)
    stripes[:, ::2] = 255
    plan = mtv._video_frame_plan(1920, 1080, 0.2)
    smooth = mtv._shape_video_frame(stripes, plan)
    shifted = mtv._shape_video_frame(np.ascontiguousarray(np.roll(stripes, 1, axis=1)), plan)
    sx, sy, cw, ch = plan[2]
    raw = torch.from_numpy(np.ascontiguousarray(stripes[sy:sy + ch, sx:sx + cw])).float().div_(255.0).permute(2, 0, 1)[None]
    hard = F.interpolate(raw, size=(plan[1], plan[0]), mode="bicubic", align_corners=False).clamp(0, 1)[0].permute(1, 2, 0)
    check(float(smooth.std()) < 0.05 and float(hard.std()) > 0.2,
          "one-pixel stripes shrunk: even grey with antialias (spread %.3f), harsh stripes without it (spread %.3f)" % (float(smooth.std()), float(hard.std())))
    check(float((smooth - shifted).abs().mean()) < 0.02,
          "the same stripes moved by one pixel look the same once shrunk: no shimmer between frames (change %.4f)" % float((smooth - shifted).abs().mean()))
    # v0.1.3 (review #5): phone videos. A phone stores a portrait clip on its side + a display rotation (FFmpeg's display
    # matrix; a portrait phone clip usually reads -90). Each test clip below is an UPRIGHT portrait picture (red band at the
    # top, blue band at the bottom, a green mark top-left) stored turned the other way, so only a correct turn shows it upright.
    nine = importlib.import_module(os.path.basename(PACK) + ".nine_images")
    orient = importlib.import_module(os.path.basename(PACK) + ".video_orientation")
    upright_pic = np.full((640, 360, 3), 128, np.uint8)
    upright_pic[:80] = (255, 0, 0)
    upright_pic[-80:] = (0, 0, 255)
    upright_pic[:40, :40] = (0, 255, 0)

    def phone(name, rotation):
        turns = int(round(rotation / 90.0)) % 4
        stored = np.ascontiguousarray(np.rot90(upright_pic, k=-turns))
        with av.open(os.path.join(TMP, name), "w") as c:
            s = c.add_stream("mpeg4", rate=24)
            s.height, s.width = stored.shape[:2]
            s.pix_fmt = "yuv420p"
            s.set_display_rotation(rotation)
            for _ in range(30):
                for p in s.encode(av.VideoFrame.from_ndarray(stored, format="rgb24")):
                    c.mux(p)
            for p in s.encode():
                c.mux(p)
        return name

    def looks_upright(img):      # img: [H,W,3] float 0..1
        h, w = int(img.shape[0]), int(img.shape[1])
        top, bottom = img[: h // 10].mean(dim=(0, 1)), img[-(h // 10):].mean(dim=(0, 1))
        corner = img[: h // 20, : w // 20].mean(dim=(0, 1))
        return (h > w and top[0] > 0.6 and top[2] < 0.3 and bottom[2] > 0.6 and bottom[0] < 0.3
                and corner[1] > 0.5 and corner[0] < 0.4)

    if not hasattr(av.video.stream.VideoStream, "set_display_rotation"):
        print("  (this PyAV cannot write a display rotation: the phone-video checks are skipped)")
    else:
        for rotation, label in ((-90, "usual portrait phone clip (-90)"), (90, "turned the other way (90)"),
                                (180, "upside down (180)"), (0, "no rotation")):
            name = phone("phone%d.mp4" % (rotation % 360), rotation)
            with av.open(os.path.join(TMP, name)) as c:
                stored = "%dx%d" % (c.streams.video[0].codec_context.width, c.streams.video[0].codec_context.height)
            imgs, _, w, h, _, status = node._load_video({"Video File": name, "Next Segment On Run": True}, 22, 1.0, 0.2, 0)
            check(looks_upright(imgs[0]) and looks_upright(imgs[-1]),
                  "MTV, %s: the clip comes out upright %dx%d (stored %s)" % (label, w, h, stored))
            turned = rotation % 360 != 0
            check(("turned upright" in status) == turned, "MTV, %s: the status %s the turn" % (label, "names" if turned else "does not mention"))
            frames9 = nine._decode_video(os.path.join(TMP, name), 0.0, 1.0, "2", "672x384")      # (full path; the thinned path is tested below)
            check(tuple(frames9.shape[1:3]) == (672, 384) and looks_upright(frames9[0]),
                  "9-Images, %s: upright, and the portrait preset 384x672 is chosen (%s)" % (label, tuple(frames9.shape)))

    class _F:
        def __init__(self, rotation):
            self.rotation = rotation

    class _S:
        def __init__(self, tag):
            self.metadata = {"rotate": tag} if tag is not None else {}

    check([orient.quarter_turns(_F(r)) for r in (0, 90, -90, 180, -180, 270, 89.6)] == [0, 1, 3, 2, 2, 3, 1],
          "quarter turns from frame.rotation (counter-clockwise degrees): 0, 90, -90, 180, -180, 270, 89.6")
    check([orient.quarter_turns(object(), _S(t)) for t in ("90", "270", "180", None, "bad")] == [3, 1, 2, 0, 0],
          "an older PyAV: the clockwise 'rotate' tag is the fallback (90 -> 3 counter-clockwise quarter turns)")
    check(orient.quarter_turns(_F(0), _S("90")) == 3 and orient.quarter_turns(_F(-90), _S("90")) == 3,
          "frame.rotation wins when it has a turn; a zero rotation still lets the old tag speak")
    check(orient.upright(upright_pic, 0) is upright_pic and orient.upright(upright_pic, 1).shape == (360, 640, 3),
          "upright(): no turn = the same array; one turn swaps width and height")
    # v0.1.6 (U5): ONE reader for both nodes (video_reader.read_frames). Which SOURCE frame lands on each output frame, read
    # through the frames' own timestamps (pts) so the answer does not depend on any resize
    reader = importlib.import_module(os.path.basename(PACK) + ".video_reader")

    def numbered(name, fps, seconds, pts_offset=0):
        with av.open(os.path.join(TMP, name), "w") as c:
            s = c.add_stream("mpeg4", rate=fps)
            s.width, s.height, s.pix_fmt = 64, 48, "yuv420p"
            for i in range(int(seconds * fps)):
                f = av.VideoFrame.from_ndarray(np.full((48, 64, 3), i % 256, np.uint8), format="rgb24")
                f.pts = i + pts_offset
                for p in s.encode(f):
                    c.mux(p)
            for p in s.encode():
                c.mux(p)
        return os.path.join(TMP, name)

    pts = lambda frame, turns: int(round(float(frame.time) * 24))      # the source frame number (24 fps files)
    plain = numbered("n24.mp4", 24, 3)
    late = numbered("n24_late.mp4", 24, 3, pts_offset=12)       # the file's first frame is at 0.5 s
    got, info = reader.read_frames(plain, pts, rate=24, first=24, count=3)
    check(got == [24, 25, 26] and info["t0"] == 0.0, "output frames 24-26 at 24 fps = source frames 24-26 (from 1.0 s, after a seek): %s" % got)
    got, info = reader.read_frames(late, pts, rate=24, first=24, count=3)
    check(got == [36, 37, 38] and abs(info["t0"] - 0.5) < 1e-9,
          "a file that starts at 0.5 s: time is counted from ITS start, so 1.0 s in = its 25th frame (pts 36): %s" % got)
    got, _ = reader.read_frames(plain, pts, rate=24, first=24, count=6, every=2)
    check(got == [24, 26, 28], "every=2 keeps one output frame in two: %s" % got)
    got, _ = reader.read_frames(plain, pts, rate=24, first=1.3 * 24, count=2)
    check(got == [31, 32], "a fractional start (Start_From 1.3 s = output frame 31.2) gives the frames on screen then: %s" % got)
    slow = numbered("n12.mp4", 12, 2)
    pts12 = lambda frame, turns: int(round(float(frame.time) * 12))
    got, _ = reader.read_frames(slow, pts12, rate=24, first=0, count=6)
    check(got == [0, 0, 1, 1, 2, 2], "a 12 fps file read at 24 fps: each source frame fills two output frames: %s" % got)
    seen = []
    reader.read_frames(slow, lambda f, t: seen.append(pts12(f, t)) or 0, rate=24, first=0, count=6)
    check(seen == [0, 1, 2], "... and each source frame is converted only once (the repeat reuses it)")
    got, _ = reader.read_frames(plain, pts, rate=24, first=70, count=10)
    check(got == [70, 71], "the window runs past the end: it stops at the last frame (3 s = 72 frames): %s" % got)
    got, _ = reader.read_frames(plain, pts, rate=24, first=200, count=5)
    check(got == [], "a window entirely past the end: nothing")
    check(mtv._seek is reader.seek and mtv._open_media is reader.open_media, "the MTV's audio side uses the same open / seek as the reader")
    # the 9-Images node and the MTV now agree on that late-starting file (the 9-Images node used to be 0.5 s off: it counted
    # time from the raw timestamps, so its "Sync from MTV" window showed other frames than the MTV's segment)
    nine_pts = []
    real_convert = reader.read_frames

    def spy(path, convert, **kw):
        return real_convert(path, lambda f, t: (nine_pts.append(pts(f, t)), convert(f, t))[1], **kw)

    reader.read_frames = spy
    try:
        nine._decode_video(late, 1.0, 0.25, "1", "512x288")
    finally:
        reader.read_frames = real_convert
    check(nine_pts == [36, 37, 38, 39, 40, 41], "9-Images, Start_From 1.0 s on the late file: the same frames as the MTV's timeline (pts 36-41): %s" % nine_pts)
    got, _ = reader.read_frames(plain, pts, rate=24, first=0, count=10, want={1, 4, 9})
    check(got == [None, 1, None, None, 4, None, None, None, None, 9], "v0.3.17 want={1,4,9}: only those kept frames are converted, the rest are None: %s" % got)
    seen = []
    reader.read_frames(plain, lambda f, t: seen.append(pts(f, t)) or 0, rate=24, first=0, count=10, every=2, want={0, 3})
    check(seen == [0, 6], "... counted in kept frames (every=2): kept 0 and 3 = source frames 0 and 6, nothing else converted: %s" % seen)
    real_max = nine.MAX_LLM_FRAMES
    nine.MAX_LLM_FRAMES = 10
    try:
        full = nine._decode_video(plain, 0.0, 3.0, "1", "512x288")
        thin, n = nine._decode_video_for_llm(plain, 0.0, 3.0, "1", "512x288")
        pick = nine._llm_frame_indices(72)
        check(n == 72 and thin.shape[0] == 10 and bool((thin == full[pick]).all()), "v0.3.17: the thinned decode = the full decode, then the picks (10 of 72)")
        thin2, n2 = nine._decode_video_for_llm(plain, 0.0, 5.0, "1", "512x288")      # the file ends at 3 s: 72 frames, not 120
        check(n2 == 72 and bool((thin2 == full[pick]).all()), "... and a window longer than the file re-picks for the real 72 frames (n=%d)" % n2)
    finally:
        nine.MAX_LLM_FRAMES = real_max    # the plan maths alone (no video): landscape and portrait
    check(mtv._video_frame_plan(1920, 1080, 0.2) == (608, 320, (0, 34, 1920, 1011)), "plan 1920x1080 @ 0.2 MP: %s" % (mtv._video_frame_plan(1920, 1080, 0.2),))
    tw, th, box = mtv._video_frame_plan(1080, 1920, 0.2)
    check(th > tw and box[2] <= 1080 and box[3] <= 1920, "plan for a portrait frame: %dx%d" % (tw, th))
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print("\nALL %d VIDEO-DECODE CHECKS PASSED" % ok)
