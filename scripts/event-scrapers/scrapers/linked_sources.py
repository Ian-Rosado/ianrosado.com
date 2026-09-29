"""
Scraper for a hand-picked list of small sources, configured in
../linked_sources.json — mostly the "moveable" and monthly-with-no-fixed-day
fixtures from Tunnel Vision PDX's recurring calendar, whose own sites carry the
real dates: Meetup groups (movie clubs, jams, sewists, pagans), Squarespace
event pages (The Raven's Wing, ADX), and full-moon gatherings.
Format: one reader per "type" in the config:
  squarespace  <url>?format=json -> "upcoming" items (title, start/end ms, location)
  meetup       group page's schema.org Event JSON-LD (upcoming events)
  jsonld       any page's schema.org Event JSON-LD
  full_moon    computed full-moon dates at a fixed place/time (no fetch)
Calendar: per entry ("events" default; "music", "comedy", "karaoke").

Config entry keys: name, type, url, match (keep only titles containing any of
these), exclude (drop titles containing any — use for nights already on the
calendar as recurring events), calendar, tags, location (fallback when an
event lists none); full_moon also takes title, time, cost. Add a source by adding a line to the JSON.
"""

import html
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dateutil import parser as dp
from dateutil import tz as dateutil_tz

from .base import get_page, make_event, multiday_end_date, parse_cost

SOURCE = "Linked Sources"
CONFIG = Path(__file__).resolve().parent.parent / "linked_sources.json"
PACIFIC = dateutil_tz.gettz("America/Los_Angeles")
DAYS = 60


def _clean(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def _keep(title, entry):
    t = title.lower()
    if entry.get("match") and not any(m in t for m in entry["match"]):
        return False
    return not any(x in t for x in entry.get("exclude", []))


def _local(dt):
    return dt.astimezone(PACIFIC).replace(tzinfo=None) if dt.tzinfo else dt


def _event(entry, title, start, end, location, url, cost=""):
    start, end = _local(start), (_local(end) if end else None)
    location = location or entry.get("location", "")
    return make_event(
        title=title,
        date=start.strftime("%Y-%m-%d"),
        time=start.strftime("%H:%M"),
        end_time=end.strftime("%H:%M") if end and end.date() == start.date() else "",
        end_date=multiday_end_date(start, end),
        location=location,
        cost=cost,
        url=url,
        tags=entry.get("tags", []),
        calendar=entry.get("calendar", "events"),
        source=f"{entry['name']} (via {SOURCE})",
    )


def read_squarespace(entry):
    resp = get_page(entry["url"].rstrip("/") + "?format=json", timeout=25)
    if not resp:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    base = re.match(r"https?://[^/]+", entry["url"]).group(0)
    out = []
    for it in data.get("upcoming") or data.get("items") or []:
        if not it.get("startDate") or not _keep(it.get("title", ""), entry):
            continue
        loc = it.get("location") or {}
        location = ", ".join(p for p in (_clean(loc.get("addressTitle")), _clean(loc.get("addressLine1")),
                                         _clean(loc.get("addressLine2"))) if p)
        start = datetime.fromtimestamp(it["startDate"] / 1000, tz=timezone.utc)
        end = datetime.fromtimestamp(it["endDate"] / 1000, tz=timezone.utc) if it.get("endDate") else None
        out.append(_event(entry, _clean(it["title"]), start, end, location, base + it.get("fullUrl", "")))
    return out


def _jsonld_events(page_html):
    found = []
    for s in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page_html, re.S):
        try:
            stack = [json.loads(s)]
        except ValueError:
            continue
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack += x
            elif isinstance(x, dict):
                if "Event" in str(x.get("@type", "")) and x.get("startDate") and x.get("name"):
                    found.append(x)
                stack += [v for v in x.values() if isinstance(v, (list, dict))]
    return found


def read_jsonld(entry):
    resp = get_page(entry["url"], timeout=25)
    if not resp:
        return []
    out = []
    for ev in _jsonld_events(resp.text):
        title = _clean(ev["name"])
        if not _keep(title, entry):
            continue
        if "Online" in str(ev.get("eventAttendanceMode", "")):
            continue
        place = ev.get("location") or {}
        if isinstance(place, list):
            place = place[0] if place else {}
        addr = place.get("address") or {}
        street = addr.get("streetAddress", "") if isinstance(addr, dict) else str(addr)
        name = place.get("name", "")
        location = name if street and name and name in street else ", ".join(p for p in (name, street) if p)
        offers = ev.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        price = offers.get("price") if isinstance(offers, dict) else None
        cost = "Free" if price in (0, "0", "0.00") else (f"${price}" if price else "")
        out.append(_event(entry, title, dp.parse(ev["startDate"]),
                          dp.parse(ev["endDate"]) if ev.get("endDate") else None,
                          location, ev.get("url") or entry["url"], parse_cost(cost)))
    return out


# Mean synodic month and a reference full moon (2000-01-21 04:40 UTC); accurate
# to within a few hours, which is plenty for an evening gathering.
_SYNODIC = 29.530588853
_REF_FULL = datetime(2000, 1, 21, 4, 40, tzinfo=timezone.utc)


def full_moons(start, end):
    """Full-moon datetimes (Pacific) between two dates."""
    t0 = datetime.combine(start, datetime.min.time(), tzinfo=PACIFIC)
    n = math.ceil((t0 - _REF_FULL).total_seconds() / 86400 / _SYNODIC)
    out = []
    while True:
        moon = (_REF_FULL + timedelta(days=n * _SYNODIC)).astimezone(PACIFIC)
        if moon.date() > end:
            return out
        out.append(moon)
        n += 1


def read_full_moon(entry):
    hh, mm = (int(x) for x in entry["time"].split(":"))
    out = []
    for moon in full_moons(date.today(), date.today() + timedelta(days=DAYS)):
        start = datetime.combine(moon.date(), datetime.min.time()).replace(hour=hh, minute=mm)
        out.append(_event(entry, entry["title"], start, start + timedelta(hours=2),
                          entry["location"], entry["url"], entry.get("cost", "")))
    return out


READERS = {"squarespace": read_squarespace, "meetup": read_jsonld,
           "jsonld": read_jsonld, "full_moon": read_full_moon}


def scrape():
    entries = json.loads(CONFIG.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    events = []
    for entry in entries:
        try:
            got = READERS[entry["type"]](entry)
        except Exception as ex:  # one broken source shouldn't sink the rest
            print(f"  [{SOURCE}] {entry['name']} failed: {ex}")
            continue
        got = [e for e in got if (e["end_date"] or e["date"]) >= today]
        print(f"  [{SOURCE}] {entry['name']}: {len(got)}")
        events += got
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    print(json.dumps(scrape(), indent=2))
