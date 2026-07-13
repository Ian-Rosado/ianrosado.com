#!/usr/bin/env python3
"""
mine_corrections.py — profile review_corrections.jsonl into proposed rules.

The commit stage logs every place Ian's Review-tab choices differed from the
script's proposals. This script groups those corrections into recurring
patterns and prints a compact report of PROPOSED rule additions — it never
changes anything itself. Run it periodically (or when Ian asks to "profile my
corrections"); confirmed proposals get folded into:

  - KNOWN_DROP_PATTERNS / the Blocklist tab   (repeat drops)
  - KNOWN_COMEDY_VENUES / KNOWN_NON_MUSIC_VENUES / the skill's trivia
    venue table                               (repeat recategorizations)
  - venues.json                               (repeat URL edits)

Usage:
    python mine_corrections.py            # patterns seen 2+ times
    python mine_corrections.py --min 3    # raise the bar
    python mine_corrections.py --all      # include one-offs
    python mine_corrections.py --new      # only patterns not shown before,
                                          # then remember them (mined_state.json)

--new is what the add-workflow skill runs at the end of an add-events session:
quiet when there's nothing new, so recurring patterns get surfaced exactly once.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

LOG = Path(__file__).resolve().parent / "review_corrections.jsonl"
STATE = Path(__file__).resolve().parent / "mined_state.json"  # gitignored, per-machine


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def series_key(title):
    """Collapse date/program variants: first 5 significant words."""
    words = [w for w in norm(title).split() if len(w) > 2][:5]
    return " ".join(words)


def main():
    ap = argparse.ArgumentParser(description="Profile the review-corrections log")
    ap.add_argument("--min", type=int, default=2, help="Minimum occurrences to report (default 2)")
    ap.add_argument("--all", action="store_true", help="Report everything, including one-offs")
    ap.add_argument("--new", action="store_true",
                    help="Only patterns not previously reported; remembers what it showed")
    args = ap.parse_args()
    floor = 1 if args.all else args.min

    if not LOG.exists():
        print(f"No corrections log at {LOG} — nothing to mine yet.")
        return

    seen = set()
    if args.new and STATE.exists():
        try:
            seen = set(json.loads(STATE.read_text(encoding="utf-8")))
        except Exception:
            seen = set()

    def is_new(kind, key):
        """In --new mode, report a pattern once and remember it."""
        if not args.new:
            return True
        tag = f"{kind}:{key}"
        if tag in seen:
            return False
        seen.add(tag)
        return True

    recs = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()]

    # ── Repeat drops → blocklist / KNOWN_DROP_PATTERNS candidates ────────────
    drops = Counter()
    drop_titles = defaultdict(list)
    for r in recs:
        for d in r.get("dropped", []):
            k = series_key(d["title"])
            drops[k] += 1
            drop_titles[k].append(d["title"])
    drop_hits = [(k, c) for k, c in drops.most_common()
                 if c >= floor and is_new("drop", k)]

    # ── Repeat recategorizations → venue/keyword rule candidates ────────────
    recats = Counter()
    recat_examples = {}
    for r in recs:
        for d in r.get("recategorized", []):
            k = (norm(d.get("location", ""))[:40] or "(no venue)", d["from"], d["to"])
            recats[k] += 1
            recat_examples[k] = d["title"]
    recat_hits = [(k, c) for k, c in recats.most_common()
                  if c >= floor and is_new("recat", "|".join(k))]

    # ── Repeat field edits → venues.json / scraper-fix candidates ────────────
    edits = Counter()
    edit_examples = {}
    for r in recs:
        for d in r.get("field_edits", []):
            k = (d["field"], series_key(d["title"]))
            edits[k] += 1
            edit_examples[k] = d
    edit_hits = [(k, c) for k, c in edits.most_common()
                 if c >= floor and is_new("edit", "|".join(k))]

    # ── Rescued skips → dedup false positives (should stay ~zero) ───────────
    rescued = [d for r in recs for d in r.get("rescued_from_skip", [])]
    rescued = [d for d in rescued if is_new("rescue", series_key(d["title"]))]

    if args.new:
        STATE.write_text(json.dumps(sorted(seen), indent=0), encoding="utf-8")
        if not (drop_hits or recat_hits or edit_hits or rescued):
            print("No new correction patterns since the last mining pass.")
            return

    print(f"{len(recs)} commit run(s), {recs[0]['timestamp'][:10]} to {recs[-1]['timestamp'][:10]}"
          + (" — NEW patterns only" if args.new else "") + "\n")

    print(f"── Repeat drops ({len(drop_hits)} series ≥{floor}x) — blocklist/KNOWN_DROP_PATTERNS candidates ──")
    for k, c in drop_hits:
        print(f"  {c}x  {drop_titles[k][0][:70]}")
    if not drop_hits:
        print("  (none)")

    print(f"\n── Repeat recategorizations ({len(recat_hits)} ≥{floor}x) — venue-rule candidates ──")
    for (venue, f, t), c in recat_hits:
        print(f"  {c}x  {venue}: {f} -> {t}   e.g. \"{recat_examples[(venue, f, t)][:50]}\"")
    if not recat_hits:
        print("  (none)")

    print(f"\n── Repeat field edits ({len(edit_hits)} ≥{floor}x) — venues.json / scraper-fix candidates ──")
    for (field, sk), c in edit_hits:
        d = edit_examples[(field, sk)]
        print(f"  {c}x  {field}: \"{d['title'][:40]}\"  {d['from'][:25]!r} -> {d['to'][:25]!r}")
    if not edit_hits:
        print("  (none)")

    print(f"\n── Rescued from skip: {len(rescued)} "
          f"(dedup false positives — investigate if this grows) ──")
    for d in rescued[:10]:
        print(f"  {d['date']}  {d['title'][:60]}")


if __name__ == "__main__":
    main()
