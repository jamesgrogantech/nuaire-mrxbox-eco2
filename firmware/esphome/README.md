# ESPHome firmware — MRXBOX VSC emulation

ESP32 + XY-485 on the MRXBOX display bus, standing in for the VSC controller.
Replaces the karwantes `vsc-serial-bridge` Arduino firmware (no web UI, no
telnet, no unauthenticated OTA; encrypted native API to Home Assistant).

- `components/nuaire_vsc/` — external component: port of the upstream
  emulation core (25 µs timer ISR + bus edge ISR bit-bang the replies to polls
  88/8A/AE/C5; frames 84/A1/DC decoded for faults, temps, humidity; the VSC's
  speed-3/night/holiday/bypass timers). Upstream: karwantes/Nuaire-MVHR
  `esp/vsc-serial-bridge` at dc6fb54.
- `mrxbox.yaml` — device config; entities are template wrappers over the component.
- `secrets.yaml` — git-ignored; copy `secrets.example.yaml`.

## Credits

All the protocol work behind this component, and the emulation design and
timing, are by **karwantes**:
[karwantes/Nuaire-MVHR](https://github.com/karwantes/Nuaire-MVHR). This is a
port of that code to ESPHome. Upstream publishes no license, so the repo's MIT
license does not cover `components/nuaire_vsc/`; its terms are karwantes'.

## Build

Build and update over WiFi:

    cd firmware/esphome
    esphome run mrxbox.yaml --device mrxbox.local

Health check (Poll decode stats / Replies late diagnostics): every poll cycle
(~0.7 s) should give 4 replies, `late` should stay 0.

Notes:
- ESPHome excludes `esp_driver_gptimer` from IDF builds by default; the
  component re-includes it.
- Template switches use `restore_mode: DISABLED` — otherwise ESPHome turns
  them off at boot, which would switch emulation off.
- The bus UART uses a 1-byte RX threshold/timeout; the IDF defaults batch
  ~83 ms of bytes at 1200 baud and merge frames.
- First install went over WiFi through the Arduino firmware's ArduinoOTA
  (espota.py, port 3232), into its 1280 KB app slot; the Arduino partition
  table is still on flash. Serial fallback: Pico W MicroPython USB↔UART bridge,
  BOOT held while re-applying V5 (this board's CP2102 and RST button are dead).
