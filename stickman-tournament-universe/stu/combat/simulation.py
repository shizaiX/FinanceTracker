"""Deterministic 1v1 match simulation (fixed 120 Hz timestep).

Produces a complete *timeline*: per-tick fighter skeletons, entities, HUD data
and timestamped events. Rendering and audio only read the timeline, so they can
never influence the outcome. Same seed + config => identical timeline.
"""
from __future__ import annotations

import hashlib
import math

from ..animation.poses import action_pose, template
from ..animation.rig import J, solve_local, to_world
from ..core.mathutil import clamp, seg_seg_dist, smoothstep
from . import ai
from .techniques import validate
from .director import Director
from ..themes.packs import WEAPONS, weapon_class
from .state import Action, Beam, Blast, EnvStrike, FighterState, Projectile, Zone

SIM_HZ = 120
DT = 1.0 / SIM_HZ
GRAVITY = -24.0
HALF = 7.2
START_X = 2.3

ADVANTAGE = {("fluid", "heat"), ("heat", "cold"), ("heat", "organic"), ("electric", "fluid"), ("solid", "electric"),
             ("cold", "fluid"), ("organic", "ground"), ("radiant", "void"), ("void", "radiant"), ("sharp", "organic"),
             ("force", "gas"), ("gas", "ground"), ("wave", "crystal"), ("mass", "fast"), ("conductive", "electric")}

FLAG_BLOCK, FLAG_INVULN, FLAG_SHIELD, FLAG_FLASH, FLAG_CHARGE, FLAG_BROKEN, FLAG_HIDDEN, FLAG_DISCONT, FLAG_ULT, FLAG_WEAPON = (
    1, 2, 4, 8, 16, 32, 64, 128, 256, 512)


class MatchResult:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Match:
    def __init__(self, cfg, fa, fb, theme, universe, rng, techs_by_id, archetype, arena, meta=None):
        self.cfg = cfg
        self.theme = theme
        self.universe = universe
        self.rng = rng
        self.meta = meta or {}
        self.half = HALF
        self.arena = arena
        self.ab = {a["id"]: a for a in theme["abilities"]}
        self.ptw = cfg["tournament"]["points_to_win"]
        self.director = Director(cfg, archetype, rng.stream("director"))
        self.rng_ai = [rng.stream("ai", 0), rng.stream("ai", 1)]
        self.rng_discover = [rng.stream("discover", 0), rng.stream("discover", 1)]
        self.rng_misc = rng.stream("misc")
        specs = [fa, fb]
        self.fighters = []
        for side, spec in enumerate(specs):
            abilities = [self.ab[i] for i in spec["abilities"] if i in self.ab]
            techs = [techs_by_id[t] for t in spec["repertoire"] if t in techs_by_id]
            # Re-validate saved repertoires against the current rules (older libraries may hold now-invalid moves).
            techs = [t for t in techs if validate(dict(t["signature"]), [self.ab[i] for i in t["abilities"] if i in self.ab])[0]]
            f = FighterState(spec, side, abilities, techs, -START_X if side == 0 else START_X)
            f.physical_weight = theme.get("physical_weight", 0.2)
            self.fighters.append(f)
        self.t = 0.0
        self.tick = 0
        self.fight_start = 3.6
        self.fight_t = 0.0
        self.state = "intro"
        self.state_t = 0.0
        self.projectiles, self.beams, self.envs, self.blasts, self.zones = [], [], [], [], []
        self.events = []
        self.frames = []
        self.points = []
        self.discoveries = []
        self.winner = None
        self.final_point_t = None
        self.round = 1
        self.max_total = cfg["tournament"]["maximum_fight_duration_seconds"] + 40

    # ------------------------------------------------------------------ utils
    def event(self, _etype, **kw):
        kw["t"] = round(self.t, 5)
        kw["type"] = _etype
        self.events.append(kw)

    def opp(self, f):
        return self.fighters[1 - f.side]

    def colors_of(self, ab_ids):
        return [self.ab[i]["colors"] for i in ab_ids if i in self.ab]

    # ------------------------------------------------------------ main loop
    def run(self):
        for f in self.fighters:
            self._setup_intro(f)
        while self.state != "done":
            self.step()
            if self.t > self.fight_start + self.max_total:
                self._force_finish()
        return self._result()

    def _setup_intro(self, f):
        drop = 0.35 if f.side == 0 else 1.55
        f.y = 6.5
        f.grounded = False
        f.hidden = True
        f.set_action(Action("intro", data={"style": f.side}, phases=[("wait", drop), ("air", 10.0), ("land", 0.45), ("pose", 1.1), ("hold", 10.0)]))

    def step(self):
        dt = DT
        self.t += dt
        self.state_t += dt
        fs = self.fighters
        if self.state == "intro" and self.t >= self.fight_start:
            self.state = "fight"
            self.state_t = 0.0
            for f in fs:
                f.set_action(Action("idle"))
            self.event("fight", round=self.round)
        if self.state in ("fight",):
            self.fight_t = self.t - self.fight_start
        elif self.state in ("point_pause", "reset", "ready"):
            self.fight_t = self.t - self.fight_start
        self._match_flow()
        # AI
        if self.state == "fight":
            for f in fs:
                o = self.opp(f)
                ai.react(f, o, self)
                f.think_cd -= dt
                can_cancel = (f.action.kind == "technique" and f.action.phase == "recovery" and f.action.data.get("hit")
                              and o.action.kind in ("hitstun", "broken") and f.action.phase_p > 0.25)
                if (f.free or can_cancel) and f.think_cd <= 0:
                    ai.think(f, o, self)
        for f in fs:
            f.discont = False
            self._update_action(f, self.opp(f), dt)
        for f in fs:
            self._physics(f, dt)
        self._separate()
        self._update_entities(dt)
        for f in fs:
            self._animate(f, dt)
        if self.state == "fight":
            for f in fs:
                self._melee_check(f, self.opp(f))
        self._meters(dt)
        self._record()
        self.tick += 1

    def _match_flow(self):
        fs = self.fighters
        if self.state == "point_pause" and self.state_t > 1.8:
            if self.winner is not None:
                return
            self.state = "reset"
            self.state_t = 0.0
            self.projectiles.clear(); self.beams.clear(); self.envs.clear(); self.blasts.clear(); self.zones.clear()
        if self.state == "reset":
            done = True
            for f in fs:
                home = -START_X if f.side == 0 else START_X
                if f.action.kind in ("knockdown", "hitstun", "technique", "dodge", "jump", "broken", "grabbed") and self.state_t < 3.0:
                    done = False
                    continue
                if f.action.kind != "reset" and abs(f.x - home) > 0.12:
                    f.set_action(Action("reset", data={"home": home, "dir": 1}), blend=0.12)
                if f.action.kind == "reset" or abs(f.x - home) > 0.12:
                    done = False
            if done or self.state_t > 4.0:
                self.state = "ready"
                self.state_t = 0.0
                self.round += 1
                for f in fs:
                    f.set_action(Action("idle"), blend=0.15)
                    f.poise = 100.0
                    f.energy = min(100.0, f.energy + 25)
                    f.facing = 1 if f.side == 0 else -1
                    f.handled.clear()
                    f.threat_seen.clear()
                    f.combo_taken = 0
                    f.think_cd = self.rng_misc.uniform(0.05, 0.4)
                self.event("round_start", round=self.round, score=[fs[0].score, fs[1].score])
        if self.state == "ready" and self.state_t > 1.25:
            self.state = "fight"
            self.state_t = 0.0
            self.event("fight", round=self.round)
        if self.state == "outro":
            w = fs[self.winner]
            if self.state_t > 1.7 and w.action.kind not in ("victory",) and w.grounded and w.action.kind in ("idle", "move", "block", "charge", "reset"):
                w.set_action(Action("victory"), blend=0.2)
                self.event("victory", fighter=self.winner)
            if self.state_t > 1.7 and w.action.kind == "technique" and w.action.phase == "recovery":
                pass
            if self.state_t > 5.0:
                self.state = "done"

    def _force_finish(self):
        # Safety net only (validator flags it): award the remaining point to the fighter with more poise.
        fs = self.fighters
        lead = 0 if (fs[0].score, fs[0].poise) >= (fs[1].score, fs[1].poise) else 1
        while fs[lead].score < self.ptw:
            fs[lead].score += 1
        self.winner = lead
        self.final_point_t = self.fight_t
        self.event("ko", attacker=lead, defender=1 - lead, forced=True, x=fs[1 - lead].x, y=1.0, abilities=[])
        self.state = "done"

    # -------------------------------------------------------------- actions
    def start_technique(self, f, o, tech):
        p = tech["params"]
        f.energy -= p["cost"]
        f.focus = max(0.0, f.focus - p.get("focus_cost", 0))
        f.cooldowns[tech["id"]] = self.t + p["cooldown"]
        f.recent.append(tech["id"])
        o.opp_history.append(tech["delivery"])
        if tech["kind"] in ("projectile", "beam", "env"):
            o.memory["opp_ranged"] += 1
        else:
            o.memory["opp_melee"] += 1
        su = p["startup"]
        phases = []
        if tech["movement"] != "none":
            phases.append(("move", 1.2))
        feint = tech["timing"] == "feint" and self.rng_ai[f.side].chance(0.7)
        if feint:
            phases += [("antic", su * 1.15), ("recovery", 0.14)]
        else:
            stages = p.get("stages", 1)
            for s in range(stages):
                last = s == stages - 1
                phases += [("antic", su if s == 0 else su * 0.5), ("active", p["active"]), ("recovery", p["recovery"] if last else 0.05)]
        data = {"variant": tech["variant"], "feint": feint, "entered": -1, "stage": -1, "hit": False}
        f.set_action(Action("technique", tech=tech, phases=phases, data=data), blend=0.06)
        f.stats["techniques"] += 1
        if tech["tier"] == "fusion":
            f.stats["fusions"] += 1
        if tech["tier"] == "ultimate":
            f.stats["ultimates"] += 1
        if tech["tier"] in ("fusion", "ultimate") and not feint:
            self.event("callout", fighter=f.side, name=tech["name"], tier=tech["tier"], abilities=tech["abilities"], tech=tech["id"])
        self.event("technique", fighter=f.side, tech=tech["id"], delivery=tech["delivery"], tier=tech["tier"], feint=feint,
                   name=tech["name"], abilities=tech["abilities"])

    def start_move(self, f, toward, dur, speed, then_back=False):
        d = 1 if (self.opp(f).x > f.x) == toward else -1
        f.set_action(Action("move", dur, data={"dir": d, "speed": speed, "back": then_back}), blend=0.12)
        f.think_cd = 0.0

    def start_block(self, f, dur):
        f.set_action(Action("block", dur), blend=0.05)
        f.think_cd = 0.0

    def start_jump(self, f, forward=True, flip=False, evade=False):
        if not f.grounded:
            return
        o = self.opp(f)
        d = 1 if o.x > f.x else -1
        f.vy = 8.6 if not evade else 9.2
        f.vx = (3.6 if forward else -2.4) * d
        if evade and forward:
            f.vx = 5.5 * d  # jump over
        f.grounded = False
        f.set_action(Action("jump", 3.0, data={"flip": flip, "flip_dir": 1 if f.vx * f.facing >= 0 else -1}), blend=0.06)
        self.event("jump", fighter=f.side, x=f.x)

    def start_dodge(self, f, roll=False):
        o = self.opp(f)
        d = 1 if o.x > f.x else -1
        if roll:
            f.vx = 7.5 * d
            f.set_action(Action("dodge", 0.42, data={"roll": True}), blend=0.05)
            f.invuln = 0.3
        else:
            f.vx = -7.2 * d
            f.set_action(Action("dodge", 0.3, data={"roll": False}), blend=0.04)
            f.invuln = 0.16
        self.event("dash", fighter=f.side, x=f.x, dodge=True)

    def start_charge(self, f, dur):
        f.set_action(Action("charge", dur), blend=0.15)
        self.event("charge_start", fighter=f.side, abilities=f.ability_ids)

    def start_teleport_evade(self, f, o):
        f.energy -= 15
        f.set_action(Action("teleport", 0.3, data={"evade": True}), blend=0.04)
        self.event("teleport_out", fighter=f.side, x=f.x, y=f.y + 1.0, abilities=f.ability_ids)
        f.hidden = True
        f.invuln = 0.35

    # ------------------------------------------------------------ update
    def _update_action(self, f, o, dt):
        a = f.action
        k = a.kind
        if k == "intro":
            self._update_intro(f, a, dt)
            return
        if k == "technique":
            self._update_technique(f, o, a, dt)
            return
        if k in ("idle", "block", "charge") and self.state in ("fight", "ready", "reset", "point_pause", "outro"):
            self._face(f, o)
        if k == "move":
            spd = a.data["speed"] * (0.6 if f.slow_t > 0 else 1.0)
            target = a.data["dir"] * spd
            f.vx += clamp(target - f.vx, -40 * dt, 40 * dt)
            self._face(f, o)
            if a.advance(dt):
                if a.data.get("back"):
                    a2 = Action("move", 0.22, data={"dir": -a.data["dir"], "speed": 3.0, "back": False})
                    f.set_action(a2, blend=0.1)
                else:
                    f.set_action(Action("idle"), blend=0.12)
            return
        if k == "reset":
            home = a.data["home"]
            d = 1 if home > f.x else -1
            a.data["dir"] = d
            dist = abs(home - f.x)
            spd = 3.2 if dist < 2.5 else 6.0
            target = d * min(spd, dist * 6)
            f.vx += clamp(target - f.vx, -40 * dt, 40 * dt)
            self._face(f, o)
            a.advance(dt)
            if dist < 0.1:
                f.vx = 0.0
                f.set_action(Action("idle"), blend=0.15)
            return
        if k == "jump":
            a.advance(dt)
            if f.grounded and a.t > 0.05:
                f.set_action(Action("idle"), blend=0.1)
            return
        if k == "teleport":
            if a.advance(dt):
                f.set_action(Action("idle"), blend=0.05)
            elif f.hidden and a.t >= 0.16:
                side = 1 if self.rng_misc.chance(0.5) else -1
                nx = clamp(o.x + side * 2.6, -HALF + 0.5, HALF - 0.5)
                if abs(nx - o.x) < 1.5:
                    nx = clamp(o.x - side * 2.6, -HALF + 0.5, HALF - 0.5)
                f.x, f.y, f.vx, f.vy = nx, 0.0, 0.0, 0.0
                f.grounded = True
                f.hidden = False
                f.discont = True
                self._face(f, o)
                self.event("teleport_in", fighter=f.side, x=f.x, y=1.0, abilities=f.ability_ids)
            return
        if k in ("dodge",):
            if a.advance(dt):
                f.set_action(Action("idle"), blend=0.1)
            return
        if k == "hitstun":
            if a.advance(dt):
                if not f.grounded and a.t < 3.0:
                    a.dur += 0.1
                    a.phase_dur += 0.1
                    a.pi = 0
                    return
                f.set_action(Action("idle") if f.grounded else Action("jump", 3.0, data={"flip": False, "flip_dir": 1}), blend=0.12)
                f.combo_taken = 0
            return
        if k == "knockdown":
            if a.phase == "fall":
                a.phase_t += dt
                a.t += dt
                a.phase_p = min(1.0, a.phase_t / 0.6)
                if f.grounded and a.phase_t > 0.08:
                    self.event("land", fighter=f.side, x=f.x, heavy=True)
                    a.next_phase()
                return
            if a.advance(dt):
                f.set_action(Action("idle"), blend=0.1)
                f.invuln = 0.35
                f.combo_taken = 0
            elif a.phase == "getup" and a.phase_t < dt * 1.5:
                f.invuln = 0.6
            return
        if k == "broken":
            if a.advance(dt):
                f.poise = max(f.poise, 28.0)
                f.set_action(Action("idle"), blend=0.15)
            return
        if k == "grabbed":
            a.advance(dt)
            oa = o.action
            held = oa.kind == "technique" and oa.tech["delivery"] == "grapple" and oa.data.get("grabbed") and not oa.data.get("thrown")
            if not held:
                f.set_action(Action("hitstun", 0.3, data={"low": False, "knockdown": f.y > 0.3}), blend=0.06)
                f.grounded = f.y <= 0.0
            return
        if k in ("victory", "defeat"):
            a.advance(dt)
            return
        if k == "burst":
            if a.advance(dt):
                f.set_action(Action("idle"), blend=0.1)
            return
        if a.dur > 0 and a.advance(dt):
            f.set_action(Action("idle"), blend=0.12)
        elif a.dur <= 0:
            a.advance(dt)

    def _update_intro(self, f, a, dt):
        if a.phase == "wait":
            a.advance(dt)
            if a.phase != "wait":
                f.hidden = False
                f.vy = -3.0
                self.event("intro_drop", fighter=f.side, x=f.x)
            return
        if a.phase == "air":
            a.t += dt
            if f.grounded:
                self.event("intro_land", fighter=f.side, x=f.x, abilities=f.ability_ids)
                a.next_phase()
            return
        a.advance(dt)

    def _face(self, f, o):
        if f.hidden or o.hidden:
            return
        dx = o.x - f.x
        nf = 1 if dx > 0.05 else -1 if dx < -0.05 else f.facing
        if nf != f.facing:
            f.facing = nf
            f.anim.feet.swap()
            f.anim.blend_from = dict(f.anim.local)
            f.anim.blend_t = 0.0
            f.anim.blend_dur = 0.08

    def _update_technique(self, f, o, a, dt):
        tech = a.tech
        p = tech["params"]
        d = tech["delivery"]
        dist = abs(o.x - f.x)
        if a.data["entered"] != a.pi:
            a.data["entered"] = a.pi
            self._enter_phase(f, o, a)
        ph = a.phase
        if ph == "move":
            mv = tech["movement"]
            done = False
            reach = p["reach"]
            target_d = reach * 0.8 if tech["kind"] in ("melee", "grab", "area") else 2.6
            if mv in ("dash", "step", "slide"):
                if mv == "slide":
                    f.vx *= math.exp(-2.5 * dt)
                done = dist <= target_d or a.phase_t > (0.3 if mv == "step" else 0.65) or abs(f.x) > HALF - 0.35
                if (o.x - f.x) * f.vx < 0:
                    done = True
            elif mv == "leap":
                done = (f.vy < 1.2 and a.phase_t > 0.15) or (dist <= reach and a.phase_t > 0.1)
            elif mv == "aerial_dash":
                if a.phase_t > 0.2 and not a.data.get("dashing"):
                    a.data["dashing"] = True
                    self._face(f, o)
                    f.vx = 11.0 * f.facing
                    f.vy = 0.5
                    self.event("dash", fighter=f.side, x=f.x, air=True, abilities=f.ability_ids)
                done = a.data.get("dashing") and (dist <= reach * 0.9 or a.phase_t > 0.7)
            elif mv == "teleport":
                if f.hidden and a.phase_t >= 0.16:
                    behind = self.rng_misc.chance(0.5)
                    off = reach * 0.75 if tech["kind"] in ("melee", "grab", "area") else 3.0
                    side = (-1 if o.facing > 0 else 1) if behind else (1 if f.x > o.x else -1)
                    nx = o.x + side * off
                    if abs(nx) > HALF - 0.4:
                        nx = o.x - side * off
                    f.x = clamp(nx, -HALF + 0.4, HALF - 0.4)
                    f.y = 0.0 if o.grounded or tech["kind"] not in ("melee",) else max(0.0, o.y)
                    if tech["delivery"] == "aerial_strike":
                        f.y = 1.7
                    f.grounded = f.y <= 0.0
                    f.vx = f.vy = 0.0
                    f.hidden = False
                    f.discont = True
                    self._face(f, o)
                    self.event("teleport_in", fighter=f.side, x=f.x, y=f.y + 1.0, abilities=f.ability_ids)
                done = (not f.hidden) and a.phase_t >= 0.2
            elif mv == "backstep":
                done = a.phase_t >= 0.2
            elif mv == "wall_jump":
                if not a.data.get("rebounded") and not f.grounded and abs(f.x) >= HALF - 0.36:
                    wd = 1 if f.x > 0 else -1
                    f.vx = -wd * 8.0
                    f.vy = 7.8
                    a.data["rebounded"] = True
                    a.data["rb_t"] = a.phase_t
                    self.event("wall_jump", fighter=f.side, x=f.x, y=f.y)
                if a.data.get("rebounded"):
                    a.data["flip"] = (a.phase_t - a.data["rb_t"]) / 0.45
                    done = (a.phase_t - a.data["rb_t"] > 0.2) and (dist <= reach + 0.4 or f.vy < 0)
                    if done:
                        self._face(f, o)
                done = done or (f.grounded and a.phase_t > 0.1)
            if a.phase_t > 1.1:
                done = True
            a.t += dt
            a.phase_t += dt
            if done:
                if tech["kind"] in ("melee", "grab") and dist > reach + 0.6 and tech["movement"] not in ("leap", "aerial_dash", "wall_jump"):
                    # Approach failed: abort gracefully instead of punching air across the arena.
                    a.jump_to("recovery")
                    a.data["aborted"] = True
                else:
                    a.next_phase()
            return
        if ph == "antic":
            if a.phase_t < dt * 1.5 and not f.hidden:
                self._face(f, o)
        if ph == "active":
            self._technique_active(f, o, a, dt)
        if a.phase == "active" and a.data.get("plunge") and not f.grounded:
            a.t += dt
            a.phase_t = min(a.phase_t + dt, a.phase_dur * 0.9)
            a.phase_p = a.phase_t / a.phase_dur
            return
        if a.advance(dt):
            f.set_action(Action("idle"), blend=0.1)
            if tech["delivery"] == "counter":
                pass

    def _enter_phase(self, f, o, a):
        tech = a.tech
        p = tech["params"]
        ph = a.phase
        d = tech["delivery"]
        if ph == "move":
            mv = tech["movement"]
            dist = abs(o.x - f.x)
            self._face(f, o)
            if mv == "dash":
                f.vx = 9.5 * f.facing
                self.event("dash", fighter=f.side, x=f.x, abilities=f.ability_ids)
            elif mv == "step":
                f.vx = 3.4 * f.facing
            elif mv == "slide":
                f.vx = 8.5 * f.facing
                self.event("dash", fighter=f.side, x=f.x, slide=True)
            elif mv == "leap":
                f.vy = 7.6
                f.vx = clamp((dist - p["reach"] * 0.5) / 0.7, 1.5, 7.5) * f.facing
                f.grounded = False
                self.event("jump", fighter=f.side, x=f.x)
            elif mv == "aerial_dash":
                f.vy = 7.0
                f.vx = 1.5 * f.facing
                f.grounded = False
                self.event("jump", fighter=f.side, x=f.x)
            elif mv == "teleport":
                f.hidden = True
                self.event("teleport_out", fighter=f.side, x=f.x, y=f.y + 1.0, abilities=f.ability_ids)
            elif mv == "backstep":
                f.vx = -6.5 * f.facing
                self.event("dash", fighter=f.side, x=f.x, dodge=True)
            elif mv == "wall_jump":
                wd = 1 if f.x > 0 else -1
                f.vx = 7.5 * wd
                f.vy = 7.2
                f.grounded = False
                self.event("jump", fighter=f.side, x=f.x)
            return
        if ph == "antic":
            a.data["stage"] += 1
            a.data["hit_stage"] = False
            a.data["seg"] = -1
            if a.data["stage"] > 0:
                nvar = tech["variant"] + a.data["stage"]
                a.data["variant"] = nvar
                f.anim.blend_from = dict(f.anim.local)
                f.anim.blend_t = 0.0
                f.anim.blend_dur = 0.05
            if tech["abilities"]:
                self.event("cast", fighter=f.side, abilities=tech["abilities"], tech=tech["id"], tier=tech["tier"],
                           dur=p["startup"], delivery=d)
            if tech["tier"] == "ultimate":
                self.event("ultimate", fighter=f.side, name=tech["name"], abilities=tech["abilities"], dur=p["startup"])
            return
        if ph == "active":
            self._face(f, o) if d not in ("charge",) else None
            kind = tech["kind"]
            tpl = template(d, a.data.get("variant", tech["variant"]))
            if kind == "melee" or kind == "grab":
                self.event("whoosh", fighter=f.side, delivery=d, abilities=tech["abilities"], limb=tpl["limb"])
                a.data["lunge_v"] = tpl["lunge"] / max(0.05, p["active"] * 0.6)
            if d == "charge":
                f.vx = p.get("travel", 9.0) * f.facing
                self.event("dash", fighter=f.side, x=f.x, abilities=tech["abilities"], charge=True)
            elif d == "aerial_strike":
                if f.grounded:
                    f.y = max(f.y, 0.05)
                    f.grounded = False
                f.vx = 7.5 * f.facing
                f.vy = -8.5
            elif d == "slam":
                if not f.grounded:
                    a.data["plunge"] = True
                    f.vy = -15.0
                    f.vx *= 0.3
                else:
                    self._slam_impact(f, tech)
            elif d == "projectile":
                self._spawn_projectile(f, o, tech)
            elif d == "beam":
                b = Beam(f.side, tech, tech["abilities"], self._style(tech))
                self.beams.append(b)
                self.event("beam_start", fighter=f.side, abilities=tech["abilities"], tech=tech["id"], dur=p["active"])
            elif d == "explosion":
                delay = p.get("delay_blast", 0.0)
                if tech["movement"] == "none" or True:
                    self.blasts.append(Blast(f.side, tech, f.x, f.y + 0.9, p.get("radius", 1.6), delay, tech["abilities"],
                                             {"self": True, "trap": p.get("trap", False)}))
            elif d == "env_strike":
                tx = clamp(o.x + o.vx * 0.22, -HALF + 0.4, HALF - 0.4)
                form = self.ab[tech["abilities"][0]]["env_form"] if tech["abilities"] else "pillar"
                es = EnvStrike(f.side, tech, tx, tech["abilities"], form)
                self.envs.append(es)
                self.event("env_warn", fighter=f.side, x=tx, abilities=tech["abilities"], form=form, delay=es.delay)
            elif d == "counter":
                a.data["waiting"] = True
            if p.get("shield"):
                f.shield_t = p["shield"]
                self.event("shield", fighter=f.side, abilities=tech["abilities"], dur=p["shield"])
            return

    def _technique_active(self, f, o, a, dt):
        tech = a.tech
        p = tech["params"]
        d = tech["delivery"]
        if d in ("punch", "kick", "sweep", "uppercut", "summon_weapon", "grapple", "barrage", "counter") and f.grounded:
            if a.phase_p < 0.6 and not a.data.get("hit_stage"):
                f.vx = a.data.get("lunge_v", 0.0) * f.facing
            else:
                f.vx *= math.exp(-14 * dt)
        if d == "uppercut" and a.phase_p > 0.3 and f.grounded and not a.data.get("hopped"):
            a.data["hopped"] = True
            f.vy = 3.2
            f.grounded = False
        if d == "charge":
            if abs(o.x - f.x) < 0.25 or abs(f.x) > HALF - 0.4 or a.data.get("hit_stage"):
                f.vx *= math.exp(-12 * dt)
        if d == "aerial_strike" and f.grounded and a.phase_t > 0.02:
            self.event("land", fighter=f.side, x=f.x, heavy=False)
            a.jump_to("recovery")
        if d == "slam" and a.data.get("plunge") and f.grounded:
            a.data["plunge"] = False
            self._slam_impact(f, tech)
        if d == "barrage":
            seg = int(a.phase_p * p["hits"])
            if seg != a.data.get("seg"):
                a.data["seg"] = seg
                a.data["hit_stage"] = False
                if seg % 2 == 0:
                    self.event("whoosh", fighter=f.side, delivery="punch", abilities=tech["abilities"], limb="hand_f", quiet=True)
        if d == "grapple" and a.data.get("grabbed"):
            a.data["throw_p"] = min(1.0, a.data.get("throw_p", 0.0) + dt / 0.42)
            a.phase_t = min(a.phase_t, a.phase_dur * 0.5)
            hand = f.anim.joints[J["hand_f"]] if f.anim.joints else (f.x, 1.2)
            o.x += clamp((clamp(hand[0], -HALF + 0.3, HALF - 0.3) - o.x) * 0.25, -0.12, 0.12)
            o.y += clamp((max(0.0, hand[1] - 1.05) - o.y) * 0.25, -0.12, 0.12)
            o.vx = o.vy = 0.0
            o.grounded = o.y <= 0.0
            if a.data["throw_p"] >= 1.0 and not a.data.get("thrown"):
                a.data["thrown"] = True
                o.action = Action("idle")
                self.event("throw", fighter=f.side, x=o.x, y=o.y + 0.8)
                self.apply_hit(f, o, tech, "grab", o.x, o.y + 0.8, extra={"throw": True})
                a.phase_t = a.phase_dur
        if d == "counter" and a.data.get("triggered") and not a.data.get("struck"):
            if a.phase_t - a.data["trig_t"] > 0.07:
                a.data["struck"] = True
                if abs(o.x - f.x) <= p["reach"] + 0.45 and not o.hidden:
                    self.apply_hit(f, o, tech, "counter", o.x - 0.15 * f.facing, o.y + 1.1, extra={"counter": True})
                else:
                    self.event("whoosh", fighter=f.side, delivery="counter", abilities=tech["abilities"], limb="hand_f")

    # --------------------------------------------------------- spawning
    def _style(self, tech):
        if not tech["abilities"]:
            return "orb"
        return self.ab[tech["abilities"][0]]["projectile"]

    def _spawn_projectile(self, f, o, tech):
        p = tech["params"]
        hx, hy = self.origin_point(f, tech)
        tx, ty = o.x, o.y + 1.1
        ang = math.atan2(ty - hy, (tx - hx) * f.facing)
        ang = clamp(ang, -0.5, 0.6)
        spd = p.get("speed", 11.0)
        g = p.get("gravity", 0.0)
        if g > 0:  # ballistic lob that lands on the opponent
            dist = max(1.0, abs(tx - hx))
            tflight = clamp(dist / spd, 0.35, 1.1)
            vx_ = dist / tflight
            vy_ = ((o.y + 0.6 - hy) + 0.5 * g * tflight * tflight) / tflight
            spd = math.hypot(vx_, vy_)
            ang = math.atan2(vy_, vx_)
        n = p.get("hits", 1) if tech["timing"] == "multi_hit" else 1
        for i in range(n):
            pr = Projectile(f.side, tech, hx + 0.15 * f.facing, hy, spd * math.cos(ang) * f.facing, spd * math.sin(ang),
                            p.get("radius", 0.2), tech["abilities"], self._style(tech))
            if i > 0:
                pr.x -= f.facing * 0.55 * i
                pr.age = -0.05 * i
            self.projectiles.append(pr)
        f.stats["projectiles"] += n
        self.event("projectile", fighter=f.side, abilities=tech["abilities"], x=hx, y=hy, style=self._style(tech), tech=tech["id"],
                   weapon=weapon_class(self.tech_weapon(f, tech)), dir=f.facing)

    def origin_point(self, f, tech):
        """Where a projectile / beam leaves the body: hand, muzzle or mouth."""
        j = f.anim.joints
        if not j:
            return f.x + 0.5 * f.facing, f.y + 1.3
        if any(self.ab.get(a, {}).get("origin") == "mouth" for a in tech["abilities"]):
            hx, hy = j[J["head"]]
            return hx + 0.17 * f.facing, hy - 0.03
        hx, hy = j[J["hand_f"]]
        w = self.tech_weapon(f, tech)
        if weapon_class(w) in ("firearm", "staff") and WEAPONS[w]["len"] > 0:
            ex, ey = j[J["elbow_f"]]
            dx, dy = hx - ex, hy - ey
            n = math.hypot(dx, dy) or 1.0
            L = WEAPONS[w]["len"]
            return hx + dx / n * L, hy + dy / n * L
        return hx, hy

    def _slam_impact(self, f, tech):
        p = tech["params"]
        x = f.x + f.facing * 0.85
        self.blasts.append(Blast(f.side, tech, x, 0.2, p.get("radius", 1.5), 0.0, tech["abilities"], {"low": True, "trap": p.get("trap")}))
        self.event("slam", fighter=f.side, x=x, abilities=tech["abilities"], r=p.get("radius", 1.5))

    # ------------------------------------------------------------ physics
    def _physics(self, f, dt):
        if f.hidden:
            return
        a = f.action
        gscale = 1.0
        if a.kind == "technique":
            if a.phase == "antic" and not f.grounded:
                gscale = 0.3
            if a.phase == "move" and a.data.get("dashing"):
                gscale = 0.15
            if a.phase == "active" and a.tech["delivery"] in ("beam", "projectile") and not f.grounded:
                gscale = 0.25
        if a.kind == "grabbed":
            return
        if not f.grounded:
            f.vy += GRAVITY * gscale * dt
        f.x += f.vx * dt
        f.y += f.vy * dt
        if f.y <= 0.0:
            if not f.grounded:
                impact = -f.vy
                f.grounded = True
                f.y = 0.0
                f.vy = 0.0
                if a.kind not in ("knockdown",):
                    self.event("land", fighter=f.side, x=f.x, heavy=impact > 9)
                if a.kind == "hitstun" and a.data.get("knockdown"):
                    f.set_action(Action("knockdown", phases=[("lie", 0.7), ("getup", 0.45)]), blend=0.08)
                    self.event("land", fighter=f.side, x=f.x, heavy=True)
            f.y = 0.0
            f.vy = 0.0
        else:
            f.grounded = False
        driven = (a.kind in ("move", "reset") or (a.kind == "technique" and a.phase in ("move",))
                  or (a.kind == "technique" and a.phase == "active" and a.tech["delivery"] in ("charge",)))
        if f.grounded and not driven:
            k = 14.0
            if any(z.kind == "frozen" and z.x0 <= f.x <= z.x1 and z.owner != f.side for z in self.zones):
                k = 2.5
            if a.kind in ("hitstun", "knockdown", "dodge"):
                k = 7.0
            f.vx *= math.exp(-k * dt)
        lim = HALF - 0.3
        if f.x < -lim or f.x > lim:
            side = -1 if f.x < 0 else 1
            f.x = side * lim
            if a.kind == "hitstun" and abs(f.vx) > 5.0:
                f.vx = -f.vx * 0.35
                self.event("wall_hit", fighter=f.side, x=f.x, y=f.y + 1.0)
            elif f.vx * side > 0:
                f.vx = 0.0

    def _separate(self):
        a, b = self.fighters
        if a.hidden or b.hidden:
            return
        if a.y > 0.9 or b.y > 0.9:
            return
        if "grabbed" in (a.action.kind, b.action.kind):
            return
        dx = b.x - a.x
        if abs(dx) < 0.5:
            push = min(0.03, (0.5 - abs(dx)) / 2)
            s = 1 if dx >= 0 else -1
            a.x -= push * s
            b.x += push * s

    # ------------------------------------------------------------ entities
    def _update_entities(self, dt):
        fs = self.fighters
        new = []
        for pr in self.projectiles:
            if not pr.alive:
                continue
            pr.age += dt
            pr.ttl -= dt
            tgt = fs[1 - pr.owner]
            if pr.age < 0:
                continue
            if pr.g > 0:
                pr.vy -= pr.g * dt
            if pr.homing > 0 and not tgt.hidden:
                desired = math.atan2(tgt.y + 1.1 - pr.y, tgt.x - pr.x)
                cur = math.atan2(pr.vy, pr.vx)
                diff = (desired - cur + math.pi) % (2 * math.pi) - math.pi
                cur += clamp(diff, -pr.homing * dt, pr.homing * dt)
                spd = math.hypot(pr.vx, pr.vy)
                pr.vx, pr.vy = spd * math.cos(cur), spd * math.sin(cur)
            if pr.split_t > 0 and pr.age >= pr.split_t:
                pr.split_t = -1
                spd = math.hypot(pr.vx, pr.vy)
                cur = math.atan2(pr.vy, pr.vx)
                for off in (-0.22, 0.22):
                    q = Projectile(pr.owner, pr.tech, pr.x, pr.y, spd * math.cos(cur + off), spd * math.sin(cur + off), pr.r * 0.85, pr.abilities, pr.style)
                    q.split_t = -1
                    q.age = pr.age
                    new.append(q)
                self.event("split", x=pr.x, y=pr.y, abilities=pr.abilities)
            if pr.detonate > 0 and pr.age >= pr.detonate:
                pr.alive = False
                self.blasts.append(Blast(pr.owner, pr.tech, pr.x, pr.y, 1.15, 0.0, pr.abilities, {"trap": pr.tech["params"].get("trap")}))
                continue
            speed = math.hypot(pr.vx, pr.vy)
            n = max(1, int(math.ceil(speed * dt / max(0.05, pr.r * 0.7))))
            for _ in range(n):
                px, py = pr.x, pr.y
                pr.x += pr.vx * dt / n
                pr.y += pr.vy * dt / n
                if pr.hits > 0 and not tgt.hidden and not tgt.discont and self.state == "fight" and self._circle_hits(tgt, (px, py), (pr.x, pr.y), pr.r):
                    res = self.apply_hit(fs[pr.owner], tgt, pr.tech, "projectile", pr.x, pr.y, proj=pr)
                    if res == "reflected":
                        break
                    if res in ("dodged",):
                        pr.hits = 0
                        continue
                    pr.hits -= 1
                    if not pr.pierce:
                        pr.alive = False
                        if pr.g > 0:
                            self.event("explode", x=pr.x, y=pr.y, r=0.9, abilities=pr.abilities, low=False)
                        break
                for q in self.projectiles:
                    if q is not pr and q.alive and q.owner != pr.owner and math.hypot(q.x - pr.x, q.y - pr.y) < q.r + pr.r:
                        pr.alive = q.alive = False
                        self.event("clash", x=(q.x + pr.x) / 2, y=(q.y + pr.y) / 2, abilities=pr.abilities + q.abilities)
                        self._reaction_from(pr.abilities, q.abilities, (q.x + pr.x) / 2)
                        break
                if not pr.alive:
                    break
                for es in self.envs:
                    if es.owner != pr.owner and es.state == "erupt" and abs(pr.x - es.x) < es.radius * 0.6 and pr.y < es.height:
                        pr.alive = False
                        self.event("impact", x=pr.x, y=pr.y, abilities=pr.abilities, blocked=True)
                        break
                if not pr.alive:
                    break
                if pr.y < pr.r * 0.5:
                    pr.alive = False
                    if pr.g > 0:  # bombs, kegs, cannonballs and bottles burst on landing
                        self.blasts.append(Blast(pr.owner, pr.tech, pr.x, 0.3, 1.1, 0.0, pr.abilities, {"low": True, "trap": pr.tech["params"].get("trap")}))
                    self.event("impact", x=pr.x, y=0.05, abilities=pr.abilities, ground=True)
                    self._maybe_zone(pr.owner, pr.abilities, pr.x, 0.35, pr.tech["params"].get("trap"))
                    break
                if abs(pr.x) > HALF + 0.5 or pr.y > 9:
                    pr.alive = False
                    break
            if pr.ttl <= 0 and pr.alive:
                pr.alive = False
                self.event("impact", x=pr.x, y=pr.y, abilities=pr.abilities, fizzle=True)
        self.projectiles = [p for p in self.projectiles + new if p.alive]

        # Beams
        alive_beams = []
        for bm in self.beams:
            f = fs[bm.owner]
            a = f.action
            if not (a.kind == "technique" and a.tech is bm.tech and a.phase == "active"):
                self.event("beam_end", fighter=bm.owner, x=bm.x1, y=bm.y1, abilities=bm.abilities)
                continue
            tgt = fs[1 - bm.owner]
            hx, hy = self.origin_point(f, bm.tech)
            bm.x0, bm.y0 = hx + 0.1 * f.facing, hy
            ang = math.atan2(tgt.y + 1.1 - hy, (tgt.x - hx) * f.facing)
            bm.angle = clamp(ang, -0.35, 0.35)
            dx, dy = math.cos(bm.angle) * f.facing, math.sin(bm.angle)
            length = 12.0
            if dx > 0:
                length = min(length, (HALF + 0.5 - bm.x0) / dx)
            elif dx < 0:
                length = min(length, (-HALF - 0.5 - bm.x0) / dx)
            if dy < 0:
                length = min(length, bm.y0 / -dy)
            # beam clash
            clash = None
            for other in self.beams:
                if other is not bm and other.owner != bm.owner and fs[other.owner].facing != f.facing:
                    clash = (bm.x0 + fs[other.owner].anim.joints[J["hand_f"]][0]) / 2 if fs[other.owner].anim.joints else None
            hit_len = None
            if not tgt.hidden:
                cx, cy = tgt.x, tgt.y + 1.0
                t_along = (cx - bm.x0) * dx + (cy - bm.y0) * dy
                if 0 < t_along < length:
                    px, py = bm.x0 + dx * t_along, bm.y0 + dy * t_along
                    if abs(px - cx) < 0.35 + bm.width and abs(py - cy) < 0.85 + bm.width / 2:
                        hit_len = t_along - 0.2
            if clash is not None:
                length = abs(clash - bm.x0) / max(0.2, abs(dx))
                bm.tick += dt
                if bm.tick > 0.12:
                    bm.tick = 0.0
                    self.event("beam_clash", x=clash, y=bm.y0, abilities=bm.abilities)
                    f.vx -= 1.0 * f.facing
            elif hit_len is not None:
                length = hit_len + 0.25
                bm.tick += dt
                interval = bm.tech["params"]["active"] / max(1, bm.tech["params"]["hits"])
                if bm.tick >= interval * 0.95 or bm.hits_done == 0:
                    bm.tick = 0.0
                    if bm.hits_done < bm.tech["params"]["hits"] and self.state == "fight":
                        bm.hits_done += 1
                        self.apply_hit(f, tgt, bm.tech, "beam", bm.x0 + dx * hit_len, bm.y0 + dy * hit_len)
            bm.x1, bm.y1 = bm.x0 + dx * length, bm.y0 + dy * length
            alive_beams.append(bm)
        self.beams = alive_beams

        # Environmental strikes
        alive_env = []
        for es in self.envs:
            es.t += dt
            tgt = fs[1 - es.owner]
            if es.state == "warn" and es.t >= es.delay:
                es.state = "erupt"
                es.t = 0.0
                self.event("env_erupt", x=es.x, abilities=es.abilities, form=es.form, r=es.radius)
                self._maybe_zone(es.owner, es.abilities, es.x, 0.6, es.tech["params"].get("trap"))
            if es.state == "erupt":
                es.height = 1.9 * smoothstep(es.t / 0.12)
                if not es.hit_done and es.t > 0.03:
                    es.hit_done = True
                    if not tgt.hidden and abs(tgt.x - es.x) < es.radius + 0.3 and tgt.y < 1.2 and self.state == "fight":
                        self.apply_hit(fs[es.owner], tgt, es.tech, "env", tgt.x, 0.6)
                if es.t > 0.55:
                    es.state = "retract"
                    es.t = 0.0
            if es.state == "retract":
                es.height = 1.9 * (1 - smoothstep(es.t / 0.28))
                if es.t > 0.28:
                    continue
            alive_env.append(es)
        self.envs = alive_env

        # Blasts / explosions
        alive_bl = []
        for bl in self.blasts:
            bl.delay -= dt
            if bl.delay > 0:
                alive_bl.append(bl)
                continue
            if bl.done:
                continue
            bl.done = True
            self.event("explode", x=bl.x, y=bl.y, r=bl.r, abilities=bl.abilities, low=bl.extra.get("low", False))
            tgt = fs[1 - bl.owner]
            if bl.extra.get("trap"):
                self._maybe_zone(bl.owner, bl.abilities, bl.x, bl.r, True)
            if not tgt.hidden and self.state == "fight":
                cx, cy = tgt.x, tgt.y + 0.9
                low_ok = (not bl.extra.get("low")) or tgt.y < 0.45
                if low_ok and math.hypot(cx - bl.x, (cy - bl.y) * 0.8) < bl.r + 0.35:
                    self.apply_hit(fs[bl.owner], tgt, bl.tech, "area", cx, cy, extra=bl.extra)
        self.blasts = alive_bl

        # Zones
        alive_z = []
        for z in self.zones:
            z.ttl -= dt
            if z.ttl <= 0:
                continue
            for f in fs:
                if f.side == z.owner or not f.grounded or not (z.x0 <= f.x <= z.x1) or self.state != "fight":
                    continue
                if z.kind == "burning":
                    f.poise -= 4.5 * dt
                elif z.kind == "electrified":
                    f.poise -= 12.0 * dt
                    f.hitflash = max(f.hitflash, 0.03)
                elif z.kind == "toxic":
                    f.poise -= 6.0 * dt
                elif z.kind in ("vines", "shadow"):
                    f.slow_t = 0.1
                elif z.kind == "well":
                    c = (z.x0 + z.x1) / 2
                    f.vx += (3.5 if c > f.x else -3.5) * dt
            alive_z.append(z)
        self.zones = alive_z

    def _maybe_zone(self, owner, abilities, x, r, force=False):
        if not self.cfg["combat"].get("environmental_interactions", True) or not abilities:
            return
        ab = self.ab.get(abilities[0])
        kind = ab.get("zone") if ab else None
        if not kind:
            return
        if not force and not self.rng_misc.chance(0.35):
            return
        x0, x1 = x - max(0.6, r), x + max(0.6, r)
        # environmental reactions with existing zones
        for z in list(self.zones):
            if z.x1 < x0 or z.x0 > x1:
                continue
            pair = {z.kind, kind}
            if pair == {"burning", "frozen"}:
                self.zones.remove(z)
                self.event("reaction", kind="steam", x=(max(x0, z.x0) + min(x1, z.x1)) / 2, abilities=abilities)
                return
            if pair == {"frozen", "wet"}:
                z.kind = "frozen"
                z.ttl = 5.0
                self.event("reaction", kind="freeze", x=x, abilities=abilities)
                return
            if pair == {"burning", "vines"}:
                z.kind = "burning"
                z.ttl = 4.0
                self.event("reaction", kind="wildfire", x=x, abilities=abilities)
                return
        if len(self.zones) >= 4:
            self.zones.pop(0)
        self.zones.append(Zone(x0, x1, kind, 4.5 if force else 3.5, owner, abilities))
        self.event("zone", kind=kind, x0=x0, x1=x1, abilities=abilities)

    def _reaction_from(self, abs_a, abs_b, x):
        tags_a = {t for i in abs_a for t in self.ab[i]["tags"]} if abs_a else set()
        tags_b = {t for i in abs_b for t in self.ab[i]["tags"]} if abs_b else set()
        tags = tags_a | tags_b
        if "heat" in tags and ("cold" in tags or "fluid" in tags):
            self.event("reaction", kind="steam", x=x, abilities=abs_a + abs_b)
        elif "electric" in tags and "fluid" in tags:
            self.event("reaction", kind="conduct", x=x, abilities=abs_a + abs_b)

    # ------------------------------------------------------------ hits
    def _hurt_segments(self, f):
        j = f.anim.joints
        if j is None:
            return []
        return [((j[J["hip"]]), (j[J["head"]]), 0.17), (j[J["hip"]], j[J["knee_f"]], 0.1), (j[J["knee_f"]], j[J["foot_f"]], 0.09),
                (j[J["hip"]], j[J["knee_b"]], 0.1), (j[J["knee_b"]], j[J["foot_b"]], 0.09)]

    def _circle_hits(self, tgt, p0, p1, r):
        for a, b, rr in self._hurt_segments(tgt):
            if seg_seg_dist(p0, p1, a, b) <= r + rr:
                return True
        return False

    def tech_weapon(self, f, tech):
        if tech:
            for aid in tech["abilities"]:
                w = self.ab.get(aid, {}).get("weapon")
                if w:
                    return w
            if tech["abilities"]:
                return None  # elemental / energy technique
        return f.weapon

    def _effector(self, f, limb, joints, tech=None):
        if limb == "weapon":
            hx, hy = joints[J["hand_f"]]
            ex, ey = joints[J["elbow_f"]]
            dx, dy = hx - ex, hy - ey
            n = math.hypot(dx, dy) or 1.0
            w = self.tech_weapon(f, tech)
            L = WEAPONS[w]["len"] if w in WEAPONS and WEAPONS[w]["len"] > 0 else 0.95
            return (hx, hy), (hx + dx / n * L, hy + dy / n * L)
        if limb == "body":
            limb = "chest"
        p = joints[J[limb]]
        return p, p

    def _melee_check(self, f, o):
        a = f.action
        if a.kind != "technique" or a.phase != "active" or a.data.get("hit_stage") or o.hidden:
            return
        tech = a.tech
        if tech["kind"] not in ("melee", "grab"):
            return
        if tech["delivery"] == "grapple" and a.data.get("grabbed"):
            return
        tpl = template(tech["delivery"], a.data.get("variant", tech["variant"]))
        limb = tpl["limb"]
        j, pj = f.anim.joints, f.anim.prev_joints or f.anim.joints
        r = 0.1 if limb != "chest" else 0.3
        if tech["delivery"] == "grapple":
            r = 0.2
        if tech["delivery"] == "charge":
            limb, r = "chest", 0.32
        a0, a1 = self._effector(f, limb, j, tech)
        b0, b1 = self._effector(f, limb, pj, tech)
        hit = False
        for s, e, rr in self._hurt_segments(o):
            if seg_seg_dist(b1, a1, s, e) <= r + rr or seg_seg_dist(a0, a1, s, e) <= r + rr:
                hit = True
                break
        if hit:
            a.data["hit_stage"] = True
            res = self.apply_hit(f, o, tech, "grab" if tech["delivery"] == "grapple" else "melee", a1[0], a1[1])
            if tech["delivery"] == "grapple" and res == "hit":
                a.data["grabbed"] = True

    def _adv(self, att_abs, dfd):
        if not att_abs or not dfd.abilities:
            return 1.0
        ta = {t for i in att_abs for t in self.ab[i]["tags"]}
        td = set(dfd.abilities[0]["tags"])
        return 1.15 if any((x, y) in ADVANTAGE for x in ta for y in td) else 1.0

    def apply_hit(self, att, dfd, tech, kind, x, y, proj=None, extra=None):
        extra = extra or {}
        p = tech["params"]
        sa, sb = self.fighters[0].score, self.fighters[1].score
        ft = self.fight_t
        abil = tech["abilities"]
        if self.state != "fight":
            return "ignored"
        if dfd.invuln > 0 or dfd.hidden:
            if not extra.get("counter"):
                self.event("dodge", fighter=dfd.side, x=x, y=y)
                att.memory["dodged"] += 1
                dfd.memory["opp_dodges"] += 0
                att.memory["opp_dodges"] += 1
            return "dodged"
        da = dfd.action
        # Counter stance
        if (da.kind == "technique" and da.tech["delivery"] == "counter" and da.phase == "active"
                and not da.data.get("triggered") and kind in ("melee", "grab", "projectile")):
            if kind == "projectile" and da.tech["params"].get("reflect") and proj is not None:
                proj.owner = dfd.side
                proj.vx = -proj.vx * 1.15
                proj.vy = -proj.vy * 0.5
                proj.tech = da.tech if da.tech["kind"] == "projectile" else proj.tech
                self.event("reflect", fighter=dfd.side, x=x, y=y, abilities=da.tech["abilities"])
                da.data["triggered"] = True
                da.data["trig_t"] = da.phase_t
                da.data["struck"] = True
                return "reflected"
            if kind == "projectile" and da.tech["params"].get("absorb"):
                dfd.energy = min(100, dfd.energy + 22)
                self.event("absorb", fighter=dfd.side, x=x, y=y, abilities=da.tech["abilities"])
                return "absorbed"
            if kind in ("melee", "grab"):
                da.data["triggered"] = True
                da.data["trig_t"] = da.phase_t
                dfd.stats["counters"] += 1
                att.memory["countered"] += 1
                self.event("counter", fighter=dfd.side, x=x, y=y, abilities=da.tech["abilities"])
                att.set_action(Action("hitstun", 0.5, data={"low": False}), blend=0.04)
                att.vx = -2.0 * att.facing
                return "countered"
        # Shield
        if dfd.shield_t > 0 and not p.get("guard_break"):
            if kind == "projectile":
                self.event("shield_block", fighter=dfd.side, x=x, y=y, abilities=abil)
                return "shielded"
            dfd.poise -= p["poise"] * 0.25
            self.event("shield_block", fighter=dfd.side, x=x, y=y, abilities=abil)
            return "shielded"
        L = self.director.lethality(ft, sa, sb)
        adv = self._adv(abil, dfd)
        stun = p.get("stun", 1.0)
        if abil and any("electric" in self.ab[i]["tags"] for i in abil):
            for z in self.zones:
                if z.kind == "wet" and z.x0 <= dfd.x <= z.x1 and dfd.grounded:
                    stun *= 1.5
                    z.kind = "electrified"
                    z.ttl = 1.4
                    self.event("reaction", kind="conduct", x=dfd.x, abilities=abil)
        height = "low" if tech["delivery"] in ("sweep",) or (kind == "area" and extra.get("low")) or kind == "env" else "mid"
        facing_ok = dfd.facing == (1 if att.x > dfd.x else -1)
        blocking = da.kind == "block" and facing_ok
        if blocking and not p.get("unblockable") and height != "low" and kind != "grab":
            if p.get("guard_break"):
                dfd.poise -= p["poise"] * 0.9 * L
                self.event("guard_crush", fighter=dfd.side, x=x, y=y, abilities=abil)
                dfd.set_action(Action("hitstun", 0.32, data={"low": False}), blend=0.04)
                dfd.vx = 2.5 * (1 if dfd.x > att.x else -1)
            else:
                dfd.poise -= p["poise"] * 0.32 * L
                dfd.vx = 2.2 * (1 if dfd.x > att.x else -1)
                da.dur = max(da.dur, da.t + 0.16)
                da.phase_dur = da.dur
                dfd.stats["blocked"] += 1
                att.memory["opp_blocks"] += 1
                att.focus = min(100, att.focus + 2)
                self.event("block", fighter=dfd.side, x=x, y=y, abilities=abil, dmg=p["dmg"])
                if dfd.poise <= 0:
                    self._guard_break(att, dfd, x, y, abil)
                return "blocked"
            if dfd.poise <= 0:
                self._guard_break(att, dfd, x, y, abil)
            return "blocked"
        # Clean hit
        dmg_poise = p["poise"] * L * adv * (1.0 + 0.1 * (stun - 1.0))
        if extra.get("counter"):
            dmg_poise *= 1.3
        broken = da.kind == "broken"
        combo = (self.t - dfd.last_hit_t) < 0.75 and dfd.action.kind in ("hitstun", "broken", "grabbed", "knockdown")
        dfd.last_hit_t = self.t
        dfd.no_regen = 1.6
        att.stats["hits"] += 1
        att.memory["landed"] += 1
        att.focus = min(100.0, att.focus + p["dmg"] * 1.3)
        dfd.focus = min(100.0, dfd.focus + p["dmg"] * 0.8)
        dfd.hitflash = 0.08
        finisher = p.get("finisher", False)
        sudden = self.director.sudden_death(ft)
        scoring = (broken and p["dmg"] >= 6.5) or (finisher and dfd.poise - dmg_poise <= 40) or (sudden and p["dmg"] >= 6)
        if scoring:
            if self.director.can_score(ft, att.score, sa, sb) or (sudden and ft - self.director.last_point > 3):
                self.score_point(att, dfd, tech, x, y, kind)
                return "score"
            # Too early for a decisive point: heavy damage, the defender survives.
            dfd.poise = 30.0
            self.event("hit", level="significant", fighter=dfd.side, attacker=att.side, x=x, y=y, abilities=abil, survived=True,
                       tech=tech["id"], dmg=p["dmg"])
            att.stats["significant"] += 1
            self._knock(att, dfd, tech, (6.5, 4.5), knockdown=True)
            return "hit"
        dfd.poise -= dmg_poise
        if dfd.poise <= 0:
            self.event("hit", level="significant", fighter=dfd.side, attacker=att.side, x=x, y=y, abilities=abil, tech=tech["id"], dmg=p["dmg"])
            self._guard_break(att, dfd, x, y, abil)
            return "hit"
        if combo:
            dfd.combo_taken += 1
            level = "combo"
            att.stats["combo"] += 1
        elif dmg_poise >= 14:
            level = "significant"
            att.stats["significant"] += 1
        else:
            level = "minor"
            att.stats["minor"] += 1
        self.event("hit", level=level, fighter=dfd.side, attacker=att.side, x=x, y=y, abilities=abil, tech=tech["id"],
                   dmg=p["dmg"], combo=dfd.combo_taken, delivery=tech["delivery"])
        if p.get("chain"):
            self.blasts.append(Blast(att.side, tech, dfd.x, dfd.y + 1.0, 0.6, 0.16, abil, {"chain": True}))
        if p.get("delay_blast"):
            self.blasts.append(Blast(att.side, tech, dfd.x, dfd.y + 1.0, 0.9, p["delay_blast"], abil, {"mark": True}))
        if extra.get("throw"):
            self._knock(att, dfd, tech, (6.0, 6.5), knockdown=True, away=True)
            return "hit"
        if kind == "grab" and tech["delivery"] == "grapple":
            dfd.set_action(Action("grabbed", 1.0), blend=0.05)
            self.event("grab", fighter=att.side, x=x, y=y)
            return "hit"
        # Combo breaker
        if dfd.combo_taken >= 3 and dfd.energy >= 35 and self.rng_ai[dfd.side].chance(0.3 + 0.3 * dfd.traits["evasive"]):
            dfd.energy -= 35
            dfd.combo_taken = 0
            dfd.set_action(Action("burst", 0.35), blend=0.04)
            dfd.invuln = 0.4
            self.event("burst", fighter=dfd.side, x=dfd.x, y=dfd.y + 1.0, abilities=dfd.ability_ids)
            if abs(att.x - dfd.x) < 2.2:
                att.set_action(Action("hitstun", 0.4, data={"low": False}), blend=0.04)
                att.vx = 6.0 * (1 if att.x > dfd.x else -1)
                att.vy = 3.0
                att.grounded = False
            return "hit"
        kb = p["kb"]
        knock = p.get("knockdown") and level != "minor"
        self._knock(att, dfd, tech, kb, knockdown=knock or (p.get("launcher") and False),
                    scale=max(0.55, 1.0 - 0.12 * dfd.combo_taken))
        return "hit"

    def _knock(self, att, dfd, tech, kb, knockdown=False, scale=1.0, away=False):
        p = tech["params"]
        d = 1 if dfd.x >= att.x else -1
        if away:
            d = att.facing
        dfd.vx = kb[0] * d * scale
        launch = p.get("launcher") or kb[1] > 3.0
        if (launch or not dfd.grounded) and kb[1] > 0:
            dfd.vy = max(dfd.vy, kb[1] * scale)
            dfd.grounded = False
        dur = (0.2 + 0.012 * p["dmg"] * p.get("stun", 1.0)) * scale
        low = tech["delivery"] in ("charge", "punch") and dfd.y < 0.1 and kb[1] < 1.0
        data = {"low": low, "knockdown": knockdown or (not dfd.grounded and kb[1] > 5), "spin": 3.0 * d * -1 if not dfd.grounded else 0.0}
        dfd.set_action(Action("hitstun", dur, data=data), blend=0.03)
        if knockdown and dfd.grounded and dfd.vy <= 0:
            dfd.vy = 3.5
            dfd.grounded = False
            data["knockdown"] = True
        if dfd.action.kind == "hitstun" and not dfd.grounded:
            dfd.y = max(dfd.y, 0.01)

    def _guard_break(self, att, dfd, x, y, abil):
        dfd.poise = 0.0
        dfd.stats["guard_breaks"] += 0
        att.stats["guard_breaks"] += 1
        dfd.set_action(Action("broken", 1.25), blend=0.06)
        dfd.vx = 2.0 * (1 if dfd.x > att.x else -1)
        self.event("guard_break", fighter=dfd.side, attacker=att.side, x=x, y=y, abilities=abil)
        att.think_cd = 0.0

    def score_point(self, att, dfd, tech, x, y, kind):
        att.score += 1
        att.stats["points"] += 1
        final = att.score >= self.ptw
        self.director.last_point = self.fight_t
        self.points.append({"t": round(self.fight_t, 3), "abs_t": round(self.t, 4), "scorer": att.side, "tech": tech["id"],
                            "tech_name": tech["name"], "score": [self.fighters[0].score, self.fighters[1].score], "final": final})
        self.event("ko" if final else "score", attacker=att.side, defender=dfd.side, x=x, y=y, abilities=tech["abilities"],
                   tech=tech["id"], name=tech["name"], score=[self.fighters[0].score, self.fighters[1].score],
                   finisher=tech["params"].get("finisher", False))
        d = 1 if dfd.x >= att.x else -1
        dfd.vx = 7.5 * d
        dfd.vy = 7.5
        dfd.grounded = False
        dfd.y = max(dfd.y, 0.02)
        dfd.set_action(Action("knockdown", phases=[("fall", 10.0), ("lie", 1.2 if not final else 99.0), ("getup", 0.5)]), blend=0.03)
        dfd.poise = 0.0
        self.beams.clear()
        if final:
            self.winner = att.side
            self.final_point_t = self.fight_t
            self.state = "outro"
            self.state_t = 0.0
        else:
            self.state = "point_pause"
            self.state_t = 0.0

    # ------------------------------------------------------------ meters
    def _meters(self, dt):
        for f in self.fighters:
            f.invuln = max(0.0, f.invuln - dt)
            f.shield_t = max(0.0, f.shield_t - dt)
            f.slow_t = max(0.0, f.slow_t - dt)
            f.hitflash = max(0.0, f.hitflash - dt)
            f.no_regen = max(0.0, f.no_regen - dt)
            if self.state != "fight":
                continue
            regen = 10.0 + (34.0 if f.action.kind == "charge" else 0.0)
            f.energy = min(100.0, f.energy + regen * dt)
            if f.action.kind == "charge":
                f.focus = min(100.0, f.focus + 4.0 * dt)
            if f.no_regen <= 0 and f.action.kind != "broken" and f.poise < 100:
                f.poise = min(100.0, f.poise + 6.0 * dt)
            if f.poise < 0 and f.action.kind not in ("broken",) and f.action.kind not in ("knockdown",):
                self._guard_break(self.opp(f), f, f.x, f.y + 1.0, [])
            ult = f.action.kind == "technique" and f.action.tech["tier"] == "ultimate"
            charging = f.action.kind == "charge" or (f.action.kind == "technique" and f.action.phase == "antic" and f.action.tech["timing"] in ("charged", "finisher"))
            f.aura += ((1.0 if (ult or charging) else 0.35 if f.focus >= 100 else 0.0) - f.aura) * min(1.0, dt * 6)

    # ------------------------------------------------------------ animation
    def _animate(self, f, dt):
        a = f.anim
        target = action_pose(f, self.t)
        a.blend_t += dt
        if a.blend_t < a.blend_dur:
            b = smoothstep(a.blend_t / a.blend_dur)
            local = {k: a.blend_from[k] + (target[k] - a.blend_from[k]) * b for k in target}
        else:
            local = target
        a.local = local
        a.stride += abs(f.vx) * dt / (1.0 + 0.07 * abs(f.vx))
        rot = local["rot"]
        grounded = f.grounded and abs(rot) < 0.05 and not f.hidden
        lead = f.vx * 0.09 if grounded else 0.0
        desired = [(f.x + f.facing * local["ffx"] + lead, f.y + local["ffy"]), (f.x + f.facing * local["fbx"] + lead, f.y + local["fby"])]
        flags = [local["ffree"], local["fbfree"]]
        if f.discont:
            for ft_, (dx, dy) in zip(a.feet.feet, desired):
                ft_.x, ft_.y, ft_.planted, ft_.stepping = dx, max(0.0, dy), True, False
        feet, landed = a.feet.update(dt, desired, grounded, flags, abs(f.vx))
        for i in landed:
            if abs(f.vx) > 1.0 and self.state != "intro":
                self.event("step", fighter=f.side, x=feet[i][0], speed=abs(f.vx))
        fl = [((wx - f.x) * f.facing, wy - f.y) for wx, wy in feet]
        loc = solve_local(local, f.build, fl)
        a.prev_joints = a.joints
        a.joints = to_world(loc, rot, f.x, f.y, f.facing)
        if a.prev_joints is None or f.discont:
            a.prev_joints = a.joints

    # ------------------------------------------------------------ recording
    def _record(self):
        fs = []
        for f in self.fighters:
            flags = 0
            k = f.action.kind
            if k == "block":
                flags |= FLAG_BLOCK
            if f.invuln > 0:
                flags |= FLAG_INVULN
            if f.shield_t > 0:
                flags |= FLAG_SHIELD
            if f.hitflash > 0:
                flags |= FLAG_FLASH
            if k == "charge" or (k == "technique" and f.action.phase == "antic" and f.action.tech["timing"] in ("charged", "finisher")):
                flags |= FLAG_CHARGE
            if k == "broken":
                flags |= FLAG_BROKEN
            if f.hidden:
                flags |= FLAG_HIDDEN
            if f.discont:
                flags |= FLAG_DISCONT
            if k == "technique" and f.action.tech["tier"] == "ultimate":
                flags |= FLAG_ULT
            tech = f.action.tech if k == "technique" else None
            front = self.tech_weapon(f, tech) if tech and tech["abilities"] else (f.kit[0] if f.kit else None)
            if tech and not tech["abilities"]:
                front = None if not f.kit or weapon_class(f.kit[0]) in ("firearm", "bow") else f.kit[0]
            back = next((w for w in f.kit if w != front), None)
            if front and weapon_class(front) == "shield":
                front, back = back, front
            energy = None
            if tech and tech["delivery"] == "summon_weapon" and not self.tech_weapon(f, tech) and f.action.phase in ("antic", "active", "recovery"):
                energy = tech["abilities"]
            weapon = (front, back, energy)
            if front or back or energy:
                flags |= FLAG_WEAPON
            tech_ab = tech["abilities"] if tech else None
            limb = template(tech["delivery"], f.action.data.get("variant", tech["variant"]))["limb"] if tech else ""
            joints = [round(c, 4) for pt in f.anim.joints for c in pt]
            fs.append((round(f.x, 4), round(f.y, 4), f.facing, joints, k, flags, round(f.aura, 3), weapon, tech_ab,
                       f.action.phase if k == "technique" else "", round(f.vx, 3), limb))
        rec = {
            "t": round(self.t, 5),
            "f": fs,
            "p": [(pr.id, round(pr.x, 3), round(pr.y, 3), round(pr.vx, 2), round(pr.vy, 2), pr.r, pr.style, pr.abilities)
                  for pr in self.projectiles if pr.age >= 0],
            "b": [(bm.id, round(bm.x0, 3), round(bm.y0, 3), round(bm.x1, 3), round(bm.y1, 3), bm.width, bm.abilities) for bm in self.beams],
            "e": [(es.id, es.x, round(es.height, 3), es.radius, es.form, es.state, es.abilities, round(es.t, 3)) for es in self.envs],
            "z": [(z.id, round(z.x0, 2), round(z.x1, 2), z.kind, round(min(1.0, z.ttl / 0.6, (z.max_ttl - z.ttl) / 0.3 + 0.01), 3), z.abilities) for z in self.zones],
            "h": (self.fighters[0].score, self.fighters[1].score, round(self.fighters[0].poise, 1), round(self.fighters[1].poise, 1),
                  round(self.fighters[0].energy, 1), round(self.fighters[1].energy, 1), round(self.fighters[0].focus, 1),
                  round(self.fighters[1].focus, 1)),
            "s": self.state,
        }
        self.frames.append(rec)

    def _result(self):
        fs = self.fighters
        h = hashlib.sha256()
        for fr in self.frames[::30]:
            for fd in fr["f"]:
                h.update(repr(fd[3]).encode())
        tech_uses = {}
        for e in self.events:
            if e["type"] == "technique":
                tech_uses[e["tech"]] = tech_uses.get(e["tech"], 0) + 1
        return MatchResult(
            frames=self.frames,
            events=self.events,
            winner=self.winner,
            scores=[fs[0].score, fs[1].score],
            points=self.points,
            fight_start=self.fight_start,
            final_point_t=self.final_point_t,
            sim_duration=self.t,
            archetype=self.director.archetype,
            arena=self.arena,
            stats=[f.stats for f in fs],
            discoveries=self.discoveries,
            tech_uses=tech_uses,
            timeline_hash=h.hexdigest(),
            fighters=[f.spec for f in fs],
            dt=DT,
        )
