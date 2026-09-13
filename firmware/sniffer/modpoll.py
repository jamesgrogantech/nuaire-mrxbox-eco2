"""Modbus RTU read-only poll sweep (Pico W, MicroPython) over WiFi.

Becomes the bus master: sends Modbus read requests and prints any reply.
ONLY read function codes are sent (0x03/0x04/0x01/0x02) — non-mutating, they
cannot change unit state. No write codes anywhere in this file. This is the
first firmware that transmits; see docs/protocol.md write-back preconditions.

Wiring (half-duplex RS485):
    RO  -> GP5 (UART1 RX)
    DI  -> GP4 (UART1 TX)
    DE + /RE tied together -> GP0   (HIGH = transmit, LOW = receive)
    VCC -> 3V3, GND common

Run headless: cp to :main.py, power-cycle, then  nc <pico-ip> 9000
Commands over the socket (newline-terminated):
    sweep            addresses 1..32, all read FCs, register 0, at current baud
    sweep 1 247      address range low..high
    baud 19200       change baud (default 9600)
    fc 3             restrict to a single function code for the next sweep
    read 2 3 0 8     one-shot: addr=2 fc=3 start=0 count=8
    marker <text>    timestamped note into the log
Nothing is sent except in response to these commands — idle is pure receive.
"""

import network
import socket
import time
from machine import UART, Pin

RX_PIN, TX_PIN, DE_PIN = 5, 4, 0
BAUD = 9600
PARITY = None          # None=8N1, 0=8E1 (Modbus default), 1=8O1
INVERT = False         # True = invert TX+RX = software A/B swap (no rewiring)
PORT = 9000
REPLY_TIMEOUT_MS = 300      # wait this long for a slave answer
READ_FCS = (0x03, 0x04, 0x01, 0x02)  # holding, input, coils, discrete — all reads

de = Pin(DE_PIN, Pin.OUT, value=0)   # start in receive


def _inv():
    return (UART.INV_TX | UART.INV_RX) if INVERT else 0


uart = UART(1, baudrate=BAUD, bits=8, parity=None, stop=1,
            tx=Pin(TX_PIN), rx=Pin(RX_PIN), timeout=0, rxbuf=512, invert=_inv())


def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def build_read(addr, fc, start, count):
    body = bytes([addr, fc, start >> 8, start & 0xFF, count >> 8, count & 0xFF])
    c = crc16(body)
    return body + bytes([c & 0xFF, c >> 8])


def make_uart():
    return UART(1, baudrate=BAUD, bits=8, parity=PARITY, stop=1,
                tx=Pin(TX_PIN), rx=Pin(RX_PIN), timeout=0, rxbuf=512, invert=_inv())


def txrx(frame):
    """Send one frame, return raw reply bytes (may be empty)."""
    uart.read()               # flush stale
    de.value(1)               # drive bus
    uart.write(frame)
    # wait for the last bit to leave before releasing the driver:
    # ~ (len*10 bits / baud) seconds, plus margin
    time.sleep_us(int(len(frame) * 10 * 1_000_000 / BAUD) + 800)
    de.value(0)               # back to receive
    deadline = time.ticks_add(time.ticks_ms(), REPLY_TIMEOUT_MS)
    buf = b""
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        chunk = uart.read()
        if chunk:
            buf += chunk
            deadline = time.ticks_add(time.ticks_ms(), 50)  # extend on activity
    return buf


def hexs(b):
    return " ".join("%02X" % x for x in b)


def strip_echo(req, rep):
    """Half-duplex with /RE grounded means we hear our own TX first.
    Drop a leading copy of the request so only a genuine slave reply remains."""
    if rep[:len(req)] == req:
        return rep[len(req):]
    return rep


def valid_reply(req, rep):
    """A genuine Modbus reply: not an echo of the request, >=5 bytes, echoes
    addr, function byte matches (or is an exception 0x80|fc), CRC checks."""
    rep = strip_echo(req, rep)
    if len(rep) < 5 or rep[0] != req[0]:
        return False
    if rep[1] != req[1] and rep[1] != (req[1] | 0x80):
        return False
    return crc16(rep[:-2]) == (rep[-2] | (rep[-1] << 8))


def sweep(client, lo, hi, only_fc):
    fcs = (only_fc,) if only_fc else READ_FCS
    client.send(("# sweep addr %d..%d fcs %s baud %d\n"
                 % (lo, hi, [hex(f) for f in fcs], BAUD)).encode())
    hits = 0
    for addr in range(lo, hi + 1):
        for fc in fcs:
            req = build_read(addr, fc, 0, 8)
            rep = txrx(req)
            real = strip_echo(req, rep)   # what's left after our own echo
            if real:
                ok = valid_reply(req, rep)
                client.send(("%s addr=%d fc=0x%02X -> %s%s\n"
                             % ("HIT " if ok else "junk", addr, fc, hexs(real),
                                " [CRC OK]" if ok else "")).encode())
                if ok:
                    hits += 1
        time.sleep_ms(20)
    client.send(("# sweep done, %d valid replies\n" % hits).encode())


def handle(client, cmd):
    global BAUD, PARITY, INVERT, uart
    p = cmd.strip().split()
    if not p:
        return
    if p[0] == "sweep":
        lo = int(p[1]) if len(p) > 1 else 1
        hi = int(p[2]) if len(p) > 2 else 32
        sweep(client, lo, hi, None)
    elif p[0] == "bsweep":
        # try every standard baud against a small address range
        lo = int(p[1]) if len(p) > 1 else 1
        hi = int(p[2]) if len(p) > 2 else 8
        for b in (9600, 19200, 4800, 38400, 2400, 57600, 115200, 1200):
            BAUD = b
            uart = make_uart()
            time.sleep_ms(50)
            client.send(("# --- baud %d ---\n" % b).encode())
            sweep(client, lo, hi, 0x03)
    elif p[0] == "psweep":
        # sweep baud x parity, the full net. addr range small to stay quick.
        lo = int(p[1]) if len(p) > 1 else 1
        hi = int(p[2]) if len(p) > 2 else 8
        for par, pname in ((None, "8N1"), (0, "8E1"), (1, "8O1")):
            PARITY = par
            for b in (9600, 19200, 4800, 38400, 2400):
                BAUD = b
                uart = make_uart()
                time.sleep_ms(50)
                client.send(("# --- %s baud %d ---\n" % (pname, b)).encode())
                sweep(client, lo, hi, 0x03)
        PARITY = None
        uart = make_uart()
    elif p[0] == "parity" and len(p) == 2:
        PARITY = {"none": None, "even": 0, "odd": 1}[p[1]]
        uart = make_uart()
        client.send(("# parity now %s\n" % p[1]).encode())
    elif p[0] == "invert" and len(p) == 2:
        INVERT = (p[1] == "on")
        uart = make_uart()
        client.send(("# invert (software A/B swap) now %s\n" % ("ON" if INVERT else "OFF")).encode())
    elif p[0] == "isweep":
        # sweep with A/B inverted in software, both bauds, addr range
        lo = int(p[1]) if len(p) > 1 else 1
        hi = int(p[2]) if len(p) > 2 else 32
        INVERT = True
        for b in (9600, 19200):
            BAUD = b
            uart = make_uart()
            time.sleep_ms(50)
            client.send(("# --- INVERTED baud %d ---\n" % b).encode())
            sweep(client, lo, hi, 0x03)
        INVERT = False
        uart = make_uart()
    elif p[0] == "fc" and len(p) == 2:
        sweep(client, 1, 32, int(p[1]))
    elif p[0] == "read" and len(p) == 5:
        req = build_read(int(p[1]), int(p[2]), int(p[3]), int(p[4]))
        rep = txrx(req)
        client.send(("req %s -> %s %s\n" % (hexs(req), hexs(rep) or "(silence)",
                     "[CRC OK]" if rep and valid_reply(req, rep) else "")).encode())
    elif p[0] == "baud" and len(p) == 2:
        BAUD = int(p[1])
        uart = make_uart()
        client.send(("# baud now %d\n" % BAUD).encode())
    elif p[0] == "marker":
        client.send(("# marker t=%dms %s\n" % (time.ticks_ms(), " ".join(p[1:]))).encode())
    else:
        client.send(("# unknown: %s\n" % cmd.strip()).encode())


def main():
    network.hostname("nuaire-pico")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    import secrets
    wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
    for _ in range(30):
        if wlan.isconnected():
            break
        time.sleep(1)
    print("ip:", wlan.ifconfig()[0])

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PORT))
    srv.listen(1)
    print("modpoll listening on", PORT)

    while True:
        cli, addr = srv.accept()
        cli.send(("# modpoll ready. baud=%d. commands: sweep / read a f s c / baud N / fc N / marker\n" % BAUD).encode())
        buf = b""
        try:
            while True:
                chunk = cli.recv(64)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    handle(cli, line.decode())
        except OSError:
            pass
        finally:
            de.value(0)   # always leave bus in receive
            cli.close()


try:
    main()
except Exception as e:
    import sys
    de.value(0)
    try:
        with open("crash.log", "a") as f:
            f.write("--- modpoll crash ---\n")
            sys.print_exception(e, f)
    except OSError:
        pass
    sys.print_exception(e)
    time.sleep(10)
    import machine
    machine.reset()
