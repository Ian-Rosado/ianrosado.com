#!/usr/bin/env python3
"""
inbox_common.py
---------------
Shared core for every front-end that feeds the add-to-calendar pipeline by
appending rows to the **Inbox** tab of the Portland Events Inbox sheet.

Three front-ends write to the Inbox and then hand off to the unchanged
`portland_events_add.py` flow (prep -> Categorize/Dedup -> Review -> commit):

  - instagram_events.py  (saved Instagram post links)
  - flyer_events.py      (photos of flyers taken around town)
  - feedback_events.py   (submissions from the public feedback form)

The Inbox row shape, the calendar name<->code mapping, and the append logic all
live here so a change to the Inbox columns lands in one place instead of three.

Auth: shared token via scripts/google_auth.py (anchored to that file).
"""

import sys
from datetime import datetime
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────

SHEET_ID = "1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4"
INBOX_TAB = "Inbox"

# Inbox tab columns (must match scripts/event-scrapers/sheets_writer.py):
#   A include | B Title | C Date | D Time | E End Time | F Duration (min)
#   G Location | H Cost | I Calendar | J Tags | K Source | L URL | M Added
#   N ★ IG?  (Instagram-pick flag; blank for scraper/flyer/feedback rows)
INBOX_HEADERS = [
    "include", "Title", "Date", "Time", "End Time", "Duration (min)",
    "Location", "Cost", "Calendar", "Tags", "Source", "URL", "Added", "★ IG?",
]

# The '★ IG?' value written into the Inbox for a flagged pick.
IG_PICK_MARK = "★"

# The Inbox "Calendar" column must hold the full calendar NAME (e.g.
# "Portland Live Music") — that's what portland_events_add.py's categorize step
# recognizes (see CALENDAR_ALIASES there). Short codes like "music"/"events" are
# NOT recognized and silently default to Portland Events, so we normalize any
# short code back to its full name before writing. The categorize stage can
# still override the guess; this is just a starting point.
CALENDAR_CODES = {
    "Portland Events": "events",
    "Portland Live Music": "music",
    "Portland Comedy": "comedy",
    "Portland Karaoke": "karaoke",
    "Portland Farmers Markets": "farmers_market",
    "Portland Sports": "sports",
    "Trivia Nights - SE": "trivia_se",
    "Trivia Nights - N/NE": "trivia_nne",
    "Trivia Nights - NW/SW": "trivia_nwsw",
    "Trivia Nights - Further Out": "trivia_further",
}
# Inverse: short code -> full name, so a code passed in rows.json still expands.
_CODE_TO_NAME = {code: name for name, code in CALENDAR_CODES.items()}


# ── Auth (shared token — scripts/google_auth.py) ────────────────────────────

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import google_auth  # noqa: E402


def get_sheet():
    """Open the Portland Events Inbox spreadsheet."""
    return google_auth.get_gspread_client().open_by_key(SHEET_ID)


# ── Inbox row mapping + append ───────────────────────────────────────────────

def to_inbox_row(ev, default_source=""):
    """Map one extracted-event dict to the 14-column Inbox row order.

    The Inbox tab's first column is the blank 'include' flag (filled during
    review), so the row leads with an empty cell to stay aligned — see
    INBOX_HEADERS / scripts/event-scrapers/sheets_writer.py.

    Recognized event keys (all optional except title + date):
        title, date (YYYY-MM-DD), time (HH:MM 24h), end_time, duration,
        location, cost, calendar (full name or short code), tags
        (comma-separated), source, url, ig (truthy -> flag as an Instagram
        pick: purple on the calendar).
    `default_source` fills the Source column when the event has no `source`.
    """
    cal = ev.get("calendar", "")
    cal_name = _CODE_TO_NAME.get(cal, cal)  # accept a name or a code; store the name
    return [
        "",                            # include (blank; set during review)
        ev.get("title", ""),
        ev.get("date", ""),            # YYYY-MM-DD
        ev.get("time", ""),            # HH:MM 24h
        ev.get("end_time", ""),
        ev.get("duration", ""),
        ev.get("location", ""),
        ev.get("cost", ""),
        cal_name,
        ev.get("tags", ""),            # comma-separated
        ev.get("source", default_source),
        ev.get("url", ""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        IG_PICK_MARK if ev.get("ig") else "",   # ★ IG? — pre-fills the Review flag
    ]


def ensure_inbox(sheet):
    """Return the Inbox worksheet, creating it (or fixing an old header) so the
    14-column header — including '★ IG?' — is in place before we append."""
    import gspread
    try:
        inbox = sheet.worksheet(INBOX_TAB)
        header = inbox.row_values(1)
        if header != INBOX_HEADERS:
            inbox.update([INBOX_HEADERS], "A1")
    except gspread.WorksheetNotFound:
        inbox = sheet.add_worksheet(title=INBOX_TAB, rows=2000, cols=len(INBOX_HEADERS))
        inbox.update([INBOX_HEADERS], "A1")
    return inbox


def append_events(events, default_source="", sheet=None, dry_run=False):
    """Append a list of extracted-event dicts to the Inbox tab.

    Returns the number of rows appended (or that would be, for dry_run). Pass an
    already-opened `sheet` to avoid re-authenticating when the caller also needs
    the sheet for its own bookkeeping.
    """
    rows = [to_inbox_row(ev, default_source) for ev in events]
    if dry_run:
        print(f"[dry-run] would append {len(rows)} row(s) to '{INBOX_TAB}':")
        for r in rows:
            print("  " + " | ".join(str(c) for c in r[:9]))
        return len(rows)

    sheet = sheet or get_sheet()
    inbox = ensure_inbox(sheet)
    if rows:
        inbox.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"Appended {len(rows)} event(s) to '{INBOX_TAB}'.")
    return len(rows)
