FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PLAYWRIGHT_BROWSERS_PATH=0 \
    PLAYWRIGHT_HEADLESS=1

WORKDIR /app

COPY requirements.txt ./

RUN apt-get update && apt-get install -y --no-install-recommends \
      libnss3 \
      libatk-bridge2.0-0 \
      libgtk-3-0 \
      libdrm2 \
      libxkbcommon0 \
      libasound2 \
      fonts-liberation \
      libxshmfence1 \
      libgbm1 \
      wget \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

CMD ["python", "api.py"]

