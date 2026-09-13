"""WiFi bus sniffer (Pico 2W, MicroPython): streams capture lines over TCP.

Same output format as main.py, but served on a TCP socket so the laptop needs
no USB connection — power the Pico from a USB wall adapter near the unit.

Setup (once, over USB):
    cp firmware/sniffer/secrets.example.py firmware/sniffer/secrets.py  # edit in SSID/pass
    mpremote cp firmware/sniffer/secrets.py firmware/sniffer/netsniff.py :
    mpremote run firmware/sniffer/netsniff.py     # note the printed IP
    # optional: mpremote cp firmware/sniffer/netsniff.py :main.py  -> runs on power-up
    # tip: give the Pico a DHCP reservation in the router so the IP is stable

Capture from the laptop (anywhere on the LAN):
    nc <pico-ip> 9000 | tee captures/$(date +%Y%m%d-%H%M)-idle-9600-8N1.log

Live commands — type into the nc session, newline-terminated:
    baud 19200      switch baud rate on the fly
    parity none|even|odd
    marker <text>   inject "# marker <text>" into the stream (stimulus timing)
"""

import network
import socket
import time
from machine import UART, Pin

import secrets

BAUD = 9600
BITS, PARITY, STOP = 8, None, 1
RX_PIN = 5
GAP_US = 3000
PORT = 9000

PARITY_NAMES = {None: "N", 0: "E", 1: "O"}


def wifi_connect():
    network.hostname("nuaire-pico")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("connecting to", secrets.WIFI_SSID)
        wlan.connect(secrets.WIFI_SSID, secrets.WIFI_PASS)
        for _ in range(30):
            if wlan.isconnected():
                break
            time.sleep(1)
    if not wlan.isconnected():
        print("wifi failed, retrying from scratch in 5s")
        time.sleep(5)
        import machine
        machine.reset()
    print("wifi ok, ip:", wlan.ifconfig()[0])
    return wlan


def make_uart():
    return UART(1, baudrate=BAUD, bits=BITS, parity=PARITY, stop=STOP,
                rx=Pin(RX_PIN), timeout=0, rxbuf=1024)


def banner():
    return "# sniffer baud=%d %d%s%d gap_us=%d t0_ms=%d\n" % (
        BAUD, BITS, PARITY_NAMES[PARITY], STOP, GAP_US, time.ticks_ms())


def handle_command(cmd, uart):
    """Returns (uart, reply). Unknown commands are echoed as comments."""
    global BAUD, PARITY
    parts = cmd.strip().split()
    if not parts:
        return uart, ""
    if parts[0] == "baud" and len(parts) == 2:
        BAUD = int(parts[1])
        uart.deinit()
        return make_uart(), banner()
    if parts[0] == "parity" and len(parts) == 2:
        PARITY = {"none": None, "even": 0, "odd": 1}[parts[1]]
        uart.deinit()
        return make_uart(), banner()
    if parts[0] == "marker":
        return uart, "# marker t=%dms %s\n" % (time.ticks_ms(), " ".join(parts[1:]))
    return uart, "# unknown command: %s\n" % cmd.strip()


def serve(client, uart):
    client.setblocking(False)
    client.send(banner().encode())
    line = []
    cmd_buf = b""
    last_byte_us = time.ticks_us()

    while True:
        # inbound commands
        try:
            chunk = client.recv(64)
            if chunk == b"":
                return uart  # client closed
            cmd_buf += chunk
            while b"\n" in cmd_buf:
                cmd, cmd_buf = cmd_buf.split(b"\n", 1)
                uart, reply = handle_command(cmd.decode(), uart)
                if reply:
                    client.send(reply.encode())
        except OSError:
            pass  # no data waiting

        # bus bytes -> gap-split lines
        data = uart.read()
        now = time.ticks_us()
        flush = line and time.ticks_diff(now, last_byte_us) >= GAP_US
        if data:
            if flush:
                client.send(("%10d %s\n" % (time.ticks_ms(), " ".join(line))).encode())
                line = []
            line.extend("%02X" % b for b in data)
            last_byte_us = now
        elif flush:
            client.send(("%10d %s\n" % (time.ticks_ms(), " ".join(line))).encode())
            line = []


def main():
    wifi_connect()
    uart = make_uart()
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(1)
    print("listening on port", PORT)

    while True:
        client, addr = server.accept()
        print("client:", addr)
        try:
            uart = serve(client, uart)
        except OSError as e:
            print("client gone:", e)
        except (ValueError, KeyError) as e:
            print("bad command:", e)
        finally:
            client.close()
        # drain anything that piled up while nobody was listening
        uart.read()


# Headless resilience: any unhandled crash is appended to crash.log on flash
# (read later with `mpremote fs cat :crash.log`), then the board hard-resets
# and tries again rather than sitting dead at the REPL.
try:
    main()
except Exception as e:
    import sys, machine
    try:
        with open("crash.log", "a") as f:
            f.write("--- crash at ticks_ms=%d ---\n" % time.ticks_ms())
            sys.print_exception(e, f)
    except OSError:
        pass
    sys.print_exception(e)
    time.sleep(10)
    machine.reset()
