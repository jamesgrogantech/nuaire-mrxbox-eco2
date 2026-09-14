#!/bin/sh
# Method B: long-term raw-frame logger for the Nuaire MRXBOX bridge.
# Subscribes to nuaire/raw and appends "<unixtime>,<16 bytes>" to a CSV.
# Needs only the mosquitto clients (mosquitto_sub). Run on any always-on box:
# the HA host (SSH/Terminal add-on), a spare Pi, or a laptop left running.
#
#   ./log_raw.sh <broker_host> <mqtt_user> <mqtt_pass> [csv_path]
#   ./log_raw.sh 192.168.1.10 pico 'your-mqtt-pass' ~/nuaire_raw.csv
#
# Runs forever; safe to Ctrl-C and restart (appends). Leave it going for days,
# then feed the CSV to tools/analyze_longterm.py.

HOST="$1"
USER="$2"
PASS="$3"
CSV="${4:-nuaire_raw.csv}"

if [ -z "$HOST" ] || [ -z "$USER" ] || [ -z "$PASS" ]; then
  echo "usage: $0 <broker_host> <mqtt_user> <mqtt_pass> [csv_path]" >&2
  exit 2
fi

# column labels match RAWMAP order in firmware/ha/ha_read.py
HDR="unixtime,11_1,11_2,21_1,21_2,21_3,31_3,33_3,3B_1,3B_2,3B_3,51_4,75_5,85_1,85_3,85_6,A3_7"
[ -f "$CSV" ] || echo "$HDR" > "$CSV"

echo "logging nuaire/raw from $HOST -> $CSV (Ctrl-C to stop)"
# %U = unix time of receipt, %p = payload (the 16-value CSV)
mosquitto_sub -h "$HOST" -u "$USER" -P "$PASS" -t nuaire/raw -F '%U,%p' \
  | while IFS= read -r line; do
      echo "$line" >> "$CSV"
    done
