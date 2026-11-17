"""Claude-generated theme packs for themes the engine does not know yet.

When a tournament theme matches no built-in pack, the engine asks Claude to
design a complete pack: abilities (mapped onto mechanical archetypes), real
weapons (existing catalogue entries or brand-new parametric weapons), costume
parts, the share of unarmed fighting, and arena biomes (existing or brand-new
parametric scenes). The response is constrained by a JSON schema whose enums
are the engine's drawable catalogues, then validated again locally, so every
generated pack is renderable and simulatable. The result is saved to
themes/<key>.json and reused afterwards (Claude is called once per theme).

Without credentials (or with creative.theme_generator = "offline") the engine
falls back to pack composition / the procedural generator. A pack JSON written
elsewhere (e.g. by Claude in claude.ai using `python -m stu themes prompt`)
can be imported with `python -m stu themes import <file>`.
"""
from __future__ import annotations

import copy
import json
import re
import time

from .arenas import BIOMES
from .catalog import ARCHETYPES
from .packs import COSTUMES, EXTRA_ARCHETYPES, WEAPONS

ARCHETYPES.update(EXTRA_ARCHETYPES)

MODEL = "claude-opus-5-5"

PROJECTILES = ["inherit", "orb", "shard", "bolt", "rock", "crescent", "disc", "seed", "ray", "void", "wave", "arrow",
               "bullet", "cannonball", "bomb", "bottle", "knife", "shuriken", "harpoon"]
ENV_FORMS = ["inherit", "pillar", "spikes", "geyser", "sky_strike", "vines", "hands", "light_pillar", "well", "column",
             "burst", "cannon_rain", "tentacles"]
ZONES = ["inherit", "none", "burning", "wet", "frozen", "vines", "shadow", "well", "cracked", "toxic"]
WEAPON_CLASSES = ["blade", "polearm", "blunt", "firearm", "bow", "staff", "claws", "shield", "fist"]
HEADS = ["none", "leaf", "barb", "trident", "blade", "cone", "orb", "star", "block", "spiked", "anchor", "axe", "club"]
GUARDS = ["none", "cross", "basket", "tsuba", "ring"]
STOCKS = ["none", "pistol", "flare", "rifle"]
FAR_TYPES = ["mountains", "volcanoes", "sea", "cave", "clouds", "city", "dunes", "forest", "bamboo", "castle", "dojo_wall", "town"]
PROP_TYPES = ["mast", "rigging", "cannon", "barrel", "crate", "palm", "chest", "gold_pile", "torch", "bones", "rock_spire",
              "lava_fall", "floating_rock", "crystals", "column", "arch", "monolith", "lantern", "paper_screen", "bamboo",
              "chimney", "antenna", "banner", "tent", "tree", "mushroom"]
GROUNDS = ["planks", "sand", "stone", "lava", "ice", "grass", "tatami", "tiles", "metal"]
AMBIENTS = ["ember", "snow", "rain", "spray", "leaves", "motes", "bubbles", "dust", "stars"]
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _obj(props, required=None):
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


def _arr(items):
    return {"type": "array", "items": items}


S, N, B, I = {"type": "string"}, {"type": "number"}, {"type": "boolean"}, {"type": "integer"}


def pack_schema():
    weapon_choice = {"type": "string"}  # existing key, a new_weapons key, or "none" (validated locally)
    ability = _obj({
        "name": S, "archetype": {"type": "string", "enum": sorted(ARCHETYPES)}, "weapon": weapon_choice,
        "origin": {"type": "string", "enum": ["hand", "mouth"]}, "physical": B,
        "projectile": {"type": "string", "enum": PROJECTILES}, "env_form": {"type": "string", "enum": ENV_FORMS},
        "zone": {"type": "string", "enum": ZONES}, "colors": _arr(S), "adjectives": _arr(S), "nouns": _arr(S),
        "description": S,
    })
    new_weapon = _obj({
        "key": S, "class": {"type": "string", "enum": WEAPON_CLASSES}, "length_m": N, "head": {"type": "string", "enum": HEADS},
        "curve": N, "blade_width": N, "guard": {"type": "string", "enum": GUARDS}, "stock": {"type": "string", "enum": STOCKS},
        "colors": _arr(S),
    })
    biome = _obj({
        "key": S, "far": {"type": "string", "enum": FAR_TYPES}, "props": _arr({"type": "string", "enum": PROP_TYPES}),
        "ground": {"type": "string", "enum": GROUNDS}, "ambient": {"type": "string", "enum": AMBIENTS},
        "day_sky_top": S, "day_sky_horizon": S, "night_sky_top": S, "night_sky_horizon": S,
        "far_color": S, "mid_color": S, "ground_color": S, "accent_color": S,
        "name_templates": _arr(S), "adjectives": _arr(S), "nouns": _arr(S), "lightning": B, "ships": B,
    })
    return _obj({
        "title": S, "title_words": _arr(S), "physical_weight": N, "abilities": _arr(ability), "new_weapons": _arr(new_weapon),
        "costumes": _arr({"type": "string", "enum": sorted(COSTUMES)}),
        "always_costumes": _arr({"type": "string", "enum": sorted(COSTUMES)}),
        "extras_min": I, "extras_max": I,
        "existing_biomes": _arr({"type": "string", "enum": sorted(BIOMES)}), "new_biomes": _arr(biome),
    })


def build_prompt(theme_name):
    weapons = ", ".join(f"{k} ({v['class']})" for k, v in sorted(WEAPONS.items()))
    costumes = ", ".join(f"{k} ({v})" for k, v in sorted(COSTUMES.items()))
    archetypes = "; ".join(f"{k}: {', '.join(v['tags'])}" for k, v in sorted(ARCHETYPES.items()))
    return f"""You are the creative director of a procedural stickman fighting-tournament series.
Design a complete theme pack for the tournament theme: "{theme_name}".

The pack drives combat mechanics, visuals and arenas, so everything must feel unmistakably like "{theme_name}".
Fighters are articulated stick figures; costume parts, weapons, projectiles and arenas are drawn procedurally from the
catalogues below, so only use catalogue values where an enum is given.

Requirements
- abilities: 10 to 14 abilities that someone who loves "{theme_name}" would expect (signature weapons, powers, creatures,
  fighting skills). Names short (1-3 words). Each maps to the mechanical archetype whose tags fit best.
  * weapon: a held weapon from the existing catalogue, a key you define in new_weapons, or "none" for powers.
    A physical weapon ability must have a weapon; never give a gun-like or thrown ability a melee weapon.
  * physical=true for weapons, martial skills and thrown objects; false for magic, elemental or supernatural powers.
  * origin="mouth" only for breath, roars, spit, eye beams and similar.
  * projectile/env_form/zone: pick what the ability visibly launches or creates, or "inherit" to keep the archetype's.
  * colors: three hex colours [highlight, main, dark] that read well on dark backgrounds.
  * adjectives/nouns: 3-5 evocative words each, used to name generated techniques.
- new_weapons: define weapons the theme needs that the catalogue lacks (0-6). length_m is metres from the hand
  (daggers 0.3, swords 0.8-1.1, spears 1.3-1.8). Colors are three hex values [edge, main, grip].
- costumes: 4-9 catalogue parts that give fighters a recognisable silhouette; always_costumes: parts every fighter
  wears (may be empty); extras_min/extras_max: how many non-head parts a fighter adds (0-3).
- physical_weight: 0.05-0.35, how much plain unarmed punching/kicking suits the theme (low for magic themes).
- existing_biomes and/or new_biomes: 3-5 arena scenes in total that look like places where "{theme_name}" happens.
  new_biomes use the far/props/ground/ambient catalogues with hex colours; name_templates use {{adj}} and {{noun}}.
- title: one or two words for the series; title_words: 3-4 tournament names.

Catalogues
- archetypes (key: tags): {archetypes}
- existing weapons: {weapons}
- costume parts (part: slot): {costumes}
- existing biomes: {", ".join(sorted(BIOMES))}

Return only the JSON object described by the schema."""


# ---------------------------------------------------------------------------
# Validation / conversion
# ---------------------------------------------------------------------------
def _hex(c, default):
    return c if isinstance(c, str) and HEX.match(c) else default


def _colors(cs, default):
    cs = [c for c in (cs or []) if isinstance(c, str) and HEX.match(c)]
    return (cs + default)[:3] if len(cs) < 3 else cs[:3]


def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "x"


def pack_to_theme(theme_name, data, make_ability, theme_key):
    """Validate a pack (from Claude or a file) and convert it into a theme."""
    key = theme_key(theme_name)
    weapons = {}
    for w in data.get("new_weapons", [])[:8]:
        wk = f"{key}_{_slug(w.get('key', 'weapon'))}"
        cls = w.get("class") if w.get("class") in WEAPON_CLASSES else "blade"
        spec = {"class": cls, "len": round(_clamp(w.get("length_m"), 0.0, 2.2, 0.9), 2),
                "colors": _colors(w.get("colors"), ["#f4f7fb", "#aab6c4", "#5b4127"])}
        if cls == "blade":
            spec.update(curve=round(_clamp(w.get("curve"), 0.0, 0.4, 0.1), 2), w=round(_clamp(w.get("blade_width"), 0.03, 0.12, 0.06), 3),
                        guard=w.get("guard") if w.get("guard") in GUARDS and w.get("guard") != "none" else "cross")
        if cls in ("polearm", "blunt", "staff"):
            spec["head"] = w.get("head") if w.get("head") in HEADS and w.get("head") != "none" else \
                {"polearm": "leaf", "blunt": "block", "staff": "orb"}[cls]
        if cls == "firearm":
            spec["stock"] = w.get("stock") if w.get("stock") in STOCKS and w.get("stock") != "none" else "pistol"
        weapons[_slug(w.get("key", wk))] = (wk, spec)
    for wk, spec in weapons.values():  # must exist before abilities are tuned to their weapons
        WEAPONS.setdefault(wk, copy.deepcopy(spec))
    abilities = []
    seen = set()
    for a in data.get("abilities", [])[:16]:
        name = str(a.get("name", "")).strip()[:28]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        arch = a.get("archetype") if a.get("archetype") in ARCHETYPES else "kinetic"
        over = {"colors": _colors(a.get("colors"), ARCHETYPES[arch]["colors"]), "physical": bool(a.get("physical")),
                "description": str(a.get("description", ""))[:200]}
        adj = [str(x)[:16] for x in a.get("adjectives", []) if str(x).strip()][:5]
        noun = [str(x)[:16] for x in a.get("nouns", []) if str(x).strip()][:5]
        if adj and noun:
            over["words"] = {"adj": adj, "noun": noun}
        w = str(a.get("weapon", "none")).strip()
        if w in WEAPONS:
            over["weapon"] = w
        elif _slug(w) in weapons:
            over["weapon"] = weapons[_slug(w)][0]
        else:
            over["weapon"] = None
        if a.get("origin") == "mouth":
            over["origin"] = "mouth"
        if a.get("projectile") in PROJECTILES and a.get("projectile") != "inherit":
            over["projectile"] = a["projectile"]
            if a["projectile"] in ("bomb", "bottle", "cannonball"):
                over["gravity"] = True
        if a.get("env_form") in ENV_FORMS and a.get("env_form") != "inherit":
            over["env_form"] = a["env_form"]
        if a.get("zone") in ZONES and a.get("zone") != "inherit":
            over["zone"] = None if a["zone"] == "none" else a["zone"]
        abilities.append(make_ability(key, name, arch, over))
    if len(abilities) < 4:
        raise ValueError("generated pack has too few valid abilities")
    biome_defs = {}
    for b in data.get("new_biomes", [])[:5]:
        bk = f"{key}_{_slug(b.get('key', 'arena'))}"
        names = [t for t in b.get("name_templates", []) if isinstance(t, str) and t.strip()][:4] or ["{adj} {noun}"]
        biome_defs[bk] = {
            "far": b.get("far") if b.get("far") in FAR_TYPES else "mountains",
            "props": [p for p in b.get("props", []) if p in PROP_TYPES][:5] or ["rock_spire"],
            "ground": b.get("ground") if b.get("ground") in GROUNDS else "stone",
            "ambient": b.get("ambient") if b.get("ambient") in AMBIENTS else "motes",
            "skies": {"day": (_hex(b.get("day_sky_top"), "#3a6ab0"), _hex(b.get("day_sky_horizon"), "#e0e8f0")),
                      "night": (_hex(b.get("night_sky_top"), "#05081a"), _hex(b.get("night_sky_horizon"), "#2a3a5c"))},
            "far_c": _hex(b.get("far_color"), "#2a3040"), "mid_c": _hex(b.get("mid_color"), "#3a3a48"),
            "ground_c": _hex(b.get("ground_color"), "#3a3430"), "accent": _hex(b.get("accent_color"), "#ffd27a"),
            "names": names, "adj": [str(x)[:16] for x in b.get("adjectives", [])][:6] or ["Grand"],
            "noun": [str(x)[:20] for x in b.get("nouns", [])][:6] or [theme_name.title()],
            "lightning": bool(b.get("lightning")), "ships": bool(b.get("ships")),
        }
    biomes = [b for b in data.get("existing_biomes", []) if b in BIOMES] + list(biome_defs)
    costumes = [c for c in data.get("costumes", []) if c in COSTUMES] or ["headband", "scarf"]
    always = [c for c in data.get("always_costumes", []) if c in COSTUMES]
    lo = int(_clamp(data.get("extras_min"), 0, 3, 0))
    hi = int(max(lo, _clamp(data.get("extras_max"), 0, 3, 2)))
    title = str(data.get("title") or theme_name.title())[:24]
    return {
        "key": key, "name": theme_name, "title": title,
        "title_words": [str(t)[:32] for t in data.get("title_words", []) if str(t).strip()][:4] or [f"{title} Clash"],
        "abilities": abilities, "costumes": costumes, "costume_rules": {"head": 1, "extras": (lo, hi), "always": always},
        "biomes": biomes or ["caldera", "storm_peak", "frozen_sanctum"],
        "physical_weight": round(_clamp(data.get("physical_weight"), 0.05, 0.35, 0.2), 3),
        "weapons": {wk: spec for wk, spec in weapons.values()}, "biome_defs": biome_defs,
        "packs": [], "generated_by": "claude", "generator_model": data.get("_model", MODEL),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "expansions": [],
    }


def register_theme_assets(theme):
    """Make a theme's custom weapons and biomes available to sim + renderer."""
    for k, spec in (theme.get("weapons") or {}).items():
        WEAPONS.setdefault(k, copy.deepcopy(spec))
    for k, spec in (theme.get("biome_defs") or {}).items():
        b = copy.deepcopy(spec)
        b["skies"] = {t: tuple(v) for t, v in b["skies"].items()}
        BIOMES.setdefault(k, b)


def generate_with_claude(theme_name, log=print):
    """Ask Claude for a pack. Returns the raw validated-by-schema dict or None."""
    try:
        import anthropic
    except ImportError:
        log("  (anthropic SDK not installed: pip install anthropic — using offline theme generator)")
        return None
    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": pack_schema()}},
            messages=[{"role": "user", "content": build_prompt(theme_name)}],
        )
    except anthropic.AuthenticationError:
        log("  (no Anthropic credentials: set ANTHROPIC_API_KEY or run `ant auth login` — using offline theme generator)")
        return None
    except anthropic.APIConnectionError:
        log("  (Claude API unreachable — using offline theme generator)")
        return None
    except anthropic.APIStatusError as e:
        log(f"  (Claude API error {e.status_code} — using offline theme generator)")
        return None
    except (TypeError, anthropic.AnthropicError) as e:
        # e.g. no credentials configured at all (the SDK raises before sending)
        log(f"  (Claude API not available: {type(e).__name__} — using offline theme generator)")
        return None
    if response.stop_reason == "refusal":
        log("  (Claude declined to design this theme — using offline theme generator)")
        return None
    if response.stop_reason == "max_tokens":
        log("  (theme pack response was cut off — using offline theme generator)")
        return None
    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        return None
    data = json.loads(text)
    data["_model"] = response.model
    return data
