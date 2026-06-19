"""
Scraper for Rip City Remix (NBA G League, Blazers affiliate) — home games.
Via ESPN site.api. Home venue: Chiles Center (University of Portland).
Calendar: sports (basketball).
"""

from .espn_common import fetch_home_games

SOURCE = "Rip City Remix"


def scrape():
    return fetch_home_games(
        sport="basketball", league="nba-development", team_id=128019,
        source=SOURCE, team_short="Rip City Remix",
        tags=["sports", "basketball", "rip-city-remix"],
        default_venue="Chiles Center",
    )


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
