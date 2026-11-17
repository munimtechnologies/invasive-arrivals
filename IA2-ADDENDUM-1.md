# IA-2 addendum 1

Filed 2026-11-17, **before IA-2's baseline run** (no file under watch/ exists, and no
IA-1 output exists either). By MV2 of Munim, Inc.; made with AI agents working in his
name. Licence: CC BY 4.0.

This addendum changes **no** hypothesis, threshold, class or flagging rule in
IA2-PREREG.md. W1-W4 are graded exactly as registered. It adds a run-venue note, some
descriptive labels and a checking procedure, all prompted by hand pilots 1 and 2
(pilot/), which used hand-picked species outside the study window.

## 1. Where the watch runs

IA2-PREREG.md names `.github/workflows/watch.yml` as the weekly runner, but that file is
not yet in the repository: the automated publishing route could not add workflow files.
Until it is added, a run may also be made as a sealed compute job that downloads tag
v0.2.0 and runs `watch.py --state-dir watch --targets watch/targets.csv --build-targets
--workers 2 --min-interval 0.25`. These are the same code and arguments, followed by a
commit of watch/. Each run's venue and date will be listed below. A run counts as weekly
run k only if it falls in its own ISO week, as registered. If venues mix, the gaps
are reported as registered.

## 2. Descriptive labels within class 4 (do not change the class)

Every class-4 pair also gets one label:
- **4-identity**: the identification is in doubt. Examples: a validator or expert on the
  source page rejected it, or the only support is a species-level ID that a published
  source says is easily confused with a look-alike present in that country.
- **4-place**: the location is in doubt (border, sea, the observer is asked to confirm and
  does not, or the coordinates disagree with the locality text).
- **4-survey-negative**: an official survey of the site found nothing, or an official
  database lists the record as unreliable.

## 3. Outcome of class-5 pairs (descriptive; W3 unchanged)

Each class-5 pair also gets **later_outcome**, set on 2027-06-30:
**confirmed** (the registered later_confirmed = yes), **surveyed_absent** (an official
source says it looked and did not find the species), or **no_report**. W3 counts only
"confirmed", as registered. The surveyed_absent count is reported next to it.

## 4. Checking procedure

The checker reads each arrival pair's **source record page** (iNaturalist, Artportalen,
Observation.org and others), not only its GBIF copy. Pilot 2 found a quarantine-pest
record that its source's validator had rejected 19 days earlier, which GBIF still served
under the pest's name. Native range is checked against POWO, CABI or the primary
literature even when GRIIS lists the species as invasive in a neighbouring country.

## 5. Secondary descriptive split (no threshold)

Next to W2, we report the class-5 share separately for:
(a) pairs whose strong evidence includes a record expert-validated at the source,
(b) iNaturalist research-grade only,
(c) other.
Pilot 2 suggests (b) carries most of the look-alike errors. This split tests that, but
it is descriptive and does not grade anything.

## Run log

| Run | Date | Venue | Notes |
|---|---|---|---|
| baseline | pending | pending | compute job ia2-baseline-v1 filed 2026-11-17 |
