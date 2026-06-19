"""
Scraper for Portland Cherry Bombs FC (USL W League) — home games. Their own
Squarespace page has no structured schedule, but the USL W data platform
(modular11) does: team 8112. Home venue: Lents Field.
Calendar: sports (soccer).
"""

from .modular11_common import fetch_home_games

SOURCE = "Portland Cherry Bombs"


def scrape():
    return fetch_home_games(
        team_id=8112, source=SOURCE, team_short="Cherry Bombs",
        tags=["sports", "soccer", "cherry-bombs"],
    )


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
