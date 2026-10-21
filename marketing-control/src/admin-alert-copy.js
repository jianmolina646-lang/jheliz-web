import {usdtFromPenCents} from './binance-pricing.js';
export const ADMIN_ALERT_JID='51978640413@s.whatsapp.net';
const plain=v=>String(v||'').replace(/[\r\n*_~`]/g,' ').slice(0,100);
export function pendingPaymentReason(o){
 if(o.lemon_check==='MANUAL_BINANCE')return 'Pago Binance pendiente de revisión manual.';
 if(o.receipt_amount_cents==null)return 'No se pudo leer un monto único en la captura.';
 if(o.receipt_amount_cents!==o.price_cents)return 'El monto de la captura no coincide con el precio del pedido.';
 if(!o.receipt_operation_minute)return 'No se pudo leer la fecha y hora de operación en la captura.';
 if(o.lemon_name_requested_at||!o.has_payer)return 'Falta que el cliente envíe o corrija el nombre completo del titular.';
 if(o.verifier_enabled===false)return 'La validación automática está desactivada.';
 if(o.verifier_error)return 'El verificador de correo no está disponible; requiere revisión.';
 return ({NAME_MISMATCH:'El nombre enviado no coincide con el titular del correo.',
  RECEIPT_TIME_MISMATCH:'La fecha o el minuto de la captura no coincide con el correo.',
  AMBIGUOUS:'Hay varias coincidencias posibles; no se puede asignar el pago con seguridad.',
  AMBIGUOUS_OR_USED:'Pago ambiguo, utilizado o bloqueado; requiere revisión.',
  NO_STOCK:'No hay una cuenta disponible que cubra la vigencia del pedido.',
  RENEWAL_REVIEW:'La cuenta original de la renovación requiere revisión.'
 })[o.lemon_check]||'Todavía no se encontró una coincidencia válida con el correo de pago.';
}
export function adminAlertText(order,kind){
 if(kind==='PAYMENT_DELAYED')return `⏳ *Pago pendiente · Más de 5 minutos*\n*JHELIZ · Aviso al administrador*\n\n👤 ${plain(order.customer)}\n🎬 ${plain(order.product_name)}\n💰 S/ ${(order.price_cents/100).toFixed(2)}\n\n🔎 *Motivo:* ${pendingPaymentReason(order)}\n\n🧾 Pedido: ${order.id}\n\nRevisa el caso antes de aprobar. Este aviso no confirma el pago. No pidas al cliente que vuelva a pagar.\nAviso único para este pedido.`;
 return `${kind==='RECEIPT'?'📸 *Comprobante recibido*':'🛍️ *Nuevo pedido*'}\n*JHELIZ · Aviso al administrador*\n\n👤 ${plain(order.customer)}\n🎬 ${plain(order.product_name)} · ${order.days} días\n💰 S/ ${(order.price_cents/100).toFixed(2)}\n\n🟡 Pendiente de revisión. Este aviso NO confirma el pago.\n${kind==='RECEIPT'?'Consulta el estado del pago antes de aprobar manualmente.':'Espera el comprobante y la validación del ingreso.'}\n\n🧾 Pedido: ${order.id}`;
}
