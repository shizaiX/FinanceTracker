"""Automated quality control for matches, videos and tournaments.

Checks objective properties only. Subjective animation quality cannot be proven
by code: contact sheets of key moments are produced for the manual review
procedure described in docs/QA.md.
"""
from __future__ import annotations

import math
import os

from ..animation.rig import BONES, J
from ..rendering.encoder import probe

BONE_IDX = [(J[a], J[b], L) for a, b, L in BONES]


def validate_match(res, cfg, techniques=None):
    issues = []
    t = cfg["tournament"]
    ptw = t["points_to_win"]
    sa, sb = res["scores"]
    if res["winner"] not in (0, 1):
        issues.append("no winner")
    if max(sa, sb) != ptw:
        issues.append(f"winner must have exactly {ptw} points (got {sa}-{sb})")
    if min(sa, sb) >= ptw:
        issues.append("both fighters reached the winning score")
    if res["winner"] is not None and res["scores"][res["winner"]] != ptw:
        issues.append("winner flag does not match score")
    if len(res["points"]) != sa + sb:
        issues.append("point log does not match score")
    if res.get("final_point_t") is None or res["final_point_t"] < t["minimum_fight_duration_seconds"]:
        issues.append(f"fight ended at {res.get('final_point_t')}s < minimum {t['minimum_fight_duration_seconds']}s")
    if res.get("final_point_t") and res["final_point_t"] > t["maximum_fight_duration_seconds"]:
        issues.append(f"fight exceeded maximum duration ({res['final_point_t']:.1f}s)")
    if any(e.get("forced") for e in res["events"] if e["type"] == "ko"):
        issues.append("match was force-finished by the safety net")
    # point events consistent and monotonic
    run = [0, 0]
    for p in res["points"]:
        run[p["scorer"]] += 1
        if p["score"] != run:
            issues.append(f"score progression inconsistent at {p['t']}")
            break
    # skeleton integrity + continuity
    frames = res["frames"]
    build = [f.get("build", 1.0) for f in res["fighters"]]
    max_jump = 0.0
    bad_len = 0
    for i, fr in enumerate(frames):
        for side, fd in enumerate(fr["f"]):
            j = fd[3]
            if any(math.isnan(v) or math.isinf(v) for v in j):
                issues.append(f"invalid joint coordinates at frame {i}")
                return issues
            if i % 4 == 0:
                for a, b, L in BONE_IDX:
                    d = math.hypot(j[2 * a] - j[2 * b], j[2 * a + 1] - j[2 * b + 1])
                    if abs(d - L * build[side]) > 0.02:
                        bad_len += 1
            if i > 0:
                prev = frames[i - 1]["f"][side]
                if not (fd[5] & (128 | 64)) and not (prev[5] & 64):
                    jump = math.hypot(fd[0] - prev[0], fd[1] - prev[1])
                    max_jump = max(max_jump, jump)
    if bad_len:
        issues.append(f"{bad_len} bone-length violations (limb stretching)")
    if max_jump > 0.35:
        issues.append(f"non-ability teleport detected (root moved {max_jump:.2f} m in one tick)")
    # collision timing: every hit must be near the defender's body at that tick
    dt = res["dt"]
    for e in res["events"]:
        if e["type"] == "hit" and "x" in e:
            i = min(len(frames) - 1, max(0, int(round(e["t"] / dt)) - 1))
            fd = frames[i]["f"][e["fighter"]]
            if abs(fd[0] - e["x"]) > 2.2:
                issues.append(f"hit at t={e['t']:.2f} registered far from defender")
                break
    if techniques is not None:
        for tid in res.get("tech_uses", {}):
            if tid not in techniques:
                issues.append(f"unknown technique {tid}")
    return issues


def validate_video(path, cfg, expected_frames=None, expect_audio=True):
    issues = []
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        return [f"missing or empty video {path}"]
    try:
        info = probe(path)
    except Exception as ex:  # corrupted
        return [f"ffprobe failed: {ex}"]
    v = [s for s in info["streams"] if s["codec_type"] == "video"]
    a = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not v:
        return ["no video stream"]
    v = v[0]
    vc = cfg["video"]
    if (v["width"], v["height"]) != (vc["width"], vc["height"]):
        issues.append(f"resolution {v['width']}x{v['height']} != {vc['width']}x{vc['height']}")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    fps = num / den
    if fps < vc["fps"] - 0.01:
        issues.append(f"framerate {fps:.2f} < {vc['fps']}")
    if v.get("codec_name") != "h264":
        issues.append(f"codec {v.get('codec_name')} != h264")
    n = int(v.get("nb_read_frames") or v.get("nb_frames") or 0)
    if expected_frames is not None and n != expected_frames:
        issues.append(f"frame count {n} != expected {expected_frames} (missing frames)")
    if expect_audio:
        if not a:
            issues.append("no audio stream")
        else:
            vd = float(v.get("duration", 0))
            ad = float(a[0].get("duration", 0))
            if abs(vd - ad) > 0.1:
                issues.append(f"audio/video duration mismatch {ad:.3f}s vs {vd:.3f}s")
    return issues


def contact_sheet(renderer, frame_ids, out_path, cols=4, scale=0.3, labels=None):
    from PIL import Image, ImageDraw
    tiles = []
    for k in frame_ids:
        surf = renderer.render(k)
        img = Image.frombuffer("RGBA", (surf.get_width(), surf.get_height()), bytes(surf.get_data()), "raw", "BGRA", 0, 1)
        img = img.convert("RGB").resize((int(surf.get_width() * scale), int(surf.get_height() * scale)))
        tiles.append(img)
    if not tiles:
        return None
    w, h = tiles[0].size
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (w * cols, h * rows), (10, 10, 14))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(tiles):
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y))
        if labels:
            d.rectangle([x, y + h - 24, x + w, y + h], fill=(0, 0, 0))
            d.text((x + 6, y + h - 20), labels[i], fill=(255, 255, 255))
    sheet.save(out_path)
    return out_path
