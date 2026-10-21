import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {fileURLToPath} from 'node:url';
import {db,rows} from './db.js';
import {transaction} from './commerce.js';
import {requireSalesInstance} from './instance-purpose.js';
import {approveRenewal} from './renewals.js';
import {normalizePayer,matchesPayment} from './lemon-match.js';
const execute=promisify(execFile);
let lastPoll=0,busy=false;
export async function lemonEnabled(){return !!(await rows('SELECT enabled FROM lemon_verifier WHERE id=1'))[0]?.enabled;}

export const correctionHint='✍️ Escribe /corregirnombre para enviar nuevamente el nombre completo del titular. No necesitas volver a pagar ni reenviar la captura.';
export async function requestPayerCorrection(instance,jid){
 return transaction(async c=>{
  await c.query("SELECT pg_advisory_xact_lock(hashtext('lemon-payment-verification'))");
  const [o]=(await c.query("SELECT * FROM orders WHERE instance_id=$1 AND jid=$2 AND status='PENDING' FOR UPDATE",[instance,jid])).rows;
  if(!o)return 'No tienes un pedido pendiente que permita corregir el nombre. Consulta /pedidos.';
  if(!o.receipt)return 'Primero elige el método de pago y envía el comprobante de tu pedido.';
  if(o.lemon_check==='MANUAL_BINANCE')return 'Tu pago es por Binance y requiere revisión manual. Escribe /soporte si necesitas corregir datos.';
  if(o.lemon_name_requested_at)return '✍️ Envía ahora el nombre completo y apellidos del titular que realizó el pago. Conservamos tu pedido y comprobante; no vuelvas a pagar.';
  const [limit]=(await c.query("SELECT count(*)::int AS n FROM audit WHERE action='payment.name_correction_requested' AND details->>'order'=$1 AND created_at>now()-interval '15 minutes'",[o.id])).rows;
  if(limit.n>=5)return 'Has realizado varios intentos. Espera 15 minutos o escribe /soporte. No vuelvas a pagar.';
  await c.query("UPDATE orders SET lemon_payer=null,lemon_payer_normalized=null,lemon_name_requested_at=now(),lemon_name_notice_at=null,lemon_check='AWAITING_NAME',sheets_synced_at=null WHERE id=$1",[o.id]);
  await c.query("INSERT INTO audit(action,details) VALUES('payment.name_correction_requested',$1)",[{order:o.id}]);
  return '✍️ *Corrige el nombre del titular*\n\nEnvía en tu siguiente mensaje el nombre completo y los apellidos de quien realizó el pago. Revisa que no falten letras.\n\nConservamos tu pedido, captura e importe. No vuelvas a pagar ni reenviar el comprobante.';
 });
}

export async function recordPayer(instance,jid,text){
 return transaction(async c=>{
  await c.query("SELECT pg_advisory_xact_lock(hashtext('lemon-payment-verification'))");
  const [o]=(await c.query("SELECT * FROM orders WHERE instance_id=$1 AND jid=$2 AND status='PENDING' AND receipt IS NOT NULL AND lemon_name_requested_at IS NOT NULL FOR UPDATE",[instance,jid])).rows;
  if(!o)return null;
  if(text.trim().toLowerCase()==='binance'){
   await c.query("UPDATE orders SET lemon_name_requested_at=null,lemon_check='MANUAL_BINANCE',lemon_payer=null,lemon_payer_normalized=null WHERE id=$1",[o.id]);
   return '🟡 *Pago por Binance · Revisión manual*\nEl administrador comprobará el ingreso antes de aprobar tu pedido.';
  }
  const normalized=normalizePayer(text);
  if(!normalized)return '✍️ Envía únicamente el nombre completo y los apellidos del titular que pagó. No envíes números, comprobantes ni códigos.';
  await c.query("UPDATE orders SET lemon_payer=$1,lemon_payer_normalized=$2,lemon_name_requested_at=null,lemon_check='WAITING',sheets_synced_at=null WHERE id=$3",[text.trim(),normalized,o.id]);
  return '🔎 *JHELIZ · Verificación en curso*\n\nNombre del titular recibido. Buscaremos una coincidencia única con el pago de Lemon Cash.\n\n✅ Compra: recibirás tu cuenta automáticamente si hay stock.\n🔄 Renovación: actualizaremos la vigencia de tu misma cuenta y te enviaremos la nueva fecha.\n🟡 Si falta información o hay varias coincidencias, un administrador lo revisará.\n\n📦 Consultar estado → /pedidos';
 });
}

export async function reconcileLemon(payments){
 return transaction(async c=>{
  await c.query("SELECT pg_advisory_xact_lock(hashtext('lemon-payment-verification'))");
  const [config]=(await c.query('SELECT * FROM lemon_verifier WHERE id=1 FOR UPDATE')).rows;
  if(!config?.enabled||!config.activated_at)return {approved:0};
  // Validate the entire batch before any mutation. Fail closed on malformed input.
  for(const p of payments){
   p.payer_normalized=normalizePayer(p.payer);
   if(!p.payer_normalized||p.currency!=='PEN'||!Number.isSafeInteger(p.amount_cents)||p.amount_cents<=0||
      !/^[A-F0-9]{8}(?:-[A-F0-9]{4}){3}-[A-F0-9]{12}$/.test(p.operation_id)||!/^\d{10,60}$/.test(p.external_id)||
      !Number.isFinite(Date.parse(p.paid_at))||!Number.isFinite(Date.parse(p.received_at)))throw new Error('Invalid payment batch');
  }
  for(const p of payments){
   const existing=(await c.query('SELECT * FROM lemon_payments WHERE operation_id=$1 OR external_id=$2 FOR UPDATE',[p.operation_id,p.external_id])).rows;
   if(existing.length){
    if(existing.some(x=>x.operation_id!==p.operation_id||x.external_id!==p.external_id||x.amount_cents!==p.amount_cents||x.payer_normalized!==p.payer_normalized||new Date(x.paid_at).getTime()!==Date.parse(p.paid_at))){
     await c.query('UPDATE lemon_payments SET blocked=true WHERE operation_id=$1 OR external_id=$2',[p.operation_id,p.external_id]);
    }
   }else await c.query('INSERT INTO lemon_payments(operation_id,external_id,payer_normalized,amount_cents,paid_at,received_at) VALUES($1,$2,$3,$4,$5,$6)',[p.operation_id,p.external_id,p.payer_normalized,p.amount_cents,p.paid_at,p.received_at]);
  }
  const orders=(await c.query("SELECT * FROM orders WHERE status='PENDING' AND receipt IS NOT NULL AND lemon_payer_normalized IS NOT NULL AND created_at >= $1 ORDER BY created_at FOR UPDATE",[config.activated_at])).rows;
  const ledger=(await c.query("SELECT *, 'PEN' AS currency FROM lemon_payments WHERE paid_at>=now()-interval '1 day' FOR UPDATE")).rows;
  let approved=0;
  for(const o of orders){
   if(!o.receipt_operation_minute){await c.query("UPDATE orders SET lemon_check='RECEIPT_TIME_UNREADABLE' WHERE id=$1",[o.id]);continue;}
   if(o.receipt_amount_cents!==o.price_cents){
    await c.query('UPDATE orders SET lemon_check=$1 WHERE id=$2',[o.receipt_amount_cents==null?'RECEIPT_UNREADABLE':'RECEIPT_AMOUNT_MISMATCH',o.id]);continue;
   }
   const matches=ledger.filter(p=>matchesPayment(o,p));
   if(matches.length!==1){
    const nameMismatch=!matches.length&&ledger.some(p=>!p.blocked&&!p.order_id&&matchesPayment({...o,lemon_payer_normalized:p.payer_normalized},p));
    const timeMismatch=!matches.length&&!nameMismatch&&ledger.some(p=>!p.blocked&&!p.order_id&&matchesPayment({...o,receipt_operation_minute:p.received_at},p));
    await c.query('UPDATE orders SET lemon_check=$1 WHERE id=$2',[matches.length?'AMBIGUOUS':nameMismatch?'NAME_MISMATCH':timeMismatch?'RECEIPT_TIME_MISMATCH':'WAITING',o.id]);continue;
   }
   const p=matches[0];
   if(p.blocked||p.order_id||orders.filter(other=>matchesPayment(other,p)).length!==1){
    await c.query("UPDATE orders SET lemon_check='AMBIGUOUS_OR_USED' WHERE id=$1",[o.id]);continue;
   }
   // Check both aliases against ALL previous manual/automatic references.
   const reused=await c.query('SELECT id FROM orders WHERE upper(trim(payment_ref))=ANY($1::text[])',[ [p.operation_id,p.external_id] ]);
   if(reused.rowCount){await c.query('UPDATE lemon_payments SET blocked=true WHERE operation_id=$1',[p.operation_id]);continue;}
   await requireSalesInstance(c,o.instance_id);
   if(o.renewal_of){
    // Owner confirms these services are already renewed upstream.
    // Keep a bad renewal from blocking valid payments in the same batch.
    await c.query('SAVEPOINT lemon_renewal');
    try{await approveRenewal(c,o,p.operation_id,null,true);}
    catch(error){
     await c.query('ROLLBACK TO SAVEPOINT lemon_renewal');
     if(error.statusCode!==409)throw error;
     await c.query("UPDATE orders SET lemon_check='RENEWAL_REVIEW' WHERE id=$1",[o.id]);
     await c.query('RELEASE SAVEPOINT lemon_renewal');continue;
    }
    await c.query('RELEASE SAVEPOINT lemon_renewal');
    await c.query("UPDATE orders SET lemon_check='VERIFIED' WHERE id=$1",[o.id]);
   }else{
   const [stock]=(await c.query("SELECT id FROM stock WHERE product_id=$1 AND state='AVAILABLE' AND (expires_on IS NULL OR expires_on >= (now() AT TIME ZONE 'America/Lima')::date+$2::integer) ORDER BY expires_on NULLS LAST,created_at FOR UPDATE SKIP LOCKED LIMIT 1",[o.product_id,o.days])).rows;
   if(!stock){await c.query("UPDATE orders SET lemon_check='NO_STOCK' WHERE id=$1",[o.id]);continue;}
   await c.query("UPDATE stock SET state='SOLD' WHERE id=$1",[stock.id]);
   await c.query("UPDATE orders SET status='APPROVED',stock_id=$1,payment_ref=$2,approved_by=null,approved_at=now(),lemon_check='VERIFIED',sheets_synced_at=null WHERE id=$3",[stock.id,p.operation_id,o.id]);
   }
   await c.query('UPDATE lemon_payments SET order_id=$1 WHERE operation_id=$2',[o.id,p.operation_id]);
   await c.query("INSERT INTO audit(action,details) VALUES('payment.lemon_verified',$1)",[{order:o.id,operation:p.operation_id,amount_cents:p.amount_cents,source:'authenticated_gmail'}]);
   p.order_id=o.id;approved++;
  }
  await c.query('UPDATE lemon_verifier SET last_success=now(),last_error=null WHERE id=1');
  return {approved};
 });
}

export async function verifyLemonPayments(){
 if(busy||Date.now()-lastPoll<60000)return;
 busy=true;lastPoll=Date.now();
 try{
  if(!await lemonEnabled())return;
  const [pending]=await rows("SELECT id FROM orders WHERE status='PENDING' AND lemon_payer_normalized IS NOT NULL LIMIT 1");
  if(!pending)return;
  const {stdout}=await execute('python3',[fileURLToPath(new URL('./lemon-mail.py',import.meta.url))],{timeout:90000,maxBuffer:1000000});
  const result=JSON.parse(stdout);
  if(result.ok!==true||!Array.isArray(result.payments))throw new Error('Mail unavailable');
  await reconcileLemon(result.payments);
 }catch{
  await db.query("UPDATE lemon_verifier SET last_error='Verificación no disponible; pago pendiente de revisión manual.' WHERE id=1").catch(()=>{});
 }finally{busy=false;}
}
