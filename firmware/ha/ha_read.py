# Nuaire MRXBOX ECO2 -> Home Assistant (read-only), Pico W MicroPython.
# Reads the display bus at 1200 8N1 on GP5 (MAX485 RO), decodes the broadcast,
# publishes humidity / temperature / boost to MQTT with HA auto-discovery.
# Receive-only: MAX485 DE+/RE tied to GND. See docs/protocol.md.
# Kept flat and ASCII-only on purpose: this exact structure is the one verified
# stable on the bench (refactors and a non-ASCII degree symbol both broke it).
# Fields, in raw UART bytes (the bus is MSB-first, so a UART sees each byte
# bit-reversed). A message is used only if all its raw bytes XOR to 0xAB.
#   humidity     = msg 3B byte1: rev(b) ^ 0x7F -> RH %   (0 or 127 = sensor fault)
#   temp_extract = msg 85 byte1: b >> 1, signed 7-bit -> C  (-63 = sensor fault)
#   temp_intake  = msg 85 byte3: same encoding
#   boost        = msg 21 byte2 bit 0x02 (ON when clear)
# Humidity and temperature encodings follow karwantes/Nuaire-MVHR (decoded from
# the VSC's own firmware); HYPOTHESIS on this ECO2 until a stimulus test
# confirms them. See docs/protocol.md "Upstream cross-check".
# Setup: mpremote mip install umqtt.simple; cp secrets.py + this as :main.py
#
# Resilience: a hardware WDT (8.388s, the RP2040 max) is fed at the top of the
# main loop and between each network op. The board used to hang until manual
# repower (WiFi/socket lockup, no watchdog); a *fed* WDT self-heals any hang in
# <9s. The trick that avoids the old false-trips: feed BETWEEN network calls so
# a slow-but-progressing broker never trips it, while a genuine stuck call does.
# Every blocking wait (WiFi bring-up, reconnect) either feeds each second or is
# short enough to reset the board before the WDT would fire.
import network, time, ujson, ubinascii, machine, secrets, os
from machine import UART, Pin
from umqtt.simple import MQTTClient

def rev(b):
    r = 0
    for i in range(8):
        r = (r << 1) | ((b >> i) & 1)
    return r

def msg_ok(b, i, n):
    # n raw bytes from b[i] (header .. checksum) XOR to 0xAB on a good message
    if i + n > len(b): return False
    x = 0
    for k in range(i, i + n): x ^= b[k]
    return x == 0xAB

def temp(b):
    v = b >> 1                       # raw b >> 1 == rev(msb-first byte) >> 1
    v = v - 128 if v >= 64 else v    # signed 7-bit
    return None if v == -63 else v   # -63 = sensor fault

w = network.WLAN(network.STA_IF); w.active(True)
try: w.config(pm=0xa11140)
except: pass
# static IP is optional: set STATIC_IP = (ip, mask, gw, dns) in secrets.py to
# pin one, or leave it None (default) for DHCP. See secrets.example.py.
try:
    _ip = getattr(secrets, 'STATIC_IP', None)
    if _ip: w.ifconfig(_ip)
except: pass
w.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
# WDT armed here so a hang anywhere past this point self-heals. 8388ms = RP2040
# max. The wait loop below feeds every second, so WiFi association (which can
# take >8s) never trips it; only a truly stuck call does.
wdt = machine.WDT(timeout=8388)
for _ in range(30):
    if w.isconnected(): break
    wdt.feed(); time.sleep(1)
if not w.isconnected():
    machine.reset()   # <5s to here, so we reset before the WDT would fire

def connect():
    cid = b'nuaire_' + ubinascii.hexlify(os.urandom(4))
    c = MQTTClient(cid, secrets.MQTT_HOST, port=getattr(secrets,'MQTT_PORT',1883),
                   user=secrets.MQTT_USER, password=secrets.MQTT_PASS, keepalive=60)
    c.connect()
    try: c.sock.settimeout(3)
    except: pass
    # keep the device block small so the discovery JSON stays well under any
    # MQTT publish-buffer limit (a longer payload was seen truncating earlier)
    dev = {'identifiers': ['nuaire_mrxbox'], 'name': 'Nuaire MRXBOX ECO2'}
    degc = '\u00b0C'   # escaped so this source stays ASCII; payload is encoded below
    for kind, key, extra in [('sensor','humidity',{'name':'MRXBOX Humidity','device_class':'humidity','unit_of_measurement':'%','state_class':'measurement'}),
                             ('sensor','temp_extract',{'name':'MRXBOX Extract Temperature','device_class':'temperature','unit_of_measurement':degc,'state_class':'measurement'}),
                             ('sensor','temp_intake',{'name':'MRXBOX Intake Temperature','device_class':'temperature','unit_of_measurement':degc,'state_class':'measurement'}),
                             ('binary_sensor','boost',{'name':'MRXBOX Boost','payload_on':'ON','payload_off':'OFF'})]:
        p = {'state_topic':'nuaire/'+key,'expire_after':90,'unique_id':'nuaire_mrxbox_'+key,'device':dev}
        p.update(extra)
        # encode to bytes: umqtt.simple uses len() for the MQTT length field, and
        # len(str) miscounts non-ASCII (the degree sign) -> malformed packet ->
        # broker resets the connection. Bytes give the correct length.
        c.publish('homeassistant/%s/nuaire_mrxbox/%s/config' % (kind, key),
                  ujson.dumps(p).encode('utf-8'), retain=True)
    return c

wdt.feed()
c = connect()   # if the broker is down this may block; the WDT resets us then
u = UART(1, baudrate=1200, bits=8, parity=None, stop=1, rx=Pin(5), timeout=0, rxbuf=1024)
buf = bytearray()
vals = {'humidity': None, 'temp_extract': None, 'temp_intake': None, 'boost': None}
# gap-split message assembler for the raw-frame log (additive; the anchored
# humidity/boost decode above is untouched). frame[header] = list of raw bytes.
mbuf = bytearray(); mlast = time.ticks_us(); frame = {}
# fixed order of (header, byte-index) to emit as nuaire/raw (bit-reversed).
# Covers every non-padding data byte across the 9 messages, so long-term
# logging can correlate any of them. -1 if that message is absent this cycle.
RAWMAP = ((0x11,1),(0x11,2),(0x21,1),(0x21,2),(0x21,3),(0x31,3),(0x33,3),
          (0x3B,1),(0x3B,2),(0x3B,3),(0x51,4),(0x75,5),(0x85,1),(0x85,3),
          (0x85,6),(0xA3,7))
lastpub = time.ticks_ms(); fails = 0

while True:
    wdt.feed()   # fast path: loop spins on non-blocking u.read -> fed many times/s
    d = u.read()
    now = time.ticks_us()
    if d:
        buf.extend(d)
        if len(buf) > 400: buf = bytearray(buf[-200:])
        for i in range(len(buf) - 3):
            h = buf[i]
            if h == 0x3B and msg_ok(buf, i, 4):
                v = rev(buf[i+1]) ^ 0x7F
                if 0 < v <= 100: vals['humidity'] = v
            elif h == 0x85 and msg_ok(buf, i, 7):
                vals['temp_extract'] = temp(buf[i+1])
                vals['temp_intake'] = temp(buf[i+3])
            elif h == 0x21 and msg_ok(buf, i, 4):
                vals['boost'] = 'ON' if (buf[i+2] & 0x02) == 0 else 'OFF'
        if mbuf and time.ticks_diff(now, mlast) > 15000:
            frame[mbuf[0]] = list(mbuf); mbuf = bytearray()
        mbuf.extend(d); mlast = now
    elif mbuf and time.ticks_diff(now, mlast) > 15000:
        frame[mbuf[0]] = list(mbuf); mbuf = bytearray()
    if time.ticks_diff(time.ticks_ms(), lastpub) >= 15000:
        # NOTE: do NOT gate on w.isconnected() - the CYW43 goes "zombie" (reports
        # connected, keeps the IP, sends don't raise) while no traffic actually
        # flows, so isconnected() lies. The only reliable liveness test is a
        # round-trip the BROKER must answer: ping + read PINGRESP with a socket
        # timeout. No answer -> dead link -> hard reset re-inits the WiFi stack.
        try:
            for k in vals:
                if vals[k] is not None:
                    c.publish('nuaire/'+k, str(vals[k]), retain=True)
                    wdt.feed()   # feed between ops: slow broker != hang
            raw = []
            for h, pos in RAWMAP:
                m = frame.get(h)
                raw.append(str(rev(m[pos])) if m and len(m) > pos else '-1')
            c.publish('nuaire/raw', ','.join(raw), retain=True)
            wdt.feed()
            c.ping()
            c.sock.settimeout(3)
            c.wait_msg()         # expects PINGRESP; zombie link -> timeout -> except
            wdt.feed()
            fails = 0
        except Exception:
            # dead link (or broker gone). One quick reconnect attempt; if two
            # cycles in a row fail (~30s), hard-reset to rebuild the WiFi stack.
            fails += 1
            if fails >= 2:
                machine.reset()
            try:
                c = connect()
            except Exception:
                machine.reset()
        lastpub = time.ticks_ms()
