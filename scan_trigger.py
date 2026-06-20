#!/usr/bin/env python3
"""scan_trigger.py — Trigger FFB Scan via USB serial command."""

import sys
import time
import serial

PORT = '/dev/ttyACM1'
BAUD = 115200

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else PORT
    baud = 115200
    
    print(f"Connecting to MAX78000FTHR on {port}...")
    try:
        with serial.Serial(port, baud, timeout=1) as ser:
            time.sleep(0.1)  # Short delay to let connection settle
            ser.write(b'SCAN\n')
            print(f"[SUCCESS] SCAN command sent to {port}")
    except Exception as e:
        print(f"[ERROR] Failed to send SCAN command: {e}")
        print("Please check if the port is correct and not occupied by another process (e.g. usb_serial_bridge.py).")
        sys.exit(1)

if __name__ == '__main__':
    main()
