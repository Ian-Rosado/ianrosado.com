"""
Scraper for Flyer Escape (flyerescape.dad)
URL: https://flyerescape.dad/
Format: Static HTML, show listings with image flyers + text.
        Structure: date headings (h4/h5) followed by event text paragraphs.
Calendar: music
"""

import re
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_cost, parse_time_12h, CALENDAR_MUSIC

SOURCE = "Flyer Escape"
URL = "https://flyerescape.dad/"
BASE = "https://flyerescape.dad"


def scrape():
    resp = get_page(URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    # The page has date headings (h4/h5) followed by show entries.
    # Show entries contain: "MM/DD ArtistName, SupportAct - Venue, Time, $Price"
    current_date = ""

    for el in soup.find_all(["h2", "h3", "h4", "h5", "p", "div"]):
        text = el.get_text(strip=True)
        if not text:
            continue

        # Check if this is a date heading
        date_match = re.match(
            r"^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b", text
        )
        if el.name in ("h2", "h3", "h4", "h5") and date_match:
            try:
                current_date = dp.parse(date_match.group(1), fuzzy=True).strftime("%Y-%m-%d")
            except Exception:
                current_date = ""
            continue

        # Show entry: starts with date prefix or is a paragraph following a date heading
        # Pattern: "MM/DD Artist - Venue Time $Price" or just "Artist - Venue Time $Price"
        if not current_date and not date_match:
            continue

        # Extract inline date prefix if present
        event_date = current_date
        if date_match:
            try:
                event_date = dp.parse(date_match.group(1), fuzzy=True).strftime("%Y-%m-%d")
                text = text[date_match.end():].strip().lstrip("- ").strip()
            except Exception:
                pass

        # Need at least some text to work with
        if len(text) < 5:
            continue

        # Extract time
        time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))", text, re.I)
        time_str = parse_time_12h(time_match.group(1)) if time_match else ""

        # Extract price
        price_match = re.search(r"\$\d+|free|pwyc|pay what", text, re.I)
        cost = parse_cost(price_match.group(0)) if price_match else ""

        # Extract venue (look for " - Venue" or " at Venue" pattern)
        venue = ""
        venue_match = re.search(r"[-–@]\s*([A-Z][^,$\n]+?)(?:\s*\d|\s*$|\s*,|\s*\$)", text)
        if venue_match:
            venue = venue_match.group(1).strip()

        # Title is whatever is left before the venue separator
        if venue_match:
            title = text[:venue_match.start()].strip().rstrip(" -–@")
        else:
            title = text.split(",")[0].strip()

        # Skip headings/nav elements accidentally captured
        if len(title) > 120 or len(title) < 2:
            continue

        # Get URL from any link in the element
        link = el.find("a")
        event_url = link.get("href", URL) if link else URL
        if event_url and not event_url.startswith("http"):
            event_url = BASE + event_url

        events.append(make_event(
            title=title,
            date=event_date,
            time=time_str,
            location=venue,
            cost=cost,
            url=event_url,
            tags=["music", "local"],
            calendar=CALENDAR_MUSIC,
            source=SOURCE,
        ))

    # Deduplicate
    seen = set()
    unique = []
    for e in events:
        key = (e["title"][:40], e["date"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    print(f"  [{SOURCE}] Found {len(unique)} events")
    return unique


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
