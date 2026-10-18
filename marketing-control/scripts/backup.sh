#!/bin/sh
set -eu
umask 077
cd /opt/jheliz-marketing-control
destination="/opt/backups/marketing-control/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$destination"
docker compose exec -T db pg_dump -U marketing -d marketing -Fc > "$destination/database.dump"
cp .env "$destination/environment"
if [ -d /opt/jheliz-marketing-secrets ]; then cp -a /opt/jheliz-marketing-secrets "$destination/secrets"; fi
docker run --rm -v marketing-control_sessions:/source:ro -v "$destination":/backup alpine:3.20 tar -czf /backup/sessions.tgz -C /source .
docker compose exec -T db pg_restore -l < "$destination/database.dump" > "$destination/contents.txt"
echo "Backup: $destination"
