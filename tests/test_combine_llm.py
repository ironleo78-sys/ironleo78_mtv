"""Tests for Output_To_LLM (v0.0.2c). Needs torch (any ComfyUI Python has it).
Run:  python tests/test_combine_llm.py      (skips itself with a message when torch is missing)
No ComfyUI needed: folder_paths is stubbed."""
import importlib.util
import os
import sys
import types
import unittest

try:
    import torch
except Exception:                                  # pragma: no cover
    print("SKIPPED: torch is not installed in this Python (run it with ComfyUI's Python).")
    sys.exit(0)

from unittest.mock import MagicMock

sys.modules.setdefault("folder_paths", types.ModuleType("folder_paths"))
# v0.1.3: nine_images.py imports the pack's video_orientation.py, so it is loaded THROUGH the pack (as ComfyUI does); the pack's
# __init__ also imports the MTV, whose ComfyUI modules are stand-ins here (torch / numpy / Pillow stay real)
for _name in ("comfy", "comfy.sd", "comfy.utils", "comfy.model_management", "nodes", "server"):
    sys.modules.setdefault(_name, MagicMock())
sys.modules.setdefault("comfy_extras", types.ModuleType("comfy_extras"))
sys.modules.setdefault("comfy_extras.nodes_minimax_h3", types.ModuleType("comfy_extras.nodes_minimax_h3"))
_fp = sys.modules["folder_paths"]
for _attr, _fn in (("get_input_directory", lambda: "."), ("get_output_directory", lambda: "."), ("get_filename_list", lambda k: [])):
    if not hasattr(_fp, _attr):
        setattr(_fp, _attr, _fn)
HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.dirname(HERE)
sys.path.insert(0, os.path.dirname(PACK))
pack = importlib.import_module(os.path.basename(PACK) + ".nine_images")      # v0.1.0: inside the MTV pack


def img(h, w, v):
    return torch.full((1, h, w, 3), float(v))


class CombineTests(unittest.TestCase):
    def test_order_and_size_follow_the_video(self):
        pics = [img(60, 80, 0.2), img(100, 50, 0.4)]          # landscape 4:3, portrait
        video = torch.stack([img(36, 64, 0.9)[0]] * 3)         # 3 frames, 64x36
        out = pack._combine_for_llm(pics, video, "512x288")
        self.assertEqual(tuple(out.shape), (5, 36, 64, 3))
        self.assertTrue(torch.allclose(out[0], torch.full((36, 64, 3), 0.2), atol=1e-3))
        self.assertTrue(torch.allclose(out[1], torch.full((36, 64, 3), 0.4), atol=1e-3))
        self.assertTrue(torch.equal(out[2:], video))           # video frames untouched, right after the pictures

    def test_no_picture_means_video_only_no_none_placeholder(self):
        video = torch.stack([img(36, 64, 0.9)[0]] * 2)
        out = pack._combine_for_llm([], video, "512x288")
        self.assertTrue(torch.equal(out, video))

    def test_no_video_uses_the_preset_size_and_no_none_placeholder(self):
        out = pack._combine_for_llm([img(60, 80, 0.5)], None, "512x288")
        self.assertEqual(tuple(out.shape), (1, 288, 512, 3))
        self.assertTrue(torch.allclose(out, torch.full_like(out, 0.5), atol=1e-3))

    def test_nothing_at_all_gives_one_none_picture_at_preset_size(self):
        out = pack._combine_for_llm([], None, "672x384")
        self.assertEqual(tuple(out.shape), (1, 384, 672, 3))

    def test_portrait_video_gives_portrait_frame(self):
        video = torch.stack([img(64, 36, 0.9)[0]] * 2)         # 36 wide, 64 tall
        out = pack._combine_for_llm([img(60, 80, 0.2)], video, "512x288")
        self.assertEqual(tuple(out.shape), (3, 64, 36, 3))

    def test_tall_picture_crop_is_top_biased(self):
        rows = torch.linspace(0, 1, 200).view(1, 200, 1, 1).expand(1, 200, 100, 3).contiguous()
        out = pack._combine_for_llm([rows], None, "512x288")   # -> 512x288 frame
        first_row = float(out[0, 0, :, 0].mean())
        # centre crop would start near 0.36 of the picture height; top bias (25% of the spare) starts near 0.18
        self.assertLess(first_row, 0.26)
        self.assertGreater(first_row, 0.10)

    def test_wide_picture_crop_is_centred_horizontally(self):
        cols = torch.linspace(0, 1, 400).view(1, 1, 400, 1).expand(1, 100, 400, 3).contiguous()
        out = pack._combine_for_llm([cols], None, "512x288")
        self.assertAlmostEqual(float(out[0, :, :, 0].mean()), 0.5, delta=0.02)

    def test_off_ratio_slots(self):
        singles = [img(288, 512, 0), None, img(300, 400, 0), img(512, 288, 0), img(384, 672, 0)]
        self.assertEqual(pack._off_ratio_slots(singles + [None] * 4, 288, 512), [3, 4])   # 16:9 ok, 7:4 ok (within 6%)


class NoneMarkTests(unittest.TestCase):
    def test_none_pictures_carry_the_mark(self):
        """v0.0.2d: the IronLeo78 MTV skips a picture with this mark (an empty slot is not a reference)."""
        self.assertIs(getattr(pack._none_image(), pack.NONE_MARK), True)
        self.assertIs(getattr(pack._none_image(288, 512), pack.NONE_MARK), True)
        self.assertEqual(pack.NONE_MARK, "ironleo78_none")

    def test_the_cache_itself_is_never_marked_or_shared(self):
        a, b = pack._none_image(), pack._none_image()
        self.assertIsNot(a, b)
        self.assertFalse(any(hasattr(t, pack.NONE_MARK) for t in pack._none_cache.values()))

    def test_real_pictures_are_not_marked(self):
        self.assertFalse(hasattr(img(60, 80, 0.2), pack.NONE_MARK))


class IsChangedTests(unittest.TestCase):
    """v0.0.2e: the files are identified by name + size + mtime, never read."""

    def setUp(self):
        import tempfile
        self.dir = tempfile.mkdtemp()
        self.pic = os.path.join(self.dir, "a.png")
        with open(self.pic, "wb") as f:
            f.write(b"x" * 10)
        fp = sys.modules["folder_paths"]
        self.saved = (getattr(fp, "exists_annotated_filepath", None), getattr(fp, "get_annotated_filepath", None))
        fp.exists_annotated_filepath = lambda n: os.path.exists(os.path.join(self.dir, n))
        fp.get_annotated_filepath = lambda n: os.path.join(self.dir, n)

    def tearDown(self):
        fp = sys.modules["folder_paths"]
        fp.exists_annotated_filepath, fp.get_annotated_filepath = self.saved

    def kw(self, **extra):
        d = {f"image_{i}": "" for i in range(1, 10)}
        d.update(video="", Start_From=0.0, Duration=5.0, Frame_Interval="2", Video_Size="672x384", image_1="a.png")
        d.update(extra)
        return d

    def test_same_file_same_value_and_the_file_is_never_read(self):
        IC = pack.IronLeo78_9ImagesToBatchToLLM.IS_CHANGED
        real_open = open
        opened = []
        import builtins
        builtins.open = lambda *a, **k: opened.append(a[0]) or real_open(*a, **k)
        try:
            a, b = IC(**self.kw()), IC(**self.kw())
        finally:
            builtins.open = real_open
        self.assertEqual(a, b)
        self.assertEqual(opened, [])

    def test_a_file_replaced_under_the_same_name_changes_the_value(self):
        IC = pack.IronLeo78_9ImagesToBatchToLLM.IS_CHANGED
        a = IC(**self.kw())
        with open(self.pic, "wb") as f:
            f.write(b"y" * 20)
        self.assertNotEqual(IC(**self.kw()), a)

    def test_another_slot_or_widget_changes_the_value(self):
        IC = pack.IronLeo78_9ImagesToBatchToLLM.IS_CHANGED
        self.assertNotEqual(IC(**self.kw()), IC(**self.kw(image_1="", image_2="a.png")))
        self.assertNotEqual(IC(**self.kw()), IC(**self.kw(Duration=6.0)))


class ContractTests(unittest.TestCase):
    def test_outputs(self):
        cls = pack.IronLeo78_9ImagesToBatchToLLM
        self.assertEqual(cls.RETURN_NAMES[0], "Output_To_LLM")
        self.assertEqual(cls.RETURN_NAMES[-2:], ("video_frames", "LLM_Frame_Info"))      # ONE text output, LAST (v0.1.17: preset included)
        self.assertEqual(cls.RETURN_TYPES[-1], "STRING")
        self.assertNotIn("Start_From", cls.RETURN_NAMES)
        self.assertNotIn("Duration", cls.RETURN_NAMES)
        self.assertEqual(len(cls.RETURN_NAMES), len(cls.RETURN_TYPES))
        self.assertEqual(len(cls.RETURN_NAMES), 12)


class FrameInfoTests(unittest.TestCase):
    """v0.1.13: the sentence for the LLM is built from Frame_Interval (24 fps / interval)."""
    def test_fps_follows_the_interval(self):
        for iv, fps in (("2", "12"), ("4", "6"), ("8", "3"), ("12", "2")):
            t = pack._frame_info([1], 48, iv)
            self.assertIn(f"{fps} frames per second", t)
            self.assertIn(f"{fps} FPS", t)
            self.assertIn("frame 2 = 00:00.%03d" % round(1000 / int(fps)), t)
            self.assertIn("48 frames of Video 1", t)

    def test_every_frame_has_its_time(self):
        t = pack._frame_info([1], 10, "12")
        self.assertIn("frame 1 = 00:00.000, frame 2 = 00:00.500", t)
        self.assertIn("frame 10 = 00:04.500", t)
        self.assertIn("lasts 00:05.000", t)
        self.assertEqual(pack._stamp(61.5), "01:01.500")

    def test_pictures_are_named_in_order(self):
        t = pack._frame_info([1, 3, 4], 10, "12")
        self.assertTrue(t.startswith("The first 3 images are the reference pictures (<Picture 1>, <Picture 2> (slot 3), <Picture 3> (slot 4), in this order)"))
        self.assertIn("already count only the pictures that are sent", t)               # v0.3.4: slots and labels differ: said once
        self.assertNotIn("already count", pack._frame_info([1, 2], 10, "12"))             # no gap: nothing extra
        self.assertIn("The first 1 image is the reference picture (<Picture 1> (slot 2)", pack._frame_info([2], 10, "12"))

    def test_no_video_and_no_pictures(self):
        self.assertTrue(pack._frame_info([1], None, "12").endswith("and no video."))
        self.assertNotIn("FPS", pack._frame_info([1], None, "12"))
        self.assertTrue(pack._frame_info([], 5, "12").startswith("There are no reference pictures. The images are the 5 frames"))

    def test_widget_order_unchanged(self):
        """Saved workflows store widget VALUES by position: this order must never shift."""
        keys = list(pack.IronLeo78_9ImagesToBatchToLLM.INPUT_TYPES()["required"].keys())
        self.assertEqual(keys, [f"image_{i}" for i in range(1, 10)] +
                         ["video", "Start_From", "Duration", "Frame_Interval", "Video_Size", "Preset"])      # v0.1.15: Preset appended LAST


class PresetTests(unittest.TestCase):
    """v0.1.15: the scenario presets live in presets/*.md (# SYSTEM / # TASK)."""
    def test_parse(self):
        s, t = pack._parse_preset("ignored\n# SYSTEM\nrule 1\n\nrule 2\n# TASK\ndo it\n")
        self.assertEqual((s, t), ("rule 1\n\nrule 2", "do it"))
        self.assertEqual(pack._parse_preset("# TASK\nonly task"), ("", "only task"))
        self.assertEqual(pack._parse_preset("# SYSTEM\r\na\r\n# TASK\r\nb\r\n"), ("a", "b"))
        self.assertEqual(pack._parse_preset("no markers"), ("", ""))

    def test_suggested_prompt(self):
        d = pack._parse_preset_full("# SYSTEM\na\n# TASK\nb:\n# PROMPT\nReplace him.\n")
        self.assertEqual({k: d[k] for k in ("system", "task", "prompt")}, {"system": "a", "task": "b:", "prompt": "Replace him."})
        self.assertEqual((d["i2v_system"], d["i2v_task"], d["i2v_prompt"]), ("", "", ""))
        d2 = pack._parse_preset_full("# SYSTEM\na\n# I2V SYSTEM\nx\n# I2V TASK\ny:\n# I2V PROMPT\nz\n# TASK\nb:\n")
        self.assertEqual((d2["system"], d2["task"], d2["i2v_system"], d2["i2v_task"], d2["i2v_prompt"]), ("a", "b:", "x", "y:", "z"))
        self.assertEqual(pack._parse_preset("# SYSTEM\na\n# TASK\nb:\n# PROMPT\nx\n"), ("a", "b:"))        # the prompt never leaks into the LLM texts
        self.assertEqual(pack._parse_preset_full("# SYSTEM\na")["prompt"], "")

    def test_every_shipped_preset_has_a_working_prompt(self):
        sp = pack.preset_prompts()
        names = pack._preset_names()
        self.assertEqual(sp["None"], "")
        for n in names:
            self.assertTrue(sp[n].strip(), "preset %r has no # PROMPT" % n)
            s, t = pack._read_preset(n)
            self.assertNotIn(sp[n], s + t)
        self.assertEqual(sp[names[0]], "Replace the main character of Video 1.")
        self.assertEqual(sp[names[1]], "Replace the main character and the environment of Video 1.")
        self.assertEqual(sp[names[2]], "Replace the two characters and the environment of Video 1.")

    def test_every_shipped_preset_has_an_i2v_version(self):
        sp = pack.preset_prompts("i2v")
        self.assertEqual(sp["None"], "")
        for n in pack._preset_names():
            s, t = pack._read_preset(n, "i2v")
            self.assertTrue(s and t and sp[n].strip(), "preset %r lacks its i2v text or prompt" % n)
            self.assertIn("IMAGE-TO-VIDEO", s)
            self.assertIn("NO source video", s)
            self.assertNotIn("<Video 1> (timing", s)                          # nothing about a source video to keep
            self.assertIn("TIMELINE", s)
            self.assertIn("[reference generation", s)                           # (a musician preset adds " + audio reuse")
            self.assertIn("N/A", s)                                           # audio is left to the MTV
            self.assertTrue(t.rstrip().endswith(":"))
            self.assertNotEqual((s, t), pack._read_preset(n, "v2v"))
            self.assertNotEqual(sp[n], pack.preset_prompts()[n])
        names = pack._preset_names()
        self.assertIn("<Picture 2> is the REPLACEMENT CHARACTER", pack._read_preset(names[0], "i2v")[0])       # roles shift up one slot
        s3 = pack._read_preset(names[2], "i2v")[0]
        for key in ("<Picture 4>", "GENDER MATCHING", "MATCH BY GENDER", "is the SECONDARY ACTOR"):
            self.assertIn(key, s3)

    def test_all_presets_share_the_same_timeline_rules(self):
        import re
        names = pack._preset_names()
        base_v = re.search(r"8\. Timing \(mandatory\).*?(?=\n9\. )", pack._read_preset(names[0])[0], re.S).group(0)
        base_i = re.search(r"8\. Timeline \(mandatory\).*?(?=\n9\. )", pack._read_preset(names[0], "i2v")[0], re.S).group(0)
        for n in names:
            v = re.search(r"8\. Timing \(mandatory\).*?(?=\n9\. )", pack._read_preset(n)[0], re.S)
            i = re.search(r"8\. Timeline \(mandatory\).*?(?=\n9\. )", pack._read_preset(n, "i2v")[0], re.S)
            self.assertTrue(v and v.group(0) == base_v, "v2v rule 8 differs in %r" % n)
            self.assertTrue(i and i.group(0) == base_i, "i2v rule 8 differs in %r" % n)

    def test_the_new_presets_follow_the_guide(self):
        names = {n.split(" ", 1)[0]: n for n in pack._preset_names()}
        for k in ("4", "5", "6", "11"):                                                   # the video keeps its own audio
            s = pack._read_preset(names[k])[0]
            self.assertIn("[video editing + reference generation + audio reuse]", s)
            self.assertIn("synchronized audio track of <Video 1>", s)
            self.assertIn("`fully_copy`", s)
        self.assertIn("<Picture 1> is the NEW ENVIRONMENT", pack._read_preset(names["4"])[0])
        self.assertIn("<Picture 2> is the NEW ENVIRONMENT", pack._read_preset(names["4"], "i2v")[0])      # i2v: the scene is Picture 1
        self.assertIn("STYLE REFERENCE", pack._read_preset(names["5"])[0])
        self.assertIn("OUTFIT REFERENCE", pack._read_preset(names["6"])[0])
        self.assertIn("`attribute_transfer`", pack._read_preset(names["6"])[0])
        self.assertIn("If it names none, use golden hour", pack._read_preset(names["11"])[0].replace("if it names none, use golden hour", "If it names none, use golden hour"))
        for k in ("7", "8", "9", "10"):                                                  # musicians: the sound of the video is NOT used
            s, t = pack._read_preset(names[k])
            self.assertIn("DRIVEN BY THE CUSTOM AUDIO", s)
            self.assertIn("the sound of <Video 1> is NOT used", s)
            self.assertIn("You cannot hear it", s)
            self.assertIn("Never write lyrics" if k == "7" else "stays", s)
            si = pack._read_preset(names[k], "i2v")[0]
            self.assertIn("<Picture 2> is the", si)
            self.assertIn("`[reference generation + audio reuse]`", si)

    def test_ironleo78_mode(self):
        names = {n.split(" ", 1)[0]: n for n in pack._preset_names()}
        self.assertEqual(names["12"], "12 - IronLeo78 Mode")
        s, t = pack._read_preset(names["12"])
        si, ti = pack._read_preset(names["12"], "i2v")
        for text in (s, si):
            for key in ("six-year-old girl", "mixed heritage", "curly", "48-year-old", "Caucasian", "bald head", "blue eyes",
                        "SINGER and the GUITARIST", "DRUMMER", "FULL MIX", "LIP-SYNCS", "main guitar", "kick, snare, hi-hat", "child-size",
                        "`attribute_transfer`", "`fully_copy`", "You cannot hear it", "never invent words", "TIMELINE" if text is si else "Timing (mandatory)"):
                self.assertIn(key, text, key)
        self.assertIn("[video editing + reference generation + audio reuse]", s)
        self.assertIn("the sound of <Video 1> is NOT used", s)
        self.assertIn("`[reference generation + audio reuse]`", si)
        self.assertIn("NO source video", si)
        self.assertIn("<Picture 2>, when it is listed, is a photo of the DAUGHTER", si)          # i2v: Picture 1 is the scene
        self.assertIn("<Picture 1>, when it is listed, is a photo of the DAUGHTER", s)           # v2v: no scene picture
        self.assertTrue(t.rstrip().endswith(":") and ti.rstrip().endswith(":"))
        sp, spi = pack.preset_prompts(), pack.preset_prompts("i2v")
        self.assertIn("daughter", sp[names["12"]]); self.assertIn("daughter", spi[names["12"]])
        self.assertNotEqual(sp[names["12"]], spi[names["12"]])

    def test_musician_presets_set_the_mtv_stem_and_audio(self):
        info = pack.preset_audio_info()
        names = {n.split(" ", 1)[0]: n for n in pack._preset_names()}
        self.assertEqual(info["None"], {"audio": "", "stem": ""})
        for k, stem in (("7", "Vocals"), ("8", "Drums"), ("9", "Bass"), ("10", "Guitars")):
            self.assertEqual(info[names[k]], {"audio": "Custom Audio", "stem": stem})
        for k in ("1", "2", "3", "4", "5", "6", "11"):
            self.assertEqual(info[names[k]], {"audio": "", "stem": ""})
        self.assertEqual(info[names["12"]], {"audio": "Custom Audio", "stem": "Full"})            # IronLeo78 Mode: the FULL mix (vocals + guitar + drums)
        d = pack._parse_preset_full("# SYSTEM\na\n# STEM\nDrums\n# AUDIO\nCustom Audio\n")
        self.assertEqual((d["stem"], d["audio"]), ("Drums", "Custom Audio"))
        self.assertEqual(pack._preset_sort_key("10 - x") > pack._preset_sort_key("9 - x"), True)
        self.assertTrue(pack._preset_sort_key("None") > pack._preset_sort_key("11 - x"))

    def test_relabel_and_bom(self):
        # v0.3.4 #2: the rules use the labels the MTV gives (it counts only the pictures that are sent)
        txt = "<Picture 1> is the actor, <Picture 2> the second, <Picture 3> the environment, <Picture 4> unused"
        self.assertEqual(pack._labels([1, 3]), {1: 1, 3: 2})
        self.assertEqual(pack._relabel(txt, [1, 3]), "<Picture 1> is the actor, <slot 2: not provided> the second, <Picture 2> the environment, <slot 4: not provided> unused")
        self.assertEqual(pack._relabel(txt, [1, 2, 3]), txt.replace("<Picture 4>", "<slot 4: not provided>"))      # no gap: the same numbers
        self.assertEqual(pack._relabel(txt, []).count("not provided"), 4)
        self.assertEqual(pack._relabel("no labels here", [1]), "no labels here")
        # v0.3.4 #1: a preset file saved with a BOM keeps its first section
        self.assertEqual(pack._parse_preset_full("\ufeff# SYSTEM\nrules\n# TASK\ntask:\n")["system"], "rules")
        import tempfile
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "9 - bom.md"), "wb") as fh:
            fh.write(b"\xef\xbb\xbf# SYSTEM\nrules\n# TASK\ntask:\n# PROMPT\nhello\n")
        old = pack.PRESET_DIR
        pack.PRESET_DIR = d
        try:
            self.assertEqual(pack._read_preset("9 - bom"), ("rules", "task:"))
            self.assertEqual(pack.preset_prompts()["9 - bom"], "hello")
        finally:
            pack.PRESET_DIR = old

    def test_frame_cap(self):
        self.assertEqual(pack._llm_frame_indices(10), list(range(10)))
        self.assertEqual(pack._llm_frame_indices(120), list(range(120)))
        ix = pack._llm_frame_indices(300)
        self.assertEqual((len(ix), ix[0], ix[-1]), (120, 0, 299))
        self.assertTrue(all(a < b for a, b in zip(ix, ix[1:])))                   # increasing, no repeats
        t = pack._frame_info([1], 300, "2", ix)
        self.assertIn("120 frames of Video 1 (evenly spaced out of its 300 frames", t)
        self.assertIn("lasts 00:25.000", t)                                       # the real length is still given
        self.assertNotIn("evenly spaced", pack._frame_info([1], 10, "12"))        # a short clip: all frames, as before

    def test_i2v_frame_text(self):
        t = pack._frame_info_i2v([1, 2], 5.0)
        self.assertIn("image-to-video request", t)
        self.assertIn("(<Picture 1>, <Picture 2>, in this order)", t)
        self.assertIn("about 5 seconds", t)
        self.assertIn("00:05.000", t)
        self.assertIn("no reference pictures", pack._frame_info_i2v([], 3.0))

    def test_none_is_empty(self):
        self.assertEqual(pack._read_preset("None"), ("", ""))
        self.assertEqual(pack._read_preset(""), ("", ""))

    def test_shipped_presets(self):
        names = pack._preset_names()
        self.assertEqual(len(names), 12)                                               # v0.3.0: 3 actor presets + 8 more; v0.3.3: + IronLeo78 Mode
        self.assertEqual([n.split(" ", 1)[0] for n in names], [str(i) for i in range(1, 13)])      # natural order: 10, 11 and 12 come after 9
        self.assertTrue(names[0].startswith("1 - ") and names[1].startswith("2 - ") and names[2].startswith("3 - "))
        req = pack.IronLeo78_9ImagesToBatchToLLM.INPUT_TYPES()["required"]
        self.assertEqual(req["Preset"][0], ["None"] + names)
        self.assertEqual(req["Preset"][1]["default"], "None")
        s1, t1 = pack._read_preset(names[0])
        s2, t2 = pack._read_preset(names[1])
        self.assertTrue(s1 and t1 and s2 and t2)
        for key in ("<Picture 1>", "<Video 1>", "attribute_transfer", "video editing", "fully_copy", "At MM:SS.mmm", "TIMELINE"):
            self.assertIn(key, s1)
        self.assertIn("Replace ONLY the main actor", t1)
        self.assertTrue(t1.endswith(":"))                  # the user's own prompt follows it
        # v0.1.23: preset 2 = preset 1 + the environment of <Picture 2>; both follow the guide's six sections, the audio rule and the timeline rule
        for key in ("<Picture 2>", "environment", "attribute_transfer", "fully_preserved", "fully_copy", "TIMELINE", "At MM:SS.mmm",
                    "[video editing + reference generation + audio reuse]", "<Subject 2>"):
            self.assertIn(key, s2)
        self.assertIn("Preset 2", t2)
        self.assertTrue(t2.rstrip().endswith(":"))
        self.assertNotEqual(s1, s2)
        rule8 = lambda s: s[s.index("8. Timing (mandatory)"):s.index("9. If the request")]
        self.assertEqual(rule8(s1), rule8(s2))                                # the same timeline rule in both
        self.assertNotIn("Placeholder", names[1])
        # v0.2.0: preset 3 = two actors + environment, matched BY GENDER, same guide rules and the same timeline rule
        s3, t3 = pack._read_preset(names[2])
        for key in ("<Picture 1>", "<Picture 2>", "<Picture 3>", "<Subject 4>", "GENDER MATCHING", "MATCH BY GENDER", "no matter which person",
                    "attribute_transfer", "fully_preserved", "fully_copy", "TIMELINE", "[video editing + reference generation + audio reuse]",
                    "ORDER of the vocal events", "explicitly"):
            self.assertIn(key, s3)
        self.assertIn("BY GENDER", t3)
        self.assertTrue(t3.rstrip().endswith(":"))
        self.assertEqual(rule8(s1), rule8(s3))                                # the same timeline rule in all three

    def test_one_text_carries_everything(self):
        info = pack._frame_info([1], 10, "12")
        self.assertEqual(pack._llm_text(info, "", ""), info)                       # no preset: the frame info alone
        s, t = pack._read_preset(pack._preset_names()[0])
        full = pack._llm_text(info, s, t)
        self.assertTrue(full.startswith(info))
        self.assertTrue(full.index(s) < full.index(t))
        self.assertTrue(full.rstrip().endswith(":"))                               # the user's prompt is appended right after

    def test_missing_file_is_an_error(self):
        with self.assertRaises(FileNotFoundError):
            pack._read_preset("nope")

    def test_edited_preset_changes_the_value(self):
        IC = pack.IronLeo78_9ImagesToBatchToLLM.IS_CHANGED
        base = dict(image_1="", Start_From=0.0, Duration=5.0, Frame_Interval="12", Video_Size="672x384")
        self.assertNotEqual(IC(**base, Preset="None"), IC(**base, Preset=pack._preset_names()[0]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
