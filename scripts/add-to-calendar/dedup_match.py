"""
dedup_match.py
--------------
Source-agnostic helpers for spotting the same event listed differently by
different scrapers. Used by portland_events_add.py (Dedup tab + intra-batch
dedup), so every scraper's results get the same treatment.

  fold_text(s)        accent/special-letter folding ("LØLØ" -> "lolo", "&" -> "and")
  title_words(s)      significant title words (folded, no "[genre]" prefix, no year)
  TitleIDF            rarity weights over a pool of titles: distinctive words
                      ("kultur", "shock") count far more than common ones
                      ("trivia", "night", "festival") when comparing titles
  address_key(loc)    ("3552", "mississippi") from a street address, so a venue
                      named in one source and only addressed in another still match
"""

import math
import re
import unicodedata
from collections import Counter

# Letters NFKD doesn't decompose into ASCII + a combining mark.
_SPECIAL = str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe",
                          "ß": "ss", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
                          "þ": "th", "ı": "i",
                          "’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def fold_text(s):
    """Lowercase, strip accents/special letters, '&' -> 'and'."""
    s = (s or "").translate(_SPECIAL)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("&", " and ")


_TITLE_STOP = {
    "the", "a", "an", "and", "with", "w", "at", "in", "on", "of", "for", "to",
    "feat", "featuring", "ft", "vs", "plus", "presents", "present", "presented",
    "by", "live", "tour", "tickets", "pdx", "portland", "event", "special",
    "night", "show", "screening", "restoration", "4k", "anniversary", "edition",
    # Weekdays name a series slot, not the event ("Trivia Thursdays" vs
    # "Jazz Titan Thursdays").
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mondays", "tuesdays", "wednesdays", "thursdays", "fridays", "saturdays", "sundays",
}


def title_words(s):
    """Significant words of a title for duplicate matching. Drops a leading
    "[genre]" tag (added by build_title), a "(1982)"-style year, and
    stopwords — so "[comedy] Vidura Bandara Rajapaksa" ~ "Vidura Bandara
    Rajapaksa: The Paradise Tour" and "The Thing (1982) Screening" ~ "The Thing"."""
    s = re.sub(r"^\s*\[[^\]]+\]\s*", "", s or "")
    s = re.sub(r"\(\s*(19|20)\d\d\s*\)", " ", s)
    s = re.sub(r"'", "", fold_text(s))
    return {w for w in re.findall(r"[a-z0-9]+", s) if w not in _TITLE_STOP and len(w) > 1}


class TitleIDF:
    """Inverse-document-frequency weights over a pool of titles (the existing
    calendar window plus the incoming batch)."""

    def __init__(self, titles):
        docs = [title_words(t) for t in titles]
        self.n = max(len(docs), 1)
        self.df = Counter(w for d in docs for w in d)

    def weight(self, w):
        return math.log((self.n + 1) / (1 + self.df.get(w, 0)))

    def overlap(self, a, b, ignore=frozenset()):
        """Weighted overlap coefficient of two titles (0..1): the shared words'
        weight over the lighter title's total weight. A headliner-only listing
        ("Bella Kay") fully overlaps the full billing ("Bella Kay: The Reckless
        Tour"), while two nights that only share "trivia" barely register.
        `ignore` drops words first (e.g. the venue's name appearing in a title)."""
        return self.overlap_sets(title_words(a) - ignore, title_words(b) - ignore)

    def overlap_sets(self, wa, wb):
        if not wa or not wb:
            return 0.0
        shared = sum(self.weight(w) for w in wa & wb)
        lighter = min(sum(self.weight(w) for w in wa), sum(self.weight(w) for w in wb))
        return shared / lighter if lighter > 0 else 0.0

    def is_rare(self, w, max_df):
        return self.df.get(w, 0) <= max_df

    def distinct_on_both_sides(self, wa, wb, max_df):
        """Each title has a distinctive word the other lacks — they name
        different things ("Eraserhead x Fresh Cut Flowers" vs "Blue Velvet x
        Fresh Cut Flowers") even when they share a series name."""
        return (any(self.is_rare(w, max_df) for w in wa - wb)
                and any(self.is_rare(w, max_df) for w in wb - wa))


_DIRS = r"(?:n|s|e|w|ne|nw|se|sw|north|south|east|west|northeast|northwest|southeast|southwest)"


def address_key(location):
    """(house number, first street word) from a location, e.g.
    "The Pharmacy, 2100 NW Glisan St" and "2100 NW Glisan St, Portland" both
    give ("2100", "glisan"). None when there's no street address."""
    m = re.search(r"\b(\d{2,5})\s+(?:" + _DIRS + r"\.?\s+)?([a-z][a-z]+)", fold_text(location))
    return (m.group(1), m.group(2)) if m else None
