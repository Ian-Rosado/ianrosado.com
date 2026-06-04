"""
Scraper for Queer Social Club - Portland Events
URL: https://queersocialclub.com/events-portland
Format: Static HTML (Squarespace eventlist), confirmed class names:
  .eventlist-event          -- one per event
  .eventlist-title-link     -- <a> title + href
  <time datetime="YYYY-MM-DD">  -- date element
  <time> "9:00 AM"          -- start time (narrow no-break space before AM/PM)
  <time> "5:00 PM"          -- end time
  .eventlist-meta-address   -- location
Calendar: events (LGBTQ+/community)
"""

import re
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_cost, CALENDAR_EVENTS

SOURCE = "Queer Social Club"
URL = "https://queersocialclub.com/events-portland"
BASE = "https://queersocialclub.com"

# Narrow no-break space (U+202F) used by Squarespace between digit and AM/PM
NARROW_NBSP = " "


def scrape():
    resp = get_page(URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.content, "lxml")
    events = []

    cards = soup.select(".eventlist-event--upcoming, .eventlist-event")

    for card in cards:
        classes = " ".join(card.get("class") or [])
        if "eventlist-event--past" in classes:
            continue

        # Title + URL
        title_el = card.select_one(".eventlist-title-link")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        if url and not url.startswith("http"):
            url = BASE + url

        # Date and times from <time> elements
        # Squarespace pattern per card:
        #   time[datetime="YYYY-MM-DD"] -- date
        #   time (text = "9:00 AM")     -- start time
        #   time (text = "5:00 PM")     -- end time
        date_str = ""
        time_str = ""
        end_time_str = ""

        # All <time> elements share the same datetime attr on Squarespace.
        # Use text content to distinguish: check for AM/PM first, then date.
        for t in card.select("time"):
            dt_attr = t.get("datetime", "")
            raw = t.get_text(strip=True).replace(NARROW_NBSP, " ")

            if re.search(r"\d{1,2}:\d{2}\s*(AM|PM)", raw, re.I):
                # Time element — parse as start or end
                try:
                    parsed = dp.parse("2000-01-01 " + raw, fuzzy=True)
                    if not time_str:
                        time_str = parsed.strftime("%H:%M")
                    else:
                        end_time_str = parsed.strftime("%H:%M")
                except Exception:
                    pass
            elif re.match(r"^\d{4}-\d{2}-\d{2}$", dt_attr) and not date_str:
                date_str = dt_attr
            elif not date_str and re.search(
                r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", raw, re.I
            ):
                try:
                    parsed = dp.parse(raw, fuzzy=True)
                    date_str = parsed.strftime("%Y-%m-%d")
                except Exception:
                    pass

        # Location
        loc_el = card.select_one(".eventlist-meta-address")
        location = " ".join(loc_el.get_text(" ", strip=True).split()) if loc_el else ""
        # Strip "(map)" suffix Squarespace adds
        location = re.sub(r"\s*\(map\)\s*$", "", location).strip()

        tags = ["lgbtq", "community", "queer"]

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
    import json, sys
    result = scrape()
    sys.stdout.buffer.write(json.dumps(result[:3], indent=2, ensure_ascii=True).encode())
