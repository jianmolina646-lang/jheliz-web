import assert from 'node:assert/strict';
import {setTimeout as delay} from 'node:timers/promises';
import {db} from '../src/db.js';
const {rows:[instance]}=await db.query('SELECT id FROM instances ORDER BY name LIMIT 1');
async function waitFor(status){for(let n=0;n<30;n++){const {rows:[row]}=await db.query('SELECT status,qr,heartbeat,last_error FROM instances WHERE id=$1',[instance.id]);if(row.status===status){assert.ok(Date.now()-new Date(row.heartbeat)<20000);if(status==='QR_READY')assert.ok(row.qr?.startsWith('data:image/png;base64,'));console.log('Verified:',status);return;}await delay(2000);}throw new Error('Worker did not reach '+status);}
try{
 await db.query('UPDATE instances SET desired=true,revision=revision+1 WHERE id=$1',[instance.id]);await waitFor('QR_READY');
 await db.query("UPDATE instances SET revision=revision+1,status='CONNECTING',qr=null WHERE id=$1",[instance.id]);await waitFor('QR_READY');
 await db.query('UPDATE instances SET desired=false WHERE id=$1',[instance.id]);await waitFor('DISCONNECTED');await delay(6000);await waitFor('DISCONNECTED');
}finally{await db.query('UPDATE instances SET desired=false WHERE id=$1',[instance.id]);await db.end();}
