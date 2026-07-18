FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    HOME=/home/browser \
    LANG=ru_RU.UTF-8 \
    LC_ALL=ru_RU.UTF-8 \
    TZ=Europe/Moscow \
    BROWSER_CDP_HOST=127.0.0.1 \
    BROWSER_CDP_PORT=9222 \
    BROWSER_PROFILE_DIR=/data/browser-profile \
    BROWSER_DISPLAY=:99 \
    BROWSER_WINDOW_SIZE=1400,900 \
    BROWSER_LANGUAGE=ru-RU \
    APP_PORT=8095 \
    APP_MODULE=ozon_browser_fetcher.manage:app \
    GUNICORN_WORKERS=1 \
    GUNICORN_THREADS=1 \
    GUNICORN_TIMEOUT=120

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       fonts-liberation \
       fonts-noto-color-emoji \
       fonts-noto-core \
       fonts-noto-cjk \
       locales \
       openbox \
       tini \
       tzdata \
       xvfb \
    && echo "ru_RU.UTF-8 UTF-8" > /etc/locale.gen \
    && locale-gen \
    && curl -fsSL \
       https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
       -o /tmp/google-chrome-stable.deb \
    && apt-get install -y --no-install-recommends \
       /tmp/google-chrome-stable.deb \
    && rm -f /tmp/google-chrome-stable.deb \
    && rm -rf /var/lib/apt/lists/*

COPY ozon_browser_fetcher/requirements.txt ./ozon_browser_fetcher/requirements.txt
RUN pip install --no-cache-dir -r ./ozon_browser_fetcher/requirements.txt

COPY ozon_browser_fetcher ./ozon_browser_fetcher
COPY --chmod=0755 browser_runtime/start_browser_fetcher.sh /usr/local/bin/start-browser-fetcher

RUN sed -i 's/\r$//' /usr/local/bin/start-browser-fetcher && chmod 0755 /usr/local/bin/start-browser-fetcher

RUN useradd --create-home --uid 10001 --shell /bin/bash browser \
    && mkdir -p /data/browser-profile /tmp/browser-runtime \
    && chown -R browser:browser \
       /data/browser-profile \
       /tmp/browser-runtime \
       /home/browser

USER browser

EXPOSE 8095

HEALTHCHECK --interval=20s --timeout=5s --start-period=90s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8095/api/v1/health || exit 1

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/start-browser-fetcher"]
