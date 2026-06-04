"""
Scraper for PDX Parent
URL: https://pdxparent.com/events/
Format: Static HTML, WordPress/The Events Calendar plugin.
        Events in <article> tags with tribe-* classes.
Calendar: events (family-friendly)
"""

import re
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_cost, CALENDAR_EVENTS

SOURCE = "PDX Parent"
URL = "https://pdxparent.com/events/"
HEADERS_OVERRIDE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


def scrape():
    import requests as _req
    try:
        resp = _req.get(URL, headers=HEADERS_OVERRIDE, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [ERROR] {SOURCE}: {e}")
        return []

    soup = BeautifulSoup(resp.content, "lxml")
    events = []

    articles = soup.select("article[class*='tribe_events'], article[class*='type-tribe']")
    if not articles:
        # Fallback to any article with an h3 link
        articles = soup.select("article")

    for article in articles:
        title_el = article.select_one("h3 a, h2 a, .tribe-event-url")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url = title_el.get("href", URL)

        # Date/time
        date_str = ""
        time_str = ""
        end_time_str = ""

        start_el = article.select_one(
            "abbr.tribe-events-abbr, .tribe-event-date-start, time[class*='start']"
        )
        if start_el:
            raw = start_el.get("title", "") or start_el.get_text(strip=True)
            try:
                dt = dp.parse(raw, fuzzy=True)
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else ""
            except Exception:
                date_str = raw

        end_el = article.select_one(".tribe-event-date-end, time[class*='end']")
        if end_el:
            raw_end = end_el.get("title", "") or end_el.get_text(strip=True)
            try:
                dt_end = dp.parse(raw_end, fuzzy=True)
                end_time_str = dt_end.strftime("%H:%M") if (dt_end.hour or dt_end.minute) else ""
            except Exception:
                pass

        # Location
        loc_el = article.select_one(".tribe-venue, address, [class*='venue']")
        location = loc_el.get_text(" ", strip=True) if loc_el else ""

        # Cost
        cost_el = article.select_one(".tribe-events-cost, [class*='cost']")
        cost = parse_cost(cost_el.get_text(strip=True) if cost_el else "")

        # Tags
        tags = ["family-friendly"]
        tag_els = article.select("[rel='tag'], .tribe-event-tags a")
        tags += [t.get_text(strip=True).lower() for t in tag_els]

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            end_time=end_time_str,
            location=location,
            cost=cost,
            url=url,
            tags=tags,
            calendar=CALENDAR_EVENTS,
            source=SOURCE,
        ))

    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
