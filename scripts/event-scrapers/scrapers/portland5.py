"""
Scraper for Portland'5 Centers for the Arts (portland5.com)
URL: https://www.portland5.com/events
Format: Static HTML (Drupal). The /events listing paginates (?page=0,1,2,…) in
        CHRONOLOGICAL order, 10 cards per page. Each `.teaser--event` card gives
        the title, venue (Schnitzer / Keller / Newmark / Winningstad / Main St),
        and a /event/<slug> link — but NOT the date. The date lives on the
        detail page in `time.event-hero__date` as free text, e.g.
          "Wednesday, July 29, 2026 5:00 to 7:00 PM"   (single day + times)
          "August 1 to 15, 2026"                       (multi-day run, all-day)
          "Friday, September 25, 2026 7:00 PM"          (single day, start only)
        Because the list is chronological, we paginate + fetch detail dates only
        until a page's events pass a near-term horizon, then stop.
Calendar: events (mixed-genre venues); "Music on Main" free series → music
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from dateutil import parser as dp
from bs4 import BeautifulSoup
from .base import get_page, make_event, parse_time_12h, CALENDAR_EVENTS, CALENDAR_MUSIC

SOURCE = "Portland'5"
BASE = "https://www.portland5.com"
LIST_URL = BASE + "/events?page={}"

MAX_PAGES = 15          # safety cap (listing runs many months out)
HORIZON_DAYS = 120      # stop paginating once a page starts beyond this
DETAIL_WORKERS = 10

_MONTHS = ("January|February|March|April|May|June|July|August|September|"
           "October|November|December")


def _parse_date(text: str):
    """Parse a Portland'5 event-hero date string into
    (date, time, end_time, end_date). Any part may be '' if absent/unparseable."""
    text = (text or "").strip()
    ym = re.search(r"\b(20\d\d)\b", text)
    if not ym:
        return "", "", "", ""
    year = ym.group(1)
    date_part = text[:ym.end()].strip().rstrip(",").strip()
    time_part = text[ym.end():].strip()

    # Multi-day date RANGE (the "to" sits in the date part, before the year):
    # "August 1 to 15, 2026" or "September 30 to October 2, 2026".
    if " to " in date_part:
        rng = re.search(rf"({_MONTHS})\s+(\d{{1,2}})\s+to\s+(?:({_MONTHS})\s+)?(\d{{1,2}})",
                        date_part)
        if rng:
            m1, d1, m2, d2 = rng.group(1), rng.group(2), rng.group(3) or rng.group(1), rng.group(4)
            try:
                sd = dp.parse(f"{m1} {d1}, {year}").date()
                ed = dp.parse(f"{m2} {d2}, {year}").date()
                return sd.isoformat(), "", "", (ed.isoformat() if ed > sd else "")
            except (ValueError, OverflowError):
                return "", "", "", ""

    # Single day.
    try:
        sd = dp.parse(date_part, fuzzy=True).date()
    except (ValueError, OverflowError):
        return "", "", "", ""

    start_t = end_t = ""
    if time_part:
        ampm = re.search(r"(am|pm)", time_part, re.I)
        suffix = ampm.group(1) if ampm else ""
        if " to " in time_part:  # "5:00 to 7:00 PM" — suffix applies to both ends
            a, b = time_part.split(" to ", 1)
            if suffix and not re.search(r"(am|pm)", a, re.I):
                a = f"{a.strip()} {suffix}"
            start_t, end_t = parse_time_12h(a), parse_time_12h(b)
        else:
            start_t = parse_time_12h(time_part)
    return sd.isoformat(), start_t, end_t, ""


def _list_cards(page: int):
    """Return [(title, venue, detail_url)] for one listing page."""
    resp = get_page(LIST_URL.format(page))
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    cards = []
    for c in soup.select(".teaser--event"):
        a = c.select_one('a[href^="/event/"]')
        if not a:
            continue
        title_el = c.select_one(".teaser__title") or a
        venue_el = c.select_one(".teaser__venue")
        cards.append((
            title_el.get_text(" ", strip=True),
            venue_el.get_text(" ", strip=True) if venue_el else "",
            BASE + a["href"].split("?")[0],
        ))
    return cards


def _fetch_detail_date(url: str):
    """Fetch an event detail page and return its parsed date tuple."""
    resp = get_page(url)
    if not resp:
        return "", "", "", ""
    tel = BeautifulSoup(resp.text, "lxml").select_one("time.event-hero__date")
    return _parse_date(tel.get_text(" ", strip=True) if tel else "")


def scrape():
    horizon = date.today() + timedelta(days=HORIZON_DAYS)
    today = date.today()
    events = []
    seen = set()

    for page in range(MAX_PAGES):
        cards = [c for c in _list_cards(page) if c[2] not in seen]
        if not cards:
            break  # empty page or the pager wrapped to already-seen events
        for c in cards:
            seen.add(c[2])

        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as ex:
            dates = list(ex.map(_fetch_detail_date, [c[2] for c in cards]))

        page_starts = []
        for (title, venue, url), (d, t, et, ed) in zip(cards, dates):
            if not d:
                continue
            page_starts.append(date.fromisoformat(d))
            # drop events whose whole run is already in the past
            end_iso = ed or d
            if date.fromisoformat(end_iso) < today:
                continue
            is_mom = "music on main" in title.lower()
            events.append(make_event(
                title=title,
                date=d,
                time=t,
                end_time=et,
                end_date=ed,
                location=f"{venue}, Portland, OR" if venue else "Portland, OR",
                cost="Free" if is_mom else "",
                url=url,
                tags=["music"] if is_mom else [],
                calendar=CALENDAR_MUSIC if is_mom else CALENDAR_EVENTS,
                source=SOURCE,
            ))

        # Chronological listing → once a whole page starts past the horizon, stop.
        if page_starts and min(page_starts) > horizon:
            break

    events.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
