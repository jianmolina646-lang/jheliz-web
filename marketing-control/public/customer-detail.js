export function deliveryNotice(order){
 if(order.purpose!=='CODES')return '';
 return order.status==='DELIVERED'?'Envío registrado · pedido asociado al bot de códigos. Revisar historial; no reenviar.':'Pedido asociado al bot de códigos. Entrega comercial no permitida con esta asignación.';
}
export function periodState(order,now=Date.now()){
 if(order.status!=='DELIVERED')return 'Sin entrega confirmada';
 const end=Date.parse(order.expires_at),start=Date.parse(order.started_at);
 if(!Number.isFinite(end))return 'Sin fecha de corte';
 if(end<=now)return 'Período vencido';
 if(Number.isFinite(start)&&start>now)return 'Inicio pendiente';
 return end-now<=72*3600000?'Vence en 72 horas':'Período vigente';
}
export function customerDetail(data,jid,{escape:h,date,money,badge,table}){
 const orders=data.orders||[],support=data.support||[];
 const groups=new Map();
 for(const o of orders){const key=o.product_name||'Sin plataforma';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(o);}
 const dt=v=>v?date(v):'—';
 return `<section class="detail-profile"><span class="customer-avatar" aria-hidden="true">${h((orders[0]?.customer||'C').slice(0,1).toUpperCase())}</span><div><strong>${h(orders[0]?.customer||'Cliente')}</strong><p>${h(jid.split('@')[0])}${jid.endsWith('@lid')?' · alias WhatsApp':''}</p></div></section><div class="detail-summary"><span><strong>${orders.length}</strong> operaciones cargadas</span><span><strong>${groups.size}</strong> plataformas</span><span><strong>${support.length}</strong> casos de soporte cargados</span></div><p class="muted">Historial por plataforma. Cada fila es una operación, no una cuenta adicional. Una renovación puede sustituir un período anterior. Hasta 500 operaciones y 100 casos; identidad separada por bot.</p>`+
 [...groups].map(([platform,items])=>`<section class="detail-platform"><h3>${h(platform)} <small>${items.length} operaciones</small></h3>`+table(['Cuenta / operación','Entrega / período','Inicio','Vencimiento','Importe / pago'],items.map(o=>`<tr><td><strong>${h(o.email||'Sin cuenta asignada')}</strong><small class="detail-secondary">${o.renewal_of?'Renovación':'Compra'} · ${h(o.id)}</small></td><td>${badge(o.status)}<small class="detail-period">${h(periodState(o))}</small></td><td>${dt(o.started_at)}</td><td>${dt(o.expires_at)}</td><td>${money(o.price_cents)}<small class="detail-secondary">${h(o.payment_ref||'Sin referencia')}</small></td></tr>`).join(''))+'</section>').join('')+
 (!orders.length?'<p class="empty">No hay operaciones registradas para esta identidad.</p>':'')+
 '<h3>Historial de soporte</h3>'+table(['Caso','Estado','Creado','Resuelto'],support.map(t=>`<tr><td>${h(t.category)}<small class="detail-secondary">${h(t.id)}</small></td><td>${h(t.status)}</td><td>${dt(t.created_at)}</td><td>${dt(t.resolved_at)}</td></tr>`).join(''));
}
