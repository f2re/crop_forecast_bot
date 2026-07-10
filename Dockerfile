FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    HEARTBEAT_FILE=/tmp/crop_forecast_bot/heartbeat

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gdal-bin \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin cropbot

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY . /app

RUN mkdir -p /app/data/cache /app/data/literature /app/logs /tmp/crop_forecast_bot && \
    chown -R cropbot:cropbot /app/data /app/logs /tmp/crop_forecast_bot

USER cropbot

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -m src.ops.heartbeat "${HEARTBEAT_FILE}" --max-age 90

CMD ["python", "-m", "src.bot.main"]
