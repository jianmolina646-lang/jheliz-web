const rgb=(r,g,b)=>({red:r/255,green:g/255,blue:b/255});
const ink=rgb(20,36,62),green=rgb(39,100,196),mint=rgb(232,240,252),paper=rgb(239,245,255),white=rgb(255,255,255),muted=rgb(99,115,136);
const paid=o=>['APPROVED','SENDING','DELIVERED','REVIEW'].includes(o.status);
const localDay=d=>new Date(new Date(d).getTime()-5*3600000).toISOString().slice(0,10);
const serial=d=>(new Date(d).getTime()-5*3600000)/86400000+25569;
export const tabColors={
 'Panel ejecutivo':ink,
 'Ventas Bot':rgb(37,99,235),
 'Resumen':rgb(79,70,229),
 'Catálogo':rgb(147,51,234),
 'Inventario':rgb(8,145,178),
 'Disponibles':rgb(22,163,74),
 'Vendidas':rgb(219,39,119),
 'Clientes':rgb(13,148,136),
 'Pagos':rgb(202,138,4),
 'Vencimientos':rgb(220,38,38),
 'Guía':rgb(100,116,139),
 'Soporte':rgb(234,88,12),
 'Historial soporte':rgb(162,28,175)
};

// Trusted, native formulas only. Customer-entered text is always written as RAW.
export function dashboardFormulas(){
 const states=['Pago aprobado','Enviando cuenta','Entregado','Revisar entrega'];
 const sum=(extra='')=>states.map(s=>`SUMIFS('Pagos'!E2:E,'Pagos'!F2:F,"${s}"${extra})`).join('+');
 const month=`, 'Pagos'!J2:J,">="&DATE(YEAR('Resumen'!B2),MONTH('Resumen'!B2),1),'Pagos'!J2:J,"<"&EOMONTH('Resumen'!B2,0)+1`;
 const formulas=[`=${sum()}`,`=COUNTIF('Inventario'!C2:C,"Disponible")`,`=COUNTIF('Clientes'!A2:A,"?*")`,`=${sum(month)}`,`=COUNTIF('Inventario'!C2:C,"Vendida")`,`=COUNTIF('Ventas Bot'!A2:A,"?*")`,`=COUNTIFS('Ventas Bot'!K2:K,">"&'Resumen'!B2,'Ventas Bot'!K2:K,"<="&'Resumen'!B2+7)`,`=COUNTIF('Ventas Bot'!F2:F,"Entregado")`];
 const data=formulas.map((formula,n)=>({range:`'Panel ejecutivo'!${['A','D','G','J'][n%4]}${n<4?6:10}`,values:[[formula]]}));
 data.push({range:"'Panel ejecutivo'!AB1:AB3",values:['Disponible','Vendida','Retirada'].map(s=>[`=COUNTIF('Inventario'!C2:C,"${s}")`])});
 data.push({range:"'Panel ejecutivo'!AD1:AE14",values:Array.from({length:14},(_,i)=>[`=INT('Resumen'!B2)-${13-i}`,`=${sum(`,'Pagos'!J2:J,">="&AD${i+1},'Pagos'!J2:J,"<"&AD${i+1}+1`)}`])});
 return data.map(item=>({...item,values:item.values.map(row=>row.map(value=>value.replace(/('(?:Pagos|Inventario|Clientes|Ventas Bot|Resumen)'![A-Z]+)2\b/g,(_,ref)=>ref+'3')))}));
}

export function dashboardData(products,stock,orders,tickets,now=new Date()){
 const approved=orders.filter(paid),available=stock.filter(s=>s.state==='AVAILABLE').length,sold=stock.filter(s=>s.state==='SOLD').length,retired=stock.filter(s=>s.state==='DISABLED').length;
 const revenue=approved.reduce((n,o)=>n+o.price_cents,0)/100;
 const clients=new Set(orders.map(o=>o.instance_id+':'+o.jid)).size;
 const soon=orders.filter(o=>o.expires_at&&new Date(o.expires_at)>now&&new Date(o.expires_at)-now<=7*86400000).length;
 const month=localDay(now).slice(0,7);
 const monthRevenue=approved.filter(o=>o.approved_at&&localDay(o.approved_at).startsWith(month)).reduce((n,o)=>n+o.price_cents,0)/100;
 const metrics=[['VENTAS · COBROS APROBADOS',revenue],['CUENTAS DISPONIBLES',available],['CLIENTES CON PEDIDOS',clients],['INGRESOS · MES EN CURSO',monthRevenue],['CUENTAS VENDIDAS / ASIGNADAS',sold],['OPERACIONES · TODOS LOS ESTADOS',orders.length],['VENCEN EN 7 DÍAS',soon],['VENTAS ENTREGADAS',orders.filter(o=>o.status==='DELIVERED').length]];
 const trend=Array.from({length:14},(_,index)=>{const day=localDay(new Date(now.getTime()-(13-index)*86400000));return [day.slice(8)+'/'+day.slice(5,7),approved.filter(o=>o.approved_at&&localDay(o.approved_at)===day).reduce((sum,o)=>sum+o.price_cents,0)/100];});
 const platforms=products.map(p=>{const own=stock.filter(s=>s.product_id===p.id);return [p.name,'',own.filter(s=>s.state==='AVAILABLE').length,'',Number(p.available),'',own.filter(s=>s.state==='SOLD').length,'',approved.filter(o=>o.product_id===p.id).reduce((sum,o)=>sum+o.price_cents,0)/100,'',p.active?'Activo':'Pausado',''];});
 return {metrics,trend,platforms,inventory:[['Disponibles',available],['Asignadas',sold],['Retiradas',retired]],updated:serial(now)};
}

export function tableDesign(report,sheet,totalRows){
 const id=sheet.properties.sheetId,cols=report.headers.length,requests=[];
 const tab=tabColors[report.title]||green;
 requests.push({updateSheetProperties:{properties:{sheetId:id,tabColorStyle:{rgbColor:tab},gridProperties:{frozenColumnCount:0}},fields:'tabColorStyle,gridProperties.frozenColumnCount'}},
 {updateDimensionProperties:{range:{sheetId:id,dimension:'ROWS',startIndex:1},properties:{pixelSize:34},fields:'pixelSize'}},
 {repeatCell:{range:{sheetId:id,startRowIndex:0,endRowIndex:1},cell:{userEnteredFormat:{textFormat:{fontFamily:'Arial',fontSize:10,bold:true,foregroundColor:white},backgroundColor:ink,verticalAlignment:'MIDDLE',wrapStrategy:'WRAP'}},fields:'userEnteredFormat'}},
 {updateDimensionProperties:{range:{sheetId:id,dimension:'ROWS',startIndex:0,endIndex:1},properties:{pixelSize:52},fields:'pixelSize'}});
 if(!report.summary&&report.title!=='Guía'){
  const cells={sheetId:id,startRowIndex:1,endRowIndex:totalRows,startColumnIndex:0,endColumnIndex:cols};
  const edge={style:'SOLID',color:rgb(215,225,238)};
  requests.push({repeatCell:{range:cells,cell:{userEnteredFormat:{wrapStrategy:'WRAP',verticalAlignment:'MIDDLE',padding:{left:10,right:10,top:8,bottom:8}}},fields:'userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment,userEnteredFormat.padding'}},
   {updateBorders:{range:{...cells,startRowIndex:0},innerVertical:edge,innerHorizontal:edge,left:edge,right:edge,bottom:edge}});
  const bandedRange={range:{sheetId:id,startRowIndex:0,endRowIndex:totalRows,startColumnIndex:0,endColumnIndex:cols},rowProperties:{headerColor:ink,firstBandColor:white,secondBandColor:paper}};
  const existing=(sheet.bandedRanges||[]).find(b=>(b.range.startRowIndex||0)<=1&&!b.range.startColumnIndex);
  requests.push(existing?{updateBanding:{bandedRange:{...bandedRange,bandedRangeId:existing.bandedRangeId},fields:'range,rowProperties'}}:{addBanding:{bandedRange}});
 }
 report.headers.forEach((name,col)=>{
  const width=/Correo/.test(name)?260:/WhatsApp/.test(name)?190:/Referencia|^ID |Pedido|Caso|Cuenta anterior|Cuenta actual|Cuenta asignada|Cuenta reportada/.test(name)?230:/Estado|Problema|Solución/.test(name)?220:/Producto|Plataforma|Cliente|Nombre/.test(name)?200:(report.dates||[]).includes(col)?180:145;
  if(!report.summary&&report.title!=='Guía')requests.push({updateDimensionProperties:{range:{sheetId:id,dimension:'COLUMNS',startIndex:col,endIndex:col+1},properties:{pixelSize:width},fields:'pixelSize'}});
 });
 if(report.summary){requests.push({repeatCell:{range:{sheetId:id,startRowIndex:2,endRowIndex:14,startColumnIndex:1,endColumnIndex:2},cell:{userEnteredFormat:{textFormat:{fontSize:18,bold:true,foregroundColor:green}}},fields:'userEnteredFormat.textFormat'}},{repeatCell:{range:{sheetId:id,startRowIndex:12,endRowIndex:13,startColumnIndex:1,endColumnIndex:2},cell:{userEnteredFormat:{numberFormat:{type:'CURRENCY',pattern:'"S/ "#,##0.00'}}},fields:'userEnteredFormat.numberFormat'}});}
 if(report.title==='Guía')requests.push({repeatCell:{range:{sheetId:id,startRowIndex:1,startColumnIndex:1,endColumnIndex:2},cell:{userEnteredFormat:{wrapStrategy:'WRAP'}},fields:'userEnteredFormat.wrapStrategy'}},{updateDimensionProperties:{range:{sheetId:id,dimension:'ROWS',startIndex:1},properties:{pixelSize:64},fields:'pixelSize'}});
 return requests;
}

let dashboardReady=false;
export async function syncDashboard(sheets,meta,products,stock,orders,tickets){
 const data=dashboardData(products,stock,orders,tickets),title='Panel ejecutivo';
 let sheet=meta.sheets.find(s=>s.properties.title===title);
 if(!sheet){
  const created=await sheets(':batchUpdate','POST',{requests:[{addSheet:{properties:{title,index:0,gridProperties:{rowCount:Math.max(120,data.platforms.length+40),columnCount:32}}}}]});sheet=created.replies[0].addSheet;
  await sheets(':batchUpdate','POST',{requests:[{createDeveloperMetadata:{developerMetadata:{metadataKey:'jheliz_report',metadataValue:'dashboard-v1',location:{sheetId:sheet.properties.sheetId},visibility:'DOCUMENT'}}}]});
 }else if(!sheet.developerMetadata?.some(m=>m.metadataKey==='jheliz_report'))throw new Error('Dashboard name already used by another sheet');
 const id=sheet.properties.sheetId,gridRows=Math.max(sheet.properties.gridProperties.rowCount,data.platforms.length+40);
 const range=(r1,r2,c1=0,c2=12)=>({sheetId:id,startRowIndex:r1,endRowIndex:r2,startColumnIndex:c1,endColumnIndex:c2});
 const merge=(r1,r2,c1=0,c2=12,type='MERGE_ALL')=>({mergeCells:{range:range(r1,r2,c1,c2),mergeType:type}});
 const format=(r1,r2,c1,c2,f)=>({repeatCell:{range:range(r1,r2,c1,c2),cell:{userEnteredFormat:f},fields:'userEnteredFormat'}});
 const requests=[];
 if(gridRows>sheet.properties.gridProperties.rowCount){requests.push({updateSheetProperties:{properties:{sheetId:id,gridProperties:{rowCount:gridRows}},fields:'gridProperties.rowCount'}});dashboardReady=false;}
 if(!dashboardReady){
  requests.push({updateSheetProperties:{properties:{sheetId:id,index:0,gridProperties:{hideGridlines:true,frozenRowCount:3},tabColorStyle:{rgbColor:ink}},fields:'index,gridProperties.hideGridlines,gridProperties.frozenRowCount,tabColorStyle'}},
   {unmergeCells:{range:{sheetId:id}}},
   format(0,gridRows,0,12,{backgroundColor:paper,textFormat:{fontFamily:'Arial',fontSize:10,foregroundColor:ink},verticalAlignment:'MIDDLE'}),
   {updateDimensionProperties:{range:{sheetId:id,dimension:'COLUMNS',startIndex:0,endIndex:12},properties:{pixelSize:92},fields:'pixelSize'}},
   {updateDimensionProperties:{range:{sheetId:id,dimension:'COLUMNS',startIndex:12,endIndex:32},properties:{hiddenByUser:true},fields:'hiddenByUser'}},
   {updateDimensionProperties:{range:{sheetId:id,dimension:'ROWS',startIndex:0},properties:{pixelSize:24},fields:'pixelSize'}},
   merge(0,2),merge(2,3),format(0,2,0,12,{backgroundColor:white,textFormat:{fontFamily:'Arial',fontSize:23,bold:true,foregroundColor:ink},verticalAlignment:'MIDDLE',padding:{left:14},borders:{bottom:{style:'SOLID',color:green}}}),
   format(2,3,0,12,{backgroundColor:mint,textFormat:{fontSize:10,foregroundColor:ink},verticalAlignment:'MIDDLE',padding:{left:14}}));
  data.metrics.forEach((m,n)=>{const row=n<4?4:8,col=(n%4)*3;requests.push(merge(row,row+1,col,col+3),merge(row+1,row+3,col,col+3),format(row,row+1,col,col+3,{backgroundColor:n===0?green:white,textFormat:{fontSize:9,bold:true,foregroundColor:n===0?white:muted},horizontalAlignment:'CENTER',verticalAlignment:'MIDDLE',wrapStrategy:'WRAP'}),format(row+1,row+3,col,col+3,{backgroundColor:n===0?green:white,textFormat:{fontSize:28,bold:true,foregroundColor:n===0?white:ink},horizontalAlignment:'CENTER',verticalAlignment:'MIDDLE',numberFormat:n===0||n===3?{type:'CURRENCY',pattern:'"S/ "#,##0.00'}:{type:'NUMBER',pattern:'#,##0'}}));});
  requests.push(merge(11,12),merge(28,29),merge(29,30),merge(30,31),format(11,12,0,12,{textFormat:{fontSize:11,bold:true,foregroundColor:green},backgroundColor:paper}),format(28,29,0,12,{textFormat:{fontSize:10,foregroundColor:muted},backgroundColor:paper}),format(29,30,0,12,{textFormat:{fontSize:10,foregroundColor:muted},backgroundColor:paper}),format(30,31,0,12,{textFormat:{fontSize:13,bold:true,foregroundColor:ink},backgroundColor:mint}));
  for(let col=0;col<12;col+=2)requests.push(merge(31,gridRows,col,col+2,'MERGE_ROWS'));
  requests.push(format(31,32,0,12,{backgroundColor:ink,textFormat:{fontSize:10,bold:true,foregroundColor:white},horizontalAlignment:'CENTER',verticalAlignment:'MIDDLE'}),{repeatCell:{range:range(32,gridRows,8,10),cell:{userEnteredFormat:{numberFormat:{type:'CURRENCY',pattern:'"S/ "#,##0.00'}}},fields:'userEnteredFormat.numberFormat'}});
  const source=(col,rows)=>({sourceRange:{sources:[range(0,rows,col,col+1)]}});
  const charts=[
   {title:'Jheliz · Inventario',subtitle:'Disponibles, asignadas y retiradas',pieChart:{legendPosition:'RIGHT_LEGEND',domain:source(26,3),series:source(27,3),pieHole:0.7}},
   {title:'Jheliz · Cobros de los últimos 14 días',subtitle:'Pagos aprobados por día · soles',basicChart:{chartType:'COLUMN',legendPosition:'NO_LEGEND',headerCount:0,axis:[{position:'BOTTOM_AXIS',title:'Fecha de aprobación'},{position:'LEFT_AXIS',title:'S/'}],domains:[{domain:source(29,14)}],series:[{series:source(30,14),targetAxis:'LEFT_AXIS',colorStyle:{rgbColor:green}}]}}
  ];
  charts.forEach((spec,n)=>{
   const styled={...spec,fontName:'Arial',hiddenDimensionStrategy:'SHOW_ALL',backgroundColorStyle:{rgbColor:white},titleTextFormat:{fontSize:14,bold:true,foregroundColor:ink}};
   const existing=(sheet.charts||[]).find(c=>c.spec?.title===spec.title);
   if(existing)requests.push({updateChartSpec:{chartId:existing.chartId,spec:styled}});
   else requests.push({addChart:{chart:{spec:styled,position:{overlayPosition:{anchorCell:{sheetId:id,rowIndex:12,columnIndex:n*6},widthPixels:540,heightPixels:370,offsetXPixels:5,offsetYPixels:8}}}}});
  });
  requests.push({repeatCell:{range:range(0,14,29,30),cell:{userEnteredFormat:{numberFormat:{type:'DATE',pattern:'dd/mm'}}},fields:'userEnteredFormat.numberFormat'}},{repeatCell:{range:range(0,14,30,31),cell:{userEnteredFormat:{numberFormat:{type:'CURRENCY',pattern:'"S/ "#,##0.00'}}},fields:'userEnteredFormat.numberFormat'}});
 }
 if(requests.length)await sheets(':batchUpdate','POST',{requests});
 const values=[{range:"'Panel ejecutivo'!A1",values:[['JHELIZ  /  CENTRO DE OPERACIONES']]},{range:"'Panel ejecutivo'!A3",values:[['INVENTARIO · VENTAS · CLIENTES · SOPORTE  |  Actualizado: '+new Date().toLocaleString('es-PE',{timeZone:'America/Lima'})]]},{range:"'Panel ejecutivo'!A12",values:[['VISTA GENERAL  /  INVENTARIO Y EVOLUCIÓN DE COBROS']]},{range:"'Panel ejecutivo'!A29",values:[['Los cobros aprobados no son utilidad: no incluyen gastos ni devoluciones.']]},{range:"'Panel ejecutivo'!A30",values:[['Reporte automático · Modifica cuentas y pedidos desde el panel, no desde esta hoja.']]},{range:"'Panel ejecutivo'!A31",values:[['CONTROL POR PLATAFORMA']]},{range:"'Panel ejecutivo'!A32:L32",values:[['Plataforma','','Disponibles','','Stock válido','','Asignadas','','Cobros S/','','Catálogo','']]},{range:"'Panel ejecutivo'!AA1:AB3",values:data.inventory},{range:"'Panel ejecutivo'!AD1:AE14",values:data.trend}];
 // Do not replace the KPI formulas with snapshot values on subsequent updates.
 values[0].values=[['▣  JHELIZ VENTAS  |  Panel ejecutivo']];
 values.splice(values.findIndex(v=>v.range==="'Panel ejecutivo'!AA1:AB3"),2,{range:"'Panel ejecutivo'!AA1:AA3",values:data.inventory.map(r=>[r[0]])});
 data.metrics.forEach(([label],n)=>{const col=['A','D','G','J'][n%4],row=n<4?5:9;values.push({range:`'Panel ejecutivo'!${col}${row}`,values:[[label]]});});
 const platformRows=[...data.platforms,...Array(Math.max(0,gridRows-32-data.platforms.length)).fill(Array(12).fill(''))];
 values.push({range:"'Panel ejecutivo'!A33:L"+gridRows,values:platformRows});
 await sheets('/values:batchUpdate','POST',{valueInputOption:'RAW',data:values});
 if(!dashboardReady)await sheets('/values:batchUpdate','POST',{valueInputOption:'USER_ENTERED',data:dashboardFormulas()});
 dashboardReady=true;
}
