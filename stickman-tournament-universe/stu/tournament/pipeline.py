"""End-to-end production pipeline with checkpointing.

config -> libraries -> theme -> fighters -> bracket -> (simulate -> validate ->
render -> audio -> export -> validate video -> record -> advance)* -> bracket
cards -> champion -> complete tournament -> highlights -> metadata.

All progress is stored in tournaments/<slug>/state.json; every step is skipped
when already complete, so an interrupted run resumes where it stopped.
"""
from __future__ import annotations

import copy
import gzip
import json
import os
import pickle
import re
import time

import numpy as np

from .. import PROJECT_ROOT
from ..animation.poses import export_templates
from ..audio.mixer import build_audio
from ..audio.synth import SR, sound
from ..combat.director import choose_archetype
from ..combat.fighters import generate_fighters
from ..combat.simulation import Match
from ..config import resolve_auto
from ..core.rng import RNG
from ..persistence.library import Universe, atomic_write_json, stable_id
from ..qa.validate import contact_sheet, validate_match, validate_video
from ..rendering.camera import build_camera
from ..rendering.cards import BracketCard, RosterCard
from ..rendering.encoder import cleanup_work, concat_videos, cut_clip, render_video, shrink_to
from ..rendering.renderer import SceneRenderer
from ..rendering.timemap import build_timemap
from ..themes.arenas import tournament_arenas
from ..themes.generator import load_or_create_theme
from . import bracket as B
from .metadata import match_metadata, tournament_metadata

STAGE_LABEL = {"final": "GRAND FINAL", "semifinals": "SEMIFINAL", "quarterfinals": "QUARTERFINAL"}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def log(msg):
    print(time.strftime("[%H:%M:%S] ") + msg, flush=True)


class Tournament:
    def __init__(self, path, universe=None):
        self.path = path
        with open(os.path.join(path, "state.json")) as f:
            self.state = json.load(f)
        if self.state.get("schema") != "stu.tournament":
            raise ValueError("not a tournament state file")
        self.root = self.state.get("root", PROJECT_ROOT)
        self.u = universe or Universe(self.root)
        self.cfg = self.state["config"]
        self.theme = self.u.load_theme(self.state["theme"])
        from ..themes.ai_pack import register_theme_assets
        register_theme_assets(self.theme)
        self.abilities = {a["id"]: a for a in self.theme["abilities"]}
        self.fighters = {f["id"]: f for f in self.state["fighters"]}
        self.names = {fid: f["name"] for fid, f in self.fighters.items()}
        self.export_dir = os.path.join(self.root, "exports", self.state["slug"])

    # ------------------------------------------------------------- state io
    def save(self):
        self.state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        atomic_write_json(os.path.join(self.path, "state.json"), self.state)
        atomic_write_json(os.path.join(self.export_dir, "tournament_bracket.json"), {
            "name": self.state["name"], "theme": self.state["theme"], "seed": self.cfg["tournament"]["random_seed"],
            "fighters": {fid: {"name": f["name"], "abilities": f["ability_names"], "color": f["color"], "personality": f["personality"]}
                         for fid, f in self.fighters.items()},
            "bracket": self.state["bracket"], "champion": self.state.get("champion")})
        self.u.save_all()

    # ------------------------------------------------------------- paths
    def match_dir(self, m):
        rn = m["round_name"]
        if rn == "final":
            d = "final"
        elif rn == "semifinals":
            d = "semifinals"
        else:
            d = f"round_{m['round'] + 1:02d}"
        return os.path.join(self.export_dir, d)

    def match_video(self, m):
        return os.path.join(self.match_dir(m), f"match_{int(m['id'][1:]):03d}.mp4")

    def cache_path(self, mid):
        return os.path.join(self.path, "cache", f"{mid}.pkl.gz")

    # ------------------------------------------------------------- matches
    def stage_label(self, m):
        label = STAGE_LABEL.get(m["round_name"], m["round_name"].replace("_", " ").upper())
        if m["round_name"] == "final":
            return label
        return f"{label} · MATCH {m['index'] + 1}"

    def simulate(self, m):
        cp = self.cache_path(m["id"])
        if os.path.exists(cp):
            with gzip.open(cp, "rb") as f:
                return pickle.load(f)
        seed = self.cfg["tournament"]["random_seed"]
        rng = RNG(seed, "match", m["id"])
        fa, fb = self.fighters[m["a"]], self.fighters[m["b"]]
        stage = {"final": "final", "semifinals": "semifinal"}.get(m["round_name"], "round")
        archetype = choose_archetype(fa, fb, stage, rng.stream("archetype"))
        arenas = self.state.get("arenas")
        if not arenas:  # tournaments created before per-tournament arenas
            arenas = tournament_arenas(self.theme, len(self.state["bracket"]["rounds"]), RNG(seed, "arenas"), self.state["slug"])
            self.state["arenas"] = arenas
        arena = arenas[min(m["round"], len(arenas) - 1)]
        techs = dict(self.u["techniques"].items)
        match = Match(self.cfg, fa, fb, self.theme, self.u, rng, techs, archetype, arena,
                      meta={"tournament": self.state["slug"], "match": m["id"]})
        t0 = time.time()
        r = match.run()
        res = dict(vars(r))
        log(f"  simulated {m['id']} {fa['name']} vs {fb['name']} [{archetype}] -> {res['scores'][0]}-{res['scores'][1]}"
            f" final point @ {res['final_point_t']:.1f}s ({time.time() - t0:.1f}s cpu)")
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with gzip.open(cp, "wb", compresslevel=5) as f:
            pickle.dump(res, f, protocol=pickle.HIGHEST_PROTOCOL)
        return res

    def render_context(self, m, res):
        cfg = self.cfg
        vfs, hook_t = build_timemap(res, cfg["video"]["fps"], cfg["creative"].get("slow_motion", "dramatic"), hook=True)
        cams = build_camera(res, vfs, cfg["video"]["width"], cfg["video"]["height"], cfg["video"]["fps"],
                            float(cfg["creative"].get("screen_shake", 1.0)), "balanced")
        nl = B.next_opponent_line(self.state["bracket"], m["id"], self.names) if m["round_name"] != "final" else "CHAMPION OF THE TOURNAMENT"
        info = {"tournament_name": self.state["name"], "stage_label": self.stage_label(m), "next_line": nl,
                "arena_name": res["arena"].get("name", ""),
                "is_final": m["round_name"] == "final"}
        return {"cfg": cfg, "result": res, "abilities": self.abilities, "fighters": res["fighters"], "vframes": vfs,
                "camera": cams, "arena": res["arena"], "info": info, "hook_t": hook_t}

    def run_match(self, m, render=True):
        res = self.simulate(m)
        issues = validate_match(res, self.cfg, self.u["techniques"].items)
        rec = self.state["matches"].setdefault(m["id"], {})
        rec.update({"scores": res["scores"], "winner": m["a"] if res["winner"] == 0 else m["b"],
                    "final_point_t": round(res["final_point_t"], 3), "archetype": res["archetype"], "arena": res["arena"]["name"],
                    "points": res["points"], "stats": res["stats"], "discoveries": res["discoveries"], "sim_issues": issues,
                    "timeline_hash": res["timeline_hash"]})
        if issues:
            log(f"  QA issues for {m['id']}: {issues}")
        if render and self.cfg["video"].get("export_individual_fights", True):
            out = self.match_video(m)
            if not (rec.get("video") and os.path.exists(out) and rec.get("video_ok")):
                ctx = self.render_context(m, res)
                n = len(ctx["vframes"])
                os.makedirs(os.path.dirname(out), exist_ok=True)
                work = os.path.join(self.path, "work", m["id"])
                os.makedirs(work, exist_ok=True)
                wav = os.path.join(work, "audio.wav")
                log(f"  rendering {m['id']}: {n} frames ({n / self.cfg['video']['fps']:.1f}s video)")
                build_audio(res, ctx["vframes"], self.cfg["video"]["fps"], self.abilities, self.cfg["creative"], wav)
                t0 = time.time()
                fight_only = os.path.join(work, "fight.mp4")
                render_video(lambda: SceneRenderer(ctx), n, fight_only, self.cfg["video"], work, audio_path=wav, log=log)
                # Stage intros live in the same video: roster + bracket before the first
                # match of the tournament, the bracket before the first match of each stage.
                intros = self.stage_intros(m)
                intro_frames = sum(fr for _, fr in intros)
                if intros:
                    concat_videos([p for p, _ in intros] + [fight_only], out)
                else:
                    os.replace(fight_only, out)
                shrink_to(out, self.cfg["video"].get("max_file_mb", 95), self.cfg["video"], log=log)
                total = n + intro_frames
                vissues = validate_video(out, self.cfg, expected_frames=total)
                fps = self.cfg["video"]["fps"]
                rec.update({"video": os.path.relpath(out, self.root), "video_frames": total, "video_seconds": round(total / fps, 3),
                            "intro_seconds": round(intro_frames / fps, 3),
                            "video_issues": vissues, "video_ok": not vissues, "render_seconds": round(time.time() - t0, 1)})
                ko = next((k / fps for k, vf in enumerate(ctx["vframes"])
                           if vf.segment == "fight" and res["final_point_t"] is not None
                           and vf.sim_t >= res["fight_start"] + res["final_point_t"]), None)
                rec["ko_video_t"] = None if ko is None else ko + intro_frames / fps
                # contact sheet of key moments for manual review
                keys, labels = [], []
                for e in res["events"]:
                    if e["type"] in ("score", "ko", "callout", "guard_break") and len(keys) < 12:
                        k = next((i for i, vf in enumerate(ctx["vframes"]) if vf.segment == "fight" and vf.sim_t >= e["t"] + 0.05), None)
                        if k is not None:
                            keys.append(k)
                            labels.append(f"{e['type']} t={e['t'] - res['fight_start']:.1f}s")
                sheet = os.path.join(self.path, "qa", f"{m['id']}_contact.png")
                os.makedirs(os.path.dirname(sheet), exist_ok=True)
                contact_sheet(SceneRenderer(ctx), keys, sheet, labels=labels)
                rec["contact_sheet"] = os.path.relpath(sheet, self.root)
                meta = match_metadata(self, m, res)
                with open(out[:-4] + ".json", "w") as f:
                    json.dump(meta, f, indent=1)
                if vissues:
                    log(f"  VIDEO QA issues: {vissues}")
                else:
                    cleanup_work(work)
                log(f"  exported {os.path.relpath(out, self.root)} in {rec['render_seconds']}s")
        B.record_result(self.state["bracket"], m["id"], rec["winner"], res["scores"])
        self._update_stats(m, res, rec)
        self.save()
        return rec

    def _update_stats(self, m, res, rec):
        if rec.get("stats_recorded"):
            return
        st = self.u["statistics"]
        for side, fid in enumerate((m["a"], m["b"])):
            f = self.fighters[fid]
            won = res["winner"] == side
            car = f.setdefault("career", {"wins": 0, "losses": 0, "points_for": 0, "points_against": 0, "tournaments": []})
            car["wins" if won else "losses"] += 1
            car["points_for"] += res["scores"][side]
            car["points_against"] += res["scores"][1 - side]
            lib_f = self.u["fighters"].get(fid)
            if lib_f is not None:
                lib_f["career"] = car
                self.u["fighters"].dirty = True
            for k, v in res["stats"][side].items():
                st.bump(f"fighter:{fid}", k, v)
            for aid in f["abilities"]:
                st.bump(f"ability:{aid}", "matches", 1)
                st.bump(f"ability:{aid}", "wins", int(won))
        for tid, n in res["tech_uses"].items():
            st.bump(f"technique:{tid}", "uses", n)
        for p in res["points"]:
            st.bump(f"technique:{p['tech']}", "points", 1)
        st.bump("global", "matches", 1)
        st.bump("global", "sim_seconds", round(res["final_point_t"] or 0, 2))
        rec["stats_recorded"] = True

    # ------------------------------------------------------------- cards
    def _card_audio(self, n_frames, kind, path):
        fps = self.cfg["video"]["fps"]
        buf = np.zeros(int(n_frames / fps * SR) + 1, dtype=np.float32)

        def put(x, t, g):
            s = int(t * SR)
            e = min(len(buf), s + len(x))
            buf[s:e] += x[:e - s] * g
        if kind == "champion":
            put(sound("ko"), 0.1, 0.6)
            put(sound("victory"), 0.6, 0.8)
        else:
            put(sound("riser"), 0.0, 0.5)
            put(sound("fight"), 0.5, 0.6)
            for k in range(6):
                put(sound("whoosh", k % 3), 0.6 + 0.35 * k, 0.25)
        import wave
        pcm = (np.clip(np.stack([buf, buf], 1) * 0.8, -1, 1) * 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        return path

    def render_clip(self, key, factory, out, audio_kind="bracket"):
        """Render a presentation clip once (resumable); returns (path, frames)."""
        done = self.state["steps"].get(key)
        probe = factory()
        if done and os.path.exists(os.path.join(self.root, done["path"] if isinstance(done, dict) else done)):
            return os.path.join(self.root, done["path"] if isinstance(done, dict) else done), probe.n
        work = os.path.join(self.path, "work", key)
        os.makedirs(work, exist_ok=True)
        wav = self._card_audio(probe.n, audio_kind, os.path.join(work, "a.wav"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        render_video(factory, probe.n, out, self.cfg["video"], work, audio_path=wav, chunk=10**9, workers=1, log=log)
        issues = validate_video(out, self.cfg, expected_frames=probe.n)
        if issues:
            log(f"  clip QA issues: {issues}")
        cleanup_work(work)
        self.state["steps"][key] = {"path": os.path.relpath(out, self.root), "frames": probe.n}
        self.save()
        return out, probe.n

    def stage_intros(self, m):
        """Intro clips to put in front of match m (empty unless m opens a stage)."""
        br = self.state["bracket"]
        first = next((mid for mid in br["rounds"][m["round"]] if br["matches"][mid]["status"] != "bye"), None)
        if first != m["id"]:
            return []
        clips = []
        idir = os.path.join(self.path, "intros")
        name = self.state["name"].upper()
        if m["round"] == 0:
            clips.append(self.render_clip("intro_roster", lambda: RosterCard(self.cfg, self.state, self.abilities, self.state["name"]),
                                          os.path.join(idir, "roster.mp4")))
            sub = "THE BRACKET IS SET"
        else:
            label = STAGE_LABEL.get(m["round_name"], m["round_name"].replace("_", " ").upper())
            sub = f"{label}S" if label in ("SEMIFINAL", "QUARTERFINAL") else label
        r = m["round"]
        clips.append(self.render_clip(f"intro_bracket_{r + 1:02d}",
                                      lambda: BracketCard(self.cfg, self.state, name, sub, 5.0, None, r),
                                      os.path.join(idir, f"bracket_{r + 1:02d}.mp4")))
        return clips

    def render_card(self, key, title, subtitle, out, duration=6.0, champion=None, upto_round=None):
        done = self.state["steps"].get(key)
        if done and os.path.exists(os.path.join(self.root, done)):
            return os.path.join(self.root, done)
        card = BracketCard(self.cfg, self.state, title, subtitle, duration, champion, upto_round)
        work = os.path.join(self.path, "work", key)
        os.makedirs(work, exist_ok=True)
        wav = self._card_audio(card.n, "champion" if champion else "bracket", os.path.join(work, "a.wav"))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        render_video(lambda: BracketCard(self.cfg, self.state, title, subtitle, duration, champion, upto_round), card.n, out, self.cfg["video"], work,
                     audio_path=wav, chunk=10**9, workers=1, log=log)
        issues = validate_video(out, self.cfg, expected_frames=card.n)
        if issues:
            log(f"  card QA issues: {issues}")
        cleanup_work(work)
        self.state["steps"][key] = os.path.relpath(out, self.root)
        self.save()
        log(f"  exported {os.path.relpath(out, self.root)}")
        return out

    # ------------------------------------------------------------- run
    def run(self, render=True, max_matches=None):
        log(f"Tournament '{self.state['name']}' ({self.state['theme']}, {len(self.fighters)} fighters, seed {self.cfg['tournament']['random_seed']})")
        br = self.state["bracket"]
        done = 0
        while True:
            ready = B.ready_matches(br)
            if not ready:
                break
            m = ready[0]
            prev_round = m["round"]
            log(f"Match {m['id']} ({self.stage_label(m)}): {self.names[m['a']]} vs {self.names[m['b']]}")
            self.run_match(m, render=render)
            done += 1
            if max_matches and done >= max_matches:
                log(f"Stopped after {done} match(es) as requested")
                return
        champ = B.champion(br)
        if champ is None:
            return
        self.state["champion"] = champ
        self.save()
        cf = self.fighters[champ]
        log(f"CHAMPION: {cf['name']}")
        if render:
            wins = [r for r in self.state["matches"].values() if r.get("winner") == champ]
            rec = f"{len(wins)} WINS · " + " · ".join(f"{max(r['scores'])}-{min(r['scores'])}" for r in wins)
            self.render_card("champion", self.state["name"].upper(), rec, os.path.join(self.export_dir, "champion.mp4"), 6.0, champion=champ)
            self.finalize_exports()
        self._finish_history()

    def finalize_exports(self):
        v = self.cfg["video"]
        br = self.state["bracket"]
        if v.get("export_complete_tournament", True) and not self.state["steps"].get("complete"):
            parts = []  # stage intros (roster, brackets) are already inside the match videos
            for r, mids in enumerate(br["rounds"]):
                for mid in mids:
                    rec = self.state["matches"].get(mid)
                    if rec and rec.get("video"):
                        parts.append(os.path.join(self.root, rec["video"]))
            parts.append(os.path.join(self.root, self.state["steps"]["champion"]))
            out = os.path.join(self.export_dir, "complete_tournament.mp4")
            try:
                concat_videos(parts, out)
            except Exception:
                concat_videos(parts, out, reencode=True, video_cfg=v)
            self.state["steps"]["complete"] = os.path.relpath(out, self.root)
            self.save()
            log(f"  exported {os.path.relpath(out, self.root)}")
        if v.get("export_highlights", True) and not self.state["steps"].get("highlights"):
            hdir = os.path.join(self.export_dir, "highlights")
            os.makedirs(hdir, exist_ok=True)
            clips = []
            for mid in br["order"]:
                rec = self.state["matches"].get(mid)
                if not rec or not rec.get("video") or rec.get("ko_video_t") is None:
                    continue
                out = os.path.join(hdir, f"{mid}_finish.mp4")
                cut_clip(os.path.join(self.root, rec["video"]), rec["ko_video_t"] - 2.2, 5.5, out, v)
                clips.append(out)
            champ_card = os.path.join(self.root, self.state["steps"]["champion"])
            clips.append(champ_card)
            out = os.path.join(self.export_dir, "highlights.mp4")
            concat_videos(clips, out, reencode=True, video_cfg=v)
            self.state["steps"]["highlights"] = os.path.relpath(out, self.root)
            self.save()
            log(f"  exported {os.path.relpath(out, self.root)}")
        with open(os.path.join(self.export_dir, "metadata.json"), "w") as f:
            json.dump(tournament_metadata(self), f, indent=1)

    def _finish_history(self):
        th = self.u["tournaments"]
        th.put(self.state["slug"], {"name": self.state["name"], "theme": self.state["theme"], "seed": self.cfg["tournament"]["random_seed"],
                                    "champion": self.state.get("champion"), "champion_name": self.names.get(self.state.get("champion")),
                                    "participants": len(self.fighters), "finished": time.strftime("%Y-%m-%dT%H:%M:%S")})
        th.items[self.state["slug"]]["champion"] = self.state.get("champion")
        th.dirty = True
        for fid, f in self.fighters.items():
            lib_f = self.u["fighters"].get(fid)
            if lib_f is not None and self.state["slug"] not in lib_f["career"]["tournaments"]:
                lib_f["career"]["tournaments"].append(self.state["slug"])
                self.u["fighters"].dirty = True
        self.u.save_all()


def _existing_names(root):
    d = os.path.join(root, "tournaments")
    out = set()
    for slug in (os.listdir(d) if os.path.isdir(d) else []):
        try:
            with open(os.path.join(d, slug, "state.json")) as f:
                out.add(json.load(f).get("name"))
        except (OSError, ValueError):
            pass
    return out


def create_tournament(cfg, root=PROJECT_ROOT, universe=None, custom_abilities=None):
    """Generate everything the tournament needs and persist it."""
    u = universe or Universe(root)
    raw_unique = cfg["tournament"]["abilities_unique"]
    seed = cfg["tournament"]["random_seed"]
    t = cfg["tournament"]
    probe_rng = RNG(seed if seed is not None else 0, "theme")
    needed = t["participants"] * t["abilities_per_fighter"] if raw_unique is True else t["abilities_per_fighter"] + 1
    theme = load_or_create_theme(u, t["theme"], probe_rng, needed, custom_abilities,
                                 mode=cfg["creative"].get("theme_generator", "auto"), log=log)
    cfg = resolve_auto(cfg, len(theme["abilities"]))
    seed = cfg["tournament"]["random_seed"]
    rng = RNG(seed)
    # library bootstrapping: animation templates are persistent data too
    for k, v in export_templates().items():
        u["animations"].put(k, v)
    name = t["name"]
    if name in (None, "auto"):
        # Tournaments are never numbered.
        # The tournament title is just the theme (no numbering, no extra words).
        name = theme["name"].strip().title()
    slug = f"{slugify(name)}_{seed}"
    path = os.path.join(root, "tournaments", slug)
    if os.path.exists(os.path.join(path, "state.json")):
        log(f"Tournament {slug} already exists — resuming")
        return Tournament(path, u)
    fighters = generate_fighters(theme, cfg, rng.stream("fighters"), u)
    br = B.build_bracket([f["id"] for f in fighters], rng.stream("bracket"), t["initial_matchmaking"])
    u["render_configs"].put(stable_id("rc", cfg["video"]), {"video": cfg["video"], "creative": cfg["creative"]})
    arenas = tournament_arenas(theme, len(br["rounds"]), rng.stream("arenas"), slug)
    for a in arenas:
        u["arenas"].put(a["id"], dict(a, tournament=slug, theme=theme["key"]))
    state = {"schema": "stu.tournament", "version": 1, "slug": slug, "name": name, "theme": theme["key"], "root": root,
             "config": cfg, "fighters": fighters, "bracket": br, "arenas": arenas, "matches": {}, "steps": {}, "champion": None,
             "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    os.makedirs(path, exist_ok=True)
    atomic_write_json(os.path.join(path, "state.json"), state)
    u.save_all()
    tour = Tournament(path, u)
    tour.save()
    log(f"Created tournament '{name}' -> {os.path.relpath(path, root)}")
    for f in fighters:
        log(f"  {f['name']:<10} {' + '.join(f['ability_names']):<34} {f['personality']:<13} look: {', '.join(f.get('costume', []))}")
    for r, a in enumerate(arenas):
        log(f"  arena round {r + 1}: {a['name']} ({a['biome']}, {a['time_of_day']})")
    return tour
