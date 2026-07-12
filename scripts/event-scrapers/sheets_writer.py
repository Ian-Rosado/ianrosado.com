"""
Portland Events — Google Sheets Writer

Writes scraped events to the Portland Events Inbox Google Sheet.
Authenticates via OAuth (browser login on first run, then cached).

Sheet: Portland Events Inbox
ID: 1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4

The sheet is used as a review inbox — events land here first, then
you push approved ones to Google Calendar.

Tab layout (written to "Inbox" tab, created if missing):
  A: Title
  B: Date        (YYYY-MM-DD)
  C: Time        (HH:MM 24h)
  D: End Time    (HH:MM 24h, or YYYY-MM-DD end date for a multi-day event)
  E: Duration    (minutes)
  F: Location
  G: Cost
  H: Calendar    (events | music | farmers_market)
  I: Tags        (comma-separated)
  J: Source
  K: URL
  L: Added       (timestamp this row was written)

Auth: shared token via scripts/google_auth.py — the same
scripts/add-to-calendar/{credentials.json, token.json} pair every other
Portland Events script uses. First run opens a browser; the token is cached
and refreshed automatically. See CLAUDE.md for the one-time credential setup.
"""

import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

import gspread

# Shared OAuth helper (scripts/google_auth.py) — one token for all scripts.
# (This replaced the separate credentials/ store this script used to keep.)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import google_auth
from google_auth import TOKEN_FILE, CLIENT_SECRET_FILE  # re-exported for reauth_and_push

# ── Config ────────────────────────────────────────────────────────────────────

SHEET_ID = "1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4"
INBOX_TAB = "Inbox"

# Sheet columns (1-indexed for gspread)
HEADERS = [
    "include", "Title", "Date", "Time", "End Time", "Duration (min)",
    "Location", "Cost", "Calendar", "Tags", "Source", "URL", "Added",
]

CALENDAR_LABELS = {
    "events": "Portland Events",
    "music": "Portland Live Music",
    "comedy": "Portland Comedy",
    "karaoke": "Portland Karaoke",
    "farmers_market": "Portland Farmers Markets",
    "sports": "Portland Sports",
}

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_credentials():
    """Get or refresh OAuth credentials (shared token, see google_auth)."""
    return google_auth.get_credentials()


def get_client():
    """Return an authenticated gspread client."""
    return google_auth.get_gspread_client()

# ── Sheet helpers ─────────────────────────────────────────────────────────────

def get_or_create_inbox(client):
    """Open the spreadsheet and return the Inbox worksheet, creating it if needed."""
    sheet = client.open_by_key(SHEET_ID)

    try:
        ws = sheet.worksheet(INBOX_TAB)
    except gspread.WorksheetNotFound:
        print(f"Creating '{INBOX_TAB}' tab...")
        ws = sheet.add_worksheet(title=INBOX_TAB, rows=2000, cols=len(HEADERS))

    # Ensure header row exists
    first_row = ws.row_values(1)
    if first_row != HEADERS:
        ws.update("A1", [HEADERS])
        # Bold the header row
        ws.format("A1:M1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
        })
        print(f"Header row written to '{INBOX_TAB}'")

    return ws


def get_existing_keys(ws):
    """
    Return a set of (title_lower, date) tuples already in the sheet.
    Used to skip duplicates.
    """
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return set()
    keys = set()
    for row in rows[1:]:  # skip header
        if len(row) >= 3:
            # Column A is "Include", B is Title, C is Date
            title = row[1].strip().lower()[:50]
            date_ = row[2].strip()
            keys.add((title, date_))
    return keys


def event_to_row(event):
    """Convert an event dict to a sheet row (list of values)."""
    tags = ", ".join(event.get("tags") or [])
    calendar = CALENDAR_LABELS.get(event.get("calendar", ""), event.get("calendar", ""))
    added = datetime.now().strftime("%Y-%m-%d %H:%M")

    return [
        "",  # Include (column A) — left blank for manual review
        event.get("title", ""),
        event.get("date", ""),
        event.get("time", ""),
        # For a multi-day event the "End Time" column carries the end DATE
        # (YYYY-MM-DD); portland_events_add reads that as the span's last day.
        event.get("end_date") or event.get("end_time", ""),
        event.get("duration_minutes", "") or "",
        event.get("location", ""),
        event.get("cost", ""),
        calendar,
        tags,
        event.get("source", ""),
        event.get("url", ""),
        added,
    ]


# ── Main write function ───────────────────────────────────────────────────────

def write_events_to_sheet(events, skip_duplicates=True, clear_first=False):
    """
    Write a list of events to the Inbox sheet.

    Args:
        events: list of event dicts (from run_all.py)
        skip_duplicates: if True, check existing rows and skip matches by (title, date)
        clear_first: if True, clear all existing data rows before writing (fresh run)

    Returns:
        (written_count, skipped_count)
    """
    print("\nConnecting to Google Sheets...")
    client = get_client()
    ws = get_or_create_inbox(client)

    if clear_first:
        # Keep header, clear data rows
        last_row = ws.row_count
        if last_row > 1:
            ws.delete_rows(2, last_row)
            print("Cleared existing rows.")
        existing_keys = set()
    elif skip_duplicates:
        existing_keys = get_existing_keys(ws)
        print(f"Found {len(existing_keys)} existing events in sheet (will skip duplicates)")
    else:
        existing_keys = set()

    # Build rows, filtering duplicates
    rows_to_write = []
    skipped = 0
    for event in events:
        key = (event.get("title", "").lower()[:50], event.get("date", ""))
        if skip_duplicates and key in existing_keys:
            skipped += 1
            continue
        rows_to_write.append(event_to_row(event))
        existing_keys.add(key)  # prevent intra-batch dupes too

    if not rows_to_write:
        print(f"Nothing new to write ({skipped} duplicates skipped).")
        return 0, skipped

    # Append in one batch (much faster than row-by-row)
    ws.append_rows(rows_to_write, value_input_option="USER_ENTERED")

    print(f"Wrote {len(rows_to_write)} events to '{INBOX_TAB}' tab")
    if skipped:
        print(f"Skipped {skipped} duplicates")

    return len(rows_to_write), skipped


# ── Standalone usage ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Write events JSON to Google Sheets inbox")
    parser.add_argument("json_file", nargs="?", help="Path to events JSON file (from run_all.py)")
    parser.add_argument("--clear", action="store_true", help="Clear sheet before writing")
    parser.add_argument("--no-dedup", action="store_true", help="Skip duplicate checking")
    parser.add_argument("--calendar", choices=sorted(CALENDAR_LABELS),
                        help="Filter to one calendar type")
    args = parser.parse_args()

    # Load events
    if args.json_file:
        with open(args.json_file, encoding="utf-8") as f:
            events = json.load(f)
    else:
        # Find the most recent output file
        output_dir = Path(__file__).parent / "output"
        json_files = sorted(output_dir.glob("events_*.json"), reverse=True)
        if not json_files:
            print("No events JSON found. Run run_all.py first.")
            sys.exit(1)
        latest = json_files[0]
        print(f"Using latest output: {latest}")
        with open(latest, encoding="utf-8") as f:
            events = json.load(f)

    if args.calendar:
        events = [e for e in events if e.get("calendar") == args.calendar]
        print(f"Filtered to {args.calendar}: {len(events)} events")

    written, skipped = write_events_to_sheet(
        events,
        skip_duplicates=not args.no_dedup,
        clear_first=args.clear,
    )
    print(f"\nDone. {written} written, {skipped} skipped.")
