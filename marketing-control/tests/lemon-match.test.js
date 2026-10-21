import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePayer,matchesPayment,payerPrompt} from '../src/lemon-match.js';
const now=Date.parse('2026-10-21T12:00:00Z');
const o={lemon_payer_normalized:'MARIA ELENA PRUEBA',price_cents:700,created_at:'2026-10-21T11:00:00Z',receipt_operation_minute:'2026-10-21T06:10:00-05:00'};
const p={payer_normalized:'MARIA ELENA PRUEBA',amount_cents:700,currency:'PEN',paid_at:'2026-10-21T11:10:00Z',received_at:'2026-10-21T11:10:10Z'};
test('normalizes case accents and spaces but never partial or reordered names',()=>{
 assert.equal(normalizePayer(' María  Elena Prueba '),'MARIA ELENA PRUEBA');
 for(const s of ['Maria','12345','Maria 123 Prueba','<Maria Prueba>','a'.repeat(200)])assert.equal(normalizePayer(s),null);
 assert.notEqual(normalizePayer('Elena Maria Prueba'),o.lemon_payer_normalized);
});
test('exact matching requires amount currency full name and order time window',()=>{
 assert.ok(matchesPayment(o,p,now));
 for(const change of [{amount_cents:701},{currency:'USD'},{payer_normalized:'MARIA PRUEBA'},
  {paid_at:'2026-10-21T10:59:59Z'},{paid_at:'2026-10-21T14:00:00Z'},
  {received_at:'2026-10-21T11:40:00Z'},{paid_at:'invalid'}])assert.equal(matchesPayment(o,{...p,...change},now),false);
});
test('requests payer identity and explains screenshot is not proof',()=>{
 const copy=payerPrompt('order-test');
 assert.match(copy,/nombre completo/);assert.match(copy,/apellidos/);assert.match(copy,/no confirma el pago/);assert.doesNotMatch(copy,/Binance/);
});
test('receipt date and minute distinguish equal amounts and fail closed',()=>{
 assert.ok(matchesPayment(o,{...p,received_at:'2026-10-21T11:10:59Z'},now));
 for(const minute of [null,'invalid','2026-10-21T11:11:00Z','2026-10-20T11:10:00Z'])
  assert.equal(matchesPayment({...o,receipt_operation_minute:minute},p,now),false);
 assert.equal(matchesPayment(o,{...p,received_at:'2026-10-21T11:11:00Z'},now),false);
});
