# Captures

Raw sniffer logs. **Immutable once saved** — analysis conclusions in
docs/protocol.md must cite these files.

## Naming

```
YYYYMMDD-HHMM-<condition>-<baud>-<params>.log
```

Examples:
- `20260830-1015-idle-9600-8N1.log` — unit idling, nothing touched
- `20260830-1042-breath-on-sensor-9600-8N1.log` — RH stimulated
- `20260830-1101-speed2-9600-8N1.log` — switched-live speed change during capture

`<condition>` is the physical stimulus — it is what makes field decoding
possible later. One stimulus per capture. Note exact timing of the stimulus in
a comment line inside the file, e.g. `# t=41200ms breathed on sensor`.

## Capturing

```
mpremote run firmware/sniffer/main.py | tee captures/$(date +%Y%m%d-%H%M)-idle-9600-8N1.log
```

Then: `python3 tools/analyze.py captures/<file>.log`
