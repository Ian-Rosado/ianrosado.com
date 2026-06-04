---
name: portland-events-instagram-post
description: >
  Create a Portland Events Instagram graphic — either the weekly "Events of the
  Week" (Mon–Sun) or the "Plan Your Weekend" (Fri–Sun) post. Use whenever Ian
  pastes a table of selected events (with Google Calendar event IDs) and asks for
  an Instagram post, weekend roundup, or events graphic. Looks up each event's
  details from the calendar, fills the HTML template, renders a 1080×1080 PNG,
  then iterates.
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

## The flow

**Ian curates, you build.** The flow is:
1. **Ian pastes a table of chosen events**, each with its Google Calendar **event ID**
   (he has already picked the day/night events — you are not curating).
2. **You look up each event's full details** from the calendar by ID (title, date,
   time, location, cost, description).
3. **You substitute them into the HTML template** and render the PNG.
4. **You iterate with Ian** on wording, colors, and layout until it's right.

---

## Step 1 — Look up the pasted events by ID

Ian's table has one row per chosen event with its calendar event ID (and usually
which day/slot it's for). Fetch full details from the Portland calendars by ID.

Robust approach: pull all events from the Portland calendars over the target week
into an `{id: event}` map, then look up each pasted ID (handles not knowing which
calendar each ID is on).

```python
import sys
from datetime import datetime, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
sys.stdout.reconfigure(encoding="utf-8")

# Calendar token (has calendar scope) — written by the add-to-calendar script
TOKEN = r"C:\Users\nai19\Documents\GitHub\ianrosado.com\scripts\add-to-calendar\token.json"
creds = Credentials.from_authorized_user_file(TOKEN, ["https://www.googleapis.com/auth/calendar"])
svc = build("calendar", "v3", credentials=creds)

CALENDARS = {
    "Portland Events":        "6218570f10546f6f03748bbd25adcde299bfd55ef4741d8d1520e79653d9c9f6@group.calendar.google.com",
    "Portland Live Music":    "34ae96ffcf119eb4dbf6acf86b0886273efeb8a702ed6e9267ef3d24f0e9a1f7@group.calendar.google.com",
    "Portland Comedy":        "94a06447d97328f27a5e219c8e01c42be692998a7573738132a4405a739efec4@group.calendar.google.com",
    "Portland Karaoke":       "e911229a59a93265f26cc81a1cbd2c3be4300fad84e935846ddb8fa7909f42fb@group.calendar.google.com",
    "Portland Farmers Markets":"560e859bd2c7b5dfd2262cb6f28389921434606cec955e7ec75f02df9fd2138a@group.calendar.google.com",
}

# Option A — direct get when you know the calendar:
#   ev = svc.events().get(calendarId=CAL_ID, eventId=EVENT_ID).execute()

# Option B — build an id->event map across all calendars for the week:
by_id = {}
for cal_id in CALENDARS.values():
    page = None
    while True:
        resp = svc.events().list(
            calendarId=cal_id, timeMin="2026-05-29T00:00:00-07:00",
            timeMax="2026-06-01T00:00:00-07:00", singleEvents=True,
            maxResults=250, pageToken=page,
        ).execute()
        for ev in resp.get("items", []):
            by_id[ev["id"]] = ev
        page = resp.get("nextPageToken")
        if not page:
            break

# Then for each pasted id: ev = by_id.get(event_id)
# Pull: ev["summary"], ev["start"]["dateTime"], ev.get("location"), ev.get("description")
# Cost is the first line of the description ("cost\nurl").
```

If a pasted ID isn't found, tell Ian which one so he can correct it.

---

## Step 2 — Map events to day/night slots

Ian's table indicates the day and (usually) whether each is the ☀ Day or 🌙 Night
pick. If a slot isn't specified, infer: Day = before ~4pm, Night = evening. Build
each tile's `name` and `meta` (`Venue · Time · Cost`) from the looked-up details:
- Trim long titles to ~1–2 lines
- Lead the meta with "Free" when the cost is free
- One ☀ Day + one 🌙 Night tile per day row

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
