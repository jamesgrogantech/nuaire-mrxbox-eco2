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

## To do
- [ ] Re-read full thread (all posts, not just #5) and mine for photos/pinouts
- [ ] Search GitHub for "nuaire", "mrxbox" repos
- [ ] Check FCC/CE teardown photos, Nuaire installation manuals for connector
      pinouts (manual sometimes labels the controller cable cores)
