FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    INDIC_PARLER_MODEL_DIR=/models/indic-parler \
    INDIC_PARLER_DESCRIPTION_TOKENIZER_DIR=/models/description-tokenizer \
    INDIC_PARLER_THREADS=2 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2

RUN apt-get update && apt-get install -y --no-install-recommends \
      git libsndfile1 libgomp1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 \
      --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir \
      git+https://github.com/huggingface/parler-tts.git@d108732cd57788ec86bc857d99a6cabd66663d68 \
      fastapi uvicorn soxr numpy accelerate

WORKDIR /app
COPY app.py /app/app.py
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
