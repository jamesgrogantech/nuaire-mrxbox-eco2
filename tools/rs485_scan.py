#!/usr/bin/env python3
"""Laptop-side RS485 / Modbus scanner for a USB-RS485 dongle (pyserial).

Run with an interpreter that has pyserial. On this machine:
    PY=/opt/homebrew/Cellar/mpremote/1.29.0/libexec/bin/python
    $PY tools/rs485_scan.py <port> listen 30
    $PY tools/rs485_scan.py <port> sweep --baud 9600 --parity N --lo 1 --hi 32
    $PY tools/rs485_scan.py <port> auto            # baud x parity x addr net

Port here is /dev/cu.usbserial-11430 (the CH340 dongle).

Modes:
  listen <secs>     passive: hexdump everything received, gap-split into frames.
                    Use FIRST — if the bus has any spontaneous traffic this
                    finds it with zero transmission and reveals baud by trial.
  sweep [opts]      send Modbus READ requests (fc 03/04/01/02 — non-mutating)
                    across an address range, print genuine replies.
  auto              sweep addr 1..16, fc03, over every baud x parity combo.

Only Modbus read function codes are ever transmitted. No writes anywhere here.
"""
import sys
import time
import argparse

import serial

READ_FCS = (0x03, 0x04, 0x01, 0x02)
BAUDS = (9600, 19200, 4800, 38400, 2400, 57600, 115200, 1200)
PARITIES = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN, "O": serial.PARITY_ODD}


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


def hexs(b):
    return " ".join("%02X" % x for x in b)


def open_port(port, baud, parity):
    return serial.Serial(port, baudrate=baud, bytesize=8, parity=parity,
                         stopbits=1, timeout=0.05)


def do_listen(port, secs):
    s = open_port(port, 9600, serial.PARITY_NONE)
    print("# listening %ss at 9600 8N1 (edit baud in code to retry). Ctrl-C to stop." % secs)
    end = time.time() + secs
    line = bytearray()
    last = time.time()
    total = 0
    while time.time() < end:
        chunk = s.read(256)
        now = time.time()
        if chunk:
            total += len(chunk)
            if line and (now - last) > 0.05:
                print("%.3f  %s" % (now, hexs(line)))
                line = bytearray()
            line += chunk
            last = now
        elif line and (now - last) > 0.05:
            print("%.3f  %s" % (now, hexs(line)))
            line = bytearray()
    s.close()
    print("# done, %d bytes total%s" % (total, "" if total else "  <-- SILENCE"))


def poll(s, addr, fc, start=0, count=8, wait=0.3):
    s.reset_input_buffer()
    s.write(build_read(addr, fc, start, count))
    s.flush()
    deadline = time.time() + wait
    buf = bytearray()
    while time.time() < deadline:
        chunk = s.read(64)
        if chunk:
            buf += chunk
            deadline = time.time() + 0.05
    return bytes(buf)


def valid(req_addr, req_fc, rep):
    if len(rep) < 5 or rep[0] != req_addr:
        return False
    if rep[1] != req_fc and rep[1] != (req_fc | 0x80):
        return False
    return crc16(rep[:-2]) == (rep[-2] | (rep[-1] << 8))


def do_sweep(port, baud, parity_key, lo, hi, fcs=READ_FCS):
    par = PARITIES[parity_key]
    s = open_port(port, baud, par)
    hits = 0
    for addr in range(lo, hi + 1):
        for fc in fcs:
            rep = poll(s, addr, fc)
            if rep:
                ok = valid(addr, fc, rep)
                tag = "HIT " if ok else "junk"
                print("%s baud=%d %s addr=%d fc=0x%02X -> %s" %
                      (tag, baud, parity_key, addr, fc, hexs(rep)))
                if ok:
                    hits += 1
        time.sleep(0.02)
    s.close()
    return hits


def do_auto(port, lo, hi):
    print("# auto: addr %d..%d, fc03, every baud x parity" % (lo, hi))
    grand = 0
    for pk in ("N", "E", "O"):
        for b in BAUDS:
            print("# --- %s baud %d ---" % (pk, b))
            grand += do_sweep(port, b, pk, lo, hi, fcs=(0x03,))
    print("# auto done, %d genuine replies total" % grand)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("mode", choices=["listen", "sweep", "auto"])
    ap.add_argument("secs", nargs="?", type=int, default=30)
    ap.add_argument("--baud", type=int, default=9600)
    ap.add_argument("--parity", default="N", choices=list(PARITIES))
    ap.add_argument("--lo", type=int, default=1)
    ap.add_argument("--hi", type=int, default=32)
    a = ap.parse_args()

    if a.mode == "listen":
        do_listen(a.port, a.secs)
    elif a.mode == "sweep":
        n = do_sweep(a.port, a.baud, a.parity, a.lo, a.hi)
        print("# sweep done, %d genuine replies" % n)
    elif a.mode == "auto":
        do_auto(a.port, a.lo, a.hi)


if __name__ == "__main__":
    main()
