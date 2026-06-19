"""
Scraper for Portland Timbers (MLS) — home matches. Via ESPN site.api (the
official timbers.com schedule is a JS SPA with an image-based view). Home
venue: Providence Park. Calendar: sports (soccer).
"""

from .espn_common import fetch_home_games

SOURCE = "Portland Timbers"


def scrape():
    return fetch_home_games(
        sport="soccer", league="usa.1", team_id=9723,
        source=SOURCE, team_short="Timbers",
        tags=["sports", "soccer", "timbers"],
        default_venue="Providence Park",
    )


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
