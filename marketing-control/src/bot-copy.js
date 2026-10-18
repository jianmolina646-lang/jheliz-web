import {usdtFromPenCents} from './binance-pricing.js';
const date=v=>v?new Date(v).toLocaleString('es-PE',{timeZone:'America/Lima'}):'Sin fecha registrada';
const price=c=>(c/100).toFixed(2);
const divider='────────────';
const reference=id=>`🧾 Referencia de pedido\n${id}`;
const binanceNote='💱 Cambio fijo: S/ 3.80 por USDT.\n🟡 Binance: revisión manual del pago. La captura no activa la entrega.';
// Category icons, not official brand logos.
export function platformIcon(name=''){
 const n=name.toLowerCase();
 if(n.includes('netflix'))return '🎬';
 if(n.includes('prime'))return '🍿';
 if(n.includes('disney'))return '✨';
 if(n.includes('crunchy'))return '🎌';
 if(n.includes('spotify'))return '🎧';
 if(n.includes('youtube'))return '▶️';
 return '📺';
}
export function catalogText(products){
 const cards=products.map(p=>`${platformIcon(p.name)} *${p.name}*\n💰 *S/ ${price(p.price_cents)}* · ${p.days} días\n≈ ${usdtFromPenCents(p.price_cents)} USDT\n${Number(p.available)>0?'🟢 Disponible\n👇 Copia este comando para comprar\n/comprar '+p.code:'⚪ Sin stock · Compra no disponible'}`);
 return `🛍️ *JHELIZ · Catálogo*\nElige tu plataforma y copia su comando.\n\n${cards.length?cards.join('\n\n'+divider+'\n\n'):'Por ahora no hay productos en el catálogo.\nEscribe /soporte si necesitas ayuda.'}\n\n${divider}\n${binanceNote}\n\n📦 Mis compras → /pedidos\n🛟 Ayuda → /soporte\n🏠 Menú → /menu`;
}
export function paymentText(o){
 return `🧾 *JHELIZ · Tu pedido*\n🟡 Pendiente de pago y revisión\n\n${platformIcon(o.product_name)} *${o.product_name}*\n📅 ${o.days} días\n\n*Elige UN método de pago*\n\n💳 *Ligo: S/ ${price(o.price_cents)}*\nEscanea el QR de Ligo adjunto.\nDestinatario: Jhedy Javier Villa Lima\n\n🟨 *Binance Pay: ${usdtFromPenCents(o.price_cents)} USDT*\nID de recepción:\n739582457\nAlias del destinatario: *Jheliz2004*\nComprueba el ID y el alias antes de confirmar. Si no coinciden, no pagues y contacta al administrador. El QR adjunto es SOLO de Ligo.\n\n📸 *Después de pagar*\nEnvía una captura como imagen JPG o PNG, de menos de 5 MB. Debe mostrar el importe, moneda, destinatario e ID de operación. Oculta saldos y datos ajenos al pago.\n\n🔎 Un administrador comprobará el ingreso real. Una captura no confirma el pago. La cuenta se entrega únicamente después de aprobar y asignar stock disponible.\n\n${binanceNote}\n\n${reference(o.id)}\n\n📦 Estado → /pedidos\n↩️ Cancelar antes de pagar → /cancelar\n🛟 Ayuda → /soporte`;
}
export function receiptText(id){
 return `📩 *JHELIZ · Comprobante recibido*\n🟡 *Pendiente de verificación*\n\nUn administrador comprobará el ingreso real en Ligo o Binance, según tu comprobante.\n\n🔎 Se revisará el importe, la moneda y que la operación no haya sido utilizada antes.\n📦 La entrega se realizará después de aprobar el pago y asignar una cuenta disponible.\n\nRecibir la captura no significa que el pago esté aprobado. No envíes claves ni códigos de seguridad.\n\n${reference(id)}\n\n📦 Consultar estado → /pedidos\n🛟 Ayuda → /soporte`;
}
export function deliveryText(o,a){
 const duration=Number.isInteger(o.days)&&o.days>0?`${o.days} días`:'Consulta la vigencia indicada';
 return `✅ *JHELIZ · Tu cuenta está lista*\n${o.source==='EXTERNAL'?'📋 Venta anterior registrada · vigencia original conservada':'💳 Pago aprobado'}\n\n${platformIcon(o.product_name)} *${o.product_name}*\nGracias por elegir Jheliz.\n\n${divider}\n🔐 *DATOS DE ACCESO*\n\n📧 *Correo*\n${a.email}\n\n🔑 *Contraseña*\n${a.password}\n\n${divider}\n🗓️ *VIGENCIA DE TU CUENTA*\n\n🟢 *Fecha de inicio*\n${date(o.started_at)}\n\n🏁 *Fecha de fin*\n${date(o.expires_at)}\n\n⏳ *Duración del plan:* ${duration}\n🕒 Todas las fechas están en hora de Perú.\n\n${divider}\n*¿Cómo ingresar?*\n1️⃣ Abre la plataforma indicada.\n2️⃣ Inicia sesión con el correo y la contraseña de arriba, respetando mayúsculas y símbolos.\n\n🔒 Guarda este mensaje en privado. No compartas tus accesos.\n\n🛟 ¿Problemas para ingresar? → /soporte\n📦 Consultar mis compras → /pedidos\n\n${reference(o.id)}`;
}
export function expiryReminderText(o){
 return `⏰ *JHELIZ · Recordatorio de vencimiento*\n\n${platformIcon(o.product_name)} *${o.product_name}*\n🟠 *Vence hoy*\n📅 ${date(o.expires_at)} · Hora de Perú\n\n¿Quieres continuar con tu servicio?\nEscribe /soporte para recibir ayuda con la renovación.\n\n${reference(o.id)}\n\n📦 Mis compras → /pedidos`;
}
export function supportHelp(orders,tickets,states){
 const options=orders.map(o=>`${platformIcon(o.product_name)} *${o.product_name}*\n\n🔑 Contraseña incorrecta\n/soporte ${o.id} clave\n\n⚠️ Suscripción caída\n/soporte ${o.id} caida\n\n💬 Otro problema\n/soporte ${o.id} otro`);
 const recent=tickets.length?'\n\n'+divider+'\n📋 *Tus casos recientes*\n'+tickets.map(t=>`${t.product_name} · ${states[t.status]||'En revisión'}\nCaso: ${t.id}`).join('\n\n'):'';
 return `🛟 *JHELIZ · Centro de ayuda*\nEstamos aquí para ayudarte.\n\n${options.length?'Elige tu compra y copia el comando que corresponde:\n\n'+options.join('\n\n'+divider+'\n\n'):'No encontramos compras entregadas en este WhatsApp. Contacta al administrador para revisar tu compra.'}${recent}\n\n🔒 No envíes contraseñas al reportar.\nSi ya abriste un caso, no necesitas crear otro por el mismo problema.\n\n🏠 Volver al menú → /menu`;
}
