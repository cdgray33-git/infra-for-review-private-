FROM python:3.11-slim

ARG PUID=1000
ARG PGID=1000

WORKDIR /app

RUN groupadd -g ${PGID} appgroup && \
    useradd -m -u ${PUID} -g ${PGID} appuser

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/config && chown appuser:appgroup /app/config && chmod 700 /app/config

USER appuser

HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1

CMD ["python3", "health_server.py"]
