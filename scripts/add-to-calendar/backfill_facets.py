#!/usr/bin/env python3
"""
backfill_facets.py
------------------
Add extendedProperties.shared facets to events ALREADY on the Portland
calendars, so the website can filter them.

Primary source: the "Inbox" tab of the Portland Events sheet, which still has
the full tags/source/cost for every scraped event. Calendar events are matched
to sheet rows by (normalized title, date), recovering the FULL facet set
(cost, genres, age, neighborhood, tags, source).

Fallback for events with no sheet match: derive cost from the description and
genre from the "[genre]" title prefix.

Usage:
    python backfill_facets.py --dry-run          # preview, no writes
    python backfill_facets.py                     # backfill all calendars
    python backfill_facets.py --calendar comedy   # one calendar only

Auth reuses token.json / credentials.json. Requires the calendar + sheets
scopes (same as `portland_events_add.py --from-sheets`); if you get a scope
error, delete token.json and re-run.
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone

import portland_events_add as pea
from portland_events_add import (
    CALENDARS, CALENDAR_ALIASES, SHEET_ID, INBOX_TAB,
    classify_cost, build_extended_properties,
    SCOPES_CALENDAR_AND_SHEETS,
)

# Import the scraper-side tag normalizer so recovered tags get cleaned the
# same way new events do.
SCRAPERS_DIR = Path(__file__).resolve().parent.parent / "event-scrapers"
sys.path.insert(0, str(SCRAPERS_DIR))
try:
    from scrapers.base import normalize_tags
except Exception:
    def normalize_tags(tags):  # fallback: light dedupe
        seen, out = set(), []
        for t in tags or []:
            t = str(t).strip().lower()
            if t and t not in seen:
                seen.add(t); out.append(t)
        return out

# Use the combined scope so one token works for both calendar + sheets.
pea.SCOPES = SCOPES_CALENDAR_AND_SHEETS


# ── Auth (one creds → calendar service + gspread client) ────────────────────

def get_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    token_path = Path("token.json")
    creds_path = Path("credentials.json")
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES_CALENDAR_AND_SHEETS)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES_CALENDAR_AND_SHEETS)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return creds


# ── Title normalization for matching ────────────────────────────────────────

def norm_title(title: str) -> str:
    """Strip a '[genre]' prefix, lowercase, drop punctuation, truncate."""
    t = re.sub(r"^\[[^\]]+\]\s*", "", title or "")
    return re.sub(r"[^a-z0-9]", "", t.lower())[:50]


def genre_from_title(title: str) -> str:
    m = re.match(r"^\[([^\]]+)\]", (title or "").strip())
    if not m:
        return ""
    tag = m.group(1).strip().lower()
    return "" if tag == "comedy" else tag


def parse_cost_from_description(desc: str) -> str:
    for line in (desc or "").split("\n"):
        line = line.strip()
        if not line or line.startswith("http") or line.lower().startswith("look up venue"):
            continue
        return line
    return ""


# ── Load sheet lookup ───────────────────────────────────────────────────────

def load_sheet_lookup(creds):
    import gspread
    client = gspread.authorize(creds)
    ws = client.open_by_key(SHEET_ID).worksheet(INBOX_TAB)
    records = ws.get_all_records(default_blank="")
    lookup = {}
    for r in records:
        title = str(r.get("Title", "")).strip()
        date = str(r.get("Date", "")).strip()
        if not title or not date:
            continue
        key = (norm_title(title), date)
        # first match wins; keep tags/source/cost
        lookup.setdefault(key, {
            "tags":   str(r.get("Tags", "")).strip(),
            "source": str(r.get("Source", "")).strip(),
            "cost":   str(r.get("Cost", "")).strip(),
        })
    return lookup


# ── Facet building ──────────────────────────────────────────────────────────

def shared_from_sheet(row, cal_name):
    """Full facets from a matched sheet row."""
    tags = normalize_tags([t.strip() for t in row["tags"].split(",") if t.strip()])
    tags_str = ",".join(tags)
    cost = row["cost"]
    source = row["source"] or cal_name
    return build_extended_properties(cost, tags_str, source)["shared"]


def shared_from_event(title, description, cal_name):
    """Fallback facets derived from the calendar event itself."""
    cost = parse_cost_from_description(description)
    genre = genre_from_title(title)
    tags_str = genre if genre else ""
    return build_extended_properties(cost, tags_str, cal_name)["shared"]


def event_date(ev) -> str:
    start = ev.get("start", {})
    raw = start.get("date") or start.get("dateTime", "")
    return raw[:10]  # local date portion


# ── Main backfill ───────────────────────────────────────────────────────────

# Only backfill the near-future window the website actually shows. Without an
# upper bound, singleEvents=True expands every recurring event (weekly markets,
# trivia, annual events) into thousands of future instances.
BACKFILL_DAYS_AHEAD = 60


def fetch_upcoming(service, cal_id):
    from datetime import timedelta
    events, page_token = [], None
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=BACKFILL_DAYS_AHEAD)).isoformat()
    while True:
        resp = service.events().list(
            calendarId=cal_id, timeMin=time_min, timeMax=time_max,
            maxResults=250, singleEvents=True, pageToken=page_token,
        ).execute()
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events


def backfill(dry_run=False, only_calendar=None):
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    creds = get_creds()
    service = build("calendar", "v3", credentials=creds)

    print("Loading sheet Inbox for tag recovery...")
    lookup = load_sheet_lookup(creds)
    print(f"  {len(lookup)} sheet rows indexed")

    targets = CALENDARS
    if only_calendar:
        canonical = CALENDAR_ALIASES.get(only_calendar.lower(), only_calendar)
        targets = {canonical: CALENDARS[canonical]} if canonical in CALENDARS else {}
        if not targets:
            print(f"Unknown calendar: {only_calendar}")
            return

    t_updated = t_skipped = t_errors = t_matched = t_fallback = 0

    for cal_name, cal_id in targets.items():
        events = fetch_upcoming(service, cal_id)
        print(f"\n{cal_name}: {len(events)} upcoming event instances")
        updated = skipped = errors = matched = fallback = 0
        seen_targets = set()  # dedupe recurring masters + repeats

        for ev in events:
            title = ev.get("summary", "")
            desc = ev.get("description", "")

            # For a recurring instance, patch the MASTER once (so all instances
            # inherit the facets and we don't create per-instance exceptions).
            target_id = ev.get("recurringEventId") or ev["id"]
            if target_id in seen_targets:
                skipped += 1
                continue
            seen_targets.add(target_id)

            key = (norm_title(title), event_date(ev))
            row = lookup.get(key)
            if row:
                new_shared = shared_from_sheet(row, cal_name)
                matched += 1
            else:
                new_shared = shared_from_event(title, desc, cal_name)
                fallback += 1

            existing = ev.get("extendedProperties", {}).get("shared", {})
            merged = {**existing, **new_shared}
            if merged == existing:
                skipped += 1
                continue

            if dry_run:
                src = "sheet" if row else "derived"
                rec = " (recurring master)" if ev.get("recurringEventId") else ""
                facet_str = ", ".join(f"{k}={v}" for k, v in new_shared.items())
                print(f"  [DRY/{src}] {title[:42]:<42} -> {facet_str}{rec}")
                updated += 1
                continue

            try:
                service.events().patch(
                    calendarId=cal_id, eventId=target_id,
                    body={"extendedProperties": {"shared": merged}},
                    sendUpdates="none",
                ).execute()
                updated += 1
            except HttpError as e:
                print(f"  ERROR: {title[:40]}: {e}")
                errors += 1

        print(f"  {'would update' if dry_run else 'updated'}: {updated}, skipped: {skipped}, "
              f"errors: {errors}  (sheet-matched: {matched}, derived: {fallback})")
        t_updated += updated; t_skipped += skipped; t_errors += errors
        t_matched += matched; t_fallback += fallback

    print(f"\n{'=' * 55}")
    print(f"TOTAL {'(DRY RUN)' if dry_run else ''}: {t_updated} updated, {t_skipped} skipped, {t_errors} errors")
    print(f"  Recovered full facets from sheet: {t_matched}")
    print(f"  Derived (cost+genre only):        {t_fallback}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill calendar event facets from the sheet")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--calendar", help="Limit to one calendar (e.g. comedy, music)")
    args = parser.parse_args()
    backfill(dry_run=args.dry_run, only_calendar=args.calendar)
