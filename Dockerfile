# Cloud Run container for the advisor API (FastAPI → main:app).
# The frontend is a separate image; see Dockerfile.frontend.
FROM python:3.12-slim

# Faster, quieter, no .pyc clutter.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so this layer is cached when only source changes.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy only what the API actually imports or reads. Explicit rather than `COPY . .`
# because the build context is now shared with the frontend image, so the ignore
# file can no longer be the thing that keeps the frontend's sources out of here.
#   public/ is required, not optional: settings.data_file defaults to
#   public/data.json and the advisor is grounded on it.
COPY main.py ./
COPY advisor ./advisor
COPY public ./public

# Drop root. The app writes only advisor/.news_cache.json, so that one path needs
# to stay writable by the runtime user.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app/advisor
USER appuser

# Cloud Run sends traffic to $PORT (default 8080) and requires 0.0.0.0.
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
