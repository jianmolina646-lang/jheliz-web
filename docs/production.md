# Producción

## Principios

- No desplegar desde un árbol Git sucio.
- No modificar `.env`, secretos o datos durante una actualización de código.
- Verificar un backup restaurable antes de cambios de riesgo.
- Usar el mismo conjunto de archivos Compose en despliegue y rollback.
- No ejecutar simultáneamente dos proyectos que publiquen el mismo puerto.

## Servicios base

Validar primero la configuración renderizada:

```bash
docker compose config
```

Iniciar base y web:

```bash
docker compose up -d db web
docker compose ps
docker compose logs --tail=100 web db
```

El servicio `web` ejecuta en orden:

1. `python manage.py migrate --noinput`.
2. `python manage.py collectstatic --noinput`.
3. Gunicorn en `0.0.0.0:8000`.

El puerto se publica solamente en `127.0.0.1:8000`; Nginx es la entrada pública.

## JhelizTV aislado

El override selecciona `config.settings_jheliztv` y la base lógica
`jheliz_control`:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.jheliztv.yml \
  config
```

Usa exactamente esos mismos `-f` en `up`, `ps`, `logs` y rollback.

## Perfiles

```bash
# Bots de tienda y códigos
docker compose --profile bot up -d

# Alertas de My Control y scheduler WhatsApp
docker compose --profile control-alerts up -d

# Backup cifrado
docker compose --profile backup up -d backup
```

Consulta [services.md](services.md) antes de habilitar un perfil. Un token vacío
puede hacer que un comando termine inmediatamente aunque el build sea correcto.

## Verificación posterior

```bash
docker compose ps
docker compose logs --tail=100 web
curl -fsS -o /dev/null http://127.0.0.1:8000/
```

Además se debe verificar:

- Dominio público y certificado TLS.
- Login y página principal sin mutar datos.
- Conectividad PostgreSQL.
- Estado de bots y workers habilitados.
- Última ejecución de tareas programadas.
- Último backup cifrado y su presencia remota.

## Nginx y TLS

`deploy/nginx.conf.example` es referencia, no debe copiarse ciegamente sobre una
configuración activa. Antes de recargar:

```bash
nginx -t
```

Conservar redirects, hosts, rutas privadas y publicación de estáticos existente.

## Migraciones

Antes de desplegar una versión con migraciones:

```bash
python manage.py showmigrations --plan
python manage.py makemigrations --check --dry-run
```

No ejecutar migraciones destructivas ni revertir migraciones aplicadas sin un
plan específico de datos y rollback.

## Secretos

Producción admite `.env` y overrides con Docker Secrets. La guía de transición
está en `docs/DOCKER_SECRETS.md`. Nunca usar `docker compose config` en una salida
pública, porque puede expandir valores secretos.

## Rollback

Consulta [rollback.md](rollback.md). El rollback de código y el rollback de base
de datos son operaciones distintas; no se debe restaurar una base únicamente
porque se revierte un commit.

