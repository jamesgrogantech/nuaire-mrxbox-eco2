# Nuaire MRXBOX ECO2 — bus reverse engineering & Home Assistant bridge

Read live data from a **Nuaire MRXBOX ECO2** MVHR unit by tapping its
controller/sensor bus — **no official display controller required** — and
surface it in **Home Assistant** over MQTT. The unit broadcasts its status on
the bus by itself, so a passive, receive-only tap is enough to read it.

**Status:** humidity and boost/fan state are decoded, confirmed, and running
read-only in Home Assistant. The bus protocol is documented below. Writing
controls (fan speed, boost) is not solved yet. Other frame bytes (temperatures?
counters? RPM?) are being logged long-term to decode by correlation.

Prior art & discussion: [HA community thread](https://community.home-assistant.io/t/nuaire-mrxbox-interface-for-home-assistant/573933)

---

## ⚠️ Safety first

**A Nuaire MVHR is mains-powered. Mains can kill you and mains mistakes cause
fires.** This project only ever touches the **low-voltage data bus** on the
controller connector — never open the mains side, and isolate the unit at the
consumer unit before working near it if in any doubt. The RP2040 (Pico) is
**not 5 V-tolerant** — run your RS485 transceiver at 3.3 V or divide its RX
line. **Receive-only** wiring (transmitter disabled) is strongly recommended
until you understand the bus — see [`docs/hardware.md`](docs/hardware.md).

This is an **unofficial, community** project. It is not affiliated with or
endorsed by Nuaire. Interfacing with the bus may void your warranty. You do all
of this **at your own risk** (see [LICENSE](LICENSE) — no warranty).

---

## The protocol (confirmed)

| Property | Value |
|---|---|
| Medium | RS485 differential (WS3471 / SP3485-class transceiver on the PCB) |
| Baud / framing | **1200 baud, 8N1** |
| Bit order | **Data bytes are MSB-first** — a normal UART reads them bit-reversed |
| Traffic | Unit **broadcasts** ~every 0.7 s: 9 short messages, each with a header byte |

**Bit-reverse each data byte** to read values:
`rev(b) = int('{:08b}'.format(b)[::-1], 2)`. (Raw `0xFE` = `0x7F` reversed =
padding.)

A decoded broadcast burst (raw bytes, before reversing the data):

```
21 AA F4 D4      <- fan/boost
11 F6 4C
51 FE FE FE 04
31 FE FE 9A
33 FE FE 98
85 2E FE 30 FE FE CE
A3 FE FE FE FE FE FE 08
75 FE FE FE FE DE
3B C2 54 06      <- humidity
```

- **Humidity (RH %)** — `3B` message, **byte 1, bit-reversed = RH %** directly.
  (`rev(0xC2)=0x43=67 %`.) Shower-stimulus confirmed.
- **Boost / fan** — `21` message, **bit `0x02` of byte 2**: clear = ON, set =
  OFF. (`21 AA F4 D4` on / `21 AA F6 D6` off.) Byte 3 is an integrity copy of
  byte 2 with bit `0x20` cleared.

Full working notes, evidence, and open questions: [`docs/protocol.md`](docs/protocol.md).

---

## Hardware

Reference build (what this repo is tested on):

- **Raspberry Pi Pico W** (RP2040) running MicroPython
- An **RS485 transceiver** module (MAX485-class). Run it at **3.3 V**.
- Buck converter if powering from the unit's 12 V line; or just a USB supply.

**Use your own hardware — the protocol is the portable part.** Any of these work
if they can do 1200 8N1 and let you bit-reverse the data bytes:

- **ESP32 + ESPHome** — a natural target for an HA-native integration (UART
  read + a lambda to bit-reverse). Contributions very welcome; see the roadmap.
- **USB-RS485 dongle on a PC/Pi** — a 5 V CH340/SP485 dongle passively reads the
  bus; great for capturing and decoding (`tools/rs485_scan.py`,
  `tools/capture_frame.py`). Note: a **5 V** dongle reads the weakly-biased bus
  where a 3.3 V Pico transceiver may miss it.
- **Any MCU with a UART** — the decode logic is a dozen lines.

Wiring diagrams and pin-identification: [`docs/hardware.md`](docs/hardware.md).

---

## Quick start — read into Home Assistant (Pico W)

1. **Read the safety section** of `docs/hardware.md`. Seriously.
2. Identify the bus pins (continuity to the WS3471, then a voltage survey) and
   wire your RS485 module **receive-only** (RO → Pico UART RX GP5; DE/¬RE → GND).
3. Flash MicroPython, then set up credentials:
   ```
   cp firmware/sniffer/secrets.example.py firmware/sniffer/secrets.py
   # edit secrets.py: WiFi + your MQTT broker (secrets.py is gitignored)
   ```
4. Install the MQTT lib and copy the firmware to the board:
   ```
   mpremote mip install umqtt.simple
   mpremote cp firmware/sniffer/secrets.py firmware/ha/ha_read.py :
   mpremote cp firmware/ha/ha_read.py :main.py
   mpremote reset
   ```
5. It joins WiFi and publishes `nuaire/humidity` + `nuaire/boost` to MQTT with
   **Home Assistant auto-discovery** — the entities appear automatically. It is
   self-healing (watchdog + a broker-liveness probe that resets a wedged WiFi
   stack).

### Decode more of the frame (long-term logging)

The firmware also publishes all 16 candidate bytes on `nuaire/raw`. Log them for
a few days and correlate against reference temperature/humidity sensors to work
out what the unknown bytes mean — see [`docs/longterm-logging.md`](docs/longterm-logging.md)
(`tools/publish_raw_discovery.py`, `tools/analyze_longterm.py`).

---

## Repo layout

| Where | What |
|---|---|
| [`docs/protocol.md`](docs/protocol.md) | Living protocol findings (the important one) |
| [`docs/hardware.md`](docs/hardware.md) | Safety, pin identification, wiring |
| [`docs/longterm-logging.md`](docs/longterm-logging.md) | Decoding the remaining frame bytes |
| [`docs/vsc-mitm.md`](docs/vsc-mitm.md) | **Have a VSC display? Capture the temperatures** (MITM guide) |
| [`docs/roadmap.md`](docs/roadmap.md) | Phased plan + next steps |
| [`docs/prior-art.md`](docs/prior-art.md) | Other people's Nuaire work |
| [`firmware/ha/ha_read.py`](firmware/ha/ha_read.py) | Pico W → HA MQTT bridge (production) |
| [`firmware/sniffer/`](firmware/sniffer/) | Bench tools: baud finder, bit timing, decoders |
| [`tools/`](tools/) | Desktop capture/analysis (plain Python 3, stdlib) |
| [`captures/`](captures/) | Raw logs (immutable; see naming convention) |

---

## Contributing

Contributions are very welcome — especially **other units** (does an MRXBOX ECO2
vary? do MRXBOXAB / other Nuaire models speak the same bus?) and **other
hardware** (an ESPHome port is the big one).

**Have the MRXBOX-VSC display?** You can help unlock the temperatures — they're
polled by the display, not broadcast, so a capture from a bus with a real VSC on
it is the missing piece. Follow [docs/vsc-mitm.md](docs/vsc-mitm.md). Please read
[CONTRIBUTING.md](CONTRIBUTING.md): it covers the receive-only safety rule, the
capture-naming and "confirmed needs two captures" conventions, and how to report
your hardware/unit.

## Credits

Kicked off from the HA community thread linked above — thanks to everyone there
for the WS3471/pinout pointers. Licensed under [MIT](LICENSE).
