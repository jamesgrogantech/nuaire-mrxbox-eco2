# Nuaire MRXBOX ECO2 — bus reverse engineering

Reverse engineering the (suspected RS485) controller/sensor bus of a Nuaire
MRXBOX ECO2 MVHR unit with a Raspberry Pi Pico 2W + MAX485, aiming at a Home
Assistant integration with real feedback (temps, humidity, fan state) and
eventually control (speed, boost).

Prior art: [HA community thread](https://community.home-assistant.io/t/nuaire-mrxbox-interface-for-home-assistant/573933)

| Where | What |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Project context, conventions, key unknowns |
| [docs/roadmap.md](docs/roadmap.md) | Phased plan + next steps |
| [docs/hardware.md](docs/hardware.md) | Safety, pin identification, wiring |
| [docs/protocol.md](docs/protocol.md) | Living protocol findings |
| [firmware/sniffer/](firmware/sniffer/) | Pico 2W MicroPython: baud finder + sniffer |
| [tools/analyze.py](tools/analyze.py) | Desktop capture analysis |
| [captures/](captures/) | Raw logs (see naming convention) |

## Quick start

1. Read the safety section of `docs/hardware.md`. Seriously.
2. Identify bus pins (continuity to the WS3471, then voltage survey).
3. Wire the MAX485 receive-only, flash MicroPython on the Pico 2W.
4. `mpremote run firmware/sniffer/baudfind.py` → baud rate.
5. Set `BAUD` in `firmware/sniffer/main.py`, capture:
   `mpremote run firmware/sniffer/main.py | tee captures/<name>.log`
   — or wireless: set up `firmware/sniffer/netsniff.py` (see its docstring),
   power the Pico from a wall adapter, then
   `nc <pico-ip> 9000 | tee captures/<name>.log`
6. `python3 tools/analyze.py captures/<name>.log`
7. Write findings into `docs/protocol.md`.
