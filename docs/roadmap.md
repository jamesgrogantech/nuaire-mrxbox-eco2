# Roadmap

## Phase 1 — bus discovery (current)
- [ ] Isolate unit, open, photograph PCB + connectors (→ docs/img/)
- [ ] Trace connector pins to WS3471 with continuity (power off) → pinout in
      docs/hardware.md
- [ ] Powered voltage survey of candidate pins (≤12V expected)
- [ ] Wire MAX485 receive-only per docs/hardware.md
- [ ] Run firmware/sniffer/baudfind.py — pulse-width histogram → baud rate
- [ ] Run firmware/sniffer/main.py at discovered baud → first capture in
      captures/
- [ ] Milestone: clean, repeating byte stream captured; baud CONFIRMED in
      docs/protocol.md

## Phase 1.5 — get the unit to actually reply (current)
What's confirmed (2026-08-27): the display connector is a live RS485 bus,
unit-biased, A>B, correct polarity, our pin ID right (meter check). What
fails: no reply to Modbus polling. Leading cause: our 3.3V MAX485 under-drives
the differential — the unit never receives a clean poll. Our own self-echo
masks this (local, always works).

- [x] Confirm connector is live RS485 (meter)
- [x] Rule out reversed A/B (software UART inversion)
- [x] Rule out module fault (A/B = 120Ω terminator, not a short)
- [ ] **USB-RS485 dongle** (Waveshare, SP485EEN, 5V, auto-direction) — on order
- [ ] Laptop tooling: install `mbpoll` (brew) + a pymodbus scanner script
- [ ] When it lands: wire A+/B-/GND to connector, then
      1. passive listen at each baud for spontaneous traffic
      2. `mbpoll` address+baud sweep, read function codes only
      3. if silent, swap A/B screw terminals, retry
- [ ] If still silent with proper 5V drive: unit likely needs a real display
      to poll it → borrow/buy MRXBOX-VSC and MITM sniff (Option C)
- [ ] Milestone: one genuine, CRC-valid frame the UNIT generated

## Phase 2 — protocol decode
- [ ] tools/analyze.py over captures: frame split, checksum hunt
- [ ] Correlate fields with physical reality (breathe on RH sensor, change
      speed via switched-live/relay inputs, note RPM changes)
- [ ] Milestone: temp/RH/fan state decoded and CONFIRMED

## Phase 3 — write-back (gated — see docs/protocol.md preconditions)
- [ ] Understand master/slave vs broadcast
- [ ] Replay a single captured command frame, observe unit, revert
- [ ] Milestone: speed change via Pico

## Phase 4 — Home Assistant
- Route TBD (MQTT over WiFi is the default assumption: Pico 2W → broker →
  MQTT discovery entities)
- [ ] Continuous-read firmware with reconnect/watchdog
- [ ] HA entities: temps, RH, fan speed/RPM, filter/diag flags
- [ ] Controls: speed select, boost
