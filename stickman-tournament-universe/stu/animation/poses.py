"""Keypose library + procedural pose synthesis for every action state.

Templates are stored as data (and persisted to library/animations.json) so new
procedural variants can be added without code. Each technique stage is played
as anticipation -> action -> impact hold -> recovery with dedicated easing.
"""
from __future__ import annotations

import math

from ..core.mathutil import clamp, ease_in, ease_out, ease_out_back, lerp, smoothstep
from .rig import POSE_KEYS

STANCES = {
    "orthodox": dict(lean=0.08, crouch=0.1, head=-0.05, rot=0.0, hfx=0.24, hfy=0.10, hbx=0.14, hby=0.02,
                     ffx=0.27, ffy=0.0, fbx=-0.27, fby=0.0, ffree=0.0, fbfree=0.0),
    "southpaw": dict(lean=0.06, crouch=0.12, head=-0.05, rot=0.0, hfx=0.30, hfy=0.04, hbx=0.10, hby=0.12,
                     ffx=0.30, ffy=0.0, fbx=-0.24, fby=0.0, ffree=0.0, fbfree=0.0),
    "low": dict(lean=0.16, crouch=0.2, head=-0.1, rot=0.0, hfx=0.30, hfy=0.0, hbx=0.12, hby=-0.04,
                ffx=0.36, ffy=0.0, fbx=-0.34, fby=0.0, ffree=0.0, fbfree=0.0),
    "upright": dict(lean=0.03, crouch=0.05, head=0.0, rot=0.0, hfx=0.22, hfy=0.16, hbx=0.16, hby=0.08,
                    ffx=0.22, ffy=0.0, fbx=-0.22, fby=0.0, ffree=0.0, fbfree=0.0),
}


def P(base, **kw):
    d = dict(base)
    d.update(kw)
    return d


S = STANCES["orthodox"]

# delivery -> list of variants; variant = {"limb": effector, "keys": [antic, strike], "lunge": m}
TEMPLATES = {
    "punch": [
        {"limb": "hand_f", "lunge": 0.28, "keys": [
            P(S, lean=0.04, crouch=0.14, hfx=0.10, hfy=0.06, ffx=0.30),
            P(S, lean=0.30, crouch=0.17, hfx=0.62, hfy=0.04, hbx=0.10, hby=0.0, ffx=0.50, fbx=-0.30)]},
        {"limb": "hand_b", "lunge": 0.32, "keys": [
            P(S, lean=-0.06, crouch=0.12, hbx=-0.02, hby=0.04, hfx=0.24, hfy=0.14),
            P(S, lean=0.42, crouch=0.16, hbx=0.62, hby=0.05, hfx=0.06, hfy=0.06, ffx=0.52, fbx=-0.26)]},
        {"limb": "hand_f", "lunge": 0.22, "keys": [
            P(S, lean=-0.22, crouch=0.1, hfx=-0.12, hfy=0.38, hbx=0.12, hby=0.0),
            P(S, lean=0.38, crouch=0.18, hfx=0.56, hfy=0.24, hbx=0.0, hby=-0.08, ffx=0.46)]},
    ],
    "kick": [
        {"limb": "foot_f", "lunge": 0.16, "keys": [
            P(S, lean=-0.14, crouch=0.06, ffx=0.26, ffy=0.44, ffree=1.0, fbx=-0.12, hfx=0.2, hfy=0.12, hbx=-0.02),
            P(S, lean=-0.34, crouch=0.02, ffx=0.98, ffy=0.88, ffree=1.0, fbx=-0.10, hfx=0.14, hfy=0.1, hbx=-0.28, hby=-0.08)]},
        {"limb": "foot_b", "lunge": 0.12, "keys": [
            P(S, lean=-0.08, crouch=0.06, fbx=0.06, fby=0.46, fbfree=1.0, ffx=0.06, hfx=0.18, hfy=0.16, hbx=-0.1, hby=0.08),
            P(S, lean=-0.48, crouch=0.02, fbx=0.86, fby=1.26, fbfree=1.0, ffx=0.04, hfx=0.1, hfy=0.2, hbx=-0.36, hby=0.02)]},
        {"limb": "foot_f", "lunge": 0.2, "keys": [
            P(S, lean=0.34, crouch=0.08, ffx=0.0, ffy=0.36, ffree=1.0, fbx=-0.1, hfx=0.1, hfy=-0.1, hbx=-0.1),
            P(S, lean=0.62, crouch=0.06, ffx=1.02, ffy=0.72, ffree=1.0, fbx=-0.18, hfx=-0.1, hfy=-0.2, hbx=-0.3, hby=-0.2)]},
    ],
    "sweep": [
        {"limb": "foot_f", "lunge": 0.1, "keys": [
            P(S, lean=0.36, crouch=0.42, ffx=0.15, ffy=0.05, ffree=1.0, fbx=-0.36, hfx=0.30, hfy=-0.50, hbx=-0.2, hby=-0.4),
            P(S, lean=0.46, crouch=0.5, ffx=1.06, ffy=0.08, ffree=1.0, fbx=-0.30, hfx=0.36, hfy=-0.56, hbx=-0.3, hby=-0.3)]},
    ],
    "uppercut": [
        {"limb": "hand_f", "lunge": 0.2, "keys": [
            P(S, lean=0.32, crouch=0.38, hfx=0.14, hfy=-0.40, hbx=0.2, hby=0.1, ffx=0.36, fbx=-0.32),
            P(S, lean=-0.12, crouch=-0.06, hfx=0.22, hfy=0.62, hbx=0.0, hby=0.0, ffx=0.3, ffy=0.12, ffree=1.0, fbx=-0.2)]},
    ],
    "aerial_strike": [
        {"limb": "foot_f", "lunge": 0.0, "keys": [
            P(S, lean=-0.2, crouch=0.0, ffx=0.25, ffy=0.55, ffree=1.0, fbx=-0.05, fby=0.45, fbfree=1.0, hfx=0.1, hfy=0.3, hbx=-0.2, hby=0.2),
            P(S, lean=-0.55, crouch=0.0, ffx=0.78, ffy=0.05, ffree=1.0, fbx=-0.15, fby=0.55, fbfree=1.0, hfx=0.1, hfy=0.35, hbx=-0.35, hby=0.25)]},
        {"limb": "hand_f", "lunge": 0.0, "keys": [
            P(S, lean=-0.1, crouch=0.0, hfx=-0.1, hfy=0.4, ffx=0.2, ffy=0.45, ffree=1.0, fbx=-0.2, fby=0.35, fbfree=1.0),
            P(S, lean=0.5, crouch=0.0, hfx=0.62, hfy=-0.18, hbx=-0.3, hby=0.1, ffx=0.1, ffy=0.4, ffree=1.0, fbx=-0.35, fby=0.45, fbfree=1.0)]},
    ],
    "slam": [
        {"limb": "hand_f", "lunge": 0.15, "keys": [
            P(S, lean=-0.32, crouch=0.04, hfx=0.06, hfy=0.60, hbx=-0.04, hby=0.60),
            P(S, lean=0.72, crouch=0.40, hfx=0.46, hfy=-0.56, hbx=0.40, hby=-0.56, ffx=0.40, fbx=-0.36)]},
    ],
    "grapple": [
        {"limb": "hand_f", "lunge": 0.3, "keys": [
            P(S, lean=0.26, crouch=0.18, hfx=0.56, hfy=0.0, hbx=0.50, hby=-0.06, ffx=0.42),
            P(S, lean=0.32, crouch=0.2, hfx=0.50, hfy=0.04, hbx=0.46, hby=0.0, ffx=0.46),
            P(S, lean=-0.62, crouch=0.08, hfx=-0.22, hfy=0.56, hbx=-0.26, hby=0.50, ffx=0.36, fbx=-0.34)]},
    ],
    "charge": [
        {"limb": "chest", "lunge": 0.0, "keys": [
            P(S, lean=0.42, crouch=0.28, hfx=0.30, hfy=-0.10, hbx=0.05, hby=-0.10),
            P(S, lean=0.78, crouch=0.30, hfx=0.36, hfy=0.06, hbx=0.10, hby=-0.20)]},
    ],
    "projectile": [
        {"limb": "hand_f", "lunge": 0.12, "keys": [
            P(S, lean=-0.16, crouch=0.16, hfx=-0.06, hfy=-0.16, hbx=-0.12, hby=-0.18),
            P(S, lean=0.26, crouch=0.18, hfx=0.62, hfy=0.02, hbx=0.58, hby=-0.04, ffx=0.46, fbx=-0.34)]},
        {"limb": "hand_f", "lunge": 0.1, "keys": [
            P(S, lean=-0.30, crouch=0.1, hfx=-0.36, hfy=0.34, hbx=0.3, hby=0.0),
            P(S, lean=0.36, crouch=0.16, hfx=0.60, hfy=0.0, hbx=-0.22, hby=-0.2, ffx=0.46)]},
        {"limb": "hand_f", "lunge": 0.05, "keys": [
            P(S, lean=0.1, crouch=0.26, hfx=0.0, hfy=-0.32, hbx=-0.1, hby=-0.3),
            P(S, lean=-0.08, crouch=0.08, hfx=0.48, hfy=0.36, hbx=0.4, hby=0.3)]},
    ],
    "beam": [
        {"limb": "hand_f", "lunge": 0.0, "keys": [
            P(S, lean=-0.1, crouch=0.25, hfx=-0.16, hfy=-0.32, hbx=-0.18, hby=-0.35, ffx=0.42, fbx=-0.42),
            P(S, lean=0.18, crouch=0.24, hfx=0.62, hfy=0.0, hbx=0.60, hby=-0.04, ffx=0.44, fbx=-0.44)]},
    ],
    "explosion": [
        {"limb": "chest", "lunge": 0.0, "keys": [
            P(S, lean=0.26, crouch=0.40, hfx=0.18, hfy=-0.1, hbx=0.12, hby=-0.12),
            P(S, lean=-0.2, crouch=-0.04, hfx=0.45, hfy=0.42, hbx=-0.45, hby=0.42, ffx=0.38, fbx=-0.38)]},
    ],
    "counter": [
        {"limb": "hand_f", "lunge": 0.25, "keys": [
            P(S, lean=-0.05, crouch=0.2, hfx=0.35, hfy=-0.05, hbx=0.25, hby=0.15),
            P(S, lean=0.36, crouch=0.18, hfx=0.62, hfy=0.06, hbx=0.0, hby=-0.05, ffx=0.48)]},
    ],
    "summon_weapon": [
        {"limb": "weapon", "lunge": 0.3, "keys": [
            P(S, lean=-0.22, crouch=0.1, hfx=-0.2, hfy=0.5, hbx=-0.15, hby=0.45),
            P(S, lean=0.46, crouch=0.2, hfx=0.55, hfy=-0.3, hbx=0.3, hby=-0.2, ffx=0.5, fbx=-0.3)]},
        {"limb": "weapon", "lunge": 0.24, "keys": [
            P(S, lean=0.3, crouch=0.26, hfx=0.1, hfy=-0.5, hbx=0.0, hby=-0.4),
            P(S, lean=-0.12, crouch=0.06, hfx=0.4, hfy=0.55, hbx=-0.2, hby=0.1, ffx=0.46)]},
    ],
    "env_strike": [
        {"limb": "hand_f", "lunge": 0.05, "keys": [
            P(S, lean=0.3, crouch=0.3, hfx=0.2, hfy=0.28, hbx=-0.1, hby=0.1),
            P(S, lean=0.56, crouch=0.46, hfx=0.46, hfy=-0.62, hbx=-0.3, hby=-0.2, ffx=0.42, fbx=-0.4)]},
    ],
    "barrage": [
        {"limb": "hand_f", "lunge": 0.15, "keys": [
            P(S, lean=0.1, crouch=0.16, hfx=0.12, hfy=0.06),
            P(S, lean=0.3, crouch=0.18, hfx=0.60, hfy=0.05, hbx=0.1, ffx=0.46)]},
    ],
}

POSES = {
    "dash": P(S, lean=0.62, crouch=0.2, hfx=0.02, hfy=-0.26, hbx=-0.38, hby=-0.18, head=0.1),
    "jump_up": P(S, lean=0.0, crouch=0.0, ffx=0.25, ffy=0.42, ffree=1.0, fbx=-0.15, fby=0.28, fbfree=1.0, hfx=0.22, hfy=0.26, hbx=-0.15, hby=0.3),
    "fall": P(S, lean=0.05, crouch=0.0, ffx=0.22, ffy=0.18, ffree=1.0, fbx=-0.2, fby=0.08, fbfree=1.0, hfx=0.28, hfy=0.32, hbx=-0.24, hby=0.38),
    "block": P(S, lean=0.02, crouch=0.18, head=-0.16, hfx=0.24, hfy=0.18, hbx=0.22, hby=0.04, ffx=0.3, fbx=-0.32),
    "backstep": P(S, lean=-0.34, crouch=0.2, hfx=0.16, hfy=0.14, hbx=0.05, hby=0.05),
    "tuck": P(S, lean=0.3, crouch=0.42, head=0.3, hfx=0.25, hfy=-0.25, hbx=0.2, hby=-0.3, ffx=0.3, ffy=0.4, ffree=1.0, fbx=0.15, fby=0.35, fbfree=1.0),
    "hit_high": P(S, lean=-0.48, crouch=0.12, head=0.34, hfx=-0.1, hfy=0.36, hbx=-0.32, hby=0.22),
    "hit_low": P(S, lean=0.58, crouch=0.24, head=-0.3, hfx=0.16, hfy=-0.26, hbx=0.10, hby=-0.32),
    "launched": P(S, lean=-0.3, crouch=0.0, head=0.4, hfx=-0.2, hfy=0.45, hbx=-0.4, hby=0.3, ffx=0.35, ffy=0.3, ffree=1.0, fbx=0.05, fby=0.1, fbfree=1.0),
    "lying": P(S, lean=0.0, crouch=0.78, head=0.15, rot=1.48, hfx=0.36, hfy=0.12, hbx=0.2, hby=-0.25, ffx=0.42, ffy=0.15, ffree=1.0, fbx=0.3, fby=0.0, fbfree=1.0),
    "kneel": P(S, lean=0.32, crouch=0.42, head=-0.2, hfx=0.36, hfy=-0.36, hbx=0.12, hby=-0.3, ffx=0.36, fbx=-0.38),
    "charge_energy": P(S, lean=-0.06, crouch=0.32, head=0.16, hfx=0.34, hfy=-0.4, hbx=-0.30, hby=-0.42, ffx=0.42, fbx=-0.42),
    "victory": P(S, lean=-0.06, crouch=0.02, head=0.25, hfx=0.06, hfy=0.62, hbx=0.18, hby=-0.3, ffx=0.24, fbx=-0.24),
    "defeat": P(S, lean=0.62, crouch=0.46, head=-0.42, hfx=0.28, hfy=-0.62, hbx=0.12, hby=-0.64, ffx=0.36, fbx=-0.42),
    "taunt": P(S, lean=-0.04, crouch=0.08, head=0.1, hfx=0.5, hfy=0.12, hbx=0.0, hby=-0.32),
    "counter_stance": P(S, lean=-0.05, crouch=0.22, hfx=0.36, hfy=-0.04, hbx=0.24, hby=0.16, ffx=0.32, fbx=-0.34),
    "grabbed": P(S, lean=-0.3, crouch=0.0, head=0.3, hfx=0.3, hfy=0.2, hbx=0.25, hby=0.3, ffx=0.2, ffy=0.2, ffree=1.0, fbx=-0.1, fby=0.1, fbfree=1.0),
    "dizzy": P(S, lean=-0.15, crouch=0.18, head=0.35, hfx=0.1, hfy=-0.4, hbx=-0.05, hby=-0.42),
    "cast_hold": P(S, lean=0.0, crouch=0.2, hfx=0.4, hfy=0.32, hbx=0.36, hby=0.28),
    "teleport": P(S, lean=0.4, crouch=0.32, hfx=0.1, hfy=-0.1, hbx=0.0, hby=-0.15),
}


def template(delivery, variant):
    vs = TEMPLATES[delivery]
    return vs[variant % len(vs)]


def stance_pose(fighter):
    return STANCES.get(fighter.stance, S)


def idle_pose(fighter, t):
    st = stance_pose(fighter)
    b = math.sin(t * 2 * math.pi * 0.9 + fighter.side * 1.3)
    return P(st, crouch=st["crouch"] + 0.018 * b + 0.02, hfy=st["hfy"] + 0.015 * b, hby=st["hby"] + 0.012 * b)


def walk_pose(fighter, t, direction):
    st = idle_pose(fighter, t)
    ph = fighter.anim.stride * 2 * math.pi
    sw = 0.08 * math.sin(ph)
    lean = st["lean"] + (0.12 if direction > 0 else -0.06)
    return P(st, lean=lean, hfx=st["hfx"] + sw * 0.5, hbx=st["hbx"] - sw * 0.5, crouch=st["crouch"] + 0.02 * abs(math.cos(ph)))


def run_pose(fighter, t):
    ph = fighter.anim.stride * 2 * math.pi
    sw = math.sin(ph)
    return P(POSES["dash"], hfx=0.02 + 0.22 * sw, hbx=-0.3 - 0.18 * sw, crouch=0.2 + 0.04 * abs(math.cos(ph)))


def technique_pose(fighter, action, t):
    """Anticipation / action / impact / recovery for one technique stage."""
    tech = action.tech
    tpl = template(tech["delivery"], action.data.get("variant", tech["variant"]))
    keys = tpl["keys"]
    base = idle_pose(fighter, t)
    antic, strike = keys[0], keys[1]
    ph, p = action.phase, action.phase_p
    if ph == "move":
        mv = tech["movement"]
        if mv in ("dash", "step", "slide"):
            if mv == "slide":
                return P(POSES["tuck"], rot=-0.2, crouch=0.5, ffree=1.0, fbfree=1.0, ffx=0.55, ffy=0.05, fbx=0.1, fby=0.05, lean=-0.35, head=0.2)
            return run_pose(fighter, t) if mv == "dash" else walk_pose(fighter, t, 1)
        if mv in ("leap", "aerial_dash", "wall_jump"):
            if mv == "wall_jump" and action.data.get("rebounded"):
                return P(POSES["tuck"], rot=-2 * math.pi * clamp(action.data.get("flip", 0.0), 0, 1))
            return POSES["jump_up"] if fighter.vy > 0 else POSES["fall"]
        if mv == "backstep":
            return POSES["backstep"]
        if mv == "teleport":
            return POSES["teleport"]
        return base
    if ph == "antic":
        e = smoothstep(p)
        pose = blend_pose_safe(base, antic, e)
        if tech["timing"] in ("charged", "finisher"):
            tremble = 0.012 * math.sin(t * 90)
            pose["crouch"] += 0.04 * e + tremble
        if action.data.get("feint") and p > 0.7:
            pose = blend_pose_safe(pose, base, (p - 0.7) / 0.3)
        return pose
    if ph == "active":
        if tech["delivery"] == "barrage":
            hits = max(4, tech["params"]["hits"])
            k = p * hits
            i = int(k)
            f = k - i
            side = i % 2
            punch = template("punch", side)
            ext = math.sin(math.pi * f)
            return blend_pose_safe(punch["keys"][0], punch["keys"][1], ext)
        if tech["delivery"] == "grapple" and len(keys) > 2 and action.data.get("grabbed"):
            return blend_pose_safe(strike, keys[2], ease_in_out(action.data.get("throw_p", 0.0)))
        if tech["delivery"] in ("beam", "counter") or tech["delivery"] == "charge":
            e = ease_out(min(1.0, p * 4))
            pose = blend_pose_safe(antic, strike, e)
            if tech["delivery"] == "beam":
                pose["lean"] += 0.02 * math.sin(t * 70)
            if tech["delivery"] == "counter" and not action.data.get("triggered"):
                return POSES["counter_stance"]
            if tech["delivery"] == "charge":
                ph2 = fighter.anim.stride * 2 * math.pi
                pose["ffx"] = 0.3 + 0.3 * math.sin(ph2)
                pose["fbx"] = -0.3 - 0.3 * math.sin(ph2)
            return pose
        e = ease_out_back(min(1.0, p * 2.4), 1.2)
        return blend_pose_safe(antic, strike, e)
    if ph == "hold":
        return dict(strike)
    if ph == "recovery":
        last = keys[2] if (tech["delivery"] == "grapple" and len(keys) > 2 and action.data.get("grabbed")) else strike
        return blend_pose_safe(last, base, smoothstep(p))
    return base


def ease_in_out(p):
    return smoothstep(p)


def blend_pose_safe(a, b, t):
    t = clamp(t, -0.2, 1.2)
    return {k: lerp(a[k], b[k], t) for k in POSE_KEYS}


def action_pose(fighter, t):
    a = fighter.action
    k = a.kind
    if k == "technique":
        return technique_pose(fighter, a, t)
    if k == "idle":
        if not fighter.grounded:
            return POSES["jump_up"] if fighter.vy > 0 else POSES["fall"]
        return idle_pose(fighter, t)
    if k in ("move", "reset"):
        d = a.data.get("dir", 1)
        if abs(fighter.vx) > 4.5:
            return run_pose(fighter, t)
        return walk_pose(fighter, t, d * fighter.facing)
    if k == "dash":
        return run_pose(fighter, t) if fighter.grounded else P(POSES["dash"], ffree=1.0, fbfree=1.0, ffx=0.3, ffy=0.3, fbx=-0.4, fby=0.25)
    if k == "jump":
        if a.data.get("flip"):
            return P(POSES["tuck"], rot=-a.data["flip_dir"] * 2 * math.pi * smoothstep(clamp(a.t / 0.5, 0, 1)))
        return POSES["jump_up"] if fighter.vy > 0 else POSES["fall"]
    if k == "block":
        return POSES["block"]
    if k == "dodge":
        if a.data.get("roll"):
            return P(POSES["tuck"], rot=-2 * math.pi * smoothstep(a.phase_p))
        return blend_pose_safe(POSES["backstep"], idle_pose(fighter, t), smoothstep(max(0.0, a.phase_p - 0.6) / 0.4))
    if k == "hitstun":
        pz = POSES["hit_low"] if a.data.get("low") else POSES["hit_high"]
        if not fighter.grounded:
            pz = POSES["launched"]
            pz = P(pz, rot=a.data.get("spin", 0.0) * a.t)
        return blend_pose_safe(pz, idle_pose(fighter, t), smoothstep(max(0.0, a.phase_p - 0.65) / 0.35))
    if k == "knockdown":
        if a.phase == "fall":
            return P(POSES["launched"], rot=lerp(0.0, 1.3, smoothstep(a.phase_p)))
        if a.phase == "lie":
            return POSES["lying"]
        if a.phase == "getup":
            return blend_pose_safe(POSES["lying"], POSES["kneel"] if a.phase_p < 0.5 else idle_pose(fighter, t),
                                   smoothstep(a.phase_p * 2) if a.phase_p < 0.5 else 1.0) if a.phase_p < 0.5 else \
                blend_pose_safe(POSES["kneel"], idle_pose(fighter, t), smoothstep((a.phase_p - 0.5) * 2))
    if k == "broken":
        sw = math.sin(t * 6)
        return P(POSES["dizzy"], lean=-0.15 + 0.1 * sw, head=0.35 + 0.15 * sw)
    if k == "grabbed":
        return POSES["grabbed"]
    if k == "charge":
        return POSES["charge_energy"]
    if k == "teleport":
        return POSES["teleport"]
    if k == "victory":
        return blend_pose_safe(idle_pose(fighter, t), POSES["victory"], smoothstep(a.t / 0.5))
    if k == "defeat":
        return POSES["lying"] if a.data.get("down", True) else POSES["defeat"]
    if k == "taunt":
        pz = dict(POSES["taunt"])
        pz["hfy"] += 0.08 * math.sin(t * 9)
        return pz
    if k == "intro":
        style = a.data.get("style", 0)
        if a.phase == "air":
            return POSES["fall"]
        if a.phase == "land":
            return blend_pose_safe(POSES["kneel"], idle_pose(fighter, t), smoothstep(a.phase_p))
        if a.phase == "pose":
            if style == 0:
                return POSES["charge_energy"] if a.phase_p < 0.6 else idle_pose(fighter, t)
            return POSES["taunt"] if a.phase_p < 0.6 else idle_pose(fighter, t)
        return idle_pose(fighter, t)
    return idle_pose(fighter, t)


def export_templates():
    """Animation templates as persistent data (library/animations.json)."""
    out = {}
    for d, variants in TEMPLATES.items():
        for i, v in enumerate(variants):
            out[f"anim_{d}_{i}"] = {"delivery": d, "variant": i, "limb": v["limb"], "lunge": v["lunge"], "keys": v["keys"]}
    for k, v in POSES.items():
        out[f"pose_{k}"] = {"delivery": None, "keys": [v]}
    return out
