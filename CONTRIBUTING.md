# Contributing

Thanks for helping reverse-engineer the Nuaire MRXBOX bus. This is a community
effort — different units, firmware revisions, and interface hardware all add
signal. A few conventions keep the findings trustworthy.

## Safety (non-negotiable)

- The MVHR is **mains-powered**. Only ever touch the **low-voltage data bus** on
  the controller connector. If in doubt, isolate the unit at the consumer unit.
- Work **receive-only** until the framing and a specific write are understood:
  disable your transceiver's driver (on a MAX485, tie DE and ¬RE to GND). Do not
  transmit onto the bus without a written, reviewed plan (see
  `docs/protocol.md` → write-back preconditions).
- The RP2040 is **not 5 V-tolerant** — 3.3 V transceiver, or divide the RX line.

## What's especially valuable

- **Other units / models.** Captures from a different MRXBOX ECO2, or from
  MRXBOXAB / other Nuaire models — do they use the same 1200 8N1, MSB-first,
  9-message broadcast? Tell us the exact model and firmware/label if visible.
- **Other hardware ports.** An **ESP32 / ESPHome** implementation is the most
  requested. The decode is small; the value is a native HA integration.
- **New decoded fields.** Temperatures, fan RPM, filter/run-hours, error flags —
  see `docs/longterm-logging.md` for the correlation approach.
- **Calibration.** Cross-checking humidity against a known hygrometer, etc.

## How findings get confirmed

- A finding is **CONFIRMED** only when reproduced in **at least two captures**,
  with the capture files cited. Otherwise mark it `HYPOTHESIS:` in
  `docs/protocol.md`. This rule is why the decoded fields are trustworthy —
  please keep it.
- Confirm behaviour with a **deliberate stimulus** where you can (toggle boost,
  run a shower for humidity, change fan speed) rather than a single snapshot.

## Captures

- Capture files are **immutable once committed** — never edit an existing one;
  add a new one.
- Name them per [`captures/README.md`](captures/README.md) and **reference them
  from `docs/protocol.md`** so every claim is backed by data.
- Include enough context in the capture or its commit message: unit model, baud,
  wiring, and what stimulus (if any) was applied.

## Code conventions

- **Desktop tools** (`tools/`): plain Python 3, standard library only where
  possible. Run as `python3 tools/<script>.py <capture>`.
- **MicroPython** (`firmware/`): target the Pico W port, dependency-free
  (`machine` / `rp2` / `network` only) so files copy straight to the board with
  `mpremote`. Keep `firmware/ha/ha_read.py` flat and ASCII-only — that exact
  structure is the one verified stable on the bench (see its header comment).
- **Never commit secrets.** `firmware/sniffer/secrets.py` is gitignored; copy it
  from `secrets.example.py`. Don't hard-code SSIDs, passwords, tokens, or your
  personal LAN IPs into tracked files — take them as arguments or from
  `secrets.py`.

## Pull requests

1. Fork, branch, and make focused changes.
2. If you decode or change protocol behaviour, update `docs/protocol.md` (with
   the citing captures) in the same PR.
3. Describe your hardware and unit in the PR so results are reproducible.
4. Keep receive-only safety intact unless the PR is explicitly a reviewed
   write-back experiment.

## Reporting a unit or issue

Open an issue with: your Nuaire model and any firmware/label markings, your
interface hardware (MCU + transceiver, or dongle), the baud/framing you observed,
and a short capture or the decoded broadcast if you have one. Even "same as the
README on my ECO2" is useful — it turns a single-unit finding into a confirmed
one.
