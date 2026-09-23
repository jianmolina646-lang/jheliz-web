# Jheliz WhatsApp Control

Panel privado para construir y operar un bot autorizado de WhatsApp. No contiene tienda pública, ecommerce, checkout ni panel de clientes.

## Arquitectura

- `apps/panel`: panel Next.js/React.
- `apps/api`: API Fastify, autenticación, permisos y auditoría.
- `apps/whatsapp`: proceso Baileys independiente.
- `packages/db`: Prisma/PostgreSQL.
- `packages/shared`: validaciones compartidas.

Baileys es una integración no oficial y puede sufrir cambios o restricciones. Úsala únicamente con números y operaciones autorizadas. No se incluyen envíos masivos, scraping ni evasión de controles.

## Instalación

1. Copiar `.env.example` a `.env`.
2. Agregar `POSTGRES_PASSWORD` y `REDIS_PASSWORD` y generar valores aleatorios distintos para todos los secretos.
3. Generar `ENCRYPTION_KEY` con `openssl rand -base64 32`.
4. Configurar `OWNER_INITIAL_PASSWORD` con al menos 12 caracteres.
5. Ejecutar `docker compose build`.
6. Ejecutar `docker compose up -d postgres redis`.
7. Ejecutar `docker compose run --rm migrate`.
8. Ejecutar `docker compose run --rm api npm run seed -w @jheliz/api`.
9. Ejecutar `docker compose up -d`.

Cambiar inmediatamente la contraseña inicial. Nunca subir `.env` a Git.

## Migraciones y ejecución

- Producción: `docker compose run --rm migrate`.
- Desarrollo: `npm run db:dev -w @jheliz/db -- --name descripcion`.
- Estado: `docker compose ps`.
- Logs seguros: `docker compose logs --tail=200 api whatsapp`.

## Conectar WhatsApp

Inicia los servicios, entra como `OWNER`, abre **Conexión** y vincula desde *Dispositivos vinculados* del número autorizado. La sesión vive exclusivamente en el volumen `whatsapp_session`; reiniciar contenedores no la elimina.

## Pruebas

Probar `.menu`, `.shop`, `.info SKU`, `.saldo` y `.help` desde otro número autorizado. Antes de `.buy`, cargar producto, inventario y saldo. La compra usa transacción serializable, bloqueo de inventario e idempotencia.

## Backup y restauración

`scripts/backup.sh` crea un dump PostgreSQL en formato custom. Copiar también el volumen privado de sesión. Para restaurar: detener `api` y `whatsapp`, ejecutar `scripts/restore.sh backup.dump`, aplicar migraciones, levantar servicios y comprobar datos antes de reabrir el proxy.

## Seguridad

Cookies HttpOnly/Secure/SameSite, rate limiting, Argon2, roles `OWNER/ADMIN/SUPPORT`, validación Zod, AES-256-GCM para secretos, logs redactados y auditoría. Las credenciales completas no aparecen en tablas ni logs.

## Pendientes antes de producción plena

- Exponer el QR mediante endpoint autenticado.
- Completar los formularios CRUD visuales, editor gráfico de flujos, 2FA y cambio de contraseña.
- Integrar un proveedor de pagos verificable; no se simulan pagos.
- Ejecutar pruebas E2E, concurrencia, backup/restauración y reconexión prolongada.
- Baileys 7 está fijado a `7.0.0-rc14`; revisar cambios antes de actualizar.
