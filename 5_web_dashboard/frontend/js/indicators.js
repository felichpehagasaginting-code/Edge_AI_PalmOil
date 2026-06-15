/**
 * @file    indicators.js
 * @brief   LED status indicators, metric cards, anomaly alerts,
 *          and the Device Connection Status bar.
 *
 * Manages all DOM elements that show live state:
 *   - LED dots (MQTT / MAX78000 / ESP-12E / LoRa / Server)
 *   - Connection bar cards (conn-bar panel)
 *   - Offline banner
 *   - Last scan card (grade badge, confidence bar)
 *   - Throughput gauge value
 *   - Today's total counter
 *   - Anomaly alert toast + flash overlay
 *   - Live feed table rows
 */

const Indicators = (() => {
  // ── LED Indicator helper ───────────────────────────────────────────────────
  /**
   * Set the visual state of an LED dot element.
   * @param {string} id      Element ID of the .led-dot span
   * @param {'green'|'red'|'yellow'|'gray'} state
   * @param {string} [title] Tooltip text
   */
  function setLed(id, state, title) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = `led-dot led-${state}`;
    if (title) el.title = title;
  }

  // ── Connection Panel ────────────────────────────────────────────────────────
  /**
   * Track last-seen timestamps per device key.
   * Keys: 'max78000' | 'esp12e' | 'mqtt' | 'lora' | 'server'
   */
  const _lastSeen = {};

  /**
   * Update one card in the Device Connection Status bar.
   *
   * @param {'max78000'|'esp12e'|'mqtt'|'lora'|'server'} key
   * @param {'online'|'offline'|'reconnecting'|'waiting'} state
   * @param {string} statusText  Human-readable status line
   * @param {boolean} [seen]     If true, record last-seen = now
   */
  function updateConnPanel(key, state, statusText, seen = false) {
    const card   = document.getElementById(`connCard_${key}`);
    const led    = document.getElementById(`connLed_${key}`);
    const status = document.getElementById(`connStatus_${key}`);
    const time   = document.getElementById(`connTime_${key}`);

    if (card)   card.dataset.state = state;
    if (status) status.textContent  = statusText;

    // LED colour mapping
    const ledState = {
      online:       'green',
      offline:      'red',
      reconnecting: 'yellow',
      waiting:      'gray',
    }[state] ?? 'gray';

    if (led) {
      led.className = `led-dot led-${ledState}`;
      led.title     = statusText;
    }

    // Update last-seen time
    if (seen) {
      _lastSeen[key] = new Date();
    }
    if (time) {
      time.textContent = _lastSeen[key]
        ? _lastSeen[key].toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
        : '—';
    }
  }

  // ── Offline Banner ──────────────────────────────────────────────────────────
  /**
   * Show or hide the offline banner.
   * Banner shows when BOTH server API AND MQTT are unreachable.
   */
  let _serverOnline = false;
  let _mqttOnline   = false;

  function _evalOfflineBanner() {
    const allOffline = !_serverOnline && !_mqttOnline;
    const banner     = document.getElementById('offlineBanner');
    if (banner) {
      if (allOffline) {
        banner.classList.remove('offline-banner-hidden');
      } else {
        banner.classList.add('offline-banner-hidden');
      }
    }
  }

  /**
   * Dim all metric cards when offline (data-offline attribute).
   * @param {boolean} offline
   */
  function setCardsOffline(offline) {
    const cardIds = ['lastScanCard', 'anomalyCard'];
    cardIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.dataset.offline = offline ? 'true' : 'false';
    });

    // Also dim section cards via their parent sections
    document.querySelectorAll('.metrics-row .card').forEach(card => {
      card.dataset.offline = offline ? 'true' : 'false';
    });
  }


  // ── Last Scan Card ─────────────────────────────────────────────────────────
  function updateLastScan(grade, confidence, scanCount) {
    const gradeInfo = CONFIG.GRADES[grade] ?? CONFIG.GRADES[0];

    // Grade badge
    const badge = document.getElementById('lastScanGrade');
    if (badge) {
      badge.textContent = gradeInfo.name;
      badge.style.setProperty('--badge-color', gradeInfo.color);
    }

    // Grade class label
    const classLabel = document.getElementById('lastScanClass');
    if (classLabel) classLabel.textContent = `Kelas ${grade}`;

    // Camera Preview Image
    const previewImg = document.getElementById('cameraPreviewImg');
    if (previewImg) {
      const imgMap = {
        0: 'img/unripe_bunch.png',
        1: 'img/ripe_bunch.png',
        2: 'img/overripe_bunch.png',
        3: 'img/empty_bunch.png',
      };
      previewImg.src = imgMap[grade] ?? 'img/camera_placeholder.png';
    }

    // Confidence percentage
    const confEl = document.getElementById('lastScanConf');
    if (confEl) confEl.textContent = `${confidence}%`;

    // Confidence progress bar
    const bar = document.getElementById('confBar');
    if (bar) {
      bar.style.width = `${confidence}%`;
      // Color based on confidence level
      bar.style.background =
        confidence >= 80 ? '#00ff9d' :
        confidence >= 60 ? '#ffa502' : '#ff4757';
    }

    // Scan number
    const scanEl = document.getElementById('lastScanNum');
    if (scanEl && scanCount != null) scanEl.textContent = `#${scanCount}`;

    // Timestamp
    const timeEl = document.getElementById('lastScanTime');
    if (timeEl) {
      timeEl.textContent = new Date().toLocaleTimeString('id-ID', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
    }

    // Card flash animation
    const card = document.getElementById('lastScanCard');
    if (card) {
      card.classList.remove('card-flash');
      void card.offsetWidth; // reflow to restart animation
      card.classList.add('card-flash');
    }
  }

  // ── Stats Metrics ──────────────────────────────────────────────────────────
  function updateStats(stats) {
    _setText('statTotal',      stats.total_scanned ?? 0);
    _setText('statMatang',     stats.matang_count  ?? 0);
    _setText('statMentah',     stats.mentah_count  ?? 0);
    _setText('statOverripe',   stats.overripe_count ?? 0);
    _setText('statJanjang',    stats.janjang_count ?? 0);
    _setText('statAnomalies',  stats.anomaly_count ?? 0);
    _setText('statAvgConf',   `${stats.avg_confidence ?? 0}%`);
    _setText('statMatangRate', `${stats.matang_rate_pct ?? 0}%`);
  }

  // ── Throughput Gauge ───────────────────────────────────────────────────────
  function updateThroughputGauge(rows) {
    if (!rows || rows.length === 0) {
      _setText('throughputValue', '0');
      return;
    }
    // Take the most recent completed minute bucket
    const latest = rows[rows.length - 1];
    _setText('throughputValue', latest.count ?? 0);
  }

  // ── Gateway Status ─────────────────────────────────────────────────────────
  function updateGatewayStatus(gwData) {
    const isOnline = gwData.status === 'online' && !gwData.stale;
    const loraOk   = gwData.lora_status === 'ok';

    setLed('ledGateway', isOnline ? 'green' : 'red',
           isOnline ? `Gateway Online — IP: ${gwData.ip_address ?? 'N/A'}` : 'Gateway Offline');
    setLed('ledLora', loraOk ? 'green' : 'red',
           loraOk ? 'LoRa-02 OK' : 'LoRa-02 Fault');

    // Update connection panel — ESP-12E
    if (isOnline) {
      const rssiText = gwData.wifi_rssi_dbm != null ? ` (${gwData.wifi_rssi_dbm} dBm)` : '';
      updateConnPanel('esp12e', 'online', `Online${rssiText}`, true);
    } else {
      updateConnPanel('esp12e', gwData.stale ? 'offline' : 'waiting',
                      gwData.stale ? `Tidak responsif (>${CONFIG.GATEWAY_STALE_THRESHOLD_SEC}s)` : 'Belum ada data');
    }

    // Update connection panel — LoRa
    updateConnPanel('lora',
      loraOk ? 'online' : (gwData.status === 'online' ? 'offline' : 'waiting'),
      loraOk ? 'OK · 433 MHz' : (gwData.status === 'online' ? 'Fault / Tidak terdeteksi' : 'Menunggu gateway'),
      loraOk);

    // RSSI badge
    const rssiEl = document.getElementById('gatewayRssi');
    if (rssiEl && gwData.wifi_rssi_dbm != null) {
      rssiEl.textContent = `${gwData.wifi_rssi_dbm} dBm`;
      rssiEl.style.color =
        gwData.wifi_rssi_dbm >= -60 ? '#00ff9d' :
        gwData.wifi_rssi_dbm >= -75 ? '#ffa502' : '#ff4757';
    }
  }


  // ── MQTT Connection State ──────────────────────────────────────────────────
  function updateMqttState(connected, reason) {
    _mqttOnline = connected;
    _evalOfflineBanner();

    setLed('ledMqtt', connected ? 'green' : 'red',
           connected ? 'MQTT Terhubung' : `MQTT Terputus${reason ? ': ' + reason : ''}`);

    const statusBar = document.getElementById('mqttStatusBar');
    if (statusBar) {
      statusBar.textContent = connected ? 'Live ●' : '⚡ Reconnecting...';
      statusBar.className   = connected ? 'status-badge badge-green' : 'status-badge badge-red pulse';
    }

    // Update connection panel
    if (connected) {
      updateConnPanel('mqtt', 'online', 'Terhubung', true);
    } else {
      const text = reason ? `Terputus: ${reason}` : 'Menghubungkan ulang…';
      updateConnPanel('mqtt', reason ? 'offline' : 'reconnecting', text);
    }
  }

  // ── Anomaly Alert Toast ────────────────────────────────────────────────────
  let _anomalyQueue  = [];
  let _showingToast  = false;

  function triggerAnomalyAlert(grade, confidence, scanCount) {
    const gradeInfo = CONFIG.GRADES[grade] ?? CONFIG.GRADES[0];
    _anomalyQueue.push({ gradeInfo, confidence, scanCount });
    if (!_showingToast) _processToastQueue();

    // Flash the whole screen briefly
    const overlay = document.getElementById('alertOverlay');
    if (overlay) {
      overlay.classList.remove('flash');
      void overlay.offsetWidth;
      overlay.classList.add('flash');
    }

    // Bump anomaly counter
    const counter = document.getElementById('statAnomalies');
    if (counter) {
      const current = parseInt(counter.textContent, 10) || 0;
      counter.textContent = current + 1;
    }
  }

  function _processToastQueue() {
    if (_anomalyQueue.length === 0) { _showingToast = false; return; }
    _showingToast = true;

    const { gradeInfo, confidence, scanCount } = _anomalyQueue.shift();

    const toast   = document.getElementById('anomalyToast');
    const nameEl  = document.getElementById('toastGradeName');
    const confEl  = document.getElementById('toastConfidence');
    const scanEl  = document.getElementById('toastScanNum');

    if (!toast) return;
    if (nameEl)  nameEl.textContent  = gradeInfo.name;
    if (confEl)  confEl.textContent  = `${confidence}% conf.`;
    if (scanEl)  scanEl.textContent  = scanCount != null ? `#${scanCount}` : '';

    toast.classList.remove('toast-hidden');
    toast.classList.add('toast-show');

    setTimeout(() => {
      toast.classList.remove('toast-show');
      toast.classList.add('toast-hide');
      setTimeout(() => {
        toast.classList.remove('toast-hide');
        toast.classList.add('toast-hidden');
        _processToastQueue();
      }, 400);
    }, 4000);
  }

  // ── Live Feed Table ────────────────────────────────────────────────────────

  /**
   * Prepend a new scan row to the live feed table.
   * Removes oldest row if table exceeds CONFIG.FEED_MAX_ROWS.
   */
  function prependFeedRow(event) {
    const tbody = document.getElementById('feedTableBody');
    if (!tbody) return;

    const gradeInfo   = CONFIG.GRADES[event.grade] ?? CONFIG.GRADES[0];
    const timeStr     = new Date(event.receivedAt || Date.now()).toLocaleTimeString('id-ID', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
    const isAnomaly   = event.grade === CONFIG.JANJANG_KOSONG_GRADE ||
                        event.confidence < CONFIG.MIN_CONFIDENCE_ANOMALY;

    const tr = document.createElement('tr');
    tr.className = isAnomaly ? 'row-anomaly row-new' : 'row-normal row-new';
    tr.innerHTML = `
      <td class="td-time">${timeStr}</td>
      <td>${event.cnt != null ? `<span class="scan-num">#${event.cnt}</span>` : '—'}</td>
      <td><span class="grade-badge" style="--badge-color:${gradeInfo.color}">${gradeInfo.name}</span></td>
      <td>
        <span class="conf-value" style="color:${_confColor(event.confidence)}">${event.confidence}%</span>
      </td>
      <td><span class="transport-tag">${event.transport ?? 'wi-fi'}</span></td>
      <td>${isAnomaly
          ? '<span class="status-tag tag-anomaly">⚠ ANOMALY</span>'
          : '<span class="status-tag tag-normal">✓ Normal</span>'}</td>
    `;

    tbody.insertBefore(tr, tbody.firstChild);

    // Remove animation class after it fires
    requestAnimationFrame(() => {
      setTimeout(() => tr.classList.remove('row-new'), 600);
    });

    // Trim oldest rows
    while (tbody.rows.length > CONFIG.FEED_MAX_ROWS) {
      tbody.deleteRow(tbody.rows.length - 1);
    }
  }

  /**
   * Populate the table with historical rows on initial load.
   */
  function populateFeedFromHistory(rows) {
    const tbody = document.getElementById('feedTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    rows.forEach(row => {
      const synthetic = {
        grade:      row.grade,
        confidence: row.confidence_pct,
        cnt:        row.scan_count,
        transport:  row.transport,
        receivedAt: row.event_time,
        isAnomaly:  row.is_anomaly,
      };
      prependFeedRow(synthetic);
    });
  }

  // ── Utilities ──────────────────────────────────────────────────────────────
  function _setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function _confColor(pct) {
    if (pct >= 80) return '#00ff9d';
    if (pct >= 60) return '#ffa502';
    return '#ff4757';
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  return {
    setLed,
    updateConnPanel,
    setCardsOffline,
    updateLastScan,
    updateStats,
    updateThroughputGauge,
    updateGatewayStatus,
    updateMqttState,
    triggerAnomalyAlert,
    prependFeedRow,
    populateFeedFromHistory,
    /** Expose server online setter so dashboard.js can call it */
    setServerOnline(val) {
      _serverOnline = val;
      _evalOfflineBanner();
      setCardsOffline(!val && !_mqttOnline);
    },
  };
})();
