import makeWASocket,{Browsers,DisconnectReason,useMultiFileAuthState,normalizeMessageContent} from 'baileys';
import QRCode from 'qrcode';
import pino from 'pino';
import {mkdir} from 'node:fs/promises';
import {join} from 'node:path';
import {db,rows,event} from './db.js';
import {commandReply} from './policy.js';
import {isWelcomeGreeting} from './welcome.js';
import {commerceMessage,deliverOrders,deliverExpiryReminders,syncSheets} from './commerce-worker.js';
import {supportMessage,deliverSupport} from './support.js';
import {deliverAdminAlerts} from './admin-alerts.js';
import {codesMessage,isCodesInstance} from './codes-bridge.js';
import {syncCodesSheets} from './codes-sheets.js';
import {sheets} from './commerce-worker.js';

// Commerce credentials are only delivered to the purchaser after manual approval.
const logger=pino({level:'silent'}),running=new Map(),limits=new Map();
let stopping=false,busy=false;
async function update(iid,data){const allowed=['status','qr','phone','last_error'];const pairs=Object.entries(data).filter(([k])=>allowed.includes(k));await db.query(`UPDATE instances SET ${pairs.map(([k],n)=>`${k}=$${n+1}`).join(',')},updated_at=now() WHERE id=$${pairs.length+1}`,[...pairs.map(([,v])=>v),iid]);}
async function close(state){state.closed=true;clearTimeout(state.timer);state.socket?.end(undefined);running.delete(state.id);}
async function connect(instance,state){
 if(state.closed||stopping)return;
 const directory=join(process.env.SESSION_DIR||'/data',instance.id);
 await mkdir(directory,{recursive:true,mode:0o700});
 await update(instance.id,{status:'CONNECTING',qr:null,last_error:null});
 const {state:auth,saveCreds}=await useMultiFileAuthState(directory);
 const socket=makeWASocket({auth,browser:Browsers.ubuntu('Chrome'),logger,printQRInTerminal:false,syncFullHistory:false,markOnlineOnConnect:false});
 state.socket=socket;
 const current=()=>!state.closed&&state.socket===socket;
 socket.ev.on('creds.update',()=>{if(current())saveCreds().catch(()=>event(instance.id,'ERROR','No se pudo guardar la sesión de WhatsApp'));});
 socket.ev.on('connection.update',async change=>{
  if(!current())return;
  try{
   if(change.qr){const qr=await QRCode.toDataURL(change.qr,{width:300,margin:2});if(current())await update(instance.id,{status:'QR_READY',qr});}
   if(change.connection==='open'){state.connected=true;state.attempt=0;await update(instance.id,{status:'CONNECTED',qr:null,phone:socket.user?.id?.split(':')[0]?.split('@')[0]||null,last_error:null});await event(instance.id,'INFO','WhatsApp conectado');}
   if(change.connection==='close'){
    state.connected=false;
    const code=change.lastDisconnect?.error?.output?.statusCode;
    const loggedOut=code===DisconnectReason.loggedOut;
    await update(instance.id,{status:loggedOut?'DISCONNECTED':'ERROR',qr:null,last_error:loggedOut?'Sesión cerrada desde WhatsApp. Crea una nueva conexión para vincular otra vez.':`Conexión interrumpida (${Number(code)||'red'}). Reintentando automáticamente.`});
    await event(instance.id,loggedOut?'WARN':'ERROR',loggedOut?'El teléfono cerró la sesión':`Conexión interrumpida (${Number(code)||'red'}). ${auth.creds.registered?'Reintento programado':'Instancia sin vincular: abre WhatsApp y escanea el QR.'}`);
    if(loggedOut){await db.query('UPDATE instances SET desired=false WHERE id=$1',[instance.id]);return;}
    const delay=code===DisconnectReason.restartRequired?1500:Math.min(120000,10000*2**Math.min(state.attempt++,4));
    state.timer=setTimeout(()=>connect(instance,state).catch(()=>failure(instance,state)),delay);
   }
  }catch{await event(instance.id,'ERROR','No se pudo procesar el estado de conexión').catch(()=>{});}
 });
 socket.ev.on('messages.upsert',async({messages,type})=>{
  if(type!=='notify'||!current())return;
  for(const message of messages){
   const jid=message.key.remoteJid,mid=message.key.id;
   if(!jid||!mid||message.key.fromMe||jid.endsWith('@g.us')||jid==='status@broadcast')continue;
   message.message=normalizeMessageContent(message.message);
   const text=(message.message?.conversation||message.message?.extendedTextMessage?.text||'').trim();
   const greeting=isWelcomeGreeting(text);
   if((!text.startsWith('/')&&!greeting&&!message.message?.imageMessage&&!(isCodesInstance(instance)&&text))||text.length>500)continue;
   const key=instance.id+':'+jid,now=Date.now(),bucket=limits.get(key)||{start:now,count:0};
   if(now-bucket.start>60000){bucket.start=now;bucket.count=0;}if(++bucket.count>8)continue;limits.set(key,bucket);
   try{
    const [active]=await rows('SELECT desired FROM instances WHERE id=$1',[instance.id]);if(!active?.desired||!current())continue;
    const inserted=await db.query('INSERT INTO received_messages(instance_id,message_id) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING message_id',[instance.id,mid]);if(!inserted.rowCount)continue;
    if(await codesMessage(socket,instance,message)){await event(instance.id,'INFO','Solicitud del bot de códigos procesada');continue;}
    if(await supportMessage(socket,instance.id,message))continue;
    if(await commerceMessage(socket,instance.id,message))continue;
    const name=greeting?'menu':text.slice(1).split(/\s/)[0].toLowerCase();if(!/^[a-z][a-z0-9_]{0,29}$/.test(name))continue;
    const [command]=await rows('SELECT * FROM commands WHERE name=$1',[name]);const response=commandReply(command);if(!response)continue;
    await socket.sendMessage(jid,{text:response});
    await event(instance.id,'INFO',`Comando /${name} atendido`);
   }catch{await event(instance.id,'ERROR','No se pudo responder un comando').catch(()=>{});}
  }
 });
}
async function failure(instance,state){if(state.closed)return;await update(instance.id,{status:'ERROR',qr:null,last_error:'No se pudo iniciar la conexión. Reintento en 60 segundos.'}).catch(()=>{});state.timer=setTimeout(()=>connect(instance,state).catch(()=>failure(instance,state)),60000);}
async function tick(){
 if(busy||stopping)return;busy=true;
 try{
  const all=await rows('SELECT * FROM instances');
  for(const instance of all){let state=running.get(instance.id);
   if(state&&(!instance.desired||state.revision!==instance.revision)){await close(state);state=null;}
   if(!instance.desired){if(instance.status!=='DISCONNECTED')await update(instance.id,{status:'DISCONNECTED',qr:null});continue;}
   if(!state){state={id:instance.id,revision:instance.revision,attempt:0,closed:false};running.set(instance.id,state);await event(instance.id,'INFO','Iniciando conexión de WhatsApp');await connect(instance,state).catch(()=>failure(instance,state));}
  }
  await db.query('UPDATE instances SET heartbeat=now()');
  await deliverOrders(running);
  await deliverExpiryReminders(running);
  await deliverSupport(running);
  await deliverAdminAlerts(running);
  for(const [key,value] of limits)if(Date.now()-value.start>60000)limits.delete(key);
 }catch{console.error('WhatsApp worker: database unavailable');}finally{busy=false;}
}
await tick();const timer=setInterval(tick,3000);
let syncing=false;
let codesSyncing=false;
const codesReports=setInterval(async()=>{if(codesSyncing||stopping)return;codesSyncing=true;try{await syncCodesSheets(sheets);}catch{await event(null,'ERROR','No se pudo actualizar Clientes · Códigos en Google Sheets; reintento automático.').catch(()=>{});}finally{codesSyncing=false;}},60000);
const reports=setInterval(async()=>{if(syncing||stopping)return;syncing=true;try{await syncSheets();}catch{}finally{syncing=false;}},15000);
const cleanup=setInterval(()=>db.query("DELETE FROM received_messages WHERE created_at<now()-interval '7 days'; DELETE FROM sessions WHERE expires_at<now(); DELETE FROM events WHERE created_at<now()-interval '30 days'").catch(()=>{}),3600000);
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,async()=>{stopping=true;clearInterval(timer);clearInterval(reports);clearInterval(codesReports);clearInterval(cleanup);for(const state of [...running.values()])await close(state);await db.end();process.exit(0);});
