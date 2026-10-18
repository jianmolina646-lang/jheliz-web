import test from 'node:test';
import assert from 'node:assert/strict';
import {isCodesInstance,requireSalesInstance,duplicateMessage} from '../src/instance-purpose.js';
test('codes routing survives accents and persisted purpose',()=>{
 assert.equal(isCodesInstance({name:'Códigos Jheliz'}),true);
 assert.equal(isCodesInstance({name:'Otro nombre',purpose:'CODES'}),true);
 assert.equal(isCodesInstance({name:'Ventas',purpose:'SALES'}),false);
});
test('sales guard rejects codes and unknown sender',async()=>{
 for(const rows of [[],[{purpose:'CODES',name:'Códigos'}]])await assert.rejects(requireSalesInstance({query:async()=>({rows})},'id'),e=>e.statusCode===409);
 assert.equal((await requireSalesInstance({query:async()=>({rows:[{name:'Ventas'}]})},'id')).name,'Ventas');
});
test('duplicate errors identify email versus payment without leaking values',()=>{
 assert.match(duplicateMessage('stock_fingerprint_key'),/correo/);
 assert.match(duplicateMessage('orders_payment_ref_key'),/referencia/);
 assert.match(duplicateMessage('orders_stock_id_key'),/asignada/);
 assert.ok(!duplicateMessage('private-constraint').includes('private-constraint'));
});
