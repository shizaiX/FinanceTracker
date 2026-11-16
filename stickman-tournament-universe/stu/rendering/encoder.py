"""Streaming FFmpeg encoding with parallel, resumable chunk rendering.

Frames are rendered straight into an FFmpeg pipe (never held in memory).
A video is split into chunks; each chunk is encoded to its own segment by a
worker process and marked done, so an interrupted render resumes at the first
unfinished chunk. Segments are concatenated losslessly and muxed with audio.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import subprocess

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

_CTX = {}


def ffmpeg_writer(path, w, h, fps, crf, preset, threads=2):
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-an", "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-g", str(fps * 2), "-threads", str(threads), "-r", str(fps), path]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def _render_chunk(args):
    idx, start, end, path = args
    factory = _CTX["factory"]
    renderer = _CTX.get("renderer")
    if renderer is None:
        renderer = factory()
        _CTX["renderer"] = renderer
    v = _CTX["video"]
    enc = v["encoder"]
    tmp = path + ".part.mp4"
    p = ffmpeg_writer(tmp, v["width"], v["height"], v["fps"], enc["crf"], enc["preset"], threads=_CTX.get("threads", 2))
    for k in range(start, end):
        surf = renderer.render(k)
        p.stdin.write(surf.get_data())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg failed on chunk {idx}")
    os.replace(tmp, path)
    with open(path + ".done", "w") as f:
        f.write(str(end - start))
    return idx


def render_video(factory, n_frames, out_path, video_cfg, work_dir, audio_path=None, chunk=600, workers=None, log=print):
    """Render frames [0, n_frames) via `factory()` -> object with render(k)."""
    os.makedirs(work_dir, exist_ok=True)
    workers = workers or video_cfg.get("render_workers", 2)
    jobs = []
    segs = []
    for i, s in enumerate(range(0, n_frames, chunk)):
        e = min(n_frames, s + chunk)
        path = os.path.join(work_dir, f"seg_{i:04d}.mp4")
        segs.append(path)
        if os.path.exists(path + ".done") and os.path.exists(path):
            continue
        jobs.append((i, s, e, path))
    _CTX.clear()
    _CTX.update(factory=factory, video=video_cfg, threads=max(1, 4 // max(1, workers)) + 1)
    if jobs:
        log(f"    rendering {n_frames} frames in {len(jobs)} chunk(s) with {min(workers, len(jobs))} worker(s)")
        if workers <= 1 or len(jobs) == 1:
            for j in jobs:
                _render_chunk(j)
        else:
            ctx = mp.get_context("fork")
            with ctx.Pool(min(workers, len(jobs))) as pool:
                for _ in pool.imap_unordered(_render_chunk, jobs):
                    pass
    else:
        log("    all chunks already rendered (resume)")
    _CTX.clear()
    lst = os.path.join(work_dir, "concat.txt")
    with open(lst, "w") as f:
        for p in segs:
            f.write(f"file '{os.path.abspath(p)}'\n")
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst]
    if audio_path:
        cmd += ["-i", audio_path, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", "-f", "mp4", out_path + ".tmp.mp4"]
    subprocess.run(cmd, check=True)
    os.replace(out_path + ".tmp.mp4", out_path)
    return out_path


def cleanup_work(work_dir):
    if os.path.isdir(work_dir):
        shutil.rmtree(work_dir, ignore_errors=True)


def probe(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-count_frames", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def concat_videos(paths, out_path, reencode=False, video_cfg=None):
    lst = out_path + ".list.txt"
    with open(lst, "w") as f:
        for p in paths:
            f.write(f"file '{os.path.abspath(p)}'\n")
    if not reencode:
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", out_path]
    else:
        enc = video_cfg["encoder"]
        cmd = [FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", str(enc["crf"]),
               "-preset", enc["preset"], "-pix_fmt", "yuv420p", "-r", str(video_cfg["fps"]), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
               "-movflags", "+faststart", out_path]
    subprocess.run(cmd, check=True)
    os.remove(lst)
    return out_path


def cut_clip(src, start, dur, out_path, video_cfg):
    enc = video_cfg["encoder"]
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-ss", f"{max(0, start):.3f}", "-i", src, "-t", f"{dur:.3f}", "-c:v", "libx264",
           "-crf", str(enc["crf"]), "-preset", enc["preset"], "-pix_fmt", "yuv420p", "-r", str(video_cfg["fps"]),
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out_path]
    subprocess.run(cmd, check=True)
    return out_path


def shrink_to(path, max_mb, video_cfg, log=print):
    """Re-encode a finished video until it is below max_mb (phone apps refuse to
    share very large files). Resolution, frame rate and audio stay unchanged."""
    crf = video_cfg["encoder"]["crf"]
    while os.path.getsize(path) > max_mb * 1024 * 1024 and crf < 30:
        crf += 3
        tmp = path + ".shrink.mp4"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path, "-c:v", "libx264", "-crf", str(crf), "-preset", "slow",
                        "-pix_fmt", "yuv420p", "-profile:v", "high", "-fps_mode", "passthrough", "-c:a", "copy",
                        "-movflags", "+faststart", tmp], check=True)
        os.replace(tmp, path)
        log(f"    re-encoded at crf {crf}: {os.path.getsize(path) / 2**20:.0f} MB")
    return path
