###############################################################################
# FILE: mqtt_to_db/Dockerfile
# PROJECT: Edge AI Palm Oil FFB (TBS) Grading System — Server Backend
# DESCRIPTION:
#   Multi-stage Docker build for the mqtt_to_db Python daemon.
#   Uses a minimal Python slim base to reduce image size.
###############################################################################

FROM python:3.11-slim AS base

# Metadata labels
LABEL maintainer="IoT_Grad_Scanner"
LABEL description="MQTT to TimescaleDB bridge daemon for TBS FFB grading data"

# Set working directory
WORKDIR /app

# Copy dependency list first (leverages Docker layer caching)
COPY requirements.txt .

# Install Python dependencies (no cache to minimize image size)
RUN pip install --no-cache-dir -r requirements.txt

# Copy daemon script
COPY mqtt_to_db.py .

# Run as non-root user for security
RUN useradd --no-create-home --shell /bin/false daemon_user
USER daemon_user

# Start the daemon
CMD ["python", "-u", "mqtt_to_db.py"]
