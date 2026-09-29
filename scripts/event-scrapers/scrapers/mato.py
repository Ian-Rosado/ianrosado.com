"""
Scraper for Mato — curated Portland events: live music, parties, film, markets,
workshops, talks, community meetups (letter-writing clubs, drink-and-draws ...).
URL: https://ma.to/events/portland
Format: Next.js. The listing loads more events through a Next.js Server Action
        (a POST to the listing URL carrying a `next-action` id header), which
        returns clean JSON: title, start/end, price/isFreePrice, venue,
        categories. The action id changes on every Mato deploy, so we load the
        page in Playwright, scroll once to capture it, then call the action
        ourselves with our own date window, 50 events per page.
Calendar: music for Live Music, comedy for Comedy, events for everything else
          (the Categorize step re-checks mixed rows anyway).
"""

import json
from datetime import datetime, timedelta

from dateutil import parser as dp
from dateutil import tz as dateutil_tz

from .base import make_event, multiday_end_date, CALENDAR_EVENTS, CALENDAR_MUSIC, CALENDAR_COMEDY

SOURCE = "Mato"
LIST_URL = "https://ma.to/events/portland/this-weekend"
EVENT_URL = "https://ma.to/event/{slug}"
CITY_ID = "81f266d5-8aef-49ab-ab93-bc424625a787"   # Portland
DAYS = 30
PAGE_SIZE = 50
MAX_PAGES = 60
PACIFIC = dateutil_tz.gettz("America/Los_Angeles")

PLAYWRIGHT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_CALL_ACTION_JS = """async ([url, headers, body]) => {
    const r = await fetch(url, {method: 'POST', body, headers: {
        'next-action': headers['next-action'],
        'next-router-state-tree': headers['next-router-state-tree'],
        'content-type': 'text/plain;charset=UTF-8',
        'accept': 'text/x-component'}});
    return await r.text();
}"""


def _action_payload(text):
    """A Server Action response is RSC lines ("0:{...}", "1:{...}"); the data is line 1."""
    for line in text.split("\n"):
        if line.startswith("1:"):
            return json.loads(line[2:])
    return {}


def _fetch_raw():
    from playwright.sync_api import sync_playwright

    start = datetime.now(PACIFIC).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=DAYS)
    raw = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=PLAYWRIGHT_UA)
        captured = {}
        page.on("request", lambda r: captured.setdefault("req", (r.url, dict(r.headers)))
                if r.method == "POST" and "/events/portland" in r.url else None)
        page.goto(LIST_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        for _ in range(8):  # scroll until the infinite list fires its "load more"
            if "req" in captured:
                break
            page.mouse.wheel(0, 8000)
            page.wait_for_timeout(1500)
        if "req" not in captured:
            browser.close()
            print(f"  [{SOURCE}] couldn't capture the load-more action (site change?)")
            return []
        url, headers = captured["req"]
        for n in range(1, MAX_PAGES + 1):
            body = json.dumps([{
                "cityId": CITY_ID, "categoryId": "anything",
                "startDate": int(start.timestamp()), "endDate": int(end.timestamp()) - 1,
                "timezone": "America/Los_Angeles", "datePeriodId": "custom",
                "page": n, "limit": PAGE_SIZE, "search": "",
            }])
            data = _action_payload(page.evaluate(_CALL_ACTION_JS, [url, headers, body]))
            raw += data.get("events", [])
            if not (data.get("pagination") or {}).get("hasNext"):
                break
        browser.close()
    return raw


def _cost(ev):
    if ev.get("isFreePrice"):
        return "Free"
    price = str(ev.get("price") or "").strip()
    if not price:
        return ""
    return price if price.startswith("$") or not price[0].isdigit() else f"${price}"


def scrape():
    events, seen = [], set()
    for ev in _fetch_raw():
        if not ev.get("title") or not ev.get("startDate") or ev.get("slug") in seen:
            continue
        seen.add(ev.get("slug"))
        start = dp.parse(ev["startDate"]).astimezone(PACIFIC).replace(tzinfo=None)
        end = dp.parse(ev["endDate"]).astimezone(PACIFIC).replace(tzinfo=None) if ev.get("endDate") else None
        cats = [c.get("slug", "") for c in ev.get("categories") or []]
        calendar = (CALENDAR_MUSIC if "live-music" in cats
                    else CALENDAR_COMEDY if cats == ["comedy"] else CALENDAR_EVENTS)
        venue = ev.get("venueName") or ev.get("venueLocation") or ""
        if ev.get("venueAddress"):
            venue = f"{venue}, {ev['venueAddress']}" if venue else ev["venueAddress"]
        cost = _cost(ev)
        events.append(make_event(
            title=ev["title"].strip(),
            date=start.strftime("%Y-%m-%d"),
            time=start.strftime("%H:%M"),
            end_time=end.strftime("%H:%M") if end else "",
            end_date=multiday_end_date(start, end),
            location=venue,
            cost=cost,
            url=EVENT_URL.format(slug=ev["slug"]),
            tags=[c.replace("-", " ") for c in cats] + (["free"] if cost == "Free" else []),
            calendar=calendar,
            source=SOURCE,
        ))
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    print(json.dumps(scrape(), indent=2))
