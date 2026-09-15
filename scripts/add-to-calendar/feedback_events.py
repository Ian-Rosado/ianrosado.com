#!/usr/bin/env python3
"""
feedback_events.py
------------------
Front-end for the add-to-calendar pipeline that turns **public feedback-form
submissions** into rows on the **Inbox** tab, so the existing
`portland_events_add.py` flow (prep -> Categorize/Dedup -> review -> commit)
takes over unchanged — the phone double-check still happens in the Review tab.

The form is a Google Form whose responses land in a Google Sheet. Submissions
are mostly free text ("tell us about the event"), so — exactly like the flyer
and Instagram flows — Claude reads each submission and extracts the event
fields; this script only moves rows between sheets.

Two ways to feed it:

  A. Automated (this script reads the responses sheet):
       python feedback_events.py init            # create the Feedback Log tab (once)
       python feedback_events.py pending          # list unprocessed submissions
       python feedback_events.py fetch            # dump pending submissions ->
                                                  #   feedback_work/manifest.json
       # -> Claude reads the manifest, extracts event fields, writes rows.json
       python feedback_events.py write rows.json  # append to Inbox, log responses done

  B. Paste (no automated read): Ian pastes a submission into the chat, Claude
     extracts it into a rows.json (no resp_key), and runs the same
     `write rows.json`. Nothing gets logged because there's no response row —
     that's fine.

Then the normal pipeline for the phone review + commit:
     python portland_events_add.py --stage prep
     python portland_events_add.py --stage review
     python portland_events_add.py --stage commit --yes

Processed submissions are tracked in a **Feedback Log** tab inside the main
Portland Events Inbox sheet (keyed by the response Timestamp), NOT by writing
into the Form's own responses sheet — that keeps the form's columns untouched
and the bookkeeping in the one sheet used everywhere else.

This script never touches the calendar; the `commit` stage does, after Ian's
Review-tab pass. That's the guardrail.

Auth: shared token via scripts/google_auth.py.

Requirements:
    pip install gspread google-auth google-auth-oauthlib
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import inbox_common

# ── Config: the Google Form's responses sheet ───────────────────────────────
# Fill FEEDBACK_SHEET_ID with the key from the responses-sheet URL:
#   https://docs.google.com/spreadsheets/d/<THIS PART>/edit
# (or pass --sheet-id on the command line). FEEDBACK_TAB is the worksheet the
# Form writes to — Google's default name is "Form Responses 1".
FEEDBACK_SHEET_ID = ""            # <-- set me once (or use --sheet-id)
FEEDBACK_TAB = "Form Responses 1"  # <-- confirm/override with --tab

DEFAULT_SOURCE = "Feedback form"

# Bookkeeping tab (lives in the MAIN Portland Events Inbox sheet).
LOG_TAB = "Feedback Log"
LOG_HEADERS = ["Response Timestamp", "Submitter", "Status", "Added", "Logged", "Note"]

WORK_DIR = Path("feedback_work")  # gitignored per-run scratch (manifest + rows.json)


# ── Sheet access ─────────────────────────────────────────────────────────────

def _client():
    return inbox_common.google_auth.get_gspread_client()


def get_responses_ws(client, sheet_id, tab):
    if not sheet_id:
        print("ERROR: no feedback responses sheet configured.\n"
              "  Set FEEDBACK_SHEET_ID at the top of feedback_events.py to the key in\n"
              "  the responses-sheet URL, or pass --sheet-id <key>.")
        sys.exit(1)
    import gspread
    ss = client.open_by_key(sheet_id)
    try:
        return ss.worksheet(tab)
    except gspread.WorksheetNotFound:
        titles = [w.title for w in ss.worksheets()]
        print(f"ERROR: no '{tab}' tab in that sheet. Tabs present: {titles}\n"
              "  Pass the right one with --tab \"<name>\".")
        sys.exit(1)


def get_log_ws(client, create=False):
    """The Feedback Log tab in the main Inbox sheet."""
    import gspread
    main = client.open_by_key(inbox_common.SHEET_ID)
    try:
        return main.worksheet(LOG_TAB)
    except gspread.WorksheetNotFound:
        if not create:
            print(f"No '{LOG_TAB}' tab yet. Run:  python feedback_events.py init")
            sys.exit(1)
        ws = main.add_worksheet(title=LOG_TAB, rows=1000, cols=len(LOG_HEADERS))
        ws.update([LOG_HEADERS], "A1")
        ws.format(f"A1:{chr(64+len(LOG_HEADERS))}1", {"textFormat": {"bold": True}})
        return ws


def logged_keys(log_ws):
    """Set of Response Timestamp strings already logged (col A, minus header)."""
    return {(r[0] or "").strip() for r in log_ws.get_all_values()[1:] if r and (r[0] or "").strip()}


# ── Reading the responses sheet ──────────────────────────────────────────────

def _col_index(headers, *names):
    low = [h.strip().lower() for h in headers]
    for n in names:
        if n.lower() in low:
            return low.index(n.lower())
    return None


def read_submissions(resp_ws):
    """Return a list of submission dicts, newest sheet-order preserved.

    Each: {row, key (timestamp), submitter, fields {header: value}, text}.
    `text` concatenates every non-empty answer as "Question: answer" lines so
    the extraction step works no matter how the form's questions are worded.
    """
    vals = resp_ws.get_all_values()
    if not vals:
        return []
    headers = vals[0]
    ts_i = _col_index(headers, "Timestamp") or 0
    email_i = _col_index(headers, "Email Address", "Email")
    out = []
    for i, r in enumerate(vals[1:], start=2):  # row 1 = headers
        if not any((c or "").strip() for c in r):
            continue
        key = (r[ts_i] if len(r) > ts_i else "").strip()
        submitter = (r[email_i].strip() if email_i is not None and len(r) > email_i else "")
        fields, lines = {}, []
        for j, h in enumerate(headers):
            val = (r[j] if len(r) > j else "").strip()
            if not val or j in (ts_i,):
                continue
            fields[h] = val
            lines.append(f"{h}: {val}")
        out.append({
            "row": i,
            "key": key or f"row{i}",   # fall back to row id if a form has no Timestamp
            "submitter": submitter,
            "fields": fields,
            "text": "\n".join(lines),
        })
    return out


def pending_submissions(client, sheet_id, tab):
    resp_ws = get_responses_ws(client, sheet_id, tab)
    subs = read_submissions(resp_ws)
    done = logged_keys(get_log_ws(client))
    return [s for s in subs if s["key"] not in done]


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_init(args):
    client = _client()
    get_log_ws(client, create=True)
    print(f"'{LOG_TAB}' tab ready in the main Inbox sheet.")
    if not (args.sheet_id or FEEDBACK_SHEET_ID):
        print("\nNext: point the script at your form's responses sheet — set")
        print("FEEDBACK_SHEET_ID at the top of feedback_events.py (or pass --sheet-id),")
        print("then:  python feedback_events.py pending")


def cmd_pending(args):
    client = _client()
    pend = pending_submissions(client, args.sheet_id or FEEDBACK_SHEET_ID, args.tab or FEEDBACK_TAB)
    if not pend:
        print("No unprocessed feedback submissions.")
        return
    print(f"{len(pend)} unprocessed submission(s):")
    for s in pend:
        snippet = s["text"].replace("\n", " | ")
        print(f"  row {s['row']} [{s['key']}] {snippet[:100]}")


def cmd_fetch(args):
    client = _client()
    pend = pending_submissions(client, args.sheet_id or FEEDBACK_SHEET_ID, args.tab or FEEDBACK_TAB)
    if not pend:
        print("Nothing to fetch — no unprocessed submissions.")
        return
    WORK_DIR.mkdir(exist_ok=True)
    manifest_path = WORK_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(pend, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {manifest_path} ({len(pend)} submission(s)).")
    print("Next: Claude reads each submission's text, extracts event fields, and")
    print("      writes a rows.json (carry each event's resp_key = the submission's")
    print("      'key'), then:  python feedback_events.py write rows.json")


def cmd_write(args):
    events = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    if not isinstance(events, list):
        print("rows.json must be a JSON list of event objects.")
        sys.exit(1)

    client = _client()
    sheet = client.open_by_key(inbox_common.SHEET_ID)
    n = inbox_common.append_events(events, default_source=DEFAULT_SOURCE,
                                   sheet=sheet, dry_run=args.dry_run)
    if args.dry_run:
        return

    # Log each source submission done (keyed by resp_key). Events sharing a
    # resp_key came from one submission; log it once with the event count.
    counts, submitters = {}, {}
    for ev in events:
        rk = ev.get("resp_key")
        if rk:
            counts[rk] = counts.get(rk, 0) + 1
            submitters.setdefault(rk, ev.get("submitter", ""))
    if counts:
        log_ws = get_log_ws(client)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = [[rk, submitters.get(rk, ""), "done", cnt, now, ""] for rk, cnt in counts.items()]
        log_ws.append_rows(rows, value_input_option="USER_ENTERED")
        print(f"Logged {len(counts)} submission(s) done in '{LOG_TAB}'.")
    else:
        print("(No resp_key values in rows.json — nothing logged. Paste-path events "
              "are expected to have none.)")


def main():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sheet-id", help="Responses-sheet key (overrides FEEDBACK_SHEET_ID).")
    p.add_argument("--tab", help=f"Responses worksheet name (default '{FEEDBACK_TAB}').")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Create the Feedback Log tab (run once).").set_defaults(func=cmd_init)
    sub.add_parser("pending", help="List feedback submissions not yet processed.").set_defaults(func=cmd_pending)
    sub.add_parser("fetch", help="Dump pending submissions to feedback_work/manifest.json.").set_defaults(func=cmd_fetch)

    w = sub.add_parser("write", help="Append extracted events (rows.json) to Inbox, log submissions done.")
    w.add_argument("rows", help="Path to the JSON list of extracted event dicts.")
    w.add_argument("--dry-run", action="store_true", help="Show what would be written, don't write.")
    w.set_defaults(func=cmd_write)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
