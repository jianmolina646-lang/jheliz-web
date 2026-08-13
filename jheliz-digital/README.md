# Jheliz Digital

Plataforma independiente para controlar cuentas digitales completas de Netflix,
Prime Video, Disney+, Max, Spotify y otros servicios. No administra perfiles ni
cupos internos.

## Estado

Fase 4 completada: además del catálogo, inventario cifrado y ventas anónimas, incluye
reposiciones trazables entre cuentas completas. Ninguna operación almacena identidad
ni datos personales del comprador.

## Desarrollo local

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

La aplicación usa SQLite solamente para desarrollo cuando `POSTGRES_HOST` está
vacío. Producción utilizará una base PostgreSQL exclusiva.

## Variables de entorno

- `DJANGO_SECRET_KEY`: clave privada obligatoria en producción.
- `DJANGO_DEBUG`: debe ser `false` en producción.
- `DJANGO_ALLOWED_HOSTS`: hosts separados por comas.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: orígenes HTTPS separados por comas.
- `ACCOUNT_CREDENTIAL_KEY`: clave Fernet exclusiva para cifrar las contraseñas del
  inventario. Debe conservarse fuera de Git y respaldarse de forma segura.
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
  `POSTGRES_PASSWORD`: conexión PostgreSQL.

El archivo `.env.example` nunca contiene secretos reales.

## Pruebas

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Despliegue con Docker

La configuración de producción usa PostgreSQL y publica la aplicación únicamente en
`127.0.0.1:8200`, detrás de Nginx. Los secretos se guardan en `.env` exclusivamente
en el servidor.

```bash
docker compose -f compose.production.yml up -d --build
docker compose -f compose.production.yml ps
```

La plantilla Nginx se encuentra en `deploy/nginx/jheliz-digital.conf`. Este despliegue
no comparte base, volumen ni puerto con JhelizTV o Mail Control.

El servicio opcional `backup` crea copias cifradas en MEGA con retención diaria y
mensual. Su operación y verificación están documentadas en `docs/backups.md`.

Nginx protege el login y la aplicación contra intentos y ráfagas excesivas. Los
límites activos y la precaución necesaria al usar proxy Cloudflare se describen en
`docs/rate-limiting.md`.

## Límites de la Fase 4

Esta fase administra servicios, cuentas completas, ventas anónimas y reposiciones;
no administra perfiles, cupos ni clientes. Todavía no implementa revelado de
credenciales. El proyecto continúa sin desplegar y no se modificó DNS, VPS ni ningún
sistema existente.

La referencia de pago acepta únicamente una etiqueta segura o los últimos cuatro
dígitos. Nunca se deben guardar números completos de tarjeta, fechas de vencimiento
ni CVV.
