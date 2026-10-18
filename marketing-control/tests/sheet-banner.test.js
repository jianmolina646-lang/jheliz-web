import test from 'node:test';
import assert from 'node:assert/strict';
import {migrationRequests,belowBanner,bannerDesign,bannerVersion} from '../src/sheet-banner.js';
import {reportWrites} from '../src/sheet-quality.js';
import {dashboardFormulas} from '../src/sheet-design.js';
test('banner migration inserts once, preserves IDs and rejects unexpected headings',()=>{
 const report={title:'Ventas Bot',headers:['Pedido','Cliente']};
 const sheet={properties:{title:report.title,sheetId:7},data:[{rowData:[{values:report.headers.map(h=>({userEnteredValue:{stringValue:h}}))}]}]};
 const requests=migrationRequests({sheets:[sheet]},[report]);
 assert.equal(requests.length,2);assert.equal(requests[0].insertDimension.range.sheetId,7);
 sheet.developerMetadata=[{metadataKey:bannerVersion}];
 assert.deepEqual(migrationRequests({sheets:[sheet]},[report]),[]);
 sheet.developerMetadata=[];sheet.data=[];
 assert.throws(()=>migrationRequests({sheets:[sheet]},[report]),/Unexpected headers/);
});
test('formatting shifts row ranges and INDIRECT references, not column indices',()=>{
 const shifted=belowBanner({addConditionalFormatRule:{index:0,rule:{ranges:[{sheetId:1,startRowIndex:1,startColumnIndex:2}],booleanRule:{condition:{values:[{userEnteredValue:'=AND($C2="Vendida",$F2>INDIRECT("Resumen!B2"),COUNTIF($G$2:$G,$G2)>1)'}]}}}}});
 assert.equal(shifted.addConditionalFormatRule.rule.ranges[0].startRowIndex,2);
 assert.equal(shifted.addConditionalFormatRule.rule.ranges[0].startColumnIndex,2);
 assert.equal(shifted.addConditionalFormatRule.rule.booleanRule.condition.values[0].userEnteredValue,'=AND($C3="Vendida",$F3>INDIRECT("Resumen!B3"),COUNTIF($G$3:$G,$G3)>1)');
});
test('writes start at row two and preserve formulas in row three',()=>{
 const writes=reportWrites({title:'Test',headers:['A','B'],rows:[[1,2]]},3,{data:[{startRow:2,rowData:[{values:[{userEnteredValue:{formulaValue:'=1'}}]}]}]},1);
 assert.deepEqual(writes,[{range:"'Test'!A2",values:[['A','B']]},{range:"'Test'!B3",values:[[2]]}]);
});
test('all native dashboard sources start at data row three; helper references stay put',()=>{
 const text=JSON.stringify(dashboardFormulas());
 assert.ok(text.includes("'Resumen'!B3"));assert.ok(text.includes("'Pagos'!E3:E"));
 assert.ok(!text.includes("'Resumen'!B2"));assert.ok(text.includes('AD2'));
});
test('banner has section identity and does not write into business rows',()=>{
 const requests=bannerDesign({title:'Ventas Bot',headers:Array(15).fill('x')},{properties:{sheetId:7}});
 assert.ok(JSON.stringify(requests).includes('Control de pedidos'));
 for(const r of requests)if(r.updateCells)assert.equal(r.updateCells.start.rowIndex,0);
 assert.equal(requests[0].updateSheetProperties.properties.gridProperties.frozenRowCount,2);
});
