FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY build_xray_config.py /app/build_xray_config.py

ENTRYPOINT ["python", "/app/build_xray_config.py"]