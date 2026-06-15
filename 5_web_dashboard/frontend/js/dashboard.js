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

  // ── Mode Data State ────────────────────────────────────────────────────────
  let isMockMode = localStorage.getItem('mode_data') !== 'real';
  let lastScanCountSeen = null;

  function getApiBase() {
    if (isMockMode) {
      return `${window.location.origin}/api`;
    } else {
      if (window.location.port === '8080') {
        return `http://${window.location.hostname}/api`;
      }
      return `${window.location.origin}/api`;
    }
  }

  // ── 2. REST API helpers ─────────────────────────────────────────────────────
  async function apiFetch(path) {
    try {
      const res = await fetch(`${getApiBase()}${path}`, {
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
        lastScanCountSeen = latest.scan_count;
      }
    }

    if (isMockMode) {
      setMockUIStatus();
    } else if (gw) {
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
    const fetchPromises = [
      apiFetch('/stats/today'),
      apiFetch(`/trend/throughput?minutes=${CONFIG.THROUGHPUT_WINDOW_MINUTES}`),
      apiFetch('/gateway/status'),
    ];

    if (isMockMode) {
      fetchPromises.push(apiFetch(`/events/recent?limit=1`));
    }

    const results = await Promise.all(fetchPromises);
    const stats = results[0];
    const throughput = results[1];
    const gw = results[2];
    const mockEvents = isMockMode ? results[3] : null;

    const serverOk = stats !== null;

    if (stats) {
      Indicators.updateStats(stats);
      Charts.updateDonut(stats);
    }
    if (throughput) {
      Charts.updateThroughput(throughput);
      Indicators.updateThroughputGauge(throughput);
    }
    
    if (isMockMode) {
      setMockUIStatus();
    } else if (gw) {
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

    // Mock scan event generator
    if (isMockMode && mockEvents && mockEvents.length > 0) {
      const latest = mockEvents[0];
      if (latest && latest.scan_count !== lastScanCountSeen) {
        if (lastScanCountSeen !== null) {
          console.info(`[MOCK SIMULATOR] Dispatching scan result #${latest.scan_count}`);
          document.dispatchEvent(new CustomEvent('tbs:scan-result', {
            detail: {
              grade: latest.grade,
              confidence: latest.confidence_pct,
              ts: latest.event_time,
              cnt: latest.scan_count
            }
          }));
        } else {
          Indicators.updateLastScan(latest.grade, latest.confidence_pct, latest.scan_count);
        }
        lastScanCountSeen = latest.scan_count;
      }
    }
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
  setTimeout(() => {
    if (!isMockMode) {
      MqttClient.connect();
    } else {
      setMockUIStatus();
    }
  }, 300);

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
      if (!isMockMode) {
        Indicators.setLed('ledMax78000', 'yellow', 'MAX78000 — Menunggu scan berikutnya');
        Indicators.updateConnPanel('max78000', 'waiting', 'Menunggu scan berikutnya…');
      } else {
        // Keep simulated online in mock mode
        Indicators.setLed('ledMax78000', 'green', 'MAX78000 — Simulasi Aktif');
        Indicators.updateConnPanel('max78000', 'online', 'Simulasi Aktif (Mock)', true);
      }
    }, 5000);
  });

  // ── Mock Status Helper ──
  function setMockUIStatus() {
    Indicators.setLed('ledMqtt', 'yellow', 'MQTT — Dinonaktifkan (MOCK)');
    Indicators.updateConnPanel('mqtt', 'offline', 'MOCK Aktif — MQTT Dinonaktifkan', false);
    
    Indicators.setLed('ledMax78000', 'green', 'MAX78000 — Simulasi Aktif');
    Indicators.updateConnPanel('max78000', 'online', 'Simulasi Aktif (Mock)', true);
    
    Indicators.setLed('ledGateway', 'green', 'ESP-12E — Simulasi Aktif');
    Indicators.updateConnPanel('esp12e', 'online', 'Simulasi Aktif (Mock)', true);
    
    Indicators.setLed('ledLora', 'green', 'LoRa-02 — Simulasi Aktif');
    Indicators.updateConnPanel('lora', 'online', 'Simulasi Aktif (Mock)', true);

    const barEl = document.getElementById('mqttStatusBar');
    if (barEl) {
      barEl.textContent = 'SIMULATION';
      barEl.className = 'status-badge badge-green';
    }
  }

  // ── 9. Mock/Real Mode Toggle Event Handler ─────────────────────────────────
  const toggleInput = document.getElementById('modeDataToggle');
  const toggleStatus = document.getElementById('modeDataStatus');

  if (toggleInput) {
    toggleInput.checked = !isMockMode;
    updateToggleUI();

    toggleInput.addEventListener('change', async (e) => {
      isMockMode = !e.target.checked;
      localStorage.setItem('mode_data', isMockMode ? 'mock' : 'real');
      
      updateToggleUI();
      
      if (isMockMode) {
        MqttClient.disconnect();
        setMockUIStatus();
      } else {
        // Reset Real UI state to waiting/connecting
        Indicators.setLed('ledMqtt', 'yellow', 'MQTT — Menghubungkan…');
        Indicators.updateConnPanel('mqtt', 'waiting', 'Menghubungkan ke broker ws:9001…', false);
        
        Indicators.setLed('ledMax78000', 'yellow', 'MAX78000 — Menunggu data');
        Indicators.updateConnPanel('max78000', 'waiting', 'Menunggu scan…');
        
        Indicators.setLed('ledGateway', 'gray', 'ESP-12E — Menunggu data');
        Indicators.updateConnPanel('esp12e', 'offline', 'Menunggu data…');

        Indicators.setLed('ledLora', 'gray', 'LoRa-02 — Menunggu data');
        Indicators.updateConnPanel('lora', 'offline', 'Menunggu data…');

        const barEl = document.getElementById('mqttStatusBar');
        if (barEl) {
          barEl.textContent = 'Connecting…';
          barEl.className = 'status-badge badge-red pulse';
        }

        MqttClient.connect();
      }

      await loadHistoricalData();
    });
  }

  function updateToggleUI() {
    if (toggleStatus) {
      if (isMockMode) {
        toggleStatus.textContent = 'MOCK';
        toggleStatus.className = 'toggle-status-text mode-mock';
      } else {
        toggleStatus.textContent = 'REAL';
        toggleStatus.className = 'toggle-status-text mode-real';
      }
    }
  }

})();
