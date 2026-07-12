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

Auth: shared token via scripts/google_auth.py (anchored to that file, not the
cwd). Still run this from scripts/add-to-calendar/ so ig_work/ lands here.

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
INBOX_TAB = "Inbox"        # the existing pipeline entry point (13 cols, see below)
IG_TAB = "IG Inbox"        # where phone-pasted Instagram links land

WORK_DIR = Path("ig_work")  # gitignored; holds fetched flyers + manifest.json

# IG Inbox tab columns (1-indexed):
#   A URL | B Status | C Note
# Status: blank/"pending" = to do, "done" = added, "skip" = ignored, "error".
IG_HEADERS = ["Instagram URL", "Status", "Note"]

# Inbox tab columns (must match scripts/event-scrapers/sheets_writer.py):
#   A include | B Title | C Date | D Time | E End Time | F Duration (min)
#   G Location | H Cost | I Calendar | J Tags | K Source | L URL | M Added
INBOX_HEADERS = [
    "include", "Title", "Date", "Time", "End Time", "Duration (min)",
    "Location", "Cost", "Calendar", "Tags", "Source", "URL", "Added",
]

# The Inbox "Calendar" column must hold the full calendar NAME (e.g.
# "Portland Live Music") — that's what portland_events_add.py's categorize step
# recognizes (see CALENDAR_ALIASES there). Short codes like "music"/"events" are
# NOT recognized and silently default to Portland Events, so we normalize any
# short code back to its full name before writing. The categorize stage can
# still override the guess; this is just a starting point.
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
# Inverse: short code -> full name, so a code passed in rows.json still expands.
_CODE_TO_NAME = {code: name for name, code in CALENDAR_CODES.items()}


# ── Auth (shared token — scripts/google_auth.py) ────────────────────────────

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import google_auth


def get_sheet():
    return google_auth.get_gspread_client().open_by_key(SHEET_ID)


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


def fetch_post(url, dest_dir, cookies_from_browser=None):
    """
    Best-effort fetch of a public post's first image + caption, no login.

    Returns {"url", "shortcode", "caption", "image": <path or None>, "error"}.
    Instagram 403s anonymous requests, so the reliable path is a logged-in
    fetch. Pass `cookies_from_browser` (e.g. "chrome") to have yt-dlp reuse the
    browser you're already signed into Instagram on — that gets past the wall
    without you exporting anything. Without cookies it falls back to public
    og: meta tags, which often fail; failures are reported (not raised) so the
    batch keeps going.

    Order: with cookies, try the logged-in yt-dlp fetch first (most reliable);
    without, try the anonymous og: tags first, then yt-dlp as a long shot.
    """
    code = shortcode(url) or "post"
    result = {"url": url, "shortcode": code, "caption": "", "image": None, "error": ""}

    def try_og():
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
            return bool(result["caption"] or result["image"])
        except Exception as e:  # noqa: BLE001 - report, keep going
            result["error"] = f"og-fetch: {e}"
            return False

    def try_ytdlp():
        try:
            import yt_dlp  # type: ignore
            opts = {
                "quiet": True,
                "skip_download": True,
                "outtmpl": str(dest_dir / f"{code}.%(ext)s"),
                "writethumbnail": True,
            }
            if cookies_from_browser:
                # e.g. ("chrome",) — yt-dlp reads the logged-in browser's cookies.
                opts["cookiesfrombrowser"] = (cookies_from_browser,)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            result["caption"] = (info.get("description") or result["caption"]).strip()
            for ext in ("jpg", "webp", "png"):
                cand = dest_dir / f"{code}.{ext}"
                if cand.exists():
                    result["image"] = str(cand)
                    break
            if result["caption"] or result["image"]:
                result["error"] = ""
                return True
            return False
        except ImportError:
            if not result["error"]:
                result["error"] = "login-gated (install yt-dlp, ideally with --cookies-from-browser)"
            return False
        except Exception as e:  # noqa: BLE001
            result["error"] = result["error"] or f"yt-dlp: {e}"
            return False

    attempts = [try_ytdlp, try_og] if cookies_from_browser else [try_og, try_ytdlp]
    for attempt in attempts:
        if attempt():
            return result
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
        info = fetch_post(r["url"], WORK_DIR, cookies_from_browser=args.cookies_from_browser)
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
    """Map one extracted-event dict to the 13-column Inbox row order.

    The Inbox tab's first column is the blank 'include' flag (filled during
    review), so the row must lead with an empty cell to stay aligned — see
    INBOX_HEADERS / scripts/event-scrapers/sheets_writer.py.
    """
    cal = ev.get("calendar", "")
    cal_name = _CODE_TO_NAME.get(cal, cal)  # accept a name or a code; store the name
    return [
        "",                            # include (blank; set during review)
        ev.get("title", ""),
        ev.get("date", ""),            # YYYY-MM-DD
        ev.get("time", ""),            # HH:MM 24h
        ev.get("end_time", ""),
        ev.get("duration", ""),
        ev.get("location", ""),
        ev.get("cost", ""),
        cal_name,
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
    f.add_argument("--cookies-from-browser", default="chrome",
                   help="Browser to read Instagram login cookies from (chrome/firefox/edge/safari/brave). "
                        "Pass '' to disable and fetch anonymously. Default: chrome.")
    f.set_defaults(func=cmd_fetch)

    w = sub.add_parser("write", help="Append extracted events (rows.json) to Inbox, mark links done.")
    w.add_argument("rows", help="Path to the JSON list of extracted event dicts.")
    w.add_argument("--dry-run", action="store_true", help="Show what would be written, don't write.")
    w.set_defaults(func=cmd_write)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
