// Fixed commercial rate confirmed by the owner, not a live market quotation.
export const PEN_CENTS_PER_USDT = 380;
export function usdtFromPenCents(cents) {
 if (!Number.isSafeInteger(cents) || cents <= 0) throw new Error('INVALID_PRICE');
 // Round half up to two decimals using integers, avoiding floating-point drift.
 const hundredths = (BigInt(cents) * 100n + 190n) / 380n;
 return `${hundredths / 100n}.${String(hundredths % 100n).padStart(2, '0')}`;
}
export const binancePriceNotice = 'Conversión fija: S/ 3.80 = 1 USDT. USDT no es USD bancario. Pago por Binance temporalmente no disponible; no envíes transferencias por este método.';
