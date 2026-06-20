#!/usr/bin/env python3
"""
usb_serial_bridge.py
Bridge script to connect MAX78000FTHR directly to the PC/Web Dashboard via USB.
Bypasses the ESP-12E gateway module (no soldering required).

Reads from the serial port (USB debug port or FTDI UART) and publishes to MQTT.

Requirements:
  pip install pyserial paho-mqtt

Usage:
  python usb_serial_bridge.py --port /dev/ttyACM0 --mode debug
  python usb_serial_bridge.py --port COM3 --mode debug
"""

import sys
import time
import json
import re
import argparse
import threading
import serial
import paho.mqtt.client as mqtt

# ── Configuration Defaults ───────────────────────────────────────────────────
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_RESULT = "pks/grading/tbs/result"
MQTT_TOPIC_STATUS = "pks/grading/tbs/status"
MQTT_CLIENT_ID = "PC_SERIAL_BRIDGE"
MQTT_USER = "iot_gateway"
MQTT_PASSWORD = "secure_mqtt_pass"

# ── Regex parser for MAX78000 USB printf logs (Mode: debug) ──────────────────
# Example log:
# [MAIN] === SCAN #42 COMPLETE | Grade=1 (Matang) | Confidence=94% ===
DEBUG_LOG_PATTERN = re.compile(
    r"SCAN\s+#(\d+)\s+COMPLETE\s*\|\s*Grade=(\d+)\s*"
    r"\((.*?)\)\s*\|\s*Confidence=(\d+)%"
)


def parse_args():
    """Parse command-line arguments for the serial bridge."""
    parser = argparse.ArgumentParser(
        description="MAX78000FTHR to MQTT Serial Bridge"
    )
    parser.add_argument(
        "-p",
        "--port",
        required=True,
        help="Serial port (e.g. /dev/ttyACM0, /dev/ttyUSB0, COM3)"
    )
    parser.add_argument(
        "-b", "--baud",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)"
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["debug", "raw"],
        default="debug",
        help=(
            "Bridge mode: "
            "'debug' to parse USB console logs (printf), "
            "'raw' to parse raw UART0 JSON lines"
        )
    )
    parser.add_argument(
        "--host",
        default=MQTT_BROKER,
        help=f"MQTT broker hostname/IP (default: {MQTT_BROKER})"
    )
    parser.add_argument(
        "--auto-scan",
        type=float,
        default=0,
        metavar="SECONDS",
        help=(
            "Auto-trigger scan every N seconds "
            "(0 = disabled, keyboard only)"
        )
    )
    return parser.parse_args()


def main():
    """Run the serial to MQTT bridge daemon."""
    args = parse_args()

    print("=" * 60)
    print("        MAX78000FTHR USB-SERIAL TO MQTT BRIDGE")
    print("=" * 60)
    print(f"Serial Port: {args.port} ({args.baud} baud)")
    print(f"Bridge Mode: {args.mode.upper()}")
    print(f"MQTT Broker: {args.host}:{MQTT_PORT}")
    if args.auto_scan > 0:
        print(f"Auto-Scan:   every {args.auto_scan}s")
    else:
        print("Keyboard:    press 's' + Enter to trigger scan remotely")
    print("-" * 60)

    # ── Initialize MQTT Client ───────────────────────────────────────────────
    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    try:
        mqtt_client.connect(args.host, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        print("[MQTT] Connected to broker successfully.")

        # Publish online status for the bridge
        status_payload = {
            "status": "online",
            "uptime": 0,
            "ip": "127.0.0.1",
            "rssi": -30,
            "scans": 0,
            "lora": "disabled (bridge)"
        }
        mqtt_client.publish(
            MQTT_TOPIC_STATUS,
            json.dumps(status_payload),
            qos=0,
            retain=True
        )
    except Exception as e:  # pylint: disable=broad-except
        print(f"[MQTT] ERROR: Connection failed: {e}")
        print("Make sure Mosquitto is running (e.g. docker-compose up -d).")
        sys.exit(1)

    # ── Open Serial Port ─────────────────────────────────────────────────────
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1.0)
        # Flush buffers
        ser.reset_input_buffer()
        print(f"[SERIAL] Successfully opened {args.port}.")
        print("Listening for FFB scan triggers...")
        print("Press Ctrl+C to stop the bridge.")
        print("-" * 60)
    except serial.SerialException as e:
        print(f"[SERIAL] ERROR: Could not open port: {e}")
        mqtt_client.loop_stop()
        sys.exit(1)

    # ── Background Trigger Threads ───────────────────────────────────────────
    stop_event = threading.Event()

    def keyboard_trigger_thread():
        """Listen for 's' + Enter in this terminal to send SCAN to board."""
        while not stop_event.is_set():
            try:
                cmd = input()
                if cmd.strip().lower() == 's':
                    ser.write(b"SCAN\n")
                    print("[BRIDGE] >>> SCAN command sent to board!")
            except (EOFError, OSError):
                break

    def auto_scan_thread(interval_sec):
        """Automatically send SCAN every interval_sec seconds."""
        print(f"[BRIDGE] Auto-scan active: sending SCAN every {interval_sec}s")
        while not stop_event.is_set():
            time.sleep(interval_sec)
            if not stop_event.is_set():
                ser.write(b"SCAN\n")
                print("[BRIDGE] >>> Auto-SCAN sent!")

    # Start keyboard listener thread (always active)
    kb_thread = threading.Thread(target=keyboard_trigger_thread, daemon=True)
    kb_thread.start()

    # Start auto-scan thread only if --auto-scan flag is set
    if args.auto_scan > 0:
        as_thread = threading.Thread(
            target=auto_scan_thread, args=(args.auto_scan,), daemon=True
        )
        as_thread.start()

    try:
        while True:
            if not ser.is_open:
                print(
                    "[SERIAL] Port closed unexpectedly. "
                    "Retrying connection..."
                )
                time.sleep(2)
                try:
                    ser.open()
                    continue
                except serial.SerialException:
                    continue

            try:
                line_bytes = ser.readline()
                if not line_bytes:
                    continue

                line = line_bytes.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                # Print debug line to terminal so user sees what is happening
                print(f"[SERIAL OUT] {line}")

                grade = None
                confidence = None
                scan_count = 0

                # ── Mode A: Parsing standard printf console logs ─────────────
                if args.mode == "debug":
                    match = DEBUG_LOG_PATTERN.search(line)
                    if match:
                        scan_count = int(match.group(1))
                        grade = int(match.group(2))
                        grade_name = match.group(3)
                        confidence = int(match.group(4))
                        print(
                            f"\n>>> [PARSED SCAN #{scan_count}] "
                            f"Grade={grade} ({grade_name}) | "
                            f"Confidence={confidence}%"
                        )

                # ── Mode B: Parsing raw JSON from UART0 (FTDI bridge) ────────
                elif args.mode == "raw":
                    # Looks like: {"g":1,"c":94}
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            data = json.loads(line)
                            if "g" in data and "c" in data:
                                grade = int(data["g"])
                                confidence = int(data["c"])
                                scan_count = data.get("cnt", 1)
                                print(
                                    f"\n>>> [PARSED RAW] Grade={grade} | "
                                    f"Confidence={confidence}%"
                                )
                        except ValueError:
                            pass

                # ── Publish Result if parsed successfully ────────────────────
                if grade is not None and confidence is not None:
                    # Construct matching ESP-12E gateway format
                    payload = {
                        "g": grade,
                        "c": confidence,
                        "ts": int(time.time() * 1000),
                        "cnt": scan_count
                    }

                    mqtt_client.publish(
                        MQTT_TOPIC_RESULT,
                        json.dumps(payload),
                        qos=1
                    )
                    print(
                        f"[MQTT PUBLISH] Sent to {MQTT_TOPIC_RESULT}: "
                        f"{payload}\n"
                    )

            except serial.SerialException as e:
                print(f"[SERIAL] Error reading data: {e}")
                time.sleep(1)
            except UnicodeDecodeError:
                pass

    except KeyboardInterrupt:
        print("\nStopping serial bridge...")
        stop_event.set()
    finally:
        if ser.is_open:
            ser.close()

        # Publish offline status
        status_payload = {"status": "offline", "reason": "user_terminated"}
        mqtt_client.publish(
            MQTT_TOPIC_STATUS,
            json.dumps(status_payload),
            qos=0,
            retain=True
        )

        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("Bridge stopped. Goodbye!")


if __name__ == "__main__":
    main()
