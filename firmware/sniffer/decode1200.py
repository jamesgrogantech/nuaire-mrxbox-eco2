"""Clean-decode the MRXBOX broadcast at the confirmed 1200 baud 8N1.

Reads UART1 (RO->GP5), gap-splits the ~9 messages per ~0.7s cycle, groups them
by their header byte (each header appears once per cycle), and prints a
canonical (modal) message per header plus any byte positions that vary.

Run:  mpremote run firmware/sniffer/decode1200.py
Passive (no DE/DI use). Use to snapshot a unit STATE; diff snapshots across
boost / humidity to pinpoint fields.
"""
from machine import UART, Pin
import time

u = UART(1, baudrate=1200, bits=8, parity=None, stop=1, rx=Pin(5),
         timeout=0, rxbuf=512)

msgs = []          # list of (header, tuple(bytes))
line = []
last = time.ticks_us()
t0 = time.ticks_ms()
CAP_MS = 5000

while time.ticks_diff(time.ticks_ms(), t0) < CAP_MS:
    d = u.read()
    now = time.ticks_us()
    if d:
        if line and time.ticks_diff(now, last) > 15000:
            msgs.append(tuple(line)); line = []
        line.extend(d); last = now
    elif line and time.ticks_diff(now, last) > 15000:
        msgs.append(tuple(line)); line = []
if line:
    msgs.append(tuple(line))

# group by header (first byte); canonical = modal byte per position
from_headers = {}
for m in msgs:
    if not m:
        continue
    from_headers.setdefault(m[0], []).append(m)

print("# 1200 8N1 decode: %d messages, %d distinct headers, cap=%dms"
      % (len(msgs), len(from_headers), CAP_MS))
for hdr in sorted(from_headers):
    group = from_headers[hdr]
    # use the most common length
    lens = {}
    for m in group:
        lens[len(m)] = lens.get(len(m), 0) + 1
    L = max(lens, key=lens.get)
    g = [m for m in group if len(m) == L]
    canon = []
    varies = []
    for i in range(L):
        vals = {}
        for m in g:
            vals[m[i]] = vals.get(m[i], 0) + 1
        best = max(vals, key=vals.get)
        canon.append(best)
        if len(vals) > 1:
            varies.append(i)
    hexs = " ".join("%02X" % b for b in canon)
    tag = ("  varies@%s" % varies) if varies else ""
    print("%02X x%-2d : %s%s" % (hdr, len(group), hexs, tag))
