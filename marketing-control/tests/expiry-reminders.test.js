import test from 'node:test';
import assert from 'node:assert/strict';
import {db} from '../src/db.js';
import {encrypt} from '../src/commerce.js';
import {deliverExpiryReminders} from '../src/commerce-worker.js';

test('isolated expiry reminder sends once for a delivered purchase expiring today',{skip:!process.env.RUN_EXPIRY_TEST},async()=>{
 assert.equal(new URL(process.env.DATABASE_URL).pathname,'/marketing_commerce_test');
 try{
  await db.query('TRUNCATE expiry_notifications,orders,stock,products CASCADE');
  const [instance]=(await db.query("UPDATE instances SET status='CONNECTED' RETURNING id")).rows;
  const [product]=(await db.query("INSERT INTO products(code,name,price_cents,days) VALUES('expiry-test','Expiry test',3500,30) RETURNING id")).rows;
  const [stock]=(await db.query("INSERT INTO stock(product_id,secret,fingerprint,state) VALUES($1,$2,$3,'SOLD') RETURNING id",[product.id,encrypt(JSON.stringify({email:'private@example.test',password:'do-not-send'})),'expiry-reminder-test'])).rows;
  const [order]=(await db.query(`INSERT INTO orders(instance_id,jid,customer,product_id,product_name,price_cents,days,status,stock_id,started_at,expires_at,delivered_at)
   VALUES($1,'51999999999@s.whatsapp.net','Cliente prueba',$2,'Expiry test',3500,30,'DELIVERED',$3,now()-interval '30 days',((now() AT TIME ZONE 'America/Lima')::date+time '12:00') AT TIME ZONE 'America/Lima',now()) RETURNING id`,[instance.id,product.id,stock.id])).rows;
  const messages=[];
  const running=new Map([[instance.id,{connected:true,closed:false,socket:{sendMessage:async(jid,payload)=>messages.push({jid,payload})}}]]);
  await deliverExpiryReminders(running);await deliverExpiryReminders(running);
  assert.equal(messages.length,1);assert.equal(messages[0].jid,'51999999999@s.whatsapp.net');
  assert.ok(messages[0].payload.text.includes('Vence hoy'));assert.ok(!messages[0].payload.text.includes('do-not-send'));
  const [notice]=(await db.query('SELECT status FROM expiry_notifications WHERE order_id=$1',[order.id])).rows;
  assert.equal(notice.status,'SENT');
 }finally{await db.end();}
});
