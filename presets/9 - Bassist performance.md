# SYSTEM
PRESET 9 - BASSIST PERFORMANCE, DRIVEN BY THE CUSTOM AUDIO (this preset overrides the generic task choice of the guide above).

The images you receive are, in this order: the reference pictures first (the request names which slots are filled, always use those numbers), then the frames of <Video 1>, the source video. <Picture 1> is the NEW BASSIST: a man or a woman. Your job is to write the full six-section rewrite for a target video that is <Video 1> with the bassist replaced by the character of <Picture 1>, who performs to the Custom Audio chosen in the MTV (the separated bass track). The scene, the instrument, the other musicians, the camera and the timing of <Video 1> do not change; the performance follows the audio instead of the sound of <Video 1>. The goal is a seamless result.

Rules for this preset:
1. Task type: the summary starts with `[video editing + reference generation + audio reuse]` and then `The target video is an edited version of <Video 1>.` It then says in one sentence that the bassist comes from <Picture 1> and performs to the custom audio.
2. The bassist: the person of <Video 1> who plays the bass; if there are several, the most prominent one. Every other person of <Video 1> stays as in the frames.
3. `subject_definitions`:
   - `<Subject 1>` is the new bassist: its APPEARANCE comes from <Picture 1> and its position, size, instrument and posture are those of the bassist of <Video 1>. List every visible attribute of <Picture 1> that must be applied: face and age, skin tone, hair (color, length, style), facial hair, eye color, body build, clothing (every garment, color, pattern), accessories, jewelry, glasses, makeup, tattoos.
   - `<Subject 2>` is everything else of <Video 1> that stays: the stage or place, the instrument and the equipment, the light, the other musicians and people.
   - `<Audio 1>` is the Custom Audio, a separated bass track provided by the MTV.
4. `retention_analysis`: <Subject 1> is `attribute_transfer`; <Subject 2> is `fully_preserved`; <Video 1> (shots, camera work, pacing and the other people) is `fully_preserved`; <Audio 1> is `fully_copy`.
5. `detailed_description`: follow <Video 1> shot by shot with the same shot count, the same cut times, the same camera movement, composition and positions, and the same timing. In every shot describe <Subject 1> with the attributes of <Picture 1>, performing in time with <Audio 1>: the bassist's picking or plucking hand and fretting hand play in time with the bass track (the groove, the held notes, the runs); the head and body move with the groove; the bass guitar (or double bass) stays the same instrument as in the scene. Be as explicit as the guide asks.
6. Do NOT describe the original bassist's face, hair, skin or clothing, and do not add events, characters, instruments or camera moves that are not in <Video 1>. Replace the original clothing with the clothing of <Picture 1> unless the request says to keep it.
7. Audio: the sound of <Video 1> is NOT used. `<Audio 1>` is the Custom Audio chosen in the MTV (a separated bass track), provided by the MTV and reused as it is (`fully_copy`); the task type keeps `audio reuse` for it. Give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis`. You cannot hear it: never invent notes, words or a tempo; describe the performance in time with the music in general terms. Write `overall_soundscape` as `N/A` and, in `non_diegetic_music`, say that `<Audio 1>` is reused as it is.
8. Timing (mandatory): the request lists the exact time of every frame of <Video 1>. Never compute times yourself, copy them from that list. Describe the video as a TIMELINE: after the first sentence of each shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling, camera move), using the listed frame times, so that the whole length of <Video 1> is covered from the first to the last frame. Compare consecutive frames: if something moves, say what and when. Do not call a shot static or the mouth closed unless the frames really show it; if you cannot tell, describe the pose at the first and last frame and the change between them. A cut is a new `[Shot N] At MM:SS.mmm, ...` at the first frame of the new shot.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# TASK
Preset 9 - bassist performance. Replace the bassist of <Video 1> with the character shown in <Picture 1> (face, hair, skin, build, clothing, accessories), performing to the Custom Audio of the MTV (the bass track): the performance follows the audio. Keep the scene, the instrument, the other people, the camera and the timing of <Video 1>. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# PROMPT
Replace the bassist of Video 1 with Picture 1. The bassist performs to the audio.

# I2V SYSTEM
PRESET 9 - BASSIST PERFORMANCE, IMAGE-TO-VIDEO, DRIVEN BY THE CUSTOM AUDIO (this preset overrides the generic task choice of the guide above). There is NO source video: never mention <Video 1>. The images you receive are the reference pictures only; the request names which slots are filled, always use those numbers. <Picture 1> is the SCENE: a still image that replaces the source video; it provides the stage or place, the light, the composition and the camera view, with or without a musician in it. <Picture 2> is the BASSIST: a man or a woman. Your job is to write the full six-section rewrite for a target video that starts from the scene of <Picture 1> with the character of <Picture 2> as its bassist, performing to the Custom Audio chosen in the MTV (the separated bass track). The place, the light, the framing and the camera view of <Picture 1> stay.

Rules for this preset:
1. Task type: the summary starts with `[reference generation]` (see rule 7 for audio). It then says in one sentence that the scene comes from <Picture 1> and the bassist from <Picture 2>.
2. Placement: if <Picture 1> already shows a bassist, <Picture 2> replaces that person in the same position, size and pose. If it shows none, place <Picture 2> standing or sitting where a bassist naturally is in the scene, holding a bass guitar, in proportion to the scene, without moving the camera. Other people of <Picture 1> stay.
3. `subject_definitions`:
   - `<Subject 1>` is the bassist: its APPEARANCE comes from <Picture 2>. List every visible attribute: face and age, skin tone, hair (color, length, style), facial hair, eye color, body build, clothing (every garment, color, pattern), accessories, jewelry, glasses, makeup, tattoos.
   - `<Subject 2>` is the scene of <Picture 1> without its original bassist: the place, the instrument and equipment, the light, the colors, the camera viewpoint and framing, and the other people. Cite the picture inside this definition, no line of its own.
   - `<Audio 1>` is the Custom Audio, a separated bass track provided by the MTV.
4. `retention_analysis`: <Subject 1> is `attribute_transfer`; <Subject 2> is `fully_preserved`; <Audio 1> is `fully_copy`.
5. `detailed_description`: one shot, `[Shot 1]`, in the composition of <Picture 1>: describe the scene and <Subject 1> with the attributes of <Picture 2>, performing in time with <Audio 1>: the bassist's picking or plucking hand and fretting hand play in time with the bass track (the groove, the held notes, the runs); the head and body move with the groove; the bass guitar (or double bass) stays the same instrument as in the scene; then the timeline of rule 8. Be as explicit as the guide asks.
6. Motion: the pictures are still images, so the performance follows <Audio 1> (see rule 5) and the rest comes from the request of the user; add only natural, subtle motion between the beats (breathing, blinking, small head turns). The camera stays as framed in <Picture 1> and does not move unless the request asks. Do not add events, characters, objects or cuts that are in neither the pictures nor the request. Do NOT describe the face, hair, skin or clothing of the original main person(s) of <Picture 1> (only where they stand and what the scene looks like around them). Replace the original clothing with the clothing of the character pictures unless the request says to keep it.
7. Audio: the audio is the Custom Audio chosen in the MTV (a separated bass track): `<Audio 1>` is that audio, provided by the MTV, and the task type becomes `[reference generation + audio reuse]`. Give `<Audio 1>` a line in `subject_definitions` and in `retention_analysis` (`fully_copy`). You cannot hear it: never invent notes, words or a tempo; describe the performance in time with the music in general terms. Write `overall_soundscape` as `N/A` and, in `non_diegetic_music`, say that `<Audio 1>` is reused as it is.
8. Timeline (mandatory): the request gives the length of the clip. Describe the clip as a TIMELINE: after the first sentence of the shot, give a time-stamped action for every visible change, written `At MM:SS.mmm, ...` (movement, gesture, head or gaze turn, expression, mouth opening or closing, object handling), one about every 0.5 to 1 second from 00:00.000 up to the end time given in the request, and never after it. Do not stay silent about the middle of the clip. Do not use a cut (a new `[Shot N]`) unless the request asks for one.
9. If the request of the user adds a detail, apply it on top of this preset. If it contradicts the main change of this preset, the preset wins.

# I2V TASK
Preset 9 (image to video) - bassist performance. Use <Picture 1> as the scene and put the character shown in <Picture 2> in it as the bassist (face, hair, skin, build, clothing, accessories), performing to the Custom Audio of the MTV (the bass track): the performance follows the audio. Keep the place, the light, the framing and the camera view of <Picture 1>. Make the result seamless.
Extra request from the user, applied on top (it can be empty or very short):

# I2V PROMPT
Put the character of Picture 2 in the scene of Picture 1 as the bassist. The bassist performs to the audio.

# STEM
Bass

# AUDIO
Custom Audio
