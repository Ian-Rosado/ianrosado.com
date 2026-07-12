"""
Portland Events — Master Scraper Runner
Runs all scrapers in parallel and writes combined output to:
  output/events_YYYY-MM-DD.json   (all events)
  output/events_YYYY-MM-DD.csv    (spreadsheet-friendly)

Usage:
  python run_all.py                    # scrape all sources
  python run_all.py --days 14          # only include events in next 14 days (default: 30)
  python run_all.py --calendar music   # filter to one calendar type
  python run_all.py --no-csv           # skip CSV output
  python run_all.py --push-to-sheets   # write results directly to Google Sheets inbox
  python run_all.py --push-to-sheets --clear  # clear sheet first, then write

Calendars:
  events          → General Portland Events calendar
  music           → Portland Live Music calendar
  comedy          → Portland Comedy calendar
  karaoke         → Portland Karaoke calendar
  farmers_market  → Portland Farmers Markets calendar
  sports          → Portland Sports calendar
"""

import json
import csv
import argparse
import importlib
import pkgutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

# ── Scraper auto-discovery ────────────────────────────────────────────────────
# Every module in scrapers/ that defines a top-level scrape() is run. Helper
# modules (base, espn_common, modular11_common) define none, so they're skipped.
# To add a source, just drop a new file with a scrape() into scrapers/.
# To temporarily disable a scraper, add its module name here:
DISABLED_SCRAPERS = set()

_SCRAPERS_DIR = Path(__file__).parent / "scrapers"

def discover_scrapers():
    found = {}
    for m in sorted(pkgutil.iter_modules([str(_SCRAPERS_DIR)]), key=lambda m: m.name):
        if m.name in DISABLED_SCRAPERS:
            continue
        mod = importlib.import_module(f"scrapers.{m.name}")
        if callable(getattr(mod, "scrape", None)):
            found[m.name] = mod.scrape
    return found

SCRAPERS = discover_scrapers()

CALENDAR_LABELS = {
    "events": "Portland Events",
    "music": "Portland Live Music",
    "comedy": "Portland Comedy",
    "karaoke": "Portland Karaoke",
    "farmers_market": "Portland Farmers Markets",
    "sports": "Portland Sports",
}

CSV_FIELDS = [
    "title", "date", "time", "end_time", "duration_minutes",
    "location", "cost", "url", "tags", "calendar", "source",
]


def run_all_scrapers():
    """Run all scrapers in parallel, return combined list of events."""
    all_events = []
    errors = []

    print(f"\nRunning {len(SCRAPERS)} scrapers in parallel...\n")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(fn): name
            for name, fn in SCRAPERS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                events = future.result()
                all_events.extend(events)
            except Exception as e:
                print(f"  [ERROR] {name} failed: {e}")
                errors.append(name)

    if errors:
        print(f"\nFailed scrapers: {', '.join(errors)}")

    return all_events


def filter_events(events, days=30, calendar=None):
    """Filter events to a date window and optional calendar type."""
    today = date.today()
    cutoff = today + timedelta(days=days)

    filtered = []
    for e in events:
        # Date filter. A multi-day event (end_date set) is kept while it's
        # still ongoing — drop only when its whole [date, end_date] window
        # falls outside [today, cutoff].
        if e["date"]:
            try:
                event_date = date.fromisoformat(e["date"])
                try:
                    event_end = date.fromisoformat(e.get("end_date") or e["date"])
                except ValueError:
                    event_end = event_date
                if event_end < today or event_date > cutoff:
                    continue
            except ValueError:
                pass  # Keep events with unparseable dates

        # Calendar filter
        if calendar and e.get("calendar") != calendar:
            continue

        filtered.append(e)

    return filtered


def deduplicate(events):
    """Remove duplicate events by (title, date, source)."""
    seen = set()
    unique = []
    for e in events:
        key = (e["title"].lower()[:50], e["date"], e["source"])
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def sort_events(events):
    """Sort by date, then time."""
    def sort_key(e):
        return (e.get("date") or "9999", e.get("time") or "99:99")
    return sorted(events, key=sort_key)


def write_json(events, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2, ensure_ascii=False)
    print(f"  JSON -> {path}")


def write_csv(events, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for e in events:
            row = dict(e)
            # Flatten tags list to comma-separated string
            row["tags"] = ", ".join(e.get("tags", []))
            writer.writerow(row)
    print(f"  CSV  -> {path}")


def print_summary(events):
    """Print a count breakdown by calendar and source."""
    from collections import Counter
    by_cal = Counter(e.get("calendar", "unknown") for e in events)
    by_src = Counter(e.get("source", "unknown") for e in events)

    print(f"\n{'='*50}")
    print(f"Total events: {len(events)}")
    print(f"\nBy calendar:")
    for cal, count in sorted(by_cal.items()):
        label = CALENDAR_LABELS.get(cal, cal)
        print(f"  {label}: {count}")
    print(f"\nBy source:")
    for src, count in sorted(by_src.items()):
        print(f"  {src}: {count}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="Portland Events scraper runner")
    parser.add_argument("--days", type=int, default=30,
                        help="Number of days ahead to include (default: 30)")
    parser.add_argument("--calendar", choices=sorted(CALENDAR_LABELS),
                        help="Filter to a specific calendar")
    parser.add_argument("--no-csv", action="store_true",
                        help="Skip CSV output")
    parser.add_argument("--output-dir", default="output",
                        help="Output directory (default: output/)")
    parser.add_argument("--push-to-sheets", action="store_true",
                        help="Write results to Google Sheets inbox after scraping")
    parser.add_argument("--clear", action="store_true",
                        help="With --push-to-sheets: clear existing sheet rows first")
    args = parser.parse_args()

    # Run scrapers
    raw_events = run_all_scrapers()
    print(f"\nRaw events collected: {len(raw_events)}")

    # Filter, dedup, sort
    events = filter_events(raw_events, days=args.days, calendar=args.calendar)
    events = deduplicate(events)
    events = sort_events(events)

    print_summary(events)

    # Write output
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    today_str = date.today().isoformat()
    suffix = f"_{args.calendar}" if args.calendar else ""

    json_path = output_dir / f"events_{today_str}{suffix}.json"
    write_json(events, json_path)

    if not args.no_csv:
        csv_path = output_dir / f"events_{today_str}{suffix}.csv"
        write_csv(events, csv_path)

    print(f"\nDone. {len(events)} events written.")

    if args.push_to_sheets:
        from sheets_writer import write_events_to_sheet
        # Re-sort by source then date for easier sheet review
        sheet_events = sorted(events, key=lambda e: (
            e.get("source") or "",
            e.get("date") or "9999",
            e.get("time") or "99:99",
        ))
        write_events_to_sheet(
            sheet_events,
            skip_duplicates=True,
            clear_first=args.clear,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
