#!/usr/bin/env bash
# =============================================================================
# Jheliz Web — Backup diario (DB + media + .env)
#
# Qué hace:
#   1. pg_dump completo de la DB postgres (dentro del container db).
#   2. tar.gz de /srv/jheliz/media (comprobantes Yape, imágenes de chat, etc).
#   3. Copia del .env (contiene secrets: SECRET_KEY, MP, Brevo, FIELD_KEY).
#   4. Junta los 3 en un único .tar.gz, opcionalmente cifrado con GPG.
#   5. Rota viejos: conserva últimos 7 diarios + 4 semanales (lunes).
#   6. Si rclone está configurado con remoto "drive", sube a Drive.
#
# Para correr manualmente:
#   sudo bash /srv/jheliz/deploy/backup.sh
#
# Para automatizar (root crontab):
#   0 3 * * * /srv/jheliz/deploy/backup.sh >> /var/log/jheliz-backup.log 2>&1
#
# Configuración opcional vía /etc/jheliz-backup.env:
#   BACKUP_DIR=/srv/backups            # dónde guardar (default)
#   GPG_PASSPHRASE=...                 # si está, cifra el tar final con AES256
#   RCLONE_REMOTE=drive:JhelizBackups  # si está, sube ahí (formato remoto:carpeta)
#   KEEP_DAILY=7                       # días a retener (default 7)
#   KEEP_WEEKLY=4                      # semanas a retener (default 4)
#
# Sale con código != 0 si algo falla, para que cron alerte por mail.
# =============================================================================

set -euo pipefail

# --- Config ------------------------------------------------------------------

JHELIZ_ROOT="${JHELIZ_ROOT:-/srv/jheliz}"
BACKUP_DIR="${BACKUP_DIR:-/srv/backups}"
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"

# Cargá overrides de /etc/jheliz-backup.env si existe.
if [[ -f /etc/jheliz-backup.env ]]; then
    # shellcheck disable=SC1091
    source /etc/jheliz-backup.env
fi

TS=$(date +%Y%m%d-%H%M%S)
DOW=$(date +%u)  # 1=Mon … 7=Sun
WORK_DIR=$(mktemp -d -t jheliz-backup-XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

log() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*"; }

# --- 1. pg_dump --------------------------------------------------------------

log "Dump de Postgres ..."
cd "$JHELIZ_ROOT"
# Tomamos POSTGRES_USER/DB del docker-compose para no hardcodear nada.
DB_USER=$(docker compose exec -T db sh -c 'printf %s "$POSTGRES_USER"')
DB_NAME=$(docker compose exec -T db sh -c 'printf %s "$POSTGRES_DB"')
if [[ -z "$DB_USER" || -z "$DB_NAME" ]]; then
    log "ERROR: no pude leer POSTGRES_USER/DB del container db."
    exit 1
fi
docker compose exec -T db pg_dump \
    --no-owner --no-privileges --clean --if-exists \
    -U "$DB_USER" -d "$DB_NAME" \
    > "$WORK_DIR/db.sql"
log "  -> $(wc -c <"$WORK_DIR/db.sql") bytes."

# --- 2. media + 3. .env ------------------------------------------------------

log "Tar de /srv/jheliz/media ..."
if [[ -d "$JHELIZ_ROOT/media" ]]; then
    tar -czf "$WORK_DIR/media.tar.gz" -C "$JHELIZ_ROOT" media
    log "  -> $(wc -c <"$WORK_DIR/media.tar.gz") bytes."
else
    log "  (sin media/, salto)"
fi

if [[ -f "$JHELIZ_ROOT/.env" ]]; then
    cp "$JHELIZ_ROOT/.env" "$WORK_DIR/dotenv"
    chmod 600 "$WORK_DIR/dotenv"
fi

# Metadata útil para restaurar.
cat > "$WORK_DIR/README.txt" <<EOF
Jheliz Web backup
=================
Generado: $(date -u +'%Y-%m-%dT%H:%M:%SZ')
Host: $(hostname)
DB user: $DB_USER
DB name: $DB_NAME
Git HEAD: $(cd "$JHELIZ_ROOT" && git rev-parse HEAD 2>/dev/null || echo 'n/a')

Para restaurar:
  1. Levantar postgres vacío y la app.
  2. cat db.sql | docker compose exec -T db psql -U $DB_USER -d $DB_NAME
  3. tar -xzf media.tar.gz -C /srv/jheliz/
  4. cp dotenv /srv/jheliz/.env
  5. docker compose up -d --force-recreate web
EOF

# --- 4. Bundle + GPG opcional ------------------------------------------------

BUNDLE="$BACKUP_DIR/daily/jheliz-${TS}.tar.gz"
tar -czf "$BUNDLE" -C "$WORK_DIR" .
chmod 600 "$BUNDLE"
log "Bundle generado: $BUNDLE ($(wc -c <"$BUNDLE") bytes)"

if [[ -n "${GPG_PASSPHRASE:-}" ]]; then
    log "Cifrando con GPG (AES256) ..."
    gpg --batch --yes --passphrase "$GPG_PASSPHRASE" --symmetric --cipher-algo AES256 -o "${BUNDLE}.gpg" "$BUNDLE"
    rm "$BUNDLE"
    BUNDLE="${BUNDLE}.gpg"
    chmod 600 "$BUNDLE"
    log "  -> $BUNDLE"
fi

# Copia semanal (lunes).
if [[ "$DOW" == "1" ]]; then
    cp "$BUNDLE" "$BACKUP_DIR/weekly/"
    log "Copia semanal generada."
fi

# --- 5. Rotación -------------------------------------------------------------

log "Rotando diarios > $KEEP_DAILY ..."
find "$BACKUP_DIR/daily" -maxdepth 1 -type f -name 'jheliz-*' -printf '%T@ %p\n' \
    | sort -nr | tail -n +"$((KEEP_DAILY + 1))" | cut -d' ' -f2- \
    | xargs -r rm -v

log "Rotando semanales > $KEEP_WEEKLY ..."
find "$BACKUP_DIR/weekly" -maxdepth 1 -type f -name 'jheliz-*' -printf '%T@ %p\n' \
    | sort -nr | tail -n +"$((KEEP_WEEKLY + 1))" | cut -d' ' -f2- \
    | xargs -r rm -v

# --- 6. Upload a Drive (opcional) -------------------------------------------

if [[ -n "${RCLONE_REMOTE:-}" ]]; then
    if command -v rclone >/dev/null; then
        log "Subiendo a $RCLONE_REMOTE ..."
        rclone copy "$BUNDLE" "$RCLONE_REMOTE/daily/" --transfers=1 --checkers=1 || {
            log "WARNING: rclone falló subiendo el daily."
        }
        if [[ "$DOW" == "1" ]]; then
            rclone copy "$BUNDLE" "$RCLONE_REMOTE/weekly/" --transfers=1 --checkers=1 || {
                log "WARNING: rclone falló subiendo el weekly."
            }
        fi
        # Mantener Drive también limpio (mismo criterio).
        rclone delete "$RCLONE_REMOTE/daily/" --min-age "${KEEP_DAILY}d" --rmdirs >/dev/null 2>&1 || true
        rclone delete "$RCLONE_REMOTE/weekly/" --min-age "${KEEP_WEEKLY}w" --rmdirs >/dev/null 2>&1 || true
    else
        log "WARNING: rclone no instalado; RCLONE_REMOTE ignorado."
    fi
fi

log "Backup OK: $BUNDLE"
