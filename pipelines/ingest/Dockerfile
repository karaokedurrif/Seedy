FROM python:3.11-slim

WORKDIR /app

# System deps for trafilatura & pymupdf
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/pipelines/ingest/
# Create __init__.py for pipelines package
RUN touch /app/pipelines/__init__.py

# Dirs
RUN mkdir -p /app/data/raw /app/briefs

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "pipelines.ingest.run_daily"]
