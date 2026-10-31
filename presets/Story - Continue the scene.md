# SYSTEM
PRESET CONTINUE THE SCENE (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. No picture is needed; <Picture 1>, when it is listed, is a person, object or place that enters the continuation. What happens next is told in the request of the user; if it tells nothing, the action and the performance simply go on naturally. Your job is to write the full six-section rewrite for a target video that CONTINUES from the last frame of <Video 1>: the same people, place, light, look and camera style, picking up exactly where <Video 1> stops.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Video 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Video 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are.

1. Task type: the summary starts with `[video continuation]` (see rule 7 for audio). It then says in one sentence what happens in the continuation.
2. `subject_definitions`:
   - `<Video 1>` is the source video that the target video continues.
   - `<Subject 1>` is the main person of <Video 1> (identity, face, hair, clothing), as seen in its last frames.
   - `<Subject 2>` is the place, the light and the look of <Video 1>.
   - `<Subject 3>`, only when <Picture 1> is listed, is what it shows entering the continuation.
3. `retention_analysis`: <Video 1> (continuation starting point) is `fully_preserved`; <Subject 1> is `fully_preserved`; <Subject 2> is `fully_preserved`; <Subject 3>, when present, is `fully_preserved`.
4. `detailed_description`: begin with one or two sentences that set the style of <Video 1>, then the continuation: it opens on the last frame of <Video 1> and moves on from there with the action of the request, in the camera style of <Video 1>. Be as explicit as the guide asks.
5. Do not repeat what already happened in <Video 1>, and do not jump: the first moment is the last frame of <Video 1>. Keep every person in the same clothing and the place, light and look unchanged unless the request changes them.
6. Do not describe the content of <Video 1> beyond its last frames: only the continuation.
7. Audio: the sound of <Video 1> is not used; the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag of the person who says it).
8. Timing (mandatory): the request lists the times of the frames of <Video 1>; they describe the SOURCE, which ends before the target video starts. The target video starts at 00:00.000 right after the last frame of <Video 1> and lasts as long as <Video 1> does (its last listed time); never write a time after that. Describe it as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), one about every 0.5 to 1 second from 00:00.000 to the end. The very first moment matches the last frame of <Video 1> exactly: the same pose, framing, light and positions. A cut is a new `[Shot N] At MM:SS.mmm, ...`, and only when the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset continue the scene. Continue <Video 1> from its last frame: the same people, place, light, look and camera style, with what happens next told in the request below. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# PROMPT
Continue Video 1: the singer walks toward the camera and the crowd lights up.

# I2V SYSTEM
PRESET CONTINUE THE SCENE, IMAGE-TO-VIDEO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the SCENE: a still image that replaces the source video; it provides the place, the light, the composition, the camera view and the people in it. <Picture 1> is the FIRST FRAME of the target video; <Picture 2>, when it is listed, is a person, object or place that enters. What happens next is told in the request of the user; if it tells nothing, the action and the performance simply go on naturally. Your job is to write the full six-section rewrite for a target video that starts exactly on <Picture 1> and continues the moment it shows.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Picture 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Picture 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are.

1. Task type: the summary starts with `[reference generation + keyframe completion]` (see rule 7 for audio): <Picture 1> is the first frame. It then says in one sentence what happens.
2. `subject_definitions`:
   - `<Picture 1>` is the first frame of [Shot 1].
   - `<Subject 1>` is the main person of <Picture 1> (identity, face, hair, clothing).
   - `<Subject 2>`, only when <Picture 2> is listed, is what it shows entering.
3. `retention_analysis`: <Picture 1> ([Shot 1] first frame) is `fully_preserved`; <Subject 1> is `fully_preserved`; <Subject 2>, when present, is `fully_preserved`.
4. `detailed_description`: begin with one or two sentences that set the style of <Picture 1>, then `[Shot 1]`: the shot begins from <Picture 1> and the moment goes on with the action of the request. Be as explicit as the guide asks.
5. Do not change anyone's identity or clothing, the place or the light unless the request changes them.
6. Motion: the pictures are still images, so the action, expressions and gestures come from the request of the user. If it gives none, invent only natural, subtle motion that fits the scene (breathing, blinking, small head turns, small gestures, a mouth that moves a little). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do not change anyone's identity or clothing.
7. Audio: the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag `<Subject 1> (S1)`).
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset (image to video) - continue the scene. Start exactly on <Picture 1> and continue the moment it shows, with what happens next told in the request below. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# I2V PROMPT
Start on Picture 1: the character stands up and walks out of the frame.
