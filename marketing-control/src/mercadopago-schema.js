export const mercadoPagoSchema=`
CREATE TABLE IF NOT EXISTS mp_checkouts(
 order_id uuid PRIMARY KEY REFERENCES orders(id),preference_id text UNIQUE,checkout_url text,
 state text NOT NULL DEFAULT 'CREATING',created_at timestamptz NOT NULL DEFAULT now(),
 next_check_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS mp_payments(
 payment_id text PRIMARY KEY,order_id uuid REFERENCES orders(id),status text NOT NULL,
 amount_cents integer,outcome text NOT NULL,updated_at timestamptz NOT NULL DEFAULT now());
CREATE UNIQUE INDEX IF NOT EXISTS mp_one_applied_payment ON mp_payments(order_id) WHERE outcome='APPLIED';
CREATE TABLE IF NOT EXISTS mp_webhook_queue(
 payment_id text PRIMARY KEY,version bigint NOT NULL DEFAULT 1,processed_version bigint NOT NULL DEFAULT 0,
 attempts integer NOT NULL DEFAULT 0,next_attempt_at timestamptz NOT NULL DEFAULT now());
`;
