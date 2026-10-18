import test from 'node:test';
import assert from 'node:assert/strict';
import {deliveriesReference,deliveryState} from '../public/deliveries-reference.js';
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const order={id:'abc-123',instance_id:'bot',jid:'51900000000@s.whatsapp.net',customer:'Prueba',product_name:'Netflix',bot:'Ventas',purpose:'SALES',status:'DELIVERED',retry_count:0,created_at:'2026-10-16T01:00:00Z'};
test('delivery rendering uses real status, local day and existing safe actions',()=>{
 const html=deliveriesReference([order],{h,date:s=>s});
 assert.match(html,/data-day="2026-10-15"/);assert.match(html,/brands\/netflix.png/);assert.match(html,/data-customer-instance="bot"/);assert.match(html,/https:\/\/wa.me\/51900000000/);assert.doesNotMatch(html,/data-retry-delivery|Nueva entrega|156/);assert.equal(deliveryState('REVIEW'),'En revisión');
});
test('LID never becomes a phone chat; retry requires SALES REVIEW and preserves cap',()=>{
 const html=deliveriesReference([{...order,jid:'123456789@lid',customer:'<script>',status:'REVIEW',retry_count:3}],{h,date:s=>s});
 assert.doesNotMatch(html,/wa.me|<script>/);assert.match(html,/&lt;script&gt;/);assert.match(html,/data-retry-delivery="abc-123"[^>]*disabled/);
 const wrong=deliveriesReference([{...order,purpose:'CODES',status:'REVIEW'}],{h,date:s=>s});assert.doesNotMatch(wrong,/data-retry-delivery/);assert.match(wrong,/Entrega comercial no permitida/);
});
