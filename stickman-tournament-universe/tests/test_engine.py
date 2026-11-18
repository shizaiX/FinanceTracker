"""Automated tests: determinism, scoring, duration, bracket, techniques,
persistence, rig integrity, config. Run: python -m pytest tests -q"""
import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stu.animation.rig import BONES, J, solve_local, to_world  # noqa: E402
from stu.animation.poses import POSES, STANCES  # noqa: E402
from stu.combat.combinations import combination_for, pair_compatibility  # noqa: E402
from stu.combat.director import choose_archetype  # noqa: E402
from stu.combat.fighters import generate_fighters  # noqa: E402
from stu.combat.simulation import Match  # noqa: E402
from stu.combat.techniques import make_technique, validate  # noqa: E402
from stu.config import load_config, resolve_auto  # noqa: E402
from stu.core.rng import RNG  # noqa: E402
from stu.persistence.library import Library, LibraryError, Universe  # noqa: E402
from stu.qa.validate import validate_match  # noqa: E402
from stu.themes.arenas import tournament_arenas  # noqa: E402
from stu.themes.generator import generate_theme, load_or_create_theme  # noqa: E402
from stu.tournament import bracket as B  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def setup(seed, theme="elements", tmp=None):
    tmp = tmp or tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "themes"), exist_ok=True)
    cfg = load_config(os.path.join(ROOT, "config.yaml"), [(["tournament", "random_seed"], seed), (["tournament", "theme"], theme)])
    u = Universe(tmp)
    rng = RNG(seed)
    th = load_or_create_theme(u, theme, rng, 3)
    cfg = resolve_auto(cfg, len(th["abilities"]))
    fs = generate_fighters(th, cfg, rng.stream("fighters"), u)
    return cfg, u, th, fs, rng


def run_match(seed, theme="elements"):
    cfg, u, th, fs, rng = setup(seed, theme)
    m = Match(cfg, fs[0], fs[1], th, u, rng.stream("m"), dict(u["techniques"].items),
              choose_archetype(fs[0], fs[1], "round", rng), tournament_arenas(th, 1, rng.stream("a"), "t")[0])
    return cfg, u, vars(m.run())


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_match_rules(seed):
    cfg, u, r = run_match(seed)
    assert validate_match(r, cfg, u["techniques"].items) == []
    assert sorted(r["scores"])[1] == 3 and sorted(r["scores"])[0] < 3
    assert r["final_point_t"] >= cfg["tournament"]["minimum_fight_duration_seconds"]


def test_determinism():
    _, _, a = run_match(5)
    _, _, b = run_match(5)
    assert a["timeline_hash"] == b["timeline_hash"]
    assert a["scores"] == b["scores"] and a["points"] == b["points"]


def test_other_themes_and_procedural_theme():
    for theme in ("weapons", "dragon pirates"):
        cfg, u, r = run_match(3, theme)
        assert validate_match(r, cfg) == []


@pytest.mark.parametrize("n", [2, 3, 5, 6, 8, 12, 16])
def test_bracket_with_byes(n):
    br = B.build_bracket([f"f{i}" for i in range(n)], RNG(1), "random")
    byes = [m for m in br["matches"].values() if m["status"] == "bye"]
    assert len(byes) == br["size"] - n
    played = 0
    while B.ready_matches(br):
        m = B.ready_matches(br)[0]
        B.record_result(br, m["id"], m["a"], [3, 1])
        played += 1
    assert played == n - 1          # byes never count as fights
    assert B.champion(br) is not None
    assert B.validate_bracket(br) == []


def test_technique_validation_rejects_nonsense():
    assert not validate({"delivery": "sweep", "movement": "leap", "modifiers": [], "timing": "instant", "abilities": []}, [])[0]
    assert not validate({"delivery": "punch", "movement": "none", "modifiers": ["split"], "timing": "instant", "abilities": []}, [])[0]
    assert not validate({"delivery": "beam", "movement": "none", "modifiers": [], "timing": "instant", "abilities": []}, [])[0]
    assert validate({"delivery": "kick", "movement": "dash", "modifiers": [], "timing": "instant", "abilities": []}, [])[0]


def test_combinations_and_dedup():
    cfg, u, th, fs, rng = setup(4)
    ab = {a["name"]: a for a in th["abilities"]}
    assert combination_for([ab["Fire"], ab["Wind"]]) is not None
    assert pair_compatibility(ab["Fire"], ab["Fire"])[0] < 0.45
    spec = {"delivery": "projectile", "movement": "none", "modifiers": ["split"], "timing": "instant", "abilities": [ab["Fire"]["id"]]}
    t1, s1 = make_technique(spec, [ab["Fire"]], RNG(1), u)
    t2, s2 = make_technique(dict(spec), [ab["Fire"]], RNG(2), u)
    assert t1["id"] == t2["id"] and s2 == "existing"


def test_library_persistence_and_versioning():
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "library", "techniques.json")
    lib = Library("techniques", p)
    assert lib.put("tq_1", {"name": "x", "signature": {}, "delivery": "punch"})
    assert not lib.put("tq_1", {"name": "y", "signature": {}, "delivery": "punch"})
    lib.save()
    assert Library("techniques", p).get("tq_1")["name"] == "x"
    with open(p, "w") as f:
        f.write('{"schema": "stu.other", "version": 1, "items": {}}')
    with pytest.raises(LibraryError):
        Library("techniques", p)


def test_rig_bone_lengths_constant():
    for pose in list(POSES.values()) + list(STANCES.values()):
        pts = to_world(solve_local(pose), pose["rot"], 1.0, 0.0, -1)
        for a, b, L in BONES:
            d = math.hypot(pts[J[a]][0] - pts[J[b]][0], pts[J[a]][1] - pts[J[b]][1])
            assert abs(d - L) < 1e-3


def test_config_requires_only_three_values():
    cfg = load_config(None, [(["tournament", "theme"], "cosmic"), (["tournament", "participants"], 5),
                             (["tournament", "abilities_per_fighter"], 3)])
    r = resolve_auto(cfg, 8)
    assert r["tournament"]["random_seed"] and r["combat"]["combat_speed"] == 1.0
    with pytest.raises(ValueError):
        load_config(None, [(["tournament", "participants"], 1)])


def test_theme_packs_and_composition():
    pir = generate_theme("pirates", RNG(1))
    assert pir["generated_by"] == "pack" and "hook_hand" in pir["costumes"]
    assert any(a.get("weapon") == "cutlass" for a in pir["abilities"])
    assert any(a.get("projectile") == "bullet" for a in pir["abilities"])
    combo = generate_theme("space pirates", RNG(1))
    assert combo["generated_by"] == "composition" and set(combo["packs"]) == {"cosmic", "pirates"}
    drag = generate_theme("dragons", RNG(1))
    assert any(a.get("origin") == "mouth" for a in drag["abilities"])


def test_new_arena_every_tournament():
    th = generate_theme("pirates", RNG(1))
    a1 = tournament_arenas(th, 3, RNG(1, "arenas"), "t1")
    a2 = tournament_arenas(th, 3, RNG(2, "arenas"), "t2")
    assert len({a["biome"] for a in a1}) == 3          # distinct scenes per round
    assert [a["name"] for a in a1] != [a["name"] for a in a2] or [a["sky"] for a in a1] != [a["sky"] for a in a2]


def test_theme_first_combat():
    cfg, u, th, fs, rng = setup(2, "pirates")
    themed = total = 0
    for seed in (2, 3):
        cfg, u, r = run_match(seed, "pirates")
        for e in r["events"]:
            if e["type"] == "technique":
                total += 1
                themed += bool(u["techniques"].get(e["tech"])["abilities"])
    assert themed / total > 0.8


def test_physical_abilities_never_get_energy_blades():
    from stu.combat.techniques import validate
    th = generate_theme("pirates", RNG(1))
    ab = {a["name"]: a for a in th["abilities"]}
    spec = lambda names: {"delivery": "summon_weapon", "movement": "none", "modifiers": [], "timing": "instant",
                          "abilities": [ab[n]["id"] for n in names]}
    assert not validate(spec(["Rum Bottle"]), [ab["Rum Bottle"]])[0]       # bottle is not a sword
    assert not validate(spec(["Flintlock"]), [ab["Flintlock"]])[0]         # pistol is not a sword
    assert validate(spec(["Cutlass"]), [ab["Cutlass"]])[0]
    el = generate_theme("elements", RNG(1))
    fire = next(a for a in el["abilities"] if a["name"] == "Fire")
    assert validate(dict(spec([]), abilities=[fire["id"]]), [fire])[0]      # a supernatural fire blade is fine


def test_simultaneous_callouts_get_separate_slots():
    from stu.rendering.renderer import SceneRenderer
    evs = [{"type": "callout", "t": 1.0, "name": "A", "abilities": [], "fighter": 0, "tier": "fusion", "tech": "a"},
           {"type": "callout", "t": 1.2, "name": "B", "abilities": [], "fighter": 1, "tier": "fusion", "tech": "b"},
           {"type": "callout", "t": 1.3, "name": "C", "abilities": [], "fighter": 0, "tier": "fusion", "tech": "c"}]
    fake = SceneRenderer.__new__(SceneRenderer)
    fake.events, fake.abilities = evs, {}
    fake.fighters = [{"name": "X"}, {"name": "Y"}]
    items = fake._layout_callouts()
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            overlap = a["t"] < b["t"] + b["dur"] and b["t"] < a["t"] + a["dur"]
            assert not (overlap and a["slot"] == b["slot"]), (a["name"], b["name"])


def test_claude_theme_pack_generation(monkeypatch, tmp_path):
    """Exercises the real Claude code path with a mocked SDK client."""
    import json as _json
    import types
    import anthropic
    from stu.combat.techniques import DELIVERIES
    from stu.themes.packs import WEAPONS
    fixture = os.path.join(ROOT, "tests", "fixtures", "wild_west_pack.json")
    calls = []

    class FakeMessages:
        def create(self, **kw):
            calls.append(kw)
            _json.dumps(kw["output_config"]["format"]["schema"])  # schema must be serialisable
            return types.SimpleNamespace(stop_reason="end_turn", model=kw["model"],
                                         content=[types.SimpleNamespace(type="text", text=open(fixture).read())])

    class FakeClient:
        def __init__(self, *a, **k):
            self.beta = types.SimpleNamespace(messages=FakeMessages())

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    u = Universe(str(tmp_path))
    th = load_or_create_theme(u, "wild west", RNG(3), 0, mode="auto", log=lambda *_: None)
    assert calls and calls[0]["model"] == "claude-opus-5-5"
    assert th["generated_by"] == "claude" and len(th["abilities"]) >= 10
    assert "wild_west_bowie_knife" in WEAPONS and any(b.startswith("wild_west_") for b in th["biomes"])
    # saved and reused: a second load must not call Claude again
    calls.clear()
    th2 = load_or_create_theme(Universe(str(tmp_path)), "wild west", RNG(3), 0, mode="auto", log=lambda *_: None)
    assert not calls and th2["key"] == th["key"]
    # the generated theme fights validly
    cfg = load_config(os.path.join(ROOT, "config.yaml"), [(["tournament", "random_seed"], 4), (["tournament", "theme"], "wild west")])
    cfg = resolve_auto(cfg, len(th["abilities"]))
    fs = generate_fighters(th, cfg, RNG(4).stream("f"), u)
    arena = tournament_arenas(th, 1, RNG(4).stream("a"), "t")[0]
    m = Match(cfg, fs[0], fs[1], th, u, RNG(4).stream("m"), dict(u["techniques"].items), "rivalry", arena)
    r = vars(m.run())
    assert validate_match(r, cfg) == []


def test_theme_generation_falls_back_without_credentials(monkeypatch, tmp_path):
    import anthropic

    class NoAuthMessages:
        def create(self, **kw):
            raise TypeError("Could not resolve authentication method")

    class NoAuthClient:
        def __init__(self, *a, **k):
            import types
            self.beta = types.SimpleNamespace(messages=NoAuthMessages())

    monkeypatch.setattr(anthropic, "Anthropic", NoAuthClient)
    th = load_or_create_theme(Universe(str(tmp_path)), "cosmic powers", RNG(1), 0, mode="auto", log=lambda *_: None)
    assert th["generated_by"] in ("composition", "pack", "procedural") and len(th["abilities"]) >= 4


def test_discovery_notices_never_share_a_line():
    from stu.rendering.renderer import SceneRenderer
    evs = [{"type": "discovery", "t": t, "name": n, "fighter": f, "tech": n}
           for t, n, f in ((14.03, "A", 1), (14.84, "B", 1), (15.08, "C", 0), (15.98, "D", 1), (16.0, "E", 0))]
    fake = SceneRenderer.__new__(SceneRenderer)
    fake.events, fake.abilities = evs, {}
    fake.fighters = [{"name": "X"}, {"name": "Y"}]
    fake.fcol = [(1, 0, 0), (0, 1, 0)]
    _, disc = fake._layout_labels()
    for i, a in enumerate(disc):
        for b in disc[i + 1:]:
            overlap = a["t"] < b["t"] + b["dur"] and b["t"] < a["t"] + a["dur"]
            assert not (overlap and a["slot"] == b["slot"]), (a["name"], b["name"])
