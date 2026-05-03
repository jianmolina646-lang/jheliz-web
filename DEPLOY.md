# Deploy de Jheliz — `jhelizservicestv.xyz`

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
- `ALLOWED_HOSTS=jhelizservicestv.xyz,www.jhelizservicestv.xyz`
- `SITE_URL=https://jhelizservicestv.xyz`
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
    server_name jhelizservicestv.xyz www.jhelizservicestv.xyz;

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
sudo certbot --nginx -d jhelizservicestv.xyz -d www.jhelizservicestv.xyz
```

### 1.5 DNS en Hostinger

Entra a hPanel → Dominios → DNS/Nameservers. Apunta:

- `A` `@` → IP pública del VPS
- `A` `www` → IP pública del VPS

Espera 5–30 min a que propague.

### 1.6 Webhook de Mercado Pago

En https://www.mercadopago.com.pe/developers/panel → tu app JHELIZ → **Webhooks**:

- URL: `https://jhelizservicestv.xyz/pedidos/webhooks/mercadopago/`
- Eventos: `payment`

---

## 2) Si tienes **Hosting compartido** en Hostinger (NO corre Django)

Hosting compartido solo corre PHP/Node/estáticos. Django necesita Python + Gunicorn, así que la alternativa más sencilla es:

- **Fly.io** → gratis hasta ~3 máquinas pequeñas. Muy rápido de deployar.
- Apuntas `jhelizservicestv.xyz` desde Hostinger hacia Fly.io por DNS.

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
  DEFAULT_FROM_EMAIL='Jheliz <no-reply@jhelizservicestv.xyz>'
fly deploy
```

### 2.3 Dominio personalizado

```bash
fly certs create jhelizservicestv.xyz
fly certs create www.jhelizservicestv.xyz
fly certs show jhelizservicestv.xyz
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

- [ ] `jhelizservicestv.xyz` responde con HTTPS y muestra el home
- [ ] `/jheliz-admin/` carga y puedes entrar como superuser
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
