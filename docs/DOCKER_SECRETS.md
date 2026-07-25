# Migración a Docker Secrets

Esta configuración mantiene compatibilidad con `.env`, pero en producción
permite que Django, PostgreSQL y el bot lean credenciales desde archivos
montados en `/run/secrets`.

## Credenciales protegidas

- Clave secreta de Django.
- URL de PostgreSQL.
- Contraseña de PostgreSQL.
- Clave de cifrado de campos.
- Token del bot de códigos.
- Contraseñas IMAP de las dos casillas.

Cada servicio recibe solamente los archivos que necesita. El directorio
`secrets/` está ignorado por Git.

## Activación en producción

Ejecutar desde `/opt/jheliz-web`. Antes de empezar, confirmar que `.env`
contiene los valores actuales. La contraseña PostgreSQL debe conservarse: no
hay que generar otra durante esta migración.

```bash
cd /opt/jheliz-web
sudo cp .env ".env.before-secrets.$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 700 -o root -g root secrets

sudo sed -n 's/^SECRET_KEY=//p' .env | sudo tee secrets/django_secret_key.txt >/dev/null
sudo sed -n 's/^DATABASE_URL=//p' .env | sudo tee secrets/database_url.txt >/dev/null
sudo sed -n 's/^POSTGRES_PASSWORD=//p' .env | sudo tee secrets/postgres_password.txt >/dev/null
sudo sed -n 's/^FIELD_ENCRYPTION_KEY=//p' .env | sudo tee secrets/field_encryption_key.txt >/dev/null
sudo sed -n 's/^TELEGRAM_CODES_BOT_TOKEN=//p' .env | sudo tee secrets/telegram_codes_bot_token.txt >/dev/null
sudo sed -n 's/^CODES_IMAP_PASSWORD=//p' .env | sudo tee secrets/codes_imap_password.txt >/dev/null
sudo sed -n 's/^CODES_IMAP2_PASSWORD=//p' .env | sudo tee secrets/codes_imap2_password.txt >/dev/null

sudo chown root:root secrets/*.txt
sudo chmod 600 secrets/*.txt
```

Comprobar únicamente que todos tienen contenido, sin mostrarlo:

```bash
for archivo in secrets/*.txt; do
  if sudo test -s "$archivo"; then
    echo "OK: $archivo"
  else
    echo "VACÍO: $archivo"
  fi
done
```

Si una segunda cuenta IMAP no está configurada, se puede dejar su archivo con
un valor temporal como `NO_CONFIGURADA`; el bot no la usa mientras
`CODES_IMAP2_USER` esté vacío.

Actualizar y levantar la base y el bot con ambos archivos Compose:

```bash
git pull --ff-only origin main
sudo docker compose -f docker-compose.yml -f docker-compose.secrets.yml config --quiet
sudo docker compose -f docker-compose.yml -f docker-compose.secrets.yml up -d --force-recreate db
sudo docker compose -f docker-compose.yml -f docker-compose.secrets.yml --profile bot up -d --no-deps --build codes_bot
sudo docker compose -f docker-compose.yml -f docker-compose.secrets.yml logs --tail=50 codes_bot
```

Cuando el bot funcione, vaciar las credenciales antiguas del `.env`:

```bash
sudo sed -i \
  -e 's/^SECRET_KEY=.*/SECRET_KEY=/' \
  -e 's/^DATABASE_URL=.*/DATABASE_URL=/' \
  -e 's/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=/' \
  -e 's/^FIELD_ENCRYPTION_KEY=.*/FIELD_ENCRYPTION_KEY=/' \
  -e 's/^TELEGRAM_CODES_BOT_TOKEN=.*/TELEGRAM_CODES_BOT_TOKEN=/' \
  -e 's/^CODES_IMAP_PASSWORD=.*/CODES_IMAP_PASSWORD=/' \
  -e 's/^CODES_IMAP2_PASSWORD=.*/CODES_IMAP2_PASSWORD=/' \
  .env

sudo chmod 600 .env
sudo docker compose -f docker-compose.yml -f docker-compose.secrets.yml --profile bot up -d --no-deps --force-recreate codes_bot
sudo docker compose -f docker-compose.yml -f docker-compose.secrets.yml logs --tail=50 codes_bot
```

Para futuros reinicios o actualizaciones hay que usar siempre ambos archivos:

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.secrets.yml --profile bot up -d
```

## Verificación

El contenedor debe contener rutas `_FILE`, nunca los valores:

```bash
sudo docker inspect jheliz-web-codes_bot-1 \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep '_FILE='
```

No ejecutar `cat`, `grep` ni `docker inspect` buscando valores de tokens o
contraseñas.

## Reversión

Si el bot no inicia, restaurar la copia creada al principio y volver al Compose
normal:

```bash
cd /opt/jheliz-web
sudo cp .env.before-secrets.FECHA-HORA .env
sudo docker compose up -d --force-recreate db
sudo docker compose --profile bot up -d --no-deps --build codes_bot
```
