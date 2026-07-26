# Backups automáticos de JHELIZCONTROLTV

El servicio `backup` respalda diariamente a las 03:20 (`America/Lima`):

- PostgreSQL de `jheliztv.xyz`.
- Clientes, suscripciones, inventario, Telegram y configuración del bot.
- Archivos de `media/`, incluyendo comprobantes.
- `.env` y Docker Secrets necesarios para una restauración completa.

Antes de salir del VPS, el archivo se cifra con AES-256-CBC, PBKDF2 y
200 000 iteraciones. MEGA recibe únicamente el archivo `.enc`.

- `Daily/`: una copia diaria durante 30 días.
- `Monthly/`: una copia del primer día de cada mes durante 12 meses.

## Restauración

Guarda `BACKUP_ARCHIVE_PASSWORD` también en un gestor de contraseñas fuera del
VPS. Sin esa clave no se puede recuperar el backup.

```bash
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in jheliz-control-YYYYMMDD-HHMMSS.tar.gz.enc \
  -out jheliz-control.tar.gz \
  -pass env:BACKUP_ARCHIVE_PASSWORD
mkdir restore && tar -xzf jheliz-control.tar.gz -C restore
cd restore && sha256sum -c SHA256SUMS
```

Restaura PostgreSQL primero en una base de prueba:

```bash
pg_restore --no-owner --no-acl --dbname=jheliz_restore_test database.dump
```

Un backup no se considera verificado hasta completar una restauración de
prueba.
