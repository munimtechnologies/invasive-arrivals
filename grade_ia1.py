#!/usr/bin/env python3
# Copyright 2026 Munim, Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use
# this file except in compliance with the License. You may obtain a copy at
# http://www.apache.org/licenses/LICENSE-2.0
"""grade_ia1: the grader for the invasive-arrivals IA-1 screen, published before the
screen has produced any output.

It grades H1-H3 (PREREGISTRATION.md) from the screen's own output files, checks that
summary.json agrees with candidates.csv, re-draws the pre-registered 60-pair
verification sample from candidates.csv to prove it reproduces, and grades V1-V2 from
the hand-verification sheet, together with the descriptive measures of ADDENDUM-1.
The rules it applies are written out in IA1-GRADING-RULES.md.

By MV2 of Munim, Inc. (mv2@munimtech.com). Made with AI agents. Python stdlib only.

Usage:
  python grade_ia1.py --run-dir out                      # grade H1-H3, check the sample
  python grade_ia1.py --run-dir out --make-sheet results/ia-1/verification.csv
  python grade_ia1.py --run-dir out --verification results/ia-1/verification.csv \
      --json-out results/ia-1/grading.json
"""

import argparse
import csv
import datetime
import json
import statistics
import sys

from arrivals import draw_sample

H1_LOW, H1_HIGH = 200, 4000           # strong pairs, inclusive
H2_MIN_PCT = 50                       # % of strong pairs with an iNat research-grade record
V1_MIN_PCT = 15                       # % of sample in class 5 (plausible new arrival)
V2_MAX_PCT = 40                       # % of sample in class 1 (native)
MAX_FACET_FAILURE_PCT = 2             # completeness rule (IA1-GRADING-RULES.md)
CLASS_LABELS = {1: "native", 2: "already reported", 3: "not wild",
                4: "doubtful identity or place", 5: "plausible new arrival"}
SHEET_EXTRA = ["class", "class_label", "class_source_url", "first_strong_event_date",
               "first_public_report_date", "first_public_report_url", "later_confirmed",
               "changed_by_addendum1", "notes"]


def truthy(value):
    return str(value).strip().lower() in ("true", "1", "yes")


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def pct_at_least(count, n, pct):
    """count / n >= pct / 100, in exact integer arithmetic."""
    return n > 0 and count * 100 >= pct * n


def pct_at_most(count, n, pct):
    return n > 0 and count * 100 <= pct * n


def completeness(summary):
    """Is this a complete run in the sense of IA1-GRADING-RULES.md section 1?"""
    problems = []
    if summary.get("error"):
        problems.append("run error: " + str(summary["error"]))
    if not summary.get("finished"):
        problems.append("summary.json has no 'finished' time")
    facets = summary.get("facets") or {}
    screened = int(facets.get("species_screened") or 0)
    matched = int((summary.get("species") or {}).get("matched") or 0)
    if screened == 0:
        problems.append("no species screened")
    elif matched and screened != matched:
        problems.append(f"only {screened} of {matched} matched species screened (--max-species cap)")
    failures = int(facets.get("failures") or 0)
    if screened and failures * 100 > MAX_FACET_FAILURE_PCT * screened:
        problems.append(f"facet failures {failures} of {screened} exceed {MAX_FACET_FAILURE_PCT}%")
    if "results" not in summary:
        problems.append("summary.json has no results block")
    return {"complete": not problems, "problems": problems}


def grade_screen(summary, candidate_rows):
    """H1-H3 from summary.json, each re-derived from candidates.csv as a cross-check."""
    res = summary.get("results") or {}
    strong = [r for r in candidate_rows if r.get("strength") == "strong"]
    n = len(strong)
    inat = sum(1 for r in strong if truthy(r.get("has_inaturalist")))
    kingdoms = {}
    for r in strong:
        kingdoms[r.get("kingdom", "")] = kingdoms.get(r.get("kingdom", ""), 0) + 1
    plantae, animalia = kingdoms.get("Plantae", 0), kingdoms.get("Animalia", 0)

    checks = []
    if res.get("H1_strong_pairs") is not None and int(res["H1_strong_pairs"]) != n:
        checks.append(f"H1: summary says {res['H1_strong_pairs']} strong pairs, candidates.csv has {n}")
    share = res.get("H2_share_strong_with_inaturalist")
    if share is not None and n and abs(float(share) - inat / n) > 0.0001:
        checks.append(f"H2: summary share {share} differs from candidates.csv {inat}/{n}")
    by_k = {str(k): int(v) for k, v in (res.get("H3_strong_by_kingdom") or {}).items()}
    if by_k and by_k != kingdoms:
        checks.append(f"H3: summary kingdoms {by_k} differ from candidates.csv {kingdoms}")

    def verdict(ok):
        return "PASS" if ok else "FAIL"

    return {
        "strong_pairs": n,
        "H1": {"value": n, "rule": f"{H1_LOW} <= strong pairs <= {H1_HIGH}",
               "verdict": verdict(H1_LOW <= n <= H1_HIGH)},
        "H2": {"value": f"{inat}/{n}", "share": round(inat / n, 4) if n else None,
               "rule": f"share with an iNaturalist research-grade record >= {H2_MIN_PCT}%",
               "verdict": verdict(pct_at_least(inat, n, H2_MIN_PCT))},
        "H3": {"value": {"Plantae": plantae, "Animalia": animalia}, "all_kingdoms": kingdoms,
               "rule": "Plantae strong pairs > Animalia strong pairs",
               "verdict": verdict(plantae > animalia)},
        "consistency_problems": checks,
    }


def check_sample(candidate_rows, sample_rows):
    """Re-draw the registered sample from candidates.csv and compare, in order."""
    strong = [r for r in candidate_rows if r.get("strength") == "strong"]
    redrawn = [(str(r["species_key"]), r["country"]) for r in draw_sample(strong)]
    given = [(str(r["species_key"]), r["country"])
             for r in sorted(sample_rows, key=lambda r: int(r["sample_index"]))]
    return {"reproduces": redrawn == given, "size": len(given), "expected_size": len(redrawn)}


def make_sheet(sample_rows, path):
    """Write an empty hand-verification sheet, one row per sampled pair."""
    rows = sorted(sample_rows, key=lambda r: int(r["sample_index"]))
    base = ["sample_index", "species_key", "species", "kingdom", "class", "country",
            "first_qualifying_date", "example_occurrences", "gbif_search_url"]
    fields = base[:4] + ["taxon_class"] + base[5:] + SHEET_EXTRA
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = {k: r.get(k, "") for k in base if k != "class"}
            out["taxon_class"] = r.get("class", "")
            w.writerow(out)
    return len(rows)


def parse_date(value):
    try:
        return datetime.date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def early_verdict_at_least(count, done, n, pct):
    """Verdict on 'count/n >= pct%' once no remaining classification can change it."""
    remaining = n - done
    if pct_at_least(count, n, pct):
        return "PASS"
    if not pct_at_least(count + remaining, n, pct):
        return "FAIL"
    return "OPEN"


def early_verdict_at_most(count, done, n, pct):
    remaining = n - done
    if not pct_at_most(count, n, pct):
        return "FAIL"
    if pct_at_most(count + remaining, n, pct):
        return "PASS"
    return "OPEN"


def grade_verification(sample_rows, sheet_rows):
    """V1-V2 and the ADDENDUM-1 descriptives from the hand-verification sheet."""
    sample = {int(r["sample_index"]): (str(r["species_key"]), r["country"]) for r in sample_rows}
    n = len(sample)
    problems, classes, seen = [], {}, set()
    for r in sheet_rows:
        try:
            idx = int(r.get("sample_index", ""))
        except ValueError:
            problems.append(f"bad sample_index {r.get('sample_index')!r}")
            continue
        if idx not in sample:
            problems.append(f"sample_index {idx} is not in the sample")
            continue
        if (str(r.get("species_key")), r.get("country")) != sample[idx]:
            problems.append(f"sample_index {idx}: species/country do not match the sample")
            continue
        if idx in seen:
            problems.append(f"sample_index {idx} appears twice")
            continue
        seen.add(idx)
        cls = str(r.get("class", "")).strip()
        if cls == "":
            continue
        if cls not in ("1", "2", "3", "4", "5"):
            problems.append(f"sample_index {idx}: class {cls!r} is not 1-5")
            continue
        classes[idx] = (int(cls), r)

    done = len(classes)
    counts = {c: sum(1 for v, _ in classes.values() if v == c) for c in CLASS_LABELS}
    final = done == n and not problems
    v1 = early_verdict_at_least(counts[5], done, n, V1_MIN_PCT)
    v2 = early_verdict_at_most(counts[1], done, n, V2_MAX_PCT)

    plausible = [r for c, r in classes.values() if c == 5]
    later = [r for r in plausible if truthy(r.get("later_confirmed"))]
    lags = []
    for _, r in classes.values():
        a, b = parse_date(r.get("first_strong_event_date")), parse_date(r.get("first_public_report_date"))
        if a and b:
            lags.append((b - a).days)
    changed = sum(1 for _, r in classes.values() if truthy(r.get("changed_by_addendum1")))
    return {
        "sample_size": n, "classified": done, "final": final, "problems": problems,
        "counts": {CLASS_LABELS[c]: counts[c] for c in CLASS_LABELS},
        "V1": {"value": f"{counts[5]}/{n}", "rule": f"class 5 share >= {V1_MIN_PCT}%",
               "verdict": v1},
        "V2": {"value": f"{counts[1]}/{n}", "rule": f"class 1 share <= {V2_MAX_PCT}%",
               "verdict": v2},
        "addendum1": {
            "class5_later_confirmed": f"{len(later)}/{len(plausible)}",
            "event_to_report_days_n": len(lags),
            "event_to_report_days_median": statistics.median(lags) if lags else None,
            "event_to_report_days_range": [min(lags), max(lags)] if lags else None,
            "pairs_changed_by_first_strong_record_rule": changed,
        },
    }


def report_markdown(result):
    lines = ["# IA-1 grading (grade_ia1.py)", ""]
    comp = result["completeness"]
    lines.append("Run complete: " + ("yes" if comp["complete"] else
                                     "NO (" + "; ".join(comp["problems"]) + ")"))
    s = result["screen"]
    for h in ("H1", "H2", "H3"):
        lines.append(f"- {h}: {s[h]['verdict']} ({s[h]['value']}; rule: {s[h]['rule']})")
    for p in s["consistency_problems"]:
        lines.append(f"- consistency problem: {p}")
    smp = result["sample_check"]
    lines.append(f"- verification sample reproduces from candidates.csv: "
                 f"{'yes' if smp['reproduces'] else 'NO'} ({smp['size']} pairs)")
    v = result.get("verification")
    if v:
        state = "final" if v["final"] else f"{v['classified']} of {v['sample_size']} classified"
        lines.append(f"- verification ({state}): {v['counts']}")
        for k in ("V1", "V2"):
            lines.append(f"- {k}: {v[k]['verdict']} ({v[k]['value']}; rule: {v[k]['rule']})")
        lines.append(f"- ADDENDUM-1: {v['addendum1']}")
        for p in v["problems"]:
            lines.append(f"- sheet problem: {p}")
    return "\n".join(lines) + "\n"


def grade(run_dir, verification=None):
    with open(f"{run_dir}/summary.json", encoding="utf-8") as fh:
        summary = json.load(fh)
    cands = read_csv(f"{run_dir}/candidates.csv")
    sample = read_csv(f"{run_dir}/verification_sample.csv")
    result = {"completeness": completeness(summary), "screen": grade_screen(summary, cands),
              "sample_check": check_sample(cands, sample)}
    if verification:
        result["verification"] = grade_verification(sample, read_csv(verification))
    return result, sample


def main(argv=None):
    ap = argparse.ArgumentParser(description="Grade the IA-1 screen against PREREGISTRATION.md.")
    ap.add_argument("--run-dir", required=True, help="folder with summary.json, candidates.csv, "
                    "verification_sample.csv")
    ap.add_argument("--verification", help="hand-verification sheet (CSV)")
    ap.add_argument("--make-sheet", help="write an empty verification sheet here and stop")
    ap.add_argument("--json-out", help="also write the grading as JSON here")
    args = ap.parse_args(argv)
    result, sample = grade(args.run_dir, args.verification)
    if args.make_sheet:
        print(f"wrote {make_sheet(sample, args.make_sheet)} rows to {args.make_sheet}")
        return 0
    sys.stdout.write(report_markdown(result))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    ok = (result["completeness"]["complete"] and result["sample_check"]["reproduces"]
          and not result["screen"]["consistency_problems"])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
