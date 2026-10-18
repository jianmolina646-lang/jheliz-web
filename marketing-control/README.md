# Jheliz Control — fases 1 y 2

Panel privado nuevo para https://marketingjhelizxyz.online. Implementa autenticación, roles, conexiones independientes de WhatsApp, QR, activar/desactivar/reiniciar, comandos editables, actividad y auditoría. No publica tienda ni funcionalidades simuladas de pagos/clientes.

## Arquitectura

- `src/server.js`: API Fastify y frontend estático del mismo origen.
- `src/worker.js`: adaptador WhatsApp Baileys, sesiones por instancia en volumen privado, reconexión y deduplicación.
- `src/migrate.js`: migración inicial idempotente y comandos predeterminados.
- `src/policy.js`: roles, validación y protección de comandos privados.
- PostgreSQL independiente: usuarios, sesiones, instancias, comandos, eventos, auditoría y deduplicación. No se almacenan datos en Sheets.

Se reutiliza el proveedor Baileys de la instalación previa. Es una integración no oficial; su conexión depende de WhatsApp y de vincular un teléfono real. No se migran sesiones antiguas al nuevo panel. Los módulos futuros de clientes, cuentas, ventas, pagos, soporte y reportes deben añadirse por migraciones, rutas y adaptadores independientes. Los comandos privados están desactivados: requieren identificación verificada del cliente antes de implementar respuestas con datos.

## Instalación VPS

Copiar `.env.example` a `.env`, usar secreto aleatorio para PostgreSQL y configurar un administrador inicial con `OWNER_EMAIL` y `OWNER_INITIAL_PASSWORD` (12+ caracteres). Ejecutar `docker compose build` y `docker compose up -d`. La migración se ejecuta antes de API y worker. API escucha únicamente en `127.0.0.1:8011` del host. Publicar con Nginx y certificado HTTPS para el dominio. No abrir el puerto 8011 ni PostgreSQL a Internet.

En esta sustitución se preservan exclusivamente los accesos administrativos activos anteriores mediante `src/import-admins.js`; los datos comerciales anteriores quedan en respaldo. No se transfieren contraseñas en texto plano. Se permite cambiarlas desde Mi cuenta. La instalación anterior no debe arrancarse en paralelo una vez retirado el sitio.

## Conectar WhatsApp

Entrar → WhatsApp → Activar bot → desde el teléfono, WhatsApp / Dispositivos vinculados / Vincular dispositivo. Escanear el QR privado. Esperar Conectado y enviar `/menu` desde otro número. Desactivar cierra la conexión sin borrar la sesión. Reiniciar conserva el vínculo. Si el teléfono cerró la sesión, crear una conexión nueva y volver a vincular. Máximo cinco instancias configurables; una sola réplica del worker. No escalar el worker sin introducir un bloqueo distribuido por instancia.

## Roles

| Rol | Consulta | Bot y comandos | Equipo y auditoría |
|---|---|---|---|
| ADMIN | Sí | Sí | Sí |
| OPERATOR | Sí | Sí | No |
| SUPPORT | Sí, sin QR | No | No |

## API

Todas las rutas `/api` requieren cookie de sesión excepto `POST /api/login`. Mutaciones requieren `Origin` igual a `APP_URL` y cabecera `X-CSRF-Token` entregada por `GET /api/me`.

| Rutas | Uso |
|---|---|
| POST /api/login, /api/logout, /api/password | Acceso, salida y cambio de contraseña |
| GET /api/me | Identidad y CSRF |
| GET/POST /api/instances | Consultar/crear conexiones |
| POST /api/instances/:id/start, stop, restart | Control real del worker |
| GET/POST /api/commands | Listar/crear |
| PUT/DELETE /api/commands/:id | Editar/eliminar |
| GET /api/events, /api/audit | Actividad y auditoría |
| GET/POST /api/users, PATCH /api/users/:id | Equipo y activación |
| GET /health | Salud DB/API |

## Seguridad y operación

Contraseñas Argon2, sesiones aleatorias guardadas como hash SHA256, cookie Secure/HttpOnly/SameSite Strict con 8 horas de duración, comprobación de rol y cuenta activa en cada petición, CSRF por origen y token, consultas SQL parametrizadas, Zod, CSP y escape HTML. Rate limit de login (8/minuto/IP), controles (10/minuto/IP) y comandos (8/minuto/remitente). No guardar credenciales en respuestas. Auditoría sin contraseñas ni tokens. El QR solo se entrega a roles con control y se elimina al conectar/desconectar. Las claves del dispositivo en el volumen son secretos: limitar acceso de host y cifrar las copias externas. Eventos se retienen 30 días; auditoría no se elimina automáticamente.

## Verificación

`docker compose exec -T api npm test` prueba permisos, comandos privados y validación. `docker compose exec -T -e RUN_INTEGRATION=1 api node --test tests/integration.test.js` prueba autenticación real, CSRF, autorización, CRUD y cierre de sesión contra PostgreSQL; crea y elimina usuarios temporales. Para verificar QR y control real usar una instancia de prueba sin escanear y desactivarla después. La confirmación de mensajes requiere que el propietario vincule el teléfono.

## Backup y restauración

`sudo sh scripts/backup.sh` guarda dump PostgreSQL, `.env` y sesión en `/opt/backups/marketing-control/FECHA`; carpeta accesible solo por root. Copiar cifrado a almacenamiento externo. Antes de restaurar, verificar la fecha y respaldar estado actual. Detener API/worker. Restaurar en una base vacía con `pg_restore -U marketing -d marketing --exit-on-error`, recuperar `.env` correspondiente y extraer sesiones en un volumen nuevo, propietario 1000:1000. Arrancar migración/API/worker y comprobar `/health`, acceso, instancias y comandos antes de apuntar Nginx. No restaurar encima de datos vivos sin respaldo y confirmación del destino.

Para rollback del reemplazo, restaurar la configuración Nginx guardada en `/opt/backups/marketing-before-clean-20261011/nginx.conf`, arrancar el compose anterior, ejecutar `nginx -t` y recargar Nginx. Los volúmenes anteriores se conservan para recuperación, fuera de la web activa.
