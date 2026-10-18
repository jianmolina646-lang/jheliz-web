#!/bin/sh
set -eu
cd /opt/jheliz-marketing-control
# Additive schema; do not alter other projects or reset WhatsApp sessions.
docker compose build api worker migrate
docker compose exec -T db psql -U marketing -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='marketing_commerce_test'" | grep -q 1 || docker compose exec -T db createdb -U marketing marketing_commerce_test
docker compose run --rm --no-deps --entrypoint sh api -c 'export DATABASE_URL="${DATABASE_URL%/*}/marketing_commerce_test"; node src/migrate.js; RUN_COMMERCE_TEST=1 node --test tests/commerce.test.js'
docker compose run --rm --no-deps --entrypoint sh api -c 'export DATABASE_URL="${DATABASE_URL%/*}/marketing_commerce_test"; RUN_SUPPORT_TEST=1 node --test tests/support.test.js'
docker compose run --rm --no-deps --entrypoint sh api -c 'export DATABASE_URL="${DATABASE_URL%/*}/marketing_commerce_test"; RUN_EXTERNAL_TEST=1 node --test tests/external-sales.test.js'
docker compose run --rm --no-deps --entrypoint sh api -c 'export DATABASE_URL="${DATABASE_URL%/*}/marketing_commerce_test"; RUN_EXPIRY_TEST=1 node --test tests/expiry-reminders.test.js'
docker compose run --rm --no-deps api sh -c 'node --check src/commerce.js && node --check src/commerce-worker.js && node --check src/worker.js && node --check public/commerce-ui.js && node --check public/app.js && npm test'
docker compose run --rm migrate
docker compose up -d api worker
docker compose exec -T api node --input-type=module -e "for(let n=0;n<20;n++){try{const r=await fetch('http://127.0.0.1:4000/health');if(r.ok){console.log(await r.text());process.exit(0)}}catch{}await new Promise(r=>setTimeout(r,1000))}process.exit(1)"
