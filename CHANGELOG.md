# Changelog

All notable changes to **IronLeo78 MTV**. The version in `pyproject.toml` (Comfy Registry) is the same as the one shown on the MTV node.

## v0.4.8

### Code only: the HTTP routes moved out of `mtv.py` (sweep item S2, block 3)
- New `routes.py` holds the segment panel and Model Loader routes (free, segments, reset, jump, loader defaults, save / reset defaults). They read the MTV's counters, defaults and "a Run is going" flag when a request arrives, so behaviour is unchanged. `mtv.py` is now about 1790 lines (from 3165 at 0.3.16).
- New test section: the seven routes had no test before; they are now checked (free refused while a Run is going, segments, jump, reset, defaults). All 14 suites pass (MTV 479 checks).

## v0.4.7

### Code only: settings and defaults moved out of `mtv.py` (sweep item S2, block 2)
- New `settings.py` (the hardcoded settings, factory defaults, route names and limits; the version number now lives here) and `defaults.py` (the Model Loader's factory and saved defaults, the overrides applied to a Run, the model-file check). Small helpers moved to `consts.py` and `core_call.py`. `mtv.py` imports every name back; `mtv.VERSION` and the other names still work.
- No widget, socket or saved value changed; `mtv_defaults.json` is read and written exactly as before. All 14 suites pass (MTV 471).

## v0.4.6

### Code only: the segment counter and file-location code moved out of `mtv.py` (sweep item S2, block 1)
- New `state.py`: where the pack keeps its data (ComfyUI/user/ironleo78_mtv), the per-song segment counters, the Jump / Reset helpers and the Guide's last frames (about 330 lines). `mtv.py` imports every name back, so nothing else changes. `VIDEO_EXTS` / `AUDIO_EXTS` moved to `consts.py`.
- No widget, socket, saved value or file location changed (the counters file and last frames are read and written exactly as before). All 14 suites pass (MTV 471).

## v0.4.5

### Code only: `_load_media` split into helpers (sweep item S1) and small tidy-ups
- The most complex function of the MTV (`_load_media`, 154 lines) is now 96 lines plus four helpers: `_custom_audio_chunk`, `_reference_pictures`, `_resized_pictures`, `_media_status_lines`. Same behaviour, same status text, same cache ids.
- Removed 15 re-exports in `mtv.py` that nothing uses, three stacked comment banners, and a counter read twice in a row.
- No widget, socket or saved value moved. All 14 suites pass (MTV 471).

## v0.4.4

### Fix: Keep LLM in RAM no longer evicts the other models from the GPU (sweep item N1)
- With the switch ON, the LLM now leaves the GPU alone (ComfyUI's `unload_model_and_clones`); the MTV / Revitalizer diffusion models stay on the GPU, so the next MTV run does not reload them. An older ComfyUI without that function, or any error, falls back to the previous way (unload everything).
- Tests: `test_prompt_generator.py` 30.

## v0.4.3

### Changed: "Keep LLM in RAM" is ON by default (Prompt Generator)
- New nodes, and saved workflows that never had the switch, now start with the LLM kept in RAM between runs (about 4 GB; the next run skips the read from disk). Switch it OFF to unload the LLM after each run. A workflow that already saved the switch keeps its own value. "Use LLM" (the LLM itself) was and stays ON by default.
- Tests: `test_prompt_generator.py` 29.

## v0.4.2

### Removed: the blue "Tip: Picture N isn't 16:9" text (Prompt Generator)
- The written tip under the picture grid is gone. The ✂ mark on a picture's number (picture will be cropped for the LLM) stays; the console still prints the tip line when a run starts.
- Browser-only change: no widget, socket or saved value moved.

## v0.4.1

### New: the video preview follows Start_From (Prompt Generator)
- The small video preview on the IronLeo78-MTV-Prompt-Generator now shows the frame where the window starts (Start_From) instead of always the first frame. It moves on every Start_From change (typing or the arrows), on the Sync button and on Auto-sync (Go / Go time / Latest). Start_From 0 still shows the first frame; a start past the end of the file shows the last moment of it. Not used in i2v (no video).
- Browser-only change: no widget, socket or saved value moved. Tests: `test_generator_jsdom.mjs` section 5.

## v0.4.0

### Speed, cleanup and fixes (from the 0.3.16 sweep)
- **Video frames:** the Prompt Generator now decodes (resizes and converts) only the frames that go to the LLM (at most 120) instead of every frame of the window and thinning afterwards. Same frames, same text; less time and memory on long windows. A window longer than the file is re-picked for the real frame count.
- **Keep LLM in RAM:** up to two LLM files stay kept (least recently used is dropped), "Use LLM OFF" always clears the kept model, toggling the switch no longer re-runs the node, and the console line says "left the GPU (kept in RAM)".
- **Code:** `mtv.py` is smaller: three blocks moved into `core_call.py`, `naming.py`, `media_decode.py` and the shared constants into `consts.py` (all names still reachable as before). The two identical unload functions are one.
- **Notes:** the invisible BOM characters in the changelog and dev notes are gone, and the build script strips them.
- No widget, socket or saved value moved. Tests: MTV 471, generator 28, video decode 65, sync 24, migration, shadow 16, jsdom panel and generator.

## v0.3.16

### New: "Keep LLM in RAM" switch (Prompt Generator)
- New last widget on the IronLeo78-MTV-Prompt-Generator, default OFF (nothing changes unless you switch it on). ON: the loaded LLM stays in RAM between runs (about the size of its file, several GB) and only leaves the GPU, so the next run skips the read from disk. The console prints "LLM reused from RAM".
- The kept model is keyed by LLM file name + file date: choosing another LLM or replacing the file loads fresh. Switching the option OFF (or turning "Use LLM" OFF without keeping) drops the kept model and gives the RAM back.
- Saved workflows load unchanged (the widget is appended after Seed). Tests: `test_prompt_generator.py` 25.

## v0.3.15

### Cleanup (quick wins of the optimisation list)
- Removed a dead browser function (`applyModeAudio`, replaced by the preset / Mode logic in 0.3.0); its test now uses the real code path.
- README: a stale sentence about the old `LLM_Frame_Info` output is fixed.
- No widget, socket or saved value moved. Tests: ``test_sync_logic.mjs`` 24.

## v0.3.14

### Added: the Prompt Generator syncs itself when you jump
- Clicking **Go**, **Go time** or **Latest** in the MTV's segment panel now makes every Prompt Generator of the workflow copy the MTV's window by itself (Start_From and Duration of the chosen segment; in i2v the padded duration), so it is already synced. A line under the video cell says `Auto-synced: segment N of M (...)`.
- It stays quiet when it cannot sync (another video loaded in the two nodes, no MTV): the **Sync from MTV** button is kept as a fail-safe and still explains why. A refused jump (out of range) syncs nothing. **Reset** and an MTV Run do not trigger it yet.
- No widget, socket or saved value moved. Tests: the two jsdom tests (+7 checks). Not run in a live ComfyUI.

## v0.3.13

### Tests (open items of the 0.3.10 list, pack 3): the Prompt Generator's browser code
- A new test, ``tests/test_generator_jsdom.mjs``, runs the Prompt Generator's web code in a real DOM (jsdom) with ComfyUI stubbed, and checks 17 things: the seed control starts at *fixed* for a new node and a loaded workflow keeps its own; choosing a preset fills its example over typed text and sets the MTV's Choose Audio latent and Audio Stem; the missing-Custom-Audio-File warning and pop-up; what was applied is saved with the workflow; leaving a musician preset gives the MTV settings back; the Mode swaps the example and the MTV audio; the i2v info line; the i2v Sync button copies the padded duration; a song setup survives a Mode change.
- No code change in the pack itself (the checks found nothing to fix). It is run like the other jsdom test, with jsdom installed.

## v0.3.12

### Fixed (open items of the 0.3.10 list, pack 2)
- **If the LLM stays in GPU memory after use, it is now unloaded by force.** The console line `LLM unloaded: GPU memory in use X MB -> Y MB` is unchanged; when the LLM had added more than 512 MB and less than 70 % of it went away, ComfyUI's model manager is asked to unload everything (the other models load again when needed) and a second line says so. Memory already used before the LLM is never counted.
- **Leaving a musician preset now gives back what YOU had before it.** The first musician preset remembers each MTV's Choose Audio latent and Audio Stem (saved with the workflow); choosing another preset puts those back, so a song project with the Vocals stem comes back as it was. Switching between musician presets keeps the original values, and a value you changed by hand in between is left alone. Without a remembered value it falls back to the Mode's audio and the Full stem as before.
- No widget, socket or saved value moved. Tests: ``test_prompt_generator.py`` 23, ``test_sync_logic.mjs`` 24 (extended). Not run in a live ComfyUI.

## v0.3.11

### Fixed (open items of the 0.3.10 list, pack 1)
- **The Prompt Generator's seed control now starts at "fixed" whenever the frontend creates it** (set at once, on the next tick and a little later, only for a new node; a loaded workflow keeps its own value), so the LLM no longer re-rolls on every queue by surprise.
- **The MTV's prompt box names its role even if your frontend ignores the label**: its tooltip now starts with `MTV_Prompt: the prompt, e.g. the output of the IronLeo78-MTV-Prompt-Generator`.
- **A quiet hint on the MTV's segment panel when Custom Audio is selected but no Custom Audio File is**: `audio: no Custom Audio File, no song is used` (not a warning: it is the default of a new node). It never shows for another audio mode.
- No widget, socket or saved value moved. Tests: ``test_phased_run.py`` 471, the jsdom panel test (+3). Not run in a live ComfyUI.

## v0.3.10

### Fixed: three small things from the sweep
- **The MTV no longer skips a missing Custom Audio File silently.** With **Choose Audio latent = Custom Audio** and no file picked, the `status` output and the console now say `WARNING: ... NO song is used`. The run still goes on (that setup is the default of a new node and is fine for runs without a song).
- **The amber "many frames, high VRAM" text is gone.** Only 120 frames go to the LLM, so the info line under the video cell now says how many of the window's frames are sent; in image-to-video it says the LLM writes a timeline for the Duration.
- **i2v Sync now copies the length the MTV really renders**: its frame count is padded up (5 s becomes 124 frames = 5.17 s, 7.5 s becomes 8 s), and the Prompt Generator's Duration follows that, so the timeline matches the clip. A 20 s duration stays at the 20 s maximum without a warning.
- No widget, socket or saved value moved. Tests: ``test_phased_run.py`` 470 (+3), ``test_sync_logic.mjs`` 24. Not run in a live ComfyUI.

## v0.3.9

### Changed: the MTV's prompt box is labelled MTV_Prompt
- The MTV node's **prompt** box now reads **MTV_Prompt**, the name of the Prompt Generator's output that goes in there, so the connection is obvious without instructions.
- Display only: the widget keeps its internal name ``prompt``, so saved workflows, wires and API prompts are unaffected. Tests: ``test_migration.mjs`` +1. Not run in a live ComfyUI.

## v0.3.8

### Cleanup (pack 5 of the bug list): notes, tests, imports
- Developer notes brought up to date: the file map of `DEV_NOTES` describes the real files (Prompt Generator, presets, guide, shared model cache and video reader), and `DEV_NOTES_NODES.md` is now **generated from the code** (every node's widgets in saved order, sockets, outputs, the presets) instead of describing the removed 9-Images node.
- A test now registers and calls the `/ironleo78/mtv/presets` route against a fake server (it was never exercised outside ComfyUI).
- Five unused imports removed from `model_loader.py`.
- No widget, socket or saved value moved. Tests: ``test_prompt_generator.py`` 20 (+1).

## v0.3.7

### Fixed (pack 4 of the bug list): audio switching, stems, small things
- **A song setup is no longer overridden.** When an MTV node is set to **Custom Audio with a Custom Audio File picked**, loading a video or changing the Mode no longer switches it to Audio From Video (the file is still copied). Coming back from a musician preset still restores the Mode's audio, because that Custom Audio was the preset's own setting.
- **The stem memory survives a reload**: what the last preset set (Custom Audio, Audio Stem) is now saved with the workflow, so after reopening it, choosing another preset still puts a stale stem back to Full.
- **The console tells you whether the LLM unload freed the GPU memory** (``[IronLeo78] LLM unloaded: GPU memory in use X MB -> Y MB``), so the unload can be checked on a real run.
- The MTV status line no longer says "9-Images loader" (it says Prompt Generator).
- No widget, socket or saved value moved. Tests: ``test_sync_logic.mjs`` 24 (+1), ``test_prompt_generator.py`` 19. Not run in a live ComfyUI.

## v0.3.6

### Fixed (pack 3 of the bug list): LLM OFF, frame cap, re-roll
- **LLM OFF is now really off**: it no longer decodes the video, no longer reads the preset file (so a preset without an i2v text can no longer stop an OFF run) and passes your prompt through as typed.
- **The LLM gets at most 120 video frames.** A long window (for example 20 s at Frame_Interval 2 = 240 frames) is thinned to 120 evenly spaced frames, the first and the last included; the text says so and gives the exact time of every frame that is sent, plus the real length of the clip. Shorter windows are unchanged.
- **New last widget `Seed`** (with its *control after generate*, **fixed** by default): the same inputs always give the same text, so to get another one change the seed or set the control to *randomize*. Saved workflows get seed 0 / fixed, so nothing changes for them.
- Tests: ``test_prompt_generator.py`` 18 (+3), ``test_combine_llm.py`` 36 (+1). Not run in a live ComfyUI.

## v0.3.5

### Fixed (pack 2 of the bug list): image-to-video rough edges
- **Sync works in i2v.** With Mode i2v the button becomes **Sync duration from MTV** and copies the MTV's `duration` into the Prompt Generator's `Duration` (no video needed), so the LLM writes its timeline for the clip the MTV will make. It was impossible before (Sync needed a loaded video).
- **A musician preset warns when no Custom Audio File is picked**: a line on the node and a pop-up say to pick a file in the MTV, because those presets follow that file.
- **In i2v a loaded video is no longer copied into the MTV's Video File** (the Prompt Generator ignores it, so the MTV must not use it by accident).
- No widget, socket or saved value moved. Tests: ``test_sync_logic.mjs`` 23 (+1). Not run in a live ComfyUI.

## v0.3.4

### Fixed (pack 1 of the bug list): presets and labels
- **A preset file saved with a BOM no longer loses its first section.** Older Windows Notepad saves "UTF-8 with BOM"; the reader now ignores the BOM (the guide file too).
- **Picture labels now agree when a slot is empty.** The MTV numbers `<Picture N>` by the pictures that are actually sent, but the LLM used slot numbers. Now the request says which label each slot gets (for example `<Picture 2> (slot 3)`), the preset rules are rewritten with those labels, and an unused slot reads `<slot 2: not provided>`, so it can never be mistaken for another picture. With no gap nothing changes.
- **Editing `guide/Claude.Minimax.md` now re-runs the node** (the guide file is part of the node's change check).
- No widget, socket or saved value moved. Tests: ``test_combine_llm.py`` 35, ``test_prompt_generator.py`` 15. Not run in a live ComfyUI.

## v0.3.3

### Added: a personal preset, 12 - IronLeo78 Mode (not published)
- A fixed-cast family band preset in v2v and i2v: a child who sings (lip-sync) and plays a child-size guitar, and a dad at the drums, both following the full-mix Custom Audio. Choosing it sets the MTV's Choose Audio latent to Custom Audio and its Audio Stem to **Full** (all three parts are needed). It has its own suggested prompt in each mode.
- The file is listed in `.gitignore` and `.comfyignore`: it stays on this machine and is never part of a published package.
- No widget, socket or saved value moved. Tests: `test_combine_llm.py` 34. Not run in a live ComfyUI; the output quality is untested.

## v0.3.2

### Changed: changing the Mode shows the matching example too
- Switching **v2v / i2v** now loads the example prompt of the chosen preset for that mode (the i2v example names the shifted picture slots), over text you typed, like choosing a preset does. With **None** chosen there is no example, so typed text is kept.
- The Mode's audio and the musician presets' audio / stem settings are unchanged. No widget, socket or saved value moved. Tests: `test_sync_logic.mjs` 22. Not run in a live ComfyUI.

## v0.3.1

### Fixed: choosing a Preset now always fills its example prompt
- Before, the example was only put in the prompt box when it was empty or still held an example, so a preset change did nothing once you had typed your own text. Now **choosing a Preset always fills its suggested prompt**, over your text too.
- Safeguards: changing only the **Mode** still never replaces text you typed (it only swaps an untouched example), and choosing **None** never wipes typed text (it only clears an untouched example).
- No widget, socket or saved value moved. Tests: `test_sync_logic.mjs` 22. Not run in a live ComfyUI.

## v0.3.0

### Added: eight presets, including musicians driven by your Custom Audio
- **4 - Replace environment only**: Picture 1 is the new place; the people, motion, lip-sync, camera and audio stay. **5 - Restyle video**: name a style in your prompt (anime, oil painting, film noir ...); Picture 1 is an optional style reference. **6 - Outfit swap**: Picture 1 is the clothing; the actor keeps face, hair and body. **11 - Time of day or weather**: name the condition (night, golden hour, rain, snow, fog ...); no picture needed.
- **7 - Singer, 8 - Drummer, 9 - Bassist, 10 - Guitarist performance**: Picture 1 is the new musician and replaces the singer / drummer / bassist / guitarist of the video; the performance follows your **Custom Audio** (mouth and phrasing for the singer, sticks and feet for the drummer, picking and fretting hands for the bassist, strumming and fretting for the guitarist) and the sound of the video is not used. Choosing one of these sets the MTV's **Choose Audio latent** to Custom Audio and its **Audio Stem** to Vocals / Drums / Bass / Guitars (you can change both afterwards; choosing another preset puts the Mode's audio back and the stem back to Full when it still holds the old one). You still pick the Custom Audio File yourself.
- Every preset has its image-to-video version (Picture 1 = the scene; the character or the style / outfit / environment picture moves to Picture 2; the musician presets put the performer in the scene) and a suggested working prompt. The preset list is now sorted by number (10 and 11 come after 9).
- The minor version goes to **0.3.0**. No widget, socket or saved value moved. Tests: `test_combine_llm.py` 33, `test_sync_logic.mjs` 22. Not run in a live ComfyUI; the new presets' output quality is untested.

## v0.2.6

### Changed: the Mode switch also sets Choose Audio latent
- Choosing **v2v** on the Prompt Generator sets the MTV's **Choose Audio latent** to **Audio From Video**; choosing **i2v** sets it to **MiniMax Audio** (no video, so the model makes the sound). It is a starting point: change it afterwards if you want another source. Every MTV node in the workflow is updated, only when you change the Mode (not when a workflow is opened).
- In i2v, loading a video in the Prompt Generator no longer switches the audio to Audio From Video (it only copies the file name, as before).
- Note: v2v still overrides a Custom Audio setup (bug list #2); pick Custom Audio again afterwards for song-driven work.
- No widget, socket or saved value moved. Tests: `test_sync_logic.mjs` 21 (+1). Not run in a live ComfyUI.

## v0.2.5

### Added: v2v / i2v switch for the presets
- New last widget **Mode** on the Prompt Generator: **v2v** (default, nothing changes) or **i2v** for when you load no video. In i2v every preset does the same job as in v2v but **Picture 1 is the scene** that replaces Video 1; the characters move up one slot (preset 1: Picture 2 = the new character; preset 2: Picture 3 = the new environment; preset 3: Picture 2 / 3 = the actors, Picture 4 = the environment, still matched by gender).
- No video means no motion to copy: the action comes from your prompt, with only natural subtle motion added if it gives none; the camera stays as in Picture 1; the time-stamps follow the Duration you set (instead of the frame times). The audio is left to you in the MTV: the i2v presets define no soundtrack unless your prompt mentions speech, lip-sync or an audio track.
- A video that is loaded while in i2v is ignored (not even decoded). The suggested working prompt follows the Preset AND the Mode; text you typed is never overwritten.
- Each preset file now holds both versions (`# SYSTEM / # TASK / # PROMPT` and `# I2V SYSTEM / # I2V TASK / # I2V PROMPT`); every new preset needs both. A preset with no i2v text stops with a clear message in i2v.
- No saved value moved (the widget is added last; saved workflows get v2v). Tests: `test_combine_llm.py` 30, `test_prompt_generator.py` 13, `test_sync_logic.mjs` 20. Not run in a live ComfyUI; the i2v text quality is untested.

## v0.2.4

### Added: Jump to time in the segment panel
- A second jump row, **Jump to time**: type a time in the video / song (`1:23`, `01:23.5`, `1:02:03` or `83` seconds) and click **Go time** (or press Enter). The next Run makes the segment that contains that time, so it can start up to one segment (about 5 s with the default duration) before the time you typed. The button confirms with *-> segment 17 (01:22.67)*; a time past the end says where the video ends.
- It sets the same counter as **Go**, so Next Segment ON/OFF, **Latest**, the Guide and **Sync from MTV** all work unchanged. Both ways to jump stay available.
- The panel is a little taller (room for the new row). No widget, socket or saved value moved. Tests: `test_migration.mjs` section 25 (8), the jsdom panel test passes. Not run in a live ComfyUI. (An exact start second, not snapped to a segment, is the next idea.)

## v0.2.3

### Changed (MTV): Next Segment On Run OFF repeats the segment chosen with Go
- Before, OFF always made segment 1 and Go had no effect, which removed the option to choose a scene of a long video. Now an OFF Run makes the segment set with **Go** (segment 1 until you set one) on every Run, and the counter does not move. ON is unchanged: it steps through the segments.
- A counter that is already at the end of the file (a finished session) gives segment 1 with OFF, as before. Changing the Go position makes an OFF node run again.
- The panel says *every Run repeats segment N (set it with Go)*. Sync from MTV (0.2.2) and the MTV Run now agree. The Guide still needs ON (it continues from the previous segment). Clips made with OFF now carry the real segment number in their tag.
- No widget, socket or saved value moved. Tests: `test_phased_run.py` 467 (+7, section 41), `test_sync_logic.mjs` 19. Not run in a live ComfyUI.

## v0.2.2

### Changed: Sync from MTV follows Go even with Next Segment On Run OFF
- **Sync from MTV** now takes the segment from the MTV's counter (the position you set with **Go**) whether or not Next Segment On Run is ON, so you can choose any scene of a long video. Before, with it OFF Sync always gave segment 1.
- With it OFF a short note is shown: the MTV itself will still make segment 1 on every Run (turn it ON to make the synced segment). A counter that is already at the end of the video, with it OFF, gives segment 1. With it ON nothing changed.
- The MTV's own Run is unchanged. No widget, socket or saved value moved. Tests: `test_sync_logic.mjs` 19. Not run in a live ComfyUI.

## v0.2.1

### Fixed: Sync from MTV no longer looks like it ignores Go`n- Sync copies the segment the MTV will make next. With **Next Segment On Run OFF** the MTV always makes segment 1 and ignores the Go-to position, so Sync gave segment 1 without saying why. It now shows a warning (*The MTV has Next Segment On Run OFF: it always makes segment 1 and ignores your Go-to position (segment N). Turn it ON to follow the counter*). With Next Segment ON, Sync follows the counter and your Go position, as before.
- No widget, socket or saved value moved. Tests: `test_sync_logic.mjs` 19 (+1). Not run in a live ComfyUI.

## v0.2.0

### Added: Preset 3 - Replace two actors and environment
- Slot 1 = primary actor, slot 2 = secondary actor, slot 3 = the new environment. Both actors of the video are replaced like the main actor of preset 1, and the environment like preset 2. Each of slot 2 and slot 3 is optional.
- **Gender matching:** the LLM decides the apparent gender of each pictured character and of the two people of the video and pairs them by gender, whatever looks primary or secondary in the scene (woman picture to the woman of the video, man picture to the man). If the genders do not decide it, Picture 1 replaces the most prominent person. With one person in the video, the picture whose gender matches is used. Your prompt can state another pairing explicitly (for example *Picture 1 replaces the man on the left*), which then wins. The pairing is written once in the subject definitions and kept in every shot.
- It follows the Claude Minimax guide like the other presets (`attribute_transfer` for the actors, `fully_preserved` environment and props, `fully_copy` audio, speaker IDs in the order of the vocal events, the same mandatory timeline). Suggested prompt: *Replace the two characters and the environment of Video 1.*
- The minor version goes to **0.2.0** (all 0.1.x tests passed). No widget, socket or saved value moved. Tests: `test_combine_llm.py` 28. Not run in a live ComfyUI.

## v0.1.25

### Added: LLM ON / OFF on the Prompt Generator
- New last widget **Use LLM** (ON by default; saved workflows get ON). **OFF**: the LLM is not loaded or run (so no LLM file is needed and no VRAM is used) and `MTV_Prompt` is your prompt exactly as typed. `Pictures` and the video features (shared loading, Sync from MTV, Choose Audio latent switch) work the same.
- No saved value moved. Tests: `test_prompt_generator.py` 11 (+1). Not run in a live ComfyUI.

## v0.1.24

### Added: a suggested working prompt for every preset
- Choosing a **Preset** on the IronLeo78-MTV-Prompt-Generator now fills the prompt box with a simple working prompt that fits it: preset 1 *Replace the main character of Video 1.*, preset 2 *Replace the main character and the environment of Video 1.* Changing the preset changes the suggestion; **None** clears it. The box is only filled when it is empty or still holds a suggestion: your own text is never overwritten.
- The suggestion is the new `# PROMPT` part of a preset file (every preset has one; it is not sent to the LLM by itself). The node reads them through a new route, `/ironleo78/mtv/presets`.
- No widget, socket or saved value moved. Tests: `test_combine_llm.py` 28 (+3), `test_sync_logic.mjs` 18 (+1). Not run in a live ComfyUI.

## v0.1.23

### Changed: Preset 2 is now 'Replace main actor and environment'
- The placeholder preset is replaced by **2 - Replace main actor and environment**: the main actor is replaced by the character of Picture 1 exactly like preset 1, and the **whole environment of the scene is replaced by the place shown in Picture 2** (a living room, a desert, a street ...), seen from the camera views of the video, with its own light on the actor. The motion, actions, lip-sync, camera, timing and audio stay those of the video. Without a Picture 2 it behaves like preset 1.
- It follows the Claude Minimax guide: the environment is a `<Subject 2>` that cites Picture 2 (no line of its own for the picture), kept `fully_preserved`; the actor is `attribute_transfer`; props the actor holds stay; the audio stays `fully_copy`; same mandatory timeline as preset 1.
- **Saved workflows that had the old 'Preset 2 - Placeholder' selected** must pick the new entry again. Preset 1 is unchanged. No widget, socket or saved value moved. Tests: `test_combine_llm.py` 25. Not run in a live ComfyUI.

## v0.1.22

### Changed: loading a video sets Choose Audio latent = Audio From Video
- Picking, uploading or dropping a video in the Prompt Generator, or picking one in the MTV's Video File, now sets the MTV's **Choose Audio latent** to **Audio From Video** (it used to stay on whatever it was, and forgetting it was easy). Change it afterwards if you want another source: it is only touched when a video is loaded.
- Removing a video or choosing None leaves it alone. Opening a saved workflow changes nothing.
- No widget, socket or saved value moved. Tests: `test_sync_logic.mjs` 17 (+1). Not run in a live ComfyUI.

## v0.1.21

### Removed: the legacy loader node and the prompt-generator subgraph
- The standalone **IronLeo78 9-Images-to-batch-to-LLM** node and the **IronLeo78-MTV-LLM Prompt Generator** subgraph (`subgraphs/` folder) are gone from the pack. The **IronLeo78-MTV-Prompt-Generator** does everything they did (pictures, video, frame times, presets, the LLM) and has two outputs: `Pictures` and `MTV_Prompt`.
- A saved workflow that still contains the removed nodes shows them as missing (red) nodes: replace them by the Prompt Generator and wire its two outputs to the MTV. Sync from MTV and the shared video loading work with the Prompt Generator only.
- Nothing else moved: no widget, socket or saved value of the MTV, Model Loader, Revitalizer or Prompt Generator changed. Tests: `test_phased_run.py` 460 (the pack registers four nodes), `test_prompt_generator.py` 10, `test_sync_logic.mjs` 16; `test_subgraph_blueprint.py` removed. Not run in a live ComfyUI.

## v0.1.20

### Removed (MTV): the nine legacy Picture_1 … Picture_9 inputs
- The MTV node now has only two optional inputs: `models` and `Pictures` (the one wire from the IronLeo78-MTV-Prompt-Generator). Clean node.
- **This means the old 9-Images loader node (and the subgraph) can no longer feed pictures to the MTV.** Use the IronLeo78-MTV-Prompt-Generator for that. The loader node's `Picture_n` outputs remain for previews and other nodes.
- Old workflows: a Picture_n socket with no wire is removed on load; one that still has a wire stays and keeps working. API prompts that still send `Picture_n` are honoured. No saved widget value moved.
- Tests: `test_phased_run.py` 460, `test_migration.mjs` section 24 (+3). Not run in a live ComfyUI.

## v0.1.19

### Changed: one wire for the nine pictures
- The **IronLeo78-MTV-Prompt-Generator** now has two outputs: `Pictures` (all nine slots on one wire) and `MTV_Prompt`. The **MTV** node has a new optional input `Pictures` (the last optional socket: nothing saved moves). Connect those two and the MTV processes the nine pictures exactly as before; empty slots stay empty.
- A `Picture_1` … `Picture_9` input that is also connected takes precedence for its slot, so old workflows and the loader node work as ever.
- The `Pictures` wire is a special type: it only connects between these two nodes (use the loader node's `Picture_n` outputs for previews or other nodes).
- Tests: `test_phased_run.py` 460 (+6, section 40), `test_prompt_generator.py` 10. Not run in a live ComfyUI.

## v0.1.18

### Added: IronLeo78-MTV-Prompt-Generator, the all-in-one node
- A new node, **IronLeo78-MTV-Prompt-Generator**, puts the 9-Images loader and the prompt generator in one: same pictures / video / Start_From / Duration / Frame_Interval / Video_Size / Preset widgets and the same thumbnail UI, plus your `prompt` and the `LLM` file. Outputs: `Picture_1` to `Picture_9` (to the MTV pictures) then `MTV_Prompt` (to the MTV prompt).
- It runs ComfyUI's own *Generate Text* with `guide/Claude.Minimax.md` as the system prompt and the frame times + preset + your prompt as the request, then unloads the LLM. Fixed: LLM type, 8192 tokens, sampling on (temperature 0.7, seed 0).
- The old loader node and the subgraph blueprint are unchanged. Loading a video in the MTV or in either loader still fills the others.
- No saved value of an existing node moved. Tests: `test_prompt_generator.py` 10 (LLM stubbed), `test_sync_logic.mjs` 16. **The real LLM call has not been run.**

## v0.1.17

### Changed: one text wire for the prompt generator
- The two preset outputs added in v0.1.15 (`LLM_Preset_System`, `LLM_Preset_Task`) are gone: the chosen preset now travels inside the single `LLM_Frame_Info` output (frame layout and times first, then the preset rules and task). The generator subgraph has only `image_1`, `frame_info` and `prompt` again: **two wires** from the loader (`Output_To_LLM` and `LLM_Frame_Info`).
- Inside the generator the preset rules now reach the LLM in its request (before your prompt) instead of its system prompt; the system prompt is the Claude guide alone.
- If you wired the 0.1.15 / 0.1.16 outputs, remove those two wires. This one-text structure is kept from now on. No saved widget value moved. Tests: `test_combine_llm.py` 26, `test_subgraph_blueprint.py` 10. Not run in a live ComfyUI.

## v0.1.16

### Fixed: time-stamps in the generated prompt
- The LLM was asked to compute the time-stamps from the frame rate and often skipped them (a single `[Shot 1]` with no timing). `LLM_Frame_Info` now lists the exact time of every video frame (`frame 1 = 00:00.000, frame 2 = 00:00.500, ...` for the chosen `Frame_Interval`) and the total length, in the guide's `MM:SS.mmm` format.
- Preset rule 8 (both presets) now makes the timeline mandatory: copy the listed times, give an `At MM:SS.mmm, ...` action for every visible change from the first to the last frame, and do not call a shot static or the mouth closed unless the frames show it.
- No widget, socket or saved value moved. Tests: `test_combine_llm.py` 25 (+1). Not run in a live ComfyUI.

## v0.1.15

### Added: scenario presets for the prompt generator
- New widget **`Preset`** on the 9-Images loader (added last: saved workflows keep every value and get `None`) and two new last text outputs, `LLM_Preset_System` and `LLM_Preset_Task`.
- **1 - Replace main actor**: with a prompt as short as *Replace the main character of Video 1*, the LLM is instructed to rewrite Video 1 shot by shot with ONLY the main actor swapped for the character of Picture 1 (face, hair, skin, build, clothing, accessories), keeping the scene, camera, motion, actions, lip-sync, timing and the original audio. **2 - Placeholder (copy of 1)** is the same text, for the next scenarios.
- The presets are text files in `presets/` (`# SYSTEM` / `# TASK`); edit or add files freely.
- **Changed (prompt generator subgraph):** the LLM now really RECEIVES the frame information and the preset: system prompt = Claude guide + preset system text; request = frame info + preset task + your prompt. Before, the frame-rate text was only glued in front of the LLM's answer, so the LLM never saw it, and that text no longer appears in the final prompt (the output is the LLM text alone). The subgraph has two new inputs, `preset_system` and `preset_task`.
- No saved value moved. Tests: `test_combine_llm.py` 24 (+5), `test_subgraph_blueprint.py` 11. Not run in a live ComfyUI.

## v0.1.14

### Added: the prompt generator ships with the pack
- The **IronLeo78-MTV-LLM Prompt Generator** (the subgraph that turns your short idea into a MiniMax-style prompt: Claude's Full-Reference system prompt + the LLM text generation) is now part of the pack, in `subgraphs/IronLeo78-MTV-LLM Prompt Generator.json`. ComfyUI lists it under the subgraph blueprints of the node library; add it like a node. It updates with the pack.
- Inputs: `image_1` (the loader's `Output_To_LLM`), `frame_info` (the loader's `LLM_Frame_Info`), `prompt`. Output: the final MTV prompt text.
- Delete any old copy of it in your own library to avoid two versions. No widget, socket or saved value of a node moved. New test `tests/test_subgraph_blueprint.py` (6 checks). Not run in a live ComfyUI.

## v0.1.13

### Added (9-Images loader): LLM_Frame_Info text output
- A new **last** output, `LLM_Frame_Info` (STRING), tells the LLM how its image batch is laid out, built from the node's own settings: the filled reference pictures first (named, in order), then the frames of Video 1 and the frame rate they are shown at (24 / **Frame_Interval**: 12 gives 2 FPS, 8 gives 3, 4 gives 6, 2 gives 12). Example: `The first 1 image is the reference picture (Picture 1, in this order), followed by the 120 frames of Video 1, which is shown at 2 frames per second (one frame every 0.5 s). Video 1 is sampled at 2 FPS, so take it into account when making the time-stamps.`
- Wire it into the prompt generator instead of typing the frame-rate text by hand. The two example workflows are updated in `IronLeo78-MTV-LLM_TesterWorkflow_0.1.13.json` and `IronLeo78-MTV-LLM_0.1.13.json`: the subgraph has a new `Frame_Info` input that replaces the hand-typed text node.
- No widget, socket or saved value moved (the new output is added at the end, so existing links keep working). Tests: `test_combine_llm.py` 19 (+3). Not run in a live ComfyUI.

## v0.1.12

### Added: load a video once
- Picking, uploading or dropping a video in the **9-Images loader** now puts the same file in the **MTV's Video File**, and the other way round. Several nodes of the other kind all get it, subgraphs included.
- Only a real file is copied: choosing None or removing the video in one node leaves the other alone. Nothing happens when a workflow is opened.
- A freshly uploaded file is added to the MTV's list at once, no refresh needed.
- The French README (`README_fr.md`) is removed; only `README.md` is kept from now on.
- No widget, socket or saved value moved. Tests: `test_sync_logic.mjs` +1. Not run in a live ComfyUI.

## v0.1.11

### Changed (MTV): "Choose Audio latent" sits right under "Video File"
- New order: `Turbo`, `Use Video`, `Video File`, **`Choose Audio latent`**, `Custom Audio File`, `Audio Stem`, `megapixels`, `duration`, `Next Segment On Run`, `prompt`, `Save Latent`, `Guide` (it was after `prompt`).
- Saved workflows keep every value: a workflow saved with v0.0.9t or later is restored **by name** (its named copy); an older one is put in the new order by the new migration `migrateMakerPositional` (recognised by what the values are, never by counting).

### Added (Model Loader): Turbo LoRA strength
- New widget **`turbo_lora_strength`** right under `turbo_lora_name` (-100 to 100, default 1.0, the value that was hardcoded until now). Only used while the MTV's Turbo is ON. It is part of **Set New Defaults** / **Factory**, and a saved set puts it into the Revitalizer's `lora_strength`.
- Saved Model Loaders keep every value (named copy, or the positional migration: 1.0 is inserted after the Turbo LoRA file).

### Changed: new default values (the tuned set "20261030-1007pm")
- These are what a **new** node starts with, and what **Factory** on the Model Loader gives back. Saved workflows keep their own values.
- **MTV:** `Save Latent` ON (was OFF). A prompt that sends no Save Latent value at all (older than v0.6) still saves no latent files.
- **Model Loader / built-in set:** Turbo steps **6** (was 4), Turbo OFF steps **30** (was 40), LoRa_1 file **None** (was H3_Unlocked_V2), LoRa_1-3 strength **1.0** (was 0.65). Models, seed 1978 and "fixed" unchanged.
- **2in1 Revitalizer:** `lora_on` ON, `upscale_model` `h3_upscaler_sharpness_2000steps_v0.1_fp32` (when installed), `megapixels` 0.4 (was 1.2), `temporal_chunking` OFF, `force_unload` OFF, `seed` 1978 (was 0), `sampler_name` res_multistep (was euler), LoRa_1-3 strength 1.0.
- **9-Images:** `Frame_Interval` 12 (was 2).
- Tests: `test_phased_run.py` and `test_revitalizer.py` updated to the new defaults / order (+ Turbo strength checks); `test_migration.mjs` new sections 11b, 22, 23 (the user's own 0.1.10 workflow, with and without its named copy, through the real hooks). Not run in a live ComfyUI.

## v0.1.10

### Changed (MTV): your counters, saved set and Guide frames live outside the pack folder
- The segment counters (`mtv_state.json`), the saved set of **Set New Defaults** (`mtv_defaults.json`) and the Guide's last frames (`mtv_last_frame*.png`) were written **inside the pack folder**, so replacing the folder for an update (or a Manager / Registry update) could wipe them.
- They now live in **`ComfyUI/user/ironleo78_mtv/`**. On the first start of this version, the files an older version left in the pack folder are **moved** there automatically (a file already at the new place is never overwritten).
- **For this one update:** copy the new pack OVER the old folder (or keep those files) so they can be moved; after that, replacing the pack folder is safe.

### Changed (MTV): Next Segment On Run OFF leaves the counter alone
- A Run with **Next Segment On Run OFF** always makes segment 1, but it also set the song's counter to 1, which lost a Jump position (Latest could bring it back). Now an OFF Run does not touch the counter (nor the Guide's saved frame).
- No widget, socket or saved value moved. Tests: `test_phased_run.py` section 39 (8 checks). Not run in a live ComfyUI.

## v0.1.9

### Fixed: five small ones
- **Revitalizer:** `lora_strength` (the Turbo slot) now allows -100 to 100, like `LoRa_1` - `LoRa_3` (it stopped at -10 / 10). Only the range changed; saved values stay as they are.
- **Revitalizer:** an upload that breaks off (tab closed, disk full) no longer leaves a half-written `.tmp` file in `input/ironleo78_revitalizer/`.
- **MTV + 9-Images panels:** no more polling while the browser tab is hidden (the MTV panel asked the backend for the segment info every few seconds, the 9-Images node re-checked the Sync button twice a second). They pick up again as soon as you come back to the tab.
- **9-Images:** **Sync from MTV** now finds the MTV node anywhere in the workflow, inside subgraphs too (it only looked at the loader's own graph level).
- **Audio Stem:** two different songs whose names clean to the same text (`song.wav` and `song.mp3`, or `My Song!.wav` and `My Song?.wav`) no longer replace each other's stems, which made Demucs run again on every switch. The second one gets its own folder, `output/<Song>_<8 characters>/stems/`; the first keeps its folder, and an edited version of the same file still replaces its own stems.
- No widget, socket or saved value moved. Tests: `test_stems.py` +6, `test_revitalizer.py` +4, `test_sync_logic.mjs` +3; the panel test now runs as a visible tab (jsdom `pretendToBeVisual`). Not run in a live ComfyUI.

## v0.1.8

### Changed (MTV node): one segment counter per song
- Until now there was **one** segment counter for every MTV node and every song: switching to another song continued at the old song's segment, and going back meant using Jump.
- Now each **Custom Audio File** (or, without one, each **Video File**) keeps its own counter, its own "Latest" point and its own saved last frame for the Guide. Switch songs freely: each one remembers where it was.
- The panel names the counter it shows (`counter: MySong.wav`; `shared` when no file is selected), and **Reset**, **Jump** and **Latest** act on that song only. Two MTV nodes on the same song share its counter. The 9-Images node's Sync from MTV follows the song's counter too.
- **After updating:** the first song you run continues from the old single counter (nobody loses their place); every other song starts at segment 1.
- No widget, socket or saved value moved. `mtv_state.json` keeps the old layout for the shared counter and adds a `songs` section. Tests: `test_phased_run.py` section 38 (22 checks), the panel test (jsdom) run again. Not run in a live ComfyUI.

## v0.1.7

### Changed (2in1 Revitalizer): the third-party upscaler node is optional
- The Revitalizer's upscale step needed the third-party **Comfyui_Minimax_h3_latent_Upscaler** node and its model file; without them you had to switch Upscale OFF (and a missing model file stopped the run with an error).
- Now, when that node or its model file is missing, the Revitalizer **resizes the video latent itself** to the chosen megapixels (each frame on its own, keeping the clip's shape, sides in multiples of 32 pixels), and its refine pass, which starts from heavy noise, redraws the detail. When the node **and** a model file are installed, its trained upscaler is used exactly as before.
- The `status` output says which one ran, for example `upscale: 1.2 MP built in: latent resized to 1504x800 (the Minimax H3 Latent Upscaler node is not installed)`.
- The trained upscaler still gives the best result: it cleans the resized latent up before the refine. The built-in resize is the same first step without that clean-up.
- ComfyUI's own "Load Latent Upscale Model" cannot load the H3 upscaler files (their format is not one it knows), so there was no core node to switch to.
- No widget, socket or saved value moved (only tooltips changed). Tests: `test_revitalizer.py` section 10 (8 checks), new `tests/test_latent_resize.py` (12 checks with real torch). Not run in a live ComfyUI.

## v0.1.6

### Changed (MTV + 9-Images): one video reader for both nodes
- The MTV and the 9-Images loader each had their own copy of the code that reads a window of a video (timing at 24 fps, seeking, repeating frames of a slower video, the end of the file, the phone rotation). It now exists once, in `video_reader.py`; each node keeps only its own resize.
- **Same frames as v0.1.5**, checked frame by frame on real videos (30, 25, 12 and 60 fps, portrait, a phone rotation, three MTV segments each, four 9-Images windows each with seeks, intervals and the end of the file): difference 0.
- **Fixed on the way (9-Images):** with a video file whose first frame is not at time 0 (some cameras and editors write such files), the 9-Images node counted time from the raw timestamps while the MTV counts from the start of the file, so a **Sync from MTV** window could show other frames (half a second off in the test file) than the MTV's segment. Both now count from the start of the file. A frame without a timestamp is now placed one frame after the previous one, as in the MTV, instead of being skipped.
- No widget, socket or saved value moved. Tests: `tests/test_video_decode.py` 61 checks (10 new on the reader: which source frame lands where, seek, interval, a fractional start, a slower video, the end of the file, a late-starting file for both nodes). Not run in a live ComfyUI.

## v0.1.5

### Faster, less memory (MTV + 2in1 Revitalizer): one shared copy of the diffusion model
- **MTV:** changing a LoRA, a LoRA strength or the Turbo switch used to load the whole diffusion model **from disk** again (minutes with the big H3 model), and up to **two full copies** stayed in RAM. Now the model file is read **once**: a LoRA change only applies the LoRAs again on top of it, and the two kept combinations share the same weights. The LoRA files themselves are kept too (up to 4: the Turbo LoRA + LoRa_1-3).
- **MTV + Revitalizer together:** both nodes now use the **same** copy of the model instead of one each (they load the same file). In a workflow with both, the model sits in RAM once.
- Switching to **another** model file drops everything built on the old one **before** the new file loads, so two big models are never in memory at once.
- The Revitalizer's `status` says `diffusion model: already in memory (shared with the MTV / an earlier run)` when the file was not read again.
- New shared file `model_cache.py`. No widget, socket or saved value moved. Tests: `test_phased_run.py` section 37 (11 checks, one of them across both nodes), `test_revitalizer.py` (+6). Not run in a live ComfyUI.

## v0.1.4

### Faster (2in1 Revitalizer): the model and the VAEs stay loaded between runs
- Until now every Revitalizer run loaded the diffusion model, its LoRAs and both VAEs **from disk again**, even when you only changed the seed or the sigmas.
- Now the model (with its LoRA chain and attention backend) and the two VAEs are **kept** after a run. The next run loads again only what changed: another model or VAE file (or the same name replaced on disk), a LoRA switched ON / OFF, another LoRA file or strength, another attention backend. A LoRa_n that is OFF never counts.
- The old model is dropped **before** a new one loads, and at most one model and two VAEs are kept, so memory does not pile up.
- The `status` output says `model: kept from the previous run` / `VAEs: kept from the previous run`.
- Deleting the last MTV node (which frees the MTV's models) frees the Revitalizer's too. A workflow with only the Revitalizer keeps them until ComfyUI restarts.
- No widget, socket or saved value moved. Tests: `test_revitalizer.py` section 9 (17 checks). Not run in a live ComfyUI.

## v0.1.3

### Fixed (MTV node + 9-Images node): phone videos filmed in portrait came out lying on their side
- A phone stores a portrait video as a landscape picture plus a "display rotation". The MTV only read the old `rotate` tag, which current FFmpeg (the one inside ComfyUI) no longer fills, and the 9-Images node ignored rotation entirely: such clips were sent to the model **sideways**, and the 9-Images node also picked the landscape `Video_Size` for them.
- Both nodes now read the rotation that the video library reports for each frame and turn the picture upright (any multiple of 90 degrees: portrait either way, or upside down). The 9-Images node chooses portrait / landscape from the size **as shown**. The old tag is still read as a fallback on an older ComfyUI.
- The MTV's `status` output says so: `resolution: 320x608 | turned upright (270 degrees: phone video)`.
- New shared file `video_orientation.py`. Not handled: a mirrored (selfie-flipped) video stays mirrored.
- No widget, socket or saved value moved. Tests: `tests/test_video_decode.py` 51 checks, now with real videos carrying a display rotation (-90, 90, 180, none). Checked against FFmpeg's rotation convention, **not yet with a clip from a real phone**: please try one.

## v0.1.2

### Fixed (MTV node): no more shimmering edges in the reference video
- With **Use Video ON**, each frame is shrunk to the working size (a 1920 px wide video goes down to about 600 px). The resize skipped most of the source pixels, so fine detail (hair, fabric, grilles, text) turned into jagged edges that jump around from one frame to the next, and that shimmer went to the model as part of the reference. The resize now uses **antialias** (every source pixel counts), as the `Picture_n` inputs already did.
- Measured on a test pattern of one-pixel stripes shrunk 1920 → 608 px: before, harsh stripes (spread 0.348); now, an even grey (spread 0.006), and the same stripes moved by one pixel give nearly the same frame (no flicker).
- **Visible change:** shrunk videos look slightly softer and calmer than in 0.1.1 (mean pixel change about 1-2 % on the test videos). A video that is **enlarged** (smaller than the working size) or already the right size keeps exactly the same pixels.
- No widget, socket or saved value moved. Tests: `tests/test_video_decode.py` now 35 checks. Not run in a live ComfyUI.

## v0.1.1

### Fixed (MTV node): a video segment no longer needs gigabytes of memory
- With **Use Video ON**, the MTV used to decode the whole segment at the video's full size, turn it into 32-bit floats, and only then crop and shrink it to the small working size (0.2 MP by default). Measured on a 5 s segment (124 frames): **about 4 GB of RAM for a 1080p video and about 15 GB for a 4K one**, enough to crash ComfyUI on many PCs.
- Now each frame is cropped and shrunk **as soon as it is decoded**, so only the small frames are kept: **about 0.8 GB (1080p) and 1.2 GB (4K)** for the same segment, and the decoding is faster (1080p 0.61 s → 0.42 s, 4K 2.09 s → 1.36 s).
- **The frames are exactly the same as before** (checked pixel by pixel on real encoded videos: 1080p, a second segment after a seek, portrait, a small video made bigger, a video already at the target size, a video shorter than the segment). No widget, socket or saved value moved.
- Tests: new `tests/test_video_decode.py` (27 checks, real videos; needs ComfyUI's Python). Not run in a live ComfyUI.

## v0.1.0

### Added: the 9-Images-to-batch-to-LLM loader is part of the pack
- The node **IronLeo78 9-Images-to-batch-to-LLM** (9 pictures + 1 video with thumbnails, one batch for a vision LLM, `Picture_1` … `Picture_9` for the MTV, Sync from MTV) was a separate pack, `ComfyUI-IronLeo78-9Images` (last version v0.0.2e). It now ships inside IronLeo78 MTV: `nine_images.py`, `web/ironleo78_9images.js`, `web/il78_sync_logic.js`, `web/il78_shadow.js`, and its tests in `tests/`.
- **Same node id** (`IronLeo78_9ImagesToBatchToLLM`) and display name: saved workflows load as before, values and links included.
- **Delete the old `ComfyUI-IronLeo78-9Images` folder from `custom_nodes/`** when you install this version. With both installed, the node is registered twice (two thumbnail grids on one node).
- It moved from the menu **IronLeo78** to **IronLeo78 > MTV**, next to the other three nodes (the menu place is not saved in workflows).
- Behaviour unchanged from its v0.0.2e: NONE pictures skipped by the MTV, values also saved by name, faster video decode, IS_CHANGED without reading the pictures.

### Changed: version 0.1.0
- One version for the whole pack: `pyproject.toml`, `__init__.py`, `mtv.py` (`VERSION`, the node shows **IronLeo78 MTV (v0.1.0)**), the READMEs.
- The Revitalizer's own internal label ("v0.4" in its status) is unchanged.
- No widget, socket or saved value moved in any node. Tests: `test_phased_run.py` section 36 (four nodes registered, ids, category, one version, web files, shared NONE mark name), every suite run from the merged pack: 406 / 18 / 23 / 90 / migration / 12 / 16 / 11 / 16. Not run in a live ComfyUI.

## v0.0.9

### Fixed (quick fixes, build 0.0.9w)
- **Segment numbers count from 1 everywhere.** The status lines (`Video ON | segment …`, `custom audio chunk: segment …`, `video audio only …`) and the header with Next Segment On Run OFF used to say `segment 0 … next: 1` while the panel and the header said segment 1. Now: `segment 1 | next: segment 2`; with Next Segment On Run OFF just `segment 1` (every Run makes segment 1, so there is no "next").
- **Set New Defaults / Factory now re-run the MTV** on the next queue even when nothing else changed (the saved set's file is part of the node's change check). Before, ComfyUI could reuse the previous result.
- **The clip's `.json` sidecar** says `"models_source": "saved defaults"` when the saved set was used (it said `"hardcoded"`).
- **Revitalizer:** the node's name headed its `status` text twice; now once.
- No widget, socket or saved value moved. Tests: `test_phased_run.py` section 35 (9 checks), `test_revitalizer.py` +1. Not run in a live ComfyUI.

### Fixed (MTV node): an empty slot of the 9-Images loader is no longer sent as a reference
- The IronLeo78 9-Images loader outputs a grey **NONE** picture on `Picture_N` when that slot is empty. Wired into the MTV's `Picture_N` input, it was sent to the model as a real reference and shifted every `<Picture n>` number after it. The MTV now treats it as an **empty socket**: skipped, not counted, and named in the `status` output (`empty slots skipped (NONE picture from the 9-Images loader): Picture_3`).
- Recognised by the mark the loader (v0.0.2d) puts on its NONE pictures, or, when another node copied the picture on the way, by its look (512x512, grey corners, lighter border). A real picture is never skipped.
- No widget, socket or saved value moved. Tests: `test_phased_run.py` section 34 (8 checks), new `tests/test_none_placeholder.py` (12 checks with the REAL loader picture; needs ComfyUI's Python, skips itself without torch or without the loader next to the pack). Two old `;` in `test_phased_run.py` section 29 split into separate lines (Registry E702). Not run in a live ComfyUI.

### Added (Revitalizer): the node keeps a named copy of its values
- Like the Model Loader and the MTV node, the Revitalizer now writes a copy of its widget values **by name** into the workflow (`properties.ironleo78_values`, plus the widget order of the save) on every save. If a later update moves or adds a widget, the values of a workflow saved from this release on go back to **their own widgets by name** instead of shifting. The seed's **control after generate** word (`fixed` / `increment` ...) sits in the *middle* of this node's saved list, right after the seed: on a restore it is put back at that place, not at the end.
- Same widget order as at save time: nothing changes, the saved positional values are used (a value edited by hand in the workflow file stays). Workflows saved before this release hold no copy: they go through the same repairs as before (the old `filename_prefix` text becomes the default sigmas; the nine `LoRa_n` values are completed OFF / None / 0.65).
- A `LoRa_n` value the copy lacks is OFF / None / 0.65, never the Model Loader's saved set. A damaged value in the copy takes the widget's default, a copy that cannot be used is ignored. The Upload button is not part of the copy.
- JS only (`web/ironleo78_2in1_revitalizer.js`), no Python change, no widget moved. Tests: `test_migration.mjs` section 21 (30 checks, stand-in node with the control word after the seed). Not run in a live ComfyUI.

### Added (MTV node): the node keeps a named copy of its values
- Like the Model Loader, the MTV node now writes a copy of its widget values **by name** into the workflow (`properties.ironleo78_values`, plus the widget order of the save) on every save. Saved values are positional, so until now the next update that moved a MTV widget relied on position-based migrations again. A workflow saved from now on is restored **by name** whatever later updates do to the widget order: a widget the copy does not know gets its default, a value of the wrong type falls back to its default.
- When the widgets are in the same order as at save time nothing changes: the saved positional values are used (a value edited by hand in the workflow file stays). Workflows saved before this release hold no copy: they go through the same migrations as before and carry the copy from their next save on.
- No widget, socket or saved value moves; no migration to write. The workflow file grows by one small `properties` entry per MTV node. Tests: `test_migration.mjs` section 20 (the pure helpers, and the REAL `nodeCreated` / `onConfigure` / `onSerialize` of the node: moved + added widgets, hand edit, damaged copy, no copy, load + save + load). Not run in a live ComfyUI.

### Removed (MTV node): the optional `Video_1` input
- The video now comes in **only** through the **Video File** picker, as before; the optional `VIDEO` socket `Video_1` is gone, with everything that only served it: the in-memory video route (`_MemVideo` / `_PathVideo`), the cross-run cache and its 4 GB limit, the 2 GB size warning, the **Free video** button of the segment panel (and the `release_video` route, `held_bytes` in the segment info). The segment counter works from the Video File picker and the Custom Audio File as it always did.
- **Use Video ON with an empty Video File is refused at queue time again** (it was left to the Run while `Video_1` existed).
- No widget or saved value moves (`Video_1` was an optional socket, the last one). A workflow saved with a wire into `Video_1` may keep a dead socket on the node until you delete that link; the backend ignores it.
- Tests: `test_phased_run.py` 381 checks (section 27 rewritten: everything is gone, the picker rules are back; the Video_1 sections 30, 31, 34 and the release part of 32 removed), `test_migration.mjs` (section 19 rewritten). `test_panel_jsdom.mjs` updated but **not run** (no jsdom here). Not run in a live ComfyUI.

### Changed (logs): silent errors now leave a debug trace
- Six places that swallowed an error without a word now log it at **debug** level (restoring an input's hidden flag, the LoadAudio fallback, numbering a clip when the folder cannot be listed, a failed seek, the audio resampler flush, a file that vanished while the Revitalizer lists latents). Behaviour is unchanged. Four harmless ones (a speed hint, the optional progress bar, the Cancel hook outside ComfyUI, a size count in the conditioning file) stay silent on purpose and are marked so in the code. Nothing was needed for the picture edge cases ("I;16", transparent pixels): the picture file loader that had them was removed in an earlier release, pictures now come in as ComfyUI image inputs.

### Fixed (MTV node): the Guide's saved last frame is read and closed in one step
- The saved last frame (the PNG the Guide continues from) is now opened in a `with` block, so the file is closed as soon as it has been read. Before, closing depended on the garbage collector; on Windows an open handle can stop the next Run from overwriting the file. In practice recent Pillow versions close a single-frame PNG after loading it, so this was a safety fix more than a live bug. Tests: `test_phased_run.py` section 33 (no handle left, the file can be replaced right after). Not run in a live ComfyUI.

### Fixed (MTV node): a file replaced under the same name is noticed
- With **Use Video OFF** and **Next Segment On Run OFF**, ComfyUI decides whether to re-run the node from `IS_CHANGED`, which hashed only the *name* of `Custom Audio File` and `Video File`. Replacing the song or the video in the input folder under the same name was not noticed and the old result came back. It now hashes the file's name, modification time and size (the same id the other caches use). A missing file or `None` still gives a stable value.
- No widget, socket or saved value changes. Tests: `test_phased_run.py` section 32. Not run in a live ComfyUI.

### Changed (MTV node): faster cache id for the wired pictures
- The conditioning cache now identifies each `Picture_n` input from the **resized** picture (what the model actually receives) instead of the full-resolution one. Hashing a 12 MP picture took about 290 ms; its resized version about 23 ms: roughly 270 ms saved per picture and Run (up to nine pictures). A changed picture still changes the id; two different images that end up with exactly the same resized pixels now share one cache entry, which is correct because the conditioning is identical.
- No widget, socket or saved value changes. Tests: `test_phased_run.py` 383 checks (2 new in section 24). Not run in a live ComfyUI.

### Fixed (MTV node): a lock around every change of the segment counter file
- The panel buttons (jump, Latest, reset) and a Run that is finishing could both read `mtv_state.json`, change it and write it back at the same moment; the later write then put back a stale copy and could lose the other one's change (the `furthest` point or the Guide frame marker). Every read -> change -> write of the file now happens under **one lock** (`_save_index`, `_jump_to`, the Guide frame marker), and the write itself is under it too, so two writers can no longer share the temporary file either.
- The lock is held only around those few lines, never while a model runs or a picture is saved. It protects one ComfyUI process (the normal case), not two processes sharing the same folder.
- **Not changed (on purpose):** a jump made *while a Run is in progress* is still overwritten when that Run finishes and saves its own counter. That is a choice about what the counter should mean, not a file race: ask if you want a jump during a Run to win.
- No widget, socket or saved value changes. Tests: `test_phased_run.py` 381 checks (section 29: a writer waits while the lock is held, re-entrant, 150 + 150 concurrent saves lose nothing). Not run in a live ComfyUI.

### Fixed (MTV node): the segment counter file is written atomically
- `mtv_state.json` (the segment counter, the "Latest" point and the Guide frame marker) used to be rewritten in place: a crash or a kill in the middle of the write left a truncated file, which was then read as empty and **silently sent the counter back to segment 1**. It is now written to a temporary file, flushed to disk, and swapped in with `os.replace` in one step: after a crash you keep the previous, complete file. A failed write removes its temporary file and still reports the error as before. The file is read and written as UTF-8.
- No widget, socket or saved workflow value changes. Tests: `test_phased_run.py` 371 checks (section 28: a write that dies half way, a failing replace, no `.tmp` left, save / load still fine). Not run in a live ComfyUI.

### Changed (MTV node): pictures only come in through the `Picture_1` ... `Picture_9` inputs
- **Removed from the node:** the nine `Picture1-9` pickers (with their upload buttons), the **`More References`** OFF / ON switch and the **thumbnail gallery**. The nine optional `IMAGE` inputs `Picture_1` ... `Picture_9` stay and are now **always on**: every connected input is sent as `<Picture n>` (nine at most; empty inputs are skipped and the numbers count only the connected ones). The segment panel, the Video File / Custom Audio File options and every other widget are untouched.
- **No saved value moves:** the removed widgets were the last ones (right after `Guide`). The 12 remaining widgets keep their positions. A workflow saved with an older version still holds up to 10 surplus values at the end; they are cut on load (`dropOldPictureValues`, recognised by what they are) and the old tall node height is fitted once. The picture files an old workflow had picked are **not** carried over (there is nowhere to put them): wire the pictures into the inputs.
- Old API prompts that still send `picture_1..9` / `More References` are accepted: those values are ignored.
- A picture input has no file name, so with Use Video OFF and no Custom Audio File the clip folder falls back to `video/ComfyUI` (before: the Picture1 picker's file name). A Custom Audio File or a Video File still names the folder.
- Faster queueing: `IS_CHANGED` no longer reads the picture files.
- Removed code nothing used any more: `_image_files`, `_load_one_image`, `_active_slots`, `MORE_REFERENCES`.
- Tests: `test_phased_run.py` (361 checks, section 24 rewritten), `test_migration.mjs` (section 10 rewritten, new section 18: an old 22-value workflow through the real hook), `test_panel_jsdom.mjs` updated but **not run** (no jsdom here). Not run in a live ComfyUI.

### Added (MTV node): optional image inputs `Picture_1` ... `Picture_9`
- Nine optional **`IMAGE` sockets**, an alternative to the pickers: wire any image into a slot and it is used **instead of the picker of the same slot**; unwired slots keep their picker (both can be mixed). A batch gives its first image, an alpha channel is dropped, a grey image is widened to RGB. The slot's thumbnail shows `linked`.
- **Picture_4-9 still follow More References** (OFF = not sent; the status says so). The status lists which slots come from a linked input; the clip record / manifest name them `Picture_n (linked)`; the conditioning cache uses the picture's content, so a changed image is never served from the cache.
- A wired `Picture_1` with no audio / video file has no name to build the clip folder from: it falls back to `video/ComfyUI` as before.
- They are optional sockets (no widget): **no saved widget value moves, no migration**. `models` stays the first optional socket.
- Tests: `tests/test_phased_run.py` section 26 (342 checks). Not run in a live ComfyUI.

### Fixed (MTV node): thumbnails not refreshing when a new picture is loaded
- Choosing or uploading a picture now redraws that slot's thumbnail at once, **also when the file name is the same as before** (the picker callback resets the slot and adds a cache-buster, so the browser cannot serve the old image).
- One failing slot can no longer stop the other thumbnails from updating (each slot is refreshed on its own), and the lookup of the new `Picture_n` sockets is defensive.
- A picture that cannot be loaded shows `can't load` instead of a broken-image icon; names with a sub-folder or a trailing `[input]` are turned into a proper `/view` URL.

### Added (Model Loader + MTV node)
- **`Set New Defaults` button, on top of the Model Loader, above every other option.** Set the loader the way you want (models, LoRa_1-3 toggle / file / strength, steps, seed), click: **those values are saved as the new defaults** (`mtv_defaults.json` in the pack folder, written by the backend through the new route `POST /ironleo78/mtv/save_defaults`; it is git-ignored and not part of the workflow).
- **The MTV uses the saved defaults** from its next run, even with no Model Loader connected (a connected Model Loader still wins). A **new** Model Loader node starts from them too. The MTV status says `models: saved defaults (Set New Defaults)`, and a missing saved file is reported as `(saved defaults) not found`.
- **It confirms itself:** after saving, the button asks the backend for the defaults again and compares every value: `✔ New defaults saved: 17 of 17 values stored and read back from the backend` (plus a toast). `⚠` names a saved file that is not installed; `✖` says a value did not come back the same, or that nothing was saved (a refused value, e.g. steps 0, writes nothing).
- **`Factory`** (small button next to it): deletes the saved defaults and sets the widgets to the built-in values (models, LoRAs OFF at 0.65, steps 4 / 40, seed 1978, fixed), with the same read-back line.
- The button is a panel like the MTV's segment panel (not saved in the workflow), so **no saved value moves** and no migration is needed.

### Cleaned up (internal, nothing visible changes)
- Removed code nothing used any more: four helpers from the one-LoRA layout (`_lora_choices`, `_pick_default`, `_default_file`, `_with_none`), four constants (`CORE_CLIP_NODE`, `FALLBACK_ATTN_OPTIONS`, `FALLBACK_CLIP_TYPES`, `DEFAULT_PREFIX`) and an unused import in `model_loader.py`. The module docstring now says how to refine / upscale later (Save Latent ON + the Revitalizer) instead of "upscaling is not done here".

### Changed (MTV node): no audio file = a subfolder named after Picture1 (or the video)
- With **no Custom Audio File**, the clip files now go into a **subfolder named after the Picture1 file** (or after the **video file** when Use Video is ON), exactly like the song's folder: `output/<name>/<name>_seg004_A_00001_...` holds the sidecar `.json`, the latents / conditioning (Save Latent) and the manifest `<name>_manifest.csv`. The `filename` output follows (`cat/cat_seg000_A_00001_`). Before, those files went loose into the output folder with a shared `mtv_manifest.csv`. A custom audio file still wins. Nothing at all to name it after (no audio, no video, Picture1 = None) = `video/ComfyUI_...` as before.
- The Guide's read-back of the previous clip uses the same name. Changing Picture1 starts a new folder (and a new manifest) for the new name. Files made before stay where they are (no rename, no move). No widget changed: no migration.
- The headers of the `.latent` / `.conditioning` files (Save Latent) carry the same name in their `song` field (`clip_meta["project"]`).
- Test: `tests/test_phased_run.py` section 2 (320 checks).

### Changed (Model Loader + MTV node): `Set New Defaults` is now ONE set held on both sides
- **The saved set is loaded back into every Model Loader** each time it is created or a workflow is opened (a moment after the load, so it is the last word): models, LoRa_1-3 toggle / file / strength, steps, seed **and the seed's control after generate** (it is now saved with the set). Before, only a brand-new node started from the set; a loaded workflow kept its own stored values, so the loader and the MTV drifted apart. A new node gets the set right away (no page refresh needed after saving).
- **Replaced values are reported:** a line under the button (plus a toast) names what the workflow held and the set replaced (`turbo_steps 5 -> 3`), and any saved file that is not installed here (kept as it was). The values and the seed control are read back after loading.
- **The MTV status says whether both sides match:** `models: Model Loader (same as the saved set)` or `Model Loader (DIFFERS from the saved set: turbo_steps=7)`. A connected loader's live values still win for that run.
- **No saved set = nothing is forced:** a workflow keeps its own values. Changing a loader value without clicking `Set New Defaults` lasts until the next reload.
- No widget was added, removed or moved: no saved value moves and no migration is needed. The route `GET /loader_defaults` also answers `seed_control`, and `POST /save_defaults` accepts it (validated: fixed / increment / decrement / randomize).

### Changed (Model Loader)
- **Three custom LoRAs: `LoRa_1`, `LoRa_2`, `LoRa_3`** (was one `custom_lora_name`). Each one has its own **OFF / ON** toggle (`LoRa_1_enabled` ...), its file and its strength (`LoRa_1_strength` ..., default 0.65, -100 to 100). They are applied **after the Turbo LoRA, chained in this order** (LoRa_1, then LoRa_2, then LoRa_3); only the ones that are ON are applied and checked. LoRa_1 keeps the old default file (`H3_Unlocked_V2.safetensors`), LoRa_2 and LoRa_3 start empty.
- **All the custom LoRA widgets now sit right after the Turbo LoRA** (they were right under the diffusion model). Order: diffusion model, Turbo LoRA, LoRa_1 (toggle, file, strength), LoRa_2, LoRa_3, text encoder, video VAE, audio VAE, steps, seed.
- **`full_steps` now starts at 40** (was 25). Turbo ON is still 4 steps. This is also the built-in value of the MTV when no Model Loader is connected (Turbo OFF = 40 steps). A saved Model Loader keeps its own value.
- The run manifest lists `custom_loras` (the LoRAs that were ON, with slot, file and strength) instead of `custom_lora`.

### Changed (MTV node, small)
- **`duration` moves by 0.1 s** with the arrows (was 0.01). Only the step changed: same position, same default (5), same range, so saved workflows are unaffected and a saved value like 5.17 is kept as it is (it is only rounded if you click the arrows).

### Added (2in1 Revitalizer + Model Loader): LoRa_1-3 and the Model Loader's saved set
- **Three more LoRAs on the Revitalizer: `LoRa_1`, `LoRa_2`, `LoRa_3`**, each with `_enabled` (OFF), a file (`None`) and `_strength` (0.65, -100 to 100), named exactly like the Model Loader's. The model is built as: diffusion model, the existing LoRA (the Turbo slot), then LoRa_1, LoRa_2, LoRa_3 (the same order as the MTV), only the ones that are ON; a LoRa that is OFF is never checked (a saved file that is not installed does not block the run). An ON LoRa with no file is refused before the run, naming the slot.
- **Nothing moves in saved workflows:** the nine widgets are optional ones that sit after `sigmas` (the last required widget). A workflow saved before has no value for them: they come up OFF / None / 0.65 (a LoRa never switches itself ON because of the saved set), also with the Upload button's saved value in that place. An API prompt without them runs with all three OFF.
- **`Use Set New Defaults` button on top of the Revitalizer:** loads the Model Loader's saved set into the node: diffusion model, both VAEs, the Turbo LoRA file (into `lora_name`), LoRa_1-3 toggle / file / strength, and the seed with its control after generate. It reads the values back and prints a line under the button (plus a toast): green when everything took, amber for a saved file that is not installed here (a LoRa file that is missing becomes None / OFF), red when a value did not take. A panel like the Model Loader's (not saved in the workflow).
- **`Set New Defaults` on a Model Loader now also sends the set to every Revitalizer of the open workflow** (after its own read-back, if that did not fail). A **new** Revitalizer node starts from the saved set too (new route `GET /ironleo78/revitalizer/saved_set`, the set already translated to the Revitalizer's widget names). Nothing is forced when a workflow is opened. The `lora_on` switch, the text encoder and the step counts are not part of what is sent.
- **The Revitalizer's `status` says whether the models match the saved set:** `models: same as the saved set (Set New Defaults)` or `models: DIFFERS from the saved set (...)` with the values. No saved set = no line.
- Tests: `tests/test_revitalizer.py` section 8 (89 checks: widgets, defaults from the set, validation, the LoRA chain order, old API prompts, status), `tests/test_phased_run.py` (324 checks, +4: the real `mtv.py` set read by the real Revitalizer, after Factory nothing is forced), `tests/test_migration.mjs` section 16 (old workflows with / without the saved control word and the button value, the real hook incl. values assigned after it, the set applied and read back, missing files, the button's loader function, the Model Loader's event). The jsdom panel test was NOT run (no network); the DOM panel and both clicks are not exercised anywhere yet.

### Changed (2in1 Revitalizer)
- **`megapixels` now starts at 1.2** (was 2.0). The maximum is still 2.0. Only new nodes get the new default: a saved workflow keeps its own value.
- **The Revitalizer no longer saves the video** (same as the MTV): link its **`video`** output to your own Save Video node. The `filename_prefix` widget and the saved-video preview are gone, and so is the "Saving video" stage (8 stages now).
- **The sigmas are visible and editable:** a new `sigmas` text widget (last widget, where `filename_prefix` was). Default `0.9231, 0.8780, 0.8000, 0.6316, 0.3158, 0.0000` (5 steps, as before). Numbers separated by commas, going down from left to right; N numbers = N - 1 steps. A bad list is refused before the run with a plain message, and the sigmas used are listed in the `status` output.
- Workflows saved before: the old prefix text that sat where `sigmas` now is gets replaced by the default sigmas on load. Nothing else moved.

### Changed (MTV node)
- **The status box at the bottom of the node is gone** (it took space). The run report is now a third output, **`status`** (STRING), after `video` and `filename`: link it to a Preview Any / text node to read it. It holds the same text the box used to show. It is the last output, so links saved with 0.0.8 or older keep working. When every segment is done, `video` and `filename` stay blocked (a linked Save Video does not run) but `status` still says FINISHED.

### Fixed / Safety
- **Model Loader values no longer depend on the widget order.** Saved values are positional, so every update that moved a widget could load values into the wrong widgets. Now every save also stores a copy of the loader's values **by name** (with the widget order of that save). If a later update moves the widgets, the values are restored by name; if the order did not change, the normal saved values are used (so a value edited by hand in the workflow file still wins). Workflows saved before this change still go through the order-based conversion and get the copy from their next save.
- The conversion of an old saved Model Loader now rewrites the saved list in place and sets the final values once more right after the load, so it also holds when the frontend assigns the saved values after the node's hook.
- **Saved Model Loaders are converted on load.** Moving the widgets moves every saved value, so the old values are re-ordered (recognised by what they are, not by how many): a workflow saved with 0.0.8 or older keeps its models, LoRA toggle / file / strength (now LoRa_1), steps and seed. Loading the same workflow again and again never changes a value.

### Tests
- Saved set loaded on create / open: `tests/test_phased_run.py` section 11 (+7: seed control saved / refused / damaged, status says same / DIFFERS; 313 checks), `tests/test_migration.mjs` section 15 (the real hook: a workflow with steps 5 / seed 111 / randomize opens with the set's 3 / 4242 / increment, a new node gets the set, no saved set = nothing forced, no backend answer, a missing file).
- Set New Defaults: `tests/test_phased_run.py` section 11 (save, read back, the MTV runs with steps 3, a new loader starts from them, refused values write nothing, damaged file, Factory), `tests/test_migration.mjs` section 14 (what is saved = the current widget values, read-back comparison, confirmation texts, Factory), `tests/test_panel_jsdom.mjs` (the panel, both clicks; not run, see DEV_NOTES).
- The outputs / FINISHED checks of `tests/test_phased_run.py` expect the third output (279 checks).
- `tests/test_phased_run.py` section 25 (the chain order, ON / OFF, file checks), `tests/test_migration.mjs` section 11, and `tests/test_panel_jsdom.mjs` loads an old Model Loader through the real hook.

## v0.0.8

### Added
- **Six more reference pictures, Picture4 to Picture9**, with the same naming (`<Picture 4>` ... `<Picture 9>` in the prompt; the numbers still count only the filled slots, and the status box lists the mapping). MiniMax H3 takes nine reference pictures at most, so nine is the limit.
- **More References (OFF / ON)** switch, OFF by default. OFF hides the six new pickers and their thumbnails, and the thumbnail grid is one row again. ON shows them (three rows of thumbnails). **OFF also means "not sent":** a file left in Picture4-9 is ignored while the switch is OFF, and the status box says so (`More References OFF: Picture5 hold a file but are NOT sent`). A hidden slot is never checked for a missing file.
- The switch and the six pickers were added at the END of the widget list, so every workflow saved before loads as it did. Values that landed on them (an upload-button value) are repaired on load.

### Tests
- `tests/test_phased_run.py` section 24 (loading, tags, validation, change signature), `tests/test_migration.mjs` section 10, `tests/test_panel_jsdom.mjs` (nine thumbnails, hide / show). The jsdom test was run this time.

## v0.0.7

### Changed
- **duration now starts at 5 s** on a new node (it was 15 s). `megapixels` already started at 0.2 and stays there. A workflow you saved keeps its own values: only new nodes get the new default.
- **Audio Stem: "Song" is now called "Full"** (the whole mix, no separation). Same position and meaning. Workflows saved with "Song" are converted to "Full" when they load, and API prompts that still send "Song" keep working. The stem files on disk (`<Song>_Vocals.wav` ...) are not affected.

### Tests
- `tests/test_migration.mjs` section 9 (Song -> Full), `tests/test_phased_run.py` checks updated (options, default, old name accepted, new duration default).

## v0.0.6

### Fixed
- **The "Video failed to load" box at the bottom of the MTV node is gone.** ComfyUI's own frontend builds a preview from the Video File picker even when it is set to `None` (it asks the server for a file called "None", which fails). The node's script now removes that placeholder preview, for the Video File picker and for empty picture slots. **When a real video is picked, its preview is shown as before.** If you prefer no video preview at all, set `ALWAYS_HIDE_VIDEO_PREVIEW = true` at the top of `web/ironleo78_mtv.js`.
- This replaces the v0.0.5 attempt, which looked for the preview by widget name and did not match what the frontend really does.

### Tests
- `tests/test_migration.mjs` checks the new helpers (`isPlaceholderPreview`, `dropNonePreview`).

## v0.0.5

### Changed
- **The MTV node no longer saves the clip and shows no video preview.** The internal *Save Video* step is gone. Create Video's result leaves on a new **`video`** output: link it to a *Save Video* node of your choice (so you pick the format, codec and prefix).
- **Create Video stays hardcoded** (24 fps, sRGB, h264); there are no widgets for it.
- **New `filename` output** (STRING): the clip's name in the pack's usual naming, without extension (e.g. `Song/Song_seg004_A_00001_`). The number is the next free one for that name (the latent files and the `.json` count too), so a redo never overwrites anything.
- **Save Latent keeps the old naming:** `<tag>_00001_video.latent`, `_audio.latent`, `<tag>_00001.conditioning` in the song folder, now with the planned clip number. The `.json` sidecar and the manifest row also use the planned clip name (written even if no Save Video is linked).
- Both outputs are blocked (a linked Save Video does not run) when the node stops quietly after the last segment.
- The widget **Bypassed Audio Latent** is renamed **Choose Audio latent** (same position and values: saved workflows load as before; API prompts that still send the old name keep working).
- The video preview at the bottom of the node (the player added by the Video File picker) is hidden by the frontend script. Not verified in a live ComfyUI: report it if a preview still shows.
- The Guide can still read the previous clip back: if the manifest's planned file does not exist, the newest video that starts with the same stem (`<tag>_`) in that folder is used.

### Tests
- `tests/test_phased_run.py` section 23 (outputs, hardcoded Create Video settings, no SaveVideo call, blocked outputs, renamed widget, old name accepted). 251 checks pass.

## v0.0.4

### Changed
- **MiniMax Audio now works exactly like the official ComfyUI MiniMax H3 ref2v template** (`video_minimax_h3_r2v`). In that template the `LATENT` output of *MiniMax H3 Reference To Video* goes straight into the sampler and the model generates the audio itself, because the latent already holds the audio. The node now does the same: with **MiniMax Audio** nothing is trimmed, encoded, masked or concatenated, and the sampled latent is decoded by the video VAE and the audio VAE as before. (v0.0.3 built a silent audio latent with a noise mask of 1, which was a guess; that is removed.)
- A Custom Audio File or a video soundtrack is, in this mode, only sent to the model as a **reference** (use `<Audio 1>` in the prompt, as in the template). Nothing steps through the song in this mode.
- **Custom Audio** and **Audio From Video** (the bypass modes, made earlier for passing your own audio through) are unchanged.
- Tooltip, status text and both READMEs describe the three modes.

### Tests
- `tests/test_phased_run.py` section 22 now checks that MiniMax Audio calls none of the bypass nodes (trim, audio encode, mask, concat), that the MiniMax node's own latent reaches the sampler untouched, and that the bypass modes still do the full chain. 238 checks pass.

## v0.0.3

### Added
- **Audio source: MiniMax Audio / Audio From Video / Custom Audio.** The *Bypassed Audio Latent* switch on the MTV node is now a list at the same position:
  - **Custom Audio** (default): your song is cut into segments, encoded and frozen into the audio latent (noise mask 0). The model never invents sound. Same behaviour as before.
  - **Audio From Video**: the video soundtrack is bypassed the same way. Same behaviour as before.
  - **MiniMax Audio** (new again): no bypass, the model generates the sound itself (reworked in v0.0.4 to match the official template).
- Workflows saved with the old OFF / ON switch are converted when loaded (OFF -> Audio From Video, ON -> Custom Audio). API prompts that still send true / false keep working.
- The cache of encoded audio latents tells the three modes apart, and the status box says which audio mode was used.
- Tests for the three modes, the cache, the segment plan and the workflow conversion (`tests/test_phased_run.py` section 22, `tests/test_migration.mjs` section 7).

### Changed
- **Test files cleaned up for the Comfy Registry security check.** Every `a; b` line in `tests/` is now one statement per line (rule E702, which the Registry says will become an error). The code is identical: it was verified by comparing the syntax trees before and after, and all test suites still pass.
- `requirements.txt` is empty (the pack needs no pip packages) so that `comfy node init` can no longer paste its comments into `pyproject.toml`.
- Version shown on the node: **IronLeo78 MTV (v0.0.3)**.

## v0.0.2

### Fixed
- **Model Loader: steps and seed turned into "fixed" after a few loads.** The old-workflow migration decided a Model Loader was "old" by counting its saved values. ComfyUI's frontend saves one value (the *control after generate* setting) that is not listed among the widget names, so a current-format workflow was mistaken for an old one and one value was dropped at every load + save: `turbo_steps` was lost first, then `full_steps`, then `noise_seed`, until all three read `fixed` and the node reported "must be a whole number". The migration now recognises the old format by **what the values are** (an upscale model file name where a number should be), so a current workflow is never touched.
- **Same safeguard for the MTV node:** the 0.5 -> 0.6 migration of the MTV widgets also looks at the values instead of counting them, so extra saved values (such as the picture upload button) can no longer trigger it by accident.
- **Model Loader repairs damaged workflows on load:** if `turbo_steps`, `full_steps`, `noise_seed` or `custom_lora_strength` is not a number (or `custom_lora_enabled` is not ON/OFF), it is reset to the default (4 / 25 / 1978 / 0.65 / OFF) instead of raising an error. Values lost earlier have to be typed in again.
- **Revitalizer:** `megapixels` is rounded to 2 decimals before it reaches the upscaler (a saved `1.1999999999999993` is now exactly `1.2`).

### Changed
- Version shown on the node: **IronLeo78 MTV (v0.0.2)**. Node ids are unchanged, so existing workflows keep loading.
- Added regression tests for the cases above (`tests/test_migration.mjs`, sections 5 and 6).

## v0.0.1

First public pre-alpha: IronLeo78 MTV node, MTV Model Loader and 2in1 Revitalizer in one pack, Audio Stem cache, Save Latent, README in English and French, Comfy Registry metadata and publish workflow.
