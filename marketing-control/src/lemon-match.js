export function normalizePayer(value){
 if(typeof value!=='string'||value.length>160||!/^\p{L}[\p{L}\p{M}\s.'’-]+$/u.test(value.trim()))return null;
 const normalized=value.normalize('NFD').replace(/\p{Diacritic}/gu,'').replace(/[.'’-]/g,' ').replace(/\s+/g,' ').trim().toUpperCase();
 return normalized.split(' ').length>=2&&normalized.length>=5?normalized:null;
}
export function matchesPayment(order,payment,now=Date.now()){
 const created=new Date(order.created_at).getTime(),paid=new Date(payment.paid_at).getTime(),received=new Date(payment.received_at).getTime();
 return !!order.lemon_payer_normalized&&order.lemon_payer_normalized===payment.payer_normalized&&
  order.price_cents===payment.amount_cents&&payment.currency==='PEN'&&
  order.receipt_operation_minute!=null&&Math.floor(new Date(order.receipt_operation_minute).getTime()/60000)===Math.floor(received/60000)&&
  [created,paid,received].every(Number.isFinite)&&paid>=created&&paid<=created+7200000&&
  paid<=now&&received<=now&&now-paid<=86400000&&Math.abs(paid-received)<=600000;
}
export const payerPrompt=id=>`🧾 *JHELIZ · Verifiquemos tu pago*\n\n📸 Recibimos tu comprobante.\n\nPor favor, envía el *nombre completo y los apellidos del titular que realizó el pago*, tal como figuran en su cuenta. Si pagó otra persona, escribe los datos de esa persona.\n\n🔎 Contrastaremos el titular, el importe y la operación con la notificación auténtica de Lemon Cash. Una captura por sí sola no confirma el pago.\n\n🧾 Pedido: ${id}\nNo envíes contraseñas, CCI ni códigos de seguridad.\n/soporte · Corregir los datos del pago`;
