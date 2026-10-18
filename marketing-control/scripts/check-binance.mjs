import {loadBinanceCredentials, getPayHistory} from '../src/binance-pay.js';

try {
 const credentials = loadBinanceCredentials();
 const endTime = Date.now();
 await getPayHistory({...credentials, startTime: endTime - 3600000, endTime});
 console.log('Binance: consulta autenticada correcta. No se aprobaron pagos ni se mostraron movimientos.');
} catch (error) {
 const safe = /^BINANCE_[A-Z_0-9]+$/.test(error.message) ? error.message : 'BINANCE_CONFIGURATION_ERROR';
 console.error(`Binance: ${safe}. No se modificaron pagos.`);
 process.exitCode = 1;
}
