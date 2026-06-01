"""Cricbuzz URL registry for IPL 2026 matches.

Maps each match date to Cricbuzz URLs for scraping match data,
squads, and stats. Populated via scripts/scrape_match_urls.py.

URL patterns:
  - Match:  https://www.cricbuzz.com/live-cricket-scores/<id>/<slug>
  - Squads: https://www.cricbuzz.com/cricket-match-squads/<id>/<slug>
  - Stats:  https://www.cricbuzz.com/cricket-series/9241/.../stats
"""

# Season-level URLs (don't change per match)
SERIES_ID = "9241"
STATS_URL = (
    "https://www.cricbuzz.com/cricket-series/9241/"
    "indian-premier-league-2026/stats"
)
POINTS_TABLE_URL = (
    "https://www.cricbuzz.com/cricket-series/9241/"
    "indian-premier-league-2026/points-table"
)
SQUADS_URL = (
    "https://www.cricbuzz.com/cricket-series/9241/"
    "indian-premier-league-2026/squads"
)

_CB = "https://www.cricbuzz.com"
_L = "/live-cricket-scores"
_S = "/cricket-match-squads"
_IPL = "indian-premier-league-2026"


def _m(mid, slug, team1, team2, num):
    """Build a match entry dict."""
    return {
        "team1": team1,
        "team2": team2,
        "match_num": num,
        "match_url": f"{_CB}{_L}/{mid}/{slug}",
        "squads_url": f"{_CB}{_S}/{mid}/{slug}",
    }


# Per-match URLs — keyed by ISO date.
# Double-header days have multiple entries.
# fmt: off
MATCHES: dict[str, list[dict]] = {
    "2026-03-28": [_m("149618", f"srh-vs-rcb-1st-match-{_IPL}", "SRH", "RCB", 1)],
    "2026-03-29": [_m("149629", f"kkr-vs-mi-2nd-match-{_IPL}", "KKR", "MI", 2)],
    "2026-03-30": [_m("149640", f"rr-vs-csk-3rd-match-{_IPL}", "RR", "CSK", 3)],
    "2026-03-31": [_m("149651", f"pbks-vs-gt-4th-match-{_IPL}", "PBKS", "GT", 4)],
    "2026-04-01": [_m("149662", f"lsg-vs-dc-5th-match-{_IPL}", "LSG", "DC", 5)],
    "2026-04-02": [_m("149673", f"kkr-vs-srh-6th-match-{_IPL}", "KKR", "SRH", 6)],
    "2026-04-03": [_m("149684", f"csk-vs-pbks-7th-match-{_IPL}", "CSK", "PBKS", 7)],
    "2026-04-04": [
        _m("149695", f"dc-vs-mi-8th-match-{_IPL}", "DC", "MI", 8),
        _m("149699", f"gt-vs-rr-9th-match-{_IPL}", "GT", "RR", 9),
    ],
    "2026-04-05": [
        _m("149710", f"srh-vs-lsg-10th-match-{_IPL}", "SRH", "LSG", 10),
        _m("149721", f"rcb-vs-csk-11th-match-{_IPL}", "RCB", "CSK", 11),
    ],
    "2026-04-06": [_m("149732", f"kkr-vs-pbks-12th-match-{_IPL}", "KKR", "PBKS", 12)],
    "2026-04-07": [_m("149743", f"rr-vs-mi-13th-match-{_IPL}", "RR", "MI", 13)],
    "2026-04-08": [_m("149746", f"dc-vs-gt-14th-match-{_IPL}", "DC", "GT", 14)],
    "2026-04-09": [_m("149757", f"kkr-vs-lsg-15th-match-{_IPL}", "KKR", "LSG", 15)],
    "2026-04-10": [_m("149768", f"rr-vs-rcb-16th-match-{_IPL}", "RR", "RCB", 16)],
    "2026-04-11": [
        _m("149779", f"pbks-vs-srh-17th-match-{_IPL}", "PBKS", "SRH", 17),
        _m("149790", f"csk-vs-dc-18th-match-{_IPL}", "CSK", "DC", 18),
    ],
    "2026-04-12": [
        _m("149801", f"lsg-vs-gt-19th-match-{_IPL}", "LSG", "GT", 19),
        _m("149812", f"mi-vs-rcb-20th-match-{_IPL}", "MI", "RCB", 20),
    ],
    "2026-04-13": [_m("151752", f"srh-vs-rr-21st-match-{_IPL}", "SRH", "RR", 21)],
    "2026-04-14": [_m("151763", f"csk-vs-kkr-22nd-match-{_IPL}", "CSK", "KKR", 22)],
    "2026-04-15": [_m("151774", f"rcb-vs-lsg-23rd-match-{_IPL}", "RCB", "LSG", 23)],
    "2026-04-16": [_m("151785", f"mi-vs-pbks-24th-match-{_IPL}", "MI", "PBKS", 24)],
    "2026-04-17": [_m("151796", f"gt-vs-kkr-25th-match-{_IPL}", "GT", "KKR", 25)],
    "2026-04-18": [
        _m("151807", f"rcb-vs-dc-26th-match-{_IPL}", "RCB", "DC", 26),
        _m("151818", f"srh-vs-csk-27th-match-{_IPL}", "SRH", "CSK", 27),
    ],
    "2026-04-19": [
        _m("151829", f"kkr-vs-rr-28th-match-{_IPL}", "KKR", "RR", 28),
        _m("151840", f"pbks-vs-lsg-29th-match-{_IPL}", "PBKS", "LSG", 29),
    ],
    "2026-04-20": [_m("151845", f"gt-vs-mi-30th-match-{_IPL}", "GT", "MI", 30)],
    "2026-04-21": [_m("151856", f"srh-vs-dc-31st-match-{_IPL}", "SRH", "DC", 31)],
    "2026-04-22": [_m("151867", f"lsg-vs-rr-32nd-match-{_IPL}", "LSG", "RR", 32)],
    "2026-04-23": [_m("151878", f"mi-vs-csk-33rd-match-{_IPL}", "MI", "CSK", 33)],
    "2026-04-24": [_m("151889", f"rcb-vs-gt-34th-match-{_IPL}", "RCB", "GT", 34)],
    "2026-04-25": [
        _m("151891", f"dc-vs-pbks-35th-match-{_IPL}", "DC", "PBKS", 35),
        _m("151902", f"rr-vs-srh-36th-match-{_IPL}", "RR", "SRH", 36),
    ],
    "2026-04-26": [
        _m("151913", f"gt-vs-csk-37th-match-{_IPL}", "GT", "CSK", 37),
        _m("151924", f"lsg-vs-kkr-38th-match-{_IPL}", "LSG", "KKR", 38),
    ],
    "2026-04-27": [_m("151935", f"dc-vs-rcb-39th-match-{_IPL}", "DC", "RCB", 39)],
    "2026-04-28": [_m("151943", f"pbks-vs-rr-40th-match-{_IPL}", "PBKS", "RR", 40)],
    "2026-04-29": [_m("151954", f"mi-vs-srh-41st-match-{_IPL}", "MI", "SRH", 41)],
    "2026-04-30": [_m("151965", f"gt-vs-rcb-42nd-match-{_IPL}", "GT", "RCB", 42)],
    "2026-05-01": [_m("151976", f"rr-vs-dc-43rd-match-{_IPL}", "RR", "DC", 43)],
    "2026-05-02": [_m("151987", f"csk-vs-mi-44th-match-{_IPL}", "CSK", "MI", 44)],
    "2026-05-03": [
        _m("151998", f"srh-vs-kkr-45th-match-{_IPL}", "SRH", "KKR", 45),
        _m("152009", f"gt-vs-pbks-46th-match-{_IPL}", "GT", "PBKS", 46),
    ],
    "2026-05-04": [
        _m("152020", f"mi-vs-lsg-47th-match-{_IPL}", "MI", "LSG", 47),
    ],
    "2026-05-05": [_m("152031", f"dc-vs-csk-48th-match-{_IPL}", "DC", "CSK", 48)],
    "2026-05-06": [_m("152042", f"srh-vs-pbks-49th-match-{_IPL}", "SRH", "PBKS", 49)],
    "2026-05-07": [_m("152053", f"lsg-vs-rcb-50th-match-{_IPL}", "LSG", "RCB", 50)],
    "2026-05-08": [_m("152064", f"dc-vs-kkr-51st-match-{_IPL}", "DC", "KKR", 51)],
    "2026-05-09": [_m("152075", f"rr-vs-gt-52nd-match-{_IPL}", "RR", "GT", 52)],
    "2026-05-10": [
        _m("152086", f"csk-vs-lsg-53rd-match-{_IPL}", "CSK", "LSG", 53),
        _m("152097", f"rcb-vs-mi-54th-match-{_IPL}", "RCB", "MI", 54),
    ],
    "2026-05-11": [_m("152108", f"pbks-vs-dc-55th-match-{_IPL}", "PBKS", "DC", 55)],
    "2026-05-12": [_m("152119", f"gt-vs-srh-56th-match-{_IPL}", "GT", "SRH", 56)],
    "2026-05-13": [_m("152130", f"rcb-vs-kkr-57th-match-{_IPL}", "RCB", "KKR", 57)],
    "2026-05-14": [_m("152141", f"pbks-vs-mi-58th-match-{_IPL}", "PBKS", "MI", 58)],
    "2026-05-15": [_m("152152", f"lsg-vs-csk-59th-match-{_IPL}", "LSG", "CSK", 59)],
    "2026-05-16": [_m("152163", f"kkr-vs-gt-60th-match-{_IPL}", "KKR", "GT", 60)],
    "2026-05-17": [
        _m("152174", f"pbks-vs-rcb-61st-match-{_IPL}", "PBKS", "RCB", 61),
        _m("152185", f"dc-vs-rr-62nd-match-{_IPL}", "DC", "RR", 62),
    ],
    "2026-05-18": [_m("152196", f"csk-vs-srh-63rd-match-{_IPL}", "CSK", "SRH", 63)],
    "2026-05-19": [_m("152207", f"rr-vs-lsg-64th-match-{_IPL}", "RR", "LSG", 64)],
    "2026-05-20": [_m("152218", f"kkr-vs-mi-65th-match-{_IPL}", "KKR", "MI", 65)],
    "2026-05-21": [_m("152229", f"csk-vs-gt-66th-match-{_IPL}", "CSK", "GT", 66)],
    "2026-05-22": [_m("152240", f"srh-vs-rcb-67th-match-{_IPL}", "SRH", "RCB", 67)],
    "2026-05-23": [_m("152241", f"lsg-vs-pbks-68th-match-{_IPL}", "LSG", "PBKS", 68)],
    "2026-05-24": [
        _m("152252", f"mi-vs-rr-69th-match-{_IPL}", "MI", "RR", 69),
        _m("152263", f"kkr-vs-dc-70th-match-{_IPL}", "KKR", "DC", 70),
    ],
}
# fmt: on
