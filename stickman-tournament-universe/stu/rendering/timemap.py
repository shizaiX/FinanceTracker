"""Video-time -> simulation-time mapping (hook, slow motion, hit-stop).

The simulation always runs in real time; cinematic time effects are pure
render-side remapping, so they can never change the outcome. The fight's
simulated duration (validated against the 63 s rule) is unaffected.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VFrame:
    sim_t: float
    segment: str      # hook | intro | fight | outro
    speed: float      # playback speed relative to real time


def _windows(events, slowmo_mode, intensity_scale=1.0):
    """(start, end, speed) slow-motion windows in sim time."""
    if slowmo_mode in (False, "off", None):
        return [], []
    w, stops = [], []
    for e in events:
        t = e["t"]
        ty = e["type"]
        if ty == "ko":
            w.append((t - 0.45, t + 1.6, 0.22))
        elif ty == "score":
            w.append((t - 0.2, t + 0.75, 0.3))
        elif ty == "ultimate":
            w.append((t, t + min(0.9, e.get("dur", 0.6)), 0.4))
        elif ty == "guard_break":
            w.append((t, t + 0.3, 0.45))
        elif ty == "hit" and e.get("level") == "significant":
            stops.append((t, 0.05))
        elif ty in ("clash", "beam_clash") and slowmo_mode == "dramatic":
            stops.append((t, 0.03))
        elif ty == "counter":
            w.append((t, t + 0.25, 0.4))
    return w, stops


def build_timemap(result, fps, slowmo_mode="dramatic", hook=True):
    events = result["events"]
    fight_start = result["fight_start"]
    end = result["sim_duration"]
    windows, stops = _windows(events, slowmo_mode)
    stops.sort()
    frames = []
    dt = 1.0 / fps

    # -- hook (cold open): a spectacular non-deciding moment, slowed down.
    hook_t = None
    if hook:
        final_t = next((e["t"] for e in events if e["type"] == "ko"), end)
        cands = [e for e in events if e["type"] == "hit" and e.get("level") in ("significant",) and e["t"] < final_t - 4]
        cands += [e for e in events if e["type"] in ("score",) and e["t"] < final_t - 4]
        best = None
        for e in cands:
            score = 2.0 if e["type"] == "score" else 1.0
            if any(c["type"] == "callout" and 0 < e["t"] - c["t"] < 1.5 for c in events):
                score += 1.5
            if best is None or score > best[0]:
                best = (score, e)
        if best:
            hook_t = best[1]["t"]
            s = hook_t - 0.75
            while s < hook_t + 0.55:
                frames.append(VFrame(s, "hook", 0.5))
                s += dt * 0.5

    def speed_at(s):
        sp = 1.0
        for a, b, v in windows:
            if a <= s <= b:
                sp = min(sp, v)
        return sp

    s = 0.0
    si = 0
    outro_t = next((e["t"] for e in events if e["type"] == "ko"), None)
    while s < end - 1e-6:
        seg = "intro" if s < fight_start else ("outro" if outro_t is not None and s > outro_t + 1.2 else "fight")
        sp = speed_at(s)
        frames.append(VFrame(s, seg, sp))
        # hit-stop: hold for a few frames when crossing an impact
        nxt = s + dt * sp
        while si < len(stops) and stops[si][0] <= nxt:
            if stops[si][0] >= s:
                n = int(round(stops[si][1] * fps))
                frames.extend(VFrame(stops[si][0], seg, 0.0) for _ in range(n))
            si += 1
        s = nxt
    return frames, hook_t
