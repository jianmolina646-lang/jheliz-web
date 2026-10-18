import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import {getPayHistory, loadBinanceCredentials} from '../src/binance-pay.js';

const options = {apiKey: 'test-key', apiSecret: 'test-secret', startTime: 1000, endTime: 2000, now: () => 2000};
test('requires credentials without exposing secrets', () => {
 assert.throws(() => loadBinanceCredentials({}), /BINANCE_NOT_CONFIGURED/);
});
test('signs a read-only request to the fixed Binance host', async () => {
 const result = await getPayHistory({...options, fetchImpl: async (url, init) => {
  const parsed = new URL(url);
  assert.equal(parsed.origin, 'https://api.binance.com');
  const signature = parsed.searchParams.get('signature');
  parsed.searchParams.delete('signature');
  assert.equal(signature, createHmac('sha256', options.apiSecret).update(parsed.searchParams.toString()).digest('hex'));
  assert.equal(init.method, 'GET');
  assert.equal(init.redirect, 'error');
  assert.equal(init.headers['X-MBX-APIKEY'], options.apiKey);
  return {ok: true, json: async () => ({success: true, code: '000000', data: []})};
 }});
 assert.deepEqual(result, {transactions: [], potentiallyTruncated: false});
});
test('sanitizes network failures', async () => {
 await assert.rejects(getPayHistory({...options, fetchImpl: async () => {throw new Error('private-url-secret');}}), /^Error: BINANCE_CONNECTION_FAILED$/);
});
test('fails closed on HTTP and malformed API responses', async () => {
 await assert.rejects(getPayHistory({...options, fetchImpl: async () => ({ok: false, status: 401})}), /BINANCE_HTTP_401/);
 await assert.rejects(getPayHistory({...options, fetchImpl: async () => ({ok: true, json: async () => ({success: false})})}), /BINANCE_INVALID_RESPONSE/);
});
test('rejects invalid intervals before making requests', async () => {
 await assert.rejects(getPayHistory({...options, endTime: 0}), /BINANCE_INVALID_WINDOW/);
});
test('flags full pages as potentially incomplete', async () => {
 const result = await getPayHistory({...options, fetchImpl: async () => ({ok: true, json: async () => ({success: true, code: '000000', data: Array(100).fill({})})})});
 assert.equal(result.potentiallyTruncated, true);
});
