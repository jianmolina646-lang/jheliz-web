import test from 'node:test';
import assert from 'node:assert/strict';
import {usdtFromPenCents} from '../src/binance-pricing.js';
import {catalogText, paymentText} from '../src/bot-copy.js';

test('converts catalog prices at the fixed rate with two decimals', () => {
 for (const [pen, usdt] of [[3500,'9.21'],[2500,'6.58'],[700,'1.84'],[600,'1.58'],[4300,'11.32'],[190,'0.50'],[19,'0.05']]) {
  assert.equal(usdtFromPenCents(pen), usdt);
 }
});
test('rejects invalid money values', () => {
 for (const price of [NaN,Infinity,-1,0,1.5,'3500',Number.MAX_SAFE_INTEGER+1]) assert.throws(() => usdtFromPenCents(price));
});
test('shows manual Binance payment without changing original price', () => {
 const product = {name:'Netflix',price_cents:3500,days:30,available:1,code:'netflix'};
 const before = JSON.stringify(product);
 const catalog = catalogText([product]);
 assert.match(catalog, /S\/ 35.00/);
 assert.match(catalog, /9.21 USDT/);
 assert.match(catalog, /S\/ 3.80 por USDT/);
 assert.match(catalog, /revisión manual/);
 assert.equal(JSON.stringify(product), before);
 const payment = paymentText({...product, product_name:'Netflix',id:'test'});
 assert.match(payment, /9.21 USDT/);
 assert.match(payment, /QR de Ligo/);
 assert.match(payment, /739582457/);
 assert.match(payment, /Jheliz2004/);
 assert.match(payment, /Una captura no confirma el pago/);
 assert.match(payment, /SOLO de Ligo/);
});
