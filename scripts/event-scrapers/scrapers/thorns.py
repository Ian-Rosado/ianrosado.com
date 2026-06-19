"""
Scraper for Portland Thorns FC (NWSL) — home matches. Via ESPN site.api (the
official thorns.com schedule is a JS SPA). Home venue: Providence Park.
Calendar: sports (soccer).
"""

from .espn_common import fetch_home_games

SOURCE = "Portland Thorns"


def scrape():
    return fetch_home_games(
        sport="soccer", league="usa.nwsl", team_id=15362,
        source=SOURCE, team_short="Thorns",
        tags=["sports", "soccer", "thorns"],
        default_venue="Providence Park",
    )


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
