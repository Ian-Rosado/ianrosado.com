"""
Scraper for Community Playlist (communityplaylist.com)
URL: https://communityplaylist.com/
Format: JS-rendered (requires Playwright). Event cards are <a class="ev-card">
  with everything in attributes + child spans:
    - href / data-slug          → contains YYYY-MM-DD date
    - data-cat                  → "music" | "food" | "arts" | "fund" | ""
    - span.ev-time              → "Today · 5:30 PM" / "Fri Jun 5 · 8 PM"
    - div.ev-artists            → event title
    - span.ev-loc               → venue ("· Venue Name, address")
    - span.hood-tag             → neighborhood
    - span.ev-free              → "FREE" if free
    - span.genre-tag            → genre
Calendar: music for data-cat=music, events otherwise

Each event's own communityplaylist.com page usually has a "More info /
Tickets" link to the real outbound site — sometimes a venue, sometimes a
Google Calendar event page when that's the only link the organizer provided
(still a real, useful link). A few events instead show the URL itself as
plain link text with no "More info" label. Either way, fetched per-event (in
parallel; plain requests work fine here even though the listing page itself
needs Playwright) to replace the communityplaylist.com page link with that
real one. Filters out the site's own Discord/GitHub-issue links and the
generic "Add to Google Calendar" template link that appears on every page.
"""

import re
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_time_12h, CALENDAR_EVENTS, CALENDAR_MUSIC

SOURCE = "Community Playlist"
URL = "https://communityplaylist.com/"
BASE = "https://communityplaylist.com"

PLAYWRIGHT_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
PLAYWRIGHT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

JUNK_LINK_DOMAINS = (
    "communityplaylist.com", "discord.gg", "github.com/khildren",
    "google.com/calendar/render", "openstreetmap.org", "google.com/maps", "maps.google.com",
)


def _resolve_real_link(detail_url):
    """Fetch an event's communityplaylist.com page and pull its real outbound
    link — preferring a "More info / Tickets" label, else the first other
    qualifying external link. Returns '' if none found."""
    resp = get_page(detail_url)
    if not resp:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and not any(d in href for d in JUNK_LINK_DOMAINS):
            candidates.append((a.get_text(strip=True), href))
    for text, href in candidates:
        if "more info" in text.lower() or "tickets" in text.lower():
            return href
    return candidates[0][1] if candidates else ""


def _parse_time(time_text: str) -> str:
    """Extract HH:MM from 'Today · 5:30 PM' or 'Fri Jun 5 · 8 PM'."""
    if "·" in time_text:
        time_part = time_text.split("·")[-1].strip()
    else:
        time_part = time_text.strip()
    m = re.search(r"\d{1,2}(?::\d{2})?\s*(?:AM|PM)", time_part, re.I)
    return parse_time_12h(m.group(0)) if m else ""


def _parse_card(card) -> dict | None:
    # Date from href/slug
    href = card.get("href", "")
    slug = card.get("data-slug", "")
    date_m = re.search(r"(\d{4}-\d{2}-\d{2})", href + " " + slug)
    if not date_m:
        return None
    date_str = date_m.group(1)

    # Title
    artists_el = card.find(class_="ev-artists")
    title = artists_el.get_text(strip=True) if artists_el else ""
    if not title:
        return None

    # Time
    time_el = card.find(class_="ev-time")
    time_str = _parse_time(time_el.get_text(strip=True)) if time_el else ""

    # Location — strip leading "· "
    loc_el = card.find(class_="ev-loc")
    location = ""
    if loc_el:
        location = re.sub(r"^[·\s]+", "", loc_el.get_text(strip=True)).strip()

    # Neighborhood (prepend if no location, else keep as tag)
    hood_el = card.find(class_="hood-tag")
    neighborhood = ""
    if hood_el:
        neighborhood = re.sub(r"^[📍\s]+", "", hood_el.get_text(strip=True)).strip()

    # Cost
    cost = ""
    if card.find(class_="ev-free"):
        cost = "Free"
    else:
        meta = card.find(class_="ev-meta")
        if meta:
            cost_m = re.search(r"\$\s?[\d.]+", meta.get_text())
            if cost_m:
                cost = cost_m.group(0).replace(" ", "")

    # Category → calendar + tags
    data_cat = card.get("data-cat", "")
    calendar = CALENDAR_MUSIC if data_cat == "music" else CALENDAR_EVENTS

    tags = []
    if data_cat:
        tags.append(data_cat)
    genre_el = card.find(class_="genre-tag")
    if genre_el:
        genre = genre_el.get_text(strip=True)
        if genre:
            tags.append(genre.lower())
    if neighborhood:
        tags.append(neighborhood.lower())
    if not tags:
        tags = ["events"]

    event_url = BASE + href if href.startswith("/") else (href or URL)

    return make_event(
        title=title,
        date=date_str,
        time=time_str,
        location=location,
        cost=cost,
        url=event_url,
        tags=tags,
        calendar=calendar,
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
            await page.goto(URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
            content = await page.content()
            await browser.close()

        soup = BeautifulSoup(content, "lxml")
        for card in soup.find_all(class_="ev-card"):
            ev = _parse_card(card)
            if ev:
                events.append(ev)
    except Exception as e:
        print(f"  [{SOURCE}] Error: {e}")

    return events


def scrape():
    events = asyncio.run(_fetch())

    # Dedup by (title, date) and filter to upcoming
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

    # Swap each event's communityplaylist.com page URL for its real outbound
    # link, where one exists.
    unique_urls = {e["url"] for e in unique if e["url"]}
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
    for e in unique:
        if e["url"] in resolved:
            e["url"] = resolved[e["url"]]

    unique.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    print(f"  [{SOURCE}] Found {len(unique)} events")
    return unique


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
