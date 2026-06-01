"""Quick script to set captain and vice-captain without full interactive flow."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ipl_fantasy.auth import create_browser, login
from ipl_fantasy.config import Settings
from ipl_fantasy.driver import FantasyDriver
from ipl_fantasy.notify import Telegram

CAPTAIN = "Iyer"
VICE_CAPTAIN = "Chahal"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    settings = Settings()
    telegram = Telegram(settings)
    telegram.send_message("Setting captain/VC...")

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

            players = driver.get_current_team()
            if not players:
                telegram.send_message("Could not read team.")
                return

            team_msg = driver.format_team(players)
            telegram.send_message(team_msg)

            changes = []

            if driver.set_captain(CAPTAIN):
                changes.append(f"Captain: {CAPTAIN}")

            if driver.set_vice_captain(VICE_CAPTAIN):
                changes.append(f"Vice-Captain: {VICE_CAPTAIN}")

            if changes:
                driver.save_team()
                summary = "Captain/VC changes:\n" + "\n".join(f"- {c}" for c in changes)
            else:
                summary = "No captain/VC changes were made."

            telegram.send_message(summary)
            driver._screenshot("captains_final")
        finally:
            driver.close()
    except Exception:
        logging.exception("Failed")
        telegram.send_message("Captain/VC script failed. Check logs.")
    finally:
        browser.close()
        pw.stop()


if __name__ == "__main__":
    main()
