export const supportSchema=`
CREATE TABLE IF NOT EXISTS support_tickets(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),order_id uuid NOT NULL REFERENCES orders(id),
 stock_id uuid NOT NULL REFERENCES stock(id),category text NOT NULL CHECK(category IN ('PASSWORD','SUBSCRIPTION','OTHER')),
 status text NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','IN_PROGRESS','QUEUED','SENDING','REVIEW','RESOLVED')),
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),resolved_at timestamptz);
CREATE UNIQUE INDEX IF NOT EXISTS support_one_active ON support_tickets(order_id) WHERE status<>'RESOLVED';
CREATE TABLE IF NOT EXISTS support_actions(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),ticket_id uuid NOT NULL UNIQUE REFERENCES support_tickets(id),
 actor uuid NOT NULL REFERENCES users(id),kind text NOT NULL CHECK(kind IN ('CORRECT','REPLACE','MESSAGE')),
 old_stock_id uuid NOT NULL REFERENCES stock(id),new_stock_id uuid NOT NULL REFERENCES stock(id),
 payload text NOT NULL,message_id text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 sending_at timestamptz,sent_at timestamptz,expires_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS support_recent ON support_tickets(created_at DESC);
INSERT INTO schema_migrations(version) VALUES(3) ON CONFLICT DO NOTHING;
`;
