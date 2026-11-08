#pragma once

#include <string>

#include "esphome/core/component.h"
#include "esphome/core/helpers.h"
#include "esphome/core/preferences.h"

namespace esphome {
namespace nuaire_vsc {

// The emulated VSC's settings, persisted. mode is AE byte 1, active low:
// 0x01 bypass on, 0x10 bypass off (both set = Auto), 0x08 night, 0x04 holiday,
// 0x02 rising humidity boost. air[] is in C5 order: supply 3, extract 3,
// supply 1, supply 2, extract 1, extract 2.
struct EmuSettings {
  uint8_t on;
  uint8_t speed;      // 1..3
  uint8_t mode;
  uint8_t bypass_sp;  // deg C
  uint8_t hum_sp;     // %
  uint8_t frost;      // AE byte 4 (frost level, 0..5 = 0..-5 C)
  uint8_t air[6];
} __attribute__((packed));

// Run/filter minutes and the VSC timers, persisted.
struct EmuCounters {
  uint32_t run_min;
  uint32_t filt_min;
  uint8_t tm_len[4];    // timer lengths in their unit steps; 0 = no limit
  uint32_t tm_left[4];  // minutes left; 0 = not running
  uint8_t prev_speed;   // speed to return to when the speed 3 timer ends
} __attribute__((packed));

enum TimerIndex { TM_BOOST = 0, TM_NIGHT, TM_HOLIDAY, TM_BYPASS, TM_N };

class NuaireVsc : public Component {
 public:
  void set_pins(int rx, int tx);
  void set_emulation_default(bool on) { this->emulation_default_ = on; }

  void setup() override;
  void loop() override;
  void dump_config() override;
  // Before WiFi and everything else: TXD must be driven high as early as
  // possible so the auto-direction RS485 module stays in receive.
  float get_setup_priority() const override { return setup_priority::BUS; }

  // ---- controls ----
  void set_emulation(bool on);
  void set_speed(int speed);
  void set_bypass(const std::string &option);  // "Auto", "On", "Off"
  void set_bypass_sp(int v);                   // 15..30
  void set_humidity_sp(int v);                 // 50..85
  void set_frost_sp(int v);                    // -5..0
  void set_night(bool on) { this->set_mode_flag_(0x08, on); }
  void set_holiday(bool on) { this->set_mode_flag_(0x04, on); }
  void set_rising_boost(bool on) { this->set_mode_flag_(0x02, on); }
  // key: 0..5 = supply speed 1/2/3, extract speed 1/2/3
  void set_airflow(int key, int v);  // 1..100
  void set_timer_len(int timer, int v);
  void reset_filter();

  // ---- state ----
  bool emulation() const { return this->emu_.on; }
  int speed() const { return this->emu_.speed; }
  std::string speed_str() const { return to_string(this->emu_.speed); }
  std::string bypass() const;
  int bypass_sp() const { return this->emu_.bypass_sp; }
  int humidity_sp() const { return this->emu_.hum_sp; }
  int frost_sp() const { return -(int) this->emu_.frost; }
  bool night() const { return !(this->emu_.mode & 0x08); }
  bool holiday() const { return !(this->emu_.mode & 0x04); }
  bool rising_boost() const { return !(this->emu_.mode & 0x02); }
  int airflow(int key) const;
  int timer_len(int timer) const { return this->cnt_.tm_len[timer]; }
  std::string timers_text() const;
  float run_hours() const { return this->cnt_.run_min / 60; }
  float filter_hours() const { return this->cnt_.filt_min / 60; }
  bool filter_change() const { return this->cnt_.filt_min / 60 > 8759; }

  bool comms() const;                 // emulating and the unit's 84 frame seen in the last 5 s
  float temp_extract() const;         // NAN if unknown
  float temp_intake() const;          // NAN if unknown
  float humidity() const;             // NAN if unknown
  float fan_running() const;          // NAN without comms
  optional<bool> bypass_active() const;
  // 0 supply fan, 1 extract fan, 2 heater, 3 cooler, 4 frost, 5 test routine required
  optional<bool> fault(int i) const;

  // ---- diagnostics ----
  uint32_t replies_sent() const;
  uint32_t replies_late() const;
  uint32_t replies_synced() const;
  uint32_t frames_good() const;
  uint32_t bus_edges() const;
  std::string flags_hex() const;
  std::string id_stats() const;

 protected:
  void set_mode_flag_(uint8_t bit, bool on);
  void save_settings_();
  void save_counters_();
  void build_frames_();
  void count_hours_();
  void run_timers_();
  void timer_run_(int i, bool run);

  bool emulation_default_{false};
  EmuSettings emu_{};
  EmuCounters cnt_{};
  ESPPreferenceObject pref_settings_;
  ESPPreferenceObject pref_counters_;

  uint8_t tm_speed_{1}, tm_mode_{0x7F};  // emu_.speed / mode as the timers last saw them
  uint32_t timer_min_t_{0}, hours_min_t_{0}, hours_save_t_{0};
};

}  // namespace nuaire_vsc
}  // namespace esphome
