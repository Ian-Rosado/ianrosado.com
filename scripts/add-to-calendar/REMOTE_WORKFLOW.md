# Portland Events — Remote / Non-Interactive Workflow

How to run the scrape → add-to-calendar pipeline without sitting at the home
desktop pressing Enter, and how to drive it remotely while traveling.

---

## The staged flow

The add-to-calendar script used to pause four times for Enter. It now also
supports running as **discrete, non-blocking stages**, with the Google Sheet as
the shared state between them. Each stage does one thing and exits — so the flow
can be driven by Claude in a single session, or run a stage at a time from
anywhere.

> **Always run `portland_events_add.py` from inside `scripts/add-to-calendar/`.**
> It looks for `token.json` + `credentials.json` in the *current directory*.

| Step | Command | Who | Blocks? |
|---|---|---|---|
| 1. Scrape → Inbox | `cd scripts/event-scrapers` then `python run_all.py --days 30 --push-to-sheets --clear` | Claude/you | No |
| 2. Prep tabs | `cd scripts/add-to-calendar` then `python portland_events_add.py --stage prep` | Claude/you | No |
| 3. Fill Categorize + Dedup | *(Claude fills via the sheet scripts, or you fill by hand)* | Claude | — |
| 4. Write Review tab | `python portland_events_add.py --stage review` | Claude/you | No |
| 5. Review | Open the **Review** tab in the Google Sheets app, mark Include `y`/`n`, edit any fields | **You** | — |
| 6. Commit | `python portland_events_add.py --stage commit --yes` | Claude/you | No |

`--yes` skips the final "type yes" confirmation (needed for unattended runs).
Leave it off if you want the prompt.

The old behavior is unchanged: `python portland_events_add.py --from-sheets`
(no `--stage`) still runs the original interactive flow with the four pauses,
and `--skip-to-review` still works.

### What each stage reads/writes

- **prep** — reads the Inbox, writes the **Categorize** and **Dedup** tabs
  (populated, blank decision columns), exits. Always rewrites both tabs fresh,
  so a later stage never reads stale flags.
- **review** — reads the filled **Categorize** + **Dedup** tabs, writes the
  **Review** tab (with suggested-skip rows pre-marked), exits.
- **commit** — reads the filled **Categorize** + **Dedup** + **Review** tabs and
  writes to Google Calendar (adds included events; refreshes existing events
  that have better scraped data).

The `#` column is the original Inbox row index in **all three** tabs, so the
stages line up even across separate processes.

---

## Driving it with Claude

The only step that truly needs you is **Review** (step 5), and that happens in
the Google Sheets mobile/web app — from any phone or laptop. Everything else
Claude can run as tool calls in one session:

1. You tell Claude "run the events flow."
2. Claude runs **scrape → prep**, fills **Categorize + Dedup**, runs **review**,
   and hands you the Review tab link.
3. You open the link on your phone/laptop, mark `y`/`n`, and reply "go."
4. Claude runs **commit --yes**. Done — no Enter presses.

For this to work, Claude has to be running on a machine that has the repo,
Python, the OAuth tokens, and network access. Today that's the home desktop.
The two options below are how you reach it (or replace it) while away.

---

## Option A (primary) — Remote Desktop into the home machine via Tailscale

Reuses everything that already works on the desktop; nothing to copy. This is a
Windows 11 **Pro** box, so Remote Desktop (host) is included.

**One-time setup (do this before you leave, on the home desktop):**

1. **Enable Remote Desktop:** Settings → System → Remote Desktop → toggle **On**.
   Note the PC name shown there.
2. **Keep it awake:** Settings → System → Power → set "When plugged in, PC goes
   to sleep after" to **Never** (RDP can't reach a sleeping machine). Leave the
   desktop powered on while you're gone.
3. **Install Tailscale** (https://tailscale.com) on the **desktop**, the
   **travel laptop**, and your **phone**. Sign all three into the *same*
   Tailscale account. This creates a private network so you can reach the home
   machine from anywhere **without** exposing Remote Desktop to the public
   internet (do **not** port-forward 3389 on your router — that's the unsafe way).
4. In the Tailscale admin console, note the desktop's Tailscale IP
   (`100.x.y.z`) or its MagicDNS name.

**While traveling (from the laptop):**

1. Make sure Tailscale is connected on both ends.
2. Open **Remote Desktop Connection** (`mstsc`) → enter the desktop's Tailscale
   IP / name → sign in with your Windows account.
3. You now have the desktop's full session — run Claude Code exactly as you do
   at home. The Microsoft Remote Desktop app on the phone works too, but a
   laptop is far easier for driving Claude.

**Caveats:** the desktop must stay on and online; a home internet/power outage
takes it offline. That's what Option B covers.

---

## Option B (fallback) — Self-contained travel laptop

Make the laptop able to run the whole flow on its own, with no dependence on the
home desktop being reachable.

**One-time setup (before you leave):**

1. Install **Node.js** and **Python 3.11+** on the laptop, plus Claude Code.
2. Clone the repo: `git clone https://github.com/Ian-Rosado/ianrosado.com`.
3. Install Python deps:
   ```
   pip install gspread google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client beautifulsoup4 lxml python-dateutil requests
   ```
   (plus `pip install -r scripts/event-scrapers/requirements.txt`)
4. **Copy the OAuth tokens** from the desktop to the same paths on the laptop —
   these are what let it write to your calendar and sheet without re-auth:
   - `scripts/add-to-calendar/token.json` **and** `credentials.json`
     (calendar + sheets, used by `portland_events_add.py`)
   - `scripts/event-scrapers/credentials/token.json` **and** `credentials.json`
     (used by `run_all.py` / `reauth_and_push.py` to push to the Inbox)

   Move them over a secure channel (encrypted USB, password manager, or a
   private file transfer). These tokens grant access to your Google account —
   treat them like passwords and delete the copies when the trip is over.
5. **Sanity check** while still on home network:
   `cd scripts/add-to-calendar && python portland_events_add.py --stage prep`
   — if it writes the tabs without a browser prompt, the tokens work. If you
   instead get a browser auth window, complete it once on the laptop and it'll
   save a fresh `token.json`.

**While traveling:** run Claude Code on the laptop and drive the staged flow
directly. The Review step is the same — done in the Sheets app.

> Tip: you can set both up. Use Tailscale/RDP normally, and keep the laptop as a
> ready fallback if the home machine drops offline.

---

## Auth / token notes

- Both `get_service()` (calendar) and `get_sheets_client()` (sheets) in
  `portland_events_add.py` read `token.json` + `credentials.json` from the
  **current working directory** — always `cd scripts/add-to-calendar` first.
- A single `token.json` there covers both calendar and sheets once you've run a
  `--from-sheets`/`--stage` command (broader scope). If you see a scope-mismatch
  or `invalid_grant` error, delete that `token.json` and rerun — it falls back to
  a browser auth and writes a fresh one.
- The scraper push side uses a separate token at
  `scripts/event-scrapers/credentials/token.json`; if it expires mid-run, use
  `python scripts/event-scrapers/reauth_and_push.py <output/events_*.json>` to
  re-auth and push the already-scraped file without re-scraping.
