#!/usr/bin/env python3
"""
instagram_events.py
-------------------
Front-end for the add-to-calendar pipeline that turns saved Instagram event
posts into rows on the **Inbox** tab, so the existing
`portland_events_add.py` flow (prep → Categorize/Dedup → review → commit) can
take over unchanged.

The flow (collect-then-run, phone-friendly):

  1. On your phone, when you see an event worth adding, use Instagram's share
     sheet → "Copy link", then paste the link into the **IG Inbox** tab of the
     Portland Events Inbox sheet (one link per row, column A). Do this all week.
  2. Later, tell Claude "run the IG batch". Claude runs the stages below:

       python instagram_events.py init           # create the IG Inbox tab (once)
       python instagram_events.py pending         # list links still to process
       python instagram_events.py fetch           # download flyer + caption for
                                                   #   each pending link into ig_work/
       # → Claude reads each flyer image + caption (vision) and extracts
       #   date/time/location/cost/tags + a suggested calendar, writing a JSON
       #   file of Inbox-shaped rows (see --help on `write`).
       python instagram_events.py write rows.json # append to Inbox, mark links done

  3. Run the normal pipeline to review on your phone and commit:
       python portland_events_add.py --stage prep
       python portland_events_add.py --stage review
       # (review/edit in the Sheets app on your phone, mark Include y/n)
       python portland_events_add.py --stage commit --yes

This script only ever writes to the Google Sheet (Inbox + IG Inbox tabs); it
never touches the calendar directly — the existing `commit` stage does that,
which is what gives you the phone double-check before anything lands.

Auth: reads token.json + credentials.json from the CURRENT directory, exactly
like portland_events_add.py — always run it from inside scripts/add-to-calendar/.

Requirements:
    pip install gspread google-auth google-auth-oauthlib requests
    # optional but more robust for fetching: pip install yt-dlp
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ── Config ──────────────────────────────────────────────────────────────────

SHEET_ID = "1mx4U8klkuTeR1E7lmChABlShfE_kVwAFaV37gAjoId4"
INBOX_TAB = "Inbox"        # the existing pipeline entry point (12 cols, see below)
IG_TAB = "IG Inbox"        # where phone-pasted Instagram links land

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

WORK_DIR = Path("ig_work")  # gitignored; holds fetched flyers + manifest.json

# IG Inbox tab columns (1-indexed):
#   A URL | B Status | C Note
# Status: blank/"pending" = to do, "done" = added, "skip" = ignored, "error".
IG_HEADERS = ["Instagram URL", "Status", "Note"]

# Inbox tab columns (must match scripts/event-scrapers/sheets_writer.py):
#   A Title | B Date | C Time | D End Time | E Duration | F Location | G Cost
#   H Calendar | I Tags | J Source | K URL | L Added
INBOX_HEADERS = [
    "Title", "Date", "Time", "End Time", "Duration", "Location",
    "Cost", "Calendar", "Tags", "Source", "URL", "Added",
]

# Maps a human calendar name (what Claude suggests during extraction) onto the
# short "Calendar" code the Inbox/categorize step understands. The categorize
# stage can still override this; it's just a starting guess.
CALENDAR_CODES = {
    "Portland Events": "events",
    "Portland Live Music": "music",
    "Portland Comedy": "comedy",
    "Portland Karaoke": "karaoke",
    "Portland Farmers Markets": "farmers_market",
    "Portland Sports": "sports",
    "Trivia Nights - SE": "trivia_se",
    "Trivia Nights - N/NE": "trivia_nne",
    "Trivia Nights - NW/SW": "trivia_nwsw",
    "Trivia Nights - Further Out": "trivia_further",
}


# ── Auth (mirrors portland_events_add.get_sheets_client) ─────────────────────

def get_sheet():
    import gspread
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    token_path = Path("token.json")
    creds_path = Path("credentials.json")

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print("ERROR: credentials.json not found. Run from scripts/add-to-calendar/.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return gspread.authorize(creds).open_by_key(SHEET_ID)


def get_ig_tab(sheet, create=False):
    import gspread
    try:
        return sheet.worksheet(IG_TAB)
    except gspread.WorksheetNotFound:
        if not create:
            print(f"No '{IG_TAB}' tab yet. Run:  python instagram_events.py init")
            sys.exit(1)
        ws = sheet.add_worksheet(title=IG_TAB, rows=500, cols=len(IG_HEADERS))
        ws.update([IG_HEADERS], "A1")
        ws.format("A1:C1", {"textFormat": {"bold": True}})
        return ws


# ── Helpers ──────────────────────────────────────────────────────────────────

def _norm_status(v):
    return (v or "").strip().lower()


def read_ig_rows(ws):
    """Return list of dicts: {row, url, status, note} for every data row."""
    vals = ws.get_all_values()
    out = []
    for i, r in enumerate(vals[1:], start=2):  # row 1 = headers
        url = (r[0] if len(r) > 0 else "").strip()
        if not url:
            continue
        out.append({
            "row": i,
            "url": url,
            "status": _norm_status(r[1] if len(r) > 1 else ""),
            "note": (r[2] if len(r) > 2 else "").strip(),
        })
    return out


def pending_rows(ws):
    return [r for r in read_ig_rows(ws) if r["status"] in ("", "pending")]


# ── Fetching a post's flyer + caption (no login) ─────────────────────────────

def shortcode(url):
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
    return m.group(1) if m else None


def fetch_post(url, dest_dir):
    """
    Best-effort fetch of a public post's first image + caption, no login.

    Returns {"url", "shortcode", "caption", "image": <path or None>, "error"}.
    Tries the public og: meta tags first, then yt-dlp if installed. Instagram
    increasingly gates content behind login, so failures are expected and are
    reported (not raised) so the batch keeps going — Claude can still open the
    link by hand, or you can paste the caption.
    """
    code = shortcode(url) or "post"
    result = {"url": url, "shortcode": code, "caption": "", "image": None, "error": ""}

    # --- Attempt 1: public Open Graph meta tags ---
    try:
        import requests
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=20)
        html = resp.text
        og_img = re.search(r'property=["\']og:image["\']\s+content=["\']([^"\']+)', html)
        og_desc = re.search(r'property=["\']og:description["\']\s+content=["\']([^"\']+)', html)
        if og_desc:
            desc = og_desc.group(1)
            # og:description looks like: 123 likes, 4 comments - user on Date: "caption"
            m = re.search(r':\s*"(.+)"\s*$', desc, re.S)
            result["caption"] = (m.group(1) if m else desc).strip()
        if og_img:
            img_url = og_img.group(1).replace("&amp;", "&")
            img = requests.get(img_url, headers=headers, timeout=20)
            if img.ok and img.content:
                p = dest_dir / f"{code}.jpg"
                p.write_bytes(img.content)
                result["image"] = str(p)
        if result["caption"] or result["image"]:
            return result
    except Exception as e:  # noqa: BLE001 - report, keep going
        result["error"] = f"og-fetch: {e}"

    # --- Attempt 2: yt-dlp (handles more cases, optional dependency) ---
    try:
        import yt_dlp  # type: ignore
        opts = {
            "quiet": True,
            "skip_download": True,
            "outtmpl": str(dest_dir / f"{code}.%(ext)s"),
            "writethumbnail": True,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        result["caption"] = (info.get("description") or result["caption"]).strip()
        for ext in ("jpg", "webp", "png"):
            cand = dest_dir / f"{code}.{ext}"
            if cand.exists():
                result["image"] = str(cand)
                break
        result["error"] = ""
        return result
    except ImportError:
        if not result["error"]:
            result["error"] = "login-gated (install yt-dlp for a better chance)"
    except Exception as e:  # noqa: BLE001
        result["error"] = result["error"] or f"yt-dlp: {e}"

    return result


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_init(args):
    sheet = get_sheet()
    get_ig_tab(sheet, create=True)
    print(f"'{IG_TAB}' tab ready.")
    print(f"Paste Instagram post links into column A (one per row) from your phone:")
    print(f"  https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


def cmd_pending(args):
    sheet = get_sheet()
    ws = get_ig_tab(sheet)
    pend = pending_rows(ws)
    if not pend:
        print("No pending Instagram links.")
        return
    print(f"{len(pend)} pending link(s):")
    for r in pend:
        print(f"  row {r['row']}: {r['url']}")


def cmd_fetch(args):
    sheet = get_sheet()
    ws = get_ig_tab(sheet)
    pend = pending_rows(ws)
    if args.url:
        pend = [{"row": None, "url": args.url, "status": "", "note": ""}]
    if not pend:
        print("Nothing to fetch.")
        return

    WORK_DIR.mkdir(exist_ok=True)
    manifest = []
    for r in pend:
        print(f"fetching row {r['row']}: {r['url']}")
        info = fetch_post(r["url"], WORK_DIR)
        info["ig_row"] = r["row"]
        manifest.append(info)
        status = "ok" if (info["image"] or info["caption"]) else f"FAILED ({info['error']})"
        print(f"  → {status}"
              + (f"  image={info['image']}" if info["image"] else "")
              + (f"  caption={len(info['caption'])} chars" if info["caption"] else ""))

    manifest_path = WORK_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {manifest_path} ({len(manifest)} post(s)).")
    print("Next: Claude reads each image + caption, extracts event fields, and")
    print("      writes a rows.json — then:  python instagram_events.py write rows.json")


def _to_inbox_row(ev):
    """Map one extracted-event dict to the 12-column Inbox row order."""
    cal = ev.get("calendar", "")
    cal_code = CALENDAR_CODES.get(cal, cal)  # accept either a name or a code
    return [
        ev.get("title", ""),
        ev.get("date", ""),            # YYYY-MM-DD
        ev.get("time", ""),            # HH:MM 24h
        ev.get("end_time", ""),
        ev.get("duration", ""),
        ev.get("location", ""),
        ev.get("cost", ""),
        cal_code,
        ev.get("tags", ""),            # comma-separated
        ev.get("source", "Instagram"),
        ev.get("url", ""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]


def cmd_write(args):
    """
    Append extracted events to the Inbox tab and mark their source IG links done.

    rows.json is a list of event dicts. Recognized keys (all optional except
    title + date):
        title, date (YYYY-MM-DD), time (HH:MM 24h), end_time, duration,
        location, cost, calendar (name or code), tags (comma-separated),
        source, url, ig_row (the IG Inbox row this came from)
    Multiple events may share one ig_row (a post can list several events); the
    link is marked done once all of its events are written.
    """
    events = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    if not isinstance(events, list):
        print("rows.json must be a JSON list of event objects.")
        sys.exit(1)

    sheet = get_sheet()

    # Ensure Inbox tab + header exist.
    import gspread
    try:
        inbox = sheet.worksheet(INBOX_TAB)
    except gspread.WorksheetNotFound:
        inbox = sheet.add_worksheet(title=INBOX_TAB, rows=2000, cols=len(INBOX_HEADERS))
        inbox.update([INBOX_HEADERS], "A1")

    rows = [_to_inbox_row(ev) for ev in events]
    if args.dry_run:
        print(f"[dry-run] would append {len(rows)} row(s) to '{INBOX_TAB}':")
        for r in rows:
            print("  " + " | ".join(str(c) for c in r[:8]))
        return

    if rows:
        inbox.append_rows(rows, value_input_option="USER_ENTERED")
    print(f"Appended {len(rows)} event(s) to '{INBOX_TAB}'.")

    # Mark the source IG links done (and note how many events each produced).
    ig_rows = {}
    for ev in events:
        rn = ev.get("ig_row")
        if rn:
            ig_rows[rn] = ig_rows.get(rn, 0) + 1
    if ig_rows:
        ws = get_ig_tab(sheet)
        updates = []
        for rn, n in ig_rows.items():
            updates.append({"range": f"B{rn}", "values": [["done"]]})
            updates.append({"range": f"C{rn}", "values": [[f"added {n} event(s) {datetime.now():%Y-%m-%d}"]]})
        ws.batch_update(updates)
        print(f"Marked {len(ig_rows)} IG Inbox link(s) done.")
    else:
        print("(No ig_row values in rows.json — IG Inbox not updated.)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create the IG Inbox tab (run once).").set_defaults(func=cmd_init)
    sub.add_parser("pending", help="List Instagram links not yet processed.").set_defaults(func=cmd_pending)

    f = sub.add_parser("fetch", help="Download flyer + caption for pending links into ig_work/.")
    f.add_argument("--url", help="Fetch a single URL instead of the pending list.")
    f.set_defaults(func=cmd_fetch)

    w = sub.add_parser("write", help="Append extracted events (rows.json) to Inbox, mark links done.")
    w.add_argument("rows", help="Path to the JSON list of extracted event dicts.")
    w.add_argument("--dry-run", action="store_true", help="Show what would be written, don't write.")
    w.set_defaults(func=cmd_write)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
