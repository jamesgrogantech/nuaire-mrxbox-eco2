#!/usr/bin/env python3
"""Diff two decode1200 snapshots to pinpoint which bytes changed between states.

    python3 tools/diff_frames.py captures/frame-clean-state-A.txt captures/frame-clean-state-B.txt

Parses lines like  '3B x7  : 3B 62 54 A6'  keyed by header byte, and reports
per-header byte differences. Byte positions that change = the field that the
stimulus (boost / humidity / speed) controls.
"""
import sys
import re


def parse(path):
    out = {}
    for ln in open(path):
        m = re.match(r"\s*([0-9A-Fa-f]{2})\s+x\d+\s*:\s*([0-9A-Fa-f ]+)", ln)
        if m:
            hdr = int(m.group(1), 16)
            body = [int(x, 16) for x in m.group(2).split()]
            out[hdr] = body
    return out


a = parse(sys.argv[1])
b = parse(sys.argv[2])
la, lb = sys.argv[1], sys.argv[2]
print("# diff  A=%s  B=%s" % (la, lb))
any_change = False
for hdr in sorted(set(a) | set(b)):
    if hdr not in a:
        print("%02X : only in B" % hdr); any_change = True; continue
    if hdr not in b:
        print("%02X : only in A" % hdr); any_change = True; continue
    va, vb = a[hdr], b[hdr]
    if va == vb:
        continue
    any_change = True
    diffs = []
    for i in range(max(len(va), len(vb))):
        x = va[i] if i < len(va) else None
        y = vb[i] if i < len(vb) else None
        if x != y:
            diffs.append("pos%d %02X->%02X" % (i, x if x is not None else 0,
                                               y if y is not None else 0))
    print("%02X : %s   |   A=%s  B=%s" % (
        hdr, "  ".join(diffs),
        " ".join("%02X" % v for v in va),
        " ".join("%02X" % v for v in vb)))
if not any_change:
    print("# no differences — states identical")
