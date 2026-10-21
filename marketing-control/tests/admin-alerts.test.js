import test from 'node:test';
import assert from 'node:assert/strict';
import {adminAlertText,ADMIN_ALERT_JID,pendingPaymentReason} from '../src/admin-alert-copy.js';
test('admin destination is the explicitly confirmed Peru number',()=>{
 assert.equal(ADMIN_ALERT_JID,'51978640413@s.whatsapp.net');
});
test('delayed alert explains reason without links, names from email or secrets',()=>{
 const o={id:'test',customer:'Cliente',product_name:'Disney',price_cents:1000,receipt_amount_cents:1000,receipt_operation_minute:new Date(),has_payer:true,lemon_check:'NAME_MISMATCH'};
 assert.match(pendingPaymentReason(o),/nombre enviado/);
 assert.match(pendingPaymentReason({...o,lemon_check:'RECEIPT_TIME_MISMATCH'}),/minuto/);
 assert.match(pendingPaymentReason({...o,lemon_check:'NO_STOCK'}),/cuenta disponible/);
 assert.match(pendingPaymentReason({...o,receipt_amount_cents:null}),/monto único/);
 const text=adminAlertText(o,'PAYMENT_DELAYED');
 assert.match(text,/5 minutos/);assert.match(text,/Aviso único/);assert.match(text,/S\/ 10.00/);
 assert.doesNotMatch(text,/https?:\/\//);
});
test('alerts retain references and never include credentials or proof images',()=>{
 const order={id:'order-test',customer:'Ana\n*aprobado*',product_name:'Netflix',price_cents:3500,days:30,password:'secret-test',receipt:'private-image'};
 for(const kind of ['ORDER','RECEIPT']){
  const text=adminAlertText(order,kind);
  for(const value of ['order-test','S/ 35.00','NO confirma el pago'])assert.ok(text.includes(value));
  assert.doesNotMatch(text,/https?:\/\/|marketingjhelizxyz/);
  assert.ok(!text.includes('secret-test'));assert.ok(!text.includes('private-image'));
  assert.ok(!text.includes('Ana\n*aprobado*'));
 }
});
