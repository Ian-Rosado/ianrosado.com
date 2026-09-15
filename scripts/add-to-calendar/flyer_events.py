#!/usr/bin/env python3
"""
flyer_events.py
---------------
Front-end for the add-to-calendar pipeline that turns **photos of flyers** (the
ones Ian snaps around town) into rows on the **Inbox** tab, so the existing
`portland_events_add.py` flow (prep -> Categorize/Dedup -> review -> commit)
takes over unchanged — the phone double-check still happens in the Review tab.

The flow (Claude does the seeing; this script only writes the sheet):

  1. Ian attaches one or more flyer photos in the Claude chat.
  2. Claude reads each image (vision), extracts the event fields — date, time,
     venue, cost, tags + a suggested calendar — and writes a rows.json:

       [
         {"title": "Trivia Night", "date": "2026-09-20", "time": "19:00",
          "location": "Great Notion NW", "cost": "Free",
          "tags": "trivia, 21+", "calendar": "Trivia Nights - NW/SW"}
       ]

  3. Claude shows Ian the extracted table, then writes it:

       python flyer_events.py write rows.json          # add --dry-run to preview

  4. Normal pipeline for the phone review + commit:
       python portland_events_add.py --stage prep
       python portland_events_add.py --stage review
       python portland_events_add.py --stage commit --yes

This script only writes to the Inbox tab; it never touches the calendar — the
`commit` stage does that after Ian's Review-tab pass, which is the guardrail.

The Source column defaults to "Flyer" (override per-row with a "source" key).
There is no Instagram link to fetch and no IG Inbox row to mark, so unlike
instagram_events.py this is a single `write` step.

Auth: shared token via scripts/google_auth.py.

Requirements:
    pip install gspread google-auth google-auth-oauthlib
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import inbox_common

DEFAULT_SOURCE = "Flyer"

# A gitignored scratch dir for the per-run rows.json Claude writes (parallels
# ig_work/). Not required — `write` takes any path — but keeps runs tidy.
WORK_DIR = Path("flyer_work")

TEMPLATE = [
    {
        "title": "",
        "date": "YYYY-MM-DD",
        "time": "HH:MM",
        "end_time": "",
        "location": "",
        "cost": "",
        "tags": "",
        "calendar": "Portland Events",
        "source": DEFAULT_SOURCE,
        "url": "",
    }
]


def cmd_template(args):
    WORK_DIR.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else WORK_DIR / "rows.json"
    out.write_text(json.dumps(TEMPLATE, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote a rows.json template to {out}")
    print("Fill one object per event (title + date required), then:")
    print(f"  python flyer_events.py write {out}")


def cmd_write(args):
    events = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    if not isinstance(events, list):
        print("rows.json must be a JSON list of event objects.")
        sys.exit(1)
    inbox_common.append_events(events, default_source=DEFAULT_SOURCE, dry_run=args.dry_run)


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("template", help="Write a starter rows.json to fill in.")
    t.add_argument("--out", help="Where to write the template (default flyer_work/rows.json).")
    t.set_defaults(func=cmd_template)

    w = sub.add_parser("write", help="Append extracted flyer events (rows.json) to the Inbox tab.")
    w.add_argument("rows", help="Path to the JSON list of extracted event dicts.")
    w.add_argument("--dry-run", action="store_true", help="Show what would be written, don't write.")
    w.set_defaults(func=cmd_write)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
