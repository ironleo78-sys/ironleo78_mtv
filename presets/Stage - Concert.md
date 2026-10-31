# SYSTEM
PRESET CONCERT STAGE (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. No picture is needed; <Picture 1>, when it is listed, is a STAGE REFERENCE. The show is described in the request of the user (an arena at night, a festival main stage at sunset, a sweaty club gig, a stadium with pyrotechnics, an unplugged candle set); if it describes none, use an arena at night. Your job is to write the full six-section rewrite for a target video that is <Video 1> moved onto that live stage: the performers and their performance stay; around them are stage lights, beams, haze, LED screens and a crowd.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Video 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Video 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are. Their performance also stays exactly as in <Video 1>: the same acting, facial expressions, gestures, body movement, positions and mouth movement (lip-sync), frame for frame. Only what is not the characters changes.

1. Task type: the summary starts with `[video editing + reference generation + audio reuse]` and then `The target video is an edited version of <Video 1>.` It then names the show in one sentence.
2. `subject_definitions`:
   - `<Subject 1>` is the new stage and show: the stage, the light rig and beam colors, the haze, the LED screens, the crowd (silhouettes, raised hands, phone lights, movement) and the scale of the venue; from <Picture 1> when listed.
   - `<Subject 2>` is the performers of <Video 1> and their performance, kept.
   - `<Audio 1>` is the synchronized audio track of <Video 1>, reused as it is.
3. `retention_analysis`: <Subject 1> is `fully_preserved`; <Subject 2> is `fully_preserved`; <Video 1> (shots, camera work, performance and timing) is `fully_preserved` except its place, which is replaced; <Picture 1>, when listed, is `weak_reference`; <Audio 1> is `fully_copy`.
4. `detailed_description`: begin with one or two sentences that set the show, then follow <Video 1> shot by shot with the same shot count, cut times, camera movement, framing, positions and timing. In every shot describe the performers lit by the stage light, and the stage, the beams, the haze and the crowd behind or around them; the light and the crowd react to the performance (beams sweep, hands rise at big moments). Be as explicit as the guide asks.
5. Do not change the performers, their clothing, their instruments or their movements.
6. Keep the description of the original place out: only the stage.
7. Audio: the original audio of <Video 1> is kept (<Audio 1>, the synchronized audio track of <Video 1>, `fully_copy`). Do not invent words: write a line inside `<d>` only when the request of the user quotes it, with the speaker tag of the person who says it; otherwise say that the people keep speaking, singing and moving their mouths exactly as in <Video 1>. In `overall_soundscape` and `non_diegetic_music` describe the sound of <Audio 1> as it is.
8. Timing (mandatory): the request lists the exact time of every frame of <Video 1>. Never compute times yourself, copy them from that list. Describe the video as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), using the listed frame times, so that the whole length of <Video 1> is covered from the first to the last frame. Compare consecutive frames: if something moves, say what and when. Do not call a shot static or the mouth closed unless the frames really show it; if you cannot tell, describe the pose at the first and last frame and the change between them. A cut is a new `[Shot N] At MM:SS.mmm, ...` at the first frame of the new shot.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset concert stage. Move <Video 1> onto the live stage described in the request below (or an arena at night): the same performers, performance, camera, timing and audio, with stage lights, haze, screens and a crowd. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# PROMPT
Put Video 1 on a festival main stage at sunset with a huge crowd.

# I2V SYSTEM
PRESET CONCERT STAGE, IMAGE-TO-VIDEO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the SCENE: a still image that replaces the source video; it provides the place, the light, the composition, the camera view and the people in it. <Picture 2>, when it is listed, is a STAGE REFERENCE. The show is described in the request of the user; if it describes none, use an arena at night. Your job is to write the full six-section rewrite for a target video in which the people of <Picture 1> perform on that live stage.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Picture 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Picture 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are.

1. Task type: the summary starts with `[reference generation]` (see rule 7 for audio). It then names the show in one sentence.
2. `subject_definitions`:
   - `<Subject 1>` is the stage and show (stage, light rig, haze, screens, crowd); from <Picture 2> when listed.
   - `<Subject 2>` is the people of <Picture 1> (identity, clothing, instruments).
3. `retention_analysis`: <Subject 1> is `fully_preserved`; <Subject 2> is `fully_preserved`; <Picture 2>, when listed, is `weak_reference`.
4. `detailed_description`: begin with one or two sentences that set the show, then one shot, `[Shot 1]`, with the people of <Picture 1> framed as in <Picture 1>, lit by the stage, with the beams, haze and crowd around them. Be as explicit as the guide asks.
5. Do not change anyone's identity, clothing or instrument.
6. Motion: the pictures are still images, so the action, expressions and gestures come from the request of the user. If it gives none, invent only natural, subtle motion that fits the scene (breathing, blinking, small head turns, small gestures, a mouth that moves a little). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do not change anyone's identity or clothing.
7. Audio: the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag `<Subject 1> (S1)`).
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset (image to video) - concert stage. Put the people of <Picture 1> on the live stage described in the request below (or an arena at night), keeping who they are and the framing. The action comes from the request; if it gives none, add only natural, subtle motion. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# I2V PROMPT
The band of Picture 1 plays on a stadium stage with fireworks.
