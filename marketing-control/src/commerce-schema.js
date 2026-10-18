export const commerceSchema = `
CREATE TABLE IF NOT EXISTS products(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),code text UNIQUE NOT NULL,name text NOT NULL,
 price_cents integer NOT NULL CHECK(price_cents>0),days integer NOT NULL CHECK(days BETWEEN 1 AND 3660),
 active boolean NOT NULL DEFAULT true,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS stock(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),product_id uuid NOT NULL REFERENCES products(id),
 secret text NOT NULL,fingerprint text UNIQUE NOT NULL,expires_on date,
 state text NOT NULL DEFAULT 'AVAILABLE' CHECK(state IN ('AVAILABLE','SOLD','DISABLED')),
 created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS orders(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),report_row bigserial UNIQUE NOT NULL,
 instance_id uuid NOT NULL REFERENCES instances(id),jid text NOT NULL,customer text NOT NULL,
 product_id uuid NOT NULL REFERENCES products(id),product_name text NOT NULL,
 price_cents integer NOT NULL,days integer NOT NULL,
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','APPROVED','SENDING','DELIVERED','REVIEW','REJECTED')),
 stock_id uuid UNIQUE REFERENCES stock(id),payment_ref text UNIQUE,approved_by uuid REFERENCES users(id),
 receipt text,receipt_mime text,created_at timestamptz NOT NULL DEFAULT now(),approved_at timestamptz,
 started_at timestamptz,expires_at timestamptz,delivered_at timestamptz,
 delivery_id text,delivery_started_at timestamptz,sheets_synced_at timestamptz);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_order ON orders(instance_id,jid) WHERE status='PENDING';
CREATE TABLE IF NOT EXISTS commerce_sync(id integer PRIMARY KEY CHECK(id=1),last_success timestamptz,last_error text);
INSERT INTO commerce_sync(id) VALUES(1) ON CONFLICT DO NOTHING;
INSERT INTO schema_migrations(version) VALUES(2) ON CONFLICT DO NOTHING;
`;
