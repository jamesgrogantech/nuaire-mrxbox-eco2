#!/usr/bin/env python3
"""Verify the per-message XOR checksum on 1200-baud decoded captures.

Finding (2026-09-16): XOR of every raw byte in a message (header, data bytes
AND the trailing byte) == 0xAB for all 9 broadcast messages, in every variant
captured so far. Equivalently the trailing byte is

    chk = 0xAB ^ hdr ^ d1 ^ d2 ^ ... ^ dN        (raw, UART LSB-first view)

or, in the unit's own MSB-first bit order (rev() every byte):

    chk = 0xD5 ^ hdr ^ d1 ^ ... ^ dN            (always < 0x80 -> 7-bit)

Usage: python3 tools/checksum_verify.py captures/*.log captures/*.txt
Accepts any file; it pulls out every run of 3..12 hex bytes that starts with a
known header byte (or, with --any, any run) and tests it.
"""
import re
import sys

HEADERS = {0x21, 0x11, 0x51, 0x31, 0x33, 0x85, 0xA3, 0x75, 0x3B}
HEX_RUN = re.compile(r"(?:\b[0-9A-Fa-f]{2}\b[ \t]*){3,12}")
CONST = 0xAB


def rev(b):
    return int("{:08b}".format(b)[::-1], 2)


def messages(path, any_hdr=False):
    seen = set()
    with open(path) as f:
        for line in f:
            if line.lstrip().startswith("#") and "raw" not in line:
                continue
            # strip everything after '|' (fulldump 'rev ...' decimals) and
            # keep only the raw hex segment
            if "raw" in line:
                line = line.split("raw", 1)[1].split("|", 1)[0]
            for m in HEX_RUN.finditer(line):
                data = bytes(int(x, 16) for x in m.group(0).split())
                if not any_hdr and data[0] not in HEADERS:
                    continue
                if data not in seen:
                    seen.add(data)
                    yield data


def main(argv):
    any_hdr = "--any" in argv
    paths = [a for a in argv if not a.startswith("--")]
    ok = bad = 0
    for p in paths:
        for msg in messages(p, any_hdr):
            x = 0
            for b in msg:
                x ^= b
            good = x == CONST
            ok += good
            bad += not good
            print("%s  %-32s xor=%02X  %s" % ("OK " if good else "BAD", msg.hex(" "), x, p))
    print("\n%d messages verified, %d failed" % (ok, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
