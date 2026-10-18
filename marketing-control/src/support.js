import {randomBytes} from 'node:crypto';
import {isCodesInstance} from './instance-purpose.js';
import {z} from 'zod';
import {db,rows} from './db.js';
import {transaction,encrypt,decrypt,accountFingerprint} from './commerce.js';

export const categoryNames={PASSWORD:'Contraseña incorrecta',SUBSCRIPTION:'Suscripción caída',OTHER:'Otro problema'};
export const ticketStates={OPEN:'Abierto',IN_PROGRESS:'En atención',QUEUED:'Solución pendiente de envío',SENDING:'Enviando solución',REVIEW:'Revisar envío',RESOLVED:'Resuelto'};
import {supportHelp} from './bot-copy.js';
const id=z.string().uuid(),category=z.enum(['PASSWORD','SUBSCRIPTION','OTHER']);
const fail=(message,statusCode=409)=>{throw Object.assign(new Error(message),{statusCode,publicMessage:message});};
async function audit(c,actor,action,details){await c.query('INSERT INTO audit(actor,action,details) VALUES($1,$2,$3)',[actor,action,details]);}
export async function openTicket(orderId,type,owner=null,actor=null){
 id.parse(orderId);category.parse(type);
 return transaction(async c=>{
  const [o]=(await c.query('SELECT * FROM orders WHERE id=$1 FOR UPDATE',[orderId])).rows;
  if(!o||(owner&&(o.instance_id!==owner.instance||o.jid!==owner.jid)))fail('No se encontró esa compra para este WhatsApp.',404);
  if(o.status!=='DELIVERED'||!o.stock_id||!o.expires_at)fail('Soporte de cuentas está disponible para compras entregadas. Para pagos o entregas pendientes, contacta al administrador.');
  const [existing]=(await c.query("SELECT * FROM support_tickets WHERE order_id=$1 AND status<>'RESOLVED'",[orderId])).rows;if(existing)return existing;
  const [ticket]=(await c.query('INSERT INTO support_tickets(order_id,stock_id,category) VALUES($1,$2,$3) RETURNING *',[orderId,o.stock_id,type])).rows;
  await audit(c,actor,'support.opened',{ticket:ticket.id,order:orderId,category:type});return ticket;
 });
}
export const solutionSchema=z.discriminatedUnion('kind',[
 z.object({kind:z.literal('CORRECT'),email:z.string().email().max(254),password:z.string().min(1).max(256)}).strict(),
 z.object({kind:z.literal('REPLACE'),replacement_id:id.nullable()}).strict(),
 z.object({kind:z.literal('MESSAGE'),message:z.string().trim().min(5).max(1000)}).strict()
]);
export async function resolveTicket(ticketId,input,actor){const data=solutionSchema.parse(input);return transaction(async c=>{
 const [t]=(await c.query('SELECT * FROM support_tickets WHERE id=$1 FOR UPDATE',[id.parse(ticketId)])).rows;if(!t)fail('Caso no encontrado',404);
 if(!['OPEN','IN_PROGRESS'].includes(t.status))fail('Este caso ya tiene una solución preparada. No se asignará otra cuenta.');
 const [o]=(await c.query('SELECT * FROM orders WHERE id=$1 FOR UPDATE',[t.order_id])).rows;
 if(o.stock_id!==t.stock_id||o.status!=='DELIVERED')fail('La compra cambió. Revisa la cuenta y el estado antes de continuar.');
 if(data.kind!=='MESSAGE'&&new Date(o.expires_at)<=new Date())fail('La compra venció. No se permite sustituir ni corregir accesos de una compra vencida.');
 const [old]=(await c.query('SELECT * FROM stock WHERE id=$1 FOR UPDATE',[o.stock_id])).rows;
 let next=old,text;
 if(data.kind==='CORRECT'){
  const account={email:data.email,password:data.password};
  await c.query('UPDATE stock SET secret=$1,fingerprint=$2 WHERE id=$3',[encrypt(JSON.stringify(account)),accountFingerprint(o.product_id,data.email),old.id]);
  next={...old,secret:encrypt(JSON.stringify(account))};
 }
 if(data.kind==='REPLACE'){
  const result=await c.query("SELECT * FROM stock WHERE product_id=$1 AND state='AVAILABLE' AND ($2::uuid IS NULL OR id=$2) AND (expires_on IS NULL OR ((expires_on+1)::timestamp AT TIME ZONE 'America/Lima') >= $3::timestamptz) ORDER BY expires_on NULLS LAST,created_at FOR UPDATE SKIP LOCKED LIMIT 1",[o.product_id,data.replacement_id,o.expires_at]);
  next=result.rows[0];if(!next)fail('No hay una cuenta disponible del mismo producto que cubra el vencimiento original.');
  await c.query("UPDATE stock SET state='DISABLED' WHERE id=$1",[old.id]);
  await c.query("UPDATE stock SET state='SOLD' WHERE id=$1",[next.id]);
  await c.query('UPDATE orders SET stock_id=$1,sheets_synced_at=null WHERE id=$2',[next.id,o.id]);
 }
 if(data.kind==='MESSAGE')text=`💬 *JHELIZ · Respuesta de soporte*\n\n🎬 ${o.product_name}\n\n${data.message}\n\nCaso: ${t.id}\n🛠️ Consultar tus casos: /soporte`;
 else {const account=JSON.parse(decrypt(next.secret));text=`✅ *JHELIZ · Solución de soporte*\n\n🎬 ${o.product_name}\n${data.kind==='REPLACE'?'🔄 Cuenta de reemplazo':'🔑 Accesos corregidos'}\n\n📧 Correo: ${account.email}\n🔑 Contraseña: ${account.password}\n\n⏳ Vencimiento original: ${new Date(o.expires_at).toLocaleString('es-PE',{timeZone:'America/Lima'})}\nEl vencimiento no ha cambiado.\n🔒 Guarda estos datos en privado.\n\nCaso: ${t.id}\n🛠️ ¿Continúa el problema? Escribe /soporte`;}
 await c.query('INSERT INTO support_actions(ticket_id,actor,kind,old_stock_id,new_stock_id,payload,message_id,expires_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8)',[t.id,actor,data.kind,old.id,next.id,encrypt(text),randomBytes(16).toString('hex').toUpperCase(),o.expires_at]);
 await c.query("UPDATE support_tickets SET status='QUEUED',updated_at=now() WHERE id=$1",[t.id]);
 await audit(c,actor,'support.solution_prepared',{ticket:t.id,kind:data.kind,old_stock:old.id,new_stock:next.id});
 return {ok:true};
 });}

export function registerSupport(app){
 const options={preHandler:async(req,reply)=>{if(req.user.role!=='ADMIN')return reply.code(403).send({error:'Solo administradores'});}};
 app.get('/api/support',options,async()=>rows(`SELECT t.*,o.customer,o.jid,o.product_name,o.expires_at,o.stock_id AS current_stock_id,
 a.kind,a.old_stock_id,a.new_stock_id,a.created_at AS solution_at,a.sent_at,u.email AS solved_by
 FROM support_tickets t JOIN orders o ON o.id=t.order_id LEFT JOIN support_actions a ON a.ticket_id=t.id LEFT JOIN users u ON u.id=a.actor ORDER BY t.created_at DESC LIMIT 300`));
 app.post('/api/support',options,async req=>{const d=z.object({order_id:id,category}).strict().parse(req.body);return openTicket(d.order_id,d.category,null,req.user.id);});
 app.get('/api/support/:id/replacements',options,async req=>rows("SELECT s.id,s.expires_on FROM support_tickets t JOIN orders o ON o.id=t.order_id JOIN stock s ON s.product_id=o.product_id WHERE t.id=$1 AND s.state='AVAILABLE' AND (s.expires_on IS NULL OR ((s.expires_on+1)::timestamp AT TIME ZONE 'America/Lima') >= o.expires_at) ORDER BY s.expires_on NULLS LAST,s.created_at LIMIT 500",[id.parse(req.params.id)]));
 app.get('/api/support/:id/account',options,async req=>transaction(async c=>{
  const [t]=(await c.query('SELECT s.secret FROM support_tickets t JOIN orders o ON o.id=t.order_id JOIN stock s ON s.id=o.stock_id WHERE t.id=$1',[id.parse(req.params.id)])).rows;if(!t)fail('Caso no encontrado',404);
  const account=JSON.parse(decrypt(t.secret));await audit(c,req.user.id,'support.account_viewed',{ticket:req.params.id});return {email:account.email};
 }));
 app.post('/api/support/:id/start',options,async req=>transaction(async c=>{const tid=id.parse(req.params.id);const r=await c.query("UPDATE support_tickets SET status='IN_PROGRESS',updated_at=now() WHERE id=$1 AND status='OPEN'",[tid]);if(!r.rowCount)fail('El caso ya está en atención o tiene una solución.');await audit(c,req.user.id,'support.started',{ticket:tid});return {ok:true};}));
 app.post('/api/support/:id/resolve',options,async req=>resolveTicket(req.params.id,req.body,req.user.id));
 app.post('/api/support/:id/review',options,async req=>transaction(async c=>{
  const {action,confirmed}=z.object({action:z.enum(['retry','delivered']),confirmed:z.literal(true)}).strict().parse(req.body),tid=id.parse(req.params.id);
  const [t]=(await c.query('SELECT * FROM support_tickets WHERE id=$1 FOR UPDATE',[tid])).rows;if(t?.status!=='REVIEW')fail('Este caso no está pendiente de revisión.');
  await c.query("UPDATE support_tickets SET status=$1,updated_at=now(),resolved_at=CASE WHEN $1='RESOLVED' THEN now() ELSE null END WHERE id=$2",[action==='retry'?'QUEUED':'RESOLVED',tid]);
  if(action==='delivered')await c.query('UPDATE support_actions SET sent_at=now() WHERE ticket_id=$1',[tid]);
  await audit(c,req.user.id,'support.delivery_'+action,{ticket:tid});return {ok:true};
 }));
}

export async function supportMessage(socket,instance,message){
 const text=(message.message?.conversation||message.message?.extendedTextMessage?.text||'').trim();
 const [command,orderId,kind]=text.toLowerCase().split(/\s+/);if(command!=='/soporte')return false;
 const jid=message.key.remoteJid;
 const owner={instance,jid};
 try{
  if(!orderId){
   const orders=await rows("SELECT id,product_name FROM orders WHERE instance_id=$1 AND jid=$2 AND status='DELIVERED' ORDER BY created_at DESC LIMIT 5",[instance,jid]);
   const tickets=await rows("SELECT t.id,t.status,o.product_name FROM support_tickets t JOIN orders o ON o.id=t.order_id WHERE o.instance_id=$1 AND o.jid=$2 ORDER BY t.created_at DESC LIMIT 5",[instance,jid]);
   await socket.sendMessage(jid,{text:supportHelp(orders,tickets,ticketStates)});return true;
  }
  const categories={clave:'PASSWORD',contrasena:'PASSWORD','contraseña':'PASSWORD',caida:'SUBSCRIPTION','caída':'SUBSCRIPTION',suscripcion:'SUBSCRIPTION',otro:'OTHER'};
  if(!id.safeParse(orderId).success||!categories[kind]){await socket.sendMessage(jid,{text:'Escribe /soporte para ver tus compras y las instrucciones. Ejemplo: /soporte ID_DEL_PEDIDO clave'});return true;}
  const t=await openTicket(orderId,categories[kind],owner);
  await socket.sendMessage(jid,{text:`📩 *JHELIZ · Caso de soporte*\n\nProblema: ${categoryNames[t.category]}\nEstado: *${ticketStates[t.status]}*\n\nNuestro equipo revisará tu compra. No necesitas repetir el reporte.\nCaso: ${t.id}\n\n📋 Consultar estado: /soporte`});
 }catch(e){await socket.sendMessage(jid,{text:e.publicMessage||'No se pudo registrar el caso. Contacta al administrador.'});}
 return true;
}

export async function deliverSupport(running){
 await db.query("UPDATE support_tickets t SET status='REVIEW',updated_at=now() FROM support_actions a WHERE a.ticket_id=t.id AND t.status='SENDING' AND a.sending_at<now()-interval '5 minutes'");
 for(const [instance,state] of running){if(!state.connected||state.closed)continue;
  const [sender]=await rows('SELECT * FROM instances WHERE id=$1',[instance]);
  if(!sender||isCodesInstance(sender))continue;
  const job=await transaction(async c=>{
   const [t]=(await c.query("SELECT t.id,o.jid FROM support_tickets t JOIN orders o ON o.id=t.order_id WHERE t.status='QUEUED' AND o.instance_id=$1 ORDER BY t.updated_at FOR UPDATE OF t SKIP LOCKED LIMIT 1",[instance])).rows;if(!t)return;
   const [a]=(await c.query('UPDATE support_actions SET sending_at=now() WHERE ticket_id=$1 RETURNING payload,message_id,kind,expires_at',[t.id])).rows;
   if(a.kind!=='MESSAGE'&&new Date(a.expires_at)<=new Date()){await c.query("UPDATE support_tickets SET status='REVIEW',updated_at=now() WHERE id=$1",[t.id]);return;}
   await c.query("UPDATE support_tickets SET status='SENDING',updated_at=now() WHERE id=$1",[t.id]);return {...t,...a};
  });if(!job)continue;
  try{
   await state.socket.sendMessage(job.jid,{text:decrypt(job.payload)},{messageId:job.message_id});
   await transaction(async c=>{await c.query('UPDATE support_actions SET sent_at=now() WHERE ticket_id=$1',[job.id]);await c.query("UPDATE support_tickets SET status='RESOLVED',resolved_at=now(),updated_at=now() WHERE id=$1",[job.id]);});
  }catch{await db.query("UPDATE support_tickets SET status='REVIEW',updated_at=now() WHERE id=$1",[job.id]);}
 }
}
