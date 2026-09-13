#!/usr/bin/env python3
"""Capture the unit's repeating broadcast frame and print a canonical view.

Collects frames for a few seconds, keeps the most common length, and prints
the per-position MODE byte (the stable value) plus which positions vary.
Use to diff the frame between unit states (rest vs boost vs high humidity):
whichever byte positions change map to the thing you changed.

    PY=/opt/homebrew/Cellar/mpremote/1.29.0/libexec/bin/python
    $PY tools/capture_frame.py <port> <label> [baud] [secs]

Writes captures/frame-<label>.txt and prints the canonical frame.
"""
import sys
import time
from collections import Counter

import serial

port = sys.argv[1]
label = sys.argv[2]
baud = int(sys.argv[3]) if len(sys.argv) > 3 else 1990
secs = float(sys.argv[4]) if len(sys.argv) > 4 else 4.0

s = serial.Serial(port, baud, timeout=0.02)
end = time.time() + secs
frames, line, last = [], bytearray(), time.time()
while time.time() < end:
    c = s.read(256)
    now = time.time()
    if c:
        if line and now - last > 0.03:
            frames.append(bytes(line))
            line = bytearray()
        line += c
        last = now
    elif line and now - last > 0.03:
        frames.append(bytes(line))
        line = bytearray()
s.close()

if not frames:
    sys.exit("no frames — bus silent or wrong baud")

L = Counter(len(f) for f in frames).most_common(1)[0][0]
grp = [f for f in frames if len(f) == L]
canon = bytearray(L)
varies = []
for i in range(L):
    col = Counter(f[i] for f in grp)
    canon[i] = col.most_common(1)[0][0]
    if len(col) > 1:
        varies.append(i)

hexline = " ".join("%02X" % b for b in canon)
print("# label=%s baud=%d frames=%d len=%d (of %d captured)"
      % (label, baud, len(grp), L, len(frames)))
print("# canonical (mode) frame:")
print(hexline)
print("# varying positions:", varies)

with open("captures/frame-%s.txt" % label, "w") as fh:
    fh.write("# label=%s baud=%d frames=%d len=%d\n" % (label, baud, len(grp), L))
    fh.write(hexline + "\n")
    fh.write("# varying positions: %s\n" % varies)
    for f in grp:
        fh.write(" ".join("%02X" % b for b in f) + "\n")
print("# wrote captures/frame-%s.txt" % label)
