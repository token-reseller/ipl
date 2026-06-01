"""Scrape an authenticated IPL Fantasy private league.

Usage:
    uv run python scripts/scrape_league.py
    uv run python scripts/scrape_league.py --matches 69-70 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ipl_fantasy.auth import create_browser, login
from ipl_fantasy.config import Settings

BASE_URL = "https://fantasy.iplt20.com/classic"
LEAGUE_ID = 24300104
LEAGUE_NAME = "Gentlemans league"
DEFAULT_MATCHES = "1-70"
OUT_JSON = Path("data/gentlemans_league_2026.json")
OUT_CSV = Path("data/gentlemans_league_2026.csv")

BOOSTERS = {
    1: "wildcard",
    3: "double_power",
    9: "foreign_stars",
    10: "indian_warriors",
    11: "free_hit",
    12: "triple_captain",
}
ROLE_BY_SKILL = {
    1: "BAT",
    2: "BOWL",
    3: "AR",
    4: "WK",
}

log = logging.getLogger(__name__)


class SilentTelegram:
    """Small adapter for auth.login without sending Telegram messages."""

    def send_message(self, text: str, parse_mode: str | None = None) -> None:
        log.info("%s", text)


def parse_match_range(raw: str) -> list[int]:
    matches: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            matches.extend(range(int(start), int(end) + 1))
        else:
            matches.append(int(part))
    return sorted(set(matches))


def api_value(payload: dict[str, Any]) -> Any:
    return ((payload.get("Data") or {}).get("Value"))


def api_success(payload: dict[str, Any]) -> bool:
    return bool((payload.get("Meta") or {}).get("Success"))


def get_login_user(page) -> dict[str, Any]:
    cookie_user = page.evaluate(
        """() => {
            const uid = document.cookie.split('; ')
              .find((row) => row.startsWith('my11c-uid='));
            if (uid) return { SocialId: decodeURIComponent(uid.split('=')[1]) };
            const raw = document.cookie.split('; ')
              .find((row) => row.startsWith('my11c-user='));
            if (!raw) return null;
            try {
                const value = raw.split('=').slice(1).join('=');
                return JSON.parse(decodeURIComponent(value));
            }
            catch (err) { return null; }
        }"""
    )
    if cookie_user:
        return cookie_user

    payload = fetch_json(page, f"{BASE_URL}/api/user/validate-token", method="POST")
    value = api_value(payload)
    if isinstance(value, dict):
        return value
    raise RuntimeError("Could not determine logged-in user GUID")


def fetch_json(page, url: str, method: str = "GET") -> dict[str, Any]:
    result = page.evaluate(
        """async ({ url, method }) => {
            const response = await fetch(url, { credentials: 'include', method });
            const text = await response.text();
            let body = null;
            try { body = text ? JSON.parse(text) : null; }
            catch (err) { body = { raw_text: text }; }
            return { status: response.status, body };
        }""",
        {"url": url, "method": method},
    )
    if result["status"] >= 400:
        raise RuntimeError(f"HTTP {result['status']} for {url}")
    return result["body"] or {}


def buster() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


def leaderboard_url(match: int) -> str:
    return (
        f"{BASE_URL}/api/user/leagues/{LEAGUE_ID}/leaderboard?"
        "optType=1"
        f"&gamedayId={match}"
        "&phaseId=1"
        "&pageNo=1"
        "&topNo=100"
        "&pageChunk=100"
        "&pageOneChunk=100"
        "&minCount=4"
        f"&leagueId={LEAGUE_ID}"
    )


def players_url(match: int, live: bool = False) -> str:
    prefix = "feed/live/gamedayplayers" if live else "feed/gamedayplayers"
    version_param = "LivePntsVrsnNo=70" if live else "announcedVersion=05242026185741"
    return (
        f"{BASE_URL}/api/{prefix}?lang=en"
        f"&tourgamedayId={match}"
        f"&teamgamedayId={match}"
        f"&{version_param}"
    )


def team_url(team: dict[str, Any], match: int, user_guid: str) -> str:
    common = (
        "optType=1"
        f"&gamedayId={match}"
        f"&tourgamedayId={match}"
        "&phaseId=1"
        f"&buster={buster()}"
    )
    social_id = team.get("usrscoid")
    if social_id == user_guid:
        return f"{BASE_URL}/api/user/{user_guid}/team-get?{common}"
    return (
        f"{BASE_URL}/api/user/guid/lb-team-get?{common}"
        f"&teamId={team['temid']}"
        f"&socialId={social_id}"
    )


def card_stats_url(player: dict[str, Any], match: int, live: bool = False) -> str:
    prefix = "feed/live" if live else "feed"
    return (
        f"{BASE_URL}/api/{prefix}/gameday-player/card-stats?"
        f"teamId={player.get('TeamId')}"
        f"&playerId={player.get('Id')}"
        f"&gamedayId={match}"
    )


def profile_url(player: dict[str, Any], live: bool = False) -> str:
    prefix = "feed/live" if live else "feed"
    return (
        f"{BASE_URL}/api/{prefix}/gameday-player/popup-cards?"
        f"teamId={player.get('TeamId')}"
        f"&playerId={player.get('Id')}"
        f"&buster={buster()}"
    )


def fixtures_by_match(page) -> dict[int, dict[str, Any]]:
    payload = fetch_json(
        page,
        f"{BASE_URL}/api/feed/tour-fixtures?lang=en&liveVersion=05242026185741",
    )
    raw = api_value(payload) or []
    if isinstance(raw, dict):
        raw = raw.get("Fixtures") or raw.get("fixtures") or []
    fixtures: dict[int, dict[str, Any]] = {}
    for item in raw:
        match = item.get("TeamGamedayId") or item.get("Gameday") or item.get("Matchday")
        if match is not None:
            fixtures[int(match)] = item
    return fixtures


def player_catalog(page, match: int) -> tuple[dict[int, dict[str, Any]], bool]:
    payload = fetch_json(page, players_url(match))
    live = False
    if not api_success(payload):
        payload = fetch_json(page, players_url(match, live=True))
        live = True
    value = api_value(payload) or {}
    players = value.get("Players") if isinstance(value, dict) else value
    return {int(player["Id"]): player for player in players or []}, live


def active_booster(team_value: dict[str, Any], match: int) -> dict[str, Any] | None:
    for entry in team_value.get("booster") or []:
        if int(entry.get("cf_team_gamedayid") or -1) == match:
            booster_id = int(entry.get("cf_boosterid") or 0)
            return {
                "id": booster_id,
                "name": BOOSTERS.get(booster_id, f"booster_{booster_id}"),
                "raw": entry,
            }
    return None


def is_scoring_player(player: dict[str, Any], match: int) -> bool:
    return (
        player.get("IsAnnounced") in {"P", "S", "IMP"}
        and int(player.get("PlyrGamedayId") or -1) == match
    )


def booster_applies(player: dict[str, Any], booster_id: int | None) -> bool:
    if booster_id == 3:
        return True
    if booster_id == 9:
        return str(player.get("IS_FP")) == "1"
    if booster_id == 10:
        return not int(float(player.get("IS_FP") or 0))
    return False


def fantasy_points(
    player: dict[str, Any],
    match: int,
    team_value: dict[str, Any],
    booster: dict[str, Any] | None,
) -> float:
    if not is_scoring_player(player, match):
        return 0.0
    points = float(player.get("GamedayPoints") or 0)
    player_id = int(player["Id"])
    booster_id = booster["id"] if booster else None
    if player_id == int(team_value.get("mcapt") or -1):
        points *= 3 if booster_id == 12 else 2
    elif player_id == int(team_value.get("vcapt") or -1):
        points *= 1.5
    elif player_id == int(team_value.get("bcapt") or -1):
        points *= 2
    if booster_applies(player, booster_id):
        points *= 2
    return points


def extract_stats(raw: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    stats: dict[str, Any] = {}
    breakdown: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return stats, breakdown

    gameday_stats = raw.get("GamedayStats") or []
    if gameday_stats:
        stat = gameday_stats[0]
        stats.update(
            {
                "runs": stat.get("BatsmanRuns"),
                "balls": stat.get("NoOfFacedBalls"),
                "fours": stat.get("Boundaries"),
                "sixes": stat.get("Sixes"),
                "strikerate": stat.get("StrikeRate"),
                "wickets": stat.get("Wickets"),
                "economy": stat.get("EconomyRate"),
                "maidens": stat.get("IsMaiden"),
                "catches": stat.get("Catches"),
                "runouts": stat.get("RunOut"),
                "stumpings": stat.get("Stumping"),
                "played": stat.get("IsPlayed"),
            }
        )

    gameday_points = raw.get("GamedayPoints") or []
    if gameday_points:
        points = gameday_points[0]
        breakdown.update(
            {
                "starting_xi": points.get("PlayedPoints"),
                "runs": points.get("RunsPoints"),
                "fours": points.get("FourPoints"),
                "sixes": points.get("SixPoints"),
                "strike_rate": points.get("StrikeRatePoints"),
                "wickets": points.get("WicketPoints"),
                "economy": points.get("EconomyRatePoint"),
                "catches": points.get("CatchePoints"),
                "stumpings": points.get("StumpingPoints"),
                "run_outs": points.get("RunOutPoints"),
                "bonuses": {
                    "half_century": points.get("HalfCenturyPoints"),
                    "century": points.get("FullCenturyPoints"),
                    "thirty": points.get("ThirtyBonusPoints"),
                    "wicket_bonus": points.get("WicketBonusPoints"),
                    "catch_bonus": points.get("CthsBonusPoints"),
                    "mom": points.get("MomPoints"),
                },
                "overall": points.get("OverAllPoints"),
            }
        )

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            name = value.get("Name") or value.get("name") or value.get("Title")
            points = value.get("Points") or value.get("points") or value.get("Pts")
            if name is not None and points is not None:
                breakdown[str(name).strip()] = points
            for key, child in value.items():
                low = str(key).lower()
                if low in {
                    "runs",
                    "balls",
                    "fours",
                    "sixes",
                    "strikerate",
                    "wickets",
                    "economy",
                    "maidens",
                    "catches",
                    "runouts",
                    "stumpings",
                    "played",
                }:
                    stats[low] = child
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(raw)
    return stats, breakdown


def player_detail(
    page,
    player: dict[str, Any],
    match: int,
    live: bool,
) -> dict[str, Any]:
    if not is_scoring_player(player, match):
        return {
            "scrape_status": "not_played_or_no_points",
            "stats": {},
            "points_breakdown": {},
            "raw": None,
        }

    urls = [card_stats_url(player, match, live=False)]
    if live:
        urls.append(card_stats_url(player, match, live=True))
    last_payload: dict[str, Any] | None = None
    for url in urls:
        payload = fetch_json(page, url)
        last_payload = payload
        if api_success(payload) and api_value(payload) is not None:
            raw = api_value(payload)
            stats, breakdown = extract_stats(raw)
            return {
                "scrape_status": "ok",
                "stats": stats,
                "points_breakdown": breakdown,
                "raw": raw,
            }
    meta = (last_payload or {}).get("Meta") or {}
    return {
        "scrape_status": "unavailable",
        "stats": {},
        "points_breakdown": {},
        "raw": last_payload,
        "message": meta.get("Message"),
        "retval": meta.get("RetVal"),
    }


def player_profile(page, player: dict[str, Any], live: bool) -> dict[str, Any] | None:
    urls = [profile_url(player, live=False)]
    if live:
        urls.append(profile_url(player, live=True))
    for url in urls:
        payload = fetch_json(page, url)
        if api_success(payload) and api_value(payload) is not None:
            raw = api_value(payload)
            return {
                "scrape_status": "ok",
                "completed_matches": raw.get("CompletedMatches")
                if isinstance(raw, dict)
                else None,
                "raw": raw,
            }
    return None


def fixture_summary(fixture: dict[str, Any] | None) -> dict[str, Any]:
    if not fixture:
        return {}
    return {
        "match_id": fixture.get("MatchId"),
        "match_number": fixture.get("MatchNumber") or fixture.get("Matchday"),
        "team_gameday_id": fixture.get("TeamGamedayId"),
        "tour_gameday_id": fixture.get("TourGamedayId"),
        "home_team": fixture.get("HomeTeamShortName") or fixture.get("HomeTeamName"),
        "away_team": fixture.get("AwayTeamShortName") or fixture.get("AwayTeamName"),
        "venue": fixture.get("Venue1") or fixture.get("Venue"),
        "status": fixture.get("Status") or fixture.get("MatchStatus"),
        "starts_at": fixture.get("MatchdateTime"),
    }


def scrape(args: argparse.Namespace) -> dict[str, Any]:
    settings = Settings()
    pw, browser = create_browser()
    try:
        login(browser, settings, SilentTelegram())
        page = browser.new_page()
        page.goto(f"{BASE_URL}/league/view/{LEAGUE_ID}", wait_until="networkidle")
        user = get_login_user(page)
        user_guid = user.get("SocialId") or user.get("Guid") or user.get("UserGuid")
        if not user_guid:
            raise RuntimeError(f"Could not find user GUID in login cookie: {user!r}")

        fixtures = fixtures_by_match(page)
        first_match = max(args.matches)
        leaderboard = api_value(fetch_json(page, leaderboard_url(first_match))) or []
        teams_by_id = {int(team["temid"]): dict(team) for team in leaderboard}
        profiles: dict[int, dict[str, Any] | None] = {}
        catalogs: dict[int, tuple[dict[int, dict[str, Any]], bool]] = {}
        details: dict[tuple[int, int, int], dict[str, Any]] = {}

        result = {
            "league": {
                "id": LEAGUE_ID,
                "name": LEAGUE_NAME,
                "source": f"{BASE_URL}/league/view/{LEAGUE_ID}",
            },
            "generated_at": datetime.now(UTC).isoformat(),
            "teams": [],
        }

        for team in leaderboard:
            log.info("Scraping %s", team.get("temname"))
            team_obj = {
                "team_id": team.get("temid"),
                "team_name": team.get("temname"),
                "user_name": team.get("usrname"),
                "social_id": team.get("usrscoid"),
                "overall": team,
                "matches": [],
            }
            for match in args.matches:
                if match not in catalogs:
                    catalogs[match] = player_catalog(page, match)
                catalog, live = catalogs[match]
                team_payload = fetch_json(page, team_url(team, match, user_guid))
                team_value = api_value(team_payload) or {}
                booster = active_booster(team_value, match)
                players = []
                total = 0.0
                for player_id in team_value.get("plyid") or []:
                    player = catalog.get(int(player_id), {"Id": int(player_id)})
                    applied = fantasy_points(player, match, team_value, booster)
                    total += applied
                    if args.include_profiles and int(player_id) not in profiles:
                        profiles[int(player_id)] = player_profile(page, player, live)
                    detail_key = (
                        int(player.get("TeamId") or 0),
                        int(player.get("Id") or 0),
                        match,
                    )
                    if detail_key not in details:
                        details[detail_key] = player_detail(page, player, match, live)
                    detail = details[detail_key]
                    player_obj = {
                        "player_id": player.get("Id"),
                        "player_name": player.get("Name") or player.get("ShortName"),
                        "ipl_team_id": player.get("TeamId"),
                        "ipl_team": player.get("TeamShortName")
                        or player.get("TeamName"),
                        "role": ROLE_BY_SKILL.get(
                            int(player.get("SkillId") or 0),
                            player.get("SkillName"),
                        ),
                        "selected_fantasy_team": team.get("temname"),
                        "match": match,
                        "base_gameday_points": player.get("GamedayPoints"),
                        "fantasy_applied_score": applied,
                        "is_captain": int(player.get("Id") or -1)
                        == int(team_value.get("mcapt") or -2),
                        "is_vice_captain": int(player.get("Id") or -1)
                        == int(team_value.get("vcapt") or -2),
                        "is_booster_captain": int(player.get("Id") or -1)
                        == int(team_value.get("bcapt") or -2),
                        "metadata": player,
                        "detail": detail,
                        "profile": profiles.get(int(player_id)),
                    }
                    players.append(player_obj)

                match_obj = {
                    "match": match,
                    "fixture": fixture_summary(fixtures.get(match)),
                    "league_rank": (
                        teams_by_id.get(int(team["temid"])) or {}
                    ).get("rank"),
                    "leaderboard_total_points": (
                        teams_by_id.get(int(team["temid"])) or {}
                    ).get("points"),
                    "total_match_points": round(total, 1),
                    "transfers": {
                        "used_in_match": team_value.get("subgdusr"),
                        "used_cumulative": team_value.get("subusr"),
                        "remaining": team_value.get("subleft"),
                        "allowed": team_value.get("suballd"),
                    },
                    "booster": booster,
                    "scrape_status": (
                        "ok" if api_success(team_payload) else "team_unavailable"
                    ),
                    "raw_team": team_value,
                    "players": players,
                }
                team_obj["matches"].append(match_obj)
                log.info(
                    "%s match %s: %.1f pts, %d players",
                    team.get("temname"),
                    match,
                    total,
                    len(players),
                )
            result["teams"].append(team_obj)
        return result
    finally:
        browser.close()
        pw.stop()


def flatten_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team in data["teams"]:
        for match in team["matches"]:
            for player in match["players"]:
                detail = player.get("detail") or {}
                stats = detail.get("stats") or {}
                breakdown = detail.get("points_breakdown") or {}
                row = {
                    "league_id": data["league"]["id"],
                    "league_name": data["league"]["name"],
                    "team_id": team["team_id"],
                    "team_name": team["team_name"],
                    "overall_rank": (team.get("overall") or {}).get("rank"),
                    "overall_points": (team.get("overall") or {}).get("points"),
                    "match": match["match"],
                    "fixture": json.dumps(match.get("fixture") or {}, sort_keys=True),
                    "league_rank": match.get("league_rank"),
                    "total_match_points": match.get("total_match_points"),
                    "transfers_used_in_match": match["transfers"].get("used_in_match"),
                    "transfers_used_cumulative": match["transfers"].get(
                        "used_cumulative"
                    ),
                    "transfers_remaining": match["transfers"].get("remaining"),
                    "booster_id": (match.get("booster") or {}).get("id"),
                    "booster_name": (match.get("booster") or {}).get("name"),
                    "player_id": player.get("player_id"),
                    "player_name": player.get("player_name"),
                    "ipl_team_id": player.get("ipl_team_id"),
                    "ipl_team": player.get("ipl_team"),
                    "role": player.get("role"),
                    "base_gameday_points": player.get("base_gameday_points"),
                    "fantasy_applied_score": player.get("fantasy_applied_score"),
                    "is_captain": player.get("is_captain"),
                    "is_vice_captain": player.get("is_vice_captain"),
                    "is_booster_captain": player.get("is_booster_captain"),
                    "detail_scrape_status": detail.get("scrape_status"),
                    "runs": stats.get("runs"),
                    "balls": stats.get("balls"),
                    "fours": stats.get("fours"),
                    "sixes": stats.get("sixes"),
                    "strike_rate": stats.get("strikerate"),
                    "wickets": stats.get("wickets"),
                    "economy": stats.get("economy"),
                    "maidens": stats.get("maidens"),
                    "catches": stats.get("catches"),
                    "run_outs": stats.get("runouts"),
                    "stumpings": stats.get("stumpings"),
                    "played_status": stats.get("played"),
                    "points_breakdown_json": json.dumps(breakdown, sort_keys=True),
                    "raw_detail_json": json.dumps(detail.get("raw"), sort_keys=True),
                }
                rows.append(row)
    return rows


def write_outputs(data: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    rows = flatten_rows(data)
    if not rows:
        csv_path.write_text("", encoding="utf-8")
        return
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matches", default=DEFAULT_MATCHES)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-out", type=Path, default=OUT_JSON)
    parser.add_argument("--csv-out", type=Path, default=OUT_CSV)
    parser.add_argument(
        "--include-profiles",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    args.matches = parse_match_range(args.matches)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    data = scrape(args)
    rows = flatten_rows(data)
    print(
        f"Scraped {len(data['teams'])} teams, {len(args.matches)} matches, "
        f"{len(rows)} player rows."
    )
    for team in data["teams"]:
        totals = ", ".join(
            f"M{m['match']}={m['total_match_points']}" for m in team["matches"]
        )
        print(f"{team['team_name']}: {totals}")

    if args.dry_run:
        return
    write_outputs(data, args.json_out, args.csv_out)
    print(f"Wrote {args.json_out}")
    print(f"Wrote {args.csv_out}")


if __name__ == "__main__":
    main()
