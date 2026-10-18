import test from 'node:test';
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import argon2 from 'argon2';
import {db} from '../src/db.js';

test('live authentication, CSRF, roles, command CRUD and session revocation',{skip:!process.env.RUN_INTEGRATION},async()=>{
 const prefix='check-'+randomBytes(6).toString('hex'),password=randomBytes(18).toString('hex'),url='http://127.0.0.1:4000',origin=process.env.APP_URL;
 const ids=[];let command;
 async function call(path,method='GET',body,cookie='',csrf='',sentOrigin=origin){return fetch(url+'/api'+path,{method,headers:{Origin:sentOrigin,Cookie:cookie,...(body?{'Content-Type':'application/json'}:{}),'X-CSRF-Token':csrf},...(body?{body:JSON.stringify(body)}:{})});}
 try{
  for(const role of ['ADMIN','SUPPORT']){const r=await db.query('INSERT INTO users(email,password_hash,role) VALUES($1,$2,$3) RETURNING id',[`${prefix}-${role.toLowerCase()}@example.test`,await argon2.hash(password),role]);ids.push(r.rows[0].id);}
  assert.equal((await call('/instances')).status,401);
  assert.equal((await call('/login','POST',{email:`${prefix}-ADMIN@example.test`,password},'','','https://evil.invalid')).status,403);
  const login=await call('/login','POST',{email:`${prefix}-ADMIN@example.test`,password});assert.equal(login.status,200);
  const cookie=login.headers.get('set-cookie').split(';')[0];assert.ok(login.headers.get('set-cookie').includes('HttpOnly'));
  const me=await (await call('/me','GET',null,cookie)).json();assert.equal(me.role,'ADMIN');
  const data={name:prefix.replaceAll('-',''),response:'integration verification',enabled:true,private:false};
  assert.equal((await call('/commands','POST',data,cookie)).status,403);
  const created=await call('/commands','POST',data,cookie,me.csrf);assert.equal(created.status,200);command=(await created.json()).id;
  assert.equal((await call('/commands/'+command,'PUT',{...data,enabled:false},cookie,me.csrf)).status,200);
  const support=await call('/login','POST',{email:`${prefix}-SUPPORT@example.test`,password});const sc=support.headers.get('set-cookie').split(';')[0];const sm=await(await call('/me','GET',null,sc)).json();
  assert.equal((await call('/commands','POST',data,sc,sm.csrf)).status,403);
  assert.equal((await call('/users','GET',null,sc)).status,403);
  for(const path of ['/products','/stock','/orders','/reports','/support']){assert.equal((await call(path,'GET',null,sc)).status,403);assert.equal((await call(path,'GET',null,cookie)).status,200);assert.equal((await call(path)).status,401);}
  const inst=await(await call('/instances','GET',null,sc)).json();assert.ok(inst.every(i=>i.qr===null));
  assert.equal((await call('/commands/'+command,'DELETE',null,cookie,me.csrf)).status,200);command=null;
  assert.equal((await call('/logout','POST',null,cookie,me.csrf)).status,200);assert.equal((await call('/me','GET',null,cookie)).status,401);
 }finally{if(command)await db.query('DELETE FROM commands WHERE id=$1',[command]);await db.query('UPDATE audit SET actor=null WHERE actor=ANY($1::uuid[])',[ids]);await db.query('DELETE FROM users WHERE id=ANY($1::uuid[])',[ids]);await db.end();}
});
