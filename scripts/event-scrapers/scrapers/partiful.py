"""
Scraper for Partiful — Portland public events.
Calendar: events (social gatherings, parties, mixers, meetups)

Partiful has no Portland "region" on the web. Its discover feed (the curated
carousels the app shows) only exists for a fixed set of cities — verified by
probing the site's own region endpoint:

    https://partiful.com/_next/data/<buildId>/explore/<region>.json

which returns 200 for NYC / LA / SF / ATX / CHI / MIA and **404 for pdx /
portland / seattle / pnw**. Even Partiful's own geolocation endpoint (/api/geo)
correctly detects a Portland visitor yet serves no Portland feed. So there is no
on-platform way to *discover* Portland events like the app does — the app's
"local" feed is a native-app-only geo feature we can't reach from the web.

What IS reachable: every individual event page (partiful.com/e/<id>) is fully
public and server-rendered, with the complete event embedded as JSON in the
page's __NEXT_DATA__ (title, structured location w/ venue name + address,
startDate/endDate in UTC, timezone, isPublic, status). Plain requests — no
Playwright needed. So this scraper solves discovery from *outside* Partiful and
reuses one detail parser for everything:

  1. Inbox (primary, robust) — URLs/IDs Ian collects from the app during the
     week, one per line in `partiful_inbox.txt` (mirrors the IG-ingest flow).
     Trusted: kept even if the event hides its address.
  2. Search seed (best-effort) — a `site:partiful.com` DuckDuckGo query for
     Portland, to surface public events Google/DDG has indexed. Auto-discovered,
     so filtered to Portland-metro addresses.
  3. Region reader (dormant) — reads the PDX region endpoint above. It 404s
     today, so it contributes nothing; if Partiful ever launches a Portland
     region, this lights up automatically with no code change.

Each source yields Partiful event objects (fetched per-URL in parallel for 1 & 2,
embedded directly for 3); one `_build_from_event()` normalizes them all.
"""

import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from pathlib import Path
from urllib.parse import unquote

import requests

from .base import HEADERS, get_page, make_event, multiday_end_date, CALENDAR_EVENTS

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

SOURCE = "Partiful"
EVENT_URL = "https://partiful.com/e/{id}"
EXPLORE_URL = "https://partiful.com/explore"
REGION_DATA_URL = "https://partiful.com/_next/data/{build}/explore/{region}.json"
PDX_REGION = "pdx"  # dormant — 404s until Partiful launches a Portland region

INBOX_FILE = Path(__file__).resolve().parent.parent / "partiful_inbox.txt"

MAX_DETAIL_FETCHES = 80   # politeness cap on per-event page fetches
SEARCH_MAX = 40           # cap on search-discovered ids

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)
# partiful.com/e/<id>  (id is Firestore-style, letters/digits)
_EVENT_ID_RE = re.compile(r"partiful\.com/e/([A-Za-z0-9_-]+)")

# Portland metro — used to keep only local events from auto-discovered sources.
_METRO_RE = re.compile(
    r",\s*OR\b|\bOregon\b|\b(?:Portland|Beaverton|Hillsboro|Gresham|Tigard|"
    r"Tualatin|Lake\s+Oswego|Milwaukie|Oregon\s+City|Happy\s+Valley|West\s+Linn|"
    r"Wilsonville|Clackamas|Fairview|Troutdale|Vancouver,\s*WA)\b",
    re.I,
)


# ── event id / url handling ─────────────────────────────────────────────────

def _event_id(token):
    """Extract a bare Partiful event id from a URL, /e/<id>, or bare id."""
    token = (token or "").strip().strip('"').strip("'")
    if not token:
        return ""
    m = _EVENT_ID_RE.search(token)
    if m:
        return m.group(1)
    if "/" in token:
        token = token.rstrip("/").rsplit("/", 1)[-1]
    return token.split("?")[0].split("#")[0]


# ── detail fetch + normalization ────────────────────────────────────────────

def _fetch_event(event_id):
    """Fetch one event page and return its embedded event dict, or None."""
    resp = get_page(EVENT_URL.format(id=event_id))
    if not resp:
        return None
    resp.encoding = "utf-8"  # pages are UTF-8; requests otherwise guesses latin-1
    m = _NEXT_DATA_RE.search(resp.text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    ev = (data.get("props", {}).get("pageProps", {}) or {}).get("event")
    return ev or None


def _local_dt(iso_utc, tz):
    """UTC ISO ('...Z' or with offset) -> aware datetime in the event's tz."""
    if not iso_utc:
        return None
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ZoneInfo is not None:
        try:
            return dt.astimezone(ZoneInfo(tz or "America/Los_Angeles"))
        except Exception:
            pass
    return dt


def _location(loc_info):
    """Build 'Venue, address' from Partiful's structured locationInfo."""
    if not isinstance(loc_info, dict):
        return ""
    maps = loc_info.get("mapsInfo") or {}
    name = (maps.get("name") or "").strip()
    lines = loc_info.get("displayAddressLines") or maps.get("addressLines") or []
    addr = ", ".join(x.strip() for x in lines if x and x.strip())
    if name and addr and name.lower() not in addr.lower():
        return f"{name}, {addr}"
    return name or addr or (maps.get("approximateLocation") or "").strip()


def _build_from_event(ev, trusted):
    """Normalize a Partiful event object into the pipeline schema, or None.

    trusted=True (inbox / region feed) keeps events even when the address is
    hidden; trusted=False (search) requires a Portland-metro location so a
    stray non-local hit can't slip in.
    """
    if not isinstance(ev, dict):
        return None
    if ev.get("isPublic") is False or ev.get("status") not in (None, "PUBLISHED"):
        return None

    title = (ev.get("title") or "").strip()
    if not title:
        return None

    start = _local_dt(ev.get("startDate"), ev.get("timezone"))
    if not start:
        return None  # never emit an event without a real date
    end = _local_dt(ev.get("endDate"), ev.get("timezone"))

    location = _location(ev.get("locationInfo"))
    if not trusted and not _METRO_RE.search(location):
        return None

    end_date = multiday_end_date(start, end)
    eid = ev.get("id") or ""

    return make_event(
        title=title,
        date=start.strftime("%Y-%m-%d"),
        time=start.strftime("%H:%M"),
        end_time=end.strftime("%H:%M") if end else "",
        end_date=end_date,
        location=location,
        url=EVENT_URL.format(id=eid) if eid else "",
        tags=[],  # Partiful exposes no reliable category tags
        calendar=CALENDAR_EVENTS,
        source=SOURCE,
    )


# ── discovery source 1: inbox file ──────────────────────────────────────────

def _inbox_ids():
    """Event ids from partiful_inbox.txt (one URL/id per line, # comments)."""
    if not INBOX_FILE.exists():
        return []
    ids = []
    for line in INBOX_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        eid = _event_id(line)
        if eid:
            ids.append(eid)
    return ids


# ── discovery source 2: search seed (best-effort, DuckDuckGo HTML) ──────────

_DDG_HTML = "https://html.duckduckgo.com/html/"
_DDG_QUERIES = [
    "site:partiful.com Portland Oregon",
    "site:partiful.com PDX event",
]
# DDG wraps result links as /l/?uddg=<encoded target>
_DDG_LINK_RE = re.compile(r'href="(?:https?:)?//duckduckgo\.com/l/\?uddg=([^"&]+)')
_DDG_DIRECT_RE = re.compile(r'href="(https?://partiful\.com/e/[A-Za-z0-9_-]+)')


def _search_ids():
    ids = []
    seen = set()
    for q in _DDG_QUERIES:
        try:
            resp = requests.post(
                _DDG_HTML, data={"q": q}, headers=HEADERS, timeout=15
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [{SOURCE}] search '{q}' failed: {e}")
            continue
        targets = [unquote(m) for m in _DDG_LINK_RE.findall(resp.text)]
        targets += _DDG_DIRECT_RE.findall(resp.text)
        for t in targets:
            if "partiful.com/e/" not in t:
                continue
            eid = _event_id(t)
            if eid and eid not in seen:
                seen.add(eid)
                ids.append(eid)
                if len(ids) >= SEARCH_MAX:
                    return ids
    return ids


# ── discovery source 3: PDX region feed (dormant; 404 today) ────────────────

def _region_events():
    """Read the Portland region discover feed if Partiful ever ships one.

    Returns full event objects embedded in the feed (no per-event fetch needed).
    Today the endpoint 404s, so this returns []. When it goes live it activates
    automatically. Guarded end-to-end: any failure yields [].
    """
    try:
        page = requests.get(EXPLORE_URL, headers=HEADERS, timeout=15)
        page.raise_for_status()
        m = re.search(r'"buildId":"([^"]+)"', page.text)
        if not m:
            return []
        url = REGION_DATA_URL.format(build=m.group(1), region=PDX_REGION)
        resp = requests.get(url, headers={**HEADERS, "x-nextjs-data": "1"}, timeout=15)
        if resp.status_code != 200:
            return []  # 404 = no Portland region yet
        pp = resp.json().get("pageProps", {}) or {}
    except (requests.RequestException, ValueError):
        return []

    # Sections come as either a single trendingSection or a list of sections,
    # each with items[].event; feedItems is a flat fallback list.
    sections = pp.get("sections") or []
    if pp.get("trendingSection"):
        sections = [pp["trendingSection"]] + list(sections)
    events = []
    for sec in sections:
        for item in (sec.get("items") or []):
            ev = item.get("event") if isinstance(item, dict) else None
            if ev:
                events.append(ev)
    for item in (pp.get("feedItems") or []):
        ev = item.get("event") if isinstance(item, dict) else None
        if ev:
            events.append(ev)
    return events


# ── orchestration ───────────────────────────────────────────────────────────

def scrape():
    today = date.today()

    inbox_ids = _inbox_ids()
    search_ids = [i for i in _search_ids() if i not in set(inbox_ids)]

    # trust map: inbox + region are trusted; search is not.
    trust = {i: True for i in inbox_ids}
    for i in search_ids:
        trust.setdefault(i, False)

    fetch_ids = (inbox_ids + search_ids)[:MAX_DETAIL_FETCHES]

    fetched = {}
    if fetch_ids:
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(_fetch_event, i): i for i in fetch_ids}
            for fut in as_completed(futures):
                eid = futures[fut]
                try:
                    fetched[eid] = fut.result()
                except Exception:
                    fetched[eid] = None

    out = []
    seen = set()

    def _add(ev, trusted):
        built = _build_from_event(ev, trusted)
        if not built:
            return
        eid = _event_id(built["url"]) or built["title"].lower()[:50]
        if eid in seen:
            return
        try:
            if built["date"] and date.fromisoformat(built["date"]) < today:
                return
        except ValueError:
            pass
        seen.add(eid)
        out.append(built)

    for eid in fetch_ids:
        ev = fetched.get(eid)
        if ev:
            _add(ev, trust.get(eid, False))

    region_events = _region_events()
    for ev in region_events:
        _add(ev, True)

    out.sort(key=lambda e: (e.get("date", ""), e.get("time", "")))
    n_search = sum(1 for e in out if not trust.get(_event_id(e["url"]), False)
                   and _event_id(e["url"]) in set(search_ids))
    print(
        f"  [{SOURCE}] Found {len(out)} events "
        f"({len(inbox_ids)} inbox, {len(search_ids)} search seed, "
        f"{len(region_events)} region)"
    )
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        # Quick single-event test: python -m scrapers.partiful <url-or-id> ...
        for tok in sys.argv[1:]:
            ev = _fetch_event(_event_id(tok))
            print(json.dumps(_build_from_event(ev, True), indent=2, ensure_ascii=False))
    else:
        print(json.dumps(scrape(), indent=2, ensure_ascii=False))
