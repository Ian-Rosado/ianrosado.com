"""
Scraper for NearHear — Portland live music
URL: https://nearhear.app/calendar
Format: JS-rendered (Playwright). Each show row contains an "Add to Calendar"
        Google Calendar render link that encodes the full event cleanly:
          text=Artist at Venue
          dates=YYYYMMDDTHHMMSSZ/...  (UTC)
          details=Price: $X\nAge: ...\nTickets: URL
          location=Venue
        We parse those render URLs — most reliable signal on the page.
Calendar: music
"""

import re
import asyncio
from datetime import date, datetime, timezone
from urllib.parse import unquote, urlparse, parse_qs
from dateutil import tz as dateutil_tz
from .base import make_event, parse_cost, CALENDAR_MUSIC

SOURCE = "NearHear"
URL = "https://nearhear.app/calendar"
PACIFIC = dateutil_tz.gettz("America/Los_Angeles")

PLAYWRIGHT_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
PLAYWRIGHT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _parse_gcal_dates(dates_param: str) -> tuple[str, str]:
    """Convert '20260604T013000Z/20260604T043000Z' (UTC) → Pacific date + time."""
    start_raw = dates_param.split("/")[0]
    m = re.match(r"(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z", start_raw)
    if not m:
        return "", ""
    y, mo, d, h, mi, s = map(int, m.groups())
    dt_utc = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    dt_pac = dt_utc.astimezone(PACIFIC)
    return dt_pac.strftime("%Y-%m-%d"), dt_pac.strftime("%H:%M")


def _find_venue_page(render_anchor) -> str:
    """From an event's 'Add to Calendar' anchor, walk up to the smallest
    enclosing card and return its NearHear venue-page URL (/venues/<id>/<slug>).
    NearHear has no per-event pages, so the venue page is the most specific link
    on the card. Returns "" if none is found."""
    node = render_anchor
    for _ in range(8):
        node = getattr(node, "parent", None)
        if node is None:
            break
        v = node.find("a", href=re.compile(r"^/venues/\d+"))
        if v and v.get("href"):
            return "https://nearhear.app" + v["href"].split("?")[0]
    return ""


def _parse_render_url(href: str, venue_page: str = "") -> dict | None:
    decoded = unquote(href)
    qs = parse_qs(urlparse(href).query)

    text = (qs.get("text", [""])[0]).strip()
    dates = qs.get("dates", [""])[0]
    details = (qs.get("details", [""])[0])
    location = (qs.get("location", [""])[0]).strip()

    # details uses literal "\n" (backslash-n), not real newlines — normalize
    details = details.replace("\\n", "\n")

    if not text or not dates:
        return None

    # text = "Artist at Venue" — split on last " at "
    if " at " in text:
        title, venue_from_text = text.rsplit(" at ", 1)
        title = title.strip()
    else:
        title = text
        venue_from_text = ""
    location = location or venue_from_text

    date_str, time_str = _parse_gcal_dates(dates)
    if not date_str:
        return None

    # details: "Price: $25.00\nAge: All Ages\nTickets: https://..."
    # NearHear uses "$-1.00" as a sentinel for "price not set" — leave blank
    # rather than passing that through as a literal cost.
    cost = ""
    ticket_url = ""
    tags = ["music"]
    price_m = re.search(r"Price:\s*([^\n]+)", details)
    if price_m:
        price_raw = price_m.group(1).strip()
        # Strip a "$-1.00" sentinel half of a range ("$10.00 - $-1.00" -> "$10.00")
        price_raw = re.sub(r"\s*-\s*\$?-1(\.0+)?$", "", price_raw)
        if not re.match(r"\$?-1(\.0+)?$", price_raw):
            cost = parse_cost(price_raw)
    age_m = re.search(r"Age:\s*([^\n]+)", details)
    if age_m:
        age = age_m.group(1).strip()
        if age:
            tags.append(age.lower().replace(" ", "-"))
    ticket_m = re.search(r"Tickets:\s*(https?://\S+)", details)
    if ticket_m:
        ticket_url = ticket_m.group(1).strip()

    return make_event(
        title=title,
        date=date_str,
        time=time_str,
        location=location,
        cost=cost,
        # ticket page (most specific) > NearHear venue page > generic calendar hub
        url=ticket_url or venue_page or URL,
        tags=tags,
        calendar=CALENDAR_MUSIC,
        source=SOURCE,
    )


async def _fetch() -> list:
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    events = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_ARGS)
            context = await browser.new_context(
                user_agent=PLAYWRIGHT_UA,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="America/Los_Angeles",
            )
            await context.add_init_script(
                'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            )
            page = await context.new_page()
            await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            content = await page.content()
            await browser.close()

        soup = BeautifulSoup(content, "lxml")
        for a in soup.find_all("a", href=re.compile(r"calendar\.google\.com/calendar/render")):
            ev = _parse_render_url(a.get("href", ""), _find_venue_page(a))
            if ev:
                events.append(ev)
    except Exception as e:
        print(f"  [{SOURCE}] Error: {e}")

    return events


def scrape():
    events = asyncio.run(_fetch())

    today = date.today()
    seen = set()
    unique = []
    for e in events:
        try:
            if date.fromisoformat(e["date"]) < today:
                continue
        except ValueError:
            continue
        key = (e["title"].lower()[:50], e["date"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    unique.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    print(f"  [{SOURCE}] Found {len(unique)} events")
    return unique


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
