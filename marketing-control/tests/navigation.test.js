import test from 'node:test';
import assert from 'node:assert/strict';
import {navigationGroups} from '../public/modern-ui.js';
test('navigation includes every operational destination once',()=>{
 const views=navigationGroups.flatMap(([,items])=>items);
 assert.equal(new Set(views).size,views.length);
 assert.deepEqual([...views].sort(),['overview','customers','orders','renewals','deliveries','catalog','inventory','connections','commands','support','reports','events','history','team','audit','settings'].sort());
});
test('sales and product navigation remain distinct from WhatsApp configuration',()=>{
 const groups=Object.fromEntries(navigationGroups);
 assert.deepEqual(groups.WhatsApp,['connections','commands','support']);
 assert.deepEqual(groups.Productos,['catalog','inventory']);
 assert.ok(groups.Ventas.includes('orders'));
});
