# Cloud Run container for the advisor API (FastAPI → main:app).
# The frontend (Vite) is deployed separately; this image is the backend only.
FROM python:3.12-slim

# Faster, quieter, no .pyc clutter.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so this layer is cached when only source changes.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App source.
COPY . .

# Cloud Run sends traffic to $PORT (default 8080) and requires 0.0.0.0.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
