#!/usr/bin/env python3
"""
tag_free_events.py
------------------
Ensure free events carry a "free" tag.

Some events have "Free" on the cost line (or a stored cost=free facet) but no
"free" in their description "Tags:" line. This walks the upcoming events on
every calendar and adds "free" to the tag list — and the description's "Tags:"
line — for any event classified free that's missing it. Paid/unknown events
are left untouched.

    python tag_free_events.py --dry-run            # preview, no writes
    python tag_free_events.py                       # apply to all calendars
    python tag_free_events.py --calendar music      # one calendar only

Reuses backfill_facets' HTML-safe parsers and portland_events_add's
description builder, so output matches what the rest of the pipeline writes.
Auth reuses token.json / credentials.json (calendar scope).
"""

import argparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import portland_events_add as pea
from portland_events_add import (
    CALENDARS, CALENDAR_ALIASES, classify_cost, build_description,
    NOTE_LOOKUP_VENUE, SCOPES_CALENDAR_AND_SHEETS,
)
from backfill_facets import (
    get_creds, fetch_upcoming,
    parse_cost_from_description, parse_url_from_description,
    parse_tags_from_description, _desc_lines,
)

pea.SCOPES = SCOPES_CALENDAR_AND_SHEETS


def tag_free(dry_run=False, only_calendar=None):
    creds = get_creds()
    service = build("calendar", "v3", credentials=creds)

    targets = CALENDARS
    if only_calendar:
        canonical = CALENDAR_ALIASES.get(only_calendar.lower(), only_calendar)
        targets = {canonical: CALENDARS[canonical]} if canonical in CALENDARS else {}
        if not targets:
            print(f"Unknown calendar: {only_calendar}")
            return

    t_updated = t_skipped = t_errors = 0

    for cal_name, cal_id in targets.items():
        events = fetch_upcoming(service, cal_id)
        print(f"\n{cal_name}: {len(events)} upcoming event instances")
        updated = skipped = errors = 0
        seen = set()  # patch recurring masters once

        for ev in events:
            target_id = ev.get("recurringEventId") or ev["id"]
            if target_id in seen:
                continue
            seen.add(target_id)

            desc = ev.get("description", "")
            shared = ev.get("extendedProperties", {}).get("shared", {})

            cost = parse_cost_from_description(desc)
            # Trust the cost line first; fall back to a stored facet only when
            # the description has no cost text, so a paid line is never
            # mislabeled free.
            is_free = classify_cost(cost) == "free" or (not cost and shared.get("cost") == "free")
            if not is_free:
                skipped += 1
                continue

            tags = parse_tags_from_description(desc)
            if "free" in tags:
                skipped += 1
                continue

            # Build the new description: free first, keep existing tags, keep URL.
            new_tags = ["free"] + tags
            tags_str = ",".join(new_tags)
            url = parse_url_from_description(desc)
            note = "" if url else (NOTE_LOOKUP_VENUE if "look up venue" in (desc or "").lower() else "")
            if not cost:
                cost = "Free"  # make the description self-contained
            new_desc = build_description(cost, url, note, tags_str)

            title = ev.get("summary", "")
            rec = " (recurring master)" if ev.get("recurringEventId") else ""

            if dry_run:
                old1 = " | ".join(_desc_lines(desc)) or "(empty)"
                new1 = " | ".join(new_desc.split("\n"))
                print(f"  [DRY] {title[:46]:<46}{rec}")
                print(f"        old: {old1[:110]}")
                print(f"        new: {new1[:110]}")
                updated += 1
                continue

            try:
                service.events().patch(
                    calendarId=cal_id, eventId=target_id,
                    body={"description": new_desc},
                    sendUpdates="none",
                ).execute()
                updated += 1
            except HttpError as e:
                print(f"  ERROR: {title[:40]}: {e}")
                errors += 1

        print(f"  {'would tag' if dry_run else 'tagged'} free: {updated}, skipped: {skipped}, errors: {errors}")
        t_updated += updated; t_skipped += skipped; t_errors += errors

    print(f"\n{'=' * 55}")
    print(f"TOTAL {'(DRY RUN)' if dry_run else ''}: {t_updated} tagged free, {t_skipped} skipped, {t_errors} errors")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Add a 'free' tag to free events missing it")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    ap.add_argument("--calendar", help="Limit to one calendar (e.g. music, events)")
    args = ap.parse_args()
    tag_free(dry_run=args.dry_run, only_calendar=args.calendar)
