/**
 * @file    dashboard.js
 * @brief   Main orchestrator — ties together MQTT, Charts, and Indicators.
 *
 * Initialisation order:
 *   1. Charts.init()
 *   2. Fetch initial historical data from REST API
 *   3. Populate live feed table with recent events
 *   4. Start MQTT WebSocket connection
 *   5. Listen for MQTT events → update indicators/charts in real-time
 *   6. Start 5-second polling timer for historical data refresh
 */

(async function DashboardInit() {
  'use strict';

  // ── 1. Init Charts ──────────────────────────────────────────────────────────
  Charts.init();

  // ── 2. REST API helpers ─────────────────────────────────────────────────────
  async function apiFetch(path) {
    try {
      const res = await fetch(`${CONFIG.API_BASE}${path}`, {
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (err) {
      console.warn(`[API] ${path} failed: ${err.message}`);
      return null;
    }
  }

  // ── 3. Initial data load ────────────────────────────────────────────────────
  async function loadHistoricalData() {
    const [stats, throughput, recentEvents, gw] = await Promise.all([
      apiFetch('/stats/today'),
      apiFetch(`/trend/throughput?minutes=${CONFIG.THROUGHPUT_WINDOW_MINUTES}`),
      apiFetch(`/events/recent?limit=${CONFIG.FEED_MAX_ROWS}`),
      apiFetch('/gateway/status'),
    ]);

    const serverOk = stats !== null;

    if (serverOk) {
      Indicators.updateStats(stats);
      Charts.updateDonut(stats);
    }

    if (throughput) {
      Charts.updateThroughput(throughput);
      Indicators.updateThroughputGauge(throughput);
    }

    if (recentEvents && recentEvents.length > 0) {
      Indicators.populateFeedFromHistory(recentEvents);
      const latest = recentEvents[0];
      if (latest) {
        Indicators.updateLastScan(latest.grade, latest.confidence_pct, latest.scan_count);
      }
    }

    if (gw) {
      Indicators.updateGatewayStatus(gw);
    }

    // Server LED + panel
    Indicators.setLed('ledServer', serverOk ? 'green' : 'red',
                      serverOk ? 'Server API Online' : 'Server API Unreachable');
    Indicators.setServerOnline(serverOk);
    Indicators.updateConnPanel(
      'server',
      serverOk ? 'online' : 'offline',
      serverOk ? 'Online · TimescaleDB terhubung' : 'Tidak dapat dijangkau — cek Docker',
      serverOk,
    );
  }

  await loadHistoricalData();

  // ── 4. Start polling timer (every 5 s) ─────────────────────────────────────
  setInterval(async () => {
    const [stats, throughput, gw] = await Promise.all([
      apiFetch('/stats/today'),
      apiFetch(`/trend/throughput?minutes=${CONFIG.THROUGHPUT_WINDOW_MINUTES}`),
      apiFetch('/gateway/status'),
    ]);

    const serverOk = stats !== null;

    if (stats) {
      Indicators.updateStats(stats);
      Charts.updateDonut(stats);
    }
    if (throughput) {
      Charts.updateThroughput(throughput);
      Indicators.updateThroughputGauge(throughput);
    }
    if (gw) {
      Indicators.updateGatewayStatus(gw);
    }

    Indicators.setLed('ledServer', serverOk ? 'green' : 'red');
    Indicators.setServerOnline(serverOk);
    Indicators.updateConnPanel(
      'server',
      serverOk ? 'online' : 'offline',
      serverOk ? 'Online · TimescaleDB terhubung' : 'Tidak dapat dijangkau — cek Docker',
      serverOk,
    );

  }, CONFIG.HISTORICAL_REFRESH_MS);

  // ── 5. MQTT event listeners ─────────────────────────────────────────────────

  // Scan result → update last-scan card, feed table, anomaly alerts
  document.addEventListener('tbs:scan-result', (e) => {
    const { grade, confidence, ts, cnt } = e.detail;

    // LED + panel: MAX78000 just sent data → green
    Indicators.setLed('ledMax78000', 'green', 'MAX78000 Active — Inferensi berhasil');
    Indicators.updateConnPanel('max78000', 'online', `Aktif · Grade ${grade} · ${confidence}% conf.`, true);

    // Update last-scan card
    Indicators.updateLastScan(grade, confidence, cnt);

    // Prepend live feed row
    Indicators.prependFeedRow({
      grade,
      confidence,
      cnt,
      transport:  'wi-fi',
      receivedAt: new Date().toISOString(),
    });

    // Trigger anomaly if needed
    const isAnomaly = grade === CONFIG.JANJANG_KOSONG_GRADE ||
                      confidence < CONFIG.MIN_CONFIDENCE_ANOMALY;
    if (isAnomaly) {
      Indicators.triggerAnomalyAlert(grade, confidence, cnt);
    }
  });

  // Gateway status → update connection LEDs
  document.addEventListener('tbs:gw-status', (e) => {
    const { status, ip, rssi, lora } = e.detail;
    Indicators.updateGatewayStatus({
      status,
      ip_address:    ip,
      wifi_rssi_dbm: rssi,
      lora_status:   lora,
      stale:         false,
    });
    Indicators.setLed('ledGateway', status === 'online' ? 'green' : 'red',
                      status === 'online' ? `ESP-12E Online (${ip})` : 'ESP-12E Offline');
  });

  // MQTT connection state → update MQTT LED
  document.addEventListener('tbs:mqtt-state', (e) => {
    const { connected, reason } = e.detail;
    Indicators.updateMqttState(connected, reason);

    if (connected) {
      // MQTT connected: MAX78000 & ESP-12E go to 'waiting' until first data
      Indicators.setLed('ledMax78000', 'yellow', 'MAX78000 — Menunggu data');
      Indicators.updateConnPanel('max78000', 'waiting', 'MQTT terhubung — menunggu scan…');
    } else {
      Indicators.setLed('ledMax78000', 'gray', 'MAX78000 — MQTT tidak terhubung');
      Indicators.setLed('ledGateway',  'gray', 'ESP-12E  — MQTT tidak terhubung');
      Indicators.updateConnPanel('max78000', 'offline', 'Tidak ada koneksi MQTT');
      Indicators.updateConnPanel('esp12e',   'offline', 'Tidak ada koneksi MQTT');
    }
  });

  // ── 6. Connect MQTT ─────────────────────────────────────────────────────────
  // Small delay so UI renders first before WebSocket handshake
  setTimeout(() => MqttClient.connect(), 300);

  // ── 7. Clock ────────────────────────────────────────────────────────────────
  function _tickClock() {
    const el = document.getElementById('liveClock');
    if (el) {
      el.textContent = new Date().toLocaleTimeString('id-ID', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    }
  }
  _tickClock();
  setInterval(_tickClock, 1000);

  // ── 8. MAX78000 LED blink-off: go to 'waiting' 5s after last scan ─────────
  let _max78kTimer = null;
  document.addEventListener('tbs:scan-result', () => {
    clearTimeout(_max78kTimer);
    _max78kTimer = setTimeout(() => {
      Indicators.setLed('ledMax78000', 'yellow', 'MAX78000 — Menunggu scan berikutnya');
      Indicators.updateConnPanel('max78000', 'waiting', 'Menunggu scan berikutnya…');
    }, 5000);
  });

})();
