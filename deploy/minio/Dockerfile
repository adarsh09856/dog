FROM debian:bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN set -eux; \
    ARCH="${TARGETARCH:-amd64}"; \
    case "$ARCH" in \
      amd64) MINIO_ARCH="amd64" ;; \
      arm64) MINIO_ARCH="arm64" ;; \
      *) MINIO_ARCH="amd64" ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/minio "https://github.com/minio/minio/releases/download/RELEASE.2025-09-07T16-13-09Z/minio.linux-${MINIO_ARCH}.RELEASE.2025-09-07T16-13-09Z"; \
    chmod +x /usr/local/bin/minio

RUN mkdir -p /data && chmod 777 /data

EXPOSE 9000 9001
VOLUME ["/data"]

ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
