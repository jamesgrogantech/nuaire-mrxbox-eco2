// Nuaire MRXBOX VSC emulation on the RS485 bus, as an ESPHome component.
//
// Port of the emulation core of karwantes/Nuaire-MVHR
// esp/vsc-serial-bridge/vsc-serial-bridge.ino (commit dc6fb54): emuTick,
// busEdgeIsr, emuBuild, busParse, emuTimers and emuHours are carried over with
// the same timing constants. The web UI, telnet, MQTT and VSC-console code are
// replaced by ESPHome entities.
//
// How it works (from upstream): the unit polls each VSC slot (88, 8A, AE, C5)
// with its ID byte; if nobody answers it sends its own default bytes, starting
// about 25 us after the ID. The XY-485 only drives the bus while TXD is low,
// so our 1 bits are passive and our 0 bits win. The ID is sampled bit by bit
// in a 25 us timer interrupt and the answer is bit-banged on the TX pin in
// step with the unit's own bytes. The bus sends bytes MSB first; every frame
// XORs to 0xD5 in bus bit order.

#include "nuaire_vsc.h"

#include <cmath>
#include <cstring>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#include "driver/gpio.h"
#include "driver/gptimer.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "soc/gpio_reg.h"
#include "soc/soc.h"

namespace esphome {
namespace nuaire_vsc {

static const char *const TAG = "nuaire_vsc";

static constexpr uint32_t BUS_BAUD = 1200;
static constexpr uart_port_t BUS_UART = UART_NUM_2;
static constexpr uint32_t BUS_GAP_MS = 20;      // 8.3 ms per byte; longer silence ends a frame
static constexpr uint32_t COMMS_MS = 5000;      // no good 84 frame for this long = no comms
static constexpr uint32_t SAVE_MS = 900000;     // run/filter minutes to flash every 15 min
static constexpr int BUS_FRAME = 64;

static const uint8_t EMU_ID[4] = {0x88, 0x8A, 0xAE, 0xC5};
static const uint8_t AIR_C5[6] = {2, 3, 0, 4, 5, 1};  // airflow key -> emu air[] (C5 order)
static const uint8_t FAULT_BYTE[6] = {8, 8, 8, 8, 9, 9};
static const uint8_t FAULT_BIT[6] = {0x08, 0x20, 0x40, 0x80, 0x20, 0x04};
static const uint8_t TM_MIN[TM_N] = {1, 4, 1, 1}, TM_MAX[TM_N] = {59, 8, 21, 12};  // or 0
static const uint16_t TM_UNIT[TM_N] = {1, 60, 1440, 60};                         // minutes per step

// ---------------------------------------------------------------------------
// State shared with the ISRs. One instance only, so plain statics as upstream.
// ---------------------------------------------------------------------------
static int s_rx_pin = 25, s_tx_pin = 26;
static uint32_t s_rx_bit = 1u << 25, s_tx_bit = 1u << 26;

static uint8_t s_frame[4][8], s_len[4];  // data bytes per slot, checksum last
static portMUX_TYPE s_emu_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile bool s_on = false;
// First byte +30 us after the ID, then +100 us, checksum +78 us (measured
// upstream with the VSC off) when the unit has no start bit of its own.
static volatile int32_t s_off_us = 30, s_gap_us = 100, s_last_gap_us = 78;
static volatile uint32_t s_sent[4], s_late, s_synced, s_own, s_edges;
// ID decode diagnostics: IDs started, no stop bit, other IDs (not our slots)
static volatile uint32_t s_id_start, s_id_nostop, s_id_other;
static volatile uint8_t s_last_other;
static volatile uint8_t s_state;  // 0 idle, 1 reading an ID, 2 sending
static volatile bool s_wait;      // sending, between bytes: waiting for the unit's start bit
static volatile uint32_t s_start, s_prev_edge, s_byte_t, s_due;

#define NOW_US() ((uint32_t) esp_timer_get_time())
#define RX_LOW() (!(REG_READ(GPIO_IN_REG) & s_rx_bit))

static uint8_t rev8(uint8_t b) {
  b = (b & 0xF0) >> 4 | (b & 0x0F) << 4;
  b = (b & 0xCC) >> 2 | (b & 0x33) << 2;
  return (b & 0xAA) >> 1 | (b & 0x55) << 1;
}

// Every 25 us while s_state is set: sample the ID at its bit centres, then send
// the slot's bytes, MSB first, start bit low, stop bit high. Each byte starts
// on the unit's start bit (edge_isr), or at s_due if it has none.
static bool IRAM_ATTR emu_tick(gptimer_handle_t, const gptimer_alarm_event_data_t *, void *) {
  static uint8_t bit, id, slot, len, out[8], j;
  if (!s_state) {
    bit = id = j = 0;
    return false;
  }
  uint32_t dt = NOW_US() - s_start;
  if (s_state == 1) {
    if (dt < (3 + 2 * bit) * 1000000UL / (2 * BUS_BAUD))
      return false;
    int lv = RX_LOW() ? 0 : 1;
    if (bit < 8) {
      id = id << 1 | lv;
      bit++;
      return false;
    }
    slot = id == 0x88 ? 0 : id == 0x8A ? 1 : id == 0xAE ? 2 : id == 0xC5 ? 3 : 255;
    if (!lv || slot == 255) {  // no stop bit, or not our slot
      if (!lv)
        s_id_nostop++;
      else {
        s_id_other++;
        s_last_other = id;
      }
      s_state = 0;
      return false;
    }
    portENTER_CRITICAL_ISR(&s_emu_mux);
    len = s_len[slot];
    for (int i = 0; i < len; i++)
      out[i] = s_frame[slot][i];
    portEXIT_CRITICAL_ISR(&s_emu_mux);
    bit = 1;
    j = 0;
    s_due = s_start + 10 * 1000000UL / BUS_BAUD + s_off_us;
    s_wait = true;
    s_state = 2;
    return false;
  }
  if (s_wait) {
    if ((int32_t) (NOW_US() - s_due) < 60)
      return false;
    s_byte_t = s_due;  // the unit has not started a byte: send on its timing
    s_wait = false;
    s_own++;
    REG_WRITE(GPIO_OUT_W1TC_REG, s_tx_bit);
    bit = 1;
  }
  uint32_t t = bit * 1000000UL / BUS_BAUD;
  dt = NOW_US() - s_byte_t;
  if (dt < t)
    return false;
  if (dt - t > 100)
    s_late++;
  int lv = bit == 9 ? 1 : (out[j] >> (8 - bit)) & 1;
  REG_WRITE(lv ? GPIO_OUT_W1TS_REG : GPIO_OUT_W1TC_REG, s_tx_bit);
  if (++bit < 10)
    return false;
  bit = 1;
  if (++j < len) {
    s_due = s_byte_t + 10 * 1000000UL / BUS_BAUD + (j == len - 1 ? s_last_gap_us : s_gap_us);
    s_wait = true;
    return false;
  }
  s_sent[slot]++;
  s_state = 0;
  return false;
}

static void IRAM_ATTR edge_isr(void *) {
  uint32_t now = NOW_US();
  bool low = RX_LOW();
  // an ID's start bit: the first falling edge after a silence longer than a byte
  if (s_on && !s_state && now - s_prev_edge > 12000 && low) {
    s_start = now;
    s_state = 1;
    s_id_start++;
  } else if (s_state == 2 && s_wait && low) {
    // the unit's start bit: start ours with it
    REG_WRITE(GPIO_OUT_W1TC_REG, s_tx_bit);
    s_byte_t = now;
    s_wait = false;
    s_synced++;
  }
  s_prev_edge = now;
  s_edges++;
}

// ---------------------------------------------------------------------------
// Bus receive: the unit's own frames (84 faults/bypass, A1 temps, DC humidity).
// ---------------------------------------------------------------------------
struct BusState {
  uint32_t t84, tA1, tDC;  // millis() of the last good frame, 0 = none yet
  uint8_t p8, p9;
  int ext, in, hum;
};
static BusState s_bus{};
static portMUX_TYPE s_bus_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t s_frames_good;

static int bus_temp(uint8_t b) {  // >>1, signed 7 bit, -63 = sensor fault
  int v = rev8(b) >> 1;
  return v & 0x40 ? v - 128 : v;
}

static void bus_parse(const uint8_t *raw, int n) {
  uint8_t d[BUS_FRAME], x = 0;
  for (int i = 0; i < n; i++) {
    d[i] = rev8(raw[i]);  // a UART sees LSB first; the bus is MSB first
    x ^= d[i];
  }
  if (x != 0xD5)
    return;  // includes our own slots, where only the poll ID is received
  s_frames_good++;
  uint32_t now = millis();
  if (now == 0)
    now = 1;
  portENTER_CRITICAL(&s_bus_mux);
  if (d[0] == 0x84 && n == 4) {
    s_bus.p8 = rev8(d[1]);
    s_bus.p9 = rev8(d[2]);
    s_bus.t84 = now;
  } else if (d[0] == 0xA1 && n == 7) {
    s_bus.ext = bus_temp(d[1]);
    s_bus.in = bus_temp(d[3]);
    s_bus.tA1 = now;
  } else if (d[0] == 0xDC && n == 4) {
    s_bus.hum = d[1] ^ 0x7F;  // same as rev8 >> 1, active low
    s_bus.tDC = now;
  }
  portEXIT_CRITICAL(&s_bus_mux);
}

static void bus_task(void *) {
  uint8_t f[BUS_FRAME];
  int n = 0;
  uint32_t last = 0;
  for (;;) {
    uint8_t c;
    int r = uart_read_bytes(BUS_UART, &c, 1, pdMS_TO_TICKS(2));
    uint32_t now = millis();
    if (r <= 0) {
      if (n && now - last > BUS_GAP_MS) {
        bus_parse(f, n);
        n = 0;
      }
      continue;
    }
    if (n == BUS_FRAME) {
      bus_parse(f, n);
      n = 0;
    }
    f[n++] = c;
    last = now;
  }
}

static BusState bus_snapshot() {
  portENTER_CRITICAL(&s_bus_mux);
  BusState b = s_bus;
  portEXIT_CRITICAL(&s_bus_mux);
  return b;
}

static bool fresh(uint32_t t) { return t && millis() - t < COMMS_MS; }

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
void NuaireVsc::set_pins(int rx, int tx) {
  s_rx_pin = rx;
  s_tx_pin = tx;
  s_rx_bit = 1u << rx;
  s_tx_bit = 1u << tx;
}

void NuaireVsc::setup() {
  // First thing: keep the auto-direction module in receive.
  gpio_num_t tx = (gpio_num_t) s_tx_pin, rx = (gpio_num_t) s_rx_pin;
  gpio_reset_pin(tx);
  gpio_set_level(tx, 1);
  gpio_set_direction(tx, GPIO_MODE_OUTPUT);
  gpio_set_level(tx, 1);

  this->emu_ = EmuSettings{(uint8_t) this->emulation_default_, 1, 0x7F, 24, 66, 0, {100, 100, 18, 32, 18, 32}};
  this->cnt_ = EmuCounters{0, 0, {0, 0, 0, 0}, {0, 0, 0, 0}, 1};
  this->pref_settings_ = global_preferences->make_preference<EmuSettings>(fnv1_hash("nuaire_vsc_settings_v1"));
  this->pref_counters_ = global_preferences->make_preference<EmuCounters>(fnv1_hash("nuaire_vsc_counters_v1"));
  EmuSettings saved;
  if (this->pref_settings_.load(&saved) && saved.speed >= 1 && saved.speed <= 3)
    this->emu_ = saved;
  EmuCounters saved_cnt;
  if (this->pref_counters_.load(&saved_cnt))
    this->cnt_ = saved_cnt;
  if (this->cnt_.prev_speed < 1 || this->cnt_.prev_speed > 2)
    this->cnt_.prev_speed = 1;
  this->tm_speed_ = this->emu_.speed;  // a timer left running before a restart carries on
  this->tm_mode_ = this->emu_.mode;
  this->timer_min_t_ = this->hours_min_t_ = this->hours_save_t_ = millis();
  this->build_frames_();
  s_on = this->emu_.on;

  // Bus receive: UART2, RX only, 1200 8N1.
  uart_config_t uc{};
  uc.baud_rate = BUS_BAUD;
  uc.data_bits = UART_DATA_8_BITS;
  uc.parity = UART_PARITY_DISABLE;
  uc.stop_bits = UART_STOP_BITS_1;
  uc.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
  uc.source_clk = UART_SCLK_DEFAULT;
  esp_err_t err = uart_driver_install(BUS_UART, 1024, 0, 0, nullptr, 0);
  if (err == ESP_OK)
    err = uart_param_config(BUS_UART, &uc);
  if (err == ESP_OK)
    err = uart_set_pin(BUS_UART, UART_PIN_NO_CHANGE, s_rx_pin, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
  // Hand every byte to the driver as it arrives. The defaults (FIFO threshold
  // 120, timeout ~10 byte times = 83 ms at 1200 baud) batch several frames
  // together, which hides the 20 ms gaps that split frames.
  if (err == ESP_OK)
    err = uart_set_rx_full_threshold(BUS_UART, 1);
  if (err == ESP_OK)
    err = uart_set_rx_timeout(BUS_UART, 1);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "UART setup failed: %s", esp_err_to_name(err));
    this->mark_failed();
    return;
  }
  gpio_pullup_en(rx);  // idle high while nothing is connected

  // Edge interrupt on the RX pin (the UART keeps reading the same pin).
  gpio_set_intr_type(rx, GPIO_INTR_ANYEDGE);
  err = gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
  if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
    ESP_LOGE(TAG, "GPIO ISR service failed: %s", esp_err_to_name(err));
    this->mark_failed();
    return;
  }
  gpio_isr_handler_add(rx, edge_isr, nullptr);
  gpio_intr_enable(rx);

  // 25 us periodic timer for the bit-banged replies.
  gptimer_handle_t timer = nullptr;
  gptimer_config_t tc{};
  tc.clk_src = GPTIMER_CLK_SRC_DEFAULT;
  tc.direction = GPTIMER_COUNT_UP;
  tc.resolution_hz = 1000000;
  gptimer_event_callbacks_t cbs{};
  cbs.on_alarm = emu_tick;
  gptimer_alarm_config_t ac{};
  ac.alarm_count = 25;
  ac.reload_count = 0;
  ac.flags.auto_reload_on_alarm = true;
  err = gptimer_new_timer(&tc, &timer);
  if (err == ESP_OK)
    err = gptimer_register_event_callbacks(timer, &cbs, nullptr);
  if (err == ESP_OK)
    err = gptimer_set_alarm_action(timer, &ac);
  if (err == ESP_OK)
    err = gptimer_enable(timer);
  if (err == ESP_OK)
    err = gptimer_start(timer);
  if (err != ESP_OK) {
    ESP_LOGE(TAG, "Timer setup failed: %s", esp_err_to_name(err));
    this->mark_failed();
    return;
  }

  xTaskCreatePinnedToCore(bus_task, "nuaire_bus", 4096, nullptr, 2, nullptr, 0);
}

void NuaireVsc::dump_config() {
  ESP_LOGCONFIG(TAG, "Nuaire VSC emulation:");
  ESP_LOGCONFIG(TAG, "  RX GPIO%d, TX GPIO%d, %u baud", s_rx_pin, s_tx_pin, (unsigned) BUS_BAUD);
  ESP_LOGCONFIG(TAG, "  Emulation: %s, speed %u, mode 0x%02X", this->emu_.on ? "ON" : "OFF", this->emu_.speed,
                this->emu_.mode);
}

void NuaireVsc::loop() {
  this->count_hours_();
  this->run_timers_();
}

// Bus bytes from the emulated settings. A bus byte is the VSC's I2C byte
// bit-reversed; each frame XORs to D5.
void NuaireVsc::build_frames_() {
  const EmuSettings &e = this->emu_;
  uint8_t f[4][8], n[4];
  f[0][0] = e.speed == 1 ? 0x6F : 0x6B;
  n[0] = 1;
  f[1][0] = 0x7F;
  f[1][1] = e.speed == 1 ? 0x7F : e.speed == 2 ? 0x1F : 0x17;
  f[1][2] = 0x7F;
  n[1] = 3;
  f[2][0] = e.mode;
  f[2][1] = rev8(e.bypass_sp << 2);
  f[2][2] = rev8(e.hum_sp << 1);
  f[2][3] = rev8(e.frost << 4);
  n[2] = 4;
  for (int i = 0; i < 6; i++)
    f[3][i] = rev8(e.air[i] << 1);
  n[3] = 6;
  for (int k = 0; k < 4; k++) {
    uint8_t x = 0xD5 ^ EMU_ID[k];
    for (int i = 0; i < n[k]; i++)
      x ^= f[k][i];
    f[k][n[k]++] = x;
  }
  portENTER_CRITICAL(&s_emu_mux);
  memcpy(s_frame, f, sizeof f);
  memcpy(s_len, n, sizeof n);
  portEXIT_CRITICAL(&s_emu_mux);
}

void NuaireVsc::save_settings_() {
  this->pref_settings_.save(&this->emu_);
  this->build_frames_();
  s_on = this->emu_.on;
}

void NuaireVsc::save_counters_() { this->pref_counters_.save(&this->cnt_); }

// Count a minute of running while the unit answers; save now and then.
void NuaireVsc::count_hours_() {
  uint32_t now = millis();
  if (now - this->hours_min_t_ < 60000)
    return;
  this->hours_min_t_ += 60000;
  if (!this->comms())
    return;
  this->cnt_.run_min++;
  this->cnt_.filt_min++;
  if (now - this->hours_save_t_ >= SAVE_MS) {
    this->hours_save_t_ = now;
    this->save_counters_();
  }
}

void NuaireVsc::timer_run_(int i, bool run) {
  this->cnt_.tm_left[i] = run && this->cnt_.tm_len[i] ? (uint32_t) this->cnt_.tm_len[i] * TM_UNIT[i] : 0;
}

// The VSC's own timers. The VSC counts these down and only the resulting speed
// and mode bits reach the bus, so the emulation runs them too: speed 3, night,
// holiday and the bypass On/Off override fall back when their time is up. A
// length of 0 means no limit. Starting the bypass override cancels night,
// holiday and rising boost, as the VSC does.
void NuaireVsc::run_timers_() {
  EmuSettings &e = this->emu_;
  if (!e.on) {
    this->timer_min_t_ = millis();
    this->tm_speed_ = e.speed;
    this->tm_mode_ = e.mode;
    return;
  }
  bool changed = false;
  if ((this->tm_mode_ & 0x01) && !(e.mode & 0x01) && (~e.mode & 0x0E)) {
    e.mode |= 0x0E;  // bypass override started: night, holiday and rising boost off
    changed = true;
  }
  if (e.speed != this->tm_speed_) {
    if (e.speed == 3)
      this->cnt_.prev_speed = this->tm_speed_;
    this->timer_run_(TM_BOOST, e.speed == 3);
  }
  uint8_t ch = e.mode ^ this->tm_mode_;
  if (ch & 0x08)
    this->timer_run_(TM_NIGHT, !(e.mode & 0x08));
  if (ch & 0x04)
    this->timer_run_(TM_HOLIDAY, !(e.mode & 0x04));
  if (ch & 0x11)
    this->timer_run_(TM_BYPASS, (e.mode & 0x11) != 0x11);
  bool started = e.speed != this->tm_speed_ || (ch & 0x1D);
  if (millis() - this->timer_min_t_ >= 60000) {
    this->timer_min_t_ += 60000;
    for (int i = 0; i < TM_N; i++) {
      if (!this->cnt_.tm_left[i])
        continue;
      if (--this->cnt_.tm_left[i])
        continue;
      if (i == TM_BOOST)
        e.speed = this->cnt_.prev_speed;
      else if (i == TM_NIGHT)
        e.mode |= 0x08;
      else if (i == TM_HOLIDAY)
        e.mode |= 0x04;
      else
        e.mode |= 0x11;
      changed = true;
    }
  }
  this->tm_speed_ = e.speed;
  this->tm_mode_ = e.mode;
  if (changed)
    this->save_settings_();
  if (changed || started)
    this->save_counters_();
}

// ---- controls ----
void NuaireVsc::set_emulation(bool on) {
  if ((bool) this->emu_.on == on)
    return;
  this->emu_.on = on;
  this->save_settings_();
  ESP_LOGI(TAG, "Emulation %s", on ? "ON" : "OFF");
}

void NuaireVsc::set_speed(int speed) {
  if (speed < 1 || speed > 3)
    return;
  this->emu_.speed = speed;
  this->save_settings_();
}

void NuaireVsc::set_bypass(const std::string &option) {
  uint8_t clear = option == "On" ? 0x01 : option == "Off" ? 0x10 : option == "Auto" ? 0 : 0xFF;
  if (clear == 0xFF)
    return;
  this->emu_.mode = (this->emu_.mode | 0x11) & ~clear;
  this->save_settings_();
}

void NuaireVsc::set_bypass_sp(int v) {
  if (v < 15 || v > 30)
    return;
  this->emu_.bypass_sp = v;
  this->save_settings_();
}

void NuaireVsc::set_humidity_sp(int v) {
  if (v < 50 || v > 85)
    return;
  this->emu_.hum_sp = v;
  this->save_settings_();
}

void NuaireVsc::set_frost_sp(int v) {
  if (v < -5 || v > 0)
    return;
  this->emu_.frost = -v;
  this->save_settings_();
}

void NuaireVsc::set_mode_flag_(uint8_t bit, bool on) {
  this->emu_.mode = on ? this->emu_.mode & ~bit : this->emu_.mode | bit;
  this->save_settings_();
}

void NuaireVsc::set_airflow(int key, int v) {
  if (key < 0 || key > 5 || v < 1 || v > 100)
    return;
  this->emu_.air[AIR_C5[key]] = v;
  this->save_settings_();
}

void NuaireVsc::set_timer_len(int timer, int v) {
  if (timer < 0 || timer >= TM_N)
    return;
  if (v != 0 && (v < TM_MIN[timer] || v > TM_MAX[timer]))
    return;
  this->cnt_.tm_len[timer] = v;  // a running timer keeps its time; the length applies from the next start
  this->save_counters_();
}

void NuaireVsc::reset_filter() {
  this->cnt_.filt_min = 0;
  this->save_counters_();
}

// ---- state ----
std::string NuaireVsc::bypass() const {
  return !(this->emu_.mode & 0x01) ? "On" : !(this->emu_.mode & 0x10) ? "Off" : "Auto";
}

int NuaireVsc::airflow(int key) const { return key >= 0 && key < 6 ? this->emu_.air[AIR_C5[key]] : 0; }

std::string NuaireVsc::timers_text() const {
  static const char *const name[TM_N] = {"Speed 3", "Night", "Holiday", "Bypass"};
  std::string txt;
  for (int i = 0; i < TM_N; i++) {
    uint32_t m = this->cnt_.tm_left[i];
    if (!m)
      continue;
    if (!txt.empty())
      txt += ", ";
    txt += name[i];
    if (m >= 1440)
      txt += " " + to_string(m / 1440) + " d";
    if (m % 1440 >= 60)
      txt += " " + to_string(m % 1440 / 60) + " h";
    if (m % 60 || m < 60)
      txt += " " + to_string(m % 60) + " min";
  }
  return txt.empty() ? "None running" : txt;
}

bool NuaireVsc::comms() const { return this->emu_.on && fresh(bus_snapshot().t84); }

float NuaireVsc::temp_extract() const {
  BusState b = bus_snapshot();
  return this->comms() && fresh(b.tA1) && b.ext != -63 ? (float) b.ext : NAN;
}

float NuaireVsc::temp_intake() const {
  BusState b = bus_snapshot();
  return this->comms() && fresh(b.tA1) && b.in != -63 ? (float) b.in : NAN;
}

float NuaireVsc::humidity() const {
  BusState b = bus_snapshot();
  return this->comms() && fresh(b.tDC) && b.hum > 0 && b.hum < 127 ? (float) b.hum : NAN;
}

float NuaireVsc::fan_running() const { return this->comms() ? (float) this->emu_.speed : NAN; }

optional<bool> NuaireVsc::bypass_active() const {
  if (!this->comms())
    return {};
  return (bus_snapshot().p9 & 0x08) != 0;
}

optional<bool> NuaireVsc::fault(int i) const {
  if (i < 0 || i > 5 || !this->comms())
    return {};
  BusState b = bus_snapshot();
  uint8_t v = FAULT_BYTE[i] == 8 ? b.p8 : b.p9;
  return !(v & FAULT_BIT[i]);  // active low
}

// ---- diagnostics ----
uint32_t NuaireVsc::replies_sent() const { return s_sent[0] + s_sent[1] + s_sent[2] + s_sent[3]; }
uint32_t NuaireVsc::replies_late() const { return s_late; }
uint32_t NuaireVsc::replies_synced() const { return s_synced; }
uint32_t NuaireVsc::frames_good() const { return s_frames_good; }
uint32_t NuaireVsc::bus_edges() const { return s_edges; }

std::string NuaireVsc::id_stats() const {
  char buf[96];
  snprintf(buf, sizeof buf, "ids %u nostop %u other %u (last %02X) sent %u/%u/%u/%u own %u", (unsigned) s_id_start,
           (unsigned) s_id_nostop, (unsigned) s_id_other, s_last_other, (unsigned) s_sent[0], (unsigned) s_sent[1],
           (unsigned) s_sent[2], (unsigned) s_sent[3], (unsigned) s_own);
  return buf;
}

std::string NuaireVsc::flags_hex() const {
  BusState b = bus_snapshot();
  if (!b.t84)
    return "none";
  char buf[16];
  snprintf(buf, sizeof buf, "p8 %02X p9 %02X", b.p8, b.p9);
  return buf;
}

}  // namespace nuaire_vsc
}  // namespace esphome
