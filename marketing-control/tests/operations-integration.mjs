import pg from 'pg';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import Fastify from 'fastify';
const schema='operations_test_'+randomUUID().replaceAll('-','');
const admin=new pg.Pool({connectionString:process.env.DATABASE_URL});
const url=new URL(process.env.DATABASE_URL);url.searchParams.set('options','-c search_path='+schema);process.env.DATABASE_URL=url.toString();
let db,app;
try{
 await admin.query(`CREATE SCHEMA ${schema}`);
 ({db}=await import('../src/db.js'));
 const {commerceSchema}=await import('../src/commerce-schema.js');
 const {supportSchema}=await import('../src/support-schema.js');
 const {externalSalesSchema,registerExternalSale}=await import('../src/external-sales.js');
 const {renewalSchema}=await import('../src/renewals.js');
 const {operationsSchema,retryDelivery,registerOperations}=await import('../src/operations.js');
 const {encrypt,accountFingerprint,createOrder}=await import('../src/commerce.js');
 const {deliverOrders}=await import('../src/commerce-worker.js');
 await db.query(`CREATE TABLE users(id uuid PRIMARY KEY,email text);
 CREATE TABLE instances(id uuid PRIMARY KEY,name text,status text DEFAULT 'CONNECTED',desired boolean DEFAULT true,phone text);
 CREATE TABLE schema_migrations(version integer PRIMARY KEY);
 CREATE TABLE audit(id bigserial,actor uuid,action text,details jsonb,created_at timestamptz DEFAULT now());
 CREATE TABLE events(instance_id uuid,level text,message text)`);
 for(const sql of [commerceSchema,externalSalesSchema,renewalSchema,supportSchema,operationsSchema])await db.query(sql);
 const actor=randomUUID(),sales=randomUUID(),codes=randomUUID();
 await db.query("INSERT INTO users VALUES($1,'test@example.test');",[actor]);
 await db.query("INSERT INTO instances(id,name,purpose) VALUES($1,'Ventas','SALES'),($2,'Codigos Jheliz','CODES')",[sales,codes]);
 const p=(await db.query("INSERT INTO products(code,name,price_cents,days) VALUES('netflix','Netflix',3500,30) RETURNING *")).rows[0];
 const stock=(await db.query("INSERT INTO stock(product_id,secret,fingerprint,state) VALUES($1,$2,$3,'SOLD') RETURNING *",[p.id,encrypt(JSON.stringify({email:'owned@example.test',password:'never-export-this'})),accountFingerprint(p.id,'owned@example.test')])).rows[0];
 const order=(await db.query(`INSERT INTO orders(instance_id,jid,customer,product_id,product_name,price_cents,days,status,stock_id,started_at,expires_at,delivery_id)
 VALUES($1,'51900000000@s.whatsapp.net','Test',$2,'Netflix',3500,30,'REVIEW',$3,now()-interval '5 days',now()+interval '25 days','previous-id') RETURNING *`,[sales,p.id,stock.id])).rows[0];
 await assert.rejects(createOrder(codes,'test@s.whatsapp.net','Test','netflix'),e=>e.statusCode===409);
 await assert.rejects(registerExternalSale({request_id:randomUUID(),instance_id:codes,customer:'Test',phone:'51900000000',product_id:p.id,stock_id:stock.id,started_at:new Date(Date.now()-86400000).toISOString(),expires_at:new Date(Date.now()+86400000).toISOString(),price_cents:3500,reference:'',confirmed:true},actor),e=>e.statusCode===409);
 await assert.rejects(retryDelivery(order.id,actor,{verified_not_received:false,reason:'Chat revisado'}));
 const input={verified_not_received:true,reason:'Verificado en el chat de prueba'};
 const results=await Promise.allSettled([retryDelivery(order.id,actor,input),retryDelivery(order.id,actor,input)]);
 assert.equal(results.filter(x=>x.status==='fulfilled').length,1);
 const queued=(await db.query('SELECT * FROM orders WHERE id=$1',[order.id])).rows[0];
 assert.equal(queued.retry_count,1);assert.equal(+queued.started_at,+order.started_at);assert.equal(+queued.expires_at,+order.expires_at);
 let sent=0;
 const running=new Map([[sales,{connected:true,socket:{sendMessage:async()=>{sent++;}}}],[codes,{connected:true,socket:{sendMessage:async()=>{throw Error('Codes must not send sales');}}}]]);
 await deliverOrders(running);await deliverOrders(running);assert.equal(sent,1);
 await assert.rejects(retryDelivery(order.id,actor,input));
 const delivered=(await db.query('SELECT * FROM orders WHERE id=$1',[order.id])).rows[0];
 assert.equal(+delivered.started_at,+order.started_at);assert.equal(+delivered.expires_at,+order.expires_at);
 // A legacy wrongly routed job must remain unsent, not silently rerouted.
 await db.query("UPDATE orders SET instance_id=$1,status='APPROVED' WHERE id=$2",[codes,order.id]);
 await deliverOrders(running);assert.equal(sent,1);
 await db.query("UPDATE orders SET instance_id=$1,status='DELIVERED' WHERE id=$2",[sales,order.id]);
 app=Fastify();let role='ADMIN';app.addHook('onRequest',async req=>{req.user={id:actor,role};});registerOperations(app);
 for(const path of ['/overview','/customers','/customer?instance='+sales+'&jid=51900000000%40s.whatsapp.net','/renewals','/deliveries','/history']){
  const res=await app.inject('/api/operations'+path);assert.equal(res.statusCode,200,path+' '+res.body);assert.ok(!res.body.includes('never-export-this'));assert.ok(!res.body.includes('"secret"'));
  role='SUPPORT';assert.equal((await app.inject('/api/operations'+path)).statusCode,403);role='ADMIN';
 }
 const metrics=(await app.inject('/api/operations/overview')).json();assert.equal(metrics.customers,1);assert.equal(metrics.available,0);
 assert.equal((await app.inject('/api/operations/customers?q=does-not-exist')).json().length,0);
 const history=(await app.inject('/api/operations/history')).json();assert.ok(history.some(e=>e.action==='delivery.retry_requested'));assert.ok(history.some(e=>e.action==='delivery.sent'));
 console.log('PASS isolated operations: sales/codes separation, external-sale guard, explicit retry confirmation, concurrent retry, preserved dates, one simulated send, legacy codes job blocked, authenticated role checks, six views, private data excluded, metrics and audit.');
}finally{
 if(app)await app.close();if(db)await db.end();
 if(!/^operations_test_[a-f0-9]{32}$/.test(schema))throw Error('Unsafe test schema');
 await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();
}
