"""
Scraper for PDX Parent
URL: https://pdxparent.com/events/  (data via The Events Calendar REST API)
Format: WordPress + The Events Calendar. We read the plugin's REST API
        (/wp-json/tribe/events/v1/events) rather than scraping HTML — it returns
        real start_date/end_date (so genuine multi-day events like a 4-day camp
        span correctly, which the HTML listing couldn't express), an all_day
        flag, cost, venue, tags, and the external website.

        Long-running exhibitions (TITANIC, library storytimes) are modeled by the
        plugin as recurring DAILY occurrences — one API event per day — so we
        dedup by title and keep only the next upcoming occurrence, matching how
        the old listing showed them once.
Calendar: events (family-friendly)
"""

import html
from datetime import date, datetime, timedelta
import requests
from .base import make_event, parse_cost, CALENDAR_EVENTS

SOURCE = "PDX Parent"
URL = "https://pdxparent.com/events/"
API = "https://pdxparent.com/wp-json/tribe/events/v1/events"
# pdxparent.com's WAF returns 403 to any client that claims a browser
# User-Agent but lacks a real browser's TLS fingerprint (the fake-Chrome-UA
# mismatch that bot filters flag). A plain, non-browser UA is served normally —
# for the REST API too. DO NOT "upgrade" this to a Mozilla/Chrome UA.
HEADERS_OVERRIDE = {
    "User-Agent": "pdx-events-scraper/1.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

PER_PAGE = 50
HORIZON_DAYS = 45     # stop paging once events start beyond this
MAX_PAGES = 12


def _venue_location(venue) -> str:
    """Build a location string from the API's venue object."""
    if not isinstance(venue, dict):
        return ""
    parts = [venue.get("venue", "")]
    addr = venue.get("address", "")
    city = venue.get("city", "")
    state = venue.get("state", "") or venue.get("stateprovince", "")
    zipc = venue.get("zip", "")
    tail = " ".join(p for p in [addr, ", ".join(x for x in [city, state] if x), zipc] if p).strip()
    if tail:
        parts.append(tail)
    return ", ".join(p for p in parts if p).strip(", ").strip()


def _parse(e: dict) -> dict | None:
    if e.get("status") and e["status"] != "publish":
        return None
    if e.get("is_virtual"):
        return None
    title = html.unescape((e.get("title") or "").strip())
    if not title or not e.get("start_date"):
        return None
    try:
        sd = datetime.strptime(e["start_date"], "%Y-%m-%d %H:%M:%S")
        ed = datetime.strptime(e.get("end_date") or e["start_date"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    all_day = bool(e.get("all_day"))
    date_str = sd.strftime("%Y-%m-%d")
    # Multi-day: the plugin's end_date is inclusive (…T23:59:59), so a later end
    # date is a genuine span. make_event renders date..end_date as all-day.
    end_date_str = ed.strftime("%Y-%m-%d") if ed.date() > sd.date() else ""
    if all_day or end_date_str:
        time_str = end_time_str = ""
    else:
        time_str = sd.strftime("%H:%M") if (sd.hour or sd.minute) else ""
        end_time_str = ed.strftime("%H:%M") if (ed.date() == sd.date() and (ed.hour or ed.minute)) else ""

    tags = ["family-friendly"]
    for c in (e.get("categories") or []):
        n = (c.get("name") if isinstance(c, dict) else c)
        if n:
            tags.append(str(n).lower())
    for t in (e.get("tags") or []):
        n = (t.get("name") if isinstance(t, dict) else t)
        if n:
            tags.append(str(n).lower())

    website = (e.get("website") or "").strip()
    url = website if website.startswith("http") else (e.get("url") or URL)

    return make_event(
        title=title,
        date=date_str,
        time=time_str,
        end_time=end_time_str,
        end_date=end_date_str,
        location=_venue_location(e.get("venue")),
        cost=parse_cost(e.get("cost", "")),
        url=url,
        tags=tags,
        calendar=CALENDAR_EVENTS,
        source=SOURCE,
    )


def scrape():
    today = date.today()
    horizon = today + timedelta(days=HORIZON_DAYS)
    raw = []
    for page in range(1, MAX_PAGES + 1):
        params = {"per_page": PER_PAGE, "start_date": today.isoformat(), "page": page}
        try:
            resp = requests.get(API, headers=HEADERS_OVERRIDE, params=params, timeout=20)
            if resp.status_code == 400:  # past the last page
                break
            resp.raise_for_status()
            events = resp.json().get("events", [])
        except Exception as e:
            print(f"  [ERROR] {SOURCE}: {e}")
            break
        if not events:
            break
        raw.extend(events)
        # Sorted by start_date — stop once a page starts beyond the horizon.
        try:
            if datetime.strptime(events[0]["start_date"], "%Y-%m-%d %H:%M:%S").date() > horizon:
                break
        except (ValueError, KeyError):
            pass

    # Dedup recurring-series occurrences: keep the earliest upcoming per title.
    seen = {}
    for e in raw:
        ev = _parse(e)
        if not ev:
            continue
        try:
            if date.fromisoformat(ev["date"]) < today:
                continue
        except ValueError:
            continue
        key = ev["title"].lower()
        if key not in seen or ev["date"] < seen[key]["date"]:
            seen[key] = ev

    events = sorted(seen.values(), key=lambda e: (e["date"], e.get("time", "")))
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
