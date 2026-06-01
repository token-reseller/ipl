"""One-off script to scrape all IPL 2026 match URLs from Cricbuzz.

Opens the series matches page with Playwright (headed mode +
persistent context to bypass Akamai bot detection) and extracts
match links. Prints Python dict entries for cricbuzz.py.

Usage:
    uv run python scripts/scrape_match_urls.py
"""

import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ipl_fantasy.auth import create_browser

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

MATCHES_URL = (
    "https://www.cricbuzz.com/cricket-series/9241/"
    "indian-premier-league-2026/matches"
)

# Short forms used in Cricbuzz URL slugs → standard abbreviations
TEAM_ABBREV = {
    "srh": "SRH", "rcb": "RCB", "mi": "MI", "csk": "CSK",
    "kkr": "KKR", "dc": "DC", "rr": "RR", "gt": "GT",
    "pbks": "PBKS", "lsg": "LSG",
}


def normalize(name: str) -> str:
    return TEAM_ABBREV.get(name.lower().strip(), name.upper().strip())


def main():
    # Headed mode + persistent context needed to bypass Akamai CDN
    pw, browser = create_browser(headless=False)
    page = browser.new_page()
    page.set_viewport_size({"width": 1280, "height": 800})

    log.info("Loading %s", MATCHES_URL)
    page.goto(MATCHES_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)

    # Extract IPL 2026 match links only
    raw = page.evaluate(r"""() => {
        const links = document.querySelectorAll('a[href*="indian-premier-league-2026"]');
        const results = [];
        const seen = new Set();
        for (const a of links) {
            const href = a.getAttribute('href') || '';
            if (!href.includes('/live-cricket-scores/') && !href.includes('/cricket-scores/')) continue;
            if (seen.has(href)) continue;
            seen.add(href);
            const container = a.closest('div');
            results.push({
                href: href,
                context: container ? container.textContent.trim().substring(0, 300) : '',
            });
        }
        return results;
    }""")

    log.info("Found %d IPL match links", len(raw))
    print("\n# --- Paste this into cricbuzz.py MATCHES dict ---\n")

    for entry in raw:
        href = entry["href"]
        ctx = entry["context"]

        m = re.search(r"/(?:cricket-scores|live-cricket-scores)/(\d+)/(.+)", href)
        if not m:
            continue

        match_id = m.group(1)
        slug = m.group(2)

        teams_m = re.match(r"(\w+)-vs-(\w+)-", slug)
        if not teams_m:
            continue

        team1 = normalize(teams_m.group(1))
        team2 = normalize(teams_m.group(2))

        num_m = re.search(r"(\d+)(?:st|nd|rd|th)-match", slug)
        match_num = int(num_m.group(1)) if num_m else None

        base = "https://www.cricbuzz.com"
        match_url = f"{base}{href}"
        squads_url = f"{base}/cricket-match-squads/{match_id}/{slug}"

        # Extract date from context text
        date_m = re.search(
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"(\d{1,2})",
            ctx,
        )
        date_str = ""
        if date_m:
            months = {
                "January": "01", "February": "02", "March": "03", "April": "04",
                "May": "05", "June": "06", "July": "07", "August": "08",
                "September": "09", "October": "10", "November": "11", "December": "12",
            }
            mo = months.get(date_m.group(1), "01")
            day = date_m.group(2).zfill(2)
            date_str = f"2026-{mo}-{day}"

        num_str = f", \"match_num\": {match_num}" if match_num else ""
        print(f'    # Match {match_num or "?"}: {team1} vs {team2}')
        print(f'    "{date_str}": [{{')
        print(f'        "team1": "{team1}",')
        print(f'        "team2": "{team2}"{num_str},')
        print(f'        "match_url": "{match_url}",')
        print(f'        "squads_url": "{squads_url}",')
        print('    }],')
        print()

    page.close()
    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()
