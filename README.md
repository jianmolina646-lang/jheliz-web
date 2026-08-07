# Jheliz Web

Monolito Django que reúne la tienda de servicios digitales, JhelizTV/My Control,
el panel administrativo y las integraciones operativas de Jheliz.

El repositorio usa aplicaciones Django por dominio, plantillas renderizadas en
servidor y procesos independientes para bots, recordatorios y backups. La
arquitectura actual se conserva para mantener compatibilidad con rutas,
migraciones, comandos y despliegues existentes.

## Componentes principales

- **Tienda:** catálogo, carrito, pedidos, pagos, stock, soporte y distribuidores.
- **JhelizTV/My Control:** clientes, servicios, renovaciones, inventario y cobros.
- **Administración:** panel Django personalizado, reportes, auditoría y 2FA.
- **Bots:** Telegram de tienda, códigos Netflix, Disney+, alertas de My Control y Discord.
- **Automatizaciones:** recordatorios de Telegram/WhatsApp, vencimientos y backups.

## Tecnologías

- Python 3.12 y Django 5.2.
- PostgreSQL 16 en producción; SQLite como alternativa local.
- Django Templates, HTMX, JavaScript y CSS propios.
- Gunicorn, Nginx y Docker Compose.
- Telegram Bot API, Discord, Meta WhatsApp Cloud API, Mercado Pago e IMAP.
- Backups cifrados con OpenSSL y almacenamiento externo en MEGA.

## Estructura

```text
accounts/       usuarios, roles, wallet y seguridad
blog/           contenido, feeds y sitemap
catalog/        productos, planes, stock, reseñas y distribuidores
codes/          bots y parsers de códigos Netflix/Disney+
config/         settings, URLs, middleware y panel global
discord_bot/    integración e interacciones de Discord
gestion/        JhelizTV/My Control
livechat/       chat y notificaciones
orders/         carrito, pedidos, pagos, entregas e integraciones
support/        tickets y solicitudes de códigos
templates/      frontend server-rendered
static/         CSS, JavaScript, imágenes y vendor assets
backup/         servicio Docker de backup cifrado
deploy/         utilidades operativas y documentación histórica
docs/           documentación técnica y operativa
```

La explicación detallada está en [docs/architecture.md](docs/architecture.md).

## Desarrollo local

Requisitos: Python 3.12, entorno virtual y las librerías de sistema necesarias
para PostgreSQL/Pillow.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

No uses credenciales ni copias de bases de producción para desarrollo. Consulta
[docs/development.md](docs/development.md) para configuración y pruebas.

## Comprobaciones

```bash
python manage.py check
python manage.py test
python manage.py showmigrations --plan
```

Antes de desplegar:

```bash
python manage.py check --deploy
docker compose config
```

## Producción

El servicio web ejecuta migraciones, recopila estáticos e inicia Gunicorn. Los
bots, automatizaciones y backups se habilitan mediante perfiles de Compose.

```bash
docker compose up -d db web
docker compose --profile bot up -d
docker compose --profile control-alerts up -d
docker compose --profile backup up -d backup
```

JhelizTV puede usar el override específico:

```bash
docker compose -f docker-compose.yml -f docker-compose.jheliztv.yml up -d db web
```

No ejecutes estos comandos contra producción sin inventario, backup verificado y
plan de rollback. Consulta [docs/production.md](docs/production.md).

## Variables de entorno

`.env.example` contiene los nombres soportados y valores de ejemplo no secretos.
Las categorías principales son:

- Django, dominios y base de datos.
- Email, pagos y Web Push.
- Telegram, Discord y WhatsApp.
- IMAP del bot de códigos.
- Seguridad, 2FA y cifrado de campos.
- Backups, retención y almacenamiento externo.

Nunca se deben versionar `.env`, archivos en `secrets/`, tokens o contraseñas.
Consulta [docs/development.md](docs/development.md#variables-de-entorno).

## Servicios y operaciones

- [Servicios y procesos](docs/services.md)
- [Despliegue de producción](docs/production.md)
- [Backups y restauración](docs/backups.md)
- [Rollback](docs/rollback.md)
- [Docker Secrets](docs/DOCKER_SECRETS.md)
- [Telegram de My Control](docs/TELEGRAM_CONTROL.md)
- [WhatsApp Cloud API](docs/WHATSAPP_META_SETUP.md)

## Reglas de mantenimiento

- Cambios pequeños, revisables y con pruebas.
- No mover modelos entre apps ni reescribir migraciones aplicadas.
- Conservar rutas, namespaces, comandos y módulos fachada.
- Tratar JhelizTV, My Control, bots, autenticación y backups como componentes protegidos.
- Nunca hacer `force push` ni desplegar desde un árbol Git sucio.
