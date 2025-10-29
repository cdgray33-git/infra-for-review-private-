FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY mail_assistant_requirements.txt .
RUN pip install --no-cache-dir -r mail_assistant_requirements.txt

COPY app.py .
COPY tasks.py .
COPY parse_email.py .
COPY server.py .
COPY tools/ /app/tools/
COPY agent_logging.py .
RUN chmod -R +x /app/tools || true

CMD ["gunicorn", "--bind", "0.0.0.0:8002", "server:app"]
