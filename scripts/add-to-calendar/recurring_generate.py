#!/usr/bin/env python3
"""
recurring_generate.py
---------------------
Generate weekly/monthly recurring events on the main calendars (Portland Events,
Live Music, Comedy, Karaoke, Farmers Markets) from recurring_schedule.json —
the same idea as trivia_generate.py, for non-trivia fixtures: goth nights,
drag bingo, jam sessions, lock-picking meetups, cemetery tours ...

Each entry becomes ONE event with an RRULE. Re-running is idempotent: events
carry a private extendedProperty `recurring_key`, so a second run updates
existing events, adds new ones, and deletes events whose entry was removed.

recurring_schedule.json entry shape:
  {
    "title": "Scary-oke Karaoke",
    "venue": "The Coffin Club",            # location; ", Portland, OR" added if no city
    "calendar": "Portland Karaoke",
    "rrule": "FREQ=WEEKLY;BYDAY=TU",       # or e.g. FREQ=MONTHLY;BYDAY=2WE,4WE
    "time": "21:00",
    "end_time": "",                        # optional; default time + 2h
    "cost": "Free",                        # optional
    "url": "https://thecoffinclubpdx.com/",
    "tags": "karaoke, free",               # optional; website facet tags
    "credit": "Tunnel Vision PDX"          # optional; key into CREDITS
  }

Workflow for a new batch from Tunnel Vision's recurring calendar:
  python recurring_generate.py --from-sheet   # pull 'y' rows from the "Recurring
                                              # Review" tab into the JSON
  python recurring_generate.py --dry-run
  python recurring_generate.py

Usage:
  python recurring_generate.py --dry-run     # preview, no writes
  python recurring_generate.py               # create/update/prune events
"""

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta, date, time as dtime

from googleapiclient.errors import HttpError

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import google_auth

from portland_events_add import (build_description, build_extended_properties,
                                 with_default_city, CALENDARS)

HERE = Path(__file__).resolve().parent
SCHEDULE = HERE / "recurring_schedule.json"
REVIEW_TAB = "Recurring Review"
TIMEZONE = "America/Los_Angeles"
DEFAULT_DURATION_MIN = 120
MANAGED_TAG = "recurring_generate"

# Attribution line appended to the description (after the event's own link, so
# the website still picks the event link as the source URL).
CREDITS = {
    "Tunnel Vision PDX": "via Tunnel Vision PDX https://tunnelvisionpdx.com",
}

TARGET_CALENDARS = ["Portland Events", "Portland Live Music", "Portland Comedy",
                    "Portland Karaoke", "Portland Farmers Markets"]

BYDAY_TO_WEEKDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}

# Default facet tags by calendar when an entry doesn't set its own.
CALENDAR_TAGS = {
    "Portland Karaoke": "karaoke",
    "Portland Comedy": "comedy",
    "Portland Live Music": "live music",
    "Portland Farmers Markets": "farmers market",
}


def recurring_key(e):
    days = re.search(r"BYDAY=([^;]+)", e["rrule"]).group(1)
    return f"{e['calendar']}|{e['title'].strip().lower()}|{e['venue'].strip().lower()}|{days}"


def _occurs_on(rrule, d):
    """Does a WEEKLY/MONTHLY BYDAY rule include date d?"""
    days = re.search(r"BYDAY=([^;]+)", rrule).group(1).split(",")
    wd = d.weekday()
    for spec in days:
        m = re.fullmatch(r"(-?\d)?([A-Z]{2})", spec)
        n, day = m.group(1), m.group(2)
        if BYDAY_TO_WEEKDAY[day] != wd:
            continue
        if n is None:
            return True
        n = int(n)
        if n > 0 and (d.day - 1) // 7 + 1 == n:
            return True
        if n < 0 and (d + timedelta(days=7)).month != d.month:  # last <day> of month
            return True
    return False


def first_occurrence(e):
    """First date >= today that the rule actually hits (DTSTART must be a real
    occurrence, or Google shows an extra stray instance)."""
    d = max(date.today(), date.fromisoformat(e["start_date"]) if e.get("start_date") else date.today())
    for _ in range(62):
        if _occurs_on(e["rrule"], d):
            return d
        d += timedelta(days=1)
    raise ValueError(f"no occurrence found for {e['title']} ({e['rrule']})")


def build_event_body(e):
    d = first_occurrence(e)
    hh, mm = (int(x) for x in e["time"].split(":"))
    start = datetime.combine(d, dtime(hh, mm))
    if e.get("end_time"):
        eh, em = (int(x) for x in e["end_time"].split(":"))
        end = datetime.combine(d, dtime(eh, em))
        if end <= start:
            end += timedelta(days=1)  # runs past midnight
    else:
        end = start + timedelta(minutes=DEFAULT_DURATION_MIN)

    cost = e.get("cost", "").strip()
    tags = e.get("tags") or CALENDAR_TAGS.get(e["calendar"], "")
    if cost.lower().startswith("free") and "free" not in tags:
        tags = f"{tags}, free" if tags else "free"
    description = build_description(cost, e.get("url", ""), tags=tags)
    credit = CREDITS.get(e.get("credit", ""))
    if credit:
        # Insert the credit before the trailing "Tags:" line.
        lines = description.split("\n")
        at = len(lines) - 1 if lines and lines[-1].startswith("Tags:") else len(lines)
        lines.insert(at, credit)
        description = "\n".join(lines)

    ext = build_extended_properties(cost, tags, e.get("credit") or "Recurring")
    ext["private"] = {"managed": MANAGED_TAG, "recurring_key": recurring_key(e)}
    return {
        "summary": e["title"].strip(),
        "location": with_default_city(e["venue"]),
        "description": description,
        "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": TIMEZONE},
        "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": TIMEZONE},
        "recurrence": [f"RRULE:{e['rrule']}"],
        "extendedProperties": ext,
    }


def fetch_managed(svc, cal_id):
    """Return {recurring_key: master event} for events this script manages.
    Edited single occurrences carry the key too — skip them (see the same fix
    in trivia_generate.fetch_managed)."""
    out, page = {}, None
    while True:
        resp = svc.events().list(
            calendarId=cal_id, privateExtendedProperty=f"managed={MANAGED_TAG}",
            showDeleted=False, maxResults=250, pageToken=page, singleEvents=False,
        ).execute()
        for ev in resp.get("items", []):
            if ev.get("recurringEventId"):
                continue
            k = ev.get("extendedProperties", {}).get("private", {}).get("recurring_key")
            if k:
                out[k] = ev
        page = resp.get("nextPageToken")
        if not page:
            break
    return out


def import_from_sheet():
    """Merge the 'y' rows of the Recurring Review tab into recurring_schedule.json
    (keyed by recurring_key, so re-importing updates rather than duplicates)."""
    import inbox_common
    ws = inbox_common.get_sheet().worksheet(REVIEW_TAB)
    rows = ws.get_all_records()
    existing = json.loads(SCHEDULE.read_text(encoding="utf-8")) if SCHEDULE.exists() else []
    by_key = {recurring_key(e): e for e in existing}
    added = 0
    for r in rows:
        if str(r.get("Include", "")).strip().lower() != "y" or not r.get("RRULE") or not r.get("Time"):
            continue
        e = {"title": r["Title"], "venue": r["Venue"], "calendar": r["Calendar"],
             "rrule": r["RRULE"], "time": str(r["Time"]).zfill(5),
             "end_time": str(r.get("End") or ""), "cost": str(r.get("Cost") or ""),
             "url": r["Link"], "credit": "Tunnel Vision PDX"}
        if e["end_time"]:
            e["end_time"] = e["end_time"].zfill(5)
        k = recurring_key(e)
        if k not in by_key:
            added += 1
        by_key[k] = {**by_key.get(k, {}), **e}
    SCHEDULE.write_text(json.dumps(list(by_key.values()), indent=2) + "\n", encoding="utf-8")
    print(f"Imported from '{REVIEW_TAB}': {added} new, {len(by_key)} total in {SCHEDULE.name}")


def main():
    ap = argparse.ArgumentParser(description="Generate recurring events from recurring_schedule.json")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    ap.add_argument("--from-sheet", action="store_true",
                    help=f"Import 'y' rows from the '{REVIEW_TAB}' tab into the JSON, then stop")
    args = ap.parse_args()

    if args.from_sheet:
        import_from_sheet()
        return

    entries = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    print(f"Loaded {len(entries)} entries from {SCHEDULE.name}")
    bad = [e for e in entries if e.get("calendar") not in TARGET_CALENDARS]
    if bad:
        print(f"ERROR: {len(bad)} entries have an unknown calendar (e.g. {bad[0].get('calendar')!r})")
        sys.exit(1)

    svc = google_auth.get_calendar_service()
    created = updated = pruned = errors = 0
    for cal_name in TARGET_CALENDARS:
        cal_id = CALENDARS[cal_name]
        desired = [e for e in entries if e["calendar"] == cal_name]
        existing = fetch_managed(svc, cal_id)
        desired_keys = {recurring_key(e) for e in desired}
        if not desired and not existing:
            continue
        print(f"\n{cal_name}: {len(desired)} in schedule, {len(existing)} managed on calendar")
        for e in desired:
            k = recurring_key(e)
            try:
                body = build_event_body(e)
            except ValueError as ex:
                print(f"  ERROR {ex}"); errors += 1; continue
            verb = "update" if k in existing else "create"
            if args.dry_run:
                print(f"  [DRY] {verb:6} {body['summary']}  ({e['rrule']} {e['time']})")
            else:
                try:
                    if k in existing:
                        svc.events().update(calendarId=cal_id, eventId=existing[k]["id"],
                                            body=body, sendUpdates="none").execute()
                    else:
                        svc.events().insert(calendarId=cal_id, body=body, sendUpdates="none").execute()
                except HttpError as ex:
                    print(f"  ERROR {verb} {body['summary']}: {ex}"); errors += 1; continue
            if verb == "update":
                updated += 1
            else:
                created += 1
        for k, ev in existing.items():
            if k in desired_keys:
                continue
            if args.dry_run:
                print(f"  [DRY] prune  {ev.get('summary', '')}")
            else:
                try:
                    svc.events().delete(calendarId=cal_id, eventId=ev["id"], sendUpdates="none").execute()
                except HttpError as ex:
                    print(f"  ERROR prune {ev.get('summary', '')}: {ex}"); errors += 1; continue
            pruned += 1

    print(f"\n{'=' * 55}")
    print(f"{'(DRY RUN) ' if args.dry_run else ''}created: {created}, updated: {updated}, "
          f"pruned: {pruned}, errors: {errors}")


if __name__ == "__main__":
    main()
