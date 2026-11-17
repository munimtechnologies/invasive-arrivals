---
name: invasive-arrivals
description: Read or run an open weekly watch of GBIF for the first record of a known invasive species (GRIIS-flagged) in a new country. Use it when a user asks about new invasive species arrivals, early detection of pests or weeds in a country, biosecurity alerts from open biodiversity data, or how to watch GBIF for new national records of a species list.
license: Apache-2.0
---

# invasive-arrivals

An open screen of GBIF for **candidate first national records of known invasive
species**, by MV2 of Munim, Inc. (mv2@munimtech.com); made with AI agents.
Repository: https://github.com/munimtechnologies/invasive-arrivals

## Read the weekly feed (no install)

- Atom feed: https://raw.githubusercontent.com/munimtechnologies/invasive-arrivals/main/watch/atom.xml
- JSON (newest 200 candidates): https://raw.githubusercontent.com/munimtechnologies/invasive-arrivals/main/watch/feed.json
- Full append-only log of every new pair: `watch/first_seen.csv`
- One report per ISO week: `watch/weeks/<YYYY>-W<NN>.md`
- Run log: `watch/runs.csv`

Useful `first_seen.csv` / `feed.json` fields: `species`, `kingdom`, `country` (ISO-2),
`kind` (`arrival` is the one that matters), `first_seen_date` (when the watch first saw
the pair), `first_strong_event_date` (earliest photo or specimen record),
`band` (`front` = known in another country within 300 km, `mid` = within 1,000 km,
`jump` = none within 1,000 km), `countries_within_1000km`, `griis_invasive_in_count`
(how many GRIIS country lists flag it invasive), `example_occurrences`, `gbif_search_url`.

To answer "what new invasive arrivals were seen in country X": fetch `feed.json`, keep
items with `country == "X"`, and list species, dates and GBIF links.

## How to present results

- Every item is a **candidate, not a confirmed arrival**. Say so. Many will turn out to
  be misidentifications, garden or captive records, or arrivals already published.
- Point the user to the national plant-health, biosecurity or environment authority for
  confirmation. Do not tell anyone to contact the observers.
- The pre-registered hit-rate study is in `IA2-PREREG.md` (and `PREREGISTRATION.md`
  for the retrospective screen). Quote measured rates only once results are published.

## Run your own watch (Python 3.10+, standard library only)

```
git clone https://github.com/munimtechnologies/invasive-arrivals
cd invasive-arrivals
python -m unittest test_arrivals test_watch
python watch.py --state-dir mywatch --targets my_species.csv
```

`my_species.csv` needs a `species_key` column (GBIF backbone keys; look them up with
`https://api.gbif.org/v1/species/match?name=<name>`) and may add `species`, `kingdom`,
and `listed_in` (ISO-2 codes separated by `;`, countries where the species is already
known and should not be flagged). The first run is a baseline and flags nothing; run it
weekly after that. Use `--build-targets` with a missing targets file to build the full
GRIIS list (about 1-2 hours of polite API calls). Keep the default rate limit.

Licences: code Apache-2.0; feed and text CC BY 4.0; GBIF records keep their own
licences (cite GBIF.org and the datasets).
