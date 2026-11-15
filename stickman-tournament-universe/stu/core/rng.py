"""Deterministic, named random streams.

Every subsystem draws from its own stream derived from the master seed and a
name, so adding randomness in one subsystem never shifts another one. The same
seed + config always reproduces the same tournament and the same timelines.
"""
from __future__ import annotations

import hashlib
import math
import random


def derive_seed(*parts) -> int:
    h = hashlib.sha256("::".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big")


class RNG(random.Random):
    def __init__(self, *parts):
        self._parts = tuple(parts)
        super().__init__(derive_seed(*parts))

    def stream(self, *names) -> "RNG":
        return RNG(*self._parts, *names)

    def chance(self, p: float) -> bool:
        return self.random() < p

    def weighted(self, items, weights):
        total = sum(max(0.0, w) for w in weights)
        if total <= 0:
            return self.choice(list(items))
        r = self.random() * total
        acc = 0.0
        for it, w in zip(items, weights):
            acc += max(0.0, w)
            if r <= acc:
                return it
        return list(items)[-1]

    def softmax_choice(self, items, scores, temperature=1.0):
        if not items:
            return None
        t = max(1e-3, temperature)
        m = max(scores)
        weights = [math.exp((s - m) / t) for s in scores]
        return self.weighted(items, weights)

    def jitter(self, value: float, rel: float) -> float:
        return value * (1.0 + self.uniform(-rel, rel))


def stable_noise(seed: int, t: float) -> float:
    """Smooth 1D value noise in [-1, 1], pure function of (seed, t)."""
    i = math.floor(t)
    f = t - i
    def h(n):
        x = (n * 374761393 + seed * 668265263) & 0xFFFFFFFF
        x = (x ^ (x >> 13)) * 1274126177 & 0xFFFFFFFF
        return ((x ^ (x >> 16)) & 0xFFFF) / 32767.5 - 1.0
    u = f * f * (3 - 2 * f)
    return h(i) * (1 - u) + h(i + 1) * u
