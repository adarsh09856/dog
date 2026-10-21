FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 HF_HOME=/models/huggingface
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn sherpa-onnx==1.13.8 huggingface_hub numpy
COPY app.py NOTICE.md /app/
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
