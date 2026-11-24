#!/usr/bin/env python3
"""Fast version: count GBIF Cantharellus records on a 1° x 1.5° grid (about 110 km),
with a month breakdown, for Europe, USA and Canada. No record download.

Run on a Mac (Python 3, nothing to install):
    python3 fetch_grid_fast.py
Takes about 1-3 minutes. Writes chanterelle_grid.json next to this script.
Send that file back in the chat.
"""
import json, os, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

TAXON = 9623860
REGIONS = {
    "EU": ({"continent": "EUROPE"}, (34, 72), (-12, 42)),
    "US": ({"country": "US"}, (24, 50), (-126, -66)),
    "CA": ({"country": "CA"}, (41, 61), (-141, -51)),
}
FINE_LAT, FINE_LON = 1.0, 1.5      # final cell size
COARSE = 4                         # coarse block = 4 x 4 fine cells, skipped if empty
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chanterelle_grid.json")


def count(filt, la0, la1, lo0, lo1, months=False):
    q = {"taxonKey": TAXON, "hasCoordinate": "true", "hasGeospatialIssue": "false",
         "decimalLatitude": f"{la0},{la1}", "decimalLongitude": f"{lo0},{lo1}", "limit": 0, **filt}
    if months:
        q.update({"facet": "month", "facetLimit": 12})
    url = "https://api.gbif.org/v1/occurrence/search?" + urllib.parse.urlencode(q)
    for i in range(6):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                d = json.load(r)
            mm = [0] * 12
            for f in d.get("facets", []):
                for c in f["counts"]:
                    mm[int(c["name"]) - 1] = c["count"]
            return d["count"], mm
        except Exception:
            time.sleep(2 * (i + 1))
    return None, None


def frange(a, b, step):
    x = a
    while x < b - 1e-9:
        yield round(x, 4)
        x += step


def main():
    t0 = time.time()
    out = {}
    with ThreadPoolExecutor(max_workers=16) as pool:
        for code, (filt, (la0, la1), (lo0, lo1)) in REGIONS.items():
            cl, co = FINE_LAT * COARSE, FINE_LON * COARSE
            blocks = [(a, a + cl, b, b + co) for a in frange(la0, la1, cl) for b in frange(lo0, lo1, co)]
            res = list(pool.map(lambda c: count(filt, *c), blocks))
            busy = [b for b, (n, _) in zip(blocks, res) if n]
            cells = [(a, round(a + FINE_LAT, 4), b, round(b + FINE_LON, 4))
                     for (A, A1, B, B1) in busy for a in frange(A, A1, FINE_LAT) for b in frange(B, B1, FINE_LON)]
            res = list(pool.map(lambda c: count(filt, *c, months=True), cells))
            rows = [{"la0": c[0], "la1": c[1], "lo0": c[2], "lo1": c[3], "n": n, "mm": mm}
                    for c, (n, mm) in zip(cells, res) if n]
            failed = sum(1 for n, _ in res if n is None)
            out[code] = rows
            print(f"{code}: {len(blocks)} blocks, {len(cells)} cells checked, {len(rows)} with records"
                  + (f", {failed} failed" if failed else ""))
    json.dump(out, open(OUT, "w"))
    print(f"Saved {OUT} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
