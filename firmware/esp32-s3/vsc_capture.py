# VSC MITM capture — Waveshare ESP32-S3-RS485-CAN, MicroPython.
#
# Passively logs the RS485 bus between a real Nuaire MRXBOX-VSC display and the
# fan unit, so you can capture the display's POLL requests and the unit's
# responses (which carry the temperatures the broadcast does NOT). Prints every
# message with a millisecond timestamp; flags any message whose header is not
# one of the 9 the unit broadcasts on its own -> those are the poll exchange.
#
# Board RS485 mapping (Waveshare ESP32-S3-RS485-CAN):
#   TX = GPIO17, RX = GPIO18, DE/flow-control = GPIO21, terminals A(+)/B(-).
#   Set the onboard 120R termination jumper to NC (disabled) for a parallel tap.
# Receive-only: we hold DE (GPIO21) LOW and never write to the UART.
#
# Run over USB:  mpremote connect <port> run firmware/esp32-s3/vsc_capture.py
# (or save as main.py to log headless; add WiFi/MQTT like firmware/ha/ha_read.py)
#
# Data bytes are MSB-first -> bit-reverse to read values (0xFE = 127 = padding).
import time
from machine import UART, Pin

RS485_TX = 17
RS485_RX = 18
RS485_DE = 21
BAUD = 1200

# hold the transceiver in receive; never transmit (passive tap)
de = Pin(RS485_DE, Pin.OUT)
de.value(0)

u = UART(1, baudrate=BAUD, bits=8, parity=None, stop=1,
         tx=RS485_TX, rx=RS485_RX, timeout=0, rxbuf=4096)

KNOWN = set([0x21, 0x11, 0x51, 0x31, 0x33, 0x85, 0xA3, 0x75, 0x3B])

def rev(b):
    r = 0
    for i in range(8):
        r = (r << 1) | ((b >> i) & 1)
    return r

def show(msg, t_ms):
    hx = " ".join("%02X" % b for b in msg)
    rv = " ".join(str(rev(b)) for b in msg)
    tag = "" if msg[0] in KNOWN else "   <<< NON-BROADCAST (poll/response?)"
    print("t=%d H%02X L%d | raw %s | rev %s%s" % (t_ms, msg[0], len(msg), hx, rv, tag))

print("# VSC capture running. Known broadcast headers:",
      " ".join("%02X" % h for h in sorted(KNOWN)))
print("# Interact with the VSC (Home screen shows temps; Diagnostics polls the")
print("# unit) and watch for NON-BROADCAST lines = the poll exchange.\n")

cur = bytearray()
last = time.ticks_us()
t0 = time.ticks_ms()
while True:
    d = u.read()
    now = time.ticks_us()
    if d:
        if cur and time.ticks_diff(now, last) > 12000:      # >12ms gap = message boundary
            show(bytes(cur), time.ticks_diff(time.ticks_ms(), t0)); cur = bytearray()
        cur.extend(d); last = now
    else:
        if cur and time.ticks_diff(now, last) > 12000:
            show(bytes(cur), time.ticks_diff(time.ticks_ms(), t0)); cur = bytearray()
        time.sleep_ms(2)
