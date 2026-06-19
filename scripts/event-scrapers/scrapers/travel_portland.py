"""
Scraper for Travel Portland Events
URL: Multiple pages (today, tomorrow, this-weekend, next-weekend, monthly)
Format: Requires Playwright with stealth settings to bypass Cloudflare.
        Event cards: div.tp-card
          - h3.tp-card__title       → event title
          - span.tp-card__date      → date string ("Friday, June 5, 2026" / "June 4–25, 2026" / "Ongoing")
          - span.tp-card__venue-name → venue
          - span.tp-card__meta      → venue + cost concatenated (subtract venue to get cost)
          - a[href*=/event/]        → event URL
Calendar: events (general Portland events, well-curated)

Each event's own travelportland.com page has an anchor literally labeled
"Website" linking to the real outbound site (sometimes a Facebook event page
when there's no dedicated site) — fetched per-event (in parallel) to replace
the travelportland.com page link with that real one. Unlike the listing
pages, the event detail pages aren't Cloudflare-protected, so a plain request
works (no Playwright needed for this part). Ignores the "Book Now" Expedia
affiliate link that appears identically on every event page — it's a site-
wide hotel-booking widget, not event-specific.
"""

import re
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_cost, CALENDAR_EVENTS

SOURCE = "Travel Portland"
BASE = "https://www.travelportland.com"


def _resolve_real_link(detail_url):
    """Fetch an event's travelportland.com page and pull its "Website"
    anchor (the real outbound link). Returns '' if not found."""
    resp = get_page(detail_url)
    if not resp:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True) == "Website":
            return a["href"]
    return ""

PLAYWRIGHT_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
PLAYWRIGHT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _get_urls():
    today = date.today()
    urls = [
        f"{BASE}/events/things-to-do-in-portland-today/",
        f"{BASE}/events/things-to-do-in-portland-tomorrow/",
        f"{BASE}/events/things-to-do-in-portland-this-weekend/",
        f"{BASE}/events/things-to-do-in-portland-next-weekend/",
    ]
    # Add current and next month pages
    for offset in range(2):
        d = date(today.year, today.month, 1) + timedelta(days=32 * offset)
        d = date(d.year, d.month, 1)
        month_name = d.strftime("%B").lower()
        urls.append(f"{BASE}/events/portland-{month_name}-events/")
    return urls


def _parse_date(date_str: str) -> str:
    """Parse a Travel Portland date string to YYYY-MM-DD."""
    if not date_str:
        return ""
    s = date_str.strip()
    if s.lower() in ("ongoing", "year-round", ""):
        return ""

    today = date.today()

    if s.lower() == "today":
        return today.isoformat()
    if s.lower() == "tomorrow":
        return (today + timedelta(days=1)).isoformat()

    # Require a month name — otherwise it's not a real date string
    if not re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", s, re.I):
        return ""

    # Strip ranges: "June 4–25, 2026" → use start date "June 4, 2026"
    s = re.sub(r"[–—]\s*\d+", "", s).strip().rstrip(",").strip()

    # Add year if missing
    if not re.search(r"\d{4}", s):
        s = f"{s}, {today.year}"

    try:
        parsed = dp.parse(s, fuzzy=True)
        # If parsed date is in the past, bump to next year
        if parsed.date() < today:
            parsed = parsed.replace(year=today.year + 1)
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return ""


def _parse_card(card) -> dict | None:
    # Title
    title_el = card.find("h3", class_="tp-card__title")
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        return None

    # Skip navigation/promo cards
    if title.lower().startswith("things to do in portland"):
        return None

    # Date (div, not span)
    date_el = card.find(class_="tp-card__date")
    date_str = _parse_date(date_el.get_text(strip=True) if date_el else "")
    if not date_str:
        return None  # skip ongoing/undated events

    # Venue
    venue_el = card.find(class_="tp-card__venue-name")
    location = venue_el.get_text(strip=True) if venue_el else ""

    # Cost: tp-card__meta contains "VenueNameCost" — strip venue to isolate cost
    cost = ""
    meta_el = card.find(class_="tp-card__meta")
    if meta_el:
        meta_text = meta_el.get_text(strip=True)
        # Remove venue name from meta to get cost
        cost_text = meta_text.replace(location, "").strip()
        if cost_text:
            cost = parse_cost(cost_text)

    # URL — prefer travelportland.com links over staging (pantheonsite.io)
    event_url = ""
    for a in card.find_all("a", href=True):
        href = a.get("href", "")
        if "travelportland.com/event/" in href:
            event_url = href
            break
        elif "/event/" in href and not event_url:
            # Normalize staging URLs to production
            event_url = re.sub(r"https?://[^/]+(/event/)", rf"{BASE}\1", href)

    return make_event(
        title=title,
        date=date_str,
        location=location,
        cost=cost,
        url=event_url,
        tags=["events"],
        calendar=CALENDAR_EVENTS,
        source=SOURCE,
    )


async def _fetch_page(url: str) -> list:
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    events = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_ARGS)
            context = await browser.new_context(
                user_agent=PLAYWRIGHT_UA,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                timezone_id="America/Los_Angeles",
            )
            await context.add_init_script(
                'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=25000)
            await page.wait_for_timeout(2000)
            content = await page.content()
            await browser.close()

        soup = BeautifulSoup(content, "lxml")
        for card in soup.find_all("div", class_="tp-card"):
            ev = _parse_card(card)
            if ev:
                events.append(ev)

    except Exception as e:
        print(f"  [{SOURCE}] Error fetching {url}: {e}")

    return events


def scrape():
    all_events = []
    seen = set()

    for url in _get_urls():
        page_events = asyncio.run(_fetch_page(url))
        for e in page_events:
            key = (e["title"].lower()[:50], e["date"])
            if key not in seen:
                seen.add(key)
                all_events.append(e)

    # Filter to upcoming only
    today = date.today()
    all_events = [
        e for e in all_events
        if e["date"] and date.fromisoformat(e["date"]) >= today
    ]
    all_events.sort(key=lambda e: e["date"])

    # Swap each event's travelportland.com page URL for its "Website" link.
    unique_urls = {e["url"] for e in all_events if e["url"]}
    resolved = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(_resolve_real_link, u): u for u in unique_urls}
        for future in as_completed(future_to_url):
            u = future_to_url[future]
            try:
                real_url = future.result()
                if real_url:
                    resolved[u] = real_url
            except Exception:
                pass
    for e in all_events:
        if e["url"] in resolved:
            e["url"] = resolved[e["url"]]

    print(f"  [{SOURCE}] Found {len(all_events)} events")
    return all_events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
