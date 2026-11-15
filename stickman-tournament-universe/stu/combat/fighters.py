"""Fighter generation: identity, colour, personality, balanced ability loadouts."""
from __future__ import annotations

import colorsys
import itertools
import time

from ..core.mathutil import hex_to_rgb, rgb_to_hex
from ..persistence.library import stable_id
from .combinations import pair_compatibility
from .techniques import build_repertoire

PERSONALITIES = {
    #                aggression caution evasive counter creativity range  temp
    "aggressive":   dict(aggression=0.85, caution=0.25, evasive=0.3, counter=0.3, creativity=0.5, range=1.0, temperature=0.55),
    "defensive":    dict(aggression=0.35, caution=0.8, evasive=0.4, counter=0.6, creativity=0.4, range=1.8, temperature=0.45),
    "evasive":      dict(aggression=0.5, caution=0.55, evasive=0.85, counter=0.4, creativity=0.6, range=2.6, temperature=0.6),
    "technical":    dict(aggression=0.55, caution=0.55, evasive=0.5, counter=0.55, creativity=0.75, range=1.6, temperature=0.4),
    "unpredictable": dict(aggression=0.6, caution=0.4, evasive=0.55, counter=0.4, creativity=0.95, range=2.0, temperature=1.0),
    "strategic":    dict(aggression=0.5, caution=0.65, evasive=0.5, counter=0.5, creativity=0.7, range=3.2, temperature=0.4),
    "counter":      dict(aggression=0.4, caution=0.6, evasive=0.45, counter=0.9, creativity=0.5, range=1.4, temperature=0.5),
}
ACCESSORIES = ["headband", "scarf", "spikes", "horns", "halo", "ponytail", "visor", "topknot"]


def choose_costume(theme, rng):
    """Theme costume: one headwear + extras (hook hands, peg legs, wings...)."""
    from ..themes.packs import COSTUMES
    pool = theme.get("costumes") or ACCESSORIES
    rules = theme.get("costume_rules") or {"head": 1, "extras": (0, 1)}
    parts = list(rules.get("always", []))
    heads = [c for c in pool if COSTUMES.get(c) == "head" and c not in parts]
    others = [c for c in pool if COSTUMES.get(c) != "head" and c not in parts]
    if heads and not any(COSTUMES.get(c) == "head" for c in parts):
        parts.append(rng.choice(heads))
    lo, hi = rules.get("extras", (0, 1))
    k = min(len(others), rng.randint(lo, hi))
    rare = {"peg_leg": 0.45, "hook_hand": 0.5, "parrot": 0.5}
    pool2 = list(others)
    for _ in range(k):
        pick = rng.weighted(pool2, [rare.get(c, 1.0) for c in pool2])
        parts.append(pick)
        pool2.remove(pick)
    return parts
STANCES = ["orthodox", "southpaw", "low", "upright"]
SUFFIXES = ["tar", "ax", "ix", "ion", "ara", "eth", "yx", "os", "ra", "en", "is", "or", "ka", "us", "ia", "ex"]
CONNECT = ["", "", "r", "n", "v", "z", "k", "l"]


def _syllable_root(ability):
    base = "".join(ch for ch in ability["name"] if ch.isalpha())
    return base[:3].capitalize() if len(base) >= 3 else base.capitalize()


def make_name(abilities, rng, taken):
    for _ in range(80):
        a = rng.choice(abilities)
        root = _syllable_root(a)
        if rng.chance(0.35):
            root = rng.choice(a["words"]["noun"])[:3].capitalize()
        name = (root + rng.choice(CONNECT) + rng.choice(SUFFIXES)).upper()
        name = name.replace("QX", "QUIX")
        if 4 <= len(name) <= 9 and name not in taken:
            return name
    return f"FIGHTER{len(taken) + 1}"


PALETTE = ["#ff3b3b", "#ff9a1f", "#ffe23d", "#8cff3a", "#1fe08a", "#2ee9ff", "#3a7bff", "#a35cff",
           "#ff4fd8", "#f4f4f4", "#ff7a59", "#c6ff7a", "#7af0ff", "#ffb3e6", "#d9a8ff", "#ffd37a"]


def _distinct_colors(n, rng, preferred_hues):
    """Assign high-contrast colours from a curated palette (well separated even
    on small screens), matched to each fighter's primary ability hue."""
    pal = PALETTE[:max(n, 8)] if n <= len(PALETTE) else PALETTE + [
        rgb_to_hex(colorsys.hsv_to_rgb((i * 0.618) % 1.0, 0.8, 1.0)) for i in range(n - len(PALETTE))]
    hues = [colorsys.rgb_to_hsv(*hex_to_rgb(c))[0] for c in pal]
    sats = [colorsys.rgb_to_hsv(*hex_to_rgb(c))[1] for c in pal]
    free = list(range(len(pal)))
    out = [None] * n
    order = sorted(range(n), key=lambda i: rng.random())
    for i in order:
        h = preferred_hues[i]
        best = min(free, key=lambda j: (min(abs(hues[j] - h), 1 - abs(hues[j] - h)) + (0.3 if sats[j] < 0.2 else 0.0)))
        free.remove(best)
        out[i] = pal[best]
    return out


def rating(abilities, personality):
    p = sum(a["stats"]["power"] for a in abilities) / len(abilities)
    s = sum(a["stats"]["speed"] for a in abilities) / len(abilities)
    c = sum(a["stats"]["control"] for a in abilities) / len(abilities)
    d = sum(a["stats"]["defense"] for a in abilities) / len(abilities)
    synergy = 0.0
    for x, y in itertools.combinations(abilities, 2):
        synergy += pair_compatibility(x, y)[0]
    return round(p * 0.32 + s * 0.26 + c * 0.22 + d * 0.2 + 0.04 * synergy, 4)


def assign_loadouts(pool, n, k, unique, rng):
    """Balanced assignment: try many candidate drafts, keep the one with the
    lowest rating variance and best synergy coverage."""
    best, best_score = None, None
    for attempt in range(60):
        r = rng.stream("draft", attempt)
        if unique:
            order = list(pool)
            r.shuffle(order)
            groups = [order[i * k:(i + 1) * k] for i in range(n)]
        else:
            usage = {a["id"]: 0 for a in pool}
            groups = []
            for _ in range(n):
                cand = sorted(pool, key=lambda a: (usage[a["id"]], r.random()))
                g = []
                for a in cand:
                    if len(g) == k:
                        break
                    if all(a["archetype"] != b["archetype"] for b in g):
                        g.append(a)
                for a in g:
                    usage[a["id"]] += 1
                groups.append(g)
            # distinct loadouts
            sigs = [tuple(sorted(a["id"] for a in g)) for g in groups]
            if len(set(sigs)) < len(sigs):
                continue
        ratings = [rating(g, None) for g in groups]
        mean = sum(ratings) / len(ratings)
        var = sum((x - mean) ** 2 for x in ratings) / len(ratings)
        syn = sum(pair_compatibility(x, y)[0] for g in groups for x, y in itertools.combinations(g, 2))
        score = var * 100 - syn * 0.02
        if best_score is None or score < best_score:
            best, best_score = groups, score
    return best


def generate_fighters(theme, cfg, rng, universe):
    t = cfg["tournament"]
    n, k = t["participants"], t["abilities_per_fighter"]
    pool = theme["abilities"]
    groups = assign_loadouts(pool, n, k, t["abilities_unique"], rng.stream("loadouts"))
    taken = set()
    hues = [colorsys.rgb_to_hsv(*hex_to_rgb(g[0]["colors"][1]))[0] for g in groups]
    colors = _distinct_colors(n, rng.stream("colors"), hues)
    style_cfg = cfg["combat"].get("fighting_style", "auto")
    fighters = []
    for i, g in enumerate(groups):
        fr = rng.stream("fighter", i)
        name = make_name(g, fr, taken)
        taken.add(name)
        personality = style_cfg if style_cfg in PERSONALITIES else fr.choice(sorted(PERSONALITIES))
        traits = dict(PERSONALITIES[personality])
        for key in ("aggression", "caution", "evasive", "counter", "creativity"):
            traits[key] = round(min(0.98, max(0.05, fr.jitter(traits[key], 0.15))), 3)
        traits["reaction"] = round(fr.uniform(0.07, 0.15), 3)  # seconds
        traits["read"] = round(fr.uniform(0.45, 0.8), 3)       # defensive read skill
        traits["adaptability"] = round(fr.uniform(0.4, 0.9), 3)
        secondary = rgb_to_hex(tuple(min(1, c * 0.55 + 0.45) for c in hex_to_rgb(colors[i])))
        fid = stable_id("ftr", f"{theme['key']}:{t['random_seed']}:{name}")
        repertoire = build_repertoire(g, fr.stream("repertoire"), universe, cfg, theme.get("physical_weight", 0.2))
        f = {
            "id": fid,
            "name": name,
            "theme": theme["key"],
            "abilities": [a["id"] for a in g],
            "ability_names": [a["name"] for a in g],
            "color": colors[i],
            "secondary": secondary,
            "costume": (costume := choose_costume(theme, fr.stream("costume"))),
            "accessory": costume[0] if costume else fr.choice(ACCESSORIES),
            "weapons": [a["weapon"] for a in g if a.get("weapon")],
            "stance": fr.choice(STANCES),
            "build": round(fr.uniform(0.94, 1.06), 3),
            "personality": personality,
            "traits": traits,
            "rating": rating(g, personality),
            "repertoire": [tq["id"] for tq in repertoire],
            "signature_move": next((tq["name"] for tq in repertoire if tq["tier"] == "ultimate"), None),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "career": {"wins": 0, "losses": 0, "points_for": 0, "points_against": 0, "tournaments": []},
        }
        universe["fighters"].put(fid, f)
        fighters.append(f)
    return fighters
