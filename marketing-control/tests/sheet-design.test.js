import test from 'node:test';
import assert from 'node:assert/strict';
import {dashboardData,tableDesign,dashboardFormulas} from '../src/sheet-design.js';
import {qualityRules,preservedFilter,reportWrites} from '../src/sheet-quality.js';
test('dashboard totals use paid orders, platform identity and Lima dates without credentials',()=>{
 const now=new Date('2026-10-13T12:00:00Z');
 const products=[{id:'p',name:'Netflix',available:1,active:true}];
 const stock=[{id:'s',product_id:'p',state:'AVAILABLE',password:'SECRET'}];
 const orders=[{product_id:'p',instance_id:'i',jid:'j',status:'DELIVERED',price_cents:3500,approved_at:'2026-10-13T04:00:00Z',expires_at:'2026-10-15T12:00:00Z'}, {product_id:'p',instance_id:'i',jid:'j',status:'REJECTED',price_cents:9000}];
 const result=dashboardData(products,stock,orders,[{status:'OPEN'}],now);
 assert.equal(result.metrics[0][1],35);assert.equal(result.metrics[2][1],1);assert.equal(result.metrics[6][1],1);
 assert.equal(result.platforms[0][8],35);assert.equal(result.trend.at(-2)[1],35);assert.equal(result.trend.at(-1)[1],0);
 assert.ok(!JSON.stringify(result).includes('SECRET'));
});
test('native dashboard formulas reference existing source tabs, not example values',()=>{
 const data=dashboardFormulas();
 assert.equal(data.length,10);
 assert.ok(data.slice(0,8).every(r=>r.values[0][0].startsWith('=')));
 assert.ok(data[3].values[0][0].includes('EOMONTH'));
 assert.equal(data.at(-1).values.length,14);
 assert.ok(!JSON.stringify(data).includes('TODAY'));
 assert.ok(!JSON.stringify(data).includes('COUNTA'));
 assert.ok(data[2].values[0][0].includes('"?*"'));
});
test('quality rules flag identifiers and expiry without deleting custom rules',()=>{
 const custom={ranges:[{sheetId:1}],booleanRule:{condition:{type:'TEXT_EQ',values:[{userEnteredValue:'Manual'}]}}};
 const requests=qualityRules({title:'Vendidas',headers:['Plataforma','Correo de la cuenta','Estado','Cliente','Fecha de inicio','Fecha de vencimiento','Referencia cuenta','Pedido'],status:2},{properties:{sheetId:1},conditionalFormats:[custom]});
 assert.ok(!requests.some(r=>r.deleteConditionalFormatRule));
 assert.ok(JSON.stringify(requests).includes('duplicate-id'));
 assert.ok(JSON.stringify(requests).includes('expires-soon'));
 assert.ok(JSON.stringify(requests).includes('missing-delivery-date'));
});
test('filter refresh preserves criteria and sort settings',()=>{
 const basicFilter={criteria:{2:{hiddenValues:['Retirada']}},sortSpecs:[{dimensionIndex:0,sortOrder:'ASCENDING'}]};
 const filter=preservedFilter({properties:{sheetId:1},basicFilter},11,5);
 assert.deepEqual(filter.criteria,basicFilter.criteria);
 assert.deepEqual(filter.sortSpecs,basicFilter.sortSpecs);
 assert.equal(filter.range.endRowIndex,6);
});
test('report writes never overwrite existing formulas, including cells inside a row',()=>{
 const report={title:'Test',headers:['A','B','C'],rows:[[1,2,3],[4,5,6]]};
 const sheet={data:[{startRow:1,rowData:[{values:[{}, {userEnteredValue:{formulaValue:'=1+1'}}]}]}]};
 const writes=reportWrites(report,3,sheet);
 assert.deepEqual(writes,[{range:"'Test'!A1",values:[['A','B','C']]},{range:"'Test'!A2",values:[[1]]},{range:"'Test'!C2",values:[[3]]},{range:"'Test'!A3",values:[[4,5,6]]}]);
});
test('monthly revenue is based on Lima approval dates and excludes rejected orders',()=>{
 const result=dashboardData([],[],[
 {status:'DELIVERED',price_cents:3500,approved_at:'2026-10-01T04:00:00Z'},
 {status:'APPROVED',price_cents:2000,approved_at:'2026-10-01T05:00:00Z'},
 {status:'REJECTED',price_cents:9000,approved_at:'2026-10-02T05:00:00Z'}
 ],[],new Date('2026-10-13T12:00:00Z'));
 assert.equal(result.metrics[0][1],55);
 assert.equal(result.metrics[3][1],20);
 assert.equal(result.metrics[5][1],3);
});
test('table design preserves data and emits formatting only',()=>{
 const requests=tableDesign({title:'Vendidas',headers:['Plataforma','Correo de la cuenta','Fecha de inicio'],dates:[2]}, {properties:{sheetId:1},bandedRanges:[]},100);
 assert.ok(requests.some(r=>r.addBanding));assert.ok(!requests.some(r=>r.deleteSheet||r.updateCells));
 assert.equal(requests.find(r=>r.updateDimensionProperties?.range?.dimension==='COLUMNS'&&r.updateDimensionProperties.range.startIndex===1).updateDimensionProperties.properties.pixelSize,260);
 assert.ok(requests.some(r=>r.repeatCell?.cell?.userEnteredFormat?.wrapStrategy==='WRAP'&&r.repeatCell.range.startRowIndex===1));
 assert.ok(requests.some(r=>r.updateBorders?.innerVertical));
 assert.equal(requests[0].updateSheetProperties.properties.gridProperties.frozenColumnCount,0);
});
