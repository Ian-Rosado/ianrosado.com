# Portland Events Scrapers

Python scrapers for the Portland Events calendar project. Runs all sources in parallel
and outputs structured JSON + CSV.

## Setup

```bash
cd scripts/event-scrapers
pip install -r requirements.txt
```

## Run

```bash
# Scrape all sources, next 30 days (default)
python run_all.py

# Next 14 days only
python run_all.py --days 14

# Music calendar only
python run_all.py --calendar music

# Events calendar only
python run_all.py --calendar events

# Farmers markets only
python run_all.py --calendar farmers_market
```

Output files land in `output/events_YYYY-MM-DD.json` and `output/events_YYYY-MM-DD.csv`.

## Event Schema

| Field | Type | Description |
|---|---|---|
| `title` | str | Event name |
| `date` | str | YYYY-MM-DD |
| `time` | str | HH:MM (24h), or "" |
| `end_time` | str | HH:MM (24h), or "" |
| `duration_minutes` | int\|null | Computed from time + end_time |
| `location` | str | Venue name / address |
| `cost` | str | "Free", "$10", "PWYC", etc. |
| `url` | str | Event detail page |
| `tags` | list | e.g. ["music", "free", "all-ages"] |
| `calendar` | str | `events` \| `music` \| `farmers_market` |
| `source` | str | Source site name |

## Sources

| Scraper | Source | Calendar | Method |
|---|---|---|---|
| `portland_living_cheap.py` | Portland Living on the Cheap | events | web_fetch |
| `pc_pdx.py` | PC-PDX Show Guide | music | web_fetch |
| `pdx_parent.py` | PDX Parent | events | web_fetch |
| `pdx_after_dark.py` | PDX After Dark | music | web_fetch |
| `nineteen_hz.py` | 19hz PNW | music | web_fetch |
| `calagator.py` | Calagator | events | web_fetch |
| `queer_social_club.py` | Queer Social Club | events | web_fetch |
| `laughs_pdx.py` | Laughs PDX | events | web_fetch |
| `flyer_escape.py` | Flyer Escape | music | web_fetch |
| `toc_portland.py` | TOC Portland | music | web_fetch |

## Sources Requiring Chrome (not yet scripted)

- curbsideserenade.org — Square Online (JS-required)
- Instagram sources (@loudnlitride, @williamsfirstfriday)
- Travel Portland — 403 bot block
- Do PDX — 403 bot block
- Bands in Town — 403 bot block

## Adding a New Scraper

1. Create `scrapers/my_source.py` with a `scrape()` function that returns a list of event dicts
2. Use `make_event()` from `scrapers/base.py` for consistent schema
3. Import and add to `SCRAPERS` dict in `run_all.py`
