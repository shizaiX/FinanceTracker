"""Channel logo in the style of the fight videos (same rig, glow strokes, VFX, fonts).

    python tools/make_logo.py            -> branding/logo_1080.png (+ circle preview, small preview)

TikTok shows profile pictures as a circle, so everything important stays inside
the central circle.
"""
import math
import os
import random
import sys

import cairo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stu.animation.poses import P, POSES, STANCES, template  # noqa: E402
from stu.animation.rig import HEAD_R, J, solve_local, to_world  # noqa: E402
from stu.core.mathutil import hex_to_rgb, mix  # noqa: E402
from stu.rendering.hud import text  # noqa: E402
from stu.rendering.vfx import draw_bolt  # noqa: E402

S = 1080
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "branding")


def body(cr, Pts, col, back, width, alpha):
    hx, hy = Pts[J["head"]]
    cx, cy = Pts[J["chest"]]
    d = math.hypot(hx - cx, hy - cy) or 1
    neck = (hx - (hx - cx) / d * HEAD_R, hy - (hy - cy) / d * HEAD_R)
    chains = [((Pts[J["hip"]], Pts[J["knee_b"]], Pts[J["foot_b"]]), back), ((Pts[J["chest"]], Pts[J["elbow_b"]], Pts[J["hand_b"]]), back),
              ((Pts[J["hip"]], Pts[J["chest"]], neck), col), ((Pts[J["hip"]], Pts[J["knee_f"]], Pts[J["foot_f"]]), col),
              ((Pts[J["chest"]], Pts[J["elbow_f"]], Pts[J["hand_f"]]), col)]
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    for ch, c in chains:
        cr.set_source_rgba(*c, alpha)
        cr.set_line_width(width)
        cr.move_to(*ch[0])
        for q in ch[1:]:
            cr.line_to(*q)
        cr.stroke()
    cr.arc(hx, hy, HEAD_R + (width - 0.075) * 0.5, 0, 2 * math.pi)
    cr.set_source_rgba(*col, alpha)
    cr.fill()


def fighter(cr, pose, x, facing, col):
    pts = to_world(solve_local(pose), pose["rot"], x, 0.0, facing)
    back = mix(col, (0.05, 0.05, 0.08), 0.38)
    body(cr, pts, col, col, 0.42, 0.10)
    body(cr, pts, col, col, 0.24, 0.20)
    body(cr, pts, (0.02, 0.02, 0.04), (0.02, 0.02, 0.04), 0.12, 0.9)
    body(cr, pts, mix(col, (1, 1, 1), 0.15), back, 0.08, 1.0)
    # eye slit
    hx, hy = pts[J["head"]]
    cr.set_source_rgba(0.03, 0.03, 0.06, 1)
    cr.set_line_width(0.035)
    cr.move_to(hx + facing * 0.02, hy + 0.02)
    cr.line_to(hx + facing * 0.1, hy + 0.025)
    cr.stroke()
    return pts


def glow(cr, x, y, r, cols, a=1.0):
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, 1, 1, 1, a)
    g.add_color_stop_rgba(0.25, *cols[0], 0.85 * a)
    g.add_color_stop_rgba(1, *cols[1], 0)
    cr.set_source(g)
    cr.arc(x, y, r, 0, 2 * math.pi)
    cr.fill()


def main():
    os.makedirs(OUT, exist_ok=True)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
    cr = cairo.Context(surf)
    # ---- background: deep arena night with rays
    g = cairo.RadialGradient(S / 2, S * 0.42, 0, S / 2, S * 0.5, S * 0.75)
    g.add_color_stop_rgb(0, 0.20, 0.07, 0.28)
    g.add_color_stop_rgb(0.55, 0.07, 0.03, 0.12)
    g.add_color_stop_rgb(1, 0.02, 0.01, 0.04)
    cr.set_source(g)
    cr.paint()
    cx, cy = S / 2, S * 0.4
    for k in range(28):
        a = k / 28 * 2 * math.pi
        cr.move_to(cx, cy)
        cr.line_to(cx + math.cos(a) * S, cy + math.sin(a) * S)
        cr.line_to(cx + math.cos(a + 0.07) * S, cy + math.sin(a + 0.07) * S)
        cr.close_path()
        cr.set_source_rgba(1, 0.7, 0.4, 0.05 if k % 2 else 0.025)
        cr.fill()
    rr = random.Random(4)
    for _ in range(70):
        cr.arc(rr.uniform(0, S), rr.uniform(0, S * 0.9), rr.uniform(1, 3.5), 0, 2 * math.pi)
        cr.set_source_rgba(1, 0.8, 0.5, rr.uniform(0.15, 0.6))
        cr.fill()

    # ---- world transform for the fighters (metres, y up)
    fire = [hex_to_rgb("#ffb347"), hex_to_rgb("#ff3d00")]
    ice = [hex_to_rgb("#9fe8ff"), hex_to_rgb("#3a8dde")]
    cr.save()
    cr.translate(S / 2, S * 0.585)
    z = 215
    cr.scale(z, -z)
    # ground glow line
    g = cairo.LinearGradient(-2.6, 0, 2.6, 0)
    g.add_color_stop_rgba(0, 1, 0.6, 0.3, 0)
    g.add_color_stop_rgba(0.5, 1, 0.8, 0.5, 0.9)
    g.add_color_stop_rgba(1, 0.4, 0.8, 1, 0)
    cr.set_source(g)
    cr.rectangle(-2.6, -0.02, 5.2, 0.035)
    cr.fill()
    # left: fire fighter throwing a cross; right: ice fighter high roundhouse
    punch = template("punch", 1)["keys"][1]
    kick = template("kick", 1)["keys"][1]
    a_pose = P(punch, lean=0.45, hbx=0.63, hby=0.18)
    b_pose = P(kick, fbx=0.8, fby=1.2)
    # place the fighters so the fire fist and the ice foot meet exactly at the clash
    ax = -1.2
    fist0 = to_world(solve_local(a_pose), 0.0, ax, 0.0, 1)[J["hand_b"]]
    foot0 = to_world(solve_local(b_pose), 0.0, 0.0, 0.0, -1)[J["foot_b"]]
    bx = fist0[0] - foot0[0] + 0.18
    c0 = (ax + bx) / 2  # recentre the pair horizontally
    ax, bx = ax - c0, bx - c0
    a = fighter(cr, a_pose, ax, 1, hex_to_rgb("#ff7a2a"))
    b = fighter(cr, b_pose, bx, -1, hex_to_rgb("#2ee9ff"))
    fist = a[J["hand_b"]]
    foot = b[J["foot_b"]]
    mx, my = (fist[0] + foot[0]) / 2, (fist[1] + foot[1]) / 2
    # elemental infusion + trails
    for k in range(7):
        t = k / 7
        glow(cr, fist[0] - 0.12 * k, fist[1] - 0.04 * k + 0.03 * math.sin(k * 2), 0.22 * (1 - t) + 0.05, fire, 0.8 * (1 - t))
        glow(cr, foot[0] + 0.1 * k, foot[1] - 0.09 * k, 0.2 * (1 - t) + 0.05, ice, 0.8 * (1 - t))
    # clash: flash, shockwave rings, sparks, lightning
    glow(cr, mx, my, 0.5, [(1, 0.95, 0.8), (1, 0.6, 0.3)], 1.0)
    for r_, a_, w in ((0.42, 0.8, 0.04), (0.62, 0.4, 0.03)):
        cr.set_source_rgba(1, 0.92, 0.8, a_)
        cr.set_line_width(w)
        cr.arc(mx, my, r_, 0, 2 * math.pi)
        cr.stroke()
    for k in range(22):
        ang = rr.uniform(0, 2 * math.pi)
        L = rr.uniform(0.3, 0.62)
        cr.set_source_rgba(*(fire[0] if k % 2 else ice[0]), 0.95)
        cr.set_line_width(rr.uniform(0.02, 0.045))
        cr.move_to(mx + math.cos(ang) * 0.18, my + math.sin(ang) * 0.18)
        cr.line_to(mx + math.cos(ang) * L, my + math.sin(ang) * L)
        cr.stroke()
    draw_bolt(cr, mx - 0.05, my + 0.12, mx - 0.35, my + 0.75, [(1, 1, 1), (1, 0.85, 0.5), (1, 0.5, 0.2)], 11, 0.9, 0.03)
    draw_bolt(cr, mx + 0.05, my + 0.1, mx + 0.4, my + 0.7, [(1, 1, 1), (0.75, 0.95, 1), (0.3, 0.6, 1)], 23, 0.9, 0.03)
    cr.restore()

    # ---- title, inside the circular safe area
    text(cr, "ULTIMATE", S / 2, S * 0.675, 86, (1, 0.83, 0.35), "center", 1.0, glow=(1, 0.55, 0.15), tracking=0.18, outline=0.14)
    text(cr, "STICK FIGHT", S / 2, S * 0.775, 132, (1, 1, 1), "center", 1.0, glow=(0.55, 0.4, 1.0), outline=0.13, max_width=S * 0.8)
    text(cr, "TOURNAMENTS", S / 2, S * 0.865, 64, (1, 0.83, 0.35), "center", 1.0, glow=(1, 0.55, 0.15), tracking=0.16, outline=0.15)
    path = os.path.join(OUT, "logo_1080.png")
    surf.write_to_png(path)

    # circle-cropped preview as TikTok shows it
    circ = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
    c2 = cairo.Context(circ)
    c2.arc(S / 2, S / 2, S / 2, 0, 2 * math.pi)
    c2.clip()
    c2.set_source_surface(surf, 0, 0)
    c2.paint()
    c2.arc(S / 2, S / 2, S / 2 - 6, 0, 2 * math.pi)
    c2.set_source_rgba(1, 0.8, 0.4, 0.9)
    c2.set_line_width(12)
    c2.stroke()
    circ.write_to_png(os.path.join(OUT, "logo_circle_preview.png"))
    print(path)


if __name__ == "__main__":
    main()
