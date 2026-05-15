# Backups de Jheliz Web

Scripts para hacer backup diario de la **base de datos**, los **archivos subidos por usuarios** (`media/`) y el **`.env`** del VPS — y para restaurar desde uno de esos backups.

## Archivos

| Archivo | Qué hace |
|---|---|
| `deploy/backup.sh` | Genera un `.tar.gz` con `db.sql` + `media.tar.gz` + `dotenv` + `README.txt`. Rota viejos. Opcional: cifra con GPG y sube a Drive con `rclone`. |
| `deploy/restore.sh` | Toma uno de esos bundles y restaura DB + media + `.env`. Pide confirmación explícita. |

## Estructura en disco (VPS)

```
/srv/backups/
├── daily/
│   ├── jheliz-20260513-030001.tar.gz
│   ├── jheliz-20260514-030001.tar.gz
│   └── ... (últimos 7 días)
└── weekly/
    ├── jheliz-20260512-030001.tar.gz   # lunes
    └── ... (últimas 4 semanas)
```

## Configuración (`/etc/jheliz-backup.env`)

Override de defaults sin tocar el script:

```bash
# /etc/jheliz-backup.env  (chmod 600 — contiene secrets)
GPG_PASSPHRASE=...                 # cifra el bundle final con AES256
RCLONE_REMOTE=drive:JhelizBackups  # sube a Google Drive (carpeta nueva)
KEEP_DAILY=7                       # default 7
KEEP_WEEKLY=4                      # default 4
```

Sin `GPG_PASSPHRASE`: el bundle queda en texto plano (con `.env` y credenciales legibles). Recomendado tenerlo siempre.

Sin `RCLONE_REMOTE`: solo se guarda local en `/srv/backups/`. Si el VPS muere, perdés el backup. Recomendado configurar Drive.

## Programar (cron de root)

```bash
sudo crontab -e
# Agregar:
0 3 * * * /srv/jheliz/deploy/backup.sh >> /var/log/jheliz-backup.log 2>&1
```

Logs en `/var/log/jheliz-backup.log`.

## Configurar rclone con Google Drive

```bash
sudo apt-get install -y rclone
sudo rclone config
# n) new remote
# name> drive
# type> drive
# client_id / client_secret> (dejar vacío para usar default — para producción seria se recomienda crear uno propio)
# scope> 1  (full access)
# advanced> n
# auto config> n
# (te da una URL — abrí en tu compu, logueá Google, copiá el token)
# team drive> n
# y) yes
```

Verificar:

```bash
sudo rclone lsd drive:
sudo rclone mkdir drive:JhelizBackups
```

## Configurar GPG passphrase

```bash
# Generá una passphrase fuerte y guardala en tu password manager
openssl rand -base64 32
# Guardala en /etc/jheliz-backup.env como GPG_PASSPHRASE=...
sudo chmod 600 /etc/jheliz-backup.env
```

⚠️ **Si perdés la passphrase, los backups cifrados son irrecuperables.** Guardala en al menos 2 lugares (password manager + impreso).

## Verificar que un backup es válido

```bash
# Listar el contenido sin extraer
tar -tzf /srv/backups/daily/jheliz-20260513-030001.tar.gz | head
# Si está cifrado con GPG:
gpg --decrypt jheliz-20260513-030001.tar.gz.gpg | tar -tz | head
```

Deberías ver:

```
db.sql
media.tar.gz
dotenv
README.txt
```

## Restaurar desde un backup

```bash
sudo bash /srv/jheliz/deploy/restore.sh /srv/backups/daily/jheliz-YYYYMMDD-HHMMSS.tar.gz
# Te pide escribir 'RESTORE' para confirmar.
# Si el bundle está cifrado, te pide la passphrase de GPG.
```

Hace en orden:

1. `psql` re-importa `db.sql` (la DB queda exactamente como en el backup).
2. Reemplaza `/srv/jheliz/media/` con el del backup.
3. Reemplaza `/srv/jheliz/.env` (haciendo backup del actual en `.env.bak.<timestamp>`).
4. Recrea el container web para tomar el `.env` nuevo.

## Test rápido (probarlo sin romper nada)

```bash
# 1. Generar un backup manualmente:
sudo bash /srv/jheliz/deploy/backup.sh

# 2. Ver que existe:
ls -lh /srv/backups/daily/

# 3. Listar contenido:
tar -tzf /srv/backups/daily/jheliz-*.tar.gz

# 4. Extraer en /tmp y revisar manualmente que db.sql tiene datos:
mkdir -p /tmp/checkbk
tar -xzf /srv/backups/daily/jheliz-*.tar.gz -C /tmp/checkbk
head /tmp/checkbk/db.sql
ls -la /tmp/checkbk/
rm -rf /tmp/checkbk
```

## Restaurar **a otra máquina** (simulacro DR)

1. Levantar Docker + clonar el repo en la máquina nueva.
2. `cp dotenv .env` del backup.
3. `docker compose up -d db`.
4. `cat db.sql | docker compose exec -T db psql -U jheliz -d jheliz`.
5. `tar -xzf media.tar.gz -C /srv/jheliz/`.
6. `docker compose up -d web`.

Ya tenés un clone funcional.
