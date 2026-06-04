"""
Scraper for Willamette Week Events Calendar (CitySpark-powered)
URL: https://www.wweek.com/getbusy/calendar/events/#/
Format: JS-rendered (Vue/CitySpark). Requires Playwright.
        Event cards: div[class*="csEvWrap"]
          - data-date attr          -> ISO date
          - a[href]                 -> #/details/slug/PId/datetime (relative hash URL)
          - div.csOneLine span      -> event title
          - div.cityVenue span[0]   -> venue name
          - div.csIconRow           -> time text e.g. "8:00 am"
Calendar: events (general) or music based on card classes
"""

import re
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import make_event, parse_time_12h, CALENDAR_EVENTS, CALENDAR_MUSIC

SOURCE = "Willamette Week"
URL = "https://www.wweek.com/getbusy/calendar/events/#/"
BASE_URL = "https://www.wweek.com/getbusy/calendar/events/"

WAIT_MS = 5000  # ms to wait for JS rendering


def _get_html():
    """Fetch rendered HTML using Playwright."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, timeout=30000)
        page.wait_for_timeout(WAIT_MS)
        html = page.content()
        browser.close()
    return html


def scrape():
    try:
        html = _get_html()
    except Exception as e:
        print(f"  [{SOURCE}] Playwright error: {e}")
        return []

    soup = BeautifulSoup(html, "lxml")
    events = []

    cards = soup.select("[class*='csEvWrap']")
    for card in cards:
        # Title
        title_el = card.select_one(".csOneLine span")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        # Date from data-date attr
        date_str = ""
        raw_date = card.get("data-date", "")
        if raw_date:
            try:
                date_str = dp.parse(raw_date).strftime("%Y-%m-%d")
            except Exception:
                pass
        if not date_str:
            continue

        # Time from csIconRow text e.g. "8:00 am" or "8:00 am - 10:00 pm"
        time_str = ""
        icon_row = card.select_one("[class*='csIconRow']")
        if icon_row:
            row_text = icon_row.get_text(" ", strip=True)
            time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))", row_text, re.I)
            if time_match:
                parsed = parse_time_12h(time_match.group(1))
                time_str = "" if parsed == "00:00" else parsed  # midnight = no time set

        # Venue
        venue_spans = card.select(".cityVenue span")
        location = venue_spans[0].get_text(strip=True) if venue_spans else ""
        # Filter " | " separator span
        location = location if location != "|" else ""

        # URL: hash fragment → make absolute
        link = card.select_one("a[href]")
        href = link.get("href", "") if link else ""
        event_url = BASE_URL + href.lstrip("#/") if href.startswith("#") else href

        # Calendar: check card classes for music indicators
        card_classes = " ".join(card.get("class", []))
        calendar = CALENDAR_MUSIC if "music" in card_classes.lower() else CALENDAR_EVENTS

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            url=event_url,
            tags=["portland"],
            calendar=calendar,
            source=SOURCE,
        ))

    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
