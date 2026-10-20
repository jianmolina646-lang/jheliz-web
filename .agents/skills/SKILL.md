# Skill — Política y operación de Jheliz Web

> **Quién lee esto**: Devin (o cualquier IDE-agent) cuando arranca una sesión sobre este repo.
> **Por qué existe**: en mayo 2026 se descubrió que ~1.300 líneas de código habían sido editadas directamente en el VPS (`/srv/jheliz/`) sin pasar por Git. Causó conflictos al hacer PRs nuevas y casi rompe la DB. Ese drift se consolidó en las PRs #161-#166 y este SKILL define las reglas para que **no vuelva a pasar**.

---

## 1. Datos básicos del proyecto

| | |
|---|---|
| Repo | `https://github.com/jianmolina646-lang/jheliz-web` |
| Producción | `https://ecormecejhelizstore.com/` |
| Admin panel | `https://ecormecejhelizstore.com/panel-jheliz-2026/` (Django Unfold) |
| VPS | DigitalOcean — `144.172.111.120` |
| Source en VPS | `/srv/jheliz/` |
| Deploy | Docker Compose (servicios: `web`, `db`) |
| Email sender | `ecomercejheliz@gmail.com` (verificado en Brevo) |
| Email backend | `orders.brevo_backend.BrevoEmailBackend` (HTTP, no SMTP) |
| Webhook MP | `https://ecormecejhelizstore.com/pedidos/webhooks/mercadopago/` (notar: `/pedidos/`, **no** `/orders/`) |

---

## 2. ⛔ Regla #1 — NO editar archivos directamente en el VPS

**Prohibido** tocar archivos en `/srv/jheliz/` con `vi`, `nano`, `sed`, `cat > archivo.py`, copy-paste por SSH, etc. **Excepciones**:

- `/srv/jheliz/.env` — vars de entorno (no se commitea por seguridad).
- `/srv/jheliz/.env.bak.*` — backups del `.env`.
- `/srv/jheliz/media/` — uploads de usuarios.
- `/srv/jheliz/staticfiles/` — assets recolectados por collectstatic (se regeneran solos).

**Cualquier otro cambio** (modelos, views, templates, migrations, settings, scripts) **debe ir por PR**. Sin excepciones.

### Por qué

- `/srv/jheliz/` es un clone de Git. Si alguien hace `git reset --hard` o si la imagen Docker se rebuildeza desde cero, **todo el código edit-in-place se pierde**.
- Los archivos modificados sin commit causan conflictos con futuras PRs basadas en `main`.
- Las migraciones de DB que se aplican localmente pero no están en el repo dejan la DB **inconsistente** con el código: el próximo `makemigrations` puede generar migraciones contradictorias.

---

## 3. ✅ Workflow correcto para cualquier cambio de código

### 3a. Flujo normal (no urgente)

```
1. Cloná el repo en tu máquina (o usá el del VM de Devin: /home/ubuntu/repos/jheliz-web).
2. Creá una rama nueva:
     git checkout -b devin/$(date +%s)-descripcion-corta
3. Editá los archivos. Para nuevos modelos: python manage.py makemigrations.
4. Corré tests localmente:
     python manage.py test catalog orders accounts livechat support --keepdb
5. Commit + push:
     git add -A && git commit -m "feat(area): descripción corta"
     git push -u origin devin/$(date +%s)-...
6. Abrí PR contra `main` (NUNCA contra otra rama de feature — ver §3c).
7. Esperar a que CI pase (verde).
8. Pedir al usuario que mergee. NUNCA mergear sin que CI esté verde.
9. Después del merge:
     - VPS: ver §4 (rebuild de la imagen).
     - Si hubo migraciones nuevas: ver §5.
```

### 3b. Hotfix urgente (algo ROTO en producción)

Si el sitio está caído o hay un 500 generalizado y no hay tiempo para PR + CI:

```
1. Identificar el archivo problemático y la línea exacta del fix.
2. Editar SOLO ese archivo en /srv/jheliz/. Documentar en un comentario:
     # HOTFIX 2026-MM-DD aplicado en vivo — ver TODO/PR pendiente.
3. Reiniciar el container afectado:
     docker compose restart web
4. Verificar que la web vuelve a estar OK.
5. **MISMO DÍA / DÍA SIGUIENTE**: abrir PR con el mismo cambio,
   mergear, rebuild la imagen.
6. Verificar en el VPS que `git status` no muestra el archivo modificado
   localmente (porque ahora el cambio ya está en `main`).
```

**Si dejás un hotfix en vivo sin convertirlo a PR en <24h, estás generando drift y este SKILL existe específicamente para evitarlo.**

### 3c. Bases de PRs

- Para una PR independiente: `base = main`.
- **NUNCA** abrir una PR con `base = otra rama de feature` salvo que sea estrictamente necesario (ej. dependencias entre PRs que se mergearán juntas).
- Si lo hacés: cuando la rama base se mergea a main, tenés que **manualmente reapuntar** la PR dependiente a `main` (botón "Edit" en el título de la PR → cambiar base branch). Si no lo hacés, GitHub puede mergearla contra la rama base ya muerta y tu cambio **queda fuera de main** (le pasó a la PR #165 — se "mergeó" pero nunca llegó a main, hubo que reabrirla como #166).
- Si en duda, abrir contra `main` y resolver conflictos manualmente.

---

## 4. Rebuild de la imagen Docker en el VPS (después de mergear PR)

```
ssh root@144.172.111.120
cd /srv/jheliz
git pull origin main
docker compose build web        # rebuildeza la imagen con el código nuevo
docker compose up -d web        # recrea el container con la imagen nueva
sleep 10
docker compose ps               # verificar que el container está "healthy"
curl -sk https://ecormecejhelizstore.com/ -o /dev/null -w "HTTP %{http_code}\n"
```

**`docker compose restart` NO sirve para aplicar código nuevo** — solo reinicia el container actual con la imagen vieja. Si querés código nuevo: **build + up**.

`docker compose restart` SÍ se usa cuando solo cambiás `.env` (vars de entorno) sin código. Y aún así, si cambiaste `env_file: .env` hay que **recrear** (`docker compose up -d --force-recreate web`), porque `restart` no recarga env files.

---

## 5. Migraciones de DB

Las migraciones de Django se aplican **dentro del container**. Nunca se ejecutan migraciones a mano contra Postgres por fuera de Django.

### Aplicar migraciones después de mergear PR con `makemigrations`

```
ssh root@144.172.111.120
cd /srv/jheliz
git pull origin main
docker compose build web
# El comando de la imagen (ver docker-compose.yml) hace `migrate` automáticamente al arrancar.
# Pero si querés forzarlo antes:
docker compose run --rm web python manage.py migrate
docker compose up -d --force-recreate web
```

### Rollback de migración (raro pero útil)

```
docker compose run --rm web python manage.py migrate <app> <numero_previo>
```

### Nunca

- Editar tablas a mano con `psql` salvo en emergencias de soporte (ej. revertir un cambio de email manual). Si lo hacés, documentar en un comentario en el PR/issue.
- Aplicar migraciones desde fuera del container.

---

## 6. Verificar que el VPS está sincronizado con `main`

Después de cualquier rebuild, **siempre** verificar:

```
ssh root@144.172.111.120
cd /srv/jheliz
git fetch origin
git status                      # debe decir "nothing to commit, working tree clean"
git log --oneline -3            # último commit debe coincidir con origin/main
git rev-parse HEAD              # SHA debe ser el último de origin/main
```

Si `git status` muestra **archivos modificados**, hay drift de nuevo. Hay que:
1. Revisar qué cambió: `git diff`.
2. Si es legítimo: backupear (`cp archivo archivo.bak`), abrir PR con el cambio, mergear, hacer `git checkout -- archivo` para descartar la modificación local.
3. Si no es legítimo: descartarlo con `git checkout -- archivo` después de confirmar que no rompe nada.

**En este repo NUNCA debe quedar nada uncommitted en `/srv/jheliz/` salvo el `.env`.**

---

## 7. Vars críticas del `.env` (no commitearlas)

Todas viven en `/srv/jheliz/.env`. Si se pierden, hay backup en `/srv/jheliz/.env.bak.*` (timestamped).

| Variable | Para qué |
|---|---|
| `DATABASE_URL` | Conexión a Postgres del container `db`. |
| `SECRET_KEY` | Django session/CSRF. **No regenerar** — invalida sessions activas. |
| `FIELD_ENCRYPTION_KEY` | Cifra `delivered_credentials` (Fernet, 44 chars urlsafe-base64). **Si se pierde, las credenciales cifradas guardadas se vuelven ilegibles.** |
| `EMAIL_BACKEND` | Debe ser `orders.brevo_backend.BrevoEmailBackend` en prod (no `django.core.mail.backends.console.EmailBackend`). |
| `BREVO_API_KEY` | API key de Brevo para mandar correos HTTP. |
| `DEFAULT_FROM_EMAIL` | `Jheliz <ecomercejheliz@gmail.com>` (sender verificado en Brevo). |
| `MERCADOPAGO_ACCESS_TOKEN` | Token de prod MP (`APP_USR-...`, ~75 chars). |
| `MERCADOPAGO_PUBLIC_KEY` | Public key MP (no se usa hoy en el backend, declarada por compatibilidad). |
| `MERCADOPAGO_WEBHOOK_SECRET` | Secret HMAC para validar webhooks (~64 chars hex). |
| `TELEGRAM_BOT_TOKEN` | Bot para notificar al admin cada pedido. |
| `TELEGRAM_ADMIN_CHAT_ID` | Chat de Telegram donde llegan las notificaciones. |

---

## 8. Email — SMTP saliente bloqueado, usar HTTP

**Importante**: el VPS (DigitalOcean/Hostinger) **bloquea puertos SMTP salientes** (25, 465, 587, 2525). Configurar `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend` no funciona — todos los correos fallan con `[Errno 101] Network is unreachable`.

**Solución usada**: `orders.brevo_backend.BrevoEmailBackend` (HTTP API de Brevo sobre HTTPS 443, que NO está bloqueado). Implementado en `orders/brevo_backend.py`. Plan free de Brevo: 300 emails/día (sobra para Jheliz).

Si en el futuro hay que cambiar de provider:
- **Resend** (3000/mes free) — API HTTP también.
- **Mailgun** (100/día free después de trial) — pide tarjeta.
- **SendGrid** (no recomendado — bloquea cuentas free agresivamente).

**Nunca** intentar volver a SMTP en este VPS. Sería tirar el trabajo.

---

## 9. Mercado Pago — configuración

Tres vars en `.env`. Para obtenerlas:

1. https://www.mercadopago.com.pe/developers/panel/app
2. Click en la app **JHELIZTEAM** (User ID `1804582803`).
3. **Credenciales → Producción** → copiar Access Token (~75 chars) y Public Key.
4. **Webhooks → Producción** → URL = `https://ecormecejhelizstore.com/pedidos/webhooks/mercadopago/`, evento "Pagos" → Save → copiar "Clave secreta" (~64 chars hex).

⚠️ URL del webhook = `/pedidos/webhooks/...` (no `/orders/...`, porque las URLs de `orders/` están montadas en `/pedidos/` en `config/urls.py`).

### Test rápido

```
docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings web python -c '
import django; django.setup()
from orders import mercadopago_client
print("is_configured:", mercadopago_client.is_configured())
'
```

Si devuelve `False`, las vars no están en el container — probablemente faltó `force-recreate` (ver §4).

---

## 10. Tests del repo

```
# Local (desde el VM de Devin):
cd /home/ubuntu/repos/jheliz-web
python manage.py test catalog orders accounts livechat support --keepdb

# Con CI verde, también pasan en GitHub Actions automáticamente.
```

Tests críticos:
- `catalog/tests.py` — productos, planes, vistas.
- `orders/tests.py` — checkout, carrito, wallet payment, MP webhook signature.
- `accounts/tests.py` — wallet, distributor approval.
- `livechat/tests.py` — chat widget.
- `support/tests.py` — tickets, code requests.

**No hacer commits con tests rotos en `main`**. CI los rechaza con red status pero igual: corre los tests localmente antes de pushear.

---

## 11. Acceso al VPS

- SSH como root: `ssh root@144.172.111.120`.
- Password: en secret `JHELIZ_VPS_ROOT_PASSWORD` (level: org, no inline en código).
- Trick para automatizar: `sshpass -p "$JHELIZ_VPS_ROOT_PASSWORD" ssh -o StrictHostKeyChecking=no root@144.172.111.120 '<comando>'`.

**Nunca** pegar el password en chat / logs / commits / SKILL files / código.

---

## 12. Errores comunes y cómo diagnosticarlos

### Error 500 al "Entregar pedido" en admin

Causa más probable: `FIELD_ENCRYPTION_KEY` vacío en `.env`.

Diagnóstico:
```
docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings web python -c '
from django.conf import settings
print(len(settings.FIELD_ENCRYPTION_KEY or ""))
'
```

Fix: generar una llave Fernet (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`), meterla en `.env`, `docker compose up -d --force-recreate web`.

### Correos no llegan al cliente

1. Ver `EmailLog` en admin (`/panel-jheliz-2026/orders/emaillog/`): si `status=sent` pero el cliente no recibe → backend está en `console` (no manda) o Brevo está mal configurado.
2. Verificar `EMAIL_BACKEND` en `.env`: debe ser `orders.brevo_backend.BrevoEmailBackend`.
3. Verificar `BREVO_API_KEY` está set.
4. Test rápido:
   ```
   docker compose exec -T -e DJANGO_SETTINGS_MODULE=config.settings web python -c '
   import django; django.setup()
   from django.core.mail import send_mail
   send_mail("test", "test body", "ecomercejheliz@gmail.com", ["destinatario@dominio.com"])
   '
   ```

### "Mercado Pago aún no está configurado" al cliente en checkout

Las 3 vars de MP están vacías. Ver §9.

### Container "unhealthy" después de deploy

Ver logs: `docker compose logs web --tail=50`. Causas frecuentes:
- Migración rota → `docker compose run --rm web python manage.py migrate`.
- Settings inválido → revisar `.env` y comparar con `config/settings.py`.
- DB down → `docker compose ps db` debe decir "healthy".

### Web carga lento

Ver `docker stats` para CPU/RAM del container. Si CPU al 100%: probablemente una query N+1 en una vista nueva. Activar `DEBUG=True` un momento, abrir la vista, mirar el Django Debug Toolbar para ver queries.

**No** dejes `DEBUG=True` activo más de los 30 segundos del debug — expone tracebacks completos.

---

## 13. ¿Qué hacer si encontrás drift de nuevo?

Drift = archivos modificados en `/srv/jheliz/` que no están en `main`.

```
ssh root@144.172.111.120 'cd /srv/jheliz && git status'
```

Si hay drift:

1. **NO** hacer `git reset --hard` ni `git checkout -- .` automático. Podés perder cambios legítimos.
2. **Backupear todo** con tar:
   ```
   ssh root@144.172.111.120 'cd /srv && tar czf jheliz-vps-drift-$(date +%Y%m%d-%H%M%S).tar.gz $(cd jheliz && git status --porcelain | awk "{print \"jheliz/\" \$2}")'
   ```
3. **Bajar el diff** a tu máquina, revisarlo archivo por archivo.
4. **Dividir por features** y abrir PRs separadas (no un megacommit) — facilita review.
5. Cada PR debe pasar CI antes de mergear.
6. Después de mergear todas: en el VPS, `git pull` y verificar que `git status` queda limpio (§6).

Ver PRs #161-#166 como ejemplo de cómo se hizo en mayo 2026 (1.314 líneas drift consolidadas en 6 PRs).

---

## 14. Branches del repo

- `main` — rama de producción. **Solo se mergea vía PR con CI verde.** Nadie pushea directo.
- `devin/<timestamp>-<descripcion>` — branches de feature de Devin. Cleanup después de merge.

Nunca usar `master`, `dev`, `staging` salvo que sea explícitamente decidido.

---

## 15. PRs históricas relevantes

Para entender decisiones de diseño:

| PR | Qué |
|---|---|
| #61 / #63 | Auto-entrega + reserva de stock al pagar (cifrado de credenciales). |
| #62 | 7 mejoras quick-win en panel admin. |
| #123-#125 | Live chat propio dentro del admin (sin servicios externos). |
| #160 | Backend HTTP de Brevo (workaround a SMTP bloqueado). |
| #161-#166 | Consolidación del drift VPS mayo 2026 (PWA, i18n, distributor portal, wallet, checkout integration, política). |
