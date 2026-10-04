FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Piper TTS with HTTP server (OHF-Voice/piper1-gpl 1.8.0 release)
RUN pip install --no-cache-dir "piper-tts[http]==1.8.0"

# Create voice data directory
RUN mkdir -p /data /app

WORKDIR /app

# Copy entrypoint script
COPY deploy/piper/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Pre-download starter voices for instant startup (Hindi Priyamvada, US English Lessac, UK English Alan)
RUN python -m piper.download_voices --data-dir /data hi_IN-priyamvada-medium || true
RUN python -m piper.download_voices --data-dir /data en_US-lessac-medium || true
RUN python -m piper.download_voices --data-dir /data en_GB-alan-medium || true

EXPOSE 5000

ENV DATA_DIR=/data
ENV DEFAULT_MODEL=hi_IN-priyamvada-medium

ENTRYPOINT ["/app/entrypoint.sh"]
