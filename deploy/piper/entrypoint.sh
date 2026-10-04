#!/usr/bin/env bash
set -e

DEFAULT_VOICE=${DEFAULT_MODEL:-"hi_IN-priyamvada-medium"}
DATA_DIR=${DATA_DIR:-"/data"}

mkdir -p "$DATA_DIR"

# Download default voice if not present
if [ ! -f "$DATA_DIR/$DEFAULT_VOICE.onnx" ]; then
    echo "Downloading default voice: $DEFAULT_VOICE into $DATA_DIR..."
    python -m piper.download_voices --data-dir "$DATA_DIR" "$DEFAULT_VOICE" || true
fi

# Ensure English starter voices are present
if [ ! -f "$DATA_DIR/en_US-lessac-medium.onnx" ]; then
    echo "Downloading en_US-lessac-medium into $DATA_DIR..."
    python -m piper.download_voices --data-dir "$DATA_DIR" "en_US-lessac-medium" || true
fi

if [ ! -f "$DATA_DIR/en_GB-alan-medium.onnx" ]; then
    echo "Downloading en_GB-alan-medium into $DATA_DIR..."
    python -m piper.download_voices --data-dir "$DATA_DIR" "en_GB-alan-medium" || true
fi

echo "Starting Piper HTTP Server on 0.0.0.0:5000 with model $DATA_DIR/$DEFAULT_VOICE.onnx..."
exec python -m piper.http_server --model "$DATA_DIR/$DEFAULT_VOICE.onnx" --data-dir "$DATA_DIR" --host 0.0.0.0 --port 5000
