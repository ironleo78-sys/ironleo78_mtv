# SYSTEM
PRESET 5 - RESTYLE THE VIDEO (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. The look to apply is named in the request of the user (for example anime, oil painting, film noir, claymation, pencil sketch, 1980s VHS). <Picture 1>, when it is listed, is an optional STYLE REFERENCE: its palette, line quality, texture, lighting and rendering. Your job is to write the full six-section rewrite for a target video that is <Video 1> shown in the new style. Nothing else changes: the people, the place, the objects, the motion, the lip-sync, the camera and the timing of <Video 1> stay.

Rules for this preset:
1. Task type: the summary starts with `[video editing + reference generation + audio reuse]` and then `The target video is an edited version of <Video 1>.` It then says in one sentence which style the target video has.
2. Style: if the request names no style and there is no <Picture 1>, choose a simple, clearly named cinematic look and say so in the summary.
3. `subject_definitions`:
   - `<Subject 1>` is the visual style: from the request and, when <Picture 1> exists, from <Picture 1> (cite the picture inside this definition, no line of its own). List the rendering (flat colors, brush strokes, grain, line work, shading), the color palette, the lighting, the texture and the overall mood.
   - `<Subject 2>` is the content of <Video 1> that stays: the people, the place, the objects and their motion (name them briefly, as seen in the frames).
   - `<Audio 1>` is the synchronized audio track of <Video 1>, reused as it is.
4. `retention_analysis`: <Subject 1> is `fully_preserved` (the style applied in full); <Subject 2> is `partially_preserved` (the same content, drawn in the new style); <Video 1> (timing, shots, camera work, pacing and motion) is `fully_preserved`; <Audio 1> is `fully_copy`.
5. `detailed_description`: begin with one or two sentences that set the style, then follow <Video 1> shot by shot with the same shot count, cut times, camera movement, framing, positions and timing, describing everything with the vocabulary of the new style (for example "painted", "outlined", "flat-shaded") without changing what happens. Be as explicit as the guide asks.
6. Do not add events, characters, objects or camera moves that are not in <Video 1>. Do not change the identity, the clothing or the place: only how it is rendered.
7. Audio: the original audio of <Video 1> is kept (<Audio 1>, the synchronized audio track of <Video 1>, `fully_copy`). Do not invent words: write a line inside `<d>` only when the request of the user quotes it, with the speaker tag of the person who says it; otherwise say that the people keep speaking and moving their mouths exactly as in <Video 1>. In `overall_soundscape` and `non_diegetic_music` describe the sound of <Audio 1> as it is, even when the new look would sound different.
8. Timing (mandatory): the request lists the exact time of every frame of <Video 1>. Never compute times yourself, copy them from that list. Describe the video as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), using the listed frame times, so that the whole length of <Video 1> is covered from the first to the last frame. Compare consecutive frames: if something moves, say what and when. Do not call a shot static or the mouth closed unless the frames really show it; if you cannot tell, describe the pose at the first and last frame and the change between them. A cut is a new `[Shot N] At MM:SS.mmm, ...` at the first frame of the new shot.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset 5 - restyle the video. Show <Video 1> in the style named in the request below (and, if a <Picture 1> is listed, in the style of <Picture 1>): the same people, place, objects, motion, lip-sync, camera, timing and audio, rendered in the new look. Make the result seamless.
Extra request from the user, applied on top (name the style here):

# PROMPT
Restyle Video 1 as a hand-painted anime.

# I2V SYSTEM
PRESET 5 - RESTYLE, IMAGE-TO-VIDEO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the SCENE: a still image that replaces the source video; it provides the place, the light, the composition, the camera view and the people in it. <Picture 2>, when it is listed, is an optional STYLE REFERENCE. The look to apply is named in the request of the user (anime, oil painting, film noir, claymation ...). Your job is to write the full six-section rewrite for a target video that starts from the scene of <Picture 1> shown in the new style, with nothing else changed: the people, the place, the objects, the framing and the camera view stay.

Rules for this preset:
1. Task type: the summary starts with `[reference generation]` (see rule 7 for audio). It then says in one sentence which style the target video has.
2. Style: if the request names no style and there is no <Picture 2>, choose a simple, clearly named cinematic look and say so in the summary.
3. `subject_definitions`:
   - `<Subject 1>` is the visual style: from the request and, when <Picture 2> exists, from <Picture 2> (cite the picture inside this definition, no line of its own). List the rendering, the color palette, the lighting, the texture and the mood.
   - `<Subject 2>` is the content of <Picture 1> that stays: the people, the place and the objects (name them briefly, as seen).
4. `retention_analysis`: <Subject 1> is `fully_preserved`; <Subject 2> is `partially_preserved` (the same content, drawn in the new style).
5. `detailed_description`: begin with one or two sentences that set the style, then one shot, `[Shot 1]`, in the composition of <Picture 1>, described with the vocabulary of the new style, then the timeline of rule 8. Be as explicit as the guide asks.
6. Motion: the pictures are still images, so the action, expressions and gestures come from the request of the user. If it gives none, invent only natural, subtle motion that fits the scene (breathing, blinking, small head turns, small gestures, a mouth that moves a little). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do not change the identity, the clothing or the place: only how it is rendered.
7. Audio: the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag `<Subject 1> (S1)`).
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset 5 (image to video) - restyle. Use <Picture 1> as the scene and show it in the style named in the request below (and, if a <Picture 2> is listed, in the style of <Picture 2>), keeping the people, the place, the framing and the camera view. The action comes from the request; if it gives none, add only natural, subtle motion. Make the result seamless.
Extra request from the user, applied on top (name the style here):

# I2V PROMPT
Restyle Picture 1 as a hand-painted anime. The character looks at the camera and talks.
