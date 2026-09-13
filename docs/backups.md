# Backups y restauración

## Sistema vigente

Para **jheliztv.xyz en el VPS**, el respaldo completo vigente desde el
2026-09-06 es el servicio del host descrito en [production-backup-v2.md](production-backup-v2.md).
Las copias Docker descritas a continuación siguen como legado durante la transición.

El servicio del host `jheliz-backup-v2` es el mecanismo autoritativo de
`jheliztv.xyz`. El servicio Docker `backup` se conserva como generador legado y
para instalaciones aisladas del bot de códigos; no define la copia completa del
producto SaaS.

Incluye:

- Dump PostgreSQL en formato custom.
- `media/` y `private_media/`.
- Copia de `.env` y del directorio `secrets/` si están montados.
- Manifiesto y checksums SHA-256.

El bundle completo autoritativo se cifra con `age` antes de salir del VPS. R2 y
Google Drive reciben solamente el archivo cifrado. Las copias legacy Docker usan
AES-256-CBC, PBKDF2 y 200 000 iteraciones.

## Programación y retención

Los defaults del servicio son:

- Ejecución diaria a las 03:20, zona `America/Lima`.
- 30 copias diarias.
- 12 copias mensuales.

Una instalación aislada debe usar un prefijo y carpeta remota propios para no
mezclar backups de bases diferentes.

## Verificación

```bash
docker compose --profile backup ps backup
docker compose --profile backup logs --tail=100 backup
```

Un log de carga exitosa no basta. Periódicamente debe realizarse una restauración
en una base temporal y comprobar los checksums.

## Descifrado controlado

Ejecutar fuera de producción y con la contraseña obtenida del gestor seguro:

```bash
export BACKUP_ARCHIVE_PASSWORD='<obtenida-del-gestor>'
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -in jheliz-control-YYYYMMDD-HHMMSS.tar.gz.enc \
  -out jheliz-control.tar.gz \
  -pass env:BACKUP_ARCHIVE_PASSWORD
mkdir restore
tar -xzf jheliz-control.tar.gz -C restore
cd restore
sha256sum -c SHA256SUMS
```

No escribir la contraseña en historial, commits o documentación.

## Restauración de prueba

Crear una base temporal aislada y restaurar el dump:

```bash
createdb jheliz_restore_test
pg_restore --no-owner --no-acl \
  --dbname=jheliz_restore_test \
  database.dump
```

Validar tablas, conteos representativos, usuarios, suscripciones y migraciones.
Eliminar la base temporal solo después de registrar el resultado de la prueba.

## Restauración de producción

Es una operación destructiva y requiere autorización específica. Antes:

1. Confirmar el archivo y su checksum.
2. Conservar una copia de la base y archivos actuales.
3. Detener procesos que escriben: web, bots, workers y schedulers.
4. Restaurar primero en una base temporal.
5. Documentar comandos y responsable.
6. Tener rollback del propio procedimiento de restauración.

## Implementación legacy

`deploy/backup.sh`, `deploy/restore.sh` y `deploy/BACKUP.md` describen un sistema
anterior basado en cron, GPG y rclone. Se conservan por compatibilidad e historia.
No se deben mezclar ambos procedimientos ni eliminar el legado hasta confirmar
que ninguna instalación lo utiliza.
