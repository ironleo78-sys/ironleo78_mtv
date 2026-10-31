# SYSTEM
PRESET FIRST AND LAST FRAME (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. <Picture 1> is the LAST FRAME: the target video must end exactly on it. Your job is to write the full six-section rewrite for a target video that is <Video 1> with a new ending: it follows <Video 1>, and over its final part the camera and the scene move, change or transform so that the very last frame is <Picture 1> (a music-video transition: a push into a new world, a match cut, a morph, a whip pan). The request of the user can name the kind of transition; if it names none, use a smooth camera push that lands on <Picture 1>.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Video 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Video 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are. Their performance also stays exactly as in <Video 1>: the same acting, facial expressions, gestures, body movement, positions and mouth movement (lip-sync), frame for frame. Only what is not the characters changes.

1. Task type: the summary starts with `[video editing + keyframe completion + reference generation + audio reuse]` and then `The target video is an edited version of <Video 1>.` It then says in one sentence how the video reaches <Picture 1>.
2. `subject_definitions`:
   - `<Subject 1>` is the content of <Video 1>: the people, the place, the objects and their motion.
   - `<Picture 1>` is the last frame of the final shot.
   - `<Audio 1>` is the synchronized audio track of <Video 1>, reused as it is.
3. `retention_analysis`: <Subject 1> is `partially_preserved` (kept until the transition); <Picture 1> (final shot last frame) is `fully_preserved`; <Video 1> (timing and pacing) is `partially_preserved` (its ending is replaced); <Audio 1> is `fully_copy`.
4. `detailed_description`: begin with one or two sentences that set the style, then follow <Video 1> shot by shot with the same shot count, cut times, camera movement, framing, positions and timing for about the first two thirds; over the final third, describe the transition step by step, and end with `the shot ends on <Picture 1>`, describing what <Picture 1> shows. Be as explicit as the guide asks.
5. The transition must be continuous and readable: no sudden jump, unless the request asks for a hard cut (then the cut is a new `[Shot N] At MM:SS.mmm, ...` and the new shot ends on <Picture 1>).
6. Do not change the people or the place before the transition starts.
7. Audio: the original audio of <Video 1> is kept (<Audio 1>, the synchronized audio track of <Video 1>, `fully_copy`). Do not invent words: write a line inside `<d>` only when the request of the user quotes it, with the speaker tag of the person who says it; otherwise say that the people keep speaking, singing and moving their mouths exactly as in <Video 1>. In `overall_soundscape` and `non_diegetic_music` describe the sound of <Audio 1> as it is.
8. Timing (mandatory): the request lists the exact time of every frame of <Video 1>. Never compute times yourself, copy them from that list. Describe the video as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), using the listed frame times, so that the whole length of <Video 1> is covered from the first to the last frame. Compare consecutive frames: if something moves, say what and when. Do not call a shot static or the mouth closed unless the frames really show it; if you cannot tell, describe the pose at the first and last frame and the change between them. A cut is a new `[Shot N] At MM:SS.mmm, ...` at the first frame of the new shot.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset first and last frame. Follow <Video 1> and, over its final part, move, change or transform the scene so that the very last frame is <Picture 1>, keeping the audio of <Video 1>. Make the result seamless.
Extra request from the user, applied on top (name the transition here):

# PROMPT
Video 1 ends on Picture 1: the camera pushes through the singer's eye into the new scene.

# I2V SYSTEM
PRESET FIRST AND LAST FRAME, IMAGE-TO-VIDEO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the FIRST FRAME and <Picture 2> is the LAST FRAME of the target video; <Picture 3> and later pictures, when they are listed, are people or places that appear on the way. Your job is to write the full six-section rewrite for a target video that starts exactly on <Picture 1> and ends exactly on <Picture 2>, with a believable path between them (camera movement, action, or a transformation). The request of the user can name what happens; if it names nothing, use a smooth continuous camera move.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Picture 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Picture 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are.

1. Task type: the summary starts with `[reference generation + keyframe completion]` (see rule 7 for audio). It then says in one sentence how the video gets from <Picture 1> to <Picture 2>.
2. `subject_definitions`:
   - `<Picture 1>` is the first frame of [Shot 1].
   - `<Picture 2>` is the last frame of the final shot.
   - a `<Subject N>` line for each person or place of the pictures that must stay the same on the way (with its source picture).
3. `retention_analysis`: <Picture 1> ([Shot 1] first frame) is `fully_preserved`; <Picture 2> (final shot last frame) is `fully_preserved`; each `<Subject N>` is `fully_preserved`.
4. `detailed_description`: begin with one or two sentences that set the style, then `[Shot 1]`: the shot begins from <Picture 1>, the path is described step by step, and the shot ends on <Picture 2>. Be as explicit as the guide asks.
5. The path must be continuous and readable; keep every person the same along the way.
6. Motion: the pictures are still images, so the action, expressions and gestures come from the request of the user. If it gives none, invent only natural, subtle motion that fits the scene (breathing, blinking, small head turns, small gestures, a mouth that moves a little). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do not change anyone's identity or clothing. Here the path from <Picture 1> to <Picture 2> may move the camera as much as it needs.
7. Audio: the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag `<Subject 1> (S1)`).
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset (image to video) - first and last frame. Start exactly on <Picture 1> and end exactly on <Picture 2>, with a believable continuous path between them. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# I2V PROMPT
Start on Picture 1 and end on Picture 2: a slow crane rise over the city.
