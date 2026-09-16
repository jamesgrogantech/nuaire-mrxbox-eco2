# Prior art

## HA community thread (primary)
https://community.home-assistant.io/t/nuaire-mrxbox-interface-for-home-assistant/573933

Summary (as of 2026-08-25):
- WS3471 MSOP-8 chip identified near pin headers on the main PCB —
  SP3485-class RS485 transceiver clone ⇒ bus very likely RS485, 3.3V logic
- Internal humidity/temp sensor talks to the main PCB **over the same bus** ⇒
  sniffable traffic without owning the display controller
- 12V reported on a main-PCB control line; unit ON/OFF controllable via it
- Speed1/2/3, fan RPM, diagnostics, humidity/temp all flow through the
  official controller ⇒ expected to be on the bus
- One contributor uses a Pico W + MQTT reading front-LED state (optical, not
  bus); others use a Sonoff dual relay on boost/purge switch inputs
  (control without feedback)
- One contributor has obtained an official display and intends to build a
  sniffing proxy — **watch the thread for their captures**
- No baud rate, pinout, framing, or code published in the thread yet

## Related Nuaire knowledge
- Nuaire MRXBOXAB / larger commercial units expose Modbus RTU on some models —
  makes CRC16-Modbus and Modbus-style framing the first hypothesis to test
- Official VSC wired controller exists (expensive) — candidate purchase for
  Phase 2 command sniffing if sensor-bus RE stalls

## 2026-09-16 research sweep — see docs/command-research.md for the synthesis
- HA thread re-read in full (14 posts to 2026-09-14). Two members own a
  display: abinitio1980 (2023, "cheap display from eBay … EcoSmart Classic
  bus", reported +15 V / 0 V / Data+ / Data−) and MNeverOff (2026-08, working
  VSC; ordered a Waveshare ESP32-S3-RS485-CAN 2026-09-13). Neither has posted
  a capture. No repo from either as of today.
- Only other Nuaire wired RE: https://github.com/bdavj/pynuaire (Drimaster
  ECO-HC internal UART; change-flag byte + shared counter + negative-sum-8).
- The VSC/NET bus is Nuaire's **Ecosmart Classic** network (2002): 4-core
  SELV, 12 Vdc from the fan, 32 devices, unterminated multidrop, peripherals
  MRXBOX95-HUM/PIR/RFI on the same bus. Nuaire publishes no wire spec.
  Docs: https://info.nuaire.co.uk/IandM/{671432,671703,671700,671824,671415,671443}.pdf
- Commercial ES-LCD programmer runs Linux from a removable SD card
  (I&M 671415) — dumpable firmware if one is obtained.
- WS3471 = MAX3471-class (1/8 UL, 64 kbps, fail-safe RX).
- Titon BEAM (other UK MVHR maker) uses RS485 at 1200 baud too, but ASCII.

## To do
- [x] Re-read full thread — done 2026-09-16 (above)
- [x] Search GitHub for "nuaire", "mrxbox" repos — only pynuaire
- [x] Nuaire manuals for pinouts — none label the cores; only the HA-thread
      claim (+V, 0V, Data+, Data−) exists
- [ ] Ask MNeverOff / abinitio1980 for a display-side capture (link vsc-mitm.md)
- [ ] Price MRXBOX95-HUM / -PIR / ES-UCF / ES-LCD second-hand as cheaper
      command sources than a VSC
