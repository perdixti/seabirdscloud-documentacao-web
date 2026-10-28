FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SEABIRDS_DATA_DIR=/data \
    SEABIRDS_HOST=0.0.0.0 \
    HOME=/data
WORKDIR /app
COPY requirements.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client ca-certificates passwd \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.lock \
    && groupadd --gid 10001 seabirds \
    && useradd --uid 10001 --gid seabirds --home-dir /data --no-create-home seabirds \
    && mkdir /data /workspace && chown seabirds:seabirds /data /workspace
COPY seabirds ./seabirds
USER seabirds
VOLUME ["/data", "/workspace"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]
CMD ["python", "-m", "seabirds"]
