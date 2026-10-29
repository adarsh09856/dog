FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface \
    INDUS_MODEL_DIR=/models/indus-pocket-tts \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "torch==2.14.1+cpu" --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
       "pocket-tts @ git+https://github.com/kyutai-labs/pocket-tts@0c2db3b" \
       "fastapi==0.158.1" "uvicorn==0.54.0" "huggingface_hub==2.2.0" \
       "safetensors==0.8.0" "sentencepiece==0.2.2"

COPY app.py /app/app.py

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
