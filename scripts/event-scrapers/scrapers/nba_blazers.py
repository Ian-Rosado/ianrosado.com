"""
Scraper for Portland Trail Blazers (NBA) — home games
Source: NBA's public schedule JSON.
  Primary cdn.nba.com is Akamai bot-blocked from some networks (403), so we use
  the legacy data.nba.com mobile schedule feed, which is open:
    https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/<seasonYear>/league/00_full_schedule.json
  Structure: lscd[].mscd.g[] games with:
    gdte  -> "2026-01-05"            (game date)
    htm   -> "2026-01-05T19:00:00"   (home tip time, arena-local = Pacific for home games)
    an/ac/as -> arena name / city / state
    h/v   -> home / visitor team {ta: tricode, tc: city, tn: name}
    gid   -> game id (for the nba.com/game/<id> link)
Home games only (h.ta == 'POR'). Calendar: sports (basketball).
"""

import sys
from datetime import date, datetime
from .base import make_event, CALENDAR_SPORTS

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

SOURCE = "Portland Trail Blazers"
TEAM_TRICODE = "POR"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
SCHEDULE_URL = "https://data.nba.com/data/10s/v2015/json/mobile_teams/nba/{season}/league/00_full_schedule.json"


def _season_years():
    """NBA seasons are labelled by their start year (2025 = 2025-26 season).
    Released ~August. In/after August use the current year; before, last year.
    Try the computed season and the next one so we pick up a freshly released
    schedule near the season boundary."""
    today = date.today()
    primary = today.year if today.month >= 8 else today.year - 1
    return [primary, primary + 1]


def _fetch_season(season):
    if requests is None:
        return None
    try:
        resp = requests.get(SCHEDULE_URL.format(season=season), headers={"User-Agent": UA}, timeout=30)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as e:
        print(f"  [{SOURCE}] season {season} fetch failed: {e}")
        return None


def _parse_games(data):
    events = []
    today = date.today()
    for month in data.get("lscd", []):
        for g in month.get("mscd", {}).get("g", []):
            if g.get("h", {}).get("ta") != TEAM_TRICODE:
                continue  # home games only
            date_str = g.get("gdte", "")
            if not date_str:
                continue
            try:
                if date.fromisoformat(date_str) < today:
                    continue
            except ValueError:
                continue

            time_str = ""
            htm = g.get("htm", "")
            if "T" in htm:
                try:
                    time_str = datetime.fromisoformat(htm).strftime("%H:%M")
                except ValueError:
                    pass

            visitor = g.get("v", {})
            visitor_name = " ".join(p for p in [visitor.get("tc", ""), visitor.get("tn", "")] if p).strip()
            title = f"Trail Blazers vs. {visitor_name}" if visitor_name else "Trail Blazers Home Game"

            arena = g.get("an", "Moda Center")
            city = g.get("ac", "Portland")
            state = g.get("as", "OR")
            location = ", ".join(p for p in [arena, city, state] if p)

            gid = g.get("gid", "")
            url = f"https://www.nba.com/game/{gid}" if gid else "https://www.nba.com/blazers/schedule"

            events.append(make_event(
                title=title,
                date=date_str,
                time=time_str,
                location=location,
                url=url,
                tags=["sports", "basketball", "trail-blazers"],
                calendar=CALENDAR_SPORTS,
                source=SOURCE,
            ))
    return events


def scrape():
    seen = set()
    events = []
    for season in _season_years():
        data = _fetch_season(season)
        if not data:
            continue
        for e in _parse_games(data):
            key = (e["title"], e["date"])
            if key not in seen:
                seen.add(key)
                events.append(e)

    events.sort(key=lambda e: (e["date"], e["time"]))
    print(f"  [{SOURCE}] Found {len(events)} home games")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
