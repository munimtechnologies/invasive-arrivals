# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Offline tests for watch.py (IA-2). No network: GBIF is replaced by a fake client."""

import csv
import datetime
import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

import arrivals as A
import watch as W

TODAY = datetime.date(2026, 11, 23)
YEARS = (2025, 2026)


def rec(year=2026, media=True, key=1, date="2026-09-26", dataset=A.INAT_DATASET, **kw):
    r = {"year": year, "eventDate": date, "decimalLatitude": 50.06, "decimalLongitude": 19.94,
         "basisOfRecord": "HUMAN_OBSERVATION", "issues": [], "key": key, "datasetKey": dataset,
         "occurrenceStatus": "PRESENT"}
    if media:
        r["media"] = [{"type": "StillImage"}]
    r.update(kw)
    return r


def target(key, name, listed=(), invasive=()):
    return {"species_key": key, "species": name, "kingdom": "Animalia", "class": "Insecta",
            "invasive_in": set(invasive), "listed_in": set(listed) | set(invasive)}


class FakeClient:
    def __init__(self, facets, records, near):
        self._facets, self._records, self._near = facets, records, near
        self.near_calls = []

    def facets(self, key):
        return self._facets.get(key)

    def records(self, key, country):
        return self._records.get((key, country), [])

    def near(self, key, lat, lon, km):
        self.near_calls.append((key, km))
        return self._near.get((key, km))


def scenario():
    targets = {"1": target("1", "Vespa velutina", listed={"FR"}, invasive={"FR", "ES"}),
               "2": target("2", "Aethina tumida")}
    prev = {"1": "DE FR", "2": "US"}
    client = FakeClient(
        facets={"1": {"DE": 5, "FR": 3, "PL": 1, "AT": 2, "ZZ": 4, "IT": 0}, "2": None},
        records={("1", "PL"): [rec(key=11), rec(key=12, media=False, date="2026-09-20")],
                 ("1", "AT"): [rec(year=1990, date="1990-07-01", key=13)]},
        near={("1", 300): {"PL": 1, "DE": 4}, ("1", 1000): {"PL": 1, "DE": 4, "CZ": 1, "ZZ": 2}})
    return targets, prev, client


class PureHelpers(unittest.TestCase):
    def test_iso_week_and_years(self):
        self.assertEqual(W.iso_week(datetime.date(2026, 11, 17)), "2026-W47")
        self.assertEqual(W.iso_week(datetime.date(2027, 1, 1)), "2026-W53")
        self.assertEqual(W.recent_years(datetime.date(2027, 1, 4)), (2026, 2027))

    def test_pack_roundtrip(self):
        self.assertEqual(W.pack({"PL", "AT", "DE"}), "AT DE PL")
        self.assertEqual(W.unpack("AT DE PL"), {"AT", "DE", "PL"})
        self.assertEqual(W.unpack(""), set())
        self.assertEqual(W.split_codes("at; DE;;"), {"AT", "DE"})

    def test_new_countries(self):
        self.assertEqual(W.new_countries({"DE"}, {"DE", "PL", "ZZ", "AT"}, {"AT"}), ["PL"])

    def test_classify(self):
        self.assertEqual(W.classify_pair([], YEARS), ("none", []))
        kind, strong = W.classify_pair([rec(), rec(media=False, key=2)], YEARS)
        self.assertEqual(kind, "arrival")
        self.assertEqual([r["key"] for r in strong], [1])
        self.assertEqual(W.classify_pair([rec(media=False)], YEARS)[0], "weak")
        self.assertEqual(W.classify_pair([rec(), rec(year=1990)], YEARS)[0], "historical")
        self.assertEqual(W.classify_pair([rec(), rec(year=None)], YEARS)[0], "historical")
        self.assertEqual(W.classify_pair([rec(basisOfRecord="LIVING_SPECIMEN")], YEARS)[0],
                         "excluded")
        specimen = rec(media=False, basisOfRecord="PRESERVED_SPECIMEN")
        self.assertEqual(W.classify_pair([specimen], YEARS)[0], "arrival")
        captive = rec(establishmentMeans={"concept": "Captive"})
        self.assertEqual(W.classify_pair([captive], YEARS)[0], "excluded")

    def test_qualifies_in_uses_rolling_window(self):
        self.assertTrue(W.qualifies_in(rec(year=2027), (2026, 2027)))
        self.assertFalse(W.qualifies_in(rec(year=2025), (2026, 2027)))

    def test_band(self):
        self.assertEqual(W.band_from_facets("PL", {"PL": 1, "DE": 2}, {"PL": 1, "DE": 2}), "front")
        self.assertEqual(W.band_from_facets("PL", {"PL": 1, "ZZ": 3}, {"PL": 1, "CZ": 1}), "mid")
        self.assertEqual(W.band_from_facets("PL", {"PL": 1}, {"PL": 1, "XZ": 1}), "jump")
        self.assertEqual(W.band_from_facets("PL", None, {"PL": 1}), "unknown")


class WatchOnce(unittest.TestCase):
    def test_new_pairs(self):
        targets, prev, client = scenario()
        state, rows, stats = W.watch_once(client, targets, prev, TODAY, workers=2)
        self.assertEqual(state, {"1": "AT DE FR PL", "2": "US"})
        self.assertEqual(stats["facet_failures"], 1)
        self.assertEqual(stats["new_pairs"], 2)
        self.assertEqual(stats["arrival"], 1)
        self.assertEqual(stats["historical"], 1)
        first = rows[0]
        self.assertEqual((first["kind"], first["country"], first["band"]), ("arrival", "PL", "front"))
        self.assertEqual(first["countries_within_1000km"], "CZ;DE")
        self.assertEqual(first["strong_records"], 1)
        self.assertEqual(first["first_strong_event_date"], "2026-09-26")
        self.assertEqual((first["lat_1dp"], first["lon_1dp"]), (50.1, 19.9))
        self.assertTrue(first["has_inaturalist"])
        self.assertEqual(first["griis_invasive_in_count"], 2)
        self.assertEqual(first["week"], "2026-W48")
        self.assertEqual(rows[1]["kind"], "historical")
        self.assertEqual(sorted(client.near_calls), [("1", 300), ("1", 1000)])

    def test_record_failure_is_retried(self):
        targets, prev, client = scenario()
        client._records[("1", "AT")] = None
        state, rows, stats = W.watch_once(client, targets, prev, TODAY)
        self.assertEqual(state["1"], "DE FR PL")
        self.assertEqual(stats["record_failures"], 1)
        self.assertEqual([r["country"] for r in rows], ["PL"])

    def test_baseline_flags_nothing(self):
        targets, _prev, client = scenario()
        state, rows, stats = W.watch_once(client, targets, {}, TODAY)
        self.assertEqual(rows, [])
        self.assertEqual(stats["species_baselined"], 1)
        self.assertEqual(state, {"1": "AT DE FR PL"})

    def test_state_is_a_union(self):
        targets, _prev, client = scenario()
        client._facets["1"] = {"DE": 5}
        state, rows, _ = W.watch_once(client, targets, {"1": "DE FR PL"}, TODAY)
        self.assertEqual(state["1"], "DE FR PL")
        self.assertEqual(rows, [])


class Files(unittest.TestCase):
    def test_targets_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.csv")
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=W.TARGET_FIELDS)
                w.writeheader()
                w.writerow({"species_key": "1", "species": "Vespa velutina", "kingdom": "Animalia",
                            "invasive_in": "FR;ES", "listed_in": "BE"})
                w.writerow({"species_key": ""})
            t = W.load_targets(path)
            self.assertEqual(list(t), ["1"])
            self.assertEqual(t["1"]["listed_in"], {"BE", "ES", "FR"})
            self.assertEqual(t["1"]["invasive_in"], {"ES", "FR"})

    def test_first_seen_is_append_only_and_deduplicated(self):
        targets, prev, client = scenario()
        _state, rows, _ = W.watch_once(client, targets, prev, TODAY)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "first_seen.csv")
            self.assertEqual(len(W.append_first_seen(path, rows)), 2)
            self.assertEqual(len(W.append_first_seen(path, rows)), 0)
            self.assertEqual(len(W.read_csv(path)), 2)

    def test_atom_is_valid_xml(self):
        targets, prev, client = scenario()
        targets["1"]["species"] = "Vespa <velutina> & co"
        _state, rows, _ = W.watch_once(client, targets, prev, TODAY)
        feed = W.feed_rows(rows)
        self.assertEqual(len(feed), 1)
        root = ET.fromstring(W.atom_xml(feed, "2026-11-23T06:00:00Z").encode("utf-8"))
        ns = "{http://www.w3.org/2005/Atom}"
        entries = root.findall(ns + "entry")
        self.assertEqual(len(entries), 1)
        self.assertIn("Vespa <velutina> & co", entries[0].find(ns + "title").text)

    def test_run_end_to_end(self):
        targets, _prev, client = scenario()
        client._facets["2"] = {"US": 3}
        with tempfile.TemporaryDirectory() as d:
            tpath = os.path.join(d, "targets.csv")
            with open(tpath, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=W.TARGET_FIELDS)
                w.writeheader()
                w.writerow({"species_key": "1", "species": "Vespa velutina", "kingdom": "Animalia",
                            "invasive_in": "FR;ES", "listed_in": "FR"})
                w.writerow({"species_key": "2", "species": "Aethina tumida", "kingdom": "Animalia"})
            sdir = os.path.join(d, "watch")
            # week 0: baseline sees DE and FR only
            client._facets["1"] = {"DE": 5, "FR": 3}
            self.assertEqual(W.run(sdir, tpath, today=datetime.date(2026, 11, 16), client=client), 0)
            self.assertFalse(os.path.exists(os.path.join(sdir, "first_seen.csv")) and
                             W.read_csv(os.path.join(sdir, "first_seen.csv")))
            # same week again: nothing happens
            self.assertEqual(W.run(sdir, tpath, today=datetime.date(2026, 11, 17), client=client), 0)
            self.assertEqual(len(W.read_csv(os.path.join(sdir, "runs.csv"))), 1)
            # week 1: PL and AT appear
            client._facets["1"] = {"DE": 5, "FR": 3, "PL": 1, "AT": 2}
            self.assertEqual(W.run(sdir, tpath, today=TODAY, client=client), 0)
            seen = W.read_csv(os.path.join(sdir, "first_seen.csv"))
            self.assertEqual(sorted((r["country"], r["kind"]) for r in seen),
                             [("AT", "historical"), ("PL", "arrival")])
            runs = W.read_csv(os.path.join(sdir, "runs.csv"))
            self.assertEqual([r["baseline"] for r in runs], ["1", "0"])
            self.assertEqual(runs[1]["arrival"], "1")
            with open(os.path.join(sdir, "feed.json"), encoding="utf-8") as fh:
                feed = json.load(fh)
            self.assertEqual([i["country"] for i in feed["items"]], ["PL"])
            ET.parse(os.path.join(sdir, "atom.xml"))
            with open(os.path.join(sdir, "weeks", "2026-W48.md"), encoding="utf-8") as fh:
                self.assertIn("Vespa velutina", fh.read())
            with open(os.path.join(sdir, "state.json"), encoding="utf-8") as fh:
                state = json.load(fh)
            self.assertEqual(state["species"]["1"], "AT DE FR PL")
            self.assertEqual(state["week"], "2026-W48")

    def test_run_aborts_on_many_facet_failures(self):
        targets, _prev, client = scenario()
        client._facets = {}
        with tempfile.TemporaryDirectory() as d:
            tpath = os.path.join(d, "targets.csv")
            with open(tpath, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=W.TARGET_FIELDS)
                w.writeheader()
                w.writerow({"species_key": "1", "species": "Vespa velutina"})
            sdir = os.path.join(d, "watch")
            self.assertEqual(W.run(sdir, tpath, today=TODAY, client=client), 3)
            self.assertFalse(os.path.exists(os.path.join(sdir, "state.json")))


if __name__ == "__main__":
    unittest.main()
