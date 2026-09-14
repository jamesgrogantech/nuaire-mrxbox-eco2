---
name: Unit / hardware report
about: Report results from your Nuaire unit or interface hardware (even "same as the README" helps confirm findings)
title: "[unit] "
labels: unit-report
---

## Your unit
- Nuaire model (e.g. MRXBOX ECO2):
- Any firmware / label / date markings on the PCB or unit:
- Do you have the official display controller? (yes/no)

## Your interface hardware
- MCU / adapter (e.g. Pico W, ESP32, USB-RS485 dongle):
- RS485 transceiver and voltage it runs at (3.3 V / 5 V):
- Receive-only? (DE/¬RE grounded?)

## What you observed
- Baud / framing (expected: 1200 8N1):
- Does the unit broadcast ~every 0.7 s with the 9 message headers
  (21 11 51 31 33 85 A3 75 3B)? Any differences?
- Humidity (`3B` byte 1, bit-reversed) reading sensibly?
- Boost (`21` byte 2, bit 0x02) tracking your boost switch?

## Capture (optional but ideal)
Paste a decoded broadcast, or attach/link a capture file (named per
`captures/README.md`). Note any stimulus you applied (shower, boost toggle, fan
speed change).
