"""Command line interface.

    python -m stu new --theme elements --participants 8 --abilities 2
    python -m stu match --theme elements           # one demo match only
    python -m stu resume tournaments/<slug>
    python -m stu validate tournaments/<slug>
    python -m stu themes list | create <theme>
    python -m stu library stats | backup | export <zip> | import <zip>
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import PROJECT_ROOT
from .config import load_config, parse_override


def _cfg(args):
    over = [parse_override(s) for s in (args.set or [])]
    if args.theme:
        over.append((["tournament", "theme"], args.theme))
    if args.participants:
        over.append((["tournament", "participants"], args.participants))
    if args.abilities:
        over.append((["tournament", "abilities_per_fighter"], args.abilities))
    if args.seed is not None:
        over.append((["tournament", "random_seed"], args.seed))
    if args.name:
        over.append((["tournament", "name"], args.name))
    if args.preview:
        over += [(["video", "width"], 540), (["video", "height"], 960), (["video", "fps"], 30), (["video", "quality"], "draft")]
    return load_config(args.config, over)


def _add_common(p):
    p.add_argument("--config", default=os.path.join(PROJECT_ROOT, "config.yaml"))
    p.add_argument("--theme")
    p.add_argument("--participants", type=int)
    p.add_argument("--abilities", type=int, help="abilities per fighter")
    p.add_argument("--seed", type=int)
    p.add_argument("--name")
    p.add_argument("--set", action="append", help="override any setting, e.g. --set video.fps=60")
    p.add_argument("--abilities-list", help="comma separated custom ability names for a new theme")
    p.add_argument("--no-render", action="store_true", help="simulate + validate only")
    p.add_argument("--preview", action="store_true", help="fast 540x960@30 draft render (not for publishing)")
    p.add_argument("--max-matches", type=int)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="stu", description="Stickman Tournament Universe")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new", help="create and produce a tournament")
    _add_common(p_new)
    p_match = sub.add_parser("match", help="produce only the first match of a new tournament (demo)")
    _add_common(p_match)
    p_res = sub.add_parser("resume", help="resume an interrupted tournament")
    p_res.add_argument("path")
    p_res.add_argument("--no-render", action="store_true")
    p_res.add_argument("--max-matches", type=int)
    p_val = sub.add_parser("validate", help="re-run QA on a tournament's outputs")
    p_val.add_argument("path")
    p_th = sub.add_parser("themes")
    p_th.add_argument("action", choices=["list", "create", "show"])
    p_th.add_argument("name", nargs="?")
    p_lib = sub.add_parser("library")
    p_lib.add_argument("action", choices=["stats", "backup", "export", "import"])
    p_lib.add_argument("file", nargs="?")
    args = ap.parse_args(argv)

    from .persistence.library import Universe
    if args.cmd in ("new", "match"):
        from .tournament.pipeline import create_tournament
        cfg = _cfg(args)
        custom = [s.strip() for s in args.abilities_list.split(",")] if args.abilities_list else None
        t = create_tournament(cfg, PROJECT_ROOT, custom_abilities=custom)
        t.run(render=not args.no_render, max_matches=1 if args.cmd == "match" else args.max_matches)
        print(f"\nTournament folder: {os.path.relpath(t.path, PROJECT_ROOT)}\nExports: {os.path.relpath(t.export_dir, PROJECT_ROOT)}")
    elif args.cmd == "resume":
        from .tournament.pipeline import Tournament
        t = Tournament(os.path.abspath(args.path))
        t.run(render=not args.no_render, max_matches=args.max_matches)
    elif args.cmd == "validate":
        from .qa.validate import validate_video
        from .tournament.bracket import validate_bracket
        from .tournament.pipeline import Tournament
        t = Tournament(os.path.abspath(args.path))
        problems = validate_bracket(t.state["bracket"])
        for mid, rec in t.state["matches"].items():
            problems += [f"{mid}: {i}" for i in rec.get("sim_issues", [])]
            if rec.get("video"):
                problems += [f"{mid}: {i}" for i in validate_video(os.path.join(t.root, rec["video"]), t.cfg, rec.get("video_frames"))]
        print("OK — no issues found" if not problems else "\n".join(problems))
        sys.exit(1 if problems else 0)
    elif args.cmd == "themes":
        u = Universe(PROJECT_ROOT)
        if args.action == "list":
            for k in u.list_themes():
                th = u.load_theme(k)
                print(f"{k:<16} {len(th['abilities']):>3} abilities  {', '.join(a['name'] for a in th['abilities'])}")
        elif args.action in ("create", "show"):
            from .core.rng import RNG
            from .themes.generator import load_or_create_theme
            th = load_or_create_theme(u, args.name, RNG(args.name), 0)
            u.save_all()
            print(json.dumps({"key": th["key"], "abilities": [(a["name"], a["archetype"], a["tags"]) for a in th["abilities"]],
                              "arenas": [a["name"] for a in th["arenas"]]}, indent=1))
    elif args.cmd == "library":
        u = Universe(PROJECT_ROOT)
        if args.action == "stats":
            for n, lib in u.libs.items():
                print(f"{n:<16} {len(lib):>6} items")
            disc = [t for t in u["techniques"].values() if t.get("origin") == "discovered"]
            print(f"discovered techniques: {len(disc)}")
        elif args.action == "backup":
            print(u.backup())
        elif args.action == "export":
            print(u.export(args.file or "stu_library_export.zip"))
        elif args.action == "import":
            print(f"merged {u.import_bundle(args.file)} new items")


if __name__ == "__main__":
    main()
