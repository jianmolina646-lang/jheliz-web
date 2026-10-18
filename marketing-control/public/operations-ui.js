export function setupOperations({api,escape:h,date,notify,render,getUser}){
 const labels={overview:'Centro de operaciones',customers:'Clientes',renewals:'Renovaciones',deliveries:'Entregas',history:'Historial comercial'};
 const statuses={PENDING:'Pago pendiente',APPROVED:'En cola',SENDING:'Enviando',DELIVERED:'Enviado',REVIEW:'Revisar entrega',REJECTED:'Cancelado'};
 const money=n=>'S/ '+(Number(n||0)/100).toFixed(2);
 const dt=v=>v?date(v):'—';
 const badge=s=>`<span class="pill ${s==='DELIVERED'?'good':s==='REVIEW'?'bad':'warn'}">${h(statuses[s]||s)}</span>`;
 const head=(view,description)=>`<div class="page-heading"><div><p class="eyebrow">JHELIZ · CONTROL COMERCIAL</p><h2>${labels[view]}</h2><p>${description}</p></div><button data-view="${view}">Actualizar</button></div>`;
 const table=(headers,body)=>`<div class="card table-scroll"><table><thead><tr>${headers.map(t=>`<th>${t}</th>`).join('')}</tr></thead><tbody>${body||`<tr><td colspan="${headers.length}">No hay registros para mostrar.</td></tr>`}</tbody></table></div>`;
 const nav=document.querySelector('nav');
 for(const view of ['customers','renewals','deliveries','history']){const b=document.createElement('button');b.dataset.view=view;b.dataset.admin='';b.textContent=labels[view];nav.insertBefore(b,nav.querySelector('[data-view="events"]'));}
 let query='';
 const dialog=document.createElement('dialog');dialog.className='operations-dialog';document.body.append(dialog);
 const open=(title,content)=>{dialog.innerHTML=`<div class="dialog-head"><h2>${title}</h2><button type="button" data-operations-close aria-label="Cerrar">✕</button></div>${content}`;dialog.showModal();};
 document.addEventListener('submit',async e=>{
  if(e.target.id!=='customer-search')return;e.preventDefault();query=e.target.elements.q.value;await render();
 });
 document.addEventListener('click',async e=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.hasAttribute('data-operations-close')){dialog.close();return;}
  try{
   if(b.dataset.customerJid){
    const data=await api('/operations/customer?'+new URLSearchParams({instance:b.dataset.customerInstance,jid:b.dataset.customerJid}));
    open('Ficha del cliente',customerDetail(data,b.dataset.customerJid,{escape:h,date,money,badge,table}));
   }
   if(b.dataset.retryDelivery){
    open('Reintento controlado',`<form id="delivery-retry"><p>Revisa primero el chat del bot de ventas. Un fallo de conexión no demuestra que el cliente no recibió el mensaje.</p><p>Se conservarán la cuenta, el inicio y el vencimiento. No se cobrará otra vez.</p><label>Motivo<textarea name="reason" required minlength="8" maxlength="500"></textarea></label><label class="check"><input name="verified_not_received" type="checkbox" required> Revisé el chat y confirmé que el cliente no recibió esta entrega.</label><p class="danger" role="alert"></p><button class="primary" type="submit">Programar un reintento</button></form>`);
    dialog.querySelector('form').onsubmit=async ev=>{ev.preventDefault();const f=ev.target,submit=f.querySelector('[type=submit]');submit.disabled=true;try{await api('/operations/deliveries/'+b.dataset.retryDelivery+'/retry','POST',{reason:f.elements.reason.value,verified_not_received:f.elements.verified_not_received.checked});dialog.close();notify('Reintento programado y registrado en el historial.');await render();}catch(err){f.querySelector('[role=alert]').textContent=err.message;}finally{submit.disabled=false;}};
   }
  }catch(err){notify(err.message);}
 });
 return async view=>{
  if(!labels[view]||getUser()?.role!=='ADMIN')return null;
  if(view==='overview'){
   const [m,bots]=await Promise.all([api('/operations/overview'),api('/instances')]);
   const metrics=[['Pagos pendientes',m.pending_payments,'orders'],['Entregas en cola',m.queued,'deliveries'],['Requieren revisión',m.review,'deliveries'],['Vencen en 72 horas',m.expiring,'customers'],['Stock válido disponible',m.available,'inventory'],['Clientes por bot',m.customers,'customers']];
   return head(view,'Prioridades reales de tu operación. Las renovaciones no duplican el contador de cuentas.')+`<section class="workspace-metrics">${metrics.map(([label,value,target])=>`<button class="workspace-metric" data-view="${target}"><span>${label}</span><strong>${value}</strong><small>Ver detalle ↗</small></button>`).join('')}</section><div class="columns">${['SALES','CODES'].map(p=>`<section class="card"><p class="eyebrow">${p==='SALES'?'VENTAS Y RENOVACIONES':'CÓDIGOS · ACCESO SEPARADO'}</p><h3>${p==='SALES'?'Bot de ventas':'Bot de códigos'}</h3>${bots.filter(i=>i.purpose===p).map(i=>`<div class="event"><div><strong>${h(i.name)}</strong><p>${h(i.phone||'Sin vincular')}</p></div><span class="pill ${i.status==='CONNECTED'&&i.worker_online?'good':'bad'}">${i.status==='CONNECTED'&&i.worker_online?'Conectado':'Requiere atención'}</span></div>`).join('')||'<p>No hay conexiones asignadas.</p>'}<button data-view="connections">Gestionar conexión</button></section>`).join('')}</div>`;
  }
  if(view==='customers'){
   const [customers,bots]=await Promise.all([api('/operations/customers?'+new URLSearchParams({q:query})),api('/instances')]);
   return head(view,'Administra tus clientes y consulta sus cuentas, vigencia y operaciones.')+clientsReference(customers,bots,query,{h,date});
  }
  if(view==='renewals'){
   const orders=await api('/operations/renewals');
   return head(view,'Una renovación por correo y plataforma. Confirma el pago y el servicio antes de aprobar.')+table(['Cliente / bot','Cuenta','Importe / estado','Vencimiento actual','Corte propuesto / confirmado','Acciones'],orders.map(o=>`<tr><td>${h(o.customer)}<br>${h(o.bot)}<br><small>${h(o.id)}</small></td><td>${h(o.product_name)}<br>${h(o.email||'Sin cuenta')}</td><td>${money(o.price_cents)}<br>${badge(o.status)}</td><td>${dt(o.current_expiry)}</td><td>${dt(o.proposed_expiry)}<br><small>${o.status==='PENDING'?'Estimado al aprobar':'Período registrado'}</small></td><td>${o.has_receipt?`<a href="/api/orders/${o.id}/receipt" target="_blank" rel="noopener">Ver comprobante</a><br>`:'Sin comprobante<br>'}${o.status==='PENDING'?`<button data-approve="${o.id}">Verificar y aprobar</button><button data-reject="${o.id}">Rechazar</button>`:''}</td></tr>`).join(''))+'<p class="section-note">Últimas 300 renovaciones. El corte propuesto se recalcula al aprobar.</p>';
  }
  if(view==='deliveries'){
   const orders=await api('/operations/deliveries');
   return head(view,'Gestiona la cola de entregas comerciales. Envío aceptado no significa lectura del cliente.')+deliveriesReference(orders,{h,date});
  }
  const entries=await api('/operations/history');
  const actions={'order.approved':'Pago aprobado','order.external_registered':'Venta anterior registrada','order.rejected':'Pedido rechazado','renewal.approved':'Renovación aprobada','delivery.retry_requested':'Reintento solicitado','delivery.sent':'Entrega enviada','delivery.review':'Entrega en revisión','stock.created':'Cuenta cargada','stock.disabled':'Cuenta retirada'};
  return head(view,'Fecha, responsable y detalles de los movimientos. Sin contraseñas ni credenciales.')+table(['Fecha','Responsable','Acción','Detalle'],entries.map(e=>`<tr><td>${dt(e.created_at)}</td><td>${h(e.email||'Sistema / bot')}</td><td>${h(actions[e.action]||e.action)}</td><td>${Object.entries(e.details).map(([k,v])=>`${h(k)}: ${h(v)}`).join('<br>')||'—'}</td></tr>`).join(''))+'<p class="section-note">Últimos 300 movimientos comerciales. Los registros antiguos se conservan.</p>';
 };
}
import {customerDetail,deliveryNotice} from './customer-detail.js?v=1.0.0';
import {clientsReference} from './clients-reference.js?v=1.0.0';
import {deliveriesReference} from './deliveries-reference.js?v=1.0.0';
