FROM python:3.11-slim

WORKDIR /app

# install only the Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the backend source
COPY . .

# Cloud Run sets $PORT; FastAPI must bind 0.0.0.0 (uvicorn, not gunicorn — it's ASGI)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
