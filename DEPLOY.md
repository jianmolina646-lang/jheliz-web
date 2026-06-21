# Deploy de VirtualidadSP — `ecormecejhelizstore.com`

Esta guía cubre dos escenarios: **VPS Hostinger** (o cualquier VPS Linux) y **Fly.io** (gratis para empezar, tráfico bajo). Elige una según el plan que tengas.

---

## 1) Si tienes **VPS** de Hostinger (Ubuntu 22.04/24.04)

Requisitos: acceso SSH como root o usuario con sudo; dominio apuntando al IP del VPS.

### 1.1 Prepara el servidor

```bash
sudo apt update && sudo apt install -y git docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
sudo systemctl enable --now docker
```

### 1.2 Clona el repo

```bash
sudo mkdir -p /srv && cd /srv
sudo git clone https://github.com/jianmolina646-lang/jheliz-web.git jheliz
cd jheliz
sudo cp .env.example .env
sudo nano .env   # rellena SECRET_KEY, MERCADOPAGO_*, SMTP, TELEGRAM_*, etc.
```

Campos obligatorios en `.env`:

- `SECRET_KEY` → genera uno con `python -c 'import secrets;print(secrets.token_urlsafe(64))'`
- `DEBUG=False`
- `ALLOWED_HOSTS=ecormecejhelizstore.com,www.ecormecejhelizstore.com`
- `SITE_URL=https://ecormecejhelizstore.com`
- `DATABASE_URL=postgres://jheliz:jheliz@db:5432/jheliz` (o el Postgres que uses)
- `MERCADOPAGO_ACCESS_TOKEN` y `MERCADOPAGO_PUBLIC_KEY` (producción)
- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- `TELEGRAM_BOT_TOKEN` y `TELEGRAM_ADMIN_CHAT_ID` (opcional)

### 1.3 Arranca con Docker Compose

```bash
sudo docker compose up -d --build
sudo docker compose exec web python manage.py createsuperuser
# si quieres el bot también:
sudo docker compose --profile bot up -d
```

### 1.4 Nginx + HTTPS con Let's Encrypt

Crea `/etc/nginx/sites-available/jheliz`:

```nginx
server {
    listen 80;
    server_name ecormecejhelizstore.com www.ecormecejhelizstore.com;

    location /.well-known/acme-challenge/ { root /var/www/certbot; }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Real-IP $remote_addr;
    }

    client_max_body_size 20M;
}
```

```bash
sudo ln -s /etc/nginx/sites-available/jheliz /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d ecormecejhelizstore.com -d www.ecormecejhelizstore.com
```

### 1.5 DNS en Hostinger

Entra a hPanel → Dominios → DNS/Nameservers. Apunta:

- `A` `@` → IP pública del VPS
- `A` `www` → IP pública del VPS

Espera 5–30 min a que propague.

### 1.6 Webhook de Mercado Pago

En https://www.mercadopago.com.pe/developers/panel → tu app VIRTUALIDADSP → **Webhooks**:

- URL: `https://ecormecejhelizstore.com/pedidos/webhooks/mercadopago/`
- Eventos: `payment`

### 1.7 Bot de códigos (`@codigosjheliz_bot`)

Bot separado (app `codes`) que entrega códigos de Netflix por IMAP. Corre como
el servicio `codes_bot` del `docker-compose.yml` (long-polling, `restart: unless-stopped`).

1. Completá en `.env` (ya están en `.env.example`):
   ```
   TELEGRAM_CODES_BOT_TOKEN=        # token de @BotFather para @codigosjheliz_bot
   TELEGRAM_CODES_ADMIN_CHAT_ID=    # tu chat ID (de @userinfobot)
   CODES_IMAP_HOST=imap.gmail.com
   CODES_IMAP_PORT=993
   CODES_IMAP_USER=codigosjheliz@gmail.com
   CODES_IMAP_PASSWORD=             # contraseña de aplicación de 16 caracteres (NO la normal)
   CODES_LOOKBACK_MINUTES=30
   ```
   La contraseña de aplicación se genera en https://myaccount.google.com/apppasswords
   (requiere 2FA activado en esa cuenta de Gmail).

2. Levantá el servicio (junto al resto del perfil `bot`):
   ```bash
   sudo docker compose --profile bot up -d --build codes_bot
   ```

3. Verificá que esté corriendo y mirá los logs:
   ```bash
   sudo docker compose ps codes_bot
   sudo docker compose logs -f codes_bot   # debe imprimir "Bot de códigos arrancando…"
   ```

4. Probalo desde Telegram: mandá `/start` a @codigosjheliz_bot. Como admin
   tenés `/clientes`, `/asignar <ID o @usuario> <correo>` y `/quitar`.

> Al volver a deployar, `docker compose --profile bot up -d --build` reconstruye
> y reinicia también `codes_bot`. No necesita nginx (no expone puertos).

---

## 2) Si tienes **Hosting compartido** en Hostinger (NO corre Django)

Hosting compartido solo corre PHP/Node/estáticos. Django necesita Python + Gunicorn, así que la alternativa más sencilla es:

- **Fly.io** → gratis hasta ~3 máquinas pequeñas. Muy rápido de deployar.
- Apuntas `ecormecejhelizstore.com` desde Hostinger hacia Fly.io por DNS.

### 2.1 Instala flyctl

```bash
curl -L https://fly.io/install.sh | sh
fly auth signup
```

### 2.2 Lanza la app

```bash
cd jheliz-web
fly launch --no-deploy --copy-config --name jheliz-web --region gig
fly volumes create jheliz_data --size 1 --region gig
fly secrets set \
  SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(64))')" \
  MERCADOPAGO_ACCESS_TOKEN=APP_USR-... \
  MERCADOPAGO_PUBLIC_KEY=APP_USR-... \
  TELEGRAM_BOT_TOKEN=... \
  TELEGRAM_ADMIN_CHAT_ID=... \
  EMAIL_HOST=smtp-relay.brevo.com \
  EMAIL_HOST_USER=... \
  EMAIL_HOST_PASSWORD=... \
  DEFAULT_FROM_EMAIL='VirtualidadSP <no-reply@ecormecejhelizstore.com>'
fly deploy
```

### 2.3 Dominio personalizado

```bash
fly certs create ecormecejhelizstore.com
fly certs create www.ecormecejhelizstore.com
fly certs show ecormecejhelizstore.com
```

Fly te dará un par de registros DNS. En Hostinger hPanel → DNS apunta:

- `A` `@` → IP v4 que te dio Fly
- `AAAA` `@` → IP v6 que te dio Fly
- `CNAME` `www` → `jheliz-web.fly.dev`

### 2.4 Superuser + seed

```bash
fly ssh console
python manage.py createsuperuser
python manage.py seed_catalog
```

### 2.5 Bot de Telegram

Hay dos modos. Webhook es lo recomendado en producción (sin proceso extra).

**Webhook (recomendado):**

1. En `.env` define `TELEGRAM_WEBHOOK_SECRET` con un token aleatorio:
   ```bash
   python -c 'import secrets;print(secrets.token_urlsafe(32))'
   ```
2. Reinicia `web` para que lo lea.
3. Registra el webhook contra Telegram:
   ```bash
   docker compose exec web python manage.py setup_telegram_webhook
   ```
4. Verifica con `--info`:
   ```bash
   docker compose exec web python manage.py setup_telegram_webhook --info
   ```

**Polling (alternativa o dev):**

```bash
docker compose --profile bot up -d telegram_bot
```

**Resumen diario 8am Perú** (cron del host):

```cron
0 13 * * * cd /srv/jheliz && /usr/bin/docker compose exec -T web python manage.py telegram_daily_summary
```

(13:00 UTC = 08:00 hora Perú.)

---

## 3) Checklist post-deploy

- [ ] `ecormecejhelizstore.com` responde con HTTPS y muestra el home
- [ ] `/panel-jheliz-2026/` carga y puedes entrar como superuser
- [ ] Carga al menos un Category + Product + Plan desde el admin
- [ ] `python manage.py seed_catalog` si quieres ejemplos
- [ ] Haz una compra de prueba con Mercado Pago (tarjeta TEST)
- [ ] Verifica que el correo "Recibimos tu pedido" llega
- [ ] Webhook de MP registrado en el panel MP
- [ ] Bot de Telegram responde `/start`
- [ ] Cambiar estado de un pedido en el admin envía correo

---

## 4) Backups

- **Postgres** (VPS): `docker compose exec db pg_dump -U jheliz jheliz > backup.sql` (diario con cron)
- **Fly.io**: habilita volúmenes + snapshot automático: `fly volumes snapshots list`
- **Media/imágenes**: rsync de `./media` a un bucket S3/R2.

---

## 5) Migración SEO desde el dominio anterior (`jhelizservicestv.xyz` → `ecormecejhelizstore.com`)

Si vienes del dominio anterior y querés transferir el ranking de Google sin perder
tráfico, seguí estos 6 pasos en orden. **No** apagues el dominio viejo hasta que
Google haya migrado el ranking (mínimo 6 meses, idealmente para siempre).

### 5.1 Verificar ambos dominios en Google Search Console
1. Entrá a https://search.google.com/search-console.
2. Agregá la propiedad nueva `ecormecejhelizstore.com` (verificación por DNS TXT).
3. La propiedad vieja `jhelizservicestv.xyz` debe seguir verificada — no la borres.

### 5.2 Configurar redirects 301 (página por página, no a home)
- El bloque server "Migración SEO" en `deploy/nginx.conf.example` ya hace el 301
  permanente preservando `$request_uri`. Esto es **clave**: cada URL vieja redirige
  a su equivalente nueva (ej. `/productos/netflix/` → `/productos/netflix/`), no
  todas a la home. Redirigir a la home pierde el ranking de páginas internas.
- Verificalo con `curl`:
  ```bash
  curl -I https://jhelizservicestv.xyz/productos/netflix/
  # Esperado: HTTP/2 301
  # Location: https://ecormecejhelizstore.com/productos/netflix/
  ```

### 5.3 Update canonical URLs
- `config/settings.py` ya tiene `SITE_URL=https://ecormecejhelizstore.com` (vía .env).
- Verificá que `<link rel="canonical">` en cada página apunte al dominio nuevo.

### 5.4 "Change of Address" tool en Search Console
1. Search Console → Settings → **Change of Address**.
2. Source: `jhelizservicestv.xyz`, Destination: `ecormecejhelizstore.com`.
3. Google va a verificar que los redirects 301 funcionen y migra el ranking.
4. Esto **acelera** la transferencia (si no lo usás, Google también migra pero más lento).

### 5.5 Mantener los redirects 301 durante mínimo 6 meses
- Google necesita tiempo para reindexar todas las URLs. Si quitás los redirects
  antes, perdés el ranking acumulado. Recomendación: dejar el bloque server de
  migración en nginx **para siempre** (cuesta 0 mantenerlo).

### 5.6 Resubmit sitemap a la propiedad nueva
1. En Search Console (propiedad nueva) → Sitemaps → submit `https://ecormecejhelizstore.com/sitemap.xml`.
2. Monitoreá el coverage report durante las próximas 4-8 semanas para confirmar
   que las URLs nuevas se indexan y las viejas se "consolidan" en las nuevas.

### Errores comunes (no los hagas)
- **Redirigir 302 en vez de 301**: Google no transfiere ranking con 302 (es temporal).
- **Redirigir todo a la home**: pierde ranking de páginas internas. Siempre `$request_uri`.
- **Apagar el dominio viejo en menos de 6 meses**: pierde ranking acumulado.
- **Saltarse "Change of Address"**: la migración funciona igual pero más lento.
- **No actualizar canonical URLs**: Google ve señales contradictorias y demora.
