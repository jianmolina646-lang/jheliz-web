export const lemonSchema = `
ALTER TABLE orders ADD COLUMN IF NOT EXISTS lemon_payer text;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS lemon_payer_normalized text;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS lemon_name_requested_at timestamptz;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS lemon_check text;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS receipt_amount_cents integer;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS receipt_operation_minute timestamptz;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS lemon_name_notice_at timestamptz;
CREATE TABLE IF NOT EXISTS lemon_verifier(
 id integer PRIMARY KEY CHECK(id=1),enabled boolean NOT NULL DEFAULT false,
 activated_at timestamptz,last_success timestamptz,last_error text);
INSERT INTO lemon_verifier(id) VALUES(1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS lemon_payments(
 operation_id text PRIMARY KEY, external_id text UNIQUE NOT NULL,
 payer_normalized text NOT NULL,amount_cents integer NOT NULL CHECK(amount_cents>0),
 paid_at timestamptz NOT NULL,received_at timestamptz NOT NULL,
 order_id uuid UNIQUE REFERENCES orders(id),blocked boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now());
`;
