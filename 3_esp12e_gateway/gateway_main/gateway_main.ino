/**
 * @file    gateway_main.ino
 * @project Edge AI Palm Oil FFB (TBS) Grading System
 * @target  ESP-12E Wi-Fi Module (ESP8266)
 * @ide     Arduino IDE 2.x with ESP8266 Board Package v3.x
 *
 * @overview
 *   Edge gateway firmware for the ESP-12E module. Receives JSON inference
 *   results from the MAX78000FTHR over UART at 115200 baud, then:
 *     1. Parses the JSON payload securely
 *     2. Publishes results to an MQTT broker over Wi-Fi (primary path)
 *     3. Falls back to LoRa radio if Wi-Fi or MQTT is unavailable (secondary)
 *     4. Sends a periodic 30-second heartbeat/status to the broker
 *
 * @wiring
 *   MAX78000 TX (P0.1) → ESP-12E RX (GPIO3/U0RXD)  [Hardware Serial]
 *   MAX78000 RX (P0.0) → ESP-12E TX (GPIO1/U0TXD)  [Hardware Serial]
 *   LoRa-02 NSS (CS)   → ESP-12E GPIO15             [SPI Chip Select]
 *   LoRa-02 SCK        → ESP-12E GPIO14 (SPI CLK)
 *   LoRa-02 MOSI       → ESP-12E GPIO13 (SPI MOSI)
 *   LoRa-02 MISO       → ESP-12E GPIO12 (SPI MISO)
 *   LoRa-02 RST        → ESP-12E GPIO16
 *   LoRa-02 DIO0       → ESP-12E GPIO4  (LoRa interrupt)
 *   MAX78000 VCC       → 3.3V
 *   LoRa-02 VCC        → 3.3V
 *
 * @board_manager_url
 *   http://arduino.esp8266.com/stable/package_esp8266com_index.json
 *
 * @library_dependencies (install via Arduino Library Manager):
 *   - ArduinoJson     v6.x by Benoit Blanchon
 *   - PubSubClient    v2.8+ by Nick O'Leary
 *   - LoRa            v0.8+ by Sandeep Mistry (arduino-LoRa)
 *
 * @mqtt_topics
 *   Publish (QoS 1): pks/grading/tbs/result
 *                    Payload: {"g":<grade>,"c":<confidence>,"ts":<millis>}
 *   Publish (QoS 0): pks/grading/tbs/status
 *                    Payload: {"status":"online","uptime":<ms>,"ip":"x.x.x.x","rssi":<dBm>}
 *   Subscribe:       pks/grading/tbs/cmd    [for future OTA/config commands]
 */

// ── Arduino & System ──────────────────────────────────────────────────────────
#include <Arduino.h>
#include <ESP8266WiFi.h>        // Wi-Fi driver
#include <ESP8266WiFiMulti.h>   // Multi-AP failover support (optional)

// ── JSON Parsing ──────────────────────────────────────────────────────────────
#include <ArduinoJson.h>        // v6.x: StaticJsonDocument, deserializeJson

// ── MQTT ──────────────────────────────────────────────────────────────────────
#include <PubSubClient.h>       // MQTT client with QoS 0/1 support

// ── LoRa Radio ────────────────────────────────────────────────────────────────
#include <SPI.h>
#include <LoRa.h>               // sandeepmistry/arduino-LoRa library

// ═════════════════════════════════════════════════════════════════════════════
// CONFIGURATION — UPDATE THESE BEFORE FLASHING
// ═════════════════════════════════════════════════════════════════════════════

// ── Wi-Fi Credentials ─────────────────────────────────────────────────────────
const char *WIFI_SSID       = "PKS_Factory_IoT";     // Factory Wi-Fi SSID
const char *WIFI_PASSWORD   = "your_wifi_password";  // Wi-Fi password

// ── MQTT Broker ───────────────────────────────────────────────────────────────
const char *MQTT_BROKER_IP  = "192.168.1.100";       // Local factory server IP
const int   MQTT_BROKER_PORT = 1883;                 // Mosquitto default port
const char *MQTT_CLIENT_ID  = "ESP_TBS_GW_001";      // Unique device ID
const char *MQTT_USERNAME   = "iot_gateway";         // Mosquitto auth username
const char *MQTT_PASSWORD   = "secure_mqtt_pass";    // Mosquitto auth password

// ── MQTT Topics ───────────────────────────────────────────────────────────────
const char *MQTT_TOPIC_RESULT  = "pks/grading/tbs/result";  // QoS 1: scan results
const char *MQTT_TOPIC_STATUS  = "pks/grading/tbs/status";  // QoS 0: heartbeat
const char *MQTT_TOPIC_CMD     = "pks/grading/tbs/cmd";     // Subscribe: commands

// ── LoRa Radio Settings ───────────────────────────────────────────────────────
// Ai-Thinker LoRa-02 (SX1278) — for Indonesia: use 433 MHz band
// Change to 915000000L for US/Australia
const long  LORA_FREQUENCY     = 433E6;    // 433 MHz (SX1278 LoRa frequency)
const int   LORA_SPREADING_SF  = 10;       // Spreading factor 10 (range vs. speed)
const long  LORA_BANDWIDTH     = 125E3;    // 125 kHz bandwidth (standard)
const int   LORA_CODING_RATE   = 5;        // 4/5 coding rate
const int   LORA_TX_POWER_DBM  = 17;       // 17 dBm output power

// ── ESP-12E GPIO Pin Assignments ──────────────────────────────────────────────
// SPI bus is shared between LoRa-02 and internal flash.
// Standard ESP8266 SPI pins: CLK=14, MISO=12, MOSI=13
const int PIN_LORA_NSS  = 15;   // GPIO15: LoRa SPI Chip Select (CS)
const int PIN_LORA_RST  = 16;   // GPIO16: LoRa Reset
const int PIN_LORA_DIO0 = 4;    // GPIO4:  LoRa DIO0 (interrupt on TX/RX done)

// ── Timing Constants ──────────────────────────────────────────────────────────
const uint32_t HEARTBEAT_INTERVAL_MS   = 30000UL;  // 30 seconds between heartbeats
const uint32_t WIFI_RECONNECT_DELAY_MS = 5000UL;   // Retry Wi-Fi every 5 seconds
const uint32_t MQTT_RECONNECT_DELAY_MS = 3000UL;   // Retry MQTT every 3 seconds
const uint32_t UART_READ_TIMEOUT_MS    = 100UL;    // UART line accumulation timeout
const uint32_t WIFI_CONNECT_TIMEOUT_MS = 15000UL;  // Max time to wait for Wi-Fi

// ── JSON Buffer Sizes ─────────────────────────────────────────────────────────
// Input from MAX78000: {"g":3,"c":100}\n → max ~18 bytes
// StaticJsonDocument capacity should be 2x estimated JSON size + overhead
const int JSON_INPUT_CAPACITY   = 64;    // For parsing incoming {"g","c"}
const int JSON_PUBLISH_CAPACITY = 256;   // For building outbound JSON payload
const int LORA_PAYLOAD_CAPACITY = 64;    // For compact LoRa alert string

// ═════════════════════════════════════════════════════════════════════════════
// GLOBAL OBJECTS
// ═════════════════════════════════════════════════════════════════════════════

WiFiClient    wifiClient;                 // TCP socket for MQTT
PubSubClient  mqttClient(wifiClient);     // MQTT client instance

// ── State Variables ───────────────────────────────────────────────────────────
bool     loraInitialized    = false;  // Tracks LoRa module init success
bool     wifiConnected      = false;  // Current Wi-Fi connection status
bool     mqttConnected      = false;  // Current MQTT connection status

uint32_t lastHeartbeatMs    = 0;      // Millis timestamp of last heartbeat
uint32_t lastWifiRetryMs    = 0;      // Millis timestamp of last Wi-Fi retry
uint32_t lastMqttRetryMs    = 0;      // Millis timestamp of last MQTT retry

uint32_t totalBunchesScanned = 0;     // Lifetime scan count (resets on reboot)

// UART input buffer for accumulating JSON line from MAX78000
String   uartLineBuffer     = "";     // Accumulates bytes until '\n' is received
uint32_t lastUartByteMs     = 0;      // Timestamp of last received UART byte

// ═════════════════════════════════════════════════════════════════════════════
// PRIVATE FUNCTION DECLARATIONS
// ═════════════════════════════════════════════════════════════════════════════

bool     initWifi(void);
bool     reconnectWifi(void);
bool     initMqtt(void);
bool     reconnectMqtt(void);
bool     initLora(void);
void     publishResultMqtt(uint8_t grade, uint8_t confidence, uint32_t timestamp_ms);
void     publishAlertLora(uint8_t grade, uint8_t confidence);
void     sendHeartbeat(void);
void     mqttCallback(char *topic, byte *payload, unsigned int length);
bool     parseUartJson(const String &json_str, uint8_t &grade, uint8_t &confidence);
String   buildResultJson(uint8_t grade, uint8_t confidence, uint32_t timestamp_ms);
String   buildStatusJson(void);
const char *gradeToString(uint8_t grade);

// ═════════════════════════════════════════════════════════════════════════════
// SETUP
// ═════════════════════════════════════════════════════════════════════════════

void setup()
{
    // ── Hardware Serial (UART communication with MAX78000) ─────────────────
    // On ESP-12E: Serial uses GPIO1 (TX) and GPIO3 (RX)
    // This same Serial is used for debug output — in production, consider
    // using Serial1 or Software Serial for debug to free Serial for MAX78000.
    Serial.begin(115200);
    Serial.setTimeout(UART_READ_TIMEOUT_MS);

    // Wait for Serial to be ready
    delay(100);

    Serial.println("\r\n");
    Serial.println("=========================================");
    Serial.println("  ESP-12E Edge Gateway — TBS Grader    ");
    Serial.println("  Edge AI Palm Oil FFB System           ");
    Serial.println("=========================================");

    // ── LoRa Radio Initialization (done FIRST before Wi-Fi) ───────────────
    // LoRa uses SPI which should be initialized before Wi-Fi connection attempt.
    loraInitialized = initLora();
    if (!loraInitialized) {
        Serial.println("[GW] WARNING: LoRa init failed — no fallback radio available.");
    } else {
        Serial.println("[GW] LoRa radio initialized. Fallback channel ready.");
    }

    // ── Wi-Fi Connection ──────────────────────────────────────────────────
    wifiConnected = initWifi();

    // ── MQTT Client Setup ─────────────────────────────────────────────────
    mqttClient.setServer(MQTT_BROKER_IP, MQTT_BROKER_PORT);
    mqttClient.setCallback(mqttCallback);
    mqttClient.setKeepAlive(60);           // 60-second MQTT keepalive
    mqttClient.setSocketTimeout(5);        // 5-second socket timeout for clean disconnect

    if (wifiConnected) {
        mqttConnected = reconnectMqtt();
    }

    // ── Publish Boot Status ───────────────────────────────────────────────
    if (mqttConnected) {
        String status_json = buildStatusJson();
        mqttClient.publish(MQTT_TOPIC_STATUS, status_json.c_str(), false /* retain */);
        Serial.print("[GW] Boot status published: ");
        Serial.println(status_json);
    }

    // Initialize heartbeat timer
    lastHeartbeatMs = millis();

    // Clear UART line buffer
    uartLineBuffer = "";

    Serial.println("[GW] Setup complete. Listening for MAX78000 data...");
}

// ═════════════════════════════════════════════════════════════════════════════
// MAIN LOOP
// ═════════════════════════════════════════════════════════════════════════════

void loop()
{
    uint32_t now = millis();

    // ── 1. Wi-Fi Health Check & Reconnection ──────────────────────────────
    if (WiFi.status() != WL_CONNECTED) {
        if (!wifiConnected || (now - lastWifiRetryMs >= WIFI_RECONNECT_DELAY_MS)) {
            Serial.println("[GW] Wi-Fi disconnected. Attempting reconnect...");
            wifiConnected = reconnectWifi();
            lastWifiRetryMs = now;
            mqttConnected = false;  // MQTT is also lost if Wi-Fi dropped
        }
    } else {
        wifiConnected = true;

        // ── 2. MQTT Health Check & Reconnection ───────────────────────────
        if (!mqttClient.connected()) {
            if (!mqttConnected || (now - lastMqttRetryMs >= MQTT_RECONNECT_DELAY_MS)) {
                Serial.println("[GW] MQTT disconnected. Attempting reconnect...");
                mqttConnected = reconnectMqtt();
                lastMqttRetryMs = now;
            }
        } else {
            mqttConnected = true;
            // Process pending MQTT messages (subscription callbacks, keepalive)
            mqttClient.loop();
        }
    }

    // ── 3. Read UART Data from MAX78000 (line-buffered) ───────────────────
    // The MAX78000 sends: {"g":1,"c":94}\n
    // We accumulate bytes until '\n' is received or timeout occurs.
    while (Serial.available() > 0) {
        char incomingChar = (char)Serial.read();
        lastUartByteMs = millis();

        if (incomingChar == '\n' || incomingChar == '\r') {
            // End of line — process if buffer has content
            if (uartLineBuffer.length() > 0) {
                // Trim any trailing whitespace/carriage returns
                uartLineBuffer.trim();

                Serial.print("[GW] Received from MAX78000: ");
                Serial.println(uartLineBuffer);

                // Parse the JSON payload
                uint8_t grade      = 0;
                uint8_t confidence = 0;

                if (parseUartJson(uartLineBuffer, grade, confidence)) {
                    // Successful parse — handle the result
                    totalBunchesScanned++;
                    uint32_t timestamp = millis();

                    Serial.printf("[GW] Parsed: grade=%u (%s), confidence=%u%%\r\n",
                                  grade, gradeToString(grade), confidence);

                    // ── Primary Path: MQTT over Wi-Fi ────────────────────
                    if (wifiConnected && mqttConnected) {
                        publishResultMqtt(grade, confidence, timestamp);
                    }
                    // ── Fallback Path: LoRa radio ─────────────────────────
                    else {
                        Serial.println("[GW] Wi-Fi/MQTT unavailable — routing via LoRa.");
                        if (loraInitialized) {
                            publishAlertLora(grade, confidence);
                        } else {
                            Serial.println("[GW] CRITICAL: Both Wi-Fi and LoRa unavailable! Data lost.");
                        }
                    }
                } else {
                    Serial.print("[GW] WARNING: JSON parse failed for: ");
                    Serial.println(uartLineBuffer);
                }

                // Clear buffer for next message
                uartLineBuffer = "";
            }
        } else {
            // Accumulate character into buffer
            // Guard against buffer overflow (max expected line length: ~25 chars)
            if (uartLineBuffer.length() < JSON_INPUT_CAPACITY) {
                uartLineBuffer += incomingChar;
            } else {
                Serial.println("[GW] WARNING: UART buffer overflow — discarding line.");
                uartLineBuffer = "";
            }
        }
    }

    // ── 4. UART Timeout: Discard Incomplete Lines ─────────────────────────
    // If we received some bytes but then nothing for UART_READ_TIMEOUT_MS,
    // the partial message is corrupt — discard it.
    if (uartLineBuffer.length() > 0 &&
        (millis() - lastUartByteMs) > UART_READ_TIMEOUT_MS) {
        Serial.print("[GW] UART timeout — discarding partial: ");
        Serial.println(uartLineBuffer);
        uartLineBuffer = "";
    }

    // ── 5. Periodic Heartbeat ─────────────────────────────────────────────
    if ((now - lastHeartbeatMs) >= HEARTBEAT_INTERVAL_MS) {
        sendHeartbeat();
        lastHeartbeatMs = now;
    }

    // Small yield to allow ESP8266 background tasks (Wi-Fi stack, watchdog feed)
    yield();
}

// ═════════════════════════════════════════════════════════════════════════════
// PRIVATE FUNCTION IMPLEMENTATIONS
// ═════════════════════════════════════════════════════════════════════════════

/**
 * @brief  Initialize Wi-Fi connection. Blocks until connected or timeout.
 * @return true if connected, false if timeout or error.
 */
bool initWifi(void)
{
    Serial.printf("[GW] Connecting to Wi-Fi: %s\r\n", WIFI_SSID);

    // Set station mode (not AP)
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);    // Auto-reconnect on dropout
    WiFi.setPersistent(false);      // Don't save credentials to flash (manage manually)

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    uint32_t start_time = millis();
    while (WiFi.status() != WL_CONNECTED) {
        delay(250);
        Serial.print(".");
        if ((millis() - start_time) > WIFI_CONNECT_TIMEOUT_MS) {
            Serial.println("\r\n[GW] Wi-Fi connection timeout.");
            return false;
        }
    }

    Serial.println();
    Serial.printf("[GW] Wi-Fi connected! IP: %s, RSSI: %d dBm\r\n",
                  WiFi.localIP().toString().c_str(),
                  WiFi.RSSI());
    return true;
}

/**
 * @brief  Attempt to reconnect to Wi-Fi (non-blocking single attempt).
 * @return true if now connected.
 */
bool reconnectWifi(void)
{
    if (WiFi.status() == WL_CONNECTED) return true;

    WiFi.reconnect();
    uint32_t start_time = millis();

    while (WiFi.status() != WL_CONNECTED) {
        if ((millis() - start_time) > WIFI_CONNECT_TIMEOUT_MS) {
            Serial.println("[GW] Wi-Fi reconnect timeout.");
            return false;
        }
        delay(250);
        yield();
    }

    Serial.printf("[GW] Wi-Fi reconnected. IP: %s\r\n",
                  WiFi.localIP().toString().c_str());
    return true;
}

/**
 * @brief  Connect (or reconnect) to the MQTT broker.
 *
 * @details Publishes an LWT (Last Will and Testament) message so the broker
 *          can detect ungraceful disconnects (power loss, firmware crash).
 *          LWT payload: {"status":"offline"} on topic: pks/grading/tbs/status
 *
 * @return true if MQTT connection established.
 */
bool reconnectMqtt(void)
{
    if (!wifiConnected) return false;

    // Define Last Will & Testament (LWT) for ungraceful disconnect detection
    const char *lwt_topic   = MQTT_TOPIC_STATUS;
    const char *lwt_payload = "{\"status\":\"offline\",\"reason\":\"ungraceful\"}";
    const int   lwt_qos     = 0;
    const bool  lwt_retain  = true;  // Retained: broker serves this to new subscribers

    Serial.printf("[GW] Connecting to MQTT broker %s:%d...\r\n",
                  MQTT_BROKER_IP, MQTT_BROKER_PORT);

    bool connected = mqttClient.connect(
        MQTT_CLIENT_ID,
        MQTT_USERNAME,
        MQTT_PASSWORD,
        lwt_topic,    // LWT topic
        lwt_qos,      // LWT QoS
        lwt_retain,   // LWT retained
        lwt_payload   // LWT payload
    );

    if (!connected) {
        Serial.printf("[GW] MQTT connect failed. State: %d\r\n", mqttClient.state());
        /* PubSubClient state codes:
         *   -4: MQTT_CONNECTION_TIMEOUT    -3: MQTT_CONNECTION_LOST
         *   -2: MQTT_CONNECT_FAILED        -1: MQTT_DISCONNECTED
         *    0: MQTT_CONNECTED              1: MQTT_CONNECT_BAD_PROTOCOL
         *    2: MQTT_CONNECT_BAD_CLIENT_ID  3: MQTT_CONNECT_UNAVAILABLE
         *    4: MQTT_CONNECT_BAD_CREDENTIALS 5: MQTT_CONNECT_UNAUTHORIZED
         */
        return false;
    }

    Serial.println("[GW] MQTT connected.");

    // Subscribe to command topic for future OTA / config updates
    if (!mqttClient.subscribe(MQTT_TOPIC_CMD, 1 /* QoS 1 */)) {
        Serial.println("[GW] WARNING: Failed to subscribe to command topic.");
    } else {
        Serial.printf("[GW] Subscribed to: %s\r\n", MQTT_TOPIC_CMD);
    }

    return true;
}

/**
 * @brief  Initialize the Ai-Thinker LoRa-02 (SX1278) radio module.
 * @return true if SX1278 detected and configured, false otherwise.
 */
bool initLora(void)
{
    Serial.printf("[GW] Initializing LoRa-02 (SX1278) at %.0f MHz...\r\n",
                  (float)(LORA_FREQUENCY / 1e6));

    // Configure pins before begin()
    LoRa.setPins(PIN_LORA_NSS, PIN_LORA_RST, PIN_LORA_DIO0);

    // Initialize LoRa with frequency
    if (!LoRa.begin(LORA_FREQUENCY)) {
        Serial.println("[GW] LoRa SX1278 not found. Check wiring to GPIO15/14/13/12.");
        return false;
    }

    // Configure radio parameters for maximum range (at cost of lower data rate)
    // These settings target a range of ~5-10 km in open field / ~1-2 km in factory
    LoRa.setSpreadingFactor(LORA_SPREADING_SF);     // SF10: good balance
    LoRa.setSignalBandwidth(LORA_BANDWIDTH);         // 125 kHz
    LoRa.setCodingRate4(LORA_CODING_RATE);           // 4/5 coding rate
    LoRa.setTxPower(LORA_TX_POWER_DBM);              // 17 dBm
    LoRa.enableCrc();                                // Enable CRC for data integrity

    Serial.println("[GW] LoRa initialized successfully.");
    Serial.printf("[GW]   SF=%d, BW=%.0f kHz, CR=4/%d, Power=%d dBm\r\n",
                  LORA_SPREADING_SF,
                  (float)(LORA_BANDWIDTH / 1e3),
                  LORA_CODING_RATE,
                  LORA_TX_POWER_DBM);
    return true;
}

/**
 * @brief  Parse a JSON string received from MAX78000 into grade/confidence values.
 *
 * @details Uses ArduinoJson v6 StaticJsonDocument for stack-allocated, zero-heap
 *          parsing. Input format: {"g":<grade>,"c":<confidence>}
 *          Also handles the boot message: {"status":"READY","dev":"MAX78000"}
 *
 * @param  json_str    The raw JSON string to parse.
 * @param  grade       Output: parsed grade index [0..3].
 * @param  confidence  Output: parsed confidence percentage [0..100].
 *
 * @return true if a valid grade+confidence pair was parsed, false otherwise.
 */
bool parseUartJson(const String &json_str, uint8_t &grade, uint8_t &confidence)
{
    StaticJsonDocument<JSON_INPUT_CAPACITY> doc;

    DeserializationError err = deserializeJson(doc, json_str);

    if (err != DeserializationError::Ok) {
        Serial.printf("[GW] JSON deserialize error: %s\r\n", err.c_str());
        return false;
    }

    // Validate that the required fields exist and are numeric
    if (!doc.containsKey("g") || !doc.containsKey("c")) {
        // May be a status message (e.g., {"status":"READY"}) — not an error
        if (doc.containsKey("status")) {
            Serial.printf("[GW] Status message from MAX78000: %s\r\n",
                          doc["status"].as<const char *>());
        }
        return false;
    }

    uint8_t parsed_grade      = doc["g"].as<uint8_t>();
    uint8_t parsed_confidence = doc["c"].as<uint8_t>();

    // Bounds validation
    if (parsed_grade > 3) {
        Serial.printf("[GW] WARNING: Invalid grade value: %u (max 3)\r\n", parsed_grade);
        return false;
    }

    if (parsed_confidence > 100) {
        Serial.printf("[GW] WARNING: Invalid confidence: %u (max 100)\r\n", parsed_confidence);
        return false;
    }

    grade      = parsed_grade;
    confidence = parsed_confidence;
    return true;
}

/**
 * @brief  Build the JSON result payload for MQTT publication.
 *
 * @details Output format: {"g":<grade>,"c":<confidence>,"ts":<millis>,"cnt":<count>}
 *          - "g":   Grade index [0..3]
 *          - "c":   Confidence percentage [0..100]
 *          - "ts":  ESP8266 millis() timestamp (for relative timing)
 *          - "cnt": Total scan count since last reboot
 *
 * @param  grade           Grade class index.
 * @param  confidence      Confidence percentage.
 * @param  timestamp_ms    Timestamp in milliseconds (from millis()).
 * @return Serialized JSON String.
 */
String buildResultJson(uint8_t grade, uint8_t confidence, uint32_t timestamp_ms)
{
    StaticJsonDocument<JSON_PUBLISH_CAPACITY> doc;

    doc["g"]   = grade;
    doc["c"]   = confidence;
    doc["ts"]  = timestamp_ms;
    doc["cnt"] = totalBunchesScanned;

    String output;
    serializeJson(doc, output);
    return output;
}

/**
 * @brief  Build the JSON heartbeat/status payload.
 *
 * @return Serialized JSON String with status fields.
 */
String buildStatusJson(void)
{
    StaticJsonDocument<JSON_PUBLISH_CAPACITY> doc;

    doc["status"] = "online";
    doc["uptime"] = millis();
    doc["ip"]     = WiFi.localIP().toString();
    doc["rssi"]   = WiFi.RSSI();
    doc["scans"]  = totalBunchesScanned;
    doc["lora"]   = loraInitialized ? "ok" : "fail";

    String output;
    serializeJson(doc, output);
    return output;
}

/**
 * @brief  Publish a scan result to MQTT broker with QoS 1.
 *
 * @details QoS 1 ensures at-least-once delivery with acknowledgement.
 *          PubSubClient's publish() with retained=false means the broker
 *          does not cache this message for future subscribers (real-time only).
 *
 * @param  grade           Grade class index [0..3].
 * @param  confidence      Confidence percentage [0..100].
 * @param  timestamp_ms    Scan timestamp in milliseconds.
 */
void publishResultMqtt(uint8_t grade, uint8_t confidence, uint32_t timestamp_ms)
{
    String payload = buildResultJson(grade, confidence, timestamp_ms);

    // PubSubClient publish() signature: (topic, payload, retained)
    // QoS 1 requires the retained parameter to be false (PubSubClient limitation:
    // it does not natively support explicit QoS 1 PUBACK waiting, but sets the
    // QoS bit in the PUBLISH packet).
    bool success = mqttClient.publish(MQTT_TOPIC_RESULT, payload.c_str(), false);

    if (success) {
        Serial.printf("[GW] MQTT published to %s: %s\r\n",
                      MQTT_TOPIC_RESULT, payload.c_str());
    } else {
        Serial.println("[GW] ERROR: MQTT publish failed!");

        // Attempt LoRa fallback for critical data on MQTT publish failure
        Serial.println("[GW] Attempting LoRa fallback for missed MQTT publish.");
        if (loraInitialized) {
            publishAlertLora(grade, confidence);
        }
    }
}

/**
 * @brief  Transmit a compact alert payload over LoRa radio.
 *
 * @details LoRa is used as a backup channel when Wi-Fi/MQTT is unavailable.
 *          Payload is kept compact to minimize airtime (LoRa duty cycle limit).
 *          Format: "TBS:G<grade>:C<confidence>" (e.g., "TBS:G3:C72")
 *
 *          The LoRa packet is received by a LoRa gateway node (if deployed)
 *          which forwards it to the MQTT broker or a separate alarm system.
 *
 * @param  grade       Grade class index [0..3].
 * @param  confidence  Confidence percentage [0..100].
 */
void publishAlertLora(uint8_t grade, uint8_t confidence)
{
    if (!loraInitialized) {
        Serial.println("[GW] LoRa not available — cannot send.");
        return;
    }

    // Build compact payload
    char lora_payload[LORA_PAYLOAD_CAPACITY];
    snprintf(lora_payload, sizeof(lora_payload),
             "TBS:G%u:C%u:CNT%lu",
             (unsigned int)grade,
             (unsigned int)confidence,
             (unsigned long)totalBunchesScanned);

    // Begin LoRa packet transmission
    LoRa.beginPacket();
    LoRa.print(lora_payload);
    bool sent = LoRa.endPacket(false /* async = false: wait for TX done */);

    if (sent) {
        Serial.printf("[GW] LoRa packet sent: %s\r\n", lora_payload);
    } else {
        Serial.println("[GW] ERROR: LoRa packet transmission failed!");
    }
}

/**
 * @brief  Send a 30-second periodic heartbeat/status payload.
 *
 * @details Publishes to pks/grading/tbs/status with QoS 0 (best effort).
 *          The TimescaleDB ingestion daemon does NOT process this topic —
 *          it is used by Grafana for gateway health monitoring.
 *          Also sent over LoRa if MQTT is unavailable, for remote monitoring.
 */
void sendHeartbeat(void)
{
    Serial.println("[GW] Sending heartbeat...");

    if (wifiConnected && mqttConnected) {
        String status_json = buildStatusJson();

        // QoS 0 heartbeat (no delivery guarantee — acceptable for status pings)
        bool ok = mqttClient.publish(MQTT_TOPIC_STATUS, status_json.c_str(), false);
        if (ok) {
            Serial.printf("[GW] Heartbeat published: %s\r\n", status_json.c_str());
        } else {
            Serial.println("[GW] Heartbeat MQTT publish failed.");
        }
    } else {
        // Wi-Fi/MQTT unavailable — send LoRa keepalive
        if (loraInitialized) {
            char lora_hb[LORA_PAYLOAD_CAPACITY];
            snprintf(lora_hb, sizeof(lora_hb),
                     "TBS:HB:UP%lu:SC%lu",
                     (unsigned long)(millis() / 1000),
                     (unsigned long)totalBunchesScanned);
            LoRa.beginPacket();
            LoRa.print(lora_hb);
            LoRa.endPacket();
            Serial.printf("[GW] LoRa heartbeat sent: %s\r\n", lora_hb);
        } else {
            Serial.println("[GW] Heartbeat failed — no transport available.");
        }
    }
}

/**
 * @brief  MQTT subscription callback for the command topic.
 *
 * @details Called by PubSubClient when a message arrives on subscribed topics.
 *          Currently supports:
 *            {"cmd":"reboot"}  — Software reboot the ESP-12E
 *            {"cmd":"status"}  — Force-send an immediate status report
 *
 * @param  topic    MQTT topic of the incoming message.
 * @param  payload  Message payload byte array.
 * @param  length   Length of the payload in bytes.
 */
void mqttCallback(char *topic, byte *payload, unsigned int length)
{
    // Copy payload to a null-terminated string for parsing
    char payload_str[128];
    unsigned int copy_len = min(length, (unsigned int)(sizeof(payload_str) - 1));
    memcpy(payload_str, payload, copy_len);
    payload_str[copy_len] = '\0';

    Serial.printf("[GW] MQTT command received on %s: %s\r\n", topic, payload_str);

    // Parse the command JSON
    StaticJsonDocument<JSON_INPUT_CAPACITY> cmd_doc;
    DeserializationError err = deserializeJson(cmd_doc, payload_str);

    if (err != DeserializationError::Ok) {
        Serial.printf("[GW] Command JSON parse error: %s\r\n", err.c_str());
        return;
    }

    const char *cmd = cmd_doc["cmd"];
    if (cmd == nullptr) {
        Serial.println("[GW] Command JSON missing 'cmd' field.");
        return;
    }

    if (strcmp(cmd, "reboot") == 0) {
        Serial.println("[GW] Reboot command received. Rebooting in 1 second...");
        delay(1000);
        ESP.restart();

    } else if (strcmp(cmd, "status") == 0) {
        Serial.println("[GW] Status command received — sending immediate status.");
        sendHeartbeat();
        lastHeartbeatMs = millis();  // Reset heartbeat timer

    } else {
        Serial.printf("[GW] Unknown command: %s\r\n", cmd);
    }
}

/**
 * @brief  Get human-readable grade name string.
 * @param  grade  Class index [0..3].
 * @return ROM-resident constant string.
 */
const char *gradeToString(uint8_t grade)
{
    switch (grade) {
        case 0:  return "Mentah";
        case 1:  return "Matang";
        case 2:  return "Overripe";
        case 3:  return "Janjang Kosong";
        default: return "UNKNOWN";
    }
}
