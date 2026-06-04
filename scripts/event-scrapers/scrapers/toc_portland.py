"""
Scraper for TOC Portland - Free Concerts
URL: https://www.tocportland.org/free-concerts
Format: Static HTML, simple text-based recurring schedule.
        Extracts upcoming Wednesday concert dates.
Calendar: music (free concerts)
"""

import re
from datetime import date, timedelta
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, CALENDAR_MUSIC

SOURCE = "TOC Portland"
URL = "https://www.tocportland.org/free-concerts"


def _next_wednesdays(n=8):
    """Return the next n Wednesday dates from today."""
    today = date.today()
    # Days until Wednesday (weekday 2)
    days_ahead = (2 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    start = today + timedelta(days=days_ahead)
    return [start + timedelta(weeks=i) for i in range(n)]


def scrape():
    resp = get_page(URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    body_text = soup.get_text(" ", strip=True)

    # Extract any specific dated events mentioned on the page
    # Pattern: "September 10th and 24th at 5:30 PM" etc.
    specific_dates = []
    date_matches = re.finditer(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        body_text,
        re.I
    )
    for m in date_matches:
        try:
            dt = dp.parse(m.group(0), fuzzy=True)
            specific_dates.append(dt.strftime("%Y-%m-%d"))
        except Exception:
            pass

    # Extract times
    time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM))", body_text, re.I)
    time_str = ""
    end_time_str = ""
    if time_match:
        from .base import parse_time_12h
        time_str = parse_time_12h(time_match.group(1))

    # Also check for lunchtime concerts
    lunchtime_match = re.search(r"noon|12:00\s*(?:pm)?", body_text, re.I)

    # Check season bounds
    season_match = re.search(
        r"(June|July|August|September|October)\s+(?:through|to|-)\s+"
        r"(June|July|August|September|October|November)",
        body_text, re.I
    )

    # If we found specific dates, use those
    if specific_dates:
        for d in specific_dates:
            events.append(make_event(
                title="TOC Portland Free Outdoor Concert",
                date=d,
                time=time_str,
                location="TOC Portland",
                cost="Free",
                url=URL,
                tags=["music", "free", "outdoor", "concert"],
                calendar=CALENDAR_MUSIC,
                source=SOURCE,
            ))
    else:
        # Fall back to generating upcoming Wednesday dates
        for wed in _next_wednesdays(8):
            events.append(make_event(
                title="TOC Portland Free Outdoor Concert (Wednesday)",
                date=wed.strftime("%Y-%m-%d"),
                time=time_str or "17:30",
                location="TOC Portland",
                cost="Free",
                url=URL,
                tags=["music", "free", "outdoor", "concert", "recurring"],
                calendar=CALENDAR_MUSIC,
                source=SOURCE,
            ))

    # Lunchtime concerts (1st and 3rd Wednesdays)
    if lunchtime_match:
        wednesdays = _next_wednesdays(8)
        # 1st and 3rd Wednesday of each month
        first_third = []
        seen_months = {}
        for w in wednesdays:
            month_key = (w.year, w.month)
            seen_months.setdefault(month_key, []).append(w)
        for dates_in_month in seen_months.values():
            if len(dates_in_month) >= 1:
                first_third.append(dates_in_month[0])
            if len(dates_in_month) >= 3:
                first_third.append(dates_in_month[2])

        for w in first_third:
            events.append(make_event(
                title="TOC Portland Lunchtime Concert",
                date=w.strftime("%Y-%m-%d"),
                time="12:00",
                location="TOC Portland",
                cost="Free",
                url=URL,
                tags=["music", "free", "lunchtime", "concert", "recurring"],
                calendar=CALENDAR_MUSIC,
                source=SOURCE,
            ))

    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
