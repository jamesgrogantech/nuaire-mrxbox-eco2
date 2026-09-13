"""Bus sniffer (Pico 2W, MicroPython): dump raw bytes with inter-byte timing.

Prints timestamped hex over USB serial. A gap longer than GAP_US starts a new
line, so probable frame boundaries are visible immediately and the log feeds
straight into tools/analyze.py.

Wiring: MAX485 RO -> GP5 (UART1 RX), DE & /RE -> GND (receive-only).
Set BAUD from baudfind.py's result first.

Capture to file from the desktop:
    mpremote run firmware/sniffer/main.py | tee captures/$(date +%Y%m%d-%H%M)-idle-9600-8N1.log
"""

from machine import UART, Pin
import time

BAUD = 9600          # <-- set from baudfind.py
BITS, PARITY, STOP = 8, None, 1   # try 8N1 first, then parity=0 (even)
RX_PIN = 5
GAP_US = 3000        # silence >= this starts a new log line (tune: ~3.5 char times)

uart = UART(1, baudrate=BAUD, bits=BITS, parity=PARITY, stop=STOP,
            rx=Pin(RX_PIN), timeout=0, rxbuf=1024)

print("# sniffer baud=%d %d%s%d gap_us=%d t0_ms=%d"
      % (BAUD, BITS, "N" if PARITY is None else "E" if PARITY == 0 else "O",
         STOP, GAP_US, time.ticks_ms()))

line = []
last_byte_us = time.ticks_us()

while True:
    data = uart.read()
    now = time.ticks_us()
    if data:
        if line and time.ticks_diff(now, last_byte_us) >= GAP_US:
            print("%10d " % (time.ticks_ms()) + " ".join(line))
            line = []
        line.extend("%02X" % b for b in data)
        last_byte_us = now
    elif line and time.ticks_diff(now, last_byte_us) >= GAP_US:
        print("%10d " % (time.ticks_ms()) + " ".join(line))
        line = []
