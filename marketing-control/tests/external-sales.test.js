import test from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {externalSaleSchema,registerExternalSale} from '../src/external-sales.js';
import {db} from '../src/db.js';
import {deliverOrders} from '../src/commerce-worker.js';
const payload=()=>({request_id:randomUUID(),instance_id:randomUUID(),product_id:randomUUID(),customer:'Cliente prueba',phone:'51999999999',stock_id:null,email:'external@example.test',password:'not-real',started_at:new Date(Date.now()-5*86400000).toISOString(),expires_at:new Date(Date.now()+25*86400000).toISOString(),price_cents:3500,reference:'',confirmed:true});
test('external sales require past start, future expiry and explicit confirmation',()=>{
 const p=payload();assert.ok(externalSaleSchema.safeParse(p).success);
 for(const patch of [{confirmed:false},{phone:'123@g.us'},{expires_at:p.started_at},{started_at:new Date(Date.now()+86400000).toISOString()},{password:undefined}])assert.ok(!externalSaleSchema.safeParse({...p,...patch}).success);
});
test('isolated external sales: dates, idempotency, stock and delivery',{skip:!process.env.RUN_EXTERNAL_TEST},async()=>{
 assert.equal(new URL(process.env.DATABASE_URL).pathname,'/marketing_commerce_test');
 try{
  await db.query('TRUNCATE orders,stock,products CASCADE');
  const [i]=(await db.query("UPDATE instances SET status='CONNECTED' RETURNING id")).rows;
  const [u]=(await db.query("SELECT id FROM users WHERE role='ADMIN' LIMIT 1")).rows;
  const [p]=(await db.query("INSERT INTO products(code,name,price_cents,days) VALUES('external','External test',3500,30) RETURNING id")).rows;
  const v={...payload(),instance_id:i.id,product_id:p.id};
  const results=await Promise.all([registerExternalSale(v,u.id),registerExternalSale(v,u.id)]);assert.equal(results[0].id,results[1].id);
  await assert.rejects(registerExternalSale({...v,request_id:randomUUID()},u.id));
  const [o]=(await db.query('SELECT * FROM orders WHERE id=$1',[results[0].id])).rows;
  await assert.rejects(registerExternalSale({...v,request_id:randomUUID(),stock_id:o.stock_id},u.id));
  let sent=0;const running=new Map([[i.id,{connected:true,closed:false,socket:{sendMessage:async(jid,message)=>{sent++;assert.equal(jid,v.phone+'@s.whatsapp.net');assert.ok(message.text.includes(v.email));assert.ok(message.text.includes(v.password));}}}]]);
  await deliverOrders(running);await deliverOrders(running);assert.equal(sent,1);
  const [after]=(await db.query('SELECT * FROM orders WHERE id=$1',[o.id])).rows;
  assert.equal(after.source,'EXTERNAL');assert.equal(after.status,'DELIVERED');assert.equal(after.started_at.toISOString(),v.started_at);assert.equal(after.expires_at.toISOString(),v.expires_at);assert.equal(after.approved_at.toISOString(),v.started_at);
  assert.equal((await db.query('SELECT count(*)::int AS n FROM orders')).rows[0].n,1);
 }finally{await db.end();}
});
