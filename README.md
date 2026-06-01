# Gentlemans League — IPL Fantasy

Tools for a private IPL Fantasy league: a web dashboard to analyze the season,
a bot to manage the team, and a data pipeline that keeps a full history of the
league saved for later.

Live dashboard: https://gentlemans-league-ipl.pages.dev/

## Data analytics

A static single-page dashboard (`dashboard/`) for exploring the
season. Aggregations are precomputed from the season snapshot into small JSON
files, so it deploys as plain static assets on Cloudflare Pages — no backend.

Four tabs:

- **Standings** — team rankings split into their scoring components. Toggle
  Raw / Captain / VC / Boosters to see what each contributes (teams re-rank
  live), and switch scope between the full season and the playoffs (last 4
  matches).
- **Player Explorer** — per-player season totals and match-by-match form,
  filtered by IPL team, role, and which fantasy team picked them.
- **Booster Analysis** — return on each booster (applied minus base), best
  individual plays, and a drill-in to any single usage's XI.
- **Captaincy** — hit-rate (captain finished top-3 in the XI), points per
  match, and every captaincy pick.

The data layer `src/ipl_fantasy/league_data.py` (`load_league()`) flattens the
season JSON into tidy pandas DataFrames and is shared by the build and the
legacy Streamlit app.

```bash
# Build the dashboard's data artifacts (needs the season JSON locally — see
# "Getting the data"). Writes dashboard/data/{meta,players}.json.
uv run python scripts/build_web_data.py

# Preview locally
python3 -m http.server -d dashboard 8000

# Deploy to Cloudflare Pages
npx wrangler pages deploy dashboard --project-name gentlemans-league-ipl

# Legacy server-rendered version of the same analytics
uv run streamlit run scripts/dashboard.py
```

## Team selection

A Playwright bot (`src/ipl_fantasy/`) that logs into the fantasy site and
manages the team, with Telegram notifications.

- `scripts/run.py` — main run: review and apply team changes.
- `scripts/run_auto.py` — cron mode: after the toss, auto-swap any picked
  player who isn't in today's playing XI (XI checked via `playing_xi.py`, swap
  logic in `strategy.py`).
- `scripts/set_captaincy.py` — set captain / vice-captain from the
  `CAPTAIN` / `VICE_CAPTAIN` env vars. Runs on a schedule via GitHub Actions
  (`.github/workflows/set-captaincy.yml`).
- `scripts/recommend.py` — pull the day's match data from Cricbuzz
  (`cricbuzz.py`) and suggest transfers.

Configuration (credentials, Telegram token, etc.) is read from a `.env` file;
see `src/ipl_fantasy/config.py`. Bot extras install with `uv sync --extra bot`.

## Future data strategy

This season is mostly setup and learning: get the scraping right, save the data
somewhere safe, and build views we actually trust. For now the analysis is all
backward-looking.

Next season the plan is to lean on what we've stored — not just our own team but
everyone else's moves too: who they captained, when they burned boosters, how
their transfers worked out — and feed that into the picks instead of going on
gut. We'd also like to pull in older seasons. A lot of that history isn't in the
official app anymore, so we'll have to scrape it back from wherever we can find
it and stitch it together. No idea yet how far we'll get, but that's the
direction.

## Getting the data

The source of truth is one nested JSON snapshot per season, produced by the
scraper (`scripts/scrape_league.py`; `scripts/update_matches.py` adds new
matches incrementally). It is kept out of git and stored in a public,
read-only **Cloudflare R2** bucket, organized by season:

```
gentlemans-league/            (R2 bucket)
  2026/league.json
  2027/league.json            (future seasons)
```

Anyone can fetch a season directly over HTTPS, no login:

```
https://pub-1d8587a347ad4a8fa5e8cda26f291873.r2.dev/2026/league.json
```

```bash
# Download a season's JSON locally (needed to build the dashboard)
npx wrangler r2 object get gentlemans-league/2026/league.json \
  --file data/gentlemans_league_2026.json --remote

# Publish a new season to the same public bucket
npx wrangler r2 object put gentlemans-league/2027/league.json \
  --file data/gentlemans_league_2027.json --content-type application/json --remote
```

The `.csv` / `.sqlite` files under `data/` are derived from the JSON, so they
are regenerated rather than stored.

## Repo layout

```
src/ipl_fantasy/        data layer (league_data.py) + bot modules
scripts/                build_web_data.py, dashboard.py (streamlit), bot + scraper entry points
dashboard/    static dashboard (app + committed data artifacts)
data/                   raw season data (git-ignored; source in R2)
docs/                   league rules reference
```
