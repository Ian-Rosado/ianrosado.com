"""
Scraper for Portland Bangers FC (USL League Two) — home games. Their own
Squarespace page has no structured schedule, but the USL League Two data
platform (modular11) does: team 4928. Home venue: Lents Field.
Calendar: sports (soccer).
"""

from .modular11_common import fetch_home_games

SOURCE = "Portland Bangers"


def scrape():
    return fetch_home_games(
        team_id=4928, source=SOURCE, team_short="Bangers",
        tags=["sports", "soccer", "bangers"],
    )


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
