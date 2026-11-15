"""2D VFX engine (pycairo).

Particles are *analytic*: every particle is fully described by its spawn event
(seeded RNG), so its position at any time is a closed-form function. Any frame
can be rendered independently -> parallel chunk rendering + exact resumes.
Every emitter is tied to a simulation event, so no effect appears without cause.
"""
from __future__ import annotations

import bisect
import math
import random

import cairo

from ..core.mathutil import clamp, hex_to_rgb, mix

WHITE = (1.0, 1.0, 1.0)


def rgb(c):
    return hex_to_rgb(c) if isinstance(c, str) else c


class Particle:
    __slots__ = ("t0", "x", "y", "vx", "vy", "drag", "g", "life", "size", "grow", "color", "style", "spin", "seed", "ground")

    def pos(self, age):
        k = self.drag
        if k > 1e-4:
            e = math.exp(-k * age)
            vtx, vty = 0.0, self.g / k
            x = self.x + vtx * age + (self.vx - vtx) * (1 - e) / k
            y = self.y + vty * age + (self.vy - vty) * (1 - e) / k
        else:
            x = self.x + self.vx * age
            y = self.y + self.vy * age + 0.5 * self.g * age * age
        if self.ground and y < 0.03:
            y = 0.03
        return x, y


STYLE_PHYS = {
    # style: drag, gravity, life, size
    "flame":   (2.5, 3.0, 0.45, 0.10),
    "ember":   (1.2, 1.5, 0.9, 0.035),
    "droplet": (0.6, -14.0, 0.6, 0.05),
    "shard":   (1.0, -9.0, 0.55, 0.07),
    "spark":   (3.5, -2.0, 0.28, 0.03),
    "rock":    (0.4, -18.0, 0.8, 0.07),
    "gust":    (2.0, 0.0, 0.35, 0.16),
    "metal":   (1.5, -12.0, 0.45, 0.05),
    "leaf":    (2.0, -2.5, 0.8, 0.06),
    "ray":     (3.0, 0.0, 0.3, 0.04),
    "wisp":    (1.8, 1.2, 0.7, 0.09),
    "ring":    (0.0, 0.0, 0.35, 0.3),
    "wave":    (0.0, 0.0, 0.4, 0.3),
    "smoke":   (2.2, 0.8, 1.1, 0.22),
    "dust":    (3.0, 0.3, 0.6, 0.14),
    "orb":     (2.5, 0.0, 0.4, 0.06),
    "frost":   (1.5, -1.0, 0.6, 0.05),
}


class EffectSystem:
    """Builds particles from timeline events and draws them at any sim time."""

    def __init__(self, events, abilities, quality=1.0):
        self.abilities = abilities
        self.parts = []
        self.rings = []      # (t0, x, y, r_end, life, color, width)
        self.flashes = []    # (t0, x, y, r, life, color)
        self.decals = []     # (t0, x, kind, life, seed, color)
        self.bolts = []      # (t0, x0, y0, x1, y1, life, colors, seed)
        self.texts = []
        self.screen_flash = []  # (t0, life, color, strength)
        q = quality
        for i, e in enumerate(events):
            self._emit(i, e, q)
        self.parts.sort(key=lambda p: p.t0)
        self.pt0 = [p.t0 for p in self.parts]
        self.max_life = max([p.life for p in self.parts] + [1.0])

    # -- helpers ---------------------------------------------------------------
    def ab_colors(self, ab_ids):
        cols = [self.abilities[a]["colors"] for a in ab_ids if a in self.abilities]
        return [[rgb(c) for c in cs] for cs in cols] or [[WHITE, (1, 0.92, 0.7), (1, 0.7, 0.3)]]

    def ab_style(self, ab_ids, i=0):
        ab = [self.abilities[a] for a in ab_ids if a in self.abilities]
        if not ab:
            return "spark"
        return ab[i % len(ab)]["particle"]

    def _p(self, rng, t0, x, y, ang, spd, style, color, life=None, size=None, ground=True, spread_life=0.35):
        drag, g, lf, sz = STYLE_PHYS.get(style, STYLE_PHYS["spark"])
        p = Particle()
        p.t0, p.x, p.y = t0, x, y
        p.vx, p.vy = math.cos(ang) * spd, math.sin(ang) * spd
        p.drag, p.g = drag, g
        p.life = (life or lf) * rng.uniform(1 - spread_life, 1 + spread_life)
        p.size = (size or sz) * rng.uniform(0.7, 1.3)
        p.grow = 1.0 if style not in ("smoke", "dust", "gust", "wisp") else 2.2
        p.color = color
        p.style = style
        p.spin = rng.uniform(-12, 12)
        p.seed = rng.randrange(1 << 30)
        p.ground = ground
        self.parts.append(p)

    def burst(self, rng, t0, x, y, n, ab_ids, spd=(3, 7), styles=None, ang=(0, 2 * math.pi), life=None, size=None):
        cols = self.ab_colors(ab_ids)
        for k in range(n):
            cs = cols[k % len(cols)]
            st = styles[k % len(styles)] if styles else self.ab_style(ab_ids, k)
            self._p(rng, t0, x, y, rng.uniform(*ang), rng.uniform(*spd), st, rng.choice(cs), life, size)

    # -- event -> emitters -----------------------------------------------------
    def _emit(self, i, e, q):
        ty = e["type"]
        rng = random.Random(i * 7919 + 17)
        t = e["t"]
        x, y = e.get("x", 0.0), e.get("y", 1.0)
        ab = e.get("abilities") or []
        cols = self.ab_colors(ab)
        main = cols[0]
        n = lambda v: max(1, int(v * q))
        if ty == "hit":
            lvl = e.get("level")
            if lvl == "minor":
                self.burst(rng, t, x, y, n(8), ab, (3, 6), styles=["spark"])
                self.flashes.append((t, x, y, 0.32, 0.07, WHITE))
            else:
                big = lvl == "significant"
                self.burst(rng, t, x, y, n(14 if big else 10), ab, (4, 9), styles=["spark"])
                if ab:
                    self.burst(rng, t, x, y, n(14 if big else 8), ab, (2, 6))
                self.flashes.append((t, x, y, 0.55 if big else 0.4, 0.09, WHITE))
                self.rings.append((t, x, y, 1.1 if big else 0.7, 0.25, main[1], 0.06))
        elif ty in ("score", "ko"):
            ko = ty == "ko"
            self.burst(rng, t, x, y, n(40 if ko else 28), ab, (5, 13), styles=["spark"])
            self.burst(rng, t, x, y, n(30 if ko else 20), ab, (2, 8))
            self.burst(rng, t, x, y, n(10), [], (1, 3), styles=["smoke"], life=1.2)
            self.flashes.append((t, x, y, 1.2, 0.16, WHITE))
            self.rings.append((t, x, y, 2.6, 0.4, main[1], 0.1))
            self.rings.append((t + 0.06, x, y, 1.6, 0.35, WHITE, 0.05))
            self.screen_flash.append((t, 0.22 if ko else 0.14, WHITE, 0.85 if ko else 0.6))
        elif ty == "block":
            self.burst(rng, t, x, y, n(10), [], (2.5, 5), styles=["spark"], ang=(math.pi * 0.3, math.pi * 1.7))
            self.rings.append((t, x, y, 0.45, 0.15, (0.7, 0.9, 1.0), 0.04))
        elif ty in ("shield_block", "guard_crush"):
            self.burst(rng, t, x, y, n(12), ab, (2, 5))
            self.rings.append((t, x, y, 0.9, 0.25, main[1], 0.05))
        elif ty == "guard_break":
            self.burst(rng, t, x, y, n(18), [], (3, 8), styles=["shard"], life=0.7)
            self.rings.append((t, x, y, 1.3, 0.3, WHITE, 0.06))
            self.flashes.append((t, x, y, 0.8, 0.1, WHITE))
        elif ty == "explode":
            r = e.get("r", 1.5)
            low = e.get("low")
            self.burst(rng, t, x, y, n(26 + 10 * r), ab, (2, 6 + 2 * r), ang=(0, math.pi) if low else (0, 2 * math.pi))
            self.burst(rng, t, x, y, n(8), [], (1, 2.5), styles=["smoke"], life=1.0, size=0.3)
            self.rings.append((t, x, y, r * 1.1, 0.32, main[1], 0.09))
            self.flashes.append((t, x, y, r * 0.8, 0.12, main[0]))
        elif ty == "slam":
            r = e.get("r", 1.5)
            self.burst(rng, t, x, 0.1, n(16), [], (2, 7), styles=["rock"], ang=(0.3, math.pi - 0.3))
            self.burst(rng, t, x, 0.1, n(12), [], (1.5, 4), styles=["dust"], ang=(0.1, math.pi - 0.1))
            self.decals.append((t, x, "crack", 3.0, rng.randrange(1 << 20), main[1]))
            self.rings.append((t, x, 0.05, r * 1.3, 0.3, main[1], 0.07))
        elif ty in ("land",) and e.get("heavy"):
            self.burst(rng, t, x, 0.05, n(10), [], (1.5, 4), styles=["dust"], ang=(0.05, math.pi - 0.05))
        elif ty == "intro_land":
            self.burst(rng, t, x, 0.05, n(22), [], (2, 7), styles=["dust"], ang=(0.05, math.pi - 0.05))
            self.burst(rng, t, x, 0.4, n(24), ab, (2, 8), ang=(0.1, math.pi - 0.1))
            self.rings.append((t, x, 0.05, 2.4, 0.4, main[1], 0.08))
            self.decals.append((t, x, "crack", 2.5, rng.randrange(1 << 20), main[1]))
        elif ty == "step":
            if e.get("speed", 0) > 4:
                self.burst(rng, t, x, 0.03, n(2), [], (0.5, 1.5), styles=["dust"], ang=(0.3, math.pi - 0.3), size=0.08)
        elif ty in ("dash", "wall_jump"):
            self.burst(rng, t, x, 0.05, n(6), [], (1, 3), styles=["dust"], ang=(0.2, math.pi - 0.2), size=0.12)
            if ab:
                self.burst(rng, t, x, 0.9, n(8), ab, (1, 3))
        elif ty in ("teleport_out", "teleport_in"):
            self.burst(rng, t, x, y, n(22), ab, (1.5, 6))
            self.flashes.append((t, x, y, 0.9, 0.12, main[0]))
            self.bolts.append((t, x, 0.0, x, 2.4, 0.12, main, rng.randrange(1 << 20)))
        elif ty == "projectile":
            self.flashes.append((t, x, y, 0.45, 0.08, main[0]))
            self.burst(rng, t, x, y, n(6), ab, (1.5, 4))
        elif ty == "impact":
            self.burst(rng, t, x, y, n(10 if not e.get("fizzle") else 6), ab, (2, 5))
            self.flashes.append((t, x, y, 0.35, 0.07, main[0]))
        elif ty == "clash":
            self.burst(rng, t, x, y, n(24), ab, (3, 9))
            self.burst(rng, t, x, y, n(12), [], (4, 9), styles=["spark"])
            self.rings.append((t, x, y, 1.2, 0.3, WHITE, 0.07))
            self.flashes.append((t, x, y, 0.8, 0.1, WHITE))
        elif ty == "beam_clash":
            self.burst(rng, t, x, y, n(10), ab, (3, 8))
            self.flashes.append((t, x, y, 0.6, 0.12, WHITE))
        elif ty == "beam_end":
            self.burst(rng, t, x, y, n(8), ab, (1, 3))
        elif ty == "env_erupt":
            form = e.get("form", "pillar")
            st = {"pillar": "rock", "spikes": "shard", "geyser": None, "sky_strike": "spark", "vines": "leaf",
                  "hands": "wisp", "light_pillar": "ray", "well": "ring", "column": "gust", "burst": "wave"}.get(form)
            self.burst(rng, t, x, 0.1, n(18), ab, (2, 8), styles=[st] if st else None, ang=(0.3, math.pi - 0.3))
            self.burst(rng, t, x, 0.05, n(8), [], (1, 3), styles=["dust"], ang=(0.1, math.pi - 0.1))
            if form == "sky_strike":
                self.bolts.append((t, x, 9.0, x, 0.0, 0.2, main, rng.randrange(1 << 20)))
                self.screen_flash.append((t, 0.08, main[0], 0.35))
            self.decals.append((t, x, "scorch" if form in ("geyser", "sky_strike", "light_pillar") else "crack", 2.5, rng.randrange(1 << 20), main[1]))
        elif ty == "reaction":
            kind = e.get("kind")
            if kind == "steam":
                self.burst(rng, t, x, 0.4, n(18), [], (1, 3), styles=["smoke"], life=1.4, size=0.3)
            elif kind == "conduct":
                self.burst(rng, t, x, 0.2, n(18), ab, (3, 8), styles=["spark"])
                for k in range(3):
                    self.bolts.append((t + 0.05 * k, x - 0.8 + 0.8 * k, 0.05, x - 0.3 + 0.6 * k, 1.2, 0.12, main, rng.randrange(1 << 20)))
            elif kind == "freeze":
                self.burst(rng, t, x, 0.2, n(14), [], (1, 4), styles=["shard"])
            elif kind == "wildfire":
                self.burst(rng, t, x, 0.2, n(18), [], (1, 3), styles=["flame"])
        elif ty == "burst":
            self.burst(rng, t, x, y, n(30), ab, (3, 9))
            self.rings.append((t, x, y, 2.0, 0.3, main[1], 0.09))
        elif ty == "counter":
            self.flashes.append((t, x, y, 0.7, 0.1, WHITE))
            self.rings.append((t, x, y, 0.9, 0.2, (1, 0.95, 0.6), 0.05))
        elif ty in ("reflect", "absorb"):
            self.burst(rng, t, x, y, n(14), ab, (2, 6))
            self.rings.append((t, x, y, 0.8, 0.22, main[1], 0.05))
        elif ty == "wall_hit":
            self.burst(rng, t, x, y, n(12), [], (1, 4), styles=["dust", "rock"])
        elif ty == "split":
            self.flashes.append((t, x, y, 0.35, 0.06, main[0]))
        elif ty == "throw":
            self.burst(rng, t, x, y, n(8), [], (1, 3), styles=["dust"])
        elif ty == "cast" and e.get("tier") in ("fusion", "ultimate"):
            hx = x
            self.screen_flash.append((t, 0.05, main[1], 0.12 if e.get("tier") == "ultimate" else 0.0))

    # -- drawing ---------------------------------------------------------------
    def active_particles(self, s):
        i0 = bisect.bisect_left(self.pt0, s - self.max_life)
        i1 = bisect.bisect_right(self.pt0, s)
        for p in self.parts[i0:i1]:
            age = s - p.t0
            if 0 <= age < p.life:
                yield p, age

    def draw_back(self, cr, s):
        for (t0, x, kind, life, seed, col) in self.decals:
            age = s - t0
            if age < 0 or age > life:
                continue
            a = clamp(1 - age / life, 0, 1) * 0.8
            draw_decal(cr, x, kind, seed, col, a)

    def draw(self, cr, s):
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        for p, age in self.active_particles(s):
            u = age / p.life
            x, y = p.pos(age)
            draw_particle(cr, p, x, y, u, age)
        for (t0, x, y, r, life, col, w) in self.rings:
            age = s - t0
            if 0 <= age < life:
                u = age / life
                rr = r * (1 - (1 - u) ** 3)
                cr.set_source_rgba(*col, (1 - u) ** 1.5 * 0.9)
                cr.set_line_width(w * (1.4 - u))
                cr.arc(x, y, max(0.01, rr), 0, 2 * math.pi)
                cr.stroke()
        for (t0, x, y, r, life, col) in self.flashes:
            age = s - t0
            if 0 <= age < life:
                u = age / life
                g = cairo.RadialGradient(x, y, 0, x, y, r * (0.6 + 0.6 * u))
                g.add_color_stop_rgba(0, 1, 1, 1, (1 - u))
                g.add_color_stop_rgba(0.35, *col, 0.7 * (1 - u))
                g.add_color_stop_rgba(1, *col, 0)
                cr.set_source(g)
                cr.arc(x, y, r * (0.6 + 0.6 * u), 0, 2 * math.pi)
                cr.fill()
        for (t0, x0, y0, x1, y1, life, cols, seed) in self.bolts:
            age = s - t0
            if 0 <= age < life:
                u = age / life
                draw_bolt(cr, x0, y0, x1, y1, cols, seed + int(age * 60), 1 - u, 0.06)

    def screen_flash_alpha(self, s):
        best = None
        for (t0, life, col, st) in self.screen_flash:
            age = s - t0
            if 0 <= age < life and st > 0:
                a = st * (1 - age / life)
                if best is None or a > best[1]:
                    best = (col, a)
        return best


def draw_particle(cr, p, x, y, u, age):
    col = p.color
    st = p.style
    fade = (1 - u)
    size = p.size * (1 + (p.grow - 1) * u)
    if st in ("flame", "ember"):
        c = mix(col, (1, 1, 0.8), 0.5 * fade)
        cr.set_source_rgba(*c, 0.85 * fade)
        cr.arc(x, y, size * (1.2 - 0.6 * u), 0, 2 * math.pi)
        cr.fill()
    elif st in ("spark", "ray", "metal"):
        vx, vy = p.vx * math.exp(-p.drag * age), p.vy * math.exp(-p.drag * age) + p.g * age
        L = 0.02 + 0.03 * math.hypot(vx, vy) * (0.5 if st == "metal" else 1.0)
        n = math.hypot(vx, vy) or 1
        cr.set_source_rgba(*mix(col, (1, 1, 1), 0.4), fade)
        cr.set_line_width(size)
        cr.move_to(x, y)
        cr.line_to(x - vx / n * L, y - vy / n * L)
        cr.stroke()
    elif st in ("droplet", "orb", "frost"):
        cr.set_source_rgba(*col, 0.9 * fade)
        cr.arc(x, y, size, 0, 2 * math.pi)
        cr.fill()
    elif st == "shard":
        a = p.spin * age
        cr.save()
        cr.translate(x, y)
        cr.rotate(a)
        cr.move_to(0, size * 1.6)
        cr.line_to(size * 0.6, 0)
        cr.line_to(0, -size * 1.6)
        cr.line_to(-size * 0.6, 0)
        cr.close_path()
        cr.set_source_rgba(*mix(col, (1, 1, 1), 0.3), 0.95 * fade)
        cr.fill()
        cr.restore()
    elif st == "rock":
        a = p.spin * age
        cr.save()
        cr.translate(x, y)
        cr.rotate(a)
        r = random.Random(p.seed)
        pts = [(math.cos(k / 5 * 2 * math.pi) * size * r.uniform(0.6, 1.2), math.sin(k / 5 * 2 * math.pi) * size * r.uniform(0.6, 1.2)) for k in range(5)]
        cr.move_to(*pts[0])
        for q in pts[1:]:
            cr.line_to(*q)
        cr.close_path()
        cr.set_source_rgba(*mix(col, (0.2, 0.15, 0.1), 0.35), min(1.0, 1.6 * fade))
        cr.fill()
        cr.restore()
    elif st == "leaf":
        a = p.spin * age * 0.5
        cr.save()
        cr.translate(x, y)
        cr.rotate(a)
        cr.scale(1, 0.45)
        cr.arc(0, 0, size, 0, 2 * math.pi)
        cr.restore()
        cr.set_source_rgba(*col, fade)
        cr.fill()
    elif st in ("gust",):
        cr.set_source_rgba(*mix(col, (1, 1, 1), 0.4), 0.5 * fade)
        cr.set_line_width(0.025)
        cr.arc(x, y, size, p.spin, p.spin + 2.2)
        cr.stroke()
    elif st in ("smoke", "dust"):
        base = (0.55, 0.52, 0.5) if st == "smoke" else (0.62, 0.55, 0.45)
        cr.set_source_rgba(*mix(base, col, 0.15), 0.35 * fade)
        cr.arc(x, y, size, 0, 2 * math.pi)
        cr.fill()
    elif st == "wisp":
        cr.set_source_rgba(*col, 0.55 * fade)
        cr.arc(x, y, size * (1 - 0.3 * u), 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(0.05, 0.0, 0.1, 0.5 * fade)
        cr.arc(x, y, size * 0.45, 0, 2 * math.pi)
        cr.fill()
    elif st in ("ring", "wave"):
        cr.set_source_rgba(*col, 0.6 * fade)
        cr.set_line_width(0.025)
        cr.arc(x, y, size * (0.3 + u), 0, 2 * math.pi)
        cr.stroke()
    else:
        cr.set_source_rgba(*col, fade)
        cr.arc(x, y, size, 0, 2 * math.pi)
        cr.fill()


def bolt_points(x0, y0, x1, y1, seed, segs=9, jag=0.18):
    r = random.Random(seed)
    pts = [(x0, y0)]
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1
    nx, ny = -dy / L, dx / L
    for k in range(1, segs):
        t = k / segs
        off = r.uniform(-1, 1) * jag * min(1.0, L / 1.5) * (1 - abs(0.5 - t))
        pts.append((x0 + dx * t + nx * off, y0 + dy * t + ny * off))
    pts.append((x1, y1))
    return pts


def draw_bolt(cr, x0, y0, x1, y1, cols, seed, alpha, width):
    segs = max(4, int(math.hypot(x1 - x0, y1 - y0) / 0.25))
    pts = bolt_points(x0, y0, x1, y1, seed, segs)
    for w, c, a in ((width * 4, cols[2], 0.25), (width * 1.8, cols[1], 0.6), (width * 0.7, cols[0], 1.0)):
        cr.set_line_width(w)
        cr.set_source_rgba(*c, a * alpha)
        cr.move_to(*pts[0])
        for q in pts[1:]:
            cr.line_to(*q)
        cr.stroke()


def draw_decal(cr, x, kind, seed, col, a):
    r = random.Random(seed)
    if kind == "crack":
        cr.set_source_rgba(0.02, 0.02, 0.03, a)
        cr.set_line_width(0.035)
        for k in range(5):
            cr.move_to(x, 0.0)
            px = x
            d = r.choice((-1, 1))
            for j in range(4):
                px += d * r.uniform(0.12, 0.35)
                cr.line_to(px, -0.02 * j)
            cr.stroke()
        cr.set_source_rgba(*col, a * 0.35)
        cr.set_line_width(0.015)
        cr.move_to(x - 0.6, 0.0)
        cr.line_to(x + 0.6, 0.0)
        cr.stroke()
    else:
        g = cairo.RadialGradient(x, 0, 0, x, 0, 0.9)
        g.add_color_stop_rgba(0, 0.05, 0.03, 0.02, a * 0.8)
        g.add_color_stop_rgba(1, 0.05, 0.03, 0.02, 0)
        cr.save()
        cr.translate(x, 0)
        cr.scale(1, 0.15)
        cr.translate(-x, 0)
        cr.set_source(g)
        cr.arc(x, 0, 0.9, 0, 2 * math.pi)
        cr.fill()
        cr.restore()
