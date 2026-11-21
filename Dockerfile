FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    KAS_DATA_DIR=/data \
    KAS_CONFIG_DIR=/config \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      tesseract-ocr \
      tesseract-ocr-vie \
      tesseract-ocr-eng \
      poppler-utils \
      p7zip-full \
      fonts-dejavu-core \
      git \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY docs/ ./docs/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[drive-api,media,web]" \
    && mkdir -p /data /config /vaults

VOLUME ["/data", "/config", "/vaults"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)"

CMD ["kas", "ui", "--host", "0.0.0.0", "--port", "8765"]
