"""
Scraper for Do PDX
URL: https://dopdx.com/
Format: Static HTML with Schema.org Event markup (DoStuff Media platform).
        Event cards: div.ds-listing[itemprop=event]
          - itemprop="name"                    -> title
          - itemprop="startDate" content=ISO   -> date + time
          - itemprop="location" > name         -> venue
          - data-permalink                     -> relative URL
          - CSS class ds-event-category-{cat}  -> category/tags
        Paginates via ?offset=N (25 per page). Scrapes 3 pages (75 events);
        run_all.py's date filter trims to the configured window.
        Skips events tagged "eugene" (out of area).
Calendar: music for music category, events for everything else
"""

import re
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, CALENDAR_EVENTS, CALENDAR_MUSIC

SOURCE = "Do PDX"
BASE_URL = "https://dopdx.com"
PAGES = 3  # 25 events each


def _parse_events(soup):
    events = []
    for card in soup.find_all("div", class_="ds-listing"):
        # Title
        name_el = card.find(itemprop="name")
        title = name_el.get_text(strip=True) if name_el else ""
        if not title:
            continue

        # Date + time from ISO startDate
        start_el = card.find(itemprop="startDate")
        date_str = ""
        time_str = ""
        if start_el and start_el.get("content"):
            try:
                dt = dp.parse(start_el["content"])
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M")
            except Exception:
                pass
        if not date_str:
            continue

        # Venue: nested location > name
        loc_scope = card.find(itemprop="location")
        location = ""
        if loc_scope:
            loc_name = loc_scope.find(itemprop="name")
            location = loc_name.get_text(strip=True) if loc_name else loc_scope.get_text(strip=True)

        # URL from data-permalink
        permalink = card.get("data-permalink", "")
        event_url = BASE_URL + permalink if permalink.startswith("/") else permalink

        # Category from CSS class: ds-event-category-{cat}
        categories = [
            c.replace("ds-event-category-", "")
            for c in (card.get("class") or [])
            if c.startswith("ds-event-category-")
        ]

        # Skip out-of-area events
        if "eugene" in categories:
            continue

        # Assign calendar
        calendar = CALENDAR_MUSIC if "music" in categories else CALENDAR_EVENTS

        tags = categories if categories else ["events"]

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            url=event_url,
            tags=tags,
            calendar=calendar,
            source=SOURCE,
        ))

    return events


def scrape():
    all_events = []
    seen = set()

    for page in range(PAGES):
        offset = page * 25
        url = f"{BASE_URL}/?offset={offset}" if offset else BASE_URL + "/"
        resp = get_page(url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")
        events = _parse_events(soup)
        if not events:
            break

        for e in events:
            key = (e["title"].lower()[:50], e["date"])
            if key not in seen:
                seen.add(key)
                all_events.append(e)

    print(f"  [{SOURCE}] Found {len(all_events)} events")
    return all_events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
