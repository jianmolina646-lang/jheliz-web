import test from 'node:test';
import assert from 'node:assert/strict';
import {paymentChoiceText,selectedPaymentText} from '../src/payment-choice.js';
const order={id:'test',product_name:'Disney',days:30,price_cents:700};
test('selection contains no payment credentials or website',()=>{
 const text=paymentChoiceText(order);
 assert.match(text,/QR/);assert.match(text,/BINANCE/);
 assert.doesNotMatch(text,/739582457|Jheliz2004|https?:|USDT\*/);
});
test('each method displays only its own payment details',()=>{
 const qr=selectedPaymentText(order,'QR'),binance=selectedPaymentText(order,'BINANCE');
 assert.match(qr,/S\/ 7.00/);assert.match(qr,/Lemon/);assert.doesNotMatch(qr,/Binance|739582457|USDT/i);
 assert.match(binance,/1.84 USDT/);assert.match(binance,/739582457/);assert.doesNotMatch(binance,/Lemon|QR|Jhedy/);
 assert.match(paymentChoiceText({...order,renewal_of:'parent'}),/1 mes calendario/);
});
