"""Procedural technique construction.

A technique = movement primitive + delivery + modifiers + timing + abilities.
Components are theme independent; abilities only add properties/visuals. The
composer can build techniques up-front (a fighter's repertoire) or on the fly
from the live fight context (dynamic discovery). Every candidate goes through
`validate()` (logical/animation feasibility) before it is ever used, and valid
new techniques are persisted with a stable content-hash id (no duplicates).
"""
from __future__ import annotations

import math
import time

from ..persistence.library import stable_id
from .combinations import combination_for

# ---------------------------------------------------------------------------
# Component catalogues
# ---------------------------------------------------------------------------
# kind: melee | projectile | beam | area | grab | env | stance
DELIVERIES = {
    "punch":         dict(kind="melee", limb="hand", reach=0.95, height="mid", startup=0.12, active=0.08, recovery=0.22, dmg=8, poise=11, kb=(2.4, 0.6), variants=3),
    "kick":          dict(kind="melee", limb="foot", reach=1.15, height="mid", startup=0.16, active=0.10, recovery=0.28, dmg=10, poise=13, kb=(3.4, 1.2), variants=3),
    "sweep":         dict(kind="melee", limb="foot", reach=1.2, height="low", startup=0.17, active=0.12, recovery=0.34, dmg=8, poise=13, kb=(1.0, 2.5), knockdown=True, ground_only=True, variants=1),
    "uppercut":      dict(kind="melee", limb="hand", reach=0.85, height="mid", startup=0.15, active=0.10, recovery=0.36, dmg=10, poise=14, kb=(1.2, 8.0), launcher=True, ground_only=True, variants=1),
    "aerial_strike": dict(kind="melee", limb="foot", reach=1.1, height="high", startup=0.10, active=0.32, recovery=0.22, dmg=11, poise=15, kb=(4.0, -1.0), air_only=True, variants=2),
    "slam":          dict(kind="area", limb="hand", reach=1.5, height="low", startup=0.30, active=0.08, recovery=0.40, dmg=12, poise=18, kb=(3.5, 4.0), knockdown=True, radius=1.5, variants=1),
    "grapple":       dict(kind="grab", limb="hand", reach=0.85, height="mid", startup=0.12, active=0.08, recovery=0.40, dmg=12, poise=20, kb=(6.0, 5.0), unblockable=True, ground_only=True, knockdown=True, variants=1),
    "charge":        dict(kind="melee", limb="body", reach=0.7, height="mid", startup=0.20, active=0.38, recovery=0.34, dmg=11, poise=16, kb=(6.0, 2.5), travel=9.5, ground_only=True, variants=1),
    "projectile":    dict(kind="projectile", limb="hand", reach=9.0, height="mid", startup=0.22, active=0.06, recovery=0.30, dmg=7, poise=10, kb=(3.0, 1.0), speed=11.0, variants=3),
    "beam":          dict(kind="beam", limb="hand", reach=8.0, height="mid", startup=0.40, active=0.55, recovery=0.42, dmg=12, poise=22, kb=(4.5, 1.0), hits=4, variants=1),
    "explosion":     dict(kind="area", limb="body", reach=1.7, height="mid", startup=0.34, active=0.10, recovery=0.40, dmg=10, poise=17, kb=(6.0, 3.5), radius=1.7, variants=1),
    "counter":       dict(kind="stance", limb="hand", reach=1.0, height="mid", startup=0.05, active=0.65, recovery=0.30, dmg=12, poise=20, kb=(5.0, 3.0), variants=1),
    "summon_weapon": dict(kind="melee", limb="weapon", reach=1.65, height="mid", startup=0.19, active=0.12, recovery=0.30, dmg=11, poise=14, kb=(3.8, 1.5), variants=2),
    "env_strike":    dict(kind="env", limb="hand", reach=8.0, height="low", startup=0.30, active=0.10, recovery=0.38, dmg=11, poise=16, kb=(1.5, 9.0), launcher=True, delay=0.42, min_range=1.4, ground_only=True, variants=1),
    "barrage":       dict(kind="melee", limb="hand", reach=0.95, height="mid", startup=0.10, active=0.60, recovery=0.30, dmg=3, poise=5, kb=(1.0, 0.3), hits=5, variants=1),
}

MOVEMENTS = {
    "none":        dict(closes=0.0),
    "step":        dict(closes=0.8),
    "dash":        dict(closes=5.5),
    "leap":        dict(closes=3.2, air=True),
    "aerial_dash": dict(closes=6.0, air=True, requires_mobility=["glide", "float", "burst_dash"]),
    "teleport":    dict(closes=9.0, requires_mobility=["teleport"]),
    "slide":       dict(closes=3.5, requires_mobility=["slide"], fallback_ok=True),
    "backstep":    dict(closes=-2.0),
    "wall_jump":   dict(closes=4.0, air=True, requires_wall=True),
}

MOVE_COMPAT = {
    "punch": ["none", "step", "dash", "teleport", "leap", "aerial_dash"],
    "kick": ["none", "step", "dash", "teleport", "leap", "aerial_dash", "wall_jump"],
    "sweep": ["none", "step", "dash", "slide", "teleport"],
    "uppercut": ["none", "step", "dash", "slide", "teleport"],
    "aerial_strike": ["leap", "aerial_dash", "wall_jump", "teleport"],
    "slam": ["none", "leap", "aerial_dash", "teleport"],
    "grapple": ["none", "step", "dash", "teleport"],
    "charge": ["none"],
    "projectile": ["none", "backstep", "leap", "teleport", "dash"],
    "beam": ["none", "backstep", "leap", "teleport"],
    "explosion": ["none", "dash", "teleport", "leap"],
    "counter": ["none", "backstep"],
    "summon_weapon": ["none", "step", "dash", "teleport", "leap", "aerial_dash"],
    "env_strike": ["none", "backstep"],
    "barrage": ["none", "step", "dash", "teleport"],
}

MODIFIERS = {
    "chain":      ["punch", "kick", "projectile", "beam", "summon_weapon", "charge"],
    "split":      ["projectile"],
    "delayed":    ["projectile", "explosion", "env_strike", "punch"],
    "homing":     ["projectile"],
    "amplify":    ["explosion", "slam", "env_strike", "beam", "projectile"],
    "pierce":     ["projectile", "beam", "charge", "summon_weapon", "punch", "kick"],
    "trap":       ["projectile", "explosion", "slam", "env_strike", "sweep"],
    "shield":     ["charge", "counter", "explosion", "punch"],
    "reflect":    ["counter"],
    "absorb":     ["counter"],
    "multistage": ["punch", "kick", "summon_weapon", "uppercut", "charge"],
}

TIMINGS = {
    "instant": dict(startup=1.0, dmg=1.0),
    "charged": dict(startup=2.0, dmg=1.45),
    "multi_hit": dict(startup=1.1, dmg=1.25),
    "feint": dict(startup=1.0, dmg=1.0),
    "finisher": dict(startup=2.3, dmg=1.9),
}
TIMING_COMPAT = {
    "multi_hit": ["projectile", "kick", "punch", "beam", "summon_weapon"],
    "charged": ["punch", "projectile", "beam", "explosion", "slam", "charge", "env_strike", "summon_weapon", "kick"],
    "feint": ["punch", "kick", "summon_weapon", "projectile"],
    "finisher": ["beam", "explosion", "slam", "env_strike", "charge", "projectile", "punch", "summon_weapon", "aerial_strike"],
}

NOUNS = {
    "punch": ["Fist", "Knuckle", "Palm", "Strike"], "kick": ["Kick", "Heel", "Crescent"], "sweep": ["Sweep", "Reaper"],
    "uppercut": ["Rising Fist", "Ascension", "Uppercut"], "aerial_strike": ["Dive", "Meteor Kick", "Talon"],
    "slam": ["Hammer", "Crash", "Quake"], "grapple": ["Grasp", "Bind", "Suplex"], "charge": ["Rush", "Comet", "Ram"],
    "projectile": ["Orb", "Volley", "Shot", "Bolt"], "beam": ["Lance", "Ray", "Cannon"], "explosion": ["Burst", "Nova", "Eruption"],
    "counter": ["Mirror", "Riposte", "Parry"], "summon_weapon": ["Blade", "Edge", "Glaive"], "env_strike": ["Pillar", "Spire", "Eruption"],
    "barrage": ["Barrage", "Flurry", "Rush"],
}
MOVE_WORDS = {"dash": "Dashing", "leap": "Leaping", "aerial_dash": "Sky", "teleport": "Phantom", "slide": "Sliding",
              "backstep": "Retreating", "wall_jump": "Rebound", "step": "Step-in"}
MOD_WORDS = {"chain": "Chain", "split": "Triple", "delayed": "Delayed", "homing": "Seeking", "amplify": "Grand",
             "pierce": "Piercing", "trap": "Snare", "shield": "Guarded", "reflect": "Reflecting", "absorb": "Devouring",
             "multistage": "Cascade"}
TIMING_WORDS = {"charged": "Charged", "multi_hit": "Rapid", "feint": "Feint", "finisher": "Ultimate"}


def mobility_set(abilities):
    return {a.get("mobility") for a in abilities}


def validate(tech_spec, abilities):
    """Return (ok, reason). Rejects nonsensical / unanimatable constructions."""
    d, m, mods, timing = tech_spec["delivery"], tech_spec["movement"], tech_spec["modifiers"], tech_spec["timing"]
    if d not in DELIVERIES:
        return False, f"unknown delivery {d}"
    if m not in MOVE_COMPAT[d]:
        return False, f"movement {m} cannot lead into {d}"
    mv = MOVEMENTS[m]
    req = mv.get("requires_mobility")
    if req and not (mobility_set(abilities) & set(req)) and not mv.get("fallback_ok"):
        return False, f"{m} needs a mobility ability"
    if m == "slide" and not (mobility_set(abilities) & {"slide"}) and d not in ("sweep", "uppercut"):
        return False, "slide only as a low approach"
    for mod in mods:
        if d not in MODIFIERS.get(mod, []):
            return False, f"modifier {mod} incompatible with {d}"
    if len(set(mods)) != len(mods):
        return False, "duplicate modifier"
    if "split" in mods and "homing" in mods and len(abilities) < 2:
        return False, "split+homing reserved for fusions (readability)"
    if timing != "instant" and d not in TIMING_COMPAT.get(timing, []):
        return False, f"timing {timing} incompatible with {d}"
    if timing == "multi_hit" and ("split" in mods or "multistage" in mods):
        return False, "multi_hit + split/multistage is unreadable"
    if d in ("projectile", "beam", "env_strike", "explosion") and not abilities:
        return False, f"{d} needs an ability"
    if d == "summon_weapon" and not abilities:
        return False, "weapon must be summoned by an ability"
    if len(mods) > 3:
        return False, "too many modifiers"
    if timing == "finisher" and len(abilities) < 1:
        return False, "finishers are ability driven"
    if m == "leap" and DELIVERIES[d].get("ground_only"):
        return False, "ground-only delivery after a leap"
    return True, "ok"


def signature(spec):
    return {
        "abilities": sorted(spec["abilities"]),
        "delivery": spec["delivery"],
        "movement": spec["movement"],
        "modifiers": sorted(spec["modifiers"]),
        "timing": spec["timing"],
    }


def _name(spec, abilities, combo, rng):
    noun = rng.choice(NOUNS[spec["delivery"]])
    parts = []
    if spec["timing"] in TIMING_WORDS and spec["timing"] != "finisher":
        parts.append(TIMING_WORDS[spec["timing"]])
    if spec["modifiers"]:
        parts.append(MOD_WORDS[rng.choice(spec["modifiers"])])
    if combo:
        parts.append(combo["reaction"])
    elif abilities:
        parts.append(rng.choice(abilities[0]["words"]["adj"]))
    elif spec["movement"] in MOVE_WORDS:
        parts.append(MOVE_WORDS[spec["movement"]])
    else:
        parts.append(rng.choice(["Iron", "Swift", "Crushing", "Twin", "Spinning", "Snap", "Hidden"]))
    name = " ".join(parts + [noun])
    if spec["timing"] == "finisher":
        name = f"{name.upper()}"
    return name


def build_params(spec, abilities, combo):
    d = DELIVERIES[spec["delivery"]]
    t = TIMINGS[spec["timing"]]
    stats = {"power": 1.0, "speed": 1.0, "control": 1.0}
    if abilities:
        for k in stats:
            stats[k] = sum(a["stats"].get(k, 1.0) for a in abilities) / len(abilities)
    eff = combo["effects"] if combo else {}
    power = stats["power"] * eff.get("power", 1.0) * (1.08 if abilities else 1.0)
    speed = stats["speed"] * eff.get("speed", 1.0)
    p = {
        "startup": round(d["startup"] * t["startup"] / speed ** 0.35, 3),
        "active": d["active"],
        "recovery": round(d["recovery"] / speed ** 0.2, 3),
        "dmg": round(d["dmg"] * t["dmg"] * power, 2),
        "poise": round(d["poise"] * t["dmg"] * power * eff.get("poise", 1.0), 2),
        "kb": list(d["kb"]),
        "reach": d["reach"],
        "hits": d.get("hits", 1),
        "knockdown": d.get("knockdown", False),
        "launcher": d.get("launcher", False),
        "unblockable": d.get("unblockable", False),
        "guard_break": "pierce" in spec["modifiers"],
        "stun": eff.get("stun", 1.0),
    }
    if d["kind"] == "projectile":
        p["speed"] = round(d["speed"] * speed, 2)
        p["count"] = 3 if "split" in spec["modifiers"] else 1
        p["homing"] = 2.4 * stats["control"] if "homing" in spec["modifiers"] else 0.0
        p["radius"] = 0.2 * (1.35 if "amplify" in spec["modifiers"] else 1.0)
        p["pierce"] = "pierce" in spec["modifiers"]
        p["detonate"] = 0.75 if "delayed" in spec["modifiers"] else 0.0
        if spec["timing"] == "multi_hit":
            p["hits"] = 3
            p["dmg"] = round(p["dmg"] / 2.0, 2)
            p["poise"] = round(p["poise"] / 2.0, 2)
    if d["kind"] in ("area", "env") or spec["delivery"] == "slam":
        r = d.get("radius", 1.0)
        p["radius"] = round(r * eff.get("area", 1.0) * (1.4 if "amplify" in spec["modifiers"] else 1.0), 2)
    if spec["delivery"] == "env_strike":
        p["delay"] = d["delay"] + (0.35 if "delayed" in spec["modifiers"] else 0.0)
        p["radius"] = round(0.8 * eff.get("area", 1.0) * (1.4 if "amplify" in spec["modifiers"] else 1.0), 2)
    if spec["delivery"] == "beam":
        p["width"] = 0.32 * (1.4 if "amplify" in spec["modifiers"] else 1.0)
        p["dmg"] = round(p["dmg"] / p["hits"], 2)
        p["poise"] = round(p["poise"] / p["hits"], 2)
    if spec["delivery"] == "barrage" or (spec["timing"] == "multi_hit" and d["kind"] == "melee"):
        p["hits"] = max(p["hits"], 4)
        p["active"] = max(p["active"], 0.5)
        if spec["delivery"] != "barrage":
            p["dmg"] = round(p["dmg"] / 2.2, 2)
            p["poise"] = round(p["poise"] / 2.2, 2)
    if "multistage" in spec["modifiers"]:
        p["stages"] = 3 if spec["delivery"] in ("punch", "kick") else 2
    else:
        p["stages"] = 1
    if spec["delivery"] == "charge":
        p["travel"] = d["travel"] * speed ** 0.5
    if "trap" in spec["modifiers"]:
        p["trap"] = True
    if "chain" in spec["modifiers"]:
        p["chain"] = True
    if "delayed" in spec["modifiers"] and spec["delivery"] in ("punch", "explosion"):
        p["delay_blast"] = 0.6
    if "shield" in spec["modifiers"]:
        p["shield"] = 1.8
    if "reflect" in spec["modifiers"]:
        p["reflect"] = True
    if "absorb" in spec["modifiers"]:
        p["absorb"] = True
    if spec["timing"] == "finisher":
        p["finisher"] = True
    # Resource costs scale with sophistication.
    n_ab = len(abilities)
    cost = [0, 14, 30, 42][min(3, n_ab)] + 6 * len(spec["modifiers"]) + (8 if spec["timing"] == "charged" else 0)
    if spec["movement"] in ("teleport", "aerial_dash"):
        cost += 8
    p["cost"] = 0 if spec["timing"] == "finisher" else min(70, cost)
    p["focus_cost"] = 100 if spec["timing"] == "finisher" else 0
    p["cooldown"] = round(0.6 + 0.9 * n_ab + 0.4 * len(spec["modifiers"]), 2)
    return p


def tier_of(spec):
    if spec["timing"] == "finisher":
        return "ultimate"
    return ["basic", "infused", "fusion", "fusion"][min(3, len(spec["abilities"]))]


def make_technique(spec, abilities, rng, universe=None, origin="generated", meta=None):
    ok, why = validate(spec, abilities)
    if not ok:
        return None, why
    combo = combination_for(abilities, universe) if len(abilities) >= 2 else None
    if len(abilities) >= 2 and combo is None:
        return None, "invalid combination"
    sig = signature(spec)
    tid = stable_id("tq", sig)
    if universe is not None and tid in universe["techniques"]:
        return universe["techniques"].get(tid), "existing"
    nrng = rng.stream("name", tid)
    tech = {
        "id": tid,
        "signature": sig,
        "name": _name(spec, abilities, combo, nrng),
        "tier": tier_of(spec),
        "abilities": sig["abilities"],
        "ability_names": [a["name"] for a in abilities],
        "combination": combo["id"] if combo else None,
        "reaction": combo["reaction"] if combo else None,
        "delivery": spec["delivery"],
        "kind": DELIVERIES[spec["delivery"]]["kind"],
        "movement": spec["movement"],
        "modifiers": sorted(spec["modifiers"]),
        "timing": spec["timing"],
        "variant": int(tid[-4:], 16) % DELIVERIES[spec["delivery"]]["variants"],
        "anim": f"anim_{spec['delivery']}",
        "params": build_params(spec, abilities, combo),
        "origin": origin,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if meta:
        tech["discovery"] = meta
    if universe is not None:
        universe["techniques"].put(tid, tech)
    return tech, "new"


# ---------------------------------------------------------------------------
# Composer
# ---------------------------------------------------------------------------
def _delivery_weights(abilities, combo, context, allow_physical):
    w = {}
    for d in DELIVERIES:
        if not abilities:
            w[d] = 1.0 if d in ("punch", "kick", "sweep", "uppercut", "grapple", "aerial_strike", "barrage", "charge") else 0.0
            continue
        aff = sum(a["affinity"].get(d, 0.25) for a in abilities) / len(abilities)
        if combo and d in combo["deliveries"]:
            aff += 0.9
        w[d] = aff
    if not allow_physical and not abilities:
        return {}
    ctx = context or {}
    dist = ctx.get("dist")
    if dist is not None:
        for d in w:
            kind = DELIVERIES[d]["kind"]
            if dist > 3.5:
                w[d] *= 1.8 if kind in ("projectile", "beam", "env") else 0.6
            elif dist < 1.5:
                w[d] *= 1.6 if kind in ("melee", "grab", "area") else 0.5
    if ctx.get("opp_blocks", 0) > 0.4:
        w["grapple"] = w.get("grapple", 0) * 2.5 + 0.3
    if ctx.get("opp_airborne"):
        for d in ("uppercut", "beam", "projectile"):
            w[d] = w.get(d, 0) * 1.8
    if ctx.get("opp_zoning", 0) > 0.4:
        w["charge"] = w.get("charge", 0) * 1.7 + 0.2
        w["counter"] = w.get("counter", 0) * 1.5
    if ctx.get("opp_rushdown", 0) > 0.4:
        w["counter"] = w.get("counter", 0) * 2.0 + 0.2
        w["explosion"] = w.get("explosion", 0) * 1.5
    if ctx.get("airborne"):
        for d in list(w):
            if DELIVERIES[d].get("ground_only"):
                w[d] = 0.0
    return w


def compose(abilities, rng, context=None, complexity=1.0, allow_physical=True, forced=None):
    """Assemble a *spec* (not yet validated) from abilities + context."""
    combo = combination_for(abilities) if len(abilities) >= 2 else None
    weights = _delivery_weights(abilities, combo, context, allow_physical)
    if forced and forced.get("delivery"):
        delivery = forced["delivery"]
    else:
        items = [d for d, v in weights.items() if v > 0]
        if not items:
            return None
        delivery = rng.weighted(items, [weights[d] for d in items])
    moves = list(MOVE_COMPAT[delivery])
    mob = mobility_set(abilities)
    mw = []
    ctx = context or {}
    for m in moves:
        req = MOVEMENTS[m].get("requires_mobility")
        if req and not (mob & set(req)):
            mw.append(0.0 if not MOVEMENTS[m].get("fallback_ok") else 0.2)
            continue
        base = {"none": 1.2, "step": 0.9, "dash": 1.0, "leap": 0.6, "aerial_dash": 0.7, "teleport": 1.1,
                "slide": 0.8, "backstep": 0.5, "wall_jump": 0.0}.get(m, 0.5)
        if m == "wall_jump" and ctx.get("near_wall"):
            base = 1.5
        mw.append(base)
    movement = forced.get("movement") if forced and forced.get("movement") else rng.weighted(moves, mw)
    mods = []
    if abilities:
        cand = [m for m, ds in MODIFIERS.items() if delivery in ds]
        n_mods = rng.choice([0, 1, 1, 2] if complexity >= 1 else [0, 0, 1])
        for _ in range(n_mods):
            if not cand:
                break
            ws = [sum(a["mod_affinity"].get(m, 0.25) for a in abilities) for m in cand]
            mod = rng.weighted(cand, ws)
            mods.append(mod)
            cand.remove(mod)
    elif delivery in ("punch", "kick") and rng.chance(0.45):
        mods.append("multistage")
    timing = "instant"
    if forced and forced.get("timing"):
        timing = forced["timing"]
    else:
        opts = ["instant"] + [t for t, ds in TIMING_COMPAT.items() if delivery in ds and t != "finisher"]
        timing = rng.weighted(opts, [2.5] + [0.7] * (len(opts) - 1))
    if forced and forced.get("modifiers") is not None:
        mods = list(forced["modifiers"])
    return {"delivery": delivery, "movement": movement, "modifiers": mods, "timing": timing,
            "abilities": [a["id"] for a in abilities]}


def compose_valid(abilities, rng, universe=None, tries=24, **kw):
    origin = kw.pop("origin", "generated")
    meta = kw.pop("meta", None)
    for i in range(tries):
        spec = compose(abilities, rng, **kw)
        if spec is None:
            return None
        tech, status = make_technique(spec, abilities, rng, universe, origin=origin, meta=meta)
        if tech is not None:
            return tech
    return None


def build_repertoire(fighter_abilities, rng, universe, cfg):
    """Canonical move set for a fighter: physical basics, single-ability
    techniques, pair/triple fusions and one ultimate finisher."""
    combat = cfg["combat"]
    complexity = 1.0 if combat.get("combination_complexity") == "maximum" else 0.6
    out = []
    seen = set()

    def add(t):
        if t and t["id"] not in seen:
            seen.add(t["id"])
            out.append(t)

    if combat.get("physical_combat_enabled", True):
        for d in ("punch", "kick", "sweep", "uppercut", "grapple", "aerial_strike", "barrage"):
            spec_rng = rng.stream("basic", d)
            add(compose_valid([], spec_rng, universe, forced={"delivery": d}, complexity=complexity))
    if combat.get("special_abilities_enabled", True):
        variety = 3 if combat.get("attack_variety") == "maximum" else 2
        for a in fighter_abilities:
            for i in range(variety + 1):
                add(compose_valid([a], rng.stream("single", a["id"], i), universe, complexity=complexity))
        import itertools
        n = len(fighter_abilities)
        for k in range(2, min(3, n) + 1):
            for group in itertools.combinations(fighter_abilities, k):
                if combination_for(list(group), universe) is None:
                    continue
                for i in range(2 if k == 2 else 1):
                    add(compose_valid(list(group), rng.stream("fusion", *[g["id"] for g in group], i), universe, complexity=complexity))
        if combat.get("cinematic_finishers", True):
            groups = [list(g) for k in range(min(3, n), 1, -1) for g in itertools.combinations(fighter_abilities, k)
                      if combination_for(list(g)) is not None]
            group = groups[0] if groups else fighter_abilities[:1]
            frng = rng.stream("ultimate")
            for _ in range(12):
                combo = combination_for(group) if len(group) > 1 else None
                prefs = [d for d in (combo["deliveries"] if combo else []) if d in TIMING_COMPAT["finisher"]]
                d = frng.choice(prefs or ["beam", "explosion", "env_strike", "slam"])
                t = compose_valid(group, frng, universe, forced={"delivery": d, "timing": "finisher"}, complexity=complexity)
                if t:
                    add(t)
                    break
    return out
