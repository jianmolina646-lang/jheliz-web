import {sheets} from '../src/commerce-worker.js';
import {db} from '../src/db.js';
const b=await sheets('?includeGridData=true');
const result={title:b.properties.title,locale:b.properties.locale,timeZone:b.properties.timeZone,namedRanges:b.namedRanges||[],sheets:[]};
for(const s of b.sheets){
 const formulas=[],validations=[];
 for(const g of s.data||[])for(const [i,r] of (g.rowData||[]).entries())for(const [j,c] of (r.values||[]).entries()){
  if(c.userEnteredValue?.formulaValue)formulas.push({row:(g.startRow||0)+i+1,col:(g.startColumn||0)+j+1,formula:c.userEnteredValue.formulaValue});
  if(c.dataValidation)validations.push({row:i+1,col:j+1,rule:c.dataValidation});
 }
 result.sheets.push({title:s.properties.title,id:s.properties.sheetId,grid:s.properties.gridProperties,owned:s.developerMetadata,headers:s.data?.[0]?.rowData?.[0]?.values?.map(c=>c.formattedValue||''),formulas,validations,conditional:s.conditionalFormats?.length||0,filter:s.basicFilter,filterViews:s.filterViews||[],charts:s.charts?.map(c=>({id:c.chartId,title:c.spec.title})),protections:s.protectedRanges?.length||0});
}
console.log(JSON.stringify(result));
await db.end();
