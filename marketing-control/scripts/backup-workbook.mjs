import {writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {sheets} from '../src/commerce-worker.js';
import {db} from '../src/db.js';
const book=await sheets('?includeGridData=true');
const data=JSON.stringify(book);
writeFileSync('/tmp/jheliz-workbook-before-redesign.json',data,{mode:0o600});
console.log(JSON.stringify({sheets:book.sheets.length,bytes:Buffer.byteLength(data),sha256:createHash('sha256').update(data).digest('hex')}));
await db.end();
