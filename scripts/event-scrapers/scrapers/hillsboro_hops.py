"""
Scraper for Hillsboro Hops (MiLB High-A, Northwest League) — home games
Source: MLB StatsAPI (public, no key):
  https://statsapi.mlb.com/api/v1/schedule?sportId=13&teamId=419&startDate=...&endDate=...
  sportId 13 = High-A; teamId 419 = Hillsboro Hops; venue = Hops Ballpark.
  games[].gameDate is UTC ISO — convert to Pacific for the correct local
  date+time. Home games only (teams.home.team.id == 419).
Calendar: sports (baseball).
"""

import sys
from datetime import date, datetime, timedelta, timezone
from dateutil import tz as dateutil_tz
from .base import make_event, CALENDAR_SPORTS

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

PACIFIC = dateutil_tz.gettz("America/Los_Angeles")

SOURCE = "Hillsboro Hops"
TEAM_ID = 419
SPORT_ID = 13  # High-A
HORIZON_DAYS = 150  # cover the season; run_all trims to its own window
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


def scrape():
    if requests is None:
        print(f"  [{SOURCE}] requests not available")
        return []

    today = date.today()
    params = {
        "sportId": SPORT_ID,
        "teamId": TEAM_ID,
        "startDate": today.isoformat(),
        "endDate": (today + timedelta(days=HORIZON_DAYS)).isoformat(),
    }
    try:
        resp = requests.get(SCHEDULE_URL, params=params, headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [{SOURCE}] fetch failed: {e}")
        return []

    events = []
    for day in data.get("dates", []):
        for g in day.get("games", []):
            home = g.get("teams", {}).get("home", {}).get("team", {})
            if home.get("id") != TEAM_ID:
                continue  # home games only

            status = g.get("status", {}).get("detailedState", "")
            if any(s in status for s in ("Cancelled", "Canceled", "Postponed")):
                continue

            game_dt_utc = g.get("gameDate", "")
            if not game_dt_utc:
                continue
            try:
                dt_utc = datetime.fromisoformat(game_dt_utc.replace("Z", "+00:00"))
                dt_pac = dt_utc.astimezone(PACIFIC)
            except ValueError:
                continue
            date_str = dt_pac.strftime("%Y-%m-%d")
            # MiLB feeds sometimes use a midnight-UTC placeholder for TBD times;
            # only emit a time when it isn't the 00:00 sentinel.
            time_str = dt_pac.strftime("%H:%M")
            if dt_utc.strftime("%H:%M") == "00:00":
                time_str = ""

            away = g.get("teams", {}).get("away", {}).get("team", {}).get("name", "")
            title = f"Hops vs. {away}" if away else "Hillsboro Hops Home Game"

            venue = g.get("venue", {}).get("name", "Hops Ballpark")
            location = f"{venue}, Hillsboro, OR"

            game_pk = g.get("gamePk")
            url = f"https://www.milb.com/gameday/{game_pk}" if game_pk else "https://www.milb.com/hillsboro/schedule"

            events.append(make_event(
                title=title,
                date=date_str,
                time=time_str,
                location=location,
                url=url,
                tags=["sports", "baseball", "hops"],
                calendar=CALENDAR_SPORTS,
                source=SOURCE,
            ))

    events.sort(key=lambda e: (e["date"], e["time"]))
    print(f"  [{SOURCE}] Found {len(events)} home games")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
