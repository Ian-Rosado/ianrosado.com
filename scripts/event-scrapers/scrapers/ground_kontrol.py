"""
Scraper for Ground Kontrol — arcade bar: pinball and fighting-game tournaments,
Killer Queen nights, free-play parties, DJ nights.
URL: https://groundkontrol.com/events/
Format: The Events Calendar (Tribe) REST API — see tribe_common.py.
Calendar: events

Venue notices ("Blue Side Closed From 3:30-6:30PM For a Private Event") share
the calendar with real events; the add-to-calendar pipeline drops those for
every source (KNOWN_DROP_PATTERNS in portland_events_add.py).
"""

import re

from .tribe_common import fetch_tribe_events, tribe_to_event

SOURCE = "Ground Kontrol"
BASE = "https://groundkontrol.com"
LOCATION = "Ground Kontrol, 115 NW 5th Ave, Portland, OR 97209"

def scrape():
    events = []
    for ev in fetch_tribe_events(BASE):
        e = tribe_to_event(ev, SOURCE, tags=["games", "arcade"], default_location=LOCATION)
        if not e["title"]:
            continue
        if "ground kontrol" not in e["location"].lower():
            e["location"] = LOCATION
        # Monthly series carry the month in the title: "Rock Band x Ground
        # Kontrol (October 2026)". Strip it so recurring nights read cleanly.
        e["title"] = re.sub(r"\s*\((January|February|March|April|May|June|July|August|"
                            r"September|October|November|December)\s+\d{4}\)\s*$", "", e["title"])
        events.append(e)
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
