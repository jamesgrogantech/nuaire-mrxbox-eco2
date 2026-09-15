# Capturing the temperatures — MITM sniff a real MRXBOX-VSC

**Who this is for:** anyone who has the official **MRXBOX-VSC** touchscreen
controller connected to their unit. The temperatures (Outside + Indoor) and other
data shown on the VSC are **not in the unit's autonomous broadcast** — the display
gets them by *polling* the unit (see [protocol.md](protocol.md)). If you tap the
bus while the VSC is running, you can capture that poll exchange and we can
finally decode the temperature fields. **Please share your capture** (open a
unit-report issue or PR, or post to the [HA thread](https://community.home-assistant.io/t/nuaire-mrxbox-interface-for-home-assistant/573933)).

This guide uses a **Waveshare ESP32-S3-RS485-CAN**, but any 5 V RS485 receiver
works — only the pin numbers change.

> ⚠️ Safety: the data cable is **SELV 12 V** (low voltage) — safe to handle — but
> the MVHR itself is mains-powered. Only touch the data terminals. Work
> **receive-only** (never transmit): a wrong transmission could disrupt the bus
> between the display and unit.

## How the bus works (why a plain tap is enough)

The VSC and the unit share **one** RS485 pair (A/B), half-duplex — they take
turns. The unit continuously broadcasts its 9 status messages
(`21 11 51 31 33 85 A3 75 3B`). The VSC, on top of that, sends **poll requests**
that the unit answers with **responses** carrying the temperatures.

So if you log *everything* on the pair and ignore the 9 known broadcast messages,
what's left is the poll exchange. A single passive tap can't tell you *who* sent a
frame, but you can tell by elimination (known headers = the unit's broadcast) and
by timing (a request, a short gap, then a response). That's enough to decode the
temperatures. For unambiguous direction, see [In-line MITM](#in-line-mitm-advanced)
at the end.

## What you need

- A **Waveshare ESP32-S3-RS485-CAN** (onboard isolated RS485).
- Your VSC connected to the unit as normal (the 4-core SELV cable to the fan's
  `NET` terminal).
- A way to reach the A/B pair in parallel — the VSC's screw terminals, the fan's
  `NET` terminal, or a junction box. **Don't cut the cable**; tap across it.
- USB cable to a laptop (to power the board and read the capture).

## Board RS485 details (verified)

| Signal | ESP32-S3 GPIO |
|---|---|
| RS485 TX | GPIO17 |
| RS485 RX | GPIO18 |
| DE / flow-control (`talk_in`) | GPIO21 |
| Terminals | `A`(+) / `B`(−) |

Set the onboard **120 Ω termination jumper to `NC` (disabled)** — the bus is
already terminated by the VSC and the unit; adding a third terminator loads the
signal.

Sources: [Waveshare wiki](https://www.waveshare.com/wiki/ESP32-S3-RS485-CAN),
[community board doc](https://github.com/Sleeper85/esphome-yambms/blob/main/documents/README/Board_Waveshare_ESP32-S3-RS485-CAN.md).

## Wiring (passive tap)

```
   VSC  A ─────┬──────  A  unit (NET)
   VSC  B ─────┼┬─────  B  unit (NET)
               ││
    board A ───┘│   (GPIO17/18 transceiver, RX only)
    board B ────┘
    board GND ── bus 0V / SELV negative (shared reference)
```

- Board `A` → bus `A`, board `B` → bus `B`, board `GND` → the cable's 0 V.
- Termination jumper: **NC**.
- Do **not** power the board from the unit — power it from the laptop USB.
- If you're unsure which of the 4 cores are A/B: with everything powered, meter
  the pair — idle differential **A > B, ~0.3 V** (see [hardware.md](hardware.md)).
  A/B swapped just means you'll see line noise / no clean frames — swap and retry.

## Capture

1. Flash MicroPython to the ESP32-S3, then run the capture tool over USB:
   ```
   mpremote connect <port> run firmware/esp32-s3/vsc_capture.py
   ```
   (It holds DE low and only listens. To log headless, save it as `main.py` and
   add WiFi/MQTT like `firmware/ha/ha_read.py`.)
2. **Sanity check:** you should immediately see the unit's broadcast — the 9
   headers `21 11 51 31 33 85 A3 75 3B` repeating ~every 0.7 s. If you do, your
   baud (1200 8N1), polarity, and wiring are correct.
3. **Provoke a poll:** on the VSC, sit on the **Home** screen (it shows Outside +
   Indoor temperature) and open **Menu → Diagnostics** (it queries the unit's
   sensors). The tool flags any message whose header is *not* one of the 9 with
   `<<< NON-BROADCAST (poll/response?)` — those lines are the poll exchange.
4. **Write down what the VSC shows** at capture time: Outside temp, Indoor temp,
   fan speed, filter status. You'll match those numbers to bytes.

## Decode the temperatures

- In the non-broadcast frames, look for a byte whose **bit-reversed** value equals
  a temperature the VSC shows (e.g. Indoor 21 → a byte `rev(b)=21`, or a scaled
  form like `42` = 21×2, or `210` = 21×10). The tool prints the bit-reversed
  value for you.
- **Confirm with a stimulus:** warm the extract air (a hairdryer near the extract
  grille for a minute) — the VSC's Indoor/Extract temperature will rise. The byte
  that moves with it is the extract-temp field. Do the same logic for Outside/
  Supply. This is exactly how humidity and boost were confirmed.
- Two captures showing the same field = **CONFIRMED** (see
  [CONTRIBUTING.md](../CONTRIBUTING.md)); one = `HYPOTHESIS`.

## Share it

Save the capture (naming per [captures/README.md](../captures/README.md)) and
open a unit-report issue or PR, noting your unit model, the VSC firmware if
visible, and the temperatures displayed at capture time. That's what lets us add
temperatures to the Home Assistant integration for everyone.

## In-line MITM (advanced)

A single tap can't prove direction. For certainty, break the bus and bridge it
through **two** RS485 transceivers — one facing the VSC, one facing the unit —
and have the ESP32-S3 forward bytes both ways while logging each side with a
direction tag. The Waveshare board has only one RS485 port, so add a second
transceiver (e.g. a MAX485 module) on a spare UART (ESP32-S3 has UART0/1/2).
This is only needed to *label* who spoke; for decoding the temperatures the
passive tap above is normally sufficient.
