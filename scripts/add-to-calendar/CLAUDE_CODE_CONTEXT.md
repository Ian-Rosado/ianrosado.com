# Portland Events — Claude Code Context

## Project Overview
This is a script-based workflow for bulk-adding events to Ian's Portland Events
Google Calendars from a TSV file output by a web scraper.

## Script Location
`C:\Users\nai19\Documents\GitHub\ianrosado.com\scripts\add-to-calendar\portland_events_add.py`

Also needs `credentials.json` in the same folder (already there).

## What the Script Does
1. Reads a TSV file of events (output from a Chrome scraping workflow)
2. **Step 1 — Categorization**: Prints a block of events for Claude to assign to the correct calendar, waits for JSON response pasted back by the user
3. **Step 2 — Deduplication**: Fetches existing calendar events, prints a comparison block for Claude to flag fuzzy duplicates (name differences across sources), waits for JSON response
4. Adds clean events to the correct Google Calendar

## CLI Usage
```bash
# Read directly from Google Sheet (preferred workflow)
python portland_events_add.py --from-sheets               # full run from sheet
python portland_events_add.py --from-sheets --dry-run     # preview only
python portland_events_add.py --from-sheets --no-ai       # skip AI steps

# Read from TSV/CSV file (legacy / offline use)
python portland_events_add.py events.tsv                  # full run
python portland_events_add.py events.tsv --dry-run        # preview only
python portland_events_add.py events.tsv --categorize-only # step 1 only, writes *_categorized.tsv
python portland_events_add.py events.tsv --no-ai          # skip both AI steps
```

## Google Sheet Source
When using `--from-sheets`, the script reads from:
- **Sheet**: Portland Events Inbox
- **ID**: `1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4`
- **Tab**: Inbox
- Only rows where `include == "y"` are processed (same as TSV workflow)
- Requires `spreadsheets.readonly` scope in addition to calendar scope
- On first run with `--from-sheets`, a new browser auth will be needed to grant the extra scope
  (delete `token.json` first if you get a scope mismatch error)

## TSV Schema (scraper output columns)
```
include | Title | Date | Time | End Time | Duration (min) | Location | Cost | Calendar | Tags | Source | URL | Added
```
- `include`: "y" to add, "n" to skip
- `Date`: YYYY-MM-DD
- `Time` / `End Time`: HH:MM (24hr). If End Time == Start Time or is blank, defaults to 2-hour duration
- `Calendar`: existing category from scraper (may be wrong — Step 1 corrects this)
- `Tags`: comma-separated genre/type tags used for genre prefix on Live Music events

## Calendars
| Name | ID |
|---|---|
| Portland Events | `6218570f10546f6f03748bbd25adcde299bfd55ef4741d8d1520e79653d9c9f6@group.calendar.google.com` |
| Portland Live Music | `34ae96ffcf119eb4dbf6acf86b0886273efeb8a702ed6e9267ef3d24f0e9a1f7@group.calendar.google.com` |
| Portland Farmers Markets | `560e859bd2c7b5dfd2262cb6f28389921434606cec955e7ec75f02df9fd2138a@group.calendar.google.com` |
| Trivia Nights – SE | `441feafdb38c603cde09cd9a60e4f8ed10be90a21eb26dee01db64d0c8594a88@group.calendar.google.com` |
| Trivia Nights – N/NE | `561e4a90958248768cba407c23d37f1293e28f3749bc14de503d258fc03a48c7@group.calendar.google.com` |
| Trivia Nights – NW/SW | `088af359972350285c1e5bccda5fb38c349d0597d7c795ef3d1c21d7b973e457@group.calendar.google.com` |
| Trivia Nights – Further Out | `ac0a6fedb05274655f5e68e9ec26c3f9b341866ae0feed97dd703e94f164a0bf@group.calendar.google.com` |

## Event Formatting Rules
- **Live Music events**: prepend genre tag to title e.g. `[punk] Band Name`
  - Genre comes from Tags column; if unclear or missing, omit tag
  - Pick most specific genre: `[techno]` over `[electronic]`
- **Description format**: `cost\n URL ` (cost on line 1, URL on line 2 with spaces)
- **Location**: if no city in location string, append `, Portland, OR`
- Strip trailing dashes from venue names (scraper artifact): `"No Fun -"` → `"No Fun"`
- **Midnight-crossing events**: if end time < start time, end is next day
- **Default duration**: 2 hours when end time = start time or is missing
- `sendUpdates: none` on all inserts (no notifications)
- Timezone: `America/Los_Angeles`

## Google Auth
- `credentials.json`: OAuth 2.0 Desktop app credentials (already in script folder)
- `token.json`: saved after first browser authorization (auto-generated)
- Scopes: `https://www.googleapis.com/auth/calendar`
- First run opens a browser for authorization

## Dependencies
```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

## Reading the Sheet from Claude Code (AI Steps)

When helping with the Categorize or Dedup steps, **do not use the Drive MCP tool** — the spreadsheet is too large (111K+ chars) and exceeds the read limit.

Instead, read the tab directly with Python using the event-scrapers credentials:

```python
import gspread, json, sys
from google.oauth2.credentials import Credentials
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
SHEET_ID = "1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4"

creds = Credentials.from_authorized_user_file(
    str(Path(r"C:\Users\nai19\Documents\GitHub\ianrosado.com\scripts\event-scrapers\credentials\token.json")),
    ["https://www.googleapis.com/auth/spreadsheets"]
)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID)
ws = sheet.worksheet("Categorize")   # or "Dedup", "Review"
rows = ws.get_all_values()
```

**Categorize tab row layout:**
- Row 1: headers (`#, Title, Location, Tags, Source, Current Calendar, → Assigned Calendar`)
- Row 2: instructions (skip)
- Rows 3+: data — sheet row = data index + 3

**Writing corrections:**
```python
# Fix specific cells in column G (Assigned Calendar)
updates = [{"range": f"G{data_idx + 3}", "values": [["Portland Events"]]} for data_idx in [142, 148]]
ws.batch_update(updates)
```

## Known Issues / Edge Cases
- Some scraper sources produce duplicate events with slightly different names
  (e.g. "The Glass Key Trio + Mike Gamble" vs "theglass key trio + mike gamble")
  — this is what Step 2 (deduplication) is designed to catch
- Vancouver, BC events sometimes appear in the scraper output — these should be skipped
  (check URL domain: `.ca` or `edmtrain.com/vancouver-bc` are BC giveaways)
- Scraper sometimes produces `"$11:30 pm"` as a cost (parse error for end time) — treat as no cost
- PDX After Dark source has no-time events — these use 2hr default from approximate timestamp in URL
- The `include` column is pre-filtered by the scraper; only `y` rows are processed

## What Claude Code Should Help With
1. Running the script and handling errors
2. Iterating on the script if the TSV format changes
3. Debugging Google Calendar API issues
4. Improving the categorization or deduplication prompts
5. Eventually: automating the Claude chat steps using the Anthropic API
   (currently done via paste-in/paste-out to save on API costs)
