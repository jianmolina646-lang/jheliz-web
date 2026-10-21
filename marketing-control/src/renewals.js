import {transaction,accountFingerprint} from './commerce.js';
import {requireSalesInstance} from './instance-purpose.js';
export const renewalSchema=`ALTER TABLE orders ADD COLUMN IF NOT EXISTS renewal_of uuid REFERENCES orders(id);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_renewal ON orders(renewal_of) WHERE renewal_of IS NOT NULL AND status IN ('PENDING','APPROVED','SENDING','REVIEW');`;
const fail=message=>{throw Object.assign(new Error(message),{statusCode:409,publicMessage:message});};
export function parseRenewal(text){
 const parts=text.trim().toLowerCase().split(/\s+/);
 if(parts.length!==3||!/^\S+@\S+\.\S+$/.test(parts[2]))fail('Para renovar una cuenta escribe: /renovar netflix correo@ejemplo.com\nUsa el código de plataforma que aparece en /catalogo.');
 return {code:parts[1],email:parts[2]};
}
export function renewalDates(expiry,days,now=new Date()){
 const start=new Date(Math.max(new Date(expiry).getTime(),now.getTime()));
 if(days===30){
  // Monthly plans follow Peru's calendar, including month-end clamping.
  const local=new Date(start.getTime()-5*3600000),day=local.getUTCDate();
  local.setUTCDate(1);local.setUTCMonth(local.getUTCMonth()+1);
  const last=new Date(Date.UTC(local.getUTCFullYear(),local.getUTCMonth()+1,0)).getUTCDate();
  local.setUTCDate(Math.min(day,last));
  return {start,end:new Date(local.getTime()+5*3600000)};
 }
 return {start,end:new Date(start.getTime()+days*86400000)};
}
export async function createRenewal(instance,jid,text,verifiedJids=[jid]){
 const {code,email}=parseRenewal(text);
 return transaction(async c=>{
  await requireSalesInstance(c,instance);
  await c.query('SELECT pg_advisory_xact_lock(hashtext($1))',[instance+jid]);
  const p=(await c.query('SELECT * FROM products WHERE code=$1 AND active=true',[code])).rows[0];
  if(!p)fail('Plataforma no disponible. Consulta /catalogo.');
  const o=(await c.query("SELECT o.* FROM orders o JOIN stock s ON s.id=o.stock_id WHERE o.instance_id=$1 AND o.jid=ANY($2::text[]) AND s.fingerprint=$3 AND o.status='DELIVERED' AND s.state='SOLD' FOR UPDATE OF o",[instance,verifiedJids,accountFingerprint(p.id,email)])).rows[0];
  if(!o)fail('No encontramos esa cuenta entregada a tu WhatsApp en esta plataforma. Contacta /soporte.');
  const pending=(await c.query("SELECT * FROM orders WHERE instance_id=$1 AND jid=$2 AND status='PENDING'",[instance,jid])).rows[0];
  if(pending){if(pending.renewal_of===o.id)return pending;fail('Ya tienes una solicitud pendiente. Complétala o usa /cancelar antes de renovar otra cuenta.');}
  if((await c.query("SELECT id FROM orders WHERE renewal_of=$1 AND status IN ('PENDING','APPROVED','SENDING','REVIEW')",[o.id])).rowCount)fail('Esta cuenta ya tiene una renovación en proceso.');
  return (await c.query("INSERT INTO orders(instance_id,jid,customer,product_id,product_name,price_cents,days,source,renewal_of) VALUES($1,$2,$3,$4,$5,$6,$7,'RENEWAL',$8) RETURNING *",[instance,jid,o.customer,p.id,p.name,p.price_cents,p.days,o.id])).rows[0];
 });
}
export async function approveRenewal(c,o,reference,actor,confirmed){
 if(!confirmed)fail('Confirma que el servicio de esta cuenta ya fue renovado en la plataforma.');
 const parent=(await c.query('SELECT * FROM orders WHERE id=$1 FOR UPDATE',[o.renewal_of])).rows[0];
 if(!parent||parent.status!=='DELIVERED'||parent.instance_id!==o.instance_id)fail('La cuenta original requiere revisión.');
 const stock=(await c.query("SELECT * FROM stock WHERE id=$1 AND state='SOLD' FOR UPDATE",[parent.stock_id])).rows[0];
 if(!stock)fail('La cuenta ya no está disponible para renovar.');
 const {start,end}=renewalDates(parent.expires_at,o.days);
 await c.query("UPDATE orders SET status='APPROVED',payment_ref=$1,approved_by=$2,approved_at=now(),started_at=$3,expires_at=$4,sheets_synced_at=null WHERE id=$5",[reference,actor,start,end,o.id]);
 await c.query('UPDATE orders SET expires_at=$1,sheets_synced_at=null WHERE id=$2',[end,parent.id]);
 if(stock.expires_on)await c.query("UPDATE stock SET expires_on=GREATEST(expires_on,($1::timestamptz AT TIME ZONE 'America/Lima')::date) WHERE id=$2",[end,stock.id]);
 const notices=(await c.query('DELETE FROM expiry_notifications WHERE order_id=$1 RETURNING *',[parent.id])).rows;
 await c.query("INSERT INTO audit(actor,action,details) VALUES($1,'renewal.approved',$2)",[actor,JSON.stringify({order:o.id,parent:parent.id,previous_expiry:parent.expires_at,new_expiry:end,previous_notifications:notices})]);
 return {ok:true};
}
