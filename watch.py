#!/usr/bin/env python3
# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy at
# http://www.apache.org/licenses/LICENSE-2.0
"""invasive-arrivals watch (IA-2): a prospective, weekly, global watch of GBIF for
the first record of a known invasive species in a new country.

Each run asks GBIF, for every target species, which countries hold any record of
it. A country the watch has never seen for that species, and where no GRIIS
checklist lists it, is a new pair. The watch then reads the pair's records:

  arrival     every dated record is from this year or last year, and at least one
              is a checkable (photo or specimen), wild-looking, well-georeferenced
              record. These go into the public feed.
  weak        recent, but no checkable record.
  historical  an older or undated record exists (a newly digitised old record).
  excluded    recent, but no record qualifies (captive, garden, bad coordinates...).
  none        GBIF returned no records for the pair.

For arrivals it also asks how far away the species is already known in other
countries: "front" (another country within 300 km), "mid" (within 1,000 km) or
"jump" (none within 1,000 km).

Every pair is logged once, append-only, in first_seen.csv with the date the watch
first saw it, so lead times are measured from what the screen actually saw.

By MV2 of Munim, Inc. (mv2@munimtech.com). Made with AI agents. Python stdlib only.
See IA2-PREREG.md for the hypotheses this watch is graded against.
"""

import argparse
import collections
import csv
import datetime
import json
import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from xml.sax.saxutils import escape

import arrivals as A

BACKBONE = "d7dddbf4-2cf0-4f39-9b2a-bb099caae36c"  # legacy GBIF Backbone checklistKey
FRONT_KM = 300
FAR_KM = 1000
FEED_SIZE = 200
FEED_URL = ("https://raw.githubusercontent.com/munimtechnologies/invasive-arrivals/"
            "main/watch/atom.xml")
FEED_ID = "tag:munimtech.com,2026:invasive-arrivals:watch"
FEED_TITLE = "invasive-arrivals watch: candidate first national records of invasive species"

KIND_ORDER = {"arrival": 0, "weak": 1, "excluded": 2, "historical": 3, "none": 4}
BAND_ORDER = {"front": 0, "mid": 1, "jump": 2, "unknown": 3, "": 4}

TARGET_FIELDS = ["species_key", "species", "kingdom", "class", "match_type",
                 "invasive_in", "listed_in", "binomials"]
FIRST_SEEN_FIELDS = [
    "week", "first_seen_date", "species_key", "species", "kingdom", "class", "country",
    "kind", "records", "strong_records", "first_strong_event_date", "lat_1dp", "lon_1dp",
    "has_inaturalist", "band", "countries_within_1000km", "griis_invasive_in_count",
    "example_occurrences", "gbif_search_url",
]
RUN_FIELDS = [
    "week", "taken", "baseline", "species_screened", "species_baselined", "facet_failures",
    "new_pairs", "arrival", "weak", "excluded", "historical", "none", "record_failures",
    "http_calls", "http_failures", "status",
]


# ----------------------------------------------------------------- pure helpers

def iso_week(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def recent_years(day):
    """The rolling window: this calendar year and the one before."""
    return (day.year - 1, day.year)


def pack(countries):
    return " ".join(sorted(countries))


def unpack(text):
    return set((text or "").split())


def split_codes(text):
    return {c.strip().upper() for c in (text or "").split(";") if c.strip()}


def new_countries(prev, now, listed):
    """Countries in `now` the watch has never seen, minus listed and no-country codes."""
    return sorted(c for c in now
                  if c not in prev and c not in listed and c not in A.NO_COUNTRY)


def _year(rec):
    try:
        return int(rec.get("year"))
    except (TypeError, ValueError):
        return None


def qualifies_in(rec, years):
    """arrivals.qualifies() with the year window `years` instead of IA-1's fixed one."""
    year = _year(rec)
    if year is None or year not in years:
        return False
    return A.qualifies(dict(rec, year=A.RECENT_YEARS[0]))


def strong_in(rec, years):
    if not qualifies_in(rec, years):
        return False
    return bool(rec.get("media")) or str(rec.get("basisOfRecord") or "").upper() in A.STRONG_BASIS


def classify_pair(records, years):
    """-> (kind, strong records) for the records of one new (species, country) pair."""
    if not records:
        return "none", []
    if any(_year(r) is None or _year(r) < years[0] for r in records):
        return "historical", []
    strong = [r for r in records if strong_in(r, years)]
    if strong:
        return "arrival", strong
    if any(qualifies_in(r, years) for r in records):
        return "weak", []
    return "excluded", []


def other_countries(country, facets):
    return {c for c, n in (facets or {}).items()
            if n > 0 and c != country and c not in A.NO_COUNTRY}


def band_from_facets(country, near_front, near_far):
    """'front', 'mid' or 'jump' from country facets around the first record."""
    if near_front is None or near_far is None:
        return "unknown"
    if other_countries(country, near_front):
        return "front"
    if other_countries(country, near_far):
        return "mid"
    return "jump"


def first_strong(strong):
    return min(strong, key=lambda r: str(r.get("eventDate") or "9999")) if strong else {}


def make_row(week, today, sp, country, records, kind, strong, near):
    first = first_strong(strong)
    lat, lon = first.get("decimalLatitude"), first.get("decimalLongitude")
    near_front, near_far = near if near else (None, None)
    return {
        "week": week,
        "first_seen_date": today.isoformat(),
        "species_key": sp["species_key"],
        "species": sp.get("species", ""),
        "kingdom": sp.get("kingdom", ""),
        "class": sp.get("class", ""),
        "country": country,
        "kind": kind,
        "records": len(records),
        "strong_records": len(strong),
        "first_strong_event_date": str(first.get("eventDate") or "")[:10],
        "lat_1dp": "" if lat is None else round(float(lat), 1),
        "lon_1dp": "" if lon is None else round(float(lon), 1),
        "has_inaturalist": any(str(r.get("datasetKey")) == A.INAT_DATASET for r in strong),
        "band": band_from_facets(country, near_front, near_far) if near else "",
        "countries_within_1000km": ";".join(sorted(other_countries(country, near_far))),
        "griis_invasive_in_count": len(sp.get("invasive_in", ())),
        "example_occurrences": ";".join(
            f"https://www.gbif.org/occurrence/{r.get('key')}" for r in (strong or records)[:5]),
        "gbif_search_url": (f"https://www.gbif.org/occurrence/search?taxon_key="
                            f"{sp['species_key']}&country={country}"),
    }


def rank_key(row):
    return (KIND_ORDER.get(row["kind"], 9), -int(row.get("griis_invasive_in_count") or 0),
            BAND_ORDER.get(row.get("band", ""), 9), row.get("species", ""), row["country"])


# ----------------------------------------------------------------- the weekly step

def watch_once(client, targets, prev_species, today, workers=2):
    """One weekly pass.

    client: has facets(key) -> {cc: n} or None, records(key, cc) -> list or None,
            near(key, lat, lon, km) -> {cc: n} or None.
    targets: {species_key: {"species_key", "species", "kingdom", "class",
              "invasive_in": set, "listed_in": set}}
    prev_species: {species_key: "AT BE ..."}, the countries seen so far.
    Returns (species state, rows, stats). The state is a union: a country, once
    seen, stays seen, except a pair whose records could not be read (retried).
    """
    years = recent_years(today)
    week = iso_week(today)
    keys = sorted(targets)
    state, pending = {}, []
    stats = collections.Counter()
    stats["species_screened"] = len(keys)
    with ThreadPoolExecutor(workers) as pool:
        for key, facets in zip(keys, pool.map(client.facets, keys)):
            prev = unpack(prev_species[key]) if key in prev_species else None
            if facets is None:
                stats["facet_failures"] += 1
                if prev is not None:
                    state[key] = pack(prev)
                continue
            now = {c for c, n in facets.items() if n > 0 and c not in A.NO_COUNTRY}
            if prev is None:
                stats["species_baselined"] += 1
                state[key] = pack(now)
                continue
            state[key] = pack(prev | now)
            for cc in new_countries(prev, now, targets[key].get("listed_in", set())):
                pending.append((key, cc))
    stats["new_pairs"] = len(pending)

    def examine(pair):
        key, cc = pair
        records = client.records(key, cc)
        if records is None:
            return pair, None, None, [], None
        kind, strong = classify_pair(records, years)
        near = None
        if kind == "arrival":
            first = first_strong(strong)
            lat, lon = first.get("decimalLatitude"), first.get("decimalLongitude")
            near = (client.near(key, lat, lon, FRONT_KM), client.near(key, lat, lon, FAR_KM))
        return pair, records, kind, strong, near

    rows = []
    with ThreadPoolExecutor(workers) as pool:
        for (key, cc), records, kind, strong, near in pool.map(examine, pending):
            if records is None:
                stats["record_failures"] += 1
                state[key] = pack(unpack(state[key]) - {cc})
                continue
            stats[kind] += 1
            rows.append(make_row(week, today, targets[key], cc, records, kind, strong, near))
    rows.sort(key=rank_key)
    return state, rows, dict(stats)


# ----------------------------------------------------------------- files

def load_targets(path):
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row.get("species_key") or "").strip()
            if not key:
                continue
            invasive_in = split_codes(row.get("invasive_in"))
            out[key] = {"species_key": key, "species": row.get("species", ""),
                        "kingdom": row.get("kingdom", ""), "class": row.get("class", ""),
                        "invasive_in": invasive_in,
                        "listed_in": split_codes(row.get("listed_in")) | invasive_in}
    return out


def load_state(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def append_csv(path, rows, fields):
    new_file = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for row in rows:
            w.writerow(row)


def append_first_seen(path, rows):
    """Append rows for pairs not yet in the log. Returns the rows actually added."""
    seen = {(r["species_key"], r["country"]) for r in read_csv(path)}
    fresh = []
    for row in rows:
        pair = (str(row["species_key"]), row["country"])
        if pair not in seen:
            seen.add(pair)
            fresh.append(row)
    append_csv(path, fresh, FIRST_SEEN_FIELDS)
    return fresh


def feed_rows(first_seen_rows, size=FEED_SIZE):
    arrivals = [r for r in first_seen_rows if r.get("kind") == "arrival"]
    arrivals.sort(key=rank_key)
    arrivals.sort(key=lambda r: r.get("first_seen_date", ""), reverse=True)
    return arrivals[:size]


def entry_summary(row):
    near = row.get("countries_within_1000km") or "none"
    return (f"First GBIF record of {row['species']} ({row.get('kingdom', '')}) in "
            f"{row['country']} seen by the watch on {row['first_seen_date']}. "
            f"Earliest checkable record dated {row.get('first_strong_event_date') or 'unknown'}; "
            f"{row.get('strong_records')} checkable record(s). Distance band: "
            f"{row.get('band') or 'unknown'}; other countries with records within 1,000 km: "
            f"{near}. Flagged invasive in {row.get('griis_invasive_in_count')} GRIIS "
            f"countries. A candidate for expert checking, not a confirmed arrival.")


def atom_xml(rows, updated):
    attr = {'"': "&quot;"}
    parts = ['<?xml version="1.0" encoding="utf-8"?>',
             '<feed xmlns="http://www.w3.org/2005/Atom">',
             f"<title>{escape(FEED_TITLE)}</title>",
             f"<id>{FEED_ID}</id>",
             f"<updated>{escape(updated)}</updated>",
             f'<link rel="self" href="{escape(FEED_URL, attr)}"/>',
             "<author><name>MV2 of Munim, Inc.</name><email>mv2@munimtech.com</email></author>",
             "<rights>CC BY 4.0 (feed); GBIF records keep their own licences</rights>"]
    for r in rows:
        title = f"{r['species']} - first GBIF record in {r['country']} ({r.get('band') or 'unknown'})"
        parts += ["<entry>",
                  f"<title>{escape(title)}</title>",
                  f"<id>{FEED_ID}:{escape(str(r['species_key']))}-{escape(r['country'])}</id>",
                  f"<updated>{escape(r['first_seen_date'])}T00:00:00Z</updated>",
                  f'<link href="{escape(r["gbif_search_url"], attr)}"/>',
                  f"<summary>{escape(entry_summary(r))}</summary>",
                  "</entry>"]
    parts.append("</feed>")
    return "\n".join(parts) + "\n"


def week_report(week, today, rows, stats):
    arrivals = [r for r in rows if r["kind"] == "arrival"]
    lines = [f"# invasive-arrivals watch, {week} (run {today.isoformat()})", "",
             "Candidate first national records of known invasive species, seen by the watch",
             "this week. **Candidates, not confirmed arrivals**: each needs an expert's check.",
             "Made with AI agents working for MV2 of Munim, Inc. Licence: CC BY 4.0.", "",
             f"- species screened: {stats.get('species_screened', 0)}",
             f"- new (species, country) pairs: {stats.get('new_pairs', 0)}",
             f"- arrival / weak / excluded / historical / none: {stats.get('arrival', 0)} / "
             f"{stats.get('weak', 0)} / {stats.get('excluded', 0)} / "
             f"{stats.get('historical', 0)} / {stats.get('none', 0)}",
             f"- facet failures: {stats.get('facet_failures', 0)}; record failures "
             f"(retried next week): {stats.get('record_failures', 0)}", ""]
    if stats.get("baseline"):
        lines += ["This is the baseline run: it records what GBIF holds today and flags nothing.", ""]
    if arrivals:
        lines += ["| species | kingdom | country | earliest checkable record | band | "
                  "other countries within 1,000 km | GRIIS invasive in | records |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in arrivals:
            lines.append(f"| *{r['species']}* | {r['kingdom']} | {r['country']} | "
                         f"{r['first_strong_event_date']} | {r['band']} | "
                         f"{r['countries_within_1000km'] or '-'} | "
                         f"{r['griis_invasive_in_count']} | [GBIF]({r['gbif_search_url']}) |")
    elif not stats.get("baseline"):
        lines.append("No arrival candidates this week.")
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------- network

class GbifClient:
    """GBIF occurrence queries, pinned to the legacy GBIF Backbone taxonomy.

    GBIF.org moved to the Catalogue of Life Extended Release in 2026; the legacy
    Backbone (integer keys, which the GRIIS matching uses) is frozen, so pinning it
    keeps species keys stable for the whole study.
    """

    def __init__(self, http):
        self.http = http

    def _search(self, params):
        params = dict(params, checklistKey=BACKBONE)
        return self.http.get(f"{A.API}/occurrence/search?{urllib.parse.urlencode(params)}")

    def facets(self, key):
        resp = self._search({"taxonKey": key, "facet": "country", "facetLimit": 400, "limit": 0})
        return None if resp is None else A.parse_facet(resp)

    def records(self, key, country):
        resp = self._search({"taxonKey": key, "country": country, "limit": 300})
        return None if resp is None else (resp.get("results") or [])

    def near(self, key, lat, lon, km):
        if lat is None or lon is None:
            return None
        resp = self._search({"taxonKey": key,
                             "geoDistance": f"{float(lat):.4f},{float(lon):.4f},{km}km",
                             "facet": "country", "facetLimit": 400, "limit": 0})
        return None if resp is None else A.parse_facet(resp)


def build_targets(http, path, workers=2):
    """The IA-1 target list (GRIIS invasive names matched to GBIF), written to `path`."""
    countries = http.get(f"{A.API}/enumeration/country") or []
    name_to_iso = {}
    for c in countries:
        for k in ("title", "enumName"):
            if c.get(k) and c.get("iso2"):
                name_to_iso[A.norm_country(c[k])] = c["iso2"]
    datasets = A.list_griis_datasets(http)
    listed, invasive = collections.defaultdict(set), {}
    with ThreadPoolExecutor(workers) as pool:
        for ds, taxa, _err in pool.map(lambda d: A.fetch_checklist(http, d), datasets):
            if taxa is None:
                continue
            cc = A.checklist_country(taxa, ds["title"], name_to_iso)
            for t in taxa:
                b = A.binomial(t["scientific_name"])
                if not b:
                    continue
                if cc:
                    listed[cc].add(b)
                if t["invasive"]:
                    e = invasive.setdefault(b, {"name": t["scientific_name"],
                                                "kingdom": t["kingdom"], "invasive_in": set()})
                    if cc:
                        e["invasive_in"].add(cc)
    if not invasive:
        raise RuntimeError("no GRIIS invasive names found; GBIF dataset search changed?")
    names = sorted(invasive)
    with ThreadPoolExecutor(workers) as pool:
        matches = list(pool.map(
            lambda b: A.match_name(http, invasive[b]["name"], invasive[b]["kingdom"]), names))
    species = {}
    for b, m in zip(names, matches):
        if m is None:
            continue
        sp = species.setdefault(m["species_key"],
                                dict(m, binomials=set(), invasive_in=set(), listed_in=set()))
        sp["binomials"].add(b)
        sp["invasive_in"] |= invasive[b]["invasive_in"]
    for sp in species.values():
        sp["binomials"].add(A.binomial(sp["species"]) or "")
        for cc, there in listed.items():
            if sp["binomials"] & there:
                sp["listed_in"].add(cc)
        sp["listed_in"] |= sp["invasive_in"]
    A.write_csv(path, [dict(s, invasive_in=";".join(sorted(s["invasive_in"])),
                            listed_in=";".join(sorted(s["listed_in"])),
                            binomials=";".join(sorted(x for x in s["binomials"] if x)))
                       for s in sorted(species.values(), key=lambda s: s["species_key"])],
                TARGET_FIELDS)
    return load_targets(path)


# ----------------------------------------------------------------- main

def run(state_dir, targets_path, build=False, workers=2, min_interval=0.25, today=None,
        force=False, max_species=0, client=None):
    os.makedirs(os.path.join(state_dir, "weeks"), exist_ok=True)
    today = today or datetime.datetime.now(datetime.timezone.utc).date()
    week = iso_week(today)
    state_path = os.path.join(state_dir, "state.json")
    prev = load_state(state_path)
    if prev and prev.get("week") == week and not force:
        print(f"already ran for {week}; nothing to do (use --force to run again)")
        return 0
    http = getattr(client, "http", None)
    if client is None:
        http = A.Http(min_interval=min_interval)
        client = GbifClient(http)
    if os.path.exists(targets_path):
        targets = load_targets(targets_path)
    elif build:
        if http is None:
            raise RuntimeError("--build-targets needs network access")
        targets = build_targets(http, targets_path, workers)
    else:
        print(f"no targets file at {targets_path} (use --build-targets)", file=sys.stderr)
        return 2
    if max_species:
        targets = dict(sorted(targets.items())[:max_species])
    prev_species = (prev or {}).get("species", {})
    species, rows, stats = watch_once(client, targets, prev_species, today, workers)
    stats["baseline"] = int(prev is None)
    taken = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_row = dict(stats, week=week, taken=taken,
                   http_calls=getattr(http, "calls", ""), http_failures=getattr(http, "failures", ""))
    if stats.get("facet_failures", 0) > 0.1 * max(1, len(targets)):
        run_row["status"] = "aborted: more than 10% of species facet queries failed"
        append_csv(os.path.join(state_dir, "runs.csv"), [run_row], RUN_FIELDS)
        print(run_row["status"], file=sys.stderr)
        return 3
    merged = dict(prev_species)
    merged.update(species)
    save_state(state_path, {"schema": 1, "week": week, "taken": taken,
                            "recent_years": list(recent_years(today)), "species": merged})
    added = append_first_seen(os.path.join(state_dir, "first_seen.csv"), rows)
    with open(os.path.join(state_dir, "weeks", f"{week}.md"), "w", encoding="utf-8") as fh:
        fh.write(week_report(week, today, added, stats))
    feed = feed_rows(read_csv(os.path.join(state_dir, "first_seen.csv")))
    with open(os.path.join(state_dir, "feed.json"), "w", encoding="utf-8") as fh:
        json.dump({"title": FEED_TITLE, "updated": taken, "licence": "CC BY 4.0",
                   "by": "MV2 of Munim, Inc. (made with AI agents)", "items": feed},
                  fh, indent=1)
        fh.write("\n")
    with open(os.path.join(state_dir, "atom.xml"), "w", encoding="utf-8") as fh:
        fh.write(atom_xml(feed, taken))
    run_row["status"] = "ok"
    append_csv(os.path.join(state_dir, "runs.csv"), [run_row], RUN_FIELDS)
    print(json.dumps({k: run_row[k] for k in RUN_FIELDS if k in run_row}))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--state-dir", default="watch")
    ap.add_argument("--targets", default="watch/targets.csv",
                    help="CSV with species_key (and optionally species, kingdom, class, "
                         "invasive_in, listed_in); the IA-1 target_species.csv works")
    ap.add_argument("--build-targets", action="store_true",
                    help="build the GRIIS target list if the targets file is missing")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--min-interval", type=float, default=0.25, help="seconds between API calls")
    ap.add_argument("--today", help="YYYY-MM-DD (default: today, UTC)")
    ap.add_argument("--force", action="store_true", help="run again in the same ISO week")
    ap.add_argument("--max-species", type=int, default=0, help="watch only the first N species")
    args = ap.parse_args(argv)
    today = datetime.date.fromisoformat(args.today) if args.today else None
    return run(args.state_dir, args.targets, args.build_targets, args.workers,
               args.min_interval, today, args.force, args.max_species)


if __name__ == "__main__":
    sys.exit(main())
