# Copy this file to secrets.py (which is gitignored) and fill in your own
# values. NEVER commit secrets.py.
#
#   cp firmware/sniffer/secrets.example.py firmware/sniffer/secrets.py
#
# secrets.py is imported by the Pico firmware (firmware/ha/ha_read.py and the
# sniffer scripts). Keep it on the board only; it is not needed on the desktop.

WIFI_SSID = "your-ssid"
WIFI_PASS = "your-password"

# Home Assistant / MQTT broker (used by firmware/ha/ha_read.py) -------------
MQTT_HOST = "192.168.1.10"    # your HA host / Mosquitto broker IP
MQTT_PORT = 1883
MQTT_USER = "mqtt-user"       # set to None if your broker allows anonymous
MQTT_PASS = "mqtt-pass"

# Optional static IP for the Pico. Leave STATIC_IP = None to use DHCP (simplest
# — then reserve the lease in your router if you want a stable address). To pin
# an address, set a 4-tuple: (ip, netmask, gateway, dns).
STATIC_IP = None
# Example:
# STATIC_IP = ("192.168.1.50", "255.255.255.0", "192.168.1.1", "192.168.1.1")
