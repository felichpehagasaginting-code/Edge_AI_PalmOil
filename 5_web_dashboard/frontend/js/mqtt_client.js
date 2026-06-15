/**
 * @file    mqtt_client.js
 * @brief   Paho MQTT WebSocket client for real-time dashboard updates.
 *
 * Connects to Mosquitto's WebSocket listener (port 9001), subscribes to
 * grading topics, and dispatches CustomEvents that other modules listen to.
 *
 * Events dispatched on document:
 *   'tbs:scan-result'  — detail: { grade, confidence, ts, cnt, raw }
 *   'tbs:gw-status'    — detail: { status, ip, rssi, lora, uptime, scans }
 *   'tbs:mqtt-state'   — detail: { connected: bool, reason?: string }
 */

const MqttClient = (() => {
  // ── Private state ─────────────────────────────────────────────────────────
  let _client         = null;
  let _connected      = false;
  let _reconnectDelay = 1000;   // ms, doubles each failed attempt (max 30s)
  let _reconnectTimer = null;
  let _clientId       = `tbs_dashboard_${Math.random().toString(36).slice(2, 9)}`;

  // ── Helper: dispatch custom event ─────────────────────────────────────────
  function _dispatch(eventName, detail) {
    document.dispatchEvent(new CustomEvent(eventName, { detail, bubbles: false }));
  }

  // ── MQTT callbacks ────────────────────────────────────────────────────────

  function _onConnect() {
    console.info('[MQTT] Connected to broker.');
    _connected      = true;
    _reconnectDelay = 1000;  // reset backoff

    // Subscribe to both topics
    _client.subscribe(CONFIG.MQTT_TOPIC_RESULT, { qos: 1 });
    _client.subscribe(CONFIG.MQTT_TOPIC_STATUS, { qos: 0 });

    _dispatch('tbs:mqtt-state', { connected: true });
  }

  function _onConnectionLost(responseObject) {
    _connected = false;
    const reason = responseObject.errorMessage || 'Connection lost';
    console.warn(`[MQTT] Disconnected: ${reason}`);
    _dispatch('tbs:mqtt-state', { connected: false, reason });

    // Exponential backoff reconnect
    _reconnectTimer = setTimeout(() => {
      console.info(`[MQTT] Reconnecting... (delay ${_reconnectDelay}ms)`);
      _reconnectDelay = Math.min(_reconnectDelay * 2, 30_000);
      _connect();
    }, _reconnectDelay);
  }

  function _onMessageArrived(message) {
    const topic   = message.destinationName;
    const payload = message.payloadString.trim();

    let data;
    try {
      data = JSON.parse(payload);
    } catch (e) {
      console.warn(`[MQTT] JSON parse error on topic ${topic}: ${payload}`);
      return;
    }

    if (topic === CONFIG.MQTT_TOPIC_RESULT) {
      // Validate required fields
      if (data.g == null || data.c == null) return;

      const grade      = parseInt(data.g, 10);
      const confidence = parseInt(data.c, 10);
      if (isNaN(grade) || grade < 0 || grade > 3) return;
      if (isNaN(confidence) || confidence < 0 || confidence > 100) return;

      _dispatch('tbs:scan-result', {
        grade,
        confidence,
        ts:       data.ts  ?? null,
        cnt:      data.cnt ?? null,
        raw:      payload,
        receivedAt: new Date().toISOString(),
      });

    } else if (topic === CONFIG.MQTT_TOPIC_STATUS) {
      _dispatch('tbs:gw-status', {
        status:  data.status  ?? 'unknown',
        ip:      data.ip      ?? null,
        rssi:    data.rssi    ?? null,
        lora:    data.lora    ?? 'unknown',
        uptime:  data.uptime  ?? null,
        scans:   data.scans   ?? null,
      });
    }
  }

  // ── Connect ────────────────────────────────────────────────────────────────
  function _connect() {
    _client = new Paho.Client(
      CONFIG.MQTT_WS_URL,
      _clientId
    );

    _client.onConnectionLost = _onConnectionLost;
    _client.onMessageArrived = _onMessageArrived;

    _client.connect({
      useSSL:   CONFIG.MQTT_WS_URL.startsWith('wss'),
      userName: CONFIG.MQTT_USERNAME,
      password: CONFIG.MQTT_PASSWORD,
      cleanSession: true,
      keepAliveInterval: 30,
      timeout: 10,
      onSuccess: _onConnect,
      onFailure: (err) => {
        console.error(`[MQTT] Connection failed: ${err.errorMessage}`);
        _onConnectionLost({ errorMessage: err.errorMessage });
      },
    });
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  return {
    /** Start the MQTT WebSocket connection. */
    connect() {
      _connect();
    },

    /** Returns true if currently connected. */
    get isConnected() {
      return _connected;
    },

    /** Gracefully disconnect (clears reconnect timer). */
    disconnect() {
      if (_reconnectTimer) clearTimeout(_reconnectTimer);
      if (_client && _connected) _client.disconnect();
    },
  };
})();
