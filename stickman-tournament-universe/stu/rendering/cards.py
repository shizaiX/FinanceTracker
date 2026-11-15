"""Tournament presentation templates: bracket reveal / progression and the
champion reveal. Rendered with the same streaming encoder as fights."""
from __future__ import annotations

import math

import cairo

from ..core.mathutil import clamp, ease_out_back, hex_to_rgb, mix, smoothstep
from .hud import text


class BracketCard:
    """Animated bracket. `highlight_round` = round whose results are revealed."""

    def __init__(self, cfg, state, title, subtitle, duration=6.0, champion=None, upto_round=None):
        self.W, self.H = cfg["video"]["width"], cfg["video"]["height"]
        self.fps = cfg["video"]["fps"]
        self.state = state
        self.title = title
        self.subtitle = subtitle
        self.n = int(duration * self.fps)
        self.champion = champion
        self.upto = upto_round  # rounds >= upto are shown without results (no spoilers)
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.W, self.H)
        self.f = {f["id"]: f for f in state["fighters"]}

    def u(self, v):
        return v * self.W / 1080.0

    def _bg(self, cr, t):
        g = cairo.LinearGradient(0, 0, 0, self.H)
        g.add_color_stop_rgb(0, 0.03, 0.02, 0.08)
        g.add_color_stop_rgb(1, 0.10, 0.03, 0.10)
        cr.set_source(g)
        cr.paint()
        for k in range(30):
            x = (k * 137.5 + t * 20) % self.W
            y = (k * 263.1) % self.H
            cr.set_source_rgba(1, 0.8, 0.5, 0.08 + 0.05 * math.sin(t * 2 + k))
            cr.arc(x, y, self.u(2 + k % 3), 0, 2 * math.pi)
            cr.fill()

    def render(self, k):
        t = k / self.fps
        cr = cairo.Context(self.surface)
        self._bg(cr, t)
        if self.champion:
            return self._champion(cr, t)
        W, u = self.W, self.u
        top = self.H * 0.09
        text(cr, self.title, W / 2, top + u(30), u(64), (1, 0.85, 0.4), "center", clamp(t / 0.3, 0, 1), glow=(1, 0.6, 0.2))
        text(cr, self.subtitle, W / 2, top + u(100), u(34), (1, 1, 1), "center", clamp((t - 0.2) / 0.3, 0, 1), heavy=False, tracking=0.08)
        br = self.state["bracket"]
        rounds = br["rounds"]
        nR = len(rounds)
        ms = br["matches"]
        area_top, area_bot = self.H * 0.2, self.H * 0.78
        col_w = (W - u(80)) / nR
        pos = {}
        for r, mids in enumerate(rounds):
            cnt = len(mids)
            for i, mid in enumerate(mids):
                m = ms[mid]
                y = area_top + (i + 0.5) * (area_bot - area_top) / cnt
                x = u(40) + r * col_w
                pos[mid] = (x, y)
                appear = clamp((t - 0.4 - 0.12 * i - 0.5 * r) / 0.35, 0, 1)
                if appear <= 0:
                    continue
                hide = self.upto is not None and m["round"] >= self.upto
                for slot, key in ((0, "a"), (1, "b")):
                    fid = m[key] if not (self.upto is not None and m["round"] > self.upto) else None
                    yy = y + (slot - 0.5) * u(52 if r == 0 else 46)
                    name = self.f[fid]["name"] if fid else ("BYE" if r == 0 else "?")
                    col = hex_to_rgb(self.f[fid]["color"]) if fid else (0.5, 0.5, 0.55)
                    lost = (not hide) and m["winner"] and fid and m["winner"] != fid
                    a = appear * (0.35 if lost else 1.0)
                    cr.set_source_rgba(*mix(col, (0, 0, 0), 0.75), 0.85 * a)
                    cr.rectangle(x, yy - u(21), col_w - u(26), u(42))
                    cr.fill()
                    cr.set_source_rgba(*col, a)
                    cr.rectangle(x, yy - u(21), u(7), u(42))
                    cr.fill()
                    size = 30 if nR <= 3 else 24
                    text(cr, name, x + u(18), yy, u(size), col if not lost else (0.6, 0.6, 0.65), "left", a, outline=0.12)
                    if m["scores"] and fid and not hide:
                        sc = m["scores"][slot]
                        text(cr, str(sc), x + col_w - u(40), yy, u(28), (1, 1, 1), "right", a)
                if r > 0:
                    for s in m["src"]:
                        if s in pos:
                            px, py = pos[s]
                            cr.set_source_rgba(1, 1, 1, 0.25 * appear)
                            cr.set_line_width(u(3))
                            cr.move_to(px + col_w - u(26), py)
                            cr.line_to(x - u(6), py)
                            cr.line_to(x - u(6), y)
                            cr.stroke()
        return self.surface

    def _champion(self, cr, t):
        W, H, u = self.W, self.H, self.u
        f = self.f[self.champion]
        col = hex_to_rgb(f["color"])
        g = cairo.RadialGradient(W / 2, H * 0.45, 0, W / 2, H * 0.45, H * 0.5)
        g.add_color_stop_rgba(0, *col, 0.45 * clamp(t / 0.8, 0, 1))
        g.add_color_stop_rgba(1, *col, 0)
        cr.set_source(g)
        cr.paint()
        for k in range(24):
            a = k / 24 * 2 * math.pi + t * 0.3
            cr.set_source_rgba(*mix(col, (1, 1, 1), 0.5), 0.08)
            cr.move_to(W / 2, H * 0.45)
            cr.line_to(W / 2 + math.cos(a) * H, H * 0.45 + math.sin(a) * H)
            cr.line_to(W / 2 + math.cos(a + 0.08) * H, H * 0.45 + math.sin(a + 0.08) * H)
            cr.close_path()
            cr.fill()
        sc = 0.6 + 0.4 * ease_out_back(clamp((t - 0.3) / 0.5, 0, 1), 1.8)
        text(cr, self.title, W / 2, H * 0.14, u(52), (1, 0.85, 0.4), "center", clamp(t / 0.4, 0, 1), tracking=0.1)
        text(cr, "CHAMPION", W / 2, H * 0.27, u(80), (1, 0.9, 0.5), "center", clamp((t - 0.2) / 0.3, 0, 1), glow=(1, 0.7, 0.2), tracking=0.15)
        text(cr, f["name"], W / 2, H * 0.37, u(170), col, "center", clamp((t - 0.3) / 0.3, 0, 1), scale=sc, glow=col)
        text(cr, "  +  ".join(n.upper() for n in f["ability_names"]), W / 2, H * 0.45, u(42), (1, 1, 1), "center", clamp((t - 0.7) / 0.3, 0, 1))
        rec = self.subtitle
        text(cr, rec, W / 2, H * 0.5, u(34), (0.85, 0.85, 0.9), "center", clamp((t - 0.9) / 0.3, 0, 1), heavy=False)
        # trophy-like stick figure pose
        cx, gy = W / 2, H * 0.7
        s = u(190)
        a = clamp((t - 0.4) / 0.4, 0, 1)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        pts = {"hip": (0, 0.9), "chest": (0, 1.45), "head": (0, 1.66), "hf": (0.2, 2.1), "ef": (0.15, 1.8), "hb": (-0.35, 1.25),
               "eb": (-0.25, 1.5), "kf": (0.22, 0.48), "ff": (0.26, 0.0), "kb": (-0.18, 0.47), "fb": (-0.3, 0.0)}
        P = {k: (cx + v[0] * s, gy - v[1] * s) for k, v in pts.items()}
        for w, c, al in ((u(36), col, 0.15), (u(16), (0.02, 0.02, 0.04), 0.9), (u(11), mix(col, (1, 1, 1), 0.15), 1.0)):
            cr.set_source_rgba(*c, al * a)
            cr.set_line_width(w)
            for chain in (("hip", "chest"), ("chest", "ef", "hf"), ("chest", "eb", "hb"), ("hip", "kf", "ff"), ("hip", "kb", "fb")):
                cr.move_to(*P[chain[0]])
                for q in chain[1:]:
                    cr.line_to(*P[q])
                cr.stroke()
            cr.arc(P["head"][0], P["head"][1] - u(10), u(26) + (w - u(11)) / 2, 0, 2 * math.pi)
            cr.fill()
        return self.surface
