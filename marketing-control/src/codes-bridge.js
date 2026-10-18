import {createHmac,randomUUID} from 'node:crypto';
import {setTimeout as wait} from 'node:timers/promises';
import {isCodesInstance} from './instance-purpose.js';
export {isCodesInstance} from './instance-purpose.js';

const deliveryCommands=new Set(['/codigo','/viaje','/hogar','/clave','/tv','/enlacetv']);

const commandNames=new Set(['/start','/miscorreos','/codigo','/viaje','/hogar','/clave','/tv','/enlacetv','/cmds','/clientes','/activar','/desactivar','/asignar','/quitar','/anuncio','/limite','/diagnostico','/metricas']);
const phone=jid=>(jid||'').split('@')[0].replace(/\D/g,'');
const key=value=>String(value||'').normalize('NFD').replace(/\p{Diacritic}/gu,'').trim().toLowerCase();

export async function codesMessage(socket,instance,message){
 if(!isCodesInstance(instance))return false;
 const originalJid=message.key.remoteJid;
 let jid=originalJid;
 if(jid?.endsWith('@lid')){
  const alternate=message.key.remoteJidAlt;
  jid=alternate?.endsWith('@s.whatsapp.net')?alternate:await socket.signalRepository?.lidMapping?.getPNForLID(jid);
  if(!jid?.endsWith('@s.whatsapp.net')){await socket.sendMessage(originalJid,{text:'No pude verificar tu número de WhatsApp. Contacta al administrador.'});return true;}
 }
 let text=(message.message?.conversation||message.message?.extendedTextMessage?.text||'').trim();
 if(/^(hola|menu|menú|inicio|start|\/menu)$/i.test(text))text='/start';
 else if(commandNames.has('/'+text.toLowerCase().split(/\s+/,1)[0]))text='/'+text;
 const cmd=text.toLowerCase().split(/\s+/,1)[0];
 if(!jid||message.key.fromMe||!jid.endsWith('@s.whatsapp.net'))return true;
 if(!commandNames.has(cmd)){await socket.sendMessage(originalJid,{text:'Códigos Jheliz · Escribe /start o /cmds para continuar.'});return true;}
 const secret=process.env.CODES_BRIDGE_SECRET||'',url=process.env.CODES_BRIDGE_URL||'';
 if(!secret||!url){await socket.sendMessage(jid,{text:'El bot de códigos está en configuración. Inténtalo nuevamente en unos minutos.'});return true;}
 const body=JSON.stringify({phone:phone(jid),name:message.pushName||'',text,timestamp:Math.floor(Date.now()/1000),request_id:randomUUID()});
 try{
  if(deliveryCommands.has(cmd)){
   await socket.sendMessage(originalJid,{text:'*JHELIZ · CÓDIGOS*\n━━━━━━━━━━━━━━\n\n⏳ *Tu solicitud está en camino*\n🎬 Netflix\n\nEsperamos *10 segundos* para dar tiempo a que llegue el correo. Después buscaremos tu código o enlace más reciente.\n\nSolicítalo primero en Netflix.\n_Te responderemos aquí; no necesitas repetir el comando._'});
   await wait(10000);
  }
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Codes-Signature':createHmac('sha256',secret).update(body).digest('hex')},body,signal:AbortSignal.timeout(30000)});
  if(!response.ok)throw new Error('bridge');
  const result=await response.json();
  for(const outbound of result.messages||[]){
   const target=phone(outbound.to);if(!target||!outbound.text)continue;
   await socket.sendMessage(target===phone(jid)?originalJid:target+'@s.whatsapp.net',{text:String(outbound.text).slice(0,4000)});
  }
 }catch{await socket.sendMessage(jid,{text:'No pudimos atender la solicitud ahora. Inténtalo nuevamente en un minuto.'});}
 return true;
}
