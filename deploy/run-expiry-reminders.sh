#!/usr/bin/env sh
set -eu

# Ejecuta los avisos 7d, 3d, 1d y el mismo día dentro del contenedor que ya
# tiene acceso a PostgreSQL, correo y Docker Secrets.
CONTAINER_NAME="${REMINDER_CONTAINER:-jheliz-web-codes_bot-1}"

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null |
    grep -qx true; then
    echo "El contenedor $CONTAINER_NAME no está activo." >&2
    exit 1
fi

docker exec "$CONTAINER_NAME" \
    python manage.py send_expiry_reminders \
    --windows 7,3,1,0 \
    --distri-windows 7,3,1,0
