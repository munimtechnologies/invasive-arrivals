# IA-1 grading rules (grade_ia1.py)

Registered 2026-11-19, **before the IA-1 screen (job invasive-arrivals-v1) has produced
any output**. By MV2 of Munim, Inc.; the code and text were made with AI agents working
in his name. Licence: CC BY 4.0 (text), Apache-2.0 (code).

Nothing in PREREGISTRATION.md or ADDENDUM-1.md changes. This file only fixes, in code
and in advance, how the registered hypotheses are read off the screen's output, so the
grading cannot drift once the numbers are known. `grade_ia1.py` applies these rules and
`test_grade_ia1.py` tests them on made-up data.

## 1. What counts as "the first complete run"

PREREGISTRATION.md grades H1-H3 "on the first complete run". A run is complete when its
`summary.json`:

- has no `error` and has a `finished` time;
- screened every matched species (no `--max-species` cap);
- lost at most 2% of species to facet failures (`facets.failures`).

If the first run is not complete, its numbers are published as provisional and the
registered grading moves to the next complete run of the same code (a new job version).
We will say so in the grading file, with the reason.

## 2. H1-H3

Read from `summary.json` and re-derived from `candidates.csv` (rows with
`strength = strong`). If the two disagree, both are published and the grading stops
until the cause is found.

- **H1** passes if 200 <= strong pairs <= 4,000 (both ends included).
- **H2** passes if (strong pairs with an iNaturalist research-grade record) x 100 >= 50 x
  (strong pairs), computed in whole numbers, so exactly 50% passes.
- **H3** passes if Plantae strong pairs > Animalia strong pairs. A tie fails.

## 3. The verification sample

The grader re-draws the sample from `candidates.csv` with the registered rule (sort by
species key and country, then `random.Random(20261117).sample(..., 60)`) and checks that
it matches `verification_sample.csv` pair for pair. Anyone can repeat this check.

## 4. V1-V2 and the hand-verification sheet

`python grade_ia1.py --run-dir out --make-sheet results/ia-1/verification.csv` writes one
row per sampled pair. The checker fills in `class` (1-5, the first class that applies, as
registered), the source URL for that class, and the ADDENDUM-1 labels
(`first_strong_event_date`, `first_public_report_date`, `first_public_report_url`,
`later_confirmed`, and `changed_by_addendum1` when the earliest-strong-record rule changed
the class). The sheet is published as it fills, and every row is final once written.

- **V1** passes if (class 5) x 100 >= 15 x 60, that is at least 9 of 60.
- **V2** passes if (class 1) x 100 <= 40 x 60, that is at most 24 of 60.

While the sheet is partly filled, a verdict is reported early only when the remaining
pairs can no longer change it. Otherwise it is "OPEN". The final grading needs all
sampled pairs classified and no sheet problems (wrong pair, duplicate row, class not 1-5).
If the sample has fewer than 60 pairs, the same percentages apply to its real size.

## 5. Reported in full, whichever way it goes

The grading file (`results/ia-1/GRADING.md` plus `grading.json`) states every verdict,
including failures, together with the ADDENDUM-1 descriptives: the share of class-5 pairs
later confirmed, and the median and range of event-to-report days.
