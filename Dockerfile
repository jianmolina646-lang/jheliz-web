FROM python:3.12-slim
RUN apt-get update && apt-get dist-upgrade -y && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl gettext \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN python -m pip install --no-cache-dir --upgrade "setuptools>=78.1.1" "msgpack>=1.2.1"
RUN rm -rf /root/.cache/pip /tmp/*

COPY . .

# Static assets collected at build time
RUN DJANGO_SECRET_KEY=build SECRET_KEY=build DEBUG=False \
    python manage.py collectstatic --noinput || true

# Compilar traducciones (.po → .mo) si gettext está disponible.
RUN DJANGO_SECRET_KEY=build SECRET_KEY=build DEBUG=False \
    python manage.py compilemessages || true

# El proceso de producción usa el UID/GID sin privilegios definido en Compose.
RUN groupadd --gid 1000 app \
 && useradd --uid 1000 --gid 1000 --create-home app \
 && chown -R app:app /app

EXPOSE 8000

# Gunicorn:
# - 2 workers + 4 threads (gthread): mejor concurrencia que sync en VPS de 1 CPU.
# - --preload: comparte el código cargado entre workers (ahorra RAM y mejora cold starts).
# - --keepalive 5: reusa conexiones nginx → gunicorn (5s) en lugar de cerrar+abrir.
# - --max-requests/--max-requests-jitter: recicla workers para evitar memory leaks.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "--preload", "--keepalive", "5", "--max-requests", "1000", "--max-requests-jitter", "100", "--access-logfile", "-", "--error-logfile", "-"]
