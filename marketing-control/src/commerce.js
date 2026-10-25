import {readFileSync} from 'node:fs';
import {createCipheriv,createDecipheriv,createHmac,randomBytes} from 'node:crypto';
import {z} from 'zod';
import {db,rows} from './db.js';
import {registerExternalSale} from './external-sales.js';
import {approveRenewal} from './renewals.js';
import {requireSalesInstance} from './instance-purpose.js';

const fail=(message,statusCode=409)=>{throw Object.assign(new Error(message),{statusCode,publicMessage:message});};
const key=()=>{const k=Buffer.from(readFileSync(process.env.COMMERCE_KEY_FILE||'/run/secrets/commerce-key','utf8').trim(),'hex');if(k.length!==32)throw new Error('Invalid encryption key');return k;};
export function encrypt(value){const iv=randomBytes(12),c=createCipheriv('aes-256-gcm',key(),iv);return Buffer.concat([iv,c.update(value,'utf8'),c.final(),c.getAuthTag()]).toString('base64');}
export function decrypt(value){const b=Buffer.from(value,'base64'),c=createDecipheriv('aes-256-gcm',key(),b.subarray(0,12));c.setAuthTag(b.subarray(-16));return Buffer.concat([c.update(b.subarray(12,-16)),c.final()]).toString('utf8');}
export const accountFingerprint=(product,email)=>createHmac('sha256',key()).update(product+':'+email.trim().toLowerCase()).digest('hex');
export const productSchema=z.object({code:z.string().trim().regex(/^[a-z][a-z0-9_-]{0,29}$/),name:z.string().trim().min(2).max(80),price_cents:z.number().int().min(1).max(10000000),days:z.number().int().min(1).max(3660),active:z.boolean()}).strict();
export const stockSchema=z.object({product_id:z.string().uuid(),email:z.string().email().max(254),password:z.string().min(1).max(256),expires_on:z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable()}).strict();
export const money=c=>(c/100).toFixed(2);
export async function transaction(fn){const c=await db.connect();try{await c.query('BEGIN');const result=await fn(c);await c.query('COMMIT');return result;}catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}}
async function log(c,user,action,details){await c.query('INSERT INTO audit(actor,action,details) VALUES($1,$2,$3)',[user,action,details]);}
export async function createOrder(instance,jid,customer,code){return transaction(async c=>{
 await requireSalesInstance(c,instance);
 await c.query('SELECT pg_advisory_xact_lock(hashtext($1))',[instance+jid]);
 const pending=(await c.query("SELECT * FROM orders WHERE instance_id=$1 AND jid=$2 AND status='PENDING'",[instance,jid])).rows[0];if(pending)return pending;
 const p=(await c.query('SELECT * FROM products WHERE code=$1 AND active=true',[code])).rows[0];if(!p)fail('Producto no disponible. Escribe /catalogo.');
 const stock=await c.query("SELECT id FROM stock WHERE product_id=$1 AND state='AVAILABLE' AND (expires_on IS NULL OR expires_on >= (now() AT TIME ZONE 'America/Lima')::date + $2::integer)",[p.id,p.days]);if(!stock.rowCount)fail('Producto sin stock suficiente para esa duración.');
 return (await c.query('INSERT INTO orders(instance_id,jid,customer,product_id,product_name,price_cents,days) VALUES($1,$2,$3,$4,$5,$6,$7) RETURNING *',[instance,jid,customer.slice(0,100),p.id,p.name,p.price_cents,p.days])).rows[0];
 });}
export async function approveOrder(id,reference,actor,serviceRenewed=false){return transaction(async c=>{
 await c.query("SELECT pg_advisory_xact_lock(hashtext('lemon-payment-verification'))");
 const used=await c.query('SELECT order_id FROM lemon_payments WHERE (operation_id=upper(trim($1)) OR external_id=trim($1)) AND (order_id IS NOT NULL OR blocked=true)',[reference]);
 if(used.rowCount)fail('Esta operación Lemon ya fue utilizada o requiere revisión.');
 const o=(await c.query('SELECT * FROM orders WHERE id=$1 FOR UPDATE',[id])).rows[0];if(!o)fail('Pedido no encontrado',404);
 if(o.status!=='PENDING')fail('Este pedido ya fue procesado.');
 if(o.lemon_check?.startsWith('MP_')||reference.startsWith('MP:'))fail('Los pagos de Mercado Pago se aprueban únicamente mediante verificación automática.');
 await requireSalesInstance(c,o.instance_id);
 if(o.renewal_of){const result=await approveRenewal(c,o,reference,actor,serviceRenewed);await c.query('UPDATE lemon_payments SET order_id=$1 WHERE operation_id=upper(trim($2)) OR external_id=trim($2)',[id,reference]);return result;}
 const s=(await c.query("SELECT * FROM stock WHERE product_id=$1 AND state='AVAILABLE' AND (expires_on IS NULL OR expires_on >= (now() AT TIME ZONE 'America/Lima')::date + $2::integer) ORDER BY expires_on NULLS LAST,created_at FOR UPDATE SKIP LOCKED LIMIT 1",[o.product_id,o.days])).rows[0];if(!s)fail('No hay stock válido. Carga una cuenta antes de aprobar.');
 await c.query("UPDATE stock SET state='SOLD' WHERE id=$1",[s.id]);
 await c.query("UPDATE orders SET status='APPROVED',stock_id=$1,payment_ref=$2,approved_by=$3,approved_at=now(),sheets_synced_at=null WHERE id=$4",[s.id,reference,actor,id]);
 await c.query('UPDATE lemon_payments SET order_id=$1 WHERE operation_id=upper(trim($2)) OR external_id=trim($2)',[id,reference]);
 await log(c,actor,'order.approved',{order:id});return {ok:true};
 });}
export function registerCommerce(app){
 const admin=async(req,reply)=>{if(req.user.role!=='ADMIN')return reply.code(403).send({error:'Solo administradores'});};
 const opts={preHandler:admin};
 app.get('/api/orders/:id',opts,async req=>{
  const [o]=await rows('SELECT id,renewal_of,product_name,days,status,price_cents FROM orders WHERE id=$1',[z.string().uuid().parse(req.params.id)]);
  if(!o)fail('Pedido no encontrado',404);return o;
 });
 app.get('/api/orders/:id/renewal-account',opts,async req=>{
  const [account]=await rows('SELECT s.secret,p.expires_at FROM orders o JOIN orders p ON p.id=o.renewal_of JOIN stock s ON s.id=p.stock_id WHERE o.id=$1',[z.string().uuid().parse(req.params.id)]);
  if(!account)fail('Renovación no encontrada',404);
  return {email:JSON.parse(decrypt(account.secret)).email,expires_at:account.expires_at};
 });
 app.post('/api/orders/external',opts,async req=>registerExternalSale(req.body,req.user.id));
 app.get('/api/external-stock',opts,async()=>{
  const stock=await rows("SELECT s.id,s.product_id,s.secret FROM stock s WHERE s.state='AVAILABLE' ORDER BY s.created_at DESC LIMIT 500");
  return stock.map(s=>({id:s.id,product_id:s.product_id,email:JSON.parse(decrypt(s.secret)).email}));
 });
 app.get('/api/products',opts,async()=>rows("SELECT p.*,count(s.id) FILTER(WHERE s.state='AVAILABLE' AND (s.expires_on IS NULL OR s.expires_on >= (now() AT TIME ZONE 'America/Lima')::date+p.days))::integer AS available FROM products p LEFT JOIN stock s ON s.product_id=p.id GROUP BY p.id ORDER BY p.name"));
 app.post('/api/products',opts,async req=>{const p=productSchema.parse(req.body);return transaction(async c=>{const r=await c.query('INSERT INTO products(code,name,price_cents,days,active) VALUES($1,$2,$3,$4,$5) RETURNING id',[p.code,p.name,p.price_cents,p.days,p.active]);await log(c,req.user.id,'product.created',{id:r.rows[0].id});return r.rows[0];});});
 app.put('/api/products/:id',opts,async req=>{const p=productSchema.parse(req.body),id=z.string().uuid().parse(req.params.id);return transaction(async c=>{const r=await c.query('UPDATE products SET code=$1,name=$2,price_cents=$3,days=$4,active=$5 WHERE id=$6 RETURNING id',[p.code,p.name,p.price_cents,p.days,p.active,id]);if(!r.rowCount)fail('Producto no encontrado',404);await log(c,req.user.id,'product.updated',{id,active:p.active});return {ok:true};});});
 app.get('/api/stock',opts,async()=>rows('SELECT s.id,s.product_id,p.name,s.state,s.expires_on,s.created_at FROM stock s JOIN products p ON p.id=s.product_id ORDER BY s.created_at DESC LIMIT 500'));
 app.post('/api/stock',opts,async req=>{const s=stockSchema.parse(req.body);if(s.expires_on&&(!Number.isFinite(Date.parse(s.expires_on))||s.expires_on<new Date().toISOString().slice(0,10)))fail('Revisa la fecha de vencimiento',400);const secret=encrypt(JSON.stringify({email:s.email,password:s.password})),fingerprint=createHmac('sha256',key()).update(s.product_id+':'+s.email.trim().toLowerCase()).digest('hex');return transaction(async c=>{const r=await c.query('INSERT INTO stock(product_id,secret,fingerprint,expires_on) VALUES($1,$2,$3,$4) RETURNING id',[s.product_id,secret,fingerprint,s.expires_on]);await log(c,req.user.id,'stock.created',{id:r.rows[0].id});return r.rows[0];});});
 app.post('/api/stock/:id/disable',opts,async req=>transaction(async c=>{const id=z.string().uuid().parse(req.params.id);const r=await c.query("UPDATE stock SET state='DISABLED' WHERE id=$1 AND state='AVAILABLE'",[id]);if(!r.rowCount)fail('Solo puedes retirar cuentas disponibles.');await log(c,req.user.id,'stock.disabled',{id});return {ok:true};}));
 app.get('/api/orders',opts,async()=>{
  const orders=await rows('SELECT o.id,o.renewal_of,o.customer,o.jid,o.product_name,o.price_cents,o.days,o.status,o.stock_id,o.payment_ref,o.created_at,o.started_at,o.expires_at,o.delivered_at,o.sheets_synced_at,(o.receipt IS NOT NULL) AS has_receipt FROM orders o ORDER BY o.created_at DESC LIMIT 300');
  return orders.map(o=>({...o,product_name:o.renewal_of?'Renovación · '+o.product_name:o.product_name}));
 });
 app.get('/api/orders/:id/receipt',opts,async(req,reply)=>{const [o]=await rows('SELECT receipt,receipt_mime FROM orders WHERE id=$1',[z.string().uuid().parse(req.params.id)]);if(!o?.receipt)fail('No hay comprobante',404);return reply.type(o.receipt_mime).header('Content-Disposition','inline').send(Buffer.from(decrypt(o.receipt),'base64'));});
 app.post('/api/orders/:id/approve',opts,async req=>{const {reference,service_renewed}=z.object({reference:z.string().trim().min(4).max(100).transform(v=>v.toUpperCase()),confirmed:z.literal(true),service_renewed:z.boolean().optional()}).strict().parse(req.body);return approveOrder(z.string().uuid().parse(req.params.id),reference,req.user.id,service_renewed);});
 app.post('/api/orders/:id/reject',opts,async req=>transaction(async c=>{const id=z.string().uuid().parse(req.params.id),{reason}=z.object({reason:z.string().trim().min(8).max(500)}).strict().parse(req.body);const r=await c.query("UPDATE orders SET status='REJECTED',sheets_synced_at=null WHERE id=$1 AND status='PENDING'",[id]);if(!r.rowCount)fail('Solo puedes rechazar pedidos pendientes.');await log(c,req.user.id,'order.rejected',{id,reason});return {ok:true};}));
 app.get('/api/reports',opts,async()=>({...(await rows('SELECT * FROM commerce_sync WHERE id=1'))[0],pending:Number((await rows('SELECT count(*) AS n FROM orders WHERE sheets_synced_at IS NULL'))[0].n),url:'https://docs.google.com/spreadsheets/d/'+(process.env.SHEETS_ID||'')+'/edit'}));
}
