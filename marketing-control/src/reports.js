import {db} from './db.js';
import {categoryNames,ticketStates} from './support.js';
import {decrypt} from './commerce.js';
import {tableDesign,syncDashboard} from './sheet-design.js';
import {qualityRules,preservedFilter,reportWrites} from './sheet-quality.js';
import {migrationRequests,belowBanner,bannerDesign,bannerVersion} from './sheet-banner.js';

export const orderLabels={PENDING:'Pendiente de pago / revisión',APPROVED:'Pago aprobado',SENDING:'Enviando cuenta',DELIVERED:'Entregado',REVIEW:'Revisar entrega',REJECTED:'Rechazado / cancelado'};
const stockLabels={AVAILABLE:'Disponible',SOLD:'Vendida',DISABLED:'Retirada'};
const paid=o=>['APPROVED','SENDING','DELIVERED','REVIEW'].includes(o.status);
const date=v=>v?(new Date(v).getTime()-5*3600000)/86400000+25569:'';
const day=v=>v?Date.parse((v instanceof Date?v.toISOString():String(v)).slice(0,10)+'T00:00:00Z')/86400000+25569:'';
const phone=v=>String(v).replace(/@.*$/,'');
const table=(title,headers,rows,options={})=>({title,headers,rows,...options});

// This projection receives only explicitly selected non-secret fields.
export function buildReports(products,stock,orders,now=new Date(),history=[]){
 const byStock=new Map(orders.filter(o=>o.stock_id).map(o=>[o.stock_id,o]));
 const emails=new Map(stock.map(s=>[s.id,s.account_email||'']));
 const byOrder=new Map(orders.map(o=>[o.id,o]));for(const a of history)if(byOrder.has(a.order_id)&&!byStock.has(a.old_stock_id))byStock.set(a.old_stock_id,byOrder.get(a.order_id));
 const stockRows=stock.map(s=>{const o=byStock.get(s.id);return [s.product_name,s.account_email||'',stockLabels[s.state],o?.customer||'',o?date(o.started_at):'',o?date(o.expires_at):'',s.id,o?.id||'',o?phone(o.jid):'',day(s.expires_on),date(s.created_at)];});
 const stockHeaders=['Plataforma / producto','Correo de la cuenta','Estado inventario','Cliente','Fecha de inicio','Fecha de vencimiento','Referencia cuenta','Pedido','WhatsApp / ID','Vencimiento fijo de inventario','Fecha de carga'];
 const customers=new Map();
 for(const o of orders){const key=o.instance_id+':'+o.jid;const c=customers.get(key)||{name:o.customer,jid:o.jid,instance:o.instance_name,first:o.created_at,last:o.created_at,total:0,paid:0,amount:0,pending:0};c.name=o.customer;c.total++;c.last=o.created_at;if(paid(o)){c.paid++;c.amount+=o.price_cents;}if(o.status==='PENDING')c.pending++;customers.set(key,c);}
 const approved=orders.filter(paid),delivered=orders.filter(o=>o.status==='DELIVERED');
 const expires=orders.filter(o=>o.expires_at&&o.source!=='RENEWAL').sort((a,b)=>new Date(a.expires_at)-new Date(b.expires_at));
 const totals=[['Última actualización (Lima)',date(now)],['Clientes con pedidos',customers.size],['Productos activos',products.filter(p=>p.active).length],['Cuentas disponibles',stock.filter(s=>s.state==='AVAILABLE').length],['Cuentas vendidas / asignadas',stock.filter(s=>s.state==='SOLD').length],['Cuentas retiradas',stock.filter(s=>s.state==='DISABLED').length],['Pedidos totales',orders.length],['Pagos pendientes',orders.filter(o=>o.status==='PENDING').length],['Pagos aprobados',approved.length],['Cuentas entregadas',delivered.length],['Entregas por revisar',orders.filter(o=>o.status==='REVIEW').length],['Cobros aprobados S/',approved.reduce((a,o)=>a+o.price_cents/100,0)],['Vencen en 7 días',expires.filter(o=>new Date(o.expires_at)>=now&&new Date(o.expires_at)-now<=7*86400000).length],['Nota','Cobros aprobados no son utilidad. No incluye gastos ni devoluciones.']];
 const reports=[
  table('Resumen',['INDICADOR','VALOR'],totals,{summary:true}),
  table('Catálogo',['ID producto','Código bot','Producto','Precio S/','Duración días','Visible en bot','Stock disponible','Stock válido para duración'],products.map(p=>[p.id,p.code,p.name,p.price_cents/100,p.days,p.active?'Sí':'No',stock.filter(s=>s.product_id===p.id&&s.state==='AVAILABLE').length,Number(p.available)]),{currency:[3]}),
  table('Inventario',stockHeaders,stockRows,{dates:[4,5,9,10],status:2}),
  table('Disponibles',stockHeaders,stockRows.filter(r=>r[2]==='Disponible'),{dates:[4,5,9,10],status:2}),
  table('Vendidas',stockHeaders,stockRows.filter(r=>r[2]==='Vendida'),{dates:[4,5,9,10],status:2}),
  table('Clientes',['ID cliente','Nombre','WhatsApp / ID','Conexión','Primer pedido','Último pedido','Pedidos','Pagos aprobados','Total aprobado S/','Pendientes'],[...customers].map(([id,c])=>[id,c.name,phone(c.jid),c.instance,date(c.first),date(c.last),c.total,c.paid,c.amount/100,c.pending]),{dates:[4,5],currency:[8]}),
  table('Ventas Bot',['Pedido','Cliente','WhatsApp / ID','Producto','Importe S/','Estado','Referencia cuenta','Referencia de pago','Fecha pedido','Inicio','Vencimiento','Entrega','Conexión','Días','Correo de la cuenta'],orders.map(o=>[o.id,o.customer,phone(o.jid),o.product_name,o.price_cents/100,orderLabels[o.status],o.stock_id||'',o.payment_ref||'',date(o.created_at),date(o.started_at),date(o.expires_at),date(o.delivered_at),o.instance_name,o.days,emails.get(o.stock_id)||'']),{dates:[8,9,10,11],currency:[4],status:5}),
  table('Pagos',['Pedido','Cliente','WhatsApp / ID','Producto','Importe S/','Estado','Método','Referencia de pago','Aprobado por','Fecha aprobación','Comprobante recibido'],orders.map(o=>[o.id,o.customer,phone(o.jid),o.product_name,o.price_cents/100,orderLabels[o.status],'No registrado · revisión manual',o.payment_ref||'',o.approver||'',date(o.approved_at),o.has_receipt?'Sí':'No']),{dates:[9],currency:[4],status:5}),
  table('Vencimientos',['Pedido','Cliente','WhatsApp / ID','Producto','Referencia cuenta','Inicio','Vencimiento','Días restantes','Situación','Estado entrega'],expires.map(o=>{const remaining=Math.ceil((new Date(o.expires_at)-now)/86400000);return [o.id,o.customer,phone(o.jid),o.product_name,o.stock_id||'',date(o.started_at),date(o.expires_at),remaining,remaining<=0?'Vencida':remaining<=7?'Por vencer':'Vigente',orderLabels[o.status]];}),{dates:[5,6],status:8}),
  table('Guía',['SECCIÓN','CÓMO UTILIZARLA'],[
   ['Panel','Configura productos, cuentas y pedidos en https://marketingjhelizxyz.online. Esta hoja es un reporte, no modifica el bot.'],
   ['Actualización','Automática aproximadamente cada minuto. Verifica la fecha en Resumen y el estado de Google Sheets en el panel.'],
   ['Ediciones','No edites ni ordenes físicamente estas pestañas: se regeneran desde el panel. Para analizar, usa vistas de filtro o crea una pestaña propia.'],
   ['Seguridad','No contiene contraseñas, claves privadas ni imágenes de comprobantes. Comparte solo con personal autorizado.'],
   ['Inventario','Disponible indica que no fue asignada. Stock válido en Catálogo también comprueba que el vencimiento cubre la duración vendida.'],
   ['Vendidas','Incluye cuentas asignadas a pagos aprobados, aunque su entrega esté pendiente. Consulta Ventas Bot para conocer la entrega.'],
   ['Clientes','Clientes que crearon al menos un pedido. WhatsApp puede usar un identificador privado en vez del teléfono.'],
   ['Fechas','Hora de Perú (America/Lima). La duración empieza al intentar la entrega; los envíos ambiguos requieren revisión.'],
   ['Pagos','Una captura no prueba el ingreso. El administrador verifica el ingreso real en Lemon Cash o Binance antes de aprobar. El método no se deduce de la referencia.'],
   ['Devoluciones','No hay gestión automática de devoluciones. Los totales muestran aprobaciones registradas, no utilidad neta.'],
   ['Historial','Desactivar un producto no borra ventas. La base de datos del panel es la fuente principal.'],
  ])
 ];
 for(const title of ['Ventas Bot','Pagos']){
  const report=reports.find(r=>r.title===title);report.headers.push('Origen de venta');
  report.rows.forEach((row,i)=>{const external=orders[i].source==='EXTERNAL';row.push(orders[i].source==='RENEWAL'?'Renovación':external?'Venta externa':'Bot');if(external&&title==='Pagos')row[6]='Venta externa · registro manual';
   if(title==='Ventas Bot'&&orders[i].renewal_of){const parent=byOrder.get(orders[i].renewal_of);row[6]=parent?.stock_id||'';row[14]=emails.get(parent?.stock_id)||'';}
  });
 }
 return reports;
}

let formatted=false;
export function buildSupportReports(tickets,actions){
 const kinds={CORRECT:'Accesos corregidos',REPLACE:'Cuenta reemplazada',MESSAGE:'Respuesta del administrador'};
 return [
  table('Soporte',['Caso','Pedido','Cliente','WhatsApp / ID','Producto','Problema','Estado','Cuenta reportada','Cuenta actual','Creado','Actualizado','Resuelto','Vencimiento original'],tickets.map(t=>[t.id,t.order_id,t.customer,phone(t.jid),t.product_name,categoryNames[t.category],ticketStates[t.status],t.stock_id,t.current_stock_id,date(t.created_at),date(t.updated_at),date(t.resolved_at),date(t.expires_at)]),{dates:[9,10,11,12],status:6}),
  table('Historial soporte',['Acción','Caso','Pedido','Cliente','Producto','Solución','Cuenta anterior','Cuenta asignada','Responsable','Fecha solución','Envío confirmado','Vencimiento conservado'],actions.map(a=>[a.id,a.ticket_id,a.order_id,a.customer,a.product_name,kinds[a.kind],a.old_stock_id,a.new_stock_id,a.actor_email,date(a.created_at),date(a.sent_at),date(a.expires_at)]),{dates:[9,10,11]})
 ];
}
const color=(r,g,b)=>({red:r/255,green:g/255,blue:b/255});
export async function syncWorkbook(sheets){
 const c=await db.connect();let products,stock,orders,tickets,actions;
 try{await c.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  products=(await c.query("SELECT p.*,count(s.id) FILTER(WHERE s.state='AVAILABLE' AND (s.expires_on IS NULL OR s.expires_on >= (now() AT TIME ZONE 'America/Lima')::date+p.days))::integer AS available FROM products p LEFT JOIN stock s ON s.product_id=p.id GROUP BY p.id ORDER BY p.name")).rows;
  stock=(await c.query('SELECT s.id,s.product_id,p.name AS product_name,s.state,s.expires_on,s.created_at,s.secret FROM stock s JOIN products p ON p.id=s.product_id ORDER BY p.name,s.created_at,s.id')).rows.map(({secret,...item})=>({...item,account_email:JSON.parse(decrypt(secret)).email}));
  orders=(await c.query('SELECT o.id,o.renewal_of,o.source,o.product_id,o.instance_id,o.customer,o.jid,o.product_name,o.price_cents,o.days,o.status,o.stock_id,o.payment_ref,o.created_at,o.approved_at,o.started_at,o.expires_at,o.delivered_at,(o.receipt IS NOT NULL) AS has_receipt,i.name AS instance_name,u.email AS approver FROM orders o JOIN instances i ON i.id=o.instance_id LEFT JOIN users u ON u.id=o.approved_by ORDER BY o.created_at,o.id')).rows;
  tickets=(await c.query('SELECT t.*,o.customer,o.jid,o.product_name,o.stock_id AS current_stock_id,o.expires_at FROM support_tickets t JOIN orders o ON o.id=t.order_id ORDER BY t.created_at,t.id')).rows;
  actions=(await c.query('SELECT a.id,a.ticket_id,t.order_id,o.customer,o.product_name,a.kind,a.old_stock_id,a.new_stock_id,u.email AS actor_email,a.created_at,a.sent_at,a.expires_at FROM support_actions a JOIN support_tickets t ON t.id=a.ticket_id JOIN orders o ON o.id=t.order_id JOIN users u ON u.id=a.actor ORDER BY a.created_at,a.id')).rows;
  await c.query('COMMIT');
 }catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}
 const reports=[...buildReports(products,stock,orders,new Date(),actions),...buildSupportReports(tickets,actions)];
 const metadataPath='?includeGridData=true&fields=sheets.properties,sheets.developerMetadata,sheets.conditionalFormats,sheets.bandedRanges,sheets.charts,sheets.basicFilter,sheets.data(startRow,startColumn,rowData(values(userEnteredValue)))';
 let meta=await sheets(metadataPath);
 const migration=migrationRequests(meta,reports);
 if(migration.length){await sheets(':batchUpdate','POST',{requests:migration});meta=await sheets(metadataPath);formatted=false;}
 const requests=[],layout=[];
 for(const report of reports){
  let s=meta.sheets?.find(s=>s.properties.title===report.title);
  if(!s){const result=await sheets(':batchUpdate','POST',{requests:[{addSheet:{properties:{title:report.title,gridProperties:{rowCount:Math.max(100,report.rows.length+20),columnCount:Math.max(16,report.headers.length)}}}}]});s=result.replies[0].addSheet;
   await sheets(':batchUpdate','POST',{requests:[{createDeveloperMetadata:{developerMetadata:{metadataKey:'jheliz_report',metadataValue:'v1',location:{sheetId:s.properties.sheetId},visibility:'DOCUMENT'}}}]});formatted=false;
   await sheets(':batchUpdate','POST',{requests:[{createDeveloperMetadata:{developerMetadata:{metadataKey:bannerVersion,metadataValue:'1',location:{sheetId:s.properties.sheetId},visibility:'DOCUMENT'}}}]});
  }else if(report.title!=='Ventas Bot'&&!s.developerMetadata?.some(m=>m.metadataKey==='jheliz_report'))throw new Error('Unmanaged report tab: '+report.title);
  const id=s.properties.sheetId,cols=report.headers.length,totalRows=Math.max(s.properties.gridProperties.rowCount,report.rows.length+20);
  if(totalRows>s.properties.gridProperties.rowCount)requests.push({updateSheetProperties:{properties:{sheetId:id,gridProperties:{rowCount:totalRows}},fields:'gridProperties.rowCount'}});
  if(!formatted){
   const formatStart=requests.length;
   requests.push({updateSheetProperties:{properties:{sheetId:id,gridProperties:{frozenRowCount:1,hideGridlines:true},tabColorStyle:{rgbColor:color(32,128,99)}},fields:'gridProperties.frozenRowCount,gridProperties.hideGridlines,tabColorStyle'}},
    {repeatCell:{range:{sheetId:id},cell:{userEnteredFormat:{textFormat:{fontFamily:'Arial',fontSize:10},verticalAlignment:'MIDDLE',wrapStrategy:'CLIP'}},fields:'userEnteredFormat'}},
    {repeatCell:{range:{sheetId:id,startRowIndex:0,endRowIndex:1},cell:{userEnteredFormat:{backgroundColor:color(16,43,37),textFormat:{foregroundColor:color(255,255,255),bold:true,fontSize:11},wrapStrategy:'WRAP'}},fields:'userEnteredFormat'}},
    {updateDimensionProperties:{range:{sheetId:id,dimension:'ROWS',startIndex:0,endIndex:1},properties:{pixelSize:44},fields:'pixelSize'}},
    {updateDimensionProperties:{range:{sheetId:id,dimension:'COLUMNS',startIndex:0,endIndex:cols},properties:{pixelSize:180},fields:'pixelSize'}});
   if(report.title==='Guía'||report.summary)requests.push({updateDimensionProperties:{range:{sheetId:id,dimension:'COLUMNS',startIndex:1,endIndex:2},properties:{pixelSize:report.summary?420:850},fields:'pixelSize'}});
   for(const col of report.dates||[])requests.push({repeatCell:{range:{sheetId:id,startRowIndex:1,startColumnIndex:col,endColumnIndex:col+1},cell:{userEnteredFormat:{numberFormat:{type:'DATE_TIME',pattern:'dd/mm/yyyy hh:mm'}}},fields:'userEnteredFormat.numberFormat'}});
   for(const col of report.currency||[])requests.push({repeatCell:{range:{sheetId:id,startRowIndex:1,startColumnIndex:col,endColumnIndex:col+1},cell:{userEnteredFormat:{numberFormat:{type:'CURRENCY',pattern:'"S/ "#,##0.00'}}},fields:'userEnteredFormat.numberFormat'}});
   if(report.summary)requests.push({repeatCell:{range:{sheetId:id,startRowIndex:1,endRowIndex:2,startColumnIndex:1,endColumnIndex:2},cell:{userEnteredFormat:{numberFormat:{type:'DATE_TIME',pattern:'dd/mm/yyyy hh:mm:ss'}}},fields:'userEnteredFormat.numberFormat'}});
   requests.push(...tableDesign(report,s,totalRows-1));
   requests.push(...qualityRules(report,s));
   for(let n=formatStart;n<requests.length;n++)requests[n]=belowBanner(requests[n]);
   requests.push(...bannerDesign(report,s));
   requests.push(...salesSheetLayout(s));
  }
  if(!report.summary&&report.title!=='Guía')requests.push(belowBanner({setBasicFilter:{filter:preservedFilter(s,cols,report.rows.length)}}));
  layout.push({report,id,totalRows,sheet:s});
 }
 if(requests.length)await sheets(':batchUpdate','POST',{requests});
 const data=[];
 for(const {report,totalRows,sheet} of layout)data.push(...reportWrites(report,totalRows,sheet,1));
 // RAW preserves identifiers and prevents customer-supplied formula injection.
 for(let n=0;n<data.length;n+=20)await sheets('/values:batchUpdate','POST',{valueInputOption:'RAW',data:data.slice(n,n+20)});
 const fitRows=layout.filter(({report})=>report.rows.length&&!report.summary&&report.title!=='Guía').map(({report,id})=>({autoResizeDimensions:{dimensions:{sheetId:id,dimension:'ROWS',startIndex:2,endIndex:report.rows.length+2}}}));
 if(fitRows.length)await sheets(':batchUpdate','POST',{requests:fitRows});
 formatted=true;
 await syncDashboard(sheets,meta,products,stock,orders,tickets);
 for(const o of orders)await db.query('UPDATE orders SET sheets_synced_at=now() WHERE id=$1 AND status=$2',[o.id,o.status]);
 await db.query('UPDATE commerce_sync SET last_success=now(),last_error=null WHERE id=1');
}
import {salesSheetLayout} from './sales-sheet-layout.js';
