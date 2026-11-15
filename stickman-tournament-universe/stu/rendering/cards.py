"""Tournament presentation templates: bracket reveal / progression and the
champion reveal. Rendered with the same streaming encoder as fights."""
from __future__ import annotations

import math

import cairo

from ..core.mathutil import clamp, ease_out_back, hex_to_rgb, mix, smoothstep
from .hud import text


class BracketCard:
    """Animated bracket. `highlight_round` = round whose results are revealed."""

    def __init__(self, cfg, state, title, subtitle, duration=6.0, champion=None, upto_round=None):
        self.W, self.H = cfg["video"]["width"], cfg["video"]["height"]
        self.fps = cfg["video"]["fps"]
        self.state = state
        self.title = title
        self.subtitle = subtitle
        self.n = int(duration * self.fps)
        self.champion = champion
        self.upto = upto_round  # rounds >= upto are shown without results (no spoilers)
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.W, self.H)
        self.f = {f["id"]: f for f in state["fighters"]}

    def u(self, v):
        return v * self.W / 1080.0

    def _bg(self, cr, t):
        g = cairo.LinearGradient(0, 0, 0, self.H)
        g.add_color_stop_rgb(0, 0.03, 0.02, 0.08)
        g.add_color_stop_rgb(1, 0.10, 0.03, 0.10)
        cr.set_source(g)
        cr.paint()
        for k in range(30):
            x = (k * 137.5 + t * 20) % self.W
            y = (k * 263.1) % self.H
            cr.set_source_rgba(1, 0.8, 0.5, 0.08 + 0.05 * math.sin(t * 2 + k))
            cr.arc(x, y, self.u(2 + k % 3), 0, 2 * math.pi)
            cr.fill()

    def render(self, k):
        t = k / self.fps
        cr = cairo.Context(self.surface)
        self._bg(cr, t)
        if self.champion:
            return self._champion(cr, t)
        W, u = self.W, self.u
        top = self.H * 0.09
        text(cr, self.title, W / 2, top + u(30), u(64), (1, 0.85, 0.4), "center", clamp(t / 0.3, 0, 1), glow=(1, 0.6, 0.2))
        text(cr, self.subtitle, W / 2, top + u(100), u(34), (1, 1, 1), "center", clamp((t - 0.2) / 0.3, 0, 1), heavy=False, tracking=0.08)
        br = self.state["bracket"]
        rounds = br["rounds"]
        nR = len(rounds)
        ms = br["matches"]
        area_top, area_bot = self.H * 0.2, self.H * 0.78
        col_w = (W - u(80)) / nR
        pos = {}
        for r, mids in enumerate(rounds):
            cnt = len(mids)
            for i, mid in enumerate(mids):
                m = ms[mid]
                y = area_top + (i + 0.5) * (area_bot - area_top) / cnt
                x = u(40) + r * col_w
                pos[mid] = (x, y)
                appear = clamp((t - 0.4 - 0.12 * i - 0.5 * r) / 0.35, 0, 1)
                if appear <= 0:
                    continue
                hide = self.upto is not None and m["round"] >= self.upto
                for slot, key in ((0, "a"), (1, "b")):
                    fid = m[key] if not (self.upto is not None and m["round"] > self.upto) else None
                    yy = y + (slot - 0.5) * u(52 if r == 0 else 46)
                    name = self.f[fid]["name"] if fid else ("BYE" if r == 0 else "?")
                    col = hex_to_rgb(self.f[fid]["color"]) if fid else (0.5, 0.5, 0.55)
                    lost = (not hide) and m["winner"] and fid and m["winner"] != fid
                    a = appear * (0.35 if lost else 1.0)
                    cr.set_source_rgba(*mix(col, (0, 0, 0), 0.75), 0.85 * a)
                    cr.rectangle(x, yy - u(21), col_w - u(26), u(42))
                    cr.fill()
                    cr.set_source_rgba(*col, a)
                    cr.rectangle(x, yy - u(21), u(7), u(42))
                    cr.fill()
                    size = 30 if nR <= 3 else 24
                    text(cr, name, x + u(18), yy, u(size), col if not lost else (0.6, 0.6, 0.65), "left", a, outline=0.12)
                    if m["scores"] and fid and not hide:
                        sc = m["scores"][slot]
                        text(cr, str(sc), x + col_w - u(40), yy, u(28), (1, 1, 1), "right", a)
                if r > 0:
                    for s in m["src"]:
                        if s in pos:
                            px, py = pos[s]
                            cr.set_source_rgba(1, 1, 1, 0.25 * appear)
                            cr.set_line_width(u(3))
                            cr.move_to(px + col_w - u(26), py)
                            cr.line_to(x - u(6), py)
                            cr.line_to(x - u(6), y)
                            cr.stroke()
        return self.surface

    def _champion(self, cr, t):
        W, H, u = self.W, self.H, self.u
        f = self.f[self.champion]
        col = hex_to_rgb(f["color"])
        g = cairo.RadialGradient(W / 2, H * 0.45, 0, W / 2, H * 0.45, H * 0.5)
        g.add_color_stop_rgba(0, *col, 0.45 * clamp(t / 0.8, 0, 1))
        g.add_color_stop_rgba(1, *col, 0)
        cr.set_source(g)
        cr.paint()
        for k in range(24):
            a = k / 24 * 2 * math.pi + t * 0.3
            cr.set_source_rgba(*mix(col, (1, 1, 1), 0.5), 0.08)
            cr.move_to(W / 2, H * 0.45)
            cr.line_to(W / 2 + math.cos(a) * H, H * 0.45 + math.sin(a) * H)
            cr.line_to(W / 2 + math.cos(a + 0.08) * H, H * 0.45 + math.sin(a + 0.08) * H)
            cr.close_path()
            cr.fill()
        sc = 0.6 + 0.4 * ease_out_back(clamp((t - 0.3) / 0.5, 0, 1), 1.8)
        text(cr, self.title, W / 2, H * 0.14, u(52), (1, 0.85, 0.4), "center", clamp(t / 0.4, 0, 1), tracking=0.1)
        text(cr, "CHAMPION", W / 2, H * 0.27, u(80), (1, 0.9, 0.5), "center", clamp((t - 0.2) / 0.3, 0, 1), glow=(1, 0.7, 0.2), tracking=0.15)
        text(cr, f["name"], W / 2, H * 0.37, u(170), col, "center", clamp((t - 0.3) / 0.3, 0, 1), scale=sc, glow=col)
        text(cr, "  +  ".join(n.upper() for n in f["ability_names"]), W / 2, H * 0.45, u(42), (1, 1, 1), "center", clamp((t - 0.7) / 0.3, 0, 1))
        rec = self.subtitle
        text(cr, rec, W / 2, H * 0.5, u(34), (0.85, 0.85, 0.9), "center", clamp((t - 0.9) / 0.3, 0, 1), heavy=False)
        # trophy-like stick figure pose
        cx, gy = W / 2, H * 0.7
        s = u(190)
        a = clamp((t - 0.4) / 0.4, 0, 1)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        pts = {"hip": (0, 0.9), "chest": (0, 1.45), "head": (0, 1.66), "hf": (0.2, 2.1), "ef": (0.15, 1.8), "hb": (-0.35, 1.25),
               "eb": (-0.25, 1.5), "kf": (0.22, 0.48), "ff": (0.26, 0.0), "kb": (-0.18, 0.47), "fb": (-0.3, 0.0)}
        P = {k: (cx + v[0] * s, gy - v[1] * s) for k, v in pts.items()}
        for w, c, al in ((u(36), col, 0.15), (u(16), (0.02, 0.02, 0.04), 0.9), (u(11), mix(col, (1, 1, 1), 0.15), 1.0)):
            cr.set_source_rgba(*c, al * a)
            cr.set_line_width(w)
            for chain in (("hip", "chest"), ("chest", "ef", "hf"), ("chest", "eb", "hb"), ("hip", "kf", "ff"), ("hip", "kb", "fb")):
                cr.move_to(*P[chain[0]])
                for q in chain[1:]:
                    cr.line_to(*P[q])
                cr.stroke()
            cr.arc(P["head"][0], P["head"][1] - u(10), u(26) + (w - u(11)) / 2, 0, 2 * math.pi)
            cr.fill()
        return self.surface


class RosterCard:
    """Fighter presentation slide: format title on top, then an animated grid of
    background cards, each with the fighter (in costume and colours), its name
    and its abilities, so viewers know who is in the tournament."""

    def __init__(self, cfg, state, abilities, theme_title, duration=None):
        self.W, self.H = cfg["video"]["width"], cfg["video"]["height"]
        self.fps = cfg["video"]["fps"]
        self.state = state
        self.abilities = abilities
        self.fighters = state["fighters"]
        n = len(self.fighters)
        self.duration = duration or (3.6 + 0.22 * n)
        self.n = int(self.duration * self.fps)
        self.title = theme_title
        self.format_line = f"{n} FIGHTERS · {state['config']['tournament']['tournament_format'].replace('_', ' ').upper()}"
        k = state["config"]["tournament"]["abilities_per_fighter"]
        self.sub = f"{k} {'ABILITY' if k == 1 else 'ABILITIES'} EACH · FIRST TO {state['config']['tournament']['points_to_win']} POINTS"
        self.cols = 2 if n <= 8 else (3 if n <= 12 else 4)
        self.rows = math.ceil(n / self.cols)
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.W, self.H)

    def u(self, v):
        return v * self.W / 1080.0

    def _figure(self, cr, f, t, cx, base, scale, appear):
        from ..animation.poses import STANCES, POSES, blend_pose_safe
        from ..animation.rig import HEAD_R, J, solve_local, to_world
        from . import costume as COS
        from .weapons import draw_weapon
        col = hex_to_rgb(f["color"])
        sec = hex_to_rgb(f["secondary"])
        st = STANCES.get(f.get("stance"), STANCES["orthodox"])
        pose = dict(st)
        b = math.sin(t * 2 * math.pi * 0.9 + hash(f["name"]) % 7)
        pose["crouch"] += 0.02 * b
        pose["hfy"] += 0.015 * b
        if t < appear + 0.6:  # small hop as the card arrives
            pose = blend_pose_safe(POSES["victory"], pose, smoothstep((t - appear) / 0.6))
        P = to_world(solve_local(pose, f.get("build", 1.0)), 0.0, 0.0, 0.0, 1)
        cr.save()
        cr.translate(cx, base)
        cr.scale(scale, -scale)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        parts = f.get("costume") or [f.get("accessory", "headband")]
        hist = lambda jn, k: P[J[jn]]
        COS.draw_back(cr, parts, P, 1, t, col, sec, hist)
        kit = f.get("weapons") or []
        if len(kit) > 1:
            draw_weapon(cr, kit[1], P[J["hand_b"]], P[J["elbow_b"]], 1, None, t)

        def body(width, c, back, a):
            hx, hy = P[J["head"]]
            chx, chy = P[J["chest"]]
            d = math.hypot(hx - chx, hy - chy) or 1
            neck = (hx - (hx - chx) / d * HEAD_R, hy - (hy - chy) / d * HEAD_R)
            for chain, cc in (((P[J["hip"]], P[J["knee_b"]], P[J["foot_b"]]), back), ((P[J["chest"]], P[J["elbow_b"]], P[J["hand_b"]]), back),
                              ((P[J["hip"]], P[J["chest"]], neck), c), ((P[J["hip"]], P[J["knee_f"]], P[J["foot_f"]]), c),
                              ((P[J["chest"]], P[J["elbow_f"]], P[J["hand_f"]]), c)):
                cr.set_source_rgba(*cc, a)
                cr.set_line_width(width)
                cr.move_to(*chain[0])
                for q in chain[1:]:
                    cr.line_to(*q)
                cr.stroke()
            cr.arc(hx, hy, HEAD_R + (width - 0.075) * 0.5, 0, 2 * math.pi)
            cr.set_source_rgba(*c, a)
            cr.fill()
        body(0.24, col, col, 0.15)
        body(0.115, (0.02, 0.02, 0.04), (0.02, 0.02, 0.04), 0.85)
        body(0.075, mix(col, (1, 1, 1), 0.12), mix(col, (0.05, 0.05, 0.08), 0.38), 1.0)
        COS.draw_limb_overrides(cr, parts, P, 1, col)
        COS.draw_front(cr, parts, P, 1, t, col, sec, hist)
        if kit:
            draw_weapon(cr, kit[0], P[J["hand_f"]], P[J["elbow_f"]], 1, None, t)
        cr.restore()

    def render(self, k):
        t = k / self.fps
        cr = cairo.Context(self.surface)
        W, H, u = self.W, self.H, self.u
        g = cairo.LinearGradient(0, 0, 0, H)
        g.add_color_stop_rgb(0, 0.03, 0.02, 0.08)
        g.add_color_stop_rgb(1, 0.09, 0.03, 0.11)
        cr.set_source(g)
        cr.paint()
        top = H * 0.085
        a0 = clamp(t / 0.35, 0, 1)
        text(cr, self.format_line, W / 2, top + u(10), u(54), (1, 0.85, 0.4), "center", a0, glow=(1, 0.6, 0.2), max_width=u(980))
        text(cr, self.title.upper(), W / 2, top + u(80), u(36), (1, 1, 1), "center", clamp((t - 0.15) / 0.3, 0, 1), heavy=False,
             tracking=0.12)
        text(cr, self.sub, W / 2, top + u(126), u(24), (0.8, 0.8, 0.88), "center", clamp((t - 0.3) / 0.3, 0, 1), heavy=False, tracking=0.08)
        gx0, gx1 = u(40), W - u(40)
        gy0, gy1 = H * 0.2, H * 0.92
        gap = u(22)
        cw = (gx1 - gx0 - gap * (self.cols - 1)) / self.cols
        ch = min((gy1 - gy0 - gap * (self.rows - 1)) / self.rows, cw * 1.45)
        total_h = ch * self.rows + gap * (self.rows - 1)
        gy0 += (gy1 - gy0 - total_h) / 2
        for i, f in enumerate(self.fighters):
            r, c = divmod(i, self.cols)
            x = gx0 + c * (cw + gap)
            y = gy0 + r * (ch + gap)
            appear = 0.55 + 0.16 * i
            p = clamp((t - appear) / 0.45, 0, 1)
            if p <= 0:
                continue
            e = ease_out_back(p, 1.3)
            col = hex_to_rgb(f["color"])
            cr.save()
            cr.translate(x + cw / 2, y + ch / 2 + (1 - e) * u(60))
            sc = 0.85 + 0.15 * e
            cr.scale(sc, sc)
            cr.translate(-cw / 2, -ch / 2)
            # background card
            rad = u(22)
            cr.new_sub_path()
            cr.arc(cw - rad, rad, rad, -math.pi / 2, 0)
            cr.arc(cw - rad, ch - rad, rad, 0, math.pi / 2)
            cr.arc(rad, ch - rad, rad, math.pi / 2, math.pi)
            cr.arc(rad, rad, rad, math.pi, 1.5 * math.pi)
            cr.close_path()
            g = cairo.LinearGradient(0, 0, 0, ch)
            g.add_color_stop_rgba(0, *mix(col, (0, 0, 0), 0.55), 0.95 * p)
            g.add_color_stop_rgba(1, *mix(col, (0, 0, 0), 0.85), 0.95 * p)
            cr.set_source(g)
            cr.fill_preserve()
            cr.set_source_rgba(*col, 0.85 * p)
            cr.set_line_width(u(3))
            cr.stroke()
            wide = cw / ch > 1.1
            fx, fbase, fh = (cw * 0.24, ch * 0.88, ch * 0.78) if wide else (cw / 2, ch * 0.56, ch * 0.46)
            gg = cairo.RadialGradient(fx, fbase - fh * 0.5, 0, fx, fbase - fh * 0.5, fh * 0.7)
            gg.add_color_stop_rgba(0, *col, 0.35 * p)
            gg.add_color_stop_rgba(1, *col, 0)
            cr.set_source(gg)
            cr.rectangle(0, 0, cw, ch)
            cr.fill()
            self._figure(cr, f, t, fx, fbase, fh / 1.75, appear)
            abil = [self.abilities.get(aid) for aid in f["abilities"] if self.abilities.get(aid)]
            if wide:
                tx, tw = cw * 0.47, cw * 0.48
                name_size = min(u(52), ch * 0.17, tw * 0.2)
                text(cr, f["name"], tx, ch * 0.27, name_size, col, "left", p, glow=col, max_width=tw)
                pers = f.get("personality", "").upper()
                text(cr, pers, tx, ch * 0.27 + name_size * 0.85, name_size * 0.42, (0.8, 0.8, 0.86), "left", p * 0.9, heavy=False,
                     tracking=0.1, max_width=tw)
                y0, avail = ch * 0.56, ch * 0.36
                pill_x, pw = tx, tw
            else:
                name_size = min(u(46), cw * 0.15)
                text(cr, f["name"], cw / 2, ch * 0.66, name_size, col, "center", p, glow=col, max_width=cw * 0.9)
                y0, avail = ch * 0.78, ch * 0.2
                pw = cw * 0.82
                pill_x = cw / 2 - pw / 2
            line_h = min(u(44), avail / max(1, len(abil)))
            size = min(u(30), line_h * 0.72)
            for j, ab in enumerate(abil):
                acol = hex_to_rgb(ab["colors"][1])
                yy = y0 + j * line_h
                r_ = size * 0.62
                cr.new_sub_path()
                cr.arc(pill_x + pw - r_, yy, r_, -math.pi / 2, math.pi / 2)
                cr.arc(pill_x + r_, yy, r_, math.pi / 2, 1.5 * math.pi)
                cr.close_path()
                cr.set_source_rgba(*mix(acol, (0, 0, 0), 0.55), 0.95 * p)
                cr.fill_preserve()
                cr.set_source_rgba(*acol, 0.7 * p)
                cr.set_line_width(u(2))
                cr.stroke()
                text(cr, ab["name"].upper(), pill_x + pw / 2, yy, size * 0.78, mix(acol, (1, 1, 1), 0.35), "center", p, outline=0.12,
                     max_width=pw * 0.88, tracking=0.05)
            cr.restore()
        return self.surface
