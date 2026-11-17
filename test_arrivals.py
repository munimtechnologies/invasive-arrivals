# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Offline tests for arrivals.py (no network). Run: python -m unittest -v test_arrivals"""

import io
import unittest
import zipfile

import arrivals as A

META = r'''<?xml version="1.0" encoding="UTF-8"?>
<archive xmlns="http://rs.tdwg.org/dwc/text/" metadata="eml.xml">
  <core encoding="UTF-8" fieldsTerminatedBy="\t" linesTerminatedBy="\n" fieldsEnclosedBy="" ignoreHeaderLines="1" rowType="http://rs.tdwg.org/dwc/terms/Taxon">
    <files><location>taxon.txt</location></files>
    <id index="0"/>
    <field index="0" term="http://rs.tdwg.org/dwc/terms/taxonID"/>
    <field index="1" term="http://rs.tdwg.org/dwc/terms/scientificName"/>
    <field index="2" term="http://rs.tdwg.org/dwc/terms/kingdom"/>
    <field index="3" term="http://rs.tdwg.org/dwc/terms/taxonRank"/>
  </core>
  <extension encoding="UTF-8" fieldsTerminatedBy="\t" linesTerminatedBy="\n" fieldsEnclosedBy="" ignoreHeaderLines="1" rowType="http://rs.gbif.org/terms/1.0/SpeciesProfile">
    <files><location>speciesprofile.txt</location></files>
    <coreid index="0"/>
    <field index="1" term="http://rs.gbif.org/terms/1.0/isInvasive"/>
  </extension>
  <extension encoding="UTF-8" fieldsTerminatedBy="\t" linesTerminatedBy="\n" fieldsEnclosedBy="" ignoreHeaderLines="1" rowType="http://rs.gbif.org/terms/1.0/Distribution">
    <files><location>distribution.txt</location></files>
    <coreid index="0"/>
    <field index="1" term="http://rs.tdwg.org/dwc/terms/countryCode"/>
    <field term="http://rs.tdwg.org/dwc/terms/occurrenceStatus" default="present"/>
  </extension>
</archive>
'''

TAXON = ("taxonID\tscientificName\tkingdom\ttaxonRank\n"
         "t1\tReynoutria japonica Houtt.\tPlantae\tspecies\n"
         "t2\tPanonychus ulmi (Koch, 1836)\tAnimalia\tspecies\n"
         "t3\tOpuntia spp.\tPlantae\tgenus\n")
PROFILE = "id\tisInvasive\nt1\tYes\nt2\tNull\nt3\tInvasive\n"
DISTRIBUTION = "id\tcountryCode\nt1\tmn\nt2\tMN\nt3\t\n"


def make_archive():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("meta.xml", META.encode("utf-8"))
        zf.writestr("taxon.txt", TAXON)
        zf.writestr("speciesprofile.txt", PROFILE)
        zf.writestr("distribution.txt", DISTRIBUTION)
    return buf.getvalue()


def record(**over):
    rec = {"key": 1, "occurrenceStatus": "PRESENT", "basisOfRecord": "HUMAN_OBSERVATION",
           "decimalLatitude": 47.91, "decimalLongitude": 106.88,
           "issues": ["COORDINATE_ROUNDED"], "year": 2025, "eventDate": "2025-06-01T10:00",
           "media": [{"type": "StillImage"}], "datasetKey": A.INAT_DATASET}
    rec.update(over)
    return rec


class ArchiveTests(unittest.TestCase):
    def test_parse_meta(self):
        meta = A.parse_meta(META.encode("utf-8"))
        self.assertEqual(meta["core"]["rowType"], "Taxon")
        self.assertEqual(meta["core"]["delimiter"], "\t")
        self.assertEqual(meta["core"]["quote"], "")
        self.assertEqual(meta["core"]["fields"]["scientificName"], 1)
        self.assertEqual([e["rowType"] for e in meta["extensions"]], ["SpeciesProfile", "Distribution"])
        self.assertEqual(meta["extensions"][1]["defaults"], {"occurrenceStatus": "present"})

    def test_parse_archive(self):
        taxa = {t["taxon_id"]: t for t in A.parse_griis_archive(make_archive())}
        self.assertEqual(sorted(taxa), ["t1", "t2", "t3"])
        self.assertTrue(taxa["t1"]["invasive"])
        self.assertFalse(taxa["t2"]["invasive"])
        self.assertTrue(taxa["t3"]["invasive"])
        self.assertEqual(taxa["t1"]["country_codes"], {"MN"})
        self.assertEqual(taxa["t2"]["country_codes"], {"MN"})
        self.assertEqual(taxa["t3"]["country_codes"], set())
        self.assertEqual(taxa["t1"]["scientific_name"], "Reynoutria japonica Houtt.")
        self.assertEqual(taxa["t1"]["kingdom"], "Plantae")

    def test_missing_meta(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("taxon.txt", TAXON)
        with self.assertRaises(ValueError):
            A.parse_griis_archive(buf.getvalue())


class NameTests(unittest.TestCase):
    def test_binomial(self):
        self.assertEqual(A.binomial("Reynoutria japonica Houtt."), "reynoutria japonica")
        self.assertEqual(A.binomial("Fallopia × bohemica"), "fallopia bohemica")
        self.assertEqual(A.binomial("Panonychus ulmi (Koch, 1836)"), "panonychus ulmi")
        self.assertEqual(A.binomial("Opuntia spp."), "")
        self.assertEqual(A.binomial("Opuntia sp"), "")
        self.assertEqual(A.binomial("Acacia"), "")
        self.assertEqual(A.binomial(""), "")
        self.assertEqual(A.binomial(None), "")

    def test_truthy(self):
        for v in ("Yes", "TRUE", " invasive ", "1"):
            self.assertTrue(A.is_truthy(v))
        for v in ("Null", "", None, "no", "not invasive"):
            self.assertFalse(A.is_truthy(v))

    def test_country_from_title(self):
        iso = {"mongolia": "MN", "unitedstatesofamerica": "US"}
        self.assertEqual(A.country_from_title(
            "GRIIS Checklist of Introduced and Invasive Species - Mongolia", iso), "MN")
        self.assertEqual(A.country_from_title("Global Register – United States of America", iso), "US")
        self.assertEqual(A.country_from_title("No separator here", iso), "")

    def test_checklist_country(self):
        taxa = [{"country_codes": {"MN"}}, {"country_codes": {"MN", "CN"}}]
        self.assertEqual(A.checklist_country(taxa, "x - Nowhere", {}), "MN")
        self.assertEqual(A.checklist_country([{"country_codes": set()}], "GRIIS - Mongolia",
                                             {"mongolia": "MN"}), "MN")


class ScreenTests(unittest.TestCase):
    def test_parse_facet(self):
        resp = {"facets": [{"field": "COUNTRY", "counts": [{"name": "BE", "count": 5},
                                                           {"name": "de", "count": 2}]}]}
        self.assertEqual(A.parse_facet(resp), {"BE": 5, "DE": 2})
        self.assertEqual(A.parse_facet({"facets": []}), {})
        self.assertEqual(A.parse_facet(None), {})

    def test_candidate_countries(self):
        all_c = {"BE": 10, "MN": 3, "KZ": 5, "ZZ": 1}
        recent = {"BE": 2, "MN": 3, "KZ": 5, "ZZ": 1, "QA": 1}
        self.assertEqual(A.candidate_countries(all_c, recent, {"KZ"}), ["MN"])
        self.assertEqual(A.candidate_countries(all_c, recent), ["KZ", "MN"])
        self.assertEqual(A.candidate_countries({}, {}), [])

    def test_qualifies_and_strong(self):
        self.assertTrue(A.qualifies(record()))
        self.assertTrue(A.is_strong(record()))
        self.assertFalse(A.qualifies(record(occurrenceStatus="ABSENT")))
        self.assertFalse(A.qualifies(record(basisOfRecord="LIVING_SPECIMEN")))
        self.assertFalse(A.qualifies(record(decimalLatitude=None)))
        self.assertFalse(A.qualifies(record(issues=["COUNTRY_COORDINATE_MISMATCH"])))
        self.assertFalse(A.qualifies(record(establishmentMeans={"concept": "Managed"})))
        self.assertFalse(A.qualifies(record(degreeOfEstablishment="cultivated")))
        self.assertFalse(A.qualifies(record(year=2019)))
        self.assertFalse(A.qualifies(record(year=None)))
        self.assertTrue(A.qualifies(record(media=[])))
        self.assertFalse(A.is_strong(record(media=[])))
        self.assertTrue(A.is_strong(record(media=[], basisOfRecord="PRESERVED_SPECIMEN")))

    def test_parse_match_v1(self):
        ok = {"usageKey": 5, "speciesKey": 4407, "species": "Halyomorpha halys",
              "kingdom": "Animalia", "class": "Insecta", "matchType": "EXACT", "confidence": 99}
        m = A.parse_match(ok)
        self.assertEqual(m["species_key"], "4407")
        self.assertEqual(m["class"], "Insecta")
        self.assertIsNone(A.parse_match({"matchType": "FUZZY", "confidence": 92, "speciesKey": 1}))
        self.assertIsNotNone(A.parse_match({"matchType": "FUZZY", "confidence": 97, "speciesKey": 1}))
        self.assertIsNone(A.parse_match({"matchType": "HIGHERRANK", "confidence": 99, "speciesKey": 1}))
        self.assertIsNone(A.parse_match({"matchType": "EXACT", "confidence": 99}))
        self.assertIsNone(A.parse_match(None))

    def test_parse_match_v2(self):
        resp = {"usage": {"key": "x", "name": "Halyomorpha halys (Stål, 1855)"},
                "classification": [{"key": "K1", "name": "Animalia", "rank": "KINGDOM"},
                                   {"key": "C1", "name": "Insecta", "rank": "CLASS"},
                                   {"key": "S1", "name": "Halyomorpha halys", "rank": "SPECIES"}],
                "diagnostics": {"matchType": "EXACT", "confidence": 98}}
        m = A.parse_match(resp)
        self.assertEqual((m["species_key"], m["kingdom"], m["class"]), ("S1", "Animalia", "Insecta"))
        resp["diagnostics"]["matchType"] = "NONE"
        self.assertIsNone(A.parse_match(resp))

    def test_draw_sample(self):
        pairs = [{"species_key": str(i), "country": "MN"} for i in range(100)]
        s1 = A.draw_sample(pairs, 60, 7)
        s2 = A.draw_sample(list(reversed(pairs)), 60, 7)
        self.assertEqual(len(s1), 60)
        self.assertEqual(s1, s2)
        self.assertEqual(len(A.draw_sample(pairs[:5], 60, 7)), 5)

    def test_summarise_pair(self):
        sp = {"species_key": "4407", "species": "Halyomorpha halys", "kingdom": "Animalia",
              "class": "Insecta", "invasive_in": {"US", "DE"}, "listed_in": {"US", "DE", "FR"}}
        recs = [record(key=1),
                record(key=2, media=[], datasetKey="abc", eventDate="2025-03-02"),
                record(key=3, occurrenceStatus="ABSENT")]
        row = A.summarise_pair(sp, "MN", recs)
        self.assertEqual(row["recent_records"], 3)
        self.assertEqual(row["qualifying_records"], 2)
        self.assertEqual(row["strong_records"], 1)
        self.assertEqual(row["strength"], "strong")
        self.assertEqual(row["first_qualifying_date"], "2025-03-02")
        self.assertEqual(row["first_lat_1dp"], 47.9)
        self.assertTrue(row["has_inaturalist"])
        self.assertEqual(row["example_occurrences"], "https://www.gbif.org/occurrence/1")
        self.assertEqual(row["griis_invasive_in"], "DE;US")
        self.assertEqual(row["griis_invasive_in_count"], 2)
        self.assertEqual(row["griis_listed_count"], 3)
        empty = A.summarise_pair(sp, "MN", [record(occurrenceStatus="ABSENT")])
        self.assertEqual(empty["strength"], "none")
        self.assertFalse(empty["has_inaturalist"])


if __name__ == "__main__":
    unittest.main()
