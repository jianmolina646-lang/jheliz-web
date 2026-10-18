import {createHmac} from 'node:crypto';
import {readFileSync} from 'node:fs';

// Separate read-only connectivity from payment approval. Never log responses,
// signatures, URLs or credentials: history contains private financial data.
export function loadBinanceCredentials(env = process.env) {
 const read = name => env[`${name}_FILE`]
  ? readFileSync(env[`${name}_FILE`], 'utf8').trim()
  : (env[name] || '').trim();
 const apiKey = read('BINANCE_API_KEY');
 const apiSecret = read('BINANCE_API_SECRET');
 if (!apiKey || !apiSecret) throw new Error('BINANCE_NOT_CONFIGURED');
 return {apiKey, apiSecret};
}

export async function getPayHistory({apiKey, apiSecret, startTime, endTime,
 fetchImpl = fetch, now = Date.now} = {}) {
 if (!apiKey || !apiSecret) throw new Error('BINANCE_NOT_CONFIGURED');
 if (!Number.isSafeInteger(startTime) || !Number.isSafeInteger(endTime)
  || startTime < 0 || endTime < startTime || endTime - startTime > 90 * 86400000) {
  throw new Error('BINANCE_INVALID_WINDOW');
 }
 const params = new URLSearchParams({startTime: String(startTime),
  endTime: String(endTime), limit: '100', recvWindow: '5000', timestamp: String(now())});
 params.set('signature', createHmac('sha256', apiSecret).update(params.toString()).digest('hex'));
 let response;
 try {
  response = await fetchImpl(`https://api.binance.com/sapi/v1/pay/transactions?${params}`, {
   method: 'GET', headers: {'X-MBX-APIKEY': apiKey},
   redirect: 'error', signal: AbortSignal.timeout(10000)
  });
 } catch { throw new Error('BINANCE_CONNECTION_FAILED'); }
 if (!response.ok) throw new Error(`BINANCE_HTTP_${response.status}`);
 let body;
 try { body = await response.json(); } catch { throw new Error('BINANCE_INVALID_RESPONSE'); }
 if (body.success !== true || body.code !== '000000' || !Array.isArray(body.data)) {
  throw new Error('BINANCE_INVALID_RESPONSE');
 }
 // A full page may omit an operation. Never interpret it as complete history.
 return {transactions: body.data, potentiallyTruncated: body.data.length >= 100};
}
