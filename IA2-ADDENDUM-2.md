# IA-2 addendum 2: an automatic look-alike risk label, tested prospectively

Filed 2026-11-17, **before IA-2 has flagged anything**. The baseline run (compute job
ia2-baseline-v1) has not run, there is no watch/ folder in this repository, and weekly
run 1 cannot happen before ISO week 2026-W48 (from Monday 2026-11-23). IA-1 has no output
either. By MV2 of Munim, Inc. (mv2@munimtech.com); made with AI agents working in his
name. Licence: CC BY 4.0. Code (lookalike.py, test_lookalike.py): Apache-2.0.

This addendum changes **nothing** in IA2-PREREG.md or IA2-ADDENDUM-1.md: W1-W4, the
watch's flags, the classes and the class-4 labels stay as registered. It adds one
automatic label, taken at flag time, and one secondary hypothesis about it (W5).

## Why

Across the three hand pilots (pilot/), 24 comparable strong pairs gave 5 plausible
arrivals and 8 doubtful ones. For insects the main failure was a **photo look-alike**:
*Solenopsis invicta* vs *S. geminata*, *Aedes albopictus* vs *Ae. aegypti*, *Aromia
bungii* vs *A. moschata*. The records reached research grade on the observer's
computer-vision suggestion plus one agreement. iNaturalist estimates research-grade
records at about 95-97% correct overall (its 2023-2024 accuracy experiments), and
errors fall mostly on visually similar species. A first national record is where the
prior is lowest, so those few percent should crowd into exactly the flags the watch
raises.

The look-alike alone does not separate real from false flags. The European hornet
(*Vespa crabro*) is by far the most frequent confusion for *Vespa velutina* on
iNaturalist (1,999 identifications in its similar-species tally, read 2026-11-17), and it
is common in Denmark and Poland. Yet both hornet arrivals there were real and were
confirmed officially. What differed was the depth of identification:

| Record (iNaturalist) | Look-alike in country (GBIF) | Observer used computer vision | Others agreeing | Pilot outcome |
|---|---|---|---|---|
| *Ae. albopictus*, Qatar (258016438) | *Ae. aegypti*, 13 records | yes | 1 | doubtful (class 4) |
| *V. velutina*, Poland (403680492) | *V. crabro*, common | yes | 11 | confirmed ~20 days later |
| *P. hysterophorus*, DR Congo (300129994) | *Torilis arvensis*, 15 records (and *Ambrosia artemisiifolia*, 1) | no (a botanist's own ID) | 1 | plausible, unreported |

Under the rule below, the first record would be risk **high** and the other two **low**.
For two of the three pairs a look-alike is recorded in the country, so presence on its
own fires often. The *Parthenium* case also shows that the global tally includes loose
confusions: hedge parsley is a carrot-family plant that looks quite different. These
three were read in hindsight. The hornet record's 11 agreements piled up after it
became news, so this table is a motivating example, not evidence. That is why the label
below is taken in the week a pair is first flagged, and why W5 is tested only
prospectively.

## The label (lookalike.py)

For every `arrival` row in watch/first_seen.csv, lookalike.py writes one row to
watch/lookalikes.csv (append-only, with the date it was taken):

- **lookalike**: from iNaturalist's public similar-species tally for the target
  (`/v1/identifications/similar_species`), take the top **5** species-rank taxa, leaving
  out hybrids, the target itself and any confused fewer than **5** times. Match each to the
  legacy GBIF Backbone and count its GBIF records in the flagged country (same pin as
  watch.py). **yes** if any count is at least 1; **no** if every count is 0; **unknown**
  if a lookup failed and none was found.
- **thin_id**: for each iNaturalist record among the pair's example occurrences (up to 5),
  read the observation. A record is thin when the observer's own first identification used
  computer vision (`vision: true`) and **at most 1** other person agrees
  (`num_identification_agreements`). The pair is **yes** if all its iNaturalist records
  are thin, **no** if any is not, **n/a** if it has none, **unknown** if one could not be
  read.
- **risk**: **high** = lookalike yes and thin_id yes; **low** = lookalike no or thin_id no;
  **unknown** otherwise.

**When:** in the same venue and the same ISO week as the weekly run that first flags the
pair, right after watch.py: `python lookalike.py --state-dir watch --only-week`. A pair
labelled in a later week is written with late = yes.

**Blinding:** the hand checker classes each arrival pair (IA-1 classes plus the
IA2-ADDENDUM-1 labels) from a sheet that leaves out every column of lookalikes.csv.
The source pages the checker must read do show identifications. That is unavoidable,
and it is noted when grading.

## W5 (secondary hypothesis, graded once, with W3 on 2027-06-30)

Population: arrival pairs from weekly runs 1-12 with late = no, risk high or low, and a
hand class. **Prediction:** the share of class 4 with label 4-identity is at least
**twice** as high among high-risk pairs as among low-risk pairs, and strictly higher.
If the low-risk share is 0, W5 passes when the high-risk share is at least 20%.

- **Untestable** if fewer than 8 high-risk or fewer than 8 low-risk pairs are in the
  population. It is then reported with its counts, and nothing is claimed.
- Reported with W5 but not graded: the class-5 share by risk; the 4-identity and class-5
  shares for lookalike alone and for thin_id alone; risk crossed with the distance band
  (front / mid / jump); and a two-sided Fisher exact p-value for the 2x2 table
  (risk x 4-identity).

## What W5 decides

If W5 passes, later versions of the public feed show the risk label on each arrival and
list high-risk pairs after the others, with the grading linked. If W5 fails or is
untestable, the label stays a descriptive column in lookalikes.csv and the feed's order
is not changed. Before grading, the feed's order does not use the label.

## Limits

- The similar-species tally is global and dominated by North American and European
  observers. It can miss local look-alikes, for example in the tropics.
- GBIF presence of a look-alike measures recording, not abundance. A look-alike may be
  common but unrecorded in GBIF (giving no) or recorded once long ago (giving yes).
- thin_id only exists for iNaturalist records. Specimens and other platforms get n/a, and
  so risk unknown when a look-alike is present.
- An agreement is not an expert's agreement, and agreements can still come before the
  watch reads the record. Week-one timing limits this but does not remove it.
- With the IA2-PREREG.md W1 range (2-60 arrivals per run), W5 may well be untestable.
  That will be reported plainly.

## Prior work

iNaturalist's identification-accuracy experiments (blog posts 88501, 89255, 90263) and
studies such as Mesaglio et al. 2025 (Plants, People, Planet, doi:10.1002/ppp3.70005) and
the PLOS ONE 2023 herbarium comparison (doi:10.1371/journal.pone.0295298) measure the
accuracy of research-grade records in bulk. We found no prospective, pre-registered test
of an automatic label that predicts which candidate **first national records of invasive
species** are misidentifications. That test is the new part here.
