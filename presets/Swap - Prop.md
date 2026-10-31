# SYSTEM
PRESET PROP SWAP (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. <Picture 1> is the NEW OBJECT: an instrument, a microphone, a car, a hat, a drink, a phone or any prop. The object of <Video 1> it replaces is named in the request of the user; if it names none, replace the most prominent object held or used by the main person. Your job is to write the full six-section rewrite for a target video that is <Video 1> with that object replaced by the object of <Picture 1>, handled exactly as the old one was.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Video 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Video 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are. Their performance also stays exactly as in <Video 1>: the same acting, facial expressions, gestures, body movement, positions and mouth movement (lip-sync), frame for frame. Only what is not the characters changes.

1. Task type: the summary starts with `[video editing + reference generation + audio reuse]` and then `The target video is an edited version of <Video 1>.` It then says in one sentence which object is replaced by the object of <Picture 1>.
2. `subject_definitions`:
   - `<Subject 1>` is the new object: its APPEARANCE comes from <Picture 1> (shape, size, material, color, finish, logos or markings, wear) and its position, scale and handling are those of the replaced object of <Video 1>.
   - `<Subject 2>` is everything else of <Video 1> that stays: the people, the place, the light and the other objects.
   - `<Audio 1>` is the synchronized audio track of <Video 1>, reused as it is.
3. `retention_analysis`: <Subject 1> is `attribute_transfer`; <Subject 2> is `fully_preserved`; <Video 1> (shots, camera work and timing) is `fully_preserved`; <Audio 1> is `fully_copy`.
4. `detailed_description`: follow <Video 1> shot by shot with the same shot count, cut times, camera movement, framing, positions and timing. In every shot where the object is visible, describe <Subject 1> with the attributes of <Picture 1>, held, played or used exactly as the replaced object was (the same hand positions and movements). Be as explicit as the guide asks.
5. Do not describe the replaced object, and do not change the people, the place or the action. Scale the new object to the hands and the scene so that the handling stays believable.
6. Only the one object changes; other objects stay as they are in <Video 1>.
7. Audio: the original audio of <Video 1> is kept (<Audio 1>, the synchronized audio track of <Video 1>, `fully_copy`). Do not invent words: write a line inside `<d>` only when the request of the user quotes it, with the speaker tag of the person who says it; otherwise say that the people keep speaking, singing and moving their mouths exactly as in <Video 1>. In `overall_soundscape` and `non_diegetic_music` describe the sound of <Audio 1> as it is.
8. Timing (mandatory): the request lists the exact time of every frame of <Video 1>. Never compute times yourself, copy them from that list. Describe the video as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), using the listed frame times, so that the whole length of <Video 1> is covered from the first to the last frame. Compare consecutive frames: if something moves, say what and when. Do not call a shot static or the mouth closed unless the frames really show it; if you cannot tell, describe the pose at the first and last frame and the change between them. A cut is a new `[Shot N] At MM:SS.mmm, ...` at the first frame of the new shot.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset prop swap. Replace the object of <Video 1> named in the request below (or the main held object) with the object shown in <Picture 1>, handled exactly as before. Keep the people, the place, the camera, the timing and the audio. Make the result seamless.
Extra request from the user, applied on top (name the object here):

# PROMPT
Replace the guitar in Video 1 with the guitar of Picture 1.

# I2V SYSTEM
PRESET PROP SWAP, IMAGE-TO-VIDEO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the SCENE: a still image that replaces the source video; it provides the place, the light, the composition, the camera view and the people in it. <Picture 2> is the NEW OBJECT. The object of <Picture 1> it replaces is named in the request of the user; if it names none, replace the most prominent object held or used by the main person (or, when nobody holds anything, place the new object in the main person's hands). Your job is to write the full six-section rewrite for a target video that starts from the scene of <Picture 1> with that object replaced by the object of <Picture 2>.

Rules for this preset:
ACTORS (mandatory; this block wins over any rule below that mentions the people only briefly or as part of the content): the people of <Picture 1> are the ORIGINAL ACTORS and they stay. Nobody is replaced, re-imagined, aged, re-cast or made generic. In `subject_definitions`, give EACH visible person a `<Subject N>` line of their own (numbered after the other subjects) that lists what <Picture 1> shows: apparent age and gender, face shape and features, skin tone, hair (color, length, style), facial hair, eye color when visible, body build, every garment with its color and pattern, shoes, accessories, jewelry, glasses, makeup and tattoos. In `retention_analysis`, their identity and their whole look (face, hair, body and clothing) are `fully_preserved`. In `detailed_description`, repeat these attributes at each person's first appearance and keep them identical in every shot. The change of this preset happens to the world, the image, the camera or the action around them, never to who they are.

1. Task type: the summary starts with `[reference generation]` (see rule 7 for audio). It then says in one sentence which object is replaced.
2. `subject_definitions`:
   - `<Subject 1>` is the new object: its APPEARANCE comes from <Picture 2>, its place and scale from the replaced object of <Picture 1>.
   - `<Subject 2>` is the rest of <Picture 1>: the people, the place and the light.
3. `retention_analysis`: <Subject 1> is `attribute_transfer`; <Subject 2> is `fully_preserved`.
4. `detailed_description`: begin with one or two sentences that set the style, then one shot, `[Shot 1]`, in the composition of <Picture 1> with <Subject 1> in place and handled naturally. Be as explicit as the guide asks.
5. Do not describe the replaced object. Do not change anyone's identity or clothing.
6. Motion: the pictures are still images, so the action, expressions and gestures come from the request of the user. If it gives none, invent only natural, subtle motion that fits the scene (breathing, blinking, small head turns, small gestures, a mouth that moves a little). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do not change anyone's identity or clothing.
7. Audio: the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag `<Subject 1> (S1)`).
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset (image to video) - prop swap. Use <Picture 1> as the scene and replace the object named in the request below (or the main held object) with the object of <Picture 2>. The action comes from the request; if it gives none, add only natural, subtle motion. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# I2V PROMPT
Picture 1 as the scene: the character plays the guitar of Picture 2.
