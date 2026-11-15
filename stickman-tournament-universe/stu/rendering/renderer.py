"""Frame renderer: composes arena, environment, fighters, projectiles, beams,
VFX, camera and HUD for one video frame. Pure function of (timeline, frame
index) -> image, which allows parallel, resumable chunk rendering.
"""
from __future__ import annotations

import bisect
import math
import random

import cairo

from ..animation.rig import HEAD_R, J
from ..core.mathutil import clamp, hex_to_rgb, lerp, mix, smoothstep
from ..core.rng import stable_noise
from .arena_art import ArenaArt
from .hud import Hud
from ..themes.packs import WEAPONS, weapon_class
from . import costume as COS
from .vfx import EffectSystem, bolt_points, draw_bolt
from .weapons import draw_energy_blade, draw_weapon, weapon_tip

HALF = 7.2
PHYSICAL_PROJ = {"bullet", "cannonball", "bomb", "bottle", "knife", "shuriken", "harpoon", "arrow"}


def rgbs(cols):
    return [hex_to_rgb(c) for c in cols]


class SceneRenderer:
    def __init__(self, ctx):
        self.ctx = ctx
        cfg = ctx["cfg"]
        self.W = cfg["video"]["width"]
        self.H = cfg["video"]["height"]
        self.res = ctx["result"]
        self.frames = self.res["frames"]
        self.dt = self.res["dt"]
        self.events = self.res["events"]
        self.ev_t = [e["t"] for e in self.events]
        self.abilities = ctx["abilities"]
        self.fighters = ctx["fighters"]
        self.fcol = [hex_to_rgb(f["color"]) for f in self.fighters]
        self.fsec = [hex_to_rgb(f["secondary"]) for f in self.fighters]
        self.vframes = ctx["vframes"]
        self.cams = ctx["camera"]
        self.arena = ctx["arena"]
        self.ptw = cfg["tournament"]["points_to_win"]
        q = 1.0 if cfg["creative"].get("visual_effects") == "high_quality" else 0.6
        if not cfg["creative"].get("particle_effects", True):
            q = 0.25
        self.fx = EffectSystem(self.events, self.abilities, q)
        self.blur = cfg["creative"].get("motion_blur", "subtle") not in ("off", False, None)
        self.hud = Hud(self.W, self.H, self.fighters, ctx.get("info", {}), self.ptw)
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.W, self.H)
        self._build_static()
        self.ko = next((e for e in self.events if e["type"] == "ko"), None)
        self.callouts = self._layout_callouts()
        self.attack_labels, self.discoveries = self._layout_labels()

    def _layout_labels(self):
        names = {e.get("tech"): e["name"] for e in self.events if e["type"] in ("callout", "discovery") and e.get("name")}
        labels = [[], []]
        for e in self.events:
            if e["type"] == "technique" and not e.get("feint"):
                name = e.get("name") or names.get(e.get("tech"))
                if not name:
                    continue
                ab = e.get("abilities") or []
                col = mix(rgbs(self.abilities[ab[0]]["colors"])[1], (1, 1, 1), 0.25) if ab and ab[0] in self.abilities else (0.92, 0.92, 0.95)
                labels[e["fighter"]].append({"t": e["t"], "name": name, "color": col, "tier": e.get("tier"), "dur": 1.8})
        disc = []
        for e in self.events:
            if e["type"] == "discovery":
                side = e.get("fighter", 0)
                slot = sum(1 for d in disc if e["t"] - d["t"] < d["dur"])
                disc.append({"t": e["t"], "name": e["name"], "owner": self.fighters[side]["name"],
                             "color": mix(self.fcol[side], (1, 1, 1), 0.15), "dur": 2.4, "slot": min(slot, 1)})
        return labels, disc

    def _layout_callouts(self, dur=1.25, slots=2):
        items = []
        for e in self.events:
            if e["type"] == "callout":
                cols = rgbs(self.abilities[e["abilities"][0]]["colors"]) if e.get("abilities") and e["abilities"][0] in self.abilities else [(1, 1, 1)] * 3
                new = any(d["type"] == "discovery" and abs(d["t"] - e["t"]) < 1.0 and d.get("tech") == e.get("tech") for d in self.events)
                items.append({"t": e["t"], "name": e["name"], "color": mix(cols[1], (1, 1, 1), 0.2), "new": new, "tier": e.get("tier"),
                              "owner": self.fighters[e["fighter"]]["name"] if "fighter" in e else None})
            elif e["type"] == "discovery" and not any(c["type"] == "callout" and c.get("tech") == e.get("tech") and abs(c["t"] - e["t"]) < 1.0
                                                     for c in self.events):
                items.append({"t": e["t"], "name": e["name"], "color": (1, 0.92, 0.6), "new": True, "tier": None,
                              "owner": self.fighters[e["fighter"]]["name"] if "fighter" in e else None})
        items.sort(key=lambda c: c["t"])
        busy = [None] * slots
        for c in items:
            c["dur"] = dur
            free = [i for i in range(slots) if busy[i] is None or busy[i]["t"] + busy[i]["dur"] <= c["t"]]
            if free:
                c["slot"] = free[0]
            else:  # all slots taken: the oldest callout ends now and yields its slot
                i = min(range(slots), key=lambda k: busy[k]["t"])
                busy[i]["dur"] = max(0.15, c["t"] - busy[i]["t"])
                c["slot"] = i
            busy[c["slot"]] = c
        return items

    # ------------------------------------------------------------- static art
    def _build_static(self):
        W, H = self.W, self.H
        self.art = ArenaArt(self.arena, W, H)
        self.vignette = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        cr = cairo.Context(self.vignette)
        g = cairo.RadialGradient(W / 2, H * 0.48, W * 0.35, W / 2, H * 0.48, H * 0.75)
        g.add_color_stop_rgba(0, 0, 0, 0, 0)
        g.add_color_stop_rgba(1, 0, 0, 0, 0.62)
        cr.set_source(g)
        cr.paint()

    def draw_background(self, cr, cam, s):
        self.art.draw_background(cr, cam, s)

    def draw_ground(self, cr, cam, s=0.0):
        self.art.draw_ground(cr, cam, s)

    # ------------------------------------------------------------ sampling
    def _idx(self, s):
        i = clamp(s / self.dt - 1.0, 0.0, len(self.frames) - 1.000001)
        return int(i), i - int(i)

    def fighter_at(self, s, side):
        i0, f = self._idx(s)
        a = self.frames[i0]["f"][side]
        b = self.frames[min(i0 + 1, len(self.frames) - 1)]["f"][side]
        if b[5] & 128 or a[5] & 64 or b[5] & 64:
            f = 0.0 if f < 0.5 else 1.0
        if f <= 0.0:
            return a
        if f >= 1.0:
            return b
        ja = a[3]
        jb = b[3]
        joints = [ja[k] + (jb[k] - ja[k]) * f for k in range(len(ja))]
        return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2], joints) + tuple(a[4:])

    def frame_at(self, s):
        i0, f = self._idx(s)
        return self.frames[i0], self.frames[min(i0 + 1, len(self.frames) - 1)], f

    # ------------------------------------------------------------ fighters
    def _pts(self, joints):
        return [(joints[2 * k], joints[2 * k + 1]) for k in range(11)]

    def _stroke_body(self, cr, P, col, back_col, width, alpha, head_fill=True):
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        chains_back = [[P[J["hip"]], P[J["knee_b"]], P[J["foot_b"]]], [P[J["chest"]], P[J["elbow_b"]], P[J["hand_b"]]]]
        hx, hy = P[J["head"]]
        cx, cy = P[J["chest"]]
        dx, dy = hx - cx, hy - cy
        n = math.hypot(dx, dy) or 1
        neck = (hx - dx / n * HEAD_R, hy - dy / n * HEAD_R)
        chains_front = [[P[J["hip"]], P[J["chest"]], neck], [P[J["hip"]], P[J["knee_f"]], P[J["foot_f"]]],
                        [P[J["chest"]], P[J["elbow_f"]], P[J["hand_f"]]]]
        cr.set_line_width(width)
        for chains, c in ((chains_back, back_col), (chains_front, col)):
            cr.set_source_rgba(*c, alpha)
            for ch in chains:
                cr.move_to(*ch[0])
                for q in ch[1:]:
                    cr.line_to(*q)
                cr.stroke()
        cr.arc(hx, hy, HEAD_R + (width - 0.075) * 0.5, 0, 2 * math.pi)
        cr.set_source_rgba(*col, alpha)
        cr.fill() if head_fill else cr.stroke()

    def draw_fighter(self, cr, side, s, fd, cam):
        x, y, facing, joints, kind, flags, aura, weapon, tech_ab, phase, vx = fd[:11]
        limb = fd[11] if len(fd) > 11 else ""
        if flags & 64:
            return
        P = self._pts(joints)
        col = self.fcol[side]
        sec = self.fsec[side]
        spec = self.fighters[side]
        flash = flags & 8
        # afterimages
        fast = abs(vx) > 6.0 or kind == "dash"
        if self.blur and fast:
            for k, a in ((1, 0.22), (2, 0.13), (3, 0.07)):
                g = self.fighter_at(s - 0.028 * k, side)
                if g[5] & 64:
                    continue
                self._stroke_body(cr, self._pts(g[3]), col, col, 0.07, a)
        # shadow
        sh = clamp(1 - y / 4.0, 0.2, 1)
        cr.save()
        cr.translate(x, 0.01)
        cr.scale(1, 0.12)
        g = cairo.RadialGradient(0, 0, 0, 0, 0, 0.6)
        g.add_color_stop_rgba(0, 0, 0, 0, 0.55 * sh)
        g.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.set_source(g)
        cr.arc(0, 0, 0.6, 0, 2 * math.pi)
        cr.fill()
        cr.restore()
        # aura
        ab_cols = [rgbs(self.abilities[a]["colors"]) for a in (tech_ab or spec["abilities"]) if a in self.abilities]
        if aura > 0.04 and ab_cols:
            ac = ab_cols[0]
            pulse = 0.85 + 0.15 * math.sin(s * 18)
            self._stroke_body(cr, P, ac[2], ac[2], 0.5, 0.13 * aura * pulse)
            self._stroke_body(cr, P, ac[1], ac[1], 0.28, 0.18 * aura * pulse)
            for k in range(10):
                ph = (s * 1.4 + k / 10.0) % 1.0
                bx = x + 0.35 * math.sin(k * 2.4 + s * 3)
                by = y + 0.2 + ph * 2.0
                c = ab_cols[k % len(ab_cols)][1]
                cr.set_source_rgba(*c, (1 - ph) * 0.7 * aura)
                cr.arc(bx, by, 0.05 * (1 - ph) + 0.015, 0, 2 * math.pi)
                cr.fill()
        # weapon / limb smears (subtle motion blur on strikes)
        if self.blur and kind == "technique" and phase == "active":
            for jn in ("hand_f", "foot_f", "foot_b", "hand_b"):
                pts = []
                for k in range(6):
                    g = self.fighter_at(s - 0.012 * k, side)
                    pts.append((g[3][2 * J[jn]], g[3][2 * J[jn] + 1]))
                L = sum(math.hypot(pts[k][0] - pts[k + 1][0], pts[k][1] - pts[k + 1][1]) for k in range(5))
                if L > 0.35:
                    c = ab_cols[0][1] if ab_cols and tech_ab else (1, 1, 1)
                    for k in range(5):
                        cr.set_source_rgba(*c, 0.32 * (1 - k / 5))
                        cr.set_line_width(0.09 * (1 - k / 6))
                        cr.move_to(*pts[k])
                        cr.line_to(*pts[k + 1])
                        cr.stroke()
        back = mix(col, (0.05, 0.05, 0.08), 0.38)
        parts = spec.get("costume") or [spec.get("accessory", "headband")]

        def hist(jn, k):
            g = self.fighter_at(s - 0.02 * k, side)
            return g[3][2 * J[jn]], g[3][2 * J[jn] + 1]
        front_w, back_w, energy = weapon if isinstance(weapon, (tuple, list)) and len(weapon) == 3 else (None, None, None)
        glow = ab_cols[0][1] if (tech_ab and ab_cols and kind == "technique" and phase in ("antic", "active")) else None
        COS.draw_back(cr, parts, P, facing, s, col, sec, hist)
        if back_w:
            draw_weapon(cr, back_w, P[J["hand_b"]], P[J["elbow_b"]], facing, None, s)
        # glow + outline + core
        self._stroke_body(cr, P, col, col, 0.24, 0.13)
        self._stroke_body(cr, P, (0.02, 0.02, 0.04), (0.02, 0.02, 0.04), 0.115, 0.85)
        core = (1, 1, 1) if flash else mix(col, (1, 1, 1), 0.12)
        self._stroke_body(cr, P, core, (1, 1, 1) if flash else back, 0.075, 1.0)
        COS.draw_limb_overrides(cr, parts, P, facing, col)
        # eye
        hx, hy = P[J["head"]]
        cx, cy = P[J["chest"]]
        ang = math.atan2(hy - cy, hx - cx)
        ex = hx + math.cos(ang - facing * 1.25) * HEAD_R * 0.45
        ey = hy + math.sin(ang - facing * 1.25) * HEAD_R * 0.45
        if "eyepatch" not in parts and "ninja_mask" not in parts and "knight_helm" not in parts:
            cr.set_source_rgba(0.03, 0.03, 0.06, 0.95)
            cr.set_line_width(0.035)
            cr.move_to(ex - math.cos(ang - facing * 1.57) * 0.03, ey - math.sin(ang - facing * 1.57) * 0.03)
            cr.line_to(ex + math.cos(ang - facing * 1.57) * 0.045, ey + math.sin(ang - facing * 1.57) * 0.045)
            cr.stroke()
        COS.draw_front(cr, parts, P, facing, s, col, sec, hist)
        # weapons in hand
        active = kind == "technique" and phase == "active"
        if front_w:
            if active and self.blur and weapon_class(front_w) in ("blade", "polearm", "blunt", "claws", "staff"):
                self._weapon_trail(cr, side, s, front_w, ab_cols[0] if (tech_ab and ab_cols) else None)
            draw_weapon(cr, front_w, P[J["hand_f"]], P[J["elbow_f"]], facing, glow, s)
            if weapon_class(front_w) == "fist":
                draw_weapon(cr, front_w, P[J["hand_b"]], P[J["elbow_b"]], facing, glow, s)
        if energy:
            ecols = [rgbs(self.abilities[a]["colors"]) for a in energy if a in self.abilities]
            if ecols:
                if active and self.blur:
                    self._weapon_trail(cr, side, s, None, ecols[0])
                draw_energy_blade(cr, P[J["hand_f"]], P[J["elbow_f"]], facing, ecols[0])
        # elemental / power infusion on the striking limb (fire fists, frost kicks, breath)
        if glow is not None and limb in ("hand_f", "hand_b", "foot_f", "foot_b", "head") and not (front_w and limb == "hand_f"):
            self._infused_limb(cr, side, s, P, limb, ab_cols, tech_ab, phase, facing)
        if kind == "technique" and phase == "antic" and tech_ab and ab_cols:
            hx2, hy2 = P[J["hand_f"]]
            r = 0.13 + 0.03 * math.sin(s * 40)
            g = cairo.RadialGradient(hx2, hy2, 0, hx2, hy2, r * 2.4)
            g.add_color_stop_rgba(0, 1, 1, 1, 0.95)
            g.add_color_stop_rgba(0.3, *ab_cols[0][1], 0.8)
            g.add_color_stop_rgba(1, *ab_cols[-1][2], 0.0)
            cr.set_source(g)
            cr.arc(hx2, hy2, r * 2.4, 0, 2 * math.pi)
            cr.fill()
        if flags & 1:
            cx2 = cx + facing * 0.32
            cr.set_source_rgba(0.75, 0.9, 1.0, 0.35)
            cr.set_line_width(0.05)
            base = 0 if facing > 0 else math.pi
            cr.arc(cx2 - facing * 0.1, cy - 0.1, 0.55, base - 0.9, base + 0.9)
            cr.stroke()
        if flags & 4 and ab_cols:
            c = ab_cols[0]
            cr.arc(x, y + 0.95, 1.0, 0, 2 * math.pi)
            cr.set_source_rgba(*c[1], 0.12)
            cr.fill_preserve()
            cr.set_source_rgba(*c[0], 0.55 + 0.2 * math.sin(s * 20))
            cr.set_line_width(0.04)
            cr.stroke()
        if flags & 32:
            for k in range(3):
                a = s * 5 + k * 2.09
                sx, sy = hx + math.cos(a) * 0.28, hy + 0.25 + math.sin(a) * 0.08
                self._star(cr, sx, sy, 0.06, (1, 0.95, 0.4))

    def _weapon_trail(self, cr, side, s, key, cols):
        pts = []
        for k in range(7):
            g = self.fighter_at(s - 0.014 * k, side)
            q = self._pts(g[3])
            h, e = q[J["hand_f"]], q[J["elbow_f"]]
            tip = weapon_tip(key or "katana", h, e)
            mid_ = (h[0] + (tip[0] - h[0]) * 0.35, h[1] + (tip[1] - h[1]) * 0.35)
            pts.append((tip, mid_))
        L = sum(math.hypot(pts[k][0][0] - pts[k + 1][0][0], pts[k][0][1] - pts[k + 1][0][1]) for k in range(6))
        if L < 0.3:
            return
        cr.move_to(*pts[0][0])
        for p in pts[1:]:
            cr.line_to(*p[0])
        for p in reversed(pts):
            cr.line_to(*p[1])
        cr.close_path()
        c1 = cols[1] if cols else (1, 1, 1)
        c2 = cols[2] if cols else (0.7, 0.8, 1)
        g = cairo.LinearGradient(pts[0][0][0], pts[0][0][1], pts[-1][0][0], pts[-1][0][1])
        g.add_color_stop_rgba(0, *c1, 0.6)
        g.add_color_stop_rgba(1, *c2, 0.0)
        cr.set_source(g)
        cr.fill()

    def _infused_limb(self, cr, side, s, P, limb, ab_cols, tech_ab, phase, facing):
        lx, ly = P[J[limb]]
        if limb == "head":  # breath leaves the mouth
            cx, cy = P[J["chest"]]
            lx, ly = lx + facing * 0.15, ly - 0.03
        c = ab_cols[0]
        c2 = ab_cols[-1]
        style = self.abilities[tech_ab[0]]["particle"] if tech_ab and tech_ab[0] in self.abilities else "spark"
        strength = 1.0 if phase == "active" else 0.6
        r = (0.16 if limb != "head" else 0.2) * strength
        g = cairo.RadialGradient(lx, ly, 0, lx, ly, r * 2.2)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.95 * strength)
        g.add_color_stop_rgba(0.35, *c[1], 0.75 * strength)
        g.add_color_stop_rgba(1, *c2[2], 0)
        cr.set_source(g)
        cr.arc(lx, ly, r * 2.2, 0, 2 * math.pi)
        cr.fill()
        trail = []
        for k in range(1, 7):
            g2 = self.fighter_at(s - 0.016 * k, side)
            trail.append((g2[3][2 * J[limb]], g2[3][2 * J[limb] + 1]))
        for k, (px, py) in enumerate(trail):
            fade = (1 - k / 7) * strength
            jit = stable_noise(side * 31 + k, s * 12) * 0.05
            col = (c if k % 2 == 0 else c2)[1]
            if style in ("flame", "ember"):
                cr.set_source_rgba(*mix(col, (1, 0.95, 0.6), 0.3), 0.7 * fade)
                cr.arc(px + jit, py + 0.04 * k, 0.09 * fade + 0.02, 0, 2 * math.pi)
                cr.fill()
            elif style in ("spark", "ray"):
                draw_bolt(cr, lx, ly, px + jit * 3, py - jit * 3, c, side * 97 + k + int(s * 40), 0.6 * fade, 0.025)
            elif style in ("shard", "frost", "metal"):
                cr.save()
                cr.translate(px, py)
                cr.rotate(k + s * 6)
                cr.move_to(0, 0.06 * fade + 0.02)
                cr.line_to(0.03, 0)
                cr.line_to(0, -0.06 * fade - 0.02)
                cr.line_to(-0.03, 0)
                cr.close_path()
                cr.set_source_rgba(*mix(col, (1, 1, 1), 0.3), 0.85 * fade)
                cr.fill()
                cr.restore()
            else:
                cr.set_source_rgba(*col, 0.6 * fade)
                cr.arc(px + jit, py, 0.07 * fade + 0.015, 0, 2 * math.pi)
                cr.fill()

    def _star(self, cr, x, y, r, col):
        cr.move_to(x + r, y)
        for k in range(1, 10):
            a = k * math.pi / 5
            rr = r if k % 2 == 0 else r * 0.45
            cr.line_to(x + math.cos(a) * rr, y + math.sin(a) * rr)
        cr.close_path()
        cr.set_source_rgba(*col, 0.95)
        cr.fill()

    def _trail(self, s, side, joint, n=7, step=0.018):
        out = []
        for k in range(n):
            g = self.fighter_at(s - step * k, side)
            out.append((g[3][2 * J[joint]], g[3][2 * J[joint] + 1]))
        return out

    # ------------------------------------------------------------ entities
    def draw_zones(self, cr, fr, s):
        for (zid, x0, x1, kind, alpha, ab) in fr["z"]:
            cols = rgbs(self.abilities[ab[0]]["colors"]) if ab and ab[0] in self.abilities else [(1, 1, 1)] * 3
            a = clamp(alpha, 0, 1)
            if kind in ("wet", "electrified"):
                cr.set_source_rgba(*cols[1], 0.35 * a)
                cr.rectangle(x0, -0.06, x1 - x0, 0.08)
                cr.fill()
                for k in range(int((x1 - x0) / 0.4)):
                    px = x0 + 0.2 + k * 0.4 + 0.1 * math.sin(s * 3 + k)
                    cr.set_source_rgba(1, 1, 1, 0.3 * a)
                    cr.set_line_width(0.015)
                    cr.move_to(px - 0.1, -0.02)
                    cr.line_to(px + 0.1, -0.02)
                    cr.stroke()
                if kind == "electrified":
                    for k in range(3):
                        bx = x0 + (x1 - x0) * ((k + 0.5) / 3)
                        draw_bolt(cr, bx - 0.3, 0.02, bx + 0.3, 0.25 + 0.2 * k % 2, [(1, 1, 1), (0.7, 0.9, 1), (0.3, 0.6, 1)],
                                  int(s * 30) + k + zid, a, 0.025)
            elif kind == "burning":
                n = max(2, int((x1 - x0) / 0.22))
                for k in range(n):
                    px = x0 + (k + 0.5) * (x1 - x0) / n
                    h = 0.18 + 0.16 * (0.5 + 0.5 * stable_noise(zid + k, s * 6))
                    cr.move_to(px - 0.1, 0)
                    cr.curve_to(px - 0.08, h * 0.6, px + 0.02 * math.sin(s * 9 + k), h, px, h)
                    cr.curve_to(px + 0.03, h * 0.7, px + 0.08, h * 0.4, px + 0.1, 0)
                    cr.close_path()
                    cr.set_source_rgba(*cols[1], 0.75 * a)
                    cr.fill()
            elif kind == "frozen":
                cr.set_source_rgba(*mix(cols[1], (1, 1, 1), 0.4), 0.55 * a)
                cr.rectangle(x0, -0.04, x1 - x0, 0.06)
                cr.fill()
                for k in range(int((x1 - x0) / 0.35)):
                    px = x0 + 0.17 + k * 0.35
                    cr.move_to(px - 0.06, 0.02)
                    cr.line_to(px, 0.14 + 0.05 * (k % 2))
                    cr.line_to(px + 0.06, 0.02)
                    cr.close_path()
                    cr.set_source_rgba(1, 1, 1, 0.6 * a)
                    cr.fill()
            elif kind in ("vines",):
                cr.set_line_width(0.035)
                for k in range(int((x1 - x0) / 0.3)):
                    px = x0 + k * 0.3
                    cr.set_source_rgba(*cols[1], 0.8 * a)
                    cr.move_to(px, 0)
                    cr.curve_to(px + 0.1, 0.25, px + 0.25, 0.05 + 0.05 * math.sin(s * 2 + k), px + 0.32, 0.18)
                    cr.stroke()
            elif kind == "toxic":
                cr.set_source_rgba(*cols[1], 0.45 * a)
                cr.rectangle(x0, -0.06, x1 - x0, 0.08)
                cr.fill()
                for k in range(int((x1 - x0) / 0.3)):
                    ph = (s * 0.8 + k * 0.37) % 1.0
                    cr.arc(x0 + 0.15 + k * 0.3, 0.05 + ph * 0.35, 0.04 * (1 - ph) + 0.01, 0, 2 * math.pi)
                    cr.set_source_rgba(*cols[0], 0.7 * a * (1 - ph))
                    cr.fill()
            elif kind in ("shadow", "well"):
                cr.save()
                cx = (x0 + x1) / 2
                cr.translate(cx, 0.0)
                cr.scale(1, 0.12)
                g = cairo.RadialGradient(0, 0, 0, 0, 0, (x1 - x0) / 2)
                g.add_color_stop_rgba(0, *cols[2], 0.75 * a)
                g.add_color_stop_rgba(1, *cols[2], 0)
                cr.set_source(g)
                cr.arc(0, 0, (x1 - x0) / 2, 0, 2 * math.pi)
                cr.fill()
                if kind == "well":
                    for k in range(3):
                        rr = ((s * 0.8 + k / 3) % 1.0)
                        cr.set_source_rgba(*cols[1], 0.6 * a * rr)
                        cr.set_line_width(0.3)
                        cr.arc(0, 0, (x1 - x0) / 2 * rr, 0, 2 * math.pi)
                        cr.stroke()
                cr.restore()
            elif kind == "cracked":
                cr.set_source_rgba(0, 0, 0, 0.5 * a)
                cr.set_line_width(0.03)
                cr.move_to(x0, 0)
                cr.line_to(x1, -0.02)
                cr.stroke()

    def draw_env(self, cr, fr, s):
        for (eid, x, h, r, form, state, ab, et) in fr["e"]:
            cols = rgbs(self.abilities[ab[0]]["colors"]) if ab and ab[0] in self.abilities else [(1, 1, 1), (0.8, 0.7, 0.5), (0.4, 0.3, 0.2)]
            if state == "warn" and form == "cannon_rain":
                for k, ox in enumerate((-r * 0.8, 0.0, r * 0.8)):
                    by = max(0.15, 10.0 - (et - 0.06 * k) * 22.0)
                    cr.arc(x + ox, by, 0.18, 0, 2 * math.pi)
                    cr.set_source_rgba(0.08, 0.08, 0.1, 1)
                    cr.fill()
                    cr.move_to(x + ox, by + 0.2)
                    cr.line_to(x + ox, by + 1.2)
                    cr.set_source_rgba(0.7, 0.7, 0.72, 0.35)
                    cr.set_line_width(0.12)
                    cr.stroke()
            if state == "warn":
                pulse = 0.5 + 0.5 * math.sin(s * 30)
                cr.save()
                cr.translate(x, 0.01)
                cr.scale(1, 0.18)
                g = cairo.RadialGradient(0, 0, 0, 0, 0, r + 0.3)
                g.add_color_stop_rgba(0, *cols[0], 0.7)
                g.add_color_stop_rgba(0.6, *cols[1], 0.45 * pulse + 0.2)
                g.add_color_stop_rgba(1, *cols[2], 0)
                cr.set_source(g)
                cr.arc(0, 0, r + 0.3, 0, 2 * math.pi)
                cr.fill()
                cr.restore()
                continue
            if h <= 0.01:
                continue
            w = r * 0.9
            if form == "pillar":
                cr.move_to(x - w, 0)
                cr.line_to(x - w * 0.8, h * 0.9)
                cr.line_to(x - w * 0.3, h)
                cr.line_to(x + w * 0.2, h * 0.93)
                cr.line_to(x + w * 0.75, h * 0.97)
                cr.line_to(x + w, 0)
                cr.close_path()
                g = cairo.LinearGradient(x - w, 0, x + w, 0)
                g.add_color_stop_rgb(0, *mix(cols[2], (0, 0, 0), 0.3))
                g.add_color_stop_rgb(0.5, *cols[1])
                g.add_color_stop_rgb(1, *mix(cols[2], (0, 0, 0), 0.5))
                cr.set_source(g)
                cr.fill()
                cr.set_source_rgba(0, 0, 0, 0.45)
                cr.set_line_width(0.025)
                cr.move_to(x - w * 0.3, h * 0.2)
                cr.line_to(x, h * 0.5)
                cr.line_to(x - w * 0.2, h * 0.8)
                cr.stroke()
            elif form == "spikes":
                for k, (ox, hh) in enumerate(((-w * 0.6, 0.75), (0.0, 1.0), (w * 0.6, 0.8))):
                    cr.move_to(x + ox - w * 0.35, 0)
                    cr.line_to(x + ox + 0.05 * (k - 1), h * hh)
                    cr.line_to(x + ox + w * 0.35, 0)
                    cr.close_path()
                    cr.set_source_rgba(*mix(cols[1], (1, 1, 1), 0.3), 0.92)
                    cr.fill_preserve()
                    cr.set_source_rgba(1, 1, 1, 0.8)
                    cr.set_line_width(0.02)
                    cr.stroke()
            elif form in ("geyser", "column"):
                n = 14
                cr.move_to(x - w * 0.5, 0)
                for k in range(n + 1):
                    yy = h * k / n
                    ww = w * (0.45 + 0.25 * k / n if form == "geyser" else 0.3 + 0.7 * k / n)
                    cr.line_to(x - ww + 0.06 * math.sin(s * 25 + k), yy)
                for k in range(n, -1, -1):
                    yy = h * k / n
                    ww = w * (0.45 + 0.25 * k / n if form == "geyser" else 0.3 + 0.7 * k / n)
                    cr.line_to(x + ww + 0.06 * math.sin(s * 23 + k * 1.3), yy)
                cr.close_path()
                g = cairo.LinearGradient(0, 0, 0, h)
                g.add_color_stop_rgba(0, *cols[2], 0.9)
                g.add_color_stop_rgba(0.6, *cols[1], 0.85)
                g.add_color_stop_rgba(1, *cols[0], 0.6)
                cr.set_source(g)
                cr.fill()
            elif form == "sky_strike":
                draw_bolt(cr, x + 0.3 * math.sin(eid), 10, x, 0, cols, eid * 31 + int(s * 40), clamp(1.2 - et * 2, 0, 1), 0.09)
            elif form == "vines":
                for k in (-1, 0, 1):
                    cr.set_source_rgba(*cols[2], 1)
                    cr.set_line_width(0.09 - 0.02 * abs(k))
                    cr.move_to(x + k * w * 0.5, 0)
                    cr.curve_to(x + k * w * 0.5 + 0.3, h * 0.35, x + k * w * 0.5 - 0.3, h * 0.65, x + k * 0.12, h)
                    cr.stroke()
                    cr.arc(x + k * 0.12, h, 0.08, 0, 2 * math.pi)
                    cr.set_source_rgba(*cols[1], 1)
                    cr.fill()
            elif form == "hands":
                for k in (-1, 1):
                    cr.set_source_rgba(*mix(cols[2], (0, 0, 0), 0.4), 0.95)
                    cr.move_to(x + k * w * 0.6 - 0.12, 0)
                    cr.curve_to(x + k * w * 0.6, h * 0.5, x + k * 0.2, h * 0.9, x - k * 0.05, h)
                    cr.curve_to(x + k * 0.25, h * 0.75, x + k * w * 0.6 + 0.12, h * 0.4, x + k * w * 0.6 + 0.12, 0)
                    cr.close_path()
                    cr.fill()
                    cr.set_source_rgba(*cols[1], 0.8)
                    cr.set_line_width(0.02)
                    cr.move_to(x + k * w * 0.6, 0.1)
                    cr.curve_to(x + k * w * 0.6, h * 0.5, x + k * 0.2, h * 0.85, x - k * 0.05, h)
                    cr.stroke()
            elif form == "cannon_rain":
                pass
            elif form == "tentacles":
                for k, (ox, sc_) in enumerate(((-w * 0.7, 0.8), (0.0, 1.0), (w * 0.7, 0.75))):
                    wig = 0.25 * math.sin(s * 5 + k * 2)
                    pts = [(x + ox + wig * (j / 6) ** 2 * (1 if k % 2 else -1) + 0.3 * math.sin(j * 0.9 + s * 4 + k) * (j / 6),
                            h * sc_ * j / 6) for j in range(7)]
                    for j in range(6):
                        cr.move_to(*pts[j])
                        cr.line_to(*pts[j + 1])
                        cr.set_source_rgba(*mix(cols[2], (0.3, 0.1, 0.3), 0.4), 1)
                        cr.set_line_width(0.24 * (1 - j / 7) + 0.03)
                        cr.stroke()
                    for j in range(1, 6):
                        cr.arc(pts[j][0] + 0.06 * (1 if k % 2 else -1), pts[j][1], 0.03, 0, 2 * math.pi)
                        cr.set_source_rgba(1, 0.85, 0.85, 0.8)
                        cr.fill()
            elif form == "light_pillar":
                g = cairo.LinearGradient(x - w, 0, x + w, 0)
                g.add_color_stop_rgba(0, *cols[2], 0)
                g.add_color_stop_rgba(0.5, *cols[0], 0.85 * h / 1.9)
                g.add_color_stop_rgba(1, *cols[2], 0)
                cr.set_source(g)
                cr.rectangle(x - w, 0, 2 * w, 10)
                cr.fill()
            else:  # well, burst
                for k in range(4):
                    rr = (k + 1) / 4 * w * 1.4 * (h / 1.9)
                    cr.set_source_rgba(*cols[1], 0.7 * (1 - k / 4))
                    cr.set_line_width(0.05)
                    cr.save()
                    cr.translate(x, 0.6 * k * h / 1.9)
                    cr.scale(1, 0.35)
                    cr.arc(0, 0, rr, 0, 2 * math.pi)
                    cr.restore()
                    cr.stroke()

    def draw_projectiles(self, cr, a, b, f, s):
        bmap = {p[0]: p for p in b["p"]}
        for p in a["p"]:
            pid, x, y, vx, vy, r, style, ab = p
            q = bmap.get(pid)
            if q:
                x, y = x + (q[1] - x) * f, y + (q[2] - y) * f
            cols = [rgbs(self.abilities[i]["colors"]) for i in ab if i in self.abilities] or [[(1, 1, 1)] * 3]
            c = cols[0]
            c2 = cols[-1]
            spd = math.hypot(vx, vy) or 1
            ux, uy = vx / spd, vy / spd
            ang = math.atan2(vy, vx)
            physical = style in PHYSICAL_PROJ
            if physical:
                # smoke / motion streak instead of an energy glow
                tl = {"bullet": 1.6, "knife": 0.5, "shuriken": 0.4, "harpoon": 0.6}.get(style, 0.9)
                g = cairo.LinearGradient(x, y, x - ux * tl, y - uy * tl)
                sc_ = (1, 0.9, 0.6) if style == "bullet" else (0.75, 0.75, 0.78)
                g.add_color_stop_rgba(0, *sc_, 0.75)
                g.add_color_stop_rgba(1, *sc_, 0)
                cr.set_source(g)
                cr.set_line_width(0.05 if style == "bullet" else 0.09)
                cr.move_to(x, y)
                cr.line_to(x - ux * tl, y - uy * tl)
                cr.stroke()
                if style in ("bomb", "cannonball", "bottle"):
                    for k in range(1, 6):
                        cr.arc(x - ux * k * 0.22, y - uy * k * 0.22 + 0.02 * k, 0.05 + 0.03 * k, 0, 2 * math.pi)
                        cr.set_source_rgba(0.6, 0.58, 0.55, 0.3 * (1 - k / 6))
                        cr.fill()
            else:
                g = cairo.RadialGradient(x, y, 0, x, y, r * 3.4)
                g.add_color_stop_rgba(0, *c[1], 0.55)
                g.add_color_stop_rgba(1, *c2[2], 0)
                cr.set_source(g)
                cr.arc(x, y, r * 3.4, 0, 2 * math.pi)
                cr.fill()
            for k in (range(1, 7) if not physical else ()):
                tx, ty = x - ux * k * r * 0.9, y - uy * k * r * 0.9
                cr.set_source_rgba(*(c2[1] if k % 2 else c[1]), 0.5 * (1 - k / 7))
                cr.arc(tx, ty, r * (1 - k / 8), 0, 2 * math.pi)
                cr.fill()
            cr.save()
            cr.translate(x, y)
            cr.rotate(ang)
            if style in ("orb",):
                for k in range(5):
                    fl = 0.5 + 0.5 * stable_noise(pid * 7 + k, s * 10)
                    cr.arc(-r * 0.4 * k * fl, r * 0.25 * math.sin(s * 20 + k), r * (1 - 0.15 * k), 0, 2 * math.pi)
                    cr.set_source_rgba(*c[1], 0.6)
                    cr.fill()
                cr.arc(0, 0, r * 0.62, 0, 2 * math.pi)
                cr.set_source_rgba(*c[0], 1)
                cr.fill()
            elif style == "shard":
                cr.move_to(r * 2.2, 0)
                cr.line_to(0, r * 0.7)
                cr.line_to(-r * 1.6, 0)
                cr.line_to(0, -r * 0.7)
                cr.close_path()
                cr.set_source_rgba(*c[1], 0.95)
                cr.fill_preserve()
                cr.set_source_rgba(*c[0], 1)
                cr.set_line_width(0.025)
                cr.stroke()
            elif style == "bolt":
                cr.restore()
                draw_bolt(cr, x - ux * 0.7, y - uy * 0.7, x + ux * 0.25, y + uy * 0.25, c, pid * 13 + int(s * 40), 1.0, 0.05)
                cr.save()
                cr.translate(x, y)
            elif style == "rock":
                cr.rotate(s * 9)
                rr = random.Random(pid)
                for k in range(6):
                    a2 = k / 6 * 2 * math.pi
                    d = r * 1.3 * rr.uniform(0.75, 1.15)
                    (cr.move_to if k == 0 else cr.line_to)(math.cos(a2) * d, math.sin(a2) * d)
                cr.close_path()
                cr.set_source_rgba(*c[1], 1)
                cr.fill_preserve()
                cr.set_source_rgba(*c[2], 1)
                cr.set_line_width(0.03)
                cr.stroke()
            elif style == "crescent":
                cr.arc(0, 0, r * 1.8, -1.3, 1.3)
                cr.arc_negative(-r * 0.6, 0, r * 1.6, 1.1, -1.1)
                cr.close_path()
                cr.set_source_rgba(*c[0], 0.9)
                cr.fill()
            elif style == "disc":
                cr.rotate(s * 30)
                cr.arc(0, 0, r * 1.2, 0, 2 * math.pi)
                cr.set_source_rgba(*c[1], 1)
                cr.set_line_width(0.05)
                cr.stroke()
                for k in range(4):
                    cr.rotate(math.pi / 2)
                    cr.move_to(r * 1.2, 0)
                    cr.line_to(r * 1.7, r * 0.35)
                    cr.line_to(r * 1.05, r * 0.4)
                    cr.close_path()
                    cr.set_source_rgba(*c[0], 1)
                    cr.fill()
            elif style == "seed":
                cr.rotate(s * 14)
                cr.scale(1, 0.45)
                cr.arc(0, 0, r * 1.4, 0, 2 * math.pi)
                cr.set_source_rgba(*c[1], 1)
                cr.fill()
            elif style == "bullet":
                cr.set_source_rgba(1, 0.95, 0.75, 1)
                cr.arc(0, 0, 0.05, 0, 2 * math.pi)
                cr.fill()
            elif style == "cannonball":
                cr.rotate(-ang)
                cr.arc(0, 0, 0.2, 0, 2 * math.pi)
                cr.set_source_rgba(0.1, 0.1, 0.12, 1)
                cr.fill()
                cr.arc(-0.06, 0.06, 0.06, 0, 2 * math.pi)
                cr.set_source_rgba(0.5, 0.5, 0.55, 0.8)
                cr.fill()
            elif style == "bomb":
                cr.rotate(-ang + s * 6)
                cr.arc(0, 0, 0.17, 0, 2 * math.pi)
                cr.set_source_rgba(0.08, 0.08, 0.1, 1)
                cr.fill()
                cr.rectangle(-0.05, 0.14, 0.1, 0.07)
                cr.set_source_rgba(0.4, 0.4, 0.42, 1)
                cr.fill()
                fl = 0.5 + 0.5 * math.sin(s * 50)
                cr.arc(0.04, 0.27, 0.04 + 0.03 * fl, 0, 2 * math.pi)
                cr.set_source_rgba(1, 0.8 * fl + 0.2, 0.2, 1)
                cr.fill()
            elif style == "bottle":
                cr.rotate(s * 12)
                cr.rectangle(-0.1, -0.06, 0.16, 0.12)
                cr.set_source_rgba(0.35, 0.55, 0.25, 0.95)
                cr.fill()
                cr.rectangle(0.06, -0.025, 0.08, 0.05)
                cr.fill()
                cr.arc(0.16, 0, 0.05 + 0.02 * math.sin(s * 40), 0, 2 * math.pi)
                cr.set_source_rgba(1, 0.6, 0.15, 1)
                cr.fill()
            elif style in ("knife", "harpoon"):
                if style == "knife":
                    cr.rotate(s * 25)
                L_ = 0.36 if style == "knife" else 0.9
                cr.rectangle(-L_ * 0.4, -0.02, L_ * 0.4, 0.04)
                cr.set_source_rgba(0.35, 0.22, 0.12, 1)
                cr.fill()
                cr.move_to(0, -0.035)
                cr.line_to(L_ * 0.6, 0)
                cr.line_to(0, 0.035)
                cr.close_path()
                cr.set_source_rgba(0.9, 0.93, 0.97, 1)
                cr.fill()
            elif style == "shuriken":
                cr.rotate(s * 30)
                for k in range(4):
                    cr.rotate(math.pi / 2)
                    cr.move_to(0.04, 0.04)
                    cr.line_to(0.2, 0)
                    cr.line_to(0.04, -0.04)
                cr.close_path()
                cr.set_source_rgba(0.75, 0.78, 0.84, 1)
                cr.fill()
                cr.arc(0, 0, 0.03, 0, 2 * math.pi)
                cr.set_source_rgba(0.1, 0.1, 0.12, 1)
                cr.fill()
            elif style == "ray" or style == "arrow":
                cr.set_line_width(0.06 if style == "ray" else 0.035)
                cr.set_source_rgba(*c[0], 1)
                cr.move_to(-r * 4, 0)
                cr.line_to(r * 1.5, 0)
                cr.stroke()
                if style == "arrow":
                    cr.move_to(r * 2.3, 0)
                    cr.line_to(r * 1.2, r * 0.6)
                    cr.line_to(r * 1.2, -r * 0.6)
                    cr.close_path()
                    cr.fill()
            elif style == "void":
                cr.arc(0, 0, r * 1.05, 0, 2 * math.pi)
                cr.set_source_rgba(0.03, 0.0, 0.06, 1)
                cr.fill_preserve()
                cr.set_source_rgba(*c[1], 1)
                cr.set_line_width(0.04)
                cr.stroke()
                for k in range(3):
                    cr.set_source_rgba(*c[0], 0.7)
                    cr.set_line_width(0.02)
                    a0 = s * 8 + k * 2.1
                    cr.arc(0, 0, r * 1.5, a0, a0 + 1.2)
                    cr.stroke()
            elif style == "wave":
                for k in range(3):
                    rr = r * (0.8 + 0.6 * k + 0.3 * ((s * 8) % 1))
                    cr.set_source_rgba(*c[1], 0.9 - 0.25 * k)
                    cr.set_line_width(0.045)
                    cr.arc(-k * 0.12, 0, rr, -0.9, 0.9)
                    cr.stroke()
            else:
                cr.arc(0, 0, r, 0, 2 * math.pi)
                cr.set_source_rgba(*c[0], 1)
                cr.fill()
            cr.restore()

    def draw_beams(self, cr, fr, s):
        for (bid, x0, y0, x1, y1, w, ab) in fr["b"]:
            cols = [rgbs(self.abilities[i]["colors"]) for i in ab if i in self.abilities] or [[(1, 1, 1)] * 3]
            c, c2 = cols[0], cols[-1]
            wob = 1 + 0.12 * math.sin(s * 50)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            for ww, col, a in ((w * 3.2, c2[2], 0.22), (w * 1.7, c[1], 0.6), (w * 0.75, c[0], 0.95), (w * 0.3, (1, 1, 1), 1)):
                cr.set_line_width(ww * wob)
                cr.set_source_rgba(*col, a)
                cr.move_to(x0, y0)
                cr.line_to(x1, y1)
                cr.stroke()
            styles = {self.abilities[i]["particle"] for i in ab if i in self.abilities}
            if "spark" in styles or len(cols) > 1:
                draw_bolt(cr, x0, y0, x1, y1, c2 if len(cols) > 1 else c, bid + int(s * 45), 0.9, 0.035)
            for (px, py, rr) in ((x0, y0, w * 1.6), (x1, y1, w * 2.4)):
                g = cairo.RadialGradient(px, py, 0, px, py, rr)
                g.add_color_stop_rgba(0, 1, 1, 1, 1)
                g.add_color_stop_rgba(0.4, *c[1], 0.8)
                g.add_color_stop_rgba(1, *c[2], 0)
                cr.set_source(g)
                cr.arc(px, py, rr, 0, 2 * math.pi)
                cr.fill()

    def ambient(self, cr, cam, s):
        self.art.ambient(cr, cam, s)

    # ------------------------------------------------------------ overlays
    def _events_between(self, s0, s1, types):
        i0 = bisect.bisect_left(self.ev_t, s0)
        i1 = bisect.bisect_right(self.ev_t, s1)
        return [e for e in self.events[i0:i1] if e["type"] in types]

    def draw_overlays(self, cr, k, vf, a):
        s = vf.sim_t
        hud = self.hud
        fs = self.res["fight_start"]
        seg = vf.segment
        if seg == "hook":
            hk = self.ctx.get("hook_t") or s
            hud.hook(cr, s - (hk - 0.75))
            return
        if seg == "intro":
            hud.header(cr, clamp(s / 0.3, 0, 1) * (1 - smoothstep((s - (fs - 0.4)) / 0.4)))
            hud.intro_card(cr, 0, s - 0.65, 0.85)
            hud.intro_card(cr, 1, s - 1.85, 0.85)
            hud.versus(cr, s - 2.65, fs - 2.65 + 0.05)
            return
        sa, sb = a["h"][0], a["h"][1]
        round_no = 1 + sum(1 for e in self._events_between(0, s, ("round_start",)))
        if seg == "fight":
            hud.draw_scoreboard(cr, a["h"], clamp((s - fs) / 0.4, 0, 1), round_no)
        # Attack names: small, under each fighter's score; discoveries: below the arena floor.
        if seg in ("fight", "outro"):
            for side in (0, 1):
                lab = None
                for L in self.attack_labels[side]:
                    if L["t"] <= s:
                        lab = L
                    else:
                        break
                if lab and s - lab["t"] <= lab["dur"]:
                    hud.attack_label(cr, side, lab["name"], lab["color"], s - lab["t"], lab["dur"], lab["tier"])
            for d in self.discoveries:
                if 0 <= s - d["t"] <= d["dur"]:
                    hud.discovery(cr, d["name"], d["owner"], d["color"], s - d["t"], d["dur"], d["slot"])
        for e in self._events_between(s - 1.6, s, ("fight", "round_start", "score", "ko", "guard_break", "counter")):
            age = s - e["t"]
            ty = e["type"]
            if ty == "fight":
                hud.banner(cr, "FIGHT!", None, (1, 0.85, 0.3), age, 0.85, size=190)
            elif ty == "round_start":
                sc = e.get("score", [sa, sb])
                mp = [n for n, v in enumerate(sc) if v == self.ptw - 1]
                sub = "MATCH POINT" if mp else f"{sc[0]} - {sc[1]}"
                hud.banner(cr, f"ROUND {e['round']}", sub, (1, 1, 1), age, 1.2, size=130)
            elif ty == "score":
                c = self.fcol[e["attacker"]]
                sc = e["score"]
                hud.banner(cr, "POINT!", f"{self.fighters[e['attacker']]['name']}  {sc[0]} - {sc[1]}", c, age, 1.5, size=160)
            elif ty == "ko":
                c = self.fcol[e["attacker"]]
                hud.banner(cr, "K.O.!", None, c, age, 1.6, size=230)
            elif ty == "guard_break":
                hud.banner(cr, "GUARD BREAK", None, (1, 0.6, 0.35), age, 0.7, y=self.H * 0.6, size=64)
            elif ty == "counter":
                hud.banner(cr, "COUNTER!", None, (1, 0.95, 0.6), age, 0.6, y=self.H * 0.6, size=70)
        if seg == "outro" and self.ko is not None:
            w = self.res["winner"]
            info = self.ctx.get("info", {})
            hud.winner(cr, w, self.res["scores"], s - (self.ko["t"] + 1.2), info.get("next_line"), info.get("is_final", False))

    # ------------------------------------------------------------ frame
    def render(self, k):
        vf = self.vframes[k]
        cam = self.cams[k]
        s = vf.sim_t
        cr = cairo.Context(self.surface)
        cr.save()
        cr.translate(self.W / 2 + cam.sx, self.H / 2 + cam.sy)
        cr.rotate(cam.rot)
        cr.translate(-self.W / 2, -self.H / 2)
        self.draw_background(cr, cam, s)
        a, b, f = self.frame_at(s)
        # world transform
        cr.save()
        cr.translate(self.W / 2, self.H / 2)
        cr.scale(cam.zoom, -cam.zoom)
        cr.translate(-cam.cx, -cam.cy)
        self.draw_ground(cr, cam, s)
        self.fx.draw_back(cr, s)
        self.draw_zones(cr, a, s)
        self.draw_env(cr, a, s)
        order = [0, 1]
        fa = self.fighter_at(s, 0)
        fb = self.fighter_at(s, 1)
        # draw the attacking fighter on top
        if fa[4] == "technique" and fb[4] != "technique":
            order = [1, 0]
        for side in order:
            self.draw_fighter(cr, side, s, fa if side == 0 else fb, cam)
        self.draw_beams(cr, a, s)
        self.draw_projectiles(cr, a, b, f, s)
        self.fx.draw(cr, s)
        self.ambient(cr, cam, s)
        cr.restore()
        cr.restore()
        cr.set_source_surface(self.vignette, 0, 0)
        cr.paint()
        flash = self.fx.screen_flash_alpha(s)
        if flash:
            cr.set_source_rgba(*flash[0], flash[1] * 0.28)
            cr.paint()
        if cam.bars > 0.01:
            bh = self.H * 0.06 * cam.bars
            cr.set_source_rgba(0, 0, 0, 0.9)
            cr.rectangle(0, 0, self.W, bh)
            cr.rectangle(0, self.H - bh, self.W, bh)
            cr.fill()
        self.draw_overlays(cr, k, vf, a)
        self.surface.flush()
        return self.surface
