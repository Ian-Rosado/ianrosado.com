"""
Scraper for Multnomah County Library — free talks, craft nights, maker/3D-print
workshops, music, film festivals, poetry readings, mahjong, puzzle swaps ...
URL: https://multcolib.org/events-classes
Format: Drupal view, static HTML, 20 events per page (?page=N), filtered to our
        date window with field_event_start_value[min]/[max]. The site 403s a
        bare User-Agent but serves normal browser headers fine.
Calendar: events

The library lists ~1,100 events a month, most of them recurring services
(storytimes, tech-help drop-ins, GED/ESL/citizenship classes, teen and kids
clubs). EXCLUDE drops those by title so what's left is the adult/all-ages
programming that fits the calendar. Tune EXCLUDE if something useful goes
missing or noise creeps in.
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests

from .base import make_event, parse_time_12h, CALENDAR_EVENTS

SOURCE = "Multnomah County Library"
BASE = "https://multcolib.org"
DAYS = 30
MAX_PAGES = 120

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
}

EXCLUDE = re.compile(
    r"stor(y|ies) ?time|storytime|cuentos|book babies|tiny tots|stories with friends"
    r"|tech help|ayuda tecnol|resume|english class|citizenship|\bged\b|tutor|homework"
    r"|intercambio|language exchange|conversation (group|circle)|\besl\b|college essay"
    r"|read to the (dogs|cats)|\bteens?\b|\btweens?\b|adolescentes|youth|kids|preschool"
    r"|bab(y|ies)|toddler|playtime|grades? \d|\bk-\d|family maker|creative learning"
    r"|follow the reader|lego|violin lessons|ukulele lessons|\binea\b"
    r"|volunteers of america|goodwill|microsoft|google sheets|computer basics"
    r"|cancel+ed|cancelado|recovery|careoregon|medicare|tax (help|prep)|\bjobs?\b"
    r"|one-on-one|appointment|library tour|cao niên"
    r"|[Ѐ-ӿ]|[一-鿿]|giờ |song ngữ",   # non-English duplicates of the above
    re.I)

# Title keyword -> tag, for the facets the website filters on.
KEYWORD_TAGS = [
    (r"craft|knit|crochet|sew|quilt|bead|yarn|printmak", "crafts"),
    (r"maker|3d print|laser|circuit|glowforge|prusa", "maker"),
    (r"music|dj |ableton|drum|dance|danc", "music"),
    (r"film|movie|cinema", "film"),
    (r"poet|reading|author|book|writ|storytelling", "books"),
    (r"mahjong|chess|game|puzzle|tabletop|pokemon", "games"),
    (r"garden|garlic|plant|bugs|botany|trees|mustangs", "nature"),
]


def _get(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        print(f"  [{SOURCE}] fetch failed {url}: {e}")
        return ""


def _field(block, cls):
    m = re.search(r'class="' + cls + r'[^"]*">(.*?)</div>', block, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()


def _list_url(start, end, page):
    return (f"{BASE}/events-classes?field_event_start_value%5Bmin%5D={start}"
            f"&field_event_start_value%5Bmax%5D={end}&page={page}")


def parse_page(page_html):
    rows = []
    for block in re.findall(r'<div class="event row.*?(?=<div class="event row|<nav|$)', page_html, re.S):
        t = re.search(r'class="event__title"><a href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not t:
            continue
        rows.append({
            "url": BASE + t.group(1),
            "title": html.unescape(re.sub(r"<[^>]+>", "", t.group(2))).strip(),
            "date": _field(block, "event__date"),
            "time": _field(block, "event__time"),
            "location": _field(block, "event__location"),
        })
    return rows


def scrape():
    start = date.today().isoformat()
    end = (date.today() + timedelta(days=DAYS)).isoformat()
    first = _get(_list_url(start, end, 0))
    if not first:
        return []
    total = re.search(r"Displaying \d+ - \d+ of (\d+)", first)
    n_pages = min(MAX_PAGES, -(-int(total.group(1)) // 20)) if total else 1
    with ThreadPoolExecutor(max_workers=6) as ex:
        pages = [first] + list(ex.map(lambda n: _get(_list_url(start, end, n)), range(1, n_pages)))

    events, seen = [], set()
    for page_html in pages:
        for r in parse_page(page_html):
            if EXCLUDE.search(r["title"]) or r["url"] in seen:
                continue
            seen.add(r["url"])
            try:
                d = datetime.strptime(r["date"], "%a %b %d %Y").date().isoformat()
            except ValueError:
                continue
            t_start, _, t_end = r["time"].partition("-")
            title_l = r["title"].lower()
            tags = ["library", "free"] + [tag for pat, tag in KEYWORD_TAGS if re.search(pat, title_l)]
            events.append(make_event(
                title=r["title"],
                date=d,
                time=parse_time_12h(t_start),
                end_time=parse_time_12h(t_end),
                location=r["location"],
                cost="Free",
                url=r["url"],
                tags=tags,
                calendar=CALENDAR_EVENTS,
                source=SOURCE,
            ))
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
