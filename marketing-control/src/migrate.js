import {db} from './db.js';
import {readFileSync} from 'node:fs';
import {operationsSchema} from './operations.js';
import {renewalSchema} from './renewals.js';
import argon2 from 'argon2';
import {commerceSchema} from './commerce-schema.js';
import {supportSchema} from './support-schema.js';
import {welcomeText} from './welcome.js';
import {externalSalesSchema} from './external-sales.js';
import {expiryNotificationsSchema} from './expiry-notifications.js';
await db.query(`
CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY, applied_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS users(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),email text UNIQUE NOT NULL,password_hash text NOT NULL,role text NOT NULL CHECK(role IN ('ADMIN','OPERATOR','SUPPORT')),active boolean NOT NULL DEFAULT true,created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS sessions(token_hash text PRIMARY KEY,user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,csrf text NOT NULL,expires_at timestamptz NOT NULL);
CREATE TABLE IF NOT EXISTS instances(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),name text NOT NULL,desired boolean NOT NULL DEFAULT false,revision integer NOT NULL DEFAULT 0,status text NOT NULL DEFAULT 'DISCONNECTED',qr text,phone text,last_error text,heartbeat timestamptz,updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS commands(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),name text UNIQUE NOT NULL,response text NOT NULL,enabled boolean NOT NULL DEFAULT true,private boolean NOT NULL DEFAULT false,updated_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS events(id bigserial PRIMARY KEY,instance_id uuid REFERENCES instances(id),level text NOT NULL,message text NOT NULL,created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS audit(id bigserial PRIMARY KEY,actor uuid REFERENCES users(id),action text NOT NULL,ip text,details jsonb NOT NULL DEFAULT '{}',created_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS received_messages(instance_id uuid NOT NULL REFERENCES instances(id),message_id text NOT NULL,created_at timestamptz DEFAULT now(),PRIMARY KEY(instance_id,message_id));
CREATE INDEX IF NOT EXISTS events_recent ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
INSERT INTO schema_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;
`);
if (!(await db.query('SELECT id FROM instances LIMIT 1')).rowCount) await db.query("INSERT INTO instances(name) VALUES('WhatsApp principal')");
for(const [name,response,priv] of [
 ['menu','Bienvenido a Jheliz. Escribe /ayuda para contactar con nuestro equipo.',false],
 ['ayuda','Nuestro equipo puede ayudarte. Describe tu consulta y un operador te atenderá.',false],
 ['soporte','Describe el problema que necesitas resolver. Un operador continuará la atención.',false],
 ['saldo','El módulo de clientes todavía no está habilitado. Contacta con un operador.',true],
 ['mis_cuentas','El módulo de cuentas todavía no está habilitado. Contacta con un operador.',true],
 ['vencimiento','El módulo de cuentas todavía no está habilitado. Contacta con un operador.',true],
 ['recargar','Las recargas todavía no están habilitadas. Contacta con un operador.',true],
]) await db.query('INSERT INTO commands(name,response,private,enabled) VALUES($1,$2,$3,$4) ON CONFLICT(name) DO NOTHING',[name,response,priv,!priv]);
if (!(await db.query('SELECT id FROM users LIMIT 1')).rowCount && process.env.OWNER_EMAIL && process.env.OWNER_INITIAL_PASSWORD?.length>=12) {
 await db.query("INSERT INTO users(email,password_hash,role) VALUES($1,$2,'ADMIN')",[process.env.OWNER_EMAIL.toLowerCase().trim(),await argon2.hash(process.env.OWNER_INITIAL_PASSWORD)]);
}
await db.query(commerceSchema);
await db.query(supportSchema);
await db.query(externalSalesSchema);
await db.query(expiryNotificationsSchema);
await db.query(renewalSchema);
await db.query(operationsSchema);
await db.query(readFileSync(new URL('./admin-alerts.sql',import.meta.url),'utf8'));
// Apply the approved welcome once; later edits in Comandos are preserved.
await db.query("WITH updated AS (UPDATE commands SET response=$1,enabled=true,private=false,updated_at=now() WHERE name='menu' AND NOT EXISTS(SELECT 1 FROM schema_migrations WHERE version=4) RETURNING id) INSERT INTO schema_migrations(version) VALUES(4) ON CONFLICT DO NOTHING",[welcomeText]);
// Explicitly requested messaging refresh, applied once; back up the former copy.
await db.query("WITH saved AS (INSERT INTO audit(action,details) SELECT 'menu.before_copy_v6',jsonb_build_object('response',response,'enabled',enabled,'private',private) FROM commands WHERE name='menu' AND NOT EXISTS(SELECT 1 FROM schema_migrations WHERE version=6)), updated AS (UPDATE commands SET response=$1,enabled=true,private=false,updated_at=now() WHERE name='menu' AND NOT EXISTS(SELECT 1 FROM schema_migrations WHERE version=6) RETURNING id) INSERT INTO schema_migrations(version) VALUES(6) ON CONFLICT DO NOTHING",[welcomeText]);
// These commands are now backed by the commerce module; expose them publicly once.
await db.query("WITH updated AS (UPDATE commands SET enabled=true,private=false,updated_at=now() WHERE name IN ('mis_cuentas','vencimiento') AND NOT EXISTS(SELECT 1 FROM schema_migrations WHERE version=8) RETURNING id) INSERT INTO schema_migrations(version) VALUES(8) ON CONFLICT DO NOTHING");
await db.end();
console.log('Database migration 1 ready');
