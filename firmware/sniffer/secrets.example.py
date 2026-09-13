# Copy to secrets.py (gitignored) and fill in. Never commit secrets.py.
WIFI_SSID = "your-ssid"
WIFI_PASS = "your-password"

# For the Home Assistant read firmware (firmware/ha/ha_read.py):
MQTT_HOST = "192.168.0.x"     # HA host / Mosquitto broker IP
MQTT_PORT = 1883
MQTT_USER = "mqtt-user"       # or None if broker allows anonymous
MQTT_PASS = "mqtt-pass"
