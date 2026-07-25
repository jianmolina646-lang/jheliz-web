#!/usr/bin/env sh
set -eu

# Ejecuta los avisos 7d, 3d, 1d y el mismo día dentro del contenedor que ya
# tiene acceso a PostgreSQL, correo y Docker Secrets.
# En producción, jheliztv.xyz corre como servicio ``web`` del proyecto
# Compose ``jheliz``. Se puede sobrescribir para otros despliegues.
CONTAINER_NAME="${REMINDER_CONTAINER:-jheliz-web-1}"

if ! docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null |
    grep -qx true; then
    echo "El contenedor $CONTAINER_NAME no está activo." >&2
    exit 1
fi

docker exec "$CONTAINER_NAME" \
    python manage.py send_expiry_reminders \
    --windows 7,3,1,0 \
    --distri-windows 7,3,1,0

docker exec "$CONTAINER_NAME" python manage.py send_control_telegram_alerts
