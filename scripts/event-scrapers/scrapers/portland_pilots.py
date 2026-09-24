"""
Scraper for the Portland Pilots (University of Portland) — home games.

University of Portland is a Division I program; its home games are real local
sporting events, so they belong on the Portland Sports calendar alongside the
pro teams. Pulled from ESPN's site.api via the shared espn_common helper, one
call per team. Home games only; offseason returns 0.

Teams / ESPN ids:
  - Women's Soccer   soccer / usa.ncaa.w.1        / 20338  (Merlo Field)
  - Men's Soccer     soccer / usa.ncaa.m.1        / 5614   (Merlo Field)
  - Volleyball (W)   volleyball / womens-college-volleyball / 2501  (Chiles Center)
  - Women's Basketball  basketball / womens-college-basketball / 2501 (Chiles Center)
  - Men's Basketball    basketball / mens-college-basketball   / 2501 (Chiles Center)

Titled "Portland Pilots <Sport>" (not "University of Portland …") so these
authoritative listings are distinct from the messier generic-source ones, which
dedup against them at commit. Calendar: sports.
"""

from .espn_common import fetch_home_games

SOURCE = "Portland Pilots"

# (sport, league, team_id, short name, extra tags)
TEAMS = [
    ("soccer",     "usa.ncaa.w.1",              20338, "Portland Pilots Women's Soccer",     ["soccer"]),
    ("soccer",     "usa.ncaa.m.1",              5614,  "Portland Pilots Men's Soccer",       ["soccer"]),
    ("volleyball", "womens-college-volleyball", 2501,  "Portland Pilots Volleyball",         ["volleyball"]),
    ("basketball", "womens-college-basketball", 2501,  "Portland Pilots Women's Basketball", ["basketball"]),
    ("basketball", "mens-college-basketball",   2501,  "Portland Pilots Men's Basketball",   ["basketball"]),
]


def scrape():
    events = []
    for sport, league, team_id, short, extra in TEAMS:
        try:
            events += fetch_home_games(
                sport=sport, league=league, team_id=team_id,
                source=SOURCE, team_short=short,
                tags=["sports", "college", "university of portland"] + extra,
            )
        except Exception as e:
            print(f"  [{SOURCE}] {short} failed: {e}")
    events.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    print(f"  [{SOURCE}] Found {len(events)} home games")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
