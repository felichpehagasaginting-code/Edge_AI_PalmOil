#!/usr/bin/env python3
"""Mock Server for the Edge AI Palm Oil FFB Grading System Dashboard.

Hosts the frontend static files and serves mock dynamic API
endpoints on port 8080. No external dependencies required.

Usage:
  python run_mock_dashboard.py
  Then open http://localhost:8080/ in your browser.
"""

import os
import sys
import http.server
import socketserver
import json
import random
import time
from datetime import datetime, timedelta, timezone

PORT = 8080

# ── Global Simulation State ─────────────────────────────────────
START_TIME = datetime.now(timezone.utc)


class SimState:
    """Mutable simulation state container."""

    total_scanned = 248
    mentah_count = 38
    matang_count = 175
    overripe_count = 27
    janjang_count = 8
    anomaly_count = 11
    total_confidence = 248 * 88.5  # avg confidence ~88.5%
    scan_counter = 248
    last_sim_time = time.time()
    recent_scans = []


def generate_random_scan(scan_num):
    """Generate a simulated FFB grading scan result."""
    grade_prob = random.random()
    if grade_prob < 0.70:
        grade = 1
        grade_name = "Matang"
        confidence = random.randint(85, 99)
    elif grade_prob < 0.85:
        grade = 0
        grade_name = "Mentah"
        confidence = random.randint(70, 94)
    elif grade_prob < 0.95:
        grade = 2
        grade_name = "Overripe"
        confidence = random.randint(65, 89)
    else:
        grade = 3
        grade_name = "Janjang Kosong"
        confidence = random.randint(75, 95)

    is_anomaly = grade == 3 or confidence < 60

    img_map = {
        0: 'img/unripe_bunch.png',
        1: 'img/ripe_bunch.png',
        2: 'img/overripe_bunch.png',
        3: 'img/empty_bunch.png'
    }

    return {
        "event_time": datetime.now(timezone.utc).isoformat(),
        "grade": grade,
        "grade_name": grade_name,
        "confidence_pct": confidence,
        "is_anomaly": is_anomaly,
        "transport": random.choice(["wi-fi", "lora"]),
        "scan_count": scan_num,
        "image_url": img_map.get(
            grade, 'img/camera_placeholder.png'
        )
    }


# Start with some historical recent scans
for _idx in range(
    SimState.scan_counter - 10, SimState.scan_counter + 1
):
    _scan = generate_random_scan(_idx)
    _scan_time = (
        datetime.now(timezone.utc)
        - timedelta(seconds=(SimState.scan_counter - _idx) * 15)
    )
    _scan["event_time"] = _scan_time.isoformat()
    SimState.recent_scans.insert(0, _scan)


def update_simulation():
    """Advance the simulation.

    Generates a new scan if enough time has passed.
    """
    now = time.time()
    elapsed = now - SimState.last_sim_time

    # Simulate a new scan every 8 to 15 seconds
    if elapsed > random.randint(8, 15):
        SimState.last_sim_time = now
        SimState.scan_counter += 1
        scan = generate_random_scan(SimState.scan_counter)
        SimState.recent_scans.insert(0, scan)
        if len(SimState.recent_scans) > 50:
            SimState.recent_scans.pop()

        SimState.total_scanned += 1
        g = scan["grade"]
        if g == 0:
            SimState.mentah_count += 1
        elif g == 1:
            SimState.matang_count += 1
        elif g == 2:
            SimState.overripe_count += 1
        elif g == 3:
            SimState.janjang_count += 1

        if scan["is_anomaly"]:
            SimState.anomaly_count += 1

        SimState.total_confidence += scan["confidence_pct"]
        print(
            f"[SIMULATOR] New Scan "
            f"#{SimState.scan_counter}: "
            f"Grade={scan['grade_name']} "
            f"({scan['confidence_pct']}%)"
        )


# ── Mock Request Handler ────────────────────────────────────────


class MockAPIHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that serves static files and mock API endpoints."""

    def do_GET(self):
        """Route API requests vs static file requests."""
        # Route API requests
        if self.path.startswith('/api/'):
            self.handle_api()
        else:
            # Serve static files from the dashboard frontend folder
            super().do_GET()

    def translate_path(self, path):
        """Map web root to the project's web dashboard folder."""
        root_dir = os.path.join(
            os.getcwd(), '5_web_dashboard', 'frontend'
        )

        # Parse path (strip queries)
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        relative_path = clean_path.lstrip('/')

        if not relative_path:
            relative_path = 'index.html'

        return os.path.join(root_dir, relative_path)

    def handle_api(self):
        """Dispatch API requests and return JSON responses."""
        # Parse query params
        clean_path = self.path.split('?', 1)[0]
        response_data = {}

        if clean_path == '/api/stats/today':
            update_simulation()
            ts = SimState.total_scanned
            avg_conf = (
                round(SimState.total_confidence / ts, 1)
                if ts > 0 else 0.0
            )
            matang_rate = (
                round(100.0 * SimState.matang_count / ts, 1)
                if ts > 0 else 0.0
            )
            response_data = {
                "total_scanned": ts,
                "mentah_count": SimState.mentah_count,
                "matang_count": SimState.matang_count,
                "overripe_count": SimState.overripe_count,
                "janjang_count": SimState.janjang_count,
                "anomaly_count": SimState.anomaly_count,
                "avg_confidence": avg_conf,
                "matang_rate_pct": matang_rate
            }

        elif clean_path == '/api/events/recent':
            update_simulation()
            response_data = SimState.recent_scans

        elif clean_path == '/api/trend/throughput':
            update_simulation()
            now = datetime.now(timezone.utc)
            trend = []
            for idx in range(30):
                bucket_time = now - timedelta(minutes=30 - idx)
                count = random.randint(6, 14)
                trend.append({
                    "bucket": bucket_time.replace(
                        second=0, microsecond=0
                    ).isoformat(),
                    "count": count
                })
            response_data = trend

        elif clean_path == '/api/trend/grades':
            update_simulation()
            now = datetime.now(timezone.utc)
            grades_trend = []
            for idx in range(24):
                bucket_time = now - timedelta(hours=24 - idx)
                grades_trend.append({
                    "bucket": bucket_time.replace(
                        minute=0, second=0, microsecond=0
                    ).isoformat(),
                    "mentah": random.randint(10, 20),
                    "matang": random.randint(50, 75),
                    "overripe": random.randint(5, 12),
                    "janjang_kosong": random.randint(0, 4)
                })
            response_data = grades_trend

        elif clean_path == '/api/gateway/status':
            update_simulation()
            uptime = int(
                time.time() - START_TIME.timestamp()
            )
            response_data = {
                "event_time": (
                    datetime.now(timezone.utc).isoformat()
                ),
                "gateway_id": "ESP_TBS_GW_001",
                "status": "online",
                "ip_address": "192.168.1.105",
                "wifi_rssi_dbm": random.randint(-68, -58),
                "lora_status": "active",
                "uptime_sec": uptime,
                "total_scans": SimState.total_scanned,
                "stale": False,
                "age_sec": 0
            }
        else:
            response_data = {
                "error": "Not Found",
                "path": clean_path
            }

        encoded_response = json.dumps(
            response_data
        ).encode('utf-8')

        self.send_response(200)
        self.send_header(
            'Content-Type', 'application/json'
        )
        self.send_header(
            'Access-Control-Allow-Origin', '*'
        )
        self.send_header(
            'Content-Length', str(len(encoded_response))
        )
        self.end_headers()

        self.wfile.write(encoded_response)


# ── Run Server ──────────────────────────────────────────────────
if __name__ == '__main__':
    # Adjust CWD to root directory if executed from subfolder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print("=" * 60)
    print("      TBS GRADER WEB DASHBOARD MOCK SERVER")
    print("=" * 60)
    print(f"Server starting on http://localhost:{PORT}")
    print(
        "Serving static files from: "
        "5_web_dashboard/frontend/"
    )
    print("Serving mock database REST APIs under /api/*")
    print(
        "Live belt scan simulation active "
        "(adds new scan every ~10s)"
    )
    print("-" * 60)
    print("Press Ctrl+C to stop the server.")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(
        ("", PORT), MockAPIHandler
    ) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped. Goodbye!")
            sys.exit(0)
