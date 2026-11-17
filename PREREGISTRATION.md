# Pre-registration: invasive-arrivals screen 1 (IA-1)

Registered 2026-11-17, before any screen output exists. By MV2 of Munim, Inc.; the
code and this text were made with AI agents working in his name. Licence: Apache-2.0
(code), CC BY 4.0 (text and outputs).

## The question

Invasive species do the least harm, and cost the least to remove, when they are found
early. Community science and museum data now reach GBIF within weeks. Is there a
measurable stream of **new national arrivals of known invasive species** hiding in open
data before anyone reports them?

Earlier work measured the lag *after the fact*. González‑Moreno et al. (2025, People and
Nature, doi:10.1002/pan3.10767) compared 687 official European first records with
citizen-science platforms and found the platforms earlier in about 20% of cases. The
LIFE RIPARIAS early-alert tool (Noé et al. 2022) watches GBIF for a fixed list of species
in Belgium. The GRIIS Country Compendium (Pagad et al. 2022) names global automated
alerts for new incursions as a goal for future workflows. We found no open, global,
prospective screen that runs across every GRIIS-flagged invasive species and every
country, and no published estimate of how many of its flags are real new arrivals.
That estimate is what this study adds.

**The "wow" if it works:** an open screen of GBIF finds dozens of arrivals of
known invasive species in new countries in 2025-2026, confirmed as real and not yet in
the literature, and the same code can run every week for any biosecurity agency.

## Definitions (fixed before any output)

- **Target species**: every name flagged `isInvasive` = yes/invasive/true in at least
  one GRIIS country checklist published on GBIF (dataset search "GRIIS", type CHECKLIST,
  title containing "GRIIS" or "Global Register of Introduced and Invasive Species").
  Each name is matched to a GBIF accepted species with the GBIF name matcher (EXACT or
  VARIANT match at confidence 90 or more, or FUZZY at 95 or more). Names above species
  rank are dropped.
- **Listed in country C**: the species' binomial, or any binomial matched to the same
  accepted species, appears in any GRIIS checklist for C. A species flagged invasive
  in C is also listed in C.
- **Raw candidate pair (S, C)**: GBIF holds at least one record of S in C with year
  2025 or 2026, the all-time count of S in C (no filters, undated records included)
  equals the 2025-2026 count, and S is not listed in C. Country codes ZZ and XZ are
  excluded.
- **Qualifying record**: present (not absent); not a living or fossil specimen; has
  coordinates; none of the GBIF issues ZERO_COORDINATE, COORDINATE_INVALID,
  COORDINATE_OUT_OF_RANGE, COUNTRY_COORDINATE_MISMATCH, COUNTRY_MISMATCH,
  PRESUMED_SWAPPED_COORDINATE, PRESUMED_NEGATED_LATITUDE/LONGITUDE,
  COORDINATE_REPROJECTION_FAILED, TAXON_MATCH_HIGHERRANK, TAXON_MATCH_NONE or
  TAXON_MATCH_FUZZY; establishment means and degree of establishment not
  managed, captive, cultivated, released or domesticated; year 2025 or 2026.
- **Strong pair**: a raw candidate pair with at least one qualifying record that has
  media or is a preserved specimen, material sample or material citation.
- **Verification sample**: strong pairs sorted by (GBIF species key, country), then
  `random.Random(20261117).sample(..., 60)`, or all of them if there are fewer.

## Hypotheses (graded on the first complete run, job invasive-arrivals-v1)

- **H1 (scale)**: the number of strong pairs is between 200 and 4,000.
- **H2 (who finds them)**: at least 50% of strong pairs include an iNaturalist
  research-grade record (GBIF dataset 50c9509d-22c7-4a22-a47d-8c48425ef4a7).
- **H3 (what they are)**: Plantae has more strong pairs than Animalia.

## Verification (graded in later runs, on the 60-pair sample only)

Each sampled pair is checked by hand, using only public sources, and assigned **one**
class, taking the first that applies:

1. **native**: S is native to C (POWO for plants, otherwise CABI Compendium, GISD or a
   regional checklist). The screen was wrong to flag it.
2. **already reported**: a publication, official report or national checklist dated
   before the first GBIF record already records S in C.
3. **not wild**: the record's notes or source show a garden, captive, aquarium,
   interception or import record.
4. **doubtful identity or place**: the record is flagged by its own source, has no
   community or expert confirmation, or sits on a border or at sea.
5. **plausible new arrival**: none of the above. This is not a confirmation, only a
   candidate worth an expert's look.

- **V1**: the share of class 5 in the sample is at least 15%.
- **V2**: the share of class 1 (native) is at most 40%.

The classes, the sample and the thresholds are fixed now. Results are reported in full
whichever way they go. A screen that is mostly false alarms is a negative result worth
publishing too: it tells agencies how much expert time an open screen costs.

## What we will not do

- No personal data: observer and identifier names are never stored or published; output
  coordinates are rounded to 0.1 degree.
- No contact with observers. Any note to a national authority or expert about a
  specific candidate is drafted for Sheehan Munim's review first and sent only once a
  person has looked at the evidence.
- GBIF data are cited by dataset. Before any paper, the records used are frozen as a
  GBIF derived dataset with a DOI.
