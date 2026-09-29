#!/usr/bin/env python3
"""
trivia_scrape.py
----------------
Re-pull every trivia company's current Portland-area schedule and diff it
against trivia_schedule.json (the source of truth trivia_generate.py reads).

Sources (one scraper per company):
  Last Call Trivia   WordPress API (lct_venue, Portland region) + each venue page
  Geeks Who Drink    venue-map AJAX endpoint (needs a page nonce -> Playwright)
  Bridgetown Trivia  Squarespace grid page (rendered with Playwright; day
                     headings and venue lists are separate blocks, so we pair
                     them by on-page position, not text order)
  Untapped Trivia    /join page text
  ShanRock's Trivia  homepage "WEEKLY QUIZZERY SCHEDULE" sidebar
  Rip City Trivia    homepage partner list (h4 name + schedule block)
  Rain Brain Trivia  homepage "Upcoming Events"
  Double Mountain    brewery events page ("<Taproom> Weekly Trivia" listings)

Only trivia is kept: Music Bingo, Feud, and Boombox Bingo nights are dropped.

Merge rules (--write):
  * Matched venues keep their JSON name, address and calendar (so trivia_key
    stays stable); day/time/rrule/cost/start_date are refreshed from the site.
  * Venues no longer listed are removed.
  * New venues are added with a calendar routed from their address. A new
    venue whose source gives no address needs an ADDRESS_OVERRIDES entry;
    it's reported and skipped until then.
  * A company whose scraper fails or returns nothing is left untouched
    (never mass-pruned because a site was down).

Usage:
  python trivia_scrape.py                      # scrape all, print diff
  python trivia_scrape.py --only gwd,lastcall  # subset of scrapers
  python trivia_scrape.py --write              # apply diff to trivia_schedule.json
  python trivia_scrape.py --save out.json      # also dump raw scraped rows

Then: python trivia_generate.py --dry-run  ->  python trivia_generate.py
"""

import re
import sys
import json
import html
import time
import argparse
from pathlib import Path
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

import requests

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
SCHEDULE = HERE / "trivia_schedule.json"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"}

SE, NNE, NWSW, FURTHER = ("Trivia Nights - SE", "Trivia Nights - N/NE",
                          "Trivia Nights - NW/SW", "Trivia Nights - Further Out")

COMPANY_URLS = {
    "Last Call Trivia": "https://lastcalltrivia.com",
    "Geeks Who Drink": "https://www.geekswhodrink.com",
    "Bridgetown Trivia": "https://www.bridgetowntrivia.com",
    "Untapped Trivia": "https://untappedtrivia.com",
    "ShanRock's Trivia": "https://shanrockstrivia.com",
    "Rip City Trivia": "https://www.ripcitytrivia.com",
    "Rain Brain Trivia": "https://rainbraintrivia.weebly.com",
    "Double Mountain": "https://doublemountainbrewery.com",
}

# Companies that charge to play (everything else defaults to "Free").
COMPANY_COST = {"ShanRock's Trivia": "$5/team"}

# Display-name cleanups for venues as they appear on a company's site.
NAME_OVERRIDES = {
    ("Rip City Trivia", "Alexs-Bar"): "Alex's Bar",
    ("Rip City Trivia", "The Heist PDX"): "The Heist",
    ("ShanRock's Trivia", "THE GOODFOOT"): "The Goodfoot",
    ("ShanRock's Trivia", "THUNDERBIRD (on Foster)"): "Thunderbird on Foster",
    ("ShanRock's Trivia", "THUNDERBIRD (on Mississippi)"): "Thunderbird on Mississippi",
}

# Addresses for venues whose source site doesn't list one. Keyed by the
# cleaned venue name (after NAME_OVERRIDES).
ADDRESS_OVERRIDES = {
    ("Bridgetown Trivia", "The Oaks Pub"): "1621 SE Bybee Blvd, Portland, OR 97202",
    ("Rip City Trivia", "Alex's Bar"): "1712 NE 223rd Ave, Fairview, OR 97024",
    ("Rip City Trivia", "The Heist"): "4727 SE Woodstock Blvd, Portland, OR 97206",
    ("ShanRock's Trivia", "The Goodfoot"): "2845 SE Stark St, Portland, OR 97214",
    ("ShanRock's Trivia", "Thunderbird on Foster"): "5339 SE Foster Rd, Portland, OR 97206",
    ("ShanRock's Trivia", "Thunderbird on Mississippi"): "3560 N Mississippi Ave, Portland, OR 97227",
}

DAY_WORDS = {"mon": "MO", "tue": "TU", "wed": "WE", "thu": "TH",
             "fri": "FR", "sat": "SA", "sun": "SU"}
ORD = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "last": -1}


# ── Parsing helpers ─────────────────────────────────────────────────────────

def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=30, **kw)
    r.raise_for_status()
    return r


def html_to_text(t):
    t = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", "", t)
    t = re.sub(r"<br\s*/?>|</(p|div|li|h\d|tr|pre|code)>", "\n", t, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t)).replace("\xa0", " ")
    t = re.sub(r"[ \t\r]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t)


def parse_day(s):
    """'Mondays' / '1st and 3rd Mondays' / '1st Thursday ... & 3rd Thursday'
    -> (BYDAY two-letter, rrule-or-None)."""
    s_l = s.lower()
    m = re.search(r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*", s_l)
    if not m:
        return None, None
    day = DAY_WORDS[m.group(1)]
    nths = [ORD[o] for o in re.findall(r"\b(1st|2nd|3rd|4th|5th|last)\b", s_l)]
    if nths:
        return day, "FREQ=MONTHLY;BYDAY=" + ",".join(f"{n}{day}" for n in nths)
    return day, None


def parse_time(s):
    """'7-9 p.m' / '@7:00 PM' / '6pm' / '@ 6:00' -> 'HH:MM' (bare hours are PM)."""
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(?:-\s*\d{1,2}(?::\d{2})?\s*)?([ap])?\.?\s*m?\b",
                  s, re.I)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "p" and h < 12:
        h += 12
    elif ap == "a" and h == 12:
        h = 0
    elif not ap and 1 <= h <= 11:
        h += 12
    return f"{h:02d}:{mi:02d}"


def clean_address(*parts):
    parts = [re.sub(r"\s+", " ", p).strip(" ,") for p in parts if p and p.strip(" ,")]
    a = ", ".join(parts)
    a = re.sub(r"\bPDX\b", "Portland, OR", a)
    a = re.sub(r",?\s+(OR|WA),?\s+(\d{5})", r", \1 \2", a, flags=re.I)
    return a


def row(company, venue, day, time_, rrule=None, address="", start_date=None):
    venue = re.sub(r"\s+", " ", venue).strip()
    venue = NAME_OVERRIDES.get((company, venue), venue)
    return {"company": company, "venue": venue, "day": day, "time": time_,
            "rrule": rrule, "address": address or ADDRESS_OVERRIDES.get((company, venue), ""),
            "start_date": start_date}


# ── Scrapers ────────────────────────────────────────────────────────────────

def scrape_lastcall():
    co = "Last Call Trivia"
    venues, page = [], 1
    while True:
        r = get("https://lastcalltrivia.com/wp-json/wp/v2/lct_venue",
                params={"lct_venue_region": 2655, "per_page": 100, "page": page})  # 2655 = portland
        venues += r.json()
        if page >= int(r.headers.get("X-WP-TotalPages", 1)):
            break
        page += 1
    out = []
    for v in venues:
        if "lct_game_type-trivia" not in v.get("class_list", []):
            continue  # music bingo / feud
        t = html_to_text(get(v["link"]).text)
        m = re.search(r"Join Game\n\s*(\w+)\n\s*at\n\s*([\d:]+\s*[ap]m)\n.*?\nTrivia Night\n(.*?)\n\s*Grab a table",
                      t, re.S)
        if not m:
            print(f"  [lastcall] couldn't parse {v['link']}")
            continue
        day, rrule = parse_day(m.group(1))
        addr_lines = [l for l in m.group(3).split("\n") if l.strip()]
        name = html.unescape(v["title"]["rendered"])
        name = re.sub(r"[,\s]*\bTrivia$", "", name).strip()
        out.append(row(co, name, day, parse_time(m.group(2)), rrule, clean_address(*addr_lines)))
        time.sleep(0.2)
    return out


def scrape_gwd():
    from playwright.sync_api import sync_playwright
    co = "Geeks Who Drink"
    # Portland metro bounding box
    n, s, w, e = 45.80, 45.15, -123.25, -122.25
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        nonce = []
        pg.on("request", lambda r: nonce.append(re.search(r"nonce=(\w+)", r.url).group(1))
              if "mb_display_mapped_events" in r.url else None)
        pg.goto("https://www.geekswhodrink.com/venues/?search=Portland%2C+OR", wait_until="domcontentloaded")
        for _ in range(40):
            if nonce:
                break
            pg.wait_for_timeout(1000)
        if not nonce:
            b.close()
            raise RuntimeError("no venue-map nonce captured")
        url = ("https://www.geekswhodrink.com/wp-admin/admin-ajax.php?action=mb_display_mapped_events"
               f"&bounds%5BnorthLat%5D={n}&bounds%5BsouthLat%5D={s}&bounds%5BwestLong%5D={w}"
               f"&bounds%5BeastLong%5D={e}&days=&brands=&nonce={nonce[0]}&search=&startLat=45.52"
               f"&startLong=-122.68&searchInit=false&tlCoord=&brCoord=&tlMapCoord=%5B{w}%2C%20{n}%5D"
               f"&brMapCoord=%5B{e}%2C%20{s}%5D&hasAll=false")
        t = pg.evaluate("u => fetch(u).then(r => r.text())", url)
        b.close()

    out = []
    for m in re.finditer(r'<a id="quizBlock-(\d+)"[^>]*data-title="([^"]*)"[^>]*data-address="([^"]*)"'
                         r' data-brand="([^"]*)" data-day="([^"]*)">(.*?)</a>', t, re.S):
        vid, title, addr, brand, day_s, body = m.groups()
        # gwd = classic, sbt = Small Batch, jbl = Jeopardy! Bar League. Skipped:
        # bng (Boombox Bingo) and qfac (occasional Quiz for a Cause nights).
        if brand not in ("gwd", "sbt", "jbl"):
            continue
        title = html.unescape(title)
        start = None
        sm = re.search(r"\s*\(Starts on (\w+ \d+)!?\)", title)
        if sm:
            title = title[:sm.start()].strip()
            d = datetime.strptime(f"{sm.group(1)} {date.today().year}", "%B %d %Y").date()
            if d < date.today():
                d = d.replace(year=d.year + 1)
            start = d.isoformat()
        day, rrule = parse_day(day_s)
        tm = re.search(r'data-time="([^"]+)"', body)
        if tm:
            # GWD stores local wall-clock times and renders them as America/Denver
            # for every visitor, so Denver is the correct conversion here.
            t_local = (datetime.strptime(tm.group(1), "%Y-%m-%dT%H:%M:%S+0000")
                       .replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Denver")))
            time_ = t_local.strftime("%H:%M")
        else:
            # Alternate-week nights have no data-time; the venue page spells it out
            # ("1st Thursday at 7:30 pm & 3rd Thursday at 7:30 pm").
            vt = html_to_text(get(f"https://www.geekswhodrink.com/venues/{vid}").text)
            sched = re.search(r"\n\s*((?:1st|2nd|3rd|4th|5th|last)[^\n]*\bat\b[^\n]*)\n", vt, re.I)
            if not sched:
                print(f"  [gwd] no time for {title}")
                continue
            day, rrule = parse_day(sched.group(1))
            time_ = parse_time(sched.group(1))
        out.append(row(co, title, day, time_, rrule, clean_address(html.unescape(addr)), start))
    return out


def scrape_bridgetown():
    from playwright.sync_api import sync_playwright
    co = "Bridgetown Trivia"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 1200})
        pg.goto("https://www.bridgetowntrivia.com/schedule", wait_until="networkidle")
        blocks = pg.evaluate("""() => [...document.querySelectorAll('.fe-block')].map(e => {
            const r = e.getBoundingClientRect();
            return {x: r.x + r.width / 2, y: r.y + scrollY, text: e.innerText.trim()};
        }).filter(b => b.text)""")
        b.close()
    headers = [bl for bl in blocks if re.fullmatch(r"(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)days", bl["text"])]
    out = []
    for bl in blocks:
        lines = [l.strip() for l in bl["text"].split("\n") if "@" in l]
        if not lines or bl in headers:
            continue
        # The day heading is the nearest one above this block (smallest vertical
        # gap), tie-broken by horizontal alignment.
        above = [h for h in headers if h["y"] < bl["y"]]
        if not above:
            continue
        hd = min(above, key=lambda h: (bl["y"] - h["y"]) + abs(bl["x"] - h["x"]) * 0.5)
        day, rrule = parse_day(hd["text"])
        for l in lines:
            name, _, rest = l.partition("@")
            name = re.sub(r"\s*-\s*in\s+McMinnville", " (McMinnville)", name.strip())
            out.append(row(co, name, day, parse_time(rest), rrule))
    return out


def scrape_untapped():
    co = "Untapped Trivia"
    t = html_to_text(get("https://untappedtrivia.com/join").text)
    sched_re = r"((?:(?:1st|2nd|3rd|4th)\s*(?:and|&)\s*(?:1st|2nd|3rd|4th)\s+)?(?:Every\s+)?\w+days?)"
    out, names = [], []
    # Main listing ("1st and 3rd Mondays, 7-9 p.m Paydirt Bar") first, then the
    # footer index ("1st & 3rd Thursdays, 6-8 p.m.\n Back 2 Earth"), which
    # catches venues missing from the main listing. Both name the same venues
    # slightly differently, so dedupe fuzzily.
    patterns = [sched_re + r",\s*(\d[\d:\-]*\s*p\.?\s*m\.?)\s+([^\n]+)\n",
                r"\n\s*" + sched_re + r"(?:,\s*([\d:\-]+\s*p\.?\s*m\.?))?\s*\n\s*([^\n]+)"]
    for pat in patterns:
        for m in re.finditer(pat, t, re.I):
            day, rrule = parse_day(m.group(1))
            name = re.sub(r"\s+Portland$", "", m.group(3).strip())
            if not day or "trivia" in name.lower() or any(same_venue(name, n) for n in names):
                continue
            names.append(name)
            out.append(row(co, name, day, parse_time(m.group(2) or ""), rrule))
    return out


def scrape_shanrock():
    co = "ShanRock's Trivia"
    t = html_to_text(get("https://shanrockstrivia.com/").text)
    i = t.find("WEEKLY QUIZZERY SCHEDULE")
    if i < 0:
        raise RuntimeError("schedule sidebar not found")
    out = []
    for m in re.finditer(r"(\w+days)\s*@\s*([\d:]+)\s*\n\s*([^\n]+)\n", t[i:]):
        day, rrule = parse_day(m.group(1))
        out.append(row(co, m.group(3).strip(), day, parse_time(m.group(2)), rrule))
    return out


def scrape_ripcity():
    co = "Rip City Trivia"
    h = get("https://www.ripcitytrivia.com/").text
    out = []
    for m in re.finditer(r"<h4[^>]*>(.*?)</h4>\s*<pre[^>]*>(.*?)</pre>", h, re.S):
        name = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        sched = html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))
        for seg in re.split(r"\s{3,}", sched.strip()):
            if not seg or "bingo" in seg.lower():
                continue
            day, rrule = parse_day(seg)
            if day:
                out.append(row(co, name, day, parse_time(seg.split("@")[-1]), rrule))
    return out


def scrape_rainbrain():
    co = "Rain Brain Trivia"
    t = html_to_text(get("https://rainbraintrivia.weebly.com/").text)
    out = []
    for m in re.finditer(r"\*\s*Trivia\s+(\w+days)[^\n]*\n\s*(\d[\d:]*\s*[ap]m)\s+at\s+([^,\n]+),\s*([^\n]+)",
                         t, re.I):
        day, rrule = parse_day(m.group(1))
        addr = clean_address(m.group(4).replace(", pdx", ", PDX"))
        out.append(row(co, m.group(3).strip(), day, parse_time(m.group(2)), rrule, addr))
    return out


def scrape_double_mountain():
    co = "Double Mountain"
    t = html_to_text(get("https://doublemountainbrewery.com/events/").text)
    t = t.replace("\n", " / ")
    out, seen = [], set()
    for m in re.finditer(r"(\w+) / (\w+ \d+) @ ([\d:]+ [ap]m)\s*/.*?/\s*\1 Weekly Trivia", t):
        loc, d, tm = m.groups()
        dt = datetime.strptime(f"{d} {date.today().year}", "%B %d %Y")
        day = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"][dt.weekday()]
        if loc not in seen:
            seen.add(loc)
            out.append(row(co, f"{loc} Taproom", day, parse_time(tm)))
    return out


SCRAPERS = {
    "lastcall": ("Last Call Trivia", scrape_lastcall),
    "gwd": ("Geeks Who Drink", scrape_gwd),
    "bridgetown": ("Bridgetown Trivia", scrape_bridgetown),
    "untapped": ("Untapped Trivia", scrape_untapped),
    "shanrock": ("ShanRock's Trivia", scrape_shanrock),
    "ripcity": ("Rip City Trivia", scrape_ripcity),
    "rainbrain": ("Rain Brain Trivia", scrape_rainbrain),
    "doublemountain": ("Double Mountain", scrape_double_mountain),
}


# ── Matching + calendar routing ─────────────────────────────────────────────

_STOP = {"the", "and", "trivia", "bar", "grill", "co", "company", "pub", "at", "on",
         "in", "mcmenamins", "music", "bingo", "thursday", "sunday", "night"}


def tokens(name):
    n = name.lower().replace("’", "").replace("'", "").replace("&", " and ")
    return {w for w in re.findall(r"[a-z0-9]+", n) if w not in _STOP}


def same_venue(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.6


def route_calendar(address):
    """Pick a Trivia Nights calendar from an address. Anything outside the
    city of Portland is Further Out; Portland splits by street quadrant."""
    if "portland" not in address.lower():
        return FURTHER
    d = re.search(r"^\s*\d+\s+(N|NE|SE|NW|SW|S|E|W|North|Northeast|Southeast|Northwest|Southwest)\b",
                  address, re.I)
    q = (d.group(1).upper() if d else "")
    q = {"NORTH": "N", "NORTHEAST": "NE", "SOUTHEAST": "SE",
         "NORTHWEST": "NW", "SOUTHWEST": "SW"}.get(q, q)
    if q in ("SE", "E"):
        return SE
    if q in ("N", "NE"):
        return NNE
    if q in ("NW", "SW", "S", "W"):
        return NWSW
    return None


def merge(schedule, scraped_by_co):
    """Return (new_schedule, report_lines). Keeps the schedule's existing order:
    updated entries stay in place and new venues go after their company's last
    entry, so diffs of trivia_schedule.json show only real changes."""
    report = []
    updated = {}   # id(json entry) -> new entry, or None if removed
    adds = {}      # company -> [new entries]
    for co in sorted({e["company"] for e in schedule} | set(scraped_by_co)):
        cur = [e for e in schedule if e["company"] == co]
        if co not in scraped_by_co:
            continue
        site = list(scraped_by_co[co])
        cost = COMPANY_COST.get(co)
        lines = []
        matched = {}  # id(json entry) -> scraped row
        # Pass 1: same venue on the same day; pass 2: same venue, day changed.
        for same_day in (True, False):
            for e in cur:
                if id(e) in matched:
                    continue
                for s in site:
                    if (s["day"] == e["day"]) == same_day and same_venue(e["venue"], s["venue"]):
                        matched[id(e)] = s
                        site.remove(s)
                        break
        for e in cur:
            s = matched.get(id(e))
            if not s:
                lines.append(f"  REMOVE  {e['day']} {e['time']}  {e['venue']}")
                updated[id(e)] = None
                continue
            new = dict(e)
            new["day"] = s["day"]
            if s["time"]:
                new["time"] = s["time"]
            if s["rrule"]:
                new["rrule"] = s["rrule"]
            else:
                new.pop("rrule", None)
            if s["start_date"]:
                new["start_date"] = s["start_date"]
            else:
                new.pop("start_date", None)
            if cost:
                new["cost"] = cost
            else:
                new.pop("cost", None)
            if not new.get("address") and s["address"]:
                new["address"] = s["address"]
            changes = [f"{k}: {e.get(k)!s} -> {new.get(k)!s}"
                       for k in ("day", "time", "rrule", "start_date", "cost", "address")
                       if e.get(k) != new.get(k)]
            if changes:
                lines.append(f"  CHANGE  {e['venue']}  ({'; '.join(changes)})")
            routed = route_calendar(new.get("address", ""))
            if routed and routed != new["calendar"]:
                # Reported only -- the JSON calendar may be a deliberate call.
                lines.append(f"  NOTE    {e['venue']} is on {new['calendar']} but its address "
                             f"routes to {routed}")
            updated[id(e)] = new
        for s in site:
            addr = s["address"]
            cal = route_calendar(addr) if addr else None
            if not cal:
                lines.append(f"  SKIP    {s['day']} {s['time']}  {s['venue']}  "
                             f"-- needs {'an address' if not addr else 'a calendar'} "
                             f"(add to ADDRESS_OVERRIDES)")
                continue
            new = {"venue": s["venue"], "address": addr, "company": co,
                   "company_url": COMPANY_URLS.get(co, ""), "day": s["day"],
                   "time": s["time"] or "19:00", "calendar": cal}
            if s["rrule"]:
                new["rrule"] = s["rrule"]
            if s["start_date"]:
                new["start_date"] = s["start_date"]
            if cost:
                new["cost"] = cost
            extra = f" [{s['rrule']}]" if s["rrule"] else ""
            extra += f" starts {s['start_date']}" if s["start_date"] else ""
            lines.append(f"  ADD     {s['day']} {new['time']}  {s['venue']}  | {addr} | "
                         f"{cal.replace('Trivia Nights - ', '')}{extra}")
            adds.setdefault(co, []).append(new)
        report.append(f"\n{co}: {len(scraped_by_co[co])} on site, {len(cur)} in schedule")
        report += lines or ["  (no changes)"]

    result = []
    last_idx = {e["company"]: i for i, e in enumerate(schedule)}
    for i, e in enumerate(schedule):
        new = updated.get(id(e), e)
        if new is not None:
            result.append(new)
        if last_idx[e["company"]] == i:
            result += adds.pop(e["company"], [])
    for extra in adds.values():  # companies not yet in the schedule
        result += extra
    return result, report


def main():
    ap = argparse.ArgumentParser(description="Scrape trivia schedules and diff vs trivia_schedule.json")
    ap.add_argument("--only", help="comma-separated scrapers: " + ",".join(SCRAPERS))
    ap.add_argument("--write", action="store_true", help="apply the diff to trivia_schedule.json")
    ap.add_argument("--save", help="dump raw scraped rows to this JSON file")
    args = ap.parse_args()

    names = args.only.split(",") if args.only else list(SCRAPERS)
    scraped = {}
    for key in names:
        co, fn = SCRAPERS[key]
        print(f"Scraping {co} ...", flush=True)
        try:
            rows = fn()
        except Exception as ex:  # one site being down shouldn't sink the rest
            print(f"  ERROR: {ex!r} -- leaving {co} unchanged")
            continue
        if not rows:
            print(f"  WARNING: 0 venues parsed -- leaving {co} unchanged (site layout change?)")
            continue
        print(f"  {len(rows)} trivia nights")
        scraped[co] = rows

    if args.save:
        Path(args.save).write_text(json.dumps(scraped, indent=1, ensure_ascii=False), encoding="utf-8")

    schedule = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    new_schedule, report = merge(schedule, scraped)
    print("\n".join(report))
    print(f"\nSchedule: {len(schedule)} -> {len(new_schedule)} entries")

    if args.write:
        SCHEDULE.write_text(json.dumps(new_schedule, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {SCHEDULE.name}. Next: python trivia_generate.py --dry-run")
    else:
        print("(dry run -- pass --write to update trivia_schedule.json)")


if __name__ == "__main__":
    main()
