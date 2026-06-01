# Gentlemans League — IPL Fantasy Analytics

A static web app for analyzing a private IPL fantasy league: standings,
player performance, boosters, and captaincy. All aggregations are precomputed
from a season data snapshot into small JSON files, so it ships as plain static
assets on Cloudflare Pages — no backend.

Live: https://gentlemans-league-ipl.pages.dev

## Data

The single source of truth is one nested JSON snapshot of a whole season. It is
**not** committed to git (large, regenerated) — it lives in **Cloudflare R2**,
bucket `gentlemans-league`, organized by season:

```
gentlemans-league/            (R2 bucket, public read-only)
  2026/league.json
  2027/league.json            (future seasons go here)
  ...
```

League members can fetch any season directly over HTTPS (no login):

```
https://pub-1d8587a347ad4a8fa5e8cda26f291873.r2.dev/2026/league.json
```

```bash
# Restore a season's JSON locally (needed to rebuild the dashboard)
npx wrangler r2 object get gentlemans-league/2026/league.json \
  --file data/gentlemans_league_2026.json --remote

# Publish a new season to the same public bucket
npx wrangler r2 object put gentlemans-league/2027/league.json \
  --file data/gentlemans_league_2027.json --content-type application/json --remote
```

`src/ipl_fantasy/league_data.py` (`load_league()`) flattens the JSON into tidy
pandas DataFrames (teams, matches, and ~3,256 player-match rows) and is the
shared data layer for the build pipeline and the legacy Streamlit app.

## Analytics

The dashboard (`pages_ipl_dashboard/`) has four tabs.

### Standings

Team rankings decomposed into their scoring components. Every applied score
splits **exactly** into `raw + captain bonus + vc bonus + booster bonus`, so:

- **Component toggles** — Raw / Captain / VC / Boosters. Turn each on/off and
  the cards, cumulative line, and per-match bars recompute, re-ranking teams
  live (e.g. raw-only standings differ from the official order).
- **Scope toggle** — full season vs **playoffs (last 4 matches)**; cumulative
  restarts and rankings are recomputed within the scope (playoff form often
  reshuffles the table).
- Plus a multiplier-boost-vs-raw comparison table.

### Player Explorer

Per-player season analysis over the raw player-match table, filtered
client-side by IPL team, role, and which fantasy team picked them:

- Season totals — matches picked, base/applied points, captain & VC counts.
- Per-player match-by-match breakdown (role-colored), with raw detail rows.

### Booster Analysis

How much each booster actually returned:

- ROI per usage (`applied − base`), total value extracted per fantasy team,
  and average ROI by booster × team.
- Best individual booster plays, plus a drill-in to any single usage's XI.

### Captaincy

- Captaincy hit-rate (captain finished top-3 in their XI) per team.
- Captain points per match, most-captained players, and every captaincy pick.

## Build, preview, deploy

```bash
# 1. Build the data artifacts (requires the source JSON locally; see Data).
#    Writes pages_ipl_dashboard/data/{meta.json,players.json} — the only data
#    the site serves (committed, <1 MB total).
uv run python scripts/build_web_data.py

# 2. Preview locally
python3 -m http.server -d pages_ipl_dashboard 8000
#    or: npx wrangler pages dev pages_ipl_dashboard

# 3. Deploy to Cloudflare Pages (project: gentlemans-league-ipl)
npx wrangler pages deploy pages_ipl_dashboard --project-name gentlemans-league-ipl
```

The front end is dependency-free: vanilla ES modules + Plotly.js via CDN, no
framework, no bundler.

Note: dashboard asset filenames are not content-hashed and we redeploy in
place, so `pages_ipl_dashboard/_headers` sets `max-age=0, must-revalidate`
(ETag-based) rather than `immutable` — don't reintroduce `immutable` unless
filenames get fingerprinted.

## Streamlit app (legacy)

The original server-rendered version of the same analytics still works and
shares the data layer:

```bash
uv run streamlit run scripts/dashboard.py
```

## Layout

```
src/ipl_fantasy/league_data.py   shared data layer (JSON -> DataFrames)
scripts/build_web_data.py        precompute the dashboard's JSON artifacts
pages_ipl_dashboard/             static dashboard (app + committed data artifacts)
data/                            raw season data (git-ignored; source in R2)
```

## Where this is heading

This season is mostly setup and learning: get the scraping right, save the data
somewhere safe, and build views we actually trust. For now it's all
backward-looking.

The plan for next season is to lean on what we've stored. Not just our own team
but everyone else's moves too: who they captained, when they burned boosters,
how their transfers worked out. Feeding that into the picks instead of going on
gut. We'd also like to pull in older seasons. A lot of that history isn't in the
official app anymore, so we'll have to scrape it back from wherever we can find
it and stitch it together. No idea yet how far we'll get, but that's the
direction.
