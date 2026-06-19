"""
Scraper for Rose City Rollers — roller derby bouts
URL: https://rosecityrollers.com/schedule/
Format: Static HTML (WordPress). The schedule page is a flat sequence of cells:
          .post-block__cell--head  -> date marker ("July 25", "August 28 through August 30")
          .post-block__cell--body  -> title (.post-block-body__header), one or
                                       more .post-block-body__copy lines (time, venue),
                                       and a "Buy Tickets" link for actual bouts
        The page mixes youth summer camps and "Skatemobile" community appearances
        in with the spectator bouts. Only the ticketed bouts are real games —
        they're the only cells with a rollerderbytickets.com link — so we filter
        to those. All bouts are at The Hangar at Oaks Amusement Park (home).
Calendar: sports (roller derby)
"""

import re
from datetime import date
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_time_12h, CALENDAR_SPORTS

SOURCE = "Rose City Rollers"
URL = "https://rosecityrollers.com/schedule/"


def _parse_date(text):
    """Parse a date marker like 'July 25' or 'August 28 through August 30' to
    YYYY-MM-DD (start date), inferring the year."""
    if not text:
        return ""
    # Date ranges ("August 28 through August 30") — keep the start.
    start = re.split(r"\bthrough\b|[-–—]", text, maxsplit=1)[0].strip()
    if not re.search(r"[A-Za-z]", start):
        return ""
    today = date.today()
    if not re.search(r"\d{4}", start):
        start = f"{start} {today.year}"
    try:
        parsed = dp.parse(start, fuzzy=True).date()
        if parsed < today:
            parsed = parsed.replace(year=parsed.year + 1)
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _parse_time(copies):
    """Pull the game start time from the copy lines. Prefer an explicit
    'Game at <time>' over a 'Doors' time."""
    for line in copies:
        # "Game at 10:30am" — explicit meridiem
        m = re.search(r"game\s*(?:at)?\s*(\d{1,2}(?::\d{2})?\s*[ap]m)", line, re.I)
        if m:
            return parse_time_12h(m.group(1))
    for line in copies:
        # "Game at 7" — no meridiem; bouts are evening, so assume PM
        m = re.search(r"game\s*(?:at)?\s*(\d{1,2}(?::\d{2})?)\b(?!\s*[ap]m)", line, re.I)
        if m:
            return parse_time_12h(m.group(1) + "pm")
    for line in copies:
        m = re.search(r"(\d{1,2}(?::\d{2})?\s*[ap]m)", line, re.I)
        if m:
            return parse_time_12h(m.group(1))
    return ""


def scrape():
    resp = get_page(URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    cells = soup.select(".post-block__cell--head, .post-block__cell--body")

    events = []
    current_date = ""
    for cell in cells:
        classes = " ".join(cell.get("class") or [])
        if "head" in classes:
            current_date = cell.get_text(" ", strip=True)
            continue

        # Body cell — only real bouts have a ticketing link.
        tix = cell.find("a", href=re.compile(r"rollerderbytickets\.com"))
        if not tix:
            continue

        title_el = cell.select_one(".post-block-body__header")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        if not title:
            continue

        copies = [p.get_text(" ", strip=True) for p in cell.select(".post-block-body__copy")]
        # Last copy line is the venue; earlier line(s) hold the time.
        location = copies[-1] if copies else "The Hangar at Oaks Amusement Park"
        time_str = _parse_time(copies)

        date_str = _parse_date(current_date)
        if not date_str:
            continue

        # The "Buy Tickets" href occasionally has stray prose prepended on their
        # site ("The public URL for this event will be https://…") — extract the
        # real URL.
        m = re.search(r"https?://www\.rollerderbytickets\.com/\S+", tix.get("href", ""))
        event_url = m.group(0) if m else tix.get("href", "")

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            url=event_url,
            tags=["sports", "roller-derby"],
            calendar=CALENDAR_SPORTS,
            source=SOURCE,
        ))

    print(f"  [{SOURCE}] Found {len(events)} bouts")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
