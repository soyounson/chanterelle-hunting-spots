#!/usr/bin/env python3
"""Download GBIF Cantharellus records for Europe, the USA and Canada, remove duplicates,
and count them on the same 1 deg x 1.5 deg grid as chanterelle_grid.json.

Run on a Mac (Python 3, nothing to install):
    python3 fetch_dedup.py
Takes about 5-15 minutes. Writes chanterelle_grid_dedup.json next to this script.
Send that file back in the chat.

Duplicate rule: two records are the same find when they have the same species,
the same date (year, month, day), coordinates equal to 2 decimals (about 1 km)
and the same recorder name (case and spacing ignored). This catches one find
uploaded to two databases, for example a national atlas and iNaturalist.
"""
import json, os, re, time, urllib.parse, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

TAXON = 9623860
API = "https://api.gbif.org/v1/occurrence/search"
REGIONS = {
    "EU": ({"continent": "EUROPE"}, (34, 72), (-12, 42)),
    "US": ({"country": "US"}, (24, 50), (-126, -66)),
    "CA": ({"country": "CA"}, (41, 61), (-141, -51)),
}
FINE_LAT, FINE_LON = 1.0, 1.5
PAGE = 300
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chanterelle_grid_dedup.json")
BASE = {"taxonKey": TAXON, "hasCoordinate": "true", "hasGeospatialIssue": "false"}


def get(params):
    url = API + "?" + urllib.parse.urlencode(params)
    for i in range(6):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 * (i + 1))
    raise RuntimeError("GBIF did not answer: " + url)


def years(filt):
    d = get({**BASE, **filt, "limit": 0, "facet": "year", "facetLimit": 400})
    ys = [(int(c["name"]), c["count"]) for f in d.get("facets", []) for c in f["counts"]]
    total = d["count"]
    no_year = total - sum(n for _, n in ys)
    return ys, no_year


def fetch_slice(filt):
    """All records for one filter (one year, or the records without a year)."""
    out, off = [], 0
    while True:
        d = get({**BASE, **filt, "limit": PAGE, "offset": off})
        for r in d["results"]:
            out.append({k: r.get(k) for k in ("key", "speciesKey", "taxonKey", "decimalLatitude", "decimalLongitude",
                                               "year", "month", "day", "recordedBy", "datasetKey", "basisOfRecord")})
        off += PAGE
        if d.get("endOfRecords") or off >= d["count"] or off >= 99900:
            return out


def norm_name(s):
    return re.sub(r"[^a-z]", "", (s or "").lower()) or "?"


def main():
    t0 = time.time()
    result, summary = {}, {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for code, (filt, (la0, la1), (lo0, lo1)) in REGIONS.items():
            ys, no_year = years(filt)
            jobs = [{**filt, "year": y} for y, _ in ys]
            recs = [r for part in pool.map(fetch_slice, jobs) for r in part]
            # records without a year are only counted (GBIF search cannot page them by year)
            seen, kept = set(), []
            for r in recs:
                lat, lon = r["decimalLatitude"], r["decimalLongitude"]
                if lat is None or lon is None:
                    continue
                key = (r["speciesKey"] or r["taxonKey"], r["year"], r["month"], r["day"],
                       round(lat, 2), round(lon, 2), norm_name(r["recordedBy"]))
                if key in seen:
                    continue
                seen.add(key)
                kept.append(r)
            cells = defaultdict(lambda: {"n": 0, "mm": [0] * 12, "ym": defaultdict(int)})
            for r in kept:
                lat, lon = r["decimalLatitude"], r["decimalLongitude"]
                if not (la0 <= lat < la1 and lo0 <= lon < lo1):
                    continue
                a = la0 + int((lat - la0) // FINE_LAT) * FINE_LAT
                b = lo0 + int((lon - lo0) // FINE_LON) * FINE_LON
                c = cells[(round(a, 4), round(b, 4))]
                c["n"] += 1
                if r["month"]:
                    c["mm"][r["month"] - 1] += 1
                    if r["year"]:
                        c["ym"][f'{r["year"]}-{r["month"]:02d}'] += 1
            result[code] = [{"la0": a, "la1": round(a + FINE_LAT, 4), "lo0": b, "lo1": round(b + FINE_LON, 4),
                             "n": c["n"], "mm": c["mm"], "ym": dict(sorted(c["ym"].items()))}
                            for (a, b), c in sorted(cells.items())]
            summary[code] = {"downloaded": len(recs), "after_dedup": len(kept), "duplicates_removed": len(recs) - len(kept),
                             "records_without_year_not_downloaded": no_year, "cells": len(result[code])}
            print(code, summary[code], f"{time.time() - t0:.0f}s", flush=True)
    meta = {"source": "GBIF.org occurrence search API", "taxonKey": TAXON, "filters": BASE,
            "fetched": time.strftime("%Y-%m-%d"), "cell": [FINE_LAT, FINE_LON],
            "dedup_rule": "same species, year, month, day, lat/lon rounded to 0.01, recorder name",
            "summary": summary}
    with open(OUT, "w") as f:
        json.dump({"meta": meta, **result}, f, separators=(",", ":"))
    print("Saved", OUT, f"in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
