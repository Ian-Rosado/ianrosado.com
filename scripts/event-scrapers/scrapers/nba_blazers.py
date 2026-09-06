"""
Scraper for Portland Trail Blazers (NBA) — home games.

Formerly read the legacy data.nba.com mobile schedule feed, but that endpoint
now 403s for the current season (2026-27), so the scraper quietly returned 0.
Switched to ESPN's site.api via the shared espn_common helper — the same source
the other basketball teams (Rip City Remix, Portland Fire) already use.
Blazers ESPN team id: 22. Home venue: Moda Center. Calendar: sports (basketball).
"""

from .espn_common import fetch_home_games

SOURCE = "Portland Trail Blazers"


def scrape():
    return fetch_home_games(
        sport="basketball", league="nba", team_id=22,
        source=SOURCE, team_short="Trail Blazers",
        tags=["sports", "basketball", "trail-blazers"],
        default_venue="Moda Center",
    )


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
