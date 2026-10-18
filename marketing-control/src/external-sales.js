import {z} from 'zod';
import {transaction,encrypt,accountFingerprint} from './commerce.js';
import {requireSalesInstance} from './instance-purpose.js';
export const externalSalesSchema=`
ALTER TABLE orders ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'BOT';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS external_key uuid UNIQUE;
INSERT INTO schema_migrations(version) VALUES(5) ON CONFLICT DO NOTHING;
`;
export const externalSaleSchema=z.object({
 request_id:z.string().uuid(),instance_id:z.string().uuid(),customer:z.string().trim().min(2).max(100),
 phone:z.string().regex(/^[1-9][0-9]{7,14}$/),product_id:z.string().uuid(),stock_id:z.string().uuid().nullable(),
 email:z.string().email().max(254).optional(),password:z.string().min(1).max(256).optional(),
 started_at:z.string().datetime({offset:true}),expires_at:z.string().datetime({offset:true}),
 price_cents:z.number().int().min(0).max(10000000),reference:z.string().trim().max(100),confirmed:z.literal(true)
}).strict().superRefine((v,ctx)=>{
 if(!v.stock_id&&(!v.email||!v.password))ctx.addIssue({code:'custom',message:'Ingresa correo y contraseña o selecciona una cuenta.'});
 const start=Date.parse(v.started_at),end=Date.parse(v.expires_at);
 if(start>Date.now()||end<=start||end<=Date.now()||end-start>3660*86400000)ctx.addIssue({code:'custom',message:'Revisa las fechas: inicio pasado y vencimiento futuro.'});
});
const fail=message=>{throw Object.assign(new Error(message),{statusCode:409,publicMessage:message});};
export async function registerExternalSale(input,actor){
 const v=externalSaleSchema.parse(input);
 return transaction(async c=>{
  await c.query('SELECT pg_advisory_xact_lock(hashtext($1))',[v.request_id]);
  const old=(await c.query('SELECT id FROM orders WHERE external_key=$1',[v.request_id])).rows[0];if(old)return old;
  const instance=await requireSalesInstance(c,v.instance_id);if(instance.status!=='CONNECTED')fail('Selecciona el bot de ventas conectado.');
  const p=(await c.query('SELECT * FROM products WHERE id=$1',[v.product_id])).rows[0];if(!p)fail('Producto no encontrado.');
  let s;
  if(v.stock_id)s=(await c.query('SELECT * FROM stock WHERE id=$1 FOR UPDATE',[v.stock_id])).rows[0];
  else s=(await c.query('INSERT INTO stock(product_id,secret,fingerprint) VALUES($1,$2,$3) RETURNING *',[p.id,encrypt(JSON.stringify({email:v.email.trim(),password:v.password})),accountFingerprint(p.id,v.email)])).rows[0];
  if(!s||s.product_id!==p.id||s.state!=='AVAILABLE')fail('La cuenta no está disponible para esa plataforma.');
  const [valid]=(await c.query("SELECT $1::date IS NULL OR (($1::date+1)::timestamp AT TIME ZONE 'America/Lima') >= $2::timestamptz AS ok",[s.expires_on,v.expires_at])).rows;if(!valid.ok)fail('El inventario vence antes de la fecha indicada.');
  const o=(await c.query(`INSERT INTO orders(instance_id,jid,customer,product_id,product_name,price_cents,days,status,stock_id,payment_ref,approved_by,approved_at,started_at,expires_at,source,external_key)
   VALUES($1,$2,$3,$4,$5,$6,$7,'APPROVED',$8,$9,$10,$11,$11,$12,'EXTERNAL',$13) RETURNING id`,[v.instance_id,v.phone+'@s.whatsapp.net',v.customer,p.id,p.name,v.price_cents,Math.ceil((Date.parse(v.expires_at)-Date.parse(v.started_at))/86400000),s.id,v.reference.toUpperCase()||null,actor,v.started_at,v.expires_at,v.request_id])).rows[0];
  await c.query("UPDATE stock SET state='SOLD' WHERE id=$1",[s.id]);
  await c.query("INSERT INTO audit(actor,action,details) VALUES($1,'order.external_registered',$2)",[actor,JSON.stringify({order:o.id})]);
  return o;
 });
}
