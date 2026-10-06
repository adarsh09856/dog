FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl wget && \
    rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN set -eux; \
    ARCH="${TARGETARCH:-amd64}"; \
    case "$ARCH" in \
      amd64) MINIO_ARCH="amd64" ;; \
      arm64) MINIO_ARCH="arm64" ;; \
      *) MINIO_ARCH="amd64" ;; \
    esac; \
    MINIO_URL="https://github.com/minio/minio/releases/download/RELEASE.2025-09-07T16-13-09Z/minio.linux-${MINIO_ARCH}.RELEASE.2025-09-07T16-13-09Z"; \
    (wget -q --tries=5 --timeout=30 -O /usr/local/bin/minio "$MINIO_URL" || \
     curl --http1.1 --tlsv1.2 -fsSL --retry 5 --retry-connrefused -o /usr/local/bin/minio "$MINIO_URL"); \
    chmod +x /usr/local/bin/minio

RUN mkdir -p /data && chmod 777 /data

EXPOSE 9000 9001
VOLUME ["/data"]

ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
