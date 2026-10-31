# Test of stems.py (the on-disk stem cache) with a FAKE separator: needs numpy only, no torch / ComfyUI / GPU.
#   python tests/test_stems.py
import contextlib, importlib.util, os, sys, tempfile, wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("stems", os.path.join(HERE, "..", "stems.py"))
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)

TMP = tempfile.mkdtemp()
OUT = os.path.join(TMP, "output")
os.makedirs(OUT)
ok = 0
def check(cond, msg):
    global ok
    assert cond, "FAIL: " + msg
    ok += 1
    print("  ok -", msg)

SONG = os.path.join(TMP, "My Song.wav")
open(SONG, "wb").write(b"song-content-1")
CALLS = {"separate": 0, "audio": 0}
SR = 44100

def fake_audio():
    CALLS["audio"] += 1
    return {"waveform": None, "sample_rate": 48000}

def make_separator(peak=0.5):
    def sep(audio, progress=None):
        CALLS["separate"] += 1
        if progress: progress(1, 1)
        t = np.linspace(0, 1, SR, dtype=np.float32)
        return {lab: np.stack([np.sin(2 * np.pi * (220 + 110 * i) * t) * peak] * 2) for i, lab in enumerate(st.STEM_LABELS)}, SR
    return sep

def go(sep=None, path=SONG, song="My_Song"):
    return st.ensure_stems(path, song, OUT, fake_audio, progress=None, separate=sep or make_separator())

print("1. first use: separate once, save four stems + metadata")
paths, info = go()
check(CALLS == {"separate": 1, "audio": 1} and not info["cached"], "separated once, the song was decoded once")
check(sorted(paths) == sorted(st.STEM_LABELS), "four stems: %s" % list(paths))
check(all(os.path.basename(p) == "My_Song_%s.wav" % lab for lab, p in paths.items()), "files are <Song>_<Stem>.wav")
check(os.path.dirname(paths["Bass"]) == os.path.join(OUT, "My_Song", "stems"), "saved in output/<Song>/stems/")
check(os.path.isfile(st.meta_file(OUT, "My_Song")), "<Song>_stems.json written")
with contextlib.closing(wave.open(paths["Vocals"], "rb")) as w:
    check((w.getnchannels(), w.getframerate(), w.getsampwidth(), w.getnframes()) == (2, SR, 2, SR), "a valid 16-bit stereo 44.1 kHz WAV, one second long")
check(not [f for f in os.listdir(os.path.dirname(paths["Bass"])) if f.endswith(".tmp")], "no temp files left behind")

print("2. every later use reads from disk")
paths2, info2 = go()
check(info2["cached"] and info2["seconds"] == 0.0 and CALLS == {"separate": 1, "audio": 1}, "second call: cached, nothing decoded, nothing separated")
check(paths2 == paths, "same paths")
st._HASHES.clear()                  # a new session: nothing in memory
paths3, info3 = go()
check(info3["cached"] and CALLS["separate"] == 1, "a new session finds the stems on disk")
copy = os.path.join(TMP, "My Song copy.wav")
open(copy, "wb").write(b"song-content-1")
check(go(path=copy)[1]["cached"], "same name + same content (re-uploaded file): still cached")

print("3. stale / damaged caches are made again")
open(SONG, "wb").write(b"song-content-2 (edited)")
_, i = go()
check(not i["cached"] and CALLS["separate"] == 2, "the song changed under the same name: separated again")
with open(paths["Drums"], "r+b") as f: f.truncate(100)
_, i = go()
check(not i["cached"] and CALLS["separate"] == 3, "a truncated stem: separated again")
os.remove(paths["Guitars"])
_, i = go()
check(not i["cached"] and CALLS["separate"] == 4, "a missing stem: separated again")
os.remove(st.meta_file(OUT, "My_Song"))
_, i = go()
check(not i["cached"] and CALLS["separate"] == 5, "no metadata (interrupted run): separated again")
_, i = go()
check(i["cached"] and CALLS["separate"] == 5, "and cached afterwards")
st.CHUNK_LENGTH = 12.0
_, i = go()
check(not i["cached"] and CALLS["separate"] == 6, "different separation settings: separated again")
st.CHUNK_LENGTH = 10.0
_, i = go()
check(not i["cached"] and CALLS["separate"] == 7, "settings back to the original: the stems are made for them again")

print("4. loud sources never clip")
paths, _ = go(sep=make_separator(peak=1.6), path=(open(SONG, "wb").write(b"loud") and SONG))
with contextlib.closing(wave.open(paths["Vocals"], "rb")) as w:
    data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
check(np.abs(data).max() <= 32767 and np.abs(data).max() > 30000, "peak 1.6 -> one common gain, loud but not clipped (%d)" % np.abs(data).max())
import json
check(json.load(open(st.meta_file(OUT, "My_Song")))["peak_gain"] < 1.0, "the gain is recorded in the metadata")

print("5. errors")
open(SONG, "wb").write(b"another")
try:
    st.ensure_stems(SONG, "My_Song", OUT, lambda: None, separate=make_separator())
    check(False, "undecodable audio accepted")
except RuntimeError as e:
    check("Could not read the audio" in str(e), "an undecodable song gives a clear error")
check(st.read_cache(OUT, "My_Song", "x") is None, "a cache is never used for a different source hash")
check(st.STEM_CHOICES == ("Full", "Vocals", "Guitars", "Drums", "Bass"), "dropdown order: Full, Vocals, Guitars, Drums, Bass")

print("6. v0.1.9: two different songs whose names clean to the same text keep their own stems")
OUT6 = os.path.join(TMP, "out6")
os.makedirs(OUT6)
A6, B6 = os.path.join(TMP, "song.wav"), os.path.join(TMP, "song.mp3")      # both clean to "song"
open(A6, "wb").write(b"first song")
open(B6, "wb").write(b"second song, other content")
run6 = lambda path: st.ensure_stems(path, "song", OUT6, fake_audio, separate=make_separator())
before = CALLS["separate"]
pa, ia = run6(A6)
pb, ib = run6(B6)
check(os.path.dirname(pa["Bass"]) == os.path.join(OUT6, "song", "stems"), "the first song keeps the plain folder output/song/stems")
check(os.path.dirname(pb["Bass"]) == os.path.join(OUT6, "song_" + st.file_sha1(B6)[:8], "stems") and not ib["cached"],
      "the other song gets its own folder: output/song_<8 characters of its fingerprint>/stems")
pa2, ia2 = run6(A6)
pb2, ib2 = run6(B6)
check(ia2["cached"] and ib2["cached"] and pa2 == pa and pb2 == pb and CALLS["separate"] == before + 2,
      "switching between the two: both read from disk, nothing separated again (it used to separate every time)")
open(A6, "wb").write(b"first song, edited")
pa3, ia3 = run6(A6)
check(not ia3["cached"] and pa3 == pa, "the SAME file edited (same name, new content) still replaces its own stems in its own folder")
copy6 = os.path.join(TMP, "song copy.wav")
open(copy6, "wb").write(b"first song, edited")
check(run6(copy6)[1]["cached"], "another file name with the same content: still the same stems (no new folder)")
check(st.cache_name(OUT6, "nothing_here", "abc", "x.wav") == "nothing_here", "no stems saved yet under that name: the plain name")

print("\nALL %d CHECKS PASSED" % ok)
