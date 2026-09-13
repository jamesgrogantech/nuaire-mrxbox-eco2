# Nuaire MRXBOX ECO2 -> Home Assistant (read-only), Pico W MicroPython.
# Reads the display bus at 1200 8N1 on GP5 (MAX485 RO), decodes the broadcast,
# publishes humidity / temperature / boost to MQTT with HA auto-discovery.
# Receive-only: MAX485 DE+/RE tied to GND. See docs/protocol.md.
# Kept flat and ASCII-only on purpose: this exact structure is the one verified
# stable on the bench (refactors and a non-ASCII degree symbol both broke it).
# Fields (data bytes are MSB-first -> bit-reverse):
#   humidity = msg 3B byte1 rev -> RH%;  temp = msg 33 byte3 rev -> C;
#   boost    = msg 21 byte2 bit 0x02 (ON when clear)
# Setup: mpremote mip install umqtt.simple; cp secrets.py + this as :main.py
import network, time, ujson, ubinascii, machine, secrets, os
from machine import UART, Pin
from umqtt.simple import MQTTClient

def rev(b):
    r = 0
    for i in range(8):
        r = (r << 1) | ((b >> i) & 1)
    return r

w = network.WLAN(network.STA_IF); w.active(True)
try: w.config(pm=0xa11140)
except: pass
try: w.ifconfig(('192.168.0.90','255.255.255.0','192.168.0.1','192.168.0.1'))
except: pass
w.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
for _ in range(30):
    if w.isconnected(): break
    time.sleep(1)
if not w.isconnected():
    time.sleep(5); machine.reset()

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
    # NOTE: temperature intentionally NOT published. The 0x33-byte3 value that
    # looked like ~25C is perfectly constant and does not respond to warming the
    # sensor (unlike humidity, which jitters) \u2014 it is not a live temperature.
    # Only humidity and boost are stimulus-confirmed. See docs/protocol.md.
    for kind, key, extra in [('sensor','humidity',{'name':'MRXBOX Humidity','device_class':'humidity','unit_of_measurement':'%','state_class':'measurement'}),
                             ('binary_sensor','boost',{'name':'MRXBOX Boost','payload_on':'ON','payload_off':'OFF'})]:
        p = {'state_topic':'nuaire/'+key,'expire_after':90,'unique_id':'nuaire_mrxbox_'+key,'device':dev}
        p.update(extra)
        # encode to bytes: umqtt.simple uses len() for the MQTT length field, and
        # len(str) miscounts non-ASCII (the degree sign) -> malformed packet ->
        # broker resets the connection. Bytes give the correct length.
        c.publish('homeassistant/%s/nuaire_mrxbox/%s/config' % (kind, key),
                  ujson.dumps(p).encode('utf-8'), retain=True)
    return c

c = connect()
u = UART(1, baudrate=1200, bits=8, parity=None, stop=1, rx=Pin(5), timeout=0, rxbuf=1024)
buf = bytearray(); vals = {'humidity': None, 'boost': None}
lastpub = time.ticks_ms(); fails = 0

while True:
    d = u.read()
    if d:
        buf.extend(d)
        if len(buf) > 400: buf = bytearray(buf[-200:])
        for i in range(len(buf) - 3):
            if buf[i] == 0x3B and buf[i+2] == 0x54:
                v = rev(buf[i+1]); vals['humidity'] = v if 0 <= v <= 100 else vals['humidity']
            elif buf[i] == 0x21 and buf[i+1] == 0xAA:
                vals['boost'] = 'ON' if (buf[i+2] & 0x02) == 0 else 'OFF'
    if time.ticks_diff(time.ticks_ms(), lastpub) >= 15000:
        try:
            for k in vals:
                if vals[k] is not None:
                    c.publish('nuaire/'+k, str(vals[k]), retain=True)
            c.ping()
            fails = 0
        except Exception:
            fails += 1
            if fails >= 8:
                machine.reset()
        lastpub = time.ticks_ms()
