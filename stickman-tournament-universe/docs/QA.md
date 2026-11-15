# Quality control

## Automatic checks (run on every match)

* **Simulation**: `stu/qa/validate.py::validate_match` checks the following:
  * Exactly one winner, who has exactly `points_to_win` points.
  * The point log is consistent with the score.
  * The final point comes at or after the minimum duration and before the maximum.
  * The safety-net force-finish was not used.
  * No NaN or infinite joint values.
  * Bone lengths stay constant within 2 cm.
  * No root displacement over 0.35 m per tick unless the move is an ability teleport.
  * Hits register at the defender's position.
  * All techniques exist in the library.
* **Video**: `validate_video` checks the resolution, fps ≥ config, the H.264 codec, and that the decoded frame count equals the expected count (no missing frames). It also checks that an audio stream is present and that audio and video durations match within 100 ms. A failed `ffprobe` means the file is corrupt.
* **Bracket**: `validate_bracket` checks that winners are participants and that the progression is consistent.
* **Unit tests**: `python -m pytest tests -q` covers determinism, scoring, duration, byes, the technique validator, combination dedup, library versioning, the rig and config.

## Manual review procedure (subjective quality)

Code cannot prove that animation *looks* good. For each tournament:

1. Open `tournaments/<slug>/qa/<match>_contact.png`. It holds frames at every point, K.O., fusion or ultimate callout, and guard break.
   * Is the hit readable in a single frame?
   * Can you tell the fighters apart?
   * Is any text clipped or covering the action?
2. Watch the first 10 s of each match video on a phone.
   * Is the hook clear without sound?
   * Can the names be read in the VS card?
3. Scrub every scoring moment.
   * Is the cause of the point visible: attacker, impact, then defender launched?
4. Check that the slow motion and camera shake on the K.O. are not excessive.
5. Watch `highlights.mp4` once with sound. Listen for clipping, missing hit sounds, and music ducking on points.
6. Log any issue with the match id and video timestamp. Most visual settings can be changed in `config.yaml` (`creative.*`) without code changes.
