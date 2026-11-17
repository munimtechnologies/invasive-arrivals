# invasive-arrivals

An open, global screen of [GBIF](https://www.gbif.org) for **candidate first national
records of known invasive species**: places where a species that the Global Register of
Introduced and Invasive Species (GRIIS) flags as invasive somewhere has turned up, in
2025 or 2026, in a country where GBIF has never recorded it before and where no GRIIS
checklist lists it.

By MV2 of Munim, Inc. (mv2@munimtech.com). The code and text were made with AI agents
working in his name. Code: Apache-2.0. Outputs and text: CC BY 4.0. Status: **first run
pre-registered, results pending.**

## Why

Finding an invasion early is the cheapest time to stop it. Community-science and museum
records now reach GBIF within weeks, but nobody runs an open check across every known
invasive species and every country for arrivals that haven't been reported yet. The
GRIIS Country Compendium (Pagad et al. 2022) names this as a goal. Earlier studies
measured the lag after the fact (González‑Moreno et al. 2025) or watched one country
(LIFE RIPARIAS, Belgium). This repository runs the global screen and, more importantly,
measures **how many of its flags survive a hand check**. See
[PREREGISTRATION.md](PREREGISTRATION.md) for the hypotheses and the verification
protocol, fixed before any output existed.

## How it works

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
python -m unittest -v test_arrivals          # offline tests
python arrivals.py --out-dir out             # full screen, about 1-2 hours, ~20k API calls
python arrivals.py --out-dir out --max-species 50   # quick trial
```

Python 3.10+ with the standard library only. The client keeps to about 5 requests a
second and identifies itself in its User-Agent.

## Outputs (in `--out-dir`)

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
  digitised. The verification step exists to measure exactly that.
- GBIF reflects where people look. Countries with few records produce more false
  "firsts", and real arrivals that nobody photographed are invisible.
- GRIIS checklists differ in age and completeness, so a species missing from a country's
  list may simply not have been added yet.

## Data credits

GBIF.org occurrence data via the GBIF API (each record keeps its own licence, from CC0
to CC BY-NC); GRIIS checklists by the IUCN SSC Invasive Species Specialist Group (ISSG),
CC BY 4.0.
