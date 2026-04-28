# Auto-deploy a VPS con GitHub Actions

Cada vez que se mergea un PR a `main`, este workflow (`.github/workflows/deploy.yml`)
se conecta por SSH al VPS, hace `git pull` y rebuild de los contenedores Docker.

No tienes que hacer nada manual después de configurarlo una sola vez.

## Configuración inicial (una sola vez)

### 1. Asegúrate que el repo esté clonado en el VPS

```bash
ssh tu_usuario@tu_ip
sudo mkdir -p /srv && cd /srv
sudo git clone https://github.com/jianmolina646-lang/jheliz-web.git jheliz
cd jheliz
sudo chown -R $USER:$USER .
```

Verifica que `docker compose up -d --build` funcione manualmente la primera vez.

### 2. Crea una llave SSH dedicada para el deploy

Desde tu computadora **local** (no el VPS):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/jheliz_deploy -N "" -C "github-actions-deploy"
```

Esto genera dos archivos:
- `~/.ssh/jheliz_deploy` → llave **privada** (esta va a GitHub Secrets)
- `~/.ssh/jheliz_deploy.pub` → llave **pública** (esta va al VPS)

### 3. Autoriza la llave pública en el VPS

```bash
ssh-copy-id -i ~/.ssh/jheliz_deploy.pub tu_usuario@tu_ip
```

O manualmente:

```bash
cat ~/.ssh/jheliz_deploy.pub | ssh tu_usuario@tu_ip "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Prueba que funciona:

```bash
ssh -i ~/.ssh/jheliz_deploy tu_usuario@tu_ip "echo OK"
```

### 4. Pega los secretos en GitHub

Ve a: **Settings → Secrets and variables → Actions** del repo.

#### Secrets (encriptados, no se muestran):

| Nombre          | Valor                                                  |
|-----------------|--------------------------------------------------------|
| `VPS_HOST`      | IP pública o dominio del VPS (ej. `185.xx.xx.xx`)     |
| `VPS_USER`      | Usuario SSH (ej. `root` o `ubuntu`)                    |
| `VPS_SSH_KEY`   | Contenido completo de `~/.ssh/jheliz_deploy` (privada) |
| `VPS_PORT`      | Puerto SSH si NO es el 22 (opcional)                   |

> **Importante**: para `VPS_SSH_KEY` pega el contenido **completo** del archivo, incluyendo
> las líneas `-----BEGIN OPENSSH PRIVATE KEY-----` y `-----END OPENSSH PRIVATE KEY-----`.

#### Variables (visibles, no encriptadas):

| Nombre              | Valor                                  |
|---------------------|----------------------------------------|
| `VPS_PROJECT_PATH`  | Ruta del proyecto en el VPS, default `/srv/jheliz` |

(Si tu proyecto está en `/srv/jheliz` no necesitas esta variable.)

### 5. Asegúrate que tu usuario SSH puede correr `docker compose` sin sudo

```bash
sudo usermod -aG docker $USER
# cierra sesión y vuelve a entrar
docker compose ps   # debería listar sin pedir sudo
```

Si requieres sudo siempre, puedes editar el workflow para usar `sudo docker compose ...`,
pero entonces el usuario SSH tiene que estar en `sudoers` con `NOPASSWD`.

## Cómo se dispara el deploy

- **Automático**: cada push a `main` (típicamente cuando mergeas un PR).
- **Manual**: en la pestaña **Actions** del repo → "Deploy to VPS" → "Run workflow".

## Logs

Cuando se ejecuta, ve a la pestaña **Actions** del repo y abre el run.
Verás cada paso del deploy: pull, build, migrate, collectstatic, restart.

Si falla, el log te dice exactamente en qué paso. Errores comunes:

- **Permission denied (publickey)**: la llave no está autorizada. Repite el paso 3.
- **`git pull` falla por conflicto**: probablemente alguien editó archivos en el VPS.
  Resuelve a mano con `git status` y luego `git reset --hard origin/main` si quieres
  forzar.
- **`docker compose: command not found`**: instala Docker en el VPS según `DEPLOY.md`.
- **Migrations fallan**: probablemente faltan variables en `.env` o la DB no está al día.
  Conéctate por SSH y ejecuta `docker compose logs web` para ver el error real.

## Hacer rollback

Si un deploy rompe la web:

```bash
ssh tu_usuario@tu_ip
cd /srv/jheliz
git log --oneline -10        # ver commits recientes
git reset --hard <COMMIT_OK> # volver al commit anterior
docker compose up -d --build
```
