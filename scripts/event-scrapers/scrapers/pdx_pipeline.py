"""
Scraper for PDX Pipeline Events
URL: https://www.pdxpipeline.com/week/ + monthly pages
Format: WordPress/Beaver Builder. Events grouped under <h3> day headings:
  "Portland Tuesday Events, June 2:"
  Each <li> under the next <ul>: "Title @ Venue | time, details ( more info )"
  First pdxpipeline.com link → event URL + title
  Falls back to li text for title if no pipeline link.
Requires Playwright (JS needed to fully render page).
Calendar: events (general Portland events, various categories)
"""

import re
import asyncio
from datetime import date, timedelta
from dateutil import parser as dp
from .base import make_event, parse_time_12h, parse_cost, CALENDAR_EVENTS

SOURCE = "PDX Pipeline"
BASE = "https://www.pdxpipeline.com"

# Pages to scrape: /week/ + current and next 2 months
def _get_urls():
    today = date.today()
    months = []
    for offset in range(3):
        d = date(today.year, today.month, 1) + timedelta(days=32 * offset)
        d = date(d.year, d.month, 1)
        month_name = d.strftime("%B").lower()
        months.append(f"{BASE}/portland-{month_name}-events/")
    return [f"{BASE}/week/"] + months


MONTH_MAP = {m: i for i, m in enumerate(
    ["january","february","march","april","may","june",
     "july","august","september","october","november","december"], 1
)}


def _parse_date_from_heading(text: str) -> str:
    """Extract YYYY-MM-DD from heading like 'Portland Tuesday Events, June 2:'"""
    m = re.search(r'([A-Z][a-z]+)\s+(\d{1,2})(?:\s*:)?$', text.strip())
    if not m:
        return ""
    month_str, day_str = m.group(1).lower(), int(m.group(2))
    month_num = MONTH_MAP.get(month_str)
    if not month_num:
        return ""
    today = date.today()
    year = today.year
    # If the month is in the past, it's next year
    if month_num < today.month:
        year += 1
    return f"{year}-{month_num:02d}-{int(day_str):02d}"


def _parse_li(li, date_str: str) -> dict | None:
    """Parse a single <li> into an event dict."""
    full_text = li.get_text(" ", strip=True)
    if not full_text or len(full_text) < 5:
        return None

    # Find best link: prefer pdxpipeline.com event link, fall back to first external
    links = li.find_all("a", href=True)
    event_url = ""
    title_from_link = ""
    for a in links:
        href = a.get("href", "")
        link_text = a.get_text(strip=True)
        if "pdxpipeline.com" in href and link_text.lower() not in ("more info", "details", ""):
            event_url = href
            title_from_link = link_text
            break
    if not event_url:
        for a in links:
            href = a.get("href", "")
            if href.startswith("http") and "more info" not in a.get_text(strip=True).lower():
                event_url = href
                break

    # Split on @ to get title and venue
    if "@" in full_text:
        parts = full_text.split("@", 1)
        raw_title = parts[0].strip()
        venue_and_rest = parts[1]
        # Venue is up to first |
        if "|" in venue_and_rest:
            venue_part, rest = venue_and_rest.split("|", 1)
        else:
            venue_part, rest = venue_and_rest, ""
        location = venue_part.strip()
    else:
        if "|" in full_text:
            raw_title, rest = full_text.split("|", 1)
        else:
            raw_title, rest = full_text, ""
        location = ""

    # Use link text as title if cleaner (strips category prefix like "Beer: ")
    title = title_from_link if title_from_link else raw_title
    # Strip leading "Category: " prefixes
    title = re.sub(r"^[A-Za-z ]+:\s+", "", title).strip()
    # Strip trailing junk
    title = re.sub(r"\(\s*more info\s*\)", "", title, flags=re.I).strip()
    title = re.sub(r"\s*\|\s*$", "", title).strip()

    if not title or len(title) < 3:
        return None

    # Parse time from rest: "8AM-11PM" or "7:30PM" etc.
    time_str = ""
    end_time_str = ""
    time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM))\s*[-–]?\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM))?", rest, re.I)
    if time_match:
        time_str = parse_time_12h(time_match.group(1))
        if time_match.group(2):
            end_time_str = parse_time_12h(time_match.group(2))

    # Parse cost
    cost = ""
    cost_match = re.search(r"(free|\$\d+[\d\-]*|pay what|pwyc)", rest, re.I)
    if cost_match:
        cost = parse_cost(cost_match.group(0))

    # Skip non-Portland events (other cities)
    non_pdx = ["Seattle", "Tacoma", "Vancouver, BC", "Victoria", "Eugene", "Salem",
               "Astoria", "Bend", "Corvallis"]
    if any(city in full_text for city in non_pdx):
        return None

    return make_event(
        title=title,
        date=date_str,
        time=time_str,
        end_time=end_time_str,
        location=location,
        cost=cost,
        url=event_url,
        tags=["events"],
        calendar=CALENDAR_EVENTS,
        source=SOURCE,
    )


async def _fetch_page(url: str) -> list:
    """Fetch a single PDX Pipeline page and return parsed events."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup

    events = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(1000)
            content = await page.content()
            await browser.close()

        soup = BeautifulSoup(content, "lxml")

        for h3 in soup.find_all("h3"):
            heading = h3.get_text(strip=True)
            if "Portland" not in heading or "Events" not in heading:
                continue
            date_str = _parse_date_from_heading(heading)
            if not date_str:
                continue

            # Skip past dates
            try:
                if date.fromisoformat(date_str) < date.today():
                    continue
            except ValueError:
                continue

            ul = h3.find_next_sibling("ul")
            if not ul:
                continue

            for li in ul.find_all("li"):
                ev = _parse_li(li, date_str)
                if ev:
                    events.append(ev)

    except Exception as e:
        print(f"  [{SOURCE}] Error fetching {url}: {e}")

    return events


def scrape():
    urls = _get_urls()
    all_events = []
    seen = set()

    for url in urls:
        page_events = asyncio.run(_fetch_page(url))
        for e in page_events:
            key = (e["title"].lower()[:50], e["date"])
            if key not in seen:
                seen.add(key)
                all_events.append(e)

    all_events.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    print(f"  [{SOURCE}] Found {len(all_events)} events")
    return all_events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
