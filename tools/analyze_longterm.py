#!/usr/bin/env python3
"""Analyse a long-term nuaire_raw.csv (from tools/log_raw.sh) to decode fields.

Stdlib only (no pandas). For each of the 16 raw byte columns it reports how it
behaves and cross-correlates it against reference signals, so you can identify
what each unknown byte means:

  - variance / unique values / range  -> is it live data or a fixed value?
  - monotonic upward trend             -> a counter (run-hours, filter timer)
  - correlation with time-of-day       -> a temperature-like daily cycle
  - correlation with outdoor temp      -> the outdoor/intake sensor
                                          (fetched from open-meteo if lat/lon given)
  - correlation with the humidity col  -> humidity-linked field

Usage:
  python3 tools/analyze_longterm.py nuaire_raw.csv                 # no weather
  python3 tools/analyze_longterm.py nuaire_raw.csv 51.48 -0.10     # with lat lon

The lat/lon enable an open-meteo historical-temperature pull for the logged
period (needs internet); without them, time-of-day correlation still runs.
"""
import csv
import sys
import math
import statistics
import json
import datetime
import urllib.request

COLS = ["11_1","11_2","21_1","21_2","21_3","31_3","33_3","3B_1","3B_2","3B_3",
        "51_4","75_5","85_1","85_3","85_6","A3_7"]
KNOWN = {"21_2": "boost/fan (known)", "3B_1": "humidity % (known)",
         "33_3": "was mis-IDd as temp"}


def pearson(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(pairs) < 10:
        return None
    xs, ys = zip(*pairs)
    if len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else None


def load(path):
    rows = []
    with open(path) as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                t = int(float(row["unixtime"]))
            except (KeyError, ValueError):
                continue
            rec = {"t": t}
            for c in COLS:
                try:
                    v = int(row[c])
                    rec[c] = v if v >= 0 else None       # -1 = message missing
                except (KeyError, ValueError):
                    rec[c] = None
            rows.append(rec)
    return rows


def fetch_outdoor(lat, lon, t0, t1):
    d0 = datetime.datetime.utcfromtimestamp(t0).strftime("%Y-%m-%d")
    d1 = datetime.datetime.utcfromtimestamp(t1).strftime("%Y-%m-%d")
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=%s&longitude=%s"
           "&start_date=%s&end_date=%s&hourly=temperature_2m&timezone=UTC"
           % (lat, lon, d0, d1))
    with urllib.request.urlopen(url, timeout=30) as resp:
        j = json.load(resp)
    times = j["hourly"]["time"]
    temps = j["hourly"]["temperature_2m"]
    out = {}
    for ts, tp in zip(times, temps):
        dt = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M")
        out[int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())] = tp
    return out


def outdoor_for(rows, table):
    keys = sorted(table)
    res = []
    for r in rows:
        # nearest hour
        k = min(keys, key=lambda kk: abs(kk - r["t"])) if keys else None
        res.append(table[k] if k is not None and abs(k - r["t"]) < 5400 else None)
    return res


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    rows = load(sys.argv[1])
    if len(rows) < 20:
        sys.exit("need more data (only %d rows) - let the logger run longer" % len(rows))
    span_h = (rows[-1]["t"] - rows[0]["t"]) / 3600.0
    print("# %d rows over %.1f hours" % (len(rows), span_h))

    hod = [(math.sin(2 * math.pi * ((r["t"] % 86400) / 86400.0))) for r in rows]  # time-of-day
    hum = [r["3B_1"] for r in rows]

    outdoor = None
    if len(sys.argv) >= 4:
        try:
            tbl = fetch_outdoor(sys.argv[2], sys.argv[3], rows[0]["t"], rows[-1]["t"])
            outdoor = outdoor_for(rows, tbl)
            print("# outdoor temp fetched from open-meteo (%d hourly points)" % len(tbl))
        except Exception as e:
            print("# outdoor fetch failed:", e)

    print("\n%-6s %-22s %5s %5s %6s  %s" %
          ("col", "note", "uniq", "rng", "trend", "correlations"))
    for c in COLS:
        vals = [r[c] for r in rows]
        present = [v for v in vals if v is not None]
        if not present:
            print("%-6s %-22s  (never present)" % (c, KNOWN.get(c, "")))
            continue
        uniq = len(set(present))
        rng = max(present) - min(present)
        # monotonic upward fraction
        ups = sum(1 for a, b in zip(present, present[1:]) if b > a)
        downs = sum(1 for a, b in zip(present, present[1:]) if b < a)
        trend = "up" if ups > 3 * max(1, downs) and uniq > 3 else \
                ("dn" if downs > 3 * max(1, ups) and uniq > 3 else "-")
        cors = []
        if uniq > 1:
            r_hod = pearson(vals, hod)
            r_out = pearson(vals, outdoor) if outdoor else None
            r_hum = pearson(vals, hum) if c != "3B_1" else None
            if r_hod is not None and abs(r_hod) > 0.4:
                cors.append("time%+.2f" % r_hod)
            if r_out is not None and abs(r_out) > 0.4:
                cors.append("OUTDOOR%+.2f" % r_out)
            if r_hum is not None and abs(r_hum) > 0.4:
                cors.append("humidity%+.2f" % r_hum)
        tag = "CONST" if uniq == 1 else ""
        print("%-6s %-22s %5d %5d %6s  %s %s" %
              (c, KNOWN.get(c, ""), uniq, rng, trend, tag, "  ".join(cors)))

    print("\n# how to read: CONST = fixed value (not a sensor). trend up/dn = a")
    print("# counter. OUTDOOR+high = that byte IS the outdoor/intake temp. time+high")
    print("# = a daily-cycling temperature. humidity+high = humidity-linked.")


if __name__ == "__main__":
    main()
