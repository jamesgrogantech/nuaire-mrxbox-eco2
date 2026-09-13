"""Baud-rate finder for an unknown UART/RS485 bus (Pico 2W, MicroPython).

Measures low-pulse widths on the RX pin (UART idles high; the narrowest pulse
on a busy line is one bit time) and reports the closest standard baud rate.

Wiring: MAX485 RO -> GP5, DE & /RE -> GND (receive-only).
Run:    mpremote run firmware/sniffer/baudfind.py
"""

from machine import Pin, time_pulse_us
import time

RX_PIN = 5
SAMPLES = 400
TIMEOUT_US = 2_000_000  # give up on a pulse after 2 s of silence

STANDARD_BAUDS = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 76800, 115200)


def collect_pulses(pin, n):
    widths = []
    misses = 0
    while len(widths) < n and misses < 5:
        # 0 = measure a low pulse (start bit / zero bits)
        w = time_pulse_us(pin, 0, TIMEOUT_US)
        if w < 0:
            misses += 1
            print("no pulse for 2s (bus quiet?), retry", misses)
            continue
        widths.append(w)
    return widths


def main():
    pin = Pin(RX_PIN, Pin.IN)
    idle = pin.value()
    print("RX idle level:", idle, "(1 expected for UART/RS485)")
    if idle == 0:
        print("WARNING: line idles low - polarity inverted or not UART. "
              "Check A/B swap on the MAX485.")

    print("collecting", SAMPLES, "low pulses...")
    widths = collect_pulses(pin, SAMPLES)
    if not widths:
        print("no traffic seen. Check wiring/tap point.")
        return

    widths.sort()
    # Shortest pulses cluster at one bit time; take the 5th percentile to
    # dodge the occasional glitch-shortened measurement.
    bit_us = widths[max(0, len(widths) // 20)]
    est = 1_000_000 / bit_us
    best = min(STANDARD_BAUDS, key=lambda b: abs(b - est))
    err = abs(best - est) / best * 100

    print("pulses:", len(widths),
          "min:", widths[0], "us  median:", widths[len(widths) // 2], "us")
    print("bit time ~%d us -> %.0f baud -> nearest standard: %d (%.1f%% off)"
          % (bit_us, est, best, err))
    if err > 5:
        print("WARNING: >5% off a standard rate - remeasure or suspect "
              "non-standard baud.")

    # Distribution helps sanity-check framing (expect multiples of bit time)
    print("pulse width histogram (us: count):")
    hist = {}
    for w in widths:
        bucket = round(w / bit_us)
        hist[bucket] = hist.get(bucket, 0) + 1
    for k in sorted(hist):
        print("  %2d bits (%5d us): %d" % (k, k * bit_us, hist[k]))


main()
