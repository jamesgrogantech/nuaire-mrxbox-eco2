# Hardware notes

## Safety — read first

The MRXBOX is a mains-powered appliance. Before opening the case or probing
anything:

1. **Isolate the unit at the fused spur / breaker and verify it is dead**
   before removing covers or attaching probes.
2. Only ever connect the Pico to the low-voltage side (the sensor/display bus,
   expected 0–12V). Never probe near the mains input, fan drivers, or heater
   circuits.
3. Re-check with the multimeter that no probe point exceeds ~12V DC to ground
   before connecting anything to the MAX485 module.
4. The Pico must be powered from USB (laptop), not from the unit, until the
   unit's supply rails are understood. A shared ground between unit and Pico is
   required for RS485 — connect bus GND to Pico GND, nothing else.

## The unit

- Nuaire MRXBOX ECO2 MVHR
- Display-controller connector on the bottom of the unit (controller not owned)
- Internal humidity/temperature sensor communicates with the main PCB over
  (presumed) the same bus
- WS3471 MSOP-8 near the PCB pin headers — clone of SP3485-class 3.3V RS485
  transceiver. Strong hint the bus is RS485 at 3.3V logic.
- 12V reported on a main-PCB control line (HA thread) — likely bus power for
  peripherals

## Identifying the bus pins (multimeter procedure)

Power OFF (verified dead):
1. Photograph the PCB and both sides of every connector. Save to `docs/img/`.
2. Continuity from candidate connector pins back to the WS3471: pins 6 (A) and
   7 (B) of the MSOP-8 are the bus lines; pin 5 is VCC, pin 4 GND. That maps
   connector pins to A/B/VCC/GND definitively without ever powering up.

Power ON (covers on where possible, probes already attached). Identify pins by
voltage signature — never by position; there is no standard pin order:

| Pin | Signature (DC volts to GND) |
|---|---|
| GND | 0V rock steady. Find first: probe pin pairs until one reads steady 12V; the lower pin of that pair is GND |
| 12V supply | Steady ~12V, no flicker |
| A (non-inverting) | Idle ~1.5–3.3V, the **higher** of the two data lines, flickers with traffic |
| B (inverting) | Idle lower than A (often 0.5–1.5V), flickers with traffic |

3. A vs B polarity: meter across the two data lines. Positive idle
   differential (typically +0.2V or more) → red probe is on A; negative →
   swap. Flicker = traffic flowing.
4. If one line sits at 0V and the other at 3.3V steady, it may be
   single-ended UART instead — note it, plan changes. If both data lines
   read ~0V steady, the bus may just be quiet — wait 30s+, sensors often
   poll infrequently.
5. Getting GND right matters most: tying the unit's 12V rail to Pico GND
   shorts it through USB ground and can damage the unit's PSU. Misplacing
   12V on MAX485 A/B is survivable (RS485 pins tolerate +12V) but verify
   before wiring anyway.
6. Probe slips short adjacent live pins — use needle probes or back-probe
   the cable, one hand, steady surface.

Record everything found in this file with photos.

## Wiring: Pico 2W ↔ MAX485 (receive-only)

```
MAX485 module          Pico 2W
------------          --------
VCC        ->  3V3 (see note) or VBUS/5V
GND        ->  GND        (also to bus GND)
RO         ->  GP5 (UART1 RX)
DI         ->  (unconnected)
DE         ->  GND  ─┐  receive-only: driver disabled,
/RE        ->  GND  ─┘  receiver always on
A          ->  bus A
B          ->  bus B
```

Notes:
- The board turned out to be a Pico W (RP2040), not a Pico 2W. **RP2040 GPIO
  are NOT 5V-tolerant.** Do not power a classic MAX485 at 5V with RO wired
  straight to GP5 — its ~5V output can damage the pin. Options, best first:
  1. Use a 3.3V transceiver module (MAX3485/SP3485) powered from 3V3.
  2. Try the blue "MAX485 TTL" module at 3.3V VCC — many receive fine at
     3.3V; verify RO idles at ~3.3V and data looks clean.
  3. If the module must run at 5V: divider on RO (e.g. 2k2 over 3k3) into GP5.
- Many cheap modules have 120Ω termination and A/B bias resistors fitted.
  For pure sniffing on an existing (already biased/terminated) bus, remove or
  disable the module's termination if reception looks corrupted.
- Keep the stub from the bus tap to the MAX485 short (<30cm).

## Later phase: powering the Pico from the unit

The display connector's 12V rail can power the Pico permanently (it powers the
official display normally). Not direct — VSYS max 5.5V:

- Buck converter (Mini-360/MP1584) set to 5V **before** connecting → VSYS
  (pin 39); bus GND → Pico GND
- Verify rail voltage under load and no sag with the ~50mA Pico W draw
- If USB may be plugged in simultaneously: Schottky diode in series
  buck→VSYS (per Pico datasheet) to prevent back-feed
- Defer until Phase 2+: during discovery, external power = one less unknown

## Later phase: display connector

Once the sensor bus is decoded, compare against the bottom display connector —
same transceiver/bus would mean commands (speed set, boost) travel there too.
MITM sniffing needs a controller (buy/borrow — deferred).
