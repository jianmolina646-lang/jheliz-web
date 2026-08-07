# Arquitectura

## Visión general

Jheliz Web es un monolito modular Django. Comparte modelos, autenticación y
configuración, pero publica dos superficies principales:

1. La tienda y su panel administrativo, servidos por `config.urls`.
2. JhelizTV/My Control, servido por `config.urls_jheliztv`.

`config.host_routing.JheliztvHostMiddleware` selecciona el URLconf según el
dominio. En un despliegue aislado, `config.settings_jheliztv` fija directamente
el URLconf y los dominios de JhelizTV.

```text
Nginx
  └── Gunicorn / Django
        ├── config.urls ── tienda, admin, pedidos, soporte y catálogo
        └── config.urls_jheliztv ── JhelizTV/My Control

PostgreSQL
  ├── procesos web
  ├── bots Django
  ├── tareas programadas
  └── backup cifrado
```

## Aplicaciones Django

| Aplicación | Responsabilidad principal |
|---|---|
| `accounts` | Usuario personalizado, roles, autenticación, wallet y eventos de seguridad |
| `blog` | Artículos, categorías, feeds, markdown y sitemap |
| `catalog` | Productos, planes, stock, reseñas, distribuidores y páginas públicas |
| `codes` | Clientes autorizados, asignación de correos, parsers IMAP y bots de códigos |
| `discord_bot` | Configuración, interacciones y notificaciones de Discord |
| `gestion` | JhelizTV/My Control: clientes, servicios, suscripciones, cobros y soporte |
| `livechat` | Conversaciones, mensajes y notificaciones del chat |
| `orders` | Carrito, pedidos, pagos, reservas, entrega e integración Telegram |
| `support` | Tickets y solicitudes de códigos desde la tienda |

Las migraciones permanecen dentro de cada aplicación. Mover modelos entre apps
cambiaría labels, permisos, content types y dependencias históricas.

## Capas actuales

- **Presentación:** Django Templates, admin, HTMX, JavaScript y CSS.
- **Controladores:** módulos `views.py`, `admin.py` y handlers de bots.
- **Dominio/persistencia:** modelos Django y operaciones transaccionales.
- **Integraciones:** Telegram, Discord, WhatsApp, IMAP, Mercado Pago y email.
- **Operaciones:** comandos Django, Docker Compose, Nginx y backups.

Algunos módulos mezclan estas capas. La futura reorganización debe separarlas
dentro de su app, conservando módulos fachada para imports existentes.

## Entradas del sistema

- HTTP WSGI/ASGI: `config.wsgi` y `config.asgi`.
- URLs tienda: `config.urls`.
- URLs JhelizTV: `config.urls_jheliztv`.
- Comandos: `*/management/commands/`.
- Bots long polling: comandos `run_*_bot`.
- Webhooks: rutas de pedidos, Discord y WhatsApp.
- Tareas periódicas: comandos de recordatorios y schedulers persistentes.

## Datos y archivos

- PostgreSQL es la base de producción.
- SQLite se admite únicamente como fallback local.
- `media/` contiene archivos públicos subidos.
- `private_media/` contiene comprobantes y archivos protegidos.
- `static/` contiene fuentes; `staticfiles/` es el resultado de `collectstatic`.
- Campos sensibles seleccionados usan cifrado mediante `FIELD_ENCRYPTION_KEY`.

## Contratos que deben conservarse

- Nombres de apps, modelos, tablas y migraciones.
- Namespaces y nombres de rutas.
- Nombres de comandos Django usados por Docker y cron.
- Imports serializados por migraciones, como `config.private_storage`.
- Payloads de webhooks y callback data de bots.
- Rutas de templates y estáticos.
- Variables de entorno y nombres de Docker Secrets.

## Componentes protegidos

JhelizTV/My Control, bots, autenticación, panel administrativo, modelos,
migraciones, cifrado, backups y configuración de producción se consideran
`PROTECTED/STABLE`. Una fase futura que necesite tocarlos requiere evaluación y
autorización explícita antes de modificar archivos.

