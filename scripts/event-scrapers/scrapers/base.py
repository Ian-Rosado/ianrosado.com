"""
Shared utilities and event schema for all Portland event scrapers.

Event schema:
  title          : str   - Event name
  date           : str   - YYYY-MM-DD
  time           : str   - HH:MM 24-hour, or "" if unknown
  end_time       : str   - HH:MM 24-hour, or "" if unknown
  duration_minutes: int  - Derived from time/end_time if available, else None
  location       : str   - Venue name and/or address
  cost           : str   - Free, $10, "Pay what you can", etc.
  url            : str   - Link to event detail page
  tags           : list  - Category tags e.g. ["music", "free", "all-ages"]
  calendar       : str   - "events" | "music" | "comedy" | "farmers_market"
  source         : str   - Human-readable source name
"""

import requests
from datetime import datetime, date
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


def make_event(
    title="",
    date="",
    time="",
    end_time="",
    duration_minutes=None,
    location="",
    cost="",
    url="",
    tags=None,
    calendar=CALENDAR_EVENTS,
    source="",
):
    """Return a new event dict with all required fields."""
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
        "duration_minutes": duration_minutes,
        "location": location,
        "cost": cost,
        "url": url,
        "tags": tags or [],
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
