FROM python:3.11-slim

WORKDIR /app

# System deps (incluye libgl para OpenCV/YOLO)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libgl1 libglib2.0-0 \
    fonts-dejavu-core \
    libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 \
    libcairo2 libgdk-pixbuf-xlib-2.0-0 libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=120 -r requirements.txt

# App code
COPY . .

EXPOSE 8000

# SIN --reload: evita spawn de worker hijo que crece a 5GB+ RAM
# Para desarrollo, reiniciar con: docker restart seedy-backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-keep-alive", "30"]
