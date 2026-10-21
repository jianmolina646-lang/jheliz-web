import {db,rows,event} from './db.js';
import {transaction} from './commerce.js';
import {isCodesInstance} from './instance-purpose.js';
import {ADMIN_ALERT_JID,adminAlertText} from './admin-alert-copy.js';

export async function enqueueDelayedPaymentAlerts(){
 return db.query(`INSERT INTO sales_admin_alerts(order_id,kind)
  SELECT o.id,'PAYMENT_DELAYED' FROM orders o
  JOIN sales_admin_alerts r ON r.order_id=o.id AND r.kind='RECEIPT'
  WHERE o.status='PENDING' AND o.receipt IS NOT NULL
  AND r.created_at<=now()-interval '5 minutes'
  ON CONFLICT(order_id,kind) DO NOTHING`);
}

export async function deliverAdminAlerts(running){
 await enqueueDelayedPaymentAlerts();
 await db.query("UPDATE sales_admin_alerts SET status='REVIEW' WHERE status='SENDING' AND started_at<now()-interval '5 minutes'");
 for(const [instance,state] of running){
  if(!state.connected||state.closed)continue;
  const [sender]=await rows('SELECT * FROM instances WHERE id=$1',[instance]);
  if(!sender||isCodesInstance(sender))continue;
  const alert=await transaction(async c=>{
   const [item]=(await c.query(`SELECT a.id AS alert_id,a.kind,o.id,o.customer,o.product_name,o.price_cents,o.days,o.status,
    o.lemon_check,o.lemon_name_requested_at,o.lemon_payer_normalized IS NOT NULL AS has_payer,
    o.receipt_amount_cents,o.receipt_operation_minute,
    (SELECT last_error IS NOT NULL FROM lemon_verifier WHERE id=1) AS verifier_error,
    (SELECT enabled FROM lemon_verifier WHERE id=1) AS verifier_enabled
    FROM sales_admin_alerts a JOIN orders o ON o.id=a.order_id
    WHERE a.status='PENDING' AND o.instance_id=$1
    ORDER BY a.id FOR UPDATE OF a SKIP LOCKED LIMIT 1`,[instance])).rows;
   if(!item)return;
   if(item.status!=='PENDING'){
    await c.query("UPDATE sales_admin_alerts SET status='SKIPPED' WHERE id=$1",[item.alert_id]);return;
   }
   await c.query("UPDATE sales_admin_alerts SET status='SENDING',started_at=now() WHERE id=$1",[item.alert_id]);
   return item;
  });
  if(!alert)continue;
  try{
   await state.socket.sendMessage(ADMIN_ALERT_JID,{text:adminAlertText(alert,alert.kind)});
   await db.query("UPDATE sales_admin_alerts SET status='SENT',sent_at=now() WHERE id=$1",[alert.alert_id]);
  }catch{
   // Transport failures can be ambiguous. Never resend automatically.
   await db.query("UPDATE sales_admin_alerts SET status='REVIEW' WHERE id=$1",[alert.alert_id]);
   await event(instance,'ERROR','Aviso al administrador pendiente de revisión: '+alert.alert_id);
  }
 }
}
