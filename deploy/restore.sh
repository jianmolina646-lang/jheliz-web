#!/usr/bin/env bash
# =============================================================================
# Jheliz Web — Restaurar desde un backup generado por deploy/backup.sh
#
# Uso:
#   sudo bash deploy/restore.sh /srv/backups/daily/jheliz-YYYYMMDD-HHMMSS.tar.gz[.gpg]
#
# Pide confirmación antes de tocar nada. Restaura DB + media + .env.
# Si el bundle está cifrado con GPG, pide passphrase.
# =============================================================================

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Uso: $0 <bundle.tar.gz[.gpg]>"
    exit 1
fi

BUNDLE="$1"
if [[ ! -f "$BUNDLE" ]]; then
    echo "ERROR: no existe $BUNDLE"
    exit 1
fi

JHELIZ_ROOT="${JHELIZ_ROOT:-/srv/jheliz}"
WORK_DIR=$(mktemp -d -t jheliz-restore-XXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

cat <<EOF

================================================================
  RESTAURAR JHELIZ DESDE BACKUP
================================================================
  Bundle : $BUNDLE
  Destino: $JHELIZ_ROOT

  Esto va a:
    1. Reemplazar TODA la base de datos jheliz por la del backup.
    2. Reemplazar /srv/jheliz/media/ por la del backup.
    3. Reemplazar /srv/jheliz/.env por el del backup.

  Estado actual será PERDIDO.
================================================================

EOF

read -rp "Escribí 'RESTORE' para confirmar: " CONFIRM
if [[ "$CONFIRM" != "RESTORE" ]]; then
    echo "Cancelado."
    exit 1
fi

# 1. Desempaquetar (decifrando primero si hace falta).
if [[ "$BUNDLE" == *.gpg ]]; then
    read -rsp "Passphrase GPG: " GPG_PP
    echo
    gpg --batch --yes --passphrase "$GPG_PP" -d "$BUNDLE" | tar -xzf - -C "$WORK_DIR"
else
    tar -xzf "$BUNDLE" -C "$WORK_DIR"
fi

ls -la "$WORK_DIR"

# 2. Restaurar DB.
cd "$JHELIZ_ROOT"
DB_USER=$(docker compose exec -T db sh -c 'printf %s "$POSTGRES_USER"')
DB_NAME=$(docker compose exec -T db sh -c 'printf %s "$POSTGRES_DB"')
echo "Restaurando DB ($DB_USER@$DB_NAME) ..."
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" < "$WORK_DIR/db.sql"

# 3. Restaurar media.
if [[ -f "$WORK_DIR/media.tar.gz" ]]; then
    echo "Restaurando media/ ..."
    rm -rf "$JHELIZ_ROOT/media"
    tar -xzf "$WORK_DIR/media.tar.gz" -C "$JHELIZ_ROOT"
fi

# 4. Restaurar .env (con backup del actual por si acaso).
if [[ -f "$WORK_DIR/dotenv" ]]; then
    echo "Restaurando .env (backup actual en .env.bak.$(date +%s)) ..."
    cp -a "$JHELIZ_ROOT/.env" "$JHELIZ_ROOT/.env.bak.$(date +%s)"
    cp "$WORK_DIR/dotenv" "$JHELIZ_ROOT/.env"
    chmod 600 "$JHELIZ_ROOT/.env"
fi

# 5. Recrear container con las nuevas credenciales.
echo "Recreando container web ..."
docker compose up -d --force-recreate web

echo "Restore completo."
