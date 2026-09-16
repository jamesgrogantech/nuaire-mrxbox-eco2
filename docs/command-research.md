# Command / poll format — research synthesis (2026-09-16)

Goal: form the best possible hypotheses for the **display→unit request and
command frames** we have never captured, from (a) what the unit already
does on the wire, (b) Nuaire's own documentation of the Ecosmart family, and
(c) how comparable MVHR / HVAC wall-panel buses are built and how others
derived their command sets. Everything here is HYPOTHESIS unless it points
at protocol.md. Nothing here authorises transmitting — see Phase 3 gates in
roadmap.md and the "Working conventions" in CLAUDE.md.

## 1. What we now know about our own bus (from protocol.md)

- 1200 baud 8N1, **MSB-first** bytes. Header byte has bit 7 set; every
  payload byte and the check byte are 7-bit (`0x7F` = "no value").
- **Check byte = XOR of header + payload, then `^ 0xD5`** (MSB-first view;
  `0xAB` in raw UART view). Confirmed on 36/36 messages, 3 sources.
- 9 messages per ~0.7 s cycle, fixed order, fixed lengths (3–8 bytes).
- Payload actually varying: `21` boost bit, `3B` RH %, `85` three bytes
  (fan/mode). Everything else constant or `0x7F`.
- Temperatures, run-time, filter timer, setpoints: **not broadcast**.

## 2. What Nuaire's documents establish about the bus (CONFIRMED from source)

The MRXBOX-VSC manual calls itself part of the **Ecosmart** range and plugs
into the fan's **NET** terminal. Nuaire's commercial Ecosmart Classic docs
describe the same bus (same 4-core SELV cable, same junction boxes, same
NET label):

| Fact | Source |
|---|---|
| "4 IDC plug-in Net connectors … for the connection of compatible sensors, manual controls and for linking the fans together under a common control" | ES-ISC I&M 671432 §5.3.2 https://info.nuaire.co.uk/iandm/671432.pdf |
| "A 4-core SELV data cable is used … maximum cable run between any two devices is 300m … total … less than 1000m" | 671432 §5.3.6 |
| "The maximum number of devices (including fans) that can be connected together via the cable is 32" | 671432 §5.3.7 |
| Classic PCB has **Tx / Rx LEDs**: "Tx LED on when the controller is transmitting data" | 671432 §6.2 |
| VSC: "SELV (12 Vdc) with the power supplied from the fan unit"; >10 m needs MRXBOX-JB; max 50 m | VSC I&M 671703 https://info.nuaire.co.uk/IandM/671703.pdf |
| MRXBOX-JB = 9 paralleled NET sockets + mains power injector, "5W max" | 671700 https://info.nuaire.co.uk/IandM/671700.pdf |
| ECO2: "Fig 14: Ecosmart Device Connector on base of unit … not present on ECO2B or SW variants" | ECO2 I&M 671822/671824 https://info.nuaire.co.uk/IandM/671824.pdf |
| ECO2 accessories on the same bus: **MRXBOX95-HUM, MRXBOX95-PIR, MRXBOX95-RFI** (remote fail indicator), "all supplied with pre-plugged 10m data cable" | https://info.nuaire.co.uk/catalogue/MRXBOX-ECO2.pdf |
| MRXBOX95-HUM "will enable the Ecosmart fan when the measured humidity level is 2% above the set point" | 671443 https://info.nuaire.co.uk/IandM/671443.pdf |
| ES-PIR: "LED will change from green to red if any fan connected in that zone has failed" | 671127 https://info.nuaire.co.uk/iandm/671127.pdf |
| Classic ES-LCD programmer: PCB silk-screened "J5 LINUX TERMINAL", "SD CARD"; "the SD card on the PCB contains the software for the controller" | ES-LCD 671415 https://info.nuaire.co.uk/IandM/671415.pdf |
| No Classic device has address switches (ES-CO2RM DIPs are thresholds only) | 671537 https://info.nuaire.co.uk/IandM/671537.pdf |
| "Ecosmart Connect" (BACnet MS/TP, Johnson Controls-derived) and "Adapt" (Trend IQ422) are **different buses**; an "EGG" gateway PCB bridges Classic NET → Connect | https://info.nuaire.co.uk/catalogue/EcosmartConnect.pdf |
| Nuaire publishes **no** wire-level description of NET: no core names, baud, addressing, protocol | all of the above (searched) |
| WS3471 on the ECO2 PCB = MAX3471-class: 1/8 unit load, 64 kbps max, fail-safe receiver (−50…−450 mV threshold) | https://doc.chipmall.com/datasheet/rev_2412250445_gec-ws3471eeua_c02338153.pdf |

Consequences:
- **It is a multi-drop peer network, not a point-to-point display link.**
  Peripherals (PIR, HUM, RFI) both *listen* (RFI shows fan fault; PIR LED goes
  red on fan fail → fault state is in the broadcast) and *talk* (HUM/PIR send
  an enable/boost demand). So the "command" class we want is already spoken
  by cheap sensors, not only by the £200+ VSC.
- No address switches + 32-device limit → devices identify by **type in the
  header byte**, consistent with our 9 fixed headers.
- Ecosmart Connect's BACnet object list is the best public **parameter
  dictionary** for what the fan model contains (supply/extract %, boost run-on
  seconds, bypass cmd, frost temp, humidity target %, CO2 target, three duct
  temperatures Supply/Fresh/Extract, alarms, run hours). Encodings are plain
  integers (% 0–100, °C, s) — matches our RH byte.

## 3. Nuaire firmware habits (from the one other Nuaire wired RE)

`bdavj/pynuaire` — Drimaster ECO-HC internal controller↔motor UART
(https://github.com/bdavj/pynuaire/blob/main/PROTOCOL.md). Different bus
(57600, inverted, nibble-encoded) but same company:
- Checksum = negative sum-8 (ours is XOR — different team/era, don't assume).
- **A "level-change flag" byte must be set on the first packet with a new
  value or the motor ignores it.** Writes need an explicit "this is a change"
  marker, not just a new value.
- **Shared down-counter handshake**: each side replies with received−1;
  controller answers 17 ms after the motor packet; 500 ms keepalive.
- Direction byte 0x81 / 0x82 in the first position.
Transferable idea: expect the VSC to send a **presence/keepalive** and
expect a write to need a **change flag or sequence byte**.

## 4. Comparable wall-panel buses — patterns that transfer

Full survey with sources: Vallox Digit SE
(https://wiki.fhem.de/w/images/7/7e/Digit_protocol_english_RS485.pdf),
Zehnder ComfoAir 350 (https://github.com/coolchip/node-comfoair), Zehnder
Climos / Paul Novus (https://github.com/chr-fritz/climos-exporter/blob/main/docs/protocol.md),
Flexit SL4R (https://github.com/agjendem/flexit-sl4r-esphome), Vent-Axia
Sentinel (https://github.com/aelias-eu/vent-axia-remote), Toshiba TCC-Link
(https://github.com/issalig/toshiba_air_cond), Mitsubishi CN105
(https://github.com/m000c400/Mitsubishi-CN105-Protocol-Decode), Panasonic ERV
(https://github.com/ShadowZZP/esphome-panasonic-erv), Votronic
(https://github.com/scy/votonic), eBUS, EMS, OpenTherm, DALI.

Ranked by likelihood of applying to Nuaire NET:

1. **Requests reuse the status envelope.** Vallox "get" = same 6-byte frame
   with VARIABLE=0 and the register in DATA; ComfoAir read = same envelope,
   LEN 0; EMS read = write with `dst|0x80`; Toshiba has an R/W byte. Nobody
   uses a second protocol for requests. → A Nuaire poll is probably
   `<hdr≥0x80> <id> [7F…] <chk>` with the same XOR rule.
2. **Response = request with one bit/nibble changed.** ComfoAir +1, CN105
   +0x20, OpenTherm READ→READ-ACK, EMS `|0x80`. → Our `0x8C` / `0xCC` pair
   (same shape, differ only in bit 6) smells like exactly this. HYPOTHESIS:
   header bit 6 = direction/source class; bits 4..0 = message/parameter id.
3. **Header = address/type marker, payload 7-bit** (MIDI; Climos uses the
   hardware 9th "address" bit for the same job). → The VSC's frames will start
   with a bit-7-set byte **not** in our 9; the unit very likely ignores frames
   carrying its own headers — the best explanation for the failed boost-frame
   replay (protocol.md 2026-08-28), independent of TX reach.
4. **Registration / handshake gates writes.** CN105 connect `5A→7A` before
   anything; ComfoAir `00 9B` PC-mode or sets are ignored; Flexit nodes must
   answer polls or are dropped; Panasonic ERV needed the OEM boot handshake.
   → A verbatim command replay that "did nothing" is consistent with this even
   if the frame were right.
5. **Context matters, copy-last-state.** Flexit: byte-identical command did
   nothing without the preceding panel-state frame; their rule after bricking
   a setting four times: never build from scratch, copy the last observed
   frame and change one field. → When we do write, use the unit's own payload
   with one field changed, under the display's header.
6. **Fixed reply slot inside the periodic cycle** (Flexit, Climos, EMS ID
   polling). → Inter-message gap histogram inside our 0.7 s burst is the
   cheapest next experiment (§5.1).
7. **Panel owns some data and the unit echoes it** (Vent-Axia/Nilan/Flexit
   setpoints and boost timer live in the panel). → The long `0x7F` runs in
   `51 31 33 A3 75` may be fields normally *filled by the VSC* (time,
   setpoints, commissioning %) rather than unit sensors.
8. **ACK may be a bare byte** (Vallox echoes just the checksum; Helios
   repeats it twice). → When probing, log every byte, not just gap-framed
   messages; a single 7-bit byte 10–50 ms after our frame is a hit.
9. **Tight reply deadline** (Vallox 10 ms; HBS no gaps). 1 char = 8.3 ms at
   1200 baud, so reply windows may be tens of ms after a specific message.
10. **MSB-first 1200 baud bit-bang is a known habit** (DALI is 1200 bit/s
    MSB-first, 833 µs bit vs our 825 µs). Expect tight baud tolerance and
    possibly no tolerance for inter-byte gaps *within* a frame.
11. **Constant-seeded check** is common (Votronic XOR seed 0x55, CN105
    `0xFC−Σ`, ComfoAir `Σ+173`). Ours is in this family; receivers silently
    drop bad frames, no NACK.
12. **Bus courtesy**: Vallox waits 100 ms after last activity, Flexit 5 ms.
    The internal sensor node (if separate) may expect the same.

## 5. Concrete next steps, cheapest and safest first

### 5.1 Receive-only (no gate needed)
1. **Per-message timestamps.** Firmware currently drops timing. Log µs gaps
   between the 9 messages for ~10 min. Look for one gap that is quantised /
   longer / jittery — a reply slot or a poll→response pair *already inside*
   the broadcast (main PCB ↔ internal RH sensor). Positive: the `3B` (RH)
   message sits after a distinctive gap.
2. **Attribute headers to talkers.** Unplug the internal RH sensor (or tap its
   TX only) and see which of the 9 messages vanish. Positive: clean split, e.g.
   bit-6-set headers (`CC C5 DC`) are the sensor's. That gives the
   direction/source encoding for free.
3. **Byte-level logging** (not gap-framed) so bare-byte ACKs are visible later.
4. **PCB photo / MCU ID.** Nobody has published one. A PIC/STM8 with software
   UART would explain MSB-first and tell us its stack.

### 5.2 Obtain a genuine talker (the reliable route)
Ranked by cost:
- **MRXBOX95-HUM or MRXBOX95-PIR** (~£40–80 used): on-bus peripheral that
  sends an *enable/boost demand* — the exact command class we want, with an
  observable effect (boost LED/bit). Capture with the existing
  docs/vsc-mitm.md tap. Verify ECO2 compatibility (listed in the ECO2
  catalogue).
- **MRXBOX95-RFI**: pure listener; confirms which broadcast field is "fault".
- **ES-UCF** (Classic 10-speed dial, cheap on eBay): sends speed-set frames if
  the residential unit accepts Classic devices (unverified).
- **ES-LCD** (Classic touch programmer): firmware on a removable **SD card**,
  Linux — a dump would contain the entire NET stack (frame builder, checksum,
  poll list). Check whether the VSC shares the SD-card platform before buying
  either.
- **MRXBOX-VSC**: the full command set (speeds %, bypass, frost, humidity,
  timed boost, night/holiday, filter reset, time). Community: MNeverOff on the
  HA thread has a VSC and ordered a Waveshare ESP32-S3-RS485-CAN on
  2026-09-13 — point them at docs/vsc-mitm.md.

### 5.3 Minimal-transmit probes (Phase 3 gate applies; write plan into protocol.md first)
Ordered by risk; all use the confirmed XOR rule and all-`7F` payloads so
nothing can be "set" by accident. Abort any sweep if a broadcast field changes.
1. **Two-device rig first**: Pico as independent RX monitor while the dongle
   transmits — proves our frames land on the bus before interpreting silence.
2. **Bare get, unit's template**: `<hdr> 7F…7F <chk>` for each of the 9
   headers, sent right after the burst. Positive = extra frame / cadence change.
3. **Direction-bit probe**: same, header bit 6 toggled (`84→C4`, `A1→E1`,
   `DC→9C`…), then bit 5, bit 4.
4. **Header-class sweep**: 3-byte `<H> <id> <chk>`, H over unused classes
   (0x90–0x9F, 0xB0–0xBF, 0xE0–0xFF), id 0x00–0x7F, one frame per cycle.
5. **Presence then replay**: repeat whichever frame provoked anything every
   0.7 s for 30 s, then retry the boost frame under the new header class.
6. **Set-as-status-copy**: message `21`'s exact payload, boost bit toggled,
   under the discovered display header. Positive = `21` broadcast flips and
   fans audibly change.
7. Check ACKs at byte level within 10–50 ms of each probe.

## 6. Dead ends (don't repeat)
GitHub/GitLab/Codeberg for nuaire/mrxbox/ecosmart/WS3471 (only this repo +
pynuaire); openHAB, EEVblog, Hackaday, Reddit, BuildHub, Greenbuildingforum,
electricianforum (relay boost only); all Nuaire RF material (Drimaster
Eco-Link = RAMSES-II 868 MHz, unrelated); Nuaire patents (76, none describe
comms); Nuaire PC tools (only ESCO-CT for Connect/BACnet); "Nuaire Modbus
gateway" (doesn't exist; Classic→BMS is 0–10 V via ES-CI); teardowns/MCU IDs
(none). Titon BEAM publishes an RS485 1200-baud ASCII protocol
(https://community.home-assistant.io/t/617868) — different maker, ASCII, no
relation.
