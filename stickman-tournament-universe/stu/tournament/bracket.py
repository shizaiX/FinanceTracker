"""Single-elimination bracket with balanced byes."""
from __future__ import annotations

import math


def next_pow2(n):
    return 1 << max(1, math.ceil(math.log2(n)))


def seed_positions(size):
    """Standard bracket order so byes / top seeds are spread evenly."""
    order = [1]
    while len(order) < size:
        m = len(order) * 2 + 1
        order = [x for s in order for x in (s, m - s)]
    return order


def round_name(n_matches_in_round, is_last):
    if is_last:
        return "final"
    return {2: "semifinals", 4: "quarterfinals"}.get(n_matches_in_round, f"round_of_{n_matches_in_round * 2}")


def build_bracket(fighter_ids, rng, initial="random"):
    ids = list(fighter_ids)
    if initial == "random":
        rng.shuffle(ids)
    n = len(ids)
    size = next_pow2(n)
    rounds_n = int(math.log2(size))
    pos = seed_positions(size)          # seed number per slot
    slots = [ids[s - 1] if s <= n else None for s in pos]  # seeds > n are byes
    rounds = []
    matches = []
    mid = 0
    prev = []
    for r in range(rounds_n):
        cur = []
        count = size >> (r + 1)
        rname = round_name(count, r == rounds_n - 1)
        for i in range(count):
            mid += 1
            if r == 0:
                a, b = slots[2 * i], slots[2 * i + 1]
                m = {"id": f"m{mid:03d}", "round": r, "round_name": rname, "index": i, "a": a, "b": b,
                     "src": [None, None], "winner": None, "status": "pending", "scores": None}
                if a is None or b is None:
                    m["status"] = "bye"
                    m["winner"] = a or b
            else:
                sa, sb = prev[2 * i], prev[2 * i + 1]
                m = {"id": f"m{mid:03d}", "round": r, "round_name": rname, "index": i, "a": None, "b": None,
                     "src": [sa["id"], sb["id"]], "winner": None, "status": "pending", "scores": None}
            cur.append(m)
            matches.append(m)
        rounds.append([m["id"] for m in cur])
        prev = cur
    bracket = {"size": size, "participants": n, "rounds": rounds, "matches": {m["id"]: m for m in matches}, "order": [m["id"] for m in matches]}
    propagate(bracket)
    return bracket


def propagate(bracket):
    ms = bracket["matches"]
    changed = True
    while changed:
        changed = False
        for m in ms.values():
            if m["round"] == 0:
                continue
            for k in (0, 1):
                src = ms[m["src"][k]]
                key = "a" if k == 0 else "b"
                if src["winner"] and m[key] != src["winner"]:
                    m[key] = src["winner"]
                    changed = True
            if m["status"] == "pending" and m["a"] and m["b"] is None and ms[m["src"][1]]["status"] == "bye_empty":
                pass
    return bracket


def ready_matches(bracket):
    return [bracket["matches"][mid] for mid in bracket["order"]
            if bracket["matches"][mid]["status"] == "pending" and bracket["matches"][mid]["a"] and bracket["matches"][mid]["b"]]


def record_result(bracket, mid, winner, scores):
    m = bracket["matches"][mid]
    assert winner in (m["a"], m["b"]), "winner must be a participant"
    m["winner"] = winner
    m["scores"] = scores
    m["status"] = "done"
    propagate(bracket)


def champion(bracket):
    final = bracket["matches"][bracket["rounds"][-1][0]]
    return final["winner"]


def next_opponent_line(bracket, mid, names):
    """'NEXT: X vs Y' style teaser for the match after `mid`."""
    ms = bracket["matches"]
    for m in ms.values():
        if mid in m["src"]:
            other = m["src"][1] if m["src"][0] == mid else m["src"][0]
            o = ms[other]
            label = m["round_name"].replace("_", " ").upper()
            if o["winner"]:
                return f"NEXT: {label} vs {names[o['winner']]}"
            if o["a"] and o["b"]:
                return f"NEXT: {label} vs {names[o['a']]} / {names[o['b']]}"
            return f"ADVANCES TO THE {label}"
    return None


def validate_bracket(bracket):
    issues = []
    ms = bracket["matches"]
    for m in ms.values():
        if m["status"] == "done":
            if m["winner"] not in (m["a"], m["b"]):
                issues.append(f"{m['id']}: winner not a participant")
            if not m["scores"] or max(m["scores"]) < 1:
                issues.append(f"{m['id']}: missing scores")
        if m["round"] > 0 and m["status"] == "done":
            for k, key in ((0, "a"), (1, "b")):
                if ms[m["src"][k]]["winner"] != m[key]:
                    issues.append(f"{m['id']}: participant {key} does not match winner of {m['src'][k]}")
    return issues
