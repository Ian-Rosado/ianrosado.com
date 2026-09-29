"""
Scraper for Tunnel Vision PDX — a weekly guide to Portland's underground:
DIY shows, weird rituals, maker nights, clown festivals, oddball screenings.
URL: https://tunnelvisionpdx.com/  (beehiiv newsletter, new issue every Thursday)
Format: Static HTML. The public "extended cut" of each issue lists ~100 events as
        paragraphs of the same shape:

          <strong>Title</strong> <em>Sep 25 at 19:30</em> Venue | $12+ [ <a>more</a> ] blurb

        grouped under section headings like "[ SEEING ]" or "[ SCREENINGS ]".
        Screenings drop the price: "<strong>Title</strong> (1977) <em>Sep 24</em> Venue [ more ]".
Calendar: events

We read the two newest issues (the latest can still list last weekend) and keep
dated listings only. Travel/outdoor sections ([ ROAMING ], [ DRIVING ],
[ STARGAZING ] ...) describe places rather than events and are skipped, as are
listings with no concrete date ("daylight, year round", "open through Oct 31").
"""

import html
import re
from datetime import date, timedelta

from .base import get_page, make_event, parse_cost, CALENDAR_EVENTS

SOURCE = "Tunnel Vision PDX"
BASE = "https://tunnelvisionpdx.com"
ISSUES_TO_READ = 2

# Section heading -> tags. Sections not listed here are skipped.
SECTIONS = {
    "SEEING": ["performance", "arts"],
    "LISTENING + DANCING": ["music", "dance"],
    "MAKING + DOING": ["workshop", "community"],
    "EATING + SHOPPING": ["food", "market"],
    "SCREENINGS": ["film"],
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_T = r"(\d{1,2}:\d{2}|noon|midnight)"


def _clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _hhmm(t):
    t = t.lower()
    if t == "noon":
        return "12:00"
    if t == "midnight":
        return "00:00"
    h, m = t.split(":")
    return f"{int(h):02d}:{m}"


def _to_date(mon, day):
    """Month abbrev + day -> date, choosing the year so it isn't long past."""
    today = date.today()
    d = date(today.year, MONTHS[mon[:3].lower()], int(day))
    if d < today - timedelta(days=60):
        d = d.replace(year=today.year + 1)
    return d


def parse_when(s):
    """Parse a Tunnel Vision date phrase.

    Returns a list of (date, time, end_time, end_date) tuples, one per
    occurrence; [] when there's no concrete date (ongoing/vague listings)."""
    s = s.strip().lower()
    m = re.match(_MON + r"\s+(\d{1,2})\b", s)
    if not m:
        return []
    mon, day = m.group(1), m.group(2)
    rest = s[m.end():]
    first = _to_date(mon, day)

    # Multi-day span: "Sep 17–19", "Sep 17 through 20", "Oct 2 through Oct 5"
    r = re.match(r"\s*(?:–|-|through)\s*(?:" + _MON + r"\s+)?(\d{1,2})\b", rest)
    if r:
        end = _to_date(r.group(1) or mon, r.group(2))
        if end < first:
            end = end.replace(year=end.year + 1)
        return [(first, "", "", end)]

    # Extra occurrences: "Sep 25 at 19:30, also Sep 26 at 19:30 and Sep 27 at 14:00"
    also = [(_to_date(a, b), _hhmm(t)) for a, b, t in
            re.findall(_MON + r"\s+(\d{1,2})\s+at\s+" + _T, rest)]
    # Same-month extra days: "Sep 25 & 26 at 19:30", "Sep 26 and 27, 10:00 to 16:00"
    extra_days = [int(x) for x in re.findall(r"^\s*(?:&|and)\s+(\d{1,2})\b", rest)]
    days = [first] + [_to_date(mon, x) for x in extra_days]

    # Time: prefer "show HH:MM", then "at HH:MM", then "HH:MM–HH:MM"/"HH:MM to HH:MM"
    start = end_t = ""
    show = re.search(r"show\s+" + _T, rest)
    at = re.match(r"(?:\s*(?:&|and)\s+\d{1,2})*\s*(?:,\s*)?at\s+" + _T, rest)
    span = re.search(_T + r"\s*(?:–|-|to)\s*" + _T, rest)
    if show:
        start = _hhmm(show.group(1))
    elif at:
        start = _hhmm(at.group(1))
    elif span:
        start, end_t = _hhmm(span.group(1)), _hhmm(span.group(2))
    else:
        lone = re.search(_T, rest.split("also")[0])
        if lone:
            start = _hhmm(lone.group(1))

    out = [(d, start, end_t, "") for d in days]
    out += [(d, t, "", "") for d, t in also if d not in days]
    return out


def _issue_urls():
    resp = get_page(f"{BASE}/archive", timeout=25)
    if not resp:
        return []
    posts = set(re.findall(r'href="(/p/issue-(\d+)[^"]*)"', resp.text))
    newest = sorted(posts, key=lambda p: int(p[1]), reverse=True)[:ISSUES_TO_READ]
    return [BASE + p[0] for p in newest]


def parse_issue(page_html):
    """Yield event dicts from one issue's HTML."""
    section = None
    # Walk h4 headings and paragraphs in document order. Section headings are
    # usually <h4>, but some ("[ SCREENINGS ]", "[ BULLETIN BOARD ]") are plain
    # paragraphs whose whole text is the bracketed label.
    for m in re.finditer(r"<h4[^>]*>(.*?)</h4>"
                         r"|<p class=\"dream-post-content-paragraph[^\"]*\">(.*?)</p>",
                         page_html, re.S):
        block = m.group(1) if m.group(1) is not None else m.group(2)
        label = re.fullmatch(r"\[\s*([^\]]+?)\s*\]", _clean(block))
        if label:
            section = re.sub(r"\s+", " ", label.group(1)).upper()
            continue
        if m.group(1) is not None or section not in SECTIONS:
            continue
        # Formatting spans wrap text inconsistently between issues — drop them.
        para = re.sub(r"</?span[^>]*>", "", block)
        pm = re.match(r"\s*<strong>(.*?)</strong>(.*?)<em>(.*?)</em>(.*?)"
                      r"\[\s*<a href=\"([^\"]+)\"", para, re.S)
        if not pm:
            continue
        title = _clean(pm.group(1))
        year = re.search(r"\((\d{4})\)", _clean(pm.group(2)))
        if year:  # screenings: "Suspiria (1977)"
            title = f"{title} ({year.group(1)})"
        venue_price = _clean(pm.group(4))
        venue, _, price = venue_price.partition("|")
        venue = re.sub(r",\s*(presented with|in \d+mm|hosted by|with)\b.*$", "", venue.strip(), flags=re.I)
        price = price.strip()
        cost = "" if price.lower() in ("", "see info") else parse_cost(price)
        for d, t, et, ed in parse_when(_clean(pm.group(3))):
            yield make_event(
                title=title,
                date=d.isoformat(),
                time=t,
                end_time=et,
                end_date=ed.isoformat() if ed else "",
                location=venue,
                cost=cost,
                url=html.unescape(pm.group(5)),
                tags=SECTIONS[section] + (["free"] if cost == "Free" else []),
                calendar=CALENDAR_EVENTS,
                source=SOURCE,
            )


def scrape():
    events, seen = [], set()
    today = date.today().isoformat()
    for url in _issue_urls():
        resp = get_page(url, timeout=25)
        if not resp:
            continue
        for e in parse_issue(resp.text):
            key = (e["title"].lower(), e["date"], e["time"])
            if key in seen or (e["end_date"] or e["date"]) < today:
                continue
            seen.add(key)
            events.append(e)
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
