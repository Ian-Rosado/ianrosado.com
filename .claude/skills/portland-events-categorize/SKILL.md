---
name: portland-events-categorize
description: >
  Categorize Portland events into the correct Google Calendar during the
  add-to-calendar workflow. Use whenever asked to fill in the "Assigned
  Calendar" column of the Categorize tab in the Portland Events Inbox sheet,
  or to categorize/route a batch of scraped events to calendars. Contains the
  valid calendars, routing rules, a venue→trivia-neighborhood lookup, and the
  exact method for reading and writing the Categorize tab.
---

# Portland Events — Categorization

Fill in the **"→ Assigned Calendar"** column of the **Categorize** tab so each
event lands on the right Google Calendar. The add-to-calendar script
(`scripts/add-to-calendar/portland_events_add.py`) writes the Categorize tab,
waits while you fill it in, then reads it back.

See also the `portland-events-context` skill for shared IDs and project background.

---

## Valid calendars (use these exact names)

| Calendar | What goes here |
|---|---|
| `Portland Events` | General: festivals, classes, outdoor, arts, film, food, non-farmer markets |
| `Portland Live Music` | Concerts, shows, DJ sets — live music as the main draw |
| `Portland Comedy` | Stand-up, improv, comedy showcases, comedy open mics, roast battles |
| `Portland Karaoke` | Karaoke nights |
| `Portland Farmers Markets` | Farmers markets, produce/craft markets |
| `Trivia Nights - SE` | Trivia in SE Portland |
| `Trivia Nights - N/NE` | Trivia in N or NE Portland |
| `Trivia Nights - NW/SW` | Trivia in NW or SW Portland |
| `Trivia Nights - Further Out` | Trivia outside Portland proper |

## Routing rules

- Concert / band / DJ as the main draw → **Portland Live Music**
- Comedy / stand-up / improv / comedy open mic / roast battle → **Portland Comedy**
- Karaoke → **Portland Karaoke**
- Trivia → the **Trivia Nights** calendar matching the venue's neighborhood
  (see venue table below; if unknown, leave blank and flag it)
- Farmers / produce / craft market → **Portland Farmers Markets**
- When in doubt → **Portland Events**
- **Leave the cell blank** if "Current Calendar" is already correct — the script keeps it.

> The script auto-detects most comedy/karaoke by title keyword before writing the
> tab, so many will already be correct in "Current Calendar". Focus on the misses.

---

## Trivia venue → neighborhood (grows over time)

When you classify a trivia event, match the venue here. **Add new venues to this
table** as you learn them so future runs are automatic.

| Venue | Calendar |
|---|---|
| Back 2 Earth | Trivia Nights - N/NE |
| The Snug | Trivia Nights - N/NE |
| Alberta Street Pub | Trivia Nights - N/NE |
| Covert Cafe | Trivia Nights - SE |
| No Fun Bar | Trivia Nights - SE |
| Mission Theater | Trivia Nights - NW/SW |
| Cascade Bar & Grill | Trivia Nights - Further Out |

If a trivia venue isn't listed and you can't determine its neighborhood, leave the
cell blank rather than guessing.

---

## How to read & write the Categorize tab

**Do not use the Drive MCP** — the sheet is too large (100K+ chars). Use Python
with the event-scrapers OAuth token.

```python
import gspread, re, sys
from google.oauth2.credentials import Credentials
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SHEET_ID = "1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4"
TOKEN = r"C:\Users\nai19\Documents\GitHub\ianrosado.com\scripts\event-scrapers\credentials\token.json"

creds = Credentials.from_authorized_user_file(TOKEN, ["https://www.googleapis.com/auth/spreadsheets"])
ws = gspread.authorize(creds).open_by_key(SHEET_ID).worksheet("Categorize")
rows = ws.get_all_values()
```

**Categorize tab column layout** (0-indexed):

| Col | Index | Field |
|---|---|---|
| A | 0 | # (data index) |
| B | 1 | Title |
| C | 2 | Location |
| D | 3 | Tags |
| E | 4 | Source |
| F | 5 | Current Calendar |
| G | 6 | → Assigned Calendar (write here) |

- Row 1 = headers, Row 2 = instructions, data starts row 3.
- **Sheet row number = data index + 3.**

**Writing assignments** (only write cells you're changing):

```python
updates = [{"range": f"G{idx + 3}", "values": [["Portland Comedy"]]} for idx in changed_indices]
ws.batch_update(updates)
```

Batch all edits into one `batch_update` call to avoid the Sheets write-rate quota.

---

## Workflow

1. Read the Categorize tab.
2. For each data row, decide the calendar using the rules + venue table.
3. Only write cells that differ from "Current Calendar" (leave the rest blank).
4. Batch-write with `ws.batch_update(...)`.
5. Tell the user how many you changed and flag any trivia venues you couldn't place.
6. The user returns to the terminal and presses Enter to continue the script.
