import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {enhanceMobileTables} from '../public/mobile-ui.js';
test('mobile cards retain existing content, actions and hidden pagination rows',()=>{
 const node=(text,colSpan=1)=>({textContent:text,colSpan,dataset:{},attributes:{},setAttribute(k,v){this.attributes[k]=v;}});
 const headers=[node('Cliente'),node('Acciones')],cells=[node('Example'),node('Approve')];
 const row={...node(''),cells,hidden:true};const headRow={...node(''),cells:headers};
 const table={...node(''),tHead:{...node(''),rows:[headRow]},tBodies:[{...node(''),rows:[row]}],rows:[headRow,row]};
 enhanceMobileTables({querySelectorAll:()=>[table]});
 assert.equal(cells[0].dataset.label,'Cliente');assert.equal(cells[1].dataset.label,'Acciones');
 assert.equal(row.hidden,true);assert.equal(cells[1].textContent,'Approve');assert.equal(table.attributes.role,'table');
 enhanceMobileTables({querySelectorAll:()=>[table]});assert.equal(row.cells.length,2);
});
test('mobile assets are loaded after reference styles and preserve desktop',()=>{
 const html=readFileSync(new URL('../public/index.html',import.meta.url),'utf8');
 const css=readFileSync(new URL('../public/mobile.css',import.meta.url),'utf8');
 assert.ok(html.indexOf('/mobile.css')>html.indexOf('/deliveries-reference.css'));
 assert.ok(html.includes('/mobile-ui.js'));assert.ok(css.includes('@media (max-width:750px)'));
 assert.ok(css.includes('[hidden]{display:none!important}'));
 assert.ok(css.includes('font-size:16px!important'));assert.ok(css.includes('.mobile-nav-backdrop{display:none}'));
});
