# Backups de jheliz-web

Documenta el sistema de backups del deploy en producción. Incluye la
configuración local (cron + script) y la replicación offsite a un
proveedor S3-compatible (Backblaze B2 recomendado por costo/simplicidad).

## Qué se respalda

`deploy/backup-jheliz.sh` genera un único `.tar.gz` por noche que contiene:

1. **`db.sql`** — dump completo de Postgres (schema + datos) hecho con
   `pg_dump --no-owner --clean --if-exists` desde el contenedor `db`.
2. **`media.tar`** — archivos subidos por usuarios (`/srv/jheliz/media/`):
   comprobantes de Yape, imágenes del catálogo, etc.
3. **`dotenv.snapshot`** — snapshot del `.env` para poder restaurar la
   app desde cero. Permisos 600.

Tamaño aproximado por noche: ~50–100 MB (depende del crecimiento de
`media/`). Si llegara a crecer mucho, cambiar `pg_dump` a `--exclude-table`
para tablas voluminosas no críticas (auditlog, etc.).

## Setup local en el VPS

```bash
# 1) Carpeta + permisos
sudo mkdir -p /var/backups/jheliz
sudo chmod 700 /var/backups/jheliz

# 2) Reemplazar el cron viejo (que respaldaba un proyecto distinto)
sudo crontab -e
# eliminar la línea: 0 3 * * * /root/backup-streaming-bot.sh
# agregar:
0 3 * * * /srv/jheliz/deploy/backup-jheliz.sh >> /var/log/jheliz-backup.log 2>&1

# 3) Permisos de ejecución
sudo chmod +x /srv/jheliz/deploy/backup-jheliz.sh /srv/jheliz/deploy/backup-offsite.sh

# 4) Probar manualmente la primera vez
sudo /srv/jheliz/deploy/backup-jheliz.sh
sudo ls -la /var/backups/jheliz/
```

## Setup offsite (Backblaze B2 — gratis hasta 10 GB)

1. Crear cuenta en https://www.backblaze.com/b2 (no pide tarjeta hasta los 10 GB).
2. Crear un bucket llamado `jheliz-backups` (private, no listing público).
3. Account → Application Keys → "Add a New Application Key":
   - Name: `jheliz-vps-backup`
   - Allow access to: `jheliz-backups` (o el nombre que hayas elegido)
   - Type: `Read and Write`
4. Copiar `keyID`, `applicationKey` y la URL del endpoint (ej.
   `https://s3.us-west-002.backblazeb2.com`).
5. En el VPS:

```bash
sudo apt-get install -y awscli
sudo tee /etc/jheliz-backup.env > /dev/null <<EOF
BACKUP_S3_BUCKET=jheliz-backups
BACKUP_S3_ENDPOINT=https://s3.us-west-002.backblazeb2.com
BACKUP_S3_REGION=us-west-002
BACKUP_S3_RETAIN=30
AWS_ACCESS_KEY_ID=tu-keyID
AWS_SECRET_ACCESS_KEY=tu-applicationKey
EOF
sudo chmod 600 /etc/jheliz-backup.env
```

A partir de la próxima ejecución del cron (3 AM UTC), `backup-jheliz.sh`
disparará `backup-offsite.sh` automáticamente al final.

Para probar manualmente sin esperar:

```bash
sudo /srv/jheliz/deploy/backup-offsite.sh /var/backups/jheliz/jheliz-XXXXXXXX-XXXXXX.tar.gz
```

Si el provider no es Backblaze, igual se usan los mismos env vars — el
script habla S3 puro vía `aws --endpoint-url`. Funciona con AWS S3
estándar (omitir `--endpoint-url` poniendo `BACKUP_S3_ENDPOINT=https://s3.amazonaws.com`),
Hostinger Object Storage, MinIO, Cloudflare R2, etc.

## Restauración (drill)

Probar restauración cada 3 meses para que no nos quede como sorpresa el
día que de verdad se necesite:

```bash
# 1) Bajar el último backup de B2
aws --endpoint-url "$BACKUP_S3_ENDPOINT" s3 cp \
    s3://"$BACKUP_S3_BUCKET"/jheliz-XXXX.tar.gz /tmp/

# 2) Extraer en una carpeta scratch
mkdir /tmp/restore && tar -xzf /tmp/jheliz-XXXX.tar.gz -C /tmp/restore

# 3) Verificar el SQL es válido (no hace falta restaurar de verdad)
head -5 /tmp/restore/db.sql

# 4) Si en realidad hay que restaurar:
docker compose -f /srv/jheliz/docker-compose.yml exec -T db \
    psql -U jheliz -d jheliz < /tmp/restore/db.sql
tar -C /srv/jheliz -xf /tmp/restore/media.tar
```

## Monitoreo

Los logs van a `/var/log/jheliz-backup.log`. Para alertar a Telegram si
el backup falla, agregar después del cron entry:

```cron
0 3 * * * /srv/jheliz/deploy/backup-jheliz.sh >> /var/log/jheliz-backup.log 2>&1 || curl -s -X POST "https://api.telegram.org/bot$TOKEN/sendMessage" -d "chat_id=$CHAT&text=⚠ Backup jheliz falló $(date)"
```
