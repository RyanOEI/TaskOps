FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=run:app \
    GUNICORN_BIND=0.0.0.0:5000

WORKDIR /app

# Instalasi paket sistem minimum untuk build psycopg2 / cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Salin dan instal dependensi Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Buat pengguna non-root appuser dan pastikan direktori instance tersedia dengan hak akses yang tepat
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/instance && \
    chown -R appuser:appuser /app

# Salin seluruh file proyek dengan hak milik appuser
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 5000

CMD ["sh", "-c", "flask db upgrade && gunicorn --bind ${GUNICORN_BIND} --workers 2 --threads 4 run:app"]

