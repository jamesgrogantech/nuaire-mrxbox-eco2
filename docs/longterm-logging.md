# Long-term logging — decoding the remaining frame bytes

Only humidity (`3B` b1) and boost (`21` b2 bit 0x02) are confirmed. The
broadcast carries ~14 other data bytes whose meaning is unknown (temperature?
fan RPM? filter/run-hours counter? error flags?). The way to decode them is to
log every byte over days and correlate against known reference signals.

The firmware publishes all 16 candidate bytes (bit-reversed decimals, fixed
order) to **`nuaire/raw`** every 15s, e.g.:

```
nuaire/raw = 111,50,85,111,107,89,25,64,42,99,32,123,116,12,115,16
```

Column order (RAWMAP in `firmware/ha/ha_read.py`):
`11_1, 11_2, 21_1, 21_2, 21_3, 31_3, 33_3, 3B_1, 3B_2, 3B_3, 51_4, 75_5, 85_1, 85_3, 85_6, A3_7`
(`21_2` = boost, `3B_1` = humidity, `33_3` = the retracted "temperature".)

## Reference signals to correlate against

- **Outdoor temperature** — add the free **Met.no** integration in HA
  (Settings → Devices & Services → Add → Met.no). A byte that tracks it is the
  outdoor/intake sensor. (The offline analyzer can also pull this from
  open-meteo.)
- **Time of day** — a byte with a daily sine-like cycle is a temperature.
- **Humidity / boost** — already known; use to spot linked fields.
- **Deliberate events** — note timestamps when you change fan speed, run a
  shower, open a window, or (later) swap/reset the filter.

## Method A — Home Assistant native (least effort)

1. Merge `docs/ha-diagnostics.yaml` into `configuration.yaml` under the
   top-level `mqtt:` key and restart HA. It creates 16 `diagnostic` sensors
   ("MRXBOX raw 33_3" etc.) that HA records automatically.
2. Add **Met.no** for outdoor temp.
3. After a few days, open **History**, overlay each `MRXBOX raw *` sensor
   against Met.no outdoor temp / time / humidity. Whichever tracks outdoor
   temp is the outdoor sensor; a slow upward ramp is a counter; a daily cycle
   is a temperature.

## Method B — raw CSV + offline analysis (most powerful)

1. Run the logger on any always-on box (HA SSH/Terminal add-on, a spare Pi, or
   a laptop). Needs only the mosquitto clients:
   ```
   ./tools/log_raw.sh 192.168.0.54 pico your-mqtt-pass ~/nuaire_raw.csv
   ```
   Leave it running for days (safe to stop/restart — it appends).
2. Analyse (stdlib only; add lat/lon for an open-meteo outdoor-temp pull):
   ```
   python3 tools/analyze_longterm.py ~/nuaire_raw.csv
   python3 tools/analyze_longterm.py ~/nuaire_raw.csv 51.48 -0.10
   ```
   It reports per column: uniqueness/range (live vs fixed), upward trend
   (counter), and correlation with time-of-day / outdoor temp / humidity.

## Reading the results

- `CONST` → fixed value, not a sensor.
- `trend up` → a counter (run-hours, filter timer, cycle count).
- `OUTDOOR+high` → that byte is the outdoor/intake temperature.
- `time+high` (no outdoor match) → a daily-cycling temperature (extract/supply).
- `humidity+high` → a humidity-derived field.

Confirm any candidate the same way we confirmed humidity/boost: a deliberate
stimulus (warm a sensor, change a mode) and check the byte moves.
