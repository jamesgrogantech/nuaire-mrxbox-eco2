#!/usr/bin/env python3
"""Analyse sniffer capture logs: frame stats, byte-position variance, checksum hunt.

Usage: python3 tools/analyze.py captures/<file>.log

Expects the main.py log format: lines of "<ms-timestamp> HH HH HH ...".
Lines starting with '#' are ignored.
"""

import sys
from collections import Counter


def parse(path):
    frames = []
    with open(path) as f:
        for raw in f:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split()
            try:
                ts = int(parts[0])
                data = bytes(int(x, 16) for x in parts[1:])
            except ValueError:
                continue
            if data:
                frames.append((ts, data))
    return frames


def crc16_modbus(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def crc8(data, poly):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def checksum_hunt(frames):
    """Test common checksums assuming they occupy the trailing byte(s)."""
    candidates = {
        "sum8 over frame[:-1]": lambda d: sum(d[:-1]) & 0xFF == d[-1],
        "sum8 two's-compl": lambda d: (-sum(d[:-1])) & 0xFF == d[-1],
        "xor over frame[:-1]": lambda d: _xor(d[:-1]) == d[-1],
        "crc8 poly 0x07": lambda d: crc8(d[:-1], 0x07) == d[-1],
        "crc8 poly 0x31": lambda d: crc8(d[:-1], 0x31) == d[-1],
        "crc16-modbus LE tail": lambda d: len(d) > 2
            and crc16_modbus(d[:-2]) == d[-2] | (d[-1] << 8),
        "crc16-modbus BE tail": lambda d: len(d) > 2
            and crc16_modbus(d[:-2]) == (d[-2] << 8) | d[-1],
    }
    total = len(frames)
    print("\n== checksum hunt (%d frames) ==" % total)
    for name, fn in candidates.items():
        hits = sum(1 for _, d in frames if len(d) >= 2 and fn(d))
        if hits:
            print("  %-24s %d/%d (%.0f%%)" % (name, hits, total, 100 * hits / total))
    print("  (no line above = zero hits for every candidate)")


def _xor(data):
    v = 0
    for b in data:
        v ^= b
    return v


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    frames = parse(sys.argv[1])
    if not frames:
        sys.exit("no frames parsed")

    print("== %d frames ==" % len(frames))
    lengths = Counter(len(d) for _, d in frames)
    print("lengths:", dict(sorted(lengths.items())))

    gaps = [b - a for (a, _), (b, _) in zip(frames, frames[1:])]
    if gaps:
        gaps.sort()
        print("inter-frame gap ms: min %d  median %d  max %d"
              % (gaps[0], gaps[len(gaps) // 2], gaps[-1]))

    first = Counter(d[0] for _, d in frames)
    print("first byte:", {"%02X" % k: v for k, v in first.most_common(8)})

    # Per-position variability for the most common frame length: constant
    # positions are headers/addresses, varying ones are data/checksum.
    common_len = lengths.most_common(1)[0][0]
    subset = [d for _, d in frames if len(d) == common_len]
    print("\n== byte positions, len=%d frames (%d of them) ==" % (common_len, len(subset)))
    for i in range(common_len):
        vals = Counter(d[i] for d in subset)
        top = " ".join("%02X:%d" % (k, v) for k, v in vals.most_common(4))
        tag = "CONST" if len(vals) == 1 else "%3d distinct" % len(vals)
        print("  [%2d] %-12s %s" % (i, tag, top))

    checksum_hunt(frames)

    print("\n== first 10 frames ==")
    for ts, d in frames[:10]:
        print("  %8d  %s" % (ts, d.hex(" ").upper()))


if __name__ == "__main__":
    main()
