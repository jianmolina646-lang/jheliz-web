import test from 'node:test';
import assert from 'node:assert/strict';
import {catalogText,paymentText,receiptText,deliveryText,expiryReminderText,supportHelp} from '../src/bot-copy.js';

test('delivery shows actual plan duration, dates and exact credentials',()=>{
 const order={id:'sample',product_name:'Netflix',days:30,started_at:'2026-10-01T15:00:00Z',expires_at:'2026-10-31T15:00:00Z'};
 const account={email:'example@example.test',password:'Ab*C_123!'};
 const text=deliveryText(order,account);
 for(const value of ['Fecha de inicio','Fecha de fin','30 días','hora de Perú','1/10/2026','31/10/2026',account.email,account.password])assert.ok(text.includes(value));
 assert.ok(deliveryText({...order,days:7},account).includes('7 días'));
 assert.ok(!deliveryText({...order,days:7},account).includes('30 días'));
 assert.ok(!deliveryText({...order,days:undefined},account).includes('undefined'));
});
test('catalog has price, stock and actionable commands without credentials',()=>{
 const text=catalogText([{name:'Netflix',code:'netflix',price_cents:3500,days:30,available:1,password:'SECRET'},{name:'Prime',code:'prime',price_cents:2000,days:30,available:0}]);
 assert.ok(text.includes('S/ 35.00'));assert.ok(text.includes('/comprar netflix'));assert.ok(!text.includes('/comprar prime'));assert.ok(!text.includes('SECRET'));
});
test('payment receipt is never represented as approved',()=>{
 assert.ok(receiptText('id').includes('Pendiente de verificación'));
 assert.ok(paymentText({id:'id',product_name:'Netflix',days:30,price_cents:3500}).includes('Una captura no confirma el pago'));
});
test('external delivery retains dates and does not assert a new payment',()=>{
 const text=deliveryText({id:'id',product_name:'Netflix',source:'EXTERNAL',started_at:'2026-10-01T15:00:00Z',expires_at:'2026-10-31T15:00:00Z'},{email:'test@example.test',password:'exact-password'});
 assert.ok(text.includes('vigencia original conservada'));assert.ok(text.includes('1/10/2026'));assert.ok(text.includes('31/10/2026'));assert.ok(text.includes('exact-password'));assert.ok(!text.includes('Pago aprobado'));
});
test('support commands contain actual order references and all categories',()=>{
 const text=supportHelp([{id:'order-id',product_name:'Netflix'}],[],{});
 for(const kind of ['clave','caida','otro'])assert.ok(text.includes('/soporte order-id '+kind));
 assert.ok(text.includes('No envíes contraseñas'));
});
test('expiry reminder has an actionable message and never contains credentials',()=>{
 const text=expiryReminderText({id:'order-id',product_name:'Netflix',expires_at:'2026-10-31T15:00:00Z'});
 assert.ok(text.includes('Vence hoy'));assert.ok(text.includes('/soporte'));assert.ok(text.includes('/pedidos'));
 assert.ok(!text.includes('Contrasena'));assert.ok(!text.includes('example.test'));
});
