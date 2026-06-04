"""
Scraper for Portland Living on the Cheap
URL: https://portlandlivingonthecheap.com/events/
Format: Static HTML, events in <h3> tags with adjacent date/time/cost text
"""

import re
from bs4 import BeautifulSoup
from .base import get_page, make_event, parse_time_12h, parse_cost, CALENDAR_EVENTS, CALENDAR_FARMERS_MARKET

SOURCE = "Portland Living on the Cheap"
URL = "https://portlandlivingonthecheap.com/events/"


def scrape():
    resp = get_page(URL)
    if not resp:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    events = []

    # Portland Living on the Cheap groups events by date.
    # Date headers appear as elements containing "Today:", "Tomorrow:", or weekday+date text.
    # Event divs follow: div.lotc-v2.event or div.event
    # Strategy: walk all elements in order, track current date from headers.

    from dateutil import parser as dp_outer

    # Build an ordered list of (date_context, event_div) by walking the main content
    main = soup.select_one("main, #main, .site-main, .tribe-events") or soup.body
    all_elements = main.find_all(True) if main else []

    date_context = ""
    event_queue = []

    for el in all_elements:
        text = el.get_text(" ", strip=True)
        # Detect date header: contains day name + month or "Today:"
        if el.name in ("h2", "h3", "h4", "p", "div", "span"):
            if re.search(r"(Today|Tomorrow|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", text, re.I):
                if re.search(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", text, re.I):
                    try:
                        dt = dp_outer.parse(text, fuzzy=True)
                        date_context = dt.strftime("%Y-%m-%d")
                    except Exception:
                        pass

        # Detect event container
        classes = el.get("class") or []
        class_str = " ".join(classes)
        if "lotc-v2" in class_str and "event" in class_str:
            event_queue.append((date_context, el))
        elif "event" in class_str and el.name == "div" and el.find("h3"):
            event_queue.append((date_context, el))

    # Deduplicate event divs (walking finds nested elements multiple times)
    seen_ids = set()
    unique_events = []
    for date_ctx, el in event_queue:
        el_id = id(el)
        if el_id not in seen_ids:
            seen_ids.add(el_id)
            unique_events.append((date_ctx, el))

    for date_ctx, article in unique_events:
        title_el = article.select_one("h3 a, h3, h2 a, h2")
        if not title_el:
            continue
        link = title_el.find("a") if title_el.name != "a" else title_el
        title = title_el.get_text(strip=True)
        url = link.get("href", URL) if link else URL

        # The remaining text in the event div holds "All Day | Location" or "10am | $5 | Location"
        # Strip the title text and parse what's left
        full_text = article.get_text(" | ", strip=True)
        # Remove title from start
        if title in full_text:
            remainder = full_text[len(title):].strip(" |")
        else:
            remainder = full_text

        parts = [p.strip() for p in remainder.split("|") if p.strip()]

        date_str = date_ctx  # inherited from section header
        time_str = ""
        end_time_str = ""
        cost = ""
        location = ""

        # Parse parts: time, price, location
        from dateutil import parser as dp
        for part in parts:
            part_low = part.lower()
            # Date patterns
            if re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", part_low):
                try:
                    dt = dp.parse(part, fuzzy=True)
                    date_str = dt.strftime("%Y-%m-%d")
                    if dt.hour or dt.minute:
                        time_str = dt.strftime("%H:%M")
                except Exception:
                    pass
            elif "all day" in part_low:
                pass  # no time
            elif re.match(r"^\d{1,2}(:\d{2})?\s*(am|pm)", part_low):
                time_match = re.match(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))", part, re.I)
                if time_match:
                    from .base import parse_time_12h
                    time_str = parse_time_12h(time_match.group(1))
            elif re.search(r"\$\d|free|pwyc", part_low):
                cost = parse_cost(part)
            elif len(part) > 3 and not re.match(r"^\d", part):
                location = part

        # Tags
        tags = []
        tag_els = article.select("[rel='tag'], .tags a")
        tags = [t.get_text(strip=True).lower() for t in tag_els]

        # Calendar type
        title_lower = title.lower()
        cal = CALENDAR_FARMERS_MARKET if "market" in title_lower or "farm" in title_lower else CALENDAR_EVENTS

        events.append(make_event(
            title=title,
            date=date_str,
            time=time_str,
            end_time=end_time_str,
            location=location,
            cost=cost,
            url=url,
            tags=tags,
            calendar=cal,
            source=SOURCE,
        ))

    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
