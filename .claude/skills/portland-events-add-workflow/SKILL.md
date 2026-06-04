---
name: portland-events-add-workflow
description: >
  Assist with the Portland Events add-to-calendar workflow: categorizing events
  to the right Google Calendar, flagging duplicates, and resolving venue URLs.
  Use whenever asked to fill in the Categorize tab (assign calendars), the Dedup
  tab (mark duplicates), the Review step, or to add venue→URL mappings, or
  otherwise help run `scripts/add-to-calendar/portland_events_add.py`. Contains
  valid calendars, routing rules, source-mislabel caveats, a venue→trivia-neighborhood
  lookup, fuzzy duplicate-matching logic with false-positive guards, how venues.json
  resolves event URLs, and the exact method for reading/writing each tab.
---

# Portland Events — Add-to-Calendar Workflow

The script `scripts/add-to-calendar/portland_events_add.py` runs a human-in-the-loop
flow with three pauses, each backed by a tab in the Portland Events Inbox sheet:

1. **Categorize** — assign each event to the correct calendar
2. **Dedup** — flag incoming events that duplicate ones already on the calendar
3. **Review** — the user marks Include y/n and can edit any field (mostly manual)

The script writes a tab, waits while it's filled in, then reads it back. You help
with steps 1 and 2 (and can spot-check 3). See `portland-events-context` for shared IDs.

---

## Sheet access (used by every step)

**Do not use the Drive MCP** — the sheet is too large (100K+ chars). Use Python
with the event-scrapers OAuth token:

```python
import gspread, re, sys
from google.oauth2.credentials import Credentials

sys.stdout.reconfigure(encoding="utf-8")
SHEET_ID = "1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4"
TOKEN = r"C:\Users\nai19\Documents\GitHub\ianrosado.com\scripts\event-scrapers\credentials\token.json"

creds = Credentials.from_authorized_user_file(TOKEN, ["https://www.googleapis.com/auth/spreadsheets"])
sheet = gspread.authorize(creds).open_by_key(SHEET_ID)
ws = sheet.worksheet("Categorize")   # or "Dedup"
rows = ws.get_all_values()
```

Both tabs: row 1 = headers, row 2 = instructions, data starts row 3, so
**sheet row number = data index + 3**. Batch all edits into one `ws.batch_update(...)`
call to stay under the Sheets write-rate quota.

---

## Step 1 — Categorize

Fill the **"→ Assigned Calendar"** column. Only write cells that should change;
leave blank to keep the "Current Calendar" value.

### Valid calendars (exact names)

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

### Routing rules

- Concert / band / DJ as the main draw → **Portland Live Music**
- Comedy / stand-up / improv / comedy open mic / roast battle → **Portland Comedy**
- Karaoke → **Portland Karaoke**
- Trivia → the **Trivia Nights** calendar matching the venue (table below; if unknown, leave blank + flag)
- Farmers / produce / craft market → **Portland Farmers Markets**
- When in doubt → **Portland Events**
- Leave blank if "Current Calendar" is already correct.

> The script auto-detects most comedy/karaoke by title keyword before writing the
> tab, so many are already correct in "Current Calendar". Focus on the misses.

### Source-based mislabels (the #1 error source — check these every run)

The script's "Current Calendar" guess leans heavily on the **source**, and several
sources are noisy. Don't trust the bucket — scan for these patterns:

- **PDX After Dark** and **Community Playlist** tag *everything* `nightlife, music`,
  so the script dumps them into **Portland Live Music**. The Live Music bucket from
  these two is unreliable: it sweeps in venue **History & Art tours** (Crystal
  Ballroom, Mission Theater), **movie nights**, **D&D nights**, **bingo**, **drag
  brunch**, **classes/workshops**, **book trades**, and **poetry readings**. Scan
  Live Music from these sources and move the non-music ones to **Portland Events**.
- **Laughs PDX** is a comedy-only source → every event is **Portland Comedy**, but
  they often land in **Portland Events**. Re-route them all.
- **Comedians slip in by name.** Keyword matching can't catch a comedian whose show
  title has no comedy word (e.g. *Jacqueline Novak*, *Chelsea Handler* came through
  as Live Music "…Tour"). Eyeball "…Tour" events at music venues; if the headliner
  is a known comedian → **Portland Comedy**.
- **Ambiguous solo-name "tours" can be neither.** A "Tour" can be a speaker/author/
  podcast, not music or comedy (e.g. *Lue Elizondo*, *Dominick Antonelli*). Those go
  to **Portland Events**, not Live Music.
- **"Tour" is a false friend** the other way too: *History & Art Tour*, *Bloom Tour*,
  guided tours = **Portland Events**, not music.

### Market sub-classification

`Portland Farmers Markets` is for **produce/farmers markets** specifically. Arts/craft
or food-vendor markets (e.g. *Portland Saturday Market*, vegan pop-up markets, a
"Black & Indigenous Market") belong in **Portland Events**. When unsure, ask.

### Categorize tab columns (0-indexed)

| Col | Idx | Field |
|---|---|---|
| A | 0 | # (data index) |
| B | 1 | Title |
| C | 2 | Location |
| D | 3 | Tags |
| E | 4 | Source |
| F | 5 | Current Calendar |
| G | 6 | → Assigned Calendar (write here) |

```python
updates = [{"range": f"G{idx + 3}", "values": [["Portland Comedy"]]} for idx in changed]
ws.batch_update(updates)
```

### Trivia routing

**Parse the title first.** Many trivia listings (esp. PDX Pipeline / Bridgetown)
state the neighborhood right in the title — "Free Trivia **in NE Portland** w/
Bridgetown @ …", "**in SE Portland**", "**in St Johns**", "**in Troutdale**",
"**in Downtown** Portland". Map that directly (Downtown → NW/SW; anywhere outside
Portland proper like Troutdale/McMinnville → Further Out) **before** consulting the
venue table. Only fall back to the venue table when the title gives no neighborhood.
If neither resolves it, **leave blank + flag**.

### Trivia venue → neighborhood (grows over time)

**Add new venues here as you classify them** so future runs are automatic.

| Venue | Calendar |
|---|---|
| Back 2 Earth | Trivia Nights - N/NE |
| The Snug | Trivia Nights - N/NE |
| Alberta Street Pub | Trivia Nights - N/NE |
| Arbor Beer Lodge | Trivia Nights - N/NE |
| Hollywood Q | Trivia Nights - N/NE |
| Chapel Pub (McMenamins) | Trivia Nights - N/NE |
| Broadway Pub | Trivia Nights - N/NE |
| Sticky Wicket (St Johns) | Trivia Nights - N/NE |
| Waypost | Trivia Nights - N/NE |
| The Paladins League | Trivia Nights - N/NE |
| The EastBurn Public House | Trivia Nights - N/NE |
| Migration Brewing (Glisan) | Trivia Nights - N/NE |
| Covert Cafe | Trivia Nights - SE |
| No Fun Bar | Trivia Nights - SE |
| Dots Cafe | Trivia Nights - SE |
| 503 Distilling | Trivia Nights - SE |
| Space Room | Trivia Nights - SE |
| Wayfinder Bar | Trivia Nights - SE |
| Gift Bar | Trivia Nights - SE |
| BareBones | Trivia Nights - SE |
| Beer Bunker Bar (Montavilla) | Trivia Nights - SE |
| Mission Theater | Trivia Nights - NW/SW |
| Ringlers Pub (Downtown) | Trivia Nights - NW/SW |
| The Pharmacy (NW 21st) | Trivia Nights - NW/SW |
| Cascade Bar & Grill | Trivia Nights - Further Out |
| Highlands Carts (Troutdale) | Trivia Nights - Further Out |
| The Pub at Grounded Table (McMinnville) | Trivia Nights - Further Out |

---

## Step 2 — Dedup

The Dedup tab has two sections:
- **Incoming events** (top): rows 3 until a `─── EXISTING CALENDAR EVENTS ───` separator
- **Existing calendar events** (below the separator): events already on the calendars

Mark `y` in the **"→ Skip?"** column for any incoming event that duplicates an
existing one. **Be conservative** — only flag if confident it's the same event on
the same date.

### Dedup tab columns

Incoming section (0-indexed): `0 #`, `1 Title`, `2 Date`, `3 Location`, `4 Source`,
`5 Calendar`, `6 → Skip?` (write `y` here).
Existing section: `0 Calendar`, `1 Existing Title`, `2 Date`.

Sheet row for an incoming event = its `#` value + 3.

### Matching logic

Compare each incoming event against existing events **on the same date**. Flag as
duplicate if any of:
- Normalized titles are equal (lowercase, strip non-alphanumeric)
- One normalized title is a prefix of the other (≥ ~15 chars)
- Significant-word overlap ≥ 0.8 (drop stopwords: the, a, and, with, at, of, feat, vs, …)
- Same venue + same/similar time, even if titles differ across sources

```python
import re
sep = next(i for i, r in enumerate(rows) if r and "EXISTING" in str(r[0]))
incoming = [r for r in rows[2:sep] if r and r[0].isdigit()]
existing = [r for r in rows[sep+2:] if len(r) >= 3 and r[1]]

def norm(s): return re.sub(r"[^a-z0-9]", "", s.lower())
STOP = {"the","a","an","and","with","at","in","of","feat","ft","vs","by","w"}
def words(s): return {w for w in re.sub(r"[^a-z0-9 ]"," ",s.lower()).split() if w not in STOP and len(w)>2}

ex_by_date = {}
for e in existing: ex_by_date.setdefault(e[2], []).append(e[1])

dup_idx = []
for inc in incoming:
    idx, title, date = int(inc[0]), inc[1], inc[2]
    for ex_title in ex_by_date.get(date, []):
        nt, ne = norm(title), norm(ex_title)
        wt, we = words(title), words(ex_title)
        overlap = len(wt & we)/min(len(wt), len(we)) if wt and we else 0
        if nt == ne or (len(nt) >= 15 and (nt.startswith(ne[:20]) or ne.startswith(nt[:20]))) or (overlap >= 0.8 and min(len(wt),len(we)) >= 2):
            dup_idx.append(idx); break

ws.batch_update([{"range": f"G{i+3}", "values": [["y"]]} for i in dup_idx])
```

The code above is a starting point — **review its output before writing**, don't
flag blindly. The guards below caught real false positives in past runs.

### False-positive guards (be conservative — a wrong skip permanently drops a real event)

- **Trivia is venue-blind and over-flags.** Existing calendar trivia entries are
  often generic brand titles with **no venue** ("Bridgetown Trivia", "Shanrock
  Trivia"), and those brands run at *many* venues on the same night. Title+date
  alone will match a Troutdale event to a downtown one. **Only skip a trivia event
  when the venue is confirmed** — i.e. the existing title names the same venue, or
  the title is distinctively venue-specific ("…on the Heated Patio!", "Star Trek
  Trivia", "Small Batch Trivia"). Generic brand-title matches → leave for manual
  review.
- **Generic-title collisions.** Short generic titles ("Comedy Show", "Comedy Open
  Mic", bare "Karaoke") hit the ≥0.8 overlap rule against unrelated events. Don't
  skip on overlap alone when the shorter title is ≤2 generic words and the venue
  differs or is unknown. (A specific show like "Conversational Lube" matching a
  generic "Comedy Show" is a false positive.)
- **Verify, then subtract.** Compute matches, print them grouped by reason
  (exact / prefix / overlap), eyeball the overlap and low-word-count ones, then
  remove false positives from the skip set before the single `batch_update`.

### Intra-batch duplicates

The same event often arrives from **multiple sources** in one batch (e.g. a show
listed by both PDX After Dark and PDX Pipeline; "68 with Nate Bergman" appeared 5×).
Dedup matches against the *existing calendar*, not within the incoming batch, so
these survive to Step 3 — call them out there for the user to mark `n`.

---

## Step 3 — Review (mostly manual)

The user marks Include `y`/`n` and may edit Date, Time, Calendar, Title, Location,
Cost, Tags, or URL — those edits flow to the calendar write. If asked, you can
help spot remaining cross-source duplicates here (same date + similar title from
two different sources) and suggest which to mark `n`.

### Venue → URL mappings live in `venues.json` (NOT this skill)

When an event's source URL is a generic listing page, the script links to the
venue's official site instead, looked up in **`scripts/add-to-calendar/venues.json`**.
Events with no match get a red "look up venue" note. To fix those, add the venue
to `venues.json` — **do not** put URLs in this skill file; the script never reads it.

- **Format:** `"venue name": "https://…"`. The key can be any human-readable form
  of the venue name — the script normalizes both the key and the event location the
  same way before matching, so you don't have to pre-normalize.
- **`normalize_venue` already handles** (so one entry covers many source spellings):
  curly→straight apostrophes, text after the first comma, parentheticals `(NW 21st)`,
  trailing street addresses (`1800 E Burnside St.`), `on <street>` qualifiers, and a
  leading `The`. So `The Pharmacy (NW 21st), Portland, OR` and
  `The Pharmacy on NW 21st Ave, …` both resolve from a single `"The Pharmacy"` entry.
- **What it deliberately does NOT do:** expand `St.`→`Street` (would corrupt Saint
  names like *St. Johns Pub*). For abbreviation variants, add an explicit **alias**
  entry (e.g. both `"Clinton Street Theater"` and `"Clinton St Theater"` → same URL).
- After adding venues, re-run the resolver mentally or in a quick Python check to
  confirm the batch's actual location strings resolve.
