"""
Scraper for Portland Winterhawks (WHL junior hockey) — home games.
Source: HockeyTech LeagueStat feed that powers whl.ca (not on ESPN).
  https://lscluster.hockeytech.com/feed/?feed=modulekit&view=schedule&client_code=whl&...
  The team_id is null in the teams feed, but each schedule row carries
  home_team_code ("POR"), so we pull the full season schedule and filter on
  that. GameDateISO8601 is a clean Pacific-offset timestamp.

Seasons come and go (regular season, playoffs, pre-season). We only pull
seasons whose end_date is today or later, so in the offseason this returns
nothing until the next schedule is published — same as the other pro teams.

Home games only (home_team_code == 'POR'). Calendar: sports (hockey).
"""

from datetime import date
from dateutil import parser as dp
from dateutil import tz as dateutil_tz
from .base import make_event, CALENDAR_SPORTS

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

PACIFIC = dateutil_tz.gettz("America/Los_Angeles")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
FEED = "https://lscluster.hockeytech.com/feed/"
KEY = "41b145a848f4bd67"  # public WHL LeagueStat client key
CLIENT = "whl"
TEAM_CODE = "POR"

SOURCE = "Portland Winterhawks"


def _feed(view, **extra):
    params = {"feed": "modulekit", "view": view, "key": KEY,
              "client_code": CLIENT, "fmt": "json", "lang": "en"}
    params.update(extra)
    resp = requests.get(FEED, params=params, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("SiteKit", {})


def scrape():
    if requests is None:
        print(f"  [{SOURCE}] requests not available")
        return []

    today = date.today()
    try:
        seasons = _feed("seasons").get("Seasons", [])
    except Exception as e:
        print(f"  [{SOURCE}] seasons fetch failed: {e}")
        return []

    # Only seasons still ongoing or in the future are worth scanning.
    active_season_ids = []
    for s in seasons:
        end = s.get("end_date", "")
        try:
            if end and date.fromisoformat(end) >= today:
                active_season_ids.append(s.get("season_id"))
        except ValueError:
            continue

    events = []
    seen = set()
    for season_id in active_season_ids:
        try:
            sched = _feed("schedule", season_id=season_id).get("Schedule", [])
        except Exception as e:
            print(f"  [{SOURCE}] schedule fetch failed (season {season_id}): {e}")
            continue
        for g in sched:
            if g.get("home_team_code") != TEAM_CODE:
                continue  # home games only
            game_id = g.get("game_id")
            if game_id in seen:
                continue

            iso = g.get("GameDateISO8601", "")
            date_str = time_str = ""
            if iso:
                try:
                    dt = dp.isoparse(iso).astimezone(PACIFIC)
                    date_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M")
                except (ValueError, OverflowError):
                    pass
            if not date_str:
                date_str = g.get("date_played", "")
            if not date_str:
                continue
            try:
                if date.fromisoformat(date_str) < today:
                    continue
            except ValueError:
                continue

            seen.add(game_id)
            visitor = g.get("visiting_team_name", "")
            title = f"Winterhawks vs. {visitor}" if visitor else "Winterhawks Home Game"
            location = g.get("venue_name", "Veterans Memorial Coliseum - Portland, OR")
            url = g.get("tickets_url") or "https://winterhawks.com/"

            events.append(make_event(
                title=title,
                date=date_str,
                time=time_str,
                location=location,
                url=url,
                tags=["sports", "hockey", "winterhawks"],
                calendar=CALENDAR_SPORTS,
                source=SOURCE,
            ))

    events.sort(key=lambda e: (e["date"], e["time"]))
    print(f"  [{SOURCE}] Found {len(events)} home games")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
