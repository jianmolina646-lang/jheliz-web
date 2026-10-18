export function codesSheetLayout(tab,rowCount){
 const sheetId=tab.properties.sheetId;
 const cell=(range,format)=>({repeatCell:{range:{sheetId,...range},cell:{userEnteredFormat:format},fields:Object.keys(format).map(k=>'userEnteredFormat.'+k).join(',')}});
 const navy={red:.07,green:.13,blue:.23},white={red:1,green:1,blue:1};
 const range={sheetId,startRowIndex:1,endRowIndex:Math.max(3,rowCount),startColumnIndex:0,endColumnIndex:10};
 const band={range,rowProperties:{headerColor:navy,firstBandColor:white,secondBandColor:{red:.95,green:.97,blue:1}}};
 const existing=tab.bandedRanges?.find(b=>b.range.startRowIndex===1);
 return [
 {updateSheetProperties:{properties:{sheetId,gridProperties:{frozenRowCount:2,hideGridlines:true}},fields:'gridProperties.frozenRowCount,gridProperties.hideGridlines'}},
 {unmergeCells:{range:{sheetId,startRowIndex:0,endRowIndex:1,startColumnIndex:0,endColumnIndex:10}}},
 ...[[1,5],[5,10]].map(([a,b])=>({mergeCells:{range:{sheetId,startRowIndex:0,endRowIndex:1,startColumnIndex:a,endColumnIndex:b},mergeType:'MERGE_ALL'}})),
 cell({startRowIndex:0,endRowIndex:1},{backgroundColor:white,textFormat:{fontFamily:'Arial',fontSize:16,bold:true,foregroundColor:navy},verticalAlignment:'MIDDLE',horizontalAlignment:'LEFT',wrapStrategy:'CLIP'}),
 cell({startRowIndex:0,endRowIndex:1,startColumnIndex:5,endColumnIndex:10},{textFormat:{fontFamily:'Arial',fontSize:10,foregroundColor:navy},backgroundColor:{red:.92,green:.95,blue:1}}),
 cell({startRowIndex:1,endRowIndex:2},{backgroundColor:navy,textFormat:{fontFamily:'Arial',fontSize:10,bold:true,foregroundColor:white},wrapStrategy:'WRAP',verticalAlignment:'MIDDLE'}),
 cell({startRowIndex:2,endRowIndex:Math.max(3,rowCount),startColumnIndex:0,endColumnIndex:10},{textFormat:{fontFamily:'Arial',fontSize:10},wrapStrategy:'WRAP',verticalAlignment:'MIDDLE',padding:{left:10,right:10,top:8,bottom:8}}),
 {updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:0,endIndex:1},properties:{hiddenByUser:true},fields:'hiddenByUser'}},
 ...[150,170,265,225,165,165,180,145,165].map((pixelSize,i)=>({updateDimensionProperties:{range:{sheetId,dimension:'COLUMNS',startIndex:i+1,endIndex:i+2},properties:{pixelSize},fields:'pixelSize'}})),
 ...[[0,1,54],[1,2,38],[2,Math.max(3,rowCount),48]].map(([startIndex,endIndex,pixelSize])=>({updateDimensionProperties:{range:{sheetId,dimension:'ROWS',startIndex,endIndex},properties:{pixelSize},fields:'pixelSize'}})),
 existing?{updateBanding:{bandedRange:{...band,bandedRangeId:existing.bandedRangeId},fields:'range,rowProperties'}}:{addBanding:{bandedRange:band}},
 {setBasicFilter:{filter:{...tab.basicFilter,range}}},
 ];
}
