# Servicios y procesos

## Docker Compose

| Servicio | Perfil | Comando/propósito |
|---|---|---|
| `db` | base | PostgreSQL 16 con volumen persistente |
| `web` | base | Migraciones, estáticos y Gunicorn |
| `telegram_bot` | `bot` | `run_telegram_bot`, bot operativo de la tienda |
| `codes_bot` | `bot` | `run_codes_bot`, códigos Netflix por IMAP |
| `disney_bot` | `bot` | `run_disney_bot`, códigos Disney+ |
| `control_alerts_bot` | `control-alerts` | `run_control_telegram_bot`, My Control |
| `whatsapp_scheduler` | `control-alerts` | `run_control_whatsapp_scheduler` |
| `backup` | `backup` | Backup cifrado programado |

Los perfiles no arrancan con un `docker compose up -d` básico. Deben habilitarse
explícitamente y requieren sus credenciales correspondientes.

## Bots

### Telegram de tienda

Gestiona pedidos, comprobantes, consultas administrativas, publicaciones y
resúmenes. Puede operar por polling o webhook según el despliegue.

### Bot de códigos Netflix

Lee casillas IMAP centrales y entrega únicamente códigos de correos asignados a
clientes autorizados. Mantiene auditoría, límites y controles antiabuso.

### Bot Disney+

Usa su propio token y comparte la infraestructura IMAP del módulo `codes`.

### Bot Telegram de My Control

Extiende JhelizTV con clientes, suscripciones, renovaciones, soporte y alertas.
Su arquitectura está ampliada en `docs/TELEGRAM_CONTROL.md`.

### Discord

Recibe interacciones HTTP y publica notificaciones operativas. Sus comandos de
setup y registro no deben ejecutarse automáticamente en cada despliegue.

## Tareas y comandos relevantes

### Stock y vencimientos

- `check_low_stock`
- `notify_provider_expiry`
- `release_stale_reservations`
- `reconcile_sold_stock`
- `send_expiry_reminders`

### My Control

- `send_control_telegram_alerts`
- `send_control_whatsapp_reminders`
- `run_control_whatsapp_scheduler`

### Discord y Telegram

- `discord_daily_summary`
- `discord_register_commands`
- `discord_setup`
- `telegram_daily_summary`
- `setup_telegram_webhook`

### Seguridad y mantenimiento

- `unlock_logins`
- `encrypt_credentials`
- `backfill_guest_users`

Algunos comandos cambian datos o configuración externa. Se debe leer su ayuda y
probar en un entorno controlado antes de usarlos en producción:

```bash
python manage.py help <comando>
```

## Salud operativa

La condición `Up` no prueba por sí sola la funcionalidad. Para cada proceso se
debe comprobar:

- Reinicios y healthcheck.
- Errores recientes en logs.
- Conectividad con PostgreSQL.
- Credencial configurada sin revelar su valor.
- Respuesta no mutante del proveedor externo.
- Progreso o timestamp de la última tarea.

