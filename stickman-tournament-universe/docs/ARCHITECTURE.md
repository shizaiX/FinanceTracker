# Architecture

## Stack decision

**Python 3 + pycairo + numpy + FFmpeg.**

* **pycairo**: anti-aliased vector drawing, a good fit for stick figures, glows and text. It renders offline and frame-exact, with no GPU and no browser.
* **Rejected alternatives**:
  * Phaser/PixiJS are real-time engines. Exporting from them adds a headless browser, frame-capture timing problems, and non-determinism.
  * A custom WebGL path would be faster, but harder to keep deterministic and to test.
* **numpy**: audio synthesis and mixing.
* **FFmpeg (libx264)**: production-grade H.264 encoding. Frames are piped in raw, never stored.
* **Measured performance**: about 22 ms per 1080×1920 frame per core. On 4 cores a 90–130 s match renders in about 2–3 minutes.

## Module map

| Layer | Module | Responsibility |
|---|---|---|
| Config | `stu/config.py` | Defaults, overrides, validation, resolution of `auto` values |
| Determinism | `stu/core/rng.py` | Named, independent random streams derived with SHA-256 from the seed |
| Persistence | `stu/persistence/library.py` | Versioned JSON libraries: atomic writes, schema checks and migration, content-hash ids, merge-only updates, backup, import and export |
| Themes | `stu/themes/{catalog,packs,generator,arenas}.py` | Archetypes, weapon/costume catalogues, theme packs, composition, procedural fallback, per-tournament arena generation |
| Fighters | `stu/combat/fighters.py` | Names, distinct colours, accessories, personalities and traits, balanced loadout draft, repertoire |
| Techniques | `stu/combat/techniques.py` | Component catalogues, validator, parameters, names, composer, repertoire builder |
| Fusion | `stu/combat/combinations.py` | Reaction rules, compatibility scoring, combination records |
| Simulation | `stu/combat/{simulation,state}.py` | 120 Hz match loop, physics, entities, collisions, scoring, timeline recording |
| AI | `stu/combat/ai.py` | Utility decisions, reactive defense, adaptation, dynamic discovery |
| Director | `stu/combat/director.py` | Phases, choreography archetypes, pacing and duration guarantees |
| Animation | `stu/animation/{rig,poses}.py` | Skeleton, FK and 2-bone IK, foot planting, keypose templates, blending |
| Rendering | `stu/rendering/*` | Time map, camera, VFX, scene, weapons, costumes, arena art, HUD, cards, encoder |
| Audio | `stu/audio/*` | Synthesis and event-synchronised mixing |
| Tournament | `stu/tournament/*` | Bracket with byes, pipeline and checkpoints, metadata |
| QA | `stu/qa/validate.py` | Match, video and bracket validation, contact sheets |

## Data flow

```
config.yaml ─► resolve_auto ─► Universe (libraries) ─► theme package ─► fighters + repertoires
     ─► bracket ─► for each ready match:
            Match.run()  (deterministic timeline: frames + events)       [cached .pkl.gz]
            validate_match()
            timemap (hook / slow-mo / hit-stop) ─► camera track
            audio mix (same time map) ─► WAV
            parallel chunk render ─► FFmpeg segments ─► concat + mux ─► validate_video()
            record result ─► stats ─► bracket advance           [state.json checkpoint]
     ─► bracket cards ─► champion ─► complete_tournament ─► highlights ─► metadata
```

## Key design guarantees

* **The simulation is the single source of truth.**
  * Rendering, camera, slow motion and audio only read the timeline, so they cannot change a winner.
  * The same seed and libraries reproduce an identical timeline. The suite tests this through a timeline hash.
* **Winners are always simulated.** A point is awarded only through a scoring event:
  1. Hits deplete the defender's *guard* (poise).
  2. An empty guard puts the defender in a *guard-broken* stagger.
  3. A clean hit during the stagger, or an ultimate finisher on a low guard, scores.
* **Hit levels** that are tracked and shown: minor, blocked, combo, significant, guard break, scoring strike, K.O.
* **Duration**:
  * The director spaces points at least 7.5 s apart, and refuses a match-winning point before `minimum_fight_duration_seconds`. An early decisive hit becomes significant damage, and the defender survives.
  * Pacing is a symmetric controller on lethality and defense quality, with no filler. Behind schedule, exchanges get more dangerous for both fighters. Ahead of schedule, they get safer.
  * Near `maximum_fight_duration_seconds`, sudden death applies.
* **No illogical actions**:
  * Melee attacks are available only within reach, or through a movement primitive that closes the distance. A failed approach aborts.
  * Defense happens only after the fighter's reaction delay, and only inside the response window.
  * Projectiles travel, using sub-stepped swept collision.
  * Only teleport abilities move a fighter discontinuously. These are flagged, and QA allows only them.
* **Animation**:
  * Limbs are solved by IK, so bone lengths are exact. QA checks bone lengths on every 4th tick.
  * Feet are planted in world space and step procedurally with arcs, so they don't slide.
  * Actions blend from the previous pose.
  * Every technique stage runs anticipation → action (ease-out-back) → impact hold → recovery.
* **Resumability**:
  * Every match result is cached.
  * Every 600-frame chunk is a separate segment with a `.done` marker.
  * `state.json` records every finished step.

## Library growth

* Techniques composed at fighter creation, and techniques discovered during fights, go to `library/techniques.json`. Discoveries carry their fight context.
* Valid combinations go to `library/combinations.json`.
* Fighters and their careers go to `library/fighters.json`.
* Per-fighter, per-ability and per-technique statistics go to `library/statistics.json`.
* Tournament history goes to `library/tournaments.json`.
* Animation templates go to `library/animations.json`.
* Saved render settings go to `library/render_configs.json`.

## Not done yet / known limits

* Several engine settings are present in the config, validated and saved, but not used yet:
  * The engine does not read `combat.combat_speed` (resolved to 1.0) or `creative.camera` (always the balanced camera style).
  * `creative.subtitles` has no effect.
  * `video.export_individual_fights: false` currently also skips match rendering, so the complete tournament and highlights would come out without fights.
* Only `single_elimination` and the `h264` codec are implemented. `subsequent_matchmaking` is always the winners bracket.
* New themes are designed by Claude, but only from drawable building blocks. The building blocks are: archetypes, ~30 costume parts, weapon classes, projectile styles, 12 backdrops, 26 prop types and 9 floor styles. Claude can invent new *combinations* and new parametric weapons and biomes, but not new costume shapes or prop drawings; those need code in `stu/rendering/costume.py` / `arena_art.py`. Without API credentials, unknown names (e.g. "candy") fall back to generic archetypes and looks.
* Energy blades are only used for powers without a physical weapon (e.g. an elemental "fire blade"); every pack weapon is drawn as itself.
