# Telegram como extensión de Jheliz Control

El bot `@JHELIZCONTROLTV_bot` se ejecuta dentro del mismo proyecto Django que
la web. No usa una base de datos paralela: lee y modifica directamente los
modelos centrales de `gestion`.

## Arquitectura

```text
Telegram Bot API
       |
run_control_telegram_bot
       |
control_operations.py
       |
PostgreSQL central
       |
tenant_views.py / web Jheliz Control
```

`TelegramConnection.owner_id` es la identidad canónica. `chat_id` solo es la
dirección de entrega. Todas las consultas de clientes y suscripciones filtran
por el `owner_id` vinculado, incluso las relaciones `client` y `service`.

## Funciones

- Menú inline con resumen del revendedor.
- Clientes paginados, filtros y búsqueda.
- Alta y edición usando `ClientForm`.
- Detalle y suscripciones reales del cliente.
- Renovación de suscripciones con confirmación.
- Eliminación de clientes con confirmación.
- Idempotencia para altas, ediciones, renovaciones y eliminaciones.
- Próximos vencimientos, estadísticas y saldo real.
- Configuración de ventanas de alertas.
- Estado de cuenta y desvinculación confirmada.
- Enlaces al panel configurados mediante variable de entorno.

Los campos de cliente respetan el modelo web: nombre, WhatsApp, correo,
Telegram y notas. Servicio, cuenta, modalidad, perfiles y vencimiento
pertenecen a `Subscription`; no se duplican como campos del cliente.

## Variables

```env
JHELIZ_CONTROL_TELEGRAM_BOT_TOKEN=
JHELIZ_CONTROL_TELEGRAM_BOT_USERNAME=JHELIZCONTROLTV_bot
JHELIZ_CONTROL_BASE_URL=https://jheliztv.xyz
```

El token debe permanecer en `.env` o en el secreto Docker existente. Nunca
debe almacenarse en Git.

## Despliegue

```bash
python manage.py migrate
python manage.py test gestion.test_telegram_alerts
python manage.py check --deploy
```

Recrear el servicio `control_alerts_bot` después de actualizar el código. El
cron existente puede seguir ejecutando `send_control_telegram_alerts`; el
campo `last_digest_date` evita repetir el resumen del mismo día.
