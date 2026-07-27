"""
Scraper for Artichoke Music (artichokemusic.org)
URL: https://www.artichokemusic.org/events
Format: The artichokemusic.org/events page is just a landing page that links
        out to Eventbrite — all of Artichoke's shows (concerts, open mics,
        jams) are ticketed through the "Artichoke Community Music" Eventbrite
        organizer. That organizer page embeds an "upcomingEvents" JSON array
        (name / url / start_date / start_time / end_date / end_time) in static
        HTML, so we parse that directly — no Playwright needed.

        Note: the embedded blob lists ~12 upcoming shows (roughly the next two
        weeks). Because the scraper runs on a schedule every few days, coverage
        rolls forward and nothing is missed over time.
Calendar: music (single-venue folk/acoustic room)
"""

import json
from datetime import date
from .base import get_page, make_event, CALENDAR_MUSIC

SOURCE = "Artichoke Music"
# artichokemusic.org/events → Eventbrite organizer for "Artichoke Community Music"
ORGANIZER_URL = "https://www.eventbrite.com/o/artichoke-community-music-115994389511"
LANDING_URL = "https://www.artichokemusic.org/events"
VENUE = "Artichoke Music, 2007 SE Powell Blvd, Portland, OR 97202"

_MARKER = '"upcomingEvents":'


def _extract_upcoming(html: str) -> list:
    """Pull the embedded upcomingEvents JSON array out of the organizer page."""
    i = html.find(_MARKER)
    if i < 0:
        return []
    j = html.find("[", i)
    if j < 0:
        return []
    try:
        # raw_decode parses the array starting at '[' and ignores trailing HTML.
        arr, _ = json.JSONDecoder().raw_decode(html[j:])
        return arr if isinstance(arr, list) else []
    except json.JSONDecodeError:
        return []


def scrape():
    resp = get_page(ORGANIZER_URL)
    if not resp:
        return []

    raw = _extract_upcoming(resp.text)
    today = date.today()
    events = []
    for e in raw:
        if e.get("is_cancelled"):
            continue
        title = (e.get("name") or "").strip()
        start_date = (e.get("start_date") or "").strip()
        if not title or not start_date:
            continue
        try:
            if date.fromisoformat(start_date) < today:
                continue
        except ValueError:
            continue

        start_time = (e.get("start_time") or "")[:5]      # "19:00:00" -> "19:00"
        end_time = (e.get("end_time") or "")[:5]
        end_date = (e.get("end_date") or "").strip()
        # Only carry an end_date when it's a genuinely later day (multi-day run).
        if end_date <= start_date:
            end_date = ""
        # Eventbrite repeats the start as the end when no real end is set —
        # that yields a zero-length event, so drop a same-as-start end_time.
        if end_time and end_time == start_time:
            end_time = ""

        events.append(make_event(
            title=title,
            date=start_date,
            time=start_time,
            end_time=end_time,
            end_date=end_date,
            location=VENUE,
            cost="",  # ticketed; price not in the listing blob
            url=(e.get("url") or LANDING_URL),
            tags=["music", "folk"],
            calendar=CALENDAR_MUSIC,
            source=SOURCE,
        ))

    events.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    print(json.dumps(scrape(), indent=2))
