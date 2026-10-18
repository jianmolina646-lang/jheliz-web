import {usdtFromPenCents} from './binance-pricing.js';
export const ADMIN_ALERT_JID='51978640413@s.whatsapp.net';
const plain=v=>String(v||'').replace(/[\r\n*_~`]/g,' ').slice(0,100);
export function adminAlertText(order,kind){
 return `${kind==='RECEIPT'?'📸 *Comprobante recibido*':'🛍️ *Nuevo pedido*'}\n*JHELIZ · Aviso al administrador*\n\n👤 ${plain(order.customer)}\n🎬 ${plain(order.product_name)} · ${order.days} días\n💰 S/ ${(order.price_cents/100).toFixed(2)} · Equivalente: ${usdtFromPenCents(order.price_cents)} USDT\n\n🟡 Pendiente de revisión. Este aviso NO confirma el pago.\n${kind==='RECEIPT'?'Abre el comprobante en el panel y verifica el ingreso real en Ligo o Binance antes de aprobar.':'Espera el comprobante y comprueba el ingreso antes de aprobar.'}\n\n🧾 Pedido: ${order.id}\n🔗 https://marketingjhelizxyz.online/\nEntra en Pedidos y pagos y busca la referencia. Requiere iniciar sesión.`;
}
