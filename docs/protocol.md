# Protocol findings (living document)

Status legend: **CONFIRMED** (reproduced in ≥2 captures, capture files cited) ·
**HYPOTHESIS** (seen once / inferred) · **RULED OUT**.

## Physical layer

| Property | Status | Value | Evidence |
|---|---|---|---|
| Medium | CONFIRMED | RS485 differential | WS3471 on PCB; live bus metered |
| Baud rate | **CONFIRMED 1200** | 825us/bit measured (Pico pulse timing), fits all pulses to 0.3% | 2026-08-28 |
| Serial params | CONFIRMED | 8N1 | clean byte-stable decode |
| Idle state | CONFIRMED | biased idle, A>B | meter 2026-08-27, see below |
| Bus is live | CONFIRMED | unit drives/biases the pair | meter 2026-08-27 |

## 2026-08-27 meter check — bus CONFIRMED live (module unplugged, unit powered)

Readings at the connector data pair, our module disconnected:
- A→GND: ~0.6–1.2V, B→GND: ~0.2–0.3V, **A−B: ~+0.3V**

Interpretation: a real RS485 bus, biased by the unit at idle, correct polarity
(A > B, matches our wiring). **Confirms: the connector pins are the RS485 pair,
pin ID correct, unit side powered and driving the bus.** Rules out the
worst-case "wires not on bus / unit dead."

The idle differential is weak (~0.3V) → gentle/high-impedance bias. Leading
suspects for why the unit ignored our polls, both testable:
1. **Termination loading** — our cheap MAX485 module likely has a 120Ω
   terminator; across a weakly-biased bus it crushes signal and loads our
   marginal 3.3V driver. Fix: disable/remove the module's 120Ω, re-poll.
2. **Weak 3.3V drive** — classic MAX485 is a 5V part; at 3.3V the differential
   may be too weak for the unit's receiver (our own receiver still hears the
   echo). Fix: proper 5V transceiver — Waveshare USB-RS485 (SP485EEN) on order.

Note: the blue MAX485 modules are fine — A/B measures 120Ω (onboard
terminator), not a fault. A transient "0Ω" reading was just a flaky probe
contact on the screw terminal. Leading suspect is the weak 3.3V drive; the
5V USB dongle is the planned fix. Retest plan is laptop-side (mbpoll/pymodbus)
once the dongle lands.

## 2026-08-26 session — Modbus master polling, no slave replies

Setup: became bus master. DE on GP0, DI on GP4, RO on GP5. **/RE left tied to
GND** → receiver always on → we hear our own transmission as an echo. Firmware
(modpoll.py) strips the leading echo before judging replies.

Swept, all echo-stripped, looking for a genuine `addr fc bytecount …` reply:
- addr 1–247, fc 0x01/0x02/0x03/0x04, register 0, 9600 8N1 → **0 replies**
- addr 1–8, fc 0x03, {2400,4800,9600,19200,38400} × {8N1,8E1,8O1} → **0 replies**

Every non-empty result was our own request echoed back (payload
`aa 03 00 00 00 08 …`), sometimes with CRC bytes mangled by a parity/baud
mismatch so echo-stripping missed it. **No genuine Modbus response observed.**

**Load-bearing caveat:** the echo is generated locally (our driver → our own
receiver). It appears even with A/B disconnected from the unit. So today proves
the RS485 *module* works and proves **nothing** about whether our signal
reaches the MVHR, nor that the unit speaks Modbus.

Open leads, cheapest first:
1. ~~A/B may be swapped~~ **RULED OUT 2026-08-27.** Tested via software UART
   inversion (INV_TX|INV_RX = electrical A/B swap), addr 1–32, fc03, 9600 +
   19200. No genuine reply in either polarity — only inverted-idle 0xFF noise.
2. Unit may not be a Modbus slave on the display port at all (proprietary
   display protocol) — would need a real display to capture (Option C).
3. Confirm A/B physically reach a live unit-side transceiver (meter the
   connector data pair with our module unplugged, unit powered).

### 2026-08-27 sweeps VOID — unit not connected
All the polling above (both polarities, addr 1–247, all FCs/bauds/parities)
was run with the module's A/B **not actually landed on the unit connector**.
Every result was pure local self-echo. These runs prove only that the RS485
module works; they say nothing about the MVHR. Re-run with A/B on the unit.

## 2026-08-28 — BREAKTHROUGH: unit broadcasts periodically (CH340 5V dongle)

Swapped to a 5V USB-RS485 dongle (CH340 + MAX485, /dev/cu.usbserial-11430).
**Passive listen** (no polling) now sees real traffic the 3.3V Pico missed:

- **Periodic broadcast, ~0.7s repeat period** (very stable: 0.702–0.712s).
- **54-byte frame**, ~90% byte-stable across repeats; a handful of bytes vary
  = live data + probable checksum.
- **Baud ≈ 1990** (non-standard; 1955–2005 all read ~90% stable).
- Frame syncs at 8N1 → polarity correct, A/B not inverted.
- So the unit does NOT need a display to talk — it broadcasts status on its
  own. Earlier "silent bus" was the 3.3V receiver missing the weak signal.
- Sample frames saved: captures/20260828-unit-broadcast-1990baud.log

**Blocker — need exact baud + clean bytes.** Autocorrelation over a 12s
continuous capture confirms **frame period = 54 bytes** (65.5% self-match,
harmonics at 108/162). But folded at that exact period, byte agreement is only
**~56%** — the bytes genuinely slip. Cause: non-standard ~2000 baud + no
inter-byte gaps → UART start-bit detection drifts frame-to-frame, and a UART
re-syncs every byte so it can't resolve baud finer than ±2–3%. No UART setting
fixes this.

**Decision: logic analyser is now the right tool** (its use case has arrived —
real traffic exists). Clip an 8-ch LA on the dongle's TTL RO line (or across
A/B) → sample at ≥1 MHz → PulseView measures true bit width = exact baud, and
its UART decoder (adjustable baud/parity/bit-order/inversion) yields clean,
correctly-framed bytes. Then: stimulus-correlate (boost / humidity / speed) to
map fields. Buy: any cheap 8-ch "24MHz logic analyser" (~£8, Cypress FX2
clone), works with sigrok/PulseView on macOS.

### On-wire structure (2026-08-28, burst timing)
Each broadcast burst is a very consistent **0.500s long**, repeating every
~0.7s (so ~0.2s idle between). 54 decoded bytes in 0.5s is far below 1990-baud
capacity → **the bytes are gapped within the burst, not a contiguous stream**
(or true byte count < 54 and framing noise inflates it). Host USB timestamps
(~1-16ms) can't measure the 500µs bit, so exact baud still needs raw bit
sampling. Next free attempt: Pico as logic analyser (time_pulse_us on the
MAX485 RO line, baudfind.py) — one bit ~500µs, easily measured.

## CLEAN DECODE achieved — 1200 baud 8N1 — 2026-08-28
Baud found by Pico pulse-timing (bittiming.py + raw low-pulse analysis): the
single-bit low pulse is a tight 825us cluster (n=524, 820–827) = 1200 baud.
The earlier "~2000 baud" was a false UART lock; decoding at 1990 oversampled
~1.7x → the 56% smear. At 1200 baud 8N1 the broadcast decodes byte-STABLE,
repeating identically every ~0.7s as 9 gap-separated messages:

```
21 AA F4 D4
11 F6 4C
51 FE FE FE 04
31 FE FE 9A
33 FE FE 98
85 2E FE 30 FE FE CE
A3 FE FE FE FE FE FE 08
75 FE FE FE FE DE
3B C2 54 06
```

Each message: distinctive header byte (21/11/51/31/33/85/A3/75/3B), then data,
lots of 0xFE (padding or "no-change"?), likely a trailing check/terminator.
Now that decode is stable, redo stimulus correlation (boost, humidity) to
pinpoint the EXACT byte — earlier value-space hits (9C/90 boost, 7C/80 RH)
were the smeared readings; the clean bytes will be different and exact.
Saved: captures/20260828-DECODED-1200baud-rest.log

## Framing

Older notes below predate the clean decode (kept for history):

- Inter-frame gap length (drives gap-based frame splitting in tools/analyze.py)
- Fixed-length or length-byte frames?
- Leading address/sync byte? (Modbus RTU-style: addr, func, data, CRC16-lo, CRC16-hi)
- Nuaire MRXBOXAB variants reportedly speak Modbus-ish — check CRC16-Modbus
  over trailing 2 bytes early.

## KEY PROPERTY: data is MSB-first (bit-reversed vs UART) — 2026-08-28
The device transmits each byte MSB-first, so a standard LSB-first UART reads
every byte bit-reversed. To interpret data values, bit-reverse each byte:
`rev(b) = int('{:08b}'.format(b)[::-1], 2)`. This is why raw frames are full of
0xFE (= 0x7F reversed = padding) and why humidity looked like noise until
reversed. Header/framing bytes: keep raw for matching; reverse DATA bytes.

## Decoded fields

### Humidity — DECODED to RH% — 2026-08-28
`3B` message, **byte 1, bit-reversed = relative humidity %**.
Evidence: shower rise gave rev-values 67→70→72; 5-min dry-out hovered
70–73 (%). ~71% in a used bathroom is physically correct. Byte 3 is a
mirror/check byte. (Cross-check against a hygrometer to confirm exact scale,
but it reads as direct RH%.)

### Fan/boost — PINPOINTED (clean, 1200 baud) — 2026-08-28
Boost toggle diff (tools/diff_frames.py), only the `21` message changed:
- boost ON : `21 AA F4 D4`
- boost OFF: `21 AA F6 D6`
Fan/boost state = **bit 0x02 of byte index 2 in the `21` message** (ON→0,
OFF→1). Byte 3 mirrors byte 2 with bit 0x20 cleared (integrity copy — useful
for constructing valid write frames later). This SUPERSEDES the old smeared
9C/90 reading below.

### Fan/boost state — OLD smeared reading (pre-decode, superseded) — 2026-08-28
Stimulus test: captured the broadcast byte-histogram boost-OFF vs boost-ON
(alignment-independent, so it reflects real on-wire value changes, not framing).
Result: byte value **0x9C vanished** boost→on (3.8% → 0.0%, 29 occurrences → 0)
and **0x90 rose** by the same margin (1.7% → 5.1%). Total variation distance
0.082 — small but unambiguous (a value going from 29 hits to 0 is not noise).
So the ~0.7s broadcast **encodes fan/boost state**, carried by a byte that
reads (bit-smeared) as 0x9C at rest / 0x90 on boost. Once exact baud + frame
alignment are known, this position is pinpointable → read speed1/2/3 + boost.
Signatures saved: captures/sig-boost-{off,on}-20260828.json.

### Temperature — NOT CONFIRMED (retracted) — 2026-09-13
Earlier guessed as msg 33 byte3 bit-reversed (=25, matched a ~24C room). But a
warm-the-extract stimulus test showed msg 33-b3 (and the other candidates
85-b3=12, A3-b7=16, 51-b4=32) are **perfectly constant** — no jitter, no
response to warming — while humidity jitters normally. They also don't map to
sensible heat-recovery duct temps (room 24/outside 19 would imply exhaust ~20,
supply ~22; observed 25/12/16/32 don't fit). Conclusion: these are fixed
status/config values, NOT live temperatures. This unit's broadcast does not
appear to carry a usable temperature. Temperature entity removed from HA.
(Could revisit via long-term logging to see if any byte tracks day/night temp.)

### Humidity (internal RH sensor) — CONFIRMED — 2026-08-28
Shower stimulus, 8-snapshot time-series over 5min (captures/humidity-
timeseries.json). A byte value climbed monotonically then plateaued as RH rose:
0x7C (124) appears at 3.7% during warm-up, then gives way to 0x80 (128) at 5.5%
once steamy (7E/126 seen mid-transition). Dry baseline had neither elevated.
Classic analog-sensor curve → the broadcast carries the **internal RH reading**,
reading (bit-smeared) ~0x7C dry / ~0x80 humid. Also 0x70 fell 6.0%→1.8% and
stayed (possible related field or humidity auto-boost threshold).
Once clean-decoded: map the byte to actual RH%.

### Fan / mode — `85` message — HYPOTHESIS (2026-09-15)
The `85` message (`85 2A FE 2E FE FE D4`, positions 85_1/85_3/85_6 bit-reversed)
is the only *varying* non-humidity data in the broadcast. Over 50 h it steps
between a small discrete set (85_1 in {12,52,76,84,116}) at intervals of hours,
sometimes within an hour. Evidence it is a **fan speed / operating mode**, not a
sensor value:
- Discrete levels, revisited across days — not a continuum.
- Switches faster than any thermal mass could (rules out temperature; see below).
- `85_1 = 84` appeared only during the highest humidity (71 %), hinting the unit
  modulates airflow with humidity demand (this is a demand-controlled MVHR:
  manual gives speeds SPD1 20% / SPD2 50% / SPD3 100%, supply + extract).
NOT yet mapped to specific speeds — needs a stimulus (change speed / shower) with
a live watch to pin values to 20/50/100 %. Note: an earlier "arithmetic step-2"
reading of these bytes was a bit-order error (double bit-reversal); the true
values are the sensor values above.

### Temperatures are NOT broadcast — they are POLL-ONLY — CONFIRMED (2026-09-15)
The MRXBOX-VSC controller **does** show Outside + Average-Indoor temperature, and
the unit has an Extract and a Supply temperature sensor (VSC manual §4.1, §9,
docs/img or Downloads). But the temperatures are **not present in the unit's
autonomous broadcast**. Three independent lines of evidence:
1. **Full frame captured** (firmware/sniffer full_dump over UART, 2026-09-15):
   the broadcast is exactly the 9 known messages and **every non-mapped byte is
   `0xFE` padding** (bit-reversed 127). There is no hidden data byte. Complete
   frame, data bytes bit-reversed:
   ```
   21: 85, boost, boost-mirror      31: 89        A3: 16
   11: 111, 50                      33: 25        75: 123
   51: 32                           85: 84, 116, 43 (fan/mode)   3B: hum, 42, 3b_3
   ```
2. **50 h of logging**: no byte tracked the outdoor swing (13→24 °C, two nights).
3. **The unit clearly has the data** (sensors + display), so the display must
   obtain it by **polling** the unit (request/response) — which we have never
   seen, having never had a display on the bus. Matches the "display is bus
   master" hypothesis in Bus roles below.
Implication: reading temperatures (and likely the run-time counters / richer
diagnostics) requires either **MITM-sniffing a real MRXBOX-VSC** to capture the
poll + response, or discovering the poll command by fuzzing (Modbus already
returned nothing — the poll is proprietary). See docs/roadmap.md.
Caveat: the full-frame scan was ~20 s (USB too flaky for minutes), so a temp
message broadcast *rarer* than ~20 s is unlikely but not fully excluded; a
headless full-frame logger would close this.
Lingering candidate: `33_3` is a stable `25` and *could* be a broadcast
indoor/extract temp that simply doesn't move (indoor ~22–25 °C all week). The
earlier warm-the-extract test didn't move it (retracted above), but may not have
reached the sensor — worth one more strong stimulus test.

_Template for full field entries once decoded:_

### <field name>  — <STATUS>
- Frame: `<hex bytes with field highlighted>`
- Offset/length: byte N, M bytes, encoding (uint8 / int16-LE / BCD / scaled x0.1)
- Meaning: e.g. exhaust air RH %
- Evidence: captures/`<file>` lines N–M; cross-checked against <independent
  observation, e.g. breathing on the sensor raised RH reading>

## Checksum

UNKNOWN. tools/analyze.py tests sum8, XOR, CRC8 (poly 0x07/0x31), and
CRC16-Modbus automatically over every gap-split frame.

## Bus roles

**HYPOTHESIS (2026-08-26): display connector is silent unless polled.**
Evidence: captures/20260826-1248 and -1250 — zero bytes over 5+ min at 9600,
including during a boost-switch toggle (boost is a switched-live input, not
bus). Zero bytes ≈ zero line transitions, so this is not a wrong-baud
artifact. Likely the (absent) display is the bus master and the unit only
answers polls. Options from here:
1. Tap the internal sensor↔PCB header inside the unit — traffic may flow
   there unprompted (original Phase 1 plan).
2. Active polling from the Pico (requires DE rewired to a GPIO, and a
   decision to transmit — see write-back preconditions below; a Modbus RTU
   read poll sweep is the lowest-risk candidate since read function codes
   are non-mutating).
3. Borrow/buy a real display and MITM it.

## Write-back experiments

### 2026-08-28 — broadcast-echo hypothesis: NEGATIVE
Via the CH340 dongle (5V, auto-direction, gap-timed TX at 1200 baud), sent
5x `21 AA F4 D4` (boost-ON, = raw replay of the unit's own boost-on 21 message)
while boost switch was OFF. The broadcast `21` message stayed `F6 D6` (off) —
no effect. Conclusion: commands are NOT the broadcast frame echoed back. The
display→unit command format is unknown (never captured — no display present).
Two things also unverified: (a) that our TX physically reached the unit (only
one device on bus, nothing independent confirmed the frame landed); (b) whether
this unit honours bus commands at all vs only the switched-live inputs.

Bit-order note for TX: our LSB-first UART transmitting raw byte W puts W on the
wire such that the MSB-first unit reads rev(W). Replaying raw received bytes
reproduces the unit's own wire waveform (double-reverse cancels), which is what
we did — so bit order was not the failure.

Realistic paths to write-back:
1. Sniff a real Nuaire VSC controller (MITM between it and unit) to capture
   genuine display→unit commands — the reliable route.
2. Two-device rig to at least VERIFY our TX lands: Pico as independent RX
   monitor in parallel while the dongle transmits (separates "TX broken" from
   "command format wrong").
3. Otherwise: ship READ-ONLY (humidity/temp/fan state) to HA now; add control
   later once a VSC is available.

## Write-back (Phase 3 — earlier notes)

Preconditions before any transmit: framing CONFIRMED, checksum CONFIRMED,
target frame captured verbatim from a real device, replay plan written here
and reviewed. See CLAUDE.md working conventions.
