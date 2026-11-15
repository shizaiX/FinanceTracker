"""Procedural arena generation.

Every tournament gets its own set of arenas: a biome (from the theme) is turned
into a concrete scene with a generated name, palette variation, time of day,
weather and prop layout seed. Generated arenas are saved to the library.
"""
from __future__ import annotations

import colorsys

from ..core.mathutil import hex_to_rgb, rgb_to_hex

# far: background silhouette layer type; props: mid-ground prop types;
# ground: floor style; skies: (top, horizon) options per time of day.
BIOMES = {
    # -------- pirates
    "ship_deck": dict(far="sea", props=["mast", "cannon", "barrel", "crate", "rigging"], ground="planks", ambient="spray",
                      skies={"day": ("#2a6fb0", "#f7d9a0"), "dusk": ("#2a1a4a", "#ff8a4a"), "night": ("#050a1c", "#1d3a5c")},
                      far_c="#163a5c", mid_c="#3a2414", ground_c="#6b4423", accent="#ffd9a0",
                      names=["Deck of the {adj} {noun}", "The {adj} {noun}"], adj=["Crimson", "Black", "Salty", "Drowned", "Golden", "Howling"],
                      noun=["Revenge", "Gull", "Maiden", "Serpent", "Doubloon", "Kraken"]),
    "tropical_cove": dict(far="sea", props=["palm", "chest", "rock", "barrel", "palm"], ground="sand", ambient="spray",
                          skies={"day": ("#1f8ad6", "#bff0ff"), "dusk": ("#3a1a5a", "#ff9a5a")},
                          far_c="#1a6a8a", mid_c="#24402a", ground_c="#d8b878", accent="#fff2b0",
                          names=["{adj} Cove", "{noun} Island"], adj=["Skull", "Smuggler's", "Parrot", "Treasure", "Coral"],
                          noun=["Cutthroat", "Doubloon", "Mermaid", "Coconut", "Lagoon"]),
    "storm_deck": dict(far="sea", props=["mast", "cannon", "barrel", "rigging"], ground="planks", ambient="rain", lightning=True,
                       skies={"night": ("#05070f", "#2a3446"), "storm": ("#0a0f1a", "#3a4a5a")},
                       far_c="#0f1a26", mid_c="#2a1a10", ground_c="#4a3220", accent="#9fd0ff",
                       names=["The {adj} Squall", "Deck of the {noun}"], adj=["Tempest", "Thundering", "Wailing"],
                       noun=["Maelstrom", "Leviathan", "Widowmaker"]),
    "skull_cave": dict(far="cave", props=["gold_pile", "chest", "torch", "bones", "gold_pile"], ground="stone", ambient="motes",
                       skies={"night": ("#08060a", "#2a1a12")},
                       far_c="#1a120e", mid_c="#2a1e16", ground_c="#3a2c22", accent="#ffc04a",
                       names=["{adj} Grotto", "Cave of {noun}"], adj=["Skull", "Gilded", "Cursed"], noun=["Plunder", "Bones", "Lost Gold"]),
    # -------- dragons
    "volcano_lair": dict(far="volcanoes", props=["rock_spire", "bones", "gold_pile", "lava_fall"], ground="lava", ambient="ember",
                         skies={"night": ("#120404", "#6a1a08"), "dusk": ("#2a0a06", "#ff5a1a")},
                         far_c="#2a0c08", mid_c="#3a140c", ground_c="#1c0e0a", accent="#ff6a2a",
                         names=["{adj} Caldera", "Lair of {noun}"], adj=["Molten", "Ashen", "Infernal", "Smoldering"],
                         noun=["the Wyrm", "Embers", "the Ancient One", "Cinders"]),
    "sky_peaks": dict(far="clouds", props=["floating_rock", "rock_spire", "floating_rock"], ground="stone", ambient="motes",
                      skies={"day": ("#3a8ae0", "#e0f4ff"), "dusk": ("#4a2a7a", "#ffb08a")},
                      far_c="#8ab8e0", mid_c="#4a5a70", ground_c="#5a5a62", accent="#ffffff",
                      names=["{adj} Aerie", "Peak of {noun}"], adj=["Cloudspire", "Windswept", "Highborne"], noun=["Wings", "the Storm", "Skies"]),
    "frozen_den": dict(far="mountains", props=["crystals", "rock_spire", "bones"], ground="ice", ambient="snow",
                       skies={"day": ("#3a7ab0", "#d8f4ff"), "night": ("#061a2a", "#3b7ea8")},
                       far_c="#a8c8e0", mid_c="#2a4a6a", ground_c="#8ab8d8", accent="#e8fbff",
                       names=["{adj} Den", "Glacier of {noun}"], adj=["Rimeclaw", "Frostfang", "Pale"], noun=["Silence", "the Frost Wyrm"]),
    "dragon_ruins": dict(far="mountains", props=["column", "arch", "column", "bones"], ground="stone", ambient="dust",
                         skies={"day": ("#4a7ab0", "#f0e0b0"), "dusk": ("#3a1a3a", "#ff9a5a")},
                         far_c="#5a4a5a", mid_c="#4a3e36", ground_c="#5a4a3a", accent="#ffd27a",
                         names=["Ruins of {noun}", "{adj} Sanctum"], adj=["Forgotten", "Shattered", "Elder"], noun=["Drakmor", "the First Flame", "Valyrn"]),
    # -------- ninjas
    "dojo": dict(far="dojo_wall", props=["lantern", "paper_screen", "lantern"], ground="tatami", ambient="motes",
                 skies={"night": ("#1a0e08", "#3a2414"), "day": ("#3a2414", "#7a5434")},
                 far_c="#e8d8b0", mid_c="#2a1a10", ground_c="#b89a5a", accent="#ffcc7a",
                 names=["{adj} Dojo", "Hall of {noun}"], adj=["Silent Leaf", "Crimson Lotus", "Iron Bamboo"], noun=["Shadows", "the Blade", "Stillness"]),
    "bamboo_forest": dict(far="bamboo", props=["bamboo", "lantern", "bamboo"], ground="grass", ambient="leaves",
                          skies={"day": ("#4a8a5a", "#e0f0c0"), "dusk": ("#2a1a3a", "#ff9a6a")},
                          far_c="#2a5a32", mid_c="#1a3a1e", ground_c="#2a3a1a", accent="#c8ff9a",
                          names=["{adj} Grove", "Bamboo of {noun}"], adj=["Whispering", "Hidden", "Jade"], noun=["the Moon", "Wind"]),
    "night_rooftops": dict(far="city", props=["chimney", "lantern", "antenna"], ground="tiles", ambient="rain",
                           skies={"night": ("#04040e", "#1a1a3a")},
                           far_c="#0e0e22", mid_c="#16162a", ground_c="#2a2a3a", accent="#ff4fd8",
                           names=["{adj} Rooftops", "Above {noun}"], adj=["Neon", "Midnight", "Rain-slick"], noun=["the City", "District 9", "Old Town"]),
    # -------- knights / wizards
    "castle_courtyard": dict(far="castle", props=["banner", "torch", "column"], ground="stone", ambient="dust",
                             skies={"day": ("#3a7ad0", "#f0f0d0"), "dusk": ("#2a1a3a", "#ff8a4a")},
                             far_c="#5a5a6a", mid_c="#3a3a4a", ground_c="#6a6a6a", accent="#ffd27a",
                             names=["{adj} Keep", "Courtyard of {noun}"], adj=["Ironhold", "Lionheart", "Ravenstone"], noun=["Kings", "Valor"]),
    "tourney_field": dict(far="forest", props=["tent", "banner", "tent"], ground="grass", ambient="leaves",
                          skies={"day": ("#3a8ae0", "#f0f8e0")},
                          far_c="#2a5a2a", mid_c="#3a3a2a", ground_c="#3a6a2a", accent="#ffe08a",
                          names=["{adj} Lists", "Field of {noun}"], adj=["Royal", "Golden"], noun=["Honor", "Lances"]),
    "arcane_tower": dict(far="mountains", props=["crystals", "monolith", "floating_rock"], ground="stone", ambient="motes",
                         skies={"night": ("#0a0418", "#3a1a6a")},
                         far_c="#1a0e2e", mid_c="#2a1a44", ground_c="#2a2236", accent="#c87dff",
                         names=["{adj} Spire", "Tower of {noun}"], adj=["Astral", "Runebound", "Violet"], noun=["Stars", "Secrets"]),
    "enchanted_forest": dict(far="forest", props=["tree", "mushroom", "tree"], ground="grass", ambient="motes",
                             skies={"night": ("#04140a", "#1f5a3e")},
                             far_c="#0e2e1a", mid_c="#164020", ground_c="#0a1d0e", accent="#a8ffd8",
                             names=["{adj} Wood", "Glade of {noun}"], adj=["Faerie", "Moonlit", "Whispering"], noun=["Wonders", "Spells"]),
    # -------- generic / elemental (also used for unknown themes)
    "caldera": dict(far="volcanoes", props=["rock_spire"], ground="lava", ambient="ember", skies={"night": ("#1a0505", "#5a1408")},
                    far_c="#2a0b08", mid_c="#3d120a", ground_c="#1c0c08", accent="#ff6a2a",
                    names=["{adj} Caldera"], adj=["Ashen", "Burning", "Scarlet"], noun=[]),
    "storm_peak": dict(far="mountains", props=["rock_spire"], ground="stone", ambient="rain", lightning=True,
                       skies={"night": ("#05081a", "#1d2a5c")}, far_c="#101a3a", mid_c="#17244c", ground_c="#0c1226", accent="#7fc8ff",
                       names=["{adj} Peak"], adj=["Stormcrown", "Thunderhead", "Howling"], noun=[]),
    "frozen_sanctum": dict(far="mountains", props=["crystals"], ground="ice", ambient="snow", skies={"day": ("#061a2a", "#3b7ea8")},
                           far_c="#14405e", mid_c="#1d5578", ground_c="#0e2b40", accent="#bff2ff",
                           names=["{adj} Sanctum"], adj=["Frozen", "Glacial", "Silent"], noun=[]),
    "elder_grove": dict(far="forest", props=["tree"], ground="grass", ambient="leaves", skies={"day": ("#04140a", "#1f5a2e")},
                        far_c="#0e2e16", mid_c="#164020", ground_c="#0a1d0e", accent="#a8ff7a",
                        names=["{adj} Grove"], adj=["Elder", "Verdant", "Thornwild"], noun=[]),
    "abyssal_shrine": dict(far="mountains", props=["arch", "monolith"], ground="stone", ambient="motes", skies={"night": ("#07030f", "#2e0f4a")},
                           far_c="#1a0a2c", mid_c="#26103e", ground_c="#100618", accent="#c77dff",
                           names=["{adj} Shrine"], adj=["Abyssal", "Umbral", "Hollow"], noun=[]),
    "sunken_coliseum": dict(far="sea", props=["column"], ground="stone", ambient="bubbles", skies={"night": ("#020c14", "#0d4a63")},
                            far_c="#082a3a", mid_c="#0c3a4f", ground_c="#06202c", accent="#5fe3ff",
                            names=["{adj} Coliseum"], adj=["Sunken", "Drowned", "Tidal"], noun=[]),
    "golden_dunes": dict(far="dunes", props=["monolith", "column"], ground="sand", ambient="dust", skies={"day": ("#1a0c02", "#a85a14")},
                         far_c="#5a300c", mid_c="#7a4412", ground_c="#2c1806", accent="#ffd27a",
                         names=["{adj} Dunes"], adj=["Golden", "Endless", "Sunscorched"], noun=[]),
    "starfall_rift": dict(far="mountains", props=["monolith", "floating_rock"], ground="metal", ambient="stars", skies={"night": ("#000004", "#141040")},
                          far_c="#0a0a24", mid_c="#141436", ground_c="#07071a", accent="#9ab0ff",
                          names=["{adj} Rift"], adj=["Starfall", "Nebula", "Void"], noun=[]),
}


def _shift(hexc, dh, ds=0.0, dv=0.0):
    r, g, b = hex_to_rgb(hexc)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return rgb_to_hex(colorsys.hsv_to_rgb((h + dh) % 1.0, min(1, max(0, s + ds)), min(1, max(0, v + dv))))


def generate_arena(biome_key, rng, uid):
    b = BIOMES.get(biome_key) or BIOMES["caldera"]
    tod = rng.choice(sorted(b["skies"]))
    top, hor = b["skies"][tod]
    dh = rng.uniform(-0.035, 0.035)
    adj = rng.choice(b["adj"]) if b["adj"] else ""
    noun = rng.choice(b["noun"]) if b["noun"] else ""
    name = rng.choice(b["names"]).format(adj=adj, noun=noun).strip()
    return {
        "id": uid, "name": name, "biome": biome_key, "time_of_day": tod,
        "sky": [_shift(top, dh), _shift(hor, dh)],
        "far": _shift(b["far_c"], dh), "mid": _shift(b["mid_c"], dh, 0, rng.uniform(-0.04, 0.04)),
        "ground": _shift(b["ground_c"], dh), "accent": _shift(b["accent"], dh),
        "far_type": b["far"], "props_list": list(b["props"]), "ground_style": b["ground"],
        "ambient": b["ambient"], "lightning": b.get("lightning", False) or (tod == "storm"),
        "ships": biome_key in ("ship_deck", "tropical_cove", "storm_deck"),
        "celestial": "moon" if tod in ("night", "storm") else ("none" if b["far"] in ("cave", "dojo_wall") else "sun"),
        "layout_seed": rng.randrange(1 << 30),
        "props": b["props"][0] if b["props"] else "spires",
    }


def tournament_arenas(theme, rounds, rng, tournament_id):
    """One arena per round (fresh for every tournament), distinct biomes first."""
    biomes = list(theme.get("biomes") or ["caldera", "storm_peak", "frozen_sanctum"])
    rng.shuffle(biomes)
    out = []
    for r in range(rounds):
        out.append(generate_arena(biomes[r % len(biomes)], rng.stream("arena", r), f"arena_{tournament_id}_{r}"))
    return out
