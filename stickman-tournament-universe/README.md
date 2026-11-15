# Stickman Tournament Universe

You pick a theme, a number of fighters and a number of abilities per fighter. The engine generates the rest of a stickman tournament: the ability set, fighters, techniques and fusions, AI-driven fights, choreography, camera, VFX, sound, the bracket, and vertical 1080×1920 / 60 fps videos.

```bash
pip install -r requirements.txt          # pycairo, numpy, pyyaml, pillow (+ ffmpeg on PATH)
python -m stu new --theme elements --participants 8 --abilities 2
```

The `elements` example above produces this:

```
exports/<tournament>/
├── tournament_bracket.json
├── bracket_reveal.mp4          # first-round bracket reveal
├── round_01/match_001.mp4 …    # one video per fight (+ match_XXX.json metadata)
├── bracket_round_02.mp4        # bracket progression card(s)
├── semifinals/ final/
├── champion.mp4
├── complete_tournament.mp4
├── highlights.mp4 (+ highlights/ clips)
└── metadata.json               # titles / descriptions / tags
```

## Commands

| Command | What it does |
|---|---|
| `python -m stu new [--theme T --participants N --abilities K --seed S]` | Create a tournament and produce all of its videos |
| `python -m stu match --theme elements` | Demo: produce only the first match |
| `python -m stu resume tournaments/<slug>` | Pick up an interrupted run, at chunk level |
| `python -m stu validate tournaments/<slug>` | Run QA again on all outputs |
| `python -m stu new … --no-render` | Simulate and validate without rendering |
| `python -m stu new … --preview` | Quick 540×960 @ 30 fps draft, not for publishing |
| `python -m stu themes list` / `themes create "<any theme>"` | Show the saved themes, or generate a new theme pack (Claude-designed when credentials are available) |
| `python -m stu themes prompt "<theme>"` / `themes import "<theme>" pack.json` | Print the pack-design prompt + JSON schema (e.g. to use in claude.ai), and import a pack JSON through the same validator |
| `python -m stu library stats \| backup \| export f.zip \| import f.zip` | Manage the persistent libraries |
| `python -m stu new … --set video.fps=60 --set tournament.points_to_win=3` | Override any setting |
| `python -m pytest tests -q` | Run the test suite |

## Configuration

Settings live in `config.yaml`. Only `theme`, `participants` and `abilities_per_fighter` are essential. Every other key is optional or `"auto"`. The engine resolves each `"auto"` value and saves the result in the tournament state. That includes `random_seed: null`, so every run can be reproduced exactly.

## How it works (short)

* **Themes** (`stu/themes`): a theme package defines the abilities, real weapons, costume parts, arena biomes and how much plain fist-fighting suits the theme.
  * Built-in packs (`stu/themes/packs.py`): elements, pirates, dragons, ninjas, knights, wizards, weapons, superpowers, cosmic.
  * **New themes are designed by Claude** (`stu/themes/ai_pack.py`): any theme name that isn't a built-in pack is sent once to Claude (`claude-opus-5-5`, structured JSON output). Claude picks abilities, their weapons, powers and projectiles, the costume parts, how much fist-fighting suits the theme and 3–5 arenas. It can also define brand-new weapons (from weapon class, length, head, guard, stock and colours) and brand-new arena biomes (backdrop, props, floor, weather, sky colours, name templates). The JSON schema's enums are the engine's drawable catalogues and the result is validated again locally, so everything generated can be simulated and rendered. The pack is saved to `themes/` and reused, so Claude is called once per theme. Needs `pip install anthropic` and credentials (`ANTHROPIC_API_KEY` or `ant auth login`). The request enables server-side refusal fallbacks. `creative.theme_generator`: `auto` (default) / `claude` / `offline`.
  * Without credentials, names are *composed* from packs ("space pirates" = cosmic + pirates) or, if nothing matches, built procedurally from the archetype catalogue with generic looks.
  * Included example: `themes/wild_west.json` was designed in this format (revolvers, a coach gun, bowie knives, tomahawks, dynamite, lassos, dust devils, stampedes; main street, canyon railway and saloon arenas). `tests/fixtures/wild_west_pack.json` is the raw pack.
  * `--abilities-list "Laser, Jetpack, …"` maps custom ability names onto archetypes through a keyword lexicon.
  * Packages are saved in `themes/` and upgraded/expanded later instead of being overwritten.
* **No out-of-theme weapons**: a physical ability without a melee weapon (rum bottle, pistol, keg, …) can never "summon a blade"; glowing energy blades are reserved for supernatural powers. Saved repertoires are re-validated before every fight.
* **Theme-first combat**: every ability gets its own close-range and ranged techniques built from its weapon or power. Weapons and martial skills cost little energy, powers cost more. Plain unarmed moves only appear in proportion to the theme (elements ≈ 8 %, pirates/knights ≈ 5 % of techniques in testing).
* **Visual identity** (`stu/rendering/{weapons,costume,arena_art}.py`):
  * About 30 procedurally drawn weapons: cutlass, katana, longsword, dagger, claws, spear, harpoon, trident, lance, war hammer, anchor, axe, mace, staff, wand, flintlock, blunderbuss, musket, longbow, crossbow, shield, gauntlets…
  * Weapon-specific animation: slashes, thrusts, overhead smashes, aimed shots with muzzle flash and smoke, lobbed bombs/bottles on real arcs, dragon breath from the mouth.
  * Costume parts: tricorne, captain hat, bandana, eyepatch, beard, hook hand, peg leg, parrot, dragon horns, wings, tails, back spikes, knight helm, plume, cape, crown, wizard hat, hood, ninja mask, horned helmet, cowboy hat…
  * Elemental strikes are visibly elemental: the striking fist/foot/mouth burns, crackles or frosts with a trail of the element.
* **Arenas** (`stu/themes/arenas.py`): every tournament generates its own arenas (one per round) from the theme's biomes, with a new name, time of day, palette shift, weather and prop layout. Biomes include ship decks (sea, sailing ships, masts, rigging, cannons, railing), tropical coves, storm decks with lightning, treasure caves, volcano lairs, cloud peaks, frozen dens, dragon ruins, dojos, bamboo forests, neon rooftops, castle courtyards, tourney fields, arcane towers and enchanted forests.
* **Techniques** (`stu/combat/techniques.py`): each technique is built from a movement, a delivery, modifiers, a timing and abilities. Every candidate goes through a validator first, which rejects logically or visually nonsensical constructions. Valid techniques get a content-hash id, so a technique is never stored twice.
* **Fusions** (`stu/combat/combinations.py`): about 60 tag-reaction rules (heat+gas → Firestorm, electric+fluid → Conductive, …), plus form/effect infusion.
  * Rejected: redundant pairs, incompatible pairs, and triples that would be unreadable.
* **Fights** (`stu/combat/simulation.py`, `ai.py`, `director.py`): a deterministic 120 Hz simulation with articulated IK skeletons, swept collision detection, projectiles, beams, environmental strikes and ground zones with element reactions. It also covers blocks, dodges, counters, grabs, combos and combo breakers.
  * **AI**: a utility-based AI with personalities and a human-like reaction delay. It adapts to the opponent's habits and occasionally improvises new techniques mid-fight. Those dynamic discoveries are saved to the library.
  * **Director**: shapes the intensity curve (opening → tactical → escalation → climax) and the choreography archetype. Pacing is symmetric and never picks a winner. It guarantees that the winning point cannot land before the minimum duration.
* **Rendering** (`stu/rendering`): pycairo vector rendering, with parallel and resumable chunks streamed into FFmpeg.
  * Includes a cinematic camera, slow motion and hit-stop. These are render-side only and cannot change results.
  * Every effect is spawned by an event and computed analytically. HUD layout respects mobile safe zones.
  * A video opens with a cold-open hook, then an intro and VS card.
* **Audio** (`stu/audio`): all sounds are synthesised procedurally (no third-party assets) and placed through the same time map as the video. Includes a procedural music bed with ducking and normalisation. Silent export: `--set creative.sound_effects=false --set creative.music=off`.
* **QA** (`stu/qa`): automatic checks on scoring, duration, bone lengths, teleports, hit positions, resolution, fps, frame count, A/V sync and decodability. Each match also gets a contact sheet for manual review (see `docs/QA.md`).

See `docs/ARCHITECTURE.md` for the full design.
