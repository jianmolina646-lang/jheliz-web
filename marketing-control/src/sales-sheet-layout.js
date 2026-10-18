export function salesSheetLayout(sheet){
 if(sheet.properties.title==='Vencimientos')return expirySheetLayout(sheet);
 if(sheet.properties.title==='Pagos')return paymentsSheetLayout(sheet);
 if(sheet.properties.title==='Clientes')return clientsSheetLayout(sheet);
 if(sheet.properties.title==='Disponibles')return availableSheetLayout(sheet);
 if(['Inventario','Vendidas'].includes(sheet.properties.title))return inventorySheetLayout(sheet);
 if(sheet.properties.title==='Catálogo')return catalogSheetLayout(sheet);
 if(sheet.properties.title!=='Ventas Bot')return [];
 const sheetId=sheet.properties.sheetId;
 const request=(startIndex,endIndex,properties)=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex,endIndex},properties,fields:Object.keys(properties).join(',')}});
 return [
  // Keep column positions and formulas intact. Technical fields remain recoverable.
  ...[[0,1],[6,9],[11,14]].map(([a,b])=>request(a,b,{hiddenByUser:true})),
  ...[[1,2,160],[2,3,150],[3,4,140],[4,5,110],[5,6,175],[9,11,155],[14,15,240]].map(([a,b,w])=>request(a,b,{pixelSize:w})),
  {repeatCell:{range:{sheetId,startRowIndex:2,startColumnIndex:0,endColumnIndex:1},cell:{userEnteredFormat:{wrapStrategy:'CLIP'}},fields:'userEnteredFormat.wrapStrategy'}},
  {repeatCell:{range:{sheetId,startRowIndex:2,startColumnIndex:6,endColumnIndex:9},cell:{userEnteredFormat:{wrapStrategy:'CLIP'}},fields:'userEnteredFormat.wrapStrategy'}},
  {repeatCell:{range:{sheetId,startRowIndex:2,startColumnIndex:9,endColumnIndex:11},cell:{userEnteredFormat:{numberFormat:{type:'DATE_TIME',pattern:'dd mmm yyyy hh:mm'},textFormat:{fontFamily:'Arial',fontSize:10}}},fields:'userEnteredFormat.numberFormat,userEnteredFormat.textFormat'}},
 ];
}

export function expirySheetLayout(sheet){
 if(sheet.properties.title!=='Vencimientos')return [];
 const sheetId=sheet.properties.sheetId;
 const fmt=(a,b,userEnteredFormat)=>({repeatCell:{range:{sheetId,startRowIndex:2,startColumnIndex:a,endColumnIndex:b},cell:{userEnteredFormat},fields:Object.keys(userEnteredFormat).map(k=>'userEnteredFormat.'+k).join(',')}});
 return [
  ...[0,4].map(i=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:i,endIndex:i+1},properties:{hiddenByUser:true},fields:'hiddenByUser'}})),
  ...[[1,165],[2,150],[3,140],[5,155],[6,155],[7,120],[8,135],[9,160]].map(([i,pixelSize])=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:i,endIndex:i+1},properties:{pixelSize},fields:'pixelSize'}})),
  fmt(0,1,{wrapStrategy:'CLIP'}),fmt(4,5,{wrapStrategy:'CLIP'}),
  fmt(1,2,{textFormat:{fontFamily:'Arial',fontSize:11,bold:true,foregroundColor:{red:.12,green:.2,blue:.3}}}),
  fmt(3,4,{textFormat:{fontFamily:'Arial',fontSize:10,bold:true}}),
  fmt(5,7,{numberFormat:{type:'DATE_TIME',pattern:'dd mmm yyyy hh:mm'},horizontalAlignment:'CENTER'}),
  fmt(7,8,{numberFormat:{type:'NUMBER',pattern:'0" días"'},horizontalAlignment:'CENTER',textFormat:{fontFamily:'Arial',fontSize:11,bold:true}}),
  fmt(8,10,{horizontalAlignment:'CENTER',wrapStrategy:'WRAP',textFormat:{fontFamily:'Arial',fontSize:10,bold:true}}),
 ];
}

export function paymentsSheetLayout(sheet){
 if(sheet.properties.title!=='Pagos')return [];
 const sheetId=sheet.properties.sheetId;
 const fmt=(a,b,userEnteredFormat)=>({repeatCell:{range:{sheetId,startRowIndex:2,startColumnIndex:a,endColumnIndex:b},cell:{userEnteredFormat},fields:Object.keys(userEnteredFormat).map(k=>'userEnteredFormat.'+k).join(',')}});
 return [
  {updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:0,endIndex:1},properties:{hiddenByUser:true},fields:'hiddenByUser'}},
  ...[165,155,145,120,175,200,165,215,165,150].map((pixelSize,i)=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:i+1,endIndex:i+2},properties:{pixelSize},fields:'pixelSize'}})),
  fmt(0,1,{wrapStrategy:'CLIP'}),
  fmt(1,2,{textFormat:{fontFamily:'Arial',fontSize:11,bold:true,foregroundColor:{red:.12,green:.2,blue:.3}}}),
  fmt(3,4,{textFormat:{fontFamily:'Arial',fontSize:10,bold:true}}),
  fmt(4,5,{numberFormat:{type:'CURRENCY',pattern:'"S/ "#,##0.00'},horizontalAlignment:'RIGHT',textFormat:{fontFamily:'Arial',fontSize:11,bold:true}}),
  fmt(5,6,{horizontalAlignment:'CENTER',wrapStrategy:'WRAP'}),
  fmt(6,9,{wrapStrategy:'WRAP',textFormat:{fontFamily:'Arial',fontSize:10}}),
  fmt(9,10,{numberFormat:{type:'DATE_TIME',pattern:'dd mmm yyyy hh:mm'},horizontalAlignment:'CENTER'}),
  fmt(10,11,{horizontalAlignment:'CENTER'}),
 ];
}

export function clientsSheetLayout(sheet){
 if(sheet.properties.title!=='Clientes')return [];
 const sheetId=sheet.properties.sheetId;
 const fmt=(a,b,userEnteredFormat)=>({repeatCell:{range:{sheetId,startRowIndex:2,startColumnIndex:a,endColumnIndex:b},cell:{userEnteredFormat},fields:Object.keys(userEnteredFormat).map(k=>'userEnteredFormat.'+k).join(',')}});
 return [
  {updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:0,endIndex:1},properties:{hiddenByUser:true},fields:'hiddenByUser'}},
  ...[175,155,145,155,155,95,125,150,100].map((pixelSize,i)=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:i+1,endIndex:i+2},properties:{pixelSize},fields:'pixelSize'}})),
  fmt(0,1,{wrapStrategy:'CLIP'}),
  fmt(1,2,{textFormat:{fontFamily:'Arial',fontSize:11,bold:true,foregroundColor:{red:.12,green:.2,blue:.3}}}),
  fmt(2,4,{textFormat:{fontFamily:'Arial',fontSize:10},wrapStrategy:'WRAP'}),
  fmt(4,6,{numberFormat:{type:'DATE_TIME',pattern:'dd mmm yyyy hh:mm'},horizontalAlignment:'CENTER'}),
  fmt(6,8,{numberFormat:{type:'NUMBER',pattern:'0'},horizontalAlignment:'CENTER'}),
  fmt(8,9,{numberFormat:{type:'CURRENCY',pattern:'"S/ "#,##0.00'},horizontalAlignment:'RIGHT',textFormat:{fontFamily:'Arial',fontSize:11,bold:true}}),
  fmt(9,10,{numberFormat:{type:'NUMBER',pattern:'0'},horizontalAlignment:'CENTER'}),
 ];
}

export function availableSheetLayout(sheet){
 if(sheet.properties.title!=='Disponibles')return [];
 const sheetId=sheet.properties.sheetId;
 const fmt=(a,b,userEnteredFormat,startRowIndex=2)=>({repeatCell:{range:{sheetId,startRowIndex,...(startRowIndex===0?{endRowIndex:1}:{}),startColumnIndex:a,endColumnIndex:b},cell:{userEnteredFormat},fields:Object.keys(userEnteredFormat).map(k=>'userEnteredFormat.'+k).join(',')}});
 return [
  {updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:3,endIndex:9},properties:{hiddenByUser:true},fields:'hiddenByUser'}},
  ...[[0,165],[1,275],[2,145],[9,205],[10,175]].map(([i,pixelSize])=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:i,endIndex:i+1},properties:{pixelSize},fields:'pixelSize'}})),
  fmt(0,4,{horizontalAlignment:'LEFT'},0),
  fmt(0,1,{textFormat:{fontFamily:'Arial',fontSize:11,bold:true,foregroundColor:{red:.12,green:.2,blue:.3}}}),
  fmt(1,2,{wrapStrategy:'WRAP',textFormat:{fontFamily:'Arial',fontSize:10}}),
  fmt(2,3,{horizontalAlignment:'CENTER',textFormat:{fontFamily:'Arial',fontSize:10,bold:true}}),
  fmt(3,9,{wrapStrategy:'CLIP'}),
  fmt(9,10,{horizontalAlignment:'CENTER',numberFormat:{type:'DATE',pattern:'dd mmm yyyy'}}),
  fmt(10,11,{horizontalAlignment:'CENTER',numberFormat:{type:'DATE_TIME',pattern:'dd mmm yyyy hh:mm'}}),
 ];
}

export function inventorySheetLayout(sheet){
 if(!['Inventario','Vendidas'].includes(sheet.properties.title))return [];
 const sheetId=sheet.properties.sheetId;
 const format=(a,b,userEnteredFormat)=>({repeatCell:{range:{sheetId,startRowIndex:2,startColumnIndex:a,endColumnIndex:b},cell:{userEnteredFormat},fields:Object.keys(userEnteredFormat).map(k=>'userEnteredFormat.'+k).join(',')}});
 return [
  {updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:6,endIndex:8},properties:{hiddenByUser:true},fields:'hiddenByUser'}},
  ...[140,235,140,160,150,150,160,160,150,170,150].map((pixelSize,i)=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:i,endIndex:i+1},properties:{pixelSize},fields:'pixelSize'}})),
  format(0,1,{textFormat:{fontFamily:'Arial',fontSize:11,bold:true,foregroundColor:{red:.12,green:.2,blue:.3}}}),
  format(1,2,{textFormat:{fontFamily:'Arial',fontSize:10},wrapStrategy:'WRAP'}),
  format(2,3,{horizontalAlignment:'CENTER',textFormat:{fontFamily:'Arial',fontSize:10,bold:true}}),
  format(3,4,{textFormat:{fontFamily:'Arial',fontSize:10,bold:true}}),
  format(4,6,{numberFormat:{type:'DATE_TIME',pattern:'dd mmm yyyy hh:mm'},horizontalAlignment:'CENTER'}),
  format(6,8,{wrapStrategy:'CLIP'}),
 ];
}

export function catalogSheetLayout(sheet){
 if(sheet.properties.title!=='Catálogo')return [];
 const sheetId=sheet.properties.sheetId;
 const format=(startColumnIndex,endColumnIndex,userEnteredFormat)=>({repeatCell:{range:{sheetId,startRowIndex:2,startColumnIndex,endColumnIndex},cell:{userEnteredFormat},fields:Object.keys(userEnteredFormat).map(k=>'userEnteredFormat.'+k).join(',')}});
 return [
  {updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:0,endIndex:1},properties:{hiddenByUser:true},fields:'hiddenByUser'}},
  ...[145,220,125,125,135,145,175].map((pixelSize,i)=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:i+1,endIndex:i+2},properties:{pixelSize},fields:'pixelSize'}})),
  format(0,1,{wrapStrategy:'CLIP'}),
  format(1,2,{textFormat:{fontFamily:'Arial',fontSize:10,foregroundColor:{red:.36,green:.43,blue:.53}}}),
  format(2,3,{textFormat:{fontFamily:'Arial',fontSize:11,bold:true,foregroundColor:{red:.12,green:.2,blue:.3}}}),
  format(3,4,{numberFormat:{type:'CURRENCY',pattern:'"S/ "#,##0.00'},horizontalAlignment:'RIGHT',textFormat:{fontFamily:'Arial',fontSize:11,bold:true}}),
  format(4,5,{numberFormat:{type:'NUMBER',pattern:'0" días"'},horizontalAlignment:'CENTER'}),
  format(5,6,{horizontalAlignment:'CENTER'}),
  format(6,8,{numberFormat:{type:'NUMBER',pattern:'0'},horizontalAlignment:'CENTER'}),
 ];
}
