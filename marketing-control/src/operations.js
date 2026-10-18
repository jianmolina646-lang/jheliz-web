import {z} from 'zod';
import {rows} from './db.js';
import {transaction,decrypt} from './commerce.js';
import {requireSalesInstance} from './instance-purpose.js';
import {renewalDates} from './renewals.js';

export const operationsSchema=`
ALTER TABLE instances ADD COLUMN IF NOT EXISTS purpose text NOT NULL DEFAULT 'SALES' CHECK(purpose IN ('SALES','CODES'));
UPDATE instances SET purpose='CODES' WHERE phone='51934550654' OR lower(name) IN ('codigos jheliz','códigos jheliz');
ALTER TABLE orders ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS orders_customer_lookup ON orders(instance_id,jid,created_at DESC);
`;
const fail=message=>{throw Object.assign(new Error(message),{statusCode:409,publicMessage:message});};
export async function retryDelivery(id,actor,input){
 const data=z.object({verified_not_received:z.literal(true),reason:z.string().trim().min(8).max(500)}).strict().parse(input);
 return transaction(async c=>{
  const o=(await c.query('SELECT * FROM orders WHERE id=$1 FOR UPDATE',[id])).rows[0];
  if(!o||o.status!=='REVIEW')fail('Solo se puede reintentar una entrega en revisión. Actualiza la lista.');
  const instance=await requireSalesInstance(c,o.instance_id);
  if(instance.status!=='CONNECTED'||!instance.desired)fail('Conecta y activa el bot de ventas antes de reintentar.');
  if(o.retry_count>=3)fail('Se alcanzaron tres reintentos. Requiere revisión técnica antes de volver a enviar.');
  if(!o.expires_at||new Date(o.expires_at)<=new Date())fail('La cuenta está vencida o no tiene fechas válidas. Revisa la venta antes de enviar.');
  const parent=o.renewal_of?(await c.query('SELECT stock_id FROM orders WHERE id=$1',[o.renewal_of])).rows[0]:o;
  const stock=(await c.query("SELECT id FROM stock WHERE id=$1 AND state='SOLD' AND (expires_on IS NULL OR ((expires_on+1)::timestamp AT TIME ZONE 'America/Lima') >= $2::timestamptz)",[parent?.stock_id,o.expires_at])).rows[0];
  if(!stock)fail('La cuenta asignada requiere revisión de disponibilidad o vencimiento.');
  await c.query("UPDATE orders SET status='APPROVED',retry_count=retry_count+1,sheets_synced_at=null WHERE id=$1",[id]);
  await c.query("INSERT INTO audit(actor,action,details) VALUES($1,'delivery.retry_requested',$2)",[actor,{order:id,reason:data.reason,previous_message_id:o.delivery_id,attempt:o.retry_count+1}]);
  return {ok:true};
 });
}
const safeAccount=o=>{const {secret,...data}=o;return {...data,email:secret?JSON.parse(decrypt(secret)).email:null};};
export function registerOperations(app){
 const opts={preHandler:async(req,reply)=>{if(req.user.role!=='ADMIN')return reply.code(403).send({error:'Solo administradores'});}};
 app.get('/api/operations/overview',opts,async()=>{
  const [metrics]=await rows(`SELECT count(*) FILTER(WHERE status='PENDING')::int AS pending_payments,
   count(*) FILTER(WHERE status IN ('APPROVED','SENDING'))::int AS queued,
   count(*) FILTER(WHERE status='REVIEW')::int AS review,
   count(*) FILTER(WHERE status='DELIVERED' AND renewal_of IS NULL AND expires_at>=now() AND expires_at<now()+interval '3 days')::int AS expiring,
   count(DISTINCT (instance_id,jid))::int AS customers FROM orders`);
  const [stock]=await rows("SELECT count(*)::int AS available FROM stock s JOIN products p ON p.id=s.product_id WHERE s.state='AVAILABLE' AND p.active AND (s.expires_on IS NULL OR s.expires_on >= (now() AT TIME ZONE 'America/Lima')::date+p.days)");
  return {...metrics,...stock};
 });
 app.get('/api/operations/customers',opts,async req=>{
  const {q=''}=z.object({q:z.string().trim().max(100).optional()}).parse(req.query);
  return rows(`SELECT o.instance_id,o.jid,max(o.customer) AS customer,i.name AS bot,
   count(*)::int AS operations,count(*) FILTER(WHERE o.renewal_of IS NULL AND o.status='DELIVERED')::int AS accounts,
   COALESCE(sum(o.price_cents) FILTER(WHERE o.status IN ('APPROVED','SENDING','DELIVERED','REVIEW')),0)::bigint AS paid_cents,
   min(o.created_at) AS first_order,
   max(o.expires_at) FILTER(WHERE o.status='DELIVERED') AS last_expiry,
   array_agg(DISTINCT o.product_name) FILTER(WHERE o.status='DELIVERED') AS platforms,
   max(o.created_at) AS last_order FROM orders o JOIN instances i ON i.id=o.instance_id
   WHERE ($1='' OR position(lower($1) in lower(o.customer))>0 OR position($1 in o.jid)>0)
   GROUP BY o.instance_id,o.jid,i.name ORDER BY last_order DESC LIMIT 200`,[q]);
 });
 app.get('/api/operations/customer',opts,async req=>{
  const {instance,jid}=z.object({instance:z.string().uuid(),jid:z.string().min(3).max(100)}).parse(req.query);
  const orders=await rows(`SELECT o.id,o.customer,o.product_name,o.status,o.price_cents,o.payment_ref,o.started_at,o.expires_at,o.created_at,o.renewal_of,s.secret
   FROM orders o LEFT JOIN orders parent ON parent.id=o.renewal_of LEFT JOIN stock s ON s.id=COALESCE(o.stock_id,parent.stock_id)
   WHERE o.instance_id=$1 AND o.jid=$2 ORDER BY o.created_at DESC LIMIT 500`,[instance,jid]);
  const support=await rows(`SELECT t.id,t.order_id,t.category,t.status,t.created_at,t.resolved_at FROM support_tickets t JOIN orders o ON o.id=t.order_id WHERE o.instance_id=$1 AND o.jid=$2 ORDER BY t.created_at DESC LIMIT 100`,[instance,jid]);
  return {orders:orders.map(safeAccount),support};
 });
 app.get('/api/operations/renewals',opts,async()=>{
  const orders=await rows(`SELECT o.id,o.customer,o.jid,o.product_name,o.price_cents,o.days,o.status,o.renewal_of,o.started_at,o.expires_at,o.created_at,
   (o.receipt IS NOT NULL) AS has_receipt,i.name AS bot,p.expires_at AS current_expiry,s.secret FROM orders o
   JOIN instances i ON i.id=o.instance_id JOIN orders p ON p.id=o.renewal_of LEFT JOIN stock s ON s.id=p.stock_id ORDER BY o.created_at DESC LIMIT 300`);
  return orders.map(o=>({...safeAccount(o),proposed_expiry:o.expires_at||renewalDates(o.current_expiry,o.days).end}));
 });
 app.get('/api/operations/deliveries',opts,async()=>rows(`SELECT o.id,o.instance_id,o.jid,o.customer,o.jid,o.product_name,o.status,o.retry_count,o.delivery_started_at,o.delivered_at,o.created_at,i.name AS bot,i.purpose FROM orders o JOIN instances i ON i.id=o.instance_id WHERE o.status IN ('APPROVED','SENDING','REVIEW','DELIVERED') ORDER BY o.created_at DESC LIMIT 300`));
 app.post('/api/operations/deliveries/:id/retry',opts,async req=>retryDelivery(z.string().uuid().parse(req.params.id),req.user.id,req.body));
 app.get('/api/operations/history',opts,async()=>{
  const entries=await rows("SELECT a.id,a.action,a.details,a.created_at,u.email FROM audit a LEFT JOIN users u ON u.id=a.actor WHERE a.action ~ '^(order|renewal|stock|support|delivery)\\.' ORDER BY a.id DESC LIMIT 300");
  // Explicit allowlist: audit payloads elsewhere can contain private before-images.
  return entries.map(({details,...e})=>({...e,details:Object.fromEntries(Object.entries(details||{}).filter(([k])=>['id','order','parent','ticket','stock','old_stock','new_stock','kind','category','reason','attempt','previous_expiry','new_expiry'].includes(k)))}));
 });
}
