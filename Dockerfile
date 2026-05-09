FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Static assets collected at build time
RUN DJANGO_SECRET_KEY=build SECRET_KEY=build DEBUG=False \
    python manage.py collectstatic --noinput || true

EXPOSE 8000

# Gunicorn:
# - 2 workers + 4 threads (gthread): mejor concurrencia que sync en VPS de 1 CPU.
# - --preload: comparte el código cargado entre workers (ahorra RAM y mejora cold starts).
# - --keepalive 5: reusa conexiones nginx → gunicorn (5s) en lugar de cerrar+abrir.
# - --max-requests/--max-requests-jitter: recicla workers para evitar memory leaks.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--preload", "--keepalive", "5", "--max-requests", "1000", "--max-requests-jitter", "100", "--access-logfile", "-", "--error-logfile", "-"]
