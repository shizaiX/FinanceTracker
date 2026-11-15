"""Screen-space typography, HUD and announcement templates.

Mobile-first: big, outlined, high-contrast text kept out of the platform UI
safe zones (top ~7 %, bottom ~20 %, right edge ~10 % in the lower half).
"""
from __future__ import annotations

import math

import cairo

from ..core.mathutil import clamp, ease_out_back, hex_to_rgb, mix, smoothstep

FONT_HEAVY = "Inter Display Black"
FONT_BOLD = "Inter Display ExtraBold"
FALLBACK = "Sans"

SAFE_TOP = 0.075
SAFE_BOTTOM = 0.80


def set_font(cr, size, heavy=True):
    cr.select_font_face(FONT_HEAVY if heavy else FONT_BOLD, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(size)


def text(cr, s, x, y, size, color=(1, 1, 1), align="center", alpha=1.0, outline=0.16, heavy=True, scale=1.0,
         glow=None, tracking=0.0, max_width=None):
    if alpha <= 0.01 or not s:
        return 0
    cr.save()
    set_font(cr, size, heavy)
    xb, yb, w, h, xa, ya = cr.text_extents(s)
    w += tracking * size * max(0, len(s) - 1)
    if max_width and w * scale > max_width:
        scale *= max_width / (w * scale)
    cr.translate(x, y)
    cr.scale(scale, scale)
    ox = {"center": -w / 2 - xb, "left": -xb, "right": -w - xb}[align]
    oy = -(yb + h / 2)
    cr.move_to(ox, oy)
    if tracking:
        for ch in s:
            cr.text_path(ch)
            cr.rel_move_to(tracking * size, 0)
    else:
        cr.text_path(s)
    path = cr.copy_path()
    if glow is not None:
        cr.set_source_rgba(*glow, 0.35 * alpha)
        cr.set_line_width(size * 0.32)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke_preserve()
    if outline:
        cr.set_source_rgba(0.02, 0.02, 0.05, 0.92 * alpha)
        cr.set_line_width(size * outline)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.stroke_preserve()
    cr.set_source_rgba(*color, alpha)
    cr.fill()
    cr.new_path()
    cr.restore()
    return w * scale


def pill(cr, x, y, w, h, color, alpha):
    r = h / 2
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, math.pi / 2)
    cr.arc(x + r, y + r, r, math.pi / 2, 3 * math.pi / 2)
    cr.close_path()
    cr.set_source_rgba(*color, alpha)
    cr.fill()


def pop(age, dur, in_t=0.18, out_t=0.25):
    """(scale, alpha) for a banner of given age/duration."""
    if age < 0 or age > dur:
        return 0.0, 0.0
    sc = 0.6 + 0.4 * ease_out_back(age / in_t, 2.0) if age < in_t else 1.0
    a = 1.0 if age < dur - out_t else clamp((dur - age) / out_t, 0, 1)
    a *= clamp(age / 0.06, 0, 1)
    return sc, a


class Hud:
    def __init__(self, W, H, fighters, info, ptw):
        self.W, self.H = W, H
        self.f = fighters
        self.info = info
        self.ptw = ptw
        self.col = [hex_to_rgb(f["color"]) for f in fighters]

    def u(self, v):
        return v * self.W / 1080.0

    # ---- persistent HUD ---------------------------------------------------
    def draw_scoreboard(self, cr, hud, alpha, round_no):
        if alpha <= 0:
            return
        W, u = self.W, self.u
        top = self.H * SAFE_TOP + u(40)
        sa, sb, pa, pb = hud[0], hud[1], hud[2], hud[3]
        # backdrop
        g = cairo.LinearGradient(0, top - u(60), 0, top + u(190))
        g.add_color_stop_rgba(0, 0, 0, 0, 0.55 * alpha)
        g.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.set_source(g)
        cr.rectangle(0, top - u(60), W, u(250))
        cr.fill()
        for side in (0, 1):
            f = self.f[side]
            c = self.col[side]
            x = u(56) if side == 0 else W - u(56)
            al = "left" if side == 0 else "right"
            text(cr, f["name"], x, top + u(28), u(58), c, al, alpha, glow=c, max_width=u(330))
            abil = " · ".join(a.upper() for a in f["ability_names"])
            text(cr, abil, x, top + u(80), u(25), (0.88, 0.88, 0.92), al, alpha * 0.95, outline=0.2, heavy=False, tracking=0.04,
                 max_width=u(330))
            # guard bar
            p = clamp((pa if side == 0 else pb) / 100.0, 0, 1)
            bw, bh = u(330), u(11)
            bx = x if side == 0 else x - bw
            by = top + u(108)
            cr.set_source_rgba(1, 1, 1, 0.16 * alpha)
            cr.rectangle(bx, by, bw, bh)
            cr.fill()
            fill = mix(c, (1, 0.25, 0.2), 1 - p if p < 0.35 else 0.0)
            cr.set_source_rgba(*fill, 0.95 * alpha)
            if side == 0:
                cr.rectangle(bx, by, bw * p, bh)
            else:
                cr.rectangle(bx + bw * (1 - p), by, bw * p, bh)
            cr.fill()
            # score pips
            score = sa if side == 0 else sb
            for k in range(self.ptw):
                px = (x + u(22) + k * u(44)) if side == 0 else (x - u(22) - k * u(44))
                py = top + u(150)
                cr.arc(px, py, u(15), 0, 2 * math.pi)
                if k < score:
                    cr.set_source_rgba(*c, alpha)
                    cr.fill_preserve()
                    cr.set_source_rgba(1, 1, 1, alpha)
                    cr.set_line_width(u(3))
                    cr.stroke()
                else:
                    cr.set_source_rgba(1, 1, 1, 0.12 * alpha)
                    cr.fill_preserve()
                    cr.set_source_rgba(1, 1, 1, 0.45 * alpha)
                    cr.set_line_width(u(2.5))
                    cr.stroke()
        text(cr, f"{sa} - {sb}", W / 2, top + u(40), u(54), (1, 1, 1), "center", alpha)
        text(cr, f"ROUND {round_no}", W / 2, top + u(92), u(24), (0.85, 0.85, 0.9), "center", alpha * 0.9, heavy=False)

    def attack_label(self, cr, side, name, color, age, dur, tier=None):
        """Name of the attack a fighter is using, small, under its score pips."""
        sc, a = pop(age, dur, 0.12, 0.35)
        if a <= 0:
            return
        u = self.u
        top = self.H * SAFE_TOP + u(40)
        x = u(56) if side == 0 else self.W - u(56)
        al = "left" if side == 0 else "right"
        y = top + u(214)
        if tier == "ultimate":
            text(cr, "ULTIMATE", x, y - u(27), u(19), (1, 0.85, 0.4), al, a, heavy=False, tracking=0.2)
        text(cr, name, x, y, u(30 if tier != "ultimate" else 34), color, al, a, outline=0.18, max_width=u(440))

    def discovery(self, cr, name, owner, color, age, dur, slot=0):
        """New-technique notice below the arena floor, in the discoverer's colour."""
        sc, a = pop(age, dur, 0.15, 0.4)
        if a <= 0:
            return
        u = self.u
        y = self.H * 0.742 + slot * u(74)
        text(cr, f"{owner} DISCOVERED A NEW TECHNIQUE", self.W / 2, y, u(22), color, "center", a * 0.9, heavy=False,
             tracking=0.08, max_width=u(900))
        text(cr, name, self.W / 2, y + u(36), u(36), color, "center", a, outline=0.18, max_width=u(900))

    # ---- announcement templates ---------------------------------------------
    def banner(self, cr, title, sub, color, age, dur, y=None, size=150):
        sc, a = pop(age, dur)
        if a <= 0:
            return
        y = y or self.H * 0.36
        text(cr, title, self.W / 2, y, self.u(size), color, "center", a, scale=sc, glow=color, outline=0.12)
        if sub:
            text(cr, sub, self.W / 2, y + self.u(size * 0.75), self.u(46), (1, 1, 1), "center", a, scale=sc)

    def callout(self, cr, name, color, age, dur, new=False, tier="fusion", slot=0, owner=None):
        sc, a = pop(age, dur, 0.14, 0.3)
        if a <= 0:
            return
        y = self.H * 0.27 + slot * self.u(150)
        size = 62 if tier != "ultimate" else 72
        if len(name) > 22:
            size *= 22 / len(name)
        if new:
            text(cr, "NEW TECHNIQUE DISCOVERED", self.W / 2, y - self.u(62), self.u(28), (1, 0.92, 0.5), "center", a, heavy=False, tracking=0.08)
        elif tier == "ultimate":
            text(cr, "ULTIMATE", self.W / 2, y - self.u(66), self.u(32), (1, 0.85, 0.4), "center", a, tracking=0.25)
        text(cr, name, self.W / 2, y, self.u(size), color, "center", a, scale=sc, glow=color, max_width=self.u(960))
        if owner:
            text(cr, owner, self.W / 2, y + self.u(48), self.u(24), (0.85, 0.85, 0.9), "center", a * 0.85, heavy=False, tracking=0.1)

    def intro_card(self, cr, side, age, dur):
        sc, a = pop(age, dur, 0.2, 0.25)
        if a <= 0:
            return
        f = self.f[side]
        c = self.col[side]
        y = self.H * 0.3
        slide = (1 - smoothstep(age / 0.25)) * self.u(120) * (-1 if side == 0 else 1)
        cr.save()
        cr.translate(slide, 0)
        text(cr, f["name"], self.W / 2, y, self.u(124), c, "center", a, scale=sc, glow=c)
        text(cr, "  +  ".join(n.upper() for n in f["ability_names"]), self.W / 2, y + self.u(100), self.u(40), (1, 1, 1), "center", a)
        text(cr, f["personality"].upper() + " FIGHTER", self.W / 2, y + self.u(150), self.u(28), (0.8, 0.8, 0.85), "center", a * 0.9,
             heavy=False, tracking=0.12)
        cr.restore()

    def versus(self, cr, age, dur):
        sc, a = pop(age, dur, 0.2, 0.3)
        if a <= 0:
            return
        y = self.H * 0.24
        text(cr, self.f[0]["name"], self.W / 2, y, self.u(104), self.col[0], "center", a, scale=sc, glow=self.col[0])
        text(cr, "VS", self.W / 2, y + self.u(105), self.u(70), (1, 1, 1), "center", a, scale=sc)
        text(cr, self.f[1]["name"], self.W / 2, y + self.u(210), self.u(104), self.col[1], "center", a, scale=sc, glow=self.col[1])
        text(cr, f"FIRST TO {self.ptw}", self.W / 2, y + self.u(300), self.u(36), (1, 0.9, 0.55), "center", a, tracking=0.12)

    def header(self, cr, alpha):
        if alpha <= 0:
            return
        info = self.info
        top = self.H * SAFE_TOP + self.u(20)
        text(cr, info.get("tournament_name", "").upper(), self.W / 2, top, self.u(34), (1, 0.88, 0.55), "center", alpha, tracking=0.1)
        text(cr, info.get("stage_label", ""), self.W / 2, top + self.u(46), self.u(28), (0.9, 0.9, 0.95), "center", alpha, heavy=False, tracking=0.08)
        if info.get("arena_name"):
            text(cr, info["arena_name"].upper(), self.W / 2, top + self.u(86), self.u(24), (0.75, 0.85, 1.0), "center", alpha * 0.9, heavy=False, tracking=0.12)

    def hook(self, cr, age):
        a = clamp(age / 0.15, 0, 1)
        top = self.H * SAFE_TOP + self.u(60)
        text(cr, "WHO WINS?", self.W / 2, top + self.u(40), self.u(110), (1, 1, 1), "center", a, glow=(1, 0.8, 0.3))
        text(cr, f"{self.f[0]['name']}  vs  {self.f[1]['name']}", self.W / 2, top + self.u(140), self.u(44), (1, 0.88, 0.55), "center", a)

    def winner(self, cr, side, score, age, next_line, champion=False):
        sc, a = pop(age, 99.0, 0.25, 0.1)
        if a <= 0:
            return
        f = self.f[side]
        c = self.col[side]
        y = self.H * 0.2
        text(cr, "CHAMPION" if champion else "WINNER", self.W / 2, y, self.u(46), (1, 0.88, 0.5), "center", a, tracking=0.3)
        text(cr, f["name"], self.W / 2, y + self.u(105), self.u(140), c, "center", a, scale=sc, glow=c)
        text(cr, f"{score[0]} - {score[1]}", self.W / 2, y + self.u(215), self.u(72), (1, 1, 1), "center", a)
        if next_line:
            a2 = clamp((age - 0.6) / 0.3, 0, 1) * a
            text(cr, next_line, self.W / 2, y + self.u(300), self.u(36), (0.92, 0.92, 0.97), "center", a2, heavy=False, tracking=0.05)
