#!/bin/sh
set -eu
umask 077
target=/opt/jheliz-marketing-control
backup=/opt/backups/marketing-before-clean-20261011
test -d /opt/jheliz-deploy/whatsapp-panel
test ! -e "$backup"
mkdir -p "$backup"
tar -czf "$backup/source.tgz" -C /opt/jheliz-deploy whatsapp-panel
docker exec jheliz-whatsapp-postgres-1 pg_dump -U jheliz_bot -d jheliz_bot -Fc > "$backup/database.dump"
docker exec -i jheliz-whatsapp-postgres-1 pg_restore -l < "$backup/database.dump" > "$backup/database-contents.txt"
cp -a /etc/nginx/sites-available/marketingjheliz "$backup/nginx.conf"
docker exec jheliz-whatsapp-postgres-1 psql -U jheliz_bot -d jheliz_bot -At -c 'SELECT row_to_json(a) FROM "Admin" a WHERE active=true;' > "$backup/admin-access.jsonl"
test -s "$backup/database.dump"
if docker volume inspect jheliz-whatsapp_whatsapp_session >/dev/null 2>&1; then
 docker run --rm -v jheliz-whatsapp_whatsapp_session:/source:ro -v "$backup":/backup alpine:3.20 tar -czf /backup/whatsapp-session.tgz -C /source .
fi
test ! -e "$target"
mkdir -p "$target"
tar -xzf /home/jhelizadmin/marketing-control.tgz -C "$target"
password=$(openssl rand -hex 32)
printf 'NODE_ENV=production\nAPP_URL=https://marketingjhelizxyz.online\nPOSTGRES_PASSWORD=%s\nDATABASE_URL=postgresql://marketing:%s@db:5432/marketing\nSESSION_DIR=/data\nLOG_LEVEL=info\n' "$password" "$password" > "$target/.env"
chmod 600 "$target/.env"
cd "$target"
docker compose build
docker compose up -d
for attempt in $(seq 1 30); do
 if curl -fsS http://127.0.0.1:8011/health >/dev/null; then break; fi
 sleep 2
done
curl -fsS http://127.0.0.1:8011/health
docker compose exec -T api node src/import-admins.js < "$backup/admin-access.jsonl"
docker compose exec -T api npm test
docker compose exec -T -e RUN_INTEGRATION=1 api node --test tests/integration.test.js
echo 'PREPARED_AND_TESTED_NOT_SWITCHED'
