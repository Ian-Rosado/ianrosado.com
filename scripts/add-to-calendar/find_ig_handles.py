#!/usr/bin/env python3
"""
find_ig_handles.py — discover venues'/organizers' Instagram handles from their
own websites and save them to ig_handles.json.

Built for the Instagram-post workflow: posts tag the venues/orgs behind each
event so they can re-share. A handle is only trusted when it comes from the
org's OWN site (the instagram.com link in their header/footer), never guessed
from the name.

Usage:
    python find_ig_handles.py --seed                 # every venues.json entry not yet in ig_handles.json
    python find_ig_handles.py "revolution hall"      # name already in venues.json
    python find_ig_handles.py "new venue=https://newvenue.com"   # name + site
    python find_ig_handles.py --dry-run --seed       # report only, no writes

Results:
  - exactly one handle found on the site  -> saved to ig_handles.json
  - several distinct handles found        -> candidates printed, NOT saved
    (pick the right one and add it to ig_handles.json by hand)
  - none found / fetch failed             -> reported; find it manually

ig_handles.json keys follow the venues.json convention: lowercase venue name,
the part before the first comma of the event location. Handles are stored
without the leading @.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
VENUES = HERE / "venues.json"
HANDLES = HERE / "ig_handles.json"

# First path segment of instagram.com URLs that are NOT profile handles.
RESERVED = {
    "p", "reel", "reels", "tv", "stories", "explore", "accounts", "share",
    "sharer", "hashtag", "about", "developer", "directory", "legal", "web",
    "invites", "embed", "oauth",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def handles_in(html):
    """Distinct IG handles linked from the page, in order of appearance."""
    found = []
    for m in re.finditer(r"instagram\.com/(?:#!/)?([A-Za-z0-9._]{2,30})", html):
        h = m.group(1).strip("._").lower()
        if h and h not in RESERVED and h not in found:
            found.append(h)
    return found


def probe(name, url):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        r.raise_for_status()
    except Exception as e:
        return {"name": name, "url": url, "handles": [], "error": str(e)}
    return {"name": name, "url": url, "handles": handles_in(r.text), "error": ""}


def main():
    ap = argparse.ArgumentParser(description="Find Instagram handles from venue websites")
    ap.add_argument("targets", nargs="*",
                    help='"name" (looked up in venues.json) or "name=https://site"')
    ap.add_argument("--seed", action="store_true",
                    help="probe every venues.json entry missing from ig_handles.json")
    ap.add_argument("--dry-run", action="store_true", help="report only, don't write")
    args = ap.parse_args()

    venues = {k: v for k, v in load(VENUES).items() if not k.startswith("_")}
    store = load(HANDLES)
    if not store:
        store = {"_comment": ("Map of venue/organizer name (lowercase, name before first "
                              "comma of the event location) -> Instagram handle (no @). "
                              "Used by get_events.py to build the post's tag list. Only add "
                              "handles verified from the org's own site or IG page — a wrong "
                              "tag pings a stranger. Grows over time like venues.json.")}
    known = {k for k in store if not k.startswith("_")}

    jobs = []
    for t in args.targets:
        if "=" in t:
            name, url = t.split("=", 1)
            jobs.append((name.strip().lower(), url.strip()))
        else:
            name = t.strip().lower()
            if name not in venues:
                print(f"SKIP  {name}: not in venues.json — pass as name=https://site")
                continue
            jobs.append((name, venues[name]))
    if args.seed:
        jobs += [(n, u) for n, u in venues.items() if n not in known
                 and n not in {j[0] for j in jobs}]
    if not jobs:
        ap.error("Nothing to do — pass targets and/or --seed")

    added = 0
    for name, url in jobs:
        r = probe(name, url)
        if r["error"]:
            print(f"FAIL  {name}: {r['error']}")
        elif not r["handles"]:
            print(f"NONE  {name}: no instagram link on {url}")
        elif len(r["handles"]) == 1:
            h = r["handles"][0]
            print(f"OK    {name}: @{h}")
            store[name] = h
            added += 1
        else:
            print(f"MULTI {name}: {', '.join('@' + h for h in r['handles'])} — pick one, add by hand")

    if added and not args.dry_run:
        HANDLES.write_text(
            json.dumps(store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {added} handle(s) to {HANDLES.name}")
    elif added:
        print(f"\n(dry-run: {added} handle(s) NOT written)")


if __name__ == "__main__":
    main()
