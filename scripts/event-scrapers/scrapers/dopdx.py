"""
Scraper for Do PDX
URL: https://dopdx.com/
Format: Static HTML with Schema.org Event markup (DoStuff Media platform).
        Event cards: div.ds-listing[itemprop=event]
          - itemprop="name"                    -> title
          - itemprop="startDate" content=ISO   -> date + time
          - itemprop="location" > name         -> venue
          - data-permalink                     -> relative URL (fallback)
          - itemprop="offers" > meta[itemprop=url] -> "Buy Tickets" link,
            already embedded in the card — no extra request needed. Usually
            wrapped in an affiliate redirect (e.g. etix.prf.hn/click/.../
            destination:<url-encoded real link>, or ticketmaster.evyy.net/
            ...?u=<url-encoded real link>) — the real link is pulled out of
            whichever query/path slot carries it. A few events have no offers
            link (href="#"), and a few platforms (tixr.com) use their own
            affiliate path with no wrapped destination to extract — both fall
            back to using the href as-is, or the dopdx.com page if absent.
          - CSS class ds-event-category-{cat}  -> category/tags
        Paginates via ?offset=N (25 per page). Scrapes 3 pages (75 events);
        run_all.py's date filter trims to the configured window.
        Skips events tagged "eugene" (out of area).
Calendar: music for music category, events for everything else
"""

import re
from urllib.parse import unquote
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, CALENDAR_EVENTS, CALENDAR_MUSIC

SOURCE = "Do PDX"
BASE_URL = "https://dopdx.com"
PAGES = 3  # 25 events each

EMBEDDED_URL_RE = re.compile(r"https?%3A%2F%2F[^&\s]+")


def _resolve_buy_link(raw_href):
    """Pull the real destination out of an affiliate-redirect href, where one
    is embedded. If there's no embedded link, the href is already the real
    (or platform-native affiliate) link — return as-is. Returns '' for empty/
    placeholder hrefs."""
    if not raw_href or raw_href == "#" or raw_href.startswith("/"):
        return ""
    m = EMBEDDED_URL_RE.search(raw_href)
    if m:
        return unquote(m.group(0))
    return raw_href


def _parse_events(soup):
    events = []
    for card in soup.find_all("div", class_="ds-listing"):
        # Title
        name_el = card.find(itemprop="name")
        title = name_el.get_text(strip=True) if name_el else ""
        if not title:
            continue

        # Date + time from ISO startDate
        start_el = card.find(itemprop="startDate")
        date_str = ""
        time_str = ""
        if start_el and start_el.get("content"):
            try:
                dt = dp.parse(start_el["content"])
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M")
            except Exception:
                pass
        if not date_str:
            continue

        # Venue: nested location > name
        loc_scope = card.find(itemprop="location")
        location = ""
        if loc_scope:
            loc_name = loc_scope.find(itemprop="name")
            location = loc_name.get_text(strip=True) if loc_name else loc_scope.get_text(strip=True)

        # URL: prefer the real "Buy Tickets" link embedded in the offers
        # markup; fall back to the dopdx.com event page (data-permalink).
        permalink = card.get("data-permalink", "")
        fallback_url = BASE_URL + permalink if permalink.startswith("/") else permalink

        buy_link = ""
        offers_el = card.find(itemprop="offers")
        if offers_el:
            offer_url_el = offers_el.find(itemprop="url")
            if offer_url_el:
                raw_href = offer_url_el.get("content") or offer_url_el.get("href", "")
                buy_link = _resolve_buy_link(raw_href)
        event_url = buy_link or fallback_url

        # Category from CSS class: ds-event-category-{cat}
        categories = [
            c.replace("ds-event-category-", "")
            for c in (card.get("class") or [])
            if c.startswith("ds-event-category-")
        ]

        # Skip out-of-area events
        if "eugene" in categories:
            continue

        # Assign calendar
        calendar = CALENDAR_MUSIC if "music" in categories else CALENDAR_EVENTS

        tags = categories if categories else ["events"]

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            location=location,
            url=event_url,
            tags=tags,
            calendar=calendar,
            source=SOURCE,
        ))

    return events


def scrape():
    all_events = []
    seen = set()

    for page in range(PAGES):
        offset = page * 25
        url = f"{BASE_URL}/?offset={offset}" if offset else BASE_URL + "/"
        resp = get_page(url)
        if not resp:
            break

        soup = BeautifulSoup(resp.text, "lxml")
        events = _parse_events(soup)
        if not events:
            break

        for e in events:
            key = (e["title"].lower()[:50], e["date"])
            if key not in seen:
                seen.add(key)
                all_events.append(e)

    print(f"  [{SOURCE}] Found {len(all_events)} events")
    return all_events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
