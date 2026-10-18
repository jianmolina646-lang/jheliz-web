import assert from 'node:assert/strict';
import {writeFileSync} from 'node:fs';
import {sheets} from '../src/commerce-worker.js';
import {tabColors} from '../src/sheet-design.js';
import {db} from '../src/db.js';
const path='?fields=sheets.properties';
const before=await sheets(path);
writeFileSync('/tmp/jheliz-tab-colors-before.json',JSON.stringify(before),{mode:0o600});
const targets=before.sheets.filter(s=>tabColors[s.properties.title]);
await sheets(':batchUpdate','POST',{requests:targets.map(s=>({updateSheetProperties:{properties:{sheetId:s.properties.sheetId,tabColorStyle:{rgbColor:tabColors[s.properties.title]}},fields:'tabColorStyle'}}))});
const after=await sheets(path);
for(const s of targets){
 const current=after.sheets.find(n=>n.properties.sheetId===s.properties.sheetId);
 assert.equal(current.properties.title,s.properties.title);
 for(const [channel,value] of Object.entries(tabColors[s.properties.title]))assert.ok(Math.abs(current.properties.tabColorStyle.rgbColor[channel]-value)<0.00001);
}
console.log(JSON.stringify({tabsUpdated:targets.map(s=>s.properties.title),verified:true,fieldsChanged:'tabColorStyle only'}));
await db.end();
