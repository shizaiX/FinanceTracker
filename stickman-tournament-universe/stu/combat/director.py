"""Match director: intensity curve, choreography archetypes and pacing.

The director never chooses a winner. It shapes *when* decisive moments may
happen so that every fight meets the duration rules with meaningful combat:

* points are spaced: a point cannot follow the previous one within
  `min_gap` seconds, and a fighter's winning point can never land before
  `minimum_fight_duration_seconds`;
* a pacing controller compares the clock with the ideal time of the next point
  and modulates `lethality` (poise damage) and `defense` (read quality) for
  BOTH fighters symmetrically — exchanges get more dangerous when the fight is
  behind schedule and safer when ahead;
* phases A–D (opening, tactical, escalation, climax) unlock fusions/ultimates
  and drive aggression, camera and music intensity.
"""
from __future__ import annotations

import math

from ..core.mathutil import clamp

PHASES = ["opening", "tactical", "escalation", "climax"]

ARCHETYPES = {
    "rivalry":          dict(aggr=[0.9, 1.0, 1.15, 1.3], tempo=1.0, ranged=1.0, slowmo=1.0, camera="balanced", desc="evenly matched rivals trading momentum"),
    "chess_match":      dict(aggr=[0.7, 0.8, 1.0, 1.25], tempo=0.9, ranged=1.25, slowmo=0.9, camera="wide", desc="patient defensive duel of reads and counters"),
    "high_speed_duel":  dict(aggr=[1.15, 1.2, 1.3, 1.4], tempo=1.2, ranged=0.8, slowmo=1.1, camera="tight", desc="relentless high-speed exchanges"),
    "underdog":         dict(aggr=[0.85, 1.0, 1.2, 1.35], tempo=1.0, ranged=1.0, slowmo=1.2, camera="balanced", desc="a lower-rated fighter tries to overturn the odds"),
    "domination":       dict(aggr=[1.2, 1.2, 1.25, 1.3], tempo=1.1, ranged=0.9, slowmo=1.0, camera="tight", desc="one fighter pushes the pace from the first second"),
    "tech_vs_power":    dict(aggr=[0.9, 1.0, 1.2, 1.35], tempo=1.0, ranged=1.1, slowmo=1.1, camera="balanced", desc="precision technique against raw power"),
    "counter_clinic":   dict(aggr=[0.8, 0.9, 1.1, 1.3], tempo=0.95, ranged=0.9, slowmo=1.2, camera="tight", desc="every mistake is punished"),
    "final_thriller":   dict(aggr=[1.0, 1.1, 1.3, 1.5], tempo=1.05, ranged=1.0, slowmo=1.35, camera="cinematic", desc="the championship on a knife's edge"),
}


def choose_archetype(fa, fb, stage, rng):
    if stage == "final":
        return "final_thriller"
    pa, pb = fa["personality"], fb["personality"]
    ra, rb = fa["rating"], fb["rating"]
    weights = {k: 1.0 for k in ARCHETYPES if k != "final_thriller"}
    if {pa, pb} <= {"defensive", "strategic", "counter", "technical"}:
        weights["chess_match"] += 2.0
    if "aggressive" in (pa, pb):
        weights["domination"] += 1.2
        weights["high_speed_duel"] += 1.0
    if pa == pb == "aggressive" or {"evasive", "aggressive"} == {pa, pb}:
        weights["high_speed_duel"] += 2.0
    if "counter" in (pa, pb):
        weights["counter_clinic"] += 1.8
    if abs(ra - rb) > 0.03:
        weights["underdog"] += 1.5
    if {"technical", "aggressive"} == {pa, pb}:
        weights["tech_vs_power"] += 2.0
    if stage == "semifinal":
        weights["rivalry"] += 1.5
    keys = sorted(weights)
    return rng.weighted(keys, [weights[k] for k in keys])


class Director:
    def __init__(self, cfg, archetype, rng):
        t = cfg["tournament"]
        self.min_d = float(t["minimum_fight_duration_seconds"])
        self.target = float(t["target_fight_duration_seconds"])
        self.max_d = float(t["maximum_fight_duration_seconds"])
        self.ptw = int(t["points_to_win"])
        self.archetype = archetype
        self.arch = ARCHETYPES[archetype]
        self.rng = rng
        # Small per-match variation so pacing differs between matches.
        self.target_j = clamp(self.target * rng.uniform(0.92, 1.12), self.min_d + 4, self.max_d - 10)
        self.min_gap = 7.5
        self.last_point = 0.0
        self.fight_t = 0.0

    # ---- clocks ---------------------------------------------------------
    def phase_index(self, ft):
        f = ft / self.target_j
        return 0 if f < 0.16 else 1 if f < 0.48 else 2 if f < 0.8 else 3

    def phase(self, ft):
        return PHASES[self.phase_index(ft)]

    def expected_remaining(self, sa, sb):
        mn = self.ptw - max(sa, sb)
        mx = (self.ptw - sa) + (self.ptw - sb) - 1
        return max(1.0, (mn + mx) / 2.0)

    def desired_next(self, ft, sa, sb):
        last = self.last_point
        rem = self.expected_remaining(sa, sb)
        d = last + max(self.min_gap + 2.0, (self.target_j - last) / rem)
        if max(sa, sb) == self.ptw - 1:
            d = max(d, self.min_d + 3.0)
        return d

    # ---- modulation ---------------------------------------------------------
    def lethality(self, ft, sa, sb):
        d = self.desired_next(ft, sa, sb)
        x = (ft - d) / 9.0
        L = clamp(math.exp(x * 0.9), 0.4, 3.2)
        if ft > self.max_d - 14:
            L *= 2.5
        return L * [0.85, 1.0, 1.08, 1.15][self.phase_index(ft)]

    def defense(self, ft, sa, sb):
        d = self.desired_next(ft, sa, sb)
        x = (ft - d) / 10.0
        v = clamp(1.12 - 0.22 * x, 0.55, 1.25)
        if ft > self.max_d - 14:
            v *= 0.5
        return v

    def aggression(self, ft):
        return self.arch["aggr"][self.phase_index(ft)]

    def can_score(self, ft, attacker_score):
        if ft - self.last_point < self.min_gap:
            return False
        if attacker_score >= self.ptw - 1 and ft < self.min_d + 0.5:
            return False
        return True

    def sudden_death(self, ft):
        return ft >= self.max_d - 4

    def intensity(self, ft):
        return clamp(0.3 + 0.7 * ft / self.target_j, 0.3, 1.0)
