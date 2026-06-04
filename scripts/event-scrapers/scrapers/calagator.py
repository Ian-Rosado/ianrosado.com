"""
Scraper for Calagator - Portland Tech/Community Events
URL: https://calagator.org/events/
Format: Static HTML, semantic markup with <h3> headings and <time> elements.
Calendar: events (tech/community)
"""

import re
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, CALENDAR_EVENTS

SOURCE = "Calagator"
URL = "https://calagator.org/events/"
BASE = "https://calagator.org"


def scrape():
    resp = get_page(URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    # Calagator uses a list of events, each in an <li> or <div class="vevent">
    # with an h3/h4 for title and <abbr class="dtstart"> or <time> for date.
    vevent_els = soup.select(".vevent, li.event, article.event")
    if not vevent_els:
        # Fallback: grab all h3 links within the main content
        main = soup.select_one("main, #main, .events-listing, #content")
        if main:
            vevent_els = main.find_all(["li", "article", "div"], recursive=False)

    for el in vevent_els:
        title_el = el.select_one("h3 a, h2 a, h4 a, a.summary, .summary a")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        if url and not url.startswith("http"):
            url = BASE + url

        # Date/time from <abbr class="dtstart"> or <time>
        date_str = ""
        time_str = ""
        end_time_str = ""

        start_el = el.select_one("abbr.dtstart, time.dtstart, [class*='dtstart']")
        if start_el:
            raw = start_el.get("title", "") or start_el.get_text(strip=True)
            try:
                dt = dp.parse(raw, fuzzy=True)
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M") if (dt.hour or dt.minute) else ""
            except Exception:
                date_str = raw

        end_el = el.select_one("abbr.dtend, time.dtend, [class*='dtend']")
        if end_el:
            raw_end = end_el.get("title", "") or end_el.get_text(strip=True)
            try:
                dt_end = dp.parse(raw_end, fuzzy=True)
                end_time_str = dt_end.strftime("%H:%M") if (dt_end.hour or dt_end.minute) else ""
            except Exception:
                pass

        # Location
        loc_el = el.select_one(".location, [class*='venue'], address")
        location = loc_el.get_text(strip=True) if loc_el else ""

        tags = ["community", "tech"]

        if not title:
            continue

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            end_time=end_time_str,
            location=location,
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
