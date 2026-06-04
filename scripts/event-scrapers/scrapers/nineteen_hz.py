"""
Scraper for 19hz PNW Electronic Music Calendar
URL: https://19hz.info/eventlisting_PNW.php
Format: Static HTML <table>, one row per event.
        Columns: Date/Time | Event Title @ Venue | Tags | Price | Age | Organizers
Calendar: music (electronic/dance)
"""

import re
from bs4 import BeautifulSoup
from dateutil import parser as dp
from .base import get_page, make_event, parse_cost, CALENDAR_MUSIC

SOURCE = "19hz PNW"
URL = "https://19hz.info/eventlisting_PNW.php"
BASE = "https://19hz.info"


def _parse_datetime(cell0_text, iso_date=""):
    """
    Parse date+time from cell 0: 'Sat: May 30(2am-8am)'
    iso_date: optional pre-parsed date from last column e.g. '2026/05/30'
    Returns (date_str, time_str, end_time_str)
    """
    date_str = ""
    time_str = ""
    end_time_str = ""

    # Use ISO date from last column if available (most reliable)
    if iso_date:
        try:
            dt = dp.parse(iso_date)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # Fallback: parse date from cell 0 text
    if not date_str:
        try:
            dt = dp.parse(cell0_text, fuzzy=True)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # Time range in parentheses: e.g. "(2am-8am)" or "(8pm-2am)"
    time_range_match = re.search(r"\(([^)]+)\)", cell0_text)
    if time_range_match:
        time_range = time_range_match.group(1)
        parts = re.split(r"[-–—]", time_range)
        try:
            start_dt = dp.parse(f"2000-01-01 {parts[0].strip()}", fuzzy=True)
            time_str = start_dt.strftime("%H:%M")
        except Exception:
            pass
        if len(parts) > 1:
            try:
                end_dt = dp.parse(f"2000-01-01 {parts[1].strip()}", fuzzy=True)
                end_time_str = end_dt.strftime("%H:%M")
            except Exception:
                pass

    return date_str, time_str, end_time_str


def scrape():
    resp = get_page(URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    # Find the main events table — skip header rows
    table = soup.find("table")
    if not table:
        print(f"  [{SOURCE}] No table found")
        return []

    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        # Actual column layout (from inspection):
        # 0: "Sat: May 30(2am-8am)"  — day/date/time
        # 1: "Artist @ Venue (City, ST)"  — title+venue link
        # 2: tags/genre (often empty)
        # 3: "$25-35 | 19+"  — price | age
        # 4: empty
        # 5: organizer
        # 6: "2026/05/30"  — ISO date (last column)

        iso_date = cells[-1].get_text(strip=True) if cells else ""
        date_str, time_str, end_time_str = _parse_datetime(cells[0].get_text(), iso_date)

        # Column 1: "Event Title @ Venue (City, ST)" — venue is OUTSIDE the <a> tag
        title_cell = cells[1]
        link = title_cell.find("a")
        if not link:
            continue
        event_url = link.get("href", "")
        if event_url and not event_url.startswith("http"):
            event_url = BASE + "/" + event_url.lstrip("/")

        # Use full cell text (not just link text) so we get the venue after @
        raw_full = title_cell.get_text(" ", strip=True)

        if "@" in raw_full:
            title, location = raw_full.split("@", 1)
            title = title.strip()
            location = location.strip()
        else:
            title = link.get_text(strip=True)  # link text is cleaner when no @
            # Fallback: venue is sometimes in cell 4 when no @ in title
            location = cells[4].get_text(strip=True) if len(cells) > 4 else ""

        # Filter to Portland, OR events (skip Vancouver BC, Seattle, etc.)
        location_text = cells[1].get_text(" ", strip=True)
        if any(x in location_text for x in ["Vancouver, BC", "Seattle, WA", "Victoria, BC", "Tacoma"]):
            continue

        # Column 3: "$25-35 | 19+" — split on |
        tags = ["electronic", "music"]
        cost = ""
        if len(cells) > 3:
            price_age = cells[3].get_text(strip=True)
            if "|" in price_age:
                price_part, age_part = price_age.split("|", 1)
                cost = parse_cost(price_part.strip())
                age = age_part.strip()
                if age:
                    tags.append(age.lower())
            else:
                cost = parse_cost(price_age)

        # Column 2: genre tags
        if len(cells) > 2:
            tag_text = cells[2].get_text(strip=True).lower()
            if tag_text:
                tags += [t.strip() for t in tag_text.split(",") if t.strip()]

        if not title or not date_str:
            continue

        events.append(make_event(
            title=title.strip(),
            date=date_str,
            time=time_str,
            end_time=end_time_str,
            location=location.strip(),
            cost=cost,
            url=event_url,
            tags=list(set(tags)),
            calendar=CALENDAR_MUSIC,
            source=SOURCE,
        ))

    # Deduplicate within-source: 19hz sometimes lists the same show twice
    # (different ticket links, slightly different titles). Keep the more detailed entry.
    import re as _re
    def _norm(s):
        return _re.sub(r"[^a-z0-9]", "", s.lower())

    unique = []
    for e in events:
        absorbed = False
        for existing in unique:
            if existing["date"] != e["date"]:
                continue
            nt = _norm(e["title"])
            ne = _norm(existing["title"])
            # One title is a prefix/substring of the other → same show
            if nt and ne and (nt in ne or ne in nt):
                # Keep the one with more info (longer title, has location, has cost)
                e_score = len(e["title"]) + bool(e["location"]) * 20 + bool(e["cost"]) * 10
                x_score = len(existing["title"]) + bool(existing["location"]) * 20 + bool(existing["cost"]) * 10
                if e_score > x_score:
                    unique[unique.index(existing)] = e
                absorbed = True
                break
        if not absorbed:
            unique.append(e)

    print(f"  [{SOURCE}] Found {len(unique)} events ({len(events) - len(unique)} within-source dupes removed)")
    return unique


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
