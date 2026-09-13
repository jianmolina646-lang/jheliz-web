# Recuperación de desastre de jheliztv.xyz

## Objetivos

- RPO normal: 15 minutos mediante archivo WAL.
- RTO objetivo: 2 horas para un VPS limpio.
- Regla 3-2-1-1-0: copia local corta, R2, Drive, una copia inmutable y cero
  errores en la restauración verificada.

## Fuentes protegidas

El respaldo completo contiene el dump consistente de PostgreSQL, `media`,
`private_media`, `.env`, secretos, archivos Compose, ambiente efectivo del
contenedor y SHA del commit. No incluye cachés, `staticfiles`, logs ni imágenes
Docker regenerables.

## Destinos y retención

- R2: `jheliztv.xyz/complete-v2/`.
- Drive: `ProductionBackups/jheliztv.xyz/complete-v2/`.
- Local: dos archivos cifrados recientes.
- Retención remota por destino: 14 diarios, 8 semanales y 12 mensuales.

Cada copia se cifra con `age` antes de salir del host. La identidad privada se
guarda fuera del VPS y nunca se sube al repositorio o a los buckets.

## Criterio de éxito

Una ejecución solo se considera correcta cuando el mismo archivo fue subido y
descargado desde R2 y Drive, coincide su SHA-256, se descifra, pasa el manifiesto
y restaura todas las tablas en PostgreSQL 16 aislado y sin red. El estado queda
en `/var/lib/jheliz-backup-v2/success.json`; más de 30 horas sin éxito genera
alerta.

## Procedimiento en un VPS nuevo

1. Instalar Docker, Compose, `age`, `rclone`, Git y PostgreSQL client.
2. Clonar el repositorio en `/opt/jheliz-deploy` y fijar el SHA registrado en el
   manifiesto del respaldo.
3. Copiar la identidad `age` desde el soporte externo a un archivo `0600`.
4. Descargar un archivo `.tar.gz.age` desde R2. Si R2 no responde, usar Drive.
5. Descifrarlo en un directorio temporal privado y comprobar todos los SHA-256
   de `manifest.json`.
6. Levantar PostgreSQL 16 vacío y ejecutar `pg_restore --exit-on-error
   --no-owner --no-acl` sobre `database.dump`.
7. Comparar los conteos de todas las tablas con `manifest.json`.
8. Restaurar configuración, secretos, `media` y `private_media`; revisar rutas y
   permisos antes de iniciar la web.
9. Ejecutar migraciones, `manage.py check --deploy`, pruebas de humo y recién
   entonces cambiar DNS o tráfico.
10. Conservar el VPS anterior y el respaldo previo hasta validar login, clientes,
    suscripciones, pagos, renovaciones y tareas programadas.

Nunca se restaura directamente sobre la base activa. Una restauración de
producción requiere ventana de mantenimiento, copia previa y plan de rollback.

## Validación periódica

- Cada hora: frescura y capacidad.
- Cada 15 minutos: cierre máximo de WAL y sincronización PITR a R2 y Drive.
- Cada domingo 06:30: copia base física PITR independiente de JhelizTV.
- Cada día: restauración automática aislada desde ambos destinos.
- Cada mes: simulacro documentado en un entorno limpio.
- Cada trimestre: comprobar que la identidad externa descifra una copia real.
- Al cambiar credenciales: probar R2 y Drive antes de retirar las anteriores.

Los logs de `/var/log/production-backups/*.log` se rotan semanalmente y se
conservan ocho rotaciones mediante `backup/production-backups.logrotate`.

## Dependencias externas

El remoto Drive debe usar un OAuth `client_id` dedicado. La autorización OAuth
se completa en el navegador del propietario; nunca se pegan refresh tokens en
issues, chats, commits o logs.
