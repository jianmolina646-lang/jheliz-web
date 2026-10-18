BEGIN;
CREATE TABLE IF NOT EXISTS sales_admin_alerts (
 id bigserial PRIMARY KEY,
 order_id uuid NOT NULL REFERENCES orders(id),
 kind text NOT NULL CHECK(kind IN ('ORDER','RECEIPT')),
 status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SENDING','SENT','REVIEW','SKIPPED')),
 created_at timestamptz NOT NULL DEFAULT now(),
 started_at timestamptz,
 sent_at timestamptz,
 UNIQUE(order_id,kind)
);
CREATE INDEX IF NOT EXISTS sales_admin_alerts_pending ON sales_admin_alerts(id) WHERE status='PENDING';
CREATE OR REPLACE FUNCTION enqueue_sales_admin_alert() RETURNS trigger AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.status='PENDING' AND NEW.source IN ('BOT','RENEWAL') THEN
   INSERT INTO sales_admin_alerts(order_id,kind) VALUES(NEW.id,'ORDER') ON CONFLICT DO NOTHING;
  END IF;
 ELSIF NEW.status='PENDING' AND OLD.receipt IS NULL AND NEW.receipt IS NOT NULL THEN
  INSERT INTO sales_admin_alerts(order_id,kind) VALUES(NEW.id,'RECEIPT') ON CONFLICT DO NOTHING;
 END IF;
 RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS sales_admin_alert_insert ON orders;
CREATE TRIGGER sales_admin_alert_insert AFTER INSERT ON orders FOR EACH ROW EXECUTE FUNCTION enqueue_sales_admin_alert();
DROP TRIGGER IF EXISTS sales_admin_alert_receipt ON orders;
CREATE TRIGGER sales_admin_alert_receipt AFTER UPDATE OF receipt ON orders FOR EACH ROW EXECUTE FUNCTION enqueue_sales_admin_alert();
COMMIT;
