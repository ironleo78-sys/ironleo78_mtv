"""Tests for prompt_generator.py (v0.1.18, the all-in-one node). Needs torch (ComfyUI's Python). The LLM itself is stubbed.
Run:  python tests/test_prompt_generator.py"""
import importlib
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
gen = importlib.import_module(os.path.basename(PACK) + ".prompt_generator")
pk = importlib.import_module(os.path.basename(PACK))
cls = gen.IronLeo78_MTV_PromptGenerator


class ContractTests(unittest.TestCase):
    def test_registered_and_named(self):
        self.assertIn("IronLeo78_MTV_PromptGenerator", pk.NODE_CLASS_MAPPINGS)
        self.assertEqual(pk.NODE_DISPLAY_NAME_MAPPINGS["IronLeo78_MTV_PromptGenerator"], "IronLeo78-MTV-Prompt-Generator")
        self.assertNotIn("IronLeo78_9ImagesToBatchToLLM", pk.NODE_CLASS_MAPPINGS)        # v0.1.21: the old standalone node is removed

    def test_outputs(self):
        self.assertEqual(cls.RETURN_NAMES, ("Pictures", "MTV_Prompt"))
        self.assertEqual(cls.RETURN_TYPES, ("IRONLEO78_PICTURES", "STRING"))

    def test_widgets_are_the_loaders_plus_prompt_and_llm(self):
        gen._llm_files = lambda: ["a.safetensors", gen.DEFAULT_LLM]
        keys = list(cls.INPUT_TYPES()["required"])
        self.assertEqual(keys, [f"image_{i}" for i in range(1, 10)] +
                         ["video", "Start_From", "Duration", "Frame_Interval", "Video_Size", "Preset", "prompt", "LLM", "Use LLM", "Mode", "Seed", "Keep LLM in RAM"])
        sd = cls.INPUT_TYPES()["required"]["Seed"]
        self.assertEqual((sd[0], sd[1]["default"], sd[1]["control_after_generate"]), ("INT", 0, True))
        m = cls.INPUT_TYPES()["required"]["Mode"]
        self.assertEqual((m[0], m[1]["default"]), (["v2v", "i2v"], "v2v"))
        u = cls.INPUT_TYPES()["required"]["Use LLM"]
        self.assertEqual((u[0], u[1]["default"]), ("BOOLEAN", True))
        self.assertEqual(cls.INPUT_TYPES()["required"]["LLM"][1]["default"], gen.DEFAULT_LLM)
        self.assertTrue(cls.INPUT_TYPES()["required"]["prompt"][1]["multiline"])

    def test_guide_ships(self):
        g = gen._read_guide()
        self.assertTrue(g.startswith("# Full-Reference Mode Rewrite Output Format Guide"))
        self.assertIn("`detailed_description`", g)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.calls = {}
        gen._llm_files = lambda: [gen.DEFAULT_LLM]
        gen._load_clip = lambda name: self.calls.setdefault("clip", name) or "CLIP"

        def fake_generate(clip, request, image, system_prompt, seed=0):
            self.calls.update(request=request, image=image, system=system_prompt, seed=seed)
            return "FINAL PROMPT"
        gen.generate = fake_generate
        self.freed = []
        gen._free = lambda: self.freed.append(1)

    def run_node(self, **over):
        kw = dict(Start_From=0.0, Duration=5.0, Frame_Interval="12", Video_Size="672x384", Preset="None", prompt="Replace him.",
                  LLM=gen.DEFAULT_LLM, video="")
        kw.update({f"image_{i}": "" for i in range(1, 10)})
        kw["Keep LLM in RAM"] = False      # (the node defaults to ON since 0.4.3: these tests are about the unload path)
        kw.update(over)
        return cls().run(**kw)      # ("Use LLM" is not sent unless a test passes it: the node must default to ON)

    def test_no_media_still_runs(self):
        out = self.run_node()
        self.assertEqual(len(out), 2)
        self.assertEqual(out[-1], "FINAL PROMPT")
        self.assertEqual(len(out[0]), 9)
        self.assertTrue(all(torch.is_tensor(t) for t in out[0]))
        self.assertTrue(self.calls["request"].endswith("Replace him."))
        self.assertIn("no reference pictures", self.calls["request"])
        self.assertTrue(self.calls["system"].startswith("# Full-Reference Mode"))
        self.assertEqual(self.freed, [1])

    def test_preset_goes_between_the_frame_info_and_the_prompt(self):
        name = [n for n in gen._Loader.INPUT_TYPES()["required"]["Preset"][0] if n != "None"][0]
        self.run_node(Preset=name)
        req = self.calls["request"]
        self.assertIn("PRESET 1", req)
        self.assertTrue(req.index("There are no reference pictures") < req.index("PRESET 1") < req.index("Replace him."))

    def test_llm_off_passes_the_prompt_through(self):
        out = self.run_node(**{"Use LLM": False, "prompt": "  keep me exactly  ", "LLM": "not-installed.safetensors"})
        self.assertEqual(out[-1], "  keep me exactly  ")
        self.assertEqual(len(out[0]), 9)
        self.assertNotIn("request", self.calls)         # generate() never ran
        self.assertNotIn("clip", self.calls)            # the LLM was never loaded
        self.assertEqual(self.freed, [])
        self.run_node(**{"Use LLM": True})
        self.assertEqual(self.calls["request"].split("\n")[-1], "Replace him.")      # ON (also the default) still uses the LLM

    def test_i2v_mode_has_no_video_and_its_own_texts(self):
        name = [n for n in gen._Loader.INPUT_TYPES()["required"]["Preset"][0] if n != "None"][0]
        self.run_node(Preset=name, Mode="i2v", video="not-a-real-video.mp4", Duration=7.0)        # a loaded video is ignored: it is not even looked up
        req = self.calls["request"]
        self.assertIn("image-to-video request", req)
        self.assertIn("NO video", req)
        self.assertIn("about 7 seconds", req)
        self.assertIn("00:07.000", req)
        self.assertNotIn("frame 1 =", req)                                   # no frame times without a video
        self.assertIn("IMAGE-TO-VIDEO", req)                                 # the i2v system text, not the v2v one
        self.assertNotIn("PRESET 1 - REPLACE THE MAIN ACTOR (this preset", req)
        self.assertTrue(req.index("image-to-video request") < req.index("IMAGE-TO-VIDEO") < req.index("Replace him."))
        self.run_node(Preset=name, Mode="v2v")
        self.assertIn("PRESET 1 - REPLACE THE MAIN ACTOR (this preset", self.calls["request"])      # v2v as before

    def test_i2v_with_a_preset_that_has_no_i2v_text_is_a_clear_error(self):
        import tempfile
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "9 - v2v only.md"), "w", encoding="utf-8") as fh:
            fh.write("# SYSTEM\na\n# TASK\nb:\n# PROMPT\nc\n")
        ni = sys.modules[gen._Loader.__module__]
        old = ni.PRESET_DIR
        ni.PRESET_DIR = d
        try:
            self.run_node(Preset="9 - v2v only")                              # v2v works
            with self.assertRaises(ValueError):
                self.run_node(Preset="9 - v2v only", Mode="i2v")
        finally:
            ni.PRESET_DIR = old

    def test_gaps_in_the_slots_give_consistent_labels(self):
        # slots 1 and 3 filled (slot 2 empty): the rules and the request use the MTV labels <Picture 1> / <Picture 2>
        name = [n for n in gen._Loader.INPUT_TYPES()["required"]["Preset"][0] if n.startswith("3 - ")][0]
        import torch as _t
        gen._Loader.__mro__[0].__dict__                                          # (no-op: keeps the import used)
        ni = sys.modules[gen._Loader.__module__]
        old = ni._load_tensor, ni.folder_paths
        ni._load_tensor = lambda p: _t.zeros((1, 8, 8, 3))
        class FP:
            exists_annotated_filepath = staticmethod(lambda v: True)
            get_annotated_filepath = staticmethod(lambda v: v)
        ni.folder_paths = FP
        try:
            self.run_node(Preset=name, image_1="a.png", image_3="c.png")
        finally:
            ni._load_tensor, ni.folder_paths = old
        req = self.calls["request"]
        self.assertIn("<Picture 1>, <Picture 2> (slot 3)", req)
        self.assertIn("already count only the pictures that are sent", req)
        self.assertIn("<slot 2: not provided>", req)                              # the unused secondary-actor slot can never be mistaken for another picture
        self.assertNotIn("<Picture 3>", req)                                      # only two pictures are sent

    def test_the_guide_file_is_part_of_IS_CHANGED(self):
        base = dict(Start_From=0.0, Duration=5.0, Frame_Interval="12", Video_Size="672x384", Preset="None", video="", prompt="a", LLM="x", Mode="v2v")
        h1 = gen.IronLeo78_MTV_PromptGenerator.IS_CHANGED(**base)
        old = gen.GUIDE_FILE
        import tempfile
        d = tempfile.mkdtemp()
        g = os.path.join(d, "guide.md")
        open(g, "w").close()
        gen.GUIDE_FILE = g
        try:
            h2 = gen.IronLeo78_MTV_PromptGenerator.IS_CHANGED(**base)
            with open(g, "w") as fh:
                fh.write("changed")
            h3 = gen.IronLeo78_MTV_PromptGenerator.IS_CHANGED(**base)
        finally:
            gen.GUIDE_FILE = old
        self.assertEqual(len({h1, h2, h3}), 3)                                    # an edited guide gives a new value

    def test_the_presets_route_is_registered_and_answers(self):
        # v0.3.8: the /ironleo78/mtv/presets route (skipped outside ComfyUI) registered against a fake PromptServer, then called
        import asyncio, json, types as _types
        got = {}
        class Routes:
            def get(self, path):
                def deco(fn):
                    got[path] = fn
                    return fn
                return deco
        fake_server = _types.ModuleType("server")
        fake_server.PromptServer = _types.SimpleNamespace(instance=_types.SimpleNamespace(routes=Routes()))
        old = sys.modules.get("server")
        sys.modules["server"] = fake_server
        try:
            gen._register_routes()
        finally:
            if old is not None:
                sys.modules["server"] = old
            else:
                del sys.modules["server"]
        self.assertIn("/ironleo78/mtv/presets", got)
        resp = asyncio.run(got["/ironleo78/mtv/presets"](None))
        body = json.loads(resp.text)
        self.assertTrue(body["ok"])
        self.assertEqual(set(body), {"ok", "presets", "i2v", "audio", "stems"})
        self.assertEqual(len(body["presets"]), 13)                                  # None + the 12 presets
        self.assertEqual(body["stems"]["8 - Drummer performance"], "Drums")
        self.assertEqual(body["audio"]["12 - IronLeo78 Mode"], "Custom Audio")
        self.assertTrue(body["i2v"]["1 - Replace main actor"].startswith("Replace the main character of Picture 1"))

    def test_forced_unload_only_when_the_llm_stayed_in_memory(self):
        f = gen._needs_forced_unload
        self.assertTrue(f(1000, 5000, 4800))                  # the LLM added 4000 MB and 200 MB went away: it is still there
        self.assertFalse(f(1000, 5000, 1100))                 # it left
        self.assertTrue(f(1000, 5000, 2500))                  # 2500 of 4000 freed is 62 %: less than 70 %, so it still counts as stuck
        self.assertFalse(f(1000, 5000, 2000))                 # 75 % freed: fine
    def test_forced_unload_edges(self):
        f = gen._needs_forced_unload
        self.assertFalse(f(1000, 1300, 1300))                 # the LLM added only 300 MB: not worth it
        self.assertFalse(f(None, 5000, 4800)); self.assertFalse(f(1000, None, 4800)); self.assertFalse(f(1000, 5000, None))   # no CUDA: never
        self.assertTrue(f(0, 4000, 4000)); self.assertFalse(f(0, 4000, 0))

    def test_the_fallback_runs_when_the_first_unload_did_not_free_the_memory(self):
        self.addCleanup(setattr, gen, "_vram_mb", gen._vram_mb)          # these patches must not leak into the other tests
        self.addCleanup(setattr, gen, "_force_unload", gen._force_unload)
        seq = iter([1000.0, 5000.0, 4900.0, 1200.0])          # base, before, after, after the forced unload
        gen._vram_mb = lambda: next(seq)
        called = []
        gen._force_unload = lambda: called.append(1)
        self.run_node()
        self.assertEqual(called, [1])
        seq2 = iter([1000.0, 5000.0, 1100.0])                 # it freed: no fallback
        gen._vram_mb = lambda: next(seq2)
        called.clear()
        self.run_node()
        self.assertEqual(called, [])

    def test_vram_probe_never_fails(self):
        v = gen._vram_mb()
        self.assertTrue(v is None or v >= 0)                                      # None without CUDA (this test machine may have either)

    def test_seed_reaches_the_llm(self):
        self.run_node()
        self.assertEqual(self.calls["seed"], 0)
        self.run_node(Seed=123456789)
        self.assertEqual(self.calls["seed"], 123456789)

    def test_llm_off_needs_neither_the_video_nor_the_preset(self):
        # v0.3.6: LLM OFF in i2v with a preset that has no i2v text and a video that does not exist: still a plain pass-through
        import tempfile
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "9 - v2v only.md"), "w", encoding="utf-8") as fh:
            fh.write("# SYSTEM\na\n# TASK\nb:\n# PROMPT\nc\n")
        ni = sys.modules[gen._Loader.__module__]
        old = ni.PRESET_DIR
        ni.PRESET_DIR = d
        try:
            out = self.run_node(**{"Use LLM": False, "Preset": "9 - v2v only", "Mode": "i2v", "video": "does-not-exist.mp4", "prompt": "as typed"})
        finally:
            ni.PRESET_DIR = old
        self.assertEqual(out[-1], "as typed")
        self.assertEqual(len(out[0]), 9)

    def test_the_llm_gets_at_most_120_video_frames(self):
        import torch as _t
        ni = sys.modules[gen._Loader.__module__]
        old = ni._decode_video_for_llm, ni.folder_paths
        seen = {}
        def fake_decode(path, start, duration, interval, size):
            return _t.zeros((120, 8, 8, 3)), 300      # (the frames the LLM gets, the window's frame count)
        ni._decode_video_for_llm = fake_decode
        class FP:
            exists_annotated_filepath = staticmethod(lambda v: True)
            get_annotated_filepath = staticmethod(lambda v: v)
        ni.folder_paths = FP
        try:
            self.run_node(video="clip.mp4", Duration=20.0, Frame_Interval="2")
        finally:
            ni._decode_video_for_llm, ni.folder_paths = old
        self.assertEqual(self.calls["image"].shape[0], 120)                       # no pictures loaded: the batch is just the capped frames
        req = self.calls["request"]
        self.assertIn("120 frames of Video 1 (evenly spaced out of its 300 frames", req)
        self.assertIn("frame 1 = 00:00.000", req)
        self.assertIn("frame 120 = 00:24.917", req)                              # the last kept frame is source frame 299 of 300: 299 / 12 fps

    def test_empty_prompt_is_fine(self):
        self.run_node(prompt="  ")
        self.assertFalse(self.calls["request"].endswith("\n"))

    def test_missing_llm_file_is_a_clear_error(self):
        with self.assertRaises(FileNotFoundError):
            self.run_node(LLM="nope.safetensors")

    def test_llm_is_freed_even_when_generation_fails(self):
        def boom(*a):
            raise RuntimeError("llm failed")
        gen.generate = boom
        with self.assertRaises(RuntimeError):
            self.run_node()
        self.assertEqual(self.freed, [1])

    def test_keep_in_ram_reuses_the_model_and_only_offloads(self):
        loads = []
        gen._load_clip = lambda name: loads.append(name) or object()
        gen._clip_key = lambda name: (name, 1)
        offloaded = []
        self.addCleanup(setattr, gen, "_offload_clip", gen._offload_clip)
        gen._offload_clip = lambda clip: offloaded.append(1)
        gen._KEPT.clear()
        self.addCleanup(gen._KEPT.clear)
        self.run_node(**{"Keep LLM in RAM": True})
        self.run_node(**{"Keep LLM in RAM": True})
        self.assertEqual(len(loads), 1)
        self.assertEqual(offloaded, [1, 1])
        self.assertEqual(self.freed, [])
        gen._clip_key = lambda name: (name, 2)      # the file changed: a fresh load
        self.run_node(**{"Keep LLM in RAM": True})
        self.assertEqual(len(loads), 2)

    def test_keep_off_loads_every_time_and_drops_the_kept_model(self):
        loads = []
        gen._load_clip = lambda name: loads.append(name) or object()
        gen._clip_key = lambda name: (name, 1)
        gen._KEPT.clear()
        self.addCleanup(gen._KEPT.clear)
        self.run_node(**{"Keep LLM in RAM": True})
        self.assertEqual(len(gen._KEPT), 1)
        self.run_node()
        self.assertEqual(len(gen._KEPT), 0)
        self.run_node()
        self.assertEqual(len(loads), 3)
        self.assertEqual(self.freed, [1, 1])
    def test_two_llms_stay_kept_and_a_third_evicts_the_oldest(self):
        loads = []
        gen._load_clip = lambda name: loads.append(name) or object()
        gen._clip_key = lambda name: (name, 1)
        gen._llm_files = lambda: ["a.safetensors", "b.safetensors", "c.safetensors"]
        gen._KEPT.clear()
        self.addCleanup(gen._KEPT.clear)
        keep = {"Keep LLM in RAM": True}
        for n in ("a.safetensors", "b.safetensors", "a.safetensors", "b.safetensors"):
            self.run_node(LLM=n, **keep)
        self.assertEqual(loads, ["a.safetensors", "b.safetensors"])
        self.run_node(LLM="c.safetensors", **keep)
        self.assertEqual(len(gen._KEPT), 2)
        self.assertNotIn(("a.safetensors", 1), gen._KEPT)      # a was the least recently used

    def test_llm_off_clears_the_kept_model_even_with_keep_on(self):
        gen._load_clip = lambda name: object()
        gen._clip_key = lambda name: (name, 1)
        gen._KEPT.clear()
        self.addCleanup(gen._KEPT.clear)
        self.run_node(**{"Keep LLM in RAM": True})
        self.assertEqual(len(gen._KEPT), 1)
        self.run_node(**{"Keep LLM in RAM": True, "Use LLM": False})
        self.assertEqual(len(gen._KEPT), 0)

    def test_is_changed_ignores_the_keep_switch(self):
        base = dict(Start_From=0.0, Duration=5.0, Frame_Interval="12", Video_Size="672x384", Preset="None", video="", prompt="a", LLM="x")
        self.assertEqual(cls.IS_CHANGED(**base), cls.IS_CHANGED(**dict(base, **{"Keep LLM in RAM": True})))
    def test_keep_in_ram_is_on_by_default(self):
        self.assertTrue(cls.INPUT_TYPES()["required"]["Keep LLM in RAM"][1]["default"])
        gen._load_clip = lambda name: object()
        gen._clip_key = lambda name: (name, 1)
        gen._force_unload = lambda: None
        gen._KEPT.clear()
        self.addCleanup(gen._KEPT.clear)
        kw = dict(Start_From=0.0, Duration=5.0, Frame_Interval="12", Video_Size="672x384", Preset="None", prompt="x", LLM=gen.DEFAULT_LLM, video="")
        kw.update({f"image_{i}": "" for i in range(1, 10)})
        cls().run(**kw)                                        # the switch is not sent: ON
        self.assertEqual(len(gen._KEPT), 1)
    def test_offload_clip_unloads_only_the_llm_and_falls_back(self):
        mmod = types.ModuleType("comfy.model_management")
        seen = []
        mmod.unload_model_and_clones = lambda patcher: seen.append(patcher)
        mmod.soft_empty_cache = lambda: seen.append("empty")
        saved = {k: sys.modules.get(k) for k in ("comfy", "comfy.model_management")}
        pkg = types.ModuleType("comfy"); pkg.model_management = mmod
        sys.modules["comfy"], sys.modules["comfy.model_management"] = pkg, mmod
        self.addCleanup(lambda: [sys.modules.__setitem__(k, v) if v is not None else sys.modules.pop(k, None) for k, v in saved.items()])
        fell = []
        self.addCleanup(setattr, gen, "_force_unload", gen._force_unload)
        gen._force_unload = lambda: fell.append(1)
        class Clip: patcher = "P"
        gen._offload_clip(Clip())
        self.assertEqual(seen, ["P", "empty"])
        self.assertEqual(fell, [])                              # only the LLM's patcher was unloaded
        del mmod.unload_model_and_clones                        # an older ComfyUI: the old way
        gen._offload_clip(Clip())
        self.assertEqual(fell, [1])
    def test_is_changed_follows_the_prompt_and_the_llm(self):
        IC = cls.IS_CHANGED
        base = dict(Start_From=0.0, Duration=5.0, Frame_Interval="12", Video_Size="672x384", Preset="None", video="", prompt="a", LLM="x")
        self.assertNotEqual(IC(**base), IC(**dict(base, prompt="b")))
        self.assertNotEqual(IC(**base), IC(**dict(base, LLM="y")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
