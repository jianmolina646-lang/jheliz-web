# Recordatorios automáticos de vencimiento

El comando envía correos a clientes y distribuidores 7, 3 y 1 día antes del
vencimiento, además del mismo día. Cada ventana tiene una marca independiente
en `OrderItem`, por lo que volver a ejecutar el comando no duplica avisos.

Si el proveedor de correo falla, la marca no se guarda y el aviso queda
pendiente para el próximo intento.

## Activación en el VPS

Después de desplegar el código, aplicar la migración:

```bash
cd /opt/jheliz-web
sudo docker exec jheliz-web-1 python manage.py migrate --noinput
```

Hacer primero una simulación:

```bash
sudo docker exec jheliz-web-1 \
  python manage.py send_expiry_reminders --dry-run
```

Instalar el cron de root para ejecutarlo diariamente a las 09:00, hora del
VPS:

```bash
sudo crontab -e
```

Agregar una sola línea:

```cron
0 9 * * * /bin/sh /opt/jheliz-web/deploy/run-expiry-reminders.sh >> /var/log/jheliz-expiry-reminders.log 2>&1
```

Comprobar la zona horaria con `timedatectl`. Si el VPS no usa
`America/Lima`, configurar la zona o ajustar la hora del cron.

## Verificación

```bash
sudo sh /opt/jheliz-web/deploy/run-expiry-reminders.sh
sudo tail -n 50 /var/log/jheliz-expiry-reminders.log
```

El panel administrativo también muestra los indicadores `7d`, `3d`, `1d` y
`Hoy` para cada renovación.
