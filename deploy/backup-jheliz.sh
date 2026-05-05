#!/bin/bash
# Backup completo del deploy de jheliz-web:
#   1. Dump de la DB Postgres (schema + datos).
#   2. Tarball del directorio `media/` (comprobantes Yape, imágenes
#      del catálogo, archivos subidos por usuarios).
#   3. Snapshot del `.env` (cifrado opcionalmente con gpg si está
#      disponible) para poder restaurar la app desde cero.
#
# El resultado es un único `.tar.gz` con timestamp en /var/backups/jheliz/.
# Pensado para correr desde cron como root.
#
# Uso (cron): 0 3 * * * /srv/jheliz/deploy/backup-jheliz.sh >> /var/log/jheliz-backup.log 2>&1
#
# Variables de entorno opcionales:
#   BACKUP_DIR           dónde dejar el .tar.gz   (default: /var/backups/jheliz)
#   COMPOSE_DIR          dónde está docker-compose.yml (default: /srv/jheliz)
#   POSTGRES_SERVICE     nombre del servicio compose de la DB (default: db)
#   POSTGRES_USER        usuario para pg_dump (default: jheliz)
#   POSTGRES_DB          nombre DB (default: jheliz)
#   RETAIN_LOCAL_DAYS    cuántos días retener localmente (default: 7)

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/jheliz}"
COMPOSE_DIR="${COMPOSE_DIR:-/srv/jheliz}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-db}"
POSTGRES_USER="${POSTGRES_USER:-jheliz}"
POSTGRES_DB="${POSTGRES_DB:-jheliz}"
RETAIN_LOCAL_DAYS="${RETAIN_LOCAL_DAYS:-7}"

mkdir -p "$BACKUP_DIR"

TS="$(date -u +%Y%m%d-%H%M%S)"
WORK_DIR="$(mktemp -d -t jheliz-backup-XXXXXX)"
trap 'rm -rf "$WORK_DIR"' EXIT

echo "[$(date -u +%FT%TZ)] Backup jheliz iniciando → $BACKUP_DIR/jheliz-$TS.tar.gz"

# 1. Dump Postgres
echo "  → pg_dump..."
docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T "$POSTGRES_SERVICE" \
    pg_dump --no-owner --clean --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB" \
    > "$WORK_DIR/db.sql"

# 2. Media
if [ -d "$COMPOSE_DIR/media" ]; then
    echo "  → tar media/..."
    tar -C "$COMPOSE_DIR" -cf "$WORK_DIR/media.tar" media
fi

# 3. .env (snapshot — útil para restaurar la app desde cero)
if [ -f "$COMPOSE_DIR/.env" ]; then
    cp "$COMPOSE_DIR/.env" "$WORK_DIR/dotenv.snapshot"
    chmod 600 "$WORK_DIR/dotenv.snapshot"
fi

# 4. Empaquetar todo en un único .tar.gz
OUT="$BACKUP_DIR/jheliz-$TS.tar.gz"
tar -C "$WORK_DIR" -czf "$OUT" .
chmod 600 "$OUT"

SIZE=$(du -h "$OUT" | awk '{print $1}')
echo "  → $OUT ($SIZE)"

# 5. Retención local
echo "  → limpieza local (>$RETAIN_LOCAL_DAYS días)..."
find "$BACKUP_DIR" -type f -name "jheliz-*.tar.gz" -mtime "+$RETAIN_LOCAL_DAYS" -delete -print | sed 's/^/    eliminado: /' || true

# 6. Si está configurado el offsite, dispararlo en background
if [ -x "$COMPOSE_DIR/deploy/backup-offsite.sh" ]; then
    echo "  → disparando offsite (best-effort)..."
    "$COMPOSE_DIR/deploy/backup-offsite.sh" "$OUT" || echo "  ⚠ offsite falló (ver logs arriba)"
fi

echo "[$(date -u +%FT%TZ)] Backup OK"
