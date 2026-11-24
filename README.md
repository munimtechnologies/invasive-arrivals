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
| **IA-1** ([PREREGISTRATION.md](PREREGISTRATION.md), [ADDENDUM-1.md](ADDENDUM-1.md), [IA1-GRADING-RULES.md](IA1-GRADING-RULES.md)) | retrospective: every 2025-2026 first national record in GBIF, with a hand-checked sample of 60 | run queued, results pending; the grader (`grade_ia1.py`) is published in advance |
| **IA-2** ([IA2-PREREG.md](IA2-PREREG.md), [IA2-ADDENDUM-1.md](IA2-ADDENDUM-1.md), [IA2-ADDENDUM-2.md](IA2-ADDENDUM-2.md)) | prospective: a weekly watch that logs the date it first sees each new pair, then measures how many were real and how many came before official reports | baseline run queued; weekly run 1 is ISO week 2026-W48 at the earliest |

Three hand pilots (hand-picked species, not the registered sample) are in
[pilot/](pilot/): six invasive insects, six more insects plus a crayfish and a mosquito,
and six invasive plants. Across 24 comparable strong pairs: 3 native, 8 already
reported, 8 doubtful and 5 plausible new arrivals. Two of the plausible ones (the Asian
hornet in Denmark and Poland) were confirmed officially 12 and about 20 days after the
record date.

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
  `watch/weeks/`; run log in `watch/runs.csv`; look-alike labels in `watch/lookalikes.csv`.

These files appear after the baseline run. Each week, watch.py asks GBIF which countries
hold records of every target species. It runs as a GitHub Actions workflow once that file
is added, and until then as a sealed compute job (see IA2-ADDENDUM-1.md). A country the
watch has never seen for that species, and where GRIIS doesn't list it, is a new pair.
Its records decide its kind: **arrival** (all records recent, at least one with a photo or
specimen), weak, excluded (captive, garden, bad coordinates), historical (an old record
newly digitised) or none. Arrivals also get a distance band: **front** (another country
has records within 300 km), **mid** (within 1,000 km) or **jump**. Every item is a
candidate for an expert's check, not a confirmed arrival.

### Look-alike risk (IA2-ADDENDUM-2)

The commonest false flag in the pilots was a photo look-alike: a mosquito, ant or beetle
that the observer's photo app suggested, with one other person agreeing. In the same week
a pair is flagged, `lookalike.py` checks two things. First, whether a species that
iNaturalist users often confuse with the target already has GBIF records in that
country. Second, whether every iNaturalist record behind the flag is "thin": the observer
used the computer-vision suggestion and at most one other person agreed. Both together
give **risk = high**. Whether high-risk flags really are misidentifications more often is
pre-registered as hypothesis W5. Until it is graded, the label is only a column and does
not change the feed.

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
6. Grade it with `grade_ia1.py`, written and tested before any output existed
   ([IA1-GRADING-RULES.md](IA1-GRADING-RULES.md)). It reads H1-H3 off the output,
   cross-checks summary.json against candidates.csv, re-draws the 60-pair sample to show
   it reproduces, and grades V1-V2 from the hand-verification sheet.

## Run it

```
python -m unittest -v test_arrivals test_watch test_lookalike test_grade_ia1   # offline tests
python arrivals.py --out-dir out                     # IA-1 screen, about 1-2 hours
python grade_ia1.py --run-dir out                    # grade H1-H3, check the sample
python grade_ia1.py --run-dir out --make-sheet verification.csv   # blank hand-check sheet
python grade_ia1.py --run-dir out --verification verification.csv --json-out grading.json
python watch.py --state-dir mywatch --targets my_species.csv   # your own weekly watch
python watch.py --state-dir watch --targets watch/targets.csv --build-targets  # full GRIIS list
python lookalike.py --state-dir watch --only-week    # look-alike labels for this week's arrivals
```

Python 3.10+ with the standard library only. The GBIF clients keep to about 4-5 requests
a second, lookalike.py keeps to about one iNaturalist request a second, and all of them
identify themselves in their User-Agent.

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
  list may simply not have been added yet. For plants, the pilots found national legal
  lists in the local language that never reached GBIF or GRIIS.
- A record's event date can be long before it reaches GBIF. That is why IA-2 measures
  lead time from the date the watch first saw a pair.

## Data credits

GBIF.org occurrence data via the GBIF API (each record keeps its own licence, from CC0
to CC BY-NC); GRIIS checklists by the IUCN SSC Invasive Species Specialist Group (ISSG),
CC BY 4.0. Look-alike tallies and identification counts from the public iNaturalist API
(api.inaturalist.org); only taxon names, counts and observation numbers are stored.
