FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STORAGE_DATA_DIR=/data \
    ASTORAGE_CONFIG_DIR=/config \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-vie \
    poppler-utils \
    p7zip-full \
    fonts-dejavu-core \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY docs ./docs

RUN pip install --upgrade pip && \
    pip install ".[media,web,drive-api]" && \
    mkdir -p /data /config

VOLUME ["/data", "/config"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)" || exit 1

ENTRYPOINT ["astorage"]
CMD ["ui", "--host", "0.0.0.0", "--port", "8765"]
