import test from 'node:test';
import assert from 'node:assert/strict';
import {db} from '../src/db.js';
import {encrypt,approveOrder} from '../src/commerce.js';
import {recordPayer,reconcileLemon,requestPayerCorrection} from '../src/lemon-payments.js';
import {randomUUID} from 'node:crypto';
import {selectPayment} from '../src/payment-choice.js';
import {enqueueDelayedPaymentAlerts,deliverAdminAlerts} from '../src/admin-alerts.js';

test('isolated PostgreSQL: Lemon identity, uniqueness, concurrent approval and stock guards',{skip:process.env.RUN_LEMON_TEST!=='1'},async()=>{
 assert.equal(new URL(process.env.DATABASE_URL).pathname,'/marketing_lemon_test');
 try{
  await db.query('TRUNCATE lemon_payments,orders,stock,products,audit RESTART IDENTITY CASCADE');
  const [i]=(await db.query('SELECT id FROM instances LIMIT 1')).rows;
  const [p]=(await db.query("INSERT INTO products(code,name,price_cents,days) VALUES('lemon-test','Test',700,30) RETURNING id")).rows;
  const [admin]=(await db.query("INSERT INTO users(email,password_hash,role) VALUES('lemon-test@example.invalid','test','ADMIN') ON CONFLICT(email) DO UPDATE SET active=true RETURNING id")).rows;
  await db.query("UPDATE lemon_verifier SET enabled=true,activated_at=now()-interval '3 hours' WHERE id=1");
  let n=0;
  const paidTime=new Date(Math.floor(Date.now()/60000)*60000-300000).toISOString();
  async function order(name='MARIA ELENA PRUEBA',receipt=true,stock=true){
   const jid=`test-${++n}@s.whatsapp.net`;
   if(stock)await db.query('INSERT INTO stock(product_id,secret,fingerprint) VALUES($1,$2,$3)',[p.id,encrypt(JSON.stringify({email:'test@example.invalid',password:'synthetic'})),randomUUID()]);
   return (await db.query("INSERT INTO orders(instance_id,jid,customer,product_id,product_name,price_cents,days,receipt,receipt_amount_cents,receipt_operation_minute,lemon_payer_normalized,created_at) VALUES($1,$2,'Test',$3,'Test',700,30,$4,700,$6,$5,now()-interval '10 minutes') RETURNING *",[i.id,jid,p.id,receipt?'synthetic':null,name,paidTime])).rows[0];
  }
  function payment(name='MARIA ELENA PRUEBA'){
   return {payer:name,operation_id:randomUUID().toUpperCase(),external_id:'20261021'+String(++n).padStart(15,'0'),amount_cents:700,currency:'PEN',paid_at:paidTime,received_at:paidTime};
  }
  async function state(o){return (await db.query('SELECT * FROM orders WHERE id=$1',[o.id])).rows[0];}
  const a=await order(),pay=payment();
  const concurrent=await Promise.all([reconcileLemon([pay]),reconcileLemon([pay])]);
  assert.equal(concurrent.reduce((s,r)=>s+r.approved,0),1);
  assert.equal((await state(a)).status,'APPROVED');
  assert.equal((await db.query('SELECT order_id FROM lemon_payments WHERE operation_id=$1',[pay.operation_id])).rows[0].order_id,a.id);
  const b=await order();await reconcileLemon([pay]);assert.equal((await state(b)).status,'PENDING');
  await assert.rejects(approveOrder(b.id,pay.external_id,admin.id));
  await assert.rejects(approveOrder(b.id,pay.operation_id.toLowerCase(),admin.id));
  await db.query("UPDATE orders SET status='REJECTED' WHERE id=$1",[b.id]);
  const c=await order('OTRO TITULAR'),d=await order('OTRO TITULAR'),ambiguous=payment('OTRO TITULAR');
  await reconcileLemon([ambiguous]);assert.equal((await state(c)).status,'PENDING');assert.equal((await state(d)).status,'PENDING');
  const e=await order('DOS PAGOS');await reconcileLemon([payment('DOS PAGOS'),payment('DOS PAGOS')]);assert.equal((await state(e)).lemon_check,'AMBIGUOUS');
  const f=await order('IMPORTE ERRONEO');await reconcileLemon([{...payment('IMPORTE ERRONEO'),amount_cents:699}]);assert.equal((await state(f)).status,'PENDING');
  const g=await order('SIN COMPROBANTE',false);await reconcileLemon([payment('SIN COMPROBANTE')]);assert.equal((await state(g)).status,'PENDING');
  const h=await order('ANTES PEDIDO');await reconcileLemon([{...payment('ANTES PEDIDO'),paid_at:new Date(Date.now()-7200000).toISOString(),received_at:new Date(Date.now()-7199000).toISOString()}]);assert.equal((await state(h)).status,'PENDING');
  const j=await order('NOMBRE CORRECTO');await reconcileLemon([payment('NOMBRE INCORRECTO')]);assert.equal((await state(j)).status,'PENDING');
  const k=await order(null);await db.query('UPDATE orders SET lemon_name_requested_at=now() WHERE id=$1',[k.id]);
  assert.equal(await recordPayer(i.id,'other-chat@s.whatsapp.net','Persona Prueba'),null);
  await recordPayer(i.id,k.jid,'Persona Prueba');assert.equal((await state(k)).lemon_payer_normalized,'PERSONA PRUEBA');
  const l=await order(null);await db.query('UPDATE orders SET lemon_name_requested_at=now() WHERE id=$1',[l.id]);
  await recordPayer(i.id,l.jid,'Binance');assert.equal((await state(l)).lemon_check,'MANUAL_BINANCE');
  const m=await order('SIN STOCK',true,false);await db.query("UPDATE stock SET state='DISABLED' WHERE state='AVAILABLE'");
  await reconcileLemon([payment('SIN STOCK')]);assert.equal((await state(m)).lemon_check,'NO_STOCK');
  const z=await order('APAGADO');await db.query('UPDATE lemon_verifier SET enabled=false WHERE id=1');
  assert.equal((await reconcileLemon([payment('APAGADO')])).approved,0);assert.equal((await state(z)).status,'PENDING');
  assert.equal((await db.query("SELECT count(*)::int AS n FROM audit WHERE action='payment.lemon_verified'")).rows[0].n,1);
  await db.query("UPDATE orders SET status='REJECTED' WHERE status='PENDING'");
  await db.query('UPDATE lemon_verifier SET enabled=true WHERE id=1');
  await db.query("UPDATE orders SET status='DELIVERED',expires_at=now()+interval '20 days' WHERE id=$1",[a.id]);
  const parent=await state(a);
  const r=await order('RENOVACION PRUEBA',true,false);
  await db.query('UPDATE orders SET renewal_of=$1 WHERE id=$2',[a.id,r.id]);
  const renewalPay=payment('RENOVACION PRUEBA');
  const stockBefore=(await db.query('SELECT count(*)::int AS n FROM stock')).rows[0].n;
  const results=await Promise.all([reconcileLemon([renewalPay]),reconcileLemon([renewalPay])]);
  assert.equal(results.reduce((s,x)=>s+x.approved,0),1);
  const renewed=await state(r),updated=await state(a);
  assert.equal(renewed.status,'APPROVED');assert.equal(renewed.lemon_check,'VERIFIED');
  assert.equal(renewed.stock_id,null);assert.equal(updated.stock_id,parent.stock_id);
  assert.equal(renewed.started_at.toISOString(),parent.expires_at.toISOString());
  assert.equal(renewed.expires_at.toISOString(),updated.expires_at.toISOString());
  assert.ok(updated.expires_at>parent.expires_at);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM stock')).rows[0].n,stockBefore);
  await assert.rejects(approveOrder(z.id,renewalPay.external_id,admin.id));
  assert.equal((await db.query("SELECT count(*)::int AS n FROM audit WHERE action='renewal.approved'")).rows[0].n,1);
  const choice=await order(null,false,false);
  assert.ok((await selectPayment(i.id,choice.jid,'BINANCE')).order);
  assert.equal((await state(choice)).lemon_check,'MANUAL_BINANCE');
  await selectPayment(i.id,choice.jid,'QR');
  assert.equal((await state(choice)).lemon_check,'QR_SELECTED');
  await db.query("UPDATE orders SET receipt='synthetic' WHERE id=$1",[choice.id]);
  assert.ok((await selectPayment(i.id,choice.jid,'BINANCE')).error);
  assert.equal((await state(choice)).lemon_check,'QR_SELECTED');
  assert.ok((await selectPayment(i.id,'unknown-chat','QR')).error);
  for(const amount of [null,699]){
   const bad=await order(amount===null?'CAPTURA ILEGIBLE':'CAPTURA INCORRECTA');
   await db.query('UPDATE orders SET receipt_amount_cents=$1 WHERE id=$2',[amount,bad.id]);
   await reconcileLemon([payment(bad.lemon_payer_normalized)]);
   assert.equal((await state(bad)).status,'PENDING');
   assert.equal((await state(bad)).lemon_check,amount===null?'RECEIPT_UNREADABLE':'RECEIPT_AMOUNT_MISMATCH');
  }
  const fix=await order('NOMBRE EQUIVOCADO');
  const fixPayment=payment('TITULAR CORRECTO');
  await reconcileLemon([fixPayment]);
  assert.equal((await state(fix)).lemon_check,'NAME_MISMATCH');
  assert.match(await requestPayerCorrection(i.id,'unrelated-chat'),/No tienes/);
  await requestPayerCorrection(i.id,fix.jid);
  let correcting=await state(fix);
  assert.equal(correcting.receipt,fix.receipt);assert.equal(correcting.receipt_amount_cents,700);
  assert.equal(correcting.lemon_payer_normalized,null);
  await reconcileLemon([fixPayment]);assert.equal((await state(fix)).status,'PENDING');
  await recordPayer(i.id,fix.jid,'Titular Correcto');
  await reconcileLemon([fixPayment]);assert.equal((await state(fix)).status,'APPROVED');
  assert.match(await requestPayerCorrection(i.id,fix.jid),/No tienes/);
  const manual=await order(null,false);
  const wrongTime=await order('HORA DISTINTA');
  await db.query("UPDATE orders SET receipt_operation_minute=receipt_operation_minute+interval '1 minute' WHERE id=$1",[wrongTime.id]);
  await reconcileLemon([payment('HORA DISTINTA')]);
  assert.equal((await state(wrongTime)).status,'PENDING');
  assert.equal((await state(wrongTime)).lemon_check,'RECEIPT_TIME_MISMATCH');
  await db.query('UPDATE orders SET receipt_operation_minute=null WHERE id=$1',[wrongTime.id]);
  await reconcileLemon([]);assert.equal((await state(wrongTime)).lemon_check,'RECEIPT_TIME_UNREADABLE');
  await selectPayment(i.id,manual.jid,'BINANCE');
  await db.query("UPDATE orders SET receipt='synthetic' WHERE id=$1",[manual.id]);
  assert.match(await requestPayerCorrection(i.id,manual.jid),/Binance/);
  const late=await order('ALERTA PENDIENTE'),recent=await order('ALERTA RECIENTE'),done=await order('ALERTA APROBADA');
  for(const [o,minutes] of [[late,6],[recent,4],[done,6]]){
   await db.query("INSERT INTO sales_admin_alerts(order_id,kind,created_at) VALUES($1,'RECEIPT',now()-$2::int*interval '1 minute') ON CONFLICT DO NOTHING",[o.id,minutes]);
  }
  await db.query("UPDATE orders SET status='REJECTED' WHERE id=$1",[done.id]);
  await Promise.all([enqueueDelayedPaymentAlerts(),enqueueDelayedPaymentAlerts()]);
  const delayed=(await db.query("SELECT order_id FROM sales_admin_alerts WHERE kind='PAYMENT_DELAYED'")).rows;
  assert.deepEqual(delayed.map(x=>x.order_id),[late.id]);
  await db.query("UPDATE sales_admin_alerts SET status='SKIPPED' WHERE kind!='PAYMENT_DELAYED'");
  const sent=[];
  const running=new Map([[i.id,{connected:true,socket:{sendMessage:async(jid,body)=>sent.push({jid,body})}}]]);
  await deliverAdminAlerts(running);await deliverAdminAlerts(running);
  assert.equal(sent.length,1);assert.equal(sent[0].jid,'51978640413@s.whatsapp.net');
  assert.match(sent[0].body.text,/5 minutos/);
 }finally{await db.end();}
});
