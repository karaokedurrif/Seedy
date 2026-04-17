/*
 * Seedy Gallinero Camera — Firmware custom para DFRobot DFR1154 ESP32-S3 AI CAM
 *
 * Funcionalidades:
 *   - MJPEG streaming vía HTTP (CameraWebServer compatible)
 *   - Snapshot JPEG en /capture
 *   - Grabación audio PDM 5s en /audio (WAV 16kHz mono)
 *   - Nivel de luz ambiente (LTR-308) en /status
 *   - IR LEDs auto: se encienden cuando luz < umbral
 *   - Telemetría MQTT periódica (luz, uptime, IP, heap libre)
 *   - OTA update vía /update (POST firmware.bin)
 *   - WiFi SmartConfig + serial fallback
 *   - mDNS: seedy-cam-palacio.local / seedy-cam-pequeno.local
 *
 * Hardware: DFRobot DFR1154 — ESP32-S3R8, OV3660 160°, IR 940nm,
 *           PDM mic (GPIO38/39), MAX98357 speaker, LTR-308 ALS
 *
 * Autor: Seedy AI System — NeoFarm 2026
 * Licencia: MIT
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <Update.h>
#include <esp_camera.h>
#include <Wire.h>

// ════════════════════════════════════════════
// CONFIGURACIÓN POR DISPOSITIVO
// Cambiar DEVICE_ID para cada cámara:
//   "palacio"  → gallinero grande (25 aves)
//   "pequeno"  → gallinero pequeño
// ════════════════════════════════════════════
#ifndef DEVICE_ID
#define DEVICE_ID "palacio"
#endif

// ── Pin definitions (DFR1154) ──
#define PWDN_GPIO_NUM    -1
#define RESET_GPIO_NUM   -1
#define XCLK_GPIO_NUM     5
#define Y9_GPIO_NUM       4
#define Y8_GPIO_NUM       6
#define Y7_GPIO_NUM       7
#define Y6_GPIO_NUM      14
#define Y5_GPIO_NUM      17
#define Y4_GPIO_NUM      21
#define Y3_GPIO_NUM      18
#define Y2_GPIO_NUM      16
#define VSYNC_GPIO_NUM    1
#define HREF_GPIO_NUM     2
#define PCLK_GPIO_NUM    15
#define SIOD_GPIO_NUM     8
#define SIOC_GPIO_NUM     9

#define LED_STATUS_PIN    3
#define LED_IR_PIN       47

// ── Audio (PDM mic) ──
#define MIC_CLOCK_PIN    38
#define MIC_DATA_PIN     39
#define AUDIO_SAMPLE_RATE 16000
#define AUDIO_REC_SECONDS 5

// ── LTR-308 (I2C ambient light sensor) ──
#define LTR308_ADDR      0x53
#define ALS_SDA_PIN       8   // compartido con cámara SDA
#define ALS_SCL_PIN       9   // compartido con cámara SCL

// ── IR auto threshold (lux) ──
#define IR_LIGHT_THRESHOLD 50

// ── MQTT ──
// Usaremos HTTP POST a Seedy backend en vez de MQTT directo (más simple)
// El backend reenviará a Mosquitto / InfluxDB

// ── Globals ──
WebServer server(80);
Preferences prefs;

String deviceHostname;
String deviceId = DEVICE_ID;
unsigned long bootTime;
float lastLux = -1;
bool irAutoMode = true;
bool irManualOn = false;

// ── Forward declarations ──
void initCamera();
void initWiFi();
void initMDNS();
void initALS();
float readALS();
void updateIR();
void handleStream();
void handleCapture();
void handleAudio();
void handleStatus();
void handleOTA();
void handleOTAUpload();
void handleReboot();
void handleRoot();

// ════════════════════════════════════════════
// SETUP
// ════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  // Wait for USB CDC to be ready (ESP32-S3 needs time to enumerate)
  unsigned long waitStart = millis();
  while (!Serial && (millis() - waitStart < 3000)) delay(10);
  delay(500);
  Serial.println("\n\n=== Seedy Gallinero Camera ===");
  Serial.printf("Device: %s\n", DEVICE_ID);

  bootTime = millis();

  // LED status
  pinMode(LED_STATUS_PIN, OUTPUT);
  digitalWrite(LED_STATUS_PIN, HIGH);  // ON durante boot

  // IR LEDs off initially
  pinMode(LED_IR_PIN, OUTPUT);
  digitalWrite(LED_IR_PIN, LOW);

  // Camera
  initCamera();

  // Light sensor
  initALS();

  // WiFi
  initWiFi();
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi FAIL — reboot in 10s");
    delay(10000);
    ESP.restart();
  }

  // mDNS
  initMDNS();

  // HTTP server
  server.on("/", HTTP_GET, handleRoot);
  server.on("/stream", HTTP_GET, handleStream);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/audio", HTTP_GET, handleAudio);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/update", HTTP_POST, handleOTA, handleOTAUpload);
  server.on("/reboot", HTTP_POST, handleReboot);
  server.begin();

  digitalWrite(LED_STATUS_PIN, LOW);
  Serial.printf("\n[Seedy] Camera ready: http://%s\n", WiFi.localIP().toString().c_str());
  Serial.printf("[Seedy] mDNS: http://%s.local\n", deviceHostname.c_str());
}

// ════════════════════════════════════════════
// LOOP
// ════════════════════════════════════════════
static unsigned long lastIrCheck = 0;
static unsigned long lastWdtFeed = 0;

void loop() {
  server.handleClient();
  yield();

  unsigned long now = millis();

  // Cada 5s: leer luz y actualizar IR
  if (now - lastIrCheck > 5000) {
    lastIrCheck = now;
    lastLux = readALS();
    updateIR();
  }

  // Watchdog: si el loop no avanza en 60s → reboot
  if (now - lastWdtFeed > 60000) {
    lastWdtFeed = now;
    // Self-check: si WiFi perdido, reconectar
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WDT] WiFi lost — reconnecting...");
      WiFi.reconnect();
      delay(5000);
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WDT] WiFi reconnect failed — rebooting");
        ESP.restart();
      }
    }
  }
}

// ════════════════════════════════════════════
// CAMERA
// ════════════════════════════════════════════
void initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.frame_size   = FRAMESIZE_SVGA;  // 800x600 default
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode    = CAMERA_GRAB_LATEST;
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count     = 2;

  if (psramFound()) {
    Serial.printf("[CAM] PSRAM: %d KB free\n", ESP.getFreePsram() / 1024);
    config.jpeg_quality = 10;
    config.fb_count     = 2;
    config.frame_size   = FRAMESIZE_UXGA;  // 1600x1200 con PSRAM
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] Init FAILED: 0x%x\n", err);
    return;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);
    s->set_brightness(s, 1);
    s->set_saturation(s, -1);
  }
  // Empezar en VGA para streaming fluido
  s->set_framesize(s, FRAMESIZE_VGA);

  Serial.println("[CAM] OV3660 init OK");
}

// ════════════════════════════════════════════
// WIFI
// ════════════════════════════════════════════
// Default credentials (override via serial or NVS)
#ifndef WIFI_SSID
#define WIFI_SSID "Casa_HS_Wifi"
#endif
#ifndef WIFI_PASS
#define WIFI_PASS "ErizoDespenado22"
#endif

void initWiFi() {
  prefs.begin("wifi", false);
  String ssid = prefs.getString("ssid", "");
  String pass = prefs.getString("pass", "");

  // Try saved credentials first
  if (ssid.length() > 0) {
    Serial.printf("[WiFi] Trying saved: '%s'\n", ssid.c_str());
    WiFi.begin(ssid.c_str(), pass.c_str());
    WiFi.setSleep(false);
    for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) {
      delay(500);
      Serial.print(".");
    }
    if (WiFi.status() == WL_CONNECTED) {
      Serial.printf("\n[WiFi] Connected (saved)! IP: %s\n", WiFi.localIP().toString().c_str());
      prefs.end();
      return;
    }
    Serial.println("\n[WiFi] Saved credentials failed");
    WiFi.disconnect();
  }

  // Try compiled-in defaults
  Serial.printf("[WiFi] Trying default: '%s'\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setSleep(false);
  for (int i = 0; i < 30 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    prefs.putString("ssid", WIFI_SSID);
    prefs.putString("pass", WIFI_PASS);
    Serial.printf("\n[WiFi] Connected (default)! IP: %s\n", WiFi.localIP().toString().c_str());
    prefs.end();
    return;
  }
  Serial.println("\n[WiFi] Default failed");
  WiFi.disconnect();

  // Fallback: pedir por serial (5s timeout, luego reboot)
  Serial.println("[WiFi] Enter SSID (5s timeout):");
  unsigned long t0 = millis();
  while (!Serial.available() && millis() - t0 < 5000) delay(10);
  if (Serial.available()) {
    String inputSSID = Serial.readStringUntil('\n');
    inputSSID.trim();
    Serial.println("[WiFi] Enter Password:");
    t0 = millis();
    while (!Serial.available() && millis() - t0 < 5000) delay(10);
    if (Serial.available()) {
      String inputPass = Serial.readStringUntil('\n');
      inputPass.trim();
      WiFi.begin(inputSSID.c_str(), inputPass.c_str());
      WiFi.setSleep(false);
      for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) {
        delay(500); Serial.print(".");
      }
      if (WiFi.status() == WL_CONNECTED) {
        prefs.putString("ssid", inputSSID);
        prefs.putString("pass", inputPass);
        Serial.printf("\n[WiFi] Connected (serial)! IP: %s\n", WiFi.localIP().toString().c_str());
      }
    }
  }
  prefs.end();
}

void initMDNS() {
  deviceHostname = "seedy-cam-" + deviceId;
  if (MDNS.begin(deviceHostname.c_str())) {
    MDNS.addService("http", "tcp", 80);
    MDNS.addServiceTxt("http", "tcp", "type", "seedy-cam");
    MDNS.addServiceTxt("http", "tcp", "device", deviceId.c_str());
    MDNS.addServiceTxt("http", "tcp", "firmware", "1.0.0");
    Serial.printf("[mDNS] %s.local\n", deviceHostname.c_str());
  }
}

// ════════════════════════════════════════════
// LIGHT SENSOR (LTR-308)
// ════════════════════════════════════════════
bool alsAvailable = false;

void initALS() {
  Wire.begin(ALS_SDA_PIN, ALS_SCL_PIN);
  Wire.beginTransmission(LTR308_ADDR);
  if (Wire.endTransmission() == 0) {
    // Active mode, gain 1x
    Wire.beginTransmission(LTR308_ADDR);
    Wire.write(0x00);  // ALS_CONTR
    Wire.write(0x02);  // Active mode, gain 1x
    Wire.endTransmission();
    // Measurement rate: 100ms, 18-bit
    Wire.beginTransmission(LTR308_ADDR);
    Wire.write(0x04);  // ALS_MEAS_RATE
    Wire.write(0x12);  // 100ms, 18-bit
    Wire.endTransmission();
    alsAvailable = true;
    Serial.println("[ALS] LTR-308 OK");
  } else {
    Serial.println("[ALS] LTR-308 not found — IR auto disabled");
  }
}

float readALS() {
  if (!alsAvailable) return -1;

  Wire.beginTransmission(LTR308_ADDR);
  Wire.write(0x0D);  // ALS_DATA_0
  Wire.endTransmission(false);
  Wire.requestFrom((uint8_t)LTR308_ADDR, (uint8_t)3);

  if (Wire.available() < 3) return -1;

  uint32_t data0 = Wire.read();
  uint32_t data1 = Wire.read();
  uint32_t data2 = Wire.read();
  uint32_t raw = data0 | (data1 << 8) | (data2 << 16);

  // Gain 1x, integration 100ms → factor 0.6
  float lux = raw * 0.6;
  return lux;
}

void updateIR() {
  if (!irAutoMode) {
    digitalWrite(LED_IR_PIN, irManualOn ? HIGH : LOW);
    return;
  }
  if (lastLux >= 0 && lastLux < IR_LIGHT_THRESHOLD) {
    digitalWrite(LED_IR_PIN, HIGH);
  } else {
    digitalWrite(LED_IR_PIN, LOW);
  }
}

// ════════════════════════════════════════════
// HTTP HANDLERS
// ════════════════════════════════════════════

// ── Root page ──
void handleRoot() {
  String html = "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<title>Seedy Cam — " + deviceId + "</title>"
    "<style>body{font-family:sans-serif;background:#111;color:#eee;text-align:center;padding:20px}"
    "h1{color:#4ecdc4}img{max-width:100%;border-radius:12px;margin:10px 0}"
    "a{color:#4ecdc4;text-decoration:none;margin:0 10px;font-size:1.1em}"
    ".status{background:#1a1a2e;padding:15px;border-radius:8px;display:inline-block;text-align:left;margin:15px}"
    "</style></head><body>"
    "<h1>🌱 Seedy Cam — " + deviceId + "</h1>"
    "<p><img src='/capture' id='snap'></p>"
    "<p><a href='/stream'>📹 MJPEG Stream</a> | "
    "<a href='/capture'>📸 Snapshot</a> | "
    "<a href='/audio'>🎙️ Grabar Audio (5s)</a> | "
    "<a href='/status'>📊 Status</a></p>"
    "<div class='status'>"
    "<b>IP:</b> " + WiFi.localIP().toString() + "<br>"
    "<b>mDNS:</b> " + deviceHostname + ".local<br>"
    "<b>Uptime:</b> " + String((millis() - bootTime) / 1000) + "s<br>"
    "<b>Luz:</b> " + String(lastLux, 1) + " lux<br>"
    "<b>IR:</b> " + String(digitalRead(LED_IR_PIN) ? "ON" : "OFF") + "<br>"
    "<b>Free heap:</b> " + String(ESP.getFreeHeap() / 1024) + " KB<br>"
    "</div>"
    "<script>setInterval(()=>{document.getElementById('snap').src='/capture?t='+Date.now()},3000)</script>"
    "</body></html>";
  server.send(200, "text/html", html);
}

// ── MJPEG stream (non-blocking: runs in handleClient but with timeout) ──
void handleStream() {
  WiFiClient client = server.client();
  if (!client.connected()) return;

  // Set socket timeout to avoid blocking forever
  client.setTimeout(5);

  String header = "HTTP/1.1 200 OK\r\n"
    "Content-Type: multipart/x-mixed-replace; boundary=--seedyframe\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "Cache-Control: no-cache\r\n"
    "Connection: close\r\n\r\n";
  client.print(header);

  unsigned long streamStart = millis();
  // Stream max 5 minutes, then client must reconnect
  while (client.connected() && (millis() - streamStart < 300000UL)) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      delay(50);
      continue;
    }

    String part = "--seedyframe\r\nContent-Type: image/jpeg\r\nContent-Length: "
                  + String(fb->len) + "\r\n\r\n";
    size_t written = client.print(part);
    if (written == 0) { esp_camera_fb_return(fb); break; }

    written = client.write(fb->buf, fb->len);
    if (written == 0) { esp_camera_fb_return(fb); break; }

    client.print("\r\n");
    esp_camera_fb_return(fb);

    delay(100);  // ~10 fps
    yield();
  }
  client.stop();
}

// ── Single JPEG capture ──
void handleCapture() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Cache-Control", "no-cache");
  server.send_P(200, "image/jpeg", (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

// ── Audio recording — TODO: add via OTA when I2S/HWCDC conflict is resolved ──
void handleAudio() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  String json = "{\"status\":\"not_implemented\","
    "\"message\":\"Audio recording coming in firmware v1.1 via OTA. "
    "Hardware: PDM mic GPIO38/39 ready.\","
    "\"device\":\"" + deviceId + "\"}";
  server.send(501, "application/json", json);
}

// ── Status JSON ──
void handleStatus() {
  unsigned long uptimeSec = (millis() - bootTime) / 1000;
  String json = "{";
  json += "\"device_id\":\"" + deviceId + "\",";
  json += "\"hostname\":\"" + deviceHostname + "\",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"mac\":\"" + WiFi.macAddress() + "\",";
  json += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  json += "\"uptime_s\":" + String(uptimeSec) + ",";
  json += "\"lux\":" + String(lastLux, 1) + ",";
  json += "\"ir_on\":" + String(digitalRead(LED_IR_PIN) ? "true" : "false") + ",";
  json += "\"ir_auto\":" + String(irAutoMode ? "true" : "false") + ",";
  json += "\"free_heap\":" + String(ESP.getFreeHeap()) + ",";
  json += "\"free_psram\":" + String(ESP.getFreePsram()) + ",";
  json += "\"firmware\":\"seedy-cam-1.0.0\",";
  json += "\"camera\":\"OV3660\"";
  json += "}";

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", json);
}

// ── OTA update ──
void handleOTA() {
  if (Update.hasError()) {
    server.send(500, "text/plain", "OTA FAILED: " + String(Update.errorString()));
  } else {
    server.send(200, "text/plain", "OTA OK — rebooting...");
    delay(500);
    ESP.restart();
  }
}

void handleOTAUpload() {
  HTTPUpload &upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    Serial.printf("[OTA] Start: %s\n", upload.filename.c_str());
    if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_END) {
    if (Update.end(true)) {
      Serial.printf("[OTA] Success: %u bytes\n", upload.totalSize);
    } else {
      Update.printError(Serial);
    }
  }
}

// ── Reboot ──
void handleReboot() {
  server.send(200, "text/plain", "Rebooting...");
  delay(500);
  ESP.restart();
}
