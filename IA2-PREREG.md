# Pre-registration: invasive-arrivals watch (IA-2)

Registered 2026-11-17, **before the watch's first run** (no IA-2 output exists, and no
IA-1 output exists either). By MV2 of Munim, Inc.; the code and this text were made with
AI agents working in his name. Licence: Apache-2.0 (code), CC BY 4.0 (text and outputs).

## The question

IA-1 asks, after the fact, how many 2025-2026 "first national records" of known invasive
species in GBIF are real. IA-2 asks the harder, prospective question: **if an open screen
watches GBIF every week, does it see real arrivals of invasive species in new countries
before any official or published report, and how often?**

Prior art (checked 2026-11-17): GBIF Alert (LIFE RIPARIAS, Ebbe Nielsen Challenge winner
2023) emails users about new GBIF records for species lists and areas *they* choose;
New Zealand's Smart Weed Alert Tool and the Atlas of Living Australia alerts do the same
nationally. González‑Moreno et al. (2025) measured citizen-science lead times on 687
European first records, after the fact. The GRIIS Country Compendium (Pagad et al. 2022)
names automated alerts for new incursions as a goal. We found no open watch that runs
over every GRIIS-flagged invasive species and every country, logs the date it first
saw each new pair, and publishes a pre-registered estimate of how many of its flags are
real and how much earlier than official reports they came.

**The "wow" if it works:** a free weekly feed, built only on open data, that names
invasive species in new countries before the authorities announce them, with a
measured hit rate any biosecurity agency can trust or reject.

## Definitions (fixed now)

- **Code**: `watch.py` at the commit that adds this file. Run weekly by
  `.github/workflows/watch.yml` (Mondays, 05:17 UTC) with Python 3.12.
- **Taxonomy**: every occurrence query is pinned to the legacy GBIF Backbone
  (checklistKey d7dddbf4-2cf0-4f39-9b2a-bb099caae36c). GBIF.org switched to the
  Catalogue of Life Extended Release in 2026 and the Backbone is frozen, so species keys
  stay stable for the whole study. (Checked 2026-11-17: pinned and unpinned queries give
  identical counts.)
- **Target species**: the IA-1 definition (PREREGISTRATION.md), built once by
  `--build-targets` into `watch/targets.csv` and then kept fixed for the whole study.
- **Baseline**: the first successful run. It records every (species, country) with any
  GBIF record and flags nothing.
- **Weekly run k** (k = 1, 2, ...): the k-th successful run after the baseline, in
  separate ISO weeks. A new pair is a country with a GBIF record of the species that no
  earlier run has seen, that no GRIIS checklist lists the species for, and is not ZZ/XZ.
- **Arrival pair**: a new pair whose records all date from the run's calendar year or
  the year before, with at least one qualifying record that has media or is a specimen
  or sample (the IA-1 "qualifying" and "strong" rules, with that rolling year window).
- **first_seen_date**: the run date on which the watch first logged the pair
  (`watch/first_seen.csv`, append-only).
- **Band**: "front" if GBIF holds records of the species in another country within
  300 km of the pair's earliest checkable record; "mid" if only within 1,000 km;
  "jump" if none within 1,000 km.

## Study window

Weekly runs 1 to 12. If a week is missed, the window is the first 12 successful weekly
runs, and the gaps are reported.

## Verification

All arrival pairs from runs 1-12 are checked by hand, or, if there are more than 60, a
random 60: pairs sorted by (species_key, country), then
`random.Random(20261118).sample(..., 60)`. Each gets one class, the first that applies,
exactly as in IA-1, except that class 2 compares with the watch date:

1. **native**: the species is native to the country.
2. **already reported**: a publication, official report or national checklist dated
   **on or before first_seen_date** records the species in the country.
3. **not wild**: garden, captive, aquarium, interception or import record.
4. **doubtful identity or place**: flagged by its own source, no community or expert
   confirmation, or on a border or at sea.
5. **plausible new arrival**: none of the above.

For class-5 pairs, the checker also records **later_confirmed** (an official report or
publication dated after first_seen_date, yes/no) and **lead_days** = that report's date
minus first_seen_date. Sources as in IA-1 and ADDENDUM-1. Observers are never contacted.

## Hypotheses

- **W1 (flow)**: the median number of arrival pairs per weekly run, over runs 1-12, is
  between 2 and 60.
- **W2 (precision)**: at least 15% of verified arrival pairs are class 5.
- **W3 (lead, the "wow")**: at least 3 verified class-5 pairs are later confirmed by an
  official report or publication dated after their first_seen_date. Checked on
  2027-06-30, for confirmations dated up to that day.
- **W4 (front vs jump)**: the class-5 share is higher among "front" pairs than among
  "jump" pairs. Tested only if each group has at least 10 verified pairs, otherwise
  reported as not testable. We also report a two-sided Fisher exact p-value, but the
  grade is the direction.

Descriptive, no threshold: the share of new pairs by kind (arrival, weak, excluded,
historical, none); arrivals by kingdom and country; the median lead_days.

## What we will not do

- Change the code's flagging rules, the target list or the classes during runs 1-12.
  Bug fixes that change what is flagged are logged in this file with a date, and the
  affected weeks are reported both ways.
- Store personal data: observer names are never read into outputs, and coordinates are
  rounded to 0.1 degree.
- Contact observers. A note to an authority about a specific candidate is drafted for
  Sheehan Munim's review first and sent only after a person has looked at the evidence.
