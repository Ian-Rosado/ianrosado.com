"""
Scraper for PDX After Dark

Crawls every venue page (/venues/<slug>) and regex-extracts ALL upcoming event
refs embedded in the page's raw HTML. The site's "Events This Week / This
Month / All" tabs are server-rendered into the page source in full, but only
the active tab ("This Week" by default) is a real DOM card — the rest of the
data is there but not in a card-shaped element, so a DOM/selector-based scrape
(the old approach) only ever saw a handful of events per venue. Regex over the
raw response text recovers the full set — weeks to months out — with no extra
requests per venue.

(The site also dropped its old /areas/<neighborhood> pages — all 19 now 404 —
so don't bring those back. /bands-with-upcoming-shows and /this-week are
strict subsets of what the venue crawl finds and are no longer scraped.)

Each unique event is then visited once to pull:
  - title + venue, from <title>Event Title | Venue | Portland | PDX After Dark</title>
  - date/time, from the Unix-ms timestamp at the end of the event URL slug
  - the real outbound venue/ticketing link, from an anchor literally labeled
    "Event Link" (falls back to the PDX After Dark page when absent — plenty
    of bar shows have no official site)
  URL pattern: /event/venue-slug/YYYY/MM/DD/event-name-YYYY-MM-DD-{unix_ms}

Calendar: music (nightlife/concerts)
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date, timedelta
from bs4 import BeautifulSoup
from dateutil import tz as dateutil_tz
from .base import get_page, make_event, CALENDAR_MUSIC

PACIFIC = dateutil_tz.gettz("America/Los_Angeles")

SOURCE = "PDX After Dark"
BASE = "https://www.pdxafterdark.com"
VENUES_INDEX_URL = f"{BASE}/venues"

# How far ahead to resolve full event details. The venue pages list events up
# to a year out, but fetching all of them isn't worth the request volume —
# this gives generous margin over run_all.py's usual 30-day window.
WINDOW_DAYS = 45

EVENT_HREF_RE = re.compile(r"/event/[a-z0-9\-]+/\d{4}/\d{2}/\d{2}/[a-z0-9\-]+")


def _parse_datetime_from_timestamp(href):
    """Extract date + time from the Unix ms timestamp at the end of the URL slug.
    e.g. /event/als-den/2026/06/05/als-den-...-1780709400000
    Returns (date_str, time_str) in Pacific time, or ("", "") if not found.
    """
    m = re.search(r"-(\d{10,13})$", href)
    if not m:
        return "", ""
    raw = int(m.group(1))
    ts_seconds = raw / 1000 if raw > 1e10 else raw
    try:
        dt_utc = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
        dt_pacific = dt_utc.astimezone(PACIFIC)
        return dt_pacific.strftime("%Y-%m-%d"), dt_pacific.strftime("%H:%M")
    except Exception:
        return "", ""


def _get_venue_slugs():
    resp = get_page(VENUES_INDEX_URL)
    if not resp:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    slugs = set()
    for a in soup.find_all("a", href=True):
        m = re.match(r"^/venues/([a-z0-9\-]+)$", a["href"])
        if m:
            slugs.add(m.group(1))
    return sorted(slugs)


def _venue_event_hrefs(slug):
    """Raw-text regex, not a DOM selector — see module docstring for why."""
    resp = get_page(f"{BASE}/venues/{slug}")
    if not resp:
        return set()
    return set(EVENT_HREF_RE.findall(resp.text))


def _fetch_event_detail(href):
    """Fetch one event's detail page and build its event dict. Returns None on
    a 404 (venue pages sometimes list events that have since been pulled) or
    if the title can't be parsed."""
    date_str, time_str = _parse_datetime_from_timestamp(href)
    if not date_str:
        return None

    resp = get_page(f"{BASE}{href}")
    if not resp:
        return None
    soup = BeautifulSoup(resp.text, "lxml")

    title_tag = soup.title.get_text() if soup.title else ""
    parts = [p.strip() for p in title_tag.split(" | ")]
    title = parts[0] if parts else ""
    if not title:
        return None
    location = parts[1] if len(parts) > 1 else ""

    event_link = ""
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True) == "Event Link":
            event_link = a["href"]
            break

    return make_event(
        title=title,
        date=date_str,
        time=time_str,
        location=location,
        url=event_link or f"{BASE}{href}",
        tags=["nightlife", "music"],
        calendar=CALENDAR_MUSIC,
        source=SOURCE,
    )


def scrape():
    slugs = _get_venue_slugs()
    if not slugs:
        print(f"  [{SOURCE}] No venue slugs found — site structure may have changed")
        return []

    # Collect every event href across all venues — the href itself dedupes
    # (a show can legitimately appear on more than one venue page).
    all_hrefs = set()
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(_venue_event_hrefs, slug) for slug in slugs]
        for future in as_completed(futures):
            try:
                all_hrefs |= future.result()
            except Exception:
                pass

    today = date.today()
    cutoff = today + timedelta(days=WINDOW_DAYS)
    in_window = []
    for href in all_hrefs:
        date_str, _ = _parse_datetime_from_timestamp(href)
        if date_str:
            try:
                if today <= date.fromisoformat(date_str) <= cutoff:
                    in_window.append(href)
            except ValueError:
                pass

    events = []
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(_fetch_event_detail, href) for href in in_window]
        for future in as_completed(futures):
            try:
                ev = future.result()
                if ev:
                    events.append(ev)
            except Exception:
                pass

    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
