# IronLeo78 MTV (v0.01)

**Turn your song into a music video, one clip at a time, without building a 50-node workflow.**

*[Version française : README_fr.md](README_fr.md)*

*Pre-alpha. A ComfyUI node pack for MiniMax H3: a singer or musician performs your track, and every clip is cut to your own recording.*

## The pitch

Making a synced music video in ComfyUI normally means a giant graph: model loaders, LoRAs, audio slicing, reference pictures, conditioning, guide frames, samplers, decoders, savers, then a second graph to upscale. And you rebuild or re-wire it for every segment of the song.

IronLeo78 MTV packs all of that into **three nodes**:

- **Pick a song, press Run.** The node cuts the matching slice of your audio, freezes it into the video latent and generates the picture to follow the music. MiniMax H3 never invents sound: what you hear is your recording.
- **One clip per Run, and it keeps its place.** A segment panel on the node shows how many segments your song holds, which is next, and your progress. Jump to any segment, redo a bad one, or let it step through the whole song.
- **Continuity built in.** *Guide* starts each clip from the last frame of the previous one, so the performance flows.
- **Follow one instrument.** *Audio Stem* splits the song once (vocals, guitars, drums, bass) and lets the picture follow only that part. Stems are cached on disk, never separated twice.
- **Upscale later, only what you like.** Switch *Save Latent* ON and each clip leaves its latent and conditioning behind. Feed the ones you want into the Revitalizer for a 2 MP refined version.

### How many nodes it saves

Counted from what the code calls, so treat the numbers as approximate:

| Node in this pack | Replaces roughly | What those are |
|---|---|---|
| **IronLeo78 MTV** | **30+ nodes** | model, 2 LoRA and attention-backend loaders, text encoder and 2 VAE loaders, audio / video / 3 picture loaders, MiniMax H3 reference-to-video and guide, audio trim + encode, mask nodes, AV concat / separate, noise, guider, sampler select, scheduler, sampler, 2 decoders, Create Video, Save Video, latent savers |
| **IronLeo78 2in1 Revitalizer** | **20+ nodes** | latent and conditioning loaders, UNET + LoRA switch + attention backend, AV separate / concat, H3 latent upscaler, mask nodes, noise, guider, sampler select, sampler, 2 VAE loaders, 2 decoders, Create Video, Save Video |
| **IronLeo78 MTV Model Loader** | optional | one node to change models, LoRAs, steps and seed for several MTV nodes at once |

**About 50 nodes (and all their wiring) become 2 nodes you actually work with.** The Model Loader is the optional third.

## The nodes

All under **IronLeo78 > MTV**.

| Node | Id | What it does |
|---|---|---|
| **IronLeo78 MTV (v0.01)** | `IronLeo78_MTV` | One clip per Run, cut and synced to your song. |
| **IronLeo78 MTV Model Loader** | `IronLeo78_MTV_ModelLoader` | Optional. Diffusion model, Turbo and custom LoRA, text encoder, VAEs, step counts, seed. |
| **IronLeo78 2in1 Revitalizer** | `IronLeo78_2in1_Revitalizer` | Upscales and refines a clip from its saved latent + conditioning and saves the video. |

```
song -> MTV (Save Latent ON) -> clips + .latent / .conditioning
                                   '-> Revitalizer -> upscaled clip
```

## Install

1. Put the folder `ironleo78_mtv` (with `__init__.py` directly inside) into `ComfyUI/custom_nodes/`.
2. Restart ComfyUI, then hard-refresh the browser (Ctrl+F5).
3. Right-click the canvas, **Add Node > IronLeo78 > MTV**.

**You need:**

- ComfyUI with its own **MiniMax H3** nodes. PyAV, torchaudio and safetensors ship with ComfyUI. No extra pip packages.
- The H3 model files in the usual folders: `diffusion_models`, `loras`, `text_encoders`, `vae`.
- **Only for the Revitalizer's upscale step:** the third-party node *Comfyui_Minimax_h3_latent_Upscaler* and its model:
  `cd ComfyUI/custom_nodes && git clone https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler.git`
  and put `h3_upscaler_lms_v0.1.safetensors` in `ComfyUI/models/latent_upscale_models/`. The Revitalizer calls it by name and does not bundle it (MIT, (c) LBH-123-AI). Without it, switch the Revitalizer's Upscale OFF.
- Hybrid Demucs weights (about 320 MB) download by themselves the first time an Audio Stem is used.

```
ComfyUI/custom_nodes/ironleo78_mtv/
├── __init__.py
├── mtv.py                              (the MTV node)
├── model_loader.py                     (Model Loader)
├── revitalizer.py                      (2in1 Revitalizer)
├── conditioning_io.py                  (reads / writes .conditioning files)
├── stems.py                            (Audio Stem: Hybrid Demucs + disk cache)
├── requirements.txt
├── README.md
├── README_fr.md
├── tests/                              (optional)
└── web/
    ├── ironleo78_mtv.js                (segment panel, thumbnails, status box)
    └── ironleo78_2in1_revitalizer.js   (Upload button)
```

## Instructions

### Make a music video

1. Add **IronLeo78 MTV**. Optionally add the **Model Loader** and plug its `models` output into the MTV's `models` input.
2. **Custom Audio File:** choose your song. Its name becomes the output folder and file prefix.
3. **Bypassed Audio Latent = Custom Audio.** The song is cut into chunks as long as one clip.
4. **Use Video = OFF** (image to video) is the normal case. **Picture1** is the singer / musician and sets the size and aspect ratio; Picture2-3 are extra references (outfit, location). Use Video ON lets an existing video drive the frames instead.
5. Write the **prompt**, referring to `<Picture 1>` etc. Describe the performance (singing to camera, playing guitar, stage lighting). Change it between Runs to follow the song's sections.
6. Set **duration** (15 s default), **Next Segment On Run = ON**, **Guide = ON**. Switch **Save Latent = ON** if you want to upscale later.
7. Check the **segment panel** at the top of the node, then press Run once per segment (or queue several). After the last segment the node stops quietly.
8. **Start in the middle:** type a segment number in the jump row and press **Go**. **Latest** returns to the furthest point. **Reset** starts over.
9. **Redo a bad clip:** Jump to it, Run, press Latest. The redo is saved beside the old one and the assembly script uses the newest.

Where cutting starts: the **segment counter** is the only thing that decides it. Segment 1 starts at second 0; each following segment starts one real clip length later (`frames / 24 fps`; duration 5 s = 124 frames = 5.17 s). Jump to segment N and the next Run starts at `(N - 1) x clip length`, for audio and video together.

### Upscale a clip with the Revitalizer

1. Make the clip with **Save Latent = ON**.
2. Add **IronLeo78 2in1 Revitalizer** and press **R** to refresh its lists. The `latent` dropdown shows every `*_video.latent` in `ComfyUI/output/`, newest first. The matching `.conditioning` is picked automatically.
3. For a faithful refine, set `seed` to the clip's own seed (the sidecar `.json` lists it as `same_noise_seed`).
4. Run. Progress goes to the console as `[Revitalizer] ...`, and the finished video is saved and previewed.
5. Clips from another machine: click **Upload latent / conditioning files...** and pick the `_video.latent`, `_audio.latent` and `.conditioning` together. They are copied into `ComfyUI/input/ironleo78_revitalizer/` and selected for you.


## MTV settings

| Setting | What it does |
|---|---|
| **Turbo** | ON = Turbo LoRA, 4 steps. OFF = 25 steps, no Turbo LoRA. |
| **Use Video / Video File** | ON = the video supplies frames and size. OFF = Picture1 sets the size. |
| **Custom Audio File** | Your song. |
| **Audio Stem** | Song, Vocals, Guitars, Drums or Bass: which part of the song is used. |
| **megapixels** | 0.1 to 1.0 (default 0.2), sides multiples of 32. |
| **duration** | Seconds per clip (default 15); real length follows MiniMax frame rules (frames % 17 == 5). |
| **Next Segment On Run** | ON = every Run moves to the next segment. OFF = always segment 1. |
| **Bypassed Audio Latent** | Audio From Video, or Custom Audio (your song, chunked). |
| **Save Latent** | OFF (default) = only the clip. ON = also save the video / audio latent and the conditioning. |
| **Guide** | Last frame of the previous clip guides the next (needs Next Segment ON). |
| **Picture1-3** | Reference pictures with thumbnails. |

Hardcoded: BasicGuider, `res_multistep`, `simple` scheduler, 24 fps, mp4 / h264.

### Audio Stem

- The first time a stem is chosen for a song, Hybrid Demucs separates **all four** at once (about 13 s for a 2 minute song on a typical GPU). Every later Run and session just reads a file.
- Saved to `ComfyUI/output/<Song>/stems/` as `<Song>_Vocals.wav`, `_Guitars.wav` (Demucs' "other": guitars, keys, synths), `_Drums.wav`, `_Bass.wav`, plus `<Song>_stems.json` (written last, so a half-finished job is never trusted).
- Reused while the song under that name has the same content (SHA-1). To force a new separation, delete the `stems` folder.
- Only the **Custom Audio File** is separated, not the soundtrack of a Video File.

### Save Latent = ON

```
output/MySong/MySong_seg004_A_00001_.mp4                  (the clip)
output/MySong/MySong_seg004_A_00001_video.latent
output/MySong/MySong_seg004_A_00001_audio.latent
output/MySong/MySong_seg004_A_00001.conditioning
output/MySong/MySong_seg004_A_00001_.json                 (sidecar with prompt, settings and the three file names)
```

The number is the clip's own, so a redo never overwrites anything. `.conditioning` is your prompt and pictures encoded by MiniMax H3, without the guide. Anything that could not be stored is listed in the sidecar under `latent_details.conditioning_unsupported_items` (normally nothing). If the latent or conditioning cannot be written, the clip is still made and a note appears in the status box.

### Model Loader

No inputs, one output `models`. Changes the diffusion model, custom LoRA (toggle, file, strength 0.65), Turbo LoRA, Qwen3-VL text encoder, video / audio VAE, step counts (4 / 25) and the noise seed (1978, fixed). Nothing connected = built-in defaults. Several MTV nodes can share one loader.

### Revitalizer settings

| Input | Default | What it does |
| :--- | :--- | :--- |
| `latent` | newest clip | Every `*_video.latent` in `output/` plus uploaded ones. Press R after a new run. |
| `conditioning` | `(match the latent)` | Loads `<clip>.conditioning`. Pick another to use a different clip's. |
| `freeze_audio` | ON | The refine pass does not re-noise the song. |
| `unet_name`, `vae_video`, `vae_audio` | the H3 files | Models. |
| `lora_on`, `lora_name`, `lora_strength` | OFF, turbo 4-step, 1.0 | Model-only LoRA. |
| `attention_backend` | comfy kitchen attention | Falls back to PyTorch attention by itself. |
| `upscale_on` | ON | OFF = refine at the saved size. |
| `upscale_model` | `h3_upscaler_lms_v0.1` | From `latent_upscale_models`. |
| `megapixels` | 2.0 | Target size, 0.1 to 2.0. |
| `temporal_chunking`, `force_unload`, `upscale_device`, `upscale_precision` | ON, ON, cuda, fp16 | Same as the upscaler node. |
| `seed`, `sampler_name` | 0 (randomize), euler | |
| `filename_prefix` | `video/MiniMax_H3` | Same names and preview as Save Video. |

Fixed inside: 5-step sigmas `0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000`, align 32, 8 bit, sRGB, 24 fps, normal VAE decode, always saved. Outputs: `video`, `images`, `audio`, `latent` (the refined AV latent) and `status`.

## Outputs

`output/MySong/MySong_seg004_A_00001_.mp4`, a `.json` sidecar with the full prompt and settings next to every clip, and `MySong_manifest.csv` with each clip's start / end second in the song (plus `audio_stem`, `latent_file` and `conditioning_file`).

## Troubleshooting

| Problem | What to do |
|---|---|
| **Nodes missing** | The folder must sit directly in `custom_nodes/` with `__init__.py` inside it. Restart ComfyUI, press Ctrl+F5, and look in the console for an import error mentioning `ironleo78_mtv`. |
| **Import error about MiniMax H3** | Update ComfyUI: the MTV needs its core MiniMax H3 nodes. |
| **Revitalizer appears twice or errors on start** | Another copy of the Revitalizer is installed in `custom_nodes/`. Keep only one. |
| **Panel says "Segments: unknown"** | Select a Custom Audio File with Bypassed Audio Latent = Custom Audio (or a Video File with Use Video ON). |
| **A dropdown says "None" or a model is "not found"** | Put the file in the matching `ComfyUI/models/` folder and press R. Use the Model Loader if your file names differ from the defaults. |
| **The node stops and does nothing** | You passed the last segment of the song. Use Jump, Latest or Reset in the panel. |
| **Picture does not follow the right part of the song** | Check **Audio Stem** and that **Bypassed Audio Latent = Custom Audio**. |
| **Stem separation fails: corrupted checkpoint** | Delete the Hybrid Demucs file in `~/.cache/torch/hub/checkpoints/` and run again. |
| **Out of memory while separating or sampling** | Lower megapixels, close other GPU programs, or retry (separation retries once after unloading models). |
| **No `.latent` / `.conditioning` files** | They are only saved with **Save Latent = ON**. Look in `output/<Song>/`. A note in the status box says if saving failed (for example a full disk). |
| **Revitalizer list says "none found"** | Make a clip with Save Latent ON, then press R, or use the Upload button. |
| **Revitalizer: "audio latent is missing" or "conditioning not found"** | The three files of a clip must share a name and folder. Upload all three together. |
| **Revitalizer: "node ... not found"** | The third-party Minimax H3 Latent Upscaler is not installed. Install it, or switch Upscale OFF. |
| **Revitalizer: out of VRAM** | Lower `megapixels`, switch Upscale OFF, or close other GPU programs. The console prints the failed step and a tip. |

## Tests (optional, no GPU needed)

```
python tests/test_phased_run.py
python tests/test_conditioning_io.py
python tests/test_stems.py
python tests/test_revitalizer.py
node   tests/test_migration.mjs
node   tests/test_panel_jsdom.mjs      # needs: npm install jsdom
```

These run against stand-ins for ComfyUI. This pre-alpha build has not yet been run inside a live ComfyUI, so please report anything odd you see in the real thing.

by IronLeo78
