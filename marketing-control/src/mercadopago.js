import {db,rows,event} from './db.js';
import {transaction} from './commerce.js';
import {requireSalesInstance} from './instance-purpose.js';
import {approveRenewal} from './renewals.js';
import {mpConfig,mpEnabled,mpRequest,validSignature,validPayment,cents,preferenceData,checkoutUrl} from './mercadopago-client.js';

const lock=c=>c.query("SELECT pg_advisory_xact_lock(hashtext('lemon-payment-verification'))");
const problem=message=>({error:message});
export async function selectMercadoPago(instance,jid,request=mpRequest,config=mpConfig()){
 // Persist the intent BEFORE contacting MP: a timeout must not allow a second provider.
 const selected=await transaction(async c=>{
  await lock(c);
  const [o]=(await c.query("SELECT * FROM orders WHERE instance_id=$1 AND jid=$2 AND status='PENDING' FOR UPDATE",[instance,jid])).rows;
  if(!o)return problem('No tienes un pedido pendiente. Escribe /catalogo.');
  if(['MP_NO_STOCK','MP_RENEWAL_REVIEW'].includes(o.lemon_check))return problem('Tu pago ya fue confirmado. La entrega requiere revisión; no vuelvas a pagar. Escribe /soporte.');
  await requireSalesInstance(c,instance);
  if(o.receipt||o.lemon_check&&!o.lemon_check.startsWith('MP_'))return problem('Tu pedido ya tiene otro método de pago. Consulta /soporte antes de cambiarlo.');
  await c.query('INSERT INTO mp_checkouts(order_id) VALUES($1) ON CONFLICT DO NOTHING',[o.id]);
  await c.query("UPDATE orders SET lemon_check='MP_PENDING',lemon_name_requested_at=null WHERE id=$1",[o.id]);
  return {order:o};
 });
 if(selected.error)return selected;
 return transaction(async c=>{
  // Only one preference creator per order, even across worker replicas.
  const [o]=(await c.query('SELECT * FROM orders WHERE id=$1 FOR UPDATE',[selected.order.id])).rows;
  const [checkout]=(await c.query('SELECT * FROM mp_checkouts WHERE order_id=$1 FOR UPDATE',[o.id])).rows;
  if(o.status!=='PENDING')return problem('Este pedido ya fue procesado. Consulta /pedidos.');
  if(checkout.checkout_url)return {order:o,url:checkout.checkout_url};
  const preference=await request('/checkout/preferences',{method:'POST',body:preferenceData(o,config),config});
  if(!checkoutUrl(preference.init_point)||String(preference.collector_id)!==config.collector||!preference.id)throw new Error('Invalid preference');
  await c.query("UPDATE mp_checkouts SET preference_id=$1,checkout_url=$2,state='READY' WHERE order_id=$3",[preference.id,preference.init_point,o.id]);
  return {order:o,url:preference.init_point};
 });
}
export const mercadoPagoText=result=>`💳 *Mercado Pago · S/ ${(result.order.price_cents/100).toFixed(2)}*\n\n${result.order.product_name}\n\nAbre tu enlace y elige Yape entre los medios disponibles:\n${result.url}\n\nEl monto ya está incluido. No envíes capturas ni códigos de autorización al bot. Confirmaremos el pago automáticamente.\nPedido: ${result.order.id}\n/pedidos · Estado\n/soporte · Ayuda`;

export async function applyMercadoPago(p,config=mpConfig()){
 if(!/^wa:[0-9a-f-]{36}$/.test(p.external_reference||'')||!/^\d{1,30}$/.test(String(p.id)))return 'IGNORED';
 return transaction(async c=>{
  await lock(c);
  const [o]=(await c.query('SELECT o.* FROM orders o JOIN mp_checkouts m ON m.order_id=o.id WHERE o.id::text=$1 FOR UPDATE OF o',[p.external_reference.slice(3)])).rows;
  if(!o)return 'IGNORED';
  const [existing]=(await c.query('SELECT * FROM mp_payments WHERE payment_id=$1 FOR UPDATE',[String(p.id)])).rows;
  if(existing&&existing.order_id!==o.id)return 'IGNORED';
  if(existing?.outcome==='APPLIED'){
   if(!validPayment(p,o,config)&&p.status!==existing.status){
    await c.query("UPDATE mp_payments SET status=$1,updated_at=now() WHERE payment_id=$2",[p.status,String(p.id)]);
    await c.query("UPDATE orders SET status='REVIEW',sheets_synced_at=null WHERE id=$1 AND status='APPROVED'",[o.id]);
    await c.query("INSERT INTO events(level,message) VALUES('ERROR',$1)",['Mercado Pago: cambio posterior al pago; revisar pedido '+o.id]);
   }
   return 'ALREADY_APPLIED';
  }
  let outcome='UNVERIFIED';
  if(validPayment(p,o,config)){
   outcome='ORDER_REVIEW';
   if(o.status==='PENDING'&&o.lemon_check?.startsWith('MP_')){
    await requireSalesInstance(c,o.instance_id);
    if(o.renewal_of){
     await c.query('SAVEPOINT mp_renewal');
     try{await approveRenewal(c,o,'MP:'+p.id,null,true);outcome='APPLIED';}
     catch(e){await c.query('ROLLBACK TO SAVEPOINT mp_renewal');if(e.statusCode!==409)throw e;outcome='RENEWAL_REVIEW';}
     await c.query('RELEASE SAVEPOINT mp_renewal');
    }else{
     const [s]=(await c.query("SELECT id FROM stock WHERE product_id=$1 AND state='AVAILABLE' AND (expires_on IS NULL OR expires_on >= (now() AT TIME ZONE 'America/Lima')::date+$2::integer) ORDER BY expires_on NULLS LAST,created_at FOR UPDATE SKIP LOCKED LIMIT 1",[o.product_id,o.days])).rows;
     if(!s)outcome='NO_STOCK';
     else{
      await c.query("UPDATE stock SET state='SOLD' WHERE id=$1",[s.id]);
      await c.query("UPDATE orders SET status='APPROVED',stock_id=$1,payment_ref=$2,approved_at=now(),sheets_synced_at=null WHERE id=$3",[s.id,'MP:'+p.id,o.id]);
      outcome='APPLIED';
     }
    }
    await c.query('UPDATE orders SET lemon_check=$1,sheets_synced_at=null WHERE id=$2',['MP_'+outcome,o.id]);
   }
  }
  await c.query(`INSERT INTO mp_payments(payment_id,order_id,status,amount_cents,outcome) VALUES($1,$2,$3,$4,$5)
   ON CONFLICT(payment_id) DO UPDATE SET status=excluded.status,amount_cents=excluded.amount_cents,outcome=excluded.outcome,updated_at=now()`,
   [String(p.id),o.id,String(p.status||'unknown').slice(0,50),cents(p.transaction_amount),outcome]);
  if(outcome!==existing?.outcome)await c.query("INSERT INTO audit(action,details) VALUES('payment.mercadopago',$1)",[{order:o.id,payment:String(p.id),outcome}]);
  if(outcome!==existing?.outcome&&['NO_STOCK','ORDER_REVIEW','RENEWAL_REVIEW'].includes(outcome))await c.query("INSERT INTO events(level,message) VALUES('ERROR',$1)",['Mercado Pago: pago confirmado requiere revisión ('+outcome+'). Pedido: '+o.id]);
  return outcome;
 });
}

export function registerMercadoPago(app,configProvider=mpConfig){
 app.post('/webhooks/mercadopago/',async(req,reply)=>{
  const dataId=req.query?.['data.id'];
  if(!validSignature(req.headers['x-signature'],req.headers['x-request-id'],dataId,configProvider().secret))return reply.code(401).send({error:'Invalid signature'});
  if(req.body?.type!=='payment'||String(req.body?.data?.id)!==dataId)return reply.code(400).send({error:'Invalid event'});
  await db.query(`INSERT INTO mp_webhook_queue(payment_id) VALUES($1) ON CONFLICT(payment_id)
   DO UPDATE SET version=mp_webhook_queue.version+1,next_attempt_at=now()`,[dataId]);
  return {received:true};
 });
}
let busy=false,lastPoll=0;
export async function verifyMercadoPago(){
 if(busy||Date.now()-lastPoll<10000)return;
 busy=true;lastPoll=Date.now();
 try{
  // Existing MP orders keep reconciling even if new checkout is disabled.
  const queue=await rows('SELECT * FROM mp_webhook_queue WHERE processed_version<version AND next_attempt_at<=now() ORDER BY next_attempt_at LIMIT 10');
  const pending=await rows("SELECT m.order_id FROM mp_checkouts m JOIN orders o ON o.id=m.order_id WHERE o.status='PENDING' AND m.next_check_at<=now() ORDER BY m.next_check_at LIMIT 5");
  if(!queue.length&&!pending.length)return;
  const config=mpConfig();
  for(const item of queue){
   try{
    const p=await mpRequest('/v1/payments/'+item.payment_id,{config});
    if(String(p.id)!==item.payment_id)throw new Error('Payment ID mismatch');
    await applyMercadoPago(p,config);
    await db.query('UPDATE mp_webhook_queue SET processed_version=$1,attempts=0 WHERE payment_id=$2',[item.version,item.payment_id]);
   }catch{
    await db.query("UPDATE mp_webhook_queue SET attempts=attempts+1,next_attempt_at=now()+interval '60 seconds' WHERE payment_id=$1",[item.payment_id]);
   }
  }
  for(const item of pending){
   await db.query("UPDATE mp_checkouts SET next_check_at=now()+interval '60 seconds' WHERE order_id=$1",[item.order_id]);
   try{
    const found=await mpRequest('/v1/payments/search?sort=date_created&criteria=desc&limit=50&external_reference='+encodeURIComponent('wa:'+item.order_id),{config});
    for(const result of found.results||[]){
     if(!/^\d{1,30}$/.test(String(result.id)))continue;
     const p=await mpRequest('/v1/payments/'+result.id,{config});
     if(String(p.id)===String(result.id))await applyMercadoPago(p,config);
    }
   }catch{await event(null,'ERROR','Mercado Pago: verificación pendiente; se reintentará automáticamente.').catch(()=>{});}
  }
 }catch{await event(null,'ERROR','Mercado Pago: verificador no disponible.').catch(()=>{});}
 finally{busy=false;}
}
