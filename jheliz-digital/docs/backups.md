# Backups de Jheliz Digital

El servicio `backup` genera cada día a las 04:20, hora de Lima, una copia de
PostgreSQL y del archivo de entorno. El contenido se cifra localmente con AES-256
antes de subirse a `/JhelizDigitalBackups/Daily` en MEGA.

- Retención diaria: 30 días.
- Retención mensual: 12 meses.
- Verificación de restauración: domingos a las 05:10, en una base temporal.
- Los archivos sin cifrar solo existen en un directorio temporal durante el proceso.

## Ejecución manual

```bash
docker compose --env-file .env -f compose.production.yml \
  --profile backup exec backup /usr/local/bin/jheliz-digital-backup
```

## Verificación manual

```bash
docker compose --env-file .env -f compose.production.yml \
  --profile backup exec backup /usr/local/bin/jheliz-digital-verify-restore
```
