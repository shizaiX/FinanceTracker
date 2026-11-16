"""Cinematic dynamic camera, precomputed for the whole video (deterministic).

Frames both fighters with a critically-damped follow, zooms out for spatially
complex moments, punches in on decisive impacts, and adds trauma-based shake
(bounded, configurable) from impact events.
"""
from __future__ import annotations

import bisect
import math

from ..core.mathutil import clamp, lerp
from ..core.rng import stable_noise


class CameraKey:
    __slots__ = ("cx", "cy", "zoom", "sx", "sy", "rot", "bars")

    def __init__(self, cx, cy, zoom, sx=0.0, sy=0.0, rot=0.0, bars=0.0):
        self.cx, self.cy, self.zoom, self.sx, self.sy, self.rot, self.bars = cx, cy, zoom, sx, sy, rot, bars


TRAUMA = {"score": 0.65, "ko": 0.9, "explode": 0.32, "slam": 0.45, "env_erupt": 0.35, "clash": 0.3, "guard_break": 0.4,
          "intro_land": 0.5, "wall_hit": 0.3, "beam_clash": 0.08, "burst": 0.3, "throw": 0.3}


def sample(frames, s, dt):
    i = clamp(s / dt - 1.0, 0.0, len(frames) - 1.000001)
    i0 = int(i)
    return frames[i0], frames[min(i0 + 1, len(frames) - 1)], i - i0


def build_camera(result, vframes, width, height, fps, shake_scale=1.0, style="balanced"):
    frames = result["frames"]
    dt = result["dt"]
    events = result["events"]
    ev_t = [e["t"] for e in events]
    focus_events = [e for e in events if e["type"] in ("score", "ko", "ultimate", "guard_break")]
    fight_start = result["fight_start"]
    ko = next((e for e in events if e["type"] == "ko"), None)
    winner = result.get("winner")
    base_div = {"tight": 2.0, "balanced": 2.4, "wide": 3.0, "cinematic": 2.2}.get(style, 2.4)
    keys = []
    cx = cy = zoom = None
    vx = vy = vz = 0.0
    trauma = 0.0
    last_s = None
    for k, vf in enumerate(vframes):
        s = vf.sim_t
        a, b, f = sample(frames, s, dt)
        fa, fb = a["f"][0], a["f"][1]
        xa, ya = fa[0], fa[1]
        xb, yb = fb[0], fb[1]
        hid_a, hid_b = fa[5] & 64, fb[5] & 64
        if hid_a and not hid_b:
            xa, ya = xb, yb
        if hid_b and not hid_a:
            xb, yb = xa, ya
        span = abs(xa - xb)
        tx = (xa + xb) / 2
        top = max(ya, yb) + 2.1
        ty = 1.25 + 0.55 * max(0.0, min(ya, yb)) + 0.25 * max(0.0, max(ya, yb) - 1.0)
        for pr in a["p"]:
            if abs(pr[1] - tx) < 6:
                span = max(span, min(8.0, abs(pr[1] - tx) * 2))
        tz = width / (span + base_div)
        tz = min(tz, height * 0.42 / max(2.2, top - ty + 1.2))
        tz = clamp(tz, 55.0, 275.0)
        stiff = 5.0
        # Intro: present each fighter, then the pair.
        if vf.segment == "intro":
            if s < 1.45:
                tx, ty, tz = xa, 1.25, 265.0
            elif s < 2.65:
                tx, ty, tz = xb, 1.25, 265.0
            else:
                tz = width / (span + 3.4)
            stiff = 7.0
        if vf.segment == "hook":
            tz *= 1.18
        # Punch-in around decisive events.
        if vf.segment in ("fight", "hook"):
            for e in focus_events:
                d = s - e["t"]
                win = {"score": (-0.15, 1.0), "ko": (-0.4, 1.8), "ultimate": (0.0, 0.8), "guard_break": (0.0, 0.5)}[e["type"]]
                if win[0] <= d <= win[1]:
                    w = math.sin(math.pi * (d - win[0]) / (win[1] - win[0]))
                    amt = {"score": 0.35, "ko": 0.55, "ultimate": 0.25, "guard_break": 0.18}[e["type"]]
                    ex = e.get("x", tx)
                    tx = lerp(tx, ex, 0.5 * w)
                    tz *= 1 + amt * w
                    stiff = 9.0
        if vf.segment == "outro" and winner is not None:
            wf = a["f"][winner]
            lf = a["f"][1 - winner]
            tx = lerp((wf[0] + lf[0]) / 2, wf[0], 0.6)
            ty = 1.35
            tz = 250.0
            stiff = 2.2
        if cx is None or (vf.segment != (vframes[k - 1].segment if k else None) and vf.segment in ("hook", "intro")):
            cx, cy, zoom = tx, ty, tz
            vx = vy = vz = 0.0
        else:
            h = 1.0 / fps
            # critically damped spring
            for target, attr in ((tx, "x"), (ty, "y"), (tz, "z")):
                pass
            wx = stiff
            ax = wx * wx * (tx - cx) - 2 * wx * vx
            vx += ax * h
            cx += vx * h
            wy = stiff * 0.8
            ay = wy * wy * (ty - cy) - 2 * wy * vy
            vy += ay * h
            cy += vy * h
            wz = stiff * 0.7
            az = wz * wz * (tz - zoom) - 2 * wz * vz
            vz += az * h
            zoom += vz * h
        # Trauma from events crossed since last frame
        if last_s is not None and s > last_s:
            i0 = bisect.bisect_right(ev_t, last_s)
            i1 = bisect.bisect_right(ev_t, s)
            for e in events[i0:i1]:
                tr = TRAUMA.get(e["type"])
                if e["type"] == "hit" and e.get("level") == "significant":
                    tr = 0.22
                if e["type"] == "land" and e.get("heavy"):
                    tr = 0.18
                if tr:
                    trauma = min(1.0, trauma + tr)
        last_s = s
        trauma = max(0.0, trauma - 1.6 / fps)
        amp = trauma * trauma * 26.0 * shake_scale
        tt = k / fps
        sx = amp * stable_noise(11, tt * 22)
        sy = amp * stable_noise(23, tt * 22)
        rot = trauma * trauma * 0.012 * shake_scale * stable_noise(37, tt * 15)
        bars = 0.0
        if vf.speed < 0.6 and vf.segment in ("fight", "outro"):
            bars = 1.0
        # Guard rail: whatever the smoothing does, both visible fighters stay in frame.
        if vf.segment in ("fight", "hook", "outro") or (vf.segment == "intro" and s >= 2.65):
            pts = [p_ for p_, h in ((xa, hid_a), (xb, hid_b)) if not h] or [tx]
            lo, hi = min(pts) - 0.95, max(pts) + 0.95
            if (hi - lo) * zoom > width:
                zoom = width / (hi - lo)
                vz = 0.0
            half = width / 2 / zoom
            if lo < cx - half:
                cx = lo + half
                vx = 0.0
            elif hi > cx + half:
                cx = hi - half
                vx = 0.0
        prev_bars = keys[-1].bars if keys else 0.0
        bars = lerp(prev_bars, bars, 0.15)
        keys.append(CameraKey(cx, cy, zoom, sx, sy, rot, bars))
    return keys
