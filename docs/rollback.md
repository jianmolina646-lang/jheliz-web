# Procedimiento de rollback

## Alcance

Un rollback puede afectar código, contenedores, configuración, migraciones o
datos. Cada categoría se trata por separado. Revertir código no autoriza a
restaurar una base ni reemplazar archivos de usuarios.

## Preparación obligatoria

- Identificar commit desplegado y commit objetivo.
- Confirmar estado de Git y cambios locales del servidor.
- Confirmar qué archivos Compose y nombre de proyecto están activos.
- Verificar backup cifrado y restauración de prueba si hubo cambios de datos.
- Registrar estado de web, bots, workers y tareas.

## Rollback de código sin cambios de esquema

Preferir un commit de reversión revisable en la rama correspondiente:

```bash
git switch <rama-de-produccion>
git status
git revert <commit-problematico>
```

No usar `git reset --hard`, `git checkout -- .` ni `force push` en producción.

Después, reconstruir solo los servicios afectados usando los mismos archivos
Compose del despliegue original y validar salud, logs y HTTP.

## Rollback con migraciones

No ejecutar `migrate <app> <anterior>` automáticamente. Antes se debe revisar:

- Si la migración elimina o transforma datos.
- Si el código anterior entiende el esquema actual.
- Dependencias entre apps.
- SQL de reversión generado por Django.
- Existencia de un backup restaurable.

Cuando una migración es compatible hacia atrás, suele ser más seguro revertir
solo el código y mantener temporalmente el esquema nuevo.

## Rollback de configuración

`.env`, Docker Secrets y Nginx no forman parte del rollback Git normal. Restaurar
únicamente desde una copia identificada, revisar permisos y validar antes de
recargar servicios. Nunca mostrar valores mediante `docker compose config` en
logs compartidos.

## Rollback de base de datos

Restaurar una base reemplaza datos actuales y exige autorización explícita.
Seguir [backups.md](backups.md), preservar primero el estado actual y detener
todos los escritores.

## Verificación posterior

```bash
python manage.py check
python manage.py showmigrations --plan
docker compose ps
docker compose logs --tail=100 web
```

Comprobar además:

- HTTP/TLS y login.
- Lecturas representativas de base de datos.
- Bots y workers habilitados.
- Tareas programadas.
- Backups posteriores al rollback.

Documentar commit final, servicios recreados, migraciones ejecutadas y cualquier
incidencia observada.

