"""Scrape Cricbuzz data for today's match and recommend transfers.

Usage:
    uv run python scripts/recommend.py

Flow:
  1. Look up today's match URLs from cricbuzz.py
  2. Scrape squads + season stats from Cricbuzz (via Playwright)
  3. Read current fantasy team from fantasy.iplt20.com
  4. Compare and recommend:
     - Players to swap out (not in playing XI)
     - Best available replacements (by stats)
     - Captain / Vice-Captain pick
  5. Send recommendations via Telegram
"""

import argparse
import logging
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ipl_fantasy.auth import create_browser, login
from ipl_fantasy.config import Settings
from ipl_fantasy.cricbuzz import STATS_URL
from ipl_fantasy.driver import FantasyDriver
from ipl_fantasy.notify import Telegram
from ipl_fantasy.schedule import get_cricbuzz_urls, get_matches_for

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Cricbuzz scraping (Playwright, no login needed)
# ------------------------------------------------------------------


def _polite_delay():
    time.sleep(random.uniform(2.0, 4.0))


def scrape_squads(page, squads_url: str) -> dict[str, list[str]]:
    """Scrape the squad/playing XI from a Cricbuzz match squads page.

    Returns {team_name: [player_names]}.
    """
    log.info("Scraping squads: %s", squads_url)
    _polite_delay()
    page.goto(squads_url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    raw = page.evaluate(r"""() => {
        const result = {};
        // Cricbuzz squads page has team sections with player lists
        // Look for team name headers followed by player lists
        const all = document.body.innerText;

        // Also try structured approach
        const sections = document.querySelectorAll(
            '[class*="squad"], [class*="player"], [class*="team"]'
        );

        // Fallback: extract from full page text
        // Squads pages typically have "Team Name" followed by player names
        const lines = all.split('\n').map(l => l.trim()).filter(l => l);
        let currentTeam = null;
        let players = [];

        for (const line of lines) {
            // Team headers are usually short (< 30 chars) and all caps or title case
            // Player names follow
            if (line.includes('Squad') || line.includes('Playing XI')) {
                if (currentTeam && players.length > 0) {
                    result[currentTeam] = players;
                }
                currentTeam = line.replace(/\s*(Squad|Playing XI|:)/gi, '').trim();
                players = [];
            } else if (currentTeam && line.length > 2 && line.length < 40) {
                // Skip obvious non-player lines
                const skip = ['bench', 'substitute', 'impact', 'coach', 'captain',
                              'wicketkeeper', 'all-rounder', 'batter', 'bowler',
                              'overseas', 'uncapped'];
                if (!skip.some(s => line.toLowerCase().includes(s))) {
                    // Clean player name — remove (c), (wk), etc.
                    const name = line.replace(/\s*\([^)]*\)\s*/g, '').trim();
                    if (name) players.push(name);
                }
            }
        }

        // Save last team
        if (currentTeam && players.length > 0) {
            result[currentTeam] = players;
        }

        return result;
    }""")

    log.info("Squads scraped: %s", {k: len(v) for k, v in raw.items()})
    return raw


def scrape_stats(page, stats_url: str) -> dict:
    """Scrape season batting/bowling stats from Cricbuzz stats page.

    Returns {"batting": [...], "bowling": [...]}.
    """
    log.info("Scraping stats: %s", stats_url)
    _polite_delay()
    page.goto(stats_url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # Scrape batting stats (default view — usually "Most Runs")
    batting = page.evaluate(r"""() => {
        const rows = [];
        const tables = document.querySelectorAll('table');
        for (const table of tables) {
            const trs = table.querySelectorAll('tbody tr, tr');
            for (const tr of trs) {
                const cells = Array.from(tr.querySelectorAll('td'));
                if (cells.length >= 4) {
                    rows.push(cells.map(td => td.textContent.trim()));
                }
            }
            if (rows.length > 0) break;
        }
        return rows;
    }""")

    # Click bowling tab and scrape
    page.evaluate(r"""() => {
        const links = document.querySelectorAll('a, button, [role="tab"]');
        for (const el of links) {
            const text = el.textContent.trim().toLowerCase();
            if (text.includes('bowling') || text.includes('most wickets')) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    bowling = page.evaluate(r"""() => {
        const rows = [];
        const tables = document.querySelectorAll('table');
        for (const table of tables) {
            const trs = table.querySelectorAll('tbody tr, tr');
            for (const tr of trs) {
                const cells = Array.from(tr.querySelectorAll('td'));
                if (cells.length >= 4) {
                    rows.push(cells.map(td => td.textContent.trim()));
                }
            }
            if (rows.length > 0) break;
        }
        return rows;
    }""")

    log.info("Stats scraped: %d batting rows, %d bowling rows",
             len(batting), len(bowling))
    return {"batting": batting, "bowling": bowling}


# ------------------------------------------------------------------
# Recommendation logic
# ------------------------------------------------------------------


def build_recommendations(
    current_team: list,
    squads: dict[str, list[str]],
    stats: dict,
    today_teams: set[str],
) -> str:
    """Compare current team against scraped data and build recommendations.

    Returns a formatted string for Telegram.
    """
    lines = ["**Transfer Recommendations**\n"]

    # 1. Players in your team from today's teams
    relevant = [p for p in current_team if p.team in today_teams]
    other = [p for p in current_team if p.team not in today_teams]

    lines.append(f"Your players in today's match: {len(relevant)}")
    lines.append(f"Your players from other teams: {len(other)}\n")

    # 2. Check who's in the squads
    all_squad_players = set()
    for team, players in squads.items():
        for name in players:
            all_squad_players.add(name.lower())

    # Flag players possibly not in squad
    not_in_squad = []
    for p in relevant:
        # Fuzzy match — player names may differ slightly
        if not any(p.name.lower() in sq or sq in p.name.lower()
                   for sq in all_squad_players):
            not_in_squad.append(p)

    if not_in_squad:
        lines.append("Players possibly NOT in squad:")
        for p in not_in_squad:
            lines.append(f"  - {p.name} ({p.team}, {p.role})")
        lines.append("")

    # 3. Top performers from stats
    if stats.get("batting"):
        lines.append("Top batters this season:")
        for row in stats["batting"][:5]:
            lines.append(f"  {' | '.join(row[:5])}")
        lines.append("")

    if stats.get("bowling"):
        lines.append("Top bowlers this season:")
        for row in stats["bowling"][:5]:
            lines.append(f"  {' | '.join(row[:5])}")
        lines.append("")

    # 4. Captain recommendation — pick from relevant players
    if relevant:
        # Prefer all-rounders, then batters from the stronger team
        ar = [p for p in relevant if p.role == "AR"]
        bat = [p for p in relevant if p.role == "BAT"]
        if ar:
            lines.append(f"Captain pick: {ar[0].name} (all-rounder)")
        elif bat:
            lines.append(f"Captain pick: {bat[0].name} (batter)")
        else:
            lines.append(f"Captain pick: {relevant[0].name}")

    if not lines[-1].startswith("Captain"):
        lines.append("No captain recommendation (no relevant players)")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Recommend IPL fantasy transfers")
    parser.add_argument(
        "--date",
        help="Target date in ISO format (e.g. 2026-03-30). Defaults to today.",
    )
    args = parser.parse_args()

    target_date = args.date
    matches = get_matches_for(target_date)
    if not matches:
        print(f"No IPL match on {target_date or 'today'}.")
        return

    match_urls = get_cricbuzz_urls(target_date)
    if not match_urls:
        print("No Cricbuzz URLs for this date. Run scrape_match_urls.py first.")
        return

    today_teams = set()
    for m in matches:
        today_teams.add(m[0])
        today_teams.add(m[1])

    match_str = ", ".join(f"{t1} vs {t2}" for t1, t2 in matches)
    log.info("Target: %s (%s)", match_str, target_date or "today")

    settings = Settings()
    telegram = Telegram(settings)
    telegram.send_message(f"Gathering data for: {match_str}")

    pw, browser = create_browser(headless=False)

    try:
        # --- Scrape Cricbuzz (no login needed) ---
        cb_page = browser.new_page()
        cb_page.set_viewport_size({"width": 1280, "height": 800})

        # Scrape squads for each match
        all_squads: dict[str, list[str]] = {}
        for match in match_urls:
            squads = scrape_squads(cb_page, match["squads_url"])
            all_squads.update(squads)

        # Scrape season stats
        stats = scrape_stats(cb_page, STATS_URL)

        cb_page.close()

        # --- Read current fantasy team (needs login) ---
        login(browser, settings, telegram)
        driver = FantasyDriver(browser, telegram)

        try:
            home_info = driver.go_home()
            if not home_info["has_manage_team"]:
                telegram.send_message(
                    "Transfer window closed. Showing data only."
                )
                # Still show recommendations
                recs = build_recommendations(
                    [], all_squads, stats, today_teams
                )
                telegram.send_message(recs)
                return

            driver.go_manage_team()
            current_team = driver.get_current_team()

            team_msg = driver.format_team(current_team)
            telegram.send_message(team_msg)

            # Build and send recommendations
            recs = build_recommendations(
                current_team, all_squads, stats, today_teams
            )
            telegram.send_message(recs)

        finally:
            driver.close()

    finally:
        browser.close()
        pw.stop()


if __name__ == "__main__":
    main()
