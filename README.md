# invasive-arrivals

An open, global screen of [GBIF](https://www.gbif.org) for **candidate first national
records of known invasive species**: places where a species that the Global Register of
Introduced and Invasive Species (GRIIS) flags as invasive somewhere has turned up in a
country where GBIF has never recorded it before and where no GRIIS checklist lists it.

By MV2 of Munim, Inc. (mv2@munimtech.com). The code and text were made with AI agents
working in his name. Code: Apache-2.0. Outputs and text: CC BY 4.0.

Two studies, both pre-registered before any output existed:

| study | what | status |
|---|---|---|
| **IA-1** ([PREREGISTRATION.md](PREREGISTRATION.md), [ADDENDUM-1.md](ADDENDUM-1.md)) | retrospective: every 2025-2026 first national record in GBIF, with a hand-checked sample of 60 | run queued, results pending |
| **IA-2** ([IA2-PREREG.md](IA2-PREREG.md)) | prospective: a weekly watch that logs the date it first sees each new pair, then measures how many were real and how many came before official reports | weekly runs start with a baseline |

A hand pilot on six well-known invasive insects is in [pilot/](pilot/PILOT-2026-11-17.md).

## Why

Finding an invasion early is the cheapest time to stop it. Community-science and museum
records now reach GBIF within weeks, but nobody runs an open check across every known
invasive species and every country for arrivals that haven't been reported yet. The
GRIIS Country Compendium (Pagad et al. 2022) names this as a goal. Earlier studies
measured the lag after the fact (González‑Moreno et al. 2025). Alert tools such as GBIF
Alert (LIFE RIPARIAS, Ebbe Nielsen Challenge 2023) notify users about new records for
species and areas they choose. This repository runs the global screen and, more
importantly, **measures how many of its flags survive a hand check**.

## The weekly feed (IA-2)

- Atom: [watch/atom.xml](https://raw.githubusercontent.com/munimtechnologies/invasive-arrivals/main/watch/atom.xml)
- JSON: [watch/feed.json](https://raw.githubusercontent.com/munimtechnologies/invasive-arrivals/main/watch/feed.json)
- Every new pair ever seen, append-only: `watch/first_seen.csv`; weekly reports in
  `watch/weeks/`; run log in `watch/runs.csv`.

Each week, `.github/workflows/watch.yml` asks GBIF which countries hold records of every
target species. A country the watch has never seen for that species, and where GRIIS
doesn't list it, is a new pair. Its records decide its kind: **arrival** (all records
recent, at least one with a photo or specimen), weak, excluded (captive, garden, bad
coordinates), historical (an old record newly digitised) or none. Arrivals also get a
distance band: **front** (another country has records within 300 km), **mid** (within
1,000 km) or **jump**. Every item is a candidate for an expert's check, not a confirmed
arrival.

Agents can use [SKILL.md](SKILL.md) to read the feed or run a watch for their own list.

## How IA-1 works

1. Download every GRIIS country checklist from GBIF (Darwin Core Archives, CC BY 4.0) and
   collect the names flagged invasive, plus every name listed per country.
2. Match each invasive name to a GBIF accepted species.
3. For each species, compare GBIF's per-country record counts for all time with those
   for 2025-2026. A country where *every* record is from 2025-2026, and where GRIIS does
   not list the species, is a raw candidate.
4. Read those records and keep pairs with a recent, present, wild-looking,
   well-georeferenced record. A pair is *strong* if a record has a photo or is a
   specimen.
5. Draw a fixed random sample of 60 strong pairs for hand verification.

## Run it

```
python -m unittest -v test_arrivals test_watch       # offline tests
python arrivals.py --out-dir out                     # IA-1 screen, about 1-2 hours
python watch.py --state-dir mywatch --targets my_species.csv   # your own weekly watch
python watch.py --state-dir watch --targets watch/targets.csv --build-targets  # full GRIIS list
```

Python 3.10+ with the standard library only. The clients keep to about 4-5 requests a
second and identify themselves in their User-Agent.

## IA-1 outputs (in `--out-dir`)

| file | contents |
|---|---|
| `candidates.csv` | one row per candidate (species, country) pair, with strength, first date, data sources and links to GBIF records |
| `verification_sample.csv` | the pre-registered 60-pair sample |
| `target_species.csv` | GRIIS invasive species matched to GBIF, with the countries that flag or list them |
| `griis_checklists.csv` | every GRIIS checklist read, with its country and counts |
| `summary.json` | counts for the pre-registered hypotheses H1-H3, and run diagnostics |

No personal data: observer and identifier names are never stored, and coordinates are
rounded to 0.1 degree.

## Limits

- A candidate is **not** a confirmed arrival. Many will be native-range gaps in GBIF,
  misidentifications, garden or captive records, or arrivals already published but not
  digitised. The verification steps exist to measure exactly that.
- GBIF reflects where people look. Countries with few records produce more false
  "firsts", and real arrivals that nobody photographed are invisible.
- GRIIS checklists differ in age and completeness, so a species missing from a country's
  list may simply not have been added yet.
- A record's event date can be long before it reaches GBIF. That is why IA-2 measures
  lead time from the date the watch first saw a pair.

## Data credits

GBIF.org occurrence data via the GBIF API (each record keeps its own licence, from CC0
to CC BY-NC); GRIIS checklists by the IUCN SSC Invasive Species Specialist Group (ISSG),
CC BY 4.0.
