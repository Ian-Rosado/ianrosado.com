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

Two post types, each with its own reusable template in `instagram/templates/`:

| Post | Days | Title | Layout | Template to copy |
|---|---|---|---|---|
| Events of the Week | Mon–Sun | "Events of the **Week**" | "Day"/"Night" as column headers; 7 rows of day badge + a Day tile + a Night tile (each tile = name + meta, 30px title) | `instagram/templates/events_of_the_week.template.html` |
| Plan Your Weekend | Fri–Sun | "Plan Your **Weekend**" | one row per event, sorted by start time; full-width tile with big title left + details right | `instagram/templates/plan_your_weekend.template.html` |

**Always start from the matching `*.template.html`** — never from a previous dated
post. The templates ship in the green theme with placeholder content and `<<THEME>>`
markers; copy one to `instagram/<post>_<dates>.html` and fill it in. Earlier dated
files in `instagram/` are finished examples for reference only. If you improve the
layout while building a post, fold the change back into the template so it persists.
See `portland-events-context` for voice/hashtag guidance and account details.

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

**Parsing the ID out of an event-edit URL.** Ian usually pastes the Google Calendar
**edit URL** (easier for him to grab) rather than the bare ID, e.g.:
`https://calendar.google.com/calendar/u/0/r/eventedit/<BLOB>`. The `<BLOB>` after
`/eventedit/` is URL-safe base64 that decodes to `"<eventId> <calendarId>"` (space-
separated). Take the **first token as the event ID** and **ignore the decoded
calendar ID** — it's truncated (ends `@g`, not `@group.calendar.google.com`), so
look the ID up against the known `CALENDARS` instead (Option B below handles this).
Remember to pad the base64 before decoding.

```python
import base64
def event_id_from_url(url_or_blob):
    blob = url_or_blob.rsplit("/eventedit/", 1)[-1].strip()
    blob += "=" * (-len(blob) % 4)                       # restore base64 padding
    return base64.urlsafe_b64decode(blob).decode("utf-8", "replace").split(" ")[0]
# Recurring instances decode to e.g. "abc123_20260605T030000Z" — use the whole token as-is.
```

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

## Step 2 — Arrange the events

Build each tile's `name` and `meta` from the looked-up details. General rules:
- Keep titles short so they stay big — shorten wording rather than letting it wrap
  (e.g. "Oregon Ren Faire" not "Oregon Renaissance Faire"). The weekend tile
  ellipsizes a too-long title.
- Lead the meta with "Free" when the cost is free.
- Use a short category label in `tile-type` (e.g. `🎭 Theater`, `🌮 Food`).

**Events of the Week:** one row per day (Mon–Sun). Ian's table says the day and
usually whether each is the ☀ Day or 🌙 Night pick; if not, infer Day = before ~4pm,
Night = evening. One ☀ Day + one 🌙 Night tile per row.

**Plan Your Weekend:** one row per event, **sorted by start date/time**. Each row's
`tile-type` is the category (not Day/Night). Single-day events use a `Day Num`
badge; multi-day / all-weekend events use the text-only `.day.span` badge
(e.g. "Sat & Sun", "All Week").

---

## Step 3 — Fill the HTML template

Copy the matching template (see the table at the top) to a dated file:
- Weekend → `instagram/templates/plan_your_weekend.template.html` →
  `instagram/plan_your_weekend_<dates>.html`
- Week → `instagram/templates/events_of_the_week.template.html` →
  `instagram/portland_events_week_<dates>.html`

Then edit:

**Header** — set the `.week-label` date range; leave the title wording as the
template ships it.

**Rows** — each template has placeholder `.row` blocks with inline comments. Fill
them in:

*Events of the Week* — "☀ Day"/"🌙 Night" are stated once in the `.col-head` row at
the top; each `.row` is a `.day` badge + a Day tile + a Night tile (tile = name + meta):
```html
<div class="tile amber">
  <div class="tile-name">Event Name</div>
  <div class="tile-meta">Venue · Time · Cost</div>
</div>
```

*Plan Your Weekend* — one `.row` per event; tile splits into a big title (left) and
right-aligned details. Use a `<br>` in the meta to stack venue over time/cost:
```html
<div class="tile amber">
  <div class="tile-main">
    <div class="tile-type">🎭 Theater</div>
    <div class="tile-name">Event Name</div>
  </div>
  <div class="tile-meta">Venue<br>Time · Cost</div>
</div>
```
Multi-day events use the text-only badge: `<div class="day span"><span class="day-name">Sat<br>&amp; Sun</span></div>`.

**Tile colors** — rotate the per-tile classes for visual variety; don't repeat the
same color adjacently: `green`, `teal`, `blue`, `amber`, `coral`, `purple`, `pink`.
(These tile classes stay the same regardless of the background theme below — but
avoid the tile color that matches the current canvas theme, e.g. skip `coral` tiles
on the Maroon theme, so they don't blend in.)

**Footer** — leave as-is (pdx-events.com, @portland_events_calendar, hashtags).

### Background theme — rotate it each post

Every post uses a different dark **canvas background + matching accent color** so
consecutive posts look distinct. The template ships with the green theme; swap in
the next theme in the rotation (don't reuse the previous week's). Change these CSS
values in the copied file:

- `.post { background: <bg> }`
- `.week-label { color: <accent> }`
- `.title span { color: <accent> }`
- `.footer-cta strong { color: <accent> }`
- `.divider { background: linear-gradient(90deg, <grad>, transparent) }`

| Theme | `<bg>` | `<accent>` | `<grad>` (divider) | Used by |
|---|---|---|---|---|
| Green  | `#0d2b1a` | `#5cdc80` | `#5cdc80, #3ecfb0, #5ca8ff` | may25–31 (week) |
| Navy   | `#0a1a3a` | `#5ca8ff` | `#5ca8ff, #3ecfb0, #b39dff` | jun1–7 (week) |
| Plum   | `#1a0e2e` | `#f07ad8` | `#f07ad8, #b39dff, #f0a500` | may29–31 (weekend) |
| Maroon | `#2a0e14` | `#ff7a5c` | `#ff7a5c, #f0a500, #f07ad8` | jun4–7 (weekend) |
| Teal   | `#062a2a` | `#3ecfb0` | `#3ecfb0, #5cdc80, #5ca8ff` | jun8–14 (week) |

The accent also lightly tints `.week-label`, the title highlight word, the divider,
and the footer CTA — keep all of those on the same accent so the post reads as one
color story. Tile background colors are unchanged; they sit on top of any canvas.

Pick the theme that hasn't been used recently (check the most recent files in
`instagram/`), or whichever Ian requests.

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
