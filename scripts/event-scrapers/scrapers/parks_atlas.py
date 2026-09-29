"""
Scraper for Portland Parks Atlas — events in Portland parks, compiled from
official Portland Parks & Recreation listings: volunteer/stewardship days,
garden tending, nature programs and community events.
URL: https://parks.portlandciviclab.org/events
Format: iCalendar feed (https://parks.portlandciviclab.org/events/calendar.ics),
        parsed by hand (a tiny subset of RFC 5545: unfolding + text escapes).
Calendar: events

Government meetings (oversight committees, hearings) share the feed and are
dropped. Parks events are free; volunteer days get a "volunteer" tag.
"""

import re
from datetime import datetime, timezone

from dateutil import tz as dateutil_tz

from .base import get_page, make_event, multiday_end_date, CALENDAR_EVENTS

SOURCE = "Portland Parks Atlas"
ICS_URL = "https://parks.portlandciviclab.org/events/calendar.ics"
PACIFIC = dateutil_tz.gettz("America/Los_Angeles")

_MEETING_RE = re.compile(r"\bmeeting\b|committee|hearing|board of|commission|webinar", re.I)
_VOLUNTEER_RE = re.compile(r"volunteer|stewardship|tending|weed|planting|clean.?up|crew|restoration", re.I)


def _unescape(v):
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\")).strip()


def _parse_dt(value, params):
    """ICS DTSTART/DTEND -> (datetime in Pacific, is_all_day)."""
    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d"), True
    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone(PACIFIC).replace(tzinfo=None), False
    # Floating / TZID-local time: treat as Portland local
    return datetime.strptime(value[:15], "%Y%m%dT%H%M%S"), False


def parse_ics(text):
    """Return a list of {prop: (params, value)} dicts, one per VEVENT."""
    lines = re.sub(r"\r?\n[ \t]", "", text).splitlines()  # unfold continuations
    events, cur = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            name, _, params = key.partition(";")
            cur[name.upper()] = (params, value)
    return events


def scrape():
    resp = get_page(ICS_URL, timeout=25)
    if not resp:
        return []
    events = []
    for v in parse_ics(resp.text):
        title = _unescape(v.get("SUMMARY", ("", ""))[1])
        if not title or _MEETING_RE.search(title) or "DTSTART" not in v:
            continue
        start, all_day = _parse_dt(v["DTSTART"][1], v["DTSTART"][0])
        end = None
        if "DTEND" in v:
            end, _ = _parse_dt(v["DTEND"][1], v["DTEND"][0])
        desc = _unescape(v.get("DESCRIPTION", ("", ""))[1])
        location = re.sub(r"\s+,", ",", _unescape(v.get("LOCATION", ("", ""))[1]))
        if re.search(r"to be (announced|determined)|\bTBA\b|\bTBD\b", location, re.I):
            location = ""
        tags = ["parks", "outdoors", "free"]
        if _VOLUNTEER_RE.search(title + " " + desc):
            tags.insert(0, "volunteer")
        events.append(make_event(
            title=title,
            date=start.strftime("%Y-%m-%d"),
            time="" if all_day else start.strftime("%H:%M"),
            end_time="" if (all_day or not end) else end.strftime("%H:%M"),
            end_date=multiday_end_date(start, end),
            location=location,
            cost="Free",
            url=_unescape(v.get("URL", ("", ""))[1]),
            tags=tags,
            calendar=CALENDAR_EVENTS,
            source=SOURCE,
        ))
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
