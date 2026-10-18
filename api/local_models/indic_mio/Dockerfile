FROM python:3.11-slim AS builder

ARG SPEECH_CORE_REVISION=a15d2e4de7d3c3ceb2297f593c232e5c82132fb0
ARG LITERT_VERSION=2.1.5
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential cmake git unzip \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /tmp/litert /tmp/wheel \
    && python -m pip download --no-deps --only-binary=:all: \
       --dest /tmp/wheel "ai-edge-litert==${LITERT_VERSION}" \
    && python -c "import glob,zipfile; z=zipfile.ZipFile(glob.glob('/tmp/wheel/*.whl')[0]); n=next(x for x in z.namelist() if x.endswith('/libLiteRt.so')); z.extract(n,'/tmp/litert'); import shutil,os; shutil.copy('/tmp/litert/'+n,'/tmp/litert/libLiteRt.so')" \
    && git init /tmp/speech-core \
    && git -C /tmp/speech-core remote add origin https://github.com/soniqo/speech-core.git \
    && git -C /tmp/speech-core fetch --depth 1 origin "${SPEECH_CORE_REVISION}" \
    && git -C /tmp/speech-core checkout --detach FETCH_HEAD

RUN cmake -S /tmp/speech-core -B /tmp/speech-core-build \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=ON \
      -DSPEECH_CORE_WITH_LITERT=ON \
      -DSPEECH_CORE_BUILD_TESTS=OFF \
      -DLITERT_DIR=/tmp/litert \
    && cmake --build /tmp/speech-core-build --target speech_core_models_litert -j1 \
    && mkdir -p /opt/speech-core /opt/litert \
    && find /tmp/speech-core-build -type f \( -name 'libspeech_core.so' -o -name 'libspeech_core_models_litert.so' \) -exec cp {} /opt/speech-core/ \; \
    && cp /tmp/litert/libLiteRt.so /opt/litert/

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/models/huggingface \
    INDIC_MIO_MODEL_DIR=/models/indic-mio \
    LD_LIBRARY_PATH=/opt/speech-core:/opt/litert \
    OMP_NUM_THREADS=2 \
    TFLITE_NUM_THREADS=2

RUN apt-get update \
    && apt-get install -y --no-install-recommends libstdc++6 libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /opt/speech-core /opt/speech-core
COPY --from=builder /opt/litert /opt/litert
RUN pip install --no-cache-dir fastapi uvicorn huggingface_hub numpy
COPY app.py /app/app.py

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
