#!/bin/sh
set -eu
cd /opt/jheliz-marketing-control
docker compose build --quiet
docker compose up -d
for attempt in $(seq 1 30); do
 if curl -fsS http://127.0.0.1:8011/health >/dev/null; then break; fi
 sleep 2
done
curl -fsS http://127.0.0.1:8011/health
docker compose exec -T api npm test
docker compose exec -T -e RUN_INTEGRATION=1 api node --test tests/integration.test.js
config=/etc/nginx/sites-available/marketingjheliz
backup=/opt/backups/marketing-before-clean-20261011
test -s "$backup/database.dump"
test -s "$backup/nginx.conf"
grep -q 'proxy_pass http://127.0.0.1:8010;' "$config"
sed -i 's|proxy_pass http://127.0.0.1:8010;|proxy_pass http://127.0.0.1:8011;|' "$config"
if ! nginx -t; then cp "$backup/nginx.conf" "$config"; exit 1; fi
systemctl reload nginx
for attempt in $(seq 1 15); do
 if curl -fsS https://marketingjhelizxyz.online/health >/dev/null; then break; fi
 sleep 2
done
if ! curl -fsS https://marketingjhelizxyz.online/health; then
 cp "$backup/nginx.conf" "$config"
 nginx -t && systemctl reload nginx
 exit 1
fi
# Only this domain's old Compose project; preserve its volumes for rollback.
docker compose -f /opt/jheliz-deploy/whatsapp-panel/compose.yml stop
sh /opt/jheliz-marketing-control/scripts/backup.sh
echo DOMAIN_SWITCHED_OLD_PROJECT_STOPPED
