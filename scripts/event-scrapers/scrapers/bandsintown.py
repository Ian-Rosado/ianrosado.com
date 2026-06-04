"""
Scraper for Bandsintown — Portland concerts
URL: https://www.bandsintown.com/c/portland-or
Format: JS-rendered (Playwright). CSS classes are obfuscated/hashed, so we
        parse from stable signals instead:
          - href: /e/{id}-{artist}-at-{venue}  → artist + venue from slug
          - container text: "{Mon Day}- {h:mm am/pm}"  → date + time
Calendar: music (concerts)
"""

import re
import asyncio
from datetime import date
from dateutil import parser as dp
from .base import make_event, parse_time_12h, CALENDAR_MUSIC

SOURCE = "Bandsintown"
URL = "https://www.bandsintown.com/c/portland-or"

PLAYWRIGHT_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
PLAYWRIGHT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"


def _slug_to_artist_venue(href: str) -> tuple[str, str]:
    """Parse /e/{id}-{artist}-at-{venue} into (artist, venue)."""
    m = re.search(r"/e/\d+-(.+)$", href.split("?")[0].rstrip("/"))
    if not m:
        return "", ""
    slug = m.group(1)
    if "-at-" in slug:
        artist_slug, venue_slug = slug.rsplit("-at-", 1)
    else:
        artist_slug, venue_slug = slug, ""

    def deslug(s: str) -> str:
        return " ".join(w.capitalize() for w in s.split("-")).strip()

    return deslug(artist_slug), deslug(venue_slug)


def _parse_date_time(text: str) -> tuple[str, str]:
    """Extract date + time from container text like 'Jun 23- 7:00 pm'."""
    today = date.today()
    date_str = ""
    time_str = ""

    date_m = re.search(rf"({MONTHS})\s+(\d{{1,2}})", text)
    if date_m:
        try:
            parsed = dp.parse(f"{date_m.group(1)} {date_m.group(2)} {today.year}")
            if parsed.date() < today:
                parsed = parsed.replace(year=today.year + 1)
            date_str = parsed.strftime("%Y-%m-%d")
        except Exception:
            pass

    time_m = re.search(r"\d{1,2}:\d{2}\s*[ap]m", text, re.I)
    if time_m:
        time_str = parse_time_12h(time_m.group(0))

    return date_str, time_str


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
        seen = set()
        for a in soup.find_all("a", href=re.compile(r"/e/\d")):
            href = a.get("href", "").split("?")[0]
            if href in seen:
                continue
            seen.add(href)

            artist, venue = _slug_to_artist_venue(href)
            if not artist:
                continue

            # Walk up a few levels to capture the date/time text
            container = a
            for _ in range(4):
                if container.parent:
                    container = container.parent
            text = container.get_text(" ", strip=True)
            date_str, time_str = _parse_date_time(text)
            if not date_str:
                continue

            events.append(make_event(
                title=artist,
                date=date_str,
                time=time_str,
                location=venue,
                url=href,
                tags=["music", "concert"],
                calendar=CALENDAR_MUSIC,
                source=SOURCE,
            ))
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
