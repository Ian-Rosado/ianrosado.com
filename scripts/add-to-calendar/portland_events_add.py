#!/usr/bin/env python3
"""
portland_events_add.py
----------------------
Bulk-add events to Portland Events Google Calendars.
All interaction happens via Google Sheets — no terminal copy-paste.

Workflow:
  1. Categorize tab  — script writes events; you (or Claude) fill in correct calendar
  2. Dedup tab       — script writes incoming + existing events; you mark duplicates
  3. Review tab      — script writes all events with corrected calendars and dup flags;
                       you mark y/n in the Include column
  4. Script reads Review tab and adds the 'y' events to Google Calendar

Usage:
    python portland_events_add.py --from-sheets          # full run from Google Sheet
    python portland_events_add.py --from-sheets --dry-run  # all steps, no calendar write
    python portland_events_add.py --from-sheets --no-ai  # skip categorize + dedup steps
    python portland_events_add.py events.tsv             # use a TSV file instead of sheet

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client gspread

Authentication:
    Create OAuth 2.0 credentials (Desktop app) at https://console.cloud.google.com/,
    download as credentials.json in the same directory as this script.
    First run opens a browser; token.json is saved for future runs.
    Delete token.json if you get a scope mismatch error.
"""

import csv
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Google Sheet inbox (Portland Events Inbox)
SHEET_ID = "1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4"
INBOX_TAB = "Inbox"

# ─── Calendar IDs ─────────────────────────────────────────────────────────────

CALENDARS = {
    "Portland Events":             "6218570f10546f6f03748bbd25adcde299bfd55ef4741d8d1520e79653d9c9f6@group.calendar.google.com",
    "Portland Live Music":         "34ae96ffcf119eb4dbf6acf86b0886273efeb8a702ed6e9267ef3d24f0e9a1f7@group.calendar.google.com",
    "Portland Comedy":             "94a06447d97328f27a5e219c8e01c42be692998a7573738132a4405a739efec4@group.calendar.google.com",
    "Portland Karaoke":            "e911229a59a93265f26cc81a1cbd2c3be4300fad84e935846ddb8fa7909f42fb@group.calendar.google.com",
    "Trivia Nights - SE":          "441feafdb38c603cde09cd9a60e4f8ed10be90a21eb26dee01db64d0c8594a88@group.calendar.google.com",
    "Trivia Nights - N/NE":        "561e4a90958248768cba407c23d37f1293e28f3749bc14de503d258fc03a48c7@group.calendar.google.com",
    "Trivia Nights - NW/SW":       "088af359972350285c1e5bccda5fb38c349d0597d7c795ef3d1c21d7b973e457@group.calendar.google.com",
    "Trivia Nights - Further Out": "ac0a6fedb05274655f5e68e9ec26c3f9b341866ae0feed97dd703e94f164a0bf@group.calendar.google.com",
    "Portland Farmers Markets":    "560e859bd2c7b5dfd2262cb6f28389921434606cec955e7ec75f02df9fd2138a@group.calendar.google.com",
}

# Calendars whose events are free by default (no cost unless a price is stated).
# Mirrors FREE_DEFAULT_SLUGS in src-shared/lib/google-calendar.ts. (Bike rides
# live on the imported Pedalpalooza calendar, which isn't written by this script.)
FREE_DEFAULT_CALENDARS = {
    "Portland Farmers Markets",
    "Trivia Nights - SE",
    "Trivia Nights - N/NE",
    "Trivia Nights - NW/SW",
    "Trivia Nights - Further Out",
}

CALENDAR_ALIASES = {
    "portland events":             "Portland Events",
    "main":                        "Portland Events",
    "portland live music":         "Portland Live Music",
    "live music":                  "Portland Live Music",
    "portland comedy":             "Portland Comedy",
    "comedy":                      "Portland Comedy",
    "portland karaoke":            "Portland Karaoke",
    "karaoke":                     "Portland Karaoke",
    "portland farmers markets":    "Portland Farmers Markets",
    "farmers markets":             "Portland Farmers Markets",
    "farmers market":              "Portland Farmers Markets",
    "trivia nights - se":          "Trivia Nights - SE",
    "trivia nights - n/ne":        "Trivia Nights - N/NE",
    "trivia nights - nw/sw":       "Trivia Nights - NW/SW",
    "trivia nights - further out": "Trivia Nights - Further Out",
}

TIMEZONE = "America/Los_Angeles"
DEFAULT_DURATION_MINUTES = 120
SCOPES_CALENDAR = ["https://www.googleapis.com/auth/calendar"]
SCOPES_CALENDAR_AND_SHEETS = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",  # full read+write
]
SCOPES = SCOPES_CALENDAR  # default; overridden to include sheets when --from-sheets

SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"

# ─── Genre tag extraction ─────────────────────────────────────────────────────

GENRE_MAP = [
    (["goth", "gothic", "darkwave", "dark wave", "industrial", "goth-industrial"], "goth"),
    (["punk rock", "punk"], "punk"),
    (["pop-punk", "pop punk"], "pop-punk"),
    (["ska punk", "ska"], "ska"),
    (["metal", "sludge", "doom", "thrash", "death metal", "black metal", "heavy metal"], "metal"),
    (["hardcore"], "hardcore"),
    (["indie rock", "indie"], "indie rock"),
    (["indie folk", "folk rock"], "indie folk"),
    (["folk", "singer songwriter", "singer-songwriter", "americana"], "folk"),
    (["jazz", "live jazz", "experimental jazz", "jazz fusion"], "jazz"),
    (["blues"], "blues"),
    (["hip-hop", "hip hop", "rap", "hiphop"], "hip-hop"),
    (["funk"], "funk"),
    (["soul", "r&b"], "soul"),
    (["reggae", "dub"], "reggae"),
    (["country", "honky tonk", "western"], "country"),
    (["classical", "orchestra", "chamber"], "classical"),
    (["electronic", "electro", "techno", "house", "tech house", "progressive house",
       "deep house", "dubstep", "drum and bass", "dnb", "ambient", "synth",
       "edm", "livetronica", "electro house"], "electronic"),
    (["italo disco", "disco"], "italo disco"),
    (["emo", "post-hardcore"], "emo"),
    (["new wave", "post-punk", "post punk"], "new wave"),
    (["shoegaze"], "shoegaze"),
    (["psych", "psychedelic"], "psych"),
]

def extract_genre(tags_str):
    if not tags_str:
        return None
    tags_lower = tags_str.lower()
    for keywords, label in GENRE_MAP:
        for kw in keywords:
            if kw in tags_lower:
                return label
    return None


# ─── Helper ───────────────────────────────────────────────────────────────────

def get(row, *keys):
    for k in keys:
        if k in row and row[k]:
            return row[k].strip()
    return ""


# ─── Shared Google Sheets client ──────────────────────────────────────────────

def get_sheets_client():
    """Return an authenticated gspread client using the current SCOPES."""
    import gspread
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    token_path = Path("token.json")
    creds_path = Path("credentials.json")

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print("ERROR: credentials.json not found.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return gspread.authorize(creds)


def get_or_clear_tab(sheet, tab_name, cols):
    """Get a worksheet by name (creating it if needed) and clear its contents."""
    import gspread
    try:
        ws = sheet.worksheet(tab_name)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=tab_name, rows=2000, cols=cols)
    return ws


def normalize_calendar(calendar_str):
    """Return a valid canonical calendar name, or 'Portland Events' as fallback.
    Catches cases where source/tag values accidentally end up in the Calendar column.
    """
    if not calendar_str:
        return "Portland Events"
    canonical = CALENDAR_ALIASES.get(calendar_str.strip().lower())
    if canonical:
        return canonical
    if calendar_str.strip() in CALENDARS:
        return calendar_str.strip()
    # Not a recognized value — default to Portland Events and log it
    print(f"  WARNING: Unrecognized calendar '{calendar_str}' — defaulting to Portland Events")
    return "Portland Events"


# ─── Step 1: Sheet-based categorization ───────────────────────────────────────

CATEGORIZE_TAB = "Categorize"
CATEGORIZE_HEADERS = [
    "#", "Title", "Location", "Tags", "Source",
    "Current Calendar", "→ Assigned Calendar (edit this column)",
]
CATEGORIZE_INSTRUCTIONS = (
    "Fill in the '→ Assigned Calendar' column for each event. "
    "Valid values: Portland Events | Portland Live Music | Portland Comedy | Portland Karaoke | Portland Farmers Markets | "
    "Trivia Nights - SE | Trivia Nights - N/NE | Trivia Nights - NW/SW | Trivia Nights - Further Out. "
    "Leave blank to keep the current value. Then return to the terminal and press Enter."
)


def step1_categorize(rows):
    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)
    ws = get_or_clear_tab(sheet, CATEGORIZE_TAB, len(CATEGORIZE_HEADERS))

    # Header + instructions
    ws.update([CATEGORIZE_HEADERS, [CATEGORIZE_INSTRUCTIONS] + [""] * (len(CATEGORIZE_HEADERS) - 1)], "A1")
    ws.batch_format([
        {"range": "A1:G1", "format": {"textFormat": {"bold": True}}},
        {"range": "A2:G2", "format": {"textFormat": {"italic": True},
                                       "backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.8}}},
    ])

    # Event rows (start at row 3)
    data = []
    for i, row in enumerate(rows):
        data.append([
            i,
            get(row, "Title", "title", "summary"),
            get(row, "Location", "location", "Venue", "venue"),
            get(row, "Tags", "tags", "Genre", "genre"),
            get(row, "Source", "source"),
            get(row, "Calendar", "calendar"),
            "",  # Assigned Calendar — user fills this in
        ])
    ws.append_rows(data, value_input_option="USER_ENTERED")

    tab_url = f"{SHEET_URL}#gid={ws.id}"
    print(f"\n{'─' * 70}")
    print("STEP 1: CALENDAR CATEGORIZATION")
    print(f"{'─' * 70}")
    print(f"Sheet tab: {tab_url}")
    print()
    print("── Paste this into Claude if you want help categorizing: ──")
    print()
    print("Assign each event to one of these calendars:")
    print("  Portland Events | Portland Live Music | Portland Comedy | Portland Karaoke | Portland Farmers Markets")
    print("  Trivia Nights - SE | Trivia Nights - N/NE | Trivia Nights - NW/SW | Trivia Nights - Further Out")
    print("Rules: karaoke -> Portland Karaoke; comedy/stand-up/open mic/improv -> Portland Comedy; live band/DJ -> Portland Live Music")
    print()
    for i, row in enumerate(rows):
        title    = get(row, "Title", "title", "summary")
        venue    = get(row, "Location", "location", "Venue", "venue")
        tags     = get(row, "Tags", "tags", "Genre", "genre")
        source   = get(row, "Source", "source")
        existing = get(row, "Calendar", "calendar")
        print(f'  {i:3d}. "{title}" | venue: "{venue}" | tags: "{tags}" | source: "{source}" | current: "{existing}"')
    print()
    print(f"{'─' * 70}")
    print(f"Fill in the '→ Assigned Calendar' column in the sheet, then press Enter:")
    print(f"  {tab_url}")
    print("\nPress Enter when done...")
    input()

    # Read back assigned calendars
    all_values = ws.get_all_values()
    results = [get(r, "Calendar", "calendar") for r in rows]
    for sheet_row in all_values[2:]:  # skip header + instructions rows
        if len(sheet_row) < 7:
            continue
        try:
            idx = int(sheet_row[0])
        except (ValueError, IndexError):
            continue
        assigned = sheet_row[6].strip()
        if assigned and 0 <= idx < len(rows):
            canonical = CALENDAR_ALIASES.get(assigned.lower(), assigned)
            if canonical in CALENDARS:
                results[idx] = canonical
            else:
                print(f"  WARNING: Unrecognized calendar '{assigned}' for row {idx}, keeping original.")

    return results


# ─── Step 2: Sheet-based deduplication ────────────────────────────────────────

DEDUP_TAB = "Dedup"
DEDUP_INCOMING_HEADERS = [
    "#", "Title", "Date", "Location", "Source", "Calendar",
    "→ Skip? (type y to skip)", "Why (auto)",
]
DEDUP_EXISTING_HEADERS = ["Calendar", "Existing Title", "Date"]
DEDUP_INSTRUCTIONS = (
    "Type 'y' in the '→ Skip?' column for any incoming event that duplicates another. "
    "Rows already marked 'y' are auto-detected cross-source duplicates within this "
    "batch (see 'Why (auto)') — clear the 'y' to keep one. Also flag any incoming "
    "event that duplicates an EXISTING calendar event listed below. Then press Enter."
)


def step2_deduplicate(rows, existing_by_cal, cross_source_skip=None, cross_source_dup_of=None):
    cross_source_skip = cross_source_skip or set()
    cross_source_dup_of = cross_source_dup_of or {}

    # Group incoming rows by calendar
    by_cal = {}
    for i, row in enumerate(rows):
        cal = row.get("_calendar_assigned", get(row, "Calendar", "calendar"))
        canonical = CALENDAR_ALIASES.get(cal.lower(), cal)
        by_cal.setdefault(canonical, []).append((i, row))

    # Check if there are any existing events to compare against
    has_existing = any(
        existing_by_cal.get(CALENDARS[cal_name])
        for cal_name in by_cal
        if cal_name in CALENDARS
    )
    # Run the step if there are existing events to compare against OR intra-batch
    # cross-source duplicates to surface for review.
    if not has_existing and not cross_source_skip:
        print("\nNo existing calendar events and no intra-batch duplicates — skipping dedup step.")
        return set()

    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)
    ws = get_or_clear_tab(sheet, DEDUP_TAB, max(len(DEDUP_INCOMING_HEADERS), len(DEDUP_EXISTING_HEADERS)))

    # ── Incoming events section ──
    ws.update([DEDUP_INCOMING_HEADERS, [DEDUP_INSTRUCTIONS] + [""] * (len(DEDUP_INCOMING_HEADERS) - 1)], "A1")
    ws.batch_format([
        {"range": "A1:H1", "format": {"textFormat": {"bold": True}}},
        {"range": "A2:H2", "format": {"textFormat": {"italic": True},
                                       "backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.8}}},
    ])

    # First pass: assign local indices in calendar-grouped order so we can
    # reference the kept ("winner") row's local number in the auto note.
    ordered = [(orig_idx, row, cal_name)
               for cal_name, indexed_rows in by_cal.items()
               for orig_idx, row in indexed_rows]
    index_map = {local: orig for local, (orig, _, _) in enumerate(ordered)}
    orig_to_local = {orig: local for local, (orig, _, _) in enumerate(ordered)}

    incoming_data = []
    prefilled = 0
    for local_counter, (orig_idx, row, cal_name) in enumerate(ordered):
        is_dup = orig_idx in cross_source_skip
        note = ""
        if is_dup:
            prefilled += 1
            winner = cross_source_dup_of.get(orig_idx)
            if winner is not None and winner in orig_to_local:
                note = f"cross-source dup of #{orig_to_local[winner]}"
            else:
                note = "cross-source duplicate (auto)"
        incoming_data.append([
            local_counter,
            get(row, "Title", "title", "summary"),
            get(row, "Date", "date"),
            get(row, "Location", "location", "Venue", "venue"),
            get(row, "Source", "source"),
            cal_name,
            "y" if is_dup else "",  # Skip? — pre-filled for intra-batch dupes
            note,
        ])

    ws.append_rows(incoming_data, value_input_option="USER_ENTERED")

    # ── Existing events section (reference, read-only) ──
    existing_start_row = len(incoming_data) + 4  # leave a blank row gap
    ws.update([["─── EXISTING CALENDAR EVENTS (for reference) ───"], DEDUP_EXISTING_HEADERS], f"A{existing_start_row}")
    ws.batch_format([
        {"range": f"A{existing_start_row}:G{existing_start_row}", "format": {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.85, "green": 0.9, "blue": 1.0},
        }},
        {"range": f"A{existing_start_row + 1}:C{existing_start_row + 1}", "format": {"textFormat": {"bold": True}}},
    ])

    existing_data = []
    for cal_name, indexed_rows in by_cal.items():
        cal_id = CALENDARS.get(cal_name)
        if not cal_id:
            continue
        for ev in existing_by_cal.get(cal_id, [])[:300]:
            start = ev.get("start", {})
            dt = start.get("dateTime", start.get("date", ""))[:10]
            existing_data.append([cal_name, ev.get("summary", ""), dt])

    if existing_data:
        ws.append_rows(existing_data, value_input_option="USER_ENTERED")

    tab_url = f"{SHEET_URL}#gid={ws.id}"
    print(f"\n{'─' * 70}")
    print("STEP 2: DUPLICATE DETECTION")
    print(f"{'─' * 70}")
    print(f"Sheet tab: {tab_url}")
    print()
    print("── Paste this into Claude if you want help spotting duplicates: ──")
    print()
    print("Flag any INCOMING event that duplicates an EXISTING one (same event, different name/source).")
    if prefilled:
        print(f"NOTE: {prefilled} row(s) are pre-marked 'y' as cross-source duplicates within this")
        print("      batch (shown as [DUP] below). Clear the 'y' on any you want to keep.")
    print("Reply with the index numbers to skip, e.g.: skip: 3, 17, 42")
    print()
    print("INCOMING:")
    for entry in incoming_data:
        flag = " [DUP]" if entry[6] == "y" else ""
        print(f'  {entry[0]:3d}. "{entry[1]}" on {entry[2]} @ {entry[3]} [{entry[5]}]{flag}')
    print()
    print("EXISTING (sample):")
    for row in existing_data[:50]:
        print(f'  "{row[1]}" on {row[2]} [{row[0]}]')
    if len(existing_data) > 50:
        print(f'  ... and {len(existing_data) - 50} more (see sheet tab for full list)')
    print()
    print(f"{'─' * 70}")
    print(f"Mark 'y' in the Skip column for duplicates in the sheet, then press Enter:")
    print(f"  {tab_url}")
    print("\nPress Enter when done...")
    input()

    # Read back skip flags
    all_values = ws.get_all_values()
    skip_indices = set()
    for sheet_row in all_values[2:]:  # skip header + instructions
        if len(sheet_row) < 7:
            continue
        skip_flag = sheet_row[6].strip().lower()
        if skip_flag != "y":
            continue
        try:
            local_idx = int(sheet_row[0])
        except (ValueError, IndexError):
            continue
        if local_idx in index_map:
            orig_idx = index_map[local_idx]
            title = get(rows[orig_idx], "Title", "title", "summary")
            print(f"  SKIP (marked duplicate): \"{title}\"")
            skip_indices.add(orig_idx)

    return skip_indices


# ─── Google Calendar auth ─────────────────────────────────────────────────────

def get_service():
    """Return an authenticated Google Calendar API service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    token_path = Path("token.json")
    creds_path = Path("credentials.json")

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print("ERROR: credentials.json not found.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


# ─── Fetch existing events ────────────────────────────────────────────────────

def fetch_existing_events(service, calendar_id, start_date, end_date):
    from googleapiclient.errors import HttpError
    events = []
    page_token = None
    start_iso = f"{start_date}T00:00:00-07:00"
    end_iso   = f"{end_date}T23:59:59-07:00"
    while True:
        try:
            result = service.events().list(
                calendarId=calendar_id,
                timeMin=start_iso,
                timeMax=end_iso,
                maxResults=250,
                singleEvents=True,
                pageToken=page_token,
            ).execute()
        except HttpError as e:
            print(f"  WARNING: Could not fetch events ({e})")
            break
        events.extend(result.get("items", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return events


# ─── Time helpers ─────────────────────────────────────────────────────────────

def parse_time(t):
    if not t:
        return None
    t = t.strip()
    if re.match(r"^\d{1,2}:\d{2}$", t):
        h, m = t.split(":")
        return f"{int(h):02d}:{m}"
    return None

def build_datetime(date_str, time_str):
    return f"{date_str}T{time_str}:00"

def add_duration(date_str, time_str, minutes):
    dt = datetime.strptime(f"{date_str}T{time_str}:00", "%Y-%m-%dT%H:%M:%S")
    dt += timedelta(minutes=minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


# ─── URL resolution + venue map ──────────────────────────────────────────────

# URLs that are listing/index pages, not specific to one event.
# A source URL matching any of these is treated as "not useful".
GENERIC_URL_PATTERNS = [
    r'^https?://(www\.)?dopdx\.com/?$',
    r'^https?://(www\.)?dopdx\.com/events/?$',
    r'^https?://(www\.)?pdxpipeline\.com/?$',
    r'^https?://(www\.)?pdxpipeline\.com/events/?$',
    r'^https?://(www\.)?pdxpipeline\.com/week/?$',
    r'^https?://(www\.)?pdxpipeline\.com/weekend/?$',
    r'^https?://(www\.)?pdxpipeline\.com/portland-[a-z]+-events/?$',
    r'^https?://(www\.)?communityplaylist\.com/?$',
    r'^https?://nearhear\.app/calendar/?$',
    r'^https?://(www\.)?19hz\.info/?.*$',
    r'^https?://(www\.)?travelportland\.com/events/?$',
    r'^https?://(www\.)?queersocialclub\.com/?$',
    r'^https?://(www\.)?queersocialclub\.com/events-portland/?$',
    r'^https?://(www\.)?laughspdx\.com/events/?$',
    r'^https?://(www\.)?flyerescape\.dad/?$',
    r'^https?://calagator\.org/events/?$',
    r'^https?://(www\.)?pc-pdx\.com/show-guide/?$',
]

NOTE_LOOKUP_VENUE = "Look up venue for more details"


def is_generic_url(url):
    """True if the URL is a listing/index page, not specific to one event."""
    if not url:
        return True
    u = url.strip()
    for pat in GENERIC_URL_PATTERNS:
        if re.match(pat, u, re.I):
            return True
    return False


def normalize_venue(location):
    """Normalize a location string to a stable venue key.

    Source feeds describe the same venue inconsistently (curly vs straight
    apostrophes, a leading "The", trailing street addresses, parenthetical or
    "on <street>" qualifiers, ", United States", etc.). We strip those so that,
    e.g., "The Pharmacy (NW 21st), Portland, OR" and
    "The Pharmacy on NW 21st Ave, Portland, OR" both reduce to "pharmacy".

    The SAME function is applied to venues.json keys at load time (see
    load_venue_map), so both sides of the lookup are normalized identically.
    """
    if not location:
        return ""
    s = location
    # Normalize smart punctuation to ASCII so apostrophes/dashes match.
    s = s.translate(str.maketrans({
        "’": "'", "‘": "'", "ʼ": "'",
        "“": '"', "”": '"',
        "–": "-", "—": "-",
    }))
    # Keep only the part before the first comma (drops city/state/country).
    s = s.split(",")[0].lower().strip()
    # Drop parenthetical/bracket qualifiers, e.g. "(NW 21st)".
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s)
    # Drop a trailing street address: a space-delimited number and everything after.
    s = re.sub(r"\s+\d{1,6}\s+.*$", "", s)
    # Drop a trailing "on <street>" qualifier, e.g. "pharmacy on nw 21st ave".
    s = re.sub(r"\s+on\s+\w+.*$", "", s)
    # Drop a leading article.
    s = re.sub(r"^the\s+", "", s)
    # Strip stray punctuation but keep & / ' - which appear in real venue names.
    s = re.sub(r"[^\w'&/ -]", " ", s)
    # Collapse whitespace.
    s = re.sub(r"\s+", " ", s).strip()
    return s


_VENUE_MAP_CACHE = None

def load_venue_map():
    """Load venues.json → {normalized venue name: website}. Cached per run."""
    global _VENUE_MAP_CACHE
    if _VENUE_MAP_CACHE is not None:
        return _VENUE_MAP_CACHE
    path = Path("venues.json")
    mapping = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            mapping = {
                normalize_venue(k): v
                for k, v in raw.items()
                if not k.startswith("_") and v
            }
        except Exception as e:
            print(f"  WARNING: could not load venues.json: {e}")
    _VENUE_MAP_CACHE = mapping
    return mapping


def resolve_event_url(url, location):
    """Return (resolved_url, note).
    - Specific event URL → keep it, no note.
    - Generic/missing URL → venue website if known, else a 'look up venue' note.
    """
    if url and not is_generic_url(url):
        return url, ""

    venue_key = normalize_venue(location)
    venue_map = load_venue_map()
    if venue_key and venue_key in venue_map:
        return venue_map[venue_key], ""

    return "", NOTE_LOOKUP_VENUE


# ─── Facet classification (for calendar extendedProperties) ──────────────────

AGE_TAGS = {"all-ages", "21+", "18+", "19+", "16+"}
NEIGHBORHOOD_TAGS = {
    "se", "ne", "nw", "sw", "n", "downtown", "pearl", "alberta", "hawthorne",
    "belmont", "division", "mississippi", "sellwood", "hollywood", "st johns",
    "st-johns", "foster", "burnside", "goose hollow", "nob hill", "82nd",
    "montavilla", "woodstock", "kenton", "old town", "central eastside",
    "laurelhurst", "beaverton", "hillsboro", "vancouver", "troutdale",
}


def classify_cost(cost):
    """Bucket a cost string into 'free' | 'paid' | 'unknown'."""
    c = (cost or "").strip().lower()
    if not c:
        return "unknown"
    if re.search(r"\bfree\b|no cover|\$0\b|donation|pwyc|pay what", c):
        return "free"
    if re.search(r"\$\s?\d", c):
        return "paid"
    return "unknown"


def classify_facets(tags_str):
    """Split a comma-separated tag string into typed facets.
    Returns (genres:list, age:str, neighborhood:str, all_tags:list).
    """
    tags = [t.strip().lower() for t in (tags_str or "").split(",") if t.strip()]
    genres, age, hood = [], "", ""
    for t in tags:
        if t in AGE_TAGS and not age:
            age = t
        elif t in NEIGHBORHOOD_TAGS and not hood:
            hood = t
        else:
            genres.append(t)
    return genres, age, hood, tags


def build_extended_properties(cost, tags_str, source):
    """Build extendedProperties.shared for a calendar event so the website
    can filter by cost/genre/age/neighborhood. Only non-empty keys are included.
    Uses 'shared' (not 'private') so an API-key reader can see them.
    """
    genres, age, hood, all_tags = classify_facets(tags_str)
    shared = {"cost": classify_cost(cost)}
    if genres:
        shared["genres"] = ",".join(genres)
    if age:
        shared["age"] = age
    if hood:
        shared["neighborhood"] = hood
    if all_tags:
        shared["tags"] = ",".join(all_tags)
    if source:
        shared["source"] = source
    return {"shared": shared}


# ─── Description and title builders ──────────────────────────────────────────

def build_description(cost, url, note="", tags=""):
    """Build the calendar event description. The website parses this at build
    time, so it doubles as the facet store: a final "Tags:" line carries the
    full tag list (genres/age/neighborhood are derived from it). Keeping facets
    here — not just in extendedProperties — means events stay editable in the
    Google Calendar UI and manually-added events get tagged too.
    """
    lines = []
    if cost and cost.strip():
        lines.append(cost.strip())
    if url and url.strip():
        lines.append(url.strip())
    elif note:
        lines.append(note)
    tag_list = [t.strip().lower() for t in (tags or "").split(",") if t.strip()]
    if tag_list:
        # dict.fromkeys dedupes while preserving order
        lines.append("Tags: " + ", ".join(dict.fromkeys(tag_list)))
    return "\n".join(lines)

def build_title(title_raw, cal_name, tags):
    title = re.sub(r'\s*-\s*$', '', title_raw.strip()).strip()
    if cal_name == "Portland Live Music":
        genre = extract_genre(tags)
        if genre:
            return f"[{genre}] {title}"
    if cal_name == "Portland Comedy":
        if not title.lower().startswith("[comedy]"):
            return f"[comedy] {title}"
    return title

def resolve_calendar(calendar_str):
    key = calendar_str.strip().lower()
    canonical = CALENDAR_ALIASES.get(key)
    if not canonical:
        for alias, name in CALENDAR_ALIASES.items():
            if alias in key or key in alias:
                canonical = name
                break
    if not canonical or canonical not in CALENDARS:
        return None
    return canonical, CALENDARS[canonical]


# ─── Review tab (disposition + preview) ──────────────────────────────────────

REVIEW_TAB = "Review"
REVIEW_HEADERS = [
    "→ Include? (y/n)", "#", "Date", "Time", "Calendar",
    "Title", "Location", "Cost", "Tags", "Source", "URL", "Calendar Link",
]
REVIEW_INSTRUCTIONS = (
    "Type 'y' in the Include column to add an event, 'n' to skip. "
    "You can also EDIT any of Date, Time, Calendar, Title, Location, Cost, Tags, URL — "
    "your edits are written to the calendar. "
    "Suggested duplicates are pre-filled 'n' (highlighted). "
    "'Calendar Link' shows the link the event will get; rows flagged 'look up venue' "
    "have no specific link (add the venue to venues.json, or paste a URL in the URL column). "
    "When done, return to the terminal and press Enter."
)

def write_review_tab(events):
    """Write all candidate events to the Review tab for disposition.

    Each event dict must have keys:
      index, title, date, time, calendar, location, cost, tags, source, url, suggested_skip
    Returns the worksheet so the caller can read it back later.
    """
    import time

    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)
    ws = get_or_clear_tab(sheet, REVIEW_TAB, len(REVIEW_HEADERS))

    # Write header + instructions in one batch, then pause to avoid quota
    ws.update([REVIEW_HEADERS, [REVIEW_INSTRUCTIONS] + [""] * (len(REVIEW_HEADERS) - 1)], "A1")
    time.sleep(1)

    data = []
    dup_rows = []     # 1-indexed sheet rows to highlight (duplicates)
    lookup_rows = []  # 1-indexed sheet rows needing a venue lookup
    for e in events:
        include_suggestion = "n" if e.get("suggested_skip") else ""

        # Resolve what calendar link this event will actually get
        loc_for_url = e["location"]
        resolved_url, url_note = resolve_event_url(e["url"], loc_for_url)
        link_display = resolved_url if resolved_url else f"⚠ {url_note}"

        data.append([
            include_suggestion,
            e["index"],
            e["date"],
            e["time"],
            e["calendar"],
            e["title"],
            e["location"],
            e["cost"],
            e["tags"],
            e["source"],
            e["url"],
            link_display,
        ])
        sheet_row = len(data) + 2  # +2 for header + instructions rows
        if e.get("suggested_skip"):
            dup_rows.append(sheet_row)
        if not resolved_url:
            lookup_rows.append(sheet_row)

    if data:
        ws.append_rows(data, value_input_option="USER_ENTERED")
        time.sleep(1)

    # Format header + instructions + dup rows + lookup-link cells in one batch
    formats = [
        {"range": "A1:L1", "format": {"textFormat": {"bold": True}}},
        {"range": "A2:L2", "format": {
            "textFormat": {"italic": True},
            "backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.8},
        }},
    ]
    dup_fmt = {"backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.6}}
    for row_num in dup_rows:
        formats.append({"range": f"A{row_num}:L{row_num}", "format": dup_fmt})
    # Highlight just the Calendar Link cell (column L) for lookup-needed rows
    lookup_fmt = {"backgroundColor": {"red": 1.0, "green": 0.85, "blue": 0.85}}
    for row_num in lookup_rows:
        formats.append({"range": f"L{row_num}", "format": lookup_fmt})
    ws.batch_format(formats)

    tab_url = f"{SHEET_URL}#gid={ws.id}"
    print(f"\n{'─' * 70}")
    print("REVIEW: Fill in the Include column")
    print(f"{'─' * 70}")
    print(f"Open the '{REVIEW_TAB}' tab, mark y/n for each event, then press Enter:")
    print(f"  {tab_url}")
    print("  (Yellow rows = suggested duplicates, pre-filled 'n')")
    if lookup_rows:
        print(f"  (Red 'Calendar Link' cells = {len(lookup_rows)} events with no specific link — add venues to venues.json)")
    print("\nPress Enter when done...")
    input()

    return ws


def read_review_tab(ws):
    """Read back the Include column plus all editable fields from the Review tab.

    Any edits you make in the sheet to Date, Time, Calendar, Title, Location,
    Cost, Tags, or URL are read back and applied before the calendar write.

    Column layout (0-indexed):
      0 Include | 1 # | 2 Date | 3 Time | 4 Calendar | 5 Title
      6 Location | 7 Cost | 8 Tags | 9 Source | 10 URL | 11 Calendar Link

    Returns:
        include_indices: set of original indices marked 'y'
        overrides: dict {idx: {field: value}} of the current cell values
    """
    all_values = ws.get_all_values()
    include_indices = set()
    overrides = {}

    def cell(row, i):
        return row[i].strip() if len(row) > i else ""

    for sheet_row in all_values[2:]:  # skip header + instructions
        if not sheet_row:
            continue
        include_flag = cell(sheet_row, 0).lower()
        if include_flag != "y":
            continue
        try:
            idx = int(sheet_row[1])
        except (ValueError, IndexError):
            continue
        include_indices.add(idx)

        ov = {
            "date":     cell(sheet_row, 2),
            "time":     cell(sheet_row, 3),
            "title":    cell(sheet_row, 5),
            "location": cell(sheet_row, 6),
            "cost":     cell(sheet_row, 7),
            "tags":     cell(sheet_row, 8),
            "url":      cell(sheet_row, 10),
        }
        # Calendar must be a valid calendar name
        cal_raw = cell(sheet_row, 4)
        canonical = CALENDAR_ALIASES.get(cal_raw.lower(), cal_raw)
        if canonical in CALENDARS:
            ov["calendar"] = canonical

        overrides[idx] = ov

    return include_indices, overrides


# ─── Read already-filled Categorize and Dedup tabs ───────────────────────────

def read_categorize_tab():
    """Read calendar assignments from an already-filled Categorize tab.
    Returns a dict of {data_index: calendar_name}.
    """
    client = get_sheets_client()
    ws = client.open_by_key(SHEET_ID).worksheet(CATEGORIZE_TAB)
    all_values = ws.get_all_values()
    assignments = {}
    for row in all_values[2:]:  # skip header + instructions
        if not row or not row[0].isdigit():
            continue
        idx = int(row[0])
        assigned = row[6].strip() if len(row) > 6 else ""
        current  = row[5].strip() if len(row) > 5 else ""
        cal = assigned or current
        if cal:
            canonical = CALENDAR_ALIASES.get(cal.lower(), cal)
            if canonical in CALENDARS:
                assignments[idx] = canonical
    return assignments


def read_dedup_tab():
    """Read skip flags from an already-filled Dedup tab.
    Returns a set of data indices marked 'y'.
    """
    client = get_sheets_client()
    ws = client.open_by_key(SHEET_ID).worksheet(DEDUP_TAB)
    all_values = ws.get_all_values()
    skip_indices = set()
    for row in all_values[2:]:  # skip header + instructions
        if not row or not row[0].isdigit():
            continue
        if row[6].strip().lower() == "y" if len(row) > 6 else False:
            skip_indices.add(int(row[0]))
    return skip_indices


# ─── Blocklist ───────────────────────────────────────────────────────────────

BLOCKLIST_TAB = "Blocklist"
BLOCKLIST_HEADERS = ["Title (normalized)", "Title (original)", "Source", "Date added"]


def _norm_title(s):
    """Normalize a title for blocklist matching — lowercase, strip punctuation."""
    import re
    return re.sub(r"[^a-z0-9 ]", "", s.lower().strip())[:60]


def load_blocklist():
    """Return a set of normalized titles that should be auto-skipped."""
    import gspread
    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)
    try:
        ws = sheet.worksheet(BLOCKLIST_TAB)
    except gspread.WorksheetNotFound:
        return set()
    rows = ws.get_all_values()
    return {row[0].strip() for row in rows[1:] if row and row[0].strip()}


def update_blocklist(skipped_events):
    """Add newly user-skipped events to the Blocklist tab.

    skipped_events: list of review_event dicts that were marked 'n' by the user
                    and were NOT already flagged as duplicates.
    """
    if not skipped_events:
        return

    import gspread
    from datetime import date
    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)

    try:
        ws = sheet.worksheet(BLOCKLIST_TAB)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=BLOCKLIST_TAB, rows=2000, cols=len(BLOCKLIST_HEADERS))
        ws.update([BLOCKLIST_HEADERS], "A1")
        ws.batch_format([{"range": "A1:D1", "format": {"textFormat": {"bold": True}}}])

    # Get existing normalized titles to avoid dupes
    existing = {row[0].strip() for row in ws.get_all_values()[1:] if row and row[0].strip()}

    today = date.today().isoformat()
    new_rows = []
    for e in skipped_events:
        norm = _norm_title(e["title"])
        if norm and norm not in existing:
            new_rows.append([norm, e["title"], e.get("source", ""), today])
            existing.add(norm)

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        print(f"  Added {len(new_rows)} title(s) to blocklist")


# ─── Load from Google Sheet ───────────────────────────────────────────────────

def load_from_sheet():
    """Read the Inbox tab from the Portland Events Google Sheet.
    Returns a list of dicts with the same keys as the TSV reader produces.
    """
    import gspread
    client = get_sheets_client()
    sheet = client.open_by_key(SHEET_ID)

    try:
        ws = sheet.worksheet(INBOX_TAB)
    except gspread.WorksheetNotFound:
        print(f"ERROR: Tab '{INBOX_TAB}' not found in sheet.")
        sys.exit(1)

    all_values = ws.get_all_records(default_blank="")
    rows = [{k.strip(): str(v).strip() for k, v in row.items()} for row in all_values]
    print(f"Loaded {len(rows)} rows from Google Sheet '{INBOX_TAB}' tab")
    return rows


# ─── Fuzzy cross-source dedup ────────────────────────────────────────────────

def _fuzzy_dedup_incoming(rows):
    """
    Find incoming events that are likely the same show scraped from two different
    sources. Returns (skip, dup_of):
      - skip:   set of row indices to flag as intra-batch duplicates (the losers)
      - dup_of: {loser_index: winner_index} — which kept event each duplicates

    Strategy: for each pair of events on the same date from different sources,
    compute word overlap of their titles. If overlap is high enough, flag the
    lower-priority one (prefer sources with more detail: longer title, has location).

    Source priority (higher = keep): PDX After Dark > PC-PDX > 19hz > Flyer Escape > others
    """
    import re

    SOURCE_PRIORITY = {
        "PDX After Dark": 6,
        "PC-PDX Show Guide": 5,
        "19hz PNW": 4,
        "Flyer Escape": 3,
        "Laughs PDX": 2,
        "Calagator": 1,
    }
    OVERLAP_THRESHOLD = 0.55  # 55% word overlap → likely same event

    def _words(s):
        # Significant words only — strip articles, conjunctions, punctuation
        stop = {"the", "a", "an", "and", "&", "with", "w", "at", "in", "of",
                "feat", "ft", "vs", "plus", "+", "•", "-"}
        return {w for w in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split() if w not in stop and len(w) > 1}

    def _overlap(a, b):
        wa, wb = _words(a), _words(b)
        if not wa or not wb:
            return 0.0
        return len(wa & wb) / min(len(wa), len(wb))

    # Group by date
    by_date = {}
    for i, row in enumerate(rows):
        date = get(row, "Date", "date")
        if date:
            by_date.setdefault(date, []).append(i)

    skip = set()
    dup_of = {}
    for date, indices in by_date.items():
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                ia, ib = indices[a], indices[b]
                if ia in skip or ib in skip:
                    continue
                ra, rb = rows[ia], rows[ib]
                src_a = get(ra, "Source", "source")
                src_b = get(rb, "Source", "source")
                if src_a == src_b:
                    continue  # same source handled by scraper-level dedup
                ta = get(ra, "Title", "title", "summary")
                tb = get(rb, "Title", "title", "summary")
                if _overlap(ta, tb) >= OVERLAP_THRESHOLD:
                    # Flag the lower-priority source; break ties by detail score
                    pri_a = SOURCE_PRIORITY.get(src_a, 0)
                    pri_b = SOURCE_PRIORITY.get(src_b, 0)
                    det_a = len(ta) + bool(get(ra, "Location", "location")) * 20
                    det_b = len(tb) + bool(get(rb, "Location", "location")) * 20
                    score_a = pri_a * 100 + det_a
                    score_b = pri_b * 100 + det_b
                    loser, winner = (ib, ia) if score_a >= score_b else (ia, ib)
                    skip.add(loser)
                    dup_of[loser] = winner

    if skip:
        print(f"  Cross-source fuzzy dedup: {len(skip)} likely duplicates flagged")
    return skip, dup_of


# ─── Main ─────────────────────────────────────────────────────────────────────

def add_events(tsv_path=None, dry_run=False, no_ai=False, from_sheets=False, skip_to_review=False):
    from googleapiclient.errors import HttpError

    # ── Load all rows (no include filter yet) ────────────────────────────────
    if from_sheets:
        rows = load_from_sheet()
    else:
        rows = []
        with open(tsv_path, newline="", encoding="utf-8") as f:
            sample = f.read(4096)
            f.seek(0)
            dialect = "excel-tab" if "\t" in sample else "excel"
            reader = csv.DictReader(f, dialect=dialect)
            for row in reader:
                rows.append({k.strip(): v.strip() for k, v in row.items()})
        print(f"Loaded {len(rows)} rows from {tsv_path}")

    # Filter out rows with no date — nothing to add
    rows = [r for r in rows if get(r, "Date", "date")]
    if not rows:
        print("No rows with dates found. Nothing to do.")
        return

    print(f"  {len(rows)} rows with dates to process")

    # ── Normalize calendar values ────────────────────────────────────────────
    for row in rows:
        raw_cal = get(row, "Calendar", "calendar")
        row["Calendar"] = normalize_calendar(raw_cal)

    # ── Auto-detect comedy events ─────────────────────────────────────────────
    # Events from generic sources (PDX After Dark, Calagator, etc.) may land in
    # Portland Events or Portland Live Music — promote obvious comedy to Portland Comedy.
    COMEDY_KEYWORDS = [
        "comedy", "stand-up", "stand up", "standup", "open mic", "improv",
        "roast battle", "laugh", "comedian", "comic", "joke night",
    ]
    KARAOKE_KEYWORDS = ["karaoke"]

    comedy_fixed = karaoke_fixed = 0
    for row in rows:
        current = row.get("Calendar", "")
        if current in ("Portland Events", "Portland Live Music"):
            title_l = get(row, "Title", "title", "summary").lower()
            if any(kw in title_l for kw in KARAOKE_KEYWORDS):
                row["Calendar"] = "Portland Karaoke"
                karaoke_fixed += 1
            elif any(kw in title_l for kw in COMEDY_KEYWORDS):
                row["Calendar"] = "Portland Comedy"
                comedy_fixed += 1
    if comedy_fixed:
        print(f"  Auto-detected {comedy_fixed} comedy events -> Portland Comedy")
    if karaoke_fixed:
        print(f"  Auto-detected {karaoke_fixed} karaoke events -> Portland Karaoke")

    # ── Connect to calendar + fetch existing events ──────────────────────────
    print("\nConnecting to Google Calendar...")
    service = get_service()

    all_dates = [get(r, "Date", "date") for r in rows]
    min_date, max_date = min(all_dates), max(all_dates)
    print(f"Fetching existing events ({min_date} to {max_date})...")

    existing_by_cal = {}
    existing_titles_by_cal = {}
    for cal_name, cal_id in CALENDARS.items():
        evs = fetch_existing_events(service, cal_id, min_date, max_date)
        existing_by_cal[cal_id] = evs
        existing_titles_by_cal[cal_id] = {ev.get("summary", "").lower().strip() for ev in evs}
        if evs:
            print(f"  {cal_name}: {len(evs)} existing")

    # ── Intra-batch cross-source dedup (computed up front) ───────────────────
    # The same show scraped from two sources (slightly different caps / punctuation
    # / partial lineup) is detected here so it can be surfaced in the Dedup step
    # (pre-filled 'y') rather than only auto-applied at Review.
    cross_source_skip, cross_source_dup_of = _fuzzy_dedup_incoming(rows)

    # ── Step 1: Categorize + Step 2: Deduplicate ─────────────────────────────
    if skip_to_review:
        # Read already-filled Categorize and Dedup tabs — skip interactive steps
        print("\nReading Categorize tab...")
        cat_assignments = read_categorize_tab()
        for i, row in enumerate(rows):
            assigned = cat_assignments.get(i)
            row["_calendar_assigned"] = assigned or get(row, "Calendar", "calendar")
        print(f"  {len(cat_assignments)} calendar assignments read")

        print("Reading Dedup tab...")
        ai_skip = read_dedup_tab()
        print(f"  {len(ai_skip)} events flagged as duplicates")
    else:
        if no_ai:
            calendar_assignments = [get(r, "Calendar", "calendar") for r in rows]
        else:
            calendar_assignments = step1_categorize(rows)
        for i, row in enumerate(rows):
            row["_calendar_assigned"] = calendar_assignments[i]

        if no_ai:
            # No interactive dedup tab; still apply the auto intra-batch skips.
            ai_skip = set(cross_source_skip)
        else:
            ai_skip = step2_deduplicate(rows, existing_by_cal,
                                        cross_source_skip, cross_source_dup_of)

    # ── Exact-match dedup against existing calendar events ──────────────────
    exact_skip = set()
    for i, row in enumerate(rows):
        calendar_str = row.get("_calendar_assigned") or get(row, "Calendar", "calendar")
        cal_result = resolve_calendar(calendar_str)
        if not cal_result:
            continue
        _, cal_id = cal_result
        title_raw = get(row, "Title", "title", "summary")
        tags      = get(row, "Tags", "tags")
        cal_name  = cal_result[0]
        title     = build_title(title_raw, cal_name, tags)
        existing_titles = existing_titles_by_cal.get(cal_id, set())
        if title.lower().strip() in existing_titles or title_raw.lower().strip() in existing_titles:
            exact_skip.add(i)

    # ── Load blocklist ───────────────────────────────────────────────────────
    print("Loading blocklist...")
    blocklist = load_blocklist()
    if blocklist:
        print(f"  {len(blocklist)} blocked titles loaded")

    # ── Build Review tab entries ─────────────────────────────────────────────
    review_events = []
    skipped_no_cal = []

    for i, row in enumerate(rows):
        title_raw    = get(row, "Title", "title", "summary")
        date_str     = get(row, "Date", "date")
        time_str     = get(row, "Time", "time", "Start Time", "start_time")
        location     = get(row, "Location", "location", "Venue", "venue")
        cost         = get(row, "Cost", "cost")
        calendar_str = row.get("_calendar_assigned") or get(row, "Calendar", "calendar")
        tags         = get(row, "Tags", "tags", "Genre", "genre")
        source       = get(row, "Source", "source")
        url          = get(row, "URL", "url", "link", "Link")

        cal_result = resolve_calendar(calendar_str)
        if not cal_result:
            skipped_no_cal.append((title_raw, calendar_str))
            continue
        cal_name, _ = cal_result
        title = build_title(title_raw, cal_name, tags)

        loc = location.strip() if location else ""
        cities = [", OR", ", WA", ", CA", "Portland", "Vancouver", "Troutdale",
                  "Canby", "Beaverton", "Hillsboro", "Lake Oswego", "Gresham"]
        if loc and not any(c in loc for c in cities):
            loc = f"{loc}, Portland, OR"

        review_events.append({
            "index":          i,
            "title":          title,
            "date":           date_str,
            "time":           time_str,
            "calendar":       cal_name,
            "location":       loc,
            "cost":           cost,
            "tags":           tags,
            "source":         source,
            "url":            url,
            # ai_skip already includes intra-batch cross-source dupes (via the
            # Dedup tab, or set(cross_source_skip) under --no-ai).
            "suggested_skip": (i in ai_skip or i in exact_skip
                               or _norm_title(title) in blocklist
                               or "sold out" in title.lower()),
            # stash for later use
            "_row":           row,
        })

    if skipped_no_cal:
        print(f"\nWARNING: {len(skipped_no_cal)} rows skipped (unrecognized calendar):")
        for t, c in skipped_no_cal:
            print(f"  '{c}' -> {t}")

    if not review_events:
        print("No events to review.")
        return

    # Sort by source then date for easier bulk review
    review_events.sort(key=lambda e: (e["source"], e["date"], e["time"]))

    # ── Write Review tab, wait for disposition ───────────────────────────────
    review_ws = write_review_tab(review_events)
    include_indices, overrides = read_review_tab(review_ws)

    # Apply any manual field edits made in the Review tab. Any of these columns
    # can be edited in the sheet and the edit flows to the calendar write.
    EDITABLE_FIELDS = ["date", "time", "calendar", "title", "location", "cost", "tags", "url"]
    review_by_index = {e["index"]: e for e in review_events}
    edited_count = 0
    for idx, ov in overrides.items():
        e = review_by_index.get(idx)
        if not e:
            continue
        row_edited = False
        for field in EDITABLE_FIELDS:
            new_val = ov.get(field, "")
            # calendar only present in ov when valid; skip empty values so a
            # blank cell never wipes a field
            if new_val and str(e.get(field, "")) != str(new_val):
                e[field] = new_val
                row_edited = True
        if row_edited:
            edited_count += 1
    if edited_count:
        print(f"  {edited_count} event(s) had manual edits from the Review tab applied")

    # ── Update blocklist with user-skipped events ────────────────────────────
    # Only add events the user actively chose to skip — not ones already flagged
    # as duplicates (those are handled by dedup, not user preference).
    already_flagged = ai_skip | exact_skip | cross_source_skip
    user_skipped = [
        review_by_index[e["index"]]
        for e in review_events
        if e["index"] not in include_indices
        and e["index"] not in already_flagged
        and not e.get("suggested_skip")  # wasn't pre-suggested, user chose this
    ]
    if user_skipped:
        print(f"\nAdding {len(user_skipped)} user-skipped event(s) to blocklist...")
        update_blocklist(user_skipped)

    print(f"\n{len(include_indices)} events marked 'y' to add.")

    if not include_indices:
        print("Nothing to add.")
        return

    if dry_run:
        _review_by_index = {e["index"]: e for e in review_events}
        print("\n[DRY RUN] The following would be added to the calendar:")
        for idx in sorted(include_indices):
            e = _review_by_index.get(idx)
            if e:
                print(f"  {e['date']}  {e['calendar']:<30}  {e['title']}")
        print("\n[DRY RUN] No events were written to the calendar.")
        return

    # ── Confirm before writing ───────────────────────────────────────────────
    print(f"\nAbout to add {len(include_indices)} events to Google Calendar.")
    confirm = input("Type 'yes' to confirm, anything else to cancel: ").strip().lower()
    if confirm != "yes":
        print("Cancelled. No events were added.")
        return

    # ── Add events marked y ──────────────────────────────────────────────────
    added, errors = [], []

    # Build a lookup from index -> review_event
    review_by_index = {e["index"]: e for e in review_events}

    for idx in sorted(include_indices):
        e = review_by_index.get(idx)
        if not e:
            continue

        row          = e["_row"]
        title        = e["title"]
        date_str     = e["date"]
        time_str     = e["time"]
        cal_name     = e["calendar"]
        loc          = e["location"]
        cost         = e["cost"]
        url          = e["url"]
        tags         = e.get("tags", "")
        source       = e.get("source", "")
        end_time_str = get(row, "End Time", "end_time", "EndTime")
        duration_str = get(row, "Duration (min)", "duration", "Duration")

        # Farmers markets and trivia are free by default — only carry a cost when
        # a price is explicitly stated. (The website applies the same default at
        # read time, incl. for the imported Pedalpalooza bike calendar.)
        if cal_name in FREE_DEFAULT_CALENDARS and classify_cost(cost) != "paid":
            cost = "Free"

        cal_id = CALENDARS[cal_name]

        start_t = parse_time(time_str)
        end_t   = parse_time(end_time_str)

        if start_t:
            start_dt = build_datetime(date_str, start_t)
            if end_t and end_t != start_t:
                end_hm   = int(end_t.split(":")[0]) * 60 + int(end_t.split(":")[1])
                start_hm = int(start_t.split(":")[0]) * 60 + int(start_t.split(":")[1])
                if end_hm <= start_hm:
                    next_day = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                    end_dt = build_datetime(next_day, end_t)
                else:
                    end_dt = build_datetime(date_str, end_t)
            elif duration_str and duration_str.isdigit():
                end_dt = add_duration(date_str, start_t, int(duration_str))
            else:
                end_dt = add_duration(date_str, start_t, DEFAULT_DURATION_MINUTES)
            all_day = False
        else:
            start_dt = f"{date_str}T00:00:00"
            next_day = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            end_dt   = f"{next_day}T00:00:00"
            all_day  = True

        resolved_url, url_note = resolve_event_url(url, loc)
        description = build_description(cost, resolved_url, url_note, tags)
        event_body = {
            "summary":     title,
            "description": description,
            "location":    loc,
            "start": {"dateTime": start_dt, "timeZone": TIMEZONE} if not all_day else {"date": date_str},
            "end":   {"dateTime": end_dt,   "timeZone": TIMEZONE} if not all_day else {"date": next_day},
            "extendedProperties": build_extended_properties(cost, tags, source),
        }

        if dry_run:
            print(f"  [DRY RUN] {date_str}  {cal_name:<30}  {title}")
            added.append((title, date_str, cal_name))
            continue

        try:
            service.events().insert(
                calendarId=cal_id,
                body=event_body,
                sendUpdates="none",
            ).execute()
            added.append((title, date_str, cal_name))
        except HttpError as e:
            errors.append((title, date_str, str(e)))

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"SUMMARY{' (DRY RUN)' if dry_run else ''}")
    print("=" * 65)
    print(f"Added:            {len(added)}")
    print(f"Skipped (n/blank):{len(review_events) - len(include_indices)}")
    print(f"Errors:           {len(errors)}")

    if added:
        print("\n-- Added --")
        for title, d, cal in added:
            print(f"  {d}  {cal:<30}  {title}")

    if errors:
        print("\n-- Errors --")
        for title, d, err in errors:
            print(f"  {d}  {title}: {err}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Bulk-add Portland events with sheet-based categorization, dedup, and review"
    )
    parser.add_argument("tsv", nargs="?",
                        help="Path to TSV or CSV file of events (omit if using --from-sheets)")
    parser.add_argument("--from-sheets", action="store_true",
                        help="Read events directly from the Portland Events Inbox Google Sheet")
    parser.add_argument("--dry-run", action="store_true",
                        help="Go through all steps but don't write to calendar")
    parser.add_argument("--no-ai", action="store_true",
                        help="Skip categorize and dedup steps, use scrapers' calendar assignment as-is")
    parser.add_argument("--skip-to-review", action="store_true",
                        help="Skip categorize and dedup steps, read already-filled tabs and go straight to Review")
    args = parser.parse_args()

    if not args.from_sheets and not args.tsv:
        parser.error("Provide a TSV file path or use --from-sheets")

    if args.tsv and not Path(args.tsv).exists():
        print(f"ERROR: File not found: {args.tsv}")
        sys.exit(1)

    # Sheets access requires broader scopes
    if args.from_sheets:
        SCOPES = SCOPES_CALENDAR_AND_SHEETS

    add_events(
        tsv_path=args.tsv,
        dry_run=args.dry_run,
        no_ai=args.no_ai,
        from_sheets=args.from_sheets,
        skip_to_review=args.skip_to_review,
    )
