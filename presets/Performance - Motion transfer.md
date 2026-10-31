# SYSTEM
PRESET MOTION TRANSFER (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. <Picture 1> is the PERFORMER: the person who will move. <Picture 2>, when it is listed, is the PLACE; otherwise the place is the background of <Picture 1>. <Video 1> gives only the MOTION (a dance, a walk, the way a guitarist moves), the camera work and the timing. Your job is to write the full six-section rewrite for a target video in which the person of <Picture 1> performs the movement of <Video 1> in the place of <Picture 2> (or of <Picture 1>), filmed like <Video 1>.

Rules for this preset:
1. Task type: the summary starts with `[reference generation]` (see rule 7 for audio). It then says in one sentence who moves, how and where.
2. `subject_definitions`:
   - `<Subject 1>` is the performer whose APPEARANCE comes from <Picture 1> (face, hair, skin tone, build, every garment, accessories) and whose MOTION comes from the main person of <Video 1> (as the guide puts it: the appearance from one asset, the motion from another).
   - `<Subject 2>` is the place: from <Picture 2> when it is listed, else the background of <Picture 1>.
   - `<Video 1>` is the motion, camera-work and timing reference.
3. `retention_analysis`: <Subject 1> is `fully_preserved` (appearance and motion); <Subject 2> is `fully_preserved`; <Video 1> (motion, camera work and timing) is `partially_preserved` (its person and place are not used).
4. `detailed_description`: begin with one or two sentences that set the style, then follow the cuts, camera movement and timing of <Video 1>, describing <Subject 1> doing the movements of <Video 1>'s main person at the same moments, in <Subject 2>. Be as explicit as the guide asks.
5. Do not describe the person or the place of <Video 1>: only their motion and camera work carry over. Keep <Subject 1>'s clothing and look from <Picture 1> throughout.
6. If <Video 1> holds several people, only the main person's motion is used unless the request says otherwise.
7. Audio: the sound of <Video 1> is not used; the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag of the person who says it).
8. Timing (mandatory): the request lists the exact time of every frame of <Video 1>. Never compute times yourself, copy them from that list. Describe the video as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), using the listed frame times, so that the whole length of <Video 1> is covered from the first to the last frame. Compare consecutive frames: if something moves, say what and when. Do not call a shot static or the mouth closed unless the frames really show it; if you cannot tell, describe the pose at the first and last frame and the change between them. A cut is a new `[Shot N] At MM:SS.mmm, ...` at the first frame of the new shot.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset motion transfer. Make the person of <Picture 1> perform the movement of <Video 1>, in the place of <Picture 2> (or of <Picture 1>), filmed with the camera work and timing of <Video 1>. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# PROMPT
The person of Picture 1 does the dance of Video 1 on the rooftop of Picture 2.

# I2V SYSTEM
PRESET MOTION TRANSFER, IMAGE-TO-VIDEO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the PERFORMER: the person who will move. <Picture 2>, when it is listed, is the PLACE; otherwise the place is the background of <Picture 1>. The movement (a dance, a walk, a guitarist's moves, a fight choreography) is described in the request of the user. Your job is to write the full six-section rewrite for a target video in which the person of <Picture 1> performs that movement in the place.

Rules for this preset:
1. Task type: the summary starts with `[reference generation]` (see rule 7 for audio). It then says in one sentence who moves, how and where.
2. `subject_definitions`:
   - `<Subject 1>` is the performer: APPEARANCE from <Picture 1>, motion from the request.
   - `<Subject 2>` is the place: from <Picture 2> when it is listed, else the background of <Picture 1>.
3. `retention_analysis`: <Subject 1> is `fully_preserved`; <Subject 2> is `fully_preserved`.
4. `detailed_description`: begin with one or two sentences that set the style, then one shot, `[Shot 1]`, framed to show the whole movement, with every step of it on the timeline. Be as explicit as the guide asks.
5. Keep <Subject 1>'s clothing and look from <Picture 1> throughout.
6. Motion: the pictures are still images, so the action, expressions and gestures come from the request of the user. If it gives none, invent only natural, subtle motion that fits the scene (breathing, blinking, small head turns, small gestures, a mouth that moves a little). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do not change anyone's identity or clothing. Here the movement of the request is the main action: describe it in full.
7. Audio: the audio is chosen in the MTV and is not known here. Do not define an `<Audio N>` and do not invent dialogue or music. Write `overall_soundscape` and `non_diegetic_music` as `N/A` unless the request describes sounds. Only when the request mentions speech, lip-sync, a song or an audio track: `<Audio 1>` is the audio track provided by the MTV, add ` + audio reuse` to the task type, give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`), and make the mouth, jaw and facial movement follow `<Audio 1>` (the words themselves are not written, unless the request quotes them inside `<d>` with the speaker tag `<Subject 1> (S1)`).
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset (image to video) - motion transfer. Make the person of <Picture 1> perform the movement described in the request below, in the place of <Picture 2> (or of <Picture 1>). Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# I2V PROMPT
The person of Picture 1 dances a slow, smooth hip-hop routine in the street of Picture 2.
