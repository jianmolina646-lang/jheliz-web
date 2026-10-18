import {codesSheetLayout} from './codes-sheet-layout.js';
import {createHmac,randomUUID} from 'node:crypto';

const title='Clientes · Códigos';
const marker='JHELIZ_CODES_ASSIGNMENTS_V1';
const headers=['ID registro','WhatsApp','Cliente','Correo asignado','Estado de acceso','Registro (Lima)','Asignación (Lima)','Vencimiento acceso (Lima)','Asignación actual','Actualizado (Lima)'];
const date=value=>value?new Intl.DateTimeFormat('es-PE',{timeZone:'America/Lima',dateStyle:'short',timeStyle:'short',hour12:false}).format(new Date(value)):'';

export function mergeAssignments(previous,records,now){
 const current=new Map(records.map(r=>[r.id,[r.id,r.phone,r.name,r.email,r.status,date(r.registered_at),date(r.assigned_at),date(r.expires_at),r.email?'Asignado':'Sin correo',date(now)]]));
 const result=[];
 for(const row of previous){
  if(!row[0])continue;
  if(current.has(row[0])){result.push(current.get(row[0]));current.delete(row[0]);}
  else {const retained=Array.from({length:10},(_,i)=>row[i]||'');retained[8]='Retirado';retained[4]='Sin acceso por esta asignación';if(row[8]!=='Retirado')retained[9]=date(now);result.push(retained);}
 }
 return [...result,...current.values()];
}

export async function syncCodesSheets(sheets){
 const secret=process.env.CODES_BRIDGE_SECRET,url=process.env.CODES_BRIDGE_URL;
 if(!process.env.SHEETS_ID||!secret||!url)return;
 const body=JSON.stringify({action:'export_assignments',timestamp:Math.floor(Date.now()/1000),request_id:randomUUID()});
 const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Codes-Signature':createHmac('sha256',secret).update(body).digest('hex')},body,signal:AbortSignal.timeout(30000)});
 if(!response.ok)throw new Error('Codes export unavailable');
 const data=await response.json();
 if(data.schema!==1||!Array.isArray(data.records)||data.records.some(r=>!r.id||!r.phone))throw new Error('Invalid codes export');
 const meta=await sheets('?fields=sheets(properties,developerMetadata,bandedRanges,basicFilter)');
 let tab=meta.sheets.find(s=>s.properties.title===title);
 if(tab&&!tab.developerMetadata?.some(m=>m.metadataKey===marker))throw new Error('Existing unmanaged codes sheet; refusing overwrite');
 if(!tab){
  const added=await sheets(':batchUpdate','POST',{requests:[{addSheet:{properties:{title,gridProperties:{rowCount:1000,columnCount:10,frozenRowCount:2},tabColorStyle:{rgbColor:{red:0.45,green:0.3,blue:0.8}}}}}]});
  tab={properties:added.replies[0].addSheet.properties};
  await sheets(':batchUpdate','POST',{requests:[{createDeveloperMetadata:{developerMetadata:{metadataKey:marker,metadataValue:'1',location:{sheetId:tab.properties.sheetId},visibility:'DOCUMENT'}}}]});
 }
 const id=tab.properties.sheetId,range="'"+title+"'!A3:J";
 const old=await sheets('/values/'+encodeURIComponent(range));
 const rows=mergeAssignments(old.values||[],data.records,new Date());
 const values=[['','JHELIZ VENTAS | Clientes y códigos','','','','Asignaciones y acceso · Gestión desde el bot'],headers,...rows];
 if(values.length>tab.properties.gridProperties.rowCount)await sheets(':batchUpdate','POST',{requests:[{appendDimension:{sheetId:id,dimension:'ROWS',length:values.length-tab.properties.gridProperties.rowCount+100}}]});
 await sheets('/values/'+encodeURIComponent("'"+title+"'!A1:J"+values.length)+'?valueInputOption=RAW','PUT',{values});
 await sheets(':batchUpdate','POST',{requests:codesSheetLayout(tab,values.length)});
 return {rows:rows.length,current:data.records.length};
}
