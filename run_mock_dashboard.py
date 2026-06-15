#!/usr/bin/env python3
"""
run_mock_dashboard.py
Mock Server for testing the Edge AI Palm Oil FFB Grading System Web Dashboard.

Hosts the frontend static files and serves mock dynamic API endpoints on port 8080.
No external dependencies required (uses built-in standard library).

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

# ── Global Simulation State ──────────────────────────────────────────────────
start_time = datetime.now(timezone.utc)
total_scanned = 248
mentah_count = 38
matang_count = 175
overripe_count = 27
janjang_count = 8
anomaly_count = 11
total_confidence = 248 * 88.5  # avg confidence around 88.5%
scan_counter = 248

def generate_random_scan(scan_num):
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
        "image_url": img_map.get(grade, 'img/camera_placeholder.png')
    }

# Start with some historical recent scans
recent_scans = []
for i in range(scan_counter - 10, scan_counter + 1):
    # space scans slightly apart in time
    scan = generate_random_scan(i)
    scan_time = datetime.now(timezone.utc) - timedelta(seconds=(scan_counter - i) * 15)
    scan["event_time"] = scan_time.isoformat()
    recent_scans.insert(0, scan)

last_sim_time = time.time()

def update_simulation():
    global last_sim_time, scan_counter, total_scanned, mentah_count
    global matang_count, overripe_count, janjang_count, anomaly_count
    global total_confidence
    
    now = time.time()
    elapsed = now - last_sim_time
    
    # Simulate a new scan every 8 to 15 seconds
    if elapsed > random.randint(8, 15):
        last_sim_time = now
        scan_counter += 1
        scan = generate_random_scan(scan_counter)
        recent_scans.insert(0, scan)
        if len(recent_scans) > 50:
            recent_scans.pop()
            
        total_scanned += 1
        g = scan["grade"]
        if g == 0:
            mentah_count += 1
        elif g == 1:
            matang_count += 1
        elif g == 2:
            overripe_count += 1
        elif g == 3:
            janjang_count += 1
            
        if scan["is_anomaly"]:
            anomaly_count += 1
            
        total_confidence += scan["confidence_pct"]
        print(f"[SIMULATOR] New Scan #{scan_counter}: Grade={scan['grade_name']} ({scan['confidence_pct']}%)")


# ── Mock Request Handler ─────────────────────────────────────────────────────
class MockAPIHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Route API requests
        if self.path.startswith('/api/'):
            self.handle_api()
        else:
            # Serve static files from the dashboard frontend folder
            super().do_GET()

    def translate_path(self, path):
        # Maps web root to the project's actual web dashboard folder
        root_dir = os.path.join(os.getcwd(), '5_web_dashboard', 'frontend')
        
        # Parse path (strip queries)
        clean_path = path.split('?', 1)[0].split('#', 1)[0]
        relative_path = clean_path.lstrip('/')
        
        if not relative_path:
            relative_path = 'index.html'
            
        return os.path.join(root_dir, relative_path)

    def handle_api(self):
        # Parse query params
        clean_path = self.path.split('?', 1)[0]
        response_data = {}
        
        if clean_path == '/api/stats/today':
            update_simulation()
            avg_conf = round(total_confidence / total_scanned, 1) if total_scanned > 0 else 0.0
            matang_rate = round(100.0 * matang_count / total_scanned, 1) if total_scanned > 0 else 0.0
            response_data = {
                "total_scanned": total_scanned,
                "mentah_count": mentah_count,
                "matang_count": matang_count,
                "overripe_count": overripe_count,
                "janjang_count": janjang_count,
                "anomaly_count": anomaly_count,
                "avg_confidence": avg_conf,
                "matang_rate_pct": matang_rate
            }
            
        elif clean_path == '/api/events/recent':
            update_simulation()
            response_data = recent_scans
            
        elif clean_path == '/api/trend/throughput':
            update_simulation()
            now = datetime.now(timezone.utc)
            trend = []
            for i in range(30):
                bucket_time = now - timedelta(minutes=30-i)
                count = random.randint(6, 14)
                trend.append({
                    "bucket": bucket_time.replace(second=0, microsecond=0).isoformat(),
                    "count": count
                })
            response_data = trend
            
        elif clean_path == '/api/trend/grades':
            update_simulation()
            now = datetime.now(timezone.utc)
            grades_trend = []
            for i in range(24):
                bucket_time = now - timedelta(hours=24-i)
                grades_trend.append({
                    "bucket": bucket_time.replace(minute=0, second=0, microsecond=0).isoformat(),
                    "mentah": random.randint(10, 20),
                    "matang": random.randint(50, 75),
                    "overripe": random.randint(5, 12),
                    "janjang_kosong": random.randint(0, 4)
                })
            response_data = grades_trend
            
        elif clean_path == '/api/gateway/status':
            update_simulation()
            response_data = {
                "event_time": datetime.now(timezone.utc).isoformat(),
                "gateway_id": "ESP_TBS_GW_001",
                "status": "online",
                "ip_address": "192.168.1.105",
                "wifi_rssi_dbm": random.randint(-68, -58),
                "lora_status": "active",
                "uptime_sec": int(time.time() - start_time.timestamp()),
                "total_scans": total_scanned,
                "stale": False,
                "age_sec": 0
            }
        else:
            response_data = {"error": "Not Found", "path": clean_path}
            
        encoded_response = json.dumps(response_data).encode('utf-8')
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(encoded_response)))
        self.end_headers()
        
        self.wfile.write(encoded_response)


# ── Run Server ────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Adjust CWD to root directory if executed from subfolder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print("=" * 60)
    print("      TBS GRADER WEB DASHBOARD MOCK SERVER")
    print("=" * 60)
    print(f"Server starting on http://localhost:{PORT}")
    print("Serving static files from: 5_web_dashboard/frontend/")
    print("Serving mock database REST APIs under /api/*")
    print("Live belt scan simulation active (adds new scan every ~10s)")
    print("-" * 60)
    print("Press Ctrl+C to stop the server.")
    
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), MockAPIHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped. Goodbye!")
            sys.exit(0)
