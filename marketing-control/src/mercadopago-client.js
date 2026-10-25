import {readFileSync} from 'node:fs';
import {createHmac,timingSafeEqual} from 'node:crypto';

export function mpEnabled(){
 try{return readFileSync(process.env.MP_ENABLED_FILE||'/run/secrets/mercadopago-enabled','utf8').trim()==='true';}catch{return false;}
}
export function mpConfig(){
 const read=name=>readFileSync('/run/secrets/mercadopago-'+name,'utf8').trim();
 return {token:read('access-token'),secret:read('webhook'),collector:'1804582803',
  webhook:'https://marketingjhelizxyz.online/webhooks/mercadopago/'};
}
export function validSignature(signature,requestId,dataId,secret){
 if(typeof signature!=='string'||typeof requestId!=='string'||!/^\d{1,30}$/.test(dataId)||!secret||!requestId||requestId.length>200)return false;
 const parts=signature.split(',').map(p=>p.trim().split('='));
 if(parts.length!==2||new Set(parts.map(p=>p[0])).size!==2)return false;
 const {ts,v1}=Object.fromEntries(parts);
 if(!/^\d{10,16}$/.test(ts)||!/^([a-fA-F0-9]{64})$/.test(v1))return false;
 const expected=createHmac('sha256',secret).update(`id:${dataId};request-id:${requestId};ts:${ts};`).digest();
 return timingSafeEqual(expected,Buffer.from(v1,'hex'));
}
export function cents(value){
 const s=String(value);
 if(!/^\d+(?:\.\d{1,2})?$/.test(s))return null;
 const [whole,decimal='']=s.split('.');const result=Number(whole)*100+Number(decimal.padEnd(2,'0'));
 return Number.isSafeInteger(result)?result:null;
}
export function validPayment(p,o,config){
 return /^\d{1,30}$/.test(String(p.id))&&p.live_mode===true&&String(p.collector_id)===config.collector&&
  p.external_reference===`wa:${o.id}`&&p.currency_id==='PEN'&&cents(p.transaction_amount)===o.price_cents&&
  p.status==='approved'&&cents(p.transaction_amount_refunded??0)===0&&
  Number.isFinite(Date.parse(p.date_approved))&&Date.parse(p.date_approved)>=new Date(o.created_at).getTime()-60000;
}
export async function mpRequest(path,{method='GET',body,config=mpConfig(),fetchImpl=fetch}={}){
 const response=await fetchImpl('https://api.mercadopago.com'+path,{method,redirect:'error',
  headers:{Authorization:`Bearer ${config.token}`,'Content-Type':'application/json'},
  body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
 if(!response.ok)throw Object.assign(new Error('Mercado Pago unavailable'),{status:response.status});
 return response.json();
}
export function preferenceData(o,config){
 return {items:[{id:o.product_id,title:o.product_name,quantity:1,unit_price:o.price_cents/100,currency_id:'PEN'}],
  external_reference:`wa:${o.id}`,metadata:{whatsapp_order_id:o.id},notification_url:config.webhook,
  expires:true,expiration_date_to:new Date(Date.now()+2*3600000).toISOString()};
}
export function checkoutUrl(value){
 try{const u=new URL(value);return u.protocol==='https:'&&['www.mercadopago.com.pe','www.mercadopago.com'].includes(u.hostname)&&!u.username&&!u.password&&!u.port;}catch{return false;}
}
