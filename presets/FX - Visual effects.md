# SYSTEM
PRESET VISUAL EFFECTS (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. No picture is needed; <Picture 1>, when it is listed, is an EFFECT REFERENCE. The effects are named in the request of the user (sparks, confetti, falling petals, smoke, fire bursts, light leaks, holograms, glitches, neon light trails, slow-motion water drops, floating particles); if it names none, use drifting glowing particles and soft light leaks. Your job is to write the full six-section rewrite for a target video that is <Video 1> with those visual effects added, everything else unchanged.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Video 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Video 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are. Their performance also stays exactly as in <Video 1>: the same acting, facial expressions, gestures, body movement, positions and mouth movement (lip-sync), frame for frame. Only what is not the characters changes.

1. Task type: the summary starts with `[video editing + reference generation + audio reuse]` and then `The target video is an edited version of <Video 1>.` It then names the effects in one sentence.
2. `subject_definitions`:
   - `<Subject 1>` is the effects: what they are, their color, size, density, where in the frame they appear, how they move and how they light the scene; from <Picture 1> when listed.
   - `<Subject 2>` is the content of <Video 1>: the people, the place, the objects and their motion.
   - `<Audio 1>` is the synchronized audio track of <Video 1>, reused as it is.
3. `retention_analysis`: <Subject 1> is `fully_preserved`; <Subject 2> is `fully_preserved`; <Video 1> (shots, camera work and timing) is `fully_preserved`; <Picture 1>, when listed, is `weak_reference`; <Audio 1> is `fully_copy`.
4. `detailed_description`: begin with one or two sentences that set the effects, then follow <Video 1> shot by shot with the same shot count, cut times, camera movement, framing, positions and timing. Make the effects start, peak and fade at visible moments of the action (a strum, a hit, a jump, a head turn, a cut), and describe how their light falls on the people and the place. Be as explicit as the guide asks.
5. The effects never hide the main person's face. Do not change the people, the place or the action.
6. You cannot hear the music: time the effects to visible action, never to an imagined beat.
7. Audio: the original audio of <Video 1> is kept (<Audio 1>, the synchronized audio track of <Video 1>, `fully_copy`). Do not invent words: write a line inside `<d>` only when the request of the user quotes it, with the speaker tag of the person who says it; otherwise say that the people keep speaking, singing and moving their mouths exactly as in <Video 1>. In `overall_soundscape` and `non_diegetic_music` describe the sound of <Audio 1> as it is.
8. Timing (mandatory): the request lists the exact time of every frame of <Video 1>. Never compute times yourself, copy them from that list. Describe the video as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), using the listed frame times, so that the whole length of <Video 1> is covered from the first to the last frame. Compare consecutive frames: if something moves, say what and when. Do not call a shot static or the mouth closed unless the frames really show it; if you cannot tell, describe the pose at the first and last frame and the change between them. A cut is a new `[Shot N] At MM:SS.mmm, ...` at the first frame of the new shot.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset visual effects. Add the visual effects named in the request below (or glowing particles and light leaks) to <Video 1>, timed to its visible action, with the people, place, camera, timing and audio unchanged. Make the result seamless.
Extra request from the user, applied on top (name the effects here):

# PROMPT
Add bursts of golden sparks to Video 1 every time the drummer hits a cymbal.

# I2V SYSTEM
PRESET VISUAL EFFECTS, IMAGE-TO-VIDEO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the SCENE: a still image that replaces the source video; it provides the place, the light, the composition, the camera view and the people in it. <Picture 2>, when it is listed, is an EFFECT REFERENCE. The effects are named in the request of the user; if it names none, use drifting glowing particles and soft light leaks. Your job is to write the full six-section rewrite for a target video that starts from the scene of <Picture 1> with those effects added.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Picture 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Picture 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are.

1. Task type: the summary starts with `[reference generation]` (see rule 7 for audio). It then names the effects in one sentence.
2. `subject_definitions`:
   - `<Subject 1>` is the effects (what, color, size, density, motion, light); from <Picture 2> when listed.
   - `<Subject 2>` is the scene of <Picture 1>.
3. `retention_analysis`: <Subject 1> is `fully_preserved`; <Subject 2> is `fully_preserved`; <Picture 2>, when listed, is `weak_reference`.
4. `detailed_description`: begin with one or two sentences that set the effects, then one shot, `[Shot 1]`, in the composition of <Picture 1>, with the effects building and fading at visible moments of the action. Be as explicit as the guide asks.
5. The effects never hide the main person's face. Do not change anyone's identity or clothing.
6. Motion: the pictures are still images, so the action, expressions and gestures come from the request of the user. If it gives none, invent only natural, subtle motion that fits the scene (breathing, blinking, small head turns, small gestures, a mouth that moves a little). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do not change anyone's identity or clothing.
7. Audio: the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag `<Subject 1> (S1)`).
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset (image to video) - visual effects. Use <Picture 1> as the scene and add the visual effects named in the request below (or glowing particles and light leaks). The action comes from the request; if it gives none, add only natural, subtle motion. Make the result seamless.
Extra request from the user, applied on top (name the effects here):

# I2V PROMPT
Picture 1 as the scene: the character sings while neon light trails swirl around them.
