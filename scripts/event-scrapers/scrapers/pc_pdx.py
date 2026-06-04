"""
Scraper for People's Co-op / PC-PDX Show Guide
URL: https://pc-pdx.com/show-guide/?date=M/D/YYYY
Format: Static HTML. Each show is in a <div class="show-listing"> containing multiple <ul>s:
  - ul with /bands/ links: band names
  - ul with /venues/ link: venue info
  - The info ul also has: date/age text "Sunday, 6/7/2026 21+", time/price text "7:30pm | $12"
  - ul with /show-guide/filter-by-tag/ links: genre tags
  - ul with /show-detail/ID link: "Full Detail" → event URL
Calendar: music (indie/punk/DIY)
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_time_12h, parse_cost, CALENDAR_MUSIC

SOURCE = "PC-PDX Show Guide"
BASE_URL = "https://pc-pdx.com/show-guide/"
BASE = "https://pc-pdx.com"

DAYS_AHEAD = 30


def _scrape_date(target_date):
    """Scrape a single date page; returns list of events."""
    date_param = f"{target_date.month}/{target_date.day}/{target_date.year}"
    url = f"{BASE_URL}?date={date_param}"

    resp = get_page(url)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    for div in soup.find_all("div", class_="show-listing"):
        # ── Band names ────────────────────────────────────────────────────────
        band_links = div.find_all("a", href=re.compile(r"/bands/"))
        title = " + ".join(a.get_text(strip=True) for a in band_links if a.get_text(strip=True))
        if not title:
            continue

        # ── Info ul: venue + date/age + time/price ────────────────────────────
        # Find the ul that contains a /venues/ link
        info_ul = None
        for ul in div.find_all("ul"):
            if ul.find("a", href=re.compile(r"/venues/")):
                info_ul = ul
                break
        if not info_ul:
            continue

        venue_link = info_ul.find("a", href=re.compile(r"/venues/"))
        location = venue_link.get_text(strip=True) if venue_link else ""

        # Parse date and age from li text e.g. "Sunday, 6/7/2026 21+"
        date_str = ""
        tags = ["music"]
        time_str = ""
        cost = ""

        for li in info_ul.find_all("li"):
            text = li.get_text(strip=True)

            # Date
            date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", text)
            if date_match and not date_str:
                try:
                    date_str = dp.parse(date_match.group(1)).strftime("%Y-%m-%d")
                except Exception:
                    pass

            # Age restriction
            age_match = re.search(r"(all\s*ages?|21\+|18\+)", text, re.I)
            if age_match:
                tags.append(age_match.group(1).lower().replace(" ", "-"))

            # Time + cost: "7:30pm | $12"
            if "|" in text:
                parts = [p.strip() for p in text.split("|")]
                for part in parts:
                    if re.search(r"\d.*(?:am|pm)", part, re.I) and not time_str:
                        time_str = parse_time_12h(part)
                    elif re.search(r"\$|free|pwyc", part, re.I) and not cost:
                        cost = parse_cost(part)
            elif re.search(r"\d.*(?:am|pm)", text, re.I) and not time_str:
                time_str = parse_time_12h(text)

        # ── Genre tags ────────────────────────────────────────────────────────
        for ul in div.find_all("ul"):
            if ul.find("a", href=re.compile(r"/show-guide/filter-by-tag/")):
                for a in ul.find_all("a"):
                    genre = a.get_text(strip=True).lower()
                    if genre:
                        tags.append(genre)
                break

        # ── Event URL: "Full Detail" link → /show-detail/ID ──────────────────
        detail_link = div.find("a", string=re.compile(r"Full Detail", re.I))
        if detail_link:
            href = detail_link.get("href", "")
            event_url = BASE + href if href.startswith("/") else href
        else:
            event_url = BASE_URL

        if not title or not date_str:
            continue

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            cost=cost,
            url=event_url,
            tags=list(dict.fromkeys(tags)),  # preserve order, dedupe
            calendar=CALENDAR_MUSIC,
            source=SOURCE,
        ))

    return events


def scrape():
    today = date.today()
    dates = [today + timedelta(days=i) for i in range(DAYS_AHEAD + 1)]

    all_events = []
    # Fetch dates in parallel (up to 10 at a time to be polite)
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_scrape_date, d): d for d in dates}
        for future in as_completed(futures):
            try:
                all_events.extend(future.result())
            except Exception as e:
                pass  # individual date failures are non-fatal

    # Deduplicate by (title, date) in case same show appears on multiple date pages
    seen = set()
    unique = []
    for e in all_events:
        key = (e["title"].lower()[:60], e["date"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    # Sort by date
    unique.sort(key=lambda e: (e.get("date") or "9999", e.get("time") or ""))

    print(f"  [{SOURCE}] Found {len(unique)} events")
    return unique


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
