import {usdtFromPenCents} from './binance-pricing.js';
import {transaction} from './commerce.js';
export function paymentChoiceText(o){
 return `🧾 *JHELIZ · ${o.renewal_of?'Renovación':'Tu pedido'}*\n\n${o.product_name}\n💰 S/ ${(o.price_cents/100).toFixed(2)}\n⏳ ${o.renewal_of&&o.days===30?'1 mes calendario':o.days+' días'}\n\n*¿Cómo deseas pagar?*\n\n📲 Responde *QR* para pagar en soles.\n🟨 Responde *BINANCE* para pagar en USDT.\n\nTe enviaremos únicamente los datos del método elegido.\n${o.renewal_of?'Conservas tu misma cuenta.\n':''}\nPedido: ${o.id}\n/pedidos · Estado\n/cancelar · Cancelar antes de pagar\n/soporte · Ayuda`;
}
export function selectedPaymentText(o,method){
 const details=method==='QR'
  ?`📲 *Lemon Cash: S/ ${(o.price_cents/100).toFixed(2)}*\nEscanea el QR adjunto.\nDestinatario: *Jhedy Javier Villa Lima*\n\nDespués de la captura te pediremos el nombre completo y apellidos del titular. Validaremos el ingreso automáticamente; los casos dudosos requieren revisión.`
  :`🟨 *Binance Pay: ${usdtFromPenCents(o.price_cents)} USDT*\nID de recepción: *739582457*\nDestinatario: *Jheliz2004*\nComprueba el ID, destinatario y moneda antes de pagar.\nCambio fijo: S/ 3.80 por USDT.\n\nEl administrador verificará el ingreso real antes de aprobar.`;
 return `${details}\n\n📸 Envía el comprobante como imagen JPG o PNG de menos de 5 MB. Oculta saldos y datos ajenos al pago.\nUna captura no confirma el pago.\n${o.renewal_of?'Al aprobar, actualizaremos el vencimiento de tu misma cuenta.':'La entrega requiere aprobación y stock disponible.'}\n\nPedido: ${o.id}\n/pedidos · Estado\n/soporte · Ayuda`;
}
export async function selectPayment(instance,jid,method){
 return transaction(async c=>{
  await c.query("SELECT pg_advisory_xact_lock(hashtext('lemon-payment-verification'))");
  const [o]=(await c.query("SELECT * FROM orders WHERE instance_id=$1 AND jid=$2 AND status='PENDING' FOR UPDATE",[instance,jid])).rows;
  if(!o)return {error:'No tienes un pedido pendiente. Escribe /catalogo para elegir una cuenta.'};
  if(o.receipt)return {error:'Ya recibimos tu comprobante. Consulta /pedidos o escribe /soporte para corregir el método de pago.'};
  await c.query('UPDATE orders SET lemon_check=$1,lemon_name_requested_at=null,lemon_payer=null,lemon_payer_normalized=null WHERE id=$2',[method==='QR'?'QR_SELECTED':'MANUAL_BINANCE',o.id]);
  return {order:o};
 });
}
