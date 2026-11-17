# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Offline tests for lookalike.py (IA-2 addendum 2). No network: a fake client
returns shapes copied from real GBIF and iNaturalist responses read 2026-11-17."""

import csv
import datetime
import os
import tempfile
import unittest

import arrivals as A
import lookalike as L

TODAY = datetime.date(2026, 11, 23)  # ISO week 2026-W48


def ident(id_, own, vision, taxon_id, category="supporting"):
    return {"id": id_, "own_observation": own, "vision": vision, "current": True,
            "category": category, "taxon": {"id": taxon_id}, "user": {"id": 1 if own else id_}}


# Aedes albopictus, Qatar (iNaturalist 258016438): observer's computer-vision ID + 1 agreement.
OBS_QATAR = {"id": 258016438, "user": {"id": 1}, "taxon": {"id": 62984},
             "num_identification_agreements": 1, "num_identification_disagreements": 0,
             "identifications": [ident(586056632, False, False, 62984),
                                 ident(582063801, True, True, 62984, "improving")]}
# Vespa velutina, Poland (iNaturalist 403680492): observer used vision, 11 agreements.
OBS_HORNET = {"id": 403680492, "user": {"id": 1}, "taxon": {"id": 119019},
              "num_identification_agreements": 11, "num_identification_disagreements": 0,
              "identifications": [ident(896412074, True, True, 119019, "improving"),
                                  ident(896718631, False, False, 119019)]}
# Parthenium hysterophorus, DR Congo (iNaturalist 300129994): botanist's own ID, no vision.
OBS_DRC = {"id": 300129994, "user": {"id": 1}, "taxon": {"id": 126424},
           "num_identification_agreements": 1, "num_identification_disagreements": 0,
           "identifications": [ident(688753947, False, False, 126424),
                               ident(669249457, True, False, 126424, "improving")]}


def sim(name, count, rank="species"):
    return {"count": count, "taxon": {"name": name, "rank": rank}}


class FakeClient:
    def __init__(self):
        self.taxa = {"Aedes albopictus": 62984, "Vespa velutina": 119019}
        self.sims = {62984: {"results": [sim("Aedes aegypti", 295), sim("Aedes japonicus", 77),
                                         sim("Culex pipiens", 3)]},
                     119019: {"results": [sim("Vespa crabro", 1999)]}}
        self.keys = {"Aedes aegypti": "1651891", "Aedes japonicus": "1652151",
                     "Vespa crabro": "1311477"}
        self.counts = {("1651891", "QA"): 13, ("1652151", "QA"): 0, ("1311477", "PL"): 900}
        self.occs = {"5062942631": {"datasetKey": A.INAT_DATASET,
                                    "references": "https://www.inaturalist.org/observations/258016438"},
                     "6500000001": {"datasetKey": A.INAT_DATASET, "catalogNumber": "403680492"}}
        self.obs = {"258016438": OBS_QATAR, "403680492": OBS_HORNET}
        self.obs_calls = 0

    def taxon_id(self, name):
        return self.taxa.get(name)

    def similar(self, tid):
        return self.sims.get(tid)

    def gbif_key(self, name, kingdom):
        return self.keys.get(name)

    def count_in(self, key, country):
        return self.counts.get((key, country))

    def occurrence(self, key):
        return self.occs.get(key)

    def observations(self, ids):
        self.obs_calls += 1
        return {i: self.obs[i] for i in ids if i in self.obs}


FS_FIELDS = ["week", "first_seen_date", "species_key", "species", "kingdom", "country",
             "kind", "example_occurrences"]


def fs_row(key, species, country, kind, occs, week="2026-W48"):
    return {"week": week, "first_seen_date": "2026-11-23", "species_key": key,
            "species": species, "kingdom": "Animalia", "country": country, "kind": kind,
            "example_occurrences": ";".join(f"https://www.gbif.org/occurrence/{o}" for o in occs)}


class PureHelpers(unittest.TestCase):
    def test_inat_taxon_id(self):
        resp = {"results": [{"id": 5, "name": "Aedes", "rank": "genus"},
                            {"id": 7, "name": "Aedes albopictus", "rank": "species",
                             "is_active": False},
                            {"id": 62984, "name": "Aedes albopictus", "rank": "species",
                             "is_active": True}]}
        self.assertEqual(L.inat_taxon_id(resp, "Aedes albopictus"), 62984)
        self.assertIsNone(L.inat_taxon_id(resp, "Aedes aegypti"))
        self.assertIsNone(L.inat_taxon_id(None, "Aedes albopictus"))

    def test_similar_species_filters_and_ranks(self):
        resp = {"results": [sim("Solenopsis invicta × richteri", 455, "hybrid"),
                            sim("Solenopsis xyloni", 268), sim("Solenopsis geminata", 174),
                            sim("Solenopsis invicta", 50), sim("Pheidole", 90, "genus"),
                            sim("Tetramorium bicarinatum", 110), sim("Rare species", 2)]}
        got = L.similar_species(resp, "Solenopsis invicta", k=2)
        self.assertEqual(got, [("Solenopsis xyloni", 268), ("Solenopsis geminata", 174)])
        all_ = L.similar_species(resp, "Solenopsis invicta", k=10)
        self.assertEqual([n for n, _ in all_],
                         ["Solenopsis xyloni", "Solenopsis geminata", "Tetramorium bicarinatum"])

    def test_inat_obs_id(self):
        self.assertEqual(L.inat_obs_id({"datasetKey": A.INAT_DATASET,
                                        "references": "https://www.inaturalist.org/observations/42"}),
                         "42")
        self.assertEqual(L.inat_obs_id({"datasetKey": A.INAT_DATASET, "catalogNumber": "77"}), "77")
        self.assertIsNone(L.inat_obs_id({"datasetKey": "other", "catalogNumber": "77"}))
        self.assertIsNone(L.inat_obs_id(None))

    def test_obs_support_real_cases(self):
        self.assertEqual(L.obs_support(OBS_QATAR), (True, 1, 0, True))
        self.assertEqual(L.obs_support(OBS_HORNET), (True, 11, 0, False))
        self.assertEqual(L.obs_support(OBS_DRC), (False, 1, 0, False))

    def test_obs_support_without_own_flag_uses_user_id(self):
        obs = {"user": {"id": 9}, "num_identification_agreements": 0,
               "identifications": [{"id": 3, "vision": True, "user": {"id": 9}}]}
        self.assertEqual(L.obs_support(obs), (True, 0, 0, True))
        self.assertEqual(L.obs_support({"identifications": []})[0], None)
        self.assertFalse(L.obs_support({"identifications": []})[3])

    def test_pair_thin_and_risk(self):
        thin, solid = (True, 1, 0, True), (True, 11, 0, False)
        self.assertEqual(L.pair_thin([], 0), "n/a")
        self.assertEqual(L.pair_thin([thin], 2), "unknown")
        self.assertEqual(L.pair_thin([thin, thin], 2), "yes")
        self.assertEqual(L.pair_thin([thin, solid], 2), "no")
        self.assertEqual(L.risk("yes", "yes"), "high")
        self.assertEqual(L.risk("no", "yes"), "low")
        self.assertEqual(L.risk("yes", "no"), "low")
        self.assertEqual(L.risk("yes", "n/a"), "unknown")
        self.assertEqual(L.risk("unknown", "yes"), "unknown")

    def test_occurrence_keys(self):
        row = {"example_occurrences": ";".join(
            f"https://www.gbif.org/occurrence/{i}" for i in range(1, 8))}
        self.assertEqual(L.occurrence_keys(row), ["1", "2", "3", "4", "5"])
        self.assertEqual(L.occurrence_keys({}), [])


class Labelling(unittest.TestCase):
    def test_label_row_high_and_low(self):
        c = FakeClient()
        q = L.label_row(c, fs_row("1651430", "Aedes albopictus", "QA", "arrival",
                                  ["5062942631"]), TODAY, "2026-W48")
        self.assertEqual(q["lookalike"], "yes")
        self.assertEqual(q["lookalikes_present"], "Aedes aegypti (13 GBIF records)")
        self.assertEqual(q["similar_checked"], "Aedes aegypti (295); Aedes japonicus (77)")
        self.assertEqual(q["thin_id"], "yes")
        self.assertEqual(q["risk"], "high")
        self.assertEqual(q["late"], "no")
        self.assertEqual(q["inat_observations"], "258016438")
        h = L.label_row(c, fs_row("1311742", "Vespa velutina", "PL", "arrival",
                                  ["6500000001"], week="2026-W47"), TODAY, "2026-W48")
        self.assertEqual((h["lookalike"], h["thin_id"], h["risk"]), ("yes", "no", "low"))
        self.assertEqual(h["late"], "yes")
        self.assertEqual(h["agreements"], "11")

    def test_label_row_unknowns(self):
        c = FakeClient()
        # No iNaturalist taxon, and an occurrence GBIF can't return.
        r = L.label_row(c, fs_row("9", "Unknown plant", "CD", "arrival", ["404"]),
                        TODAY, "2026-W48")
        self.assertEqual((r["lookalike"], r["thin_id"], r["risk"]), ("unknown", "unknown", "unknown"))
        # A failed GBIF count with nothing found elsewhere -> unknown, not "no".
        c.counts.pop(("1652151", "QA"))
        c.counts[("1651891", "QA")] = 0
        r = L.label_row(c, fs_row("1651430", "Aedes albopictus", "QA", "arrival",
                                  ["5062942631"]), TODAY, "2026-W48")
        self.assertEqual(r["lookalike"], "unknown")
        self.assertEqual(r["risk"], "unknown")
        # All counts zero -> no look-alike -> low risk even with a thin ID.
        c.counts[("1652151", "QA")] = 0
        r = L.label_row(c, fs_row("1651430", "Aedes albopictus", "QA", "arrival",
                                  ["5062942631"]), TODAY, "2026-W48")
        self.assertEqual((r["lookalike"], r["thin_id"], r["risk"]), ("no", "yes", "low"))

    def test_run_is_append_only_and_skips_non_arrivals(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "first_seen.csv"), "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=FS_FIELDS)
                w.writeheader()
                w.writerow(fs_row("1651430", "Aedes albopictus", "QA", "arrival", ["5062942631"]))
                w.writerow(fs_row("1311742", "Vespa velutina", "PL", "arrival", ["6500000001"],
                                  week="2026-W47"))
                w.writerow(fs_row("5", "Vespa velutina", "GR", "weak", []))
            c = FakeClient()
            rows = L.run(d, client=c, today=TODAY, only_week=True)
            self.assertEqual([(r["species"], r["country"]) for r in rows],
                             [("Aedes albopictus", "QA")])
            rows = L.run(d, client=c, today=TODAY)
            self.assertEqual([(r["species"], r["country"]) for r in rows],
                             [("Vespa velutina", "PL")])
            self.assertEqual(L.run(d, client=c, today=TODAY), [])
            with open(os.path.join(d, "lookalikes.csv"), newline="", encoding="utf-8") as fh:
                got = list(csv.DictReader(fh))
            self.assertEqual(len(got), 2)
            self.assertEqual(list(got[0].keys()), L.LABEL_FIELDS)
            self.assertEqual([g["risk"] for g in got], ["high", "low"])


if __name__ == "__main__":
    unittest.main()
