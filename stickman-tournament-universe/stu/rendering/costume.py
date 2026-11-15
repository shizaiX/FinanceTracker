"""Procedural costume parts (hats, eyepatches, hook hands, peg legs, wings,
tails, capes, ...). Head parts are drawn in a head-local frame (y = neck axis,
x = facing direction), so they tilt with the head and mirror with facing.
Trailing parts (tails, capes, bandana knots) use the fighter's motion history
for secondary motion.
"""
from __future__ import annotations

import math

import cairo

from ..animation.rig import HEAD_R, J
from ..core.mathutil import mix

INK = (0.02, 0.02, 0.04)
GOLD = (0.95, 0.78, 0.3)
WOOD = (0.55, 0.36, 0.18)
STEEL = (0.78, 0.82, 0.88)
BACK_PARTS = {"wings", "tail", "cape", "back_spikes"}


def _frame(cr, origin, axis_from, facing):
    ox, oy = origin
    dx, dy = ox - axis_from[0], oy - axis_from[1]
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    fx, fy = facing * uy, -facing * ux
    cr.transform(cairo.Matrix(fx, fy, ux, uy, ox, oy))


def _fill(cr, col, a=1.0, outline=0.02):
    if outline:
        cr.set_source_rgba(*INK, 0.9)
        cr.set_line_width(outline)
        cr.stroke_preserve()
    cr.set_source_rgba(*col, a)
    cr.fill()


def _stroke(cr, col, w, a=1.0):
    cr.set_source_rgba(*col, a)
    cr.set_line_width(w)
    cr.stroke()


def draw_back(cr, parts, P, facing, t, col, sec, history):
    """Parts behind the body. history(joint, k) -> past world position."""
    hip, chest = P[J["hip"]], P[J["chest"]]
    dark = mix(col, (0, 0, 0), 0.45)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if "cape" in parts:
        pts = [(chest[0] - facing * 0.05, chest[1] - 0.02)]
        for k in range(1, 6):
            hx, hy = history("chest", k)
            pts.append((chest[0] - facing * (0.1 + 0.07 * k) + (hx - chest[0]) * 0.6,
                        chest[1] - 0.13 * k + (hy - chest[1]) * 0.6 + 0.02 * math.sin(t * 7 + k)))
        cr.move_to(chest[0] + facing * 0.04, chest[1])
        for q in pts:
            cr.line_to(*q)
        cr.line_to(pts[-1][0] + facing * 0.18, pts[-1][1] + 0.02)
        cr.line_to(hip[0] + facing * 0.02, hip[1] + 0.1)
        cr.close_path()
        _fill(cr, mix(sec, (0, 0, 0), 0.25), 0.95)
    if "wings" in parts:
        flap = math.sin(t * 5.0) * 0.25
        cr.save()
        _frame(cr, chest, hip, facing)
        for depth, a in ((1, 0.9), (0, 1.0)):
            off = -0.05 * depth
            bones = [(-0.05 + off, 0.0), (-0.45 + off, 0.35 + flap), (-0.85 + off, 0.25 + flap * 1.4), (-1.05 + off, -0.05 + flap)]
            cr.move_to(*bones[0])
            cr.line_to(*bones[1])
            cr.line_to(*bones[2])
            cr.line_to(*bones[3])
            cr.curve_to(-0.8 + off, -0.15, -0.7 + off, 0.0, -0.6 + off, -0.12)
            cr.curve_to(-0.45 + off, -0.02, -0.35 + off, -0.12, -0.25 + off, -0.18)
            cr.close_path()
            _fill(cr, mix(sec, dark, 0.5 * depth), 0.85 * a)
            for b in bones[1:]:
                cr.move_to(*bones[0])
                cr.line_to(*b)
                _stroke(cr, dark, 0.03, a)
        cr.restore()
    if "tail" in parts:
        pts = [hip]
        for k in range(1, 8):
            hx, hy = history("hip", k * 2)
            sway = 0.06 * math.sin(t * 4 + k * 0.7)
            pts.append((hip[0] - facing * 0.13 * k + (hx - hip[0]) * 0.7, hip[1] - 0.06 * k + 0.012 * k * k + sway + (hy - hip[1]) * 0.5))
        for k in range(len(pts) - 1):
            cr.move_to(*pts[k])
            cr.line_to(*pts[k + 1])
            _stroke(cr, INK, 0.11 * (1 - k / 9) + 0.03, 0.9)
            cr.move_to(*pts[k])
            cr.line_to(*pts[k + 1])
            _stroke(cr, col, 0.08 * (1 - k / 9) + 0.015)
        ex, ey = pts[-1]
        px, py = pts[-2]
        a = math.atan2(ey - py, ex - px)
        cr.move_to(ex + math.cos(a) * 0.14, ey + math.sin(a) * 0.14)
        cr.line_to(ex + math.cos(a + 1.9) * 0.08, ey + math.sin(a + 1.9) * 0.08)
        cr.line_to(ex + math.cos(a - 1.9) * 0.08, ey + math.sin(a - 1.9) * 0.08)
        cr.close_path()
        _fill(cr, sec)
    if "back_spikes" in parts:
        for k in range(4):
            u = 0.15 + 0.22 * k
            bx, by = hip[0] + (chest[0] - hip[0]) * u, hip[1] + (chest[1] - hip[1]) * u
            dx, dy = chest[0] - hip[0], chest[1] - hip[1]
            n = math.hypot(dx, dy) or 1
            nx, ny = -facing * dy / n, facing * dx / n  # points away from facing
            nx, ny = -nx, -ny
            cr.move_to(bx + dx / n * 0.05, by + dy / n * 0.05)
            cr.line_to(bx - nx * 0.14, by - ny * 0.14)
            cr.line_to(bx - dx / n * 0.06, by - dy / n * 0.06)
            cr.close_path()
            _fill(cr, sec, 1.0, 0.015)


def draw_limb_overrides(cr, parts, P, facing, col):
    """Hook hands and peg legs replace the back hand / back shin."""
    if "peg_leg" in parts:
        k, f = P[J["knee_b"]], P[J["foot_b"]]
        cr.set_line_cap(cairo.LINE_CAP_BUTT)
        cr.move_to(*k)
        cr.line_to(*f)
        _stroke(cr, INK, 0.12)
        cr.move_to(*k)
        cr.line_to(*f)
        _stroke(cr, WOOD, 0.08)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.arc(k[0], k[1], 0.06, 0, 2 * math.pi)
        _fill(cr, mix(WOOD, (0, 0, 0), 0.3))
    if "hook_hand" in parts:
        h, e = P[J["hand_b"]], P[J["elbow_b"]]
        cr.save()
        _frame(cr, h, e, facing)
        cr.rectangle(-0.06, -0.045, 0.07, 0.09)
        _fill(cr, (0.25, 0.18, 0.12))
        cr.move_to(0.0, 0.0)
        cr.line_to(0.1, 0.0)
        cr.arc(0.1, -0.06, 0.06, math.pi / 2, math.pi * 2.0)
        _stroke(cr, INK, 0.045)
        cr.move_to(0.0, 0.0)
        cr.line_to(0.1, 0.0)
        cr.arc(0.1, -0.06, 0.06, math.pi / 2, math.pi * 2.0)
        _stroke(cr, STEEL, 0.026)
        cr.restore()


def draw_front(cr, parts, P, facing, t, col, sec, history):
    head, chest = P[J["head"]], P[J["chest"]]
    R = HEAD_R
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if "parrot" in parts:
        cr.save()
        _frame(cr, chest, P[J["hip"]], facing)
        bob = 0.015 * math.sin(t * 6)
        cr.translate(-0.12, 0.08 + bob)
        cr.save()
        cr.scale(0.7, 1)
        cr.arc(0, 0.06, 0.075, 0, 2 * math.pi)
        cr.restore()
        _fill(cr, (0.9, 0.15, 0.12))
        cr.arc(0.02, 0.15, 0.05, 0, 2 * math.pi)
        _fill(cr, (0.95, 0.2, 0.15))
        cr.move_to(0.06, 0.16)
        cr.line_to(0.11, 0.13)
        cr.line_to(0.06, 0.12)
        cr.close_path()
        _fill(cr, (1, 0.85, 0.2), 1, 0.01)
        cr.move_to(-0.03, 0.02)
        cr.line_to(-0.08, -0.12)
        _stroke(cr, (0.1, 0.5, 0.95), 0.04)
        cr.restore()
    cr.save()
    _frame(cr, head, chest, facing)
    for p in parts:
        if p == "tricorne":
            cr.move_to(-0.24, 0.06)
            cr.curve_to(-0.1, 0.13, 0.12, 0.13, 0.26, 0.05)
            cr.curve_to(0.18, 0.28, -0.16, 0.3, -0.24, 0.06)
            cr.close_path()
            _fill(cr, (0.1, 0.08, 0.08))
            cr.move_to(-0.22, 0.08)
            cr.curve_to(-0.1, 0.14, 0.12, 0.14, 0.24, 0.07)
            _stroke(cr, GOLD, 0.02)
            _skull(cr, 0.0, 0.18)
        elif p == "captain_hat":
            cr.move_to(-0.3, 0.07)
            cr.curve_to(-0.15, 0.36, 0.15, 0.36, 0.3, 0.07)
            cr.curve_to(0.1, 0.13, -0.1, 0.13, -0.3, 0.07)
            cr.close_path()
            _fill(cr, (0.12, 0.08, 0.1))
            cr.move_to(-0.05, 0.22)
            cr.curve_to(-0.15, 0.42, -0.35, 0.42, -0.42, 0.3)
            _stroke(cr, sec, 0.05)
            _skull(cr, 0.02, 0.17)
        elif p == "bandana":
            cr.arc(0, 0, R + 0.012, math.radians(-10), math.radians(190))
            cr.close_path()
            _fill(cr, sec)
            for k in range(3):
                cr.arc(-0.05 + 0.05 * k, 0.07, 0.012, 0, 2 * math.pi)
                cr.set_source_rgba(1, 1, 1, 0.8)
                cr.fill()
            kx, ky = -R, 0.0
            hx, hy = history("head", 3)
            lag = (hy - head[1]) * 0.5
            cr.move_to(kx, ky)
            cr.line_to(kx - 0.12, ky - 0.06 + lag)
            cr.move_to(kx, ky)
            cr.line_to(kx - 0.1, ky - 0.13 + lag)
            _stroke(cr, sec, 0.035)
        elif p == "straw_hat":
            cr.save()
            cr.translate(0, 0.1)
            cr.scale(1, 0.18)
            cr.arc(0, 0, 0.3, 0, 2 * math.pi)
            cr.restore()
            _fill(cr, (0.92, 0.8, 0.45))
            cr.arc(0, 0.12, 0.12, 0, math.pi)
            _fill(cr, (0.92, 0.8, 0.45))
            cr.move_to(-0.11, 0.12)
            cr.line_to(0.11, 0.12)
            _stroke(cr, (0.85, 0.15, 0.15), 0.03)
        elif p == "ninja_mask":
            cr.arc(0, 0, R + 0.005, math.radians(170), math.radians(370))
            cr.close_path()
            _fill(cr, (0.08, 0.08, 0.12))
            cr.arc(0, 0, R + 0.005, math.radians(60), math.radians(150))
            cr.line_to(0, 0)
            cr.close_path()
            _fill(cr, (0.08, 0.08, 0.12), 1, 0)
            cr.move_to(-R, 0.05)
            cr.line_to(-R - 0.14, 0.0)
            _stroke(cr, sec, 0.03)
        elif p == "knight_helm":
            cr.move_to(-R - 0.02, -R)
            cr.line_to(-R - 0.02, 0.06)
            cr.curve_to(-R, R + 0.06, R, R + 0.06, R + 0.03, 0.06)
            cr.line_to(R + 0.03, -R + 0.02)
            cr.close_path()
            _fill(cr, STEEL)
            cr.move_to(0.0, 0.02)
            cr.line_to(R + 0.02, 0.02)
            _stroke(cr, INK, 0.025)
            cr.move_to(0.02, -0.05)
            cr.line_to(R + 0.02, -0.05)
            _stroke(cr, INK, 0.012)
        elif p == "plume":
            cr.move_to(0, R + 0.03)
            cr.curve_to(-0.05, R + 0.25, -0.25, R + 0.2, -0.32, R + 0.05)
            _stroke(cr, INK, 0.08)
            cr.move_to(0, R + 0.03)
            cr.curve_to(-0.05, R + 0.25, -0.25, R + 0.2, -0.32, R + 0.05)
            _stroke(cr, sec, 0.055)
        elif p == "crown":
            cr.move_to(-0.11, R - 0.01)
            for k, x in enumerate((-0.11, -0.07, -0.04, 0.0, 0.04, 0.07, 0.11)):
                cr.line_to(x, R + (0.11 if k % 2 == 0 else 0.03))
            cr.line_to(0.11, R - 0.01)
            cr.close_path()
            _fill(cr, GOLD)
        elif p == "wizard_hat":
            cr.move_to(-0.24, 0.07)
            cr.line_to(0.24, 0.07)
            _stroke(cr, INK, 0.07)
            cr.move_to(-0.24, 0.07)
            cr.line_to(0.24, 0.07)
            _stroke(cr, sec, 0.045)
            cr.move_to(-0.13, 0.09)
            cr.curve_to(-0.08, 0.3, -0.05, 0.45, -0.22, 0.52 + 0.02 * math.sin(t * 3))
            cr.curve_to(0.0, 0.42, 0.08, 0.25, 0.13, 0.09)
            cr.close_path()
            _fill(cr, sec)
            _star(cr, 0.0, 0.2, 0.04, GOLD)
        elif p == "horned_helmet":
            cr.arc(0, 0.01, R + 0.02, 0, math.pi)
            cr.close_path()
            _fill(cr, STEEL)
            for d in (-1, 1):
                cr.move_to(d * 0.1, 0.08)
                cr.curve_to(d * 0.2, 0.12, d * 0.24, 0.22, d * 0.2, 0.32)
                cr.curve_to(d * 0.18, 0.22, d * 0.14, 0.15, d * 0.07, 0.12)
                cr.close_path()
                _fill(cr, (0.96, 0.92, 0.82))
        elif p == "cowboy_hat":
            cr.move_to(-0.27, 0.12)
            cr.curve_to(-0.1, 0.05, 0.1, 0.05, 0.27, 0.12)
            _stroke(cr, INK, 0.07)
            cr.move_to(-0.27, 0.12)
            cr.curve_to(-0.1, 0.05, 0.1, 0.05, 0.27, 0.12)
            _stroke(cr, (0.55, 0.36, 0.2), 0.045)
            cr.rectangle(-0.11, 0.08, 0.22, 0.13)
            _fill(cr, (0.55, 0.36, 0.2))
        elif p == "hood":
            cr.arc(0, 0.0, R + 0.06, math.radians(-60), math.radians(240))
            cr.curve_to(-0.22, -0.2, -0.1, -0.22, 0.0, -0.18)
            cr.close_path()
            _fill(cr, mix(sec, (0, 0, 0), 0.35))
            cr.arc(0.03, -0.01, R - 0.01, 0, 2 * math.pi)
            cr.set_source_rgba(*mix(col, (1, 1, 1), 0.12), 1)
            cr.fill()
        elif p == "dragon_horns":
            for d, sc in ((-1, 1.0), (1, 0.8)):
                cr.move_to(-0.02 + d * 0.04, 0.1)
                cr.curve_to(-0.15 + d * 0.03, 0.22 * sc, -0.3, 0.3 * sc, -0.42, 0.24 * sc)
                cr.curve_to(-0.28, 0.22 * sc, -0.17, 0.15, -0.08 + d * 0.04, 0.05)
                cr.close_path()
                _fill(cr, mix(sec, (1, 1, 1), 0.2))
            cr.move_to(R - 0.02, 0.04)
            cr.line_to(R + 0.08, 0.0)
            cr.line_to(R - 0.01, -0.06)
            _stroke(cr, INK, 0.025)
        elif p == "eyepatch":
            cr.arc(0.06, 0.02, 0.035, 0, 2 * math.pi)
            _fill(cr, INK, 1, 0)
            cr.move_to(-R, 0.07)
            cr.line_to(R, -0.02)
            _stroke(cr, INK, 0.015)
        elif p == "beard":
            cr.move_to(-0.02, -0.05)
            cr.curve_to(0.02, -0.2, 0.12, -0.24, 0.16, -0.12)
            cr.curve_to(0.14, -0.06, 0.12, -0.04, 0.1, -0.03)
            cr.close_path()
            _fill(cr, mix(sec, (0.25, 0.15, 0.08), 0.6))
        elif p in ("headband", "visor", "halo", "spikes", "horns", "topknot", "ponytail", "scarf"):
            _classic(cr, p, R, sec, t)
    cr.restore()


def _classic(cr, p, R, sec, t):
    if p == "headband":
        cr.move_to(-R, 0.04)
        cr.line_to(R, 0.04)
        _stroke(cr, sec, 0.045)
        cr.move_to(-R, 0.04)
        cr.line_to(-R - 0.2, 0.0 + 0.03 * math.sin(t * 9))
        cr.move_to(-R, 0.04)
        cr.line_to(-R - 0.16, -0.08 + 0.03 * math.sin(t * 8))
        _stroke(cr, sec, 0.035)
    elif p == "visor":
        cr.move_to(-0.02, 0.02)
        cr.line_to(R * 1.05, 0.025)
        _stroke(cr, mix(sec, (1, 1, 1), 0.4), 0.05)
    elif p == "halo":
        cr.save()
        cr.translate(0, R + 0.1)
        cr.scale(1, 0.3)
        cr.arc(0, 0, 0.14, 0, 2 * math.pi)
        cr.restore()
        _stroke(cr, mix(sec, (1, 1, 0.8), 0.5), 0.03, 0.9)
    elif p == "spikes":
        for k in range(3):
            a = math.pi / 2 + 0.5 + 0.45 * k
            bx, by = math.cos(a) * R, math.sin(a) * R
            tx, ty = math.cos(a) * (R + 0.13), math.sin(a) * (R + 0.13)
            cr.move_to(bx + math.cos(a + 1.57) * 0.05, by + math.sin(a + 1.57) * 0.05)
            cr.line_to(tx, ty)
            cr.line_to(bx - math.cos(a + 1.57) * 0.05, by - math.sin(a + 1.57) * 0.05)
            cr.close_path()
            _fill(cr, sec, 1, 0.01)
    elif p == "horns":
        for d in (-1, 1):
            cr.move_to(d * 0.07, 0.1)
            cr.curve_to(d * 0.12, 0.2, d * 0.2, 0.22, d * 0.22, 0.3)
            _stroke(cr, sec, 0.035)
    elif p == "topknot":
        cr.arc(-0.04, R + 0.05, 0.06, 0, 2 * math.pi)
        _fill(cr, sec, 1, 0.01)
    elif p == "ponytail":
        cr.move_to(-R * 0.8, 0.08)
        cr.curve_to(-0.25, 0.1, -0.3, -0.05, -0.35 + 0.03 * math.sin(t * 6), -0.15)
        _stroke(cr, sec, 0.05)
    elif p == "scarf":
        cr.move_to(-0.05, -R - 0.05)
        cr.line_to(-0.35, -R - 0.12 + 0.04 * math.sin(t * 8))
        _stroke(cr, sec, 0.06)


def _skull(cr, x, y):
    cr.arc(x, y, 0.028, 0, 2 * math.pi)
    cr.set_source_rgba(0.95, 0.95, 0.9, 1)
    cr.fill()


def _star(cr, x, y, r, col):
    cr.move_to(x + r, y)
    for k in range(1, 10):
        a = k * math.pi / 5
        rr = r if k % 2 == 0 else r * 0.45
        cr.line_to(x + math.cos(a) * rr, y + math.sin(a) * rr)
    cr.close_path()
    cr.set_source_rgba(*col, 1)
    cr.fill()
