"""
Shared helper for modular11.com-backed sports scrapers.

modular11 is the league-management platform behind USL League Two and USL W
League (and others). Each team has a server-rendered schedule widget whose
match rows are in the static HTML:

  https://www.modular11.com/league-schedule/teams/<team_id>

Each .table-content-row has columns:
  [match id] [MM/DD/YY HH:MMpm  <Venue> - <Venue>] [division]
  [<Home> <score> : <score> <Away>  (or  <Home> VS <Away>)] [Match Details]

The matchup column carries ordered team links (home first, away second) to
/league-schedule/teams/<id>, so home/away is detected by id — robust against
the team being named "Bangers FC" vs "Portland Cherry Bombs FC". Each row also
links to /match_details/<id>/... which we use as the event URL.

Times are already local (Pacific). Home games only. Calendar: sports (soccer).
"""

import re
from datetime import date
from dateutil import parser as dp
from bs4 import BeautifulSoup
from .base import get_page, make_event, CALENDAR_SPORTS

BASE = "https://www.modular11.com"
SCHEDULE_URL = BASE + "/league-schedule/teams/{team_id}"
_DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{2})\s+(\d{1,2}:\d{2}\s*[ap]m)", re.I)
_TEAM_HREF_RE = re.compile(r"/league-schedule/teams/(\d+)")


def _clean_venue(date_col_text):
    """The date column is 'MM/DD/YY HH:MMpm  <a> - <b>' — return a venue string.
    Venue is given as '<short> - <full>'; prefer the full (second) part."""
    after = _DATE_RE.sub("", date_col_text).strip(" -|")
    after = re.sub(r"\s+", " ", after).strip()
    if " - " in after:
        after = after.split(" - ", 1)[1].strip()
    return after


def fetch_home_games(team_id, source, team_short, tags):
    resp = get_page(SCHEDULE_URL.format(team_id=team_id))
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    today = date.today()
    team_id = str(team_id)
    events = []
    seen = set()

    for row in soup.select(".table-content-row"):
        row_text = row.get_text(" ", strip=True)
        m = _DATE_RE.search(row_text)
        if not m:
            continue
        try:
            dt = dp.parse(f"{m.group(1)} {m.group(2)}")
        except Exception:
            continue
        date_str = dt.strftime("%Y-%m-%d")
        if date.fromisoformat(date_str) < today:
            continue

        # Ordered, de-duped team links: first = home, second = away.
        ordered_ids, id_name = [], {}
        for a in row.find_all("a", href=_TEAM_HREF_RE):
            tid = _TEAM_HREF_RE.search(a["href"]).group(1)
            if tid not in ordered_ids:
                ordered_ids.append(tid)
            name = a.get_text(strip=True)
            if name:
                id_name[tid] = name
        if len(ordered_ids) < 2:
            continue
        home_id, away_id = ordered_ids[0], ordered_ids[1]
        if home_id != team_id:
            continue  # home games only

        away_name = id_name.get(away_id, "")
        title = f"{team_short} vs. {away_name}" if away_name else f"{team_short} Home Game"

        # Venue from the date column text.
        date_col = next((c.get_text(" ", strip=True) for c in row.find_all("div", recursive=False)
                         if _DATE_RE.search(c.get_text(" ", strip=True))), "")
        venue = _clean_venue(date_col)
        if venue and "portland" not in venue.lower() and "lents" in venue.lower():
            venue = f"{venue}, Portland, OR"
        location = venue or "Lents Field, Portland, OR"

        detail = row.find("a", href=re.compile(r"/match_details/"))
        url = BASE + detail["href"] if detail else SCHEDULE_URL.format(team_id=team_id)

        time_str = dt.strftime("%H:%M")
        key = (date_str, away_name, time_str)
        if key in seen:
            continue
        seen.add(key)

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            url=url,
            tags=list(tags),
            calendar=CALENDAR_SPORTS,
            source=source,
        ))

    events.sort(key=lambda e: (e["date"], e["time"]))
    print(f"  [{source}] Found {len(events)} home games")
    return events
