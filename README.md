# IronLeo78 MTV (v0.4.8)

**Turn your song into a music video, one clip at a time, without building a 50-node workflow.**

*Pre-alpha. A ComfyUI node pack for MiniMax H3: a singer or musician performs your track, and every clip is cut to your own recording.*

## The pitch

Making a synced music video in ComfyUI normally means a giant graph: model loaders, LoRAs, audio slicing, reference pictures, conditioning, guide frames, samplers, decoders, savers, then a second graph to upscale. And you rebuild or re-wire it for every segment of the song.

IronLeo78 MTV packs all of that into **three nodes** (plus a fourth that loads your reference pictures):

- **Pick a song, press Run.** The node cuts the matching slice of your audio, freezes it into the video latent and generates the picture to follow the music. MiniMax H3 never invents sound: what you hear is your recording.
- **One clip per Run, and it keeps its place.** A segment panel on the node shows how many segments your song holds, which is next, and your progress. Jump to any segment, redo a bad one, or let it step through the whole song.
- **Continuity built in.** *Guide* starts each clip from the last frame of the previous one, so the performance flows.
- **Follow one instrument.** *Audio Stem* splits the song once (vocals, guitars, drums, bass) and lets the picture follow only that part. Stems are cached on disk, never separated twice.
- **Upscale later, only what you like.** Switch *Save Latent* ON and each clip leaves its latent and conditioning behind. Feed the ones you want into the Revitalizer for a larger refined version (0.4 MP by default, 2 MP at most).

### How many nodes it saves

Counted from what the code calls, so treat the numbers as approximate:

| Node in this pack | Replaces roughly | What those are |
|---|---|---|
| **IronLeo78 MTV** | **30+ nodes** | model, 2 LoRA and attention-backend loaders, text encoder and 2 VAE loaders, audio / video / picture loaders, MiniMax H3 reference-to-video and guide, audio trim + encode, mask nodes, AV concat / separate, noise, guider, sampler select, scheduler, sampler, 2 decoders, Create Video, latent savers |
| **IronLeo78 2in1 Revitalizer** | **20+ nodes** | latent and conditioning loaders, UNET + LoRA switch + attention backend, AV separate / concat, H3 latent upscaler, mask nodes, noise, guider, sampler select, sampler, 2 VAE loaders, 2 decoders, Create Video |
| **IronLeo78 MTV Model Loader** | optional | one node to change models, LoRAs, steps and seed for several MTV nodes at once |
| **IronLeo78-MTV-Prompt-Generator** | **10+ nodes** | 9 Load Image nodes, a video loader, frame selection, resize / crop, Batch Images, a Qwen description subgraph |

**About 50 nodes (and all their wiring) become 2 nodes you actually work with.** The Model Loader is the optional third.

## The nodes

All under **IronLeo78 > MTV**.

| Node | Id | What it does |
|---|---|---|
| **IronLeo78 MTV (v0.4.8)** | `IronLeo78_MTV` | One clip per Run, cut and synced to your song. |
| **IronLeo78 MTV Model Loader** | `IronLeo78_MTV_ModelLoader` | Optional. Diffusion model, Turbo and custom LoRA, text encoder, VAEs, step counts, seed. |
| **IronLeo78 2in1 Revitalizer** | `IronLeo78_2in1_Revitalizer` | Upscales and refines a clip from its saved latent + conditioning; its `video` output goes to your own Save Video. |
| **IronLeo78-MTV-Prompt-Generator** | `IronLeo78_MTV_PromptGenerator` | 9 pictures + 1 video + your prompt in; out: `Pictures` (the nine slots on one wire, to the MTV's `Pictures` input) and `MTV_Prompt` (to the MTV's prompt). Replaces the old 9-Images loader node and the prompt-generator subgraph (removed in v0.1.21).

```
song -> MTV (Save Latent ON) -> clips + .latent / .conditioning
                                   '-> Revitalizer -> upscaled clip
```

## Tested

**Tested by the author in a live ComfyUI: all three nodes (MTV, Model Loader, 2in1 Revitalizer) work as described here.** This is still a pre-alpha release (v0.0.5), so please report anything odd you find.

## Install

1. Put the folder `ironleo78_mtv` (with `__init__.py` directly inside) into `ComfyUI/custom_nodes/`.
2. Restart ComfyUI, then hard-refresh the browser (Ctrl+F5).
3. Right-click the canvas, **Add Node > IronLeo78 > MTV**.
4. **Updating from an older version?** v0.1.21 removed the standalone **9-Images-to-batch-to-LLM** node and the **MTV-LLM Prompt Generator** subgraph. A saved workflow that still uses them shows them as missing (red) nodes: replace them by the **IronLeo78-MTV-Prompt-Generator** and re-wire its two outputs (`Pictures`, `MTV_Prompt`) to the MTV. If you still have the old separate `ComfyUI-IronLeo78-9Images` folder in `custom_nodes/`, delete it.

## Requirements (all dependencies)

**ComfyUI itself** must be recent enough to include these, since the pack calls them by name:

| Needed | Used by |
|---|---|
| MiniMax H3 nodes (`comfy_extras.nodes_minimax_h3`: Reference to Video, Add Guide) | MTV |
| `LTXVSeparateAVLatent`, `LTXVConcatAVLatent` | MTV, Revitalizer |
| `CreateVideo`, `SaveVideo`, the `comfy_api.latest` video types | MTV, Revitalizer |
| `ModelAttentionBackend` (optional: the pack falls back to PyTorch attention) | MTV, Revitalizer |
| Core samplers and loaders: `RandomNoise`, `BasicGuider`, `BasicScheduler`, `KSamplerSelect`, `SamplerCustomAdvanced`, `UNETLoader`, `LoraLoaderModelOnly`, `CLIPLoader`, `VAELoader`, `VAEDecode`, `VAEDecodeAudio`, `VAEEncodeAudio`, `TrimAudioDuration`, `SolidMask`, `SetLatentNoiseMask` | MTV, Revitalizer |

**Python packages.** None to install: `torch`, `torchaudio`, `numpy`, `Pillow`, `PyAV` (`av`), `safetensors` and `aiohttp` all ship with ComfyUI. `einops` and ffmpeg are **not** needed.

**Optional third-party node (Revitalizer upscale step):** *Comfyui_Minimax_h3_latent_Upscaler*

```
cd ComfyUI/custom_nodes
git clone https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler.git
```

Restart ComfyUI afterwards. The Revitalizer calls it by name and does not bundle it (MIT, (c) LBH-123-AI). **Optional since v0.1.7:** without it (or without its model file) the Revitalizer resizes the latent itself and its refine pass redraws the detail; with it, its trained upscaler is used. The `status` output says which one ran.

**Model files** (pre-selected by default when installed; pick others in the Model Loader):

| File | Folder |
|---|---|
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` (diffusion model) | `models/diffusion_models/` |
| `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` (Turbo LoRA) | `models/loras/` |
| any LoRA for LoRa_1 / LoRa_2 / LoRa_3 (optional, none is set by default) | `models/loras/` |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` (text encoder) | `models/text_encoders/` |
| `minimax_h3_video_vae_int8_convrot.safetensors` (video VAE) | `models/vae/` |
| `minimax_h3_audio_vae_fp32.safetensors` (audio VAE) | `models/vae/` |
| `h3_upscaler_sharpness_2000steps_v0.1_fp32.safetensors` (optional: only with the upscaler node above) | `models/latent_upscale_models/` |

**Downloaded automatically:** the Hybrid Demucs weights (about 320 MB, into `~/.cache/torch/hub/checkpoints/`) the first time an Audio Stem is used. This needs an internet connection once.

**Folder layout:**

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
├── CHANGELOG.md
├── tests/                              (optional)
└── web/
    ├── ironleo78_mtv.js                (segment panel)
    └── ironleo78_2in1_revitalizer.js   (Upload button)
```

## Instructions

### Make a music video

1. Add **IronLeo78 MTV**. Optionally add the **Model Loader** and plug its `models` output into the MTV's `models` input.
2. **Custom Audio File:** choose your song. Its name becomes the output folder and file prefix.
3. **Choose Audio latent = Custom Audio** (the default). The song is cut into chunks as long as one clip and frozen into the audio latent, so the model never invents sound. Pick **MiniMax Audio** instead if you want the model to generate the sound itself, exactly like the official MiniMax H3 ref2v template (voice, effects, music; no bypass). Your song can still be given as a reference and called with `<Audio 1>` in the prompt.
4. **Use Video = OFF** (image to video) is the normal case. Load the singer / musician in slot **1** of the **IronLeo78-MTV-Prompt-Generator** (it sets the size and aspect ratio) and extra references (outfit, location ...) in slots **2 ... 9**, then wire its **Pictures** output to the MTV's **Pictures** input. Use Video ON lets an existing video drive the frames instead.
5. Write the **prompt**, referring to `<Picture 1>` etc. Describe the performance (singing to camera, playing guitar, stage lighting). Change it between Runs to follow the song's sections.
6. Set **duration** (5 s default), **Next Segment On Run = ON**, **Guide = ON**. **Save Latent** is ON by default (since v0.1.11), so every clip can be upscaled later; switch it OFF to save disk space.
7. **Save the clip yourself:** link the MTV's **`video`** output to a **Save Video** node (v0.0.5: the MTV no longer saves the clip and shows no video preview). The **`filename`** output holds the clip's name in the pack's usual naming (e.g. `Song/Song_seg004_A_00001_`, no extension); you can link it to Save Video's `filename_prefix` if you want the same stem (Save Video then adds its own `_00001_` after it). Nothing linked = the clip is made but not written to disk; the latent files, the `.json` sidecar and the manifest are still written.
8. Check the **segment panel** at the top of the node, then press Run once per segment (or queue several). After the last segment the node stops quietly (`video` and `filename` are then empty, so a linked Save Video does not run; `status` says FINISHED).
9. **Start in the middle:** type a segment number in the jump row and press **Go**. **Latest** returns to the furthest point. **Reset** starts over.
10. **Redo a bad clip:** Jump to it, Run, press Latest. The redo gets the next number, so the old clip and its latent files stay.

Where cutting starts: the **segment counter** is the only thing that decides it. Segment 1 starts at second 0; each following segment starts one real clip length later (`frames / 24 fps`; duration 5 s = 124 frames = 5.17 s). Jump to segment N and the next Run starts at `(N - 1) x clip length`, for audio and video together.

**One counter per song (v0.1.8):** each Custom Audio File (or, without one, each Video File) keeps its own counter, so switching to another song and back does not lose your place. The panel shows which counter it is (`counter: MySong.wav`), and Reset / Jump / Latest act on that song only. Two MTV nodes on the same song share its counter. After updating, the first song you run continues from the old counter; the others start at segment 1.

### Upscale a clip with the Revitalizer

1. Make the clip with **Save Latent = ON** (the default).
2. Add **IronLeo78 2in1 Revitalizer** and press **R** to refresh its lists. The `latent` dropdown shows every `*_video.latent` in `ComfyUI/output/`, newest first. The matching `.conditioning` is picked automatically.
3. To use the **same models, LoRAs and seed as your MTV**, click **`Use Set New Defaults`** on top of the Revitalizer (after clicking `Set New Defaults` once on a Model Loader). Otherwise, for a faithful refine, set `seed` to the clip's own seed (the sidecar `.json` lists it as `same_noise_seed`).
4. Link the Revitalizer's **`video`** output to a **Save Video** node (v0.0.9: the Revitalizer no longer saves the video; set the name there). Run. Progress goes to the console as `[Revitalizer] ...`.
5. Clips from another machine: click **Upload latent / conditioning files...** and pick the `_video.latent`, `_audio.latent` and `.conditioning` together. They are copied into `ComfyUI/input/ironleo78_revitalizer/` and selected for you.


## MTV settings

| Setting | What it does |
|---|---|
| **Turbo** | ON = Turbo LoRA, 6 steps. OFF = 30 steps, no Turbo LoRA. (Steps and the Turbo LoRA strength: Model Loader.) |
| **Use Video / Video File** | ON = the video supplies frames and size. OFF = the picture in slot 1 sets the size. |
| **Choose Audio latent** | Where the sound comes from (right under Video File since v0.1.11). **MiniMax Audio**: like the official MiniMax H3 ref2v template, no bypass: the model's own audio latent goes to the sampler and the model generates the sound (a Custom Audio File or video soundtrack is then only a reference, use `<Audio 1>` in the prompt). **Audio From Video**: the video soundtrack, frozen into the latent. **Custom Audio** (default): your song, chunked and frozen into the latent. |
| **Custom Audio File** | Your song. |
| **Audio Stem** | Full, Vocals, Guitars, Drums or Bass: which part of the song is used. |
| **megapixels** | 0.1 to 1.0 (default 0.2), sides multiples of 32. |
| **duration** | Seconds per clip (default 5, the arrows change it by 0.1 s); real length follows MiniMax frame rules (frames % 17 == 5). |
| **Next Segment On Run** | ON = every Run moves to the next segment. OFF = every Run makes the SAME segment: segment 1, or the one you chose with **Go** in the panel (since v0.2.3), and the counter is left as it is (v0.1.10). A counter that is already at the end of the file gives segment 1. The panel also has **Jump to time** (since v0.2.4): type a time in the video / song (`1:23`, or `83` for seconds) and click **Go time**; the next Run makes the segment that CONTAINS that time (it can start up to one segment, about 5 s, before the time you typed). It is the same counter as Go, so Sync from MTV follows it too. |
| **Save Latent** | ON (default since v0.1.11) = save the video / audio latent and the conditioning in the song folder, named like the clip (`<tag>_00001_video.latent`, `_audio.latent`, `<tag>_00001.conditioning`). OFF = no latent files. |
| **Guide** | Last frame of the previous clip guides the next (needs Next Segment ON). |
| **Pictures** (optional input, v0.1.20: replaces the nine Picture_1 ... Picture_9 sockets) | The only way to give reference pictures (no picker, no switch, no thumbnails on the node). One wire from the **IronLeo78-MTV-Prompt-Generator**'s Pictures output carrying its nine slots; every filled slot is sent as <Picture n> (nine references at most). An empty slot is skipped, and the numbers count only the filled ones (slots 1 + 3 filled = <Picture 1> and <Picture 2>). The grey **NONE** picture of an empty slot is skipped too and the status output names it. A picture has no file name, so with Use Video OFF and no Custom Audio File there is no name to build the clip folder from (it falls back to ideo/ComfyUI). A saved workflow that still has wires on the old Picture_n sockets keeps working; sockets with no wire are removed on load. |

Outputs: **`video`** (link it to a Save Video node), **`filename`** (the clip's name, no extension) and **`status`** (the run report as text: link it to a Preview Any / text node to read it; v0.0.9 removed the status box from the bottom of the node to save space).

Hardcoded: BasicGuider, `res_multistep`, `simple` scheduler, and Create Video (24 fps, sRGB, h264). Save Video is yours to configure.

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

The number is the clip's own, so a redo never overwrites anything. `.conditioning` is your prompt and pictures encoded by MiniMax H3, without the guide. Anything that could not be stored is listed in the sidecar under `latent_details.conditioning_unsupported_items` (normally nothing). If the latent or conditioning cannot be written, the clip is still made and a note appears in the `status` output.

### Model Loader

No inputs, one output `models`. A **`Set New Defaults` button** sits on top of the node, above every other option: set the Model Loader the way you want (models, LoRAs, steps, seed), click it, and **those values are saved as the new defaults**. **It is one SET, held on both sides:** the MTV uses it from its next run (even with no Model Loader connected), and **every Model Loader loads the same set again each time it is created or a workflow is opened** (models, LoRAs, steps, seed **and the seed's control after generate**), so after a reload the loader and the MTV hold the same values. The status line says so: with a connected loader, `models: Model Loader (same as the saved set)` or `Model Loader (DIFFERS from the saved set: turbo_steps=7)`. A value you change in the loader without clicking the button is only for the current session: it is replaced by the set on the next reload (a line under the button says what was replaced); click `Set New Defaults` again to keep it. No set saved = a workflow keeps its own values. The button reads the saved values back from the backend and prints a **confirmation line under the button** (`✔ New defaults saved: 19 of 19 values stored and read back`, or a warning naming a saved file that is not installed): no test run needed. The small **Factory** button next to it goes back to the built-in values. The defaults are stored in `mtv_defaults.json` in `ComfyUI/user/ironleo78_mtv/` (since v0.1.10, with the segment counters and the Guide's last frames, so updating the pack never wipes them; older versions kept them in the pack folder and the first start moves them). Changes the diffusion model, Turbo LoRA and its strength (`turbo_lora_strength`, default 1.0, right under the file since v0.1.11), three custom LoRAs **LoRa_1, LoRa_2, LoRa_3** (each with its own OFF / ON toggle, file and strength; default OFF, None, 1.0; applied after the Turbo LoRA, in this order), Qwen3-VL text encoder, video / audio VAE, step counts (6 / 30) and the noise seed (1978, fixed). These built-in values (also what **Factory** gives back) are the tuned set of v0.1.11. Nothing connected = built-in defaults. Several MTV nodes can share one loader. With no Model Loader connected, the MTV's status line says `models: saved defaults (Set New Defaults)`.

### Revitalizer settings

| Input | Default | What it does |
| :--- | :--- | :--- |
| `latent` | newest clip | Every `*_video.latent` in `output/` plus uploaded ones. Press R after a new run. |
| `conditioning` | `(match the latent)` | Loads `<clip>.conditioning`. Pick another to use a different clip's. |
| `freeze_audio` | ON | The refine pass does not re-noise the song. |
| `unet_name`, `vae_video`, `vae_audio` | the H3 files | Models. |
| `lora_on`, `lora_name`, `lora_strength` | ON, turbo 4-step, 1.0 | Model-only LoRA (the Turbo slot). A saved set puts the Model Loader's Turbo LoRA file and strength here. |
| `attention_backend` | comfy kitchen attention | Falls back to PyTorch attention by itself. |
| `upscale_on` | ON | OFF = refine at the saved size. ON = the optional upscaler node when installed, else the built-in latent resize. |
| `upscale_model` | `h3_upscaler_sharpness_2000steps_v0.1_fp32` | From `latent_upscale_models`; only used by the optional upscaler node. |
| `megapixels` | 0.4 | Target size, 0.1 to 2.0 (default 0.4 since v0.1.11; only new nodes get it). |
| `temporal_chunking`, `force_unload`, `upscale_device`, `upscale_precision` | OFF, OFF, cuda, fp16 | Same as the upscaler node. |
| `seed`, `sampler_name` | 1978 (fixed), res_multistep | |
| `sigmas` | `0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000` | The refine schedule (v0.0.9: visible and editable). Numbers separated by commas, going down from left to right; N numbers = N - 1 steps (the default is 5 steps). A bad list is refused with a message before the run. |
| `LoRa_1`, `LoRa_2`, `LoRa_3` (each: `_enabled`, file, `_strength`) | OFF, None, 1.0 | v0.0.9: three more model-only LoRAs, named like the Model Loader's. Applied after the LoRA above, in order (LoRa_1, 2, 3), only the ones that are ON (a LoRa that is OFF is never checked). They sit after `sigmas` as optional widgets, so a saved workflow keeps every value and starts with all three OFF. |

Fixed inside: align 32, 8 bit, sRGB, 24 fps, normal VAE decode. The node does not save anything: link `video` to a Save Video. Outputs: `video`, `images`, `audio`, `latent` (the refined AV latent) and `status`.

**Same models and LoRAs as the MTV (v0.0.9):** a **`Use Set New Defaults`** button sits on top of the node. It loads the Model Loader's saved set (`Set New Defaults`) into the node: diffusion model, both VAEs, the Turbo LoRA file and strength (into `lora_name` / `lora_strength`), LoRa_1-3 toggle / file / strength, and the seed with its control after generate, then reads the values back and prints a line under the button. **Clicking `Set New Defaults` on a Model Loader sends the set to every Revitalizer of the open workflow too**, and a **new** Revitalizer node starts from it. Nothing is forced when a workflow is opened (a saved Revitalizer keeps its own values), and a saved LoRA file that is not installed is left at None / OFF and reported. The text encoder and the step counts are not used here (the sigmas are), and the `lora_on` switch is not part of the set. The `status` output says whether the run's models are `same as the saved set` or `DIFFERS` (and which values).

### IronLeo78-MTV-Prompt-Generator

One node: 9 pictures + 1 video + your prompt in, the MTV prompt out. Type a short request (for example *Replace the main character of Video 1.*), pick the **Preset**, run. The node builds the picture / video batch, the frame times and the preset text, asks the LLM (ComfyUI's *Generate Text*, with the guide in `guide/Claude.Minimax.md` as the system prompt) and returns `MTV_Prompt`. The **LLM ON / OFF** switch (last widget) turns the LLM off completely: nothing is loaded or run and `MTV_Prompt` is your prompt exactly as typed, while `Pictures` still go to the MTV (handy when you write the whole MiniMax prompt yourself, or only want the picture and video loading). The LLM is unloaded afterwards so the MTV has the VRAM; the LLM settings you do not need are fixed (8192 tokens, sampling on, seed 0). No VHS needed (the video is read with PyAV). Since v0.1.21 this is the only node for it: the old 9-Images loader node and the prompt-generator subgraph are gone.

**Outputs (two wires to the MTV)**
- `Pictures`: the nine slots on one wire, original size, never cropped. Connect it to the MTV's `Pictures` input. An empty slot is skipped by the MTV. This wire only connects these two nodes.
- `MTV_Prompt`: the text for the MTV's prompt.

**Pictures**
- 3x3 thumbnail grid. Click a cell to pick from the input folder or upload; drag & drop onto a cell (extra files fill the next empty slots).
- Empty cell = **NONE**. Remove a picture with the red x, a right-click, or "NONE (remove this picture)" in the click menu.
- The LLM sees every picture cropped to fill the VIDEO frame size (the video ratio always wins). Feed 16:9 pictures and nothing is cut: a picture that is not about the video ratio gets a ✂ on its number. A picture taller than the frame is cropped top-biased (keeps heads); a wider one from the centre. The MTV gets the pictures untouched.

**Video**
- Click the video cell to pick / upload (or drop a video on it). Remove it the same ways as a picture. A video picked here also fills the MTV's `Video File` (and the other way round) and switches the MTV's **Choose Audio latent** to **Audio From Video**, the usual setting for video-to-video (change it afterwards if you want another audio source).
- `Start_From` (seconds, 0.1 steps) and `Duration` (1-20 s, default 5). The window stops at the end of the video; a `Start_From` past the end gives an error.
- Read at 24 fps. `Frame_Interval` (2 / 4 / 8 / 12, default 12) keeps every Nth frame. `Video_Size`: 512x288 / 672x384 / 896x512, crop to fill (swapped for a portrait video). A phone video filmed in portrait is turned upright (as in the MTV). The info line under the video shows the window and the frame count and turns amber when it is large.
- **Automatic sync (since v0.3.14):** when you click **Go**, **Go time** or **Latest** in the MTV's segment panel, every Prompt Generator of the workflow that has the same video (in i2v: any MTV) copies the window by itself, and says "Auto-synced: ..." under the video cell. It stays quiet when it cannot sync (for example another video). The button below stays as a fail-safe and explains why when it cannot sync. After an MTV Run the counter moves on and you still press the button (or use Go).
- **Sync from MTV**: copies `Start_From` and `Duration` of the MTV's NEXT segment (the same video file must be loaded in both). It follows the MTV's segment counter, including a position you set with Go, **whether Next Segment On Run is ON or OFF**, so you can pick any scene of a long video with Go and Sync it. The MTV's own Run agrees: with Next Segment On Run OFF it repeats the segment you chose with Go (see Next Segment On Run).

**More details (since v0.3.4 - v0.3.7)**
- **Seed** (last widget, with its *control after generate*, **fixed** by default): the same inputs give the same text; change the seed or set the control to *randomize* to get another one.
- **At most 120 video frames** go to the LLM: a longer window is thinned to 120 evenly spaced frames (first and last included) and the text gives the exact time of every frame sent and the real length.
- **Empty picture slots:** the MTV numbers `<Picture N>` by the pictures that are really sent, so the request tells the LLM which label each slot gets (for example `<Picture 2> (slot 3)`), the preset rules are rewritten with those labels, and an unused slot reads `<slot 2: not provided>`. In your own prompt, "Picture 3" means slot 3.
- **Keep LLM in RAM** (last widget, default ON since 0.4.3): ON keeps the loaded LLM in RAM between runs (about the size of its file) and only frees the GPU, so the next run starts faster; OFF unloads it after each run and gives the RAM back. Another LLM file, or switching it OFF, gives the RAM back.
- **LLM OFF** does no video decoding and reads no preset: it only loads the pictures and passes your prompt through.
- **i2v Sync:** with the Mode on i2v the Sync button becomes **Sync duration from MTV** and copies the length the MTV really renders (its `duration` padded to its frame count, for example 5 s becomes 5.17 s) into `Duration` (no video needed). The info line under the video cell says so in i2v, and in v2v it says how many frames go to the LLM (at most 120). A video loaded here is not copied to the MTV in i2v.
- **Custom Audio without a file** (MTV): the `status` output and the console now say "WARNING: ... NO song is used" instead of skipping the song silently.
- **Song setups are respected:** an MTV set to **Custom Audio with a file picked** is not switched to Audio From Video by a video load or a Mode change. A musician preset warns if no Custom Audio File is picked.
- Presets are read as UTF-8 even when the editor saved a BOM; editing `guide/Claude.Minimax.md` re-runs the node.

**What the LLM is told**
- The frame layout: the pictures first, then the frames of Video 1, the frame rate they are shown at (24 fps divided by `Frame_Interval`: 12 gives 2 FPS) and the exact time of every video frame (`frame 1 = 00:00.000, frame 2 = 00:00.500, ...`), so it copies time-stamps instead of computing them.
- **`Preset`**: picks a scenario. **1 - Replace main actor**: your prompt can be as short as "Replace the main character of Video 1" and the LLM is told to swap ONLY the main actor of Video 1 for the character of Picture 1 (all of its attributes) while keeping the scene, camera, motion, lip-sync and audio. **2 - Replace main actor and environment**: the same, and a second picture (slot 2) replaces the WHOLE environment of the scene (a living room, a desert, a street ...) while the actor's motion, lip-sync, camera and timing stay those of the video; with nothing in slot 2 it behaves like preset 1. **3 - Replace two actors and environment**: slot 1 = primary actor, slot 2 = secondary actor, slot 3 = the new environment (each optional after slot 1). The characters are matched **by gender**: the woman of the video receives the woman of your pictures and the man receives the man, whatever their role in the scene (your prompt can state another pairing explicitly, for example "Picture 1 replaces the man on the left"). Since v0.3.0 there are eight more (each in v2v and i2v, each with its suggested prompt; the slots below are the v2v ones, in i2v Picture 1 is the scene and they move up one): **4 - Replace environment only** (Picture 1 = the new place, the people stay); **5 - Restyle video** (name a style in your prompt, Picture 1 = optional style reference); **6 - Outfit swap** (Picture 1 = the clothing, the actor keeps face and body); **7 - Singer performance**, **8 - Drummer performance**, **9 - Bassist performance**, **10 - Guitarist performance** (Picture 1 = the new musician, who performs to your **Custom Audio**: the sound of the video is not used, and the MTV's **Choose Audio latent** and **Audio Stem** are set for you: Custom Audio with Vocals / Drums / Bass / Guitars, changeable afterwards); **11 - Time of day or weather** (name the condition in your prompt, no picture needed). A personal preset, **12 - IronLeo78 Mode**, is kept out of this package (it is in `.gitignore` and `.comfyignore`). `None` = no preset. **Mode v2v / i2v** (last widget, since v0.2.5): **v2v** (default) is everything above, with the video you load. **i2v** is for when you load NO video: every preset does the same job, but **Picture 1 is the SCENE** that replaces Video 1 (its place, light, framing and camera view stay), and the characters move up one slot: preset 1 = Picture 1 scene + Picture 2 new character; preset 2 = + Picture 3 new environment; preset 3 = + Picture 2 primary actor, Picture 3 secondary actor, Picture 4 environment. With no video there is nothing to copy the motion from: the action comes from your prompt (the LLM adds only natural, subtle motion if it gives none) and the time-stamps follow the **Duration** you set. The audio is up to you in the MTV (the i2v presets define no soundtrack unless your prompt mentions speech or an audio track). A loaded video is ignored in i2v. **Choosing the Mode also sets the MTV's Choose Audio latent** (since v0.2.6): **v2v** gives **Audio From Video**, **i2v** gives **MiniMax Audio**; change it afterwards if you want another source. (It does not run when a workflow is opened.) Choosing a preset (or the mode) also puts a **suggested working prompt** in the prompt box (preset 1: *Replace the main character of Video 1.*, preset 2: *Replace the main character and the environment of Video 1.*), so you see how it is meant to be used; **choosing a preset, or changing the Mode, always shows the matching example, even over text you typed** (since v0.3.1 / v0.3.2); choosing None, which has no example, never wipes text you typed. The presets are plain text files in the `presets/` folder (`# SYSTEM` part = rules added to the request, `# TASK` part = put in front of your prompt, `# PROMPT` part = the suggested working prompt): edit them or add your own `.md` file, then refresh ComfyUI.
- The chosen preset's rules and task follow the frame information in the request the LLM receives (nothing is added with `None`), then your own prompt: one node, nothing to wire for them.

**Sync from MTV (optional)**
- The button **Sync from MTV (next segment)** under the video copies `Start_From` and `Duration` of the NEXT segment the MTV will make. Nothing is asked of the backend until you click.
- Load the SAME video file here and in the MTV's Video File. The button is greyed (hover for the reason) unless a video is loaded here, an active MTV in the same graph has that same file, and the MTV has Use Video ON (or OFF with Choose Audio latent = Audio From Video).
- Duration = frames / 24 (5 s in the MTV = 124 frames = 5.1667 s); Start_From = (segment number - 1) x that. Press it again after each MTV Run. It refuses while the MTV is running or when every segment is done. An MTV duration above 20 s is clamped, with a warning.

**Saved workflows:** like the other nodes, it saves its values by name too, so a later version that moves a widget does not shift them.

## Outputs

`output/MySong/MySong_seg004_A_00001_.mp4`, a `.json` sidecar with the full prompt and settings next to every clip, and `MySong_manifest.csv` with each clip's start / end second in the song (plus `audio_stem`, `latent_file` and `conditioning_file`).

## Troubleshooting

| Problem | What to do |
|---|---|
| **Nodes missing** | The folder must sit directly in `custom_nodes/` with `__init__.py` inside it. Restart ComfyUI, press Ctrl+F5, and look in the console for an import error mentioning `ironleo78_mtv`. |
| **Import error about MiniMax H3** | Update ComfyUI: the MTV needs its core MiniMax H3 nodes. |
| **Revitalizer appears twice or errors on start** | Another copy of the Revitalizer is installed in `custom_nodes/`. Keep only one. |
| **Panel says "Segments: unknown"** | Select a Custom Audio File with Choose Audio latent = Custom Audio (or a Video File with Use Video ON). |
| **A dropdown says "None" or a model is "not found"** | Put the file in the matching `ComfyUI/models/` folder and press R. Use the Model Loader if your file names differ from the defaults. |
| **The node stops and does nothing** | You passed the last segment of the song. Use Jump, Latest or Reset in the panel. |
| **Picture does not follow the right part of the song** | Check **Audio Stem** and that **Choose Audio latent = Custom Audio**. |
| **Stem separation fails: corrupted checkpoint** | Delete the Hybrid Demucs file in `~/.cache/torch/hub/checkpoints/` and run again. |
| **Out of memory while separating or sampling** | Lower megapixels, close other GPU programs, or retry (separation retries once after unloading models). |
| **No `.latent` / `.conditioning` files** | They are only saved with **Save Latent = ON**. Look in `output/<Song>/`. A note in the `status` output says if saving failed (for example a full disk). |
| **Revitalizer list says "none found"** | Make a clip with Save Latent ON, then press R, or use the Upload button. |
| **Revitalizer: "audio latent is missing" or "conditioning not found"** | The three files of a clip must share a name and folder. Upload all three together. |
| **Revitalizer: status says `upscale: ... built in`** | The optional Minimax H3 Latent Upscaler (or its model file) is not installed, so the built-in latent resize was used. Install both for the trained upscaler. |
| **Revitalizer: out of VRAM** | Lower `megapixels`, switch Upscale OFF, or close other GPU programs. The console prints the failed step and a tip. |
| **A phone video comes out lying on its side** | Fixed in v0.1.3: the MTV and the Prompt Generator read the phone's rotation and turn the picture upright (the MTV's `status` says `turned upright`). A mirrored (selfie-flipped) video is not un-mirrored. |
| **Prompt Generator: Sync from MTV is greyed** | Hover it for the reason: usually the two nodes do not have the same video file, or the MTV has Use Video OFF. |

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## Tests (optional, no GPU needed)

```
python tests/test_phased_run.py
python tests/test_conditioning_io.py
python tests/test_stems.py
python tests/test_revitalizer.py
node   tests/test_migration.mjs
node   tests/test_sync_logic.mjs
node   tests/test_shadow.mjs
node   tests/test_panel_jsdom.mjs      # needs: npm install jsdom
```

These run against stand-ins for ComfyUI, so they need no GPU. Two more need torch, so run them with ComfyUI's own Python: `tests/test_combine_llm.py` and `tests/test_none_placeholder.py`.

License: Apache 2.0 (see `LICENSE`).

by IronLeo78
