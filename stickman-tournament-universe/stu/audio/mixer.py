"""Event-synchronised audio mixing.

Every sound is placed at the *video* time at which its simulation event is
displayed (through the same time map the renderer uses), so audio and video stay
frame-accurate even through slow motion, hit-stop and the cold-open hook.
"""
from __future__ import annotations

import wave
import zlib

import numpy as np

from .synth import SR, music, sound

DELIVERY_SOUND = {"punch": "punch", "kick": "kick", "sweep": "kick", "uppercut": "punch", "aerial_strike": "kick",
                  "grapple": "heavy", "charge": "heavy", "barrage": "punch", "summon_weapon": "metal", "counter": "punch"}


def _place(buf, x, t, gain, pan=0.0, speed=1.0):
    if speed < 0.95:
        f = max(0.45, speed) ** 0.5
        idx = np.arange(0, len(x), f)
        x = np.interp(idx, np.arange(len(x)), x).astype(np.float32)
    s = int(t * SR)
    if s >= buf.shape[0] or s < 0:
        return
    e = min(buf.shape[0], s + len(x))
    l = np.float32(gain * min(1.0, 1 - pan))
    r = np.float32(gain * min(1.0, 1 + pan))
    buf[s:e, 0] += x[:e - s] * l
    buf[s:e, 1] += x[:e - s] * r


def build_audio(result, vframes, fps, abilities, creative, out_path):
    n_video = len(vframes)
    dur = n_video / fps
    buf = np.zeros((int(dur * SR) + 1, 2), dtype=np.float32)
    events = result["events"]
    ev_sorted = sorted(range(len(events)), key=lambda i: events[i]["t"])
    times = [events[i]["t"] for i in ev_sorted]
    import bisect
    duck = np.ones(buf.shape[0], dtype=np.float32)
    sfx = creative.get("sound_effects", True)
    prev_s, prev_seg = None, None
    for k, vf in enumerate(vframes):
        s = vf.sim_t
        if prev_s is None or vf.segment != prev_seg and vf.segment == "intro" and prev_seg == "hook":
            lo = s - 1e-9
        else:
            lo = prev_s
        if s > lo and sfx:
            i0 = bisect.bisect_right(times, lo)
            i1 = bisect.bisect_right(times, s)
            vt = k / fps
            for j in ev_sorted[i0:i1]:
                e = events[j]
                if vf.segment == "hook" and e["type"] in ("fight", "round_start"):
                    continue
                _event_sound(buf, e, vt, abilities, vf.speed, duck)
        prev_s, prev_seg = s, vf.segment
    if creative.get("music") not in (False, "off", None, "none"):
        fs = result["fight_start"]
        final = result.get("final_point_t") or 60

        def inten(t):
            return min(1.0, 0.35 + 0.65 * max(0.0, t - 3) / max(10.0, final))
        m = music(dur, seed=zlib.crc32(str(result.get("timeline_hash", "x")).encode()) & 0xFFFF, intensity=inten)
        m = m[:buf.shape[0]]
        m = np.pad(m, (0, buf.shape[0] - len(m)))
        g = (m * duck * 0.55).astype(np.float32)
        buf[:, 0] += g
        buf[:, 1] += g
    # normalisation: target RMS then soft limit
    rms = float(np.sqrt(np.mean(buf ** 2)) + 1e-9)
    buf *= min(4.0, 0.12 / rms)
    buf = np.tanh(buf * 1.1) / np.tanh(1.1)
    buf *= 0.89
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return out_path


def _voice(abilities, ab_ids):
    for a in ab_ids or []:
        if a in abilities:
            return abilities[a].get("voice")
    return None


def _event_sound(buf, e, vt, abilities, speed, duck):
    ty = e["type"]
    pan = max(-0.6, min(0.6, e.get("x", 0.0) / 8.0))
    v = _voice(abilities, e.get("abilities"))
    sp = speed if speed > 0 else 1.0
    if ty == "hit":
        lvl = e.get("level")
        base = DELIVERY_SOUND.get(e.get("delivery"), "punch")
        g = {"minor": 0.55, "combo": 0.65, "significant": 0.95}.get(lvl, 0.6)
        _place(buf, sound("heavy" if lvl == "significant" else base, hash(e["t"]) % 3), vt, g, pan, sp)
        if v:
            _place(buf, sound(v, 1), vt, 0.35 * g, pan, sp)
    elif ty in ("score", "ko"):
        _place(buf, sound("heavy"), vt, 1.0, pan, sp)
        _place(buf, sound("ko" if ty == "ko" else "score"), vt + 0.02, 0.9, 0.0, 1.0)
        _place(buf, sound("slowmo"), vt, 0.35, 0.0, 1.0)
        s = int(vt * SR)
        e2 = min(len(duck), s + int(1.6 * SR))
        duck[s:e2] = np.minimum(duck[s:e2], 0.3)
    elif ty == "block":
        _place(buf, sound("block", hash(e["t"]) % 2), vt, 0.6, pan, sp)
    elif ty in ("shield_block", "guard_crush", "reflect", "absorb"):
        _place(buf, sound("metal", 2), vt, 0.5, pan, sp)
    elif ty == "guard_break":
        _place(buf, sound("ice", 3), vt, 0.7, pan, sp)
        _place(buf, sound("heavy", 1), vt, 0.6, pan, sp)
    elif ty == "whoosh":
        if not e.get("quiet"):
            _place(buf, sound("whoosh", hash(e["t"]) % 3), vt, 0.35, pan, sp)
    elif ty in ("explode", "slam", "env_erupt"):
        _place(buf, sound("explosion", hash(e["t"]) % 2), vt, 0.6 if ty != "slam" else 0.75, pan, sp)
        if v:
            _place(buf, sound(v, 2), vt, 0.5, pan, sp)
    elif ty in ("projectile", "beam_start"):
        _place(buf, sound(v or "whoosh", 0), vt, 0.55, pan, sp)
    elif ty == "cast":
        if e.get("tier") in ("fusion", "ultimate") or e.get("dur", 0) > 0.3:
            _place(buf, sound("charge"), vt, 0.32, pan, sp)
    elif ty == "ultimate":
        _place(buf, sound("riser"), vt, 0.5, 0.0, 1.0)
        _place(buf, sound("slowmo"), vt, 0.3, 0.0, 1.0)
    elif ty in ("teleport_out", "teleport_in"):
        _place(buf, sound("teleport"), vt, 0.45, pan, sp)
    elif ty in ("land", "intro_land"):
        if e.get("heavy") or ty == "intro_land":
            _place(buf, sound("land"), vt, 0.7 if ty == "intro_land" else 0.45, pan, sp)
            if ty == "intro_land":
                _place(buf, sound("explosion", 1), vt, 0.4, pan, sp)
    elif ty == "step":
        _place(buf, sound("step", hash(e["t"]) % 4), vt, 0.18, pan, sp)
    elif ty in ("dash", "jump", "wall_jump"):
        _place(buf, sound("whoosh", 2), vt, 0.25, pan, sp)
    elif ty in ("clash", "beam_clash"):
        _place(buf, sound("block", 1), vt, 0.6 if ty == "clash" else 0.25, pan, sp)
        if ty == "clash":
            _place(buf, sound("explosion"), vt, 0.4, pan, sp)
    elif ty == "reaction":
        _place(buf, sound({"steam": "water", "conduct": "electric", "freeze": "ice", "wildfire": "fire"}.get(e.get("kind"), "wind")), vt, 0.45, pan, sp)
    elif ty in ("fight",):
        _place(buf, sound("fight"), vt, 0.7, 0.0, 1.0)
    elif ty == "round_start":
        _place(buf, sound("fight", 1), vt, 0.4, 0.0, 1.0)
    elif ty == "victory":
        _place(buf, sound("victory"), vt, 0.7, 0.0, 1.0)
    elif ty in ("burst", "counter"):
        _place(buf, sound("heavy", 2), vt, 0.6, pan, sp)
    elif ty in ("grab", "throw", "wall_hit"):
        _place(buf, sound("heavy", 3), vt, 0.55, pan, sp)
    elif ty == "charge_start":
        _place(buf, sound("charge", 1), vt, 0.3, pan, sp)
