const rgb=(r,g,b)=>({red:r/255,green:g/255,blue:b/255});
const navy=rgb(20,44,79),blue=rgb(35,104,207),pale=rgb(234,242,255),white=rgb(255,255,255);
const titles={'Ventas Bot':['▣','Control de pedidos','Registro y seguimiento de pedidos del bot'],Resumen:['◈','Resumen de operaciones','Indicadores consolidados · soles peruanos'],Catálogo:['▦','Catálogo de plataformas','Productos, precios y duración'],Inventario:['▤','Inventario de cuentas','Control de existencias por plataforma'],Disponibles:['✓','Cuentas disponibles','Stock pendiente de asignación'],Vendidas:['✓','Cuentas vendidas','Clientes, accesos y vigencia'],Clientes:['◎','Directorio de clientes','Historial de compras y seguimiento'],Pagos:['▣','Control de pagos','Lemon Cash · validación manual'],Vencimientos:['◷','Control de vencimientos','Seguimiento de vigencia y renovaciones'],Guía:['ⓘ','Guía de uso','Operación, seguridad y criterios'],Soporte:['◇','Centro de soporte','Incidencias y seguimiento'], 'Historial soporte':['◷','Historial de soluciones','Trazabilidad de cambios y reemplazos']};
export const bannerVersion='brand-header-v3';
export function migrationRequests(meta,reports){
 const requests=[];
 for(const report of reports){
  const sheet=meta.sheets.find(s=>s.properties.title===report.title);
  if(!sheet||sheet.developerMetadata?.some(m=>m.metadataKey===bannerVersion))continue;
  if(report.title!=='Ventas Bot'&&!sheet.developerMetadata?.some(m=>m.metadataKey==='jheliz_report'))throw new Error('Unmanaged sheet: '+report.title);
  const headers=sheet.data?.[0]?.rowData?.[0]?.values||[];
  if(!report.headers.every((h,i)=>headers[i]?.userEnteredValue?.stringValue===h))throw new Error('Unexpected headers; refusing to move '+report.title);
  const id=sheet.properties.sheetId;
  requests.push({insertDimension:{range:{sheetId:id,dimension:'ROWS',startIndex:0,endIndex:1},inheritFromBefore:false}}, {createDeveloperMetadata:{developerMetadata:{metadataKey:bannerVersion,metadataValue:'1',location:{sheetId:id},visibility:'DOCUMENT'}}});
 }
 return requests;
}
// Existing table layout is defined relative to its header. Shift the whole
// presentation by one row without touching cell values or business logic.
export function belowBanner(request){
 const out=structuredClone(request);
 function visit(obj){
  if(!obj||typeof obj!=='object')return;
  if('startRowIndex' in obj)obj.startRowIndex++;
  if('endRowIndex' in obj)obj.endRowIndex++;
  if(obj.dimension==='ROWS'){if('startIndex'in obj)obj.startIndex++;if('endIndex'in obj)obj.endIndex++;}
  if('frozenRowCount'in obj)obj.frozenRowCount++;
  if(typeof obj.userEnteredValue==='string'&&obj.userEnteredValue.startsWith('='))obj.userEnteredValue=obj.userEnteredValue.replace(/(\$?[A-Z]+\$?)2\b/g,(_,col)=>col+'3');
  for(const value of Object.values(obj))if(value&&typeof value==='object')visit(value);
 }
 visit(out);return out;
}
export function bannerDesign(report,sheet){
 const id=sheet.properties.sheetId,cols=report.headers.length,split=cols>3?Math.min(4,cols-1):cols;
 const [icon,title,subtitle]=titles[report.title]||['▣',report.title,'Jheliz · operaciones'];
 const range=(a,b)=>({sheetId:id,startRowIndex:0,endRowIndex:1,startColumnIndex:a,endColumnIndex:b});
 const requests=[{updateSheetProperties:{properties:{sheetId:id,gridProperties:{frozenRowCount:2,frozenColumnCount:0}},fields:'gridProperties.frozenRowCount,gridProperties.frozenColumnCount'}},
 {unmergeCells:{range:range(0,cols)}},{mergeCells:{range:range(0,split),mergeType:'MERGE_ALL'}},
 {updateDimensionProperties:{range:{sheetId:id,dimension:'ROWS',startIndex:0,endIndex:1},properties:{pixelSize:58},fields:'pixelSize'}},
 {updateDimensionProperties:{range:{sheetId:id,dimension:'ROWS',startIndex:1,endIndex:2},properties:{pixelSize:36},fields:'pixelSize'}},
 {repeatCell:{range:range(0,cols),cell:{userEnteredFormat:{backgroundColor:white,textFormat:{fontFamily:'Arial',fontSize:16,bold:true,foregroundColor:navy},verticalAlignment:'MIDDLE',wrapStrategy:'CLIP',padding:{left:14,right:12,top:8,bottom:8},borders:{bottom:{style:'SOLID',color:blue}}}},fields:'userEnteredFormat'}},
 {updateCells:{start:{sheetId:id,rowIndex:0,columnIndex:0},rows:[{values:[{userEnteredValue:{stringValue:`${icon}  JHELIZ VENTAS  |  ${title}`},textFormatRuns:[{startIndex:0,format:{foregroundColor:blue}},{startIndex:icon.length+2,format:{foregroundColor:navy}}]}]}],fields:'userEnteredValue,textFormatRuns'}}];
 if(split<cols)requests.push({mergeCells:{range:range(split,cols),mergeType:'MERGE_ALL'}},{repeatCell:{range:range(split,cols),cell:{userEnteredFormat:{backgroundColor:pale,textFormat:{fontFamily:'Arial',fontSize:10,foregroundColor:navy},horizontalAlignment:'RIGHT',verticalAlignment:'MIDDLE',padding:{right:16}}},fields:'userEnteredFormat'}},{updateCells:{start:{sheetId:id,rowIndex:0,columnIndex:split},rows:[{values:[{userEnteredValue:{stringValue:`▎ ${subtitle}`}}]}],fields:'userEnteredValue'}});
 return requests;
}
