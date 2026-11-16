---
name: new-tournament
description: Create a new stickman fight tournament (UltimateStickFightTournaments). Asks for theme, number of fighters and abilities per fighter, renders the whole tournament and sends the videos in the chat. Use when the user types /new-tournament or asks for a new tournament.
---

# /new-tournament

Produce a complete tournament with the Stickman Tournament Universe engine in
`stickman-tournament-universe/` and deliver the videos in the chat.
Reply in the language the user writes in.

## 1. Collect the settings

If the user already gave theme, fighters and abilities (e.g. `/new-tournament pirates 8 2`),
use them. Otherwise ask with **one** AskUserQuestion call containing three questions:

- **Theme** (header "Theme"): options `Elements`, `Pirates`, `Dragons`, `Ninjas`
  (the user can type any other theme via "Other"; every theme name works: built-in
  packs are used directly, new themes are designed by Claude or generated offline).
- **Fighters** (header "Fighters"): `8 fighters` (7 matches, ~25 min), `4 fighters`
  (3 matches, ~10 min), `16 fighters` (15 matches, ~55 min).
- **Abilities** (header "Abilities"): `1 ability`, `2 abilities`, `3 abilities`.

Any number of fighters >= 2 is valid; non powers of two get byes automatically.

## 2. Render

```bash
cd stickman-tournament-universe
python3 -c "import cairo, numpy, yaml, PIL" || pip install -r requirements.txt
nohup python3 -m stu new --theme "<THEME>" --participants <N> --abilities <K> > /tmp/stu_tournament.log 2>&1 &
```

Tell the user in one short message that it started, which fighters and arenas were
generated (first ~15 lines of the log) and roughly how long it takes. Then wait for
completion in the background (e.g. an `until grep -qE "Exports:|Traceback" /tmp/stu_tournament.log`
loop run in the background) instead of polling in the foreground.

If the log shows `Traceback` or `QA issues`, investigate and fix before delivering;
never send videos that failed validation without saying so.

## 3. Verify and save

```bash
python3 -m stu validate tournaments/<slug>     # must print "OK — no issues found"
```

Commit and push the new tournament state (videos in `exports/` are git-ignored):
`git add -A stickman-tournament-universe && git commit -m "Add <theme> tournament" && git push`.

## 4. Deliver

Send every match video with SendUserFile, in bracket order, in two or three batches:
`exports/<slug>/round_01/*.mp4`, `semifinals/*.mp4` (or other round folders), `final/match_*.mp4`,
then `highlights.mp4`. Use absolute paths.

- Match 1 already contains the fighter roster and the bracket.
- The first match of every later stage starts with the bracket.
- The final ends with the champion reveal.
- There is no separate bracket or champion file.

Do not send `complete_tournament.mp4`; it is too large for the chat. Mention where it is.

Finish with a short summary: champion, a results table (round, match, score, decided at),
and the export folder.
