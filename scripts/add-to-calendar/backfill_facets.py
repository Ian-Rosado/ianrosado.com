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
import html
import argparse
from pathlib import Path
from datetime import datetime, timezone

import portland_events_add as pea
from portland_events_add import (
    CALENDARS, CALENDAR_ALIASES, SHEET_ID, INBOX_TAB,
    classify_cost, build_extended_properties, build_description,
    NOTE_LOOKUP_VENUE, SCOPES_CALENDAR_AND_SHEETS,
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


def _desc_lines(desc: str):
    """Split a description into clean text lines.

    Google Calendar's web editor linkifies plain URLs into <a href> anchors and
    stores HTML, so once an event has been touched in the UI the description is
    no longer plain text. Split on real newlines AND <br>, then strip tags and
    decode entities per line (mirrors stripHtml in google-calendar.ts) so the
    parsers below see the same clean text the website does.
    """
    parts = re.split(r"\r?\n|<br\s*/?>", desc or "", flags=re.I)
    out = []
    for p in parts:
        line = html.unescape(re.sub(r"<[^>]+>", " ", p))
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            out.append(line)
    return out


def parse_cost_from_description(desc: str) -> str:
    for line in _desc_lines(desc):
        low = line.lower()
        if line.startswith("http") or low.startswith("look up venue") or low.startswith("tags:"):
            continue
        # Some sources put cost and URL on one line ("Free. https://…"); keep
        # only the cost text so it doesn't get duplicated into the URL line.
        line = re.sub(r"https?://\S+", "", line).strip(" .|-")
        if line:
            return line
    return ""


def parse_url_from_description(desc: str) -> str:
    for line in _desc_lines(desc):
        m = re.search(r"https?://\S+", line)
        if m:
            return re.sub(r"[.,)>'\"]+$", "", m.group(0))  # strip trailing punctuation
    return ""


def parse_tags_from_description(desc: str):
    """Existing 'Tags:' / 'tags:' line (case-insensitive) as a list, or []."""
    for line in _desc_lines(desc):
        m = re.match(r"tags:\s*(.+)$", line, flags=re.I)
        if m:
            return [t.strip().lower() for t in m.group(1).split(",") if t.strip()]
    return []


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

def facets_from_sheet(row):
    """(cost, tags_str) recovered from a matched sheet row."""
    tags = normalize_tags([t.strip() for t in row["tags"].split(",") if t.strip()])
    return row["cost"], ",".join(tags)


def facets_from_event(title, description):
    """(cost, tags_str) derived from the calendar event itself (fallback).

    Preserves any tags already embedded in the description (e.g. on manually
    added events) so backfill never drops them, and folds in a genre parsed
    from a '[genre]' title prefix.
    """
    cost = parse_cost_from_description(description)
    tags = parse_tags_from_description(description)
    genre = genre_from_title(title)
    if genre:
        tags.append(genre)
    # dedupe while preserving order
    return cost, ",".join(dict.fromkeys(tags))


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

            existing_shared = ev.get("extendedProperties", {}).get("shared", {})

            key = (norm_title(title), event_date(ev))
            row = lookup.get(key)
            if row:
                cost, tags_str = facets_from_sheet(row)
                source = row["source"] or cal_name
                matched += 1
            else:
                cost, tags_str = facets_from_event(title, desc)
                source = cal_name
                fallback += 1

            # Make the description self-contained: if there's no cost line but a
            # prior run stored cost=free, write a "Free" line so the description
            # alone classifies correctly (we can't recover an exact price).
            if not cost and existing_shared.get("cost") == "free":
                cost = "Free"

            # extendedProperties stays as a redundant index; the website now
            # prefers the description, but keeping shared in sync is cheap.
            new_shared = build_extended_properties(cost, tags_str, source)["shared"]
            merged_shared = {**existing_shared, **new_shared}

            # Rebuild the description so the "Tags:" line is present/updated,
            # preserving the existing event URL (or look-up-venue note).
            url = parse_url_from_description(desc)
            note = "" if url else (NOTE_LOOKUP_VENUE if "look up venue" in (desc or "").lower() else "")
            new_desc = build_description(cost, url, note, tags_str)

            shared_changed = merged_shared != existing_shared
            desc_changed = new_desc.strip() != (desc or "").strip()
            if not shared_changed and not desc_changed:
                skipped += 1
                continue

            if dry_run:
                src = "sheet" if row else "derived"
                rec = " (recurring master)" if ev.get("recurringEventId") else ""
                changes = "+".join(c for c, ch in (("desc", desc_changed), ("shared", shared_changed)) if ch)
                print(f"  [DRY/{src}] {title[:40]:<40} [{changes}] cost={classify_cost(cost)} tags={tags_str or '-'}{rec}")
                if desc_changed:
                    # Show the rewrite so destructive/mangled cases are visible.
                    old1 = " | ".join(_desc_lines(desc)) or "(empty)"
                    new1 = " | ".join(new_desc.split("\n")) or "(empty)"
                    print(f"             old: {old1[:120]}")
                    print(f"             new: {new1[:120]}")
                updated += 1
                continue

            body = {}
            if shared_changed:
                body["extendedProperties"] = {"shared": merged_shared}
            if desc_changed:
                body["description"] = new_desc
            try:
                service.events().patch(
                    calendarId=cal_id, eventId=target_id,
                    body=body,
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
