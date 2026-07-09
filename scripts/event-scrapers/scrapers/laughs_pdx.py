"""
Scraper for Laughs PDX - Portland Comedy Events
URL: https://www.laughspdx.com/events/
Format: Static HTML, WordPress The Events Calendar plugin (tribe-* classes).
Calendar: events (comedy)
"""

import re
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_cost, multiday_end_date, CALENDAR_COMEDY

SOURCE = "Laughs PDX"
URL = "https://www.laughspdx.com/events/"
BASE = "https://www.laughspdx.com"


def scrape():
    resp = get_page(URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    # The Events Calendar plugin structure
    articles = soup.select(
        "article.tribe-events-calendar-list__event, "
        "article[class*='tribe_events'], article[class*='type-tribe_events'], "
        ".tribe-events-list article, .tribe-event"
    )

    for article in articles:
        # Title
        title_el = article.select_one(
            ".tribe-event-url, h3 a, h2 a, "
            ".tribe-events-list-event-title a, "
            ".tribe-events-calendar-list__event-title a"
        )
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url = title_el.get("href", URL)

        # Date/time
        date_str = ""
        time_str = ""
        end_time_str = ""
        dt = None
        dt_end = None

        start_el = article.select_one(
            "abbr.tribe-events-abbr[title], .tribe-event-date-start, "
            "time[class*='start'], .tribe-events-start-datetime"
        )
        if start_el:
            raw = start_el.get("title", "") or start_el.get_text(strip=True)
            try:
                dt = dp.parse(raw, fuzzy=True)
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else ""
            except Exception:
                date_str = raw

        end_el = article.select_one(
            ".tribe-event-date-end, time[class*='end'], .tribe-events-end-datetime"
        )
        if end_el:
            raw_end = end_el.get("title", "") or end_el.get_text(strip=True)
            try:
                dt_end = dp.parse(raw_end, fuzzy=True)
                end_time_str = dt_end.strftime("%H:%M") if (dt_end.hour or dt_end.minute) else ""
            except Exception:
                pass

        # Multi-day events span date..end_date as an all-day event.
        end_date_str = multiday_end_date(dt, dt_end)

        # Location
        loc_el = article.select_one(".tribe-venue, address, [class*='venue']")
        location = loc_el.get_text(" ", strip=True) if loc_el else ""

        # Cost
        cost_el = article.select_one(".tribe-events-cost, [class*='cost']")
        cost = parse_cost(cost_el.get_text(strip=True) if cost_el else "")

        tags = ["comedy"]

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            end_time=end_time_str,
            end_date=end_date_str,
            location=location,
            cost=cost,
            url=url,
            tags=tags,
            calendar=CALENDAR_COMEDY,
            source=SOURCE,
        ))

    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
