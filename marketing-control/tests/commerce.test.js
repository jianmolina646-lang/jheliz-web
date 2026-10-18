import test from 'node:test';
import assert from 'node:assert/strict';
import {db} from '../src/db.js';
import {productSchema,encrypt,decrypt,createOrder,approveOrder} from '../src/commerce.js';
import {deliverOrders,commerceMessage} from '../src/commerce-worker.js';
test('product validation rejects negative prices and invalid duration',()=>{
 assert.equal(productSchema.safeParse({code:'netflix',name:'Netflix',price_cents:-20,days:30,active:true}).success,false);
 assert.equal(productSchema.safeParse({code:'netflix',name:'Netflix',price_cents:2000,days:0,active:true}).success,false);
});
test('isolated commerce: encryption, snapshot, stock, repeated and concurrent approval',{skip:!process.env.RUN_COMMERCE_TEST},async()=>{
 assert.ok(new URL(process.env.DATABASE_URL).pathname.endsWith('/marketing_commerce_test'),'Never run writes on production database');
 try{
  await db.query('TRUNCATE orders,stock,products RESTART IDENTITY CASCADE');
  const secret=encrypt('private-test-value');assert.equal(decrypt(secret),'private-test-value');assert.ok(!secret.includes('private-test-value'));
  const [u]=(await db.query("INSERT INTO users(email,password_hash,role) VALUES('commerce@example.test','unused','ADMIN') ON CONFLICT(email) DO UPDATE SET active=true RETURNING id")).rows;
  const [i]=(await db.query('SELECT id FROM instances LIMIT 1')).rows;
  const [p]=(await db.query("INSERT INTO products(code,name,price_cents,days) VALUES('test','Test',2000,30) RETURNING id")).rows;
  for(let n=0;n<2;n++)await db.query('INSERT INTO stock(product_id,secret,fingerprint) VALUES($1,$2,$3)',[p.id,encrypt(JSON.stringify({email:'sample@example.test',password:'sample-not-real'})),'test-'+n]);
  await db.query("UPDATE stock SET expires_on=(now() AT TIME ZONE 'America/Lima')::date+60");
  const a=await createOrder(i.id,'test-a@s.whatsapp.net','Test A','test');
  assert.equal((await createOrder(i.id,'test-a@s.whatsapp.net','Test A','test')).id,a.id);
  await db.query('UPDATE products SET price_cents=2500 WHERE id=$1',[p.id]);
  assert.equal(a.price_cents,2000);
  const b=await createOrder(i.id,'test-b@s.whatsapp.net','Test B','test');assert.equal(b.price_cents,2500);
  const results=await Promise.allSettled([approveOrder(a.id,'TEST-A',u.id),approveOrder(a.id,'TEST-A',u.id)]);
  assert.equal(results.filter(x=>x.status==='fulfilled').length,1);
  await assert.rejects(approveOrder(b.id,'TEST-A',u.id));
  assert.equal((await db.query("SELECT count(*)::int AS n FROM stock WHERE state='SOLD'")).rows[0].n,1);
  await approveOrder(b.id,'TEST-B',u.id);
  assert.equal((await db.query("SELECT count(DISTINCT stock_id)::int AS n FROM orders WHERE status='APPROVED'")).rows[0].n,2);
  await assert.rejects(createOrder(i.id,'test-c@s.whatsapp.net','Test C','test'));
  let calls=0;
  const running=new Map([[i.id,{connected:true,closed:false,socket:{sendMessage:async(jid,payload)=>{calls++;assert.ok(payload.text.includes('sample-not-real'));if(calls===2)throw new Error('simulated ambiguous send');}}}]]);
  await deliverOrders(running);await deliverOrders(running);await deliverOrders(running);
  assert.equal(calls,2);
  assert.equal((await db.query("SELECT count(*)::int AS n FROM orders WHERE status='DELIVERED'")).rows[0].n,1);
  assert.equal((await db.query("SELECT count(*)::int AS n FROM orders WHERE status='REVIEW'")).rows[0].n,1);
  const [delivered]=(await db.query("SELECT started_at,expires_at FROM orders WHERE status='DELIVERED'")).rows;
  assert.equal(new Date(delivered.expires_at)-new Date(delivered.started_at),30*86400000);
  let reply='';await commerceMessage({sendMessage:async(jid,payload)=>{reply=payload.text;}},i.id,{key:{remoteJid:'test-a@s.whatsapp.net'},message:{conversation:'/catalogo'}});assert.ok(reply.includes('S/ 25.00'));assert.ok(!reply.includes('sample-not-real'));
  await commerceMessage({sendMessage:async(jid,payload)=>{reply=payload.text;}},i.id,{key:{remoteJid:'test-a@s.whatsapp.net'},message:{conversation:'/mis_cuentas'}});assert.ok(reply.includes('Mis compras'));
  await commerceMessage({sendMessage:async(jid,payload)=>{reply=payload.text;}},i.id,{key:{remoteJid:'test-a@s.whatsapp.net'},message:{conversation:'/vencimiento'}});assert.ok(reply.includes('Mis vencimientos'));
  await db.query('UPDATE products SET active=false WHERE id=$1',[p.id]);
  await commerceMessage({sendMessage:async(jid,payload)=>{reply=payload.text;}},i.id,{key:{remoteJid:'test-a@s.whatsapp.net'},message:{conversation:'/catalogo'}});assert.ok(!reply.includes('S/ 25.00'));
 }finally{await db.end();}
});
