#!/usr/bin/env python3
"""
get_events.py — batch-fetch Google Calendar event details as JSON.

Built for the Instagram-post workflow: Ian pastes a table of chosen events
(usually as calendar *edit URLs*); one run of this script returns everything
the post needs, instead of per-event lookups in a chat session.

Usage:
    python get_events.py <url-or-id> [<url-or-id> ...]
    python get_events.py --file picks.txt        # one URL/ID per line
    python get_events.py --json out.json <...>   # also write to a file

Accepts, in any mix:
  - Google Calendar edit URLs:  https://calendar.google.com/calendar/u/0/r/eventedit/<BLOB>
    (the blob is url-safe base64 of "<eventId> <calendarId>"; the calendar
    domain arrives truncated and is reconstructed)
  - bare eventedit blobs
  - bare event IDs (searched across every configured calendar, including
    trivia and the imported Pedalpalooza calendar)

Output: a JSON list, one object per input, in input order:
  {input, event_id, calendar, title, date, end_date, time, end_time, all_day,
   location, cost, url, ig_handle, description, found, error}

ig_handle is the venue's Instagram handle (no @) for the post's tag list:
looked up in ig_handles.json by venue name (lowercase, before the first comma
of the location), falling back to an instagram.com profile link in the event
description. Empty when unknown — find it and add it to ig_handles.json
(see find_ig_handles.py).

Auth: shared token via scripts/google_auth.py.
"""

import argparse
import base64
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import google_auth

# Calendar names/IDs from the shared config, plus the imported Pedalpalooza
# calendar (posts sometimes feature bike rides).
_CFG = json.loads(
    (Path(__file__).resolve().parent.parent.parent / "src-shared" / "config" / "calendars.json")
    .read_text(encoding="utf-8"))
CALENDARS = {c["name"]: c["id"]
             for c in _CFG["calendars"] + _CFG["triviaCalendars"] + [_CFG["pedalpalooza"]]}
_ID_TO_NAME = {v: k for k, v in CALENDARS.items()}

TZ = ZoneInfo("America/Los_Angeles")

# Venue/organizer name -> Instagram handle, maintained by find_ig_handles.py.
try:
    IG_HANDLES = {k: v for k, v in json.loads(
        (Path(__file__).resolve().parent / "ig_handles.json").read_text(encoding="utf-8")
    ).items() if not k.startswith("_")}
except FileNotFoundError:
    IG_HANDLES = {}

# instagram.com first path segments that are NOT profile handles.
_IG_RESERVED = {"p", "reel", "reels", "tv", "stories", "explore", "accounts",
                "share", "sharer", "hashtag", "embed"}


def _ig_handle(location, desc):
    key = (location or "").split(",")[0].strip().lower()
    if key in IG_HANDLES:
        return IG_HANDLES[key]
    for m in re.finditer(r"instagram\.com/(?:#!/)?([A-Za-z0-9._]{2,30})", desc or ""):
        h = m.group(1).strip("._").lower()
        if h not in _IG_RESERVED:
            return h
    return ""


def parse_input(token):
    """Return (event_id, calendar_id_or_None) from a URL, blob, or bare ID."""
    token = token.strip().strip('"').strip("'")
    if "/eventedit/" in token:
        token = token.rsplit("/eventedit/", 1)[-1].split("?")[0]
    # A bare event ID has no space when decoded and isn't valid base64 of
    # "<id> <cal>" — detect eventedit blobs by trying to decode.
    try:
        blob = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(blob).decode("utf-8", "replace")
        if " " in decoded:
            eid, cal_raw = decoded.split(" ", 1)
            # The decoded calendar domain is truncated (ends "@g") — rebuild it.
            cal_id = cal_raw.split("@")[0] + "@group.calendar.google.com"
            return eid, cal_id
    except Exception:
        pass
    return token, None  # bare event ID — caller scans all calendars


def _fmt_time(dt_iso):
    dt = datetime.fromisoformat(dt_iso).astimezone(TZ)
    return dt.strftime("%I:%M %p").lstrip("0")


def _desc_first_url(desc):
    m = re.search(r"https?://\S+", desc or "")
    return re.sub(r"[.,)>'\"]+$", "", m.group(0)) if m else ""


def _desc_cost(desc):
    """First non-URL, non-Tags line of the description (the pipeline's cost slot)."""
    for line in re.split(r"\r?\n|<br\s*/?>", desc or "", flags=re.I):
        line = re.sub(r"<[^>]+>", " ", line)
        line = re.sub(r"\s+", " ", line).strip()
        low = line.lower()
        if not line or line.startswith("http") or low.startswith("tags:") \
                or low.startswith("look up venue"):
            continue
        return re.sub(r"https?://\S+", "", line).strip(" .|-")
    return ""


def shape(ev, cal_id, original_input):
    start = ev.get("start", {})
    end = ev.get("end", {})
    all_day = "date" in start
    desc = ev.get("description", "")
    return {
        "input": original_input,
        "event_id": ev.get("id", ""),
        "calendar": _ID_TO_NAME.get(cal_id, cal_id),
        "title": ev.get("summary", ""),
        "date": (start.get("dateTime") or start.get("date", ""))[:10],
        "end_date": (end.get("dateTime") or end.get("date", ""))[:10],
        "time": "" if all_day else _fmt_time(start["dateTime"]),
        "end_time": "" if all_day or not end.get("dateTime") else _fmt_time(end["dateTime"]),
        "all_day": all_day,
        "location": ev.get("location", ""),
        "cost": _desc_cost(desc),
        "url": _desc_first_url(desc),
        "ig_handle": _ig_handle(ev.get("location", ""), desc),
        "description": desc,
        "found": True,
        "error": "",
    }


def fetch_one(svc, token):
    from googleapiclient.errors import HttpError
    eid, cal_id = parse_input(token)
    tried = [cal_id] if cal_id else list(CALENDARS.values())
    last_err = ""
    for cid in tried:
        try:
            ev = svc.events().get(calendarId=cid, eventId=eid).execute()
            return shape(ev, cid, token)
        except HttpError as e:
            last_err = f"HTTP {e.resp.status}"
            continue
    return {"input": token, "event_id": eid, "found": False,
            "error": f"not found in {len(tried)} calendar(s) ({last_err})"}


def main():
    ap = argparse.ArgumentParser(description="Batch-fetch calendar event details as JSON")
    ap.add_argument("inputs", nargs="*", help="Event edit URLs, eventedit blobs, or bare event IDs")
    ap.add_argument("--file", help="Read inputs from a file, one per line")
    ap.add_argument("--json", dest="json_out", help="Also write the result to this file")
    args = ap.parse_args()

    inputs = list(args.inputs)
    if args.file:
        inputs += [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.strip().startswith("#")]
    if not inputs:
        ap.error("No inputs — pass URLs/IDs or --file")

    svc = google_auth.get_calendar_service()
    results = [fetch_one(svc, t) for t in inputs]

    # Duplicate guard: the same event pasted into two slots is a curation slip.
    seen = {}
    for r in results:
        if r["found"]:
            if r["event_id"] in seen:
                r["error"] = f"DUPLICATE of input: {seen[r['event_id']]}"
            else:
                seen[r["event_id"]] = r["input"]

    out = json.dumps(results, indent=2, ensure_ascii=False)
    print(out)
    if args.json_out:
        Path(args.json_out).write_text(out, encoding="utf-8")
        print(f"\n(wrote {args.json_out})", file=sys.stderr)

    missing = [r for r in results if not r["found"]]
    if missing:
        print(f"\nWARNING: {len(missing)} input(s) not found:", file=sys.stderr)
        for r in missing:
            print(f"  {r['input']}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
