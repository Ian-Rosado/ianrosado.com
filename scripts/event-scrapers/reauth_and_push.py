#!/usr/bin/env python3
"""Re-authenticate (browser) if needed, then push an already-scraped JSON to the
Inbox sheet — no re-scrape.

Use when `run_all.py --push-to-sheets` fails with an expired/revoked token
(`invalid_grant`). The scrape output is already on disk; this just re-auths and
appends it to the sheet.

    python reauth_and_push.py                                  # newest output/events_*.json
    python reauth_and_push.py output/events_2026-06-07.json    # a specific file
    python reauth_and_push.py --clear <file>                   # wipe sheet rows first

Run this in YOUR OWN terminal — it opens a browser for the Google consent.
"""
import sys
import json
import glob
import argparse
from pathlib import Path

from google.auth.exceptions import RefreshError

import sheets_writer
from sheets_writer import write_events_to_sheet, TOKEN_FILE, get_credentials


def newest_output():
    files = sorted(glob.glob(str(Path("output") / "events_*.json")))
    # Prefer the unsuffixed full-run files over per-calendar ones.
    full = [f for f in files if Path(f).stem.count("_") == 1]
    pick = (full or files)
    if not pick:
        sys.exit("No output/events_*.json found — run run_all.py first.")
    return pick[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file", nargs="?", help="events_*.json to push (default: newest)")
    ap.add_argument("--clear", action="store_true", help="clear existing sheet rows first")
    args = ap.parse_args()

    path = args.json_file or newest_output()
    events = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"Loaded {len(events)} events from {path}")

    # Match run_all.py's sheet ordering: source, then date, then time.
    events = sorted(events, key=lambda e: (
        e.get("source") or "",
        e.get("date") or "9999",
        e.get("time") or "99:99",
    ))

    # Force a fresh browser login if the stored refresh token is dead.
    try:
        get_credentials()
    except RefreshError:
        print("Stored token is revoked/expired — removing it and re-authenticating...")
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        get_credentials()  # no token now → triggers the browser flow

    write_events_to_sheet(events, skip_duplicates=True, clear_first=args.clear)
    print("Done.")


if __name__ == "__main__":
    main()
