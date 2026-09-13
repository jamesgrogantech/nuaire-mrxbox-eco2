# Nuaire MRXBOX ECO2 — RS485 Reverse Engineering

## Goal
Reverse engineer the bus protocol of a Nuaire MRXBOX ECO2 MVHR unit so a
Raspberry Pi Pico 2W (+ MAX485) can read sensor/state data and eventually write
controls (fan speed, boost). End goal: Home Assistant integration (route TBD,
MQTT most likely).

## Current phase
**Phase 1 — bus discovery.** Owner has the unit but NOT the official display
controller. Plan: sniff the bus between the internal humidity/temp sensor and
the main PCB (traffic exists without the display). Receive-only until the
protocol is understood.

## Hardware facts (verify before relying on)
- Unit: Nuaire MRXBOX ECO2 (MVHR, mains powered — see docs/hardware.md safety section)
- Suspected RS485; a WS3471 (SP3485-class RS485 transceiver) sits near the pin
  headers on the main PCB (per HA community thread)
- 12V present on a main-PCB control line (per thread); connector on the bottom
  of the unit is for the display controller
- Interface: Pico W (RP2040 — believed to be a 2W until USB ID said otherwise)
  + MAX485 module, MicroPython v1.29.0. **RP2040 GPIO are NOT 5V-tolerant** —
  the RS485 module must run at 3.3V (or divider on RO), see docs/hardware.md
- Board is flashed and headless-ready: netsniff.py installed as main.py, joins
  WiFi on power-up, serves captures on TCP :9000 (DHCP — reserve the IP in the
  router; was 192.168.0.84 on 2026-08-25)
- Test gear: multimeter only (logic analyser deferred until needed)
- Baud rate, framing, pinout: **unknown** — nothing published

## Repo layout
- `docs/protocol.md` — the living protocol document. **Every confirmed finding
  goes here** (baud, framing, decoded fields, checksums), with the capture file
  that proves it.
- `docs/hardware.md` — connector/pinout notes, wiring, safety
- `docs/prior-art.md` — links + summaries of other people's Nuaire work
- `docs/roadmap.md` — phased plan and next steps
- `firmware/sniffer/` — MicroPython for the Pico 2W (bus sniffing, autobaud)
- `captures/` — raw capture logs (naming convention in captures/README.md)
- `tools/` — desktop Python for analysing captures (frame splitting, checksum
  hunting)

## Working conventions
- **Receive-only first.** DE and /RE on the MAX485 stay tied low. Do not
  transmit onto the bus until framing + checksum are confirmed and a specific
  frame replay is planned and written up in docs/protocol.md.
- Findings are only "confirmed" when reproduced in at least two captures;
  otherwise mark them `HYPOTHESIS:` in docs/protocol.md.
- Capture files are immutable once saved. Name per captures/README.md and
  reference them from protocol.md.
- Desktop analysis tools: plain Python 3, stdlib only where possible, run as
  `python3 tools/<script>.py <capture>`.
- MicroPython code targets the Pico 2W port; keep it dependency-free
  (machine/rp2 modules only) so files can be copied straight to the board with
  mpremote: `mpremote cp firmware/sniffer/*.py :` then `mpremote run`.

## Key unknowns (update as resolved)
1. Is the sensor bus actually RS485, or single-ended UART / something else?
2. Baud rate + serial params (start with pulse-width measurement, candidates
   2400/4800/9600/19200/38400/115200, 8N1 then 8E1)
3. Frame structure: delimiters vs. gap-based, address bytes, length byte?
4. Checksum: sum8 / XOR / CRC16-Modbus?
5. Is the display-connector bus the same bus as the internal sensor bus?
6. Does the unit poll (master/slave) or do devices broadcast?
