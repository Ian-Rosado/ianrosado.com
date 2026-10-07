"""
export_picks.py — publish an Instagram post's picks on pdx-events.com.

Reads an event-cards file (instagram/event_cards_<dates>.html) — the per-event
cards rendered for an "Events of the Week" or "Plan Your Weekend" post, which
hold each pick's category, name, description, venue and time — and writes it
as JSON to src-pdx-events/data/picks/, where the site builds a /picks/ page
from it. Run it once the cards are final (after rendering), and commit the
JSON with the post.

    python export_picks.py ../../instagram/event_cards_oct5_11.html
    python export_picks.py --all          # (re)export every event_cards_*.html
    python export_picks.py --year 2027 FILE

The card templates have changed over time, so parsing is deliberately loose;
every pick missing a date or venue is reported — fix the card (or the JSON)
before committing.
"""

import argparse
import html
import json
import re
import sys
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "src-pdx-events" / "data" / "picks"

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

FIELDS = {"day-name", "day-num", "event-date", "category", "tile-tag", "event-name",
          "description", "tile-meta", "meta-venue", "meta-details"}

MONTH_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
MONTH_DAY = re.compile(MONTH_RE + r"\s+(\d{1,2})(?:\s*[–-]\s*(?:" + MONTH_RE + r"\s+)?(\d{1,2}))?", re.I)
WEEKDAY_RANGE = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*(?:\s*(?:[–-]|&)\s*(mon|tue|wed|thu|fri|sat|sun)[a-z]*)?\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", re.I)
# "4–6 PM": the start takes the end's am/pm
TIME_RANGE_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(?:([ap])\.?m)?\s*[–-]\s*\d{1,2}(?::\d{2})?\s*([ap])\.?m\b", re.I)
COST_RE = re.compile(r"\bfree\b|\$|\btickets?\b|\bticketed\b|^from\b|\bdonations?\b|\bpwyc\b|\brsvp\b|\bsliding\b|\bno cover\b", re.I)


# Tile palette shared by every card template (the site has the same colors)
TILE_COLORS = {"green", "teal", "blue", "amber", "coral", "purple", "pink"}

# Post canvas → accent, from the color-wheel table in the
# portland-events-instagram-post skill (plus the two legacy canvases)
THEME_ACCENTS = {
    "#0d2b1a": "#5cdc80", "#062a2a": "#3ecfb0", "#0a1f3a": "#5ca8ff",
    "#15163a": "#8a9bff", "#1c0e30": "#b39dff", "#2a0e28": "#f07ad8",
    "#2e1310": "#ff7a5c", "#2a1c06": "#f0a500", "#20260a": "#c4dd5e",
    "#0a1a3a": "#5ca8ff", "#1a0e2e": "#f07ad8",
}


def post_theme(source):
    """The post's canvas + accent colors, from its `.post { background }` CSS."""
    m = re.search(r"\.post\s*\{[^}]*?background:\s*(#[0-9a-f]{6})", source, re.I)
    if not m:
        return None
    bg = m.group(1).lower()
    accent = THEME_ACCENTS.get(bg)
    if not accent:
        a = re.search(r"\.title span\s*\{\s*color:\s*(#[0-9a-f]{6})", source, re.I)
        accent = a.group(1).lower() if a else None
    return {"bg": bg, "accent": accent} if accent else None


class CardParser(HTMLParser):
    """Collects (field, text) in document order; text goes to the innermost
    element carrying one of FIELDS."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []   # field name or None, per open element
        self.tokens = []  # [field, text]
        self.in_body = False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        if tag in ("br", "img", "rect", "path"):
            return
        classes = (dict(attrs).get("class") or "").split()
        # A tile's color class ("event-tile green" / "tile amber")
        if self.in_body and ({"event-tile", "tile"} & set(classes)):
            color = next((c for c in classes if c in TILE_COLORS), None)
            if color:
                self.tokens.append(["tile-color", color])
        field = next((c for c in classes if c in FIELDS), None)
        self.stack.append(field)
        if field and self.in_body:
            self.tokens.append([field, ""])

    def handle_endtag(self, tag):
        if tag in ("br", "img", "rect", "path"):
            return
        if self.stack:
            self.stack.pop()

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_data(self, data):
        if not self.in_body:
            return
        field = next((f for f in reversed(self.stack) if f), None)
        if field and self.tokens and self.tokens[-1][0] == field:
            self.tokens[-1][1] += data


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def window_from_name(stem, year):
    """event_cards_sep28_oct4 → (date(…9, 28), date(…10, 4))"""
    m = re.fullmatch(r"event_cards_([a-z]{3})(\d{1,2})_(?:([a-z]{3}))?(\d{1,2})", stem)
    if not m:
        raise ValueError(f"can't read a date range from {stem}")
    m1, d1, m2, d2 = m.groups()
    start = date(year, MONTHS.index(m1) + 1, int(d1))
    end = date(year, MONTHS.index(m2 or m1) + 1, int(d2))
    if end < start:
        end = end.replace(year=year + 1)
    return start, end


def window_days(start, end):
    return [start + timedelta(n) for n in range((end - start).days + 1)]


def resolve_dates(text, days):
    """First date (and optional end) mentioned in `text`, within the post window."""
    in_window = lambda d: days[0] - timedelta(3) <= d <= days[-1] + timedelta(3)

    m = MONTH_DAY.search(text)
    if m:
        mon1, d1, mon2, d2 = m.groups()
        y = days[0].year
        try:
            start = date(y, MONTHS.index(mon1[:3].lower()) + 1, int(d1))
            end = date(y, MONTHS.index((mon2 or mon1)[:3].lower()) + 1, int(d2)) if d2 else None
            if in_window(start):
                return start, end
        except ValueError:
            pass

    # "Mon 5", "Fri–Sun 7–9" (day-header): day numbers, month from the window
    m = re.match(r"^\D*?(\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?\b", text)
    if m:
        by_num = {d.day: d for d in days}
        start = by_num.get(int(m.group(1)))
        if start:
            return start, by_num.get(int(m.group(2))) if m.group(2) else None

    if re.search(r"all\s+weekend", text, re.I):
        return days[0], days[-1]

    m = WEEKDAY_RANGE.search(text)
    if m:
        by_wd = {WEEKDAYS[d.weekday()]: d for d in days}
        start = by_wd.get(m.group(1)[:3].lower())
        end = by_wd.get(m.group(2)[:3].lower()) if m.group(2) else None
        if not start and end:  # "Thu–Sun" in a Fri–Sun post: began before the window
            start = days[0]
        if start:
            return start, end
    return None, None


def split_meta(meta):
    """'Fri Jul 10 · SE Alder St · 4pm · Free' → venue, details"""
    venue, details = "", []
    for seg in [s.strip() for s in re.split(r"\s+·\s+", meta) if s.strip()]:
        datey = MONTH_DAY.search(seg) or re.match(r"^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\b", seg, re.I)
        timey = TIME_RE.search(seg) or re.match(r"^all (day|weekend|evening)$|^dusk$", seg, re.I)
        if not venue and not (datey or timey or COST_RE.search(seg)):
            venue = seg
        elif not (datey and not timey):  # the page shows the date already
            details.append(seg)
    return venue, " · ".join(details)


def parse_time(text):
    text = re.sub(r"\b(?:til|till|until|to)\s+\d{1,2}(?::\d{2})?\s*[ap]\.?m\b", "", text, flags=re.I)
    m = TIME_RANGE_RE.search(text)
    if m:
        h, mins, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or m.group(4)).lower()
    else:
        m = TIME_RE.search(text)
        if not m:
            return ""
        h, mins, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
    h = h % 12 + (12 if ap == "p" else 0)
    return f"{h:02d}:{mins:02d}"


def parse_file(path, year):
    stem = Path(path).stem
    start, end = window_from_name(stem, year)
    days = window_days(start, end)
    kind = "week" if len(days) == 7 and start.weekday() == 0 else "weekend"

    source = Path(path).read_text(encoding="utf-8")
    p = CardParser()
    p.feed(source)

    picks, date_ctx, category, color = [], "", "", ""
    for field, raw in p.tokens:
        text = clean(raw)
        if field == "tile-color":
            color = raw
        elif field == "day-name":
            date_ctx = text
        elif field == "day-num":
            date_ctx = f"{date_ctx} {text}".strip()
        elif field == "event-date":
            date_ctx = text
        elif field in ("category", "tile-tag"):
            category = text
        elif field == "event-name":
            picks.append({"_date_ctx": date_ctx, "_category": category, "_color": color, "name": text,
                          "description": "", "_meta": "", "venue": "", "details": ""})
            category, color = "", ""
        elif picks:
            cur = picks[-1]
            if field == "description":
                cur["description"] = text
            elif field == "tile-meta" and text:
                cur["_meta"] = text
            elif field == "meta-venue":
                cur["venue"] = text
            elif field == "meta-details":
                cur["details"] = text

    out, problems = [], []
    for pk in picks:
        cat = pk.pop("_category")
        slot = None
        if cat.startswith("☀"):
            slot = "day"
        elif cat.startswith("🌙"):
            slot = "night"
        # "🧄 Food Festival · Free" → emoji "🧄", category "Food Festival"
        m = re.match(r"^([^\w\s]+)\s*(.*)$", cat)
        emoji, label = (m.group(1), m.group(2)) if m else ("", cat)
        label = re.split(r"\s+·\s+", label)[0]
        meta = pk.pop("_meta")
        if meta and not pk["venue"]:
            pk["venue"], pk["details"] = split_meta(meta)
        ctx = pk.pop("_date_ctx")
        d_start, d_end = resolve_dates(ctx, days)
        if not d_start:
            d_start, d_end = resolve_dates(f"{meta} {pk['details']}", days)
        free = bool(re.search(r"\bfree\b", f"{cat} {meta} {pk['details']}", re.I))
        rec = {
            "date": d_start.isoformat() if d_start else "",
            **({"endDate": d_end.isoformat()} if d_end and d_end != d_start else {}),
            "time": parse_time(f"{pk['details']} {meta}"),
            "slot": slot,
            "emoji": emoji,
            "category": label,
            "name": pk["name"],
            "description": pk["description"],
            "venue": pk["venue"],
            "details": pk["details"],
            "free": free,
            "color": pk.pop("_color") or None,
        }
        if not rec["date"] or not rec["venue"]:
            problems.append(f"{stem}: {rec['name']!r} missing {'date' if not rec['date'] else 'venue'}")
        out.append(rec)

    out.sort(key=lambda r: (r["date"] or "9", 0 if r["slot"] == "day" else 1 if r["slot"] == "night" else 0, r["time"] or "99"))
    rid = f"{'week' if kind == 'week' else 'weekend'}-of-{start.isoformat()}"
    data = {"id": rid, "type": kind, "start": start.isoformat(), "end": end.isoformat(),
            "source": f"instagram/{Path(path).name}", "theme": post_theme(source), "picks": out}
    return data, problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true", help="export every instagram/event_cards_*.html")
    ap.add_argument("--year", type=int, default=date.today().year)
    args = ap.parse_args()

    files = sorted((REPO / "instagram").glob("event_cards_*.html")) if args.all else [Path(f) for f in args.files]
    if not files:
        ap.error("give one or more event_cards_*.html files, or --all")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_problems = []
    for f in files:
        data, problems = parse_file(f, args.year)
        all_problems += problems
        out = OUT_DIR / f"{data['id']}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{f.name} -> {out.relative_to(REPO)} ({len(data['picks'])} picks)")
    if all_problems:
        print("\nNeeds a look:", *all_problems, sep="\n  ")
        sys.exit(1)


if __name__ == "__main__":
    main()
