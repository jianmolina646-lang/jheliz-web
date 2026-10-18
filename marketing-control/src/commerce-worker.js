import {readFileSync} from 'node:fs';
import {createRenewal} from './renewals.js';
import {createSign,randomBytes} from 'node:crypto';
import {downloadMediaMessage} from 'baileys';
import {rows,db,event} from './db.js';
import {createOrder,decrypt,encrypt,money,transaction} from './commerce.js';
import {syncWorkbook} from './reports.js';
import {catalogText,paymentText,receiptText,deliveryText,expiryReminderText} from './bot-copy.js';
import {isCodesInstance} from './instance-purpose.js';

export async function commerceMessage(socket,instance,message){
 const jid=message.key.remoteJid;
 const image=message.message?.imageMessage;
 const text=(message.message?.conversation||message.message?.extendedTextMessage?.text||image?.caption||'').trim();
 const [cmd,arg]=text.toLowerCase().split(/\s+/);
 if(image){
  const [o]=await rows("SELECT id FROM orders WHERE instance_id=$1 AND jid=$2 AND status='PENDING'",[instance,jid]);if(!o)return false;
  const size=Number(image.fileLength?.toString()||0);if(!size||size>5000000){await socket.sendMessage(jid,{text:'Envía el comprobante como imagen de menos de 5 MB.'});return true;}
  const data=await downloadMediaMessage(message,'buffer',{}, {reuploadRequest:socket.updateMediaMessage});
  const jpeg=data[0]===255&&data[1]===216&&data[2]===255,png=data.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]));
  if(data.length>5000000||(!jpeg&&!png)){await socket.sendMessage(jid,{text:'El comprobante debe ser una imagen JPG o PNG de menos de 5 MB.'});return true;}
  await db.query("UPDATE orders SET receipt=$1,receipt_mime=$2 WHERE id=$3 AND status='PENDING'",[encrypt(data.toString('base64')),jpeg?'image/jpeg':'image/png',o.id]);
  await socket.sendMessage(jid,{text:receiptText(o.id)});return true;
 }
 if(!['/catalogo','/comprar','/renovar','/pedidos','/mis_cuentas','/vencimiento','/cancelar'].includes(cmd))return false;
 try{
  if(cmd==='/renovar'){
   const identities=[jid];
   const alt=message.key.remoteJidAlt;
   if(alt&&/@(s\.whatsapp\.net|lid)$/.test(alt))identities.push(alt);
   if(jid.endsWith('@lid')){const pn=await socket.signalRepository?.lidMapping?.getPNForLID(jid);if(pn?.endsWith('@s.whatsapp.net'))identities.push(pn);}
   const o=await createRenewal(instance,jid,text,identities);
   await socket.sendMessage(jid,{image:readFileSync(new URL('../public/ligo-qr.jpg',import.meta.url)),caption:`🔄 *JHELIZ · Renovación*\n\n${o.product_name}\nCuenta: ${text.trim().split(/\s+/)[2]}\nDuración: ${o.days} días\nTotal: S/ ${money(o.price_cents)}\n\nPaga con el QR de Ligo y envía el comprobante aquí. Verifica el destinatario: Jhedy Javier Villa Lima.\n\nLa renovación requiere verificación del pago y confirmación del servicio por el administrador. Conservas tu misma cuenta.\nPedido: ${o.id}\n/pedidos · Consultar estado\n/cancelar · Cancelar antes de pagar`});
  }
  if(cmd==='/catalogo'){
   const p=await rows("SELECT p.*,count(s.id) FILTER(WHERE s.state='AVAILABLE' AND (s.expires_on IS NULL OR s.expires_on >= (now() AT TIME ZONE 'America/Lima')::date+p.days))::integer AS available FROM products p LEFT JOIN stock s ON s.product_id=p.id WHERE p.active=true GROUP BY p.id ORDER BY p.name LIMIT 40");
   await socket.sendMessage(jid,{text:catalogText(p)});
  }
  if(cmd==='/comprar'){
   const o=await createOrder(instance,jid,message.pushName||'Cliente',arg||'');
   await socket.sendMessage(jid,{image:readFileSync(new URL('../public/ligo-qr.jpg',import.meta.url)),caption:paymentText(o)});
  }
  if(cmd==='/pedidos'||cmd==='/mis_cuentas'){
   const all=await rows('SELECT id,product_name,status,expires_at FROM orders WHERE instance_id=$1 AND jid=$2 ORDER BY created_at DESC LIMIT 5',[instance,jid]);
   const labels={PENDING:'Pendiente de revisión',APPROVED:'Pago aprobado; entrega pendiente',SENDING:'Entregando',DELIVERED:'Entregado',REVIEW:'Revisión de entrega',REJECTED:'Rechazado o cancelado'};
   await socket.sendMessage(jid,{text:'📦 *JHELIZ · Mis compras*\n\n'+(all.length?all.map(o=>`🎬 *${o.product_name}*\nEstado: ${labels[o.status]}${o.expires_at?'\n⏳ Vence: '+new Date(o.expires_at).toLocaleDateString('es-PE',{timeZone:'America/Lima'}):''}\nPedido: ${o.id}`).join('\n\n────────────\n\n'):'Todavía no tienes pedidos registrados.')+'\n\n🛠️ Reportar un problema: /soporte\n🎬 Ver plataformas: /catalogo'});
  }
  if(cmd==='/vencimiento'){
   const all=await rows("SELECT id,product_name,expires_at FROM orders WHERE instance_id=$1 AND jid=$2 AND status='DELIVERED' AND expires_at IS NOT NULL ORDER BY expires_at ASC LIMIT 10",[instance,jid]);
   const lines=all.length?all.map(o=>`${o.product_name} - vence: ${new Date(o.expires_at).toLocaleDateString('es-PE',{timeZone:'America/Lima'})}\nPedido: ${o.id}`).join('\n\n---\n\n'):'No encontramos cuentas entregadas con fecha de vencimiento.';
   await socket.sendMessage(jid,{text:'JHELIZ - Mis vencimientos\n\n'+lines+'\n\nRecibiras un recordatorio automatico el dia del vencimiento.\nAyuda: /soporte'});
  }
  if(cmd==='/cancelar'){
   const r=await db.query("UPDATE orders SET status='REJECTED',sheets_synced_at=null WHERE instance_id=$1 AND jid=$2 AND status='PENDING' AND receipt IS NULL RETURNING id",[instance,jid]);
   await socket.sendMessage(jid,{text:r.rowCount?'Pedido cancelado. Escribe /catalogo para volver a elegir.':'No hay un pedido cancelable. Si ya pagaste o enviaste el comprobante, contacta al administrador.'});
  }
 }catch(e){await socket.sendMessage(jid,{text:e.publicMessage||'No pudimos completar la solicitud. Contacta al administrador.'});}
 return true;
}

export async function deliverOrders(running){
 await db.query("UPDATE orders SET status='REVIEW',sheets_synced_at=null WHERE status='SENDING' AND delivery_started_at<now()-interval '5 minutes'");
 for(const [instance,state] of running){
  if(!state.connected||state.closed)continue;
  const [sender]=await rows('SELECT * FROM instances WHERE id=$1',[instance]);
  if(!sender||isCodesInstance(sender))continue;
  const o=await transaction(async c=>{
   const [order]=(await c.query("SELECT * FROM orders WHERE instance_id=$1 AND status='APPROVED' ORDER BY approved_at FOR UPDATE SKIP LOCKED LIMIT 1",[instance])).rows;if(!order)return;
   if(order.renewal_of){
    const [account]=(await c.query('SELECT s.secret FROM orders p JOIN stock s ON s.id=p.stock_id WHERE p.id=$1',[order.renewal_of])).rows;
    if(!account){await c.query("UPDATE orders SET status='REVIEW' WHERE id=$1",[order.id]);return;}
    const [updated]=(await c.query("UPDATE orders SET status='SENDING',delivery_id=$1,delivery_started_at=now(),sheets_synced_at=null WHERE id=$2 RETURNING *",[randomBytes(16).toString('hex').toUpperCase(),order.id])).rows;
    return {...updated,secret:account.secret};
   }
   const [s]=(await c.query("SELECT secret,(expires_on IS NOT NULL AND ((expires_on+1)::timestamp AT TIME ZONE 'America/Lima') < COALESCE($3::timestamptz,now()+$2::integer*interval '1 day')) OR ($3::timestamptz IS NOT NULL AND $3::timestamptz<=now()) AS expired FROM stock WHERE id=$1 AND state='SOLD'",[order.stock_id,order.days,order.expires_at])).rows;
   if(!s||s.expired){await c.query("UPDATE orders SET status='REVIEW',sheets_synced_at=null WHERE id=$1",[order.id]);return;}
   const deliveryId=randomBytes(16).toString('hex').toUpperCase();
   const [updated]=(await c.query("UPDATE orders SET status='SENDING',delivery_id=$1,delivery_started_at=now(),started_at=COALESCE(started_at,now()),expires_at=COALESCE(expires_at,now()+days*interval '1 day'),sheets_synced_at=null WHERE id=$2 RETURNING *",[deliveryId,order.id])).rows;
   return {...updated,secret:s.secret};
  });
  if(!o)continue;
  try{
   const account=JSON.parse(decrypt(o.secret));
   const copy=o.renewal_of?`✅ *JHELIZ · Renovación confirmada*\n\nPlataforma: ${o.product_name}\nCorreo: ${account.email}\nInicio del período: ${new Date(o.started_at).toLocaleString('es-PE',{timeZone:'America/Lima'})}\nNuevo vencimiento: ${new Date(o.expires_at).toLocaleString('es-PE',{timeZone:'America/Lima'})}\nHora de Perú\n\nConserva tus accesos actuales.\nPedido: ${o.id}\n/soporte · Ayuda`:deliveryText(o,account);
   await state.socket.sendMessage(o.jid,{text:copy},{messageId:o.delivery_id});
   await db.query("UPDATE orders SET status='DELIVERED',delivered_at=now(),sheets_synced_at=null WHERE id=$1",[o.id]);
   await db.query("INSERT INTO audit(action,details) VALUES('delivery.sent',$1)",[{order:o.id}]);
   await event(instance,'INFO','Pedido entregado: '+o.id);
  }catch{
   // An ambiguous transport result must not trigger automatic duplicate delivery.
   await db.query("UPDATE orders SET status='REVIEW',sheets_synced_at=null WHERE id=$1",[o.id]);
   await db.query("INSERT INTO audit(action,details) VALUES('delivery.review',$1)",[{order:o.id,reason:'Resultado del envío ambiguo; verificar el chat antes de reintentar.'}]);
   await event(instance,'ERROR','Revisar entrega del pedido '+o.id+' antes de volver a enviar.');
  }
 }
}

// The reminder is sent once on the calendar day of expiry in Peru. A failed or
// ambiguous transport result is left for manual review rather than duplicated.
export async function deliverExpiryReminders(running){
 await db.query("UPDATE expiry_notifications SET status='REVIEW' WHERE status='SENDING' AND started_at<now()-interval '5 minutes'");
 for(const [instance,state] of running){
  if(!state.connected||state.closed)continue;
  const reminder=await transaction(async c=>{
   const [sender]=(await c.query('SELECT * FROM instances WHERE id=$1',[instance])).rows;
   if(!sender||isCodesInstance(sender))return;
   const [order]=(await c.query(`SELECT o.* FROM orders o
    LEFT JOIN expiry_notifications n ON n.order_id=o.id
    WHERE o.instance_id=$1 AND o.status='DELIVERED' AND o.expires_at IS NOT NULL AND o.renewal_of IS NULL
      AND (o.expires_at AT TIME ZONE 'America/Lima')::date=(now() AT TIME ZONE 'America/Lima')::date
      AND n.order_id IS NULL
    ORDER BY o.expires_at,o.created_at FOR UPDATE OF o SKIP LOCKED LIMIT 1`,[instance])).rows;
   if(!order)return;
   const messageId=randomBytes(16).toString('hex').toUpperCase();
   const inserted=await c.query("INSERT INTO expiry_notifications(order_id,status,message_id,started_at) VALUES($1,'SENDING',$2,now()) ON CONFLICT(order_id) DO NOTHING RETURNING order_id",[order.id,messageId]);
   if(!inserted.rowCount)return;
   return {...order,message_id:messageId};
  });
  if(!reminder)continue;
  try{
   await state.socket.sendMessage(reminder.jid,{text:expiryReminderText(reminder)},{messageId:reminder.message_id});
   await db.query("UPDATE expiry_notifications SET status='SENT',sent_at=now() WHERE order_id=$1 AND status='SENDING'",[reminder.id]);
   await event(instance,'INFO','Recordatorio de vencimiento enviado: '+reminder.id);
  }catch{
   await db.query("UPDATE expiry_notifications SET status='REVIEW' WHERE order_id=$1 AND status='SENDING'",[reminder.id]);
   await event(instance,'ERROR','Revisar recordatorio de vencimiento '+reminder.id+' antes de volver a enviar.');
  }
 }
}

let accessToken='',tokenUntil=0,lastSync=0;
const b64=v=>Buffer.from(JSON.stringify(v)).toString('base64url');
async function token(){if(Date.now()<tokenUntil)return accessToken;const s=JSON.parse(readFileSync(process.env.SHEETS_KEY_FILE||'/run/secrets/sheets.json','utf8')),now=Math.floor(Date.now()/1000);const data=b64({alg:'RS256',typ:'JWT'})+'.'+b64({iss:s.client_email,scope:'https://www.googleapis.com/auth/spreadsheets',aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+600});const signature=createSign('RSA-SHA256').update(data).sign(s.private_key,'base64url');const r=await fetch('https://oauth2.googleapis.com/token',{method:'POST',body:new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion:data+'.'+signature}),signal:AbortSignal.timeout(15000)});if(!r.ok)throw new Error('auth');const result=await r.json();accessToken=result.access_token;tokenUntil=Date.now()+480000;return accessToken;}
export async function sheets(path,method='GET',body){const r=await fetch('https://sheets.googleapis.com/v4/spreadsheets/'+process.env.SHEETS_ID+path,{method,headers:{Authorization:'Bearer '+await token(),'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(20000)});if(!r.ok)throw Object.assign(new Error('Google Sheets HTTP '+r.status),{code:'SHEETS_'+r.status});return r.json();}
export async function syncSheets(){
 if(!process.env.SHEETS_ID||Date.now()-lastSync<60000)return;lastSync=Date.now();
 try{
  await syncWorkbook(sheets);
 }catch{await db.query("UPDATE commerce_sync SET last_error='No se pudo actualizar Google Sheets. Reintento automático en un minuto.' WHERE id=1");}
}
