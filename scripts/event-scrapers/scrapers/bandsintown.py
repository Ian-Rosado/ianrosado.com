"""
Scraper for Bandsintown — Portland concerts
URL: https://www.bandsintown.com/c/portland-or

Bandsintown is JS-rendered and behind Cloudflare. The previous version parsed
obfuscated DOM (artist/venue from /e/ slugs, date/time from container text). That
broke twice: (1) the page stopped exposing `<a href="/e/...">` links, and (2) the
date was read from a walked-up ancestor that could span multiple cards, so a
promo/"popular artists" block collapsed many events onto one shared date.

This version instead drives the site's own JSON pagination endpoint:
  /all-dates/fetch-next/upcomingEvents?page=N&longitude=..&latitude=..
Each event arrives as structured JSON with its own `startsAt`/`endsAt`,
`artistName`, `venueName`, `locationText`, and `eventUrl` — so every event keeps
its real date. The endpoint is Cloudflare-protected, so we call it from inside a
Playwright page context (which has already cleared the challenge) rather than with
plain requests (which gets a 403 "Just a moment..." page).

Calendar: music (concerts)
"""

import re
import asyncio
from datetime import date, datetime

from .base import make_event, multiday_end_date, CALENDAR_MUSIC

SOURCE = "Bandsintown"
CITY_URL = "https://www.bandsintown.com/c/portland-or"

# Portland, OR coordinates used by the city page's fetch-next endpoint.
LONGITUDE = "-122.67621"
LATITUDE = "45.52345"
FETCH_NEXT = (
    "https://www.bandsintown.com/all-dates/fetch-next/upcomingEvents"
    "?page=%d&longitude=" + LONGITUDE + "&latitude=" + LATITUDE
)
MAX_PAGES = 30  # safety cap; endpoint returns ~36/page, stops on empty

PLAYWRIGHT_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
PLAYWRIGHT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Only keep events in Oregon / SW Washington — the distance-sorted feed bleeds
# into other states on later pages.
KEEP_REGION = ("OR", "WA")


def _iso_date_time(value: str) -> tuple[str, str]:
    """'2026-06-23T17:30:00' -> ('2026-06-23', '17:30'). Missing/garbage -> ('','')."""
    if not value:
        return "", ""
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except (ValueError, TypeError):
        return "", ""


def _location(venue: str, loc_text: str) -> str:
    """Combine venue + 'City, ST' without duplicating the venue name."""
    venue = (venue or "").strip()
    loc_text = (loc_text or "").strip()
    if venue and loc_text and loc_text.lower() not in venue.lower():
        return f"{venue}, {loc_text}"
    return venue or loc_text


def _in_region(loc_text: str) -> bool:
    """True if 'City, ST' ends with a kept state code (OR / WA)."""
    if not loc_text:
        return True  # keep when unknown rather than silently drop
    state = loc_text.rsplit(",", 1)[-1].strip().upper()
    return state in KEEP_REGION


async def _fetch() -> list:
    from playwright.async_api import async_playwright

    raw_events = []
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
            # Load the city page once so the page context clears Cloudflare and
            # carries the cookies needed by the fetch-next endpoint.
            await page.goto(CITY_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4000)

            fetch_js = """async (url) => {
                const r = await fetch(url, {headers: {'Accept': 'application/json'}});
                return {status: r.status, body: await r.text()};
            }"""

            import json as _json
            for page_num in range(1, MAX_PAGES + 1):
                res = await page.evaluate(fetch_js, FETCH_NEXT % page_num)
                if res["status"] != 200:
                    print(f"  [{SOURCE}] page {page_num} HTTP {res['status']}, stopping")
                    break
                try:
                    data = _json.loads(res["body"])
                except ValueError:
                    print(f"  [{SOURCE}] page {page_num} non-JSON response, stopping")
                    break
                events = data.get("events") or []
                if not events:
                    break
                raw_events.extend(events)
                if not data.get("urlForNextPageOfEvents"):
                    break

            await browser.close()
    except Exception as e:
        print(f"  [{SOURCE}] Error: {e}")

    return raw_events


# Park / waterfront venues host multi-act festivals (acts spread across the day,
# each its own set) — those stay as separate events. Everywhere else, multiple
# acts at the same venue + date within a couple hours are one show's bill.
_FESTIVAL_VENUE_RE = re.compile(r"\bpark\b|waterfront", re.I)
_SAME_SHOW_GAP_MIN = 120


def _to_minutes(t):
    m = re.match(r"^(\d{1,2}):(\d{2})$", t or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _merge_cluster(cluster):
    """Combine several acts at one show into a single event with all names in
    the title, the earliest start, and the latest known end."""
    acts = []
    for e in cluster:
        if e["title"] not in acts:
            acts.append(e["title"])
    starts = [e["time"] for e in cluster if e["time"]]
    ends = [e["end_time"] for e in cluster if e["end_time"]]
    rep = cluster[0]  # earliest by time — carries venue + a valid event URL
    return make_event(
        title=", ".join(acts),
        date=rep["date"],
        time=min(starts) if starts else "",
        end_time=max(ends) if ends else "",
        location=rep["location"],
        url=rep["url"],
        tags=["music", "concert"],
        calendar=CALENDAR_MUSIC,
        source=SOURCE,
    )


def _merge_co_bills(events):
    """Bandsintown lists each act of a multi-act bill as its own event. Collapse
    the acts of one show (same venue + date, starts within ~2h) into a single
    combined-title event. Festival/park venues are left as separate events."""
    from collections import defaultdict
    groups = defaultdict(list)
    for e in events:
        venue = e["location"].split(",")[0].strip().lower()
        groups[(venue, e["date"])].append(e)

    merged = []
    for (venue, date), evs in groups.items():
        if len(evs) == 1:
            merged.append(evs[0])
            continue
        # Festivals: keep every act as its own event.
        if _FESTIVAL_VENUE_RE.search(evs[0]["location"]) or len(evs) > 6:
            merged.extend(evs)
            continue
        # Cluster by start-time gaps; a gap > 2h starts a new (separate) show.
        evs.sort(key=lambda e: (_to_minutes(e["time"]) if _to_minutes(e["time"]) is not None else 9999))
        clusters, cur, last = [], [], None
        for e in evs:
            m = _to_minutes(e["time"])
            if cur and m is not None and last is not None and m - last > _SAME_SHOW_GAP_MIN:
                clusters.append(cur)
                cur = []
            cur.append(e)
            if m is not None:
                last = m
        if cur:
            clusters.append(cur)
        for cl in clusters:
            merged.append(cl[0] if len(cl) == 1 else _merge_cluster(cl))
    return merged


def scrape():
    raw = asyncio.run(_fetch())

    today = date.today()
    seen = set()
    out = []
    skipped_region = 0
    for ev in raw:
        if ev.get("streamingEvent"):
            continue  # livestreams aren't local events
        loc_text = ev.get("locationText", "")
        if not _in_region(loc_text):
            skipped_region += 1
            continue

        date_str, time_str = _iso_date_time(ev.get("startsAt", ""))
        if not date_str:
            continue  # never emit an event without a real date
        _, end_time = _iso_date_time(ev.get("endsAt", ""))

        # Multi-day festivals span date..end_date; the helper is conservative so
        # a normal show ending after midnight is never treated as multi-day.
        def _iso_dt(v):
            try:
                return datetime.fromisoformat(v)
            except (ValueError, TypeError):
                return None
        end_date = multiday_end_date(_iso_dt(ev.get("startsAt", "")), _iso_dt(ev.get("endsAt", "")))

        try:
            if date.fromisoformat(date_str) < today:
                continue
        except ValueError:
            continue

        artist = (ev.get("artistName") or "").strip()
        if not artist:
            continue

        key = (artist.lower()[:50], date_str)
        if key in seen:
            continue
        seen.add(key)

        out.append(make_event(
            title=artist,
            date=date_str,
            time=time_str,
            end_time=end_time,
            end_date=end_date,
            location=_location(ev.get("venueName", ""), loc_text),
            url=(ev.get("eventUrl") or "").split("?")[0],
            tags=["music", "concert"],
            calendar=CALENDAR_MUSIC,
            source=SOURCE,
        ))

    before_merge = len(out)
    out = _merge_co_bills(out)
    merged_n = before_merge - len(out)

    out.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    extra = f" ({skipped_region} skipped: out of region)" if skipped_region else ""
    if merged_n:
        extra += f" ({merged_n} co-bill act(s) merged)"
    print(f"  [{SOURCE}] Found {len(out)} events{extra}")
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
