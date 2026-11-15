"""Theme package creation, loading, upgrading and expansion.

Resolution order for a theme name:
1. a saved package in themes/<key>.json (upgraded in place if older);
2. a built-in knowledge pack (pirates, dragons, ninjas, knights, wizards, ...);
3. *composition*: every pack whose aliases appear in the name is merged
   ("space pirates" -> cosmic + pirates, "dragon knights" -> dragons + knights)
   with their abilities, costumes, weapons and arena biomes;
4. procedural fallback from the archetype catalogue.
"""
from __future__ import annotations

import copy
import re
import time

from ..core.mathutil import hex_to_rgb, mix, rgb_to_hex
from ..persistence.library import stable_id
from .catalog import ARCHETYPES, LEXICON
from .packs import EXTRA_ARCHETYPES, PACK_ALIASES, THEME_PACKS, weapon_class

ARCHETYPES.update(EXTRA_ARCHETYPES)
LEXICON.setdefault("firearm", ["gun", "pistol", "rifle", "flintlock", "musket", "blaster", "revolver", "cannon"])
LEXICON.setdefault("explosive", ["bomb", "keg", "grenade", "dynamite", "rocket", "powder"])
LEXICON.setdefault("thrown", ["knife", "knives", "kunai", "dagger", "shuriken", "throw"])
LEXICON.setdefault("toxic", ["venom", "poison", "acid", "toxic", "plague"])

GENERIC_BIOMES = ["caldera", "storm_peak", "frozen_sanctum", "elder_grove", "abyssal_shrine", "sunken_coliseum", "golden_dunes", "starfall_rift"]
GENERIC_COSTUMES = ["headband", "scarf", "spikes", "horns", "halo", "ponytail", "visor", "topknot", "cape"]


def theme_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "custom"


def archetype_for_name(name: str, rng) -> str:
    low = name.lower()
    best, best_len = None, 0
    for arch, words in LEXICON.items():
        for w in words:
            if w in low and len(w) > best_len:
                best, best_len = arch, len(w)
    return best or rng.choice(sorted(ARCHETYPES))


def make_ability(theme_key_, name, archetype, overrides=None):
    base = copy.deepcopy(ARCHETYPES[archetype])
    over = copy.deepcopy(overrides or {})
    for k in ("affinity", "mod_affinity"):
        if k in over:
            merged = dict(base.get(k, {}))
            merged.update(over.pop(k))
            base[k] = merged
    base.update(over)
    if base.get("origin") == "mouth":  # breath powers: ranged first, few fist strikes
        aff = dict(base["affinity"])
        for d in ("punch", "kick", "barrage", "uppercut", "sweep"):
            aff[d] = aff.get(d, 0.25) * 0.3
        aff["beam"] = max(aff.get("beam", 0.5), 1.0)
        aff["projectile"] = max(aff.get("projectile", 0.5), 1.0)
        base["affinity"] = aff
    if base.get("weapon") and weapon_class(base["weapon"]) in ("blade", "polearm", "blunt", "claws", "staff"):
        aff = dict(base["affinity"])
        aff["summon_weapon"] = max(aff.get("summon_weapon", 0.0), 1.1)
        for d in ("punch", "barrage", "uppercut"):
            aff[d] = min(aff.get(d, 0.1), 0.15)
        base["affinity"] = aff
    if base.get("weapon") and "physical" not in base:
        base["physical"] = True
    key = theme_key(name)
    return {"id": stable_id("ab", f"{theme_key_}:{key}"), "key": key, "name": name, "theme": theme_key_, "archetype": archetype, **base}


def _variant_ability(theme_key_, a, b, rng):
    adj = rng.choice(a["words"]["adj"])
    noun = rng.choice(b["words"]["noun"])
    over = {
        "tags": sorted(set(a["tags"][:2] + b["tags"][:2])),
        "colors": [rgb_to_hex(mix(hex_to_rgb(x), hex_to_rgb(y), 0.5)) for x, y in zip(a["colors"], b["colors"])],
        "words": {"adj": a["words"]["adj"][:2] + b["words"]["adj"][:2], "noun": a["words"]["noun"][:2] + b["words"]["noun"][:2]},
        "variant_of": [a["id"], b["id"]],
    }
    for k in ("weapon", "origin", "physical"):
        if a.get(k):
            over[k] = a[k]
    return make_ability(theme_key_, f"{adj} {noun}", a["archetype"], over)


def matched_packs(name):
    low = name.lower()
    key = theme_key(name)
    if key in THEME_PACKS:
        return [key]
    hits = []
    for pk, aliases in PACK_ALIASES.items():
        pos = min((low.find(a) for a in aliases if a in low), default=-1)
        if pos >= 0:
            hits.append((pos, pk))
    return [pk for _, pk in sorted(hits)]


def _pack_fields(key, packs):
    if not packs:
        return {}
    ps = [THEME_PACKS[p] for p in packs]
    costumes, biomes = [], []
    for p in ps:
        costumes += [c for c in p.get("costumes", []) if c not in costumes]
        biomes += [b for b in p.get("biomes", []) if b not in biomes]
    rules = copy.deepcopy(ps[0].get("costume_rules", {"head": 1, "extras": (0, 2)}))
    return {"costumes": costumes, "costume_rules": rules, "biomes": biomes,
            "physical_weight": sum(p.get("physical_weight", 0.2) for p in ps) / len(ps), "packs": packs}


def generate_theme(name: str, rng, custom_abilities=None, mode="offline", log=print):
    key = theme_key(name)
    if mode in ("auto", "claude") and not custom_abilities and key not in THEME_PACKS:
        from .ai_pack import generate_with_claude, pack_to_theme
        log(f"  theme '{name}' is new: asking Claude to design a theme pack ...")
        data = generate_with_claude(name, log=log)
        if data is not None:
            try:
                theme = pack_to_theme(name, data, make_ability, theme_key)
                log(f"  Claude designed '{theme['title']}': {len(theme['abilities'])} abilities, "
                    f"{len(theme['weapons'])} new weapons, {len(theme['biome_defs'])} new arenas")
                return theme
            except (ValueError, KeyError, TypeError) as ex:
                log(f"  (generated pack rejected by validation: {ex} — using offline theme generator)")
        elif mode == "claude":
            raise RuntimeError("creative.theme_generator is 'claude' but no pack could be generated")
    packs = matched_packs(name)
    abilities = []
    if custom_abilities:
        for n in custom_abilities:
            abilities.append(make_ability(key, n, archetype_for_name(n, rng)))
    elif packs:
        lists = [THEME_PACKS[p]["abilities"] for p in packs]
        if len(lists) == 1:
            chosen = lists[0]
        else:  # composition: interleave abilities of all matched packs
            chosen, i = [], 0
            while any(i < len(l) for l in lists) and len(chosen) < 14:
                for l in lists:
                    if i < len(l):
                        chosen.append(l[i])
                i += 1
        seen = set()
        for n, arch, over in chosen:
            if n not in seen:
                seen.add(n)
                abilities.append(make_ability(key, n, arch, over))
    else:
        root = name.strip().title()
        primary = archetype_for_name(name, rng)
        pool = sorted(ARCHETYPES)
        rng.shuffle(pool)
        for arch in [primary] + [a for a in pool if a != primary][:9]:
            noun = rng.choice(ARCHETYPES[arch]["words"]["noun"])
            abilities.append(make_ability(key, f"{root} {noun}", arch))
    fields = _pack_fields(key, packs)
    if len(packs) == 1:
        title, title_words = THEME_PACKS[packs[0]]["title"], THEME_PACKS[packs[0]]["title_words"]
    else:
        title = name.strip().title()
        title_words = [f"{title} Clash", f"{title} Championship", f"{title} Royale"]
    return {
        "key": key, "name": name, "title": title, "title_words": title_words, "abilities": abilities,
        "costumes": fields.get("costumes", GENERIC_COSTUMES), "costume_rules": fields.get("costume_rules", {"head": 1, "extras": (0, 1)}),
        "biomes": fields.get("biomes", rng.sample(GENERIC_BIOMES, 4)), "physical_weight": fields.get("physical_weight", 0.2),
        "packs": packs, "generated_by": "pack" if len(packs) == 1 else ("composition" if packs else "procedural"),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "expansions": [],
    }


def upgrade_theme(theme, rng):
    """Bring packages saved by older engine versions up to date (merge only)."""
    if theme.get("generated_by") in ("claude", "imported"):
        return False
    changed = False
    fresh = generate_theme(theme["name"], rng, mode="offline")
    for k in ("costumes", "costume_rules", "biomes", "physical_weight", "packs", "generated_by"):
        if k not in theme:
            theme[k] = fresh[k]
            changed = True
    by_name = {a["name"]: a for a in fresh["abilities"]}
    for ab in theme["abilities"]:
        f = by_name.get(ab["name"])
        if f:
            for k in ("weapon", "physical", "origin", "projectile", "env_form", "gravity", "zone"):
                if k in f and ab.get(k) != f[k]:
                    ab[k] = f[k]
                    changed = True
    return changed


def load_or_create_theme(universe, name, rng, needed_abilities=0, custom_abilities=None, mode="offline", log=print):
    from .ai_pack import register_theme_assets
    key = theme_key(name)
    theme = universe.load_theme(key)
    created = False
    if theme is None:
        theme = generate_theme(name, rng.stream("theme", key), custom_abilities, mode=mode, log=log)
        created = True
    elif upgrade_theme(theme, rng.stream("theme", key)):
        created = True
    exp_rng = rng.stream("theme_expand", key, len(theme["abilities"]))
    tries = 0
    while len(theme["abilities"]) < needed_abilities and tries < 200:
        tries += 1
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
        universe["abilities"]._validate(ab["id"], ab)
        universe["abilities"].items[ab["id"]] = ab
    universe["abilities"].dirty = True
    register_theme_assets(theme)
    if created:
        universe.save_theme(theme)
    return theme
