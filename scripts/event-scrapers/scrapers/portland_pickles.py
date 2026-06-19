"""
Scraper for Portland Pickles (West Coast League summer baseball) — home games.
The Pickles' own site is a Squarespace page whose schedule is just an uploaded
image, but the WCL's stats host (wclstats.com, a PrestoSports site) publishes a
full structured schedule:
  https://wclstats.com/sports/bsb/2026/schedule
Per-game cards carry:
  .team-name                              -> the two teams (home = Portland Pickles)
  span 'Walker Stadium' (.venue)          -> home games are at Walker Stadium
  aria-label "View <Team> schedule, <Month Day>"  -> the date
  .status                                 -> "7:15 PM PDT" (upcoming) or "Final ..." (past)
Home games only (venue == Walker Stadium). The Pickles occasionally play under
alter-ego brands (Portland Rosebuds/Gherkins) on theme nights — those are still
Pickles home games at Walker, so the venue filter keeps them.
Calendar: sports (baseball).
"""

import re
from datetime import date
from dateutil import parser as dp
from bs4 import BeautifulSoup
from .base import get_page, make_event, parse_time_12h, CALENDAR_SPORTS

SOURCE = "Portland Pickles"
HOME_VENUE = "Walker Stadium"
SCHEDULE_URL = "https://wclstats.com/sports/bsb/{year}/schedule"
TEAM_PAGE = "https://www.portlandpicklesbaseball.com/2026-season-schedule"

_ARIA_DATE_RE = re.compile(r"schedule,\s*([A-Za-z]+\.?\s+\d{1,2})", re.I)


def _card_for(venue_span):
    """Walk up from a venue span to the game card that also holds the
    aria-label date elements and the .team-name spans."""
    node = venue_span
    for _ in range(12):
        node = node.parent
        if node is None:
            return None
        if node.select(".team-name") and node.find(attrs={"aria-label": _ARIA_DATE_RE}):
            return node
    return None


def scrape():
    year = date.today().year
    resp = get_page(SCHEDULE_URL.format(year=year))
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    today = date.today()
    events = []
    seen = set()

    venue_spans = [s for s in soup.find_all("span") if s.get_text(strip=True) == HOME_VENUE]
    for vs in venue_spans:
        card = _card_for(vs)
        if not card:
            continue

        # Date from any aria-label on the card ("... schedule, June 23")
        date_str = ""
        for el in card.find_all(attrs={"aria-label": _ARIA_DATE_RE}):
            m = _ARIA_DATE_RE.search(el.get("aria-label", ""))
            if m:
                try:
                    parsed = dp.parse(f"{m.group(1)} {year}", fuzzy=True).date()
                    # Summer league; if a parsed date looks far in the past, roll forward.
                    if (today - parsed).days > 180:
                        parsed = parsed.replace(year=year + 1)
                    date_str = parsed.strftime("%Y-%m-%d")
                except Exception:
                    pass
                break
        if not date_str or date.fromisoformat(date_str) < today:
            continue

        teams = [t.get_text(strip=True) for t in card.select(".team-name")]
        opponent = next((t for t in teams if t != "Portland Pickles"), "")

        status = ""
        st_el = card.select_one(".status")
        if st_el:
            status = st_el.get_text(" ", strip=True)
        time_str = ""
        tm = re.search(r"(\d{1,2}(?::\d{2})?\s*[ap]m)", status, re.I)
        if tm:
            time_str = parse_time_12h(tm.group(1))

        key = (date_str, opponent, time_str)
        if key in seen:
            continue
        seen.add(key)

        title = f"Pickles vs. {opponent}" if opponent else "Portland Pickles Home Game"
        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            location="Walker Stadium, Portland, OR",
            url=TEAM_PAGE,
            tags=["sports", "baseball", "pickles"],
            calendar=CALENDAR_SPORTS,
            source=SOURCE,
        ))

    events.sort(key=lambda e: (e["date"], e["time"]))
    print(f"  [{SOURCE}] Found {len(events)} home games")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
