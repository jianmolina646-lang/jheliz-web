import test from 'node:test';
import assert from 'node:assert/strict';
import {tabColors,tableDesign} from '../src/sheet-design.js';
test('all thirteen tabs have distinct persistent colors',()=>{
 assert.equal(Object.keys(tabColors).length,13);
 assert.equal(new Set(Object.values(tabColors).map(c=>JSON.stringify(c))).size,13);
 for(const [title,color] of Object.entries(tabColors)){
  if(title==='Panel ejecutivo')continue;
  const requests=tableDesign({title,headers:['ID']},{properties:{sheetId:1}},100);
  assert.deepEqual(requests[0].updateSheetProperties.properties.tabColorStyle.rgbColor,color);
 }
});
