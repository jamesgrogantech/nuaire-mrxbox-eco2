#!/usr/bin/env python3
"""Gap-aware RS485 transmitter for the CH340 dongle (Phase 3 write-back probe).

Listens for the unit's ~0.7s broadcast, waits for the idle gap, transmits a
frame, then keeps listening to see if the unit reacts (its next broadcasts
change) — all via the dongle's auto-direction transceiver.

    PY=/opt/homebrew/Cellar/mpremote/1.29.0/libexec/bin/python
    $PY tools/rs485_tx.py <port> <hexbytes> [repeats]
    # e.g. replay the boost-OFF 21 message:
    $PY tools/rs485_tx.py /dev/cu.usbserial-11430 "21 AA F6 D6" 3

Bytes are sent RAW (exact replay reproduces the original wire waveform — no
bit-reversal). Transmits only inside a detected idle gap to avoid collisions.
This is the FIRST thing that drives the bus; it cannot damage the unit, and the
physical speed/boost switch overrides anything it does.
"""
import sys
import time

import serial

port = sys.argv[1]
frame = bytes(int(x, 16) for x in sys.argv[2].replace(",", " ").split())
repeats = int(sys.argv[3]) if len(sys.argv) > 3 else 1

BAUD = 1200
GAP_S = 0.12          # idle this long = safe to transmit into the gap

s = serial.Serial(port, BAUD, timeout=0.02)


def snapshot(secs):
    """Collect raw bytes for `secs`, return them."""
    end = time.time() + secs
    buf = bytearray()
    while time.time() < end:
        c = s.read(256)
        if c:
            buf += c
    return bytes(buf)


def wait_for_gap(timeout=2.0):
    """Block until the line has been idle >= GAP_S, or timeout."""
    last_rx = time.time()
    start = time.time()
    while time.time() - start < timeout:
        c = s.read(64)
        now = time.time()
        if c:
            last_rx = now
        elif now - last_rx >= GAP_S:
            return True
    return False


print("# BEFORE (2s of bus):")
before = snapshot(2.0)
print("  ", before.hex(" ").upper()[:200] or "(silence)")

print("# frame to send:", frame.hex(" ").upper())
for i in range(repeats):
    if wait_for_gap():
        s.write(frame)
        s.flush()
        print("# sent #%d in idle gap at t=%.2f" % (i + 1, time.time() % 100))
    else:
        print("# no idle gap found — skipped #%d" % (i + 1))
    time.sleep(0.35)

print("# AFTER (3s of bus — watch for changed broadcasts):")
after = snapshot(3.0)
print("  ", after.hex(" ").upper()[:400] or "(silence)")
s.close()
