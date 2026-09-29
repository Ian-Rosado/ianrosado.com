"""
Scraper for Clinton Street Theater — cult films, Rocky Horror, Church of Film,
drag and community events.
URL: https://cstpdx.com/schedule/
Format: The Events Calendar (Tribe) REST API — see tribe_common.py.
Calendar: events

Plain film screenings are passed through as-is: the add-to-calendar Review step
already pre-skips them (Clinton Street is in KNOWN_CINEMA_VENUES), while special
programming (Q&As, live scores, cabaret, drag) is left for a human call.
"""

from .tribe_common import fetch_tribe_events, tribe_to_event

SOURCE = "Clinton Street Theater"
BASE = "https://cstpdx.com"
LOCATION = "Clinton Street Theater, 2522 SE Clinton St, Portland, OR 97202"


def scrape():
    events = []
    for ev in fetch_tribe_events(BASE):
        e = tribe_to_event(ev, SOURCE, tags=["film"], default_location=LOCATION)
        # The venue record is often blank or just the theater name; always give
        # the full address so dedup and the screening check see the venue.
        if "clinton" not in e["location"].lower() or "SE Clinton" not in e["location"]:
            e["location"] = LOCATION
        if e["title"]:
            events.append(e)
    print(f"  [{SOURCE}] Found {len(events)} events")
    return events


if __name__ == "__main__":
    import json
    print(json.dumps(scrape(), indent=2))
