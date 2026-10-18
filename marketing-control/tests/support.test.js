import test from 'node:test';
import assert from 'node:assert/strict';
import {db} from '../src/db.js';
import {encrypt,decrypt} from '../src/commerce.js';
import {openTicket,resolveTicket,deliverSupport,supportMessage} from '../src/support.js';
import {buildSupportReports} from '../src/reports.js';

test('support projections do not export credentials or message content',()=>{
 const tables=buildSupportReports([{id:'t',order_id:'o',customer:'Test',jid:'1@s.whatsapp.net',category:'PASSWORD',status:'OPEN',payload:'SECRET'}],[{id:'a',kind:'CORRECT',payload:'SECRET'}]);
 assert.equal(tables.length,2);assert.ok(!JSON.stringify(tables).includes('SECRET'));
});
test('isolated support: ownership, duplicate cases, replacement, correction, expiry and delivery',{skip:!process.env.RUN_SUPPORT_TEST},async()=>{
 assert.ok(new URL(process.env.DATABASE_URL).pathname.endsWith('/marketing_commerce_test'));
 try{
  await db.query('TRUNCATE orders,stock,products RESTART IDENTITY CASCADE');
  const [user]=(await db.query("INSERT INTO users(email,password_hash,role) VALUES('support-test@example.test','unused','ADMIN') ON CONFLICT(email) DO UPDATE SET active=true RETURNING id")).rows;
  const [instance]=(await db.query('SELECT id FROM instances LIMIT 1')).rows;
  const [p]=(await db.query("INSERT INTO products(code,name,price_cents,days) VALUES('supporttest','Support test',3500,30) RETURNING id")).rows;
  const stock=[];
  for(let n=0;n<3;n++)stock.push((await db.query('INSERT INTO stock(product_id,secret,fingerprint) VALUES($1,$2,$3) RETURNING id',[p.id,encrypt(JSON.stringify({email:`dummy${n}@example.test`,password:'DUMMY-ONLY'})),'support-'+n])).rows[0].id);
  await db.query("UPDATE stock SET state='SOLD' WHERE id=$1",[stock[0]]);
  const [order]=(await db.query("INSERT INTO orders(instance_id,jid,customer,product_id,product_name,price_cents,days,status,stock_id,started_at,expires_at,delivered_at) VALUES($1,'owner@s.whatsapp.net','Test',$2,'Support test',3500,30,'DELIVERED',$3,now()-interval '10 days',now()+interval '20 days',now()-interval '10 days') RETURNING *",[instance.id,p.id,stock[0]])).rows;
  await assert.rejects(openTicket(order.id,'PASSWORD',{instance:instance.id,jid:'intruder@s.whatsapp.net'}));
  const [a,b]=await Promise.all([openTicket(order.id,'PASSWORD',{instance:instance.id,jid:order.jid}),openTicket(order.id,'PASSWORD',{instance:instance.id,jid:order.jid})]);assert.equal(a.id,b.id);
  const result=await Promise.allSettled([resolveTicket(a.id,{kind:'REPLACE',replacement_id:stock[1]},user.id),resolveTicket(a.id,{kind:'REPLACE',replacement_id:stock[2]},user.id)]);assert.equal(result.filter(r=>r.status==='fulfilled').length,1);
  let current=(await db.query('SELECT * FROM orders WHERE id=$1',[order.id])).rows[0];assert.equal(+current.expires_at,+order.expires_at);assert.equal(+current.started_at,+order.started_at);assert.equal(current.price_cents,3500);
  assert.equal((await db.query('SELECT state FROM stock WHERE id=$1',[stock[0]])).rows[0].state,'DISABLED');
  let sends=0,last='';const running=new Map([[instance.id,{connected:true,closed:false,socket:{sendMessage:async(jid,p)=>{assert.equal(jid,order.jid);sends++;last=p.text;}}}]]);
  await deliverSupport(running);await deliverSupport(running);assert.equal(sends,1);assert.ok(last.includes('DUMMY-ONLY'));assert.ok(last.includes('vencimiento no ha cambiado'));
  assert.equal((await db.query('SELECT status FROM support_tickets WHERE id=$1',[a.id])).rows[0].status,'RESOLVED');
  const corrected=await openTicket(order.id,'PASSWORD',null,user.id);await resolveTicket(corrected.id,{kind:'CORRECT',email:'corrected@example.test',password:'UPDATED-DUMMY'},user.id);
  const [s]=(await db.query('SELECT secret FROM stock WHERE id=$1',[current.stock_id])).rows;assert.equal(JSON.parse(decrypt(s.secret)).password,'UPDATED-DUMMY');
  running.get(instance.id).socket.sendMessage=async()=>{sends++;throw new Error('ambiguous');};await deliverSupport(running);await deliverSupport(running);assert.equal(sends,2);assert.equal((await db.query('SELECT status FROM support_tickets WHERE id=$1',[corrected.id])).rows[0].status,'REVIEW');
  await assert.rejects(resolveTicket(corrected.id,{kind:'REPLACE',replacement_id:null},user.id));
  let reply='';await supportMessage({sendMessage:async(jid,p)=>reply=p.text},instance.id,{key:{remoteJid:'intruder@s.whatsapp.net'},message:{conversation:'/soporte '+order.id+' clave'}});assert.ok(!reply.includes('UPDATED-DUMMY'));assert.ok(reply.includes('No se encontró'));
  await db.query("UPDATE support_tickets SET status='RESOLVED' WHERE id=$1",[corrected.id]);await db.query("UPDATE orders SET expires_at=now()-interval '1 day' WHERE id=$1",[order.id]);
  const expired=await openTicket(order.id,'SUBSCRIPTION',null,user.id);await assert.rejects(resolveTicket(expired.id,{kind:'REPLACE',replacement_id:null},user.id),/venció/);
  await resolveTicket(expired.id,{kind:'MESSAGE',message:'La compra ya venció. Contacta al equipo para renovar.'},user.id);
 }finally{await db.end();}
});
