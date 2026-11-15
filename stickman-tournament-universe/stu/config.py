"""Configuration loading, defaults and "auto" resolution.

Only theme / participants / abilities_per_fighter are essential. Every other
value has a default, and every "auto" value is resolved here into a concrete
decision that is saved with the tournament (so resumes and replays are exact).
"""
from __future__ import annotations

import copy
import os
import random
import time

import yaml

from . import PROJECT_ROOT

DEFAULTS = {
    "tournament": {
        "name": "auto",
        "theme": "elements",
        "participants": 8,
        "abilities_per_fighter": 2,
        "abilities_unique": "auto",
        "points_to_win": 3,
        "minimum_fight_duration_seconds": 63,
        "target_fight_duration_seconds": 75,
        "maximum_fight_duration_seconds": 120,
        "initial_matchmaking": "random",
        "subsequent_matchmaking": "winners_bracket",
        "tournament_format": "single_elimination",
        "random_seed": None,
    },
    "combat": {
        "fighting_style": "auto",
        "combat_speed": "auto",
        "attack_variety": "maximum",
        "combination_complexity": "maximum",
        "physical_combat_enabled": True,
        "special_abilities_enabled": True,
        "environmental_interactions": True,
        "cinematic_finishers": True,
        "adaptive_ai": True,
    },
    "video": {
        "width": 1080,
        "height": 1920,
        "fps": 60,
        "orientation": "vertical",
        "export_individual_fights": True,
        "export_complete_tournament": True,
        "export_highlights": True,
        "codec": "h264",
        "quality": "high",
        "render_workers": "auto",
    },
    "creative": {
        "choreography": "procedural",
        "camera": "cinematic_dynamic",
        "visual_effects": "high_quality",
        "particle_effects": True,
        "screen_shake": "auto",
        "slow_motion": "auto",
        "motion_blur": "subtle",
        "sound_effects": True,
        "music": "optional",
        "subtitles": False,
    },
}

QUALITY_PRESETS = {
    "draft": {"crf": 26, "preset": "veryfast"},
    "medium": {"crf": 21, "preset": "fast"},
    "high": {"crf": 18, "preset": "medium"},
    "max": {"crf": 15, "preset": "slow"},
}


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def parse_override(expr: str):
    """'video.fps=30' -> (['video','fps'], 30)"""
    key, _, raw = expr.partition("=")
    return key.strip().split("."), yaml.safe_load(raw)


def load_config(path=None, overrides=None):
    path = path or os.path.join(PROJECT_ROOT, "config.yaml")
    user = {}
    if path and os.path.exists(path):
        with open(path) as f:
            user = yaml.safe_load(f) or {}
    cfg = deep_merge(DEFAULTS, user)
    for keys, value in overrides or []:
        node = cfg
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
    validate_config(cfg)
    return cfg


def validate_config(cfg):
    t = cfg["tournament"]
    if not isinstance(t["participants"], int) or t["participants"] < 2:
        raise ValueError("tournament.participants must be an integer >= 2")
    if not isinstance(t["abilities_per_fighter"], int) or not 1 <= t["abilities_per_fighter"] <= 5:
        raise ValueError("tournament.abilities_per_fighter must be 1..5")
    if t["points_to_win"] < 1:
        raise ValueError("points_to_win must be >= 1")
    mn, tg, mx = (t["minimum_fight_duration_seconds"], t["target_fight_duration_seconds"],
                  t["maximum_fight_duration_seconds"])
    if not mn <= tg <= mx:
        raise ValueError("fight durations must satisfy minimum <= target <= maximum")
    if t["tournament_format"] != "single_elimination":
        raise ValueError("only single_elimination is implemented")
    v = cfg["video"]
    if v["fps"] < 24:
        raise ValueError("video.fps must be >= 24")
    if v["codec"] != "h264":
        raise ValueError("only h264 export is implemented")


def resolve_auto(cfg, pool_size: int):
    """Turn every "auto" into a concrete, recorded decision."""
    cfg = copy.deepcopy(cfg)
    t, c, v, cr = cfg["tournament"], cfg["combat"], cfg["video"], cfg["creative"]
    if t["random_seed"] is None:
        t["random_seed"] = random.SystemRandom().randrange(1, 2**31)
    needed = t["participants"] * t["abilities_per_fighter"]
    if t["abilities_unique"] == "auto":
        # Unique loadouts only when the pool can actually support it.
        t["abilities_unique"] = needed <= pool_size
    if c["combat_speed"] == "auto":
        c["combat_speed"] = 1.0
    if cr["screen_shake"] == "auto":
        cr["screen_shake"] = 1.0
    elif isinstance(cr["screen_shake"], str):
        cr["screen_shake"] = {"off": 0.0, "low": 0.5, "medium": 1.0, "high": 1.5}.get(cr["screen_shake"], 1.0)
    if cr["slow_motion"] == "auto":
        cr["slow_motion"] = "dramatic"
    if cr["music"] in ("optional", "auto"):
        cr["music"] = "procedural"
    if v["render_workers"] == "auto":
        v["render_workers"] = max(1, min(8, (os.cpu_count() or 2)))
    v["encoder"] = QUALITY_PRESETS.get(v["quality"], QUALITY_PRESETS["high"])
    cfg["resolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return cfg
