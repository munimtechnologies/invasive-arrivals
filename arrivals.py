#!/usr/bin/env python3
# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy at
# http://www.apache.org/licenses/LICENSE-2.0
"""invasive-arrivals: an open, global screen of GBIF for candidate first national
records of species that the Global Register of Introduced and Invasive Species
(GRIIS) flags as invasive in at least one country.

A (species, country) pair is a candidate when GBIF holds at least one record of
the species in that country dated 2025-2026, holds NO record of it there from any
earlier date (or undated), and no GRIIS checklist for that country lists it.

By MV2 of Munim, Inc. (mv2@munimtech.com). Made with AI agents. Python stdlib only.
See PREREGISTRATION.md for the hypotheses this run is graded against.
"""

import argparse
import collections
import csv
import http.client
import io
import json
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor

API = "https://api.gbif.org/v1"
UA = "invasive-arrivals/0.1 (MV2 of Munim, Inc.; mv2@munimtech.com)"
INAT_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
RECENT_YEARS = (2025, 2026)
SAMPLE_SEED = 20261117
SAMPLE_SIZE = 60
PROBE_NAME = "Halyomorpha halys"

BAD_ISSUES = frozenset({
    "ZERO_COORDINATE", "COORDINATE_INVALID", "COORDINATE_OUT_OF_RANGE",
    "COUNTRY_COORDINATE_MISMATCH", "COUNTRY_MISMATCH", "PRESUMED_SWAPPED_COORDINATE",
    "PRESUMED_NEGATED_LATITUDE", "PRESUMED_NEGATED_LONGITUDE",
    "COORDINATE_REPROJECTION_FAILED", "TAXON_MATCH_HIGHERRANK", "TAXON_MATCH_NONE",
    "TAXON_MATCH_FUZZY",
})
BAD_BASIS = frozenset({"LIVING_SPECIMEN", "FOSSIL_SPECIMEN"})
STRONG_BASIS = frozenset({"PRESERVED_SPECIMEN", "MATERIAL_SAMPLE", "MATERIAL_CITATION"})
BAD_ESTABLISHMENT = frozenset({"managed", "captive", "cultivated", "released",
                               "captivity", "domesticated"})
TRUTHY = frozenset({"yes", "y", "true", "1", "invasive"})
NOT_EPITHETS = frozenset({"sp", "spp", "ssp", "cf", "aff", "x"})
NO_COUNTRY = frozenset({"ZZ", "XZ", ""})


# ----------------------------------------------------------------- pure helpers

def local_term(term):
    """'http://rs.gbif.org/terms/1.0/isInvasive' -> 'isInvasive'."""
    if not term:
        return ""
    return term.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def _unescape(value, default):
    if value is None:
        return default
    return value.replace("\\t", "\t").replace("\\n", "\n").replace("\\r", "\r")


def _tag(el):
    return el.tag.rsplit("}", 1)[-1]


def parse_meta(xml_bytes):
    """Parse a Darwin Core Archive meta.xml into core and extension specs."""
    root = ET.fromstring(xml_bytes)

    def spec(el):
        loc = ""
        for x in el.iter():
            if _tag(x) == "location" and x.text:
                loc = x.text.strip()
                break
        fields, defaults, id_index = {}, {}, None
        for child in el:
            tag = _tag(child)
            if tag in ("id", "coreid"):
                id_index = int(child.get("index"))
            elif tag == "field":
                name = local_term(child.get("term", ""))
                if child.get("index") is not None:
                    fields[name] = int(child.get("index"))
                elif child.get("default") is not None:
                    defaults[name] = child.get("default")
        return {
            "rowType": local_term(el.get("rowType", "")),
            "location": loc,
            "delimiter": _unescape(el.get("fieldsTerminatedBy"), "\t"),
            "quote": _unescape(el.get("fieldsEnclosedBy"), ""),
            "ignore_header": int(el.get("ignoreHeaderLines", "0") or 0),
            "id_index": id_index,
            "fields": fields,
            "defaults": defaults,
        }

    core, exts = None, []
    for child in root:
        tag = _tag(child)
        if tag == "core":
            core = spec(child)
        elif tag == "extension":
            exts.append(spec(child))
    return {"core": core, "extensions": exts}


def read_table(zf, spec):
    """Read one DwC-A data file into a list of dicts keyed by local term names."""
    names = zf.namelist()
    name = spec["location"]
    if name not in names:
        by_base = {n.rsplit("/", 1)[-1]: n for n in names}
        name = by_base.get(name.rsplit("/", 1)[-1])
        if name is None:
            return []
    text = zf.read(name).decode("utf-8", errors="replace").lstrip(chr(0xFEFF))  # drop BOM
    delim = spec["delimiter"] if len(spec["delimiter"]) == 1 else "\t"
    if spec["quote"]:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim,
                            quotechar=spec["quote"])
    else:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delim,
                            quoting=csv.QUOTE_NONE)
    rows = []
    for i, row in enumerate(reader):
        if i < spec["ignore_header"] or not row or row == [""]:
            continue
        rec = dict(spec["defaults"])
        for term, idx in spec["fields"].items():
            if idx < len(row) and row[idx].strip() != "":
                rec[term] = row[idx].strip()
        if spec["id_index"] is not None and spec["id_index"] < len(row):
            rec["_id"] = row[spec["id_index"]].strip()
        rows.append(rec)
    return rows


def is_truthy(value):
    return (value or "").strip().lower() in TRUTHY


def parse_griis_archive(zip_bytes):
    """Return the taxa of one GRIIS checklist archive.

    Each taxon: taxon_id, scientific_name, kingdom, rank, invasive (bool),
    country_codes (set of ISO-2 codes from the Distribution extension).
    """
    zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    meta_name = next((n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "meta.xml"), None)
    if meta_name is None:
        raise ValueError("archive has no meta.xml")
    meta = parse_meta(zf.read(meta_name))
    if meta["core"] is None:
        raise ValueError("meta.xml has no core")
    taxa = {}
    for rec in read_table(zf, meta["core"]):
        tid = rec.get("_id") or rec.get("taxonID")
        if not tid:
            continue
        taxa[tid] = {
            "taxon_id": tid,
            "scientific_name": rec.get("scientificName", ""),
            "kingdom": rec.get("kingdom", ""),
            "rank": rec.get("taxonRank", ""),
            "invasive": is_truthy(rec.get("isInvasive")),
            "country_codes": set(),
        }
    for ext in meta["extensions"]:
        row_type = ext["rowType"].lower()
        if row_type not in ("speciesprofile", "distribution"):
            continue
        for rec in read_table(zf, ext):
            taxon = taxa.get(rec.get("_id"))
            if taxon is None:
                continue
            if is_truthy(rec.get("isInvasive")):
                taxon["invasive"] = True
            if row_type == "distribution":
                cc = (rec.get("countryCode") or "").strip().upper()
                if len(cc) == 2 and cc.isalpha():
                    taxon["country_codes"].add(cc)
    return list(taxa.values())


def binomial(name):
    """Lower-case 'genus epithet' of a scientific name, or '' if there is none."""
    toks = [t for t in re.split(r"\s+", (name or "").strip())
            if t and t not in ("×", "x", "X")]
    if len(toks) < 2:
        return ""
    genus, epithet = toks[0], toks[1]
    if not genus[:1].isupper() or not re.fullmatch(r"[a-z][a-z\-]+", epithet):
        return ""
    if epithet in NOT_EPITHETS:
        return ""
    return (genus + " " + epithet).lower()


def norm_country(name):
    return re.sub(r"[^a-z]", "", (name or "").lower())


def country_from_title(title, name_to_iso):
    """'GRIIS Checklist of ... - Mongolia' -> 'MN' (via the GBIF country names)."""
    parts = re.split(r"\s+[-–—]\s+", title or "")
    if len(parts) < 2:
        return ""
    return name_to_iso.get(norm_country(parts[-1]), "")


def checklist_country(taxa, title, name_to_iso):
    """Most common Distribution countryCode in the checklist, else from its title."""
    counts = collections.Counter()
    for t in taxa:
        for cc in t["country_codes"]:
            counts[cc] += 1
    if counts:
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return country_from_title(title, name_to_iso)


def parse_facet(resp):
    """GBIF occurrence search response -> {ISO-2 country: count}."""
    for facet in (resp or {}).get("facets") or []:
        if str(facet.get("field", "")).upper() == "COUNTRY":
            return {str(c["name"]).upper(): int(c["count"]) for c in facet.get("counts") or []}
    return {}


def candidate_countries(all_counts, recent_counts, known=()):
    """Countries where every GBIF record of the species is from the recent window."""
    out = []
    for country, recent in sorted(recent_counts.items()):
        if recent <= 0 or country in NO_COUNTRY or country in known:
            continue
        if all_counts.get(country, 0) == recent:
            out.append(country)
    return out


def concept(value):
    if isinstance(value, dict):
        value = value.get("concept") or value.get("name") or ""
    return str(value or "").strip().lower()


def qualifies(rec):
    """A recent, present, wild-looking, well-georeferenced record."""
    if str(rec.get("occurrenceStatus") or "PRESENT").upper() != "PRESENT":
        return False
    if str(rec.get("basisOfRecord") or "").upper() in BAD_BASIS:
        return False
    if rec.get("decimalLatitude") is None or rec.get("decimalLongitude") is None:
        return False
    if BAD_ISSUES.intersection(rec.get("issues") or []):
        return False
    if concept(rec.get("establishmentMeans")) in BAD_ESTABLISHMENT:
        return False
    if concept(rec.get("degreeOfEstablishment")) in BAD_ESTABLISHMENT:
        return False
    year = rec.get("year")
    try:
        return year is not None and int(year) in RECENT_YEARS
    except (TypeError, ValueError):
        return False


def is_strong(rec):
    """Qualifying and checkable: it has media, or it is a specimen or sample."""
    if not qualifies(rec):
        return False
    return bool(rec.get("media")) or str(rec.get("basisOfRecord") or "").upper() in STRONG_BASIS


def parse_match(resp):
    """GBIF name match (v1 or v2 response) -> accepted species info, or None."""
    if not resp:
        return None
    if "usage" in resp or "diagnostics" in resp:
        diag = resp.get("diagnostics") or {}
        match_type = str(diag.get("matchType") or "").upper()
        conf = diag.get("confidence") or 0
        ranks = {str(c.get("rank", "")).upper(): c for c in resp.get("classification") or []}
        species = ranks.get("SPECIES")
        if not _match_ok(match_type, conf) or not species or species.get("key") is None:
            return None
        return {"species_key": str(species.get("key")), "species": species.get("name", ""),
                "kingdom": (ranks.get("KINGDOM") or {}).get("name", ""),
                "class": (ranks.get("CLASS") or {}).get("name", ""),
                "match_type": match_type}
    match_type = str(resp.get("matchType") or "").upper()
    conf = resp.get("confidence") or 0
    if not _match_ok(match_type, conf) or resp.get("speciesKey") is None:
        return None
    return {"species_key": str(resp.get("speciesKey")), "species": resp.get("species", ""),
            "kingdom": resp.get("kingdom", ""), "class": resp.get("class", ""),
            "match_type": match_type}


def _match_ok(match_type, conf):
    if match_type in ("EXACT", "VARIANT"):
        return conf >= 90
    if match_type == "FUZZY":
        return conf >= 95
    return False


def draw_sample(pairs, k=SAMPLE_SIZE, seed=SAMPLE_SEED):
    """Pre-registered verification sample: sort by (species_key, country), then sample."""
    ordered = sorted(pairs, key=lambda p: (str(p["species_key"]), p["country"]))
    return random.Random(seed).sample(ordered, min(k, len(ordered)))


def summarise_pair(species, country, records):
    """Turn the GBIF records of one candidate pair into one output row (no personal data)."""
    qual = [r for r in records if qualifies(r)]
    strong = [r for r in qual if is_strong(r)]
    datasets = collections.Counter(str(r.get("datasetKey", "")) for r in qual)
    dated = sorted(qual, key=lambda r: str(r.get("eventDate") or "9999"))
    first = dated[0] if dated else {}
    lat, lon = first.get("decimalLatitude"), first.get("decimalLongitude")
    return {
        "species_key": species["species_key"],
        "species": species["species"],
        "kingdom": species["kingdom"],
        "class": species["class"],
        "country": country,
        "recent_records": len(records),
        "qualifying_records": len(qual),
        "strong_records": len(strong),
        "strength": "strong" if strong else ("weak" if qual else "none"),
        "first_qualifying_date": str(first.get("eventDate") or "")[:10],
        "first_lat_1dp": "" if lat is None else round(float(lat), 1),
        "first_lon_1dp": "" if lon is None else round(float(lon), 1),
        "has_inaturalist": any(str(r.get("datasetKey")) == INAT_DATASET for r in qual),
        "datasets": ";".join(f"{k}:{v}" for k, v in datasets.most_common(5)),
        "example_occurrences": ";".join(
            f"https://www.gbif.org/occurrence/{r.get('key')}" for r in (strong or qual)[:5]),
        "griis_invasive_in": ";".join(sorted(species.get("invasive_in", ()))),
        "griis_invasive_in_count": len(species.get("invasive_in", ())),
        "griis_listed_count": len(species.get("listed_in", ())),
        "gbif_search_url": (f"https://www.gbif.org/occurrence/search?taxon_key="
                            f"{species['species_key']}&country={country}"),
    }


# ----------------------------------------------------------------- network layer

class Http:
    """Polite, rate-limited GBIF client with retries."""

    def __init__(self, min_interval=0.2, tries=5):
        self.min_interval = min_interval
        self.tries = tries
        self.lock = threading.Lock()
        self.next_t = 0.0
        self.calls = 0
        self.failures = 0

    def get(self, url, binary=False, timeout=90):
        for attempt in range(self.tries):
            with self.lock:
                now = time.monotonic()
                wait = self.next_t - now
                self.next_t = max(now, self.next_t) + self.min_interval
            if wait > 0:
                time.sleep(wait)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = resp.read()
                with self.lock:
                    self.calls += 1
                return data if binary else json.loads(data.decode("utf-8"))
            except urllib.error.HTTPError as err:
                if err.code in (400, 404):
                    with self.lock:
                        self.failures += 1
                    return None
                time.sleep(min(60, 2 ** attempt * 2))
            except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError):
                time.sleep(min(60, 2 ** attempt * 2))
        with self.lock:
            self.failures += 1
        return None


def list_griis_datasets(http):
    found, seen, offset = [], set(), 0
    while True:
        q = urllib.parse.urlencode({"q": "GRIIS", "type": "CHECKLIST", "limit": 200, "offset": offset})
        resp = http.get(f"{API}/dataset/search?{q}")
        if not resp or not resp.get("results"):
            break
        for d in resp["results"]:
            title = d.get("title", "")
            if ("GRIIS" in title or "Global Register of Introduced and Invasive Species" in title) \
                    and d.get("key") not in seen:
                seen.add(d["key"])
                found.append({"key": d["key"], "title": title})
        if resp.get("endOfRecords", True):
            break
        offset += 200
    return found


def fetch_checklist(http, ds):
    meta = http.get(f"{API}/dataset/{ds['key']}")
    url = None
    for ep in (meta or {}).get("endpoints") or []:
        if ep.get("type") == "DWC_ARCHIVE":
            url = ep.get("url")
            break
    if not url:
        return ds, None, "no DWC_ARCHIVE endpoint"
    blob = http.get(url, binary=True, timeout=180)
    if not blob:
        return ds, None, "download failed"
    try:
        return ds, parse_griis_archive(blob), ""
    except (ValueError, zipfile.BadZipFile, ET.ParseError) as err:
        return ds, None, f"parse failed: {err}"


def match_name(http, name, kingdom):
    params = {"name": name, "verbose": "false"}
    if kingdom:
        params["kingdom"] = kingdom
    resp = http.get(f"{API}/species/match?{urllib.parse.urlencode(params)}")
    if resp is None:
        q = {"scientificName": name}
        if kingdom:
            q["kingdom"] = kingdom
        resp = http.get(f"https://api.gbif.org/v2/species/match?{urllib.parse.urlencode(q)}")
    return parse_match(resp)


def country_facets(http, species_key, recent):
    params = {"taxonKey": species_key, "facet": "country", "facetLimit": 400, "limit": 0}
    if recent:
        params["year"] = f"{RECENT_YEARS[0]},{RECENT_YEARS[-1]}"
    resp = http.get(f"{API}/occurrence/search?{urllib.parse.urlencode(params)}")
    if resp is None:
        return None
    return parse_facet(resp)


def pair_records(http, species_key, country):
    params = {"taxonKey": species_key, "country": country, "limit": 300}
    resp = http.get(f"{API}/occurrence/search?{urllib.parse.urlencode(params)}")
    return (resp or {}).get("results") or []


# ----------------------------------------------------------------- pipeline

def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def log(out_dir, msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    with open(f"{out_dir}/run_log.txt", "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run(out_dir, workers=4, max_species=0, min_interval=0.2):
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    http = Http(min_interval=min_interval)
    summary = {"started": started, "recent_years": list(RECENT_YEARS),
               "sample_seed": SAMPLE_SEED, "sample_size": SAMPLE_SIZE}

    # 0. probe: the facet API must behave as assumed, or we stop.
    probe = match_name(http, PROBE_NAME, "Animalia")
    probe_facets = country_facets(http, probe["species_key"], recent=False) if probe else None
    summary["probe"] = {"name": PROBE_NAME, "match": probe,
                        "countries_all_time": len(probe_facets or {})}
    if not probe or not probe_facets or len(probe_facets) < 10:
        summary["error"] = "probe failed: GBIF match or facet API not as expected"
        json.dump(summary, open(f"{out_dir}/summary.json", "w"), indent=2)
        log(out_dir, summary["error"])
        return 2

    # 1. GRIIS checklists -> invasive names and per-country listed names.
    countries = http.get(f"{API}/enumeration/country") or []
    name_to_iso = {}
    for c in countries:
        for key in ("title", "enumName"):
            if c.get(key) and c.get("iso2"):
                name_to_iso[norm_country(c[key])] = c["iso2"]
    datasets = list_griis_datasets(http)
    log(out_dir, f"GRIIS checklist datasets: {len(datasets)}")
    listed = collections.defaultdict(set)        # country -> binomials listed there
    invasive = {}                                # binomial -> name, kingdom, invasive_in
    checklist_rows, failures = [], []
    with ThreadPoolExecutor(workers) as pool:
        for ds, taxa, err in pool.map(lambda d: fetch_checklist(http, d), datasets):
            if taxa is None:
                failures.append({"key": ds["key"], "title": ds["title"], "error": err})
                continue
            cc = checklist_country(taxa, ds["title"], name_to_iso)
            n_inv = 0
            for t in taxa:
                b = binomial(t["scientific_name"])
                if not b:
                    continue
                if cc:
                    listed[cc].add(b)
                if t["invasive"]:
                    n_inv += 1
                    entry = invasive.setdefault(b, {"name": t["scientific_name"],
                                                    "kingdom": t["kingdom"], "invasive_in": set()})
                    if cc:
                        entry["invasive_in"].add(cc)
            checklist_rows.append({"key": ds["key"], "title": ds["title"], "country": cc,
                                   "taxa": len(taxa), "invasive_flagged": n_inv})
    write_csv(f"{out_dir}/griis_checklists.csv", checklist_rows,
              ["key", "title", "country", "taxa", "invasive_flagged"])
    summary["griis"] = {"datasets_found": len(datasets), "parsed": len(checklist_rows),
                        "failed": failures, "countries": len({r["country"] for r in checklist_rows if r["country"]}),
                        "invasive_binomials": len(invasive)}
    log(out_dir, f"parsed {len(checklist_rows)} checklists; {len(invasive)} invasive-flagged binomials")

    # 2. Match invasive names to GBIF accepted species.
    species = {}
    names = sorted(invasive)
    with ThreadPoolExecutor(workers) as pool:
        matches = list(pool.map(lambda b: match_name(http, invasive[b]["name"], invasive[b]["kingdom"]), names))
    unmatched = 0
    for b, m in zip(names, matches):
        if m is None:
            unmatched += 1
            continue
        sp = species.setdefault(m["species_key"], dict(m, binomials=set(), invasive_in=set(), listed_in=set()))
        sp["binomials"].add(b)
        sp["invasive_in"] |= invasive[b]["invasive_in"]
    for sp in species.values():
        sp["binomials"].add(binomial(sp["species"]) or "")
        for cc, names_there in listed.items():
            if sp["binomials"] & names_there:
                sp["listed_in"].add(cc)
        sp["listed_in"] |= sp["invasive_in"]
    summary["species"] = {"matched": len(species), "unmatched_names": unmatched}
    write_csv(f"{out_dir}/target_species.csv",
              [dict(s, invasive_in=";".join(sorted(s["invasive_in"])),
                    listed_in=";".join(sorted(s["listed_in"])),
                    binomials=";".join(sorted(x for x in s["binomials"] if x)))
               for s in species.values()],
              ["species_key", "species", "kingdom", "class", "match_type",
               "invasive_in", "listed_in", "binomials"])
    log(out_dir, f"matched {len(species)} accepted species ({unmatched} names unmatched)")

    keys = sorted(species, key=lambda k: (species[k]["kingdom"], species[k]["species"]))
    if max_species:
        keys = keys[:max_species]

    # 3. Country facets, all time vs recent.
    def facets(key):
        return key, country_facets(http, key, False), country_facets(http, key, True)

    pairs, facet_failures = [], 0
    with ThreadPoolExecutor(workers) as pool:
        for i, (key, all_c, rec_c) in enumerate(pool.map(facets, keys)):
            if all_c is None or rec_c is None:
                facet_failures += 1
                continue
            for cc in candidate_countries(all_c, rec_c, species[key]["listed_in"]):
                pairs.append((key, cc))
            if i % 500 == 0:
                log(out_dir, f"facets {i}/{len(keys)}; raw candidate pairs so far {len(pairs)}")
    summary["facets"] = {"species_screened": len(keys), "failures": facet_failures,
                         "raw_candidate_pairs": len(pairs)}
    log(out_dir, f"raw candidate pairs: {len(pairs)}")

    # 4. Records of each candidate pair.
    rows = []
    with ThreadPoolExecutor(workers) as pool:
        for (key, cc), recs in zip(pairs, pool.map(lambda p: pair_records(http, *p), pairs)):
            rows.append(summarise_pair(species[key], cc, recs))
    fields = list(summarise_pair({"species_key": "", "species": "", "kingdom": "", "class": ""},
                                 "", []).keys())
    rows.sort(key=lambda r: (r["strength"] != "strong", r["kingdom"], r["species"], r["country"]))
    write_csv(f"{out_dir}/candidates.csv", [r for r in rows if r["strength"] != "none"], fields)
    strong = [r for r in rows if r["strength"] == "strong"]
    sample = draw_sample(strong)
    write_csv(f"{out_dir}/verification_sample.csv",
              [dict(r, sample_index=i) for i, r in enumerate(sample)], ["sample_index"] + fields)

    # 5. Pre-registered quantities.
    kingdoms = collections.Counter(r["kingdom"] for r in strong)
    by_country = collections.Counter(r["country"] for r in strong)
    summary["results"] = {
        "pairs_with_qualifying_record": sum(1 for r in rows if r["strength"] != "none"),
        "H1_strong_pairs": len(strong),
        "H2_share_strong_with_inaturalist": (round(sum(r["has_inaturalist"] for r in strong) / len(strong), 4)
                                             if strong else None),
        "H3_strong_by_kingdom": dict(kingdoms.most_common()),
        "strong_species": len({r["species_key"] for r in strong}),
        "strong_top_countries": dict(by_country.most_common(15)),
        "verification_sample_size": len(sample),
    }
    summary["http"] = {"calls": http.calls, "failures": http.failures}
    summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(f"{out_dir}/summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=sorted)
    log(out_dir, "done: " + json.dumps(summary["results"]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max-species", type=int, default=0, help="screen only the first N species (testing)")
    ap.add_argument("--min-interval", type=float, default=0.2, help="seconds between API calls")
    args = ap.parse_args(argv)
    return run(args.out_dir, args.workers, args.max_species, args.min_interval)


if __name__ == "__main__":
    sys.exit(main())
