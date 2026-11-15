"""Ability fusion engine.

Combinations are discovered from *tags*, never from ability names, so they work
for every theme. A combination is valid only if it is thematically meaningful
(a reaction rule matches, or one ability gives *form* and the other gives
*effect*), not redundant (two copies of the same archetype) and readable
(at most three abilities, every pair compatible).
"""
from __future__ import annotations

import itertools
import time

from ..persistence.library import stable_id

# (tag_a, tag_b, reaction words, effects, preferred deliveries)
REACTIONS = [
    ("heat", "gas", ["Firestorm", "Wildfire", "Combustion"], {"power": 1.2, "area": 1.4}, ["explosion", "projectile", "charge"]),
    ("heat", "cold", ["Steam", "Thermal Shock"], {"poise": 1.3}, ["explosion", "projectile"]),
    ("heat", "fluid", ["Scalding", "Boiling"], {"power": 1.15}, ["beam", "env_strike"]),
    ("heat", "ground", ["Magma", "Molten"], {"power": 1.25, "area": 1.2}, ["env_strike", "slam", "punch"]),
    ("heat", "electric", ["Plasma", "Ionized"], {"power": 1.2, "speed": 1.15}, ["beam", "projectile"]),
    ("heat", "organic", ["Wildfire", "Ashbloom"], {"area": 1.3}, ["env_strike", "projectile"]),
    ("heat", "radiant", ["Solar", "Sunfire"], {"power": 1.2}, ["beam", "explosion"]),
    ("heat", "void", ["Blackflame", "Hellfire"], {"power": 1.15}, ["projectile", "punch"]),
    ("heat", "sharp", ["Searing", "Forge"], {"power": 1.15}, ["summon_weapon", "kick"]),
    ("heat", "wave", ["Thermal Pulse", "Roaring"], {"area": 1.3}, ["explosion"]),
    ("electric", "fluid", ["Conductive", "Electrified"], {"stun": 1.5}, ["beam", "grapple", "env_strike"]),
    ("electric", "gas", ["Thunderstorm", "Tempest"], {"speed": 1.2, "area": 1.2}, ["explosion", "projectile", "kick"]),
    ("electric", "conductive", ["Railgun", "Magnetic"], {"pierce": 1.0, "speed": 1.3}, ["projectile", "summon_weapon"]),
    ("electric", "radiant", ["Photon", "Arc-light"], {"speed": 1.3}, ["beam", "projectile"]),
    ("electric", "void", ["Dark Thunder", "Null Arc"], {"stun": 1.3}, ["projectile", "env_strike"]),
    ("electric", "organic", ["Galvanic", "Thunderroot"], {"stun": 1.3}, ["grapple", "env_strike"]),
    ("electric", "wave", ["Thunderclap", "Static Roar"], {"area": 1.3}, ["explosion", "punch"]),
    ("electric", "kinetic", ["Lightspeed", "Overdrive"], {"speed": 1.3}, ["punch", "charge"]),
    ("cold", "fluid", ["Flash-Freeze", "Hailstorm"], {"stun": 1.3}, ["projectile", "env_strike", "grapple"]),
    ("cold", "gas", ["Blizzard", "Whiteout"], {"area": 1.3}, ["explosion", "projectile"]),
    ("cold", "ground", ["Permafrost", "Glacier"], {"power": 1.15}, ["env_strike", "slam"]),
    ("cold", "radiant", ["Prismatic", "Aurora"], {"pierce": 1.0}, ["beam", "projectile"]),
    ("cold", "void", ["Deathfrost", "Hollow Ice"], {"stun": 1.2}, ["projectile", "env_strike"]),
    ("cold", "wave", ["Shatter", "Cryo Pulse"], {"poise": 1.3}, ["explosion"]),
    ("solid", "gas", ["Sandstorm", "Grit Gale"], {"area": 1.3}, ["explosion", "projectile"]),
    ("mass", "force", ["Collapse", "Crush"], {"power": 1.25}, ["slam", "grapple"]),
    ("mass", "gas", ["Pressure", "Downburst"], {"power": 1.15, "area": 1.2}, ["slam", "explosion"]),
    ("organic", "fluid", ["Monsoon", "Bloomtide"], {"stun": 1.2}, ["grapple", "env_strike"]),
    ("organic", "solid", ["Ironwood", "Thornstone"], {"power": 1.15}, ["env_strike", "summon_weapon"]),
    ("organic", "void", ["Nightbloom", "Rot"], {"stun": 1.2}, ["grapple", "env_strike"]),
    ("organic", "radiant", ["Sunbloom", "Lifelight"], {"area": 1.2}, ["projectile", "env_strike"]),
    ("radiant", "void", ["Eclipse", "Twilight"], {"power": 1.25}, ["beam", "explosion"]),
    ("radiant", "crystal", ["Prism", "Refraction"], {"split": 1.0}, ["projectile", "beam"]),
    ("radiant", "sharp", ["Holy Edge", "Gleam"], {"pierce": 1.0}, ["summon_weapon", "projectile"]),
    ("void", "gravity", ["Event Horizon", "Abyssal Pull"], {"power": 1.2}, ["explosion", "grapple"]),
    ("void", "fluid", ["Ink", "Black Tide"], {"stun": 1.2}, ["grapple", "projectile"]),
    ("void", "gas", ["Shadow Gale", "Wraithwind"], {"speed": 1.2}, ["projectile", "kick"]),
    ("void", "solid", ["Obsidian", "Grave"], {"power": 1.15}, ["env_strike", "summon_weapon"]),
    ("gravity", "solid", ["Meteor", "Tectonic Pull"], {"power": 1.25}, ["slam", "env_strike", "projectile"]),
    ("gravity", "gas", ["Vortex", "Maelstrom"], {"area": 1.3}, ["explosion", "projectile"]),
    ("gravity", "radiant", ["Lensing", "Starfall"], {"pierce": 1.0}, ["beam", "projectile"]),
    ("gravity", "fluid", ["Undertow", "Riptide Well"], {"stun": 1.2}, ["grapple", "explosion"]),
    ("gravity", "sharp", ["Orbiting Blades", "Satellite"], {"split": 1.0}, ["projectile", "summon_weapon"]),
    ("wave", "gas", ["Sonic Cyclone", "Howling"], {"area": 1.3}, ["explosion", "projectile"]),
    ("wave", "solid", ["Resonant Quake", "Seismic"], {"power": 1.2}, ["slam", "env_strike"]),
    ("wave", "fluid", ["Tsunami Echo", "Sonar"], {"area": 1.2}, ["beam", "explosion"]),
    ("wave", "radiant", ["Harmonic", "Chorus of Light"], {"speed": 1.2}, ["beam", "projectile"]),
    ("wave", "void", ["Silence", "Dread Echo"], {"stun": 1.3}, ["explosion"]),
    ("wave", "organic", ["Rustling", "Pollen Song"], {"stun": 1.1}, ["explosion", "env_strike"]),
    ("sharp", "fast", ["Flash Cut", "Gale Edge"], {"speed": 1.3}, ["summon_weapon", "charge"]),
    ("sharp", "gas", ["Razor Wind", "Cutting Gale"], {"speed": 1.2}, ["projectile", "kick"]),
    ("sharp", "fluid", ["Water Blade", "Tide Cutter"], {"pierce": 1.0}, ["summon_weapon", "projectile"]),
    ("sharp", "mass", ["Guillotine", "Cleaver"], {"power": 1.25}, ["summon_weapon", "slam"]),
    ("sharp", "precise", ["Thousand Cuts", "Needlepoint"], {"pierce": 1.0}, ["summon_weapon", "projectile"]),
    ("kinetic", "mass", ["Meteor Fist", "Titan"], {"power": 1.25}, ["punch", "slam"]),
    ("kinetic", "sharp", ["Blade Dance", "Whirlwind"], {"speed": 1.2}, ["summon_weapon", "kick"]),
    ("kinetic", "ranged", ["Ricochet", "Trick Shot"], {"speed": 1.2}, ["projectile", "kick"]),
    ("protective", "force", ["Aegis Rush", "Shield Bash"], {"poise": 1.3}, ["charge", "counter"]),
    ("protective", "sharp", ["Phalanx", "Shield Edge"], {"power": 1.1}, ["counter", "summon_weapon"]),
    ("protective", "energy", ["Barrier Burst", "Warding Flare"], {"area": 1.3}, ["explosion", "counter"]),
    ("protective", "ranged", ["Covering Fire", "Rampart Volley"], {"split": 1.0}, ["projectile", "counter"]),
    ("protective", "mass", ["Juggernaut", "Fortress"], {"poise": 1.3}, ["charge", "slam"]),
    ("ranged", "fast", ["Rapid Volley", "Hailfire"], {"split": 1.0}, ["projectile"]),
    ("ranged", "heavy", ["Ballista", "Siege"], {"power": 1.25}, ["projectile"]),
]

EFFECT_TAGS = {"heat", "electric", "cold", "void", "radiant", "energy", "wave", "gravity", "fast"}
FORM_TAGS = {"solid", "sharp", "fluid", "kinetic", "mass", "organic", "gas", "crystal", "ranged", "protective"}
VALID_THRESHOLD = 0.45


def _reactions_for(a, b):
    out = []
    ta, tb = set(a["tags"]), set(b["tags"])
    for x, y, words, eff, deliv in REACTIONS:
        if (x in ta and y in tb) or (x in tb and y in ta):
            out.append({"words": words, "effects": eff, "deliveries": deliv, "rule": f"{x}+{y}"})
    return out


def pair_compatibility(a, b):
    """Return (score, reaction) for two abilities."""
    if a["id"] == b["id"]:
        return 0.0, None
    if a.get("archetype") == b.get("archetype"):
        return 0.15, None  # redundant
    reactions = _reactions_for(a, b)
    if reactions:
        r = reactions[0]
        score = min(1.0, 0.65 + 0.12 * len(reactions))
        return score, r
    ta, tb = set(a["tags"]), set(b["tags"])
    if (ta & EFFECT_TAGS and tb & FORM_TAGS) or (tb & EFFECT_TAGS and ta & FORM_TAGS):
        eff, form = (a, b) if ta & EFFECT_TAGS and tb & FORM_TAGS else (b, a)
        shared = [d for d, w in form["affinity"].items() if w >= 0.7 and eff["affinity"].get(d, 0) >= 0.5]
        return 0.55, {
            "words": [f"{eff['words']['adj'][0]} {form['words']['noun'][0]}"],
            "effects": {"power": 1.1},
            "deliveries": shared or sorted(form["affinity"], key=lambda d: -form["affinity"][d])[:2],
            "rule": "infusion",
        }
    return 0.3, None


def combination_for(abilities, universe=None):
    """Validate + build (and persist) a combination record for 2-3 abilities."""
    abilities = sorted(abilities, key=lambda a: a["id"])
    if not 2 <= len(abilities) <= 3:
        return None
    pairs = []
    for a, b in itertools.combinations(abilities, 2):
        score, r = pair_compatibility(a, b)
        if score < VALID_THRESHOLD or r is None:
            return None
        pairs.append((score, r, a, b))
    if len(abilities) == 3 and sum(1 for p in pairs if p[1]["rule"] != "infusion") < 2:
        return None  # a triple must be driven by real reactions to stay readable
    pairs.sort(key=lambda p: -p[0])
    words = [p[1]["words"][0] for p in pairs[:2]]
    if len(abilities) == 3:
        w1 = words[0].split()[-1]
        reaction = f"{words[1]} {w1}" if w1 not in words[1] else words[1]
    else:
        reaction = words[0]
    effects = {}
    for _, r, _, _ in pairs:
        for k, v in r["effects"].items():
            effects[k] = max(effects.get(k, 1.0), v)
    deliveries = []
    for _, r, _, _ in pairs:
        for d in r["deliveries"]:
            if d not in deliveries:
                deliveries.append(d)
    sig = {"abilities": [a["id"] for a in abilities]}
    rec = {
        "id": stable_id("cmb", sig),
        "abilities": [a["id"] for a in abilities],
        "ability_names": [a["name"] for a in abilities],
        "reaction": reaction,
        "alt_words": [w for _, r, _, _ in pairs for w in r["words"]],
        "rules": [r["rule"] for _, r, _, _ in pairs],
        "compatibility": round(sum(p[0] for p in pairs) / len(pairs), 3),
        "effects": effects,
        "deliveries": deliveries,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if universe is not None:
        universe["combinations"].put(rec["id"], rec)
    return rec
