---
name: portland-events-instagram-post
description: >
  Create a Portland Events Instagram graphic — either the weekly "Events of the
  Week" (Mon–Sun) or the "Plan Your Weekend" (Fri–Sun) post. Use whenever asked
  to make an Instagram post, weekend roundup, or events graphic. Walks through
  pulling events from the sheet/calendar, curating day + night picks, filling the
  HTML template, and rendering it to a 1080×1080 PNG.
---

# Portland Events — Instagram Post

Two post types share one HTML template:

| Post | Days | Title | Rows |
|---|---|---|---|
| Events of the Week | Mon–Sun | "Events of the **Week**" | 7 |
| Plan Your Weekend | Fri–Sun | "Plan Your **Weekend**" | 3 |

Template + examples live in `instagram/`. The canonical template to copy is
**`instagram/portland_events_week_may25_31.html`**. See `portland-events-context`
for voice/hashtag guidance and account details.

---

## Step 1 — Pull the events

Pull candidate events for the target dates from the **Inbox** sheet (richest data:
title, date, time, location, cost, tags, calendar). Filter to the date range and
`include == y`.

```python
import gspread, sys
from google.oauth2.credentials import Credentials
sys.stdout.reconfigure(encoding="utf-8")

SHEET_ID = "1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4"
TOKEN = r"C:\Users\nai19\Documents\GitHub\ianrosado.com\scripts\event-scrapers\credentials\token.json"
creds = Credentials.from_authorized_user_file(TOKEN, ["https://www.googleapis.com/auth/spreadsheets"])
ws = gspread.authorize(creds).open_by_key(SHEET_ID).worksheet("Inbox")
rows = [r for r in ws.get_all_records(default_blank="")
        if r.get("include","").lower() == "y"
        and "2026-05-29" <= str(r.get("Date","")) <= "2026-05-31"]  # <-- target range
for r in rows:
    print(r["Date"], r.get("Time",""), "|", r["Title"], "|", r.get("Location",""), "|", r.get("Cost",""), "|", r.get("Calendar",""))
```

(If the Inbox has been cleared since the events were added, read the calendars
instead via the Google Calendar API for the same date range.)

---

## Step 2 — Curate: one Day + one Night pick per day

For each day pick **two** events: a **☀ Day** (morning/afternoon) and a
**🌙 Night** (evening). Aim for:
- **Variety** across days — mix music, comedy, markets, festivals, food, free stuff
- **Free or notable** events favored (lead with "Free" in meta when applicable)
- Day = roughly before ~4pm; Night = evening
- Short, punchy names (trim long titles); keep meta to `Venue · Time · Cost`

Confirm the picks with the user before rendering if there's any ambiguity.

---

## Step 3 — Fill the HTML template

Copy `instagram/portland_events_week_may25_31.html` to a new file
(`instagram/plan_your_weekend_<dates>.html` or `portland_events_week_<dates>.html`)
and edit:

**Header**
```html
<div class="week-label">This week in Portland · May 29–31</div>   <!-- or "This weekend in Portland · …" -->
<div class="title">Plan Your <span>Weekend</span></div>            <!-- or "Events of the <span>Week</span>" -->
```

**Rows** — one `.row` per day. Each row = a `.day` badge + two `.tile`s
(Day then Night):
```html
<div class="row">
  <div class="day"><span class="day-name">Fri</span><span class="day-num">29</span></div>
  <div class="tile amber">
    <div class="tile-type">☀ Day</div>
    <div class="tile-name">Event Name</div>
    <div class="tile-meta">Venue · Time · Cost</div>
  </div>
  <div class="tile pink">
    <div class="tile-type">🌙 Night</div>
    <div class="tile-name">Event Name</div>
    <div class="tile-meta">Venue · Time · Cost</div>
  </div>
</div>
```

**Tile colors** — rotate for visual variety; don't repeat the same color adjacently:
`green`, `teal`, `blue`, `amber`, `coral`, `purple`, `pink`.

**Footer** — leave as-is (portland-events.com, @portland_events_calendar, hashtags).

Notes:
- The `.grid` uses flexbox with `flex: 1` rows, so it auto-fits whether there are
  3 rows (weekend) or 7 (week) — no height math needed.
- Keep `tile-name` to ~1–2 lines; very long names overflow.

---

## Step 4 — Render to a 1080×1080 PNG

Use Playwright (already installed for the scrapers) to screenshot the `.post` div:

```python
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

HTML = Path(r"C:\Users\nai19\Documents\GitHub\ianrosado.com\instagram\plan_your_weekend_may29_31.html")
OUT  = HTML.with_suffix(".png")

async def render():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 1080, "height": 1080}, device_scale_factor=2)
        await pg.goto(HTML.as_uri())
        await pg.wait_for_timeout(800)          # let web fonts load
        el = await pg.query_selector(".post")
        await el.screenshot(path=str(OUT))
        await b.close()

asyncio.run(render())
print("wrote", OUT)
```

`device_scale_factor=2` yields a crisp 2160×2160 (Instagram downscales nicely);
use `1` for an exact 1080×1080. Open the PNG to eyeball it before posting.

---

## Step 5 — Caption

Write a short caption in the account voice (see `portland-events-context` for tone
and hashtag sets). Lead with the weekend/week, 1–2 lines of flavor, then hashtags
like `#PDXEvents #Portland #FreePDX`. The graphic already carries the details, so
the caption stays brief.

---

## Output files

- HTML:  `instagram/plan_your_weekend_<dates>.html` / `portland_events_week_<dates>.html`
- PNG:   same name, `.png`

Keep both — the HTML is the editable source if the user wants tweaks.
