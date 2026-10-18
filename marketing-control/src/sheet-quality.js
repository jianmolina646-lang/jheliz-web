// Presentation-only diagnostics. Never rejects or modifies a business record.
const rgb=(r,g,b)=>({red:r/255,green:g/255,blue:b/255});
const red=rgb(253,232,232),amber=rgb(255,244,216),green=rgb(229,244,235),blue=rgb(232,240,252);
const letter=n=>String.fromCharCode(65+n);
const legacy=['Disponible','Entregado','Vigente','Vencida','Revisar entrega','Retirada','Por vencer','Pago aprobado','Pendiente de pago / revisión'];
export function qualityRules(report,sheet){
 const id=sheet.properties.sheetId,requests=[];
 // Replace only our named rules and the exact legacy status rules, not user rules.
 for(let i=(sheet.conditionalFormats||[]).length-1;i>=0;i--){
  const rule=sheet.conditionalFormats[i],condition=rule.booleanRule?.condition;
  const owned=condition?.values?.some(v=>v.userEnteredValue?.includes('jheliz:v2:'));
  const old=condition?.type==='TEXT_EQ'&&legacy.includes(condition.values?.[0]?.userEnteredValue)&&rule.ranges?.every(r=>r.startColumnIndex===report.status&&r.endColumnIndex===report.status+1);
  if(owned||old)requests.push({deleteConditionalFormatRule:{sheetId:id,index:i}});
 }
 const add=(expression,bg,col,tag)=>requests.push({addConditionalFormatRule:{index:0,rule:{ranges:[{sheetId:id,startRowIndex:1,startColumnIndex:col,endColumnIndex:col+1}],booleanRule:{condition:{type:'CUSTOM_FORMULA',values:[{userEnteredValue:`=AND(N("jheliz:v2:${tag}")=0,${expression})`}]},format:{backgroundColor:bg}}}}});
 if(report.status!==undefined){
  const col=report.status,cell=`$${letter(col)}2`;
  for(const [values,color] of [[['Disponible','Vendida','Entregado','Vigente','Resuelto'],green],[['Pago aprobado','Enviando cuenta'],blue],[['Por vencer','Pendiente de pago / revisión','Abierto','En atención','Solución pendiente de envío'],amber],[['Vencida','Revisar entrega','Retirada','Rechazado / cancelado','Revisar envío'],red]])add(`OR(${values.map(v=>`${cell}="${v}"`).join(',')})`,color,col,'status');
 }
 const idCol=['Inventario','Disponibles','Vendidas'].includes(report.title)?6:report.summary||report.title==='Guía'?undefined:0;
 if(idCol!==undefined){
  const l=letter(idCol);
  add(`$${l}2<>"",COUNTIF($${l}$2:$${l},$${l}2)>1`,red,idCol,'duplicate-id');
  add(`COUNTIF($A2:$${letter(report.headers.length-1)}2,"?*")+COUNT($A2:$${letter(report.headers.length-1)}2)>0,$${l}2=""`,red,idCol,'missing-id');
 }
 const emailCol=report.headers.indexOf('Correo de la cuenta');
 if(emailCol>=0){
  const l=letter(emailCol),stock=['Inventario','Disponibles','Vendidas'].includes(report.title);
  add(`${stock?'$G2<>""':'$G2<>""'},$${l}2=""`,amber,emailCol,'missing-email');
  if(stock)add(`$${l}2<>"",COUNTIFS($A$2:$A,$A2,$${l}$2:$${l},$${l}2)>1`,amber,emailCol,'duplicate-platform-email');
 }
 for(const [col,name] of report.headers.entries())if(/^(Fecha de vencimiento|Vencimiento|Vencimiento fijo de inventario|Vencimiento original|Vencimiento conservado)$/.test(name)){
  const l=letter(col),cell=`$${l}2`,clock='INDIRECT("\'Resumen\'!B2")';
  add(`ISNUMBER(${cell}),${cell}>${clock},${cell}<=${clock}+7`,amber,col,'expires-soon');
  add(`ISNUMBER(${cell}),${cell}<=${clock}`,red,col,'expired');
 }
 if(['Inventario','Vendidas'].includes(report.title))for(const col of [4,5])add(`$C2="Vendida",$H2<>"",COUNTIFS(INDIRECT("'Ventas Bot'!A2:A"),$H2,INDIRECT("'Ventas Bot'!F2:F"),"Entregado")>0,$${letter(col)}2=""`,red,col,'missing-delivery-date');
 return requests;
}

export function preservedFilter(sheet,cols,rows){
 return {...(sheet.basicFilter||{}),range:{sheetId:sheet.properties.sheetId,startRowIndex:0,endRowIndex:Math.max(2,rows+1),startColumnIndex:0,endColumnIndex:cols}};
}

// Leave existing formulas untouched, including formulas a user adds later.
export function reportWrites(report,totalRows,sheet,headerOffset=0){
 const protectedCells=new Set();
 for(const grid of sheet.data||[])for(const [r,row] of (grid.rowData||[]).entries())for(const [c,cell] of (row.values||[]).entries())if(cell.userEnteredValue?.formulaValue)protectedCells.add(`${(grid.startRow||0)+r}:${(grid.startColumn||0)+c}`);
 const rows=[report.headers,...report.rows,...Array(Math.max(0,totalRows-headerOffset-report.rows.length-1)).fill(Array(report.headers.length).fill(''))];
 const title=report.title.replaceAll("'","''"),writes=[];
 let pending=[],start=0;
 const flush=()=>{if(pending.length)writes.push({range:`'${title}'!A${start+1}`,values:pending});pending=[];};
 rows.forEach((row,r)=>{
  r+=headerOffset;
  if(!row.some((_,c)=>protectedCells.has(`${r}:${c}`))){if(!pending.length)start=r;pending.push(row);if(pending.length===500)flush();return;}
  flush();let values=[],col=0;
  const segment=()=>{if(values.length)writes.push({range:`'${title}'!${letter(col)}${r+1}`,values:[values]});values=[];};
  row.forEach((value,c)=>{if(protectedCells.has(`${r}:${c}`)){segment();return;}if(!values.length)col=c;values.push(value);});segment();
 });flush();return writes;
}
