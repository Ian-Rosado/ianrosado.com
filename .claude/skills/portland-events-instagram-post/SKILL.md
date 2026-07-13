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

## Step 1 — Look up the pasted events (one command)

Ian's table has one row per chosen event, usually as a Google Calendar **edit
URL** (`…/r/eventedit/<BLOB>`), sometimes a bare event ID. Fetch everything in
ONE batch call — do not write per-event lookup code:

```
cd scripts/add-to-calendar
python get_events.py <url-or-id> <url-or-id> ...
# or, for a long list:  python get_events.py --file picks.txt
```

The script accepts any mix of edit URLs / eventedit blobs / bare IDs (bare IDs
are searched across every configured calendar, including trivia and
Pedalpalooza), and prints a JSON list in input order with exactly the fields a
post needs: `title, date, end_date, time, end_time, all_day, location, cost,
url, calendar`. It also:
- decodes/reconstructs the truncated calendar ID from eventedit blobs itself
- flags copy/paste slips — a second input resolving to the same event gets
  `"error": "DUPLICATE of input: …"`. Ask Ian for the intended event instead
  of rendering the duplicate.
- exits 2 with a list of not-found inputs — tell Ian which ones to re-paste.

Use the JSON as-is for Step 2; there is nothing else to look up.

---

## Step 2 — Arrange the events

Build each tile's `name` and `meta` from the looked-up details. General rules:
- Keep titles short so they stay big — shorten wording rather than letting it wrap
  (e.g. "Oregon Ren Faire" not "Oregon Renaissance Faire"). The weekend tile
  ellipsizes a too-long title.
- Lead the meta with "Free" when the cost is free.
- Use a short category label in `tile-type` (e.g. `🎭 Theater`, `🌮 Food`). Stick to
  **single-codepoint emoji** — the headless renderer drops ZWJ sequences (e.g. use
  `🌈` for Pride, not `🏳️‍🌈`, which renders as a blank/plain flag).

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

### Background theme — advance one step along the color wheel each post

Each post uses a different dark **canvas background + matching accent color**. The
themes are ordered **around the color wheel** so that posting them in sequence makes
the Instagram profile's 3-column grid read as a smooth **gradient** as you scroll.
Change these CSS values in the copied file:

- `.post { background: <bg> }`
- `.week-label { color: <accent> }`
- `.title span { color: <accent> }`
- `.footer-cta strong { color: <accent> }`
- `.divider { background: linear-gradient(90deg, <grad>, transparent) }`

**Selection rule:** find the most recent post's theme (check the newest file in
`instagram/`), then use the **next theme down this table** (wrapping Lime → Green).
This advances one hue step per post so the grid gradients. Do NOT pick "least
recently used" — that breaks the gradient. The cycle repeats colors over time; that
is expected (a gradient loops). The `<grad>` divider for each theme previews the
next two accents in the cycle, reinforcing the flow.

**Serpentine for vertical continuity:** Instagram lays posts out 3-per-row,
left→right. To make the gradient flow smoothly *down* the grid (not just across),
post the hues in a **boustrophedon/snake order — reverse every other run of three**:
posts 1-2-3 left→right, then 6-5-4, then 7-8-9, then 12-11-10 … So after finishing a
row going up the wheel, the next three step *back down* it. That lines up the row
turns (the gradient meets itself at alternating left/right edges) instead of jumping
a column. Practically: count how many posts since the last "row start"; if you're in
an even row of three, walk the table upward instead of downward.

| # | Theme | `<bg>` | `<accent>` | `<grad>` (divider) | Used by |
|---|---|---|---|---|---|
| 1 | Green   | `#0d2b1a` | `#5cdc80` | `#5cdc80, #3ecfb0, #5ca8ff` | may25–31 (week) |
| 2 | Teal    | `#062a2a` | `#3ecfb0` | `#3ecfb0, #5ca8ff, #8a9bff` | jun8–14 (week) |
| 3 | Blue    | `#0a1f3a` | `#5ca8ff` | `#5ca8ff, #8a9bff, #b39dff` | jun12–14 (weekend) |
| 4 | Indigo  | `#15163a` | `#8a9bff` | `#8a9bff, #b39dff, #f07ad8` | — |
| 5 | Purple  | `#1c0e30` | `#b39dff` | `#b39dff, #f07ad8, #ff7a5c` | — |
| 6 | Magenta | `#2a0e28` | `#f07ad8` | `#f07ad8, #ff7a5c, #f0a500` | (≈ old Plum) may29–31 (weekend) |
| 7 | Coral   | `#2e1310` | `#ff7a5c` | `#ff7a5c, #f0a500, #c4dd5e` | (≈ old Maroon) jun4–7 (weekend) |
| 8 | Amber   | `#2a1c06` | `#f0a500` | `#f0a500, #c4dd5e, #5cdc80` | — |
| 9 | Lime    | `#20260a` | `#c4dd5e` | `#c4dd5e, #5cdc80, #3ecfb0` | — |

(The earlier Navy `#0a1a3a`/`#5ca8ff` and Plum `#1a0e2e`/`#f07ad8` posts map onto
Blue and Magenta respectively — close enough; the wheel is the source of truth now.)

The accent also lightly tints `.week-label`, the title highlight word, the divider,
and the footer CTA — keep all of those on the same accent so the post reads as one
color story. Tile background colors are unchanged; they sit on top of any canvas —
but still skip the tile class matching the current canvas (e.g. no `blue` tiles on
the Blue theme) so it doesn't blend in.

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
