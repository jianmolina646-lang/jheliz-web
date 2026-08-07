# Desarrollo local

## Requisitos

- Python 3.12.
- Git.
- PostgreSQL opcional; SQLite sirve para desarrollo básico.
- Docker y Compose opcionales para reproducir el entorno de servicios.

## Preparación

```bash
git clone <repositorio>
cd jheliz-web
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

Usa valores locales y cuentas sandbox. No copies secretos ni bases de producción.

## Variables de entorno

`.env.example` es el inventario canónico. No contiene credenciales funcionales.

### Núcleo Django

- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `SITE_URL`.
- `DATABASE_URL`.
- `STATICFILES_DIR`.

### Email, pagos y notificaciones web

- `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL`, `SUPPORT_ADMIN_EMAIL`.
- `MERCADOPAGO_ACCESS_TOKEN`, `MERCADOPAGO_PUBLIC_KEY`.
- `MERCADOPAGO_WEBHOOK_SECRET`, `MERCADOPAGO_CHECKOUT_ENABLED`.
- `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIM_EMAIL`.

### Telegram, Discord y WhatsApp

- `TELEGRAM_*` para tienda, canales, códigos y administración.
- `JHELIZ_CONTROL_TELEGRAM_*` para My Control.
- `DISCORD_*` para bot, guild, canales e interacciones.
- `WHATSAPP_NUMBER`; la configuración Meta adicional está documentada en
  `docs/WHATSAPP_META_SETUP.md`.

### Códigos e IMAP

- `CODES_IMAP_*`, `CODES_IMAP2_*`.
- `CODES_LOOKBACK_MINUTES`, límites y controles de seguridad.
- IDs opcionales `CODES_PREMIUM_EMOJI_*`.

### Seguridad

- `FIELD_ENCRYPTION_KEY`.
- `AXES_FAILURE_LIMIT`, `AXES_COOLOFF_TIME_HOURS`.
- `TRUSTED_PROXY_NETWORKS`.
- `ADMIN_LOGIN_NOTIFY`, `SECURITY_EVENT_ALERTS`, `ADMIN_2FA_ENFORCED`.

### Backups

- `MEGA_*`, `BACKUP_*` y contraseña de cifrado.

Nunca registres valores reales en documentación, commits, logs o capturas.

## Base de datos

SQLite se selecciona si no existe `DATABASE_URL`. Para PostgreSQL local usa una
base dedicada, nunca producción.

```bash
python manage.py showmigrations --plan
python manage.py migrate
```

No reescribas migraciones aplicadas. Toda migración nueva debe ser revisada con:

```bash
python manage.py makemigrations --check --dry-run
python manage.py sqlmigrate <app> <migration>
```

## Pruebas y calidad

```bash
python manage.py check
python manage.py test
python manage.py check --deploy
```

Para una aplicación concreta:

```bash
python manage.py test accounts
python manage.py test catalog
python manage.py test codes
python manage.py test gestion
python manage.py test orders
```

## Estáticos y traducciones

```bash
python manage.py collectstatic --noinput
python manage.py compilemessages
```

No edites manualmente `staticfiles/`; es contenido generado. Los `.mo` se
generan a partir de los `.po` y actualmente se versionan.

## Flujo Git

1. Trabajar en una rama separada.
2. Mantener el árbol limpio antes de comenzar una fase.
3. Hacer cambios pequeños y ejecutar pruebas.
4. Revisar `git diff --check` y `git diff --stat`.
5. Crear commits descriptivos sin mezclar alcances.

