# Pre-registration addendum 1 (IA-1)

Registered 2026-11-17, after the hand pilot in pilot/PILOT-2026-11-17.md and **before
any output of the IA-1 screen (job invasive-arrivals-v1) exists**. By MV2 of Munim,
Inc.; made with AI agents working in his name. Licence: CC BY 4.0.

Nothing in PREREGISTRATION.md changes: the definitions, the 60-pair sample, H1-H3 and
V1-V2 stay exactly as registered. This addendum only adds descriptive measures, and the
next study.

## 0. One clarification, found in the pilot

Class 2 ("already reported") says a report must be dated "before the first GBIF record".
In the pilot, the Hungarian spotted-lanternfly pair had a no-photo record dated before the
official announcement and photo records dated after it. To settle such cases, **"first
GBIF record" means the earliest strong record of the pair** (the records that make it a
strong pair). This is fixed now, before any IA-1 output exists. We will also report how
many sampled pairs this choice changed.

## A. Extra labels in the hand verification (descriptive, no threshold)

For every sampled pair the checker also records:

- **first_strong_event_date**: the earliest eventDate among the pair's strong records.
- **first_public_report**: the date and URL of the earliest official report, publication
  or national-checklist entry for the species in the country that we can find, at any date
  (before or after the GBIF record), or "none found".
- **later_confirmed**: for class-5 (plausible) pairs, whether an official report dated after
  first_strong_event_date exists (yes / no).
- **event_to_report_days** = first_public_report minus first_strong_event_date, when both exist.

We will report:
- the share of class-5 pairs that were later confirmed;
- the median and range of event_to_report_days.

These are upper bounds on any real lead, because a record usually reaches GBIF some time
after its event date (see the pilot, point 2).

## B. The next study: IA-2, a prospective weekly watch

IA-1 is retrospective. IA-2 runs the same rule every week from its start date. It logs the
**first week each strong pair appears** and keeps that log public and append-only, so lead
times are measured from the date the screen actually saw the record. Its hypotheses will be
registered in their own file before its first run. The code is a separate mode and does not
change IA-1's code path.
