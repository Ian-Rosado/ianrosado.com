---
name: portland-events-flyer-ingest
description: >
  Turn photos of event flyers into Portland Events calendar entries. Use
  whenever Ian attaches one or more photos of flyers/posters (the kind he snaps
  around town) and wants them added to the calendar, or says things like "add
  these flyers", "here are some flyers I photographed", or "run the flyer
  batch". Reads each flyer image with vision to extract
  date/time/location/cost/tags + a suggested calendar, writes them to the Inbox
  tab, and hands off to the normal add-to-calendar pipeline for the phone review
  + commit. Driven by scripts/add-to-calendar/flyer_events.py.
---

# Portland Events — Flyer Photo → Calendar Ingest

Ian photographs flyers/posters around town and attaches the photos in the chat.
You read them, extract the event details, and drop rows into the **Inbox** tab —
then the existing `portland_events_add.py` pipeline takes over, so the **phone
double-check happens in the Review tab** exactly as it always has.

Only the front-end (flyer photo → Inbox rows) is new; everything from the Inbox
onward is unchanged.

> Run the script from inside `scripts/add-to-calendar/` — it reads `token.json`
> + `credentials.json` from there, like the other pipeline scripts.

## The flow when Ian attaches flyer photos

1. **Read each flyer image (this is the vision step — you do it).**
   For every attached photo, Read the image and pull out, per event:

   | field | notes |
   |---|---|
   | `title` | the event name; keep it tight |
   | `date` | `YYYY-MM-DD`. Resolve relative dates ("this Friday", "Sat the 20th") against **today's date** — use the current/next occurrence; if the year or month/day is ambiguous, flag it rather than guessing |
   | `time` | `HH:MM` 24h start |
   | `end_time` | `HH:MM` 24h if stated (else blank) |
   | `location` | venue name (+ neighborhood if shown) |
   | `cost` | "Free", "$15", "$10-20", etc. Blank if not stated |
   | `tags` | comma-separated (genre, vibe, "21+", "all ages", "drag", "pride"…) |
   | `calendar` | your routing guess — see below |
   | `url` | an event/ticket URL if the flyer prints one (else blank) |
   | `source` | leave blank — the script defaults it to `Flyer` |

   **One flyer can list several events** (a weekly lineup, a festival schedule) —
   emit one object per event. **A flyer photo may also be blurry or crop off a
   detail** — if you can't read the date or venue with confidence, flag it to Ian
   and ask, rather than guessing.

   **Calendar routing:** follow the rules in the **portland-events-add-workflow**
   skill (Live Music / Comedy / Karaoke / Trivia-by-neighborhood / Farmers
   Markets / Sports / else Portland Events). Your guess just seeds the Inbox; the
   Categorize stage can still correct it, so when unsure use `Portland Events`
   and move on. Full name (`"Portland Comedy"`) or short code (`"comedy"`) both
   work.

   Write the results to `scripts/add-to-calendar/flyer_work/rows.json` as a JSON
   list, e.g.:
   ```json
   [
     {
       "title": "Trivia Night",
       "date": "2026-09-20", "time": "19:00",
       "location": "Great Notion NW", "cost": "Free",
       "tags": "trivia, 21+", "calendar": "Trivia Nights - NW/SW"
     }
   ]
   ```
   (`python flyer_events.py template` writes a starter file if you want one.)

2. **Show Ian the extracted table before writing.** List title / date / time /
   venue / cost / calendar for each event and let him eyeball it. This is the
   first of his two checks (the Review tab is the second). Fix anything he calls
   out in `rows.json`.

3. **Write to the Inbox**
   ```
   python flyer_events.py write flyer_work/rows.json --dry-run   # preview
   python flyer_events.py write flyer_work/rows.json             # append
   ```
   Appends to the 14-column **Inbox** tab with Source = `Flyer`. There's no link
   to fetch and nothing to mark done, so this is a single step (unlike the IG
   flow).

4. **Hand off to the normal pipeline for the phone review + commit**
   ```
   python portland_events_add.py --stage prep      # Categorize + Dedup tabs
   # (help fill Categorize/Dedup per the add-workflow skill, or let Ian)
   python portland_events_add.py --stage review     # writes the Review tab
   # → Ian opens the Review tab in the Sheets app, marks Include y/n, edits fields
   python portland_events_add.py --stage commit --yes
   ```

## Notes & failure modes

- **Don't write to the calendar from this skill.** Only the pipeline's `commit`
  stage does, after Ian's Review-tab pass — that's the guardrail.
- **Dedup is handled downstream.** Don't worry that a flyer event might already
  be on the calendar from a scraper or Instagram — the Dedup stage catches it.
  Just extract faithfully.
- **Ambiguous or unreadable flyers:** flag them and ask Ian rather than guessing
  a date/venue. A wrong date is worse than a question.
- `flyer_work/` is gitignored (the per-run rows.json is scratch).
- Shares the Inbox row shape + calendar routing with the Instagram flow via
  `inbox_common.py`; the extraction rules are the same, only the intake differs.
