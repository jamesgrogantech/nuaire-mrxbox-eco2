"""ESPHome external component: Nuaire MRXBOX VSC emulation on the RS485 bus.

Ported from the emulation core of karwantes/Nuaire-MVHR
esp/vsc-serial-bridge/vsc-serial-bridge.ino (commit dc6fb54). Entities are
declared in YAML as template entities that call into this component.
"""

import esphome.codegen as cg
from esphome.components.esp32 import include_builtin_idf_component
import esphome.config_validation as cv
from esphome.const import CONF_ID

CODEOWNERS = []
DEPENDENCIES = ["esp32"]

nuaire_vsc_ns = cg.esphome_ns.namespace("nuaire_vsc")
NuaireVsc = nuaire_vsc_ns.class_("NuaireVsc", cg.Component)

CONF_RX_PIN = "rx_pin"
CONF_TX_PIN = "tx_pin"
CONF_EMULATION_DEFAULT = "emulation_default"

# GPIO numbers, not pin schemas: the ISRs use the GPIO_IN/OUT registers
# directly, which only cover GPIO0-31.
CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(NuaireVsc),
        cv.Optional(CONF_RX_PIN, default=25): cv.int_range(min=0, max=31),
        cv.Optional(CONF_TX_PIN, default=26): cv.int_range(min=0, max=31),
        cv.Optional(CONF_EMULATION_DEFAULT, default=False): cv.boolean,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    # excluded from ESPHome's ESP-IDF build by default; the 25 us reply timer needs it
    include_builtin_idf_component("esp_driver_gptimer")
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_pins(config[CONF_RX_PIN], config[CONF_TX_PIN]))
    cg.add(var.set_emulation_default(config[CONF_EMULATION_DEFAULT]))
