"""Theme package creation, loading and expansion.

A theme package (themes/<key>.json) contains everything a tournament needs:
abilities (with tags, VFX/SFX profiles, naming flavour), arenas and title
vocabulary. Built-in seed knowledge exists for a few themes; any other theme is
synthesised procedurally from the archetype catalogue. Packages are saved and
re-used, and expanded (never overwritten) when a tournament needs more content.
"""
from __future__ import annotations

import copy
import re
import time

from ..core.mathutil import hex_to_rgb, mix, rgb_to_hex
from ..core.rng import RNG
from ..persistence.library import stable_id
from .catalog import ARCHETYPES, ARENAS_GENERIC, LEXICON, THEME_SEEDS


def theme_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "custom"


def archetype_for_name(name: str, rng: RNG) -> str:
    low = name.lower()
    best, best_len = None, 0
    for arch, words in LEXICON.items():
        for w in words:
            if w in low and len(w) > best_len:
                best, best_len = arch, len(w)
    return best or rng.choice(sorted(ARCHETYPES))


def make_ability(theme_key_, name, archetype, overrides=None):
    base = copy.deepcopy(ARCHETYPES[archetype])
    base.update(copy.deepcopy(overrides or {}))
    key = theme_key(name)
    return {
        "id": stable_id("ab", f"{theme_key_}:{key}"),
        "key": key,
        "name": name,
        "theme": theme_key_,
        "archetype": archetype,
        **base,
    }


def _variant_ability(theme_key_, a, b, rng: RNG):
    """Invent a new hybrid ability from two existing ones (theme expansion)."""
    adj = rng.choice(a["words"]["adj"])
    noun = rng.choice(b["words"]["noun"])
    name = f"{adj} {noun}"
    over = {
        "tags": sorted(set(a["tags"][:2] + b["tags"][:2])),
        "colors": [rgb_to_hex(mix(hex_to_rgb(x), hex_to_rgb(y), 0.5)) for x, y in zip(a["colors"], b["colors"])],
        "words": {"adj": a["words"]["adj"][:2] + b["words"]["adj"][:2], "noun": a["words"]["noun"][:2] + b["words"]["noun"][:2]},
        "variant_of": [a["id"], b["id"]],
    }
    return make_ability(theme_key_, name, a["archetype"], over)


def generate_theme(name: str, rng: RNG, custom_abilities=None):
    key = theme_key(name)
    seed = THEME_SEEDS.get(key)
    abilities = []
    if custom_abilities:
        for n in custom_abilities:
            abilities.append(make_ability(key, n, archetype_for_name(n, rng)))
    elif seed:
        for n, arch, over in seed["abilities"]:
            abilities.append(make_ability(key, n, arch, over))
    else:
        # Procedural theme: pick archetypes (lexicon hits on the theme name are
        # favoured) and name abilities in the theme's own vocabulary.
        root = name.strip().title()
        primary = archetype_for_name(name, rng)
        pool = sorted(ARCHETYPES)
        rng.shuffle(pool)
        chosen = [primary] + [a for a in pool if a != primary][:9]
        for arch in chosen:
            noun = rng.choice(ARCHETYPES[arch]["words"]["noun"])
            abilities.append(make_ability(key, f"{root} {noun}", arch))
    arena_idx = seed["arenas"] if seed else rng.sample(range(len(ARENAS_GENERIC)), 5)
    title = seed["title"] if seed else name.strip().title()
    title_words = seed["title_words"] if seed else [f"{title} Clash", f"{title} Championship", f"{title} Royale"]
    return {
        "key": key,
        "name": name,
        "title": title,
        "title_words": title_words,
        "abilities": abilities,
        "arenas": [copy.deepcopy(ARENAS_GENERIC[i]) for i in arena_idx],
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "expansions": [],
    }


def load_or_create_theme(universe, name, rng: RNG, needed_abilities=0, custom_abilities=None):
    key = theme_key(name)
    theme = universe.load_theme(key)
    created = False
    if theme is None:
        theme = generate_theme(name, rng.stream("theme", key), custom_abilities)
        created = True
    # Expansion: make sure the pool can serve the tournament.
    exp_rng = rng.stream("theme_expand", key, len(theme["abilities"]))
    while len(theme["abilities"]) < needed_abilities:
        a, b = exp_rng.sample(theme["abilities"], 2)
        if a["archetype"] == b["archetype"]:
            continue
        v = _variant_ability(key, a, b, exp_rng)
        if any(x["id"] == v["id"] for x in theme["abilities"]):
            continue
        theme["abilities"].append(v)
        theme["expansions"].append({"ability": v["id"], "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        created = True
    for ab in theme["abilities"]:
        universe["abilities"].put(ab["id"], ab)
    if created:
        universe.save_theme(theme)
    return theme
