import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import {sheets} from '../src/commerce-worker.js';
import {db,rows} from '../src/db.js';
const before=JSON.parse(readFileSync('/tmp/jheliz-workbook-before-redesign.json','utf8'));
const after=await sheets('?includeGridData=true');
const operational=before.sheets.filter(s=>!['Panel ejecutivo','Resumen'].includes(s.properties.title));
const banner=process.env.BANNER_VERIFY==='1';
function content(s,offset=0){
 const cells=[];
 for(const g of s.data||[])for(const [r,row] of (g.rowData||[]).entries())for(const [c,cell] of (row.values||[]).entries())if(r+(g.startRow||0)>=offset&&cell.userEnteredValue&&JSON.stringify(cell.userEnteredValue)!=='{"stringValue":""}')cells.push([r+(g.startRow||0)-offset,c+(g.startColumn||0),cell.userEnteredValue]);
 return cells;
}
assert.deepEqual(after.sheets.map(s=>[s.properties.sheetId,s.properties.title]),before.sheets.map(s=>[s.properties.sheetId,s.properties.title]));
for(const old of operational){const current=after.sheets.find(s=>s.properties.sheetId===old.properties.sheetId);assert.deepEqual(content(current,banner&&old.properties.title!=='Hoja 1'?1:0),content(old),`Data changed: ${old.properties.title}`);assert.deepEqual(current.filterViews,old.filterViews);}
const panel=after.sheets.find(s=>s.properties.title==='Panel ejecutivo');
assert.deepEqual(panel.charts.map(c=>c.chartId),before.sheets.find(s=>s.properties.title==='Panel ejecutivo').charts.map(c=>c.chartId));
const errors=[],formulas=[];
for(const s of after.sheets)for(const g of s.data||[])for(const [r,row] of (g.rowData||[]).entries())for(const [c,cell] of (row.values||[]).entries()){
 if(cell.effectiveValue?.errorValue)errors.push({sheet:s.properties.title,row:r+1,col:c+1,error:cell.effectiveValue.errorValue});
 if(cell.userEnteredValue?.formulaValue)formulas.push({sheet:s.properties.title,row:r+1,col:c+1});
}
assert.deepEqual(errors,[]);
assert.equal(formulas.length,39);
for(const s of after.sheets.filter(s=>s.basicFilter)){
 assert.equal(s.properties.gridProperties.frozenRowCount,banner?2:1);
 assert.ok(s.bandedRanges?.length,`Missing banding: ${s.properties.title}`);
 const header=s.data[0].rowData[banner?1:0].values[0].userEnteredFormat;
 assert.ok(Math.abs(header.backgroundColor.red-20/255)<0.00001,`Header palette: ${s.properties.title}`);
 assert.ok(Math.abs(header.backgroundColor.blue-62/255)<0.00001);
}
if(banner)for(const s of after.sheets.filter(s=>s.properties.title!=='Hoja 1')){
 assert.ok(s.data[0].rowData[0].values[0].userEnteredValue.stringValue.includes('JHELIZ VENTAS'));
 if(s.basicFilter)assert.equal(s.basicFilter.range.startRowIndex,1);
}
const kpis=await sheets('/values:batchGet?ranges='+encodeURIComponent("'Panel ejecutivo'!A6:L6")+'&ranges='+encodeURIComponent("'Panel ejecutivo'!A10:L10")+'&valueRenderOption=UNFORMATTED_VALUE');
const actual=kpis.valueRanges.flatMap(r=>[0,3,6,9].map(i=>r.values[0][i]));
const [expected]=await rows(`SELECT
 (SELECT coalesce(sum(price_cents),0)::float/100 FROM orders WHERE status IN ('APPROVED','SENDING','DELIVERED','REVIEW')) AS revenue,
 (SELECT count(*)::int FROM stock WHERE state='AVAILABLE') AS available,
 (SELECT count(DISTINCT (instance_id,jid))::int FROM orders) AS clients,
 (SELECT coalesce(sum(price_cents),0)::float/100 FROM orders WHERE status IN ('APPROVED','SENDING','DELIVERED','REVIEW') AND date_trunc('month',approved_at AT TIME ZONE 'America/Lima')=date_trunc('month',now() AT TIME ZONE 'America/Lima')) AS month,
 (SELECT count(*)::int FROM stock WHERE state='SOLD') AS sold,
 (SELECT count(*)::int FROM orders) AS operations,
 (SELECT count(*)::int FROM orders WHERE expires_at>now() AND expires_at<=now()+interval '7 days') AS soon,
 (SELECT count(*)::int FROM orders WHERE status='DELIVERED') AS delivered`);
assert.deepEqual(actual,Object.values(expected));
console.log(JSON.stringify({dataPreserved:operational.map(s=>s.properties.title),sheetIdsPreserved:true,chartIdsPreserved:true,headersAndBandingVerified:true,formulas:formulas.length,formulaErrors:errors,kpis:expected,filters:after.sheets.filter(s=>s.basicFilter).length,qualityRules:after.sheets.reduce((n,s)=>n+(s.conditionalFormats?.length||0),0),sync:await rows('SELECT last_success,last_error FROM commerce_sync'),instances:await rows('SELECT name,status FROM instances')}));
await db.end();
