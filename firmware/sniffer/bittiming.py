"""Pico as a logic analyser: measure RS485 bit width via pulse timing.

PASSIVE ONLY — never drives the bus (DE stays low). Reads the MAX485 RO line
on GP5 and measures how long the line holds each level with time_pulse_us
(microsecond resolution). The shortest repeated pulse = one bit time; baud =
1e6 / bit_us. Works on the unit's ~0.7s broadcast bursts.

Wiring: MAX485 RO -> GP5, DE & /RE -> GND (receive-only), A/B/GND on the bus.
Run over USB (no persist, no transmit):  mpremote run firmware/sniffer/bittiming.py
"""
from machine import Pin, time_pulse_us
import time

RX = 5
TARGET = 4000          # pulses to collect
TIMEOUT_US = 1_000_000

pin = Pin(RX, Pin.IN)
print("# idle level:", pin.value(), "(1 = normal UART idle)")
print("# collecting up to", TARGET, "pulses (both levels)...")

widths = []
misses = 0
t0 = time.ticks_ms()
while len(widths) < TARGET and misses < 40 and time.ticks_diff(time.ticks_ms(), t0) < 20000:
    # measure whichever level comes next: catch both high and low runs
    for level in (0, 1):
        w = time_pulse_us(pin, level, TIMEOUT_US)
        if w > 0:
            widths.append(w)
        else:
            misses += 1

if not widths:
    print("# NO PULSES — bus quiet, or 3.3V receiver not detecting the signal.")
else:
    widths.sort()
    n = len(widths)
    p = lambda q: widths[min(n - 1, int(n * q))]
    print("# pulses:", n, " min:", widths[0], "us  p01:", p(0.01),
          " p05:", p(0.05), " median:", p(0.5), " max:", widths[-1])
    # bit time = smallest robust cluster (5th percentile dodges glitches)
    bit_us = p(0.02)
    print("# est bit time ~%d us -> ~%.0f baud" % (bit_us, 1_000_000 / bit_us))
    # histogram in units of the estimated bit time (expect peaks at 1,2,3... bits)
    hist = {}
    for w in widths:
        k = max(1, round(w / bit_us))
        hist[k] = hist.get(k, 0) + 1
    print("# pulse-width histogram (bit-multiples):")
    for k in sorted(hist)[:12]:
        print("#  %2d bit (%5d us): %d" % (k, k * bit_us, hist[k]))
