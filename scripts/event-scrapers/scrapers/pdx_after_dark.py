"""
Scraper for PDX After Dark
Sources (fetched in parallel, deduplicated by event URL):
  1. /bands-with-upcoming-shows  — bands with registered pages (~2 weeks ahead)
     Cards: article[class*="BandEventCard"]
       - p[class*="BandEventCardDate"]        -> "Sun, May 31, 2026, 7:00 PM"
       - h4[class*="BandEventCardEventTitle"] -> full event title
       - p[class*="BandEventCardVenue"]       -> "atVenue Name"
  2. /areas/<slug> (19 neighborhood pages)  — all venue events including DJs, comedy, etc.
     Cards: article[class*="EventCard"]
       - div[class*="EventCardTitle"]  -> event title
       - div[class*="EventCardVenue"]  -> venue name
       - div[class*="EventCardTime"]   -> "Today 11am", "Fri 9pm", etc.
  URL pattern: /event/venue-slug/YYYY/MM/DD/event-name-YYYY-MM-DD-{unix_ms}
Calendar: music (nightlife/concerts)
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from dateutil import parser as dp
from dateutil import tz as dateutil_tz
from .base import get_page, make_event, parse_time_12h, CALENDAR_MUSIC

PACIFIC = dateutil_tz.gettz("America/Los_Angeles")

SOURCE = "PDX After Dark"
BASE = "https://www.pdxafterdark.com"

BANDS_URL = f"{BASE}/bands-with-upcoming-shows"
AREA_SLUGS = [
    "82nd", "alberta", "belmont", "burnside", "division", "downtown",
    "forest-grove", "foster", "goose-hollow", "hawthorne", "hollywood",
    "mississippi", "nob-hill", "pearl-district", "sellwood", "southwest",
    "st-johns", "troutdale", "vancouver",
]


def _parse_date_from_href(href):
    m = re.search(r"/event/[^/]+/(\d{4})/(\d{2})/(\d{2})/", href)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


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


def _scrape_bands_page():
    """Scrape /bands-with-upcoming-shows — BandEventCard structure."""
    resp = get_page(BANDS_URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    for article in soup.find_all("article", class_=re.compile(r"BandEventCard")):
        link = article.find("a", class_=re.compile(r"BandEventCardImageLink"))
        if not link:
            continue
        href = link.get("href", "")
        if not href:
            continue

        full_url = BASE + href if href.startswith("/") else href

        # Timestamp in URL is most reliable source for date+time
        date_str, time_str = _parse_datetime_from_timestamp(href)

        # Fallback: parse from card date element
        if not date_str:
            date_el = article.find(class_=re.compile(r"BandEventCardDate"))
            if date_el:
                try:
                    dt = dp.parse(date_el.get_text(strip=True), fuzzy=True)
                    date_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M")
                except Exception:
                    pass

        title_el = article.find(class_=re.compile(r"BandEventCardEventTitle"))
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        venue_el = article.find(class_=re.compile(r"BandEventCardVenue"))
        location = ""
        if venue_el:
            location = re.sub(r"^at\s*", "", venue_el.get_text(strip=True), flags=re.I)

        if not date_str:
            continue

        events.append((href, make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            url=full_url,
            tags=["nightlife", "music"],
            calendar=CALENDAR_MUSIC,
            source=SOURCE,
        )))

    return events


def _scrape_area_page(slug):
    """Scrape /areas/<slug> — EventCard structure."""
    resp = get_page(f"{BASE}/areas/{slug}")
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    for article in soup.find_all("article", class_=re.compile(r"EventCard")):
        link = article.find("a", class_=re.compile(r"EventCardOverlayLink"))
        if not link:
            continue
        href = link.get("href", "")
        if not href:
            continue

        full_url = BASE + href if href.startswith("/") else href

        # Timestamp in URL is most reliable source for date+time
        date_str, time_str = _parse_datetime_from_timestamp(href)

        # Fallback: date from URL path, time from card label
        if not date_str:
            date_str = _parse_date_from_href(href)
        if not time_str:
            time_div = article.find(class_=re.compile(r"EventCardTime"))
            if time_div:
                m = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))", time_div.get_text(strip=True), re.I)
                if m:
                    time_str = parse_time_12h(m.group(1))

        title_div = article.find(class_=re.compile(r"EventCardTitle"))
        title = title_div.get_text(strip=True) if title_div else ""
        if not title:
            continue

        venue_div = article.find(class_=re.compile(r"EventCardVenue"))
        location = venue_div.get_text(strip=True) if venue_div else ""

        if not date_str:
            continue

        events.append((href, make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            url=full_url,
            tags=["nightlife", "music"],
            calendar=CALENDAR_MUSIC,
            source=SOURCE,
        )))

    return events


def scrape():
    seen_hrefs = set()
    all_events = []

    # Build list of fetch tasks: bands page + all area pages
    tasks = [("bands", None)] + [("area", slug) for slug in AREA_SLUGS]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for kind, slug in tasks:
            if kind == "bands":
                futures[executor.submit(_scrape_bands_page)] = "bands"
            else:
                futures[executor.submit(_scrape_area_page, slug)] = slug

        for future in as_completed(futures):
            try:
                for href, event in future.result():
                    if href not in seen_hrefs:
                        seen_hrefs.add(href)
                        all_events.append(event)
            except Exception:
                pass

    print(f"  [{SOURCE}] Found {len(all_events)} events")
    return all_events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
