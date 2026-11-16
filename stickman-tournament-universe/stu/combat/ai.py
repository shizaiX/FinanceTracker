"""Tactical fighter AI: utility-based decisions + reactive defense + adaptation.

Each fighter evaluates distance, energy, opponent state, phase of the match and
what it has learned about the opponent (block/dodge habits, favourite
deliveries) and picks an option through a temperature-controlled softmax:
controlled randomness, but never illogical (out-of-range melee is impossible,
defense only inside a valid response window after a human-like reaction delay).
"""
from __future__ import annotations

from .techniques import DELIVERIES, MOVEMENTS, compose_valid

TIER_PHASE = {
    "basic":    [1.15, 0.85, 0.65, 0.55],
    "infused":  [0.95, 1.15, 1.05, 0.95],
    "fusion":   [0.15, 0.7, 1.45, 1.6],
    "ultimate": [0.0, 0.0, 1.6, 3.2],
}


def tech_utility(f, o, tech, dist, m):
    p = tech["params"]
    if f.cooldowns.get(tech["id"], -1) > m.t:
        return 0.0
    if p["cost"] > f.energy or p.get("focus_cost", 0) > f.focus:
        return 0.0
    d = tech["delivery"]
    dd = DELIVERIES[d]
    mv = tech["movement"]
    air = not f.grounded
    if air and (dd.get("ground_only") or mv not in ("none",)):
        return 0.0
    if not air and dd.get("air_only") and mv not in ("leap", "aerial_dash", "wall_jump", "teleport"):
        return 0.0
    if mv == "wall_jump" and abs(f.x) < m.half - 1.6:
        return 0.0
    if tech["tier"] == "ultimate" and not m.cfg["combat"].get("cinematic_finishers", True):
        return 0.0
    kind = tech["kind"]
    reach = p["reach"]
    closes = MOVEMENTS[mv]["closes"]
    if kind in ("melee", "grab", "area"):
        if mv == "none":
            fit = 1.0 if dist <= reach + 0.12 else 0.0
        elif mv == "backstep":
            fit = 0.0
        else:
            fit = 1.0 if dist <= reach + closes else 0.0
            if dist <= reach * 0.7 and mv in ("dash", "leap", "aerial_dash", "teleport"):
                fit *= 0.35
    elif kind in ("projectile", "beam"):
        fit = 1.0 if dist >= 2.0 else 0.45
        if mv == "backstep":
            fit = 1.2 if dist < 2.6 else 0.3
        if mv == "teleport":
            fit *= 0.7
    elif kind == "env":
        fit = 1.0 if dist >= dd.get("min_range", 1.4) + 0.4 else 0.0
    elif kind == "stance":
        fit = 0.9 if dist <= 2.6 else 0.0
        fit *= 0.5 + f.memory["countered"] * 0.0 + min(1.0, f.memory["opp_melee"] / 6.0)
    else:
        fit = 0.5
    if fit <= 0:
        return 0.0
    ph = m.director.phase_index(m.fight_t)
    u = 1.0 * fit * TIER_PHASE[tech["tier"]][ph]
    # Range mode (theme / config range mix): favour the current mode strongly
    # without making the other one impossible.
    if f.range_mode == "ranged":
        u *= 3.0 if kind in ("projectile", "beam", "env") else 0.08
        if mv == "backstep" and dist < 3.0:
            u *= 2.0  # shoot while backing off
    elif f.range_mode == "melee":
        u *= 2.0 if kind in ("melee", "grab", "area", "stance") else 0.6
        if f.charge_in and tech["movement"] in ("dash", "teleport", "leap", "aerial_dash") and kind in ("melee", "grab"):
            u *= 2.0  # charge in
    # Theme first: plain unarmed moves are only as common as the theme allows.
    if tech["tier"] == "basic":
        u *= 0.15 + 1.4 * f.physical_weight
    elif d in ("punch", "kick", "barrage", "uppercut") and not any(a.get("physical") for a in f.abilities if a["id"] in tech["abilities"]):
        u *= 0.45 + 2.0 * f.physical_weight  # powers are thrown, breathed, cast — not mainly punched
    elif kind in ("melee", "grab"):
        u *= 1.15
    tr = f.traits
    if kind in ("melee", "grab"):
        u *= 0.55 + tr["aggression"] * m.director.aggression(m.fight_t)
    elif kind in ("projectile", "beam", "env"):
        u *= (0.6 + tr["caution"] * 0.5 + (0.45 if tr["range"] > 2.0 else 0.0)) * m.director.arch["ranged"]
        if dist > 2.6:
            u *= 1.5
    elif kind == "stance":
        u *= tr["counter"] * 1.4
    # Opponent state.
    if o.action.kind == "broken":
        u *= 1.0 + p["dmg"] / 6.0 + (2.0 if tech["tier"] == "ultimate" else 0.0)
    if tech["tier"] == "ultimate":
        u *= 1.5 if o.poise < 45 else 0.5
    if not o.grounded and o.action.kind == "hitstun":
        if d in ("aerial_strike", "uppercut", "beam", "projectile", "kick"):
            u *= 2.0
        if dd.get("height") == "low":
            u *= 0.1
    elif not o.grounded:
        if d in ("uppercut", "beam", "projectile"):
            u *= 1.5
        if d in ("sweep", "slam", "env_strike"):
            u *= 0.15
    if m.cfg["combat"].get("adaptive_ai", True):
        mem = f.memory
        if mem["opp_blocks"] >= 3 and (p.get("unblockable") or p.get("guard_break") or dd.get("height") == "low"):
            u *= 1.0 + 0.25 * min(6, mem["opp_blocks"]) * tr["adaptability"]
        if mem["opp_dodges"] >= 3 and (kind in ("area", "beam") or p.get("homing")):
            u *= 1.0 + 0.2 * min(6, mem["opp_dodges"]) * tr["adaptability"]
    n = sum(1 for r in f.recent if r == tech["id"])
    u *= 0.5 ** n
    u *= 1.0 - 0.25 * (p["cost"] / 100.0)
    return u


def think(f, o, m):
    rng = m.rng_ai[f.side]
    dist = abs(o.x - f.x)
    tr = f.traits
    opts = []
    for tech in f.techs:
        u = tech_utility(f, o, tech, dist, m)
        if u > 0.02:
            opts.append((("tech", tech), u))
    if o.action.kind in ("broken", "grabbed"):
        # The opponent is stunned: no blocking, waiting or charging — go for the
        # punish right away (close the distance if nothing reaches yet).
        if opts:
            choice = max(opts, key=lambda x: x[1])[0]
            m.start_technique(f, o, choice[1])
        else:
            m.start_move(f, toward=True, dur=0.25, speed=7.0 if dist > 2.5 else 4.0)
            f.think_cd = 0.0
        return
    desired = tr["range"] * (0.8 if m.director.phase_index(m.fight_t) >= 2 else 1.0)
    if m.range_mix is not None:
        if m.fight_t >= f.mode_until:
            # Each fighter independently re-rolls its mode every few seconds;
            # over a fight this converges to the configured ranged share.
            # Close-combat phases are short charges, ranged phases last longer;
            # the probability is calibrated so the share of *attacks* matches the mix
            # (close combat produces attacks faster, hence the +0.1 bias).
            target = min(0.97, m.range_mix + 0.1)
            dr, dm = 5.0, 3.0
            p_r = target * dm / (target * dm + (1 - target) * dr)
            new = "ranged" if rng.random() < p_r else "melee"
            f.charge_in = new == "melee" and f.range_mode != "melee"
            f.range_mode = new
            f.mode_until = m.fight_t + (rng.uniform(3.2, 6.8) if new == "ranged" else rng.uniform(2.0, 4.0))
        desired = max(4.2, desired) if f.range_mode == "ranged" else 1.0
        if f.range_mode == "melee" and f.charge_in and dist > 2.2 and f.grounded and rng.chance(0.6):
            f.charge_in = False
            m.start_move(f, toward=True, dur=min(0.6, dist / 8.0), speed=8.0)  # rush in
            m.event("dash", fighter=f.side, x=f.x, abilities=f.ability_ids)
            return
        if dist < 2.2:
            f.charge_in = False
        if f.range_mode == "ranged" and dist < 3.2 and f.grounded and o.action.kind not in ("broken", "grabbed"):
            # Keep the distance: dash back, or jump over when cornered.
            if rng.chance(0.55):
                if abs(f.x) > m.half - 1.4:
                    m.start_jump(f, forward=True, flip=True, evade=True)
                else:
                    m.start_move(f, toward=False, dur=rng.uniform(0.3, 0.55), speed=6.5)
                return
    aggr = tr["aggression"] * m.director.aggression(m.fight_t)
    if dist > desired + 0.4:
        opts.append((("approach", None), 0.55 + 0.55 * aggr + 0.1 * (dist - desired)))
    if dist < desired - 0.3 and abs(f.x) < m.half - 1.0:
        opts.append((("retreat", None), 0.35 + 0.6 * tr["caution"]))
    opts.append((("hold", None), 0.2 + 0.3 * tr["caution"] + (0.5 * tr["caution"] if dist < 1.8 and o.free else 0.0)))
    if dist > 1.2 and f.grounded:
        opts.append((("jump", None), 0.08 + 0.25 * tr["evasive"]))
    if f.energy < 45 and dist > 3.0:
        opts.append((("charge", None), 0.45 + 0.4 * tr["caution"] + (45 - f.energy) / 60))
    if dist < 2.2 and f.grounded:
        opts.append((("bait", None), 0.08 + 0.25 * tr["creativity"] * (tr["counter"] + 0.2)))
    if m.cfg["combat"].get("special_abilities_enabled", True) and f.abilities and f.grounded:
        ph = m.director.phase_index(m.fight_t)
        opts.append((("improvise", None), tr["creativity"] * [0.06, 0.16, 0.26, 0.2][ph]))
    if not opts:
        return
    choice = rng.softmax_choice([x for x, _ in opts], [u for _, u in opts], temperature=0.35 + 0.45 * tr["temperature"])
    kind, tech = choice
    if kind == "tech":
        m.start_technique(f, o, tech)
    elif kind == "approach":
        run = dist > 4.0 and rng.chance(0.5)
        m.start_move(f, toward=True, dur=rng.uniform(0.25, 0.6), speed=6.0 if run else 2.6)
    elif kind == "retreat":
        m.start_move(f, toward=False, dur=rng.uniform(0.2, 0.45), speed=2.4)
    elif kind == "hold":
        if dist < 2.5 and rng.chance(0.35 + tr["caution"] * 0.6):
            m.start_block(f, rng.uniform(0.25, 0.5))
        else:
            f.think_cd = rng.uniform(0.15, 0.35)
    elif kind == "jump":
        m.start_jump(f, forward=rng.chance(0.6), flip=rng.chance(0.35))
    elif kind == "charge":
        m.start_charge(f, rng.uniform(0.6, 1.2))
    elif kind == "bait":
        m.start_move(f, toward=True, dur=0.18, speed=3.0, then_back=True)
    elif kind == "improvise":
        improvise(f, o, m, dist)
    if f.free and f.think_cd <= 0:
        f.think_cd = rng.uniform(0.1, 0.25)


def improvise(f, o, m, dist):
    """Dynamic combination discovery from live context."""
    rng = m.rng_discover[f.side]
    ph = m.director.phase_index(m.fight_t)
    k = 1
    if len(f.abilities) >= 2 and ph >= 1 and rng.chance(0.65):
        k = 2
    if len(f.abilities) >= 3 and ph >= 2 and rng.chance(0.4):
        k = 3
    group = rng.sample(f.abilities, k)
    ctx = {
        "dist": dist,
        "opp_airborne": not o.grounded,
        "opp_blocks": f.memory["opp_blocks"] / max(1, f.memory["landed"] + f.memory["opp_blocks"]),
        "opp_zoning": f.memory["opp_ranged"] / max(1, f.memory["opp_ranged"] + f.memory["opp_melee"]),
        "opp_rushdown": f.memory["opp_melee"] / max(1, f.memory["opp_ranged"] + f.memory["opp_melee"]),
        "near_wall": abs(f.x) > m.half - 1.6,
    }
    meta = {"tournament": m.meta.get("tournament"), "match": m.meta.get("match"), "fighter": f.spec["id"],
            "t": round(m.fight_t, 2), "context": {k2: (round(v, 2) if isinstance(v, float) else v) for k2, v in ctx.items()}}
    before = len(m.universe["techniques"]) if m.universe is not None else 0
    tech = compose_valid(group, rng, m.universe, context=ctx, origin="discovered", meta=meta)
    if tech is None:
        f.think_cd = 0.2
        return
    is_new = m.universe is not None and len(m.universe["techniques"]) > before
    if all(t["id"] != tech["id"] for t in f.techs):
        f.techs.append(tech)
        if is_new:
            f.stats["discoveries"] += 1
            m.event("discovery", fighter=f.side, tech=tech["id"], name=tech["name"])
            m.discoveries.append(tech["id"])
    u = tech_utility(f, o, tech, dist, m)
    if u > 0.05:
        m.start_technique(f, o, tech)


# ---------------------------------------------------------------------------
# Reactive defense
# ---------------------------------------------------------------------------
def _threats(f, o, m):
    out = []
    a = o.action
    dist = abs(o.x - f.x)
    if a.kind == "technique":
        tech = a.tech
        kind = tech["kind"]
        p = tech["params"]
        if kind in ("melee", "grab", "area") and a.phase in ("antic", "move"):
            reach = p["reach"] + (MOVEMENTS[tech["movement"]]["closes"] if a.phase == "move" else 0.0) + 0.4
            if dist <= reach:
                remaining = (a.phase_dur - a.phase_t) if a.phase == "antic" else 0.25
                out.append((("tech", a.uid, a.stage), tech["delivery"], DELIVERIES[tech["delivery"]]["height"], remaining, tech))
        if kind == "beam" and a.phase == "antic":
            out.append((("beam", a.uid), "beam", "mid", a.phase_dur - a.phase_t, tech))
        if kind == "stance":
            pass
    for pr in m.projectiles:
        if pr.owner != o.side or not pr.alive:
            continue
        rel = f.x - pr.x
        if pr.vx == 0 or rel * pr.vx <= 0:
            continue
        ttc = abs(rel) / max(1.0, abs(pr.vx))
        if 0.05 < ttc < 0.6 and abs(pr.y - (f.y + 1.0)) < 1.3:
            out.append((("proj", pr.id), "projectile", "mid", ttc, pr.tech))
    for es in m.envs:
        if es.owner == o.side and es.state == "warn" and abs(es.x - f.x) < es.radius + 0.6:
            out.append((("env", es.id), "env_strike", "low", es.delay - es.t, es.tech))
    for bl in m.blasts:
        if bl.owner == o.side and not bl.done and abs(bl.x - f.x) < bl.r + 0.5:
            out.append((("blast", bl.id), "explosion", "mid", bl.delay, bl.tech))
    return out


def react(f, o, m):
    if not (f.free or (f.action.kind == "technique" and f.action.phase == "antic" and f.action.phase_p < 0.3)):
        return
    if o.action.kind in ("broken", "grabbed"):
        return  # nothing to defend against a stunned opponent
    rng = m.rng_ai[f.side]
    tr = f.traits
    for key, delivery, height, remaining, tech in _threats(f, o, m):
        if key in f.handled:
            continue
        first = f.threat_seen.setdefault(key, m.t)
        if m.t - first < tr["reaction"] * (1.25 if f.energy < 10 else 1.0):
            continue
        f.handled.add(key)
        if remaining < 0.0:
            continue
        pattern = 1.0
        if m.cfg["combat"].get("adaptive_ai", True):
            seen = sum(1 for d in f.opp_history if d == delivery)
            pattern = min(1.35, 1.0 + 0.07 * seen * tr["adaptability"])
        p_ok = tr["read"] * m.director.defense(m.fight_t, m.fighters[0].score, m.fighters[1].score) * pattern
        if o.action.data.get("feint"):
            p_ok *= 1.1  # reacting to a feint is "successful" bait for the attacker
        if rng.random() > p_ok:
            continue
        choose_response(f, o, m, delivery, height, remaining, tech, rng)
        return


def choose_response(f, o, m, delivery, height, remaining, tech, rng):
    tr = f.traits
    opts = []
    mob = {a.get("mobility") for a in f.abilities}
    can_tp = "teleport" in mob and f.energy >= 15 and f.grounded
    counter = next((t for t in f.techs if t["delivery"] == "counter" and t["params"]["cost"] <= f.energy
                    and f.cooldowns.get(t["id"], -1) <= m.t), None)
    fast = None
    dist = abs(o.x - f.x)
    if delivery in ("punch", "kick", "summon_weapon", "barrage", "charge", "aerial_strike", "uppercut"):
        for t in sorted(f.techs, key=lambda t: (not t["abilities"], t["params"]["startup"])):
            pp = t["params"]
            if (t["kind"] == "melee" and t["movement"] == "none" and pp["startup"] < remaining - 0.02 and
                    dist <= pp["reach"] + 0.05 and pp["cost"] <= f.energy and not DELIVERIES[t["delivery"]].get("air_only")):
                fast = t
                break
    if height == "low" or delivery in ("sweep", "slam", "env_strike"):
        opts += [("jump", 1.0 + tr["evasive"]), ("backstep", 0.6 + tr["caution"] * 0.5)]
    elif delivery == "grapple":
        opts += [("backstep", 1.0), ("jump", 0.5 * tr["evasive"])]
    elif delivery in ("projectile",):
        if not (tech and tech["params"].get("pierce")):
            opts.append(("block", 0.6 + tr["caution"]))
        opts.append(("jump", 0.5 + tr["evasive"]))
    elif delivery == "beam":
        opts += [("jump", 0.9 + tr["evasive"]), ("block", 0.4 * tr["caution"])]
    elif delivery == "explosion":
        opts += [("backstep", 1.0 + tr["evasive"] * 0.5), ("jump", 0.3)]
    else:
        opts += [("block", 0.7 + tr["caution"]), ("backstep", 0.4 + tr["evasive"] * 0.9), ("roll", 0.2 + tr["evasive"] * 0.5)]
        if counter is not None:
            opts.append(("counter", 0.4 + tr["counter"] * 1.6))
        if fast is not None:
            opts.append(("interrupt", 0.2 + tr["aggression"] * 1.2))
    if can_tp:
        opts.append(("teleport", 0.3 + tr["evasive"] * 0.6))
    if abs(f.x) > m.half - 0.9:
        opts = [(n, w * (0.3 if n == "backstep" else 1.0)) for n, w in opts]
    if f.range_mode == "ranged":  # keep the distance instead of trading up close
        opts = [(n, w * (0.3 if n in ("counter", "interrupt") else 1.4 if n in ("backstep", "jump", "teleport") else 1.0)) for n, w in opts]
    resp = rng.weighted([n for n, _ in opts], [w for _, w in opts])
    if resp == "block":
        m.start_block(f, max(0.25, remaining + 0.25))
    elif resp == "jump":
        m.start_jump(f, forward=rng.chance(0.3), flip=rng.chance(0.4), evade=True)
    elif resp == "backstep":
        m.start_dodge(f, roll=False)
    elif resp == "roll":
        m.start_dodge(f, roll=True)
    elif resp == "counter":
        m.start_technique(f, o, counter)
    elif resp == "interrupt":
        m.start_technique(f, o, fast)
    elif resp == "teleport":
        m.start_teleport_evade(f, o)
    f.stats["dodges"] += resp in ("jump", "backstep", "roll", "teleport")
