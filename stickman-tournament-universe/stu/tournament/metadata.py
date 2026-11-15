"""Episode metadata (titles, descriptions, tags) for each exported video."""
from __future__ import annotations


def _tags(t):
    theme = t.state["theme"].replace("_", "")
    return ["#stickman", "#stickmanfight", f"#{theme}", "#animation", "#tournament", "#shorts"]


def match_metadata(t, m, res):
    fa, fb = t.fighters[m["a"]], t.fighters[m["b"]]
    stage = t.stage_label(m).title()
    ab_a = " + ".join(fa["ability_names"])
    ab_b = " + ".join(fb["ability_names"])
    title = f"{fa['name']} ({ab_a}) vs {fb['name']} ({ab_b}) | {t.state['name']} – {stage}"
    desc = (f"{t.state['name']} · {stage}\n{fa['name']} wields {ab_a} ({fa['personality']} fighter).\n"
            f"{fb['name']} wields {ab_b} ({fb['personality']} fighter).\nFirst to {t.cfg['tournament']['points_to_win']} points. "
            f"Who takes it?\n\nEvery move, combination and fight in this series is generated procedurally.")
    return {"title": title[:100], "description": desc, "tags": _tags(t), "match": m["id"], "stage": stage,
            "fighters": [fa["name"], fb["name"]], "archetype": res["archetype"], "arena": res["arena"]["name"],
            "spoiler_result": {"winner": [fa["name"], fb["name"]][res["winner"]], "score": res["scores"]}}


def tournament_metadata(t):
    champ = t.fighters.get(t.state.get("champion"), {})
    return {
        "tournament": t.state["name"], "theme": t.state["theme"], "seed": t.cfg["tournament"]["random_seed"],
        "champion": champ.get("name"),
        "complete_video": {"title": f"{t.state['name']} – Full Tournament ({len(t.fighters)} fighters)",
                           "description": f"The complete {t.state['name']}: {len(t.fighters)} procedurally generated stickman fighters, one champion.",
                           "tags": _tags(t)},
        "highlights": {"title": f"{t.state['name']} – Every Finishing Blow", "tags": _tags(t)},
        "fighters": [{"name": f["name"], "abilities": f["ability_names"], "personality": f["personality"], "color": f["color"],
                      "signature_move": f.get("signature_move")} for f in t.fighters.values()],
    }
