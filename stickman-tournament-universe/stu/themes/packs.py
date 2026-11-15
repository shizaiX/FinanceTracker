"""Theme knowledge packs: weapons, costumes, theme-specific archetypes and
complete theme definitions (abilities + costume pools + arena biomes).

Everything here is *data*. The renderer draws every weapon and costume part
procedurally from these parameters, so new themes can combine parts freely.
"""

# ---------------------------------------------------------------------------
# Weapon catalogue. class drives animation, reach, hit detection and drawing.
#   blade | polearm | blunt | firearm | bow | staff | claws | shield | fist
# len = metres from the hand along the forearm. colors = [edge/metal, mid, grip]
# ---------------------------------------------------------------------------
METAL = ["#f4f7fb", "#aab6c4", "#5b4127"]
WEAPONS = {
    "cutlass":     {"class": "blade", "len": 0.82, "curve": 0.2, "w": 0.075, "guard": "basket", "colors": METAL},
    "katana":      {"class": "blade", "len": 1.0, "curve": 0.08, "w": 0.05, "guard": "tsuba", "colors": ["#ffffff", "#c9d3df", "#2a1f3a"]},
    "longsword":   {"class": "blade", "len": 1.05, "curve": 0.0, "w": 0.07, "guard": "cross", "colors": METAL},
    "sabre":       {"class": "blade", "len": 0.9, "curve": 0.14, "w": 0.06, "guard": "cross", "colors": METAL},
    "scimitar":    {"class": "blade", "len": 0.85, "curve": 0.32, "w": 0.09, "guard": "cross", "colors": METAL},
    "dagger":      {"class": "blade", "len": 0.36, "curve": 0.0, "w": 0.06, "guard": "cross", "colors": METAL},
    "kunai":       {"class": "blade", "len": 0.34, "curve": 0.0, "w": 0.07, "guard": "ring", "colors": ["#e6ebf2", "#79808c", "#1f1f28"]},
    "claws":       {"class": "claws", "len": 0.3, "colors": ["#fff6e0", "#e8d6a8", "#6a5030"]},
    "spear":       {"class": "polearm", "len": 1.55, "head": "leaf", "colors": ["#f4f7fb", "#aab6c4", "#7a5534"]},
    "harpoon":     {"class": "polearm", "len": 1.4, "head": "barb", "colors": ["#e8eef4", "#8f9aa6", "#6b4a2a"]},
    "trident":     {"class": "polearm", "len": 1.45, "head": "trident", "colors": ["#fff2b0", "#d4a83a", "#5b4127"]},
    "glaive":      {"class": "polearm", "len": 1.45, "head": "blade", "colors": METAL},
    "lance":       {"class": "polearm", "len": 1.85, "head": "cone", "colors": ["#ffffff", "#c8cfd8", "#8a2a2a"]},
    "war_hammer":  {"class": "blunt", "len": 0.95, "head": "block", "colors": ["#e0e4ea", "#7d8794", "#5b4127"]},
    "mace":        {"class": "blunt", "len": 0.8, "head": "spiked", "colors": METAL},
    "anchor":      {"class": "blunt", "len": 1.05, "head": "anchor", "colors": ["#c8ccd2", "#5d646e", "#3a2a1a"]},
    "axe":         {"class": "blunt", "len": 0.85, "head": "axe", "colors": METAL},
    "club":        {"class": "blunt", "len": 0.8, "head": "club", "colors": ["#c79a62", "#8a5f33", "#5b4127"]},
    "staff":       {"class": "staff", "len": 1.5, "head": "orb", "colors": ["#ffffff", "#c9a36a", "#5b3a1e"]},
    "wand":        {"class": "staff", "len": 0.42, "head": "star", "colors": ["#ffffff", "#e8d6ff", "#3a2a1a"]},
    "flintlock":   {"class": "firearm", "len": 0.42, "stock": "pistol", "colors": ["#d8dde4", "#4a4f57", "#6b4122"]},
    "revolver":    {"class": "firearm", "len": 0.36, "stock": "pistol", "colors": ["#e6e9ee", "#5a5f68", "#3a2516"]},
    "blunderbuss": {"class": "firearm", "len": 0.62, "stock": "flare", "colors": ["#e8c070", "#8a6a2a", "#6b4122"]},
    "musket":      {"class": "firearm", "len": 1.1, "stock": "rifle", "colors": ["#d8dde4", "#4a4f57", "#6b4122"]},
    "longbow":     {"class": "bow", "len": 1.3, "colors": ["#ffffff", "#b07a3c", "#5b3a1e"]},
    "crossbow":    {"class": "bow", "len": 0.7, "colors": ["#ffffff", "#8a6a3a", "#3a2a1a"]},
    "shield":      {"class": "shield", "len": 0.48, "colors": ["#ffffff", "#9aa8ba", "#3a5aa8"]},
    "gauntlets":   {"class": "fist", "len": 0.0, "colors": ["#ffffff", "#c0c8d2", "#5a6470"]},
    "chakram":     {"class": "fist", "len": 0.0, "colors": METAL},
}


def weapon_class(key):
    return WEAPONS.get(key, {}).get("class") if key else None


# ---------------------------------------------------------------------------
# Costume parts (all drawn procedurally by the renderer).
# slot: head | face | body | back | hand | leg
# ---------------------------------------------------------------------------
COSTUMES = {
    "tricorne": "head", "captain_hat": "head", "bandana": "head", "straw_hat": "head", "headband": "head",
    "ninja_mask": "head", "topknot": "head", "knight_helm": "head", "crown": "head", "wizard_hat": "head",
    "horned_helmet": "head", "cowboy_hat": "head", "hood": "head", "dragon_horns": "head", "spikes": "head",
    "horns": "head", "halo": "head", "visor": "head", "ponytail": "head",
    "eyepatch": "face", "beard": "face",
    "scarf": "body", "cape": "back", "wings": "back", "tail": "back", "back_spikes": "back", "parrot": "body",
    "plume": "head", "hook_hand": "hand", "peg_leg": "leg",
}

# ---------------------------------------------------------------------------
# Additional archetypes (merged into catalog.ARCHETYPES)
# ---------------------------------------------------------------------------
EXTRA_ARCHETYPES = {
    "firearm": {
        "tags": ["ranged", "precise", "volatile"],
        "colors": ["#fff6d0", "#ffbe55", "#8a5a2a"],
        "particle": "spark", "projectile": "bullet", "aura": "dust", "zone": None,
        "env_form": "cannon_rain", "mobility": "dash", "voice": "gunshot", "weapon": "flintlock",
        "affinity": {"projectile": 1.0, "counter": 0.55, "punch": 0.35, "explosion": 0.3},
        "mod_affinity": {"pierce": 0.9, "split": 0.6, "chain": 0.3},
        "stats": {"power": 1.1, "speed": 1.05, "control": 1.1, "defense": 0.85},
        "words": {"adj": ["Deadeye", "Smoking", "Quickdraw", "Point-Blank"], "noun": ["Shot", "Volley", "Broadside", "Bullet"]},
    },
    "explosive": {
        "tags": ["volatile", "heat", "force"],
        "colors": ["#fff2c0", "#ff8a2a", "#3a2a22"],
        "particle": "flame", "projectile": "bomb", "aura": "dust", "zone": "burning", "gravity": True,
        "env_form": "cannon_rain", "mobility": "dash", "voice": "fire",
        "affinity": {"projectile": 1.0, "explosion": 0.9, "env_strike": 0.8},
        "mod_affinity": {"delayed": 1.0, "amplify": 0.9, "trap": 0.8, "split": 0.5},
        "stats": {"power": 1.25, "speed": 0.9, "control": 0.85, "defense": 0.85},
        "words": {"adj": ["Powder", "Blasting", "Fused", "Kaboom"], "noun": ["Keg", "Bomb", "Barrage", "Blast"]},
    },
    "thrown": {
        "tags": ["ranged", "sharp", "fast"],
        "colors": ["#ffffff", "#c6ced8", "#3a3f4a"],
        "particle": "metal", "projectile": "knife", "aura": "gust", "zone": None,
        "env_form": "sky_strike", "mobility": "dash", "voice": "metal", "weapon": "dagger",
        "affinity": {"projectile": 1.0, "summon_weapon": 0.8, "counter": 0.5},
        "mod_affinity": {"split": 1.0, "homing": 0.5, "pierce": 0.7},
        "stats": {"power": 0.95, "speed": 1.2, "control": 1.15, "defense": 0.85},
        "words": {"adj": ["Flicking", "Fan of", "Silent", "Whistling"], "noun": ["Knives", "Blades", "Daggers", "Throw"]},
    },
    "toxic": {
        "tags": ["organic", "bind", "fluid"],
        "colors": ["#f0ffd0", "#9be33a", "#3b6a12"],
        "particle": "droplet", "projectile": "orb", "aura": "wisp", "zone": "toxic",
        "env_form": "geyser", "mobility": "slide", "voice": "water",
        "affinity": {"projectile": 1.0, "beam": 0.8, "env_strike": 0.8, "explosion": 0.6},
        "mod_affinity": {"trap": 1.0, "delayed": 0.7, "homing": 0.6},
        "stats": {"power": 0.95, "speed": 1.0, "control": 1.2, "defense": 0.95},
        "words": {"adj": ["Venomous", "Toxic", "Acidic", "Blighted"], "noun": ["Venom", "Spit", "Bile", "Miasma"]},
    },
}

# ---------------------------------------------------------------------------
# Theme packs. Each ability: (name, archetype, overrides)
#   physical_weight: how much plain (non-ability) fist-fighting suits the theme.
# ---------------------------------------------------------------------------
BREATH = {"origin": "mouth"}

THEME_PACKS = {
    "elements": {
        "title": "Elemental", "physical_weight": 0.12,
        "title_words": ["Elemental Chaos", "Primal Clash", "Elemental Ascension", "Storm of Elements"],
        "abilities": [
            ("Fire", "flame", {}), ("Water", "tide", {}), ("Ice", "frost", {}),
            ("Lightning", "storm", {}), ("Earth", "stone", {}), ("Wind", "gale", {}),
            ("Metal", "alloy", {}), ("Nature", "verdant", {}), ("Light", "radiance", {}),
            ("Shadow", "umbra", {}), ("Gravity", "gravity", {}), ("Sound", "resonance", {}),
        ],
        "costumes": ["headband", "scarf", "spikes", "horns", "halo", "ponytail", "visor", "topknot", "cape"],
        "biomes": ["caldera", "storm_peak", "frozen_sanctum", "elder_grove", "abyssal_shrine", "sunken_coliseum", "golden_dunes", "starfall_rift"],
    },
    "pirates": {
        "title": "Pirate", "physical_weight": 0.18,
        "title_words": ["Skull & Cutlass Cup", "Seven Seas Brawl", "Black Flag Tournament", "Plunder Royale"],
        "abilities": [
            ("Cutlass", "blade", {"weapon": "cutlass", "physical": True}),
            ("Flintlock", "firearm", {"weapon": "flintlock", "physical": True}),
            ("Blunderbuss", "firearm", {"weapon": "blunderbuss", "physical": True, "mod_affinity": {"split": 1.4, "pierce": 0.3},
                                        "words": {"adj": ["Scattershot", "Boom", "Grapeshot"], "noun": ["Blast", "Spray", "Boom"]}}),
            ("Throwing Knives", "thrown", {"weapon": "dagger", "physical": True}),
            ("Powder Keg", "explosive", {"physical": True}),
            ("Anchor", "hammer", {"weapon": "anchor", "physical": True, "colors": ["#e0e4ea", "#6a727c", "#2a2f36"],
                                  "words": {"adj": ["Sunken", "Iron", "Deep"], "noun": ["Anchor", "Drop", "Plunge"]}}),
            ("Harpoon", "polearm", {"weapon": "harpoon", "physical": True, "projectile": "harpoon",
                                    "words": {"adj": ["Whaler's", "Barbed", "Reeling"], "noun": ["Harpoon", "Spike", "Line"]}}),
            ("Bare-Knuckle Brawl", "kinetic", {"physical": True, "colors": ["#ffffff", "#ffd2a0", "#c2552a"],
                                                "words": {"adj": ["Tavern", "Knuckle", "Deckhand"], "noun": ["Haymaker", "Brawl", "Knuckle"]}}),
            ("Cannon Fire", "explosive", {"physical": True, "projectile": "cannonball", "env_form": "cannon_rain",
                                          "words": {"adj": ["Broadside", "Cannon", "Thundering"], "noun": ["Cannonade", "Broadside", "Salvo"]}}),
            ("Kraken's Call", "tide", {"env_form": "tentacles", "colors": ["#e0f0ff", "#4a9ac0", "#1d3a5a"],
                                       "words": {"adj": ["Kraken", "Abyssal", "Leviathan"], "noun": ["Tentacle", "Grasp", "Maw"]}}),
            ("Rum Bottle", "explosive", {"physical": True, "projectile": "bottle", "zone": "burning",
                                         "words": {"adj": ["Flaming", "Drunken", "Grog"], "noun": ["Bottle", "Toss", "Grog"]}}),
        ],
        "costumes": ["tricorne", "captain_hat", "bandana", "eyepatch", "beard", "hook_hand", "peg_leg", "parrot"],
        "costume_rules": {"head": 1, "extras": (1, 3)},
        "biomes": ["ship_deck", "tropical_cove", "storm_deck", "skull_cave"],
    },
    "dragons": {
        "title": "Dragon", "physical_weight": 0.15,
        "title_words": ["Dragonfire Trials", "Wyrm Crown", "Clash of Dragons", "Hoard Wars"],
        "abilities": [
            ("Fire Breath", "flame", dict(BREATH)), ("Frost Breath", "frost", dict(BREATH)),
            ("Storm Breath", "storm", dict(BREATH)), ("Venom Spit", "toxic", dict(BREATH)),
            ("Dragon Claws", "blade", {"weapon": "claws", "physical": True, "colors": ["#fff6e0", "#ffcf7a", "#a8641e"],
                                       "words": {"adj": ["Rending", "Talon", "Raking"], "noun": ["Claw", "Talon", "Rake"]}}),
            ("Tail Lash", "kinetic", {"physical": True, "affinity": {"sweep": 1.2, "kick": 1.0, "charge": 0.7, "punch": 0.05, "uppercut": 0.1, "barrage": 0.05, "grapple": 0.1},
                                      "words": {"adj": ["Lashing", "Spiked", "Whiplash"], "noun": ["Tail", "Lash", "Sweep"]}}),
            ("Great Wings", "gale", {"words": {"adj": ["Skyborne", "Wingbeat", "Soaring"], "noun": ["Gust", "Downdraft", "Wingstorm"]}}),
            ("Scale Armor", "aegis", {"colors": ["#ffffff", "#c8a85a", "#6a4a1a"],
                                      "words": {"adj": ["Scaled", "Ironhide", "Ancient"], "noun": ["Scales", "Bulwark", "Carapace"]}}),
            ("Ancient Roar", "resonance", dict(BREATH)),
            ("Earthshaker", "stone", {"words": {"adj": ["Quaking", "Wyrm", "Titanic"], "noun": ["Stomp", "Quake", "Tremor"]}}),
        ],
        "costumes": ["dragon_horns", "wings", "tail", "back_spikes"],
        "costume_rules": {"head": 1, "extras": (2, 3), "always": ["dragon_horns"]},
        "biomes": ["volcano_lair", "sky_peaks", "frozen_den", "dragon_ruins"],
    },
    "ninjas": {
        "title": "Ninja", "physical_weight": 0.22,
        "title_words": ["Hidden Leaf Trials", "Shadow Clan Cup", "Way of the Shinobi"],
        "abilities": [
            ("Katana", "blade", {"weapon": "katana", "physical": True}),
            ("Shuriken", "thrown", {"projectile": "shuriken", "physical": True, "weapon": None,
                                    "words": {"adj": ["Spinning", "Star", "Silent"], "noun": ["Shuriken", "Stars", "Storm"]}}),
            ("Kunai", "thrown", {"weapon": "kunai", "physical": True}),
            ("Smoke Bomb", "umbra", {"colors": ["#f0f0f0", "#9a9aa8", "#3a3a48"], "particle": "smoke",
                                     "words": {"adj": ["Vanishing", "Smoke", "Veiled"], "noun": ["Veil", "Cloud", "Vanish"]}}),
            ("Fire Jutsu", "flame", {}), ("Wind Jutsu", "gale", {}), ("Shadow Clone", "umbra", {}),
            ("Taijutsu", "kinetic", {"physical": True, "words": {"adj": ["Leaf", "Lotus", "Iron"], "noun": ["Whirlwind", "Lotus", "Palm"]}}),
            ("Bo Staff", "polearm", {"weapon": "staff", "physical": True}),
        ],
        "costumes": ["ninja_mask", "headband", "scarf", "topknot", "hood"],
        "costume_rules": {"head": 1, "extras": (1, 2)},
        "biomes": ["dojo", "bamboo_forest", "night_rooftops"],
    },
    "knights": {
        "title": "Knight", "physical_weight": 0.15,
        "title_words": ["Grand Tourney", "Crown of Steel", "Order of the Blade"],
        "abilities": [
            ("Longsword", "blade", {"weapon": "longsword", "physical": True}),
            ("Tower Shield", "aegis", {"weapon": "shield", "physical": True}),
            ("Lance", "polearm", {"weapon": "lance", "physical": True}),
            ("Mace", "hammer", {"weapon": "mace", "physical": True}),
            ("Battle Axe", "hammer", {"weapon": "axe", "physical": True}),
            ("Crossbow", "archery", {"weapon": "crossbow", "physical": True}),
            ("Holy Light", "radiance", {}), ("Dragonfire Oil", "explosive", {"projectile": "bottle"}),
        ],
        "costumes": ["knight_helm", "plume", "cape", "crown", "horned_helmet", "beard"],
        "costume_rules": {"head": 1, "extras": (1, 2)},
        "biomes": ["castle_courtyard", "tourney_field", "dragon_ruins"],
    },
    "wizards": {
        "title": "Arcane", "physical_weight": 0.1,
        "title_words": ["Arcane Duel", "Spellbinder Cup", "Tower of Mages"],
        "abilities": [
            ("Fireball", "flame", {"weapon": "wand"}), ("Frost Nova", "frost", {"weapon": "staff"}),
            ("Arcane Missiles", "radiance", {"weapon": "wand", "colors": ["#ffffff", "#d8a8ff", "#7a3ad0"]}),
            ("Chain Lightning", "storm", {"weapon": "staff"}), ("Necromancy", "umbra", {"weapon": "staff"}),
            ("Telekinesis", "gravity", {}), ("Earth Golem", "stone", {"weapon": "staff"}),
            ("Wild Growth", "verdant", {"weapon": "staff"}), ("Sonic Rune", "resonance", {"weapon": "wand"}),
        ],
        "costumes": ["wizard_hat", "hood", "beard", "cape"],
        "costume_rules": {"head": 1, "extras": (1, 2)},
        "biomes": ["arcane_tower", "enchanted_forest", "starfall_rift"],
    },
    "weapons": {
        "title": "Armory", "physical_weight": 0.2,
        "title_words": ["Steel Tournament", "Blade Royale", "Armory Clash"],
        "abilities": [
            ("Katana", "blade", {"weapon": "katana", "physical": True}), ("Spear", "polearm", {"weapon": "spear", "physical": True}),
            ("War Hammer", "hammer", {"weapon": "war_hammer", "physical": True}), ("Longbow", "archery", {"weapon": "longbow", "physical": True}),
            ("Shield", "aegis", {"weapon": "shield", "physical": True}), ("Gauntlets", "kinetic", {"weapon": "gauntlets", "physical": True}),
            ("Chakrams", "alloy", {"weapon": None, "physical": True}), ("Twin Sabers", "blade", {"weapon": "sabre", "physical": True,
                                                                                            "colors": ["#ffffff", "#ffb0b0", "#c8323c"]}),
            ("Glaive", "polearm", {"weapon": "glaive", "physical": True, "colors": ["#ffffff", "#c8b0ff", "#6a3ad0"]}),
            ("Kunai", "thrown", {"weapon": "kunai", "physical": True}),
            ("Flintlock", "firearm", {"weapon": "flintlock", "physical": True}), ("Battle Axe", "hammer", {"weapon": "axe", "physical": True}),
        ],
        "costumes": ["headband", "scarf", "topknot", "bandana", "horned_helmet", "knight_helm", "cape"],
        "biomes": ["golden_dunes", "caldera", "castle_courtyard", "dojo", "starfall_rift"],
    },
    "superpowers": {
        "title": "Superhuman", "physical_weight": 0.2,
        "title_words": ["Super Showdown", "Power Surge", "Metahuman Masters"],
        "abilities": [
            ("Super Strength", "kinetic", {}), ("Speedster", "storm", {"colors": ["#ffffff", "#ffe38a", "#ff9f1a"]}),
            ("Telekinesis", "gravity", {}), ("Laser Vision", "radiance", {"colors": ["#ffffff", "#ff9a9a", "#ff2a2a"], "origin": "mouth"}),
            ("Pyrokinesis", "flame", {}), ("Cryokinesis", "frost", {}), ("Force Field", "aegis", {}),
            ("Sonic Scream", "resonance", dict(BREATH)), ("Phasing", "umbra", {}), ("Hydrokinesis", "tide", {}),
        ],
        "costumes": ["cape", "visor", "halo", "spikes", "scarf"],
        "biomes": ["night_rooftops", "storm_peak", "sunken_coliseum", "starfall_rift"],
    },
    "cosmic": {
        "title": "Cosmic", "physical_weight": 0.1,
        "title_words": ["Cosmic Throne", "Galactic Gauntlet", "Nebula Wars"],
        "abilities": [
            ("Supernova", "flame", {"colors": ["#ffffff", "#ffd0f0", "#ff4fd8"]}), ("Black Hole", "gravity", {}),
            ("Starlight", "radiance", {}), ("Comet", "stone", {"colors": ["#ffffff", "#a8c8ff", "#3a5ac8"]}),
            ("Solar Wind", "gale", {"colors": ["#ffffff", "#fff0a0", "#ffb020"]}), ("Void", "umbra", {}),
            ("Pulsar", "resonance", {"colors": ["#ffffff", "#a0fff0", "#20c8b0"]}), ("Plasma", "storm", {"colors": ["#ffffff", "#ffb8ff", "#c040ff"]}),
        ],
        "costumes": ["halo", "visor", "horns", "cape", "spikes"],
        "biomes": ["starfall_rift", "sky_peaks", "abyssal_shrine"],
    },
}

# Keyword -> pack aliases (theme composition: "space pirates" = cosmic + pirates)
PACK_ALIASES = {
    "pirates": ["pirate", "buccaneer", "corsair", "sea dog", "privateer"],
    "dragons": ["dragon", "wyrm", "wyvern", "drake"],
    "ninjas": ["ninja", "shinobi", "samurai", "ronin"],
    "knights": ["knight", "medieval", "paladin", "crusader", "castle", "viking"],
    "wizards": ["wizard", "mage", "magic", "sorcer", "witch", "warlock", "arcane", "spell"],
    "weapons": ["weapon", "armory", "blade", "gladiator"],
    "superpowers": ["super", "hero", "mutant", "power"],
    "cosmic": ["cosmic", "space", "galax", "star", "alien", "planet"],
    "elements": ["element", "elemental", "nature"],
}
