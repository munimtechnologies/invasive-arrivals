# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Offline tests for grade_ia1.py (no network). Made with AI agents."""

import csv
import json
import os
import tempfile
import unittest

import grade_ia1 as g
from arrivals import draw_sample


def cand(key, cc, kingdom="Plantae", strength="strong", inat=True):
    return {"species_key": str(key), "species": f"Sp {key}", "kingdom": kingdom,
            "class": "Magnoliopsida", "country": cc, "strength": strength,
            "has_inaturalist": "True" if inat else "False",
            "first_qualifying_date": "2025-06-01", "example_occurrences": "",
            "gbif_search_url": ""}


def make_candidates(n_plant, n_animal, n_inat, n_weak=0):
    rows = []
    for k in range(n_plant + n_animal):
        kingdom = "Plantae" if k < n_plant else "Animalia"
        rows.append(cand(1000 + k, "DE" if k % 2 else "PL", kingdom, inat=k < n_inat))
    for k in range(n_weak):
        rows.append(cand(9000 + k, "FR", strength="weak", inat=False))
    return rows


def summary_for(rows, **over):
    strong = [r for r in rows if r["strength"] == "strong"]
    kingdoms = {}
    for r in strong:
        kingdoms[r["kingdom"]] = kingdoms.get(r["kingdom"], 0) + 1
    inat = sum(1 for r in strong if r["has_inaturalist"] == "True")
    s = {"started": "x", "finished": "y", "species": {"matched": 100},
         "facets": {"species_screened": 100, "failures": 0},
         "results": {"H1_strong_pairs": len(strong),
                     "H2_share_strong_with_inaturalist": round(inat / len(strong), 4),
                     "H3_strong_by_kingdom": kingdoms}}
    s.update(over)
    return s


def sample_rows(rows):
    strong = [r for r in rows if r["strength"] == "strong"]
    return [dict(r, sample_index=str(i)) for i, r in enumerate(draw_sample(strong))]


class ScreenGrading(unittest.TestCase):
    def test_all_pass(self):
        rows = make_candidates(150, 100, 200)
        out = g.grade_screen(summary_for(rows), rows)
        self.assertEqual(out["H1"]["verdict"], "PASS")
        self.assertEqual(out["H2"]["verdict"], "PASS")
        self.assertEqual(out["H3"]["verdict"], "PASS")
        self.assertEqual(out["consistency_problems"], [])

    def test_h1_bounds_inclusive(self):
        rows = make_candidates(120, 80, 0)          # exactly 200
        self.assertEqual(g.grade_screen(summary_for(rows), rows)["H1"]["verdict"], "PASS")
        rows = make_candidates(120, 79, 0)          # 199
        self.assertEqual(g.grade_screen(summary_for(rows), rows)["H1"]["verdict"], "FAIL")

    def test_h2_exact_half_passes(self):
        rows = make_candidates(150, 100, 125)       # 125/250 = 50%
        self.assertEqual(g.grade_screen(summary_for(rows), rows)["H2"]["verdict"], "PASS")
        rows = make_candidates(150, 100, 124)
        self.assertEqual(g.grade_screen(summary_for(rows), rows)["H2"]["verdict"], "FAIL")

    def test_h3_tie_fails(self):
        rows = make_candidates(125, 125, 0)
        self.assertEqual(g.grade_screen(summary_for(rows), rows)["H3"]["verdict"], "FAIL")

    def test_weak_rows_ignored(self):
        rows = make_candidates(150, 100, 200, n_weak=30)
        out = g.grade_screen(summary_for(rows), rows)
        self.assertEqual(out["strong_pairs"], 250)
        self.assertEqual(out["consistency_problems"], [])

    def test_summary_mismatch_reported(self):
        rows = make_candidates(150, 100, 200)
        s = summary_for(rows)
        s["results"]["H1_strong_pairs"] = 251
        s["results"]["H3_strong_by_kingdom"] = {"Plantae": 151, "Animalia": 100}
        probs = g.grade_screen(s, rows)["consistency_problems"]
        self.assertEqual(len(probs), 2)


class Completeness(unittest.TestCase):
    def test_complete(self):
        rows = make_candidates(10, 10, 5)
        self.assertTrue(g.completeness(summary_for(rows))["complete"])

    def test_error_and_cap_and_failures(self):
        rows = make_candidates(10, 10, 5)
        self.assertFalse(g.completeness(summary_for(rows, error="probe failed"))["complete"])
        capped = summary_for(rows, facets={"species_screened": 50, "failures": 0})
        self.assertFalse(g.completeness(capped)["complete"])
        self.assertTrue(g.completeness(summary_for(rows, facets={"species_screened": 100,
                                                                 "failures": 2}))["complete"])
        self.assertFalse(g.completeness(summary_for(rows, facets={"species_screened": 100,
                                                                  "failures": 3}))["complete"])


class SampleCheck(unittest.TestCase):
    def test_reproduces_regardless_of_csv_order(self):
        rows = make_candidates(150, 100, 200, n_weak=5)
        smp = sample_rows(rows)
        self.assertEqual(len(smp), 60)
        out = g.check_sample(list(reversed(rows)), smp)
        self.assertTrue(out["reproduces"])

    def test_detects_tampered_sample(self):
        rows = make_candidates(150, 100, 200)
        smp = sample_rows(rows)
        smp[3] = dict(smp[3], country="XX")
        self.assertFalse(g.check_sample(rows, smp)["reproduces"])


def sheet(smp, classes, extra=None):
    """A hand-verification sheet; extra maps sample_index (int) -> extra columns."""
    extra = extra or {}
    out = []
    for r, c in zip(smp, classes):
        row = {"sample_index": r["sample_index"], "species_key": r["species_key"],
               "country": r["country"], "class": "" if c is None else str(c)}
        row.update(extra.get(int(r["sample_index"]), {}))
        out.append(row)
    return out


class Verification(unittest.TestCase):
    def setUp(self):
        rows = make_candidates(150, 100, 200)
        self.smp = sample_rows(rows)        # 60 pairs

    def test_final_pass_fail(self):
        # 9 class-5 = 15% (V1 pass); 24 class-1 = 40% (V2 pass)
        classes = [5] * 9 + [1] * 24 + [2] * 27
        v = g.grade_verification(self.smp, sheet(self.smp, classes))
        self.assertTrue(v["final"])
        self.assertEqual((v["V1"]["verdict"], v["V2"]["verdict"]), ("PASS", "PASS"))
        classes = [5] * 8 + [1] * 25 + [2] * 27
        v = g.grade_verification(self.smp, sheet(self.smp, classes))
        self.assertEqual((v["V1"]["verdict"], v["V2"]["verdict"]), ("FAIL", "FAIL"))

    def test_early_verdicts(self):
        # 20 classified: 9 plausible already decides V1; V2 still open
        classes = [5] * 9 + [2] * 11 + [None] * 40
        v = g.grade_verification(self.smp, sheet(self.smp, classes))
        self.assertFalse(v["final"])
        self.assertEqual(v["classified"], 20)
        self.assertEqual(v["V1"]["verdict"], "PASS")
        self.assertEqual(v["V2"]["verdict"], "OPEN")
        # 55 classified, 3 plausible: even 5 more cannot reach 9 -> V1 FAIL
        classes = [5] * 3 + [2] * 52 + [None] * 5
        v = g.grade_verification(self.smp, sheet(self.smp, classes))
        self.assertEqual(v["V1"]["verdict"], "FAIL")
        self.assertEqual(v["V2"]["verdict"], "PASS")

    def test_sheet_problems(self):
        rows = sheet(self.smp, [2] * 60)
        rows[0]["class"] = "6"
        rows[1]["country"] = "ZZ"
        rows.append(dict(rows[2]))
        v = g.grade_verification(self.smp, rows)
        self.assertFalse(v["final"])
        self.assertEqual(len(v["problems"]), 3)

    def test_addendum1_descriptives(self):
        extra = {0: {"later_confirmed": "yes", "first_strong_event_date": "2025-09-01",
                     "first_public_report_date": "2025-09-13"},
                 1: {"later_confirmed": "no", "first_strong_event_date": "2025-09-01",
                     "first_public_report_date": "none found"},
                 2: {"first_strong_event_date": "2025-05-10",
                     "first_public_report_date": "2025-03-01", "changed_by_addendum1": "yes"}}
        v = g.grade_verification(self.smp, sheet(self.smp, [5, 5, 2] + [3] * 57, extra))
        a = v["addendum1"]
        self.assertEqual(a["class5_later_confirmed"], "1/2")
        self.assertEqual(a["event_to_report_days_n"], 2)
        self.assertEqual(a["event_to_report_days_range"], [-70, 12])
        self.assertEqual(a["pairs_changed_by_first_strong_record_rule"], 1)


class EndToEnd(unittest.TestCase):
    def test_cli_on_files(self):
        rows = make_candidates(150, 100, 200, n_weak=4)
        smp = sample_rows(rows)
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "summary.json"), "w", encoding="utf-8") as fh:
                json.dump(summary_for(rows), fh)
            for name, data in (("candidates.csv", rows), ("verification_sample.csv", smp)):
                with open(os.path.join(d, name), "w", newline="", encoding="utf-8") as fh:
                    w = csv.DictWriter(fh, fieldnames=list(data[0].keys()))
                    w.writeheader()
                    w.writerows(data)
            sheet_path = os.path.join(d, "verification.csv")
            self.assertEqual(g.main(["--run-dir", d, "--make-sheet", sheet_path]), 0)
            sheet_rows = g.read_csv(sheet_path)
            self.assertEqual(len(sheet_rows), 60)
            self.assertIn("taxon_class", sheet_rows[0])
            self.assertEqual(sheet_rows[0]["class"], "")
            out_json = os.path.join(d, "grading.json")
            self.assertEqual(g.main(["--run-dir", d, "--verification", sheet_path,
                                     "--json-out", out_json]), 0)
            with open(out_json, encoding="utf-8") as fh:
                result = json.load(fh)
            self.assertEqual(result["verification"]["classified"], 0)
            self.assertTrue(result["sample_check"]["reproduces"])


if __name__ == "__main__":
    unittest.main()
