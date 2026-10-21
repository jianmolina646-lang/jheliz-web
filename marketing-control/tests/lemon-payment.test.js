import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, existsSync} from 'node:fs';
import {paymentText} from '../src/bot-copy.js';

test('payment instructions replace the former provider without changing PEN amounts', () => {
 const text = paymentText({id:'test-lemon',product_name:'Disney+',days:30,price_cents:700});
 assert.match(text, /Lemon Cash: S\/ 7\.00/);
 assert.doesNotMatch(text, /ligo/i);
 assert.match(text, /Una captura no confirma el pago/);
});

test('only the replacement QR remains available', () => {
 assert.ok(existsSync(new URL('../public/lemon-qr.jpg',import.meta.url)));
 assert.ok(!existsSync(new URL('../public/ligo-qr.jpg',import.meta.url)));
 for (const file of ['../src/commerce-worker.js','../src/admin-alert-copy.js','../src/welcome.js','../src/sheet-banner.js','../public/commerce-ui.js']) {
  assert.doesNotMatch(readFileSync(new URL(file,import.meta.url),'utf8'), /ligo/i);
 }
});
