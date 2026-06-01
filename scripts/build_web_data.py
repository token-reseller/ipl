"""Build static web data artifacts from the league JSON.

Reuses :func:`ipl_fantasy.league_data.load_league` (the same flattening the
Streamlit dashboard uses) and precomputes every aggregation that does not
depend on an interactive filter. Emits two compact JSON files consumed by the
static Cloudflare Pages app:

    pages_ipl_dashboard/data/meta.json     -- everything except the Player Explorer raw rows
    pages_ipl_dashboard/data/players.json  -- the one raw table the Player Explorer filters

Run::

    uv run python scripts/build_web_data.py

Numbers are rounded to 1 dp, NaN/NaT become null, and Timestamps become ISO
date strings so the output is small and JSON-clean.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from ipl_fantasy.league_data import LeagueFrames, load_league

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "gentlemans_league_2026.json"
OUT_DIR = ROOT / "pages_ipl_dashboard" / "data"

# Copied from scripts dashboard.py so the web build stays self-contained.
BOOSTER_DESCRIPTIONS = {
    "triple_captain": "Captain earns 3× (instead of 2×) base points.",
    "double_power": "Every picked player earns 2× base points.",
    "indian_warriors": "Indian (non-foreign) players in the XI get a boost.",
    "foreign_stars": "Foreign players in the XI get a boost.",
    "free_hit": "Free transfers without burning the weekly transfer budget.",
    "wildcard": "Full team rebuild without spending transfers.",
}


# ---------------------------------------------------------------------------
# JSON cleaning helpers
# ---------------------------------------------------------------------------

def _clean(value: Any) -> Any:
    """Make a scalar JSON-safe: NaN/NaT -> None, Timestamp -> ISO date."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.date().isoformat()
    if value is pd.NaT:
        return None
    return value


def _round(value: Any, ndigits: int = 1) -> Any:
    value = _clean(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), ndigits)
    return value


def _records(df: pd.DataFrame, *, round_cols: tuple[str, ...] = ()) -> list[dict]:
    """DataFrame -> list of JSON-safe dicts, rounding the named float columns."""
    out: list[dict] = []
    round_set = set(round_cols)
    for rec in df.to_dict(orient="records"):
        clean = {}
        for k, v in rec.items():
            clean[k] = _round(v) if k in round_set else _clean(v)
        out.append(clean)
    return out


# ---------------------------------------------------------------------------
# Tab 1 -- Standings (dashboard.py:81-220)
# ---------------------------------------------------------------------------

def build_standings(lf: LeagueFrames) -> dict[str, Any]:
    # Standings cards + last non-null match delta per team.
    last_deltas = (
        lf.team_match_df.dropna(subset=["total_match_points"])
        .sort_values("starts_at")
        .groupby("team_id")
        .tail(1)
        .set_index("team_id")["total_match_points"]
    )
    teams = []
    for _, row in lf.team_df.iterrows():
        teams.append(
            {
                "id": int(row["team_id"]),
                "name": row["team_name"],
                "rank": int(row["overall_rank"]),
                "points": _round(row["overall_points"]),
                "last_delta": _round(last_deltas.get(row["team_id"])),
            }
        )

    # Per-team x match trajectory with the four additive score components
    # (raw / captain / vc / booster), so the frontend can recompute rankings
    # for any toggled subset. Each row's components sum to total_match_points.
    tm = lf.team_match_df.dropna(subset=["cumulative_points"]).copy()
    tm["fixture"] = tm["home_team"] + " vs " + tm["away_team"]

    p = lf.team_match_player_df.copy()
    base = p["base_gameday_points"].fillna(0.0)
    p["cap_bonus"] = base.where(p["is_captain"], 0.0)  # captain = 2x base -> +1x
    p["vc_bonus"] = (0.5 * base).where(p["is_vice_captain"], 0.0)  # VC = 1.5x -> +0.5x
    comp = (
        p.groupby(["team_id", "match"], as_index=False)
        .agg(
            base_match=("base_gameday_points", "sum"),
            cap_match=("cap_bonus", "sum"),
            vc_match=("vc_bonus", "sum"),
        )
    )

    raw_match = comp.merge(
        lf.team_match_df[["team_id", "match", "starts_at"]],
        on=["team_id", "match"],
        how="left",
    ).sort_values(["team_id", "starts_at"])

    traj = tm.merge(
        comp[["team_id", "match", "base_match", "cap_match", "vc_match"]],
        on=["team_id", "match"],
        how="left",
    ).sort_values(["team_id", "starts_at"])
    # Booster component = residual so base+cap+vc+boost == official match total.
    traj["boost_match"] = traj["total_match_points"] - (
        traj["base_match"] + traj["cap_match"] + traj["vc_match"]
    )

    trajectory = [
        {
            "tid": int(r["team_id"]),
            "name": r["team_name"],
            "m": int(r["match"]),
            "fixture": r["fixture"],
            "booster": _clean(r["booster_name"]),
            "base": _round(r["base_match"]),
            "cap": _round(r["cap_match"]),
            "vc": _round(r["vc_match"]),
            "boost": _round(r["boost_match"]),
        }
        for _, r in traj.iterrows()
    ]

    # Raw standings (no captain / VC / booster).
    raw_totals = (
        raw_match.groupby("team_id", as_index=False)["base_match"]
        .sum()
        .rename(columns={"base_match": "raw_points"})
        .merge(lf.team_df[["team_id", "team_name"]], on="team_id")
        .sort_values("raw_points", ascending=False)
        .reset_index(drop=True)
    )
    raw_totals["raw_rank"] = raw_totals.index + 1
    raw_standings = [
        {
            "rank": int(r["raw_rank"]),
            "name": r["team_name"],
            "raw_points": _round(r["raw_points"]),
        }
        for _, r in raw_totals.iterrows()
    ]

    # Multiplier boost vs raw selection.
    compare = lf.team_df[
        ["team_id", "team_name", "overall_rank", "overall_points"]
    ].merge(raw_totals[["team_id", "raw_rank", "raw_points"]], on="team_id")
    compare["boost"] = compare["overall_points"] - compare["raw_points"]
    compare["rank_delta"] = compare["raw_rank"] - compare["overall_rank"]
    compare = compare.sort_values("overall_rank")
    boost_compare = [
        {
            "name": r["team_name"],
            "rank": int(r["overall_rank"]),
            "raw_rank": int(r["raw_rank"]),
            "rank_delta": int(r["rank_delta"]),
            "points": _round(r["overall_points"]),
            "raw_points": _round(r["raw_points"]),
            "boost": _round(r["boost"]),
        }
        for _, r in compare.iterrows()
    ]

    return {
        "teams": teams,
        "team_trajectory": trajectory,
        "raw_standings": raw_standings,
        "boost_compare": boost_compare,
    }


# ---------------------------------------------------------------------------
# Tab 3 -- Booster analysis (dashboard.py:362-479)
# ---------------------------------------------------------------------------

def build_boosters(lf: LeagueFrames) -> dict[str, Any]:
    tm = lf.team_match_df
    tmp = lf.team_match_player_df

    used = tm.dropna(subset=["booster_name"]).copy()
    if used.empty:
        return {"booster_usages": [], "booster_avg": [], "booster_xi": {}}

    roi = (
        tmp.groupby(["team_id", "match"])
        .agg(
            sum_base=("base_gameday_points", "sum"),
            sum_applied=("fantasy_applied_score", "sum"),
        )
        .reset_index()
    )
    roi["roi_delta"] = roi["sum_applied"] - roi["sum_base"]
    used = used.merge(roi, on=["team_id", "match"], how="left").sort_values(
        ["starts_at", "team_name"]
    )

    usages = [
        {
            "tid": int(r["team_id"]),
            "name": r["team_name"],
            "m": int(r["match"]),
            "booster": r["booster_name"],
            "home": r["home_team"],
            "away": r["away_team"],
            "base": _round(r["sum_base"]),
            "applied": _round(r["sum_applied"]),
            "roi": _round(r["roi_delta"]),
        }
        for _, r in used.iterrows()
    ]

    by_booster = (
        used.groupby(["booster_name", "team_name"], as_index=False)["roi_delta"]
        .mean()
        .sort_values("roi_delta", ascending=False)
    )
    booster_avg = [
        {
            "booster": r["booster_name"],
            "name": r["team_name"],
            "roi": _round(r["roi_delta"]),
        }
        for _, r in by_booster.iterrows()
    ]

    # Per-usage XI breakdown keyed "<tid>_<match>".
    booster_xi: dict[str, list[dict]] = {}
    for _, r in used.iterrows():
        tid, match_no = int(r["team_id"]), int(r["match"])
        xi = tmp[(tmp["team_id"] == tid) & (tmp["match"] == match_no)].sort_values(
            "fantasy_applied_score", ascending=False
        )
        booster_xi[f"{tid}_{match_no}"] = [
            {
                "p": pr["player_name"],
                "ipl": pr["ipl_team"],
                "role": pr["role"],
                "fp": bool(pr["is_foreign"]),
                "cap": bool(pr["is_captain"]),
                "vc": bool(pr["is_vice_captain"]),
                "base": _round(pr["base_gameday_points"]),
                "applied": _round(pr["fantasy_applied_score"]),
                "delta": _round(pr["delta"]),
            }
            for _, pr in xi.iterrows()
        ]

    return {
        "booster_usages": usages,
        "booster_avg": booster_avg,
        "booster_xi": booster_xi,
    }


# ---------------------------------------------------------------------------
# Tab 4 -- Captaincy (dashboard.py:490-553)
# ---------------------------------------------------------------------------

def build_captaincy(lf: LeagueFrames) -> dict[str, Any]:
    tmp = lf.team_match_player_df.copy()
    tmp["rank_in_xi"] = tmp.groupby(["team_id", "match"])[
        "base_gameday_points"
    ].rank(ascending=False, method="min")

    caps = tmp[tmp["is_captain"]].copy()
    caps["hit"] = caps["rank_in_xi"] <= 3

    summary = (
        caps.groupby("team_name")
        .agg(
            picks=("match", "count"),
            hits=("hit", "sum"),
            avg_base=("base_gameday_points", "mean"),
            avg_applied=("fantasy_applied_score", "mean"),
        )
        .reset_index()
    )
    summary["hit_rate"] = (summary["hits"] / summary["picks"] * 100).round(1)
    summary = summary.sort_values("hit_rate", ascending=False)
    captain_summary = [
        {
            "name": r["team_name"],
            "picks": int(r["picks"]),
            "hits": int(r["hits"]),
            "hit_rate": _round(r["hit_rate"]),
            "avg_base": _round(r["avg_base"]),
            "avg_applied": _round(r["avg_applied"]),
        }
        for _, r in summary.iterrows()
    ]

    caps_sorted = caps.sort_values(["team_name", "starts_at"])
    captain_picks = [
        {
            "tid": int(r["team_id"]),
            "name": r["team_name"],
            "m": int(r["match"]),
            "player": r["player_name"],
            "ipl": r["ipl_team"],
            "role": r["role"],
            "base": _round(r["base_gameday_points"]),
            "applied": _round(r["fantasy_applied_score"]),
            "rank": int(r["rank_in_xi"]) if pd.notna(r["rank_in_xi"]) else None,
            "hit": bool(r["hit"]),
            "booster": _clean(r["booster_name"]),
        }
        for _, r in caps_sorted.iterrows()
    ]

    pick_counts = (
        caps.groupby(["team_name", "player_name", "ipl_team"], as_index=False)
        .agg(
            times=("match", "count"),
            avg_base=("base_gameday_points", "mean"),
        )
        .sort_values(["team_name", "times"], ascending=[True, False])
    )
    # Top 10 per team.
    pick_counts = pick_counts.groupby("team_name", group_keys=False).head(10)
    most_captained = [
        {
            "name": r["team_name"],
            "player": r["player_name"],
            "ipl": r["ipl_team"],
            "times": int(r["times"]),
            "avg_base": _round(r["avg_base"]),
        }
        for _, r in pick_counts.iterrows()
    ]

    return {
        "captain_summary": captain_summary,
        "captain_picks": captain_picks,
        "most_captained": most_captained,
    }


# ---------------------------------------------------------------------------
# Tab 2 -- Player explorer raw rows
# ---------------------------------------------------------------------------

def build_players(lf: LeagueFrames) -> dict[str, Any]:
    df = lf.team_match_player_df
    rows = [
        {
            "tid": int(r["team_id"]),
            "tname": r["team_name"],
            "m": int(r["match"]),
            "pid": _clean(r["player_id"]),
            "player": r["player_name"],
            "ipl": _clean(r["ipl_team"]),
            "role": _clean(r["role"]),
            "base": _round(r["base_gameday_points"]),
            "applied": _round(r["fantasy_applied_score"]),
            "cap": bool(r["is_captain"]),
            "vc": bool(r["is_vice_captain"]),
            "booster": _clean(r["booster_name"]),
        }
        for _, r in df.iterrows()
    ]
    return {
        "ipl_teams": sorted(df["ipl_team"].dropna().unique().tolist()),
        "roles": sorted(df["role"].dropna().unique().tolist()),
        "fantasy_teams": sorted(df["team_name"].dropna().unique().tolist()),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    lf = load_league(DATA_PATH)

    matches = [
        {
            "m": int(r["match"]),
            "id": _clean(r["match_id"]),
            "label": f"{r['home_team']} vs {r['away_team']}",
            "home": r["home_team"],
            "away": r["away_team"],
            "ts": _clean(r["starts_at"]),
        }
        for _, r in lf.match_df.iterrows()
    ]

    standings = build_standings(lf)
    meta = {
        "league": lf.league_name or "Gentlemans league",
        "generated_at": lf.generated_at,
        "n_teams": len(lf.team_df),
        "n_matches": len(lf.match_df),
        "n_player_rows": len(lf.team_match_player_df),
        "booster_desc": BOOSTER_DESCRIPTIONS,
        "matches": matches,
        **standings,
        **build_boosters(lf),
        **build_captaincy(lf),
    }
    players = build_players(lf)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, separators=(",", ":")))
    (OUT_DIR / "players.json").write_text(
        json.dumps(players, separators=(",", ":"))
    )

    meta_kb = (OUT_DIR / "meta.json").stat().st_size / 1024
    players_kb = (OUT_DIR / "players.json").stat().st_size / 1024
    print(
        f"Wrote {OUT_DIR}/meta.json ({meta_kb:.0f} KB) and "
        f"players.json ({players_kb:.0f} KB)"
    )
    print(
        f"teams={meta['n_teams']} matches={meta['n_matches']} "
        f"player_rows={meta['n_player_rows']} "
        f"booster_usages={len(meta['booster_usages'])} "
        f"captain_picks={len(meta['captain_picks'])}"
    )


if __name__ == "__main__":
    main()
