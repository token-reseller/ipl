"""Streamlit dashboard for exploring the Gentlemans league season.

Run via the launcher::

    uv run streamlit run scripts/dashboard.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from ipl_fantasy.league_data import LeagueFrames, load_league

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "gentlemans_league_2026.json"

BOOSTER_DESCRIPTIONS = {
    "triple_captain": "Captain earns 3× (instead of 2×) base points.",
    "double_power": "Every picked player earns 2× base points.",
    "indian_warriors": "Indian (non-foreign) players in the XI get a boost.",
    "foreign_stars": "Foreign players in the XI get a boost.",
    "free_hit": "Free transfers without burning the weekly transfer budget.",
    "wildcard": "Full team rebuild without spending transfers.",
}


@st.cache_data(show_spinner="Loading league data…")
def _cached_load(path: str) -> LeagueFrames:
    return load_league(path)


def main() -> None:
    st.set_page_config(
        page_title="IPL Fantasy — Season Dashboard",
        page_icon=":cricket_game:",
        layout="wide",
    )

    lf = _cached_load(str(DATA_PATH))

    with st.sidebar:
        st.title(lf.league_name or "Gentlemans league")
        st.caption(f"Data generated at: {lf.generated_at}")
        if st.button("Reload data"):
            st.cache_data.clear()
            st.rerun()
        st.divider()
        st.write(
            f"**Teams:** {len(lf.team_df)}  \n"
            f"**Matches:** {len(lf.match_df)}  \n"
            f"**Player rows:** {len(lf.team_match_player_df):,}"
        )

    st.title("Gentlemans League — Season Explorer")

    tab_standings, tab_players, tab_boosters, tab_captains = st.tabs(
        ["Standings", "Player explorer", "Booster analysis", "Captaincy"]
    )

    with tab_standings:
        _render_standings(lf)
    with tab_players:
        _render_player_explorer(lf)
    with tab_boosters:
        _render_booster_analysis(lf)
    with tab_captains:
        _render_captaincy(lf)


# ---------------------------------------------------------------------------
# Tab 1 — Standings & trajectory
# ---------------------------------------------------------------------------

def _render_standings(lf: LeagueFrames) -> None:
    st.subheader("Current standings")
    cols = st.columns(len(lf.team_df))
    # Compute last-match delta per team for the metric arrow.
    last_deltas = (
        lf.team_match_df.dropna(subset=["total_match_points"])
        .sort_values("starts_at")
        .groupby("team_id")
        .tail(1)
        .set_index("team_id")["total_match_points"]
    )
    for col, (_, row) in zip(cols, lf.team_df.iterrows()):
        delta = last_deltas.get(row["team_id"])
        col.metric(
            label=f"#{int(row['overall_rank'])} {row['team_name']}",
            value=f"{row['overall_points']:.1f}",
            delta=f"+{delta:.1f} last match" if pd.notna(delta) else None,
        )

    st.subheader("Cumulative points across the season")
    plot_df = lf.team_match_df.dropna(subset=["cumulative_points"]).copy()
    plot_df["fixture"] = plot_df["home_team"] + " vs " + plot_df["away_team"]
    fig = px.line(
        plot_df,
        x="match",
        y="cumulative_points",
        color="team_name",
        markers=True,
        hover_data={
            "fixture": True,
            "booster_name": True,
            "total_match_points": ":.1f",
            "match": False,
        },
        labels={
            "match": "Match #",
            "cumulative_points": "Cumulative points",
            "team_name": "Fantasy team",
        },
    )
    fig.update_layout(legend_title_text="", height=480)
    st.plotly_chart(fig, width="stretch")

    st.subheader("Per-match points (overlay)")
    fig2 = px.bar(
        plot_df,
        x="match",
        y="total_match_points",
        color="team_name",
        barmode="group",
        labels={"match": "Match #", "total_match_points": "Points"},
    )
    fig2.update_layout(legend_title_text="", height=400)
    st.plotly_chart(fig2, width="stretch")

    st.subheader("Standings table")
    st.dataframe(lf.team_df, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Tab 2 — Player explorer
# ---------------------------------------------------------------------------

def _render_player_explorer(lf: LeagueFrames) -> None:
    df = lf.team_match_player_df

    f1, f2, f3 = st.columns(3)
    ipl_teams = sorted(df["ipl_team"].dropna().unique())
    roles = sorted(df["role"].dropna().unique())
    fantasy_teams = sorted(df["team_name"].dropna().unique())
    sel_ipl = f1.multiselect("IPL team", ipl_teams)
    sel_role = f2.multiselect("Role", roles)
    sel_fteam = f3.multiselect("Picked by fantasy team", fantasy_teams)

    filt = df
    if sel_ipl:
        filt = filt[filt["ipl_team"].isin(sel_ipl)]
    if sel_role:
        filt = filt[filt["role"].isin(sel_role)]
    if sel_fteam:
        filt = filt[filt["team_name"].isin(sel_fteam)]

    st.caption(
        f"{len(filt):,} player-match rows match the current filters "
        f"(out of {len(df):,})."
    )

    st.subheader("Season totals (top 25 by base points)")
    agg = (
        filt.groupby(["player_id", "player_name", "ipl_team", "role"])
        .agg(
            matches_picked=("match", "nunique"),
            matches_played=("played", lambda s: int((s == 1).sum())),
            total_base=("base_gameday_points", "sum"),
            avg_base=("base_gameday_points", "mean"),
            total_applied=("fantasy_applied_score", "sum"),
            captain_count=("is_captain", "sum"),
            vc_count=("is_vice_captain", "sum"),
        )
        .reset_index()
        .sort_values("total_base", ascending=False)
    )
    st.dataframe(
        agg.head(25).style.format(
            {
                "total_base": "{:.0f}",
                "avg_base": "{:.1f}",
                "total_applied": "{:.0f}",
                "captain_count": "{:.0f}",
                "vc_count": "{:.0f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Per-player match-by-match")
    player_options = (
        agg.sort_values("total_base", ascending=False)["player_name"].tolist()
    )
    if not player_options:
        st.info("No players match the current filters.")
        return
    chosen = st.selectbox("Player", player_options)
    pdf = filt[filt["player_name"] == chosen].sort_values("starts_at").copy()
    pdf["pick_role"] = pdf.apply(
        lambda r: "Captain"
        if r["is_captain"]
        else ("Vice-captain" if r["is_vice_captain"] else "Regular"),
        axis=1,
    )
    fig = px.bar(
        pdf,
        x="match",
        y="fantasy_applied_score",
        color="pick_role",
        color_discrete_map={
            "Captain": "#d62728",
            "Vice-captain": "#ff7f0e",
            "Regular": "#1f77b4",
        },
        hover_data={
            "team_name": True,
            "ipl_team": True,
            "base_gameday_points": True,
            "fantasy_applied_score": True,
            "runs": True,
            "wickets": True,
            "booster_name": True,
            "pick_role": False,
            "match": False,
        },
        labels={
            "match": "Match #",
            "fantasy_applied_score": "Applied points",
            "pick_role": "Role in the XI",
            "team_name": "Picked by",
        },
    )
    fig.update_layout(height=420)
    st.plotly_chart(fig, width="stretch")

    with st.expander("Raw rows for this player"):
        st.dataframe(
            pdf[
                [
                    "team_name",
                    "match",
                    "ipl_team",
                    "role",
                    "is_captain",
                    "is_vice_captain",
                    "base_gameday_points",
                    "fantasy_applied_score",
                    "runs",
                    "wickets",
                    "booster_name",
                ]
            ],
            hide_index=True,
            width="stretch",
        )


# ---------------------------------------------------------------------------
# Tab 3 — Booster analysis
# ---------------------------------------------------------------------------

def _render_booster_analysis(lf: LeagueFrames) -> None:
    tm = lf.team_match_df
    tmp = lf.team_match_player_df

    used = tm.dropna(subset=["booster_name"]).copy()
    if used.empty:
        st.info("No booster usages found in the dataset.")
        return

    # Per (team, match) ROI: applied - base summed across the 11 picks.
    roi = (
        tmp.groupby(["team_id", "match"])
        .agg(
            sum_base=("base_gameday_points", "sum"),
            sum_applied=("fantasy_applied_score", "sum"),
        )
        .reset_index()
    )
    roi["roi_delta"] = roi["sum_applied"] - roi["sum_base"]
    used = used.merge(roi, on=["team_id", "match"], how="left")

    st.subheader("Total booster value extracted per fantasy team")
    by_team = (
        used.groupby("team_name", as_index=False)["roi_delta"].sum().sort_values(
            "roi_delta", ascending=False
        )
    )
    fig_team = px.bar(
        by_team,
        x="team_name",
        y="roi_delta",
        text="roi_delta",
        labels={"team_name": "Fantasy team", "roi_delta": "Total ROI (Δ points)"},
    )
    fig_team.update_traces(texttemplate="%{text:.0f}")
    fig_team.update_layout(height=380)
    st.plotly_chart(fig_team, width="stretch")

    st.subheader("Average ROI by booster × fantasy team")
    by_booster = (
        used.groupby(["booster_name", "team_name"], as_index=False)["roi_delta"]
        .mean()
        .sort_values("roi_delta", ascending=False)
    )
    fig_b = px.bar(
        by_booster,
        x="booster_name",
        y="roi_delta",
        color="team_name",
        barmode="group",
        labels={
            "booster_name": "Booster",
            "roi_delta": "Avg Δ points per usage",
            "team_name": "Fantasy team",
        },
    )
    fig_b.update_layout(height=420, legend_title_text="")
    st.plotly_chart(fig_b, width="stretch")

    st.subheader("Best individual booster plays")
    best = used.sort_values("roi_delta", ascending=False).head(15)[
        [
            "team_name",
            "match",
            "booster_name",
            "home_team",
            "away_team",
            "sum_base",
            "sum_applied",
            "roi_delta",
        ]
    ]
    st.dataframe(
        best.style.format(
            {
                "sum_base": "{:.0f}",
                "sum_applied": "{:.0f}",
                "roi_delta": "{:+.1f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Drill into a single booster usage")
    used = used.sort_values(["starts_at", "team_name"])
    options = {
        f"M{int(r['match'])}  {r['home_team']} vs {r['away_team']}  · "
        f"{r['team_name']} · {r['booster_name']} "
        f"(Δ {r['roi_delta']:+.1f})": (r["team_id"], r["match"])
        for _, r in used.iterrows()
    }
    label = st.selectbox("Booster usage", list(options.keys()))
    team_id, match_no = options[label]
    booster_row = used[
        (used["team_id"] == team_id) & (used["match"] == match_no)
    ].iloc[0]
    booster_name = booster_row["booster_name"]
    st.caption(
        f"**{booster_name}** — "
        f"{BOOSTER_DESCRIPTIONS.get(booster_name, 'No description on file.')}"
    )

    xi = tmp[(tmp["team_id"] == team_id) & (tmp["match"] == match_no)].copy()
    xi = xi.sort_values("fantasy_applied_score", ascending=False)
    st.dataframe(
        xi[
            [
                "player_name",
                "ipl_team",
                "role",
                "is_foreign",
                "is_captain",
                "is_vice_captain",
                "base_gameday_points",
                "fantasy_applied_score",
                "delta",
            ]
        ].style.format(
            {
                "base_gameday_points": "{:.0f}",
                "fantasy_applied_score": "{:.0f}",
                "delta": "{:+.1f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )


# ---------------------------------------------------------------------------
# Tab 4 — Captaincy
# ---------------------------------------------------------------------------

def _render_captaincy(lf: LeagueFrames) -> None:
    tmp = lf.team_match_player_df
    # Rank base points within each (team, match) — descending, ties get min.
    tmp = tmp.copy()
    tmp["rank_in_xi"] = (
        tmp.groupby(["team_id", "match"])["base_gameday_points"]
        .rank(ascending=False, method="min")
    )

    caps = tmp[tmp["is_captain"]].copy()
    caps["hit"] = caps["rank_in_xi"] <= 3

    st.subheader("Captaincy hit-rate (captain finished top-3 in the XI)")
    summary = (
        caps.groupby("team_name")
        .agg(
            captain_picks=("match", "count"),
            hits=("hit", "sum"),
            avg_captain_base=("base_gameday_points", "mean"),
            avg_captain_applied=("fantasy_applied_score", "mean"),
        )
        .reset_index()
    )
    summary["hit_rate_%"] = (summary["hits"] / summary["captain_picks"] * 100).round(1)
    summary = summary.sort_values("hit_rate_%", ascending=False)
    st.dataframe(
        summary.style.format(
            {
                "captain_picks": "{:.0f}",
                "hits": "{:.0f}",
                "avg_captain_base": "{:.1f}",
                "avg_captain_applied": "{:.1f}",
                "hit_rate_%": "{:.1f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Captain points per match")
    caps_plot = caps.copy()
    caps_plot["outcome"] = caps_plot["hit"].map({True: "Hit (top-3)", False: "Miss"})
    fig = px.scatter(
        caps_plot,
        x="match",
        y="base_gameday_points",
        color="team_name",
        symbol="outcome",
        hover_data=["player_name", "ipl_team", "fantasy_applied_score"],
        labels={
            "match": "Match #",
            "base_gameday_points": "Captain base points",
            "team_name": "Fantasy team",
        },
    )
    fig.update_traces(marker={"size": 11})
    fig.update_layout(height=460, legend_title_text="")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Most-captained players per team")
    pick_counts = (
        caps.groupby(["team_name", "player_name", "ipl_team"], as_index=False)
        .agg(
            times_captained=("match", "count"),
            avg_base=("base_gameday_points", "mean"),
        )
        .sort_values(["team_name", "times_captained"], ascending=[True, False])
    )
    for team_name, grp in pick_counts.groupby("team_name"):
        with st.expander(f"{team_name}"):
            st.dataframe(
                grp.head(10)
                .drop(columns=["team_name"])
                .style.format({"avg_base": "{:.1f}", "times_captained": "{:.0f}"}),
                hide_index=True,
                width="stretch",
            )

    st.subheader("All captaincy picks")
    table = caps.sort_values(["team_name", "starts_at"])[
        [
            "team_name",
            "match",
            "player_name",
            "ipl_team",
            "role",
            "base_gameday_points",
            "fantasy_applied_score",
            "rank_in_xi",
            "hit",
            "booster_name",
        ]
    ]
    st.dataframe(
        table.style.format(
            {
                "base_gameday_points": "{:.0f}",
                "fantasy_applied_score": "{:.0f}",
                "rank_in_xi": "{:.0f}",
            }
        ),
        hide_index=True,
        width="stretch",
    )


if __name__ == "__main__":
    main()
