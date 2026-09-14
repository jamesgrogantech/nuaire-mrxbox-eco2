#!/usr/bin/env python3
"""Publish retained MQTT auto-discovery for the 16 nuaire/raw byte columns.

Creates one HA 'diagnostic' sensor per column, each parsing its field out of the
single nuaire/raw CSV topic with a value_template. HA then records their history
automatically (recorder), so the remaining unknown frame bytes can be decoded by
correlation without editing configuration.yaml or reflashing the Pico.

Discovery is published RETAINED, so it survives HA restarts. Re-run any time
(e.g. after a broker wipe). To remove a sensor, publish an empty retained payload
to its config topic (see --clear).

Column order matches RAWMAP in firmware/ha/ha_read.py.

  python3 tools/publish_raw_discovery.py 192.168.1.10 pico <password>
  python3 tools/publish_raw_discovery.py 192.168.1.10 pico <password> --clear
"""
import json
import subprocess
import sys

# (header, byte-index) -> column label, in nuaire/raw order
LABELS = ["11_1", "11_2", "21_1", "21_2", "21_3", "31_3", "33_3", "3B_1",
          "3B_2", "3B_3", "51_4", "75_5", "85_1", "85_3", "85_6", "A3_7"]
# columns already published as real entities by the firmware
KNOWN = {"21_2": "boost", "3B_1": "humidity"}

DEV = {"identifiers": ["nuaire_mrxbox"], "name": "Nuaire MRXBOX ECO2"}


def pub(host, user, pw, topic, payload, retain=True):
    cmd = ["mosquitto_pub", "-h", host, "-u", user, "-P", pw,
           "-t", topic, "-m", payload]
    if retain:
        cmd.append("-r")
    subprocess.run(cmd, check=True)


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    host, user, pw = sys.argv[1:4]
    clear = "--clear" in sys.argv[4:]

    for i, lab in enumerate(LABELS):
        topic = "homeassistant/sensor/nuaire_raw_%s/config" % lab
        if clear:
            pub(host, user, pw, topic, "", retain=True)
            print("cleared", lab)
            continue
        note = (" (%s)" % KNOWN[lab]) if lab in KNOWN else ""
        payload = {
            "name": "MRXBOX raw %s%s" % (lab, note),
            "state_topic": "nuaire/raw",
            # guard against a short payload; -1 already means "message absent"
            "value_template":
                "{%% if value.split(',')|length > %d %%}"
                "{{ value.split(',')[%d] | int }}{%% else %%}"
                "{{ None }}{%% endif %%}" % (i, i),
            "unique_id": "nuaire_raw_%s" % lab,
            "object_id": "nuaire_raw_%s" % lab,
            "entity_category": "diagnostic",
            "state_class": "measurement",
            "expire_after": 120,
            "device": DEV,
        }
        pub(host, user, pw, topic, json.dumps(payload), retain=True)
        print("published", topic)

    print("done." if not clear else "all cleared.")


if __name__ == "__main__":
    main()
