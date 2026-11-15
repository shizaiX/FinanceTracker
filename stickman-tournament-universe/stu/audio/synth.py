"""Procedural sound synthesis (100 % original audio — no external assets).

Every sound is generated from noise/oscillators with numpy, so there are no
licensing concerns. Sounds are cached by (name, variant).
"""
from __future__ import annotations

import functools
import zlib

import numpy as np

SR = 48000


def _env(n, a=0.002, d=0.2, curve=4.0):
    t = np.arange(n) / SR
    att = np.clip(t / max(a, 1e-4), 0, 1)
    dec = np.exp(-curve * np.maximum(0, t - a) / max(d, 1e-4))
    return att * dec


def _noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def _lp_fast(x, cutoff):
    """Cheap FFT brick-ish lowpass with smooth roll-off."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (f / cutoff) ** 4)
    return np.fft.irfft(X, len(x))


def _hp_fast(x, cutoff):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    X *= 1 / (1 + (cutoff / np.maximum(f, 1)) ** 4)
    return np.fft.irfft(X, len(x))


def _bp(x, lo, hi):
    return _hp_fast(_lp_fast(x, hi), lo)


def _sine_sweep(n, f0, f1, curve=2.0):
    t = np.linspace(0, 1, n)
    f = f1 + (f0 - f1) * (1 - t) ** curve
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph)


def _norm(x, peak=0.9):
    m = np.max(np.abs(x)) or 1.0
    return (x / m * peak).astype(np.float32)


@functools.lru_cache(maxsize=256)
def sound(name, v=0):
    seed = zlib.crc32(f"{name}:{v}".encode()) & 0xFFFF
    r = np.random.default_rng(seed)
    if name == "punch":
        n = int(0.22 * SR)
        body = _sine_sweep(n, 180 + 30 * v, 55) * _env(n, 0.001, 0.09)
        click = _lp_fast(_noise(n, seed), 3500) * _env(n, 0.0005, 0.02, 6)
        return _norm(body * 0.9 + click * 0.6)
    if name == "kick":
        n = int(0.3 * SR)
        body = _sine_sweep(n, 140 + 20 * v, 42) * _env(n, 0.001, 0.14)
        click = _lp_fast(_noise(n, seed), 2500) * _env(n, 0.0005, 0.03, 6)
        return _norm(body + click * 0.5)
    if name == "heavy":
        n = int(0.6 * SR)
        body = _sine_sweep(n, 120, 32) * _env(n, 0.001, 0.3)
        crunch = _lp_fast(_noise(n, seed), 1800) * _env(n, 0.001, 0.12, 5)
        return _norm(body + crunch * 0.8)
    if name == "whoosh":
        n = int(0.28 * SR)
        x = _noise(n, seed)
        t = np.linspace(0, 1, n)
        x = _bp(x, 400 + 200 * v, 3000 + 800 * v) * np.sin(np.pi * t) ** 2
        return _norm(x, 0.6)
    if name == "block":
        n = int(0.25 * SR)
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, d in ((820, 18), (1310, 22), (2140, 30)))
        x += _hp_fast(_noise(n, seed), 2000) * _env(n, 0.0005, 0.02, 6) * 0.8
        return _norm(x, 0.7)
    if name == "explosion":
        n = int(1.2 * SR)
        x = _lp_fast(_noise(n, seed), 900) * _env(n, 0.003, 0.5, 3)
        sub = _sine_sweep(n, 90, 28) * _env(n, 0.002, 0.4)
        return _norm(x + sub * 0.9)
    if name == "fire":
        n = int(0.7 * SR)
        x = _bp(_noise(n, seed), 300, 4000) * _env(n, 0.03, 0.4, 2.5)
        crack = (r.random(n) > 0.9993).astype(float)
        crack = np.convolve(crack, np.exp(-np.arange(200) / 30), "same")
        return _norm(x + crack * 2.0, 0.75)
    if name == "water":
        n = int(0.6 * SR)
        x = _bp(_noise(n, seed), 200, 2500) * _env(n, 0.01, 0.35, 3)
        t = np.arange(n) / SR
        bl = sum(np.sin(2 * np.pi * (500 + 900 * r.random()) * t * (1 + 2 * t)) * _env(n, 0.001, 0.05) *
                 (np.arange(n) > int(r.random() * n * 0.5)) for _ in range(4))
        return _norm(x + bl * 0.4, 0.75)
    if name == "ice":
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * (18 + 10 * k)) for k, f in enumerate((2400, 3170, 4430, 5900)))
        x += _hp_fast(_noise(n, seed), 4000) * _env(n, 0.001, 0.1, 4) * 0.6
        return _norm(x, 0.65)
    if name == "electric":
        n = int(0.55 * SR)
        t = np.arange(n) / SR
        saw = ((t * (95 + 15 * v)) % 1.0) * 2 - 1
        buzz = saw * (r.random(n) > 0.35)
        x = _hp_fast(buzz + _noise(n, seed) * 0.5, 600) * _env(n, 0.002, 0.3, 3)
        return _norm(x, 0.7)
    if name == "earth":
        n = int(0.9 * SR)
        x = _lp_fast(_noise(n, seed), 400) * _env(n, 0.01, 0.6, 3)
        return _norm(x + _sine_sweep(n, 70, 30) * _env(n, 0.005, 0.4) * 0.6)
    if name == "wind":
        n = int(0.7 * SR)
        t = np.linspace(0, 1, n)
        x = _bp(_noise(n, seed), 600, 2400) * np.sin(np.pi * t) ** 1.5
        return _norm(x, 0.6)
    if name == "metal":
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, d in ((523, 6), (1187, 8), (1874, 10), (2911, 14)))
        x += _hp_fast(_noise(n, seed), 3000) * _env(n, 0.0005, 0.015, 6)
        return _norm(x, 0.6)
    if name == "nature":
        n = int(0.6 * SR)
        x = _bp(_noise(n, seed), 1500, 6000) * _env(n, 0.02, 0.3, 3) * (0.6 + 0.4 * np.sin(np.arange(n) / SR * 2 * np.pi * 30))
        return _norm(x, 0.55)
    if name == "light":
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f * t * (1 + 0.6 * t)) for f in (880, 1320, 1760)) * _env(n, 0.005, 0.35, 3)
        return _norm(x, 0.5)
    if name == "shadow":
        n = int(0.7 * SR)
        x = _lp_fast(_noise(n, seed), 500) * _env(n, 0.05, 0.4, 2) + _sine_sweep(n, 160, 60) * _env(n, 0.02, 0.4) * 0.6
        return _norm(x, 0.65)
    if name == "gravity":
        n = int(0.8 * SR)
        x = _sine_sweep(n, 40, 140, 0.5) * _env(n, 0.05, 0.6, 2) + _lp_fast(_noise(n, seed), 300) * _env(n, 0.05, 0.5) * 0.5
        return _norm(x, 0.75)
    if name == "sound":
        n = int(0.5 * SR)
        t = np.arange(n) / SR
        x = np.sign(np.sin(2 * np.pi * 220 * t)) * np.sin(2 * np.pi * 7 * t) * _env(n, 0.005, 0.3, 3)
        return _norm(_lp_fast(x, 3000), 0.55)
    if name == "charge":
        n = int(0.9 * SR)
        t = np.linspace(0, 1, n)
        x = _sine_sweep(n, 1200, 200, 1.0) * t * 0.4 + _bp(_noise(n, seed), 800, 5000) * t * 0.3
        return _norm(x * np.minimum(1, (1 - t) * 10), 0.5)
    if name == "teleport":
        n = int(0.35 * SR)
        x = _sine_sweep(n, 300, 2400, 0.5) * _env(n, 0.002, 0.2, 3) + _hp_fast(_noise(n, seed), 3000) * _env(n, 0.001, 0.08) * 0.5
        return _norm(x, 0.55)
    if name == "land":
        n = int(0.3 * SR)
        x = _lp_fast(_noise(n, seed), 600) * _env(n, 0.001, 0.12, 4) + _sine_sweep(n, 90, 40) * _env(n, 0.001, 0.1) * 0.7
        return _norm(x, 0.6)
    if name == "step":
        n = int(0.08 * SR)
        x = _lp_fast(_noise(n, seed), 1200) * _env(n, 0.001, 0.03, 5)
        return _norm(x, 0.25)
    if name == "score":
        n = int(1.4 * SR)
        t = np.arange(n) / SR
        notes = (392.0, 523.25, 659.25, 783.99)
        x = sum(np.sin(2 * np.pi * f * t) * (t > k * 0.06) * np.exp(-np.maximum(0, t - k * 0.06) * 2.5) for k, f in enumerate(notes))
        boom = _sine_sweep(n, 110, 35) * _env(n, 0.001, 0.4)
        return _norm(x * 0.5 + boom, 0.85)
    if name == "ko":
        n = int(2.2 * SR)
        t = np.arange(n) / SR
        boom = _sine_sweep(n, 100, 25) * _env(n, 0.001, 0.9, 3)
        noise = _lp_fast(_noise(n, seed), 1200) * _env(n, 0.002, 0.6, 3)
        chord = sum(np.sin(2 * np.pi * f * t) for f in (130.81, 196.0, 261.63, 329.63)) * np.exp(-t * 1.2) * (t > 0.15)
        return _norm(boom + noise * 0.7 + chord * 0.25, 0.95)
    if name == "fight":
        n = int(0.8 * SR)
        t = np.arange(n) / SR
        x = sum(np.sin(2 * np.pi * f * t) for f in (293.66, 440.0, 587.33)) * np.exp(-t * 3)
        return _norm(x + _lp_fast(_noise(n, seed), 2000) * _env(n, 0.001, 0.08) * 0.6, 0.6)
    if name == "victory":
        n = int(2.5 * SR)
        t = np.arange(n) / SR
        seq = (523.25, 659.25, 783.99, 1046.5)
        x = sum(np.sin(2 * np.pi * f * t) * (t > k * 0.14) * np.exp(-np.maximum(0, t - k * 0.14) * (1.5 if k == 3 else 5)) for k, f in enumerate(seq))
        return _norm(x, 0.6)
    if name == "slowmo":
        n = int(0.9 * SR)
        x = _sine_sweep(n, 600, 80, 0.6) * _env(n, 0.01, 0.6, 2) + _lp_fast(_noise(n, seed), 800) * _env(n, 0.01, 0.5) * 0.5
        return _norm(x, 0.5)
    if name == "gunshot":
        n = int(0.7 * SR)
        crack = _hp_fast(_noise(n, seed), 1500) * _env(n, 0.0003, 0.03, 6)
        boom = _lp_fast(_noise(n, seed + 1), 600) * _env(n, 0.001, 0.25, 3)
        body = _sine_sweep(n, 160, 50) * _env(n, 0.001, 0.12)
        return _norm(crack * 1.2 + boom * 0.8 + body * 0.6, 0.95)
    if name == "slash":
        n = int(0.35 * SR)
        t = np.linspace(0, 1, n)
        swish = _bp(_noise(n, seed), 1500, 7000) * np.sin(np.pi * np.clip(t * 1.6, 0, 1)) ** 2
        tt = np.arange(n) / SR
        ring = sum(np.sin(2 * np.pi * f * tt) * np.exp(-tt * 9) for f in (2300, 3410, 5200)) * (tt > 0.08)
        return _norm(swish + ring * 0.35, 0.7)
    if name == "riser":
        n = int(1.0 * SR)
        t = np.linspace(0, 1, n)
        return _norm(_bp(_noise(n, seed), 500, 6000) * t ** 2, 0.4)
    n = int(0.2 * SR)
    return _norm(_noise(n, seed) * _env(n, 0.001, 0.05))


VOICE_OF = {"fire": "fire", "water": "water", "ice": "ice", "electric": "electric", "earth": "earth", "wind": "wind",
            "metal": "metal", "nature": "nature", "light": "light", "shadow": "shadow", "gravity": "gravity", "sound": "sound"}


def music(duration, bpm=124, seed=1, intensity=None):
    """Procedural percussion + bass bed. intensity(t)->0..1 shapes layers."""
    n = int(duration * SR)
    out = np.zeros(n, dtype=np.float32)
    beat = 60.0 / bpm
    rng = np.random.default_rng(seed)
    kick = sound("kick", 3) * 0.55
    hat_n = int(0.05 * SR)
    hat = (_hp_fast(_noise(hat_n, 99), 7000) * _env(hat_n, 0.0005, 0.02, 5)).astype(np.float32) * 0.18
    snare_n = int(0.25 * SR)
    snare = (_bp(_noise(snare_n, 77), 900, 6000) * _env(snare_n, 0.001, 0.09, 4)).astype(np.float32) * 0.35
    scale = [55.0, 65.41, 73.42, 82.41, 98.0]
    pattern = [0, 0, 3, 0, 2, 0, 4, 1]
    i = 0
    t = 0.0
    while t < duration:
        it = intensity(t) if intensity else 0.6
        s0 = int(t * SR)

        def put(x, s, g=1.0):
            e = min(n, s + len(x))
            if s < n:
                out[s:e] += x[:e - s] * g
        if i % 2 == 0:
            put(kick, s0, 0.7 + 0.3 * it)
        if it > 0.45 and i % 4 == 2:
            put(snare, s0, it)
        put(hat, s0 + int(beat * 0.5 * SR), 0.6 + 0.4 * it)
        if it > 0.75:
            put(hat, s0 + int(beat * 0.25 * SR), 0.5)
            put(hat, s0 + int(beat * 0.75 * SR), 0.5)
        f = scale[pattern[(i // 2) % len(pattern)]]
        bn = int(beat * SR)
        tt = np.arange(bn) / SR
        bass = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 3) * 0.22 * (0.5 + 0.5 * it)
        put(bass.astype(np.float32), s0)
        t += beat
        i += 1
    return out
