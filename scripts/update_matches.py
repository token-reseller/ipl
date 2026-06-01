"""Incrementally scrape new matches, merge into the dataset, build a SQLite DB.

Usage:
    uv run python scripts/update_matches.py --new-matches 71-74
    uv run python scripts/update_matches.py --new-matches 71,72,73,74 --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import scrape_league  # noqa: E402

JSON_PATH = ROOT / "data/gentlemans_league_2026.json"
CSV_PATH = ROOT / "data/gentlemans_league_2026.csv"
SQLITE_PATH = ROOT / "data/gentlemans_league_2026.sqlite"

log = logging.getLogger(__name__)


def load_existing(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def merge(existing: dict[str, Any] | None, fresh: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        return fresh

    teams_by_id: dict[int, dict[str, Any]] = {
        int(t["team_id"]): t for t in existing.get("teams", [])
    }
    fresh_match_ids: set[int] = set()
    for team in fresh.get("teams", []):
        for m in team.get("matches", []):
            fresh_match_ids.add(int(m["match"]))

    for fresh_team in fresh.get("teams", []):
        tid = int(fresh_team["team_id"])
        existing_team = teams_by_id.get(tid)
        if existing_team is None:
            existing.setdefault("teams", []).append(fresh_team)
            continue

        if fresh_team.get("overall"):
            existing_team["overall"] = fresh_team["overall"]
        for k in ("team_name", "user_name", "social_id"):
            if fresh_team.get(k) is not None:
                existing_team[k] = fresh_team[k]

        kept = [
            m for m in existing_team.get("matches", [])
            if int(m["match"]) not in fresh_match_ids
        ]
        kept.extend(fresh_team.get("matches", []))
        kept.sort(key=lambda m: int(m["match"]))
        existing_team["matches"] = kept

    existing["generated_at"] = fresh.get("generated_at", existing.get("generated_at"))
    if fresh.get("league"):
        existing["league"] = fresh["league"]
    existing.setdefault("teams", []).sort(
        key=lambda t: (
            (t.get("overall") or {}).get("rank") or 9999,
            int(t["team_id"]),
        )
    )
    return existing


def build_sqlite(data: dict[str, Any], rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE league (
            id            INTEGER PRIMARY KEY,
            name          TEXT,
            source        TEXT,
            generated_at  TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE teams (
            team_id        INTEGER PRIMARY KEY,
            team_name      TEXT,
            user_name      TEXT,
            social_id      TEXT,
            overall_rank   INTEGER,
            overall_points REAL,
            overall_json   TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE team_matches (
            team_id                   INTEGER,
            match                     INTEGER,
            league_rank               INTEGER,
            leaderboard_total_points  REAL,
            total_match_points        REAL,
            booster_id                INTEGER,
            booster_name              TEXT,
            transfers_used_in_match   INTEGER,
            transfers_used_cumulative INTEGER,
            transfers_remaining       INTEGER,
            transfers_allowed         INTEGER,
            scrape_status             TEXT,
            fixture_json              TEXT,
            raw_team_json             TEXT,
            PRIMARY KEY (team_id, match),
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE fixtures (
            match            INTEGER PRIMARY KEY,
            match_id         INTEGER,
            match_number     TEXT,
            home_team        TEXT,
            away_team        TEXT,
            venue            TEXT,
            status           INTEGER,
            starts_at        TEXT,
            team_gameday_id  INTEGER,
            tour_gameday_id  INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE player_match (
            team_id                INTEGER,
            match                  INTEGER,
            player_id              INTEGER,
            player_name            TEXT,
            ipl_team_id            INTEGER,
            ipl_team               TEXT,
            role                   TEXT,
            base_gameday_points    REAL,
            fantasy_applied_score  REAL,
            is_captain             INTEGER,
            is_vice_captain        INTEGER,
            is_booster_captain     INTEGER,
            detail_scrape_status   TEXT,
            runs                   INTEGER,
            balls                  INTEGER,
            fours                  INTEGER,
            sixes                  INTEGER,
            strike_rate            REAL,
            wickets                INTEGER,
            economy                REAL,
            maidens                INTEGER,
            catches                INTEGER,
            run_outs               INTEGER,
            stumpings              INTEGER,
            played_status          INTEGER,
            points_breakdown_json  TEXT,
            raw_detail_json        TEXT,
            PRIMARY KEY (team_id, match, player_id),
            FOREIGN KEY (team_id) REFERENCES teams(team_id)
        )
        """
    )
    cur.execute("CREATE INDEX idx_player_match_player ON player_match(player_id)")
    cur.execute("CREATE INDEX idx_player_match_match  ON player_match(match)")
    cur.execute("CREATE INDEX idx_team_matches_match  ON team_matches(match)")

    league = data.get("league") or {}
    cur.execute(
        "INSERT INTO league (id, name, source, generated_at) VALUES (?,?,?,?)",
        (
            league.get("id"),
            league.get("name"),
            league.get("source"),
            data.get("generated_at"),
        ),
    )

    fixtures_seen: dict[int, dict[str, Any]] = {}
    for team in data.get("teams", []):
        overall = team.get("overall") or {}
        cur.execute(
            """
            INSERT INTO teams (
                team_id, team_name, user_name, social_id,
                overall_rank, overall_points, overall_json
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                team.get("team_id"),
                team.get("team_name"),
                team.get("user_name"),
                team.get("social_id"),
                overall.get("rank"),
                overall.get("points"),
                json.dumps(overall, sort_keys=True),
            ),
        )
        for m in team.get("matches", []):
            fixture = m.get("fixture") or {}
            transfers = m.get("transfers") or {}
            booster = m.get("booster") or {}
            cur.execute(
                """
                INSERT INTO team_matches (
                    team_id, match, league_rank, leaderboard_total_points,
                    total_match_points, booster_id, booster_name,
                    transfers_used_in_match, transfers_used_cumulative,
                    transfers_remaining, transfers_allowed, scrape_status,
                    fixture_json, raw_team_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    team.get("team_id"),
                    m.get("match"),
                    m.get("league_rank"),
                    m.get("leaderboard_total_points"),
                    m.get("total_match_points"),
                    booster.get("id"),
                    booster.get("name"),
                    transfers.get("used_in_match"),
                    transfers.get("used_cumulative"),
                    transfers.get("remaining"),
                    transfers.get("allowed"),
                    m.get("scrape_status"),
                    json.dumps(fixture, sort_keys=True),
                    json.dumps(m.get("raw_team") or {}, sort_keys=True),
                ),
            )
            match_no = m.get("match")
            if match_no is not None and match_no not in fixtures_seen and fixture:
                fixtures_seen[int(match_no)] = fixture

    for match_no, fixture in fixtures_seen.items():
        cur.execute(
            """
            INSERT INTO fixtures (
                match, match_id, match_number, home_team, away_team,
                venue, status, starts_at, team_gameday_id, tour_gameday_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                match_no,
                fixture.get("match_id"),
                fixture.get("match_number"),
                fixture.get("home_team"),
                fixture.get("away_team"),
                fixture.get("venue"),
                fixture.get("status"),
                fixture.get("starts_at"),
                fixture.get("team_gameday_id"),
                fixture.get("tour_gameday_id"),
            ),
        )

    for row in rows:
        cur.execute(
            """
            INSERT OR REPLACE INTO player_match (
                team_id, match, player_id, player_name, ipl_team_id, ipl_team,
                role, base_gameday_points, fantasy_applied_score,
                is_captain, is_vice_captain, is_booster_captain,
                detail_scrape_status, runs, balls, fours, sixes, strike_rate,
                wickets, economy, maidens, catches, run_outs, stumpings,
                played_status, points_breakdown_json, raw_detail_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["team_id"],
                row["match"],
                row["player_id"],
                row["player_name"],
                row["ipl_team_id"],
                row["ipl_team"],
                row["role"],
                row["base_gameday_points"],
                row["fantasy_applied_score"],
                int(bool(row["is_captain"])),
                int(bool(row["is_vice_captain"])),
                int(bool(row["is_booster_captain"])),
                row["detail_scrape_status"],
                row["runs"],
                row["balls"],
                row["fours"],
                row["sixes"],
                row["strike_rate"],
                row["wickets"],
                row["economy"],
                row["maidens"],
                row["catches"],
                row["run_outs"],
                row["stumpings"],
                row["played_status"],
                row["points_breakdown_json"],
                row["raw_detail_json"],
            ),
        )

    conn.commit()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--new-matches",
        required=True,
        help="Match numbers to scrape and merge, e.g. 71-74 or 71,72,73,74",
    )
    parser.add_argument("--json-path", type=Path, default=JSON_PATH)
    parser.add_argument("--csv-path", type=Path, default=CSV_PATH)
    parser.add_argument("--sqlite-path", type=Path, default=SQLITE_PATH)
    parser.add_argument(
        "--include-profiles",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    new_matches = scrape_league.parse_match_range(args.new_matches)
    print(f"Scraping new matches: {new_matches}")

    scrape_args = argparse.Namespace(
        matches=new_matches,
        include_profiles=args.include_profiles,
    )
    fresh = scrape_league.scrape(scrape_args)

    existing = load_existing(args.json_path)
    merged = merge(existing, fresh)

    rows = scrape_league.flatten_rows(merged)
    print(
        f"Merged dataset: {len(merged.get('teams', []))} teams, "
        f"{len(rows)} player rows."
    )

    if args.dry_run:
        return

    scrape_league.write_outputs(merged, args.json_path, args.csv_path)
    print(f"Wrote {args.json_path}")
    print(f"Wrote {args.csv_path}")

    build_sqlite(merged, rows, args.sqlite_path)
    print(f"Wrote {args.sqlite_path}")


if __name__ == "__main__":
    main()
