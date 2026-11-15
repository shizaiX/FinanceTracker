"""Small vector / easing helpers used across simulation and rendering."""
from __future__ import annotations

import math


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def ease_in(t):
    t = clamp(t, 0.0, 1.0)
    return t * t


def ease_out(t):
    t = clamp(t, 0.0, 1.0)
    return 1 - (1 - t) * (1 - t)


def ease_out_back(t, s=1.4):
    t = clamp(t, 0.0, 1.0) - 1
    return t * t * ((s + 1) * t + s) + 1


def ease_out_expo(t):
    t = clamp(t, 0.0, 1.0)
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def seg_seg_dist(p1, q1, p2, q2):
    """Minimum distance between segments p1q1 and p2q2 (2D)."""
    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1])

    def dot(a, b):
        return a[0] * b[0] + a[1] * b[1]

    d1 = sub(q1, p1)
    d2 = sub(q2, p2)
    r = sub(p1, p2)
    a = dot(d1, d1)
    e = dot(d2, d2)
    f = dot(d2, r)
    eps = 1e-9
    if a <= eps and e <= eps:
        return math.hypot(*r)
    if a <= eps:
        s = 0.0
        t = clamp(f / e, 0.0, 1.0)
    else:
        c = dot(d1, r)
        if e <= eps:
            t = 0.0
            s = clamp(-c / a, 0.0, 1.0)
        else:
            b = dot(d1, d2)
            denom = a * e - b * b
            s = clamp((b * f - c * e) / denom, 0.0, 1.0) if denom > eps else 0.0
            t = (b * s + f) / e
            if t < 0:
                t = 0.0
                s = clamp(-c / a, 0.0, 1.0)
            elif t > 1:
                t = 1.0
                s = clamp((b - c) / a, 0.0, 1.0)
    cx = p1[0] + d1[0] * s - (p2[0] + d2[0] * t)
    cy = p1[1] + d1[1] * s - (p2[1] + d2[1] * t)
    return math.hypot(cx, cy)


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#" + "".join(f"{int(clamp(c, 0, 1) * 255):02x}" for c in rgb)


def mix(c1, c2, t):
    return tuple(lerp(a, b, t) for a, b in zip(c1, c2))
