"""
Shared utilities and event schema for all Portland event scrapers.

Event schema:
  title          : str   - Event name
  date           : str   - YYYY-MM-DD (start / first day)
  time           : str   - HH:MM 24-hour, or "" if unknown
  end_time       : str   - HH:MM 24-hour, or "" if unknown
  end_date       : str   - YYYY-MM-DD last day of a multi-day event, else "".
                           When set, the event is all-day and spans date..end_date
                           (see multiday_end_date() + the "End Time" column, which
                           carries this date for portland_events_add to span).
  duration_minutes: int  - Derived from time/end_time if available, else None
  location       : str   - Venue name and/or address
  cost           : str   - Free, $10, "Pay what you can", etc.
  url            : str   - Link to event detail page
  tags           : list  - Category tags e.g. ["music", "free", "all-ages"]
  calendar       : str   - "events" | "music" | "comedy" | "farmers_market"
  source         : str   - Human-readable source name
"""

import requests
from datetime import datetime, date, timedelta
from dateutil import parser as dateparser

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

CALENDAR_EVENTS = "events"
CALENDAR_MUSIC = "music"
CALENDAR_FARMERS_MARKET = "farmers_market"
CALENDAR_COMEDY = "comedy"
CALENDAR_KARAOKE = "karaoke"
CALENDAR_SPORTS = "sports"


# ── Tag normalization ──────────────────────────────────────────────────────
# Maps messy/variant tags to canonical labels so filtering is consistent.
# Applied automatically by make_event() to every scraper's output.

# variant -> canonical
TAG_CANON = {
    # genres
    "live jazz": "jazz", "experimental jazz": "jazz", "jazz fusion": "jazz",
    "live jazz music": "jazz", "improvised music": "jazz",
    "indie rock": "indie", "alternative rock": "rock", "rock music": "rock",
    "alternative": "rock", "hard rock": "rock",
    "indie folk": "folk", "folk rock": "folk", "singer-songwriter": "folk",
    "singer songwriter": "folk", "americana": "folk",
    "punk rock": "punk",
    "pop punk": "pop-punk",
    "hip hop": "hip-hop", "hiphop": "hip-hop", "rap": "hip-hop",
    "drum and bass": "dnb", "drum & bass": "dnb",
    "tech house": "house", "deep house": "house", "progressive house": "house",
    "electro house": "house",
    "synth pop": "synthpop",
    "dark wave": "darkwave", "goth-industrial": "darkwave", "gothic": "goth",
    "r&b": "soul", "rnb": "soul",
    "electronica": "electronic", "edm": "electronic",
    "post punk": "post-punk",
    # ages
    "all ages": "all-ages", "all age": "all-ages", "all-age": "all-ages",
    # neighborhoods (light touch)
    "n/ne": "ne", "nw/sw": "nw",
}

# Tags that are too generic to be useful facets — dropped.
TAG_DROP = {"music", "event", "events", "local", "misc", "show", "live", "more"}

MAX_TAGS = 6


def normalize_tags(tags):
    """Clean, canonicalize, and dedupe a raw tag list.
    - lowercases and trims
    - maps variants to canonical labels (TAG_CANON)
    - drops generic noise (TAG_DROP)
    - dedupes preserving order, caps at MAX_TAGS
    """
    if not tags:
        return []
    seen = set()
    out = []
    for raw in tags:
        if not raw:
            continue
        t = str(raw).strip().lower()
        t = TAG_CANON.get(t, t)
        if not t or t in TAG_DROP or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= MAX_TAGS:
            break
    return out


def multiday_end_date(start_dt, end_dt):
    """Given a source event's start/end *datetimes*, return the inclusive last
    day ('YYYY-MM-DD') of a genuine multi-day event, or '' for a single day.

    Conservative on purpose: requires the span to exceed 24h, so an event that
    merely ends after midnight (a late concert, e.g. 9pm–1am) is never treated
    as multi-day. An all-day end at exactly midnight is treated as exclusive
    (iCal/hCalendar convention), i.e. the last real day is the day before.

    Pass the result as make_event(end_date=...); it renders as an all-day span.
    """
    if not start_dt or not end_dt:
        return ""
    if (end_dt - start_dt) <= timedelta(hours=24):
        return ""
    last = end_dt
    if end_dt.hour == 0 and end_dt.minute == 0:
        last = end_dt - timedelta(days=1)   # exclusive all-day end
    if last.date() <= start_dt.date():
        return ""
    return last.date().isoformat()


def make_event(
    title="",
    date="",
    time="",
    end_time="",
    end_date="",
    duration_minutes=None,
    location="",
    cost="",
    url="",
    tags=None,
    calendar=CALENDAR_EVENTS,
    source="",
):
    """Return a new event dict with all required fields."""
    # Multi-day span: when end_date is a later calendar day than the start date,
    # the event is rendered as an all-day event covering date..end_date. Force
    # all-day by dropping the clock times (a week-long festival has no single
    # start/end time). A same-day-or-earlier end_date is ignored.
    if end_date and date and end_date > date:
        time = ""
        end_time = ""
    else:
        end_date = ""

    # Auto-compute duration_minutes if both times are given
    if duration_minutes is None and time and end_time:
        try:
            t1 = datetime.strptime(time, "%H:%M")
            t2 = datetime.strptime(end_time, "%H:%M")
            diff = (t2 - t1).seconds // 60
            if diff > 0:
                duration_minutes = diff
        except ValueError:
            pass

    return {
        "title": title,
        "date": date,
        "time": time,
        "end_time": end_time,
        "end_date": end_date,
        "duration_minutes": duration_minutes,
        "location": location,
        "cost": cost,
        "url": url,
        "tags": normalize_tags(tags),
        "calendar": calendar,
        "source": source,
    }


def get_page(url, timeout=15):
    """Fetch a URL and return a requests.Response, or None on error."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        print(f"  [ERROR] Failed to fetch {url}: {e}")
        return None


def parse_time_12h(text):
    """
    Parse a 12-hour time string like '7pm', '7:30 PM', '10:00 am'
    into 'HH:MM' 24-hour format. Returns '' on failure.
    """
    if not text:
        return ""
    text = text.strip().lower().replace(".", "")
    try:
        dt = dateparser.parse(f"2000-01-01 {text}")
        return dt.strftime("%H:%M") if dt else ""
    except Exception:
        return ""


def parse_cost(text):
    """Normalize cost text. Returns 'Free' if free, else the raw text."""
    if not text:
        return ""
    low = text.strip().lower()
    if any(w in low for w in ["free", "$0", "no cost", "no charge"]):
        return "Free"
    return text.strip()
