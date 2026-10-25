import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import {cents,validPayment,validSignature,preferenceData,checkoutUrl,mpRequest} from '../src/mercadopago-client.js';
const config={secret:'synthetic-secret',collector:'123',token:'synthetic',webhook:'https://example.invalid/webhook'};
const order={id:'11111111-1111-4111-8111-111111111111',price_cents:1000,product_name:'Test',created_at:'2026-10-20T00:00:00Z'};
const payment={id:1234,external_reference:'wa:'+order.id,collector_id:123,live_mode:true,currency_id:'PEN',transaction_amount:10,status:'approved',date_approved:'2026-10-20T00:05:00Z'};
test('MP amount conversion is exact and rejects malformed values',()=>{
 for(const [v,n] of [[10,1000],['10.01',1001],[0,0],['0.1',10]])assert.equal(cents(v),n);
 for(const v of [-1,NaN,Infinity,'10.001','1e3',null,undefined,''])assert.equal(cents(v),null);
});
test('MP approval requires exact order, amount, seller, currency, live approved payment',()=>{
 assert.equal(validPayment(payment,order,config),true);
 for(const patch of [{id:'bad'},{collector_id:456},{external_reference:'another'},{currency_id:'USD'},{transaction_amount:9.99},{transaction_amount_refunded:1},{live_mode:false},{status:'pending'},{status:'rejected'},{status:'refunded'},{date_approved:null},{date_approved:'2020-01-01'}])assert.equal(validPayment({...payment,...patch},order,config),false,JSON.stringify(patch));
});
test('MP signatures bind payment ID, request ID and timestamp',()=>{
 const ts='1792800000000',rid='request-1',id='1234';
 const h=createHmac('sha256',config.secret).update(`id:${id};request-id:${rid};ts:${ts};`).digest('hex');
 assert.equal(validSignature(`ts=${ts},v1=${h}`,rid,id,config.secret),true);
 for(const args of [[`ts=${ts},v1=${h}`,rid,'1235',config.secret],[`ts=${ts},v1=${h}`,'other',id,config.secret],[`ts=${ts},v1=${h}`,rid,id,'wrong'],['',rid,id,config.secret],[`ts=${ts},v1=${h},ts=${ts}`,rid,id,config.secret]])assert.equal(validSignature(...args),false);
});
test('MP preference uses server order price and safe hosted checkout',()=>{
 const p=preferenceData(order,config);assert.equal(p.items[0].unit_price,10);assert.equal(p.external_reference,'wa:'+order.id);assert.equal(p.notification_url,config.webhook);
 assert.equal(checkoutUrl('https://www.mercadopago.com.pe/checkout/v1/redirect?pref_id=test'),true);
 for(const u of ['https://evil.com','https://www.mercadopago.com.pe.evil.com','http://www.mercadopago.com.pe','https://user@www.mercadopago.com.pe'])assert.equal(checkoutUrl(u),false);
});
test('MP HTTP client does not expose provider response or credentials on error',async()=>{
 await assert.rejects(mpRequest('/test',{config,fetchImpl:async()=>({ok:false,status:401})}),e=>e.message==='Mercado Pago unavailable'&&!e.message.includes(config.token));
});
