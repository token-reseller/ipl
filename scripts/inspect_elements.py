"""One-off script: inspect manage team page for playing status selectors.

Logs in, navigates to manage team, and dumps detailed HTML of player
elements to Telegram — looking for:
  1. "playing / not playing" indicators (green/red dots, status text)
  2. "plays after X matches" indicators
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ipl_fantasy.auth import create_browser, login
from ipl_fantasy.config import Settings
from ipl_fantasy.driver import FantasyDriver, ROLE_TABS
from ipl_fantasy.notify import Telegram


def inspect():
    settings = Settings()
    telegram = Telegram(settings)
    telegram.send_message("Starting element inspection...")

    pw, browser = create_browser()

    try:
        login(browser, settings, telegram)
        driver = FantasyDriver(browser, telegram)

        try:
            home_info = driver.go_home()
            if not home_info["has_manage_team"]:
                telegram.send_message("No 'Manage Team' button. Transfer window may be closed.")
                return

            driver.go_manage_team()

            # For each role tab, dump the first few player elements in detail
            for role in ROLE_TABS:
                driver._click_role_tab(role)
                driver.page.wait_for_timeout(1500)

                # Grab detailed HTML and text from all player <li> elements
                results = driver.page.evaluate(r"""(role) => {
                    const allLis = document.querySelectorAll('li');
                    const players = [];

                    for (const li of allLis) {
                        // Only look at player-like elements (have player name class)
                        const nameEl = li.querySelector('.m11c-plyrSel__name, [class*="plyr"], [class*="player"]');
                        if (!nameEl) continue;

                        const name = li.querySelector('.m11c-plyrSel__name > span:first-child');
                        const playerName = name ? name.textContent.trim() : '(unknown)';
                        const isSelected = li.classList.contains('m11c-remove');

                        // Collect ALL classes on li and child elements
                        const allClasses = new Set();
                        allClasses.add(li.className);
                        li.querySelectorAll('*').forEach(el => {
                            if (el.className && typeof el.className === 'string') {
                                allClasses.add(el.className);
                            }
                        });

                        // Look for any dot/status indicator elements
                        const dots = [];
                        li.querySelectorAll('[class*="dot"], [class*="status"], [class*="play"], [class*="avail"], [class*="lock"], [class*="badge"], [class*="indicator"], [class*="icon"], [class*="circle"], [class*="match"], span[style*="background"], div[style*="background"]').forEach(el => {
                            dots.push({
                                tag: el.tagName,
                                className: el.className,
                                text: el.textContent.trim().substring(0, 100),
                                style: el.getAttribute('style') || '',
                            });
                        });

                        // Look for "plays after" or "match" text anywhere
                        const fullText = li.textContent;
                        const playsAfterMatch = fullText.match(/plays?\s*after\s*\d+/i);
                        const matchText = fullText.match(/\d+\s*match/i);

                        players.push({
                            playerName,
                            isSelected,
                            liClasses: li.className,
                            dotElements: dots,
                            playsAfterText: playsAfterMatch ? playsAfterMatch[0] : null,
                            matchText: matchText ? matchText[0] : null,
                            fullText: fullText.trim().substring(0, 300),
                            allClasses: [...allClasses].join(' | '),
                        });

                        if (players.length >= 6) break;  // first 6 per tab is enough
                    }
                    return players;
                }""", role)

                # Send results to Telegram
                msg_lines = [f"=== {role} TAB ({len(results)} players sampled) ===\n"]
                for p in results:
                    msg_lines.append(f"{'[SELECTED] ' if p['isSelected'] else ''}{p['playerName']}")
                    msg_lines.append(f"  li classes: {p['liClasses']}")
                    if p['dotElements']:
                        for d in p['dotElements']:
                            msg_lines.append(f"  DOT: <{d['tag']}> class=\"{d['className']}\" text=\"{d['text']}\" style=\"{d['style']}\"")
                    else:
                        msg_lines.append("  DOT: (none found)")
                    if p['playsAfterText']:
                        msg_lines.append(f"  PLAYS AFTER: {p['playsAfterText']}")
                    if p['matchText']:
                        msg_lines.append(f"  MATCH TEXT: {p['matchText']}")
                    msg_lines.append(f"  Full text: {p['fullText'][:200]}")
                    msg_lines.append("")

                telegram.send_message("\n".join(msg_lines))

            # Also dump raw outerHTML of one selected + one available player
            driver.inspect_player_dots()

            # Take a final screenshot
            driver._screenshot("inspect_final")
            telegram.send_message("Inspection complete. Check messages above for selectors.")

        finally:
            driver.close()
    except Exception as e:
        telegram.send_message(f"Inspection failed: {e}")
        raise
    finally:
        browser.close()
        pw.stop()


if __name__ == "__main__":
    inspect()
