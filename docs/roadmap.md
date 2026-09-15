# Roadmap

## Phase 1 — bus discovery ✅ DONE
- [x] Trace connector pins, confirm live RS485 bus (unit-biased, A>B, meter)
- [x] Baud/framing: **1200 8N1**, data **MSB-first** (bit-reverse each data byte)
- [x] Clean, repeating capture of the unit's autonomous broadcast
- Note: the 3.3 V Pico transceiver under-reads the weakly-biased bus; a 5 V
  transceiver/dongle reads it reliably. See docs/protocol.md.

## Phase 2 — protocol decode ✅ (broadcast fully mapped)
- [x] Frame = 9 gap-separated messages, ~0.7 s repeat (21 11 51 31 33 85 A3 75 3B)
- [x] **Humidity** decoded + confirmed (3B byte1, bit-reversed = RH %)
- [x] **Boost/fan** decoded + confirmed (21 byte2 bit 0x02; verified via bit-rev)
- [x] Full frame captured: every non-mapped byte is padding — the broadcast
      carries nothing else. All 16 candidate bytes logged long-term.
- [~] `85` message = fan speed / mode (HYPOTHESIS) — needs a speed/shower stimulus
- [x] **Temperatures are NOT in the broadcast — poll-only** (see below). No
      temperature or run-time counter is obtainable passively.

## Phase 2b — get the polled data (temperatures, counters, diagnostics)
The VSC display shows Outside + Indoor temp and the unit has Extract + Supply
temp sensors, but none of it is broadcast — the display **polls** the unit for
it. To read it we must reproduce that poll.
- [ ] **MITM a real MRXBOX-VSC** (borrow/buy): tap the bus between VSC and unit,
      capture the display's poll request + the unit's response containing temps.
      This is the reliable route. **Step-by-step guide: [docs/vsc-mitm.md](vsc-mitm.md)**
      (Waveshare ESP32-S3-RS485-CAN + firmware/esp32-s3/vsc_capture.py).
- [ ] From the capture: identify the poll frame, then transmit it ourselves and
      read the reply (moves us from receive-only to active polling).
- [ ] (Low odds without a reference) blind-fuzz poll candidates — Modbus already
      returned nothing, so the poll is proprietary.
- [ ] Optional: headless full-frame logger (small firmware add) to 100 % exclude
      a rarely-broadcast temp message.
- [ ] One more `33_3` stimulus test (strongly warm the extract, watch live) — it
      is a stable `25` and might be a broadcast indoor temp after all.

## Phase 3 — write-back / control (gated — see docs/protocol.md preconditions)
Requires transmitting onto the bus. Preconditions: framing + checksum confirmed,
a genuine command frame captured from a real VSC (see Phase 2b MITM), replay plan
written and reviewed. Receive-only until then.
- [ ] Understand the command format (from the VSC MITM capture)
- [ ] Replay a single captured command (e.g. speed change), observe, revert
- [ ] Milestone: fan speed / boost set from the Pico

## Phase 4 — Home Assistant ✅ (read-only live) / ongoing
- [x] Headless Pico W → MQTT bridge with HA auto-discovery, self-healing
      (watchdog + broker-liveness reset for the CYW43 zombie-WiFi failure mode)
- [x] Live entities: **humidity**, **boost**; all 16 raw bytes on `nuaire/raw`
      for long-term decoding (16 diagnostic sensors via MQTT discovery)
- [ ] Add fan speed/mode once `85` is confirmed
- [ ] Add temperatures once Phase 2b lands
- [ ] Add controls (speed, boost) once Phase 3 lands

## Community / repo
- [x] Public repo (MIT), README + CONTRIBUTING + issue/PR templates
- [ ] Gather other-unit / other-hardware reports (ESP32/ESPHome port wanted)
