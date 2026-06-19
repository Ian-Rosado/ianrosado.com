"""
Scraper for Portland Fire (WNBA) — home games. Via ESPN site.api (the WNBA's
own cdn/data hosts 403 or 404 from some networks). Home venue: Moda Center.
Calendar: sports (basketball).
"""

from .espn_common import fetch_home_games

SOURCE = "Portland Fire"


def scrape():
    return fetch_home_games(
        sport="basketball", league="wnba", team_id=132052,
        source=SOURCE, team_short="Fire",
        tags=["sports", "basketball", "fire"],
        default_venue="Moda Center",
    )


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
