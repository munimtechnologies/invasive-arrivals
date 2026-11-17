#!/usr/bin/env python3
# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy at
# http://www.apache.org/licenses/LICENSE-2.0
"""invasive-arrivals look-alike labeller (IA-2 addendum 2).

For every new `arrival` row the weekly watch writes to watch/first_seen.csv, this
takes two automatic labels the same week, before anyone checks the pair by hand:

  lookalike   Does a species that iNaturalist users often confuse with the target
              (its top similar species, from iNaturalist's public similar-species
              tally) already have GBIF records in the flagged country?
              yes / no / unknown.
  thin_id     Is every iNaturalist record behind the flag "thin": the observer's
              own first identification used computer vision, and at most one other
              person agreed? yes / no / n/a (no iNaturalist record) / unknown.

  risk        high = lookalike yes AND thin_id yes; low = lookalike no OR thin_id no;
              unknown otherwise.

The labels are written append-only to watch/lookalikes.csv with the date they were
taken. Agreements pile up once a record becomes notable, so a label is only fair
if it is taken in the same week the watch first flags the pair; rows flagged in an
earlier week are labelled but marked late. IA2-ADDENDUM-2.md registers what is
tested with these labels. They never change the watch's flags or the hand classes.

By MV2 of Munim, Inc. (mv2@munimtech.com). Made with AI agents. Python stdlib only.
"""

import argparse
import csv
import datetime
import os
import re
import sys
import urllib.parse

import arrivals as A

INAT = "https://api.inaturalist.org/v1"
BACKBONE = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"  # legacy GBIF Backbone, as in watch.py
TOP_K = 5             # similar species checked per target
MIN_CONFUSIONS = 5    # ignore similar species confused fewer times than this
MAX_AGREEMENTS_THIN = 1
MAX_OBS = 5           # iNaturalist records read per pair (the example occurrences)

LABEL_FIELDS = [
    "week", "labelled_on", "late", "species_key", "species", "country",
    "inat_taxon_id", "similar_checked", "lookalikes_present", "lookalike",
    "inat_observations", "observer_vision", "agreements", "disagreements", "thin_id",
    "risk",
]


# ----------------------------------------------------------------- pure helpers

def inat_taxon_id(resp, name):
    """iNaturalist /taxa search response -> id of the active species named `name`."""
    want = A.binomial(name)
    if not want:
        return None
    for t in (resp or {}).get("results") or []:
        if (str(t.get("rank", "")).lower() == "species" and t.get("is_active", True)
                and A.binomial(t.get("name", "")) == want):
            return t.get("id")
    return None


def similar_species(resp, target, k=TOP_K, min_count=MIN_CONFUSIONS):
    """iNaturalist similar_species response -> [(name, count)], the top k species
    (not hybrids, not the target itself) confused at least `min_count` times."""
    own = A.binomial(target)
    rows = []
    for r in (resp or {}).get("results") or []:
        t = r.get("taxon") or {}
        name = t.get("name", "")
        try:
            count = int(r.get("count") or 0)
        except (TypeError, ValueError):
            continue
        b = A.binomial(name)
        if str(t.get("rank", "")).lower() != "species" or not b or b == own:
            continue
        if count < min_count:
            continue
        rows.append((name, count))
    rows.sort(key=lambda x: (-x[1], x[0]))
    return rows[:k]


def inat_obs_id(occ):
    """GBIF occurrence -> iNaturalist observation id (str) or None."""
    if str((occ or {}).get("datasetKey")) != A.INAT_DATASET:
        return None
    for field in ("references", "occurrenceID"):
        m = re.search(r"inaturalist\.org/observations/(\d+)", str(occ.get(field) or ""))
        if m:
            return m.group(1)
    num = str(occ.get("catalogNumber") or "").strip()
    return num if num.isdigit() else None


def occurrence_keys(row, limit=MAX_OBS):
    keys = re.findall(r"gbif\.org/occurrence/(\d+)", row.get("example_occurrences") or "")
    return keys[:limit]


def obs_support(obs):
    """iNaturalist observation -> (observer_vision True/False/None, agreements,
    disagreements, thin True/False)."""
    idents = obs.get("identifications") or []
    owner = (obs.get("user") or {}).get("id")

    def is_own(i):
        if "own_observation" in i:
            return bool(i.get("own_observation"))
        return owner is not None and (i.get("user") or {}).get("id") == owner

    # The observer's first identification (iNaturalist ids increase over time).
    own = sorted((i for i in idents if is_own(i)), key=lambda i: int(i.get("id") or 0))
    vision = bool(own[0].get("vision")) if own else None
    # iNaturalist's tallies count other people's identifications only (checked
    # 2026-11-17 on observations 258016438, 300129994 and 403680492).
    agree = int(obs.get("num_identification_agreements") or 0)
    disagree = int(obs.get("num_identification_disagreements") or 0)
    thin = vision is True and agree <= MAX_AGREEMENTS_THIN
    return vision, agree, disagree, thin


def pair_thin(supports, n_inat):
    """Pair-level thin_id from the supports of its iNaturalist records."""
    if n_inat == 0:
        return "n/a"
    if len(supports) < n_inat:
        return "unknown"
    return "yes" if all(s[3] for s in supports) else "no"


def risk(lookalike, thin_id):
    if lookalike == "yes" and thin_id == "yes":
        return "high"
    if lookalike == "no" or thin_id == "no":
        return "low"
    return "unknown"


# ----------------------------------------------------------------- network

class Client:
    """GBIF and iNaturalist lookups with per-run caches."""

    def __init__(self, gbif_http, inat_http):
        self.gbif, self.inat = gbif_http, inat_http
        self._taxon, self._similar, self._key, self._count = {}, {}, {}, {}

    def taxon_id(self, name):
        if name not in self._taxon:
            q = urllib.parse.urlencode({"q": name, "rank": "species", "per_page": 10})
            self._taxon[name] = inat_taxon_id(self.inat.get(f"{INAT}/taxa?{q}"), name)
        return self._taxon[name]

    def similar(self, taxon_id):
        if taxon_id not in self._similar:
            resp = self.inat.get(f"{INAT}/identifications/similar_species?taxon_id={taxon_id}")
            self._similar[taxon_id] = resp
        return self._similar[taxon_id]

    def gbif_key(self, name, kingdom):
        if (name, kingdom) not in self._key:
            m = A.match_name(self.gbif, name, kingdom)
            self._key[(name, kingdom)] = m["species_key"] if m else None
        return self._key[(name, kingdom)]

    def count_in(self, key, country):
        if (key, country) not in self._count:
            q = urllib.parse.urlencode({"taxonKey": key, "country": country, "limit": 0,
                                        "checklistKey": BACKBONE})
            resp = self.gbif.get(f"{A.API}/occurrence/search?{q}")
            self._count[(key, country)] = None if resp is None else int(resp.get("count") or 0)
        return self._count[(key, country)]

    def occurrence(self, key):
        return self.gbif.get(f"{A.API}/occurrence/{key}")

    def observations(self, ids):
        if not ids:
            return {}
        resp = self.inat.get(f"{INAT}/observations?id={','.join(ids)}&per_page={len(ids)}")
        if resp is None:
            return None
        return {str(o.get("id")): o for o in resp.get("results") or []}


# ----------------------------------------------------------------- labelling

def label_row(client, row, today, week):
    species, country = row.get("species", ""), row.get("country", "")
    out = {"week": row.get("week", ""), "labelled_on": today.isoformat(),
           "late": "yes" if row.get("week") != week else "no",
           "species_key": row.get("species_key", ""), "species": species, "country": country}

    # 1. look-alikes recorded in the country
    tid = client.taxon_id(species)
    out["inat_taxon_id"] = tid or ""
    lookalike, checked, present = "unknown", [], []
    if tid is not None:
        resp = client.similar(tid)
        if resp is not None:
            sims = similar_species(resp, species)
            failed = False
            for name, n in sims:
                key = client.gbif_key(name, row.get("kingdom", ""))
                cnt = None if key is None else client.count_in(key, country)
                checked.append(f"{name} ({n})")
                if cnt is None:
                    failed = True
                elif cnt > 0:
                    present.append(f"{name} ({cnt} GBIF records)")
            if present:
                lookalike = "yes"
            elif not failed:
                lookalike = "no"
    out.update(similar_checked="; ".join(checked), lookalikes_present="; ".join(present),
               lookalike=lookalike)

    # 2. how thin the iNaturalist identifications are
    obs_ids, unreadable = [], 0
    for k in occurrence_keys(row):
        occ = client.occurrence(k)
        if occ is None:
            unreadable += 1
            continue
        oid = inat_obs_id(occ)
        if oid:
            obs_ids.append(oid)
    supports = []
    obs = client.observations(obs_ids) if obs_ids else {}
    if obs is not None:
        supports = [obs_support(obs[o]) for o in obs_ids if o in obs]
    thin = pair_thin(supports, len(obs_ids))
    if thin == "n/a" and unreadable:
        thin = "unknown"
    out.update(inat_observations=";".join(obs_ids),
               observer_vision=";".join("" if s[0] is None else ("yes" if s[0] else "no")
                                        for s in supports),
               agreements=";".join(str(s[1]) for s in supports),
               disagreements=";".join(str(s[2]) for s in supports),
               thin_id=thin, risk=risk(lookalike, thin))
    return out


def run(state_dir, client=None, today=None, only_week=False):
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    year, wk, _ = today.isocalendar()
    week = f"{year}-W{wk:02d}"
    first_seen = read_csv(os.path.join(state_dir, "first_seen.csv"))
    out_path = os.path.join(state_dir, "lookalikes.csv")
    done = {(r["species_key"], r["country"]) for r in read_csv(out_path)}
    todo = [r for r in first_seen if r.get("kind") == "arrival"
            and (str(r.get("species_key")), r.get("country")) not in done
            and (not only_week or r.get("week") == week)]
    if client is None:
        client = Client(A.Http(min_interval=0.25), A.Http(min_interval=1.1))
    rows = [label_row(client, r, today, week) for r in todo]
    new_file = not os.path.exists(out_path)
    with open(out_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LABEL_FIELDS, extrasaction="ignore")
        if new_file:
            w.writeheader()
        w.writerows(rows)
    print(f"labelled {len(rows)} arrival pair(s) for {week}")
    return rows


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--state-dir", default="watch")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today, UTC)")
    ap.add_argument("--only-week", action="store_true",
                    help="label only pairs first seen in the current ISO week")
    args = ap.parse_args(argv)
    today = datetime.date.fromisoformat(args.today) if args.today else None
    run(args.state_dir, today=today, only_week=args.only_week)
    return 0


if __name__ == "__main__":
    sys.exit(main())
