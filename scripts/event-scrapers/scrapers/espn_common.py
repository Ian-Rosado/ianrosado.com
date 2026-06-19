"""
Shared helper for ESPN-backed sports scrapers.

ESPN's public site.api returns clean per-team schedule JSON for the major
leagues with no key and no aggressive bot-blocking (unlike the leagues' own
cdn/data hosts, several of which 403 from some networks). One endpoint shape
covers NBA, WNBA, MLS, NWSL, NHL, etc.:

  https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{id}/schedule

Each event:
  event.date                      -> UTC ISO (convert to Pacific)
  competitions[0].competitors[]   -> {homeAway, team:{id, displayName}}
  competitions[0].venue.fullName  -> arena/stadium  (+ .address.city/.state)
  competitions[0].status / event.status -> type.name (STATUS_SCHEDULED, _POSTPONED, _CANCELED)
  event.links[0].href             -> ESPN game page

This helper returns home games only, as make_event() dicts.
"""

from datetime import date, datetime
from dateutil import parser as dp
from dateutil import tz as dateutil_tz
from .base import make_event, CALENDAR_SPORTS

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

PACIFIC = dateutil_tz.gettz("America/Los_Angeles")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
# ?fixture=true returns UPCOMING fixtures. Without it, soccer endpoints return
# only past results (basketball returns the full season either way), so always
# pass it for consistent upcoming-game coverage across leagues.
BASE = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{team_id}/schedule?fixture=true"

SKIP_STATUSES = ("POSTPONED", "CANCELED", "CANCELLED")


def _status_name(event, comp):
    for obj in (comp, event):
        name = (obj.get("status") or {}).get("type", {}).get("name", "")
        if name:
            return name
    return ""


def fetch_home_games(sport, league, team_id, source, team_short, tags, default_venue=""):
    """Return upcoming home games for an ESPN team as make_event() dicts.

    sport/league: ESPN path parts (e.g. 'basketball'/'wnba', 'soccer'/'usa.1').
    team_id:      ESPN numeric team id (as str or int).
    team_short:   short name for titles, e.g. 'Fire' -> 'Fire vs. <away>'.
    tags:         base tag list, e.g. ['sports', 'basketball', 'fire'].
    """
    if requests is None:
        print(f"  [{source}] requests not available")
        return []

    url = BASE.format(sport=sport, league=league, team_id=team_id)
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [{source}] fetch failed: {e}")
        return []

    today = date.today()
    team_id = str(team_id)
    events = []
    for ev in data.get("events", []):
        comps = ev.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        competitors = comp.get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or str(home.get("team", {}).get("id")) != team_id:
            continue  # home games only

        status = _status_name(ev, comp)
        if any(s in status.upper() for s in SKIP_STATUSES):
            continue

        raw_date = ev.get("date", "")
        if not raw_date:
            continue
        try:
            dt_pac = dp.isoparse(raw_date).astimezone(PACIFIC)
        except (ValueError, OverflowError):
            continue
        date_str = dt_pac.strftime("%Y-%m-%d")
        if date.fromisoformat(date_str) < today:
            continue
        time_str = dt_pac.strftime("%H:%M")

        away_name = away.get("team", {}).get("displayName", "") if away else ""
        title = f"{team_short} vs. {away_name}" if away_name else f"{team_short} Home Game"

        venue = comp.get("venue", {})
        venue_name = venue.get("fullName", "") or default_venue
        addr = venue.get("address", {}) or {}
        location = ", ".join(p for p in [venue_name, addr.get("city", ""), addr.get("state", "")] if p)

        links = ev.get("links", [])
        url_link = next((l.get("href") for l in links if l.get("href", "").startswith("http")), "")

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            url=url_link,
            tags=list(tags),
            calendar=CALENDAR_SPORTS,
            source=source,
        ))

    events.sort(key=lambda e: (e["date"], e["time"]))
    print(f"  [{source}] Found {len(events)} home games")
    return events
