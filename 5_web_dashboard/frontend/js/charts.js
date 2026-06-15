/**
 * @file    charts.js
 * @brief   Chart.js chart initialisation and update helpers.
 *
 * Manages:
 *   - donutChart   : Today's grade distribution (Donut)
 *   - throughputChart : Bundles/min rolling line chart (30 min)
 */

const Charts = (() => {


  // ── Grade palette (from CONFIG) ────────────────────────────────────────────
  const GRADE_COLORS = CONFIG.GRADES.map(g => g.color);

  // ── Instances ──────────────────────────────────────────────────────────────
  let _donutChart      = null;
  let _throughputChart = null;

  // ── Donut Chart ────────────────────────────────────────────────────────────

  function _initDonut(canvasId) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx) return null;

    return new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels:   CONFIG.GRADES.map(g => g.name),
        datasets: [{
          data:             [0, 0, 0, 0],
          backgroundColor:  GRADE_COLORS,
          hoverBackgroundColor: GRADE_COLORS.map(c => c + 'cc'),
          borderColor:      'rgba(10,14,26,0.8)',
          borderWidth:      3,
          hoverOffset:      8,
        }],
      },
      options: {
        responsive:        true,
        maintainAspectRatio: false,
        cutout:            '68%',
        animation:         { duration: 600, easing: 'easeInOutQuart' },
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              padding:     16,
              color:       '#8892aa',
              generateLabels(chart) {
                const data    = chart.data;
                const dataset = data.datasets[0];
                const total   = dataset.data.reduce((a, b) => a + b, 0);
                return data.labels.map((label, i) => ({
                  text:         `${label}  ${dataset.data[i]} (${total ? Math.round(dataset.data[i] / total * 100) : 0}%)`,
                  fillStyle:    dataset.backgroundColor[i],
                  strokeStyle:  dataset.backgroundColor[i],
                  lineWidth:    0,
                  hidden:       false,
                  index:        i,
                }));
              },
            },
          },
          tooltip: {
            callbacks: {
              label(ctx) {
                const total   = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct     = total ? (ctx.parsed / total * 100).toFixed(1) : 0;
                return `  ${ctx.label}: ${ctx.parsed} (${pct}%)`;
              },
            },
          },
        },
      },
    });
  }

  /**
   * Update the donut chart with fresh stats from /api/stats/today.
   * @param {{ mentah_count, matang_count, overripe_count, janjang_count }} stats
   */
  function updateDonut(stats) {
    if (!_donutChart) return;
    _donutChart.data.datasets[0].data = [
      stats.mentah_count   || 0,
      stats.matang_count   || 0,
      stats.overripe_count || 0,
      stats.janjang_count  || 0,
    ];
    _donutChart.update('active');
  }

  // ── Throughput Line Chart ──────────────────────────────────────────────────

  function _initThroughput(canvasId) {
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx) return null;

    // Gradient fill under the line
    const gradient = ctx.createLinearGradient(0, 0, 0, 220);
    gradient.addColorStop(0,   'rgba(0,255,157,0.25)');
    gradient.addColorStop(1,   'rgba(0,255,157,0.00)');

    return new Chart(ctx, {
      type: 'line',
      data: {
        labels:   [],
        datasets: [{
          label:            'Bundles/min',
          data:             [],
          borderColor:      '#00ff9d',
          backgroundColor:  gradient,
          borderWidth:      2,
          pointRadius:      3,
          pointBackgroundColor: '#00ff9d',
          pointHoverRadius: 5,
          fill:             true,
          tension:          0.4,
        }],
      },
      options: {
        responsive:           true,
        maintainAspectRatio:  false,
        animation:            { duration: 400 },
        interaction: {
          mode:      'index',
          intersect: false,
        },
        scales: {
          x: {
            grid:  { color: 'rgba(255,255,255,0.04)' },
            ticks: {
              color:        '#5e6272',
              maxTicksLimit: 8,
              callback(val, idx) {
                const label = this.getLabelForValue(val);
                // Show only HH:MM from ISO string
                try {
                  return new Date(label).toLocaleTimeString('id-ID', {
                    hour: '2-digit', minute: '2-digit',
                  });
                } catch { return label; }
              },
            },
          },
          y: {
            beginAtZero: true,
            grid:        { color: 'rgba(255,255,255,0.04)' },
            ticks:       { color: '#5e6272', stepSize: 1 },
            title: {
              display: true,
              text:    'bundles / min',
              color:   '#5e6272',
              font:    { size: 11 },
            },
          },
        },
        plugins: {
          legend:  { display: false },
          tooltip: {
            backgroundColor: 'rgba(10,14,26,0.95)',
            borderColor:     'rgba(0,255,157,0.3)',
            borderWidth:     1,
            padding:         10,
          },
        },
      },
    });
  }

  /**
   * Update throughput chart with API timeseries data.
   * @param {{ bucket: string, count: number }[]} rows
   */
  function updateThroughput(rows) {
    if (!_throughputChart) return;
    _throughputChart.data.labels         = rows.map(r => r.bucket);
    _throughputChart.data.datasets[0].data = rows.map(r => r.count);
    _throughputChart.update('active');
  }

  return {
    init() {
      // ── Shared Chart.js defaults ───────────────────────────────────────────────
      Chart.defaults.color           = '#8892aa';
      Chart.defaults.font.family     = "'Inter', sans-serif";
      Chart.defaults.font.size       = 12;
      Chart.defaults.borderColor     = 'rgba(255,255,255,0.06)';
      Chart.defaults.plugins.legend.labels.boxWidth = 12;

      _donutChart      = _initDonut('donutChart');
      _throughputChart = _initThroughput('throughputChart');
    },
    updateDonut,
    updateThroughput,
  };
})();
