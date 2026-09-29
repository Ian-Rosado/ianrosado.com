#!/usr/bin/env python3
"""
trivia_generate.py
------------------
Generate clean weekly-recurring trivia events on the four Trivia Nights calendars
from trivia_schedule.json (the source of truth).

Each schedule entry becomes ONE recurring event (RRULE), not a flood of future
events. Re-running is idempotent: events are tagged with a private
extendedProperty `trivia_key`, so a second run updates existing events, adds new
ones, and removes events whose venue is no longer in the JSON.

trivia_schedule.json entry shape:
  {
    "venue": "The Waypost",
    "address": "3120 N Williams Ave, Portland, OR 97227",
    "company": "ShanRock's Trivia",
    "company_url": "https://shanrockstrivia.com",
    "day": "MO",                 # MO TU WE TH FR SA SU
    "time": "19:00",             # 24h local
    "rrule": "FREQ=WEEKLY;BYDAY=MO",   # optional; defaults to weekly on `day`
    "cost": "$5/team",           # optional; defaults to "Free"
    "start_date": "2026-10-12",  # optional; first night for a venue that hasn't started yet
    "calendar": "Trivia Nights - N/NE"
  }

trivia_scrape.py re-pulls every company's schedule and updates this file.

Usage:
  python trivia_generate.py --dry-run        # preview, no writes
  python trivia_generate.py                   # create/update/prune events
  python trivia_generate.py --wipe            # delete ALL events on the 4 trivia
                                              # calendars first, then generate
"""

import re
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta, date, time as dtime

from googleapiclient.errors import HttpError

sys.stdout.reconfigure(encoding="utf-8")

# Shared OAuth helper (scripts/google_auth.py) — one token for all scripts,
# with automatic refresh (the old direct token read had none).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import google_auth

SCHEDULE = Path("trivia_schedule.json")
TIMEZONE = "America/Los_Angeles"
DEFAULT_DURATION_MIN = 120
MANAGED_TAG = "trivia_generate"   # private extendedProperty marker

# Trivia calendar IDs from the shared config (src-shared/config/calendars.json).
_CAL_CFG = json.loads(
    (Path(__file__).resolve().parent.parent.parent / "src-shared" / "config" / "calendars.json")
    .read_text(encoding="utf-8"))
CALENDARS = {c["name"]: c["id"] for c in _CAL_CFG["triviaCalendars"]}

BYDAY_TO_WEEKDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def get_service():
    return google_auth.get_calendar_service()


def trivia_key(entry):
    """Stable id for idempotent matching."""
    return f"{entry['calendar']}|{entry['venue'].strip().lower()}|{entry['day']}"


def next_occurrence(byday, time_str, not_before=None):
    """Next date (>= today, and >= not_before) whose weekday matches byday,
    combined with time."""
    target = BYDAY_TO_WEEKDAY.get(byday[:2], 0)
    start = max(date.today(), not_before or date.today())
    delta = (target - start.weekday()) % 7
    d = start + timedelta(days=delta)
    hh, mm = (int(x) for x in time_str.split(":"))
    return datetime.combine(d, dtime(hh, mm))


def build_event_body(entry):
    company = entry.get("company", "").strip()
    venue = entry["venue"].strip()
    summary = f"{venue} — {company}" if company else venue

    url = entry.get("company_url", "").strip()
    day_full = {"MO": "Monday", "TU": "Tuesday", "WE": "Wednesday", "TH": "Thursday",
                "FR": "Friday", "SA": "Saturday", "SU": "Sunday"}.get(entry["day"][:2], "")
    cost = entry.get("cost", "").strip() or "Free"
    is_free = "free" in cost.lower()
    desc_lines = [cost]
    if url:
        desc_lines.append(url)
    # Final "Tags:" line — the website parses this at build time (see
    # build_description in portland_events_add.py). Keep it so trivia events
    # carry the same facet convention as scraped events.
    desc_lines.append("Tags: trivia, free" if is_free else "Tags: trivia")
    description = "\n".join(desc_lines)

    start_date = entry.get("start_date")
    start_dt = next_occurrence(entry["day"], entry["time"],
                               date.fromisoformat(start_date) if start_date else None)
    end_dt = start_dt + timedelta(minutes=DEFAULT_DURATION_MIN)
    rrule = entry.get("rrule") or f"FREQ=WEEKLY;BYDAY={entry['day'][:2]}"

    return {
        "summary": summary,
        "location": entry.get("address", "").strip(),
        "description": description,
        "start": {"dateTime": start_dt.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": TIMEZONE},
        "end":   {"dateTime": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),   "timeZone": TIMEZONE},
        "recurrence": [f"RRULE:{rrule}"],
        "extendedProperties": {
            "shared": {"cost": "free" if is_free else "paid", "source": company or "Trivia"},
            "private": {"managed": MANAGED_TAG, "trivia_key": trivia_key(entry)},
        },
    }


def fetch_managed(svc, cal_id):
    """Return {trivia_key: event} for events this script manages on a calendar."""
    out, page = {}, None
    while True:
        resp = svc.events().list(
            calendarId=cal_id, privateExtendedProperty=f"managed={MANAGED_TAG}",
            showDeleted=False, maxResults=250, pageToken=page, singleEvents=False,
        ).execute()
        for ev in resp.get("items", []):
            # Skip edited single occurrences of a recurring event: they carry the
            # master's trivia_key too, and letting one shadow the master meant
            # updates hit the instance (error) and prunes deleted only the
            # instance, leaving the old master behind as a duplicate.
            if ev.get("recurringEventId"):
                continue
            k = ev.get("extendedProperties", {}).get("private", {}).get("trivia_key")
            if k:
                out[k] = ev
        page = resp.get("nextPageToken")
        if not page:
            break
    return out


def wipe_calendars(svc, dry_run):
    print("\n-- WIPE: deleting ALL events on the four trivia calendars --")
    for cal_name, cal_id in CALENDARS.items():
        ids, page = [], None
        while True:
            resp = svc.events().list(calendarId=cal_id, maxResults=250,
                                     pageToken=page, singleEvents=False).execute()
            ids += [e["id"] for e in resp.get("items", [])]
            page = resp.get("nextPageToken")
            if not page:
                break
        print(f"  {cal_name}: {len(ids)} events to delete")
        if dry_run:
            continue
        for eid in ids:
            try:
                svc.events().delete(calendarId=cal_id, eventId=eid, sendUpdates="none").execute()
            except HttpError as e:
                if "deleted" not in str(e).lower():
                    print(f"    ERROR deleting {eid}: {e}")


def main():
    ap = argparse.ArgumentParser(description="Generate recurring trivia events from trivia_schedule.json")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    ap.add_argument("--wipe", action="store_true", help="Delete all events on the trivia calendars first")
    ap.add_argument("--yes", action="store_true", help="Skip wipe confirmation prompt")
    args = ap.parse_args()

    if not SCHEDULE.exists():
        print(f"ERROR: {SCHEDULE} not found. Populate it first.")
        sys.exit(1)
    entries = json.loads(SCHEDULE.read_text(encoding="utf-8"))
    print(f"Loaded {len(entries)} venues from {SCHEDULE}")

    # Validate entries reference real calendars
    bad = [e for e in entries if e.get("calendar") not in CALENDARS]
    if bad:
        print(f"ERROR: {len(bad)} entries reference unknown calendars (e.g. {bad[0].get('calendar')!r})")
        sys.exit(1)

    svc = get_service()

    if args.wipe:
        if not args.dry_run and not args.yes:
            confirm = input("Type 'wipe' to delete ALL events on the 4 trivia calendars: ").strip().lower()
            if confirm != "wipe":
                print("Cancelled.")
                return
        wipe_calendars(svc, args.dry_run)

    # Group desired entries by calendar
    by_cal = {}
    for e in entries:
        by_cal.setdefault(e["calendar"], []).append(e)

    created = updated = pruned = errors = 0

    for cal_name, cal_id in CALENDARS.items():
        desired = by_cal.get(cal_name, [])
        existing = {} if args.wipe else fetch_managed(svc, cal_id)
        desired_keys = {trivia_key(e) for e in desired}

        print(f"\n{cal_name}: {len(desired)} venues in schedule, {len(existing)} managed events on calendar")

        # Create / update
        for e in desired:
            k = trivia_key(e)
            body = build_event_body(e)
            if k in existing:
                if args.dry_run:
                    print(f"  [DRY] update  {body['summary']}")
                else:
                    try:
                        svc.events().update(calendarId=cal_id, eventId=existing[k]["id"],
                                            body=body, sendUpdates="none").execute()
                    except HttpError as ex:
                        print(f"  ERROR update {body['summary']}: {ex}"); errors += 1; continue
                updated += 1
            else:
                if args.dry_run:
                    print(f"  [DRY] create  {body['summary']}  ({e['day']} {e['time']})")
                else:
                    try:
                        svc.events().insert(calendarId=cal_id, body=body, sendUpdates="none").execute()
                    except HttpError as ex:
                        print(f"  ERROR create {body['summary']}: {ex}"); errors += 1; continue
                created += 1

        # Prune managed events no longer in the schedule
        for k, ev in existing.items():
            if k not in desired_keys:
                if args.dry_run:
                    print(f"  [DRY] prune   {ev.get('summary','')}")
                else:
                    try:
                        svc.events().delete(calendarId=cal_id, eventId=ev["id"], sendUpdates="none").execute()
                    except HttpError:
                        pass
                pruned += 1

    print(f"\n{'='*55}")
    print(f"{'(DRY RUN) ' if args.dry_run else ''}created: {created}, updated: {updated}, "
          f"pruned: {pruned}, errors: {errors}")


if __name__ == "__main__":
    main()
