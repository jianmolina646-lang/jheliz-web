// A separate delivery ledger makes expiry reminders idempotent across worker restarts.
export const expiryNotificationsSchema=`
CREATE TABLE IF NOT EXISTS expiry_notifications(
 order_id uuid PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
 status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','SENDING','SENT','REVIEW')),
 message_id text UNIQUE NOT NULL,
 started_at timestamptz,
 sent_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS expiry_notifications_status ON expiry_notifications(status,created_at);
INSERT INTO schema_migrations(version) VALUES(7) ON CONFLICT DO NOTHING;
`;
