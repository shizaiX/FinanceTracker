"""Procedural weapon drawing (every entry of themes/packs.WEAPONS).

Weapons are drawn in a hand-local frame: x runs along the forearm (elbow ->
hand -> weapon), y is perpendicular and mirrored with the fighter's facing.
"""
from __future__ import annotations

import math

import cairo

from ..core.mathutil import hex_to_rgb, mix
from ..themes.packs import WEAPONS

INK = (0.02, 0.02, 0.04)


def hand_frame(cr, hand, elbow, facing):
    hx, hy = hand
    dx, dy = hx - elbow[0], hy - elbow[1]
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    px, py = -uy * facing, ux * facing
    cr.transform(cairo.Matrix(ux, uy, px, py, hx, hy))


def weapon_tip(key, hand, elbow):
    L = WEAPONS.get(key, {}).get("len", 0.95) or 0.0
    dx, dy = hand[0] - elbow[0], hand[1] - elbow[1]
    n = math.hypot(dx, dy) or 1.0
    return hand[0] + dx / n * L, hand[1] + dy / n * L


def _line(cr, pts, w, col, a=1.0):
    cr.set_line_width(w)
    cr.set_source_rgba(*col, a)
    cr.move_to(*pts[0])
    for q in pts[1:]:
        cr.line_to(*q)
    cr.stroke()


def _outlined(cr, path_fn, fill, outline_w=0.022):
    path_fn()
    cr.set_source_rgba(*INK, 0.9)
    cr.set_line_width(outline_w)
    cr.stroke_preserve()
    cr.set_source_rgba(*fill, 1.0)
    cr.fill()


def draw_weapon(cr, key, hand, elbow, facing, glow=None, t=0.0):
    """glow: optional rgb to tint/charge the weapon (ability infusion)."""
    spec = WEAPONS.get(key)
    if not spec:
        return
    edge, mid, grip = (hex_to_rgb(c) for c in spec["colors"])
    cls = spec["class"]
    L = spec.get("len", 0.9)
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if cls == "shield":
        # shields stay upright on the forearm
        cr.translate(hand[0] + facing * 0.05, hand[1] - 0.02)
        cr.scale(facing, 1)

        def shp():
            cr.move_to(0, 0.3)
            cr.curve_to(0.16, 0.3, 0.16, 0.05, 0.15, -0.05)
            cr.curve_to(0.13, -0.2, 0.05, -0.28, 0, -0.34)
            cr.curve_to(-0.05, -0.28, -0.13, -0.2, -0.15, -0.05)
            cr.curve_to(-0.16, 0.05, -0.16, 0.3, 0, 0.3)
            cr.close_path()
        _outlined(cr, shp, grip, 0.03)
        _line(cr, [(0, 0.27), (0, -0.3)], 0.035, edge, 0.9)
        _line(cr, [(-0.13, 0.08), (0.13, 0.08)], 0.035, edge, 0.9)
        cr.restore()
        return
    hand_frame(cr, hand, elbow, facing)
    if glow is not None:
        cr.set_source_rgba(*glow, 0.28)
        cr.set_line_width(0.2)
        cr.move_to(0, 0)
        cr.line_to(max(L, 0.2), 0)
        cr.stroke()
    if cls == "blade":
        w = spec.get("w", 0.06)
        curve = spec.get("curve", 0.0)
        _line(cr, [(-0.15, 0), (0.0, 0)], 0.05, INK)
        _line(cr, [(-0.14, 0), (-0.01, 0)], 0.032, grip)

        def cy(x):
            return curve * L * (x / L) ** 2

        def blade():
            n = 10
            cr.move_to(0.02, -w / 2)
            for k in range(n + 1):
                x = 0.02 + (L - 0.02) * k / n
                cr.line_to(x, cy(x) + w / 2 * (1 - (k / n) ** 3))
            for k in range(n, -1, -1):
                x = 0.02 + (L - 0.02) * k / n
                cr.line_to(x, cy(x) - w / 2 * (1 - (k / n) ** 1.5))
            cr.close_path()
        _outlined(cr, blade, mid)
        pts = [(0.02 + (L - 0.02) * k / 8, cy(0.02 + (L - 0.02) * k / 8) - w * 0.32 * (1 - k / 8)) for k in range(9)]
        _line(cr, pts, 0.012, edge)
        g = spec.get("guard")
        if g == "cross":
            _line(cr, [(0, -0.09), (0, 0.09)], 0.045, INK)
            _line(cr, [(0, -0.085), (0, 0.085)], 0.028, mix(grip, edge, 0.5))
        elif g == "basket":
            cr.arc(-0.06, 0, 0.075, -math.pi / 2, math.pi / 2)
            cr.set_source_rgba(*INK, 0.9)
            cr.set_line_width(0.035)
            cr.stroke()
            cr.arc(-0.06, 0, 0.075, -math.pi / 2, math.pi / 2)
            cr.set_source_rgba(0.85, 0.7, 0.3, 1)
            cr.set_line_width(0.02)
            cr.stroke()
        elif g == "tsuba":
            cr.save()
            cr.scale(0.4, 1)
            cr.arc(0, 0, 0.06, 0, 2 * math.pi)
            cr.restore()
            cr.set_source_rgba(0.75, 0.6, 0.3, 1)
            cr.fill()
        elif g == "ring":
            cr.arc(-0.2, 0, 0.035, 0, 2 * math.pi)
            cr.set_source_rgba(*mid, 1)
            cr.set_line_width(0.015)
            cr.stroke()
    elif cls == "claws":
        for off in (-0.045, 0.0, 0.045):
            pts = [(0.02, off), (0.14, off + 0.015), (0.24, off - 0.01), (0.3, off - 0.05)]
            _line(cr, pts, 0.04, INK)
            _line(cr, pts, 0.022, edge)
    elif cls in ("polearm", "staff"):
        _line(cr, [(-0.48, 0), (L, 0)], 0.055, INK)
        _line(cr, [(-0.47, 0), (L - 0.02, 0)], 0.035, grip)
        head = spec.get("head")
        if head == "leaf":
            _outlined(cr, lambda: (cr.move_to(L - 0.04, 0), cr.line_to(L + 0.08, 0.055), cr.line_to(L + 0.3, 0), cr.line_to(L + 0.08, -0.055), cr.close_path()), mid)
        elif head == "barb":
            _outlined(cr, lambda: (cr.move_to(L + 0.28, 0), cr.line_to(L + 0.02, 0.09), cr.line_to(L + 0.08, 0), cr.line_to(L + 0.02, -0.09), cr.close_path()), mid)
            _line(cr, [(L - 0.3, 0.03), (L - 0.4, 0.07), (L - 0.5, 0.03)], 0.015, (0.85, 0.8, 0.65))
        elif head == "trident":
            _line(cr, [(L, -0.12), (L, 0.12)], 0.045, mid)
            for off in (-0.11, 0.0, 0.11):
                _line(cr, [(L, off), (L + 0.24, off)], 0.035, mid)
                _outlined(cr, lambda off=off: (cr.move_to(L + 0.22, off - 0.035), cr.line_to(L + 0.33, off), cr.line_to(L + 0.22, off + 0.035), cr.close_path()), edge, 0.012)
        elif head == "blade":
            _outlined(cr, lambda: (cr.move_to(L - 0.05, -0.03), cr.curve_to(L + 0.1, -0.16, L + 0.3, -0.12, L + 0.42, 0.04), cr.curve_to(L + 0.25, 0.02, L + 0.1, 0.04, L - 0.05, 0.04), cr.close_path()), mid)
        elif head == "cone":
            _outlined(cr, lambda: (cr.move_to(L - 0.1, -0.11), cr.line_to(L + 0.6, 0), cr.line_to(L - 0.1, 0.11), cr.close_path()), mid)
            _outlined(cr, lambda: (cr.move_to(L - 0.18, -0.16), cr.line_to(L - 0.08, -0.16), cr.line_to(L - 0.08, 0.16), cr.line_to(L - 0.18, 0.16), cr.close_path()), grip)
        elif head == "orb":
            g = cairo.RadialGradient(L + 0.06, 0, 0, L + 0.06, 0, 0.2)
            gc = glow or edge
            g.add_color_stop_rgba(0, 1, 1, 1, 1)
            g.add_color_stop_rgba(0.4, *gc, 0.9)
            g.add_color_stop_rgba(1, *gc, 0)
            cr.set_source(g)
            cr.arc(L + 0.06, 0, 0.2, 0, 2 * math.pi)
            cr.fill()
            _line(cr, [(L - 0.05, -0.06), (L + 0.02, -0.09), (L + 0.12, -0.05)], 0.02, grip)
        elif head == "star":
            gc = glow or edge
            for k in range(4):
                a = k * math.pi / 2 + t * 4
                _line(cr, [(L, 0), (L + math.cos(a) * 0.09, math.sin(a) * 0.09)], 0.018, gc)
            cr.arc(L, 0, 0.035, 0, 2 * math.pi)
            cr.set_source_rgba(1, 1, 1, 1)
            cr.fill()
    elif cls == "blunt":
        _line(cr, [(-0.14, 0), (L, 0)], 0.06, INK)
        _line(cr, [(-0.13, 0), (L - 0.02, 0)], 0.038, grip)
        head = spec.get("head")
        if head == "block":
            _outlined(cr, lambda: cr.rectangle(L - 0.13, -0.2, 0.26, 0.4), mid, 0.03)
            _line(cr, [(L - 0.13, -0.2), (L - 0.13, 0.2)], 0.02, edge)
        elif head == "spiked":
            for k in range(8):
                a = k * math.pi / 4
                _outlined(cr, lambda a=a: (cr.move_to(L + math.cos(a + 0.25) * 0.1, math.sin(a + 0.25) * 0.1),
                                            cr.line_to(L + math.cos(a) * 0.19, math.sin(a) * 0.19),
                                            cr.line_to(L + math.cos(a - 0.25) * 0.1, math.sin(a - 0.25) * 0.1), cr.close_path()), edge, 0.01)
            _outlined(cr, lambda: cr.arc(L, 0, 0.11, 0, 2 * math.pi), mid, 0.025)
        elif head == "anchor":
            _line(cr, [(L, -0.32), (L, 0.32)], 0.07, INK)
            _line(cr, [(L, -0.31), (L, 0.31)], 0.045, mid)
            cr.arc(L - 0.3, 0, 0.32, -0.95, 0.95)
            cr.set_source_rgba(*INK, 1)
            cr.set_line_width(0.075)
            cr.stroke()
            cr.arc(L - 0.3, 0, 0.32, -0.95, 0.95)
            cr.set_source_rgba(*mid, 1)
            cr.set_line_width(0.045)
            cr.stroke()
            for sgn in (-1, 1):
                ax, ay = L - 0.3 + 0.32 * math.cos(0.95), sgn * 0.32 * math.sin(0.95)
                _outlined(cr, lambda ax=ax, ay=ay, sgn=sgn: (cr.move_to(ax - 0.02, ay), cr.line_to(ax - 0.14, ay + sgn * 0.06), cr.line_to(ax + 0.03, ay + sgn * 0.08), cr.close_path()), mid)
            cr.arc(-0.2, 0, 0.06, 0, 2 * math.pi)
            cr.set_source_rgba(*mid, 1)
            cr.set_line_width(0.025)
            cr.stroke()
        elif head == "axe":
            _outlined(cr, lambda: (cr.move_to(L - 0.15, 0.02), cr.curve_to(L - 0.2, 0.22, L + 0.1, 0.32, L + 0.12, 0.3),
                                   cr.curve_to(L + 0.02, 0.18, L + 0.02, 0.1, L + 0.04, 0.02), cr.close_path()), mid)
            _line(cr, [(L - 0.18, 0.18), (L + 0.1, 0.3)], 0.014, edge)
        elif head == "club":
            _outlined(cr, lambda: (cr.move_to(L * 0.3, -0.04), cr.curve_to(L * 0.7, -0.08, L + 0.08, -0.12, L + 0.08, 0),
                                   cr.curve_to(L + 0.08, 0.12, L * 0.7, 0.08, L * 0.3, 0.04), cr.close_path()), mid)
    elif cls == "firearm":
        stock = spec.get("stock")
        if stock == "rifle":
            _outlined(cr, lambda: (cr.move_to(-0.35, -0.05), cr.line_to(0.1, -0.03), cr.line_to(0.1, 0.03), cr.line_to(-0.35, 0.09), cr.close_path()), grip)
        else:
            _outlined(cr, lambda: (cr.move_to(0.02, -0.02), cr.line_to(-0.04, -0.13), cr.line_to(-0.12, -0.12), cr.line_to(-0.05, 0.03), cr.close_path()), grip)
        bw = 0.042
        if stock == "flare":
            _outlined(cr, lambda: (cr.move_to(-0.02, -bw / 2), cr.line_to(L - 0.1, -bw / 2), cr.line_to(L, -0.07), cr.line_to(L, 0.07), cr.line_to(L - 0.1, bw / 2), cr.line_to(-0.02, bw / 2), cr.close_path()), mid)
        else:
            _outlined(cr, lambda: cr.rectangle(-0.03, -bw / 2, L + 0.03, bw), mid)
        _line(cr, [(0.0, bw / 2 + 0.01), (0.03, bw / 2 + 0.05)], 0.018, edge)
        _line(cr, [(0.04, -bw / 2), (L * 0.6, -bw / 2)], 0.008, edge)
    elif cls == "bow":
        if L > 1.0:  # longbow held perpendicular
            cr.move_to(0.02, -L / 2)
            cr.curve_to(0.25, -L / 4, 0.25, L / 4, 0.02, L / 2)
            cr.set_source_rgba(*INK, 1)
            cr.set_line_width(0.06)
            cr.stroke_preserve()
            cr.set_source_rgba(*mid, 1)
            cr.set_line_width(0.035)
            cr.stroke()
            _line(cr, [(0.02, -L / 2), (-0.05, 0), (0.02, L / 2)], 0.008, (0.95, 0.95, 0.9))
        else:  # crossbow
            _outlined(cr, lambda: cr.rectangle(-0.15, -0.025, L, 0.05), grip)
            cr.move_to(L - 0.2, -0.3)
            cr.curve_to(L - 0.05, -0.1, L - 0.05, 0.1, L - 0.2, 0.3)
            cr.set_source_rgba(*mid, 1)
            cr.set_line_width(0.035)
            cr.stroke()
            _line(cr, [(L - 0.2, -0.3), (0.05, 0), (L - 0.2, 0.3)], 0.008, (0.95, 0.95, 0.9))
    elif cls == "fist":
        _outlined(cr, lambda: cr.arc(0.0, 0, 0.075, 0, 2 * math.pi), mid, 0.02)
        _line(cr, [(-0.12, -0.05), (-0.12, 0.05)], 0.03, edge)
    cr.restore()


def draw_energy_blade(cr, hand, elbow, facing, cols, length=0.95):
    dx, dy = hand[0] - elbow[0], hand[1] - elbow[1]
    n = math.hypot(dx, dy) or 1.0
    tx, ty = hand[0] + dx / n * length, hand[1] + dy / n * length
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    for w, c, a in ((0.22, cols[2], 0.3), (0.11, cols[1], 0.75), (0.045, cols[0], 1.0)):
        cr.set_line_width(w)
        cr.set_source_rgba(*c, a)
        cr.move_to(*hand)
        cr.line_to(tx, ty)
        cr.stroke()
