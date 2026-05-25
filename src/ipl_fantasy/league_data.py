"""Flatten the scraped league JSON into tidy pandas DataFrames.

The scraper (``scripts/scrape_league.py``) writes a nested
``data/gentlemans_league_2026.json`` shaped roughly as::

    {league, generated_at, teams: [{team_name, overall, matches: [...]}]}

For analysis (e.g. the Streamlit dashboard) it's nicer to work with a
small set of long-format DataFrames. This module is the single source of
that flattening so it can be reused outside Streamlit too. It deliberately
does not import streamlit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

_PLAYER_STAT_COLS = (
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
)


@dataclass(frozen=True)
class LeagueFrames:
    """Four flattened views of the league JSON."""

    generated_at: str
    league_name: str
    team_df: pd.DataFrame
    match_df: pd.DataFrame
    team_match_df: pd.DataFrame
    team_match_player_df: pd.DataFrame


def load_league(json_path: str | Path) -> LeagueFrames:
    """Read the league JSON and return the four flattened DataFrames."""
    with open(json_path) as f:
        raw = json.load(f)

    teams = raw["teams"]
    team_df = _build_team_df(teams)
    match_df = _build_match_df(teams)
    team_match_df = _build_team_match_df(teams)
    team_match_player_df = _build_team_match_player_df(teams)

    return LeagueFrames(
        generated_at=raw.get("generated_at", ""),
        league_name=raw.get("league", {}).get("name", ""),
        team_df=team_df,
        match_df=match_df,
        team_match_df=team_match_df,
        team_match_player_df=team_match_player_df,
    )


def _build_team_df(teams: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for t in teams:
        overall = t.get("overall") or {}
        rows.append(
            {
                "team_id": t["team_id"],
                "team_name": t["team_name"],
                "user_name": t.get("user_name"),
                "overall_rank": overall.get("rank"),
                "overall_points": overall.get("points"),
            }
        )
    return pd.DataFrame(rows).sort_values("overall_rank").reset_index(drop=True)


def _build_match_df(teams: list[dict[str, Any]]) -> pd.DataFrame:
    # All teams see the same 70 fixtures; collect unique by match_id.
    rows: dict[int, dict[str, Any]] = {}
    for t in teams:
        for m in t.get("matches", []):
            fx = m.get("fixture") or {}
            match_id = fx.get("match_id")
            if match_id in rows:
                continue
            rows[match_id] = {
                "match": m.get("match"),
                "match_id": match_id,
                "match_number": fx.get("match_number"),
                "starts_at": _parse_dt(fx.get("starts_at")),
                "home_team": fx.get("home_team"),
                "away_team": fx.get("away_team"),
                "venue": fx.get("venue"),
            }
    return (
        pd.DataFrame(list(rows.values()))
        .sort_values("starts_at")
        .reset_index(drop=True)
    )


def _build_team_match_df(teams: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for t in teams:
        for m in t.get("matches", []):
            fx = m.get("fixture") or {}
            booster = m.get("booster") or {}
            transfers = m.get("transfers") or {}
            rows.append(
                {
                    "team_id": t["team_id"],
                    "team_name": t["team_name"],
                    "match": m.get("match"),
                    "match_id": fx.get("match_id"),
                    "match_number": fx.get("match_number"),
                    "starts_at": _parse_dt(fx.get("starts_at")),
                    "home_team": fx.get("home_team"),
                    "away_team": fx.get("away_team"),
                    "booster_name": booster.get("name"),
                    "total_match_points": m.get("total_match_points"),
                    "leaderboard_total_points": m.get("leaderboard_total_points"),
                    "league_rank": m.get("league_rank"),
                    "transfers_used_in_match": transfers.get("used_in_match"),
                    "transfers_used_cumulative": transfers.get("used_cumulative"),
                    "transfers_remaining": transfers.get("remaining"),
                }
            )
    df = pd.DataFrame(rows).sort_values(["team_id", "starts_at"]).reset_index(drop=True)
    df["total_match_points"] = pd.to_numeric(df["total_match_points"], errors="coerce")
    df["cumulative_points"] = (
        df.groupby("team_id")["total_match_points"].cumsum()
    )
    return df


def _build_team_match_player_df(teams: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for t in teams:
        for m in t.get("matches", []):
            fx = m.get("fixture") or {}
            booster = m.get("booster") or {}
            for p in m.get("players", []):
                meta = p.get("metadata") or {}
                stats = p.get("stats") or {}
                row = {
                    "team_id": t["team_id"],
                    "team_name": t["team_name"],
                    "user_name": t.get("user_name"),
                    "match": m.get("match"),
                    "match_id": fx.get("match_id"),
                    "match_number": fx.get("match_number"),
                    "starts_at": _parse_dt(fx.get("starts_at")),
                    "home_team": fx.get("home_team"),
                    "away_team": fx.get("away_team"),
                    "venue": fx.get("venue"),
                    "booster_name": booster.get("name"),
                    "player_id": p.get("player_id"),
                    "player_name": p.get("player_name"),
                    "ipl_team": p.get("ipl_team"),
                    "ipl_team_id": p.get("ipl_team_id"),
                    "role": p.get("role"),
                    "skill_name": meta.get("SkillName"),
                    "base_gameday_points": p.get("base_gameday_points"),
                    "fantasy_applied_score": p.get("fantasy_applied_score"),
                    "is_captain": bool(p.get("is_captain")),
                    "is_vice_captain": bool(p.get("is_vice_captain")),
                    "is_booster_captain": bool(p.get("is_booster_captain")),
                    "selected_fantasy_team": p.get("selected_fantasy_team"),
                    "is_foreign": str(meta.get("IS_FP")) == "1",
                    "is_injured": str(meta.get("isInjured")) == "1",
                    "value": meta.get("Value"),
                    "selected_pct": meta.get("SelectedPer"),
                    "cap_selected_pct": meta.get("CapSelectedPer"),
                    "vcap_selected_pct": meta.get("VCapSelectedPer"),
                }
                for col in _PLAYER_STAT_COLS:
                    row[col] = stats.get(col)
                rows.append(row)
    df = pd.DataFrame(rows)
    df["base_gameday_points"] = pd.to_numeric(
        df["base_gameday_points"], errors="coerce"
    )
    df["fantasy_applied_score"] = pd.to_numeric(
        df["fantasy_applied_score"], errors="coerce"
    )
    df["delta"] = df["fantasy_applied_score"] - df["base_gameday_points"]
    for col in _PLAYER_STAT_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return (
        df.sort_values(["team_id", "starts_at", "player_name"])
        .reset_index(drop=True)
    )


def _parse_dt(s: str | None) -> pd.Timestamp | None:
    if not s:
        return None
    # Source format example: "03/28/2026 14:00:00"
    return pd.to_datetime(s, format="%m/%d/%Y %H:%M:%S", errors="coerce")
