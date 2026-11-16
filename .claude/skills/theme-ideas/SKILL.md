---
name: theme-ideas
description: Show the list of 50 tournament theme ideas for UltimateStickFightTournaments, and which ones are ready to use. Use when the user types /theme-ideas or asks for theme ideas.
---

# /theme-ideas

Show the user this list exactly (in the language they write in; keep the theme names in English),
then the legend, then one line: "Start one with `/new-tournament <theme> <fighters> <abilities>`,
e.g. `/new-tournament samurai 8 1`."

Before showing it, run `ls stickman-tournament-universe/themes/*.json` and mark every theme that
already has a saved pack with ✅ (built-in packs: elements, pirates, dragons, ninjas, knights,
wizards, weapons, superpowers, cosmic; saved packs: every json file in that folder).
Mark the others with 🆕.

## Classic fantasy & myth
1. Elements
2. Dragons
3. Wizards
4. Knights
5. Greek Gods
6. Norse Vikings
7. Egyptian Pharaohs
8. Samurai
9. Ninjas
10. Demons vs Angels

## Adventure & history
11. Pirates
12. Wild West
13. Gladiators
14. Spartans
15. Aztec Warriors
16. Musketeers
17. Cavemen
18. Mongol Horsemen
19. Medieval Peasants
20. Ancient China Kung Fu

## Sci-fi & future
21. Robots
22. Space Marines
23. Cyberpunk
24. Aliens
25. Cosmic Powers
26. Mechs
27. Time Travelers
28. Laser Swordsmen
29. Post-Apocalypse
30. Bounty Hunters

## Creatures & monsters
31. Animals
32. Dinosaurs
33. Zombies
34. Vampires
35. Werewolves
36. Sea Monsters
37. Insects
38. Mythical Beasts
39. Ghosts
40. Elemental Spirits

## Fun & viral
41. Kitchen Chefs (knives, pans, fire)
42. Sports Athletes (balls, bats, rackets)
43. Office Workers (staplers, coffee, printers)
44. School Supplies (pencils, rulers, erasers)
45. Musicians (guitars, drums, sound)
46. Weather (storms, tornadoes, heat waves)
47. Candy Land
48. Toys
49. Superheroes
50. Emojis

## Legend
- ✅ ready: a theme pack exists, the tournament starts immediately.
- 🆕 new: when chosen, a full theme pack (abilities, weapons, outfits, arenas) is designed first.
  With an Anthropic API key the engine asks Claude automatically; without one, Claude in this chat
  designs the pack (like Cyberpunk and Wild West) and imports it with `python -m stu themes import`.

Do not use real franchises or copyrighted characters as themes (e.g. Mario, Pokémon); offer an
original theme with a similar feel instead.
