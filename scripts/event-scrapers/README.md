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

## Sports sources (Portland Sports calendar — home games only)

| Scraper | Team | Sport | Data source |
|---|---|---|---|
| `nba_blazers.py` | Trail Blazers | basketball | data.nba.com legacy JSON (cdn.nba.com is 403-blocked) |
| `wnba_fire.py` | Portland Fire | basketball | ESPN site.api (via `espn_common.py`) |
| `rip_city_remix.py` | Rip City Remix | basketball (G League) | ESPN site.api |
| `timbers.py` | Portland Timbers | soccer (MLS) | ESPN site.api |
| `thorns.py` | Portland Thorns | soccer (NWSL) | ESPN site.api |
| `hillsboro_hops.py` | Hillsboro Hops | baseball (MiLB) | MLB StatsAPI (`statsapi.mlb.com`) |
| `portland_pickles.py` | Portland Pickles | baseball (WCL) | wclstats.com (PrestoSports) |
| `winterhawks.py` | Portland Winterhawks | hockey (WHL) | HockeyTech LeagueStat feed |
| `portland_bangers.py` | Portland Bangers | soccer (USL League Two) | modular11 (via `modular11_common.py`), team 4928 |
| `cherry_bombs_fc.py` | Portland Cherry Bombs | soccer (USL W League) | modular11, team 8112 |
| `rose_city_rollers.py` | Rose City Rollers | roller derby | rosecityrollers.com (static HTML) |

Notes:
- **Offseason returns 0, not an error.** Blazers (NBA), Rip City Remix (G League),
  and Winterhawks (WHL) all run fall→spring, so they return 0 upcoming games in
  summer; they auto-populate when the next season's schedule publishes (~Aug).
- **ESPN soccer needs `?fixture=true`** to return upcoming (not past) matches —
  handled in `espn_common.py`.
- **Sports schedules span a whole season.** `run_all.py`'s default `--days 30`
  window trims most of it; to load a full season run e.g.
  `python run_all.py --calendar sports --days 200`.
- Two shared helpers make adding teams cheap: `espn_common.py` (any ESPN-listed
  team — sport, league, team id, tags) and `modular11_common.py` (any USL
  League Two / USL W League / other modular11 team — just the team id). The
  Bangers/Cherry Bombs schedules aren't on their own Squarespace sites (those
  are ticket-waitlist forms), but the USL league pages embed a modular11
  widget whose data is in static HTML — that's what those two scrapers read.

## Sources Requiring Chrome / manual (not scriptable)

- curbsideserenade.org — Square Online (JS-required)
- Instagram sources (@loudnlitride, @williamsfirstfriday)

## Adding a New Scraper

1. Create `scrapers/my_source.py` with a `scrape()` function that returns a list of event dicts
2. Use `make_event()` from `scrapers/base.py` for consistent schema
3. Import and add to `SCRAPERS` dict in `run_all.py`
