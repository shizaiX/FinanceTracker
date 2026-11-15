"""Simulation state containers (fighters, actions, entities)."""
from __future__ import annotations

from collections import deque

from ..animation.poses import idle_pose
from ..animation.rig import FootController

_uid = [0]


def next_uid():
    _uid[0] += 1
    return _uid[0]


class Action:
    __slots__ = ("kind", "t", "dur", "phase", "phase_t", "phase_dur", "phase_p", "tech", "data", "stage",
                 "uid", "phases", "pi")

    def __init__(self, kind, dur=0.0, tech=None, data=None, phases=None):
        self.kind = kind
        self.t = 0.0
        self.dur = dur
        self.tech = tech
        self.data = data or {}
        self.stage = 0
        self.uid = next_uid()
        self.phases = phases or [(kind, dur)]
        self.pi = 0
        self.phase = self.phases[0][0]
        self.phase_dur = self.phases[0][1]
        self.phase_t = 0.0
        self.phase_p = 0.0

    def advance(self, dt):
        """Advance time; returns True when the whole action finished."""
        self.t += dt
        self.phase_t += dt
        self.phase_p = min(1.0, self.phase_t / self.phase_dur) if self.phase_dur > 0 else 1.0
        if self.phase_dur > 0 and self.phase_t >= self.phase_dur:
            return self.next_phase()
        return False

    def next_phase(self):
        self.pi += 1
        if self.pi >= len(self.phases):
            return True
        self.phase, self.phase_dur = self.phases[self.pi]
        self.phase_t = 0.0
        self.phase_p = 0.0
        return False

    def jump_to(self, name):
        for i, (n, d) in enumerate(self.phases):
            if n == name and i >= self.pi:
                self.pi = i
                self.phase, self.phase_dur = n, d
                self.phase_t = 0.0
                self.phase_p = 0.0
                return


class AnimState:
    def __init__(self, fighter):
        self.local = idle_pose(fighter, 0.0)
        self.blend_from = dict(self.local)
        self.blend_t = 1.0
        self.blend_dur = 0.1
        self.feet = FootController(fighter.x, fighter.facing)
        self.stride = 0.0
        self.joints = None
        self.prev_joints = None
        self.effector_prev = {}


class FighterState:
    FREE_KINDS = ("idle", "move", "block", "charge")

    def __init__(self, spec, side, abilities, techs, x):
        self.spec = spec
        self.name = spec["name"]
        self.side = side
        self.abilities = abilities
        self.ability_ids = [a["id"] for a in abilities]
        self.techs = list(techs)
        self.traits = spec["traits"]
        self.stance = spec.get("stance", "orthodox")
        self.build = spec.get("build", 1.0)
        self.x = x
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 1 if side == 0 else -1
        self.grounded = True
        self.action = Action("idle", 0.0)
        self.poise = 100.0
        self.energy = 60.0
        self.focus = 0.0
        self.score = 0
        self.invuln = 0.0
        self.hidden = False
        self.shield_t = 0.0
        self.slow_t = 0.0
        self.hitflash = 0.0
        self.no_regen = 0.0
        self.cooldowns = {}
        self.combo_taken = 0
        self.last_hit_t = -10.0
        self.think_cd = 0.3
        self.handled = set()
        self.threat_seen = {}
        self.recent = deque(maxlen=8)
        self.opp_history = deque(maxlen=10)
        self.memory = {"blocked": 0, "dodged": 0, "landed": 0, "countered": 0, "opp_blocks": 0, "opp_dodges": 0,
                       "opp_ranged": 0, "opp_melee": 0}
        self.discont = False
        self.aura = 0.0
        self.weapon = next((a.get("weapon") for a in abilities if a.get("weapon")), None)
        self.stats = {"hits": 0, "minor": 0, "combo": 0, "significant": 0, "blocked": 0, "dodges": 0,
                      "techniques": 0, "fusions": 0, "ultimates": 0, "counters": 0, "discoveries": 0,
                      "guard_breaks": 0, "projectiles": 0, "points": 0}
        self.anim = AnimState(self)

    @property
    def free(self):
        return self.action.kind in self.FREE_KINDS

    def set_action(self, action, blend=0.08):
        self.action = action
        a = self.anim
        a.blend_from = dict(a.local)
        a.blend_t = 0.0
        a.blend_dur = blend


class Projectile:
    __slots__ = ("id", "owner", "tech", "x", "y", "vx", "vy", "r", "ttl", "abilities", "style", "homing",
                 "pierce", "detonate", "split_t", "alive", "hits", "age", "trail")

    def __init__(self, owner, tech, x, y, vx, vy, r, abilities, style):
        self.id = next_uid()
        self.owner, self.tech = owner, tech
        self.x, self.y, self.vx, self.vy, self.r = x, y, vx, vy, r
        self.ttl = 2.2
        self.abilities = abilities
        self.style = style
        p = tech["params"]
        self.homing = p.get("homing", 0.0)
        self.pierce = p.get("pierce", False)
        self.detonate = p.get("detonate", 0.0)
        self.split_t = 0.28 if p.get("count", 1) > 1 else -1
        self.alive = True
        self.hits = 1
        self.age = 0.0


class Beam:
    __slots__ = ("id", "owner", "tech", "x0", "y0", "x1", "y1", "width", "ttl", "tick", "abilities", "style", "hits_done", "angle")

    def __init__(self, owner, tech, abilities, style):
        self.id = next_uid()
        self.owner, self.tech = owner, tech
        self.x0 = self.y0 = self.x1 = self.y1 = 0.0
        self.width = tech["params"].get("width", 0.3)
        self.ttl = tech["params"]["active"]
        self.tick = 0.0
        self.abilities = abilities
        self.style = style
        self.hits_done = 0
        self.angle = 0.0


class EnvStrike:
    __slots__ = ("id", "owner", "tech", "x", "t", "delay", "state", "height", "radius", "abilities", "form", "hit_done")

    def __init__(self, owner, tech, x, abilities, form):
        self.id = next_uid()
        self.owner, self.tech, self.x = owner, tech, x
        self.t = 0.0
        self.delay = tech["params"].get("delay", 0.4)
        self.state = "warn"
        self.height = 0.0
        self.radius = tech["params"].get("radius", 0.8)
        self.abilities = abilities
        self.form = form
        self.hit_done = False


class Blast:
    __slots__ = ("id", "owner", "tech", "x", "y", "r", "delay", "abilities", "done", "extra")

    def __init__(self, owner, tech, x, y, r, delay, abilities, extra=None):
        self.id = next_uid()
        self.owner, self.tech, self.x, self.y, self.r, self.delay = owner, tech, x, y, r, delay
        self.abilities = abilities
        self.done = False
        self.extra = extra or {}


class Zone:
    __slots__ = ("id", "x0", "x1", "kind", "ttl", "owner", "abilities", "max_ttl")

    def __init__(self, x0, x1, kind, ttl, owner, abilities):
        self.id = next_uid()
        self.x0, self.x1, self.kind, self.ttl, self.owner, self.abilities = x0, x1, kind, ttl, owner, abilities
        self.max_ttl = ttl
