---
name: portland-events-instagram-ingest
description: >
  Turn saved Instagram event posts into Portland Events calendar entries. Use
  whenever Ian says to "run the IG batch", "process my Instagram links/saved
  posts", or pastes Instagram post links to add to the calendar. Ian collects
  links in the "IG Inbox" tab from his phone all week; this skill fetches each
  post's flyer + caption, reads them with vision to extract
  date/time/location/cost/tags + a suggested calendar, writes them to the Inbox
  tab, and hands off to the normal add-to-calendar pipeline for the phone review
  + commit. Driven by scripts/add-to-calendar/instagram_events.py.
---

# Portland Events — Instagram → Calendar Ingest

Ian saves event posts on his phone all week, then kicks this off remotely. The
front-end (Instagram → **Inbox** rows) is new; everything after the Inbox is the
existing `portland_events_add.py` pipeline, so the **phone double-check happens
in the Review tab** exactly as it always has.

> Run everything from inside `scripts/add-to-calendar/` — the script reads
> `token.json` + `credentials.json` from the current directory, like
> `portland_events_add.py`.

## How Ian feeds it (collect-then-run)

On his phone, for each good post: Instagram share sheet → **Copy link** → paste
into column A of the **IG Inbox** tab of the Portland Events Inbox sheet, one
link per row. He does this over the week; the batch runs later on demand.

The first time ever: `python instagram_events.py init` creates the IG Inbox tab.

## The flow when Ian says "run the IG batch"

1. **See what's pending**
   ```
   python instagram_events.py pending
   ```
   Lists every link in IG Inbox whose Status is blank (skips done/skip/error).

2. **Fetch flyers + captions**
   ```
   python instagram_events.py fetch          # uses ig_cookies.txt if present
   ```
   Downloads each pending post's first image + caption into `ig_work/` and
   writes `ig_work/manifest.json` — a list of
   `{ig_row, url, shortcode, caption, image, error}`.

   **Instagram 403s anonymous requests, so the fetch needs a logged-in
   session.** Cookie sources, in priority order:
   1. **`scripts/add-to-calendar/ig_cookies.txt`** (gitignored) — a
      Netscape-format cookies.txt exported from a browser signed into
      Instagram. Used automatically when present; this is the reliable path
      on Windows. One-time setup: a "Get cookies.txt LOCALLY"-style browser
      extension on instagram.com → export → save under that name. If fetches
      start 403ing again, the session expired — re-export.
   2. `--cookies-from-browser chrome` (default fallback) — yt-dlp reads the
      browser's cookie store directly. **Known to fail on Windows Chrome**
      (DPAPI decryption), which is exactly why the cookies file exists.
      Override with `firefox|edge|safari|brave`, or pass `''` for an
      anonymous og:-tag attempt (usually fails now).

   > This is why the fetch can't run from a Claude-on-the-web/cloud session:
   > those sandboxes are firewalled off from instagram.com by the environment's
   > network policy AND have no access to Ian's browser cookies. Run the fetch on
   > the desktop. The *collection* half (links in the IG Inbox tab) is what
   > happens on mobile.

   Any post that still comes back with `error` and no image/caption: open the
   link yourself or ask Ian to paste the caption; if it truly can't be read,
   leave the IG Inbox row alone (it stays pending) and tell Ian which ones need
   a hand.

3. **Extract event fields (this is the vision step — you do it)**
   Read `ig_work/manifest.json`. For each post, **Read the `image`** (the flyer
   carries the real details — date, time, venue, price) and combine it with the
   `caption` text. Pull out, per event:

   | field | notes |
   |---|---|
   | `title` | the event name; keep it tight |
   | `date` | `YYYY-MM-DD`. Resolve relative dates ("this Friday") against the post — use the post's implied year; if the month/day is ambiguous, flag it rather than guessing |
   | `time` | `HH:MM` 24h start |
   | `end_time` | `HH:MM` 24h if stated (else leave blank) |
   | `location` | venue name (+ neighborhood if shown) |
   | `cost` | "Free", "$15", "$10-20", etc. Leave blank if not stated |
   | `tags` | comma-separated (genre, vibe, "21+", "all ages", "drag", "pride"…) |
   | `calendar` | your routing guess — see below |
   | `url` | keep the original Instagram link |
   | `ig_row` | copy from the manifest so the link gets marked done |

   **One post can list several events** (e.g. a weekly lineup) — emit one object
   per event, all sharing the same `ig_row`.

   **Calendar routing:** follow the rules in the **portland-events-add-workflow**
   skill (Live Music / Comedy / Karaoke / Trivia-by-neighborhood / Farmers
   Markets / Sports / else Portland Events). Your guess here just seeds the
   Inbox; the Categorize stage can still correct it, so when unsure use
   `Portland Events` and move on. You may use either the calendar's full name
   (`"Portland Comedy"`) or its short code (`"comedy"`) — the script maps names
   to codes.

   Write the results to `ig_work/rows.json` as a JSON list, e.g.:
   ```json
   [
     {
       "title": "Goth Night: Shadowplay",
       "date": "2026-07-11", "time": "21:00",
       "location": "Lovecraft Bar", "cost": "$5",
       "tags": "goth, darkwave, 21+", "calendar": "Portland Live Music",
       "url": "https://www.instagram.com/p/ABC123/", "ig_row": 2
     }
   ]
   ```

4. **Show Ian the extracted table before writing.** List title / date / time /
   venue / cost / calendar for each event and let him eyeball it. This is the
   first of his two checks (the Review tab is the second). Fix anything he calls
   out in `rows.json`.

5. **Write to the Inbox + mark links done**
   ```
   python instagram_events.py write ig_work/rows.json          # add --dry-run first to preview
   ```
   Appends to the 12-column **Inbox** tab and sets each source link's Status to
   `done`. Re-running the batch will skip those links.

6. **Hand off to the normal pipeline for the phone review + commit**
   ```
   python portland_events_add.py --stage prep      # Categorize + Dedup tabs
   # (help fill Categorize/Dedup per the add-workflow skill, or let Ian)
   python portland_events_add.py --stage review     # writes the Review tab
   # → Ian opens the Review tab in the Sheets app, marks Include y/n, edits fields
   python portland_events_add.py --stage commit --yes
   ```

## Notes & failure modes

- **Logged-in fetch is the reliable path.** `ig_cookies.txt` (see step 2) is
  the dependable login source on Windows; `--cookies-from-browser` is the
  fallback and fails on Windows Chrome. Needs `pip install yt-dlp`. Anonymous
  fetches (no cookies) mostly 403 now. Carousels only yield the first image —
  usually the flyer, which is what we want; if details are on a later slide,
  fall back to the caption or ask Ian.
- **Dedup is handled downstream.** Don't worry about an Instagram event already
  being on the calendar from a scraper — the Dedup stage catches it. Just extract
  faithfully.
- **Don't write to the calendar from this skill.** Only the pipeline's `commit`
  stage does, after Ian's Review-tab pass — that's the guardrail.
- `ig_work/` is gitignored (fetched images + manifest + rows.json are per-run
  scratch).
