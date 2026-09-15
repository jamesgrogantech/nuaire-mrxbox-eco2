# Full-frame dumper for the Nuaire MRXBOX bus (Pico W, MicroPython).
# Prints EVERY byte of EVERY broadcast message (raw hex + bit-reversed decimal),
# grouped into ~0.7s bursts. Use it to see the complete frame (not just the
# fields ha_read.py maps) and to check whether your unit ever broadcasts a
# message beyond the standard 9 (e.g. a temperature report).
#
# Reads UART1 @1200 8N1 on GP5 (MAX485 RO), receive-only. Runs in RAM without
# touching an installed main.py:
#   mpremote connect <port> run firmware/sniffer/fulldump.py
#
# Data bytes are MSB-first -> bit-reverse to read values (0xFE = 127 = padding).
# The first "rev" value on each line is the header byte reversed; ignore it.
import time
from machine import UART, Pin

def rev(b):
    r = 0
    for i in range(8):
        r = (r << 1) | ((b >> i) & 1)
    return r

u = UART(1, 1200, bits=8, parity=None, stop=1, rx=Pin(5), timeout=0, rxbuf=2048)

cur = bytearray()
last = time.ticks_us()
msgs = []
bursts = 0
NB = 4                          # how many bursts to print
t_end = time.ticks_ms() + 25000

while time.ticks_ms() < t_end and bursts < NB:
    d = u.read()
    now = time.ticks_us()
    if d:
        if cur and time.ticks_diff(now, last) > 12000:     # >12ms gap = new message
            msgs.append(bytes(cur)); cur = bytearray()
        cur.extend(d); last = now
    else:
        if cur and time.ticks_diff(now, last) > 12000:
            msgs.append(bytes(cur)); cur = bytearray()
        if msgs and time.ticks_diff(now, last) > 200000:   # >200ms idle = burst end
            print("--- burst %d (%d msgs) ---" % (bursts, len(msgs)))
            for m in msgs:
                hx = " ".join("%02X" % b for b in m)
                rv = " ".join(str(rev(b)) for b in m)
                print("H%02X L%d | raw %s | rev %s" % (m[0], len(m), hx, rv))
            bursts += 1
            msgs = []
    time.sleep_ms(2)
print("done")
