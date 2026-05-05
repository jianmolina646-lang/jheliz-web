#!/bin/bash
# Sube un archivo de backup local a un bucket S3-compatible
# (Backblaze B2, AWS S3, Hostinger Object Storage, MinIO, etc.).
#
# Uso:
#   /srv/jheliz/deploy/backup-offsite.sh /path/to/jheliz-XXXX.tar.gz
#
# Si NO se le pasa argumento, sube el último .tar.gz del BACKUP_DIR.
#
# Variables de entorno requeridas (set por /etc/jheliz-backup.env o
# /etc/environment):
#   BACKUP_S3_BUCKET     nombre del bucket (ej. "jheliz-backups")
#   BACKUP_S3_ENDPOINT   URL del endpoint S3-compatible
#                        (ej. "https://s3.us-west-002.backblazeb2.com")
#   AWS_ACCESS_KEY_ID    keyID del proveedor
#   AWS_SECRET_ACCESS_KEY  applicationKey del proveedor
#
# Variables opcionales:
#   BACKUP_DIR              default: /var/backups/jheliz
#   BACKUP_S3_REGION        default: auto
#   BACKUP_S3_RETAIN        cuántos archivos conservar offsite (default: 30)
#   BACKUP_S3_PREFIX        prefijo dentro del bucket (default: "")
#
# Cargar las creds desde /etc/jheliz-backup.env si existe.
if [ -r /etc/jheliz-backup.env ]; then
    # shellcheck disable=SC1091
    set -a; . /etc/jheliz-backup.env; set +a
fi

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/jheliz}"
BUCKET="${BACKUP_S3_BUCKET:-}"
ENDPOINT="${BACKUP_S3_ENDPOINT:-}"
REGION="${BACKUP_S3_REGION:-auto}"
RETAIN="${BACKUP_S3_RETAIN:-30}"
PREFIX="${BACKUP_S3_PREFIX:-}"

if [ -z "$BUCKET" ] || [ -z "$ENDPOINT" ] || [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    echo "offsite: BACKUP_S3_BUCKET/ENDPOINT/AWS_*_KEY no configurados — saltando" >&2
    exit 0
fi

if ! command -v aws >/dev/null 2>&1; then
    echo "offsite: 'aws' CLI no está instalado. Instalá con: apt-get install -y awscli" >&2
    exit 1
fi

# Determinar archivo a subir.
FILE="${1:-}"
if [ -z "$FILE" ]; then
    FILE=$(ls -1t "$BACKUP_DIR"/jheliz-*.tar.gz 2>/dev/null | head -n1 || true)
fi
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
    echo "offsite: no hay archivo de backup para subir (FILE='$FILE')" >&2
    exit 1
fi

KEY="${PREFIX}$(basename "$FILE")"
echo "[$(date -u +%FT%TZ)] offsite: subiendo $FILE → s3://$BUCKET/$KEY"

# Subir. La opción `--no-progress` evita ruido en el log de cron.
aws --endpoint-url "$ENDPOINT" --region "$REGION" \
    s3 cp "$FILE" "s3://$BUCKET/$KEY" \
    --storage-class STANDARD --no-progress

# Retención offsite: dejar solo los últimos $RETAIN.
echo "  → retención offsite (max $RETAIN archivos)..."
mapfile -t REMOTE < <(
    aws --endpoint-url "$ENDPOINT" --region "$REGION" s3 ls "s3://$BUCKET/$PREFIX" |
    awk '{print $4}' | grep -E '^jheliz-.*\.tar\.gz$' | sort -r
)
if [ "${#REMOTE[@]}" -gt "$RETAIN" ]; then
    for OLD in "${REMOTE[@]:$RETAIN}"; do
        echo "    eliminando viejo: $OLD"
        aws --endpoint-url "$ENDPOINT" --region "$REGION" \
            s3 rm "s3://$BUCKET/$PREFIX$OLD"
    done
fi

echo "[$(date -u +%FT%TZ)] offsite: OK"
