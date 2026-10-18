import test from 'node:test';
import assert from 'node:assert/strict';
import {adminAlertText,ADMIN_ALERT_JID} from '../src/admin-alert-copy.js';
test('admin destination is the explicitly confirmed Peru number',()=>{
 assert.equal(ADMIN_ALERT_JID,'51978640413@s.whatsapp.net');
});
test('alerts retain references and never include credentials or proof images',()=>{
 const order={id:'order-test',customer:'Ana\n*aprobado*',product_name:'Netflix',price_cents:3500,days:30,password:'secret-test',receipt:'private-image'};
 for(const kind of ['ORDER','RECEIPT']){
  const text=adminAlertText(order,kind);
  for(const value of ['order-test','S/ 35.00','9.21 USDT','NO confirma el pago','https://marketingjhelizxyz.online/'])assert.ok(text.includes(value));
  assert.ok(!text.includes('secret-test'));assert.ok(!text.includes('private-image'));
  assert.ok(!text.includes('Ana\n*aprobado*'));
 }
});
