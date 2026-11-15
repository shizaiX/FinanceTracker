"""Procedural arena art driven by generated arena dicts (themes/arenas.py).

Three parallax layers (far silhouettes, mid-ground props, ground) plus sky,
celestial body, weather and lightning. All drawing is deterministic from the
arena's layout seed and the time, so any frame renders independently.
"""
from __future__ import annotations

import math
import random

import cairo

from ..core.mathutil import clamp, hex_to_rgb, mix
from ..core.rng import stable_noise

HALF = 7.2
INK = (0.02, 0.02, 0.04)


def _defaults(ar):
    a = dict(ar)
    a.setdefault("far_type", "mountains")
    a.setdefault("ground_style", "stone")
    a.setdefault("props_list", [a.get("props", "rock_spire")])
    a.setdefault("layout_seed", sum(map(ord, a.get("name", "x"))))
    a.setdefault("celestial", "sun")
    a.setdefault("lightning", False)
    return a


class ArenaArt:
    def __init__(self, arena, W, H):
        self.a = _defaults(arena)
        self.W, self.H = W, H
        self.sky_top, self.sky_hor = (hex_to_rgb(c) for c in self.a["sky"])
        self.far = hex_to_rgb(self.a["far"])
        self.mid = hex_to_rgb(self.a["mid"])
        self.gcol = hex_to_rgb(self.a["ground"])
        self.acc = hex_to_rgb(self.a["accent"])
        r = random.Random(self.a["layout_seed"])
        self.r_seed = self.a["layout_seed"]
        # far silhouettes
        self.far_pts = [(x, 2.0 + 3.2 * abs(stable_noise(self.r_seed % 997, x * 0.18)) + 1.2 * stable_noise(self.r_seed % 991 + 3, x * 0.6))
                        for x in [i * 0.7 - 42 for i in range(122)]]
        self.far_items = []
        x = -40.0
        while x < 40:
            x += r.uniform(5, 12)
            self.far_items.append((x, r.uniform(0.7, 1.3), r.randrange(1 << 20)))
        self.props = []
        kinds = self.a["props_list"]
        x = -30.0
        while x < 30:
            x += r.uniform(2.8, 5.5)
            if abs(x) < 1.2:
                continue
            self.props.append((x, r.uniform(0.8, 1.25), r.randrange(1 << 20), r.choice(kinds)))
        self._build_sky()

    # ----------------------------------------------------------------- sky
    def _build_sky(self):
        W, H = self.W, self.H
        self.sky = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H + 200)
        cr = cairo.Context(self.sky)
        g = cairo.LinearGradient(0, 0, 0, H * 0.8)
        g.add_color_stop_rgb(0, *self.sky_top)
        g.add_color_stop_rgb(1, *self.sky_hor)
        cr.set_source(g)
        cr.paint()
        r = random.Random(self.r_seed)
        night = self.a.get("time_of_day") in ("night", "storm")
        if night:
            for _ in range(140):
                cr.arc(r.uniform(0, W), r.uniform(0, H * 0.5), r.uniform(0.6, 2.2), 0, 2 * math.pi)
                cr.set_source_rgba(1, 1, 1, r.uniform(0.15, 0.7))
                cr.fill()
        cel = self.a["celestial"]
        if cel != "none":
            cx, cy = W * r.uniform(0.62, 0.8), H * r.uniform(0.14, 0.22)
            rad = W * (0.07 if cel == "moon" else 0.09)
            col = (0.95, 0.95, 1.0) if cel == "moon" else mix(self.acc, (1, 1, 0.85), 0.5)
            g = cairo.RadialGradient(cx, cy, 0, cx, cy, rad * 3.5)
            g.add_color_stop_rgba(0, *col, 0.45)
            g.add_color_stop_rgba(1, *col, 0)
            cr.set_source(g)
            cr.paint()
            cr.arc(cx, cy, rad, 0, 2 * math.pi)
            cr.set_source_rgba(*col, 0.8)
            cr.fill()
            if cel == "moon":
                cr.arc(cx + rad * 0.35, cy - rad * 0.1, rad * 0.25, 0, 2 * math.pi)
                cr.set_source_rgba(0.6, 0.6, 0.7, 0.25)
                cr.fill()
        # soft cloud bands
        for k in range(5):
            y = H * r.uniform(0.08, 0.45)
            x = r.uniform(-0.2, 1.0) * W
            cr.save()
            cr.translate(x, y)
            cr.scale(1, 0.18)
            cr.arc(0, 0, W * r.uniform(0.25, 0.45), 0, 2 * math.pi)
            cr.restore()
            cr.set_source_rgba(*mix(self.sky_hor, (1, 1, 1), 0.3), 0.06 if night else 0.12)
            cr.fill()

    def lightning_alpha(self, s):
        if not self.a["lightning"]:
            return 0.0
        ph = (s + (self.r_seed % 7)) % 6.7
        return 0.55 * (1 - ph / 0.18) if ph < 0.18 else 0.0

    # ------------------------------------------------------------- layers
    def _layer(self, cr, cam, p, scale):
        z = cam.zoom * scale
        cr.translate(self.W / 2, self.H / 2 + cam.cy * cam.zoom)
        cr.scale(z, -z)
        cr.translate(-cam.cx * p, 0)

    def draw_background(self, cr, cam, s):
        cr.set_source_surface(self.sky, 0, -cam.cy * 8 - 60)
        cr.paint()
        la = self.lightning_alpha(s)
        if la > 0:
            cr.set_source_rgba(0.85, 0.9, 1.0, la * 0.6)
            cr.paint()
        cr.save()
        self._layer(cr, cam, 0.12, 0.42)
        getattr(self, "_far_" + self.a["far_type"], self._far_mountains)(cr, s, cam)
        cr.restore()
        gy = self.H / 2 + cam.cy * cam.zoom
        g = cairo.LinearGradient(0, gy - cam.zoom * 2.0, 0, gy)
        g.add_color_stop_rgba(0, *self.acc, 0)
        g.add_color_stop_rgba(1, *mix(self.acc, self.far, 0.5), 0.18)
        cr.set_source(g)
        cr.rectangle(0, gy - cam.zoom * 2.0, self.W, cam.zoom * 2.0)
        cr.fill()
        cr.save()
        self._layer(cr, cam, 0.45, 0.7)
        for (x, sc, seed, kind) in self.props:
            if abs(x - cam.cx * 0.45) > 13:
                continue
            fn = getattr(self, "_prop_" + kind, None)
            if fn:
                cr.save()
                fn(cr, x, sc, seed, s)
                cr.restore()
        cr.restore()

    # ---- far layer types ---------------------------------------------------
    def _far_mountains(self, cr, s, cam):
        cr.move_to(self.far_pts[0][0], -2)
        for x, y in self.far_pts:
            cr.line_to(x, max(0.5, y))
        cr.line_to(self.far_pts[-1][0], -2)
        cr.close_path()
        cr.set_source_rgb(*self.far)
        cr.fill()
        if self.a.get("ambient") == "snow" or self.a["ground_style"] == "ice":
            for x, y in self.far_pts[::3]:
                if y > 3.5:
                    cr.move_to(x - 0.5, y - 0.6)
                    cr.line_to(x, y)
                    cr.line_to(x + 0.5, y - 0.6)
                    cr.close_path()
                    cr.set_source_rgba(1, 1, 1, 0.55)
                    cr.fill()

    def _far_volcanoes(self, cr, s, cam):
        self._far_mountains(cr, s, cam)
        for (x, sc, seed) in self.far_items[::2]:
            h = 6.5 * sc
            cr.move_to(x - 5 * sc, 0)
            cr.line_to(x - 0.9 * sc, h)
            cr.line_to(x + 0.9 * sc, h)
            cr.line_to(x + 5 * sc, 0)
            cr.close_path()
            cr.set_source_rgb(*mix(self.far, (0, 0, 0), 0.25))
            cr.fill()
            g = cairo.RadialGradient(x, h, 0, x, h, 2.5 * sc)
            g.add_color_stop_rgba(0, *self.acc, 0.8)
            g.add_color_stop_rgba(1, *self.acc, 0)
            cr.set_source(g)
            cr.arc(x, h, 2.5 * sc, 0, 2 * math.pi)
            cr.fill()
            for k in range(2):
                ox = (k - 0.5) * 0.6 * sc
                cr.move_to(x + ox, h)
                cr.curve_to(x + ox * 2, h * 0.7, x + ox * 3, h * 0.4, x + ox * 4.5, h * 0.1)
                cr.set_source_rgba(*self.acc, 0.6)
                cr.set_line_width(0.15)
                cr.stroke()
            for k in range(4):
                ph = (s * 0.15 + k / 4 + seed % 10 / 10) % 1
                cr.arc(x + math.sin(k + s * 0.3) * ph * 2, h + ph * 5, 0.6 + ph * 1.6, 0, 2 * math.pi)
                cr.set_source_rgba(0.2, 0.18, 0.18, 0.35 * (1 - ph))
                cr.fill()

    def _far_sea(self, cr, s, cam):
        hz = 1.4
        x0, x1 = cam.cx * 0.12 - 40, cam.cx * 0.12 + 40
        g = cairo.LinearGradient(0, hz, 0, -2)
        g.add_color_stop_rgb(0, *mix(self.far, self.sky_hor, 0.35))
        g.add_color_stop_rgb(1, *mix(self.far, (0, 0, 0), 0.3))
        cr.set_source(g)
        cr.rectangle(x0, -2, x1 - x0, hz + 2)
        cr.fill()
        cr.set_line_width(0.05)
        for k in range(9):
            y = hz - 0.18 * k - 0.1
            cr.set_source_rgba(*mix(self.sky_hor, (1, 1, 1), 0.4), 0.18 - 0.015 * k)
            off = (s * (0.3 + 0.05 * k)) % 2.0
            xx = x0 - off
            while xx < x1:
                cr.move_to(xx, y)
                cr.curve_to(xx + 0.3, y + 0.06, xx + 0.6, y + 0.06, xx + 0.9, y)
                xx += 2.0
            cr.stroke()
        for (x, sc, seed) in (self.far_items if self.a.get("ships") else []):
            sx = x + (s * 0.15 * (1 if seed % 2 else -1)) % 6 - 3
            self._ship_silhouette(cr, sx, hz - 0.05, 0.55 * sc, mix(self.far, (0, 0, 0), 0.5))

    def _ship_silhouette(self, cr, x, y, sc, col):
        cr.move_to(x - 2.2 * sc, y + 0.5 * sc)
        cr.line_to(x + 2.4 * sc, y + 0.5 * sc)
        cr.line_to(x + 1.8 * sc, y - 0.05)
        cr.line_to(x - 1.7 * sc, y - 0.05)
        cr.close_path()
        cr.set_source_rgb(*col)
        cr.fill()
        for mx, h in ((-0.9, 3.0), (0.4, 3.6), (1.5, 2.6)):
            cr.rectangle(x + mx * sc - 0.04, y + 0.4 * sc, 0.08, h * sc)
            cr.fill()
            for k in range(2):
                yy = y + (1.0 + k * 1.1) * sc
                cr.move_to(x + mx * sc - 0.6 * sc, yy + 0.9 * sc)
                cr.curve_to(x + mx * sc - 0.4 * sc, yy + 0.4 * sc, x + mx * sc + 0.4 * sc, yy + 0.4 * sc, x + mx * sc + 0.6 * sc, yy + 0.9 * sc)
                cr.line_to(x + mx * sc + 0.55 * sc, yy)
                cr.line_to(x + mx * sc - 0.55 * sc, yy)
                cr.close_path()
                cr.set_source_rgba(*mix(col, (1, 1, 1), 0.18), 1)
                cr.fill()
                cr.set_source_rgb(*col)

    def _far_cave(self, cr, s, cam):
        x0, x1 = cam.cx * 0.12 - 40, cam.cx * 0.12 + 40
        cr.set_source_rgb(*mix(self.far, (0, 0, 0), 0.2))
        cr.rectangle(x0, -2, x1 - x0, 20)
        cr.fill()
        r = random.Random(self.r_seed + 5)
        for k in range(46):
            x = x0 + k * 1.8 + r.uniform(-0.4, 0.4)
            h = r.uniform(1.5, 5.0)
            cr.move_to(x - 0.7, 12)
            cr.line_to(x, 12 - h)
            cr.line_to(x + 0.7, 12)
            cr.close_path()
            cr.set_source_rgb(*mix(self.mid, (0, 0, 0), 0.3))
            cr.fill()
            h2 = r.uniform(0.6, 2.5)
            cr.move_to(x - 0.5, 0)
            cr.line_to(x + 0.3, h2)
            cr.line_to(x + 0.8, 0)
            cr.close_path()
            cr.fill()
        g = cairo.RadialGradient(cam.cx * 0.12, 2, 0, cam.cx * 0.12, 2, 12)
        g.add_color_stop_rgba(0, *self.acc, 0.25)
        g.add_color_stop_rgba(1, *self.acc, 0)
        cr.set_source(g)
        cr.rectangle(x0, -2, x1 - x0, 20)
        cr.fill()

    def _far_clouds(self, cr, s, cam):
        r = random.Random(self.r_seed + 9)
        for k in range(30):
            x = -40 + k * 2.8 + r.uniform(-1, 1) + s * 0.08
            y = r.uniform(-0.5, 1.5)
            for j in range(3):
                cr.arc(x + j * 0.9, y + r.uniform(0, 0.6), r.uniform(0.9, 1.6), 0, 2 * math.pi)
            cr.set_source_rgba(*mix(self.far, (1, 1, 1), 0.5), 0.55)
            cr.fill()
        for (x, sc, seed) in self.far_items:
            y = 3.5 + 1.5 * math.sin(seed) + 0.25 * math.sin(s * 0.5 + seed)
            cr.move_to(x - 2 * sc, y)
            cr.line_to(x + 2 * sc, y)
            cr.line_to(x + 0.6 * sc, y - 2.2 * sc)
            cr.line_to(x - 0.4 * sc, y - 1.4 * sc)
            cr.close_path()
            cr.set_source_rgb(*self.far)
            cr.fill()
            cr.rectangle(x - 2 * sc, y, 4 * sc, 0.15)
            cr.set_source_rgba(*mix(self.far, (0.4, 0.8, 0.4), 0.4), 1)
            cr.fill()

    def _far_city(self, cr, s, cam):
        r = random.Random(self.r_seed + 3)
        x = -42.0
        while x < 42:
            w = r.uniform(1.2, 3.0)
            h = r.uniform(2.5, 9.0)
            cr.rectangle(x, -1, w, h + 1)
            cr.set_source_rgb(*self.far)
            cr.fill()
            for wy in range(int(h / 0.6)):
                for wx in range(int(w / 0.5)):
                    if r.random() < 0.35:
                        cr.rectangle(x + 0.15 + wx * 0.5, 0.3 + wy * 0.6, 0.18, 0.25)
                        cr.set_source_rgba(*mix(self.acc, (1, 0.9, 0.6), 0.5), 0.6 * (0.6 + 0.4 * stable_noise(int(x * 10) + wx, s * 0.3)))
                        cr.fill()
            x += w + r.uniform(0.1, 0.6)

    def _far_dunes(self, cr, s, cam):
        for k, (dy, a) in enumerate(((0.0, 1.0), (-0.6, 0.85))):
            cr.move_to(-42, -2)
            for i in range(85):
                x = -42 + i
                cr.line_to(x, 1.5 + dy + 1.2 * math.sin(x * 0.25 + k * 2) + 0.6 * math.sin(x * 0.6 + k))
            cr.line_to(42, -2)
            cr.close_path()
            cr.set_source_rgba(*mix(self.far, self.acc, 0.15 * k), a)
            cr.fill()

    def _far_forest(self, cr, s, cam):
        r = random.Random(self.r_seed + 4)
        self._far_mountains(cr, s, cam)
        for k in range(110):
            x = -42 + k * 0.78 + r.uniform(-0.2, 0.2)
            h = r.uniform(2.0, 4.0)
            cr.move_to(x - 0.6, 0)
            cr.line_to(x, h)
            cr.line_to(x + 0.6, 0)
            cr.close_path()
            cr.set_source_rgb(*mix(self.far, (0, 0, 0), 0.2 + 0.2 * (k % 2)))
            cr.fill()

    def _far_bamboo(self, cr, s, cam):
        r = random.Random(self.r_seed + 6)
        for k in range(120):
            x = -42 + k * 0.7 + r.uniform(-0.2, 0.2)
            sway = 0.15 * math.sin(s * 0.8 + k)
            cr.move_to(x, -1)
            cr.line_to(x + sway, 12)
            cr.set_source_rgb(*mix(self.far, (0, 0, 0), 0.15 * (k % 3)))
            cr.set_line_width(0.22)
            cr.stroke()
            for j in range(1, 8):
                cr.move_to(x - 0.13 + sway * j / 8, j * 1.4)
                cr.line_to(x + 0.13 + sway * j / 8, j * 1.4)
                cr.set_line_width(0.05)
                cr.stroke()

    def _far_castle(self, cr, s, cam):
        self._far_mountains(cr, s, cam)
        col = mix(self.far, (0, 0, 0), 0.15)
        cr.set_source_rgb(*col)
        cr.rectangle(-42, -1, 84, 4.5)
        cr.fill()
        for k in range(-42, 42):
            if k % 2 == 0:
                cr.rectangle(k + 0.1, 3.5, 0.6, 0.5)
                cr.fill()
        for (x, sc, seed) in self.far_items:
            w, h = 2.2 * sc, 8.0 * sc
            cr.rectangle(x - w / 2, -1, w, h)
            cr.fill()
            cr.move_to(x - w / 2 - 0.3, h - 1)
            cr.line_to(x, h + 2.5 * sc)
            cr.line_to(x + w / 2 + 0.3, h - 1)
            cr.close_path()
            cr.set_source_rgb(*mix(col, self.acc, 0.25))
            cr.fill()
            cr.set_source_rgba(*mix(self.acc, (1, 0.9, 0.6), 0.5), 0.7)
            cr.rectangle(x - 0.15, h * 0.6, 0.3, 0.6)
            cr.fill()
            cr.set_source_rgb(*col)

    def _far_dojo_wall(self, cr, s, cam):
        x0, x1 = cam.cx * 0.12 - 40, cam.cx * 0.12 + 40
        cr.set_source_rgb(*mix(self.mid, (0, 0, 0), 0.2))
        cr.rectangle(x0, -1, x1 - x0, 16)
        cr.fill()
        xx = math.floor(x0 / 3) * 3
        while xx < x1:
            cr.rectangle(xx + 0.15, 0.3, 2.7, 6.0)
            cr.set_source_rgb(*self.far)
            cr.fill()
            cr.set_source_rgba(*mix(self.mid, (0, 0, 0), 0.3), 1)
            cr.set_line_width(0.08)
            for gx in range(1, 4):
                cr.move_to(xx + 0.15 + gx * 0.675, 0.3)
                cr.line_to(xx + 0.15 + gx * 0.675, 6.3)
            for gy in range(1, 6):
                cr.move_to(xx + 0.15, 0.3 + gy * 1.0)
                cr.line_to(xx + 2.85, 0.3 + gy * 1.0)
            cr.stroke()
            xx += 3
        cr.set_source_rgb(*mix(self.mid, (0, 0, 0), 0.4))
        cr.rectangle(x0, 6.3, x1 - x0, 0.6)
        cr.fill()

    # ---- mid-ground props --------------------------------------------------
    def _fill(self, cr, col, a=1.0):
        cr.set_source_rgba(*col, a)
        cr.fill()

    def _prop_mast(self, cr, x, sc, seed, s):
        wood = mix(self.mid, (0.45, 0.3, 0.15), 0.5)
        cr.rectangle(x - 0.12, 0, 0.24, 9 * sc)
        self._fill(cr, wood)
        sail = mix((0.93, 0.88, 0.75), self.sky_hor, 0.25)
        billow = 0.25 * math.sin(s * 0.9 + seed)
        for k, (y0, w) in enumerate(((3.0, 2.4), (6.0, 1.9))):
            y0 *= sc
            cr.rectangle(x - w - 0.1, y0 + 2.2 * sc, 2 * w + 0.2, 0.1)
            self._fill(cr, wood)
            cr.move_to(x - w, y0 + 2.2 * sc)
            cr.line_to(x + w, y0 + 2.2 * sc)
            cr.curve_to(x + w + 0.3 + billow, y0 + 1.1 * sc, x + w + 0.3 + billow, y0 + 0.3 * sc, x + w * 1.05, y0)
            cr.line_to(x - w * 1.05, y0)
            cr.curve_to(x - w + 0.3 + billow, y0 + 0.3 * sc, x - w + 0.3 + billow, y0 + 1.1 * sc, x - w, y0 + 2.2 * sc)
            cr.close_path()
            self._fill(cr, sail, 0.95)
        cr.move_to(x, 9 * sc)
        cr.line_to(x + 0.9, 8.6 * sc + 0.1 * math.sin(s * 3))
        cr.line_to(x, 8.3 * sc)
        cr.close_path()
        self._fill(cr, (0.08, 0.08, 0.08))
        cr.arc(x + 0.35, 8.65 * sc, 0.09, 0, 2 * math.pi)
        self._fill(cr, (0.95, 0.95, 0.9))
        cr.set_source_rgba(*mix(wood, (0, 0, 0), 0.3), 0.8)
        cr.set_line_width(0.03)
        for k in range(4):
            cr.move_to(x, 8.5 * sc)
            cr.line_to(x - 3.5 + k * 0.4, 0)
            cr.move_to(x, 8.5 * sc)
            cr.line_to(x + 3.5 - k * 0.4, 0)
        cr.stroke()

    def _prop_rigging(self, cr, x, sc, seed, s):
        cr.set_source_rgba(*mix(self.mid, (0.6, 0.5, 0.3), 0.4), 0.85)
        cr.set_line_width(0.035)
        for k in range(5):
            cr.move_to(x - 0.6 + k * 0.3, 0)
            cr.line_to(x, 4.5 * sc)
        for j in range(1, 8):
            y = j * 0.55 * sc
            w = 0.6 * (1 - y / (4.5 * sc))
            cr.move_to(x - w, y)
            cr.line_to(x + w, y)
        cr.stroke()

    def _prop_cannon(self, cr, x, sc, seed, s):
        wood = mix(self.mid, (0.4, 0.25, 0.12), 0.5)
        cr.rectangle(x - 0.6, 0.2, 1.2, 0.35)
        self._fill(cr, wood)
        for wx in (-0.4, 0.4):
            cr.arc(x + wx, 0.22, 0.2, 0, 2 * math.pi)
            self._fill(cr, mix(wood, (0, 0, 0), 0.3))
        cr.save()
        cr.translate(x, 0.65)
        cr.rotate(0.18 if seed % 2 else math.pi - 0.18)
        cr.move_to(-0.3, -0.2)
        cr.line_to(1.1, -0.13)
        cr.line_to(1.1, 0.13)
        cr.line_to(-0.3, 0.2)
        cr.close_path()
        self._fill(cr, (0.16, 0.16, 0.18))
        cr.restore()

    def _prop_barrel(self, cr, x, sc, seed, s):
        wood = mix(self.mid, (0.5, 0.32, 0.15), 0.55)
        cr.move_to(x - 0.35, 0)
        cr.curve_to(x - 0.45, 0.4, x - 0.45, 0.7, x - 0.35, 1.0)
        cr.line_to(x + 0.35, 1.0)
        cr.curve_to(x + 0.45, 0.7, x + 0.45, 0.4, x + 0.35, 0)
        cr.close_path()
        self._fill(cr, wood)
        cr.set_source_rgba(0.2, 0.2, 0.22, 1)
        cr.set_line_width(0.06)
        for y in (0.2, 0.8):
            cr.move_to(x - 0.42, y)
            cr.line_to(x + 0.42, y)
        cr.stroke()

    def _prop_crate(self, cr, x, sc, seed, s):
        wood = mix(self.mid, (0.55, 0.38, 0.18), 0.5)
        cr.rectangle(x - 0.45, 0, 0.9, 0.9)
        self._fill(cr, wood)
        cr.set_source_rgba(*mix(wood, (0, 0, 0), 0.35), 1)
        cr.set_line_width(0.05)
        cr.rectangle(x - 0.45, 0, 0.9, 0.9)
        cr.move_to(x - 0.45, 0)
        cr.line_to(x + 0.45, 0.9)
        cr.stroke()

    def _prop_palm(self, cr, x, sc, seed, s):
        h = 5.5 * sc
        lean = 0.8 if seed % 2 else -0.8
        trunk = mix(self.mid, (0.45, 0.32, 0.18), 0.6)
        cr.move_to(x - 0.15, 0)
        cr.curve_to(x, h * 0.4, x + lean * 0.5, h * 0.8, x + lean, h)
        cr.set_source_rgb(*trunk)
        cr.set_line_width(0.3)
        cr.stroke()
        tx, ty = x + lean, h
        sway = 0.1 * math.sin(s * 1.2 + seed)
        for k in range(7):
            a = -0.3 + k * (math.pi + 0.6) / 6
            ex, ey = tx + math.cos(a) * 2.0, ty + math.sin(a) * 0.9 - 0.9 + sway
            cr.move_to(tx, ty)
            cr.curve_to(tx + math.cos(a) * 1.0, ty + 0.4, ex, ey + 0.6, ex, ey)
            cr.curve_to(ex - math.cos(a) * 0.4, ey + 0.2, tx + math.cos(a) * 0.8, ty + 0.1, tx, ty)
            cr.set_source_rgb(*mix(self.mid, (0.15, 0.5, 0.2), 0.6))
            cr.fill()

    def _prop_chest(self, cr, x, sc, seed, s):
        wood = (0.42, 0.26, 0.12)
        cr.rectangle(x - 0.5, 0, 1.0, 0.55)
        self._fill(cr, wood)
        cr.move_to(x - 0.5, 0.55)
        cr.curve_to(x - 0.5, 0.85, x + 0.5, 0.85, x + 0.5, 0.55)
        cr.close_path()
        self._fill(cr, mix(wood, (0, 0, 0), 0.2))
        cr.set_source_rgba(0.95, 0.78, 0.3, 1)
        cr.set_line_width(0.05)
        for xx in (x - 0.35, x + 0.35):
            cr.move_to(xx, 0)
            cr.line_to(xx, 0.8)
        cr.stroke()
        for k in range(5):
            gx = x - 0.3 + k * 0.15
            glint = 0.5 + 0.5 * math.sin(s * 4 + k + seed)
            cr.arc(gx, 0.85, 0.06, 0, 2 * math.pi)
            self._fill(cr, (1, 0.85 * glint + 0.1, 0.3))

    def _prop_gold_pile(self, cr, x, sc, seed, s):
        cr.move_to(x - 1.6 * sc, 0)
        cr.curve_to(x - 0.8, 1.1 * sc, x + 0.8, 1.1 * sc, x + 1.6 * sc, 0)
        cr.close_path()
        self._fill(cr, (0.85, 0.65, 0.2))
        r = random.Random(seed)
        for k in range(14):
            gx = x + r.uniform(-1.2, 1.2) * sc
            gy = r.uniform(0.05, 0.6) * sc * (1 - abs(gx - x) / (1.6 * sc))
            tw = 0.5 + 0.5 * math.sin(s * 5 + k * 1.7)
            cr.arc(gx, gy, 0.07, 0, 2 * math.pi)
            self._fill(cr, (1, 0.92, 0.5 * tw + 0.3))

    def _prop_torch(self, cr, x, sc, seed, s):
        cr.rectangle(x - 0.05, 0, 0.1, 2.0)
        self._fill(cr, (0.3, 0.2, 0.1))
        fl = 0.85 + 0.15 * stable_noise(seed % 1000, s * 8)
        g = cairo.RadialGradient(x, 2.2, 0, x, 2.2, 1.6)
        g.add_color_stop_rgba(0, 1, 0.8, 0.4, 0.5 * fl)
        g.add_color_stop_rgba(1, 1, 0.5, 0.1, 0)
        cr.set_source(g)
        cr.arc(x, 2.2, 1.6, 0, 2 * math.pi)
        cr.fill()
        cr.move_to(x - 0.12, 2.0)
        cr.curve_to(x - 0.1, 2.3 * fl, x, 2.5 * fl, x, 2.55 * fl)
        cr.curve_to(x + 0.05, 2.35, x + 0.12, 2.2, x + 0.12, 2.0)
        cr.close_path()
        self._fill(cr, (1, 0.7, 0.2))

    def _prop_bones(self, cr, x, sc, seed, s):
        bone = (0.9, 0.86, 0.75)
        cr.set_source_rgba(*bone, 0.9)
        cr.set_line_width(0.1)
        for k in range(5):
            a = 0.5 + k * 0.25
            cr.arc(x, 0, 1.0 * sc, a, a + 0.12)
            cr.stroke()
            cr.move_to(x + math.cos(a) * 0.3, 0.0)
            cr.line_to(x + math.cos(a) * sc, math.sin(a) * sc)
            cr.stroke()
        cr.arc(x + 1.3 * sc, 0.25, 0.25 * sc, 0, 2 * math.pi)
        self._fill(cr, bone)

    def _prop_rock_spire(self, cr, x, sc, seed, s):
        h = 4.5 * sc
        cr.move_to(x - 0.9 * sc, 0)
        cr.line_to(x - 0.1, h)
        cr.line_to(x + 0.25, h * 0.85)
        cr.line_to(x + 0.9 * sc, 0)
        cr.close_path()
        self._fill(cr, self.mid)

    _prop_rock = _prop_rock_spire

    def _prop_lava_fall(self, cr, x, sc, seed, s):
        self._prop_rock_spire(cr, x, sc * 1.2, seed, s)
        for k in range(3):
            off = ((s * 1.5 + k / 3) % 1)
            cr.move_to(x - 0.05, 5 * sc)
            cr.curve_to(x + 0.2, 3 * sc, x - 0.1, 1.5 * sc, x + 0.05, 0)
            cr.set_source_rgba(*mix(self.acc, (1, 0.9, 0.4), off), 0.8)
            cr.set_line_width(0.2 - 0.05 * k)
            cr.stroke()

    def _prop_floating_rock(self, cr, x, sc, seed, s):
        y = 3.0 + (seed % 5) * 0.4 + 0.25 * math.sin(s * 0.7 + seed)
        cr.move_to(x - 1.0 * sc, y)
        cr.line_to(x + 1.0 * sc, y)
        cr.line_to(x + 0.3 * sc, y - 1.2 * sc)
        cr.line_to(x - 0.4 * sc, y - 0.8 * sc)
        cr.close_path()
        self._fill(cr, self.mid)
        cr.rectangle(x - 1.0 * sc, y, 2.0 * sc, 0.12)
        self._fill(cr, mix(self.mid, self.acc, 0.35))

    def _prop_crystals(self, cr, x, sc, seed, s):
        r = random.Random(seed)
        for j in range(3):
            h = r.uniform(2, 4.5) * sc
            ox = r.uniform(-0.8, 0.8)
            cr.move_to(x + ox - 0.35, 0)
            cr.line_to(x + ox, h)
            cr.line_to(x + ox + 0.35, 0)
            cr.close_path()
            self._fill(cr, mix(self.mid, self.acc, 0.3), 0.95)

    def _prop_column(self, cr, x, sc, seed, s):
        h = 4.2 * sc * (0.55 if seed % 3 == 0 else 1.0)
        cr.rectangle(x - 0.3, 0, 0.6, h)
        cr.rectangle(x - 0.5, h, 1.0, 0.3)
        cr.rectangle(x - 0.5, 0, 1.0, 0.25)
        self._fill(cr, self.mid)

    def _prop_arch(self, cr, x, sc, seed, s):
        h, w = 4.0 * sc, 1.6 * sc
        cr.rectangle(x - w, 0, 0.3, h)
        cr.rectangle(x + w - 0.3, 0, 0.3, h)
        cr.rectangle(x - w - 0.5, h, 2 * w + 1.0, 0.35)
        cr.rectangle(x - w - 0.2, h - 0.8, 2 * w + 0.4, 0.2)
        self._fill(cr, self.mid)

    def _prop_monolith(self, cr, x, sc, seed, s):
        h = (2.5 + seed % 3) * sc
        cr.move_to(x - 0.5, 0)
        cr.line_to(x - 0.4, h)
        cr.line_to(x + 0.45, h * 0.95)
        cr.line_to(x + 0.5, 0)
        cr.close_path()
        self._fill(cr, self.mid)
        cr.rectangle(x - 0.05, h * 0.3, 0.1, h * 0.4)
        self._fill(cr, self.acc, 0.35 + 0.2 * math.sin(s * 2 + seed))

    def _prop_lantern(self, cr, x, sc, seed, s):
        y = 2.6 + 0.08 * math.sin(s * 1.5 + seed)
        cr.move_to(x, 6)
        cr.line_to(x, y + 0.45)
        cr.set_source_rgba(*INK, 0.8)
        cr.set_line_width(0.03)
        cr.stroke()
        g = cairo.RadialGradient(x, y, 0, x, y, 1.4)
        g.add_color_stop_rgba(0, 1, 0.7, 0.35, 0.45)
        g.add_color_stop_rgba(1, 1, 0.5, 0.2, 0)
        cr.set_source(g)
        cr.arc(x, y, 1.4, 0, 2 * math.pi)
        cr.fill()
        cr.save()
        cr.translate(x, y)
        cr.scale(0.7, 1)
        cr.arc(0, 0, 0.42, 0, 2 * math.pi)
        cr.restore()
        self._fill(cr, (0.95, 0.35, 0.2) if seed % 2 else (1, 0.85, 0.55))

    def _prop_paper_screen(self, cr, x, sc, seed, s):
        cr.rectangle(x - 1.0, 0, 2.0, 2.6)
        self._fill(cr, mix(self.far, (1, 1, 1), 0.2), 0.9)
        cr.set_source_rgba(*mix(self.mid, (0, 0, 0), 0.2), 1)
        cr.set_line_width(0.06)
        cr.rectangle(x - 1.0, 0, 2.0, 2.6)
        for k in range(1, 4):
            cr.move_to(x - 1.0 + k * 0.5, 0)
            cr.line_to(x - 1.0 + k * 0.5, 2.6)
        cr.stroke()

    def _prop_bamboo(self, cr, x, sc, seed, s):
        for k in range(3):
            xx = x + (k - 1) * 0.35
            sway = 0.2 * math.sin(s * 0.9 + seed + k)
            cr.move_to(xx, 0)
            cr.line_to(xx + sway, 8)
            cr.set_source_rgb(*mix(self.mid, (0.3, 0.6, 0.3), 0.4))
            cr.set_line_width(0.16)
            cr.stroke()

    def _prop_chimney(self, cr, x, sc, seed, s):
        cr.rectangle(x - 0.4, 0, 0.8, 2.0 * sc)
        self._fill(cr, self.mid)
        for k in range(3):
            ph = (s * 0.3 + k / 3) % 1
            cr.arc(x + ph * 0.8, 2.0 * sc + ph * 2.5, 0.3 + ph * 0.6, 0, 2 * math.pi)
            self._fill(cr, (0.5, 0.5, 0.55), 0.25 * (1 - ph))

    def _prop_antenna(self, cr, x, sc, seed, s):
        cr.move_to(x, 0)
        cr.line_to(x, 4 * sc)
        cr.set_source_rgb(*self.mid)
        cr.set_line_width(0.07)
        cr.stroke()
        on = (s * 1.2 + seed % 7) % 1 < 0.5
        cr.arc(x, 4 * sc, 0.09, 0, 2 * math.pi)
        self._fill(cr, (1, 0.2, 0.2) if on else (0.4, 0.1, 0.1))

    def _prop_banner(self, cr, x, sc, seed, s):
        cr.rectangle(x - 0.05, 0, 0.1, 5 * sc)
        self._fill(cr, (0.3, 0.2, 0.1))
        wave = 0.15 * math.sin(s * 2.5 + seed)
        cr.move_to(x + 0.05, 5 * sc)
        cr.curve_to(x + 0.6, 5 * sc + wave, x + 1.0, 5 * sc - wave, x + 1.4, 5 * sc)
        cr.line_to(x + 1.2, 3.2 * sc)
        cr.line_to(x + 0.05, 3.2 * sc)
        cr.close_path()
        self._fill(cr, mix(self.acc, (0.7, 0.1, 0.1), 0.5))

    def _prop_tent(self, cr, x, sc, seed, s):
        sc *= 0.65
        cr.move_to(x - 1.5 * sc, 0)
        cr.line_to(x, 2.8 * sc)
        cr.line_to(x + 1.5 * sc, 0)
        cr.close_path()
        self._fill(cr, (0.85, 0.2, 0.2) if seed % 2 else (0.25, 0.35, 0.8))
        for k in range(3):
            cr.move_to(x - 1.5 * sc + k * sc, 0)
            cr.line_to(x, 2.8 * sc)
        cr.set_source_rgba(1, 1, 1, 0.5)
        cr.set_line_width(0.06)
        cr.stroke()

    def _prop_tree(self, cr, x, sc, seed, s):
        cr.rectangle(x - 0.12, 0, 0.24, 2.6 * sc)
        self._fill(cr, self.mid)
        r = random.Random(seed)
        for j in range(4):
            cr.arc(x + r.uniform(-0.8, 0.8), 2.6 * sc + r.uniform(0, 1.2), r.uniform(0.7, 1.2) * sc, 0, 2 * math.pi)
            self._fill(cr, self.mid)

    def _prop_mushroom(self, cr, x, sc, seed, s):
        cr.rectangle(x - 0.12, 0, 0.24, 1.3 * sc)
        self._fill(cr, (0.85, 0.82, 0.75))
        cr.arc(x, 1.3 * sc, 0.75 * sc, 0, math.pi)
        self._fill(cr, mix(self.acc, (0.9, 0.2, 0.5), 0.5), 0.9 + 0.1 * math.sin(s * 2 + seed))

    # ----------------------------------------------------------------- ground
    def draw_ground(self, cr, cam, s):
        style = self.a["ground_style"]
        x0, x1 = cam.cx - 12, cam.cx + 12
        g = cairo.LinearGradient(0, 0, 0, -6)
        g.add_color_stop_rgb(0, *mix(self.gcol, self.acc, 0.08))
        g.add_color_stop_rgb(1, *mix(self.gcol, (0, 0, 0), 0.55))
        cr.set_source(g)
        cr.rectangle(x0, -8, x1 - x0, 8)
        cr.fill()
        getattr(self, "_ground_" + style, self._ground_stone)(cr, cam, s, x0, x1)
        # perspective guide lines keep camera motion readable on every floor
        cr.set_line_width(0.015)
        start = math.floor(x0)
        for i in range(int(x1 - x0) + 2):
            x = start + i
            cr.set_source_rgba(*self.acc, 0.05 if x % 2 else 0.09)
            cr.move_to(x, 0)
            cr.line_to(cam.cx + (x - cam.cx) * 2.4, -5)
            cr.stroke()
        cr.set_source_rgba(*mix(self.acc, (1, 1, 1), 0.3), 0.5)
        cr.set_line_width(0.035)
        cr.move_to(x0, 0)
        cr.line_to(x1, 0)
        cr.stroke()
        for side in (-1, 1):
            x = side * HALF
            g = cairo.LinearGradient(0, 0, 0, 3.0)
            g.add_color_stop_rgba(0, *self.acc, 0.5)
            g.add_color_stop_rgba(1, *self.acc, 0.0)
            cr.set_source(g)
            cr.rectangle(x - 0.06, 0, 0.12, 3.0)
            cr.fill()

    def _ground_planks(self, cr, cam, s, x0, x1):
        dark = mix(self.gcol, (0, 0, 0), 0.4)
        cr.set_line_width(0.025)
        rows = [-0.18, -0.42, -0.75, -1.2, -1.8, -2.6, -3.6]
        for i, y in enumerate(rows):
            cr.set_source_rgba(*dark, 0.8)
            cr.move_to(x0, y)
            cr.line_to(x1, y)
            cr.stroke()
            off = 0.8 * (i % 2)
            xx = math.floor((x0 - off) / 1.6) * 1.6 + off
            prev = rows[i - 1] if i else 0.0
            while xx < x1:
                cr.move_to(cam.cx + (xx - cam.cx) * (1 + 0.35 * -prev), prev)
                cr.line_to(cam.cx + (xx - cam.cx) * (1 + 0.35 * -y), y)
                cr.stroke()
                xx += 1.6
        # ship railing behind the fighters
        wood = mix(self.gcol, (0, 0, 0), 0.15)
        xx = math.floor(x0 / 1.2) * 1.2
        while xx < x1:
            cr.rectangle(xx - 0.05, 0, 0.1, 0.85)
            cr.set_source_rgba(*wood, 0.75)
            cr.fill()
            xx += 1.2
        cr.rectangle(x0, 0.8, x1 - x0, 0.1)
        cr.set_source_rgba(*mix(wood, self.acc, 0.1), 0.85)
        cr.fill()

    def _ground_sand(self, cr, cam, s, x0, x1):
        cr.set_line_width(0.02)
        for k in range(6):
            y = -0.3 - k * 0.55
            cr.set_source_rgba(*mix(self.gcol, (1, 1, 1), 0.2), 0.35)
            cr.move_to(x0, y)
            xx = x0
            while xx < x1:
                cr.curve_to(xx + 0.4, y + 0.06, xx + 0.8, y - 0.06, xx + 1.2, y)
                xx += 1.2
            cr.stroke()

    def _ground_stone(self, cr, cam, s, x0, x1):
        dark = mix(self.gcol, (0, 0, 0), 0.4)
        cr.set_line_width(0.022)
        cr.set_source_rgba(*dark, 0.7)
        for y in (-0.35, -0.9, -1.8, -3.0):
            cr.move_to(x0, y)
            cr.line_to(x1, y)
        cr.stroke()

    def _ground_lava(self, cr, cam, s, x0, x1):
        r = random.Random(self.r_seed + 77)
        pulse = 0.6 + 0.4 * math.sin(s * 2.2)
        cr.set_line_width(0.04)
        for k in range(40):
            x = math.floor(x0) + r.uniform(0, x1 - x0)
            y = -r.uniform(0.1, 3.0)
            cr.move_to(x, y)
            for j in range(3):
                x += r.uniform(-0.5, 0.5)
                y -= r.uniform(0.05, 0.3)
                cr.line_to(x, y)
            cr.set_source_rgba(*self.acc, 0.55 * pulse)
            cr.stroke()

    def _ground_ice(self, cr, cam, s, x0, x1):
        for k in range(8):
            xx = math.floor(x0) + k * 3.1
            cr.move_to(xx, -0.1)
            cr.line_to(xx + 1.2, -0.9)
            cr.set_source_rgba(1, 1, 1, 0.18)
            cr.set_line_width(0.08)
            cr.stroke()

    def _ground_grass(self, cr, cam, s, x0, x1):
        cr.set_line_width(0.025)
        col = mix(self.gcol, (0.4, 0.8, 0.3), 0.4)
        xx = math.floor(x0 * 6) / 6
        while xx < x1:
            sway = 0.04 * math.sin(s * 2 + xx * 3)
            cr.move_to(xx, 0)
            cr.line_to(xx + sway, 0.12 + 0.06 * abs(math.sin(xx * 7.3)))
            xx += 1 / 6
        cr.set_source_rgba(*col, 0.8)
        cr.stroke()

    def _ground_tatami(self, cr, cam, s, x0, x1):
        dark = mix(self.gcol, (0.2, 0.15, 0.05), 0.5)
        cr.set_line_width(0.05)
        cr.set_source_rgba(*dark, 0.8)
        xx = math.floor(x0 / 1.8) * 1.8
        while xx < x1:
            cr.move_to(xx, 0)
            cr.line_to(cam.cx + (xx - cam.cx) * 2.4, -5)
            xx += 1.8
        for y in (-0.6, -1.8):
            cr.move_to(x0, y)
            cr.line_to(x1, y)
        cr.stroke()

    def _ground_tiles(self, cr, cam, s, x0, x1):
        dark = mix(self.gcol, (0, 0, 0), 0.4)
        cr.set_line_width(0.03)
        for k in range(5):
            y = -0.2 - k * 0.45
            cr.set_source_rgba(*dark, 0.8)
            xx = math.floor(x0 / 0.4) * 0.4
            cr.move_to(xx, y)
            while xx < x1:
                cr.curve_to(xx + 0.1, y - 0.12, xx + 0.3, y - 0.12, xx + 0.4, y)
                xx += 0.4
            cr.stroke()

    def _ground_metal(self, cr, cam, s, x0, x1):
        cr.set_line_width(0.02)
        xx = math.floor(x0 / 2) * 2
        while xx < x1:
            cr.set_source_rgba(*self.acc, 0.2)
            cr.move_to(xx, 0)
            cr.line_to(xx, -0.5)
            cr.stroke()
            for y in (-0.1, -0.4):
                cr.arc(xx + 0.2, y, 0.025, 0, 2 * math.pi)
                cr.fill()
            xx += 2

    # ----------------------------------------------------------------- weather
    def ambient(self, cr, cam, s):
        kind = self.a.get("ambient", "motes")
        rr = random.Random(7)
        x0 = cam.cx - 7
        for k in range(46):
            bx = rr.uniform(0, 14)
            by = rr.uniform(0, 8)
            sp = rr.uniform(0.3, 1.0)
            col = self.acc
            if kind in ("ember", "bubbles", "motes"):
                y = (by + s * sp * 0.8) % 8
                x = x0 + (bx + 0.3 * math.sin(s * sp + k)) % 14
            elif kind == "snow":
                y = 8 - (by + s * sp * 0.7) % 8
                x = x0 + (bx + 0.4 * math.sin(s * 0.7 * sp + k) + s * 0.2) % 14
                col = (1, 1, 1)
            elif kind == "rain":
                y = 8 - (by + s * 9 * sp) % 8
                x = x0 + (bx - s * 1.5) % 14
                cr.set_source_rgba(0.7, 0.8, 1, 0.25)
                cr.set_line_width(0.012)
                cr.move_to(x, y)
                cr.line_to(x + 0.05, y + 0.35)
                cr.stroke()
                continue
            elif kind == "spray":
                y = (by * 0.4 + (s * sp * 1.5) % 3)
                x = x0 + (bx + s * 0.8 * sp) % 14
                col = (0.9, 0.95, 1.0)
            elif kind == "leaves":
                y = 8 - (by + s * sp * 0.5) % 8
                x = x0 + (bx + s * 0.4 * sp) % 14
            else:
                y = by + 0.2 * math.sin(s * sp + k)
                x = x0 + (bx + s * 0.3 * sp) % 14
            cr.set_source_rgba(*col, 0.22 + 0.3 * sp)
            cr.arc(x, y, 0.02 + 0.025 * sp, 0, 2 * math.pi)
            cr.fill()
