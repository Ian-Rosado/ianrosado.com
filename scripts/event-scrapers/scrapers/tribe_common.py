"""
Shared reader for WordPress sites running The Events Calendar ("Tribe") plugin.

Those sites expose a public REST endpoint with clean, structured events:
  <site>/wp-json/tribe/events/v1/events?start_date=YYYY-MM-DD&per_page=50&page=N

Used by clinton_street.py and ground_kontrol.py. To add another Tribe site,
call fetch_tribe_events() with its base URL and map the results.
"""

import html
import re
from datetime import date

from dateutil import parser as dp

from .base import get_page, make_event, multiday_end_date, parse_cost, CALENDAR_EVENTS


def fetch_tribe_events(base_url, max_pages=10):
    """Return the raw event dicts from a Tribe REST API, starting today."""
    out = []
    for page in range(1, max_pages + 1):
        url = (f"{base_url.rstrip('/')}/wp-json/tribe/events/v1/events"
               f"?start_date={date.today().isoformat()}&per_page=50&page={page}")
        resp = get_page(url, timeout=25)
        if not resp:
            break
        data = resp.json()
        out += data.get("events", [])
        if page >= int(data.get("total_pages") or 1):
            break
    return out


def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def tribe_to_event(ev, source, tags=None, calendar=CALENDAR_EVENTS, default_location=""):
    """Map one Tribe API event to our event schema."""
    start = dp.parse(ev["start_date"])
    end = dp.parse(ev["end_date"]) if ev.get("end_date") else None
    all_day = bool(ev.get("all_day"))

    venue = ev.get("venue") or {}
    if isinstance(venue, list):  # empty venue comes back as []
        venue = venue[0] if venue else {}
    parts = [_clean(venue.get("venue", "")), _clean(venue.get("address", "")),
             _clean(venue.get("city", ""))]
    location = ", ".join(p for p in parts if p) or default_location

    cost = _clean(ev.get("cost", ""))
    cats = [_clean(c.get("name", "")).lower() for c in ev.get("categories") or []]

    return make_event(
        title=_clean(ev.get("title", "")),
        date=start.strftime("%Y-%m-%d"),
        time="" if all_day else start.strftime("%H:%M"),
        end_time="" if (all_day or not end) else end.strftime("%H:%M"),
        end_date=multiday_end_date(start, end),
        location=location,
        cost=parse_cost(cost) if cost else "",
        url=ev.get("url", ""),
        tags=(tags or []) + cats,
        calendar=calendar,
        source=source,
    )
