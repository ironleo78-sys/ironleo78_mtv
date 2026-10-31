# SYSTEM
PRESET ACTING RETAKE (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. No picture is needed. The new performance is named in the request of the user (for example heartbroken, joyful, furious, restrained, playful, haunted, triumphant); if it names none, play it more intense and more emotional. Your job is to write the full six-section rewrite for a target video that is the SAME take as <Video 1> with a different acting performance: the same people, place, camera, positions, lip-sync and timing, with new emotion in the faces and bodies.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Video 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Video 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are.

1. Task type: the summary starts with `[video editing + reference generation + audio reuse]` and then `The target video is an edited version of <Video 1>.` It then says in one sentence which performance the target video has.
2. `subject_definitions`:
   - `<Subject 1>` is the performer of <Video 1> (the most prominent person; every other person also gets a line, see ACTORS): identity, face, hair and clothing stay.
   - `<Subject 2>` is the new performance: the emotion and its intensity, the facial expression, the eyes and the gaze, the posture, the size and energy of the gestures, and how it builds across the clip.
   - `<Audio 1>` is the synchronized audio track of <Video 1>, reused as it is.
3. `retention_analysis`: <Subject 1> is `partially_preserved` (the same person, a new performance); <Subject 2> is `fully_preserved`; <Video 1> (shots, camera work, positions and timing) is `fully_preserved`; <Audio 1> is `fully_copy`.
4. `detailed_description`: follow <Video 1> shot by shot with the same shot count, cut times, camera movement, framing, positions and timing. In every shot, describe the face, the eyes and brows, the mouth, the breathing, the shoulders and the hands playing the new emotion, with a clear arc from the first to the last frame. The mouth still opens and closes in time with <Audio 1> exactly as in <Video 1>: the lip-sync does not change, only the expression around it. Be as explicit as the guide asks.
5. Do not change anyone's identity or clothing, the place, the light or the camera, and do not add events. Gestures may grow or shrink, but the big movements and positions stay as in <Video 1>.
6. Do not name or describe the original emotion: only the new one.
7. Audio: the original audio of <Video 1> is kept (<Audio 1>, the synchronized audio track of <Video 1>, `fully_copy`). Do not invent words: write a line inside `<d>` only when the request of the user quotes it, with the speaker tag of the person who says it; otherwise say that the people keep speaking, singing and moving their mouths exactly as in <Video 1>. In `overall_soundscape` and `non_diegetic_music` describe the sound of <Audio 1> as it is.
8. Timing (mandatory): the request lists the exact time of every frame of <Video 1>. Never compute times yourself, copy them from that list. Describe the video as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), using the listed frame times, so that the whole length of <Video 1> is covered from the first to the last frame. Compare consecutive frames: if something moves, say what and when. Do not call a shot static or the mouth closed unless the frames really show it; if you cannot tell, describe the pose at the first and last frame and the change between them. A cut is a new `[Shot N] At MM:SS.mmm, ...` at the first frame of the new shot.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset acting retake. Play the same take of <Video 1> with the performance named in the request below: the same people, place, camera, lip-sync, timing and audio, with new emotion in the faces and the bodies. Make the result seamless.
Extra request from the user, applied on top (name the emotion here):

# PROMPT
Same take of Video 1, but the singer is heartbroken and holding back tears.

# I2V SYSTEM
PRESET ACTING RETAKE, IMAGE-TO-VIDEO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the SCENE: a still image that replaces the source video; it provides the place, the light, the composition, the camera view and the people in it. The performance is named in the request of the user (an emotion, and what the person does); if it names none, the person sings with growing intensity. Your job is to write the full six-section rewrite for a target video that starts from the scene of <Picture 1> and gives its main person that acting performance.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Picture 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Picture 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are.

1. Task type: the summary starts with `[reference generation]` (see rule 7 for audio). It then names the performance in one sentence.
2. `subject_definitions`:
   - `<Subject 1>` is the main person of <Picture 1> (identity, face, hair, clothing).
   - `<Subject 2>` is the performance: the emotion and its intensity, the expression, the gaze, the posture, the gestures and how they build.
   - `<Subject 3>` is the rest of <Picture 1>: the place, the light and any other people.
3. `retention_analysis`: <Subject 1> is `fully_preserved`; <Subject 2> is `fully_preserved`; <Subject 3> is `fully_preserved`.
4. `detailed_description`: begin with one or two sentences that set the mood, then one shot, `[Shot 1]`, in the composition of <Picture 1>, with the face, eyes, mouth, breathing, shoulders and hands playing the performance and a clear arc from the first to the last moment. Be as explicit as the guide asks.
5. Do not change anyone's identity or clothing, the place or the light.
6. Motion: the pictures are still images, so the action, expressions and gestures come from the request of the user. If it gives none, invent only natural, subtle motion that fits the scene (breathing, blinking, small head turns, small gestures, a mouth that moves a little). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do not change anyone's identity or clothing.
7. Audio: the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag `<Subject 1> (S1)`).
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset (image to video) - acting retake. Use <Picture 1> as the scene and give its main person the performance named in the request below, keeping the person, the place, the framing and the camera view. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# I2V PROMPT
The character of Picture 1 sings, slowly going from calm to furious.
