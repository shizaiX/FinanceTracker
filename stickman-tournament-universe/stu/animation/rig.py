"""Articulated stickman rig: hierarchy, FK spine/head, 2-bone IK limbs and a
procedural foot-planting controller (feet stay locked to the ground until a
step is needed, so locomotion never slides).

Local pose space: facing right, origin = ground point under the hip, y up,
metres. World = mirror x by facing + translate.
"""
from __future__ import annotations

import math

from ..core.mathutil import clamp, lerp

HIP_H = 0.92
SPINE = 0.56
NECK = 0.08
HEAD_R = 0.135
UPPER_ARM = 0.32
FOREARM = 0.31
THIGH = 0.48
SHIN = 0.47
ARM_LEN = UPPER_ARM + FOREARM
LEG_LEN = THIGH + SHIN

JOINTS = ["hip", "chest", "head", "elbow_f", "hand_f", "elbow_b", "hand_b", "knee_f", "foot_f", "knee_b", "foot_b"]
J = {n: i for i, n in enumerate(JOINTS)}
BONES = [("hip", "chest", SPINE), ("chest", "elbow_f", UPPER_ARM), ("elbow_f", "hand_f", FOREARM),
         ("chest", "elbow_b", UPPER_ARM), ("elbow_b", "hand_b", FOREARM), ("hip", "knee_f", THIGH),
         ("knee_f", "foot_f", SHIN), ("hip", "knee_b", THIGH), ("knee_b", "foot_b", SHIN)]

POSE_KEYS = ["lean", "crouch", "head", "rot", "hfx", "hfy", "hbx", "hby", "ffx", "ffy", "fbx", "fby", "ffree", "fbfree"]


def ik2(ax, ay, tx, ty, l1, l2, sign):
    """Two-bone IK. sign=+1 bends counter-clockwise of the root->target line."""
    dx, dy = tx - ax, ty - ay
    d0 = math.hypot(dx, dy)
    if d0 < 1e-6:
        dx, dy, d0 = 0.0, -1.0, 1.0
    ux, uy = dx / d0, dy / d0
    d = clamp(d0, abs(l1 - l2) + 1e-4, l1 + l2 - 1e-4)
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(0.0, l1 * l1 - a * a))
    px, py = ax + ux * a, ay + uy * a
    jx, jy = px - sign * uy * h, py + sign * ux * h
    ex, ey = ax + ux * d, ay + uy * d
    return jx, jy, ex, ey


def solve_local(p, build=1.0, feet_local=None):
    """Pose dict -> 11 joint positions in local space (before rot/mirror)."""
    s = build
    hip = (0.0, HIP_H * s - p["crouch"])
    lean = p["lean"]
    chest = (hip[0] + SPINE * s * math.sin(lean), hip[1] + SPINE * s * math.cos(lean))
    ha = lean + p["head"]
    head = (chest[0] + (NECK + HEAD_R) * s * math.sin(ha), chest[1] + (NECK + HEAD_R) * s * math.cos(ha))
    sh = chest
    ua, fa, th, sn = UPPER_ARM * s, FOREARM * s, THIGH * s, SHIN * s
    ef = ik2(sh[0], sh[1], sh[0] + p["hfx"], sh[1] + p["hfy"], ua, fa, -1)
    eb = ik2(sh[0], sh[1], sh[0] + p["hbx"], sh[1] + p["hby"], ua, fa, -1)
    if feet_local:
        (ffx, ffy), (fbx, fby) = feet_local
    else:
        ffx, ffy, fbx, fby = p["ffx"], p["ffy"], p["fbx"], p["fby"]
    kf = ik2(hip[0], hip[1], ffx, ffy, th, sn, +1)
    kb = ik2(hip[0], hip[1], fbx, fby, th, sn, +1)
    return [hip, chest, head, (ef[0], ef[1]), (ef[2], ef[3]), (eb[0], eb[1]), (eb[2], eb[3]),
            (kf[0], kf[1]), (kf[2], kf[3]), (kb[0], kb[1]), (kb[2], kb[3])]


def to_world(local_pts, rot, x, y, facing):
    hx, hy = local_pts[0]
    c, sn = math.cos(rot), math.sin(rot)
    out = []
    for (px, py) in local_pts:
        dx, dy = px - hx, py - hy
        rx, ry = hx + dx * c - dy * sn, hy + dx * sn + dy * c
        out.append((x + facing * rx, y + ry))
    return out


def blend_pose(a, b, t):
    return {k: lerp(a[k], b[k], t) for k in POSE_KEYS}


class Foot:
    __slots__ = ("x", "y", "planted", "stepping", "sx", "sy", "st", "sdur", "tx")

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.planted = True
        self.stepping = False
        self.sx = self.sy = self.st = self.sdur = self.tx = 0.0


class FootController:
    """Keeps grounded feet planted in world space; triggers arc steps when the
    body drifts too far from the planted foot (procedural locomotion)."""

    def __init__(self, x, facing):
        self.feet = [Foot(x + facing * 0.26, 0.0), Foot(x - facing * 0.26, 0.0)]
        self.last_step = 0  # index of last stepping foot

    def swap(self):
        self.feet.reverse()

    def update(self, dt, desired, grounded, free_flags, speed, ground_y=0.0):
        """desired: [(wx, wy)] for front/back foot. Returns world positions and
        a list of foot indices that just landed (for footstep sounds/dust)."""
        landed = []
        for i, f in enumerate(self.feet):
            dx, dy = desired[i]
            if not grounded or free_flags[i] > 0.5:
                # Free foot: follow the animation directly.
                f.x, f.y = dx, max(ground_y, dy)
                f.planted = False
                f.stepping = False
                continue
            if f.stepping:
                f.st += dt
                p = clamp(f.st / f.sdur, 0.0, 1.0)
                f.tx = dx + (dx - f.sx) * 0.0
                f.x = lerp(f.sx, dx, p * p * (3 - 2 * p))
                lift = (0.08 + 0.035 * min(speed, 8.0)) * math.sin(math.pi * p)
                f.y = max(ground_y, lerp(f.sy, ground_y, p) + lift)
                if p >= 1.0:
                    f.stepping = False
                    f.planted = True
                    f.y = ground_y
                    landed.append(i)
                continue
            if not f.planted:
                # Was free / airborne -> come down onto the ground with a quick step.
                self._start(f, 0.07 if f.y - ground_y < 0.15 else 0.12)
                continue
            err = abs(dx - f.x)
            other = self.feet[1 - i]
            thresh = 0.2 if speed > 0.5 else 0.09
            if err > thresh and (not other.stepping or err > 0.5):
                if speed <= 0.5 and other.stepping:
                    continue
                dur = clamp(0.24 - 0.018 * speed, 0.09, 0.24)
                self._start(f, dur)
        return [(f.x, f.y) for f in self.feet], landed

    @staticmethod
    def _start(f, dur):
        f.stepping = True
        f.planted = False
        f.sx, f.sy = f.x, f.y
        f.st = 0.0
        f.sdur = dur
